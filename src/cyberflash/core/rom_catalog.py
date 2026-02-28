"""rom_catalog.py — Persistent local ROM catalog.

Stores discovered ROM entries as a JSON file at
``~/.cyberflash/rom_catalog.json``.  The catalog is a class-level
singleton; all public methods are classmethods so callers don't need an
instance.
"""

from __future__ import annotations

import contextlib
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_CATALOG_PATH = Path.home() / ".cyberflash" / "rom_catalog.json"


@dataclass
class CatalogEntry:
    """A single discovered ROM release, with AI scoring metadata."""

    codename: str
    distro: str
    version: str
    android_ver: str
    security_patch: str
    url: str
    sha256: str
    build_date: str
    size_bytes: int
    ai_score: float        # 0-100 composite AI score
    ai_notes: str          # Human-readable scoring summary
    download_path: str     # "" = not yet downloaded
    verified: bool         # True if SHA-256 confirmed post-download
    cached_at: str         # ISO-8601 UTC timestamp of discovery


class RomCatalog:
    """Class-level persistent ROM catalog backed by a JSON file.

    Thread-safety note: this class is *not* thread-safe on its own.
    Callers on background threads should only call it from a single worker
    thread (the ``RomDiscoveryWorker``) or protect access externally.
    """

    _entries: dict[str, list[CatalogEntry]] = {}  # codename → entries
    _loaded: bool = False

    # ── Persistence ──────────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> None:
        """Load the catalog from disk.  Silently starts empty on first run."""
        if not _CATALOG_PATH.exists():
            cls._entries = {}
            cls._loaded = True
            return
        try:
            with _CATALOG_PATH.open(encoding="utf-8") as f:
                raw: object = json.load(f)
            if not isinstance(raw, dict):
                cls._entries = {}
            else:
                cls._entries = {}
                for codename, items in raw.items():
                    if not isinstance(items, list):
                        continue
                    parsed: list[CatalogEntry] = []
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        with contextlib.suppress(TypeError):
                            parsed.append(CatalogEntry(**item))
                    cls._entries[codename] = parsed
            logger.info("ROM catalog loaded: %d codenames", len(cls._entries))
        except Exception as exc:
            logger.warning("Failed to load ROM catalog: %s", exc)
            cls._entries = {}
        cls._loaded = True

    @classmethod
    def save(cls) -> None:
        """Persist the catalog to disk."""
        try:
            _CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                codename: [asdict(e) for e in entries]
                for codename, entries in cls._entries.items()
            }
            with _CATALOG_PATH.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug("ROM catalog saved (%d codenames)", len(data))
        except Exception as exc:
            logger.warning("Failed to save ROM catalog: %s", exc)

    # ── Accessors ────────────────────────────────────────────────────────────

    @classmethod
    def _ensure_loaded(cls) -> None:
        if not cls._loaded:
            cls.load()

    @classmethod
    def get_entries(cls, codename: str) -> list[CatalogEntry]:
        """Return all catalog entries for *codename*, sorted best-score-first."""
        cls._ensure_loaded()
        entries = cls._entries.get(codename, [])
        return sorted(entries, key=lambda e: e.ai_score, reverse=True)

    @classmethod
    def get_all(cls) -> dict[str, list[CatalogEntry]]:
        """Return a shallow copy of the full catalog dict."""
        cls._ensure_loaded()
        return dict(cls._entries)

    @classmethod
    def upsert(cls, entry: CatalogEntry) -> None:
        """Insert or update an entry, keyed by URL."""
        cls._ensure_loaded()
        bucket = cls._entries.setdefault(entry.codename, [])
        for i, existing in enumerate(bucket):
            if existing.url == entry.url:
                bucket[i] = entry
                return
        bucket.append(entry)

    @classmethod
    def mark_downloaded(cls, url: str, path: str, verified: bool) -> None:
        """Record a completed download for the given URL."""
        cls._ensure_loaded()
        for entries in cls._entries.values():
            for entry in entries:
                if entry.url == url:
                    entry.download_path = path
                    entry.verified = verified
                    cls.save()
                    return
        logger.debug("mark_downloaded: URL not found in catalog: %s", url)

    @classmethod
    def total_count(cls) -> int:
        """Total number of entries across all codenames."""
        cls._ensure_loaded()
        return sum(len(v) for v in cls._entries.values())

    @classmethod
    def last_scan_time(cls) -> str:
        """Return the most recent cached_at timestamp across all entries, or ''."""
        cls._ensure_loaded()
        latest = ""
        for entries in cls._entries.values():
            for e in entries:
                if e.cached_at > latest:
                    latest = e.cached_at
        return latest
