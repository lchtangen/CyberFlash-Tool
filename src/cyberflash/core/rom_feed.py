"""rom_feed.py — Aggregated ROM release feed for supported distros.

Fetches release metadata from multiple AOSP-based ROM distribution APIs
and presents them as a unified list of RomRelease objects.

All HTTP is done via stdlib urllib.request (no third-party HTTP libs).
Responses are cached in-process with a configurable TTL.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

logger = logging.getLogger(__name__)

# ── In-process cache ─────────────────────────────────────────────────────────

_CACHE: dict[str, tuple[float, object]] = {}  # key -> (expires_at, data)


# ── Enums ────────────────────────────────────────────────────────────────────


class RomDistro(StrEnum):
    LINEAGE = "lineageos"
    PIXEL_EXPERIENCE = "pixelexperience"
    CRDROID = "crdroid"
    CALYXOS = "calyxos"
    GRAPHENEOS = "grapheneos"
    E_FOUNDATION = "efoundation"
    EVOLUTION_X = "evolutionx"
    NAMELESS_AOSP = "nameless"
    IODE = "iodeos"
    DIVESTOS = "divestos"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class RomRelease:
    """A single ROM release entry."""

    distro: RomDistro
    device: str
    version: str
    android_ver: str
    security_patch: str
    url: str
    size_bytes: int
    sha256: str
    build_date: str          # ISO-8601 date string
    changelog_url: str = ""

    def build_date_parsed(self) -> date | None:
        """Parse build_date as a date object, returning None on failure."""
        # Map format string → expected data length
        candidates: list[tuple[str, int]] = [
            ("%Y%m%d",       8),   # "19990101"
            ("%Y-%m-%d",    10),   # "1999-01-01"
            ("%Y%m%d_%H%M%S", 15), # "19990101_120000"
        ]
        for fmt, width in candidates:
            try:
                return datetime.strptime(self.build_date[:width], fmt).date()
            except ValueError:
                continue
        return None


# ── HTTP helpers ─────────────────────────────────────────────────────────────


def _fetch_json(url: str, timeout: int = 15) -> object | None:
    """Fetch JSON from *url*, returning parsed object or None on error."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "CyberFlash/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        logger.warning("rom_feed fetch failed (%s): %s", url, exc)
        return None


# ── Main class ────────────────────────────────────────────────────────────────


