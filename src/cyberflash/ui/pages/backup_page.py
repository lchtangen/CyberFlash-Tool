"""Backup & Restore page — full / nandroid / partition-level backups.

Provides a UI for creating device backups, browsing backup history,
and restoring from a previously saved backup archive.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.cyber_card import CyberCard
from cyberflash.utils.platform_utils import get_app_data_dir
from cyberflash.workers.backup_worker import BackupWorker

logger = logging.getLogger(__name__)

_DEFAULT_BACKUP_DIR = get_app_data_dir() / "backups"


# ── Helper widgets ───────────────────────────────────────────────────────────


class _BackupTypeCard(CyberCard):
    """Card showing a backup type option with description."""

    selected = Signal(str)

    def __init__(
        self,
        type_id: str,
        title: str,
        description: str,
        icon_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._type_id = type_id
        layout = self.card_layout()

        header = QHBoxLayout()
        icon = QLabel(icon_text)
        icon.setObjectName("backupTypeIcon")
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(icon)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("kvValue")
        header.addWidget(title_lbl)
        header.addStretch()

        self._radio = QRadioButton()
        self._radio.toggled.connect(self._on_toggled)
        header.addWidget(self._radio)
        layout.addLayout(header)

        desc = QLabel(description)
        desc.setObjectName("subtitleLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

    def _on_toggled(self, checked: bool) -> None:
        if checked:
            self.selected.emit(self._type_id)

    def radio(self) -> QRadioButton:
        return self._radio


class _BackupHistoryItem(CyberCard):
    """A single backup entry in the history list."""

    restore_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(
        self,
        name: str,
        backup_type: str,
        date_str: str,
        size_str: str,
        path: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        layout = self.card_layout()

        row1 = QHBoxLayout()
        name_lbl = QLabel(name)
        name_lbl.setObjectName("kvValue")
        row1.addWidget(name_lbl)
        row1.addStretch()
        badge = CyberBadge(backup_type, "info")
        row1.addWidget(badge)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        date_lbl = QLabel(f"\U0001f4c5 {date_str}")
        date_lbl.setObjectName("subtitleLabel")
        row2.addWidget(date_lbl)
        row2.addStretch()
        size_lbl = QLabel(f"\U0001f4be {size_str}")
        size_lbl.setObjectName("subtitleLabel")
        row2.addWidget(size_lbl)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addStretch()
        delete_btn = QPushButton("Delete")
        delete_btn.setObjectName("dangerButton")
        delete_btn.setFixedWidth(80)
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self._path))
        row3.addWidget(delete_btn)
        restore_btn = QPushButton("Restore")
        restore_btn.setObjectName("primaryButton")
        restore_btn.setFixedWidth(100)
        restore_btn.clicked.connect(lambda: self.restore_requested.emit(self._path))
        row3.addWidget(restore_btn)
        layout.addLayout(row3)


class _NoDeviceOverlay(QWidget):
    """Displayed when no device is connected."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        icon = QLabel("\U0001f4f1")
        icon.setObjectName("emptyIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        title = QLabel("No Device Connected")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = QLabel(
            "Connect an Android device via USB to create and restore backups.\n"
            "Device must be in ADB mode for full backups, or bootloader\n"
            "mode for partition-level operations."
        )
        hint.setObjectName("subtitleLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)


# ── Main page ────────────────────────────────────────────────────────────────


class BackupPage(QWidget):
    """Full backup & restore page with type selection, options, and history."""

    def __init__(
        self,
        device_service=None,
        parent: QWidget | None = None,
        *,
        ai_service: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._device_service = device_service
        self._ai_service = ai_service
        self._selected_type: str = "full"
        self._backup_dir: Path = _DEFAULT_BACKUP_DIR
        self._backup_thread: QThread | None = None
        self._backup_worker: BackupWorker | None = None
        self._setup_ui()

        if device_service is not None:
            device_service.device_list_updated.connect(self._on_devices_updated)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # ── Header ───────────────────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("Backup & Restore")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        subtitle = QLabel("Create, manage, and restore device backups")
        subtitle.setObjectName("pageSubtitle")
        header.addWidget(subtitle)
        header.addStretch()
        self._device_badge = CyberBadge("No Device", "neutral")
        header.addWidget(self._device_badge)
        root.addLayout(header)

        # ── No-device overlay ────────────────────────────────────────────
        self._no_device = _NoDeviceOverlay()
        root.addWidget(self._no_device)

        # ── Content (scrollable) ─────────────────────────────────────────
        self._content = QWidget()
        self._content.setVisible(False)
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_inner = QWidget()
        sl = QVBoxLayout(scroll_inner)
        sl.setAlignment(Qt.AlignmentFlag.AlignTop)
        sl.setSpacing(16)

        # ── Backup Type cards ────────────────────────────────────────────
        type_label = QLabel("Backup Type")
        type_label.setObjectName("cardHeader")
        sl.addWidget(type_label)

        types_row = QHBoxLayout()
        types_row.setSpacing(12)

        self._full_card = _BackupTypeCard(
            "full",
            "Full Backup",
            "Complete ADB backup including apps, data, and shared storage. Requires ADB mode.",
            "\U0001f4e6",
        )
        self._full_card.radio().setChecked(True)
        self._full_card.selected.connect(self._on_type_selected)
        types_row.addWidget(self._full_card)

        self._nandroid_card = _BackupTypeCard(
            "nandroid",
            "Nandroid Backup",
            "Full partition-level backup via custom recovery "
            "(TWRP / OrangeFox). Requires custom recovery.",
            "\U0001f527",
        )
        self._nandroid_card.selected.connect(self._on_type_selected)
        types_row.addWidget(self._nandroid_card)

        self._partition_card = _BackupTypeCard(
            "partition",
            "Partition Backup",
            "Selective partition dump (boot, recovery, system). "
            "Works in bootloader / fastboot mode.",
            "\U0001f4bf",
        )
        self._partition_card.selected.connect(self._on_type_selected)
        types_row.addWidget(self._partition_card)
        sl.addLayout(types_row)

        # ── Backup Options ───────────────────────────────────────────────
        options_group = QGroupBox("Backup Options")
        og = QGridLayout(options_group)
        og.setSpacing(10)

        og.addWidget(QLabel("Destination:"), 0, 0)
        dest_row = QHBoxLayout()
        self._dest_input = QLineEdit(str(self._backup_dir))
        self._dest_input.setReadOnly(True)
        dest_row.addWidget(self._dest_input)
        browse_btn = QPushButton("Browse\u2026")
        browse_btn.clicked.connect(self._browse_destination)
        dest_row.addWidget(browse_btn)
        og.addLayout(dest_row, 0, 1)

        og.addWidget(QLabel("Backup Name:"), 1, 0)
        self._name_input = QLineEdit()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._name_input.setPlaceholderText(f"backup_{ts}")
        og.addWidget(self._name_input, 1, 1)

        og.addWidget(QLabel("Compression:"), 2, 0)
        self._compress_combo = QComboBox()
        self._compress_combo.addItems(["gzip (recommended)", "zstd (fast)", "None"])
        og.addWidget(self._compress_combo, 2, 1)

        og.addWidget(QLabel("Include:"), 3, 0, Qt.AlignmentFlag.AlignTop)
        inc_col = QVBoxLayout()
        self._cb_apps = QCheckBox("Installed applications")
        self._cb_apps.setChecked(True)
        inc_col.addWidget(self._cb_apps)
        self._cb_data = QCheckBox("App data & settings")
        self._cb_data.setChecked(True)
        inc_col.addWidget(self._cb_data)
        self._cb_storage = QCheckBox("Shared / internal storage")
        inc_col.addWidget(self._cb_storage)
        self._cb_system = QCheckBox("System partition (requires root)")
        inc_col.addWidget(self._cb_system)
        og.addLayout(inc_col, 3, 1)
        sl.addWidget(options_group)

        # ── Partition selector (partition type only) ─────────────────────
        self._partition_group = QGroupBox("Partitions to Backup")
        pg = QVBoxLayout(self._partition_group)
        self._part_checks: dict[str, QCheckBox] = {}
        for pname in ["boot", "recovery", "system", "vendor", "dtbo", "vbmeta", "modem"]:
            cb = QCheckBox(pname)
            if pname in ("boot", "recovery"):
                cb.setChecked(True)
            self._part_checks[pname] = cb
            pg.addWidget(cb)
        self._partition_group.setVisible(False)
        sl.addWidget(self._partition_group)

        # ── Progress card ────────────────────────────────────────────────
        progress_card = CyberCard()
        pc = progress_card.card_layout()
        prog_h = QLabel("Progress")
        prog_h.setObjectName("cardHeader")
        pc.addWidget(prog_h)
        self._progress_bar = QProgressBar()
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("%p%  \u2014  %v / %m MB")
        pc.addWidget(self._progress_bar)
        self._progress_label = QLabel("Ready to backup")
        self._progress_label.setObjectName("subtitleLabel")
        pc.addWidget(self._progress_label)
        sl.addWidget(progress_card)

        # ── Action buttons ───────────────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.addStretch()
        self._abort_btn = QPushButton("Abort")
        self._abort_btn.setObjectName("dangerButton")
        self._abort_btn.setFixedWidth(100)
        self._abort_btn.setVisible(False)
        action_row.addWidget(self._abort_btn)
        self._backup_btn = QPushButton("\u25b6  Start Backup")
        self._backup_btn.setObjectName("primaryButton")
        self._backup_btn.setFixedWidth(160)
        self._backup_btn.clicked.connect(self._start_backup)
        action_row.addWidget(self._backup_btn)
        sl.addLayout(action_row)

        # ── Backup History ───────────────────────────────────────────────
        hist_hdr = QHBoxLayout()
        ht = QLabel("Backup History")
        ht.setObjectName("cardHeader")
        hist_hdr.addWidget(ht)
        hist_hdr.addStretch()
        refresh_btn = QPushButton("\u21bb Refresh")
        refresh_btn.setFixedWidth(90)
        refresh_btn.clicked.connect(self._refresh_history)
        hist_hdr.addWidget(refresh_btn)
        sl.addLayout(hist_hdr)

        self._history_layout = QVBoxLayout()
        self._history_layout.setSpacing(8)
        self._empty_history = QLabel("No backups found. Create your first backup above.")
        self._empty_history.setObjectName("subtitleLabel")
        self._empty_history.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._history_layout.addWidget(self._empty_history)
        sl.addLayout(self._history_layout)
        sl.addStretch()

        scroll.setWidget(scroll_inner)
        content_layout.addWidget(scroll)
        root.addWidget(self._content)

        self._refresh_history()

    # ── Slots ────────────────────────────────────────────────────────────

    @Slot(str)
    def _on_type_selected(self, type_id: str) -> None:
        self._selected_type = type_id
        self._partition_group.setVisible(type_id == "partition")
        is_full = type_id == "full"
        self._cb_apps.setVisible(is_full)
        self._cb_data.setVisible(is_full)
        self._cb_storage.setVisible(is_full)
        self._cb_system.setVisible(is_full or type_id == "nandroid")

    def _browse_destination(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Backup Destination",
            str(self._backup_dir),
        )
        if path:
            self._backup_dir = Path(path)
            self._dest_input.setText(path)

    def _start_backup(self) -> None:
        """Launch BackupWorker on a QThread."""
        # Resolve device serial
        serial = ""
        if self._device_service is not None:
            dev = self._device_service.selected_device
            if dev:
                serial = dev.serial
        if not serial:
            self._progress_label.setText("No device selected — connect a device first.")
            return

        name = (
            self._name_input.text().strip() or f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )

        partitions_selected: list[str] = []
        if self._selected_type == "full":
            mode = "adb_backup"
            output_path = str(self._backup_dir / f"{name}.ab")
        elif self._selected_type == "nandroid":
            # Nandroid-style: dump key partitions via root dd
            mode = "partition_dump"
            output_path = str(self._backup_dir / name)
            partitions_selected = [
                "boot",
                "recovery",
                "system",
                "vendor",
                "dtbo",
                "vbmeta",
            ]
        else:
            # Selective partition dump
            mode = "partition_dump"
            output_path = str(self._backup_dir / name)
            partitions_selected = [
                pname for pname, cb in self._part_checks.items() if cb.isChecked()
            ]
            if not partitions_selected:
                self._progress_label.setText("Select at least one partition to backup.")
                return

        logger.info("Starting backup: mode=%s serial=%s dest=%s", mode, serial, output_path)

        self._backup_worker = BackupWorker(
            serial,
            mode,
            output_path,
            include_apks=self._cb_apps.isChecked(),
            include_shared=self._cb_storage.isChecked(),
            include_all=True,
            partitions=partitions_selected,
        )
        self._backup_thread = QThread(self)
        self._backup_worker.moveToThread(self._backup_thread)

        self._backup_thread.started.connect(self._backup_worker.start)
        self._backup_worker.progress.connect(self._on_backup_progress)
        self._backup_worker.log_line.connect(self._on_backup_log)
        self._backup_worker.backup_complete.connect(self._on_backup_complete)
        self._backup_worker.error.connect(self._on_backup_error)
        self._backup_worker.finished.connect(self._backup_thread.quit)
        self._backup_worker.finished.connect(self._backup_worker.deleteLater)
        self._backup_thread.finished.connect(self._backup_thread.deleteLater)

        self._abort_btn.clicked.connect(self._abort_backup)
        self._backup_btn.setEnabled(False)
        self._abort_btn.setVisible(True)
        self._progress_label.setText("Starting backup…")
        self._progress_bar.setRange(0, 0)

        self._backup_thread.start()

    def _abort_backup(self) -> None:
        if self._backup_worker:
            self._backup_worker.abort()

    @Slot(int, int)
    def _on_backup_progress(self, current: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(current)
        else:
            self._progress_bar.setRange(0, 0)

    @Slot(str)
    def _on_backup_log(self, line: str) -> None:
        self._progress_label.setText(line[:120])

    @Slot(str)
    def _on_backup_complete(self, output_path: str) -> None:
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(1)
        self._progress_label.setText(f"Backup saved: {Path(output_path).name}")
        self._backup_btn.setEnabled(True)
        self._abort_btn.setVisible(False)
        self._refresh_history()

    @Slot(str)
    def _on_backup_error(self, message: str) -> None:
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(0)
        self._progress_label.setText(f"Error: {message}")
        self._backup_btn.setEnabled(True)
        self._abort_btn.setVisible(False)

    def _refresh_history(self) -> None:
        """Scan backup directory and populate history cards."""
        while self._history_layout.count() > 1:
            item = self._history_layout.takeAt(1)
            if item and item.widget():
                item.widget().deleteLater()

        if not self._backup_dir.exists():
            self._empty_history.setVisible(True)
            return

        entries = sorted(
            self._backup_dir.iterdir(),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        found = 0
        for entry in entries[:20]:
            if entry.is_dir() or entry.suffix in (".ab", ".tar", ".gz", ".zst", ".img"):
                sz = entry.stat().st_size / (1024 * 1024)
                size_s = f"{sz:.1f} MB" if sz < 1024 else f"{sz / 1024:.2f} GB"
                mtime = datetime.fromtimestamp(entry.stat().st_mtime)
                date_s = mtime.strftime("%Y-%m-%d %H:%M")
                btype = "Full" if entry.suffix == ".ab" else "Partition"
                card = _BackupHistoryItem(entry.name, btype, date_s, size_s, str(entry))
                card.restore_requested.connect(self._on_restore)
                card.delete_requested.connect(self._on_delete)
                self._history_layout.addWidget(card)
                found += 1
        self._empty_history.setVisible(found == 0)

    @Slot(str)
    def _on_restore(self, path: str) -> None:
        """Restore a backup using ADB restore for .ab files."""
        from PySide6.QtWidgets import QMessageBox

        p = Path(path)
        if not p.exists():
            QMessageBox.warning(self, "Not Found", f"Backup file not found:\n{path}")
            return

        reply = QMessageBox.question(
            self,
            "Restore Backup",
            f"Restore from {p.name}?\n\n"
            "This will overwrite current device data.\n"
            "You may need to confirm on the device screen.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        serial = ""
        if self._device_service is not None:
            dev = self._device_service.selected_device
            if dev:
                serial = dev.serial
        if not serial:
            self._progress_label.setText("No device connected for restore.")
            return

        logger.info("Restoring from: %s", path)
        self._progress_label.setText(f"Restoring from {p.name}\u2026")
        self._progress_bar.setRange(0, 0)
        self._backup_btn.setEnabled(False)

        self._backup_worker = BackupWorker(serial, "adb_restore", path)
        self._backup_thread = QThread(self)
        self._backup_worker.moveToThread(self._backup_thread)
        self._backup_thread.started.connect(self._backup_worker.start)
        self._backup_worker.progress.connect(self._on_backup_progress)
        self._backup_worker.log_line.connect(self._on_backup_log)
        self._backup_worker.backup_complete.connect(self._on_restore_complete)
        self._backup_worker.error.connect(self._on_backup_error)
        self._backup_worker.finished.connect(self._backup_thread.quit)
        self._backup_worker.finished.connect(self._backup_worker.deleteLater)
        self._backup_thread.finished.connect(self._backup_thread.deleteLater)
        self._backup_thread.start()

    @Slot(str)
    def _on_restore_complete(self, path: str) -> None:
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(1)
        self._progress_label.setText(f"Restore complete: {Path(path).name}")
        self._backup_btn.setEnabled(True)

    @Slot(str)
    def _on_delete(self, path: str) -> None:
        """Delete a backup file/directory after confirmation."""
        import shutil

        from PySide6.QtWidgets import QMessageBox

        p = Path(path)
        if not p.exists():
            self._refresh_history()
            return

        reply = QMessageBox.warning(
            self,
            "Delete Backup",
            f"Permanently delete {p.name}?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            logger.info("Deleted backup: %s", path)
            self._progress_label.setText(f"Deleted: {p.name}")
        except Exception as exc:
            logger.error("Failed to delete backup: %s", exc)
            QMessageBox.critical(self, "Delete Failed", f"Could not delete:\n{exc}")
        self._refresh_history()

    @Slot(list)
    def _on_devices_updated(self, devices: list) -> None:
        has = len(devices) > 0
        self._no_device.setVisible(not has)
        self._content.setVisible(has)
        if has:
            d = devices[0]
            name = getattr(d, "display_name", getattr(d, "serial", "Device"))
            self._device_badge.set_text_and_variant(f"\u2713 {name}", "success")
        else:
            self._device_badge.set_text_and_variant("No Device", "neutral")
