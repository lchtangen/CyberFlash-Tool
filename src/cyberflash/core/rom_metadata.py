"""rom_metadata.py — ROM zip filename / content metadata extraction.

Parses ROM filenames (e.g. lineage-21.0-20240115-nightly-guacamole-signed.zip)
and ZIP contents (build.prop, updater-script) to extract structured metadata.
"""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────


class GAppsType(StrEnum):
    STOCK = "stock"
    VANILLA = "vanilla"
    MICROG = "microg"
    UNKNOWN = "unknown"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class RomMeta:
    """Structured metadata for a ROM release."""

    android_ver: str = ""
    security_patch: str = ""
    gapps_type: GAppsType = GAppsType.UNKNOWN
    kernel_source_url: str = ""
    changelog: str = ""
    device_codename: str = ""
    is_gsi: bool = False


# ── Regex patterns ───────────────────────────────────────────────────────────

# Matches: lineage-21.0-20240115-nightly-guacamole
_RE_LINEAGE = re.compile(
    r"lineage-(?P<ver>\d+\.\d+)-(?P<date>\d{8})-\w+-(?P<device>[a-z0-9_]+)"
)

# Matches: evolution_guacamole-ota-tq3c.230901.001-14-20240101
_RE_EVX = re.compile(r"evolution_(?P<device>[a-z0-9_]+)-ota-.*-(?P<android>\d+)-(?P<date>\d{8})")

# Matches: PixelExperience_guacamole-14.0-20240115-1803-OFFICIAL (lowercased before match)
_RE_PE = re.compile(
    r"pixelexperience_(?P<device>[a-z0-9_]+)-(?P<ver>\d+\.\d+)-(?P<date>\d{8})"
)

# Matches Android version in build.prop: ro.build.version.release=14
_RE_ANDROID_VER = re.compile(r"ro\.build\.version\.release\s*=\s*(\S+)")

# Matches security patch: ro.build.version.security_patch=2024-01-05
_RE_SEC_PATCH = re.compile(r"ro\.build\.version\.security_patch\s*=\s*(\S+)")

# GSI indicators
_GSI_KEYWORDS = ("gsi", "treble", "_arm64_", "_arm_", "_x86")

# GApps keywords
_GAPPS_KEYWORDS = {"gapps": GAppsType.STOCK, "vanilla": GAppsType.VANILLA, "microg": GAppsType.MICROG}


# ── Main class ────────────────────────────────────────────────────────────────


class RomMetadata:
    """Classmethod-only metadata extractor for ROM zips and filenames."""

    @classmethod
    def parse_filename(cls, filename: str) -> RomMeta:
        """Extract metadata from a ROM zip filename using regex patterns."""
        name_lower = filename.lower()
        meta = RomMeta()

        # Device codename
        for pattern in (_RE_LINEAGE, _RE_EVX, _RE_PE):
            m = pattern.search(name_lower)
            if m and "device" in m.groupdict():
                meta.device_codename = m.group("device")
                break

        # Android version from PE/LineageOS patterns
        m_pe = _RE_PE.search(name_lower)
        if m_pe:
            meta.android_ver = m_pe.group("ver").split(".")[0]

        m_lineage = _RE_LINEAGE.search(name_lower)
        if m_lineage:
            # LineageOS 21 → Android 14 mapping (approx)
            los_ver = float(m_lineage.group("ver"))
            meta.android_ver = str(int(los_ver) - 7) if los_ver >= 14 else ""

        # GApps type
        meta.gapps_type = cls.detect_gapps_type(filename)

        # GSI detection
        meta.is_gsi = any(kw in name_lower for kw in _GSI_KEYWORDS)

        return meta

    @classmethod
    def detect_gapps_type(cls, filename: str) -> GAppsType:
        """Detect GApps type from ROM filename keywords."""
        name_lower = filename.lower()
        for keyword, gapps_type in _GAPPS_KEYWORDS.items():
            if keyword in name_lower:
                return gapps_type
        return GAppsType.UNKNOWN

    @classmethod
    def extract_from_zip(cls, zip_path: Path) -> RomMeta:
        """Extract metadata from a ROM zip's build.prop / updater-script."""
        meta = RomMeta()
        meta.gapps_type = cls.detect_gapps_type(zip_path.name)
        meta.is_gsi = any(kw in zip_path.name.lower() for kw in _GSI_KEYWORDS)

        try:
            with zipfile.ZipFile(zip_path) as zf:
                namelist = zf.namelist()

                # Try build.prop locations
                prop_candidates = [
                    "system/build.prop",
                    "META-INF/com/android/metadata",
                ]
                for candidate in prop_candidates:
                    if candidate in namelist:
                        try:
                            content = zf.read(candidate).decode(errors="replace")
                            cls._parse_build_prop(content, meta)
                            break
                        except (KeyError, UnicodeDecodeError):
                            continue

                # Try updater-script for additional metadata
                updater = "META-INF/com/google/android/updater-script"
                if updater in namelist:
                    try:
                        script = zf.read(updater).decode(errors="replace")
                        if not meta.android_ver:
                            m = re.search(r"android.version[\"=\s]+(\d+)", script, re.IGNORECASE)
                            if m:
                                meta.android_ver = m.group(1)
                    except (KeyError, UnicodeDecodeError):
                        pass

        except (zipfile.BadZipFile, OSError) as exc:
            logger.warning("extract_from_zip failed for %s: %s", zip_path, exc)

        # Fall back to filename parsing for missing fields
        fname_meta = cls.parse_filename(zip_path.name)
        if not meta.android_ver:
            meta.android_ver = fname_meta.android_ver
        if not meta.device_codename:
            meta.device_codename = fname_meta.device_codename

        return meta

    @classmethod
    def _parse_build_prop(cls, content: str, meta: RomMeta) -> None:
        """Parse build.prop content, populating *meta* in-place."""
        m_ver = _RE_ANDROID_VER.search(content)
        if m_ver:
            meta.android_ver = m_ver.group(1)

        m_patch = _RE_SEC_PATCH.search(content)
        if m_patch:
            meta.security_patch = cls.parse_security_patch(m_patch.group(1))

    @classmethod
    def parse_security_patch(cls, prop_str: str) -> str:
        """Normalize security patch date to YYYY-MM-DD format."""
        # Remove whitespace
        s = prop_str.strip()
        # Already YYYY-MM-DD
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return s
        # YYYYMMDD → YYYY-MM-DD
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return s

    @classmethod
    def fetch_changelog(cls, url: str, max_chars: int = 4000) -> str:
        """Fetch a changelog from a URL, returning at most *max_chars* characters."""
        if not url:
            return ""
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "CyberFlash/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read(max_chars + 512).decode(errors="replace")
                return raw[:max_chars]
        except (urllib.error.URLError, OSError) as exc:
            logger.debug("fetch_changelog failed (%s): %s", url, exc)
            return ""
