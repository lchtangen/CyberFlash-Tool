"""tests/unit/test_perf_worker.py — Unit tests for PerfWorker & data models."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cyberflash.workers.perf_worker import (
    CpuCoreInfo,
    IoStats,
    PerfSnapshot,
    PerfWorker,
    RamInfo,
)

# ---------------------------------------------------------------------------
# CpuCoreInfo
# ---------------------------------------------------------------------------


class TestCpuCoreInfo:
    def test_utilisation_normal(self) -> None:
        core = CpuCoreInfo(core_id=0, cur_freq_khz=1000, max_freq_khz=2000)
        assert core.utilisation == pytest.approx(0.5)

    def test_utilisation_zero_max(self) -> None:
        core = CpuCoreInfo(core_id=0, cur_freq_khz=500, max_freq_khz=0)
        assert core.utilisation == 0.0

    def test_utilisation_clamps_to_one(self) -> None:
        # cur > max (possible during boost)
        core = CpuCoreInfo(core_id=0, cur_freq_khz=3000, max_freq_khz=2000)
        assert core.utilisation == 1.0

    def test_defaults(self) -> None:
        core = CpuCoreInfo(core_id=3)
        assert core.governor == "unknown"
        assert core.online is True


# ---------------------------------------------------------------------------
# RamInfo
# ---------------------------------------------------------------------------


class TestRamInfo:
    def test_used_kb(self) -> None:
        ram = RamInfo(total_kb=4_000_000, available_kb=1_000_000)
        assert ram.used_kb == 3_000_000

    def test_pressure(self) -> None:
        ram = RamInfo(total_kb=4_000_000, available_kb=1_000_000)
        assert ram.pressure == pytest.approx(0.75)

    def test_pressure_zero_total(self) -> None:
        assert RamInfo(total_kb=0).pressure == 0.0

    def test_used_kb_clamps(self) -> None:
        ram = RamInfo(total_kb=1000, available_kb=2000)
        assert ram.used_kb == 0


# ---------------------------------------------------------------------------
# IoStats
# ---------------------------------------------------------------------------


class TestIoStats:
    def test_defaults(self) -> None:
        io = IoStats()
        assert io.reads_completed == 0
        assert io.write_kb == 0


# ---------------------------------------------------------------------------
# PerfSnapshot
# ---------------------------------------------------------------------------


class TestPerfSnapshot:
    def test_to_dict_keys(self) -> None:
        snap = PerfSnapshot(serial="S001", cpu_temp_celsius=42.5)
        d = snap.to_dict()
        assert d["serial"] == "S001"
        assert d["cpu_temp"] == pytest.approx(42.5)
        assert "cores" in d
        assert "error" in d

    def test_to_dict_cores(self) -> None:
        core = CpuCoreInfo(core_id=0, cur_freq_khz=1200, max_freq_khz=2400)
        snap = PerfSnapshot(serial="X", cores=[core])
        d = snap.to_dict()
        assert len(d["cores"]) == 1
        assert d["cores"][0]["id"] == 0
        assert d["cores"][0]["util"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# snapshot_to_json helper
# ---------------------------------------------------------------------------


class TestSnapshotToJson:
    def test_returns_valid_json_string(self) -> None:
        import json

        snap = PerfSnapshot(serial="Z999", cpu_temp_celsius=38.0)
        result = PerfWorker.snapshot_to_json(snap)
        parsed = json.loads(result)
        assert parsed["serial"] == "Z999"


# ---------------------------------------------------------------------------
# PerfWorker — instantiation & helpers (no QThread.start)
# ---------------------------------------------------------------------------


class TestPerfWorker:
    def test_instantiation(self) -> None:
        worker = PerfWorker("SER001", interval_ms=1000)
        assert worker._serial == "SER001"
        assert worker._interval_ms == 1000

    def test_minimum_interval_enforced(self) -> None:
        worker = PerfWorker("SER002", interval_ms=100)
        assert worker._interval_ms >= 500

    @patch("cyberflash.core.adb_manager.AdbManager")
    def test_collect_returns_snapshot(self, mock_adb_cls: MagicMock) -> None:
        mock_adb_cls.shell.return_value = ""

        worker = PerfWorker("SER003", interval_ms=500)
        snap = worker._collect()
        assert isinstance(snap, PerfSnapshot)
        assert snap.serial == "SER003"

    @patch("cyberflash.core.adb_manager.AdbManager")
    def test_collect_cpu_freqs_empty_output(self, mock_adb_cls: MagicMock) -> None:
        mock_adb_cls.shell.return_value = ""
        worker = PerfWorker("S", interval_ms=500)
        cores = worker._collect_cpu_freqs()
        assert isinstance(cores, list)

    @patch("cyberflash.core.adb_manager.AdbManager")
    def test_collect_meminfo_partial(self, mock_adb_cls: MagicMock) -> None:
        mock_adb_cls.shell.return_value = (
            "MemTotal: 3800000 kB\nMemAvailable: 1200000 kB\n"
        )
        worker = PerfWorker("S", interval_ms=500)
        ram = worker._collect_meminfo()
        assert ram.total_kb == 3_800_000
        assert ram.available_kb == 1_200_000

    @patch("cyberflash.core.adb_manager.AdbManager")
    def test_collect_cpu_temp_valid(self, mock_adb_cls: MagicMock) -> None:
        mock_adb_cls.shell.return_value = "45000"  # millidegrees
        worker = PerfWorker("S", interval_ms=500)
        temp = worker._collect_cpu_temp()
        assert temp == pytest.approx(45.0)

    @patch("cyberflash.core.adb_manager.AdbManager")
    def test_collect_cpu_temp_invalid(self, mock_adb_cls: MagicMock) -> None:
        mock_adb_cls.shell.return_value = "not_a_number"
        worker = PerfWorker("S", interval_ms=500)
        temp = worker._collect_cpu_temp()
        assert temp == 0.0
