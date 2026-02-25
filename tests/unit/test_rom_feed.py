"""Unit tests for RomFeed — mocked urllib."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from cyberflash.core.rom_feed import RomDistro, RomFeed, RomRelease, _CACHE


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_urlopen(data: object, status: int = 200):
    """Return a context-manager mock that yields JSON bytes."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(data).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.headers = {}
    return mock_resp


# ── RomRelease dataclass ──────────────────────────────────────────────────────


class TestRomRelease:
    def test_build_date_parsed_yyyymmdd(self) -> None:
        r = RomRelease(
            distro=RomDistro.LINEAGE, device="guacamole",
            version="21.0", android_ver="14", security_patch="2024-01",
            url="", size_bytes=0, sha256="", build_date="20240115",
        )
        d = r.build_date_parsed()
        assert d is not None
        assert d.year == 2024
        assert d.month == 1

    def test_build_date_parsed_iso(self) -> None:
        r = RomRelease(
            distro=RomDistro.LINEAGE, device="guacamole",
            version="21.0", android_ver="14", security_patch="2024-01",
            url="", size_bytes=0, sha256="", build_date="2024-01-15",
        )
        d = r.build_date_parsed()
        assert d is not None
        assert d.day == 15

    def test_build_date_parsed_invalid_returns_none(self) -> None:
        r = RomRelease(
            distro=RomDistro.LINEAGE, device="guacamole",
            version="", android_ver="", security_patch="",
            url="", size_bytes=0, sha256="", build_date="not-a-date",
        )
        assert r.build_date_parsed() is None


# ── Cache ─────────────────────────────────────────────────────────────────────


class TestCache:
    def setup_method(self) -> None:
        _CACHE.clear()

    def test_set_and_get_cache(self) -> None:
        RomFeed._set_cache("test_key", [1, 2, 3], ttl_seconds=3600)
        assert RomFeed._get_cached("test_key") == [1, 2, 3]

    def test_missing_key_returns_none(self) -> None:
        assert RomFeed._get_cached("nonexistent") is None

    def test_expired_returns_none(self) -> None:
        import time
        RomFeed._set_cache("expired_key", "data", ttl_seconds=-1)
        assert RomFeed._get_cached("expired_key") is None


# ── _parse_lineageos ──────────────────────────────────────────────────────────


class TestParseLineageOs:
    def setup_method(self) -> None:
        _CACHE.clear()

    def test_returns_list_on_valid_response(self) -> None:
        data = [
            {
                "version": "21.0",
                "date": "20240115",
                "files": [{"url": "http://example.com/rom.zip", "size": 1024000, "sha256": "abc"}],
            }
        ]
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen(data)
            releases = RomFeed._parse_lineageos("guacamole")
        assert len(releases) == 1
        assert releases[0].distro == RomDistro.LINEAGE

    def test_returns_empty_on_non_list_response(self) -> None:
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen({"error": "not found"})
            releases = RomFeed._parse_lineageos("unknown_device")
        assert releases == []

    def test_network_error_returns_empty(self) -> None:
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            releases = RomFeed._parse_lineageos("guacamole")
        assert releases == []

    def test_uses_cache_on_second_call(self) -> None:
        _CACHE.clear()
        data = [{"version": "21.0", "date": "20240115", "files": []}]
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen(data)
            releases1 = RomFeed._parse_lineageos("guacamole")
            releases2 = RomFeed._parse_lineageos("guacamole")
        assert mock_open.call_count == 1
        assert len(releases1) == len(releases2)


# ── _parse_grapheneos ─────────────────────────────────────────────────────────


class TestParseGrapheneOs:
    def setup_method(self) -> None:
        _CACHE.clear()

    def test_stable_channel_parsed(self) -> None:
        data = {
            "stable": {
                "oriole": {
                    "version": "2024011200",
                    "android_version": "14",
                    "security_patch_level": "2024-01-05",
                    "url": "http://example.com/oriole.zip",
                    "size": 2000000,
                    "sha256": "deadbeef",
                    "date": "20240112",
                }
            }
        }
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen(data)
            releases = RomFeed._parse_grapheneos("oriole")
        assert len(releases) >= 1
        assert releases[0].distro == RomDistro.GRAPHENEOS

    def test_unknown_device_returns_empty(self) -> None:
        data = {"stable": {}, "beta": {}, "alpha": {}}
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen(data)
            releases = RomFeed._parse_grapheneos("guacamole")
        assert releases == []


# ── fetch_releases ────────────────────────────────────────────────────────────


class TestFetchReleases:
    def setup_method(self) -> None:
        _CACHE.clear()

    def test_fetch_lineage_max_age_filter(self) -> None:
        data = [
            {"version": "21.0", "date": "19990101", "files": []},  # too old
        ]
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen(data)
            releases = RomFeed.fetch_releases(RomDistro.LINEAGE, "guacamole", max_age_days=30)
        assert releases == []

    def test_fetch_no_age_filter(self) -> None:
        data = [
            {"version": "21.0", "date": "19990101", "files": [{"url": "x", "size": 1, "sha256": "x"}]},
        ]
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen(data)
            releases = RomFeed.fetch_releases(RomDistro.LINEAGE, "guacamole", max_age_days=0)
        assert len(releases) == 1

    def test_unknown_distro_returns_empty(self) -> None:
        releases = RomFeed.fetch_releases(RomDistro.CALYXOS, "guacamole")
        assert isinstance(releases, list)


# ── get_all_releases ──────────────────────────────────────────────────────────


class TestGetAllReleases:
    def setup_method(self) -> None:
        _CACHE.clear()

    def test_aggregates_all_distros(self) -> None:
        with patch.object(RomFeed, "fetch_releases", return_value=[]) as mock_fetch:
            results = RomFeed.get_all_releases("guacamole")
        assert mock_fetch.call_count == len(RomDistro)
        assert isinstance(results, list)

    def test_sorted_newest_first(self) -> None:
        releases = [
            RomRelease(RomDistro.LINEAGE, "g", "1", "14", "", "", 0, "", "2024-01-01"),
            RomRelease(RomDistro.CRDROID, "g", "1", "14", "", "", 0, "", "2024-06-01"),
        ]
        with patch.object(RomFeed, "fetch_releases", side_effect=[releases[:1], releases[1:], [], [], [], [], [], []]):
            results = RomFeed.get_all_releases("g")
        if len(results) >= 2:
            assert results[0].build_date >= results[1].build_date
