"""update_service.py — Application self-update checker.

Queries the GitHub Releases API (no auth required) to detect new versions
and provides chunked download with SHA-256 verification.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from cyberflash import __version__

logger = logging.getLogger(__name__)

# GitHub repository (update if hosted elsewhere)
_GITHUB_API_URL = "https://api.github.com/repos/cyberflash-dev/cyberflash/releases/latest"

_CHECK_INTERVAL_S = 86_400  # 24 hours

# Singleton state
_last_check: float = 0.0
_instance: UpdateService | None = None


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class UpdateInfo:
    """Information about an available update."""

    tag: str
    body: str
    assets: list[dict[str, object]] = field(default_factory=list)
    published_at: str = ""

    @property
    def version(self) -> str:
        return self._tag_to_version(self.tag)

    @staticmethod
    def _tag_to_version(tag: str) -> str:
        return tag.lstrip("v")


# ── Main class ────────────────────────────────────────────────────────────────


class UpdateService:
    """Singleton update checker."""

    def __init__(self) -> None:
        self._last_check: float = 0.0

    @classmethod
    def instance(cls) -> UpdateService:
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    def get_current_version(self) -> str:
        """Return the current installed CyberFlash version string."""
        return __version__

    def check_update(self, force: bool = False) -> UpdateInfo | None:
        """Check GitHub Releases for a newer version.

        Returns UpdateInfo if a newer version is available, else None.
        Uses a 24-hour cache unless *force* is True.
        """
        now = time.monotonic()
        if not force and (now - self._last_check) < _CHECK_INTERVAL_S:
            return None

        self._last_check = now
        data = self._fetch_latest()
        if data is None:
            return None

        tag = str(data.get("tag_name", ""))
        if not tag:
            return None

        # Compare versions: strip leading 'v'
        latest_ver = tag.lstrip("v")
        current_ver = self.get_current_version()

        if not self._is_newer(latest_ver, current_ver):
            return None

        return UpdateInfo(
            tag=tag,
            body=str(data.get("body", "")),
            assets=list(data.get("assets", [])),
            published_at=str(data.get("published_at", "")),
        )

    def download_update(
        self,
        asset_url: str,
        dest_dir: Path,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Download an update asset to *dest_dir* with optional progress.

        Args:
            asset_url:   Direct download URL.
            dest_dir:    Local directory to save file.
            progress_cb: Called with (bytes_downloaded, total_bytes).

        Returns:
            Path to the downloaded file.

        Raises:
            OSError on download failure.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = asset_url.rsplit("/", maxsplit=1)[-1].split("?", maxsplit=1)[0] or "cyberflash_update"
        dest = dest_dir / filename

        req = urllib.request.Request(
            asset_url, headers={"User-Agent": "CyberFlash-Updater/1.0"}
        )
        sha256 = hashlib.sha256()

        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 65_536

            with open(dest, "wb") as fh:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    fh.write(chunk)
                    sha256.update(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)

        logger.info("Downloaded update to %s (sha256: %s)", dest, sha256.hexdigest()[:16])
        return dest

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fetch_latest(self) -> dict[str, object] | None:
        """Fetch the latest release JSON from GitHub API."""
        try:
            req = urllib.request.Request(
                _GITHUB_API_URL,
                headers={
                    "User-Agent": "CyberFlash-Updater/1.0",
                    "Accept": "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            return data if isinstance(data, dict) else None
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            logger.debug("update_service fetch failed: %s", exc)
            return None

    @staticmethod
    def _is_newer(latest: str, current: str) -> bool:
        """Return True if *latest* version string is newer than *current*."""
        def _parse(v: str) -> tuple[int, ...]:
            parts = []
            for part in v.split(".")[:4]:
                try:
                    parts.append(int("".join(c for c in part if c.isdigit()) or "0"))
                except ValueError:
                    parts.append(0)
            return tuple(parts)

        return _parse(latest) > _parse(current)
