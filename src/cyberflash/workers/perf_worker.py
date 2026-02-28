"""perf_worker.py — Performance profiler worker (Phase 10).

Monitors CPU frequency/governor per core, RAM pressure, and I/O stats
from ``/proc`` on the connected Android device.  Emits a ``snapshot``
signal on every poll interval so the UI can update sparkline charts.

Usage::

    worker = PerfWorker("SERIAL001", interval_ms=2000)
    worker.snapshot.connect(on_snapshot)
    # (move to thread + start via QThread pattern)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from PySide6.QtCore import Signal

from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class CpuCoreInfo:
    """Frequency data for a single CPU core."""

    core_id: int
    cur_freq_khz: int = 0
    min_freq_khz: int = 0
    max_freq_khz: int = 0
    governor: str = "unknown"
    online: bool = True

    @property
    def utilisation(self) -> float:
        """Approximate utilisation based on cur/max ratio (0.0-1.0)."""
        if self.max_freq_khz <= 0:
            return 0.0
        return min(1.0, self.cur_freq_khz / self.max_freq_khz)


@dataclass
class RamInfo:
    """Parsed /proc/meminfo snapshot."""

    total_kb: int = 0
    available_kb: int = 0
    free_kb: int = 0
    cached_kb: int = 0

    @property
    def used_kb(self) -> int:
        return max(0, self.total_kb - self.available_kb)

    @property
    def pressure(self) -> float:
        """Pressure ratio: 0.0 (plenty of RAM) to 1.0 (fully pressured)."""
        if self.total_kb <= 0:
            return 0.0
        return min(1.0, self.used_kb / self.total_kb)


@dataclass
class IoStats:
    """Aggregated I/O stats from /proc/diskstats."""

    reads_completed: int = 0
    writes_completed: int = 0
    read_kb: int = 0
    write_kb: int = 0


@dataclass
class PerfSnapshot:
    """A single performance measurement snapshot."""

    serial: str = ""
    cores: list[CpuCoreInfo] = field(default_factory=list)
    ram: RamInfo = field(default_factory=RamInfo)
    io: IoStats = field(default_factory=IoStats)
    cpu_temp_celsius: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        """Serialise to a JSON-compatible dict."""
        return {
            "serial": self.serial,
            "cpu_temp": self.cpu_temp_celsius,
            "ram_pressure": self.ram.pressure,
            "ram_used_kb": self.ram.used_kb,
            "ram_total_kb": self.ram.total_kb,
            "cores": [
                {
                    "id": c.core_id,
                    "cur_khz": c.cur_freq_khz,
                    "max_khz": c.max_freq_khz,
                    "governor": c.governor,
                    "online": c.online,
                    "util": c.utilisation,
                }
                for c in self.cores
            ],
            "io_reads": self.io.reads_completed,
            "io_writes": self.io.writes_completed,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

_CPUFREQ = "/sys/devices/system/cpu"
_MEMINFO = "/proc/meminfo"
_DISKSTATS = "/proc/diskstats"
_THERMAL = "/sys/class/thermal/thermal_zone0/temp"


class PerfWorker(BaseWorker):
    """:class:`BaseWorker` that polls device performance metrics.

    Signals:
        snapshot(PerfSnapshot): emitted every *interval_ms* milliseconds.
    """

    snapshot = Signal(object)  # PerfSnapshot

    def __init__(
        self,
        serial: str,
        interval_ms: int = 2000,
        log_cb: object = None,
    ) -> None:
        super().__init__()
        self._serial = serial
        self._interval_ms = max(500, interval_ms)
        self._log_cb = log_cb or (lambda msg: logger.debug(msg))

    # ------------------------------------------------------------------
    # BaseWorker interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Main loop: poll until ``abort()`` is called."""
        from PySide6.QtCore import QThread

        self._log_cb(f"[PerfWorker] starting for {self._serial}")
        while not self._abort:
            snap = self._collect()
            self.snapshot.emit(snap)
            QThread.msleep(self._interval_ms)
        self._log_cb("[PerfWorker] stopped")
        self.finished.emit()

    # ------------------------------------------------------------------
    # Collection helpers
    # ------------------------------------------------------------------

    def _collect(self) -> PerfSnapshot:
        """Collect a full performance snapshot from the device."""
        snap = PerfSnapshot(serial=self._serial)
        try:
            snap.cores = self._collect_cpu_freqs()
            snap.ram = self._collect_meminfo()
            snap.io = self._collect_diskstats()
            snap.cpu_temp_celsius = self._collect_cpu_temp()
        except Exception as exc:
            snap.error = str(exc)
            logger.warning("PerfWorker collect error: %s", exc)
        return snap

    def _collect_cpu_freqs(self) -> list[CpuCoreInfo]:
        """Read cpufreq sysfs for each online CPU core."""
        from cyberflash.core.adb_manager import AdbManager

        cores: list[CpuCoreInfo] = []
        # Find how many cpuN directories exist
        ls_out = AdbManager.shell(self._serial, f"ls {_CPUFREQ}") or ""
        for entry in ls_out.splitlines():
            entry = entry.strip()
            if not entry.startswith("cpu") or not entry[3:].isdigit():
                continue
            core_id = int(entry[3:])
            base = f"{_CPUFREQ}/{entry}/cpufreq"
            info = CpuCoreInfo(core_id=core_id)

            def _read(path: str) -> str:
                return AdbManager.shell(self._serial, f"cat {path}") or ""

            cur = _read(f"{base}/scaling_cur_freq").strip()
            mn = _read(f"{base}/scaling_min_freq").strip()
            mx = _read(f"{base}/scaling_max_freq").strip()
            gov = _read(f"{base}/scaling_governor").strip()
            online = _read(
                f"{_CPUFREQ}/{entry}/online"
            ).strip()

            info.cur_freq_khz = int(cur) if cur.isdigit() else 0
            info.min_freq_khz = int(mn) if mn.isdigit() else 0
            info.max_freq_khz = int(mx) if mx.isdigit() else 0
            info.governor = gov or "unknown"
            info.online = online != "0"
            cores.append(info)
        return sorted(cores, key=lambda c: c.core_id)

    def _collect_meminfo(self) -> RamInfo:
        """Parse /proc/meminfo from the device."""
        from cyberflash.core.adb_manager import AdbManager

        raw = AdbManager.shell(self._serial, f"cat {_MEMINFO}") or ""
        info = RamInfo()
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            key = parts[0].rstrip(":")
            try:
                val = int(parts[1])
            except ValueError:
                continue
            if key == "MemTotal":
                info.total_kb = val
            elif key == "MemAvailable":
                info.available_kb = val
            elif key == "MemFree":
                info.free_kb = val
            elif key == "Cached":
                info.cached_kb = val
        return info

    def _collect_diskstats(self) -> IoStats:
        """Aggregate reads + writes across all block devices in /proc/diskstats."""
        from cyberflash.core.adb_manager import AdbManager

        raw = AdbManager.shell(self._serial, f"cat {_DISKSTATS}") or ""
        stats = IoStats()
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) < 14:
                continue
            # Major, minor, name, then stats
            try:
                stats.reads_completed += int(parts[3])
                stats.read_kb += int(parts[5]) // 2  # sectors → KB (512B)
                stats.writes_completed += int(parts[7])
                stats.write_kb += int(parts[9]) // 2
            except (ValueError, IndexError):
                pass
        return stats

    def _collect_cpu_temp(self) -> float:
        """Read CPU temperature from thermal_zone0 (millidegrees → °C)."""
        from cyberflash.core.adb_manager import AdbManager

        raw = AdbManager.shell(self._serial, f"cat {_THERMAL}") or ""
        raw = raw.strip()
        try:
            millideg = int(raw)
            # Android typically reports in millidegrees
            return millideg / 1000.0 if millideg > 1000 else float(millideg)
        except ValueError:
            return 0.0

    # ------------------------------------------------------------------
    # Snapshot export
    # ------------------------------------------------------------------

    @staticmethod
    def snapshot_to_json(snap: PerfSnapshot) -> str:
        """Serialise a snapshot to a JSON string."""
        return json.dumps(snap.to_dict(), indent=2)
