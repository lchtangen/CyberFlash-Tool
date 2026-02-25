from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cyberflash.models.device import DeviceInfo
from cyberflash.services.device_service import DeviceService
from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.cyber_card import CyberCard

logger = logging.getLogger(__name__)


class _PropsCard(CyberCard):
    """Grid of device properties."""

    def __init__(self, info: DeviceInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self.card_layout()

        header = QLabel("Device Properties")
        header.setObjectName("cardHeader")
        layout.addWidget(header)

        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(24)

        rows = [
            ("Model", info.model or "—"),
            ("Brand", info.brand or "—"),
            ("Codename", info.codename or "—"),
            ("Serial", info.serial),
            ("Android Version", info.android_version or "—"),
            ("SDK Level", info.sdk_version or "—"),
            ("Build Number", info.build_number or "—"),
            ("Bootloader", info.bootloader_label),
            ("Active Slot", info.slot_label),
            ("Battery", f"{info.battery_level}%" if info.battery_level >= 0 else "—"),
        ]
        for i, (key, val) in enumerate(rows):
            k = QLabel(key)
            k.setObjectName("kvKey")
            k.setFixedWidth(140)
            v = QLabel(val)
            v.setWordWrap(True)
            grid.addWidget(k, i, 0)
            grid.addWidget(v, i, 1)

        layout.addLayout(grid)


class _ActionsCard(CyberCard):
    """Reboot action buttons."""

    reboot_requested = Signal(str)  # mode: "" | "recovery" | "bootloader" | "fastboot"

    def __init__(
        self,
        info: DeviceInfo,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = self.card_layout()

        header = QLabel("Actions")
        header.setObjectName("cardHeader")
        layout.addWidget(header)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._reboot_btns: list[tuple[str, str, str]] = []

        if info.is_adb_device:
            self._reboot_btns = [
                ("Reboot", "", "Reboot to system"),
                ("Recovery", "recovery", "Reboot to recovery"),
                ("Bootloader", "bootloader", "Reboot to bootloader"),
            ]
        elif info.is_fastboot_device:
            self._reboot_btns = [
                ("System", "", "Reboot to system"),
                ("Recovery", "recovery", "Reboot to recovery"),
            ]
            if info.has_ab_slots:
                self._reboot_btns.append(("FastbootD", "fastboot", "Reboot to fastbootd"))

        for label, mode, tip in self._reboot_btns:
            btn = QPushButton(f"Reboot \u2192 {label}")
            btn.setToolTip(tip)
            btn.setFixedHeight(32)
            btn.clicked.connect(lambda _c=False, m=mode: self.reboot_requested.emit(m))
            btn_row.addWidget(btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)


class _NoDeviceState(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        icon = QLabel("\U0001f50d")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setObjectName("emptyIcon")
        layout.addWidget(icon)

        title = QLabel("No device selected")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Select a device from the Dashboard or device selector above.")
        sub.setObjectName("subtitleLabel")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        layout.addWidget(sub)


class DevicePage(QWidget):
    def __init__(
        self,
        device_service: DeviceService | None = None,
        ai_service: object | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = device_service
        self._ai_service = ai_service
        self._current_info: DeviceInfo | None = None
        self._setup_ui()
        if self._service:
            self._service.selected_device_changed.connect(self._on_device_changed)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Page header
        header_row = QHBoxLayout()
        title = QLabel("Device")
        title.setObjectName("titleLabel")
        header_row.addWidget(title)
        header_row.addStretch()
        self._state_badge = CyberBadge("", "neutral")
        self._state_badge.setVisible(False)
        header_row.addWidget(self._state_badge)
        root.addLayout(header_row)

        self._device_name_label = QLabel("")
        self._device_name_label.setObjectName("deviceName")
        self._device_name_label.setVisible(False)
        root.addWidget(self._device_name_label)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        root.addWidget(sep)

        # No-device state
        self._no_device = _NoDeviceState()
        root.addWidget(self._no_device)

        # Scrollable device content
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_layout.setSpacing(16)
        self._scroll.setWidget(self._content_widget)
        self._scroll.setVisible(False)
        root.addWidget(self._scroll)

    @Slot(object)
    def _on_device_changed(self, info: DeviceInfo | None) -> None:
        self._current_info = info

        # Clear content
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if info is None:
            self._no_device.setVisible(True)
            self._scroll.setVisible(False)
            self._state_badge.setVisible(False)
            self._device_name_label.setVisible(False)
            return

        self._no_device.setVisible(False)
        self._scroll.setVisible(True)

        self._device_name_label.setText(info.display_name or info.serial)
        self._device_name_label.setVisible(True)
        self._state_badge.set_text_and_variant(info.state.label, info.state.badge_variant)
        self._state_badge.setVisible(True)

        # Properties card
        props_card = _PropsCard(info)
        self._content_layout.addWidget(props_card)

        # Actions card
        actions_card = _ActionsCard(info)
        actions_card.reboot_requested.connect(self._on_reboot_requested)
        self._content_layout.addWidget(actions_card)

        self._content_layout.addStretch()

    @Slot(str)
    def _on_reboot_requested(self, mode: str) -> None:
        """Handle a reboot button click."""
        target = mode or "system"
        reply = QMessageBox.question(
            self,
            "Confirm Reboot",
            f"Reboot device to {target}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self._ai_service is not None:
            self._ai_service.execute_reboot(mode)
            logger.info("Reboot to %s requested via AI service", target)
        elif self._current_info:
            # Fallback: direct ADB/fastboot call
            from cyberflash.core.adb_manager import AdbManager
            from cyberflash.core.fastboot_manager import FastbootManager

            serial = self._current_info.serial
            if self._current_info.is_adb_device:
                AdbManager.reboot(serial, mode) if mode else AdbManager.reboot(serial)
            elif self._current_info.is_fastboot_device:
                FastbootManager.reboot(serial, mode=mode)
