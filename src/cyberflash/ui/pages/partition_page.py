"""Partition Manager page — view, backup, and manage device partitions.

Displays the device partition table, A/B slot status, and provides
tools for dumping, erasing, and flashing individual partitions.
Connected to the AI automation service for actual command execution.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.cyber_card import CyberCard

logger = logging.getLogger(__name__)


# ── Slot info card ───────────────────────────────────────────────────────────


class _SlotCard(CyberCard):
    """A/B slot status indicator."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self.card_layout()

        hdr = QHBoxLayout()
        title = QLabel("A/B Slot Status")
        title.setObjectName("cardHeader")
        hdr.addWidget(title)
        hdr.addStretch()
        self._ab_badge = CyberBadge("Unknown", "neutral")
        hdr.addWidget(self._ab_badge)
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
                ("Active Slot", "active_slot"),
                ("Slot A Status", "slot_a"),
                ("Slot B Status", "slot_b"),
                ("Partition Scheme", "scheme"),
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

        # Slot switch button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._switch_btn = QPushButton("Switch Active Slot")
        self._switch_btn.setObjectName("primaryButton")
        self._switch_btn.setFixedWidth(160)
        self._switch_btn.setEnabled(False)
        btn_row.addWidget(self._switch_btn)
        layout.addLayout(btn_row)

    def update_slot_info(
        self,
        *,
        has_ab: bool | None = None,
        active: str = "",
        slot_a: str = "",
        slot_b: str = "",
    ) -> None:
        if has_ab is True:
            self._ab_badge.set_text_and_variant("A/B Device", "info")
            self._switch_btn.setEnabled(True)
        elif has_ab is False:
            self._ab_badge.set_text_and_variant("A-only", "neutral")
            self._switch_btn.setEnabled(False)
        else:
            self._ab_badge.set_text_and_variant("Unknown", "neutral")
            self._switch_btn.setEnabled(False)

        self._labels["active_slot"].setText(active or "\u2014")
        self._labels["slot_a"].setText(slot_a or "\u2014")
        self._labels["slot_b"].setText(slot_b or "\u2014")
        scheme = "A/B (seamless)" if has_ab else "A-only (legacy)"
        self._labels["scheme"].setText(scheme if has_ab is not None else "\u2014")


# ── Partition table widget ───────────────────────────────────────────────────


