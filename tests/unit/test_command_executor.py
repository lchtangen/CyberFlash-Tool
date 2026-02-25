"""Unit tests for CommandExecutor.

All ADB/Fastboot interactions are mocked — no device needed.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cyberflash.core.command_executor import (
    CommandExecutor,
    CommandLogEntry,
    CommandResult,
    CommandStatus,
    CommandType,
)
from cyberflash.core.preflight_checker import PreflightResult
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


# ── Enum tests ───────────────────────────────────────────────────────────────


class TestEnums:
    def test_command_type_values(self) -> None:
        assert CommandType.REBOOT == "reboot"
        assert CommandType.SHELL == "shell"
        assert CommandType.BACKUP == "backup"
        assert CommandType.FLASH == "flash"
        assert CommandType.PARTITION == "partition"
        assert CommandType.ROOT == "root"
        assert CommandType.DIAGNOSTICS == "diagnostics"
        assert CommandType.INFO == "info"

    def test_command_status_values(self) -> None:
        assert CommandStatus.PENDING == "pending"
        assert CommandStatus.RUNNING == "running"
        assert CommandStatus.COMPLETED == "completed"
        assert CommandStatus.FAILED == "failed"
        assert CommandStatus.BLOCKED == "blocked"
        assert CommandStatus.CANCELLED == "cancelled"


# ── CommandResult tests ──────────────────────────────────────────────────────


class TestCommandResult:
    def test_basic_result(self) -> None:
        r = CommandResult(
            command_id="test_1",
            command_type=CommandType.SHELL,
            status=CommandStatus.COMPLETED,
            message="Done",
        )
        assert r.command_id == "test_1"
        assert r.command_type == CommandType.SHELL
        assert r.status == CommandStatus.COMPLETED
        assert r.message == "Done"
        assert r.output == ""
        assert r.preflight is None

    def test_elapsed_zero_by_default(self) -> None:
        r = CommandResult(
            command_id="x",
            command_type=CommandType.INFO,
            status=CommandStatus.COMPLETED,
            message="OK",
        )
        assert r.elapsed == 0.0

    def test_elapsed_with_timestamps(self) -> None:
        r = CommandResult(
            command_id="x",
            command_type=CommandType.INFO,
            status=CommandStatus.COMPLETED,
            message="OK",
            started_at=100.0,
            finished_at=102.5,
        )
        assert r.elapsed == pytest.approx(2.5)
        assert "2.5s" in r.elapsed_str

    def test_elapsed_str_milliseconds(self) -> None:
        r = CommandResult(
            command_id="x",
            command_type=CommandType.INFO,
            status=CommandStatus.COMPLETED,
            message="OK",
            started_at=100.0,
            finished_at=100.5,
        )
        assert "ms" in r.elapsed_str

    def test_result_with_output(self) -> None:
        r = CommandResult(
            command_id="s1",
            command_type=CommandType.SHELL,
            status=CommandStatus.COMPLETED,
            message="OK",
            output="hello world",
        )
        assert r.output == "hello world"

    def test_result_with_preflight(self) -> None:
        pf = PreflightResult(checks=[], operation="flash")
        r = CommandResult(
            command_id="f1",
            command_type=CommandType.FLASH,
            status=CommandStatus.BLOCKED,
            message="Blocked by preflight",
            preflight=pf,
        )
        assert r.preflight is not None
        assert r.preflight.operation == "flash"


# ── CommandLogEntry tests ────────────────────────────────────────────────────


class TestCommandLogEntry:
    def test_log_entry_fields(self) -> None:
        entry = CommandLogEntry(
            timestamp=1234567890.0,
            command_id="cmd_1",
            command_type=CommandType.REBOOT,
            description="Reboot to bootloader",
            status=CommandStatus.RUNNING,
            device_serial="abc123",
        )
        assert entry.timestamp == 1234567890.0
        assert entry.command_id == "cmd_1"
        assert entry.command_type == CommandType.REBOOT
        assert entry.description == "Reboot to bootloader"
        assert entry.status == CommandStatus.RUNNING
        assert entry.device_serial == "abc123"

    def test_log_entry_default_serial(self) -> None:
        entry = CommandLogEntry(
            timestamp=0.0,
            command_id="x",
            command_type=CommandType.SHELL,
            description="Test",
            status=CommandStatus.COMPLETED,
        )
        assert entry.device_serial == ""


# ── CommandExecutor tests ────────────────────────────────────────────────────


class TestCommandExecutor:
    def test_init_with_device_info(self) -> None:
        dev = _make_device("serial_1")
        exe = CommandExecutor(dev)
        assert exe.device.serial == "serial_1"
        assert exe.audit_log == []

    @patch("cyberflash.core.command_executor.AdbManager")
    def test_reboot_system_success(self, mock_adb) -> None:
        mock_adb.reboot.return_value = True

        exe = CommandExecutor(_make_device())
        result = exe.reboot("")
        assert result.status == CommandStatus.COMPLETED
        assert result.command_type == CommandType.REBOOT
        assert len(exe.audit_log) == 1
        assert exe.audit_log[0].command_type == CommandType.REBOOT

    @patch("cyberflash.core.command_executor.AdbManager")
    def test_reboot_bootloader_success(self, mock_adb) -> None:
        mock_adb.reboot.return_value = True

        exe = CommandExecutor(_make_device())
        result = exe.reboot("bootloader")
        assert result.status == CommandStatus.COMPLETED
        assert "bootloader" in result.message.lower()

    @patch("cyberflash.core.command_executor.AdbManager")
    def test_reboot_failure(self, mock_adb) -> None:
        mock_adb.reboot.return_value = False

        exe = CommandExecutor(_make_device())
        result = exe.reboot("recovery")
        assert result.status == CommandStatus.FAILED

    @patch("cyberflash.core.command_executor.AdbManager")
    def test_reboot_exception(self, mock_adb) -> None:
        mock_adb.reboot.side_effect = RuntimeError("USB error")

        exe = CommandExecutor(_make_device())
        result = exe.reboot("")
        assert result.status == CommandStatus.FAILED
        assert "error" in result.message.lower()

    def test_reboot_non_adb_non_fastboot_device(self) -> None:
        dev = _make_device(state=DeviceState.DISCONNECTED)
        exe = CommandExecutor(dev)
        result = exe.reboot("")
        assert result.status == CommandStatus.FAILED

    @patch("cyberflash.core.command_executor.AdbManager")
    def test_run_shell_success(self, mock_adb) -> None:
        mock_adb.shell.return_value = "Linux abc123 5.15.0\n"

        exe = CommandExecutor(_make_device())
        result = exe.run_shell("uname -a")
        assert result.status == CommandStatus.COMPLETED
        assert "Linux" in result.output

    @patch("cyberflash.core.command_executor.AdbManager")
    def test_run_shell_failure(self, mock_adb) -> None:
        mock_adb.shell.side_effect = RuntimeError("device not found")

        exe = CommandExecutor(_make_device())
        result = exe.run_shell("uname -a")
        assert result.status == CommandStatus.FAILED

    @patch("cyberflash.core.command_executor.AdbManager")
    def test_get_device_info_success(self, mock_adb) -> None:
        mock_adb.get_props_batch.return_value = {
            "ro.product.model": "Pixel 7",
            "ro.product.brand": "Google",
        }

        exe = CommandExecutor(_make_device())
        result = exe.get_device_info()
        assert result.status == CommandStatus.COMPLETED
        assert "Pixel 7" in result.output
        assert result.command_type == CommandType.INFO

    @patch("cyberflash.core.command_executor.AdbManager")
    def test_get_device_info_failure(self, mock_adb) -> None:
        mock_adb.get_props_batch.side_effect = RuntimeError("no device")

        exe = CommandExecutor(_make_device())
        result = exe.get_device_info()
        assert result.status == CommandStatus.FAILED

    def test_audit_log_grows(self) -> None:
        exe = CommandExecutor(_make_device(state=DeviceState.DISCONNECTED))
        exe.reboot("")
        exe.reboot("recovery")
        assert len(exe.audit_log) == 2

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_run_preflight_generic(self, mock_tm) -> None:
        mock_tm.is_adb_available.return_value = True

        exe = CommandExecutor(_make_device())
        result = exe.run_preflight("generic")
        assert isinstance(result, PreflightResult)
        assert result.passed is True

    @patch("cyberflash.core.preflight_checker.ToolManager")
    def test_run_preflight_flash(self, mock_tm) -> None:
        mock_tm.is_adb_available.return_value = True
        mock_tm.is_fastboot_available.return_value = True

        exe = CommandExecutor(_make_device())
        result = exe.run_preflight("flash")
        assert isinstance(result, PreflightResult)

    @patch("cyberflash.core.command_executor.FastbootManager")
    def test_reboot_from_fastboot(self, mock_fb) -> None:
        mock_fb.reboot.return_value = True

        dev = _make_device(state=DeviceState.FASTBOOT)
        exe = CommandExecutor(dev)
        result = exe.reboot("bootloader")
        assert result.status == CommandStatus.COMPLETED
