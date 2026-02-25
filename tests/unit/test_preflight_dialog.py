"""Unit tests for PreflightDialog widget."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from cyberflash.ui.dialogs.preflight_dialog import PreflightDialog

# ── Mock types matching preflight_checker interface ──────────────────────────


class _MockStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class _MockSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"


@dataclass
class _MockCheck:
    check_id: str
    name: str
    status: _MockStatus
    severity: _MockSeverity
    message: str


@dataclass
class _MockResult:
    checks: list[_MockCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.status in (_MockStatus.PASS, _MockStatus.SKIP) for c in self.checks)

    @property
    def blocking_failures(self) -> int:
        return sum(
            1
            for c in self.checks
            if c.status == _MockStatus.FAIL and c.severity == _MockSeverity.BLOCKING
        )

    @property
    def summary(self) -> str:
        p = sum(1 for c in self.checks if c.status == _MockStatus.PASS)
        f = sum(1 for c in self.checks if c.status == _MockStatus.FAIL)
        return f"{p} passed, {f} failed"


# ── Tests ────────────────────────────────────────────────────────────────────


class TestPreflightDialog:
    def _all_pass_result(self) -> _MockResult:
        return _MockResult(
            checks=[
                _MockCheck("c1", "ADB Available", _MockStatus.PASS, _MockSeverity.BLOCKING, "OK"),
                _MockCheck("c2", "Battery", _MockStatus.PASS, _MockSeverity.WARNING, "90%"),
            ]
        )

    def _mixed_result(self) -> _MockResult:
        return _MockResult(
            checks=[
                _MockCheck("c1", "ADB Available", _MockStatus.PASS, _MockSeverity.BLOCKING, "OK"),
                _MockCheck("c2", "Battery", _MockStatus.WARN, _MockSeverity.WARNING, "Low 15%"),
                _MockCheck("c3", "Source", _MockStatus.FAIL, _MockSeverity.BLOCKING, "Not found"),
            ]
        )

    def test_dialog_creates_with_passing_result(self, qapp) -> None:
        result = self._all_pass_result()
        dlg = PreflightDialog(result)
        assert dlg is not None
        assert dlg.windowTitle() == "Pre-flight Check Results"

    def test_dialog_creates_with_failing_result(self, qapp) -> None:
        result = self._mixed_result()
        dlg = PreflightDialog(result)
        assert dlg is not None

    def test_dialog_minimum_size(self, qapp) -> None:
        result = self._all_pass_result()
        dlg = PreflightDialog(result)
        assert dlg.minimumWidth() >= 480
        assert dlg.minimumHeight() >= 400

    def test_dialog_with_empty_checks(self, qapp) -> None:
        result = _MockResult(checks=[])
        dlg = PreflightDialog(result)
        assert dlg is not None

    def test_dialog_with_all_fail(self, qapp) -> None:
        result = _MockResult(
            checks=[
                _MockCheck("c1", "Check 1", _MockStatus.FAIL, _MockSeverity.BLOCKING, "Bad"),
                _MockCheck("c2", "Check 2", _MockStatus.FAIL, _MockSeverity.BLOCKING, "Worse"),
            ]
        )
        dlg = PreflightDialog(result)
        assert dlg is not None

    def test_dialog_with_skips(self, qapp) -> None:
        result = _MockResult(
            checks=[
                _MockCheck("c1", "Check 1", _MockStatus.PASS, _MockSeverity.INFO, "OK"),
                _MockCheck("c2", "Skipped", _MockStatus.SKIP, _MockSeverity.INFO, "N/A"),
            ]
        )
        dlg = PreflightDialog(result)
        assert dlg is not None
