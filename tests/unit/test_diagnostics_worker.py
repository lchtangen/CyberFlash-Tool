"""Unit tests for DiagnosticsWorker.

AdbManager.shell is mocked so no real device is needed.
"""

from __future__ import annotations

from unittest.mock import patch

from cyberflash.workers.diagnostics_worker import DiagnosticsWorker, _clean_value

# ── _clean_value helper ──────────────────────────────────────────────────────


class TestCleanValue:
    def test_empty_returns_na(self) -> None:
        assert _clean_value("anything", "") == "N/A"

    def test_strips_colon_prefix(self) -> None:
        assert _clean_value("Battery Level", "  level: 85") == "85"

    def test_temperature_divided_by_ten(self) -> None:
        result = _clean_value("Battery Temperature (°C)", "  temperature: 310")
        assert result == "31.0"

    def test_plain_value_returned_as_is(self) -> None:
        assert _clean_value("Model", "Pixel 7") == "Pixel 7"

    def test_df_usage_returns_last_line(self) -> None:
        raw = "Filesystem  Size  Used\n/data       50G   10G"
        result = _clean_value("/data usage", raw)
        assert "/data" in result or "10G" in result


# ── DiagnosticsWorker signal tests ───────────────────────────────────────────


class TestDiagnosticsWorker:
    def test_emits_result_ready_for_each_command(self, qapp) -> None:
        """Worker should emit result_ready for every entry in _DIAG_COMMANDS."""
        from cyberflash.workers.diagnostics_worker import _DIAG_COMMANDS

        collected: list[tuple[str, str, str]] = []

        with patch(
            "cyberflash.workers.diagnostics_worker.AdbManager.shell",
            return_value="test_value",
        ):
            worker = DiagnosticsWorker("fake_serial")
            worker.result_ready.connect(
                lambda cat, key, val: collected.append((cat, key, val))
            )
            worker.start()

        assert len(collected) == len(_DIAG_COMMANDS)

    def test_emits_diagnostics_complete(self, qapp) -> None:
        completed = []

        with patch(
            "cyberflash.workers.diagnostics_worker.AdbManager.shell",
            return_value="ok",
        ):
            worker = DiagnosticsWorker("fake_serial")
            worker.diagnostics_complete.connect(lambda: completed.append(True))
            worker.start()

        assert completed == [True]

    def test_emits_finished(self, qapp) -> None:
        finished = []

        with patch(
            "cyberflash.workers.diagnostics_worker.AdbManager.shell",
            return_value="ok",
        ):
            worker = DiagnosticsWorker("fake_serial")
            worker.finished.connect(lambda: finished.append(True))
            worker.start()

        assert finished == [True]

    def test_handles_adb_exception_gracefully(self, qapp) -> None:
        """Worker should not raise if AdbManager.shell raises."""
        from cyberflash.workers.diagnostics_worker import _DIAG_COMMANDS

        collected: list[tuple] = []

        with patch(
            "cyberflash.workers.diagnostics_worker.AdbManager.shell",
            side_effect=RuntimeError("connection refused"),
        ):
            worker = DiagnosticsWorker("fake_serial")
            worker.result_ready.connect(
                lambda cat, key, val: collected.append((cat, key, val))
            )
            worker.start()

        # All commands should still emit, with "error" as value
        assert len(collected) == len(_DIAG_COMMANDS)
        for _, _, val in collected:
            assert val == "error"

    def test_log_lines_emitted(self, qapp) -> None:
        lines: list[str] = []

        with patch(
            "cyberflash.workers.diagnostics_worker.AdbManager.shell",
            return_value="v",
        ):
            worker = DiagnosticsWorker("fake_serial")
            worker.log_line.connect(lines.append)
            worker.start()

        # Should have at least one log line per command plus header/footer
        assert len(lines) >= 2

    def test_categories_match_expected(self, qapp) -> None:
        seen_categories: set[str] = set()
        expected = {"Device Info", "Battery", "Storage", "Memory", "CPU", "Security"}

        with patch(
            "cyberflash.workers.diagnostics_worker.AdbManager.shell",
            return_value="x",
        ):
            worker = DiagnosticsWorker("fake_serial")
            worker.result_ready.connect(
                lambda cat, key, val: seen_categories.add(cat)
            )
            worker.start()

        assert expected == seen_categories
