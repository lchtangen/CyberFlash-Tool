"""battery_monitor_worker.py — Periodic battery status monitor.

Polls ``dumpsys battery`` at a configurable interval and emits
structured samples.  Raises alert when temperature exceeds threshold.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import Signal, Slot

from cyberflash.core.adb_manager import AdbManager
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class BatterySample:
    """A single battery status reading."""

    timestamp: str
    level: int          # 0-100 %
    temp_c: float       # degrees Celsius
    voltage_mv: int     # millivolts
    status: str         # "Charging" | "Discharging" | "Full" | "Not charging"
    health: str         # "Good" | "Overheat" | "Dead" | etc.

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "temp_c": self.temp_c,
            "voltage_mv": self.voltage_mv,
            "status": self.status,
            "health": self.health,
        }


# Status/health code → human label maps
_STATUS_LABELS: dict[int, str] = {
    1: "Unknown", 2: "Charging", 3: "Discharging",
    4: "Not charging", 5: "Full",
}
_HEALTH_LABELS: dict[int, str] = {
    1: "Unknown", 2: "Good", 3: "Overheat",
    4: "Dead", 5: "Over voltage", 6: "Unspecified failure", 7: "Cold",
}


# ── Worker ────────────────────────────────────────────────────────────────────


class BatteryMonitorWorker(BaseWorker):
    """Poll battery status periodically and emit structured samples.

    Signals:
        sample_ready(BatterySample)  — emitted after each poll
        alert(str)                   — emitted when temperature > threshold
    """

    sample_ready = Signal(object)   # BatterySample
    alert        = Signal(str)      # alert message

    def __init__(
        self,
        serial: str,
        poll_interval_s: float = 30.0,
        temp_alert_c: float = 45.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._serial = serial
        self._interval = poll_interval_s
        self._temp_alert = temp_alert_c
        self._aborted = False

    @Slot()
    def start(self) -> None:
        try:
            while not self._aborted:
                sample = self._poll()
                if sample:
                    self.sample_ready.emit(sample)
                    if sample.temp_c >= self._temp_alert:
                        self.alert.emit(
                            f"Battery temperature {sample.temp_c:.1f}°C exceeds "
                            f"alert threshold {self._temp_alert:.1f}°C"
                        )
                # Sleep in small increments to allow abort
                elapsed = 0.0
                while elapsed < self._interval and not self._aborted:
                    time.sleep(0.5)
                    elapsed += 0.5
        except Exception as exc:
            logger.exception("BatteryMonitorWorker error")
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    def abort(self) -> None:
        """Stop the polling loop."""
        self._aborted = True

    def _poll(self) -> BatterySample | None:
        """Fetch and parse one battery status reading."""
        output = AdbManager.shell(self._serial, "dumpsys battery", timeout=10)
        if not output.strip():
            return None
        return self._parse(output)

    @classmethod
    def _parse(cls, output: str) -> BatterySample | None:
        """Parse dumpsys battery output into a BatterySample."""
        def _int(pattern: str, default: int = 0) -> int:
            m = re.search(pattern, output)
            return int(m.group(1)) if m else default

        try:
            level       = _int(r"level:\s*(\d+)")
            temp_raw    = _int(r"temperature:\s*(\d+)")
            voltage     = _int(r"voltage:\s*(\d+)")
            status_code = _int(r"status:\s*(\d+)", 1)
            health_code = _int(r"health:\s*(\d+)", 1)

            return BatterySample(
                timestamp=datetime.utcnow().isoformat() + "Z",
                level=level,
                temp_c=temp_raw / 10.0,
                voltage_mv=voltage,
                status=_STATUS_LABELS.get(status_code, "Unknown"),
                health=_HEALTH_LABELS.get(health_code, "Unknown"),
            )
        except Exception as exc:
            logger.debug("BatteryMonitorWorker._parse error: %s", exc)
            return None
