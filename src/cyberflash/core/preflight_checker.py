"""Pre-flight safety checker for device operations.

Runs a comprehensive set of automated checks before any destructive
operation (flash, partition write, root install, etc.).  Returns a
structured result with pass/fail/warning for each check.

Pure Python — no Qt dependency.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from cyberflash.core.tool_manager import ToolManager
from cyberflash.models.device import DeviceInfo, DeviceState

logger = logging.getLogger(__name__)


class CheckStatus(StrEnum):
    """Result status for a single pre-flight check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class CheckSeverity(StrEnum):
    """How important a check failure is."""

    BLOCKING = "blocking"  # Must pass or operation is blocked
    WARNING = "warning"  # User should be aware but can proceed
    INFO = "info"  # Informational only


@dataclass
class PreflightCheck:
    """A single pre-flight check result."""

    check_id: str
    name: str
    status: CheckStatus
    severity: CheckSeverity
    message: str
    detail: str = ""


@dataclass
class PreflightResult:
    """Aggregate result of all pre-flight checks."""

    checks: list[PreflightCheck] = field(default_factory=list)
    operation: str = ""

    @property
    def passed(self) -> bool:
        """True if no blocking checks failed."""
        return not any(
            c.status == CheckStatus.FAIL and c.severity == CheckSeverity.BLOCKING
            for c in self.checks
        )

    @property
    def has_warnings(self) -> bool:
        return any(c.status == CheckStatus.WARN for c in self.checks)

    @property
    def blocking_failures(self) -> list[PreflightCheck]:
        return [
            c
            for c in self.checks
            if c.status == CheckStatus.FAIL and c.severity == CheckSeverity.BLOCKING
        ]

    @property
    def warnings(self) -> list[PreflightCheck]:
        return [c for c in self.checks if c.status == CheckStatus.WARN]

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)

    @property
    def total_count(self) -> int:
        return len(self.checks)

    @property
    def summary(self) -> str:
        """Human-readable summary of all checks."""
        if self.passed and not self.has_warnings:
            return f"All {self.total_count} pre-flight checks passed. Safe to proceed."
        if self.passed and self.has_warnings:
            return (
                f"{self.pass_count}/{self.total_count} checks passed with "
                f"{len(self.warnings)} warning(s). Review before proceeding."
            )
        fails = self.blocking_failures
        return (
            f"Pre-flight BLOCKED: {len(fails)} critical issue(s) must be resolved.\n"
            + "\n".join(f"  • {f.name}: {f.message}" for f in fails)
        )


# ── Minimum battery thresholds ───────────────────────────────────────────────

MIN_BATTERY_FLASH = 25
MIN_BATTERY_ROOT = 20
MIN_BATTERY_BACKUP = 15
MIN_BATTERY_PARTITION = 30


