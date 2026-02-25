from __future__ import annotations

import logging

from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, Signal, Slot

from cyberflash.core.adb_manager import AdbManager
from cyberflash.models.device import DeviceInfo
from cyberflash.workers.device_poll_worker import DevicePollWorker

logger = logging.getLogger(__name__)


class DeviceService(QObject):
    """Owns the device polling worker and provides device state to the UI.

    Connect to:
        device_list_updated(list[DeviceInfo]) — called whenever devices change
        selected_device_changed(DeviceInfo | None) — called on selection change
    """

    device_list_updated = Signal(list)  # list[DeviceInfo]
    selected_device_changed = Signal(object)  # DeviceInfo | None

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._devices: list[DeviceInfo] = []
        self._selected: DeviceInfo | None = None
        self._thread: QThread | None = None
        self._worker: DevicePollWorker | None = None

    def start(self) -> None:
        AdbManager.start_server()

        self._thread = QThread(self)
        self._worker = DevicePollWorker()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.start_polling)
        self._worker.devices_changed.connect(self._on_devices_changed)
        self._worker.error.connect(self._on_worker_error)

        self._thread.start()
        logger.info("DeviceService started")

    def stop(self) -> None:
        if self._worker:
            # Invoke stop_polling on the worker's thread via the event loop
            QMetaObject.invokeMethod(
                self._worker, "stop_polling", Qt.ConnectionType.QueuedConnection
            )
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        logger.info("DeviceService stopped")

    # ── Public accessors ─────────────────────────────────────────────────────

    @property
    def devices(self) -> list[DeviceInfo]:
        return list(self._devices)

    @property
    def selected_device(self) -> DeviceInfo | None:
        return self._selected

    # ── Selection ────────────────────────────────────────────────────────────

    @Slot(str)
    def select_device(self, serial: str) -> None:
        for device in self._devices:
            if device.serial == serial:
                if self._selected is None or self._selected.serial != serial:
                    self._selected = device
                    self.selected_device_changed.emit(device)
                return
        self._clear_selection()

    def _clear_selection(self) -> None:
        if self._selected is not None:
            self._selected = None
            self.selected_device_changed.emit(None)

    # ── Worker slots ─────────────────────────────────────────────────────────

    @Slot(list)
    def _on_devices_changed(self, devices: list[DeviceInfo]) -> None:
        self._devices = devices

        # Invalidate selection if device disconnected
        if self._selected:
            known_serials = {d.serial for d in devices}
            if self._selected.serial not in known_serials:
                self._clear_selection()

        # Auto-select when exactly one device connects
        if self._selected is None and len(devices) == 1:
            self._selected = devices[0]
            self.selected_device_changed.emit(devices[0])

        self.device_list_updated.emit(devices)

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        logger.error("DeviceService worker error: %s", message)
