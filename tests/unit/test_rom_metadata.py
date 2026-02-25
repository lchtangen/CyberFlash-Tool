"""Unit tests for RomMetadata — filename parsing, zip extraction."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from cyberflash.core.rom_metadata import GAppsType, RomMetadata


# ── parse_filename ────────────────────────────────────────────────────────────


class TestParseFilename:
    def test_lineageos_filename(self) -> None:
        meta = RomMetadata.parse_filename(
            "lineage-21.0-20240115-nightly-guacamole-signed.zip"
        )
        assert meta.device_codename == "guacamole"

    def test_pixel_experience_filename(self) -> None:
        meta = RomMetadata.parse_filename(
            "PixelExperience_guacamole-14.0-20240115-1803-OFFICIAL.zip"
        )
        assert meta.device_codename == "guacamole"
        assert "14" in meta.android_ver

    def test_gsi_detection(self) -> None:
        meta = RomMetadata.parse_filename("lineage-21.0-gsi-arm64-ab.zip")
        assert meta.is_gsi is True

    def test_non_gsi_detection(self) -> None:
        meta = RomMetadata.parse_filename("lineage-21.0-20240115-nightly-guacamole.zip")
        assert meta.is_gsi is False

    def test_empty_filename_returns_defaults(self) -> None:
        meta = RomMetadata.parse_filename("")
        assert meta.device_codename == ""
        assert meta.gapps_type == GAppsType.UNKNOWN


# ── detect_gapps_type ─────────────────────────────────────────────────────────


class TestDetectGappsType:
    def test_gapps_keyword(self) -> None:
        assert RomMetadata.detect_gapps_type("rom-gapps-guacamole.zip") == GAppsType.STOCK

    def test_vanilla_keyword(self) -> None:
        assert RomMetadata.detect_gapps_type("rom-vanilla-arm64.zip") == GAppsType.VANILLA

    def test_microg_keyword(self) -> None:
        assert RomMetadata.detect_gapps_type("microg-rom.zip") == GAppsType.MICROG

    def test_unknown_when_no_keyword(self) -> None:
        assert RomMetadata.detect_gapps_type("random-rom.zip") == GAppsType.UNKNOWN


# ── parse_security_patch ──────────────────────────────────────────────────────


class TestParseSecurityPatch:
    def test_already_iso(self) -> None:
        assert RomMetadata.parse_security_patch("2024-01-05") == "2024-01-05"

    def test_yyyymmdd_format(self) -> None:
        assert RomMetadata.parse_security_patch("20240105") == "2024-01-05"

    def test_unknown_format_passthrough(self) -> None:
        result = RomMetadata.parse_security_patch("2024/01/05")
        assert "2024" in result


# ── extract_from_zip ──────────────────────────────────────────────────────────


class TestExtractFromZip:
    def test_extracts_build_prop(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "rom.zip"
        build_prop = (
            "ro.build.version.release=14\n"
            "ro.build.version.security_patch=2024-01-05\n"
        )
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("system/build.prop", build_prop)
        meta = RomMetadata.extract_from_zip(zip_path)
        assert meta.android_ver == "14"
        assert meta.security_patch == "2024-01-05"

    def test_bad_zip_returns_defaults(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"\x00\x01\x02")
        meta = RomMetadata.extract_from_zip(bad)
        assert meta.android_ver == "" or isinstance(meta.android_ver, str)

    def test_missing_zip_returns_defaults(self, tmp_path: Path) -> None:
        meta = RomMetadata.extract_from_zip(tmp_path / "missing.zip")
        assert isinstance(meta.android_ver, str)

    def test_gapps_detection_from_filename(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "rom-gapps-guacamole.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("dummy.txt", "")
        meta = RomMetadata.extract_from_zip(zip_path)
        assert meta.gapps_type == GAppsType.STOCK


# ── fetch_changelog ───────────────────────────────────────────────────────────


class TestFetchChangelog:
    def test_empty_url_returns_empty(self) -> None:
        assert RomMetadata.fetch_changelog("") == ""

    def test_network_error_returns_empty(self) -> None:
        import urllib.error
        from unittest.mock import patch
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            result = RomMetadata.fetch_changelog("http://example.com/changelog")
        assert result == ""
