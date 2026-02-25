"""Unit tests for IntegrityChecker (Play Integrity / SafetyNet check)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cyberflash.workers.integrity_worker import (
    AttestationReport,
    IntegrityChecker,
    IntegrityResult,
    IntegrityTier,
    TierResult,
)

# ── AttestationReport ─────────────────────────────────────────────────────────

class TestAttestationReport:
    def test_overall_pass_all_pass(self) -> None:
        report = AttestationReport(
            serial="abc",
            timestamp="2026-01-01T00:00:00",
            tiers=[
                TierResult(IntegrityTier.BASIC,  IntegrityResult.PASS),
                TierResult(IntegrityTier.DEVICE, IntegrityResult.PASS),
                TierResult(IntegrityTier.STRONG, IntegrityResult.PASS),
            ],
        )
        assert report.overall_pass() is True

    def test_overall_pass_fails_if_any_fail(self) -> None:
        report = AttestationReport(
            serial="abc",
            timestamp="2026-01-01T00:00:00",
            tiers=[
                TierResult(IntegrityTier.BASIC,  IntegrityResult.PASS),
                TierResult(IntegrityTier.DEVICE, IntegrityResult.FAIL),
                TierResult(IntegrityTier.STRONG, IntegrityResult.PASS),
            ],
        )
        assert report.overall_pass() is False

    def test_to_dict_structure(self) -> None:
        report = AttestationReport(
            serial="s1",
            timestamp="2026-01-01T00:00:00",
            tiers=[TierResult(IntegrityTier.BASIC, IntegrityResult.PASS, "ok")],
        )
        d = report.to_dict()
        assert d["serial"] == "s1"
        assert d["timestamp"] == "2026-01-01T00:00:00"
        assert len(d["tiers"]) == 1
        assert d["tiers"][0]["tier"] == "BASIC"
        assert d["tiers"][0]["result"] == "pass"


# ── _check_basic ──────────────────────────────────────────────────────────────

class TestCheckBasic:
    def _shell_map(self, props: dict) -> callable:
        def shell(serial, cmd, **kw):
            for key, value in props.items():
                if key in cmd:
                    return value
            return ""
        return shell

    def test_green_state_passes(self) -> None:
        with patch("cyberflash.workers.integrity_worker.AdbManager.shell",
                   side_effect=self._shell_map({"verifiedbootstate": "green"})):
            result, _detail, _ = IntegrityChecker._check_basic("abc")
        assert result == IntegrityResult.PASS

    def test_yellow_state_passes(self) -> None:
        with patch("cyberflash.workers.integrity_worker.AdbManager.shell",
                   side_effect=self._shell_map({"verifiedbootstate": "yellow"})):
            result, _, _ = IntegrityChecker._check_basic("abc")
        assert result == IntegrityResult.PASS

    def test_orange_state_fails(self) -> None:
        with patch("cyberflash.workers.integrity_worker.AdbManager.shell",
                   side_effect=self._shell_map({"verifiedbootstate": "orange"})):
            result, _, _ = IntegrityChecker._check_basic("abc")
        assert result == IntegrityResult.FAIL

    def test_red_state_fails(self) -> None:
        with patch("cyberflash.workers.integrity_worker.AdbManager.shell",
                   side_effect=self._shell_map({"verifiedbootstate": "red"})):
            result, _, _ = IntegrityChecker._check_basic("abc")
        assert result == IntegrityResult.FAIL

    def test_unknown_state_returns_unknown(self) -> None:
        with patch("cyberflash.workers.integrity_worker.AdbManager.shell", return_value=""):
            result, _, _ = IntegrityChecker._check_basic("abc")
        assert result == IntegrityResult.UNKNOWN


# ── _check_device ─────────────────────────────────────────────────────────────

class TestCheckDevice:
    def test_release_keys_passes(self) -> None:
        def shell(serial, cmd, **kw):
            if "build.tags" in cmd:
                return "release-keys"
            return ""

        with patch("cyberflash.workers.integrity_worker.AdbManager.shell",
                   side_effect=shell):
            result, _, _ = IntegrityChecker._check_device("abc")
        assert result == IntegrityResult.PASS

    def test_dev_keys_fails(self) -> None:
        def shell(serial, cmd, **kw):
            if "build.tags" in cmd:
                return "dev-keys"
            return ""

        with patch("cyberflash.workers.integrity_worker.AdbManager.shell",
                   side_effect=shell):
            result, _, _ = IntegrityChecker._check_device("abc")
        assert result == IntegrityResult.FAIL

    def test_test_keys_fails(self) -> None:
        def shell(serial, cmd, **kw):
            if "build.tags" in cmd:
                return "test-keys"
            return ""

        with patch("cyberflash.workers.integrity_worker.AdbManager.shell",
                   side_effect=shell):
            result, _, _ = IntegrityChecker._check_device("abc")
        assert result == IntegrityResult.FAIL

    def test_unknown_tags_returns_unknown(self) -> None:
        with patch("cyberflash.workers.integrity_worker.AdbManager.shell", return_value=""):
            result, _, _ = IntegrityChecker._check_device("abc")
        assert result == IntegrityResult.UNKNOWN


# ── _check_strong ─────────────────────────────────────────────────────────────

class TestCheckStrong:
    def test_locked_bl_passes(self) -> None:
        def shell(serial, cmd, **kw):
            if "secureboot.lockstate" in cmd:
                return "locked"
            if "keystore" in cmd:
                return "trusty"
            return ""

        with patch("cyberflash.workers.integrity_worker.AdbManager.shell",
                   side_effect=shell):
            result, _, _ = IntegrityChecker._check_strong("abc")
        assert result == IntegrityResult.PASS

    def test_unlocked_bl_fails(self) -> None:
        def shell(serial, cmd, **kw):
            if "secureboot.lockstate" in cmd:
                return "unlocked"
            return ""

        with patch("cyberflash.workers.integrity_worker.AdbManager.shell",
                   side_effect=shell):
            result, _, _ = IntegrityChecker._check_strong("abc")
        assert result == IntegrityResult.FAIL

    def test_flash_locked_zero_fails(self) -> None:
        def shell(serial, cmd, **kw):
            if "flash.locked" in cmd:
                return "0"
            return ""

        with patch("cyberflash.workers.integrity_worker.AdbManager.shell",
                   side_effect=shell):
            result, _, _ = IntegrityChecker._check_strong("abc")
        assert result == IntegrityResult.FAIL


# ── run_check ─────────────────────────────────────────────────────────────────

class TestRunCheck:
    def test_full_check_returns_three_tiers(self) -> None:
        def shell(serial, cmd, **kw):
            if "verifiedbootstate" in cmd:
                return "green"
            if "build.tags" in cmd:
                return "release-keys"
            if "secureboot.lockstate" in cmd:
                return "locked"
            if "keystore" in cmd:
                return "trusty"
            return ""

        with patch("cyberflash.workers.integrity_worker.AdbManager.shell",
                   side_effect=shell):
            report = IntegrityChecker.run_check("abc123")

        assert report.serial == "abc123"
        assert len(report.tiers) == 3
        tiers_found = {t.tier for t in report.tiers}
        assert IntegrityTier.BASIC  in tiers_found
        assert IntegrityTier.DEVICE in tiers_found
        assert IntegrityTier.STRONG in tiers_found

    def test_suggestions_on_fail(self) -> None:
        with patch("cyberflash.workers.integrity_worker.AdbManager.shell",
                   return_value="orange"):
            report = IntegrityChecker.run_check("abc")
        # BASIC fail should trigger suggestions
        assert len(report.suggestions) > 0


# ── History ───────────────────────────────────────────────────────────────────

class TestIntegrityHistory:
    def test_save_and_load(self, tmp_path: Path) -> None:
        report = AttestationReport(
            serial="s1",
            timestamp="2026-01-01T00:00:00",
            tiers=[TierResult(IntegrityTier.BASIC, IntegrityResult.PASS)],
        )
        IntegrityChecker.save_history(report, tmp_path)

        records = IntegrityChecker.load_history(tmp_path)
        assert len(records) == 1
        assert records[0]["serial"] == "s1"

    def test_load_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        records = IntegrityChecker.load_history(tmp_path / "empty")
        assert records == []

    def test_max_history_trimmed(self, tmp_path: Path) -> None:
        for i in range(105):
            report = AttestationReport(
                serial=f"s{i}",
                timestamp="2026-01-01T00:00:00",
            )
            IntegrityChecker.save_history(report, tmp_path)

        records = IntegrityChecker.load_history(tmp_path)
        assert len(records) == 100

    def test_history_file_corrupt_returns_empty(self, tmp_path: Path) -> None:
        history_file = tmp_path / "integrity_history.json"
        history_file.write_text("not valid json {{{")
        records = IntegrityChecker.load_history(tmp_path)
        assert records == []
