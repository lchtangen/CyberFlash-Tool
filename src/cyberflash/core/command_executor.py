"""Command executor for AI-driven automated operations.

Bridges the gap between the AI's recommendations and actual device
operations.  Provides a safe, audited interface for executing ADB,
fastboot, and composite commands with pre-flight checks, risk
assessment, and logging.

Pure Python — no Qt dependency.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.fastboot_manager import FastbootManager
from cyberflash.core.partition_manager import PartitionManager
from cyberflash.core.preflight_checker import PreflightChecker, PreflightResult

if TYPE_CHECKING:
    from cyberflash.models.device import DeviceInfo

logger = logging.getLogger(__name__)


class CommandType(StrEnum):
    """Categories of executable commands."""

    REBOOT = "reboot"
    SHELL = "shell"
    BACKUP = "backup"
    FLASH = "flash"
    PARTITION = "partition"
    ROOT = "root"
    DIAGNOSTICS = "diagnostics"
    INFO = "info"


class CommandStatus(StrEnum):
    """Execution status for a command."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"  # Pre-flight check failed
    CANCELLED = "cancelled"


@dataclass
class CommandResult:
    """Result of a single command execution."""

    command_id: str
    command_type: CommandType
    status: CommandStatus
    message: str
    output: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    preflight: PreflightResult | None = None

    @property
    def elapsed(self) -> float:
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return 0.0

    @property
    def elapsed_str(self) -> str:
        e = self.elapsed
        if e < 1:
            return f"{e * 1000:.0f}ms"
        return f"{e:.1f}s"


@dataclass
class CommandLogEntry:
    """An auditable log entry for executed commands."""

    timestamp: float
    command_id: str
    command_type: CommandType
    description: str
    status: CommandStatus
    device_serial: str = ""


