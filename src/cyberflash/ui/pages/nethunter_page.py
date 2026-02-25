"""NetHunter page — Kali NetHunter installation and management.

Provides UI for downloading NetHunter builds, installing (kernel + chroot),
selecting release channels, managing the chroot filesystem, and monitoring
NetHunter component status.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.tool_manager import ToolManager
from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.cyber_card import CyberCard
from cyberflash.workers.base_worker import BaseWorker
from cyberflash.workers.download_worker import DownloadWorker

logger = logging.getLogger(__name__)

# ── Download destination ──────────────────────────────────────────────────────

_NH_DOWNLOAD_DIR = Path.home() / ".local" / "share" / "CyberFlash" / "nethunter"

# Official Kali NetHunter download mirrors
_OFFICIAL_PAGE = "https://www.kali.org/get-kali/#kali-mobile"
_MIRROR_BASE = "https://kali.download/nethunter-images/current"

# Edition → filename fragment mapping for URL building
_EDITION_FRAGMENTS: dict[str, str] = {
    "Full  (kernel + chroot + app)": "kalifs-full",
    "Lite  (no custom kernel)": "kalifs-lite",
    "Rootless  (no root required)": "rootless",
}

# Common device codename → NH build name mapping
_DEVICE_BUILD_NAMES: dict[str, str] = {
    "guacamole": "oneplus7pro",
    "hotdog": "oneplus7tpro",
    "enchilada": "oneplus6",
    "fajita": "oneplus6t",
    "coral": "pixel4xl",
    "flame": "pixel4",
    "sunfish": "pixel4a",
    "bramble": "pixel4a5g",
    "redfin": "pixel5",
    "barbet": "pixel5a",
    "oriole": "pixel6",
    "raven": "pixel6pro",
}


# ── NetHunter install worker ──────────────────────────────────────────────────


class _NetHunterInstallWorker(BaseWorker):
    """Sideloads a NetHunter ZIP to a device in recovery/sideload mode.

    Signals:
        log_line(str)          — one line of ADB sideload output
        progress(int, int)     — percent done, 100
        finished()             — always emitted last (from BaseWorker)
        error(str)             — emitted on failure (from BaseWorker)
    """

    log_line = Signal(str)
    progress = Signal(int, int)

    def __init__(self, serial: str, zip_path: str) -> None:
        super().__init__()
        self._serial = serial
        self._zip_path = zip_path
        self._aborted = False

    def abort(self) -> None:
        self._aborted = True

    @Slot()
    def start(self) -> None:
        try:
            self._run_sideload()
        except Exception as exc:
            logger.exception("NetHunter install error")
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    def _run_sideload(self) -> None:
        if not Path(self._zip_path).exists():
            self.error.emit(f"ZIP not found: {self._zip_path}")
            return

        adb_bin = ToolManager.adb_cmd()
        cmd = [*adb_bin, "-s", self._serial, "sideload", self._zip_path]
        self.log_line.emit(f"Running: {' '.join(cmd)}")
        self.log_line.emit("Device must be in recovery / sideload mode (e.g. TWRP).")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            self.error.emit("ADB binary not found. Is it installed?")
            return

        pct_re = re.compile(r"(\d+)%")
        for line in proc.stdout:  # type: ignore[union-attr]
            if self._aborted:
                proc.terminate()
                self.log_line.emit("Aborted by user.")
                return
            line = line.rstrip()
            if line:
                self.log_line.emit(line)
            m = pct_re.search(line)
            if m:
                self.progress.emit(int(m.group(1)), 100)

        proc.wait()
        if proc.returncode == 0:
            self.progress.emit(100, 100)
            self.log_line.emit("✓ Sideload complete.")
        else:
            self.error.emit(f"ADB sideload exited with code {proc.returncode}")


# ── Status overview card ──────────────────────────────────────────────────────


class _NhStatusCard(CyberCard):
    """NetHunter installation status overview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self.card_layout()

        hdr = QHBoxLayout()
        title = QLabel("NetHunter Status")
        title.setObjectName("cardHeader")
        hdr.addWidget(title)
        hdr.addStretch()
        self._badge = CyberBadge("Not Installed", "neutral")
        hdr.addWidget(self._badge)
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        layout.addWidget(sep)

        grid = QGridLayout()
        grid.setSpacing(8)
        self._labels: dict[str, QLabel] = {}
        for i, (text, key) in enumerate(
            [
                ("Kernel", "kernel"),
                ("Chroot", "chroot"),
                ("NH App", "app"),
                ("NH Store", "store"),
                ("WiFi Adapter Support", "wifi"),
                ("HID Support", "hid"),
            ]
        ):
            k = QLabel(text)
            k.setObjectName("kvKey")
            v = QLabel("\u2014")
            v.setObjectName("kvValue")
            self._labels[key] = v
            grid.addWidget(k, i, 0)
            grid.addWidget(v, i, 1)
        layout.addLayout(grid)

    def set_status(self, installed: bool | None = None, **fields: str) -> None:
        if installed is True:
            self._badge.set_text_and_variant("Installed", "success")
        elif installed is False:
            self._badge.set_text_and_variant("Not Installed", "warning")
        else:
            self._badge.set_text_and_variant("Unknown", "neutral")
        for key, val in fields.items():
            if key in self._labels:
                self._labels[key].setText(val)


