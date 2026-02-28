"""fleet_dashboard_page.py — Multi-Device Fleet Dashboard.

Displays a real-time grid of all connected devices with per-device
status badges, battery levels, last-seen timestamps, and quick-action
buttons (reboot, backup, ping).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QThread, QTimer, Slot
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cyberflash.models.device import DeviceInfo
from cyberflash.services.device_service import DeviceService
from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.cyber_card import CyberCard
from cyberflash.workers.battery_monitor_worker import BatteryMonitorWorker, BatterySample

logger = logging.getLogger(__name__)


# ── Per-device card ───────────────────────────────────────────────────────────


class _DeviceFleetCard(CyberCard):
    """Compact status card for one device in the fleet grid."""

    def __init__(self, device: DeviceInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._serial = device.serial
        layout = self.card_layout()

        # Header row: model + status badge
        hdr = QHBoxLayout()
        self._model_label = QLabel(device.model or device.serial)
        self._model_label.setObjectName("cardHeader")
        hdr.addWidget(self._model_label)
        hdr.addStretch()
        self._status_badge = CyberBadge(device.state or "online", "success")
        hdr.addWidget(self._status_badge)
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        layout.addWidget(sep)

        # Details grid
        self._details = QVBoxLayout()
        self._serial_lbl = QLabel(f"Serial: {device.serial}")
        self._serial_lbl.setObjectName("kvKey")
        self._android_lbl = QLabel(f"Android: {device.android_version or '—'}")
        self._android_lbl.setObjectName("kvKey")
        self._battery_lbl = QLabel("Battery: —")
        self._battery_lbl.setObjectName("kvKey")
        for w in [self._serial_lbl, self._android_lbl, self._battery_lbl]:
            self._details.addWidget(w)
        layout.addLayout(self._details)

        # Action buttons
        btn_row = QHBoxLayout()
        self._btn_reboot = QPushButton("Reboot")
        self._btn_backup = QPushButton("Backup")
        self._btn_ping = QPushButton("Ping")
        for btn in [self._btn_reboot, self._btn_backup, self._btn_ping]:
            btn.setFixedHeight(26)
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

    def update_battery(self, text: str) -> None:
        self._battery_lbl.setText(f"Battery: {text}")

    def serial(self) -> str:
        return self._serial


# ── Page ──────────────────────────────────────────────────────────────────────


class FleetDashboardPage(QWidget):
    """Multi-device fleet overview page.

    Args:
        device_service: The shared DeviceService instance.
        parent: Optional Qt parent.
    """

    def __init__(
        self, device_service: DeviceService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._service = device_service
        self._cards: dict[str, _DeviceFleetCard] = {}
        self._battery_threads: dict[str, tuple[QThread, BatteryMonitorWorker]] = {}

        self._build_ui()
        self._service.device_list_updated.connect(self._on_devices_changed)

        # Refresh timer (battery levels, etc.)
        self._timer = QTimer(self)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self._refresh_battery)
        self._timer.start()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()
        title = QLabel("Fleet Dashboard")
        title.setObjectName("pageTitle")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self._count_badge = CyberBadge("0 devices", "neutral")
        toolbar.addWidget(self._count_badge)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.clicked.connect(self._refresh_all)
        toolbar.addWidget(self._btn_refresh)
        root.addLayout(toolbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # Scrollable device grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._grid.setSpacing(12)
        scroll.setWidget(self._grid_container)
        root.addWidget(scroll)

        # Empty state hint
        self._empty_label = QLabel("No devices connected.\nConnect an Android device via USB.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setObjectName("emptyState")
        root.addWidget(self._empty_label)

    @Slot(list)
    def _on_devices_changed(self, devices: list[DeviceInfo]) -> None:
        """Rebuild the fleet grid when device list changes."""
        new_serials = {d.serial for d in devices}

        # Stop workers for disconnected devices
        for serial in list(self._battery_threads):
            if serial not in new_serials:
                thread, worker = self._battery_threads.pop(serial)
                worker.abort()
                thread.quit()
                thread.wait(1000)

        # Clear all existing cards
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        self._empty_label.setVisible(len(devices) == 0)
        self._grid_container.setVisible(len(devices) > 0)
        self._count_badge.update_text(f"{len(devices)} device{'s' if len(devices) != 1 else ''}")

        cols = max(1, min(3, len(devices)))
        for i, device in enumerate(devices):
            card = _DeviceFleetCard(device, self)
            self._cards[device.serial] = card
            self._grid.addWidget(card, i // cols, i % cols)

            # Start battery monitor worker if not already running
            if device.serial not in self._battery_threads:
                worker = BatteryMonitorWorker(device.serial)
                thread = QThread(self)
                worker.moveToThread(thread)
                thread.started.connect(worker.start)
                worker.sample_ready.connect(
                    lambda s, serial=device.serial: self._on_battery_sample(serial, s)
                )
                worker.finished.connect(thread.quit)
                worker.finished.connect(worker.deleteLater)
                thread.finished.connect(thread.deleteLater)
                thread.start()
                self._battery_threads[device.serial] = (thread, worker)

        logger.debug("Fleet grid updated: %d devices", len(devices))

    @Slot(str, object)
    def _on_battery_sample(self, serial: str, sample: object) -> None:
        card = self._cards.get(serial)
        if card and isinstance(sample, BatterySample):
            card.update_battery(f"{sample.level}% {sample.status} {sample.temp_c:.1f}°C")

    def _refresh_all(self) -> None:
        self._refresh_battery()

    def _refresh_battery(self) -> None:
        """Fetch battery levels for all connected devices (fallback polling)."""
        from cyberflash.core.adb_manager import AdbManager

        for serial, card in list(self._cards.items()):
            try:
                output = AdbManager.shell(serial, "dumpsys battery | grep level", timeout=5)
                for line in output.splitlines():
                    if "level:" in line.lower():
                        level = int(line.split(":")[1].strip())
                        card.update_battery(f"{level}%")
                        break
            except Exception:
                logger.debug("Could not get battery for %s", serial)
