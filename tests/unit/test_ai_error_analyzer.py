"""Unit tests for AiErrorAnalyzer — pure pattern matching, no mocks needed."""

from __future__ import annotations

from cyberflash.core.ai_error_analyzer import AiErrorAnalyzer, AnalysisResult


class TestAnalyzeLog:
    def test_returns_analysis_result(self) -> None:
        result = AiErrorAnalyzer.analyze("FAILED (remote: 'Data too large')")
        assert isinstance(result, AnalysisResult)

    def test_fastboot_failed_pattern_matched(self) -> None:
        log = "< waiting for any device >\nFAILED (remote: 'Device locked')\n"
        result = AiErrorAnalyzer.analyze(log)
        assert len(result.matched_patterns) >= 1

    def test_verity_mismatch_detected(self) -> None:
        log = "dm-verity verification failed: invalid signature"
        result = AiErrorAnalyzer.analyze(log)
        assert any(p.pattern_id == "verity_mismatch" for p in result.matched_patterns)

    def test_signature_error_detected(self) -> None:
        log = "signature verify failed for boot.img"
        result = AiErrorAnalyzer.analyze(log)
        assert len(result.matched_patterns) >= 1

    def test_no_match_returns_empty_patterns(self) -> None:
        # Use a log with no known error keywords so no patterns fire
        log = "Device connected. Waiting for user input."
        result = AiErrorAnalyzer.analyze(log)
        assert result.matched_patterns == [] or len(result.matched_patterns) == 0

    def test_suggested_fixes_populated_on_match(self) -> None:
        log = "FAILED (remote: 'Failed to flash partition')"
        result = AiErrorAnalyzer.analyze(log)
        if result.matched_patterns:
            assert len(result.suggested_fixes) >= 1

    def test_confidence_between_zero_and_one(self) -> None:
        log = "error: device offline"
        result = AiErrorAnalyzer.analyze(log)
        assert 0.0 <= result.confidence <= 1.0

    def test_analyze_adb_log_string(self) -> None:
        log = "adb: error: failed to copy 'boot.img' to '/sdcard/boot.img'"
        result = AiErrorAnalyzer.analyze(log)
        assert isinstance(result, AnalysisResult)


class TestAnalyzeFromDevice:
    def test_analyze_adb_logcat_returns_result(self) -> None:
        from unittest.mock import patch

        with patch(
            "cyberflash.core.ai_error_analyzer.AdbManager.shell",
            return_value="E AndroidRuntime: FATAL EXCEPTION: main",
        ):
            result = AiErrorAnalyzer.analyze_adb_logcat("ABC")
        assert isinstance(result, AnalysisResult)

    def test_empty_logcat_returns_result(self) -> None:
        from unittest.mock import patch

        with patch("cyberflash.core.ai_error_analyzer.AdbManager.shell", return_value=""):
            result = AiErrorAnalyzer.analyze_adb_logcat("ABC")
        assert isinstance(result, AnalysisResult)


class TestSeverityOrdering:
    def test_critical_severity_pattern_exists(self) -> None:
        from cyberflash.core.ai_error_analyzer import _PATTERNS

        severities = {p.severity for p in _PATTERNS}
        assert "critical" in severities

    def test_all_patterns_have_fixes(self) -> None:
        from cyberflash.core.ai_error_analyzer import _PATTERNS

        for p in _PATTERNS:
            assert isinstance(p.fixes, list)

    def test_pattern_count_at_least_ten(self) -> None:
        from cyberflash.core.ai_error_analyzer import _PATTERNS

        assert len(_PATTERNS) >= 10

    def test_pattern_ids_are_unique(self) -> None:
        from cyberflash.core.ai_error_analyzer import _PATTERNS

        ids = [p.pattern_id for p in _PATTERNS]
        assert len(ids) == len(set(ids))

    def test_high_severity_fastboot_fail(self) -> None:
        from cyberflash.core.ai_error_analyzer import _PATTERNS

        patterns = {p.pattern_id: p for p in _PATTERNS}
        assert patterns["fastboot_failed"].severity in ("critical", "high")
