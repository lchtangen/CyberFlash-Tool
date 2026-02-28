"""Unit tests for RomCatalog CRUD and JSON persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import cyberflash.core.rom_catalog as _catalog_module
from cyberflash.core.rom_catalog import CatalogEntry, RomCatalog


# ── Fixture helpers ───────────────────────────────────────────────────────────


def _make_entry(
    codename: str = "oriole",
    distro: str = "lineageos",
    url: str = "https://example.com/rom.zip",
    ai_score: float = 80.0,
    cached_at: str = "2025-01-01T00:00:00",
) -> CatalogEntry:
    return CatalogEntry(
        codename=codename,
        distro=distro,
        version="21.0",
        android_ver="14",
        security_patch="2025-01",
        url=url,
        sha256="abc123",
        build_date="2025-01-01",
        size_bytes=1_000_000_000,
        ai_score=ai_score,
        ai_notes="Test entry",
        download_path="",
        verified=False,
        cached_at=cached_at,
    )


@pytest.fixture(autouse=True)
def _reset_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect catalog path and reset class state before each test."""
    catalog_path = tmp_path / "rom_catalog.json"
    monkeypatch.setattr(_catalog_module, "_CATALOG_PATH", catalog_path)
    # Reset singleton state
    RomCatalog._entries = {}
    RomCatalog._loaded = False


# ── CatalogEntry construction ─────────────────────────────────────────────────


def test_catalog_entry_fields() -> None:
    entry = _make_entry(codename="husky", distro="grapheneos", ai_score=95.0)
    assert entry.codename == "husky"
    assert entry.distro == "grapheneos"
    assert entry.ai_score == 95.0
    assert entry.verified is False
    assert entry.download_path == ""


# ── upsert + get_entries ──────────────────────────────────────────────────────


def test_upsert_and_get_entries_sorted_by_score() -> None:
    low = _make_entry(url="https://example.com/low.zip", ai_score=40.0)
    high = _make_entry(url="https://example.com/high.zip", ai_score=90.0)
    mid = _make_entry(url="https://example.com/mid.zip", ai_score=65.0)

    RomCatalog.upsert(low)
    RomCatalog.upsert(high)
    RomCatalog.upsert(mid)

    entries = RomCatalog.get_entries("oriole")
    assert len(entries) == 3
    assert entries[0].ai_score == 90.0
    assert entries[1].ai_score == 65.0
    assert entries[2].ai_score == 40.0


def test_upsert_updates_existing_by_url() -> None:
    entry = _make_entry(url="https://example.com/rom.zip", ai_score=50.0)
    RomCatalog.upsert(entry)

    updated = _make_entry(url="https://example.com/rom.zip", ai_score=75.0)
    RomCatalog.upsert(updated)

    entries = RomCatalog.get_entries("oriole")
    assert len(entries) == 1
    assert entries[0].ai_score == 75.0


def test_get_entries_empty_for_unknown_codename() -> None:
    assert RomCatalog.get_entries("nonexistent_device") == []


# ── mark_downloaded ───────────────────────────────────────────────────────────


def test_mark_downloaded_updates_path_and_verified(tmp_path: Path) -> None:
    entry = _make_entry(url="https://example.com/rom.zip")
    RomCatalog.upsert(entry)

    RomCatalog.mark_downloaded(
        "https://example.com/rom.zip", str(tmp_path / "rom.zip"), True
    )

    entries = RomCatalog.get_entries("oriole")
    assert entries[0].download_path == str(tmp_path / "rom.zip")
    assert entries[0].verified is True


def test_mark_downloaded_unknown_url_no_error() -> None:
    # Should not raise
    RomCatalog.mark_downloaded("https://nowhere.com/nope.zip", "/tmp/nope.zip", False)


# ── total_count ───────────────────────────────────────────────────────────────


def test_total_count() -> None:
    RomCatalog.upsert(_make_entry(codename="oriole", url="https://a.com/1.zip"))
    RomCatalog.upsert(_make_entry(codename="oriole", url="https://a.com/2.zip"))
    RomCatalog.upsert(_make_entry(codename="husky",  url="https://a.com/3.zip"))
    assert RomCatalog.total_count() == 3


# ── last_scan_time ────────────────────────────────────────────────────────────


def test_last_scan_time_returns_latest() -> None:
    RomCatalog.upsert(_make_entry(url="https://a.com/1.zip", cached_at="2025-01-01T00:00:00"))
    RomCatalog.upsert(_make_entry(url="https://a.com/2.zip", cached_at="2025-06-15T12:00:00"))
    RomCatalog.upsert(_make_entry(url="https://a.com/3.zip", cached_at="2025-03-10T08:00:00"))

    assert RomCatalog.last_scan_time() == "2025-06-15T12:00:00"


def test_last_scan_time_empty_catalog() -> None:
    assert RomCatalog.last_scan_time() == ""


# ── JSON round-trip save/load ─────────────────────────────────────────────────


def test_save_and_load_round_trip() -> None:
    entry = _make_entry(
        codename="tokay",
        url="https://example.com/tokay.zip",
        ai_score=88.0,
        cached_at="2025-05-01T10:00:00",
    )
    RomCatalog.upsert(entry)
    RomCatalog.save()

    # Reset and reload
    RomCatalog._entries = {}
    RomCatalog._loaded = False
    RomCatalog.load()

    entries = RomCatalog.get_entries("tokay")
    assert len(entries) == 1
    loaded = entries[0]
    assert loaded.codename == "tokay"
    assert loaded.ai_score == 88.0
    assert loaded.url == "https://example.com/tokay.zip"
    assert loaded.verified is False


def test_load_from_corrupted_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    catalog_path = tmp_path / "rom_catalog.json"
    monkeypatch.setattr(_catalog_module, "_CATALOG_PATH", catalog_path)
    catalog_path.write_text("not valid json", encoding="utf-8")

    RomCatalog._entries = {}
    RomCatalog._loaded = False
    RomCatalog.load()  # Should not raise

    assert RomCatalog.total_count() == 0


def test_save_creates_parent_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = tmp_path / "deep" / "nested" / "rom_catalog.json"
    monkeypatch.setattr(_catalog_module, "_CATALOG_PATH", nested)

    RomCatalog.upsert(_make_entry())
    RomCatalog.save()

    assert nested.exists()
    data = json.loads(nested.read_text())
    assert "oriole" in data
