"""tests/unit/test_storage_analyzer.py — Unit tests for StorageAnalyzer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cyberflash.core.storage_analyzer import (
    FilesystemInfo,
    StorageAnalyzer,
    StorageReport,
    TrimStatus,
)

# ---------------------------------------------------------------------------
# FilesystemInfo
# ---------------------------------------------------------------------------


class TestFilesystemInfo:
    def test_free_ratio_normal(self) -> None:
        fs = FilesystemInfo(
            mount_point="/data",
            fs_type="f2fs",
            total_kb=10_000,
            available_kb=4_000,
        )
        assert fs.free_ratio == pytest.approx(0.4)

    def test_free_ratio_zero_total(self) -> None:
        fs = FilesystemInfo(total_kb=0, available_kb=100)
        assert fs.free_ratio == 0.0

    def test_free_ratio_clamps(self) -> None:
        # available > total shouldn't go negative
        fs = FilesystemInfo(total_kb=1000, available_kb=2000)
        assert fs.free_ratio >= 0.0


# ---------------------------------------------------------------------------
# TrimStatus
# ---------------------------------------------------------------------------


class TestTrimStatus:
    def test_defaults(self) -> None:
        ts = TrimStatus()
        assert ts.supported is False
        assert ts.untrimmed_kb == 0


# ---------------------------------------------------------------------------
# StorageReport
# ---------------------------------------------------------------------------


class TestStorageReport:
    def _make_report(self) -> StorageReport:
        fs1 = FilesystemInfo(
            mount_point="/system",
            fs_type="ext4",
            total_kb=2_000_000,
            used_kb=800_000,
            available_kb=1_200_000,
            use_percent=40,
        )
        fs2 = FilesystemInfo(
            mount_point="/data",
            fs_type="f2fs",
            total_kb=50_000_000,
            used_kb=30_000_000,
            available_kb=20_000_000,
            use_percent=60,
        )
        return StorageReport(
            serial="TESTABC",
            filesystems=[fs1, fs2],
            trim=TrimStatus(supported=True, untrimmed_kb=512),
            emmc_life_estimate="normal",
            bad_block_count=0,
        )

    def test_summary_contains_serial(self) -> None:
        report = self._make_report()
        assert "TESTABC" in report.summary()

    def test_summary_contains_filesystems(self) -> None:
        report = self._make_report()
        s = report.summary()
        assert "/system" in s
        assert "/data" in s

    def test_summary_trim_info(self) -> None:
        report = self._make_report()
        assert "TRIM" in report.summary()

    def test_health_ok_true(self) -> None:
        report = self._make_report()
        assert report.health_ok is True

    def test_health_ok_false_on_errors(self) -> None:
        report = self._make_report()
        report.errors.append("something went wrong")
        assert report.health_ok is False


# ---------------------------------------------------------------------------
# StorageAnalyzer.analyze — dry_run
# ---------------------------------------------------------------------------


class TestStorageAnalyzerDryRun:
    def test_analyze_dry_run_returns_report(self) -> None:
        logs: list[str] = []
        result = StorageAnalyzer.analyze("SER001", log_cb=logs.append, dry_run=True)
        assert isinstance(result, StorageReport)
        assert result.serial == "SER001"
        assert any("dry" in m.lower() for m in logs)

    def test_run_fstrim_dry_run_returns_true(self) -> None:
        logs: list[str] = []
        ok = StorageAnalyzer.run_fstrim(
            "SER001", "/data", log_cb=logs.append, dry_run=True
        )
        assert ok is True
        assert any("dry" in m.lower() or "fstrim" in m.lower() for m in logs)


# ---------------------------------------------------------------------------
# StorageAnalyzer.analyze — live (mocked ADB)
# ---------------------------------------------------------------------------


class TestStorageAnalyzerLive:
    DF_OUTPUT = (
        "Filesystem       1K-blocks  Used Available Use% Mounted on\n"
        "/dev/block/dm-0    2000000  800000   1200000  40% /system\n"
        "/dev/block/sda20  50000000 30000000 20000000  60% /data\n"
    )
    MOUNTS_OUTPUT = (
        "/dev/block/dm-0 /system ext4 ro,seclabel 0 0\n"
        "/dev/block/sda20 /data f2fs rw,seclabel 0 0\n"
    )

    @patch("cyberflash.core.adb_manager.AdbManager")
    def test_analyze_parses_df(self, mock_adb_cls: MagicMock) -> None:
        def shell_side_effect(serial: str, cmd: str) -> str:
            if "df" in cmd:
                return self.DF_OUTPUT
            if "/proc/mounts" in cmd:
                return self.MOUNTS_OUTPUT
            return ""

        mock_adb_cls.shell.side_effect = shell_side_effect

        report = StorageAnalyzer.analyze("SERIAL", dry_run=False)
        assert report is not False
        assert isinstance(report, StorageReport)
        assert len(report.filesystems) >= 1

    @patch("cyberflash.core.adb_manager.AdbManager")
    def test_run_fstrim_success(self, mock_adb_cls: MagicMock) -> None:
        mock_adb_cls.shell.return_value = "/data: 12288 bytes trimmed"

        ok = StorageAnalyzer.run_fstrim("SERIAL", "/data", dry_run=False)
        assert ok is True
