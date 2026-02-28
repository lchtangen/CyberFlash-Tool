"""Unit tests for ProfileHubService — parse, search, cache."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cyberflash.services.profile_hub_service import HubEntry, ProfileHubService


_INDEX_JSON = json.dumps({
    "profiles": [
        {
            "codename": "guacamole",
            "brand": "OnePlus",
            "model": "OnePlus 7 Pro",
            "url": "https://example.com/guacamole.json",
            "sha256": "abc123",
            "author": "community",
            "stars": 42,
        },
        {
            "codename": "blueline",
            "brand": "Google",
            "model": "Pixel 3",
            "url": "https://example.com/blueline.json",
            "author": "goog",
        },
    ]
})


class TestParseIndex:
    def test_parses_entries(self) -> None:
        entries = ProfileHubService._parse_index(_INDEX_JSON)
        assert len(entries) == 2

    def test_entry_fields(self) -> None:
        entries = ProfileHubService._parse_index(_INDEX_JSON)
        guac = next(e for e in entries if e.codename == "guacamole")
        assert guac.brand == "OnePlus"
        assert guac.model == "OnePlus 7 Pro"
        assert guac.stars == 42
        assert guac.sha256 == "abc123"

    def test_missing_optional_fields_defaults(self) -> None:
        entries = ProfileHubService._parse_index(_INDEX_JSON)
        blue = next(e for e in entries if e.codename == "blueline")
        assert blue.sha256 == ""
        assert blue.stars == 0

    def test_empty_profiles_list(self) -> None:
        entries = ProfileHubService._parse_index('{"profiles": []}')
        assert entries == []

    def test_skips_malformed_entry(self) -> None:
        bad = json.dumps({"profiles": [{"no_codename": "x"}, {"codename": "ok", "url": "u"}]})
        entries = ProfileHubService._parse_index(bad)
        # Only the valid entry with both required fields passes
        assert all(e.codename for e in entries)


class TestSearch:
    def _service_with_entries(self) -> ProfileHubService:
        svc = ProfileHubService()
        svc._entries = ProfileHubService._parse_index(_INDEX_JSON)
        return svc

    def test_search_by_codename(self) -> None:
        svc = self._service_with_entries()
        results = svc.search("guac")
        assert any(e.codename == "guacamole" for e in results)

    def test_search_by_brand(self) -> None:
        svc = self._service_with_entries()
        results = svc.search("google")
        assert any(e.codename == "blueline" for e in results)

    def test_search_no_match(self) -> None:
        svc = self._service_with_entries()
        results = svc.search("zzznomatch")
        assert results == []

    def test_search_case_insensitive(self) -> None:
        svc = self._service_with_entries()
        results = svc.search("ONEPLUS")
        assert len(results) >= 1


class TestCachedProfiles:
    def test_empty_cache_returns_empty_list(self, tmp_path: Path) -> None:
        svc = ProfileHubService(cache_dir=tmp_path / "profiles")
        assert svc.cached_profiles() == []

    def test_lists_json_files(self, tmp_path: Path) -> None:
        cache = tmp_path / "profiles"
        cache.mkdir()
        (cache / "guacamole.json").write_text('{"codename":"guacamole"}')
        (cache / "blueline.json").write_text('{"codename":"blueline"}')
        svc = ProfileHubService(cache_dir=cache)
        paths = svc.cached_profiles()
        assert len(paths) == 2
        assert all(p.suffix == ".json" for p in paths)


class TestGetEntries:
    def test_initially_empty(self) -> None:
        svc = ProfileHubService()
        assert svc.get_entries() == []

    def test_returns_copy(self) -> None:
        svc = ProfileHubService()
        svc._entries = [HubEntry("x", "b", "m", "url")]
        entries = svc.get_entries()
        entries.clear()  # should not affect internal list
        assert len(svc._entries) == 1