class RomFeed:
    """Classmethod-only aggregator of ROM release feeds."""

    # ── Cache helpers ─────────────────────────────────────────────────────────

    @classmethod
    def _get_cached(cls, key: str) -> object | None:
        entry = _CACHE.get(key)
        if entry and time.monotonic() < entry[0]:
            return entry[1]
        return None

    @classmethod
    def _set_cache(cls, key: str, data: object, ttl_seconds: int = 3600) -> None:
        _CACHE[key] = (time.monotonic() + ttl_seconds, data)

    # ── Per-distro parsers ───────────────────────────────────────────────────

    @classmethod
    def _parse_lineageos(cls, device: str) -> list[RomRelease]:
        """Parse LineageOS nightly/stable JSON feed."""
        url = f"https://download.lineageos.org/api/v2/devices/{device}/builds"
        cache_key = f"lineageos:{device}"
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        data = _fetch_json(url)
        releases: list[RomRelease] = []
        if not isinstance(data, list):
            cls._set_cache(cache_key, releases)
            return releases

        for item in data:
            if not isinstance(item, dict):
                continue
            files = item.get("files", [])
            file_info = files[0] if files else {}
            release = RomRelease(
                distro=RomDistro.LINEAGE,
                device=device,
                version=item.get("version", ""),
                android_ver=str(item.get("version", "")),
                security_patch=item.get("date", "")[:7],
                url=file_info.get("url", ""),
                size_bytes=int(file_info.get("size", 0)),
                sha256=file_info.get("sha256", ""),
                build_date=item.get("date", ""),
                changelog_url=item.get("url", ""),
            )
            releases.append(release)

        cls._set_cache(cache_key, releases)
        return releases

    @classmethod
    def _parse_grapheneos(cls, device: str) -> list[RomRelease]:
        """Parse GrapheneOS JSON feed."""
        url = "https://releases.grapheneos.org/releases.json"
        cache_key = "grapheneos:all"
        cached = cls._get_cached(cache_key)
        raw_data: object
        if cached is not None:
            raw_data = cached
        else:
            raw_data = _fetch_json(url)
            cls._set_cache(cache_key, raw_data)

        releases: list[RomRelease] = []
        if not isinstance(raw_data, dict):
            return releases

        for channel in ("stable", "beta", "alpha"):
            channel_data = raw_data.get(channel, {})
            if not isinstance(channel_data, dict):
                continue
            device_data = channel_data.get(device, {})
            if not isinstance(device_data, dict) or not device_data:
                continue
            release = RomRelease(
                distro=RomDistro.GRAPHENEOS,
                device=device,
                version=str(device_data.get("version", "")),
                android_ver=str(device_data.get("android_version", "")),
                security_patch=str(device_data.get("security_patch_level", "")),
                url=device_data.get("url", ""),
                size_bytes=int(device_data.get("size", 0)),
                sha256=device_data.get("sha256", ""),
                build_date=str(device_data.get("date", "")),
            )
            releases.append(release)
        return releases

    @classmethod
    def _parse_pixelexperience(cls, device: str) -> list[RomRelease]:
        """Parse PixelExperience download API."""
        url = f"https://download.pixelexperience.org/api/v2/{device}/builds/all"
        cache_key = f"pixelexperience:{device}"
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        data = _fetch_json(url)
        releases: list[RomRelease] = []
        if not isinstance(data, list):
            cls._set_cache(cache_key, releases)
            return releases

        for item in data:
            if not isinstance(item, dict):
                continue
            release = RomRelease(
                distro=RomDistro.PIXEL_EXPERIENCE,
                device=device,
                version=item.get("version", ""),
                android_ver=item.get("android_version", ""),
                security_patch=item.get("security_patchlevel", ""),
                url=item.get("download_url", ""),
                size_bytes=int(item.get("size", 0)),
                sha256=item.get("md5sum", ""),
                build_date=item.get("date", ""),
            )
            releases.append(release)

        cls._set_cache(cache_key, releases)
        return releases

    @classmethod
    def _parse_crdroid(cls, device: str) -> list[RomRelease]:
        """Parse crDroid GitHub Releases."""
        # crDroid hosts on SourceForge; use their API endpoint
        url = f"https://crdroid.net/api/v1/devices/{device}"
        cache_key = f"crdroid:{device}"
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        data = _fetch_json(url)
        releases: list[RomRelease] = []
        if not isinstance(data, list):
            cls._set_cache(cache_key, releases)
            return releases

        for item in data:
            if not isinstance(item, dict):
                continue
            release = RomRelease(
                distro=RomDistro.CRDROID,
                device=device,
                version=item.get("version", ""),
                android_ver=item.get("android_version", ""),
                security_patch=item.get("security_patchlevel", ""),
                url=item.get("download", ""),
                size_bytes=int(item.get("size", 0)),
                sha256=item.get("md5", ""),
                build_date=item.get("date", ""),
            )
            releases.append(release)

        cls._set_cache(cache_key, releases)
        return releases

    @classmethod
    def _parse_generic_github(
        cls,
        owner: str,
        repo: str,
        distro: RomDistro,
        device: str,
    ) -> list[RomRelease]:
        """Parse GitHub Releases API for a ROM repository."""
        url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=10"
        cache_key = f"github:{owner}/{repo}:{device}"
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        data = _fetch_json(url)
        releases: list[RomRelease] = []
        if not isinstance(data, list):
            cls._set_cache(cache_key, releases)
            return releases

        for release_item in data:
            if not isinstance(release_item, dict):
                continue
            for asset in release_item.get("assets", []):
                if not isinstance(asset, dict):
                    continue
                name: str = asset.get("name", "")
                if device.lower() not in name.lower():
                    continue
                release = RomRelease(
                    distro=distro,
                    device=device,
                    version=release_item.get("tag_name", ""),
                    android_ver="",
                    security_patch="",
                    url=asset.get("browser_download_url", ""),
                    size_bytes=int(asset.get("size", 0)),
                    sha256="",
                    build_date=release_item.get("published_at", "")[:10],
                    changelog_url=release_item.get("html_url", ""),
                )
                releases.append(release)

        cls._set_cache(cache_key, releases)
        return releases

    @classmethod
    def _fetch_iodeos(cls, device: str) -> list[RomRelease]:
        """Parse IodéOS builds API."""
        url = "https://gitlab.com/iode/os/public-api/-/raw/main/builds.json"
        cache_key = "iodeos:all"
        cached = cls._get_cached(cache_key)
        raw_data: object
        if cached is not None:
            raw_data = cached
        else:
            raw_data = _fetch_json(url)
            cls._set_cache(cache_key, raw_data)

        releases: list[RomRelease] = []
        if not isinstance(raw_data, list):
            logger.debug("IodéOS: unexpected response type for %s", device)
            return releases

        for item in raw_data:
            if not isinstance(item, dict):
                continue
            if item.get("device", "") != device:
                continue
            release = RomRelease(
                distro=RomDistro.IODE,
                device=device,
                version=str(item.get("version", "")),
                android_ver=str(item.get("android_version", "")),
                security_patch=str(item.get("security_patch", "")),
                url=str(item.get("url", "")),
                size_bytes=int(item.get("size", 0)),
                sha256=str(item.get("sha256", "")),
                build_date=str(item.get("date", "")),
                changelog_url=str(item.get("changelog", "")),
            )
            releases.append(release)

        return releases

    @classmethod
    def _fetch_divestos(cls, device: str) -> list[RomRelease]:
        """Parse DivestOS builds listing."""
        url = f"https://divestos.org/builds/full/{device}/builds.json"
        cache_key = f"divestos:{device}"
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        data = _fetch_json(url)
        releases: list[RomRelease] = []
        if not isinstance(data, list):
            logger.debug("DivestOS: no builds found for %s", device)
            cls._set_cache(cache_key, releases)
            return releases

        for item in data:
            if not isinstance(item, dict):
                continue
            release = RomRelease(
                distro=RomDistro.DIVESTOS,
                device=device,
                version=str(item.get("version", "")),
                android_ver=str(item.get("android_version", "")),
                security_patch=str(item.get("security_patch", "")),
                url=str(item.get("url", "")),
                size_bytes=int(item.get("size", 0)),
                sha256=str(item.get("sha256", "")),
                build_date=str(item.get("date", "")),
            )
            releases.append(release)

        cls._set_cache(cache_key, releases)
        return releases

    # ── Public API ────────────────────────────────────────────────────────────

    @classmethod
    def fetch_releases(
        cls,
        distro: RomDistro,
        device_codename: str,
        max_age_days: int = 30,
    ) -> list[RomRelease]:
        """Fetch releases for a single distro + device.

        Results are filtered to those newer than *max_age_days*.
        Returns empty list on network error (never raises).
        """
        try:
            match distro:
                case RomDistro.LINEAGE:
                    releases = cls._parse_lineageos(device_codename)
                case RomDistro.GRAPHENEOS:
                    releases = cls._parse_grapheneos(device_codename)
                case RomDistro.PIXEL_EXPERIENCE:
                    releases = cls._parse_pixelexperience(device_codename)
                case RomDistro.CRDROID:
                    releases = cls._parse_crdroid(device_codename)
                case RomDistro.EVOLUTION_X:
                    releases = cls._parse_generic_github(
                        "Evolution-X", "manifest", distro, device_codename
                    )
                case RomDistro.NAMELESS_AOSP:
                    releases = cls._parse_generic_github(
                        "Nameless-AOSP", "manifest", distro, device_codename
                    )
                case RomDistro.IODE:
                    releases = cls._fetch_iodeos(device_codename)
                case RomDistro.DIVESTOS:
                    releases = cls._fetch_divestos(device_codename)
                case _:
                    releases = []
        except Exception as exc:
            logger.warning("fetch_releases error for %s/%s: %s", distro, device_codename, exc)
            releases = []

        if max_age_days <= 0:
            return releases

        cutoff = time.time() - max_age_days * 86400
        filtered: list[RomRelease] = []
        for r in releases:
            parsed = r.build_date_parsed()
            if parsed is None:
                filtered.append(r)  # keep if unparseable
            else:
                ts = datetime(parsed.year, parsed.month, parsed.day).timestamp()
                if ts >= cutoff:
                    filtered.append(r)
        return filtered

    @classmethod
    def get_all_releases(cls, device_codename: str) -> list[RomRelease]:
        """Aggregate releases from all distros, sorted newest-first."""
        all_releases: list[RomRelease] = []
        for distro in RomDistro:
            try:
                releases = cls.fetch_releases(distro, device_codename, max_age_days=0)
                all_releases.extend(releases)
            except Exception as exc:
                logger.debug("Skipping %s for %s: %s", distro, device_codename, exc)

        def _sort_key(r: RomRelease) -> str:
            return r.build_date or ""

        all_releases.sort(key=_sort_key, reverse=True)
        return all_releases
