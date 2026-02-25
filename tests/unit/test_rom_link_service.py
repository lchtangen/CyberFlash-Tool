"""Tests for RomLinkService (no network, no actual threads)."""

from __future__ import annotations

import json
from pathlib import Path

from cyberflash.models.rom_source import SourceStatus
from cyberflash.services.rom_link_service import RomLinkService


class TestRomLinkServiceSources:
    """Test source management without starting the worker thread."""

    def setup_method(self) -> None:
        self.service = RomLinkService()

    def test_add_source(self) -> None:
        src = self.service.add_source("https://example.com/rom.zip", "Example")
        assert src.url == "https://example.com/rom.zip"
        assert src.display_name == "Example"
        assert self.service.source_count == 1

    def test_add_duplicate_returns_existing(self) -> None:
        s1 = self.service.add_source("https://example.com/rom.zip")
        s2 = self.service.add_source("https://example.com/rom.zip")
        assert s1 is s2
        assert self.service.source_count == 1

    def test_remove_source(self) -> None:
        self.service.add_source("https://example.com/rom.zip")
        self.service.remove_source("https://example.com/rom.zip")
        assert self.service.source_count == 0

    def test_remove_nonexistent(self) -> None:
        self.service.remove_source("https://nope.com")
        assert self.service.source_count == 0

    def test_get_source(self) -> None:
        self.service.add_source("https://example.com/rom.zip")
        src = self.service.get_source("https://example.com/rom.zip")
        assert src is not None
        assert src.url == "https://example.com/rom.zip"

    def test_get_source_not_found(self) -> None:
        assert self.service.get_source("https://nope.com") is None

    def test_get_sources_sorted(self) -> None:
        s1 = self.service.add_source("https://a.com/rom.zip")
        s2 = self.service.add_source("https://b.com/rom.zip")
        # Manually set trust so s2 is ranked higher
        from cyberflash.models.rom_source import TrustScore

        s1.trust = TrustScore(availability=0.1, safety=0.1, speed=0.1, reputation=0.1)
        s2.trust = TrustScore(availability=0.9, safety=0.9, speed=0.9, reputation=0.9)

        sources = self.service.get_sources(sort_by_trust=True)
        assert sources[0].url == "https://b.com/rom.zip"

    def test_get_sources_exclude_blocked(self) -> None:
        self.service.add_source("https://a.com/rom.zip")
        s2 = self.service.add_source("https://b.com/rom.zip")
        s2.status = SourceStatus.BLOCKED

        sources = self.service.get_sources(exclude_blocked=True)
        assert len(sources) == 1
        assert sources[0].url == "https://a.com/rom.zip"

    def test_flagged_count(self) -> None:
        s1 = self.service.add_source("https://a.com/rom.zip")
        self.service.add_source("https://b.com/rom.zip")
        s1.status = SourceStatus.FLAGGED
        assert self.service.flagged_count == 1

    def test_healthy_count(self) -> None:
        s1 = self.service.add_source("https://a.com/rom.zip")
        s2 = self.service.add_source("https://b.com/rom.zip")
        s1.status = SourceStatus.VERIFIED
        s2.status = SourceStatus.ACTIVE
        assert self.service.healthy_count == 2


class TestRomLinkServicePersistence:
    """Test JSON load/save for source lists."""

    def test_load_sources_from_json(self, tmp_path: Path) -> None:
        data = [
            {"url": "https://a.com/rom.zip", "display_name": "Alpha"},
            {"url": "https://b.com/rom.zip"},
        ]
        json_file = tmp_path / "sources.json"
        json_file.write_text(json.dumps(data))

        service = RomLinkService()
        count = service.load_sources_from_json(json_file)
        assert count == 2
        assert service.source_count == 2

        src_a = service.get_source("https://a.com/rom.zip")
        assert src_a is not None
        assert src_a.display_name == "Alpha"

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        json_file = tmp_path / "bad.json"
        json_file.write_text("not json")

        service = RomLinkService()
        count = service.load_sources_from_json(json_file)
        assert count == 0

    def test_load_missing_file(self, tmp_path: Path) -> None:
        service = RomLinkService()
        count = service.load_sources_from_json(tmp_path / "missing.json")
        assert count == 0

    def test_save_sources_to_json(self, tmp_path: Path) -> None:
        service = RomLinkService()
        service.add_source("https://a.com/rom.zip", "Alpha")
        service.add_source("https://b.com/rom.zip")

        json_file = tmp_path / "out.json"
        service.save_sources_to_json(json_file)

        data = json.loads(json_file.read_text())
        assert len(data) == 2
        urls = {entry["url"] for entry in data}
        assert "https://a.com/rom.zip" in urls
        assert "https://b.com/rom.zip" in urls

    def test_load_deduplicates(self, tmp_path: Path) -> None:
        data = [
            {"url": "https://a.com/rom.zip"},
            {"url": "https://a.com/rom.zip"},
        ]
        json_file = tmp_path / "dupes.json"
        json_file.write_text(json.dumps(data))

        service = RomLinkService()
        count = service.load_sources_from_json(json_file)
        assert count == 1
        assert service.source_count == 1
