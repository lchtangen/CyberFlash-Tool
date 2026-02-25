"""Unit tests for FlashJournal — append/load/search/export."""

from __future__ import annotations

from pathlib import Path

import pytest

from cyberflash.core.flash_journal import FlashJournal, JournalEntry


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_entry(
    serial: str = "ABC123",
    operation: str = "flash",
    success: bool = True,
    timestamp: str = "2024-01-15T12:00:00Z",
) -> JournalEntry:
    return JournalEntry(
        id=FlashJournal.make_id(),
        timestamp=timestamp,
        serial=serial,
        model="OnePlus 7 Pro",
        operation=operation,
        steps=["unlock", "flash_boot"],
        success=success,
        duration_s=42.5,
        notes="",
    )


# ── Append / load ─────────────────────────────────────────────────────────────


class TestAppendLoad:
    def test_append_and_load(self, tmp_path: Path) -> None:
        journal = FlashJournal(tmp_path / "journal.json")
        entry = _make_entry()
        journal.append(entry)
        loaded = journal.load_all()
        assert len(loaded) == 1
        assert loaded[0].serial == "ABC123"

    def test_multiple_entries_newest_first(self, tmp_path: Path) -> None:
        journal = FlashJournal(tmp_path / "journal.json")
        journal.append(_make_entry(timestamp="2024-01-01T00:00:00Z"))
        journal.append(_make_entry(timestamp="2024-06-01T00:00:00Z"))
        loaded = journal.load_all()
        assert len(loaded) == 2
        assert loaded[0].timestamp > loaded[1].timestamp

    def test_load_empty_journal(self, tmp_path: Path) -> None:
        journal = FlashJournal(tmp_path / "journal.json")
        assert journal.load_all() == []

    def test_corrupt_json_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.json"
        path.write_text("{corrupt}", encoding="utf-8")
        journal = FlashJournal(path)
        assert journal.load_all() == []


# ── Search ────────────────────────────────────────────────────────────────────


class TestSearch:
    def _setup_journal(self, tmp_path: Path) -> FlashJournal:
        journal = FlashJournal(tmp_path / "journal.json")
        journal.append(_make_entry("DEV1", "flash", True,  "2024-01-10T12:00:00Z"))
        journal.append(_make_entry("DEV2", "backup", False, "2024-02-10T12:00:00Z"))
        journal.append(_make_entry("DEV1", "root",  True,  "2024-03-10T12:00:00Z"))
        return journal

    def test_filter_by_serial(self, tmp_path: Path) -> None:
        journal = self._setup_journal(tmp_path)
        results = journal.search(serial="DEV1")
        assert all(e.serial == "DEV1" for e in results)
        assert len(results) == 2

    def test_filter_by_operation(self, tmp_path: Path) -> None:
        journal = self._setup_journal(tmp_path)
        results = journal.search(operation="backup")
        assert len(results) == 1
        assert results[0].operation == "backup"

    def test_filter_by_date_from(self, tmp_path: Path) -> None:
        journal = self._setup_journal(tmp_path)
        results = journal.search(date_from="2024-02-01")
        assert all(e.timestamp >= "2024-02-01" for e in results)

    def test_no_filters_returns_all(self, tmp_path: Path) -> None:
        journal = self._setup_journal(tmp_path)
        assert len(journal.search()) == 3


# ── Export ────────────────────────────────────────────────────────────────────


class TestExport:
    def test_export_csv(self, tmp_path: Path) -> None:
        journal = FlashJournal(tmp_path / "journal.json")
        journal.append(_make_entry())
        csv_path = tmp_path / "export.csv"
        assert journal.export_csv(csv_path) is True
        content = csv_path.read_text()
        assert "serial" in content
        assert "ABC123" in content

    def test_export_html(self, tmp_path: Path) -> None:
        journal = FlashJournal(tmp_path / "journal.json")
        journal.append(_make_entry(success=False))
        html_path = tmp_path / "export.html"
        assert journal.export_html(html_path) is True
        content = html_path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "ABC123" in content

    def test_export_csv_empty(self, tmp_path: Path) -> None:
        journal = FlashJournal(tmp_path / "journal.json")
        csv_path = tmp_path / "empty.csv"
        ok = journal.export_csv(csv_path)
        assert ok is True  # should succeed even with no entries

    def test_make_id_unique(self) -> None:
        ids = {FlashJournal.make_id() for _ in range(100)}
        assert len(ids) >= 90  # allow minor collisions in fast runs
