"""Unit tests for SecureWiper — mocked ADB, dry-run mode."""

from __future__ import annotations

from cyberflash.core.secure_wiper import SecureWiper, WipeMethod, WipeReport


class TestWipeFileDryRun:
    def test_dry_run_returns_correct_report(self) -> None:
        report = SecureWiper.wipe_file("ABC", "/sdcard/test.txt", dry_run=True)
        assert isinstance(report, WipeReport)
        assert report.path == "/sdcard/test.txt"
        assert report.verified is True

    def test_dry_run_standard_has_one_pass(self) -> None:
        report = SecureWiper.wipe_file(
            "ABC", "/sdcard/secret.db", method=WipeMethod.STANDARD, dry_run=True
        )
        assert report.passes_completed == 1

    def test_dry_run_dod_3pass_has_three_passes(self) -> None:
        report = SecureWiper.wipe_file(
            "ABC", "/sdcard/secret.db", method=WipeMethod.DOD_3PASS, dry_run=True
        )
        assert report.passes_completed == 3

    def test_dry_run_gutmann_has_35_passes(self) -> None:
        report = SecureWiper.wipe_file(
            "ABC", "/sdcard/secret.db", method=WipeMethod.GUTMANN, dry_run=True
        )
        assert report.passes_completed == 35

    def test_dry_run_generates_certificate(self) -> None:
        report = SecureWiper.wipe_file("ABC", "/sdcard/test.txt", dry_run=True)
        assert "CYBERFLASH DATA DESTRUCTION CERTIFICATE" in report.certificate_text

    def test_timestamp_is_set(self) -> None:
        report = SecureWiper.wipe_file("ABC", "/sdcard/test.txt", dry_run=True)
        assert report.timestamp != ""


class TestWipePartitionDryRun:
    def test_dry_run_partition_returns_report(self) -> None:
        report = SecureWiper.wipe_partition("ABC", "userdata", dry_run=True)
        assert "/dev/block/by-name/userdata" in report.path

    def test_partition_dry_run_method_stored(self) -> None:
        report = SecureWiper.wipe_partition(
            "ABC", "userdata", method=WipeMethod.DOD_3PASS, dry_run=True
        )
        assert report.method == WipeMethod.DOD_3PASS


class TestGenerateCertificate:
    def test_certificate_contains_path(self) -> None:
        report = WipeReport(
            path="/sdcard/test.txt",
            method=WipeMethod.STANDARD,
            passes_completed=1,
            verified=True,
            timestamp="2026-01-01T00:00:00",
        )
        cert = SecureWiper.generate_certificate(report)
        assert "/sdcard/test.txt" in cert

    def test_certificate_contains_method(self) -> None:
        report = WipeReport(
            path="/sdcard/test.txt",
            method=WipeMethod.DOD_3PASS,
            passes_completed=3,
            verified=False,
            timestamp="2026-01-01T00:00:00",
        )
        cert = SecureWiper.generate_certificate(report)
        assert "DOD_3PASS" in cert
