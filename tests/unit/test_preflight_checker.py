"""Unit tests for PreflightChecker.

All external tool interactions are mocked — no device needed.
"""

from __future__ import annotations

from unittest.mock import patch

from cyberflash.core.preflight_checker import (
    CheckSeverity,
    CheckStatus,
    PreflightCheck,
    PreflightChecker,
    PreflightResult,
)
from cyberflash.models.device import DeviceInfo, DeviceState

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_device(
    serial: str = "abc123",
    state: DeviceState = DeviceState.ONLINE,
    battery: int = 80,
    bootloader_unlocked: bool | None = True,
) -> DeviceInfo:
    return DeviceInfo(
        serial=serial,
        state=state,
        battery_level=battery,
        bootloader_unlocked=bootloader_unlocked,
    )


# ── PreflightResult dataclass tests ─────────────────────────────────────────


class TestPreflightResult:
    def test_passed_with_all_pass(self) -> None:
        checks = [
            PreflightCheck("c1", "Check 1", CheckStatus.PASS, CheckSeverity.BLOCKING, "OK"),
            PreflightCheck("c2", "Check 2", CheckStatus.PASS, CheckSeverity.WARNING, "OK"),
        ]
        result = PreflightResult(checks=checks)
        assert result.passed is True
        assert result.blocking_failures == []

    def test_not_passed_with_blocking_fail(self) -> None:
        checks = [
            PreflightCheck("c1", "Check 1", CheckStatus.FAIL, CheckSeverity.BLOCKING, "Bad"),
            PreflightCheck("c2", "Check 2", CheckStatus.PASS, CheckSeverity.WARNING, "OK"),
        ]
        result = PreflightResult(checks=checks)
        assert result.passed is False
        assert len(result.blocking_failures) == 1
        assert result.blocking_failures[0].check_id == "c1"

    def test_warning_does_not_block(self) -> None:
        checks = [
            PreflightCheck("c1", "Check 1", CheckStatus.WARN, CheckSeverity.WARNING, "Hmm"),
        ]
        result = PreflightResult(checks=checks)
        assert result.passed is True
        assert result.has_warnings is True

    def test_passed_with_skips(self) -> None:
        checks = [
            PreflightCheck("c1", "Check 1", CheckStatus.PASS, CheckSeverity.BLOCKING, "OK"),
            PreflightCheck("c2", "Check 2", CheckStatus.SKIP, CheckSeverity.INFO, "Skipped"),
        ]
        result = PreflightResult(checks=checks)
        assert result.passed is True

    def test_summary_all_pass(self) -> None:
        checks = [
            PreflightCheck("c1", "Check 1", CheckStatus.PASS, CheckSeverity.BLOCKING, "OK"),
            PreflightCheck("c2", "Check 2", CheckStatus.PASS, CheckSeverity.WARNING, "OK"),
        ]
        result = PreflightResult(checks=checks)
        assert "passed" in result.summary.lower()

    def test_summary_with_failures(self) -> None:
        checks = [
            PreflightCheck("c1", "Check 1", CheckStatus.PASS, CheckSeverity.BLOCKING, "OK"),
            PreflightCheck("c2", "Check 2", CheckStatus.FAIL, CheckSeverity.BLOCKING, "Bad"),
        ]
        result = PreflightResult(checks=checks)
        assert "BLOCKED" in result.summary

    def test_summary_with_warnings(self) -> None:
        checks = [
            PreflightCheck("c1", "Check 1", CheckStatus.PASS, CheckSeverity.BLOCKING, "OK"),
            PreflightCheck("c2", "Check 2", CheckStatus.WARN, CheckSeverity.WARNING, "Hmm"),
        ]
        result = PreflightResult(checks=checks)
        assert "warning" in result.summary.lower()

    def test_empty_checks(self) -> None:
        result = PreflightResult(checks=[])
        assert result.passed is True
        assert result.blocking_failures == []
        assert result.pass_count == 0
        assert result.total_count == 0

    def test_pass_count(self) -> None:
        checks = [
            PreflightCheck("c1", "A", CheckStatus.PASS, CheckSeverity.BLOCKING, "OK"),
            PreflightCheck("c2", "B", CheckStatus.FAIL, CheckSeverity.BLOCKING, "Bad"),
            PreflightCheck("c3", "C", CheckStatus.WARN, CheckSeverity.WARNING, "Hmm"),
        ]
        result = PreflightResult(checks=checks)
        assert result.pass_count == 1
        assert result.total_count == 3


# ── Enum tests ───────────────────────────────────────────────────────────────


class TestEnums:
    def test_check_status_enum_values(self) -> None:
        assert CheckStatus.PASS == "pass"
        assert CheckStatus.WARN == "warn"
        assert CheckStatus.FAIL == "fail"
        assert CheckStatus.SKIP == "skip"

    def test_check_severity_enum_values(self) -> None:
        assert CheckSeverity.BLOCKING == "blocking"
        assert CheckSeverity.WARNING == "warning"
        assert CheckSeverity.INFO == "info"


# ── PreflightChecker tests ───────────────────────────────────────────────────