# ── Download tab ──────────────────────────────────────────────────────────────


class _DownloadTab(QWidget):
    """Download NetHunter builds from official Kali mirrors.

    Signals:
        download_ready(path)  — emitted when a ZIP finishes downloading;
                                parent uses this to pre-fill the Install tab.
    """

    download_ready = Signal(str)  # local path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._worker: DownloadWorker | None = None
        self._thread: QThread | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # ── Info ─────────────────────────────────────────────────────────────
        info_card = CyberCard()
        ic = info_card.card_layout()
        ih = QLabel("Official NetHunter Builds")
        ih.setObjectName("cardHeader")
        ic.addWidget(ih)
        info_lbl = QLabel(
            "Download NetHunter directly from the official Kali mirror. "
            "Select your device architecture and edition below, then enter "
            "the download URL from the Kali NetHunter download page."
        )
        info_lbl.setObjectName("subtitleLabel")
        info_lbl.setWordWrap(True)
        ic.addWidget(info_lbl)
        open_btn = QPushButton("\U0001f310  Open Official Downloads Page")
        open_btn.setFixedWidth(260)
        open_btn.clicked.connect(self._open_official_page)
        ic.addWidget(open_btn)
        layout.addWidget(info_card)

        # ── Build selector ────────────────────────────────────────────────────
        sel_group = QGroupBox("Build Selection")
        sg = QGridLayout(sel_group)
        sg.setSpacing(8)

        sg.addWidget(QLabel("Architecture:"), 0, 0)
        self._arch_combo = QComboBox()
        self._arch_combo.addItems(["arm64", "armhf"])
        sg.addWidget(self._arch_combo, 0, 1)

        sg.addWidget(QLabel("Edition:"), 1, 0)
        self._edition_combo = QComboBox()
        for name in _EDITION_FRAGMENTS:
            self._edition_combo.addItem(name)
        sg.addWidget(self._edition_combo, 1, 1)

        sg.addWidget(QLabel("Device (optional):"), 2, 0)
        self._device_combo = QComboBox()
        self._device_combo.setEditable(True)
        self._device_combo.addItem("generic")
        for codename, build_name in _DEVICE_BUILD_NAMES.items():
            self._device_combo.addItem(f"{codename}  →  {build_name}", userData=build_name)
        sg.addWidget(self._device_combo, 2, 1)

        layout.addWidget(sel_group)

        # ── URL input ─────────────────────────────────────────────────────────
        url_group = QGroupBox("Download URL")
        ug = QVBoxLayout(url_group)
        url_hint = QLabel(
            "Paste a direct download URL from the Kali NetHunter page, "
            "or browse the mirror directory linked above."
        )
        url_hint.setObjectName("subtitleLabel")
        url_hint.setWordWrap(True)
        ug.addWidget(url_hint)

        url_row = QHBoxLayout()
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText(
            "https://kali.download/nethunter-images/current/nethunter-…-kalifs-full.zip"
        )
        url_row.addWidget(self._url_input)
        self._dl_btn = QPushButton("\u2913  Download")
        self._dl_btn.setObjectName("primaryButton")
        self._dl_btn.setFixedWidth(120)
        self._dl_btn.clicked.connect(self._start_download)
        url_row.addWidget(self._dl_btn)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(80)
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._cancel_download)
        url_row.addWidget(self._cancel_btn)
        ug.addLayout(url_row)
        layout.addWidget(url_group)

        # ── Progress ──────────────────────────────────────────────────────────
        prog_card = CyberCard()
        pc = prog_card.card_layout()

        prog_hdr = QHBoxLayout()
        prog_hdr.addWidget(QLabel("Download Progress"))
        self._speed_lbl = QLabel("")
        self._speed_lbl.setObjectName("subtitleLabel")
        prog_hdr.addStretch()
        prog_hdr.addWidget(self._speed_lbl)
        pc.addLayout(prog_hdr)

        self._dl_bar = QProgressBar()
        self._dl_bar.setValue(0)
        self._dl_bar.setTextVisible(False)
        self._dl_bar.setFixedHeight(8)
        pc.addWidget(self._dl_bar)

        self._dl_status = QLabel("No active download")
        self._dl_status.setObjectName("subtitleLabel")
        pc.addWidget(self._dl_status)

        layout.addWidget(prog_card)

        # ── Downloaded files ──────────────────────────────────────────────────
        files_card = CyberCard()
        fc = files_card.card_layout()
        fh = QHBoxLayout()
        fh.addWidget(QLabel("Downloaded Files"))
        self._refresh_btn = QPushButton("\u21bb  Refresh")
        self._refresh_btn.setFixedWidth(90)
        self._refresh_btn.clicked.connect(self._refresh_file_list)
        fh.addStretch()
        fh.addWidget(self._refresh_btn)
        fc.addLayout(fh)

        self._file_list = QTextEdit()
        self._file_list.setReadOnly(True)
        self._file_list.setFixedHeight(100)
        self._file_list.setPlaceholderText("No NetHunter ZIPs downloaded yet.")
        fc.addWidget(self._file_list)

        use_row = QHBoxLayout()
        use_row.addStretch()
        self._use_btn = QPushButton("Use Selected File in Installer \u2192")
        self._use_btn.setObjectName("primaryButton")
        self._use_btn.setEnabled(False)
        self._use_btn.clicked.connect(self._emit_selected_file)
        use_row.addWidget(self._use_btn)
        fc.addLayout(use_row)

        layout.addWidget(files_card)
        layout.addStretch()

        self._refresh_file_list()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _open_official_page(self) -> None:
        QDesktopServices.openUrl(QUrl(_OFFICIAL_PAGE))

    def _start_download(self) -> None:
        url = self._url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Please enter a download URL.")
            return
        if not url.startswith(("http://", "https://")):
            QMessageBox.warning(self, "Invalid URL", "URL must start with http:// or https://")
            return

        filename = url.split("/")[-1] or "nethunter.zip"
        dest = _NH_DOWNLOAD_DIR / filename

        self._worker = DownloadWorker(url, dest)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)

        self._worker.progress.connect(self._on_progress)
        self._worker.speed_update.connect(self._on_speed)
        self._worker.download_complete.connect(self._on_complete)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._dl_btn.setEnabled(False)
        self._cancel_btn.setVisible(True)
        self._dl_status.setText(f"Downloading {filename}…")
        self._dl_bar.setRange(0, 0)
        self._thread.start()

    def _cancel_download(self) -> None:
        if self._worker:
            self._worker.abort()
        self._dl_status.setText("Cancelled.")
        self._dl_bar.setRange(0, 100)
        self._dl_bar.setValue(0)
        self._dl_btn.setEnabled(True)
        self._cancel_btn.setVisible(False)

    @Slot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._dl_bar.setRange(0, total)
            self._dl_bar.setValue(done)
            pct = int(done / total * 100)
            done_mb = done / 1_048_576
            total_mb = total / 1_048_576
            self._dl_status.setText(f"{pct}%  —  {done_mb:.1f} / {total_mb:.1f} MB")
        else:
            self._dl_bar.setRange(0, 0)
            done_mb = done / 1_048_576
            self._dl_status.setText(f"{done_mb:.1f} MB downloaded…")

    @Slot(float)
    def _on_speed(self, bps: float) -> None:
        if bps >= 1_048_576:
            self._speed_lbl.setText(f"{bps / 1_048_576:.1f} MB/s")
        else:
            self._speed_lbl.setText(f"{bps / 1024:.0f} KB/s")

    @Slot(str)
    def _on_complete(self, path: str) -> None:
        self._dl_bar.setRange(0, 100)
        self._dl_bar.setValue(100)
        self._dl_status.setText(f"✓ Saved to {path}")
        self._speed_lbl.setText("")
        self._dl_btn.setEnabled(True)
        self._cancel_btn.setVisible(False)
        self._refresh_file_list()
        self.download_ready.emit(path)
        logger.info("NetHunter download complete: %s", path)

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._dl_bar.setRange(0, 100)
        self._dl_bar.setValue(0)
        self._dl_status.setText(f"Error: {msg}")
        self._speed_lbl.setText("")
        self._dl_btn.setEnabled(True)
        self._cancel_btn.setVisible(False)
        logger.error("NetHunter download error: %s", msg)

    def _refresh_file_list(self) -> None:
        _NH_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        zips = sorted(_NH_DOWNLOAD_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        if zips:
            lines = []
            for p in zips:
                size_mb = p.stat().st_size / 1_048_576
                lines.append(f"{p.name}  ({size_mb:.0f} MB)")
            self._file_list.setPlainText("\n".join(lines))
            self._use_btn.setEnabled(True)
        else:
            self._file_list.setPlaceholderText("No NetHunter ZIPs downloaded yet.")
            self._file_list.setPlainText("")
            self._use_btn.setEnabled(False)

    def _emit_selected_file(self) -> None:
        line = self._file_list.textCursor().block().text().strip()
        if not line:
            # Use the first/most-recent file
            zips = sorted(
                _NH_DOWNLOAD_DIR.glob("*.zip"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if zips:
                self.download_ready.emit(str(zips[0]))
        else:
            filename = line.split("  ")[0]
            path = _NH_DOWNLOAD_DIR / filename
            if path.exists():
                self.download_ready.emit(str(path))

    def set_device_hint(self, codename: str) -> None:
        """Pre-select a device in the combo if it matches a known NH build name."""
        for i in range(self._device_combo.count()):
            if codename in (self._device_combo.itemText(i)):
                self._device_combo.setCurrentIndex(i)
                break


# ── Installer tab ─────────────────────────────────────────────────────────────


class _InstallerTab(QWidget):
    """NetHunter ZIP installer via ADB sideload."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._serial: str = ""
        self._install_worker: _NetHunterInstallWorker | None = None
        self._install_thread: QThread | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # ── Instructions ──────────────────────────────────────────────────────
        info_card = CyberCard()
        ic = info_card.card_layout()
        ih = QLabel("Install NetHunter via ADB Sideload")
        ih.setObjectName("cardHeader")
        ic.addWidget(ih)
        steps_lbl = QLabel(
            "1. Boot your device into recovery mode (e.g. TWRP).\n"
            "2. Select the NetHunter ZIP below (downloaded or local).\n"
            "3. Click Install — CyberFlash will ADB-sideload the ZIP.\n"
            "4. After install, reboot to system and launch the NetHunter app."
        )
        steps_lbl.setObjectName("subtitleLabel")
        steps_lbl.setWordWrap(True)
        ic.addWidget(steps_lbl)

        reboot_row = QHBoxLayout()
        reboot_row.addStretch()
        self._reboot_recovery_btn = QPushButton("\U0001f501  Reboot to Recovery")
        self._reboot_recovery_btn.setFixedWidth(190)
        self._reboot_recovery_btn.setEnabled(False)
        self._reboot_recovery_btn.clicked.connect(self._reboot_to_recovery)
        reboot_row.addWidget(self._reboot_recovery_btn)
        ic.addLayout(reboot_row)
        layout.addWidget(info_card)

        # ── NetHunter ZIP ─────────────────────────────────────────────────────
        zip_group = QGroupBox("NetHunter ZIP")
        zg = QVBoxLayout(zip_group)
        zip_hint = QLabel(
            "Select the NetHunter ZIP you downloaded (from the Download tab) "
            "or browse for a local file."
        )
        zip_hint.setObjectName("subtitleLabel")
        zip_hint.setWordWrap(True)
        zg.addWidget(zip_hint)

        zip_row = QHBoxLayout()
        self._zip_input = QLineEdit()
        self._zip_input.setPlaceholderText("Select or download a NetHunter ZIP…")
        self._zip_input.setReadOnly(True)
        zip_row.addWidget(self._zip_input)
        zip_browse = QPushButton("Browse\u2026")
        zip_browse.setFixedWidth(80)
        zip_browse.clicked.connect(self._browse_zip)
        zip_row.addWidget(zip_browse)
        zg.addLayout(zip_row)
        layout.addWidget(zip_group)

        # ── Kernel ZIP (optional) ─────────────────────────────────────────────
        kernel_group = QGroupBox("Custom Kernel ZIP  (optional — Full edition only)")
        kg = QVBoxLayout(kernel_group)
        k_info = QLabel(
            "For NetHunter Full, select a NetHunter-compatible kernel ZIP. "
            "This provides WiFi injection, HID, and other advanced features. "
            "Skip for Rootless/Lite editions."
        )
        k_info.setObjectName("subtitleLabel")
        k_info.setWordWrap(True)
        kg.addWidget(k_info)

        k_row = QHBoxLayout()
        self._kernel_input = QLineEdit()
        self._kernel_input.setPlaceholderText("Select kernel ZIP (optional)\u2026")
        self._kernel_input.setReadOnly(True)
        k_row.addWidget(self._kernel_input)
        k_browse = QPushButton("Browse\u2026")
        k_browse.setFixedWidth(80)
        k_browse.clicked.connect(self._browse_kernel)
        k_row.addWidget(k_browse)
        k_clear = QPushButton("Clear")
        k_clear.setFixedWidth(60)
        k_clear.clicked.connect(lambda: self._kernel_input.clear())
        k_row.addWidget(k_clear)
        kg.addLayout(k_row)
        layout.addWidget(kernel_group)

        # ── Install progress ──────────────────────────────────────────────────
        prog_group = QGroupBox("Installation Progress")
        pg = QVBoxLayout(prog_group)

        prog_hdr_row = QHBoxLayout()
        self._install_step_lbl = QLabel("Ready")
        self._install_step_lbl.setObjectName("sectionLabel")
        prog_hdr_row.addWidget(self._install_step_lbl)
        prog_hdr_row.addStretch()
        self._install_pct_lbl = QLabel("")
        self._install_pct_lbl.setObjectName("subtitleLabel")
        prog_hdr_row.addWidget(self._install_pct_lbl)
        pg.addLayout(prog_hdr_row)

        self._install_bar = QProgressBar()
        self._install_bar.setValue(0)
        self._install_bar.setTextVisible(False)
        self._install_bar.setFixedHeight(8)
        pg.addWidget(self._install_bar)

        self._install_log = QTextEdit()
        self._install_log.setReadOnly(True)
        self._install_log.setFixedHeight(110)
        self._install_log.setPlaceholderText("Install log will appear here…")
        pg.addWidget(self._install_log)

        layout.addWidget(prog_group)

        # ── Actions ───────────────────────────────────────────────────────────
        act = QHBoxLayout()
        act.addStretch()
        self._abort_btn = QPushButton("Abort")
        self._abort_btn.setFixedWidth(80)
        self._abort_btn.setVisible(False)
        self._abort_btn.clicked.connect(self._abort_install)
        act.addWidget(self._abort_btn)

        self._install_btn = QPushButton("\u25b6  Install NetHunter")
        self._install_btn.setObjectName("primaryButton")
        self._install_btn.setFixedWidth(180)
        self._install_btn.setEnabled(False)
        self._install_btn.clicked.connect(self._start_install)
        act.addWidget(self._install_btn)
        layout.addLayout(act)
        layout.addStretch()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def set_serial(self, serial: str) -> None:
        self._serial = serial
        has_device = bool(serial)
        self._install_btn.setEnabled(has_device and bool(self._zip_input.text()))
        self._reboot_recovery_btn.setEnabled(has_device)

    def set_zip_path(self, path: str) -> None:
        """Pre-fill ZIP from the download tab."""
        self._zip_input.setText(path)
        self._install_btn.setEnabled(bool(self._serial))
        self._install_log.append(f"Ready to install: {Path(path).name}")

    def _browse_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select NetHunter ZIP",
            str(_NH_DOWNLOAD_DIR),
            "ZIP Archives (*.zip);;All Files (*)",
        )
        if path:
            self._zip_input.setText(path)
            self._install_btn.setEnabled(bool(self._serial))

    def _browse_kernel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Kernel ZIP",
            "",
            "ZIP Archives (*.zip);;All Files (*)",
        )
        if path:
            self._kernel_input.setText(path)

    def _reboot_to_recovery(self) -> None:
        if not self._serial:
            return
        reply = QMessageBox.question(
            self,
            "Reboot to Recovery",
            f"Reboot device {self._serial} to recovery mode now?\n\n"
            "Make sure TWRP or another ADB-sideload-capable recovery is installed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            ok = AdbManager.reboot(self._serial, "recovery")
            if ok:
                self._install_log.append("Rebooting to recovery…")
            else:
                self._install_log.append("⚠ Reboot command failed. Check ADB connection.")

    def _start_install(self) -> None:
        zip_path = self._zip_input.text().strip()
        if not zip_path:
            QMessageBox.warning(self, "No ZIP", "Select a NetHunter ZIP first.")
            return
        if not Path(zip_path).exists():
            QMessageBox.warning(self, "File Not Found", f"ZIP not found:\n{zip_path}")
            return
        if not self._serial:
            QMessageBox.warning(self, "No Device", "No device selected.")
            return

        self._install_log.clear()
        self._install_log.append(f"Starting install: {Path(zip_path).name}")
        self._install_step_lbl.setText("Installing…")
        self._install_bar.setRange(0, 0)
        self._install_btn.setEnabled(False)
        self._abort_btn.setVisible(True)

        self._install_worker = _NetHunterInstallWorker(self._serial, zip_path)
        self._install_thread = QThread(self)
        self._install_worker.moveToThread(self._install_thread)
        self._install_thread.started.connect(self._install_worker.start)

        self._install_worker.log_line.connect(self._on_install_log)
        self._install_worker.progress.connect(self._on_install_progress)
        self._install_worker.error.connect(self._on_install_error)
        self._install_worker.finished.connect(self._on_install_finished)
        self._install_worker.finished.connect(self._install_thread.quit)
        self._install_worker.finished.connect(self._install_worker.deleteLater)
        self._install_thread.finished.connect(self._install_thread.deleteLater)

        self._install_thread.start()

    def _abort_install(self) -> None:
        if self._install_worker:
            self._install_worker.abort()
        self._abort_btn.setVisible(False)
        self._install_step_lbl.setText("Aborting…")

    @Slot(str)
    def _on_install_log(self, line: str) -> None:
        self._install_log.append(line)

    @Slot(int, int)
    def _on_install_progress(self, done: int, total: int) -> None:
        self._install_bar.setRange(0, total)
        self._install_bar.setValue(done)
        self._install_pct_lbl.setText(f"{done}%")

    @Slot(str)
    def _on_install_error(self, msg: str) -> None:
        self._install_log.append(f"⚠ Error: {msg}")
        self._install_step_lbl.setText("Failed")
        self._install_bar.setRange(0, 100)
        self._install_bar.setValue(0)
        self._abort_btn.setVisible(False)
        self._install_btn.setEnabled(True)
        logger.error("NetHunter install error: %s", msg)

    @Slot()
    def _on_install_finished(self) -> None:
        self._abort_btn.setVisible(False)
        self._install_btn.setEnabled(True)
        self._install_bar.setRange(0, 100)
        if self._install_bar.value() == 100:
            self._install_step_lbl.setText("Complete")
            self._install_pct_lbl.setText("100%")
        elif "Failed" not in self._install_step_lbl.text():
            self._install_step_lbl.setText("Finished")


# ── Tools tab ─────────────────────────────────────────────────────────────────


class _ToolsTab(QWidget):
    """Quick access to common NetHunter tools and chroot management."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Chroot management
        chroot_card = CyberCard()
        cc = chroot_card.card_layout()
        ct = QLabel("Chroot Management")
        ct.setObjectName("cardHeader")
        cc.addWidget(ct)

        btn_row1 = QHBoxLayout()
        for text, tip in [
            ("Start Chroot", "Mount and start the Kali chroot environment"),
            ("Stop Chroot", "Unmount and stop the chroot"),
            ("Remove Chroot", "Delete the chroot filesystem"),
            ("Update Chroot", "Run apt update && apt upgrade inside chroot"),
        ]:
            btn = QPushButton(text)
            btn.setToolTip(tip)
            if text == "Remove Chroot":
                btn.setObjectName("dangerButton")
            btn_row1.addWidget(btn)
        cc.addLayout(btn_row1)
        layout.addWidget(chroot_card)

        # Quick tools
        tools_card = CyberCard()
        tc = tools_card.card_layout()
        tt = QLabel("Quick Tools")
        tt.setObjectName("cardHeader")
        tc.addWidget(tt)

        tool_grid = QGridLayout()
        tool_grid.setSpacing(8)
        tools = [
            ("Metasploit", "Launch msfconsole in chroot"),
            ("Nmap", "Network scanner"),
            ("Aircrack-ng", "WiFi auditing suite"),
            ("Burp Suite", "Web security testing proxy"),
            ("Wireshark", "Network protocol analyzer"),
            ("Social-Engineer Toolkit", "SET framework"),
        ]
        for i, (name, desc) in enumerate(tools):
            btn = QPushButton(name)
            btn.setToolTip(desc)
            btn.setFixedHeight(36)
            tool_grid.addWidget(btn, i // 3, i % 3)
        tc.addLayout(tool_grid)
        layout.addWidget(tools_card)

        # HID Attacks card
        hid_card = CyberCard()
        hc = hid_card.card_layout()
        ht = QLabel("USB HID Attacks")
        ht.setObjectName("cardHeader")
        hc.addWidget(ht)
        hid_info = QLabel(
            "Requires a NetHunter-compatible kernel with USB HID gadget support. "
            "Use DuckHunter for HID payload scripting."
        )
        hid_info.setObjectName("subtitleLabel")
        hid_info.setWordWrap(True)
        hc.addWidget(hid_info)

        hid_btns = QHBoxLayout()
        hid_btns.addWidget(QPushButton("DuckHunter"))
        hid_btns.addWidget(QPushButton("HID Keyboard"))
        hid_btns.addStretch()
        hc.addLayout(hid_btns)
        layout.addWidget(hid_card)

        layout.addStretch()


# ── No-device overlay ─────────────────────────────────────────────────────────


class _NoDeviceOverlay(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        icon = QLabel("\U0001f5e1\ufe0f")
        icon.setObjectName("emptyIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        title = QLabel("No Device Connected")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = QLabel("Connect an Android device via USB to install\nand manage Kali NetHunter.")
        hint.setObjectName("subtitleLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)


# ── Main page ─────────────────────────────────────────────────────────────────


class NetHunterPage(QWidget):
    """NetHunter management — download, install, configure, and use tools."""

    def __init__(
        self,
        device_service=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._device_service = device_service
        self._current_serial: str = ""
        self._setup_ui()

        if device_service is not None:
            device_service.device_list_updated.connect(self._on_devices_updated)
            device_service.selected_device_changed.connect(self._on_selected_device_changed)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("NetHunter")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        subtitle = QLabel("Kali NetHunter download, installation, and tools")
        subtitle.setObjectName("pageSubtitle")
        header.addWidget(subtitle)
        header.addStretch()
        self._device_badge = CyberBadge("No Device", "neutral")
        header.addWidget(self._device_badge)
        root.addLayout(header)

        # No-device overlay
        self._no_device = _NoDeviceOverlay()
        root.addWidget(self._no_device)

        # Content
        self._content = QWidget()
        self._content.setVisible(False)
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(12)

        # Status card
        self._status_card = _NhStatusCard()
        cl.addWidget(self._status_card)

        # Tabs: Download | Install | Tools & Chroot
        self._tabs = QTabWidget()
        self._download_tab = _DownloadTab()
        self._installer_tab = _InstallerTab()
        self._tools_tab = _ToolsTab()

        self._tabs.addTab(self._download_tab, "\u2913  Download")
        self._tabs.addTab(self._installer_tab, "\u25b6  Install")
        self._tabs.addTab(self._tools_tab, "\U0001f6e0  Tools & Chroot")

        # Wire: download complete → populate installer, switch to Install tab
        self._download_tab.download_ready.connect(self._on_download_ready)

        cl.addWidget(self._tabs, stretch=1)
        root.addWidget(self._content)

    # ── Device slots ──────────────────────────────────────────────────────────

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
            self._current_serial = ""
            self._installer_tab.set_serial("")

    @Slot(object)
    def _on_selected_device_changed(self, info) -> None:
        if info is None:
            return
        self._current_serial = info.serial
        self._installer_tab.set_serial(info.serial)
        codename = getattr(info, "codename", "")
        if codename:
            self._download_tab.set_device_hint(codename)

    # ── Download → Install bridge ─────────────────────────────────────────────

    @Slot(str)
    def _on_download_ready(self, path: str) -> None:
        """Auto-fill installer ZIP and switch to the Install tab."""
        self._installer_tab.set_zip_path(path)
        self._tabs.setCurrentWidget(self._installer_tab)
