"""profile_hub_service.py — Community device profile hub.

Fetches community-contributed device profiles from a remote registry
(GitHub raw content or configurable URL), caches them locally, and
exposes them through the ProfileRegistry.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_COMMUNITY_INDEX_URL = (
    "https://raw.githubusercontent.com/cyberflash-community/profiles/main/index.json"
)
_CACHE_DIR_NAME = "community_profiles"


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class HubEntry:
    """One entry from the community profile index."""

    codename: str
    brand: str
    model: str
    url: str
    sha256: str = ""
    author: str = ""
    stars: int = 0


# ── Service ───────────────────────────────────────────────────────────────────


class ProfileHubService(QObject):
    """Service that manages fetching and caching community device profiles.

    Signals:
        index_ready(list[HubEntry])   — emitted when the index is downloaded
        profile_saved(str)            — emitted with codename after saving
        error(str)                    — emitted on download / parse failure
    """

    index_ready   = Signal(list)   # list[HubEntry]
    profile_saved = Signal(str)    # codename
    error         = Signal(str)

    def __init__(
        self,
        cache_dir: Path | None = None,
        index_url: str = _COMMUNITY_INDEX_URL,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._index_url = index_url
        self._cache_dir: Path = (
            cache_dir
            if cache_dir is not None
            else Path.home() / ".cyberflash" / _CACHE_DIR_NAME
        )
        self._entries: list[HubEntry] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh_index(self) -> None:
        """Fetch the remote profile index in a background thread."""
        threading.Thread(target=self._fetch_index, daemon=True).start()

    def get_entries(self) -> list[HubEntry]:
        """Return the most recently fetched entries (may be empty)."""
        return list(self._entries)

    def download_profile(self, entry: HubEntry) -> bool:
        """Download and save a community profile.

        Returns ``True`` on success; emits ``profile_saved`` signal.
        """
        try:
            import urllib.request

            self._cache_dir.mkdir(parents=True, exist_ok=True)
            dest = self._cache_dir / f"{entry.codename}.json"
            logger.info("Downloading profile for %s from %s", entry.codename, entry.url)
            with urllib.request.urlopen(entry.url, timeout=15) as resp:
                data = resp.read()

            # Basic JSON validation
            parsed = json.loads(data)
            if "codename" not in parsed:
                self.error.emit(f"Invalid profile for {entry.codename}: missing 'codename' field")
                return False

            dest.write_bytes(data)
            logger.info("Saved community profile: %s", dest)
            self.profile_saved.emit(entry.codename)
            return True

        except Exception as exc:
            msg = f"Failed to download profile '{entry.codename}': {exc}"
            logger.exception(msg)
            self.error.emit(msg)
            return False

    def search(self, query: str) -> list[HubEntry]:
        """Return entries matching ``query`` in codename, model, or brand."""
        q = query.lower()
        return [
            e for e in self._entries
            if q in e.codename.lower()
            or q in e.model.lower()
            or q in e.brand.lower()
        ]

    def cached_profiles(self) -> list[Path]:
        """Return paths of locally cached community profiles."""
        if not self._cache_dir.is_dir():
            return []
        return sorted(self._cache_dir.glob("*.json"))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _fetch_index(self) -> None:
        """Background: download and parse the community index JSON."""
        try:
            import urllib.request

            logger.info("Fetching community profile index from %s", self._index_url)
            with urllib.request.urlopen(self._index_url, timeout=15) as resp:
                raw = resp.read()

            entries = self._parse_index(raw.decode("utf-8"))
            self._entries = entries
            logger.info("Community index loaded: %d profiles", len(entries))
            self.index_ready.emit(entries)

        except Exception as exc:
            msg = f"Failed to fetch community profile index: {exc}"
            logger.exception(msg)
            self.error.emit(msg)

    @staticmethod
    def _parse_index(json_text: str) -> list[HubEntry]:
        """Parse community index JSON into :class:`HubEntry` objects."""
        data = json.loads(json_text)
        entries: list[HubEntry] = []
        for item in data.get("profiles", []):
            try:
                entries.append(HubEntry(
                    codename=item["codename"],
                    brand=item.get("brand", ""),
                    model=item.get("model", ""),
                    url=item["url"],
                    sha256=item.get("sha256", ""),
                    author=item.get("author", ""),
                    stars=int(item.get("stars", 0)),
                ))
            except (KeyError, ValueError):
                logger.warning("Skipping malformed profile index entry: %s", item)
        return entries
