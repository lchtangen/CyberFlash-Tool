"""feed_registry.py — ROM feed source registry.

Loads feeds.json and provides structured access to ROM feed sources.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Dataclass ─────────────────────────────────────────────────────────────────


@dataclass
class FeedSource:
    """A single ROM/recovery feed source."""

    id: str
    name: str
    base_url: str
    type: str               # "lineage_api" | "pe_api" | "crdroid_api" |
    #                         "sourceforge" | "twrp" | "orangefox_api"
    trust_tier: str         # "verified" | "active" | "community"
    supports_devices: list[str] = field(default_factory=lambda: ["all"])


# ── Registry ──────────────────────────────────────────────────────────────────


class FeedRegistry:
    """Singleton-style registry for ROM feed sources.

    Reads ``resources/rom_feeds/feeds.json`` once and caches the result.
    All public methods are class-methods so no instantiation is needed.
    """

    # Path: core/ -> cyberflash/ -> src/ -> project_root/ -> resources/
    _feeds_path: Path = (
        Path(__file__).parent.parent.parent.parent
        / "resources"
        / "rom_feeds"
        / "feeds.json"
    )
    _feeds: list[FeedSource] = []

    @classmethod
    def load(cls) -> None:
        """Read feeds.json and populate the internal feed list.

        Safe to call multiple times — only loads once unless _feeds is empty.
        """
        if not cls._feeds_path.exists():
            logger.warning("feeds.json not found at %s", cls._feeds_path)
            return

        try:
            data = json.loads(cls._feeds_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load feeds.json: %s", exc)
            return

        cls._feeds = []
        for entry in data.get("feeds", []):
            try:
                cls._feeds.append(
                    FeedSource(
                        id=str(entry["id"]),
                        name=str(entry["name"]),
                        base_url=str(entry["base_url"]),
                        type=str(entry["type"]),
                        trust_tier=str(entry["trust_tier"]),
                        supports_devices=list(entry.get("supports_devices", ["all"])),
                    )
                )
            except KeyError as exc:
                logger.warning("Skipping malformed feed entry (missing %s): %s", exc, entry)

        logger.debug("FeedRegistry loaded %d feed(s)", len(cls._feeds))

    @classmethod
    def list_feeds(cls) -> list[FeedSource]:
        """Return all registered feed sources, loading feeds.json if needed."""
        if not cls._feeds:
            cls.load()
        return list(cls._feeds)

    @classmethod
    def get_feed(cls, feed_id: str) -> FeedSource | None:
        """Return the feed with the given id, or None if not found."""
        for feed in cls.list_feeds():
            if feed.id == feed_id:
                return feed
        return None

    @classmethod
    def feeds_by_tier(cls, tier: str) -> list[FeedSource]:
        """Return feeds filtered by trust tier (verified / active / community)."""
        return [f for f in cls.list_feeds() if f.trust_tier == tier]
