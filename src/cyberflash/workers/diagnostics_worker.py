"""DiagnosticsWorker — collects ADB device diagnostics in a background thread."""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal, Slot

from cyberflash.core.adb_manager import AdbManager
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)

# (category, display_key, adb_shell_command, value_parser_hint)
_DIAG_COMMANDS: list[tuple[str, str, str]] = [
    # Device Info
    ("Device Info", "Model", "getprop ro.product.model"),
    ("Device Info", "Brand", "getprop ro.product.brand"),
    ("Device Info", "Codename", "getprop ro.product.device"),
    ("Device Info", "Android Version", "getprop ro.build.version.release"),
    ("Device Info", "SDK Level", "getprop ro.build.version.sdk"),
    ("Device Info", "Build Number", "getprop ro.build.display.id"),
    ("Device Info", "Chipset", "getprop ro.hardware"),
    ("Device Info", "CPU ABI", "getprop ro.product.cpu.abi"),
    # Battery
    ("Battery", "Level", "dumpsys battery | grep -E '^  level'"),
    ("Battery", "Status", "dumpsys battery | grep -E '^  status'"),
    ("Battery", "Health", "dumpsys battery | grep -E '^  health'"),
    ("Battery", "Temperature (°C)", "dumpsys battery | grep -E '^  temperature'"),
    ("Battery", "Voltage (mV)", "dumpsys battery | grep -E '^  voltage'"),
    # Storage
    ("Storage", "/data usage", "df -h /data 2>/dev/null | tail -1"),
    ("Storage", "/system usage", "df -h /system 2>/dev/null | tail -1"),
    ("Storage", "/sdcard usage", "df -h /sdcard 2>/dev/null | tail -1"),
    # Memory
    ("Memory", "Total RAM", "cat /proc/meminfo | grep MemTotal"),
    ("Memory", "Available RAM", "cat /proc/meminfo | grep MemAvailable"),
    ("Memory", "Buffers", "cat /proc/meminfo | grep Buffers"),
    # CPU
    ("CPU", "Hardware", "cat /proc/cpuinfo | grep Hardware | head -1"),
    ("CPU", "Processor count", "cat /proc/cpuinfo | grep -c '^processor'"),
    ("CPU", "CPU Governor", "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo N/A"),
    ("CPU", "CPU Max Freq (kHz)", "cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq 2>/dev/null || echo N/A"),
    # Security
    ("Security", "SELinux mode", "getenforce 2>/dev/null || echo N/A"),
    ("Security", "Verified Boot", "getprop ro.boot.verifiedbootstate"),
    ("Security", "Bootloader", "getprop ro.boot.flash.locked"),
    ("Security", "Security Patch", "getprop ro.build.version.security_patch"),
]


class DiagnosticsWorker(BaseWorker):
    """Run ADB diagnostics commands and emit results per category.

    Signals:
        result_ready(category, key, value) — one result row
        log_line(text) — raw command/result for log panel
        diagnostics_complete() — all commands finished
    """

    result_ready = Signal(str, str, str)   # category, key, value
    log_line = Signal(str)
    diagnostics_complete = Signal()

    def __init__(self, serial: str, parent=None) -> None:
        super().__init__(parent)
        self._serial = serial

    @Slot()
    def start(self) -> None:
        total = len(_DIAG_COMMANDS)
        self.log_line.emit(f"Running {total} diagnostic checks on {self._serial}…")

        for idx, (category, key, cmd) in enumerate(_DIAG_COMMANDS):
            self.log_line.emit(f"[{idx + 1}/{total}] {cmd}")
            try:
                raw = AdbManager.shell(self._serial, cmd, timeout=8).strip()
            except Exception as exc:
                logger.warning("Diagnostic command failed: %s — %s", cmd, exc)
                raw = "error"

            value = _clean_value(key, raw)
            self.log_line.emit(f"  → {value}")
            self.result_ready.emit(category, key, value)

        self.log_line.emit("Diagnostics complete.")
        self.diagnostics_complete.emit()
        self.finished.emit()


def _clean_value(key: str, raw: str) -> str:
    """Strip redundant prefixes from dumpsys battery output etc."""
    if not raw:
        return "N/A"

    # dumpsys battery lines look like: "  level: 85"
    if ":" in raw and raw.count("\n") == 0:
        parts = raw.split(":", 1)
        if len(parts) == 2:
            cleaned = parts[1].strip()
            if cleaned:
                # Temperature is in tenths of a degree
                if "temperature" in key.lower():
                    try:
                        return f"{int(cleaned) / 10:.1f}"
                    except ValueError:
                        pass
                return cleaned

    # df output: take the whole line
    if key.endswith("usage"):
        return raw.splitlines()[-1].strip() if raw.strip() else "N/A"

    return raw.strip() or "N/A"
