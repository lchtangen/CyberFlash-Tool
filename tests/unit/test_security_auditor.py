"""Unit tests for SecurityAuditor — each check mocked."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cyberflash.core.security_auditor import AuditFinding, AuditReport, Finding, SecurityAuditor


class TestCheckSelinux:
    def test_enforcing_is_info(self) -> None:
        with patch("cyberflash.core.security_auditor.AdbManager.shell",
                   return_value="Enforcing"):
            finding = SecurityAuditor.check_selinux("ABC")
        assert finding.severity == Finding.INFO

    def test_permissive_is_high(self) -> None:
        with patch("cyberflash.core.security_auditor.AdbManager.shell",
                   return_value="Permissive"):
            finding = SecurityAuditor.check_selinux("ABC")
        assert finding.severity == Finding.HIGH

    def test_unknown_is_medium(self) -> None:
        with patch("cyberflash.core.security_auditor.AdbManager.shell",
                   return_value=""):
            finding = SecurityAuditor.check_selinux("ABC")
        assert finding.severity == Finding.MEDIUM


class TestCheckBootloader:
    def test_locked_is_info(self) -> None:
        with patch("cyberflash.core.security_auditor.AdbManager.get_prop",
                   side_effect=["1", "green"]):
            finding = SecurityAuditor.check_bootloader("ABC")
        assert finding.severity == Finding.INFO

    def test_unlocked_is_high(self) -> None:
        with patch("cyberflash.core.security_auditor.AdbManager.get_prop",
                   side_effect=["0", "orange"]):
            finding = SecurityAuditor.check_bootloader("ABC")
        assert finding.severity == Finding.HIGH


class TestCheckRoot:
    def test_not_rooted_is_info(self) -> None:
        from cyberflash.core.root_manager import RootState
        with patch("cyberflash.core.security_auditor.RootManager.detect_root_state",
                   return_value=RootState.NOT_ROOTED):
            finding = SecurityAuditor.check_root("ABC")
        assert finding.severity == Finding.INFO

    def test_rooted_is_medium(self) -> None:
        from cyberflash.core.root_manager import RootState
        with patch("cyberflash.core.security_auditor.RootManager.detect_root_state",
                   return_value=RootState.ROOTED_MAGISK):
            finding = SecurityAuditor.check_root("ABC")
        assert finding.severity == Finding.MEDIUM


class TestCheckDebugFlags:
    def test_both_disabled_is_info(self) -> None:
        with patch("cyberflash.core.security_auditor.AdbManager.shell",
                   side_effect=["0", "0"]):
            finding = SecurityAuditor.check_debug_flags("ABC")
        assert finding.severity == Finding.INFO

    def test_usb_debug_enabled_is_medium(self) -> None:
        with patch("cyberflash.core.security_auditor.AdbManager.shell",
                   side_effect=["1", "1"]):
            finding = SecurityAuditor.check_debug_flags("ABC")
        assert finding.severity in (Finding.MEDIUM, Finding.LOW)
        assert finding.severity != Finding.INFO


class TestCheckEncryption:
    def test_fbe_is_info(self) -> None:
        with patch("cyberflash.core.security_auditor.AdbManager.get_prop",
                   side_effect=["file", "encrypted"]):
            finding = SecurityAuditor.check_encryption("ABC")
        assert finding.severity == Finding.INFO

    def test_not_encrypted_is_critical(self) -> None:
        with patch("cyberflash.core.security_auditor.AdbManager.get_prop",
                   side_effect=["", "unencrypted"]):
            finding = SecurityAuditor.check_encryption("ABC")
        assert finding.severity == Finding.CRITICAL


class TestRunAudit:
    def test_returns_audit_report(self) -> None:
        from cyberflash.core.root_manager import RootState
        with (
            patch("cyberflash.core.security_auditor.AdbManager.shell",
                  return_value="Enforcing"),
            patch("cyberflash.core.security_auditor.AdbManager.get_prop",
                  return_value="1"),
            patch("cyberflash.core.security_auditor.RootManager.detect_root_state",
                  return_value=RootState.NOT_ROOTED),
        ):
            report = SecurityAuditor.run_audit("ABC")
        assert isinstance(report, AuditReport)
        assert isinstance(report.score, int)
        assert 0 <= report.score <= 100
        assert len(report.findings) == 5

    def test_score_decreases_with_issues(self) -> None:
        from cyberflash.core.root_manager import RootState
        with (
            patch("cyberflash.core.security_auditor.AdbManager.shell",
                  return_value="Permissive"),
            patch("cyberflash.core.security_auditor.AdbManager.get_prop",
                  return_value="0"),
            patch("cyberflash.core.security_auditor.RootManager.detect_root_state",
                  return_value=RootState.ROOTED_MAGISK),
        ):
            report = SecurityAuditor.run_audit("ABC")
        assert report.score < 100
