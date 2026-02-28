"""Unit tests for PrivacyScannerWorker — init, abort, and internal scan logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cyberflash.workers.privacy_scanner_worker import (
    AppPrivacyScore,
    PrivacyScannerWorker,
    TrackingSDK,
)


class TestWorkerInit:
    def test_serial_stored(self) -> None:
        worker = PrivacyScannerWorker("TEST123")
        assert worker._serial == "TEST123"

    def test_abort_flag_initially_false(self) -> None:
        worker = PrivacyScannerWorker("TEST123")
        assert worker._aborted is False

    def test_abort_sets_flag(self) -> None:
        worker = PrivacyScannerWorker("TEST123")
        worker.abort()
        assert worker._aborted is True

    def test_signals_defined(self) -> None:
        worker = PrivacyScannerWorker("TEST123")
        assert hasattr(worker, "app_scanned")
        assert hasattr(worker, "scan_complete")
        assert hasattr(worker, "finished")
        assert hasattr(worker, "error")


class TestListThirdPartyPackages:
    def test_parses_pm_output(self) -> None:
        worker = PrivacyScannerWorker("S1")
        pm_output = "package:com.example.one\npackage:com.example.two\nsome other line\n"
        with patch("cyberflash.workers.privacy_scanner_worker.AdbManager.shell", return_value=pm_output):
            pkgs = worker._list_third_party_packages()
        assert pkgs == ["com.example.one", "com.example.two"]

    def test_empty_output_returns_empty_list(self) -> None:
        worker = PrivacyScannerWorker("S1")
        with patch("cyberflash.workers.privacy_scanner_worker.AdbManager.shell", return_value=""):
            pkgs = worker._list_third_party_packages()
        assert pkgs == []

    def test_strips_whitespace(self) -> None:
        worker = PrivacyScannerWorker("S1")
        pm_output = "package:  com.example.trimmed  \n"
        with patch("cyberflash.workers.privacy_scanner_worker.AdbManager.shell", return_value=pm_output):
            pkgs = worker._list_third_party_packages()
        assert pkgs == ["com.example.trimmed"]


class TestScanPackage:
    def test_clean_app_scores_100(self) -> None:
        worker = PrivacyScannerWorker("S1")
        with patch("cyberflash.workers.privacy_scanner_worker.AdbManager.shell", return_value=""):
            result = worker._scan_package("com.clean.app")
        assert result.score == 100
        assert result.sdks == []
        assert result.dangerous_perms == []

    def test_detects_facebook_sdk(self) -> None:
        worker = PrivacyScannerWorker("S1")
        dump = "com.facebook.ads.AdView\ncom.facebook.analytics"
        with patch("cyberflash.workers.privacy_scanner_worker.AdbManager.shell", return_value=dump):
            result = worker._scan_package("com.some.app")
        sdk_names = [s.name for s in result.sdks]
        assert "Facebook SDK" in sdk_names

    def test_dangerous_perm_reduces_score(self) -> None:
        worker = PrivacyScannerWorker("S1")
        # ACCESS_FINE_LOCATION granted=true reduces by 15
        dump = "android.permission.ACCESS_FINE_LOCATION: granted=true"
        with patch("cyberflash.workers.privacy_scanner_worker.AdbManager.shell", return_value=dump):
            result = worker._scan_package("com.spy.app")
        assert result.score <= 85
        assert "android.permission.ACCESS_FINE_LOCATION" in result.dangerous_perms

    def test_score_never_below_zero(self) -> None:
        worker = PrivacyScannerWorker("S1")
        # Pile on many dangerous permissions + SDKs
        lines = []
        for perm in [
            "android.permission.ACCESS_FINE_LOCATION: granted=true",
            "android.permission.ACCESS_BACKGROUND_LOCATION: granted=true",
            "android.permission.RECORD_AUDIO: granted=true",
            "android.permission.READ_SMS: granted=true",
            "android.permission.SEND_SMS: granted=true",
            "android.permission.READ_CALL_LOG: granted=true",
        ]:
            lines.append(perm)
        lines += [
            "com.facebook.ads.something",
            "com.adjust.sdk.Adjust",
            "com.appsflyer.AFInAppEventType",
        ]
        dump = "\n".join(lines)
        with patch("cyberflash.workers.privacy_scanner_worker.AdbManager.shell", return_value=dump):
            result = worker._scan_package("com.nasty.app")
        assert result.score >= 0

    def test_package_name_stored(self) -> None:
        worker = PrivacyScannerWorker("S1")
        with patch("cyberflash.workers.privacy_scanner_worker.AdbManager.shell", return_value=""):
            result = worker._scan_package("com.my.pkg")
        assert result.package == "com.my.pkg"


class TestDataclasses:
    def test_app_privacy_score_defaults(self) -> None:
        score = AppPrivacyScore(package="com.x", score=80)
        assert score.sdks == []
        assert score.dangerous_perms == []

    def test_tracking_sdk_fields(self) -> None:
        sdk = TrackingSDK(name="Foo", package_hint=r"com\.foo", risk_level=3)
        assert sdk.name == "Foo"
        assert sdk.risk_level == 3