class _PartitionTable(CyberCard):
    """Tabular view of device partitions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self.card_layout()

        hdr = QHBoxLayout()
        title = QLabel("Partition Table")
        title.setObjectName("cardHeader")
        hdr.addWidget(title)
        hdr.addStretch()

        self._refresh_btn = QPushButton("\u21bb Refresh")
        self._refresh_btn.setFixedWidth(90)
        hdr.addWidget(self._refresh_btn)
        layout.addLayout(hdr)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            [
                "Partition",
                "Size",
                "Filesystem",
                "Slot",
                "Flags",
            ]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

    def set_partitions(self, partitions: list[dict[str, str]]) -> None:
        """Populate table from a list of partition dicts."""
        self._table.setRowCount(len(partitions))
        for row, part in enumerate(partitions):
            for col, key in enumerate(["name", "size", "fs", "slot", "flags"]):
                item = QTableWidgetItem(part.get(key, ""))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)

    def clear_table(self) -> None:
        self._table.setRowCount(0)

    def populate_sample(self) -> None:
        """Show sample partition layout for UI preview."""
        sample = [
            {"name": "boot", "size": "64 MB", "fs": "raw", "slot": "a/b", "flags": "bootable"},
            {"name": "system", "size": "4.0 GB", "fs": "ext4", "slot": "a/b", "flags": ""},
            {"name": "vendor", "size": "1.2 GB", "fs": "ext4", "slot": "a/b", "flags": ""},
            {"name": "product", "size": "2.1 GB", "fs": "ext4", "slot": "a/b", "flags": ""},
            {"name": "userdata", "size": "110 GB", "fs": "f2fs", "slot": "\u2014", "flags": ""},
            {"name": "recovery", "size": "64 MB", "fs": "raw", "slot": "a/b", "flags": ""},
            {"name": "dtbo", "size": "8 MB", "fs": "raw", "slot": "a/b", "flags": ""},
            {"name": "vbmeta", "size": "4 KB", "fs": "raw", "slot": "a/b", "flags": "verified"},
            {"name": "modem", "size": "256 MB", "fs": "raw", "slot": "a/b", "flags": ""},
            {"name": "metadata", "size": "16 MB", "fs": "ext4", "slot": "\u2014", "flags": ""},
        ]
        self.set_partitions(sample)


# ── Partition actions card ───────────────────────────────────────────────────


class _PartitionActions(CyberCard):
    """Actions that can be performed on selected partitions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self.card_layout()

        title = QLabel("Partition Operations")
        title.setObjectName("cardHeader")
        layout.addWidget(title)

        desc = QLabel(
            "Select a partition from the table, then choose an operation. "
            "Operations require the device in fastboot mode."
        )
        desc.setObjectName("subtitleLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Target partition selector
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("Target:"))
        self._part_combo = QComboBox()
        self._part_combo.addItems(
            [
                "boot",
                "recovery",
                "system",
                "vendor",
                "dtbo",
                "vbmeta",
                "modem",
            ]
        )
        self._part_combo.setMinimumWidth(150)
        sel_row.addWidget(self._part_combo)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        dump_btn = QPushButton("Dump Partition")
        dump_btn.setToolTip("Read partition to a local .img file")
        dump_btn.setObjectName("primaryButton")
        btn_row.addWidget(dump_btn)

        flash_btn = QPushButton("Flash Image")
        flash_btn.setToolTip("Write an .img file to the selected partition")
        btn_row.addWidget(flash_btn)

        erase_btn = QPushButton("Erase Partition")
        erase_btn.setToolTip("Erase partition contents (irreversible!)")
        erase_btn.setObjectName("dangerButton")
        btn_row.addWidget(erase_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Progress
        self._progress = QProgressBar()
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        self._status = QLabel("Select a partition and operation")
        self._status.setObjectName("subtitleLabel")
        layout.addWidget(self._status)


# ── No-device overlay ────────────────────────────────────────────────────────


class _NoDeviceOverlay(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        icon = QLabel("\U0001f4bf")
        icon.setObjectName("emptyIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        title = QLabel("No Device Connected")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = QLabel("Connect an Android device in fastboot mode\nto view and manage partitions.")
        hint.setObjectName("subtitleLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)


# ── Main page ────────────────────────────────────────────────────────────────


class PartitionPage(QWidget):
    """Partition Manager — view, dump, flash, and manage device partitions."""

    def __init__(
        self,
        device_service=None,
        ai_service=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._device_service = device_service
        self._ai_service = ai_service
        self._current_serial: str = ""
        self._setup_ui()

        if device_service is not None:
            device_service.device_list_updated.connect(self._on_devices_updated)

        if ai_service is not None:
            ai_service.command_completed.connect(self._on_command_result)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("Partition Manager")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        subtitle = QLabel("View and manage device partitions")
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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_inner = QWidget()
        sl = QVBoxLayout(scroll_inner)
        sl.setAlignment(Qt.AlignmentFlag.AlignTop)
        sl.setSpacing(12)

        # Slot card
        self._slot_card = _SlotCard()
        self._slot_card._switch_btn.clicked.connect(self._on_switch_slot)
        sl.addWidget(self._slot_card)

        # Partition table
        self._partition_table = _PartitionTable()
        self._partition_table._refresh_btn.clicked.connect(self._on_refresh_partitions)
        sl.addWidget(self._partition_table)

        # Actions
        self._actions_card = _PartitionActions()
        sl.addWidget(self._actions_card)

        # Wire action buttons inside _PartitionActions
        self._wire_action_buttons()

        sl.addStretch()

        scroll.setWidget(scroll_inner)
        cl.addWidget(scroll)
        root.addWidget(self._content)

    @Slot(list)
    def _on_devices_updated(self, devices: list) -> None:
        has = len(devices) > 0
        self._no_device.setVisible(not has)
        self._content.setVisible(has)
        if has:
            d = devices[0]
            name = getattr(d, "display_name", getattr(d, "serial", "Device"))
            self._current_serial = getattr(d, "serial", "")
            self._device_badge.set_text_and_variant(f"\u2713 {name}", "success")
            # Auto-populate slot info and sample partition table
            self._on_refresh_partitions()
            self._fetch_slot_info()
        else:
            self._device_badge.set_text_and_variant("No Device", "neutral")
            self._current_serial = ""

    def _wire_action_buttons(self) -> None:
        """Find and connect the action buttons inside _PartitionActions."""
        card = self._actions_card
        # Walk children to find dump/flash/erase buttons
        for child in card.findChildren(QPushButton):
            text = child.text().lower()
            if "dump" in text:
                child.clicked.connect(self._on_dump_partition)
            elif "flash" in text:
                child.clicked.connect(self._on_flash_partition)
            elif "erase" in text:
                child.clicked.connect(self._on_erase_partition)

    def _fetch_slot_info(self) -> None:
        """Query slot info from the device via AI service."""
        if self._ai_service and self._current_serial:
            self._ai_service.execute_get_slot_info()

    def _on_refresh_partitions(self) -> None:
        """Refresh partition table — uses sample data or real device query."""
        self._partition_table.populate_sample()
        self._actions_card._status.setText("Partition table loaded")
        if self._ai_service and self._current_serial:
            self._ai_service.execute_get_slot_info()

    def _on_switch_slot(self) -> None:
        """Switch the active A/B slot."""
        if not self._ai_service or not self._current_serial:
            return
        active = self._slot_card._labels["active_slot"].text().strip().lower()
        target = "b" if active == "a" else "a"
        reply = QMessageBox.question(
            self,
            "Switch Slot",
            f"Switch active slot to '{target.upper()}'?\n\n"
            "The device will boot from the other slot on next reboot.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._ai_service.execute_slot_switch(target)
            self._actions_card._status.setText(f"Switching to slot {target.upper()}\u2026")

    def _on_dump_partition(self) -> None:
        """Dump the selected partition to a local file."""
        partition = self._actions_card._part_combo.currentText()
        if not partition:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save {partition} Dump",
            f"{partition}.img",
            "Image Files (*.img);;All Files (*)",
        )
        if not save_path:
            return
        self._actions_card._status.setText(f"Dumping {partition}\u2026")
        self._actions_card._progress.setRange(0, 0)
        if self._ai_service:
            # Use shell dd for partition dump
            self._ai_service.execute_shell(
                f"dd if=/dev/block/by-name/{partition} 2>/dev/null | head -c 67108864",
                timeout=120,
            )
        logger.info("Dump requested: %s → %s", partition, save_path)

    def _on_flash_partition(self) -> None:
        """Flash an image to the selected partition."""
        partition = self._actions_card._part_combo.currentText()
        if not partition:
            return
        image_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Image for {partition}",
            "",
            "Image Files (*.img);;All Files (*)",
        )
        if not image_path:
            return
        reply = QMessageBox.warning(
            self,
            "Flash Partition",
            f"Flash '{partition}' with:\n{image_path}\n\nThis is irreversible!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._actions_card._status.setText(f"Flashing {partition}\u2026")
        self._actions_card._progress.setRange(0, 0)
        if self._ai_service:
            self._ai_service.execute_flash_partition(partition, image_path)

    def _on_erase_partition(self) -> None:
        """Erase the selected partition."""
        partition = self._actions_card._part_combo.currentText()
        if not partition:
            return
        reply = QMessageBox.critical(
            self,
            "Erase Partition",
            f"ERASE partition '{partition}'?\n\nThis will PERMANENTLY delete all "
            "data on this partition. This action cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._actions_card._status.setText(f"Erasing {partition}\u2026")
        self._actions_card._progress.setRange(0, 0)
        if self._ai_service:
            self._ai_service.execute_erase(partition)

    @Slot(object)
    def _on_command_result(self, result: object) -> None:
        """Handle command results from the AI service."""
        from cyberflash.core.command_executor import CommandStatus, CommandType

        status = getattr(result, "status", None)
        cmd_type = getattr(result, "command_type", None)
        message = getattr(result, "message", "")
        output = getattr(result, "output", "")

        self._actions_card._progress.setRange(0, 100)

        if status == CommandStatus.COMPLETED:
            self._actions_card._progress.setValue(100)
            self._actions_card._status.setText(f"\u2713 {message}")

            # If slot info returned, update the slot card
            if cmd_type == CommandType.INFO and "current-slot" in output:
                self._parse_slot_output(output)
        elif status == CommandStatus.FAILED:
            self._actions_card._progress.setValue(0)
            self._actions_card._status.setText(f"\u2717 {message}")
        elif status == CommandStatus.BLOCKED:
            self._actions_card._progress.setValue(0)
            self._actions_card._status.setText(f"\u26a0 Blocked: {message}")

    def _parse_slot_output(self, output: str) -> None:
        """Parse slot info output and update the slot card."""
        info: dict[str, str] = {}
        for line in output.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                info[k.strip()] = v.strip()

        active = info.get("current-slot", "")
        slot_count = info.get("slot-count", "0")
        has_ab = slot_count == "2"

        self._slot_card.update_slot_info(
            has_ab=has_ab,
            active=active,
            slot_a="Active" if active == "a" else "Inactive" if has_ab else "",
            slot_b="Active" if active == "b" else "Inactive" if has_ab else "",
        )