class CommandExecutor:
    """Execute device commands with pre-flight safety and audit logging.

    This class provides the execution layer between the AI engine's
    recommendations and actual device operations.  Every execution is:
    1. Logged to the audit trail
    2. Optionally pre-flight checked
    3. Executed with proper error handling
    4. Result captured and returned

    Usage::

        executor = CommandExecutor(device_info)
        result = executor.reboot("bootloader")
        if result.status == CommandStatus.COMPLETED:
            ...
    """

    def __init__(self, device: DeviceInfo) -> None:
        self._device = device
        self._log: list[CommandLogEntry] = []
        self._checker = PreflightChecker(device)

    @property
    def audit_log(self) -> list[CommandLogEntry]:
        """Read-only access to the command audit trail."""
        return list(self._log)

    @property
    def device(self) -> DeviceInfo:
        return self._device

    # ── Reboot commands ──────────────────────────────────────────────────────

    def reboot(self, mode: str = "") -> CommandResult:
        """Reboot device to a specific mode.

        Args:
            mode: "" for system, "bootloader", "recovery", "fastboot", "edl"
        """
        cmd_id = f"reboot_{mode or 'system'}_{int(time.time())}"
        desc = f"Reboot to {mode or 'system'}"
        self._audit(cmd_id, CommandType.REBOOT, desc)

        try:
            serial = self._device.serial
            if self._device.is_adb_device:
                ok = AdbManager.reboot(serial, mode) if mode else AdbManager.reboot(serial)
            elif self._device.is_fastboot_device:
                if mode == "bootloader":
                    ok = FastbootManager.reboot(serial, mode="bootloader")
                elif mode == "recovery":
                    ok = FastbootManager.reboot(serial, mode="")
                else:
                    ok = FastbootManager.reboot(serial)
            else:
                return self._result(
                    cmd_id,
                    CommandType.REBOOT,
                    CommandStatus.FAILED,
                    "Device is not in ADB or fastboot mode.",
                )

            if ok:
                return self._result(
                    cmd_id,
                    CommandType.REBOOT,
                    CommandStatus.COMPLETED,
                    f"Rebooted to {mode or 'system'} successfully.",
                )
            return self._result(
                cmd_id,
                CommandType.REBOOT,
                CommandStatus.FAILED,
                f"Reboot to {mode or 'system'} failed.",
            )
        except Exception as exc:
            return self._result(
                cmd_id,
                CommandType.REBOOT,
                CommandStatus.FAILED,
                f"Reboot error: {exc}",
            )

    # ── Shell / info commands ────────────────────────────────────────────────

    def run_shell(self, command: str, timeout: int = 10) -> CommandResult:
        """Run an ADB shell command on the device."""
        cmd_id = f"shell_{int(time.time())}"
        desc = f"Shell: {command[:60]}"
        self._audit(cmd_id, CommandType.SHELL, desc)

        try:
            output = AdbManager.shell(self._device.serial, command, timeout=timeout)
            return self._result(
                cmd_id,
                CommandType.SHELL,
                CommandStatus.COMPLETED,
                "Shell command executed.",
                output=output.strip(),
            )
        except Exception as exc:
            return self._result(
                cmd_id,
                CommandType.SHELL,
                CommandStatus.FAILED,
                f"Shell error: {exc}",
            )

    def get_device_info(self) -> CommandResult:
        """Collect comprehensive device information."""
        cmd_id = f"info_{int(time.time())}"
        self._audit(cmd_id, CommandType.INFO, "Collect device info")

        try:
            serial = self._device.serial
            props = AdbManager.get_props_batch(
                serial,
                [
                    "ro.product.model",
                    "ro.product.brand",
                    "ro.build.display.id",
                    "ro.build.version.release",
                    "ro.build.version.sdk",
                    "ro.build.version.security_patch",
                    "ro.boot.slot_suffix",
                    "ro.crypto.state",
                ],
            )
            lines = [f"{k}: {v}" for k, v in props.items()]
            output = "\n".join(lines)
            return self._result(
                cmd_id,
                CommandType.INFO,
                CommandStatus.COMPLETED,
                "Device info collected.",
                output=output,
            )
        except Exception as exc:
            return self._result(
                cmd_id,
                CommandType.INFO,
                CommandStatus.FAILED,
                f"Info collection error: {exc}",
            )

    # ── Partition commands ───────────────────────────────────────────────────

    def switch_slot(self, slot: str) -> CommandResult:
        """Switch the active A/B slot."""
        cmd_id = f"slot_{slot}_{int(time.time())}"
        desc = f"Switch active slot to {slot}"
        self._audit(cmd_id, CommandType.PARTITION, desc)

        # Pre-flight
        check = self._checker.check_partition()
        if not check.passed:
            return self._result(
                cmd_id,
                CommandType.PARTITION,
                CommandStatus.BLOCKED,
                f"Pre-flight failed: {check.summary}",
                preflight=check,
            )

        try:
            ok = PartitionManager.set_active_slot(self._device.serial, slot)
            if ok:
                return self._result(
                    cmd_id,
                    CommandType.PARTITION,
                    CommandStatus.COMPLETED,
                    f"Active slot switched to {slot}.",
                )
            return self._result(
                cmd_id,
                CommandType.PARTITION,
                CommandStatus.FAILED,
                f"Failed to switch slot to {slot}.",
            )
        except Exception as exc:
            return self._result(
                cmd_id,
                CommandType.PARTITION,
                CommandStatus.FAILED,
                f"Slot switch error: {exc}",
            )

    def get_slot_info(self) -> CommandResult:
        """Query A/B slot information from the device."""
        cmd_id = f"slot_info_{int(time.time())}"
        self._audit(cmd_id, CommandType.INFO, "Query slot info")

        try:
            info = PartitionManager.get_slot_info(self._device.serial)
            output = "\n".join(f"{k}: {v}" for k, v in info.items())
            return self._result(
                cmd_id,
                CommandType.INFO,
                CommandStatus.COMPLETED,
                "Slot info retrieved.",
                output=output,
            )
        except Exception as exc:
            return self._result(
                cmd_id,
                CommandType.INFO,
                CommandStatus.FAILED,
                f"Slot info error: {exc}",
            )

    def erase_partition(self, partition: str) -> CommandResult:
        """Erase a partition via fastboot."""
        cmd_id = f"erase_{partition}_{int(time.time())}"
        desc = f"Erase partition: {partition}"
        self._audit(cmd_id, CommandType.PARTITION, desc)

        check = self._checker.check_partition()
        if not check.passed:
            return self._result(
                cmd_id,
                CommandType.PARTITION,
                CommandStatus.BLOCKED,
                f"Pre-flight failed: {check.summary}",
                preflight=check,
            )

        try:
            ok, output = FastbootManager.erase(self._device.serial, partition)
            if ok:
                return self._result(
                    cmd_id,
                    CommandType.PARTITION,
                    CommandStatus.COMPLETED,
                    f"Partition '{partition}' erased.",
                    output=output,
                )
            return self._result(
                cmd_id,
                CommandType.PARTITION,
                CommandStatus.FAILED,
                f"Erase failed: {output}",
                output=output,
            )
        except Exception as exc:
            return self._result(
                cmd_id,
                CommandType.PARTITION,
                CommandStatus.FAILED,
                f"Erase error: {exc}",
            )

    def flash_partition(self, partition: str, image_path: str) -> CommandResult:
        """Flash an image to a partition via fastboot."""
        cmd_id = f"flash_{partition}_{int(time.time())}"
        desc = f"Flash {partition} ← {Path(image_path).name}"
        self._audit(cmd_id, CommandType.FLASH, desc)

        check = self._checker.check_partition()
        if not check.passed:
            return self._result(
                cmd_id,
                CommandType.FLASH,
                CommandStatus.BLOCKED,
                f"Pre-flight failed: {check.summary}",
                preflight=check,
            )

        path = Path(image_path)
        if not path.exists():
            return self._result(
                cmd_id,
                CommandType.FLASH,
                CommandStatus.FAILED,
                f"Image file not found: {image_path}",
            )

        try:
            ok, output = FastbootManager.flash(
                self._device.serial,
                partition,
                path,
                timeout=300,
            )
            if ok:
                return self._result(
                    cmd_id,
                    CommandType.FLASH,
                    CommandStatus.COMPLETED,
                    f"Flashed {partition} successfully.",
                    output=output,
                )
            return self._result(
                cmd_id,
                CommandType.FLASH,
                CommandStatus.FAILED,
                f"Flash failed: {output}",
                output=output,
            )
        except Exception as exc:
            return self._result(
                cmd_id,
                CommandType.FLASH,
                CommandStatus.FAILED,
                f"Flash error: {exc}",
            )

    # ── Diagnostics commands ─────────────────────────────────────────────────

    def get_battery_info(self) -> CommandResult:
        """Read detailed battery information from the device."""
        cmd_id = f"battery_{int(time.time())}"
        self._audit(cmd_id, CommandType.DIAGNOSTICS, "Battery info")

        try:
            output = AdbManager.shell(self._device.serial, "dumpsys battery")
            return self._result(
                cmd_id,
                CommandType.DIAGNOSTICS,
                CommandStatus.COMPLETED,
                "Battery info retrieved.",
                output=output.strip(),
            )
        except Exception as exc:
            return self._result(
                cmd_id,
                CommandType.DIAGNOSTICS,
                CommandStatus.FAILED,
                f"Battery info error: {exc}",
            )

    def get_storage_info(self) -> CommandResult:
        """Get device storage usage."""
        cmd_id = f"storage_{int(time.time())}"
        self._audit(cmd_id, CommandType.DIAGNOSTICS, "Storage info")

        try:
            output = AdbManager.shell(self._device.serial, "df -h /data /system /vendor")
            return self._result(
                cmd_id,
                CommandType.DIAGNOSTICS,
                CommandStatus.COMPLETED,
                "Storage info retrieved.",
                output=output.strip(),
            )
        except Exception as exc:
            return self._result(
                cmd_id,
                CommandType.DIAGNOSTICS,
                CommandStatus.FAILED,
                f"Storage info error: {exc}",
            )

    def get_thermal_info(self) -> CommandResult:
        """Get device thermal zone information."""
        cmd_id = f"thermal_{int(time.time())}"
        self._audit(cmd_id, CommandType.DIAGNOSTICS, "Thermal info")

        try:
            output = AdbManager.shell(
                self._device.serial,
                "cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | head -5",
            )
            return self._result(
                cmd_id,
                CommandType.DIAGNOSTICS,
                CommandStatus.COMPLETED,
                "Thermal info retrieved.",
                output=output.strip(),
            )
        except Exception as exc:
            return self._result(
                cmd_id,
                CommandType.DIAGNOSTICS,
                CommandStatus.FAILED,
                f"Thermal info error: {exc}",
            )

    # ── Pre-flight runners ───────────────────────────────────────────────────

    def run_preflight(self, operation: str, **kwargs: str) -> PreflightResult:
        """Run pre-flight checks for a given operation type."""
        if operation == "flash":
            return self._checker.check_flash(
                source_path=kwargs.get("source_path"),
                expected_hash=kwargs.get("expected_hash"),
            )
        if operation == "root":
            return self._checker.check_root()
        if operation == "backup":
            return self._checker.check_backup()
        if operation == "partition":
            return self._checker.check_partition()
        return self._checker.check_generic()

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _audit(self, cmd_id: str, cmd_type: CommandType, desc: str) -> None:
        """Record a command execution to the audit trail."""
        entry = CommandLogEntry(
            timestamp=time.time(),
            command_id=cmd_id,
            command_type=cmd_type,
            description=desc,
            status=CommandStatus.RUNNING,
            device_serial=self._device.serial,
        )
        self._log.append(entry)
        logger.info("CMD [%s] %s: %s", self._device.serial, cmd_type, desc)

    def _result(
        self,
        cmd_id: str,
        cmd_type: CommandType,
        status: CommandStatus,
        message: str,
        output: str = "",
        preflight: PreflightResult | None = None,
    ) -> CommandResult:
        """Build a CommandResult and update the audit trail."""
        result = CommandResult(
            command_id=cmd_id,
            command_type=cmd_type,
            status=status,
            message=message,
            output=output,
            started_at=time.time(),
            finished_at=time.time(),
            preflight=preflight,
        )
        # Update audit log
        for entry in self._log:
            if entry.command_id == cmd_id:
                entry.status = status
                break

        level = logging.INFO if status == CommandStatus.COMPLETED else logging.WARNING
        logger.log(level, "CMD [%s] %s → %s: %s", self._device.serial, cmd_id, status, message)
        return result
