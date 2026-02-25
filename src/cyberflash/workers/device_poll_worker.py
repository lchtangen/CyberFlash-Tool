from __future__ import annotations

import logging

from PySide6.QtCore import QTimer, Signal, Slot

from cyberflash.core.device_detector import DeviceDetector
from cyberflash.models.device import DeviceInfo
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 2000


class DevicePollWorker(BaseWorker):
    """Polls ADB + fastboot every 2 s and emits devices_changed on state change.

    Enrichment (getprop calls) only happens once per new device serial,
    keeping the polling loop fast.
    """

    devices_changed = Signal(list)  # list[DeviceInfo]

    def __init__(self) -> None:
        super().__init__()
        self._timer: QTimer | None = None
        self._known: dict[str, DeviceInfo] = {}  # serial → enriched DeviceInfo

    @Slot()
    def start_polling(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self._poll()  # immediate first poll

    @Slot()
    def stop_polling(self) -> None:
        if self._timer:
            self._timer.stop()
        self.finished.emit()

    @Slot()
    def _poll(self) -> None:
        try:
            current = DeviceDetector.list_serials()  # fast: just serials + states
        except Exception as exc:
            logger.error("Poll error: %s", exc)
            self.error.emit(str(exc))
            return

        current_set = set(current)
        known_set = set(self._known)

        new_serials = current_set - known_set
        removed_serials = known_set - current_set
        state_changed = {
            s for s in current_set & known_set
            if current[s] != self._known[s].state
        }

        if not (new_serials or removed_serials or state_changed):
            return  # nothing changed — skip emit

        # Remove disconnected devices
        for serial in removed_serials:
            del self._known[serial]
            logger.info("Device disconnected: %s", serial)

        # Enrich newly appeared + state-changed devices
        for serial in new_serials | state_changed:
            state = current[serial]
            try:
                info = DeviceDetector.enrich(serial, state)
            except Exception as exc:
                logger.warning("Enrich failed for %s: %s", serial, exc)
                info = DeviceInfo(serial=serial, state=state)
            self._known[serial] = info
            logger.info(
                "Device %s: %s [%s]",
                serial,
                info.display_name or "?",
                state.label,
            )

        self.devices_changed.emit(list(self._known.values()))