class PreflightChecker:
    """Run pre-flight checks against a device before an operation.

    Usage::

        checker = PreflightChecker(device_info)
        result = checker.check_flash(source_path="/path/to/rom")
        if result.passed:
            # safe to proceed
        else:
            # show result.blocking_failures to user
    """

    def __init__(self, device: DeviceInfo) -> None:
        self._device = device

    # ── Operation-specific check suites ──────────────────────────────────────

    def check_flash(
        self,
        source_path: str | None = None,
        expected_hash: str | None = None,
    ) -> PreflightResult:
        """Run all pre-flash checks."""
        result = PreflightResult(operation="flash")
        result.checks.append(self._check_device_connected())
        result.checks.append(self._check_device_authorized())
        result.checks.append(self._check_battery(MIN_BATTERY_FLASH))
        result.checks.append(self._check_adb_available())
        result.checks.append(self._check_fastboot_available())
        result.checks.append(self._check_bootloader_state())
        if source_path:
            result.checks.append(self._check_source_exists(source_path))
        if expected_hash and source_path:
            result.checks.append(self._check_hash(source_path, expected_hash))
        result.checks.append(self._check_sufficient_host_storage())
        return result

    def check_root(self) -> PreflightResult:
        """Run pre-root checks."""
        result = PreflightResult(operation="root")
        result.checks.append(self._check_device_connected())
        result.checks.append(self._check_device_authorized())
        result.checks.append(self._check_battery(MIN_BATTERY_ROOT))
        result.checks.append(self._check_adb_available())
        result.checks.append(self._check_fastboot_available())
        result.checks.append(self._check_bootloader_state())
        return result

    def check_backup(self) -> PreflightResult:
        """Run pre-backup checks."""
        result = PreflightResult(operation="backup")
        result.checks.append(self._check_device_connected())
        result.checks.append(self._check_device_authorized())
        result.checks.append(self._check_battery(MIN_BATTERY_BACKUP))
        result.checks.append(self._check_adb_available())
        result.checks.append(self._check_sufficient_host_storage())
        return result

    def check_partition(self) -> PreflightResult:
        """Run pre-partition-operation checks."""
        result = PreflightResult(operation="partition")
        result.checks.append(self._check_device_connected())
        result.checks.append(self._check_battery(MIN_BATTERY_PARTITION))
        result.checks.append(self._check_fastboot_available())
        result.checks.append(self._check_fastboot_mode())
        return result

    def check_generic(self) -> PreflightResult:
        """Run basic device readiness checks."""
        result = PreflightResult(operation="generic")
        result.checks.append(self._check_device_connected())
        result.checks.append(self._check_device_authorized())
        result.checks.append(self._check_battery(MIN_BATTERY_BACKUP))
        result.checks.append(self._check_adb_available())
        return result

    # ── Individual checks ────────────────────────────────────────────────────

    def _check_device_connected(self) -> PreflightCheck:
        """Verify device is present in the list."""
        dev = self._device
        if dev.state == DeviceState.DISCONNECTED:
            return PreflightCheck(
                check_id="device_connected",
                name="Device Connection",
                status=CheckStatus.FAIL,
                severity=CheckSeverity.BLOCKING,
                message="No device connected.",
                detail="Connect the device via USB and ensure USB debugging is enabled.",
            )
        return PreflightCheck(
            check_id="device_connected",
            name="Device Connection",
            status=CheckStatus.PASS,
            severity=CheckSeverity.BLOCKING,
            message=f"Device {dev.serial} connected ({dev.state.label}).",
        )

    def _check_device_authorized(self) -> PreflightCheck:
        """Verify device is authorized for ADB communication."""
        dev = self._device
        if dev.state == DeviceState.UNAUTHORIZED:
            return PreflightCheck(
                check_id="device_authorized",
                name="USB Authorization",
                status=CheckStatus.FAIL,
                severity=CheckSeverity.BLOCKING,
                message="Device is unauthorized. Accept the USB debugging prompt on the device.",
            )
        if dev.state in (DeviceState.ONLINE, DeviceState.RECOVERY, DeviceState.SIDELOAD):
            return PreflightCheck(
                check_id="device_authorized",
                name="USB Authorization",
                status=CheckStatus.PASS,
                severity=CheckSeverity.BLOCKING,
                message="Device is authorized.",
            )
        return PreflightCheck(
            check_id="device_authorized",
            name="USB Authorization",
            status=CheckStatus.SKIP,
            severity=CheckSeverity.INFO,
            message=f"Authorization not applicable in {dev.state.label} mode.",
        )

    def _check_battery(self, minimum: int) -> PreflightCheck:
        """Verify battery level meets the minimum threshold."""
        level = self._device.battery_level
        if level < 0:
            return PreflightCheck(
                check_id="battery",
                name="Battery Level",
                status=CheckStatus.WARN,
                severity=CheckSeverity.WARNING,
                message="Battery level unknown — ensure device is adequately charged.",
            )
        if level < minimum:
            return PreflightCheck(
                check_id="battery",
                name="Battery Level",
                status=CheckStatus.FAIL,
                severity=CheckSeverity.BLOCKING,
                message=f"Battery too low ({level}%). Minimum {minimum}% required.",
                detail="Charge the device before proceeding to avoid bricking risks.",
            )
        return PreflightCheck(
            check_id="battery",
            name="Battery Level",
            status=CheckStatus.PASS,
            severity=CheckSeverity.BLOCKING,
            message=f"Battery at {level}% (minimum {minimum}%).",
        )

    def _check_adb_available(self) -> PreflightCheck:
        """Verify ADB binary is accessible."""
        if ToolManager.is_adb_available():
            return PreflightCheck(
                check_id="adb_available",
                name="ADB Tool",
                status=CheckStatus.PASS,
                severity=CheckSeverity.BLOCKING,
                message="ADB binary found and accessible.",
            )
        return PreflightCheck(
            check_id="adb_available",
            name="ADB Tool",
            status=CheckStatus.FAIL,
            severity=CheckSeverity.BLOCKING,
            message="ADB binary not found. Install platform-tools or check PATH.",
        )

    def _check_fastboot_available(self) -> PreflightCheck:
        """Verify fastboot binary is accessible."""
        if ToolManager.is_fastboot_available():
            return PreflightCheck(
                check_id="fastboot_available",
                name="Fastboot Tool",
                status=CheckStatus.PASS,
                severity=CheckSeverity.BLOCKING,
                message="Fastboot binary found and accessible.",
            )
        return PreflightCheck(
            check_id="fastboot_available",
            name="Fastboot Tool",
            status=CheckStatus.FAIL,
            severity=CheckSeverity.BLOCKING,
            message="Fastboot binary not found. Install platform-tools or check PATH.",
        )

    def _check_bootloader_state(self) -> PreflightCheck:
        """Check bootloader lock status."""
        bl = self._device.bootloader_unlocked
        if bl is True:
            return PreflightCheck(
                check_id="bootloader",
                name="Bootloader Status",
                status=CheckStatus.PASS,
                severity=CheckSeverity.BLOCKING,
                message="Bootloader is unlocked.",
            )
        if bl is False:
            return PreflightCheck(
                check_id="bootloader",
                name="Bootloader Status",
                status=CheckStatus.FAIL,
                severity=CheckSeverity.BLOCKING,
                message="Bootloader is LOCKED. Unlock before flashing custom images.",
                detail="Go to Flash page and use 'Unlock BL' to unlock the bootloader.",
            )
        return PreflightCheck(
            check_id="bootloader",
            name="Bootloader Status",
            status=CheckStatus.WARN,
            severity=CheckSeverity.WARNING,
            message="Bootloader status unknown — could not determine lock state.",
        )

    def _check_fastboot_mode(self) -> PreflightCheck:
        """Verify device is in fastboot mode (required for partition ops)."""
        dev = self._device
        if dev.is_fastboot_device:
            return PreflightCheck(
                check_id="fastboot_mode",
                name="Fastboot Mode",
                status=CheckStatus.PASS,
                severity=CheckSeverity.BLOCKING,
                message="Device is in fastboot mode.",
            )
        return PreflightCheck(
            check_id="fastboot_mode",
            name="Fastboot Mode",
            status=CheckStatus.FAIL,
            severity=CheckSeverity.BLOCKING,
            message="Device is NOT in fastboot mode. Reboot to bootloader first.",
            detail="Use 'adb reboot bootloader' or the reboot button on the Device page.",
        )

    def _check_source_exists(self, source_path: str) -> PreflightCheck:
        """Verify the ROM source directory or file exists."""
        path = Path(source_path)
        if path.exists():
            return PreflightCheck(
                check_id="source_exists",
                name="ROM Source",
                status=CheckStatus.PASS,
                severity=CheckSeverity.BLOCKING,
                message=f"Source exists: {path.name}",
            )
        return PreflightCheck(
            check_id="source_exists",
            name="ROM Source",
            status=CheckStatus.FAIL,
            severity=CheckSeverity.BLOCKING,
            message=f"Source not found: {source_path}",
        )

    def _check_hash(self, source_path: str, expected: str) -> PreflightCheck:
        """Verify SHA-256 hash of the source file matches expected."""
        path = Path(source_path)
        if not path.is_file():
            return PreflightCheck(
                check_id="hash_verify",
                name="Hash Verification",
                status=CheckStatus.SKIP,
                severity=CheckSeverity.INFO,
                message="Hash check skipped — source is a directory.",
            )
        try:
            sha = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    sha.update(chunk)
            computed = sha.hexdigest()
            if computed.lower() == expected.lower():
                return PreflightCheck(
                    check_id="hash_verify",
                    name="Hash Verification",
                    status=CheckStatus.PASS,
                    severity=CheckSeverity.BLOCKING,
                    message="SHA-256 hash matches expected value.",
                )
            return PreflightCheck(
                check_id="hash_verify",
                name="Hash Verification",
                status=CheckStatus.FAIL,
                severity=CheckSeverity.BLOCKING,
                message="SHA-256 hash MISMATCH — file may be corrupted or tampered.",
                detail=f"Expected: {expected[:16]}…  Got: {computed[:16]}…",
            )
        except OSError as exc:
            return PreflightCheck(
                check_id="hash_verify",
                name="Hash Verification",
                status=CheckStatus.FAIL,
                severity=CheckSeverity.BLOCKING,
                message=f"Could not read file for hashing: {exc}",
            )

    def _check_sufficient_host_storage(self) -> PreflightCheck:
        """Warn if host storage is low (< 2 GB free)."""
        import shutil

        try:
            usage = shutil.disk_usage("/")
            free_gb = usage.free / (1024**3)
            if free_gb < 2.0:
                return PreflightCheck(
                    check_id="host_storage",
                    name="Host Storage",
                    status=CheckStatus.WARN,
                    severity=CheckSeverity.WARNING,
                    message=f"Low disk space: {free_gb:.1f} GB free.",
                    detail="Ensure you have enough space for ROM images and backups.",
                )
            return PreflightCheck(
                check_id="host_storage",
                name="Host Storage",
                status=CheckStatus.PASS,
                severity=CheckSeverity.INFO,
                message=f"{free_gb:.1f} GB free on host.",
            )
        except OSError:
            return PreflightCheck(
                check_id="host_storage",
                name="Host Storage",
                status=CheckStatus.SKIP,
                severity=CheckSeverity.INFO,
                message="Could not check host disk space.",
            )
