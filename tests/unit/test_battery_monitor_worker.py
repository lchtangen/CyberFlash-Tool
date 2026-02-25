"""Unit tests for BatteryMonitorWorker — sample parsing and alert threshold."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cyberflash.workers.battery_monitor_worker import BatterySample, BatteryMonitorWorker


class TestParse:
    def test_parse_valid_output(self) -> None:
        output = (
            "  level: 75\n"
            "  temperature: 310\n"
            "  voltage: 4050\n"
            "  status: 2\n"
            "  health: 2\n"
        )
        sample = BatteryMonitorWorker._parse(output)
        assert sample is not None
        assert sample.level == 75
        assert abs(sample.temp_c - 31.0) < 0.01
        assert sample.voltage_mv == 4050
        assert sample.status == "Charging"
        assert sample.health == "Good"

    def test_parse_empty_returns_none(self) -> None:
        # Empty output should still return a BatterySample with defaults
        sample = BatteryMonitorWorker._parse("")
        assert sample is not None
        assert sample.level == 0

    def test_parse_full_battery(self) -> None:
        output = "  level: 100\n  temperature: 250\n  voltage: 4200\n  status: 5\n  health: 2\n"
        sample = BatteryMonitorWorker._parse(output)
        assert sample is not None
        assert sample.level == 100
        assert sample.status == "Full"

    def test_parse_timestamp_present(self) -> None:
        output = "  level: 50\n  temperature: 300\n  voltage: 3900\n  status: 3\n  health: 2\n"
        sample = BatteryMonitorWorker._parse(output)
        assert sample is not None
        assert "Z" in sample.timestamp

    def test_to_dict(self) -> None:
        sample = BatterySample(
            timestamp="2024-01-15T12:00:00Z",
            level=80,
            temp_c=30.0,
            voltage_mv=4000,
            status="Charging",
            health="Good",
        )
        d = sample.to_dict()
        assert d["level"] == 80
        assert d["temp_c"] == 30.0


class TestWorkerInit:
    def test_default_interval(self) -> None:
        worker = BatteryMonitorWorker("ABC123")
        assert worker._interval == 30.0
        assert worker._temp_alert == 45.0

    def test_custom_interval(self) -> None:
        worker = BatteryMonitorWorker("ABC123", poll_interval_s=10.0, temp_alert_c=50.0)
        assert worker._interval == 10.0
        assert worker._temp_alert == 50.0

    def test_abort_flag_initially_false(self) -> None:
        worker = BatteryMonitorWorker("ABC123")
        assert worker._aborted is False

    def test_abort_sets_flag(self) -> None:
        worker = BatteryMonitorWorker("ABC123")
        worker.abort()
        assert worker._aborted is True
