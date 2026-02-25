"""Unit tests for HealthScorer — mocked ADB per category."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cyberflash.core.health_scorer import CategoryScore, HealthCategory, HealthReport, HealthScorer


def _mock_shell(outputs: dict[str, str]):
    """Return a mock for AdbManager.shell keyed on command substring."""
    def _shell(serial: str, command: str, **kwargs) -> str:  # noqa: ARG001
        for key, val in outputs.items():
            if key in command:
                return val
        return ""
    return _shell


class TestScoreBattery:
    def test_healthy_battery(self) -> None:
        output = "level: 85\ntemperature: 280\nvoltage: 4000\nstatus: 2\nhealth: 2\n"
        with patch("cyberflash.core.health_scorer.AdbManager.shell", return_value=output):
            score = HealthScorer.score_battery("ABC")
        assert score.category == HealthCategory.BATTERY
        assert score.score >= 70

    def test_low_battery_penalised(self) -> None:
        output = "level: 5\ntemperature: 250\nhealth: 2\n"
        with patch("cyberflash.core.health_scorer.AdbManager.shell", return_value=output):
            score = HealthScorer.score_battery("ABC")
        assert score.score < 60

    def test_high_temp_penalised(self) -> None:
        output = "level: 70\ntemperature: 480\nhealth: 3\n"
        with patch("cyberflash.core.health_scorer.AdbManager.shell", return_value=output):
            score = HealthScorer.score_battery("ABC")
        assert score.score < 65

    def test_dead_battery_penalised(self) -> None:
        output = "level: 50\ntemperature: 250\nhealth: 4\n"
        with patch("cyberflash.core.health_scorer.AdbManager.shell", return_value=output):
            score = HealthScorer.score_battery("ABC")
        assert score.score < 50

    def test_empty_output_returns_score(self) -> None:
        with patch("cyberflash.core.health_scorer.AdbManager.shell", return_value=""):
            score = HealthScorer.score_battery("ABC")
        assert isinstance(score.score, int)


class TestScoreStorage:
    def test_low_usage(self) -> None:
        output = "Filesystem       1K-blocks  Used Available Use% Mounted on\n/dev/block/dm-0   32G   8G   24G  25% /data\n"
        with patch("cyberflash.core.health_scorer.AdbManager.shell", return_value=output):
            score = HealthScorer.score_storage("ABC")
        assert score.score >= 85

    def test_critical_usage(self) -> None:
        output = "Filesystem       1K-blocks  Used Available Use% Mounted on\n/dev/block/dm-0   32G  31G    1G  97% /data\n"
        with patch("cyberflash.core.health_scorer.AdbManager.shell", return_value=output):
            score = HealthScorer.score_storage("ABC")
        assert score.score < 60

    def test_empty_output_returns_base(self) -> None:
        with patch("cyberflash.core.health_scorer.AdbManager.shell", return_value=""):
            score = HealthScorer.score_storage("ABC")
        assert score.score == 90


class TestScoreCpu:
    def test_performance_governor_good(self) -> None:
        with patch("cyberflash.core.health_scorer.AdbManager.shell",
                   side_effect=["processor : 0\nprocessor : 1\n", "performance"]):
            score = HealthScorer.score_cpu("ABC")
        assert score.score >= 85

    def test_powersave_governor_penalised(self) -> None:
        with patch("cyberflash.core.health_scorer.AdbManager.shell",
                   side_effect=["processor : 0\n", "powersave"]):
            score = HealthScorer.score_cpu("ABC")
        assert score.score <= 80


class TestScoreMemory:
    def test_healthy_memory(self) -> None:
        output = "MemTotal:    8000000 kB\nMemAvailable: 4000000 kB\n"
        with patch("cyberflash.core.health_scorer.AdbManager.shell", return_value=output):
            score = HealthScorer.score_memory("ABC")
        assert score.score >= 80

    def test_low_memory_penalised(self) -> None:
        output = "MemTotal:    4000000 kB\nMemAvailable:  200000 kB\n"
        with patch("cyberflash.core.health_scorer.AdbManager.shell", return_value=output):
            score = HealthScorer.score_memory("ABC")
        assert score.score < 70


class TestScoreRoot:
    def test_not_rooted_scores_100(self) -> None:
        from cyberflash.core.root_manager import RootState
        with patch("cyberflash.core.health_scorer.RootManager.detect_root_state",
                   return_value=RootState.NOT_ROOTED):
            score = HealthScorer.score_root("ABC")
        assert score.score == 100

    def test_rooted_scores_lower(self) -> None:
        from cyberflash.core.root_manager import RootState
        with patch("cyberflash.core.health_scorer.RootManager.detect_root_state",
                   return_value=RootState.ROOTED_MAGISK):
            score = HealthScorer.score_root("ABC")
        assert score.score < 100


class TestScoreBoot:
    def test_zero_errors(self) -> None:
        with patch("cyberflash.core.health_scorer.AdbManager.shell", return_value="0"):
            score = HealthScorer.score_boot("ABC")
        assert score.score == 90

    def test_many_errors_penalised(self) -> None:
        with patch("cyberflash.core.health_scorer.AdbManager.shell", return_value="150"):
            score = HealthScorer.score_boot("ABC")
        assert score.score <= 65


class TestCompute:
    def test_returns_health_report(self) -> None:
        with (
            patch("cyberflash.core.health_scorer.AdbManager.shell", return_value=""),
            patch("cyberflash.core.health_scorer.RootManager.detect_root_state") as mock_root,
        ):
            from cyberflash.core.root_manager import RootState
            mock_root.return_value = RootState.NOT_ROOTED
            report = HealthScorer.compute("ABC")
        assert isinstance(report, HealthReport)
        assert isinstance(report.overall, int)
        assert 0 <= report.overall <= 100
        assert len(report.categories) == 6
