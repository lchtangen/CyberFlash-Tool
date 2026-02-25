from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cyberflash.models.device import DeviceInfo
from cyberflash.services.device_service import DeviceService
from cyberflash.ui.themes.icons import get_hero_phone_pixmap
from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.cyber_card import CyberCard


class _DeviceCard(CyberCard):
    """Single device summary card on the dashboard."""

    select_requested = Signal(str)  # serial

    def __init__(self, info: DeviceInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._serial = info.serial
        self._build_ui(info)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _build_ui(self, info: DeviceInfo) -> None:
        layout = self.card_layout()

        # ── Row 1: name + badge ──────────────────────────────────────────────
        row1 = QHBoxLayout()
        self._name_label = QLabel(info.display_name or info.serial)
        self._name_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        row1.addWidget(self._name_label)
        row1.addStretch()
        self._state_badge = CyberBadge(info.state.label, info.state.badge_variant)
        row1.addWidget(self._state_badge)
        layout.addLayout(row1)

        # ── Row 2: serial ────────────────────────────────────────────────────
        serial_label = QLabel(f"Serial: {info.serial}")
        serial_label.setObjectName("serialLabel")
        layout.addWidget(serial_label)

        # ── Separator ────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        layout.addWidget(sep)

        # ── Row 3: props ─────────────────────────────────────────────────────
        grid = QHBoxLayout()
        grid.setSpacing(24)

        if info.is_adb_device and info.android_version:
            grid.addLayout(_kv("Android", info.android_version))

        if info.has_ab_slots:
            grid.addLayout(_kv("Slot", info.slot_label))

        bl_variant = (
            "success"
            if info.bootloader_unlocked is True
            else "error"
            if info.bootloader_unlocked is False
            else "neutral"
        )
        grid.addLayout(_kv("Bootloader", info.bootloader_label, bl_variant))

        if info.battery_level >= 0:
            grid.addLayout(_kv("Battery", f"{info.battery_level}%"))

        grid.addStretch()
        layout.addLayout(grid)

        # ── Row 4: action ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        select_btn = QPushButton("Select Device")
        select_btn.setObjectName("primaryButton")
        select_btn.setFixedWidth(130)
        select_btn.clicked.connect(lambda: self.select_requested.emit(self._serial))
        btn_row.addWidget(select_btn)
        layout.addLayout(btn_row)


def _kv(key: str, value: str, variant: str = "") -> QVBoxLayout:
    col = QVBoxLayout()
    col.setSpacing(2)
    k = QLabel(key)
    k.setObjectName("kvKey")
    v = QLabel(value)
    v.setObjectName("kvValue")
    if variant:
        # Use a dynamic property to let QSS apply semantic color
        v.setProperty("variant", variant)
    col.addWidget(k)
    col.addWidget(v)
    return col


class _EmptyState(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setObjectName("emptyIcon")
        icon.setPixmap(get_hero_phone_pixmap("#00d4ff", 160))
        layout.addWidget(icon)

        title = QLabel("No device connected")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = QLabel(
            "Connect an Android device via USB and enable USB Debugging,\n"
            "or boot your device to bootloader / fastboot mode."
        )
        hint.setObjectName("subtitleLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        waiting = QLabel("Waiting for device\u2026")
        waiting.setAlignment(Qt.AlignmentFlag.AlignCenter)
        waiting.setObjectName("emptyHint")
        layout.addWidget(waiting)


class DashboardPage(QWidget):
    def __init__(
        self,
        device_service: DeviceService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = device_service
        self._setup_ui()
        if self._service:
            self._service.device_list_updated.connect(self._on_devices_updated)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("titleLabel")
        header_row.addWidget(title)
        header_row.addStretch()
        self._count_label = QLabel("")
        self._count_label.setObjectName("secondaryLabel")
        header_row.addWidget(self._count_label)
        root.addLayout(header_row)

        # Empty state (shown when no devices)
        self._empty = _EmptyState()
        root.addWidget(self._empty)

        # Scrollable device cards (shown when devices present)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._cards_layout.setSpacing(12)
        self._scroll.setWidget(self._cards_widget)
        self._scroll.setVisible(False)
        root.addWidget(self._scroll)

    @Slot(list)
    def _on_devices_updated(self, devices: list[DeviceInfo]) -> None:
        # Clear old cards
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not devices:
            self._empty.setVisible(True)
            self._scroll.setVisible(False)
            self._count_label.setText("")
            return

        self._empty.setVisible(False)
        self._scroll.setVisible(True)
        n = len(devices)
        self._count_label.setText(f"{n} device{'s' if n != 1 else ''} connected")

        for info in devices:
            card = _DeviceCard(info)
            if self._service:
                card.select_requested.connect(self._service.select_device)
            self._cards_layout.addWidget(card)