class TestPreflightChecker:
    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_check_generic_connected_device(self, mock_tm) -> None:
        mock_tm.is_adb_available.return_value = True

        checker = PreflightChecker(_make_device("abc123"))
        result = checker.check_generic()
        assert isinstance(result, PreflightResult)
        check_ids = [c.check_id for c in result.checks]
        assert "device_connected" in check_ids
        assert "adb_available" in check_ids

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_check_generic_disconnected(self, mock_tm) -> None:
        mock_tm.is_adb_available.return_value = True

        checker = PreflightChecker(_make_device(state=DeviceState.DISCONNECTED))
        result = checker.check_generic()
        assert result.passed is False
        conn_check = next(c for c in result.checks if c.check_id == "device_connected")
        assert conn_check.status == CheckStatus.FAIL

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_check_generic_unauthorized(self, mock_tm) -> None:
        mock_tm.is_adb_available.return_value = True

        checker = PreflightChecker(_make_device(state=DeviceState.UNAUTHORIZED))
        result = checker.check_generic()
        assert result.passed is False
        auth_check = next(c for c in result.checks if c.check_id == "device_authorized")
        assert auth_check.status == CheckStatus.FAIL

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_check_flash_includes_source_check(self, mock_tm, tmp_path) -> None:
        mock_tm.is_adb_available.return_value = True
        mock_tm.is_fastboot_available.return_value = True

        source_dir = tmp_path / "rom"
        source_dir.mkdir()
        (source_dir / "boot.img").write_bytes(b"fake")

        checker = PreflightChecker(_make_device())
        result = checker.check_flash(str(source_dir))
        check_ids = [c.check_id for c in result.checks]
        assert "source_exists" in check_ids
        src_check = next(c for c in result.checks if c.check_id == "source_exists")
        assert src_check.status == CheckStatus.PASS

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_check_flash_missing_source(self, mock_tm) -> None:
        mock_tm.is_adb_available.return_value = True
        mock_tm.is_fastboot_available.return_value = True

        checker = PreflightChecker(_make_device())
        result = checker.check_flash("/nonexistent/path")
        src_check = next(c for c in result.checks if c.check_id == "source_exists")
        assert src_check.status == CheckStatus.FAIL

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_check_flash_low_battery_fails(self, mock_tm) -> None:
        mock_tm.is_adb_available.return_value = True
        mock_tm.is_fastboot_available.return_value = True

        checker = PreflightChecker(_make_device(battery=10))
        result = checker.check_flash("/some/path")
        bat_check = next(c for c in result.checks if c.check_id == "battery")
        assert bat_check.status == CheckStatus.FAIL

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_check_flash_locked_bootloader_fails(self, mock_tm) -> None:
        mock_tm.is_adb_available.return_value = True
        mock_tm.is_fastboot_available.return_value = True

        checker = PreflightChecker(_make_device(bootloader_unlocked=False))
        result = checker.check_flash()
        bl_check = next(c for c in result.checks if c.check_id == "bootloader")
        assert bl_check.status == CheckStatus.FAIL

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_check_flash_unknown_bootloader_warns(self, mock_tm) -> None:
        mock_tm.is_adb_available.return_value = True
        mock_tm.is_fastboot_available.return_value = True

        checker = PreflightChecker(_make_device(bootloader_unlocked=None))
        result = checker.check_flash()
        bl_check = next(c for c in result.checks if c.check_id == "bootloader")
        assert bl_check.status == CheckStatus.WARN

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_check_partition_requires_fastboot_mode(self, mock_tm) -> None:
        mock_tm.is_fastboot_available.return_value = True

        # Not in fastboot mode → should fail fastboot_mode check
        checker = PreflightChecker(_make_device(state=DeviceState.ONLINE))
        result = checker.check_partition()
        fb_check = next(c for c in result.checks if c.check_id == "fastboot_mode")
        assert fb_check.status == CheckStatus.FAIL

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_check_partition_in_fastboot(self, mock_tm) -> None:
        mock_tm.is_fastboot_available.return_value = True

        checker = PreflightChecker(_make_device(state=DeviceState.FASTBOOT, battery=50))
        result = checker.check_partition()
        fb_check = next(c for c in result.checks if c.check_id == "fastboot_mode")
        assert fb_check.status == CheckStatus.PASS

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_check_backup_happy_path(self, mock_tm) -> None:
        mock_tm.is_adb_available.return_value = True

        checker = PreflightChecker(_make_device())
        result = checker.check_backup()
        assert result.passed is True
        check_ids = [c.check_id for c in result.checks]
        assert "device_connected" in check_ids
        assert "battery" in check_ids
        assert "adb_available" in check_ids

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_check_root_happy_path(self, mock_tm) -> None:
        mock_tm.is_adb_available.return_value = True
        mock_tm.is_fastboot_available.return_value = True

        checker = PreflightChecker(_make_device())
        result = checker.check_root()
        assert result.passed is True
        check_ids = [c.check_id for c in result.checks]
        assert "bootloader" in check_ids

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_adb_unavailable_fails(self, mock_tm) -> None:
        mock_tm.is_adb_available.return_value = False

        checker = PreflightChecker(_make_device())
        result = checker.check_generic()
        adb_check = next(c for c in result.checks if c.check_id == "adb_available")
        assert adb_check.status == CheckStatus.FAIL
        assert result.passed is False
