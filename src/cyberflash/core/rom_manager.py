"""rom_manager.py — ROM download tracking and path management.

UI-agnostic orchestration layer for ROM file downloads.  Workers handle the
actual network I/O; this module manages destination paths and persists a
lightweight download history to disk.

Usage::

    dest = RomManager.dest_for_url(url)
    # … run DownloadWorker(url, dest) …
    RomManager.record_download(url, dest, sha256=digest)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from urllib.parse import unquote, urlparse

from cyberflash.utils.platform_utils import get_app_data_dir

logger = logging.getLogger(__name__)

_HISTORY_FILE = "history.json"


# ── Download state enum ───────────────────────────────────────────────────────


class DownloadState(StrEnum):
    IDLE        = "idle"
    DOWNLOADING = "downloading"
    VERIFYING   = "verifying"
    COMPLETE    = "complete"
    FAILED      = "failed"
    CANCELLED   = "cancelled"


# ── Download record dataclass ─────────────────────────────────────────────────


@dataclass
class DownloadRecord:
    """Persisted metadata for a single ROM download."""

    url:          str
    filename:     str
    local_path:   str
    state:        str = DownloadState.IDLE   # StrEnum stored as str for JSON compat
    size_bytes:   int = 0
    sha256:       str = ""
    downloaded_at: float = field(default_factory=time.time)

    @property
    def exists(self) -> bool:
        return Path(self.local_path).exists()

    @property
    def is_complete(self) -> bool:
        return self.state == DownloadState.COMPLETE and self.exists


# ── RomManager ───────────────────────────────────────────────────────────────


class RomManager:
    """Utility class for ROM download path resolution and history management.

    All methods are static/class-level — no instance state needed.
    """

    # ── Path helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def get_downloads_dir() -> Path:
        """Return the canonical ROM downloads directory, creating it if needed."""
        d = get_app_data_dir() / "downloads"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def filename_for_url(url: str) -> str:
        """Derive a safe local filename from a URL.

        Takes the last non-empty path segment.  Falls back to ``"rom.zip"``
        if the URL has no usable path component.

        Examples::

            >>> RomManager.filename_for_url("https://example.com/files/boot.img")
            'boot.img'
            >>> RomManager.filename_for_url("https://example.com/")
            'rom.zip'
        """
        try:
            path = urlparse(url).path.rstrip("/")
            name = unquote(path.rsplit("/", 1)[-1]) if "/" in path else unquote(path)
            return name if name else "rom.zip"
        except Exception:
            return "rom.zip"

    @classmethod
    def dest_for_url(cls, url: str) -> Path:
        """Return the local destination Path for a given download URL."""
        return cls.get_downloads_dir() / cls.filename_for_url(url)

    # ── History management ────────────────────────────────────────────────────

    @classmethod
    def _history_path(cls) -> Path:
        return cls.get_downloads_dir() / _HISTORY_FILE

    @classmethod
    def load_history(cls) -> list[DownloadRecord]:
        """Load and return the persisted download history.

        Returns an empty list if the history file is missing or corrupt.
        """
        p = cls._history_path()
        if not p.exists():
            return []
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            return [DownloadRecord(**item) for item in raw]
        except Exception as exc:
            logger.warning("Failed to load ROM download history: %s", exc)
            return []

    @classmethod
    def save_history(cls, records: list[DownloadRecord]) -> None:
        """Persist the download history list to disk."""
        p = cls._history_path()
        try:
            p.write_text(
                json.dumps([asdict(r) for r in records], indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Failed to save ROM download history: %s", exc)

    @classmethod
    def record_download(
        cls,
        url: str,
        local_path: Path,
        sha256: str = "",
        state: DownloadState = DownloadState.COMPLETE,
    ) -> DownloadRecord:
        """Create or update a download record and persist it.

        Replaces any previous record for the same URL.

        Returns:
            The new DownloadRecord.
        """
        size = local_path.stat().st_size if local_path.exists() else 0
        rec = DownloadRecord(
            url=url,
            filename=local_path.name,
            local_path=str(local_path),
            state=str(state),
            size_bytes=size,
            sha256=sha256,
        )
        history = [h for h in cls.load_history() if h.url != url]
        history.append(rec)
        cls.save_history(history)
        logger.info("Recorded download: %s → %s (%d bytes)", url, local_path.name, size)
        return rec

    @classmethod
    def get_record(cls, url: str) -> DownloadRecord | None:
        """Return the most recent download record for *url*, or None."""
        for rec in reversed(cls.load_history()):
            if rec.url == url:
                return rec
        return None

    @classmethod
    def is_downloaded(cls, url: str) -> bool:
        """Return True if a complete local copy exists for *url*."""
        rec = cls.get_record(url)
        return rec is not None and rec.is_complete
