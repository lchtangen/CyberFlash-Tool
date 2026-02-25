"""Background worker for automated operations and command execution.

Runs pre-flight checks, command execution, logcat streaming, and
device health monitoring off the main thread.  Extends ``BaseWorker``
and follows the ``moveToThread`` pattern.
"""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal, Slot

from cyberflash.core.command_executor import (
    CommandExecutor,
    CommandStatus,
)
from cyberflash.core.tool_manager import ToolManager
from cyberflash.workers.base_worker import BaseWorker

if TYPE_CHECKING:
    from cyberflash.models.device import DeviceInfo

logger = logging.getLogger(__name__)


class AutomationWorker(BaseWorker):
    """Executes automated commands and streams diagnostics off the main thread.

    Signals:
        command_result(object)     — CommandResult after execution
        preflight_result(object)   — PreflightResult after checks
        logcat_line(str)           — Single logcat line during streaming
        logcat_stopped()           — Logcat streaming ended
        health_metrics(dict)       — dict of health metric key→value
        audit_log(list)            — Updated audit trail
    """

    command_result = Signal(object)  # CommandResult
    preflight_result = Signal(object)  # PreflightResult
    logcat_line = Signal(str)
    logcat_stopped = Signal()
    health_metrics = Signal(dict)
    audit_log = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self._executor: CommandExecutor | None = None
        self._logcat_proc: subprocess.Popen | None = None
        self._logcat_running = False

    # ── Device context ───────────────────────────────────────────────────────

    @Slot(object)
    def set_device(self, device: DeviceInfo) -> None:
        """Update the device context for all operations."""
        self._executor = CommandExecutor(device)

    # ── Pre-flight checks ────────────────────────────────────────────────────

    @Slot(str)
    def run_preflight(self, operation: str) -> None:
        """Run pre-flight checks and emit the result."""
        if not self._executor:
            self.error.emit("No device set for pre-flight checks")
            return
        try:
            result = self._executor.run_preflight(operation)
            self.preflight_result.emit(result)
        except Exception as exc:
            logger.exception("Preflight check failed")
            self.error.emit(f"Pre-flight error: {exc}")

    @Slot(str, str)
    def run_preflight_flash(self, source_path: str, expected_hash: str) -> None:
        """Run flash-specific pre-flight with source validation."""
        if not self._executor:
            self.error.emit("No device set for pre-flight checks")
            return
        try:
            result = self._executor.run_preflight(
                "flash",
                source_path=source_path,
                expected_hash=expected_hash,
            )
            self.preflight_result.emit(result)
        except Exception as exc:
            logger.exception("Flash preflight failed")
            self.error.emit(f"Pre-flight error: {exc}")

    # ── Command execution ────────────────────────────────────────────────────

    @Slot(str)
    def execute_reboot(self, mode: str) -> None:
        """Reboot device to specified mode."""
        if not self._executor:
            self.error.emit("No device set")
            return
        try:
            result = self._executor.reboot(mode)
            self.command_result.emit(result)
            self.audit_log.emit(self._executor.audit_log)
        except Exception as exc:
            logger.exception("Reboot command failed")
            self.error.emit(f"Reboot error: {exc}")

    @Slot(str, int)
    def execute_shell(self, command: str, timeout: int) -> None:
        """Run an ADB shell command."""
        if not self._executor:
            self.error.emit("No device set")
            return
        try:
            result = self._executor.run_shell(command, timeout=timeout)
            self.command_result.emit(result)
        except Exception as exc:
            logger.exception("Shell command failed")
            self.error.emit(f"Shell error: {exc}")

    @Slot(str)
    def execute_slot_switch(self, slot: str) -> None:
        """Switch the active A/B partition slot."""
        if not self._executor:
            self.error.emit("No device set")
            return
        try:
            result = self._executor.switch_slot(slot)
            self.command_result.emit(result)
        except Exception as exc:
            logger.exception("Slot switch failed")
            self.error.emit(f"Slot switch error: {exc}")

    @Slot(str)
    def execute_erase(self, partition: str) -> None:
        """Erase a device partition."""
        if not self._executor:
            self.error.emit("No device set")
            return
        try:
            result = self._executor.erase_partition(partition)
            self.command_result.emit(result)
        except Exception as exc:
            logger.exception("Partition erase failed")
            self.error.emit(f"Erase error: {exc}")

    @Slot(str, str)
    def execute_flash_partition(self, partition: str, image_path: str) -> None:
        """Flash an image to a device partition."""
        if not self._executor:
            self.error.emit("No device set")
            return
        try:
            result = self._executor.flash_partition(partition, image_path)
            self.command_result.emit(result)
        except Exception as exc:
            logger.exception("Partition flash failed")
            self.error.emit(f"Flash error: {exc}")

    @Slot()
    def execute_get_info(self) -> None:
        """Collect comprehensive device information."""
        if not self._executor:
            self.error.emit("No device set")
            return
        try:
            result = self._executor.get_device_info()
            self.command_result.emit(result)
        except Exception as exc:
            logger.exception("Get info failed")
            self.error.emit(f"Info error: {exc}")

    @Slot()
    def execute_get_slot_info(self) -> None:
        """Query A/B slot information."""
        if not self._executor:
            self.error.emit("No device set")
            return
        try:
            result = self._executor.get_slot_info()
            self.command_result.emit(result)
        except Exception as exc:
            logger.exception("Slot info failed")
            self.error.emit(f"Slot info error: {exc}")

    # ── Health monitoring ────────────────────────────────────────────────────

    @Slot()
    def collect_health_metrics(self) -> None:
        """Collect current device health metrics for diagnostics display."""
        if not self._executor:
            self.error.emit("No device set")
            return

        metrics: dict[str, str] = {}
        try:
            # Battery
            bat_result = self._executor.get_battery_info()
            if bat_result.status == CommandStatus.COMPLETED:
                metrics.update(self._parse_battery(bat_result.output))

            # Storage
            stor_result = self._executor.get_storage_info()
            if stor_result.status == CommandStatus.COMPLETED:
                metrics["storage_raw"] = stor_result.output

            # Thermal
            therm_result = self._executor.get_thermal_info()
            if therm_result.status == CommandStatus.COMPLETED:
                metrics.update(self._parse_thermal(therm_result.output))

            # Uptime
            from cyberflash.core.adb_manager import AdbManager

            uptime = AdbManager.shell(
                self._executor.device.serial,
                "cat /proc/uptime",
                timeout=5,
            ).strip()
            if uptime:
                secs = int(float(uptime.split()[0]))
                hrs, rem = divmod(secs, 3600)
                mins = rem // 60
                metrics["uptime"] = f"{hrs}h {mins}m"

            # USB mode
            usb = AdbManager.shell(
                self._executor.device.serial,
                "getprop sys.usb.config",
                timeout=5,
            ).strip()
            metrics["usb_mode"] = usb or "unknown"

            # RAM
            meminfo = AdbManager.shell(
                self._executor.device.serial,
                "cat /proc/meminfo | head -3",
                timeout=5,
            ).strip()
            if meminfo:
                metrics.update(self._parse_meminfo(meminfo))

            self.health_metrics.emit(metrics)
        except Exception as exc:
            logger.exception("Health metrics collection failed")
            self.error.emit(f"Health metrics error: {exc}")

    # ── Logcat streaming ─────────────────────────────────────────────────────

    @Slot(str)
    def start_logcat(self, filter_tag: str) -> None:
        """Start streaming logcat output. Filter by tag if provided."""
        if self._logcat_running:
            self.error.emit("Logcat already running")
            return
        if not self._executor:
            self.error.emit("No device set")
            return

        try:
            serial = self._executor.device.serial
            adb_cmd = ToolManager.adb_cmd()
            cmd = [*adb_cmd, "-s", serial, "logcat", "-v", "threadtime"]
            if filter_tag.strip():
                cmd.extend(["-s", filter_tag.strip()])

            self._logcat_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._logcat_running = True

            # Stream line by line
            while self._logcat_running and self._logcat_proc.poll() is None:
                line = self._logcat_proc.stdout.readline()  # type: ignore[union-attr]
                if line:
                    self.logcat_line.emit(line.rstrip("\n"))

            self._logcat_running = False
            self.logcat_stopped.emit()
        except Exception as exc:
            self._logcat_running = False
            logger.exception("Logcat streaming error")
            self.error.emit(f"Logcat error: {exc}")
            self.logcat_stopped.emit()

    @Slot()
    def stop_logcat(self) -> None:
        """Stop the current logcat stream."""
        self._logcat_running = False
        if self._logcat_proc and self._logcat_proc.poll() is None:
            self._logcat_proc.terminate()
            try:
                self._logcat_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._logcat_proc.kill()
        self._logcat_proc = None

    # ── Internal parsers ─────────────────────────────────────────────────────

    @staticmethod
    def _parse_battery(dumpsys_output: str) -> dict[str, str]:
        """Parse 'dumpsys battery' output into metrics."""
        metrics: dict[str, str] = {}
        for line in dumpsys_output.splitlines():
            line = line.strip()
            if line.startswith("level:"):
                metrics["battery"] = line.split(":", 1)[1].strip() + "%"
            elif line.startswith("health:"):
                val = line.split(":", 1)[1].strip()
                health_map = {"2": "Good", "3": "Overheat", "4": "Dead", "5": "Over voltage"}
                metrics["bat_health"] = health_map.get(val, val)
            elif line.startswith("temperature:"):
                val = line.split(":", 1)[1].strip()
                try:
                    temp_c = int(val) / 10.0
                    metrics["bat_temp"] = f"{temp_c:.1f}°C"
                except ValueError:
                    metrics["bat_temp"] = val
        return metrics

    @staticmethod
    def _parse_thermal(thermal_output: str) -> dict[str, str]:
        """Parse thermal zone temperatures."""
        temps: list[float] = []
        for line in thermal_output.splitlines():
            line = line.strip()
            if line.isdigit():
                temps.append(int(line) / 1000.0)
        if temps:
            return {"cpu_temp": f"{max(temps):.1f}°C"}
        return {}

    @staticmethod
    def _parse_meminfo(meminfo: str) -> dict[str, str]:
        """Parse /proc/meminfo first 3 lines."""
        result: dict[str, str] = {}
        for line in meminfo.splitlines():
            if "MemTotal" in line:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        total_mb = int(parts[1]) / 1024
                        result["ram_total"] = f"{total_mb:.0f} MB"
                    except ValueError:
                        pass
            elif "MemAvailable" in line or "MemFree" in line:
                parts = line.split()
                if len(parts) >= 2 and "ram" not in result:
                    try:
                        free_mb = int(parts[1]) / 1024
                        result["ram"] = f"{free_mb:.0f} MB free"
                    except ValueError:
                        pass
        return result
