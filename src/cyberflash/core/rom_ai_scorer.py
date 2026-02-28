"""rom_ai_scorer.py - AI-powered ROM release scoring.

Scores each ``RomRelease`` on five local heuristic factors (0-100 pts total)
and optionally uses Gemini to generate a human-readable notes string.

Scoring breakdown:
    Factor 1 - Build recency vs today           0-25 pts
    Factor 2 - Android version freshness        0-20 pts
    Factor 3 - Security patch recency           0-20 pts
    Factor 4 - Distro trust weight              0-20 pts
    Factor 5 - SHA-256 checksum provided         0-10 pts
    Factor 6 - File size sanity (>100 MB)         0-5 pts
    Total max = 100 pts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from cyberflash.core.rom_feed import RomRelease

logger = logging.getLogger(__name__)

# ── Distro trust weights (0-20) ───────────────────────────────────────────────

DISTRO_TRUST: dict[str, int] = {
    "grapheneos":       20,
    "calyxos":          18,
    "lineageos":        20,
    "pixelexperience":  18,
    "crdroid":          16,
    "evolutionx":       14,
    "nameless":         12,
    "efoundation":      14,
    "divestos":         17,
    "iodeos":           14,
}

# Latest known stable Android version (update as new releases land)
_LATEST_ANDROID_VER: int = 15

# How many days before a build is considered stale
_STALE_DAYS: int = 90


# ── Output dataclass ─────────────────────────────────────────────────────────


@dataclass
class RomScore:
    """AI scoring result for a single ROM release."""

    score: float           # 0-100 composite
    grade: str             # A / B / C / D / F
    notes: list[str] = field(default_factory=list)  # human-readable factors
    recommended: bool = False

    @staticmethod
    def grade_from_score(score: float) -> str:
        if score >= 90:
            return "A"
        if score >= 75:
            return "B"
        if score >= 60:
            return "C"
        if score >= 45:
            return "D"
        return "F"


# ── Scorer ────────────────────────────────────────────────────────────────────


class RomAiScorer:
    """Score a ``RomRelease`` using local heuristics + optional Gemini notes."""

    def score_release(
        self,
        release: RomRelease,
        profile: object | None = None,
        gemini: object | None = None,
    ) -> RomScore:
        """Return a ``RomScore`` for *release*.

        *profile* and *gemini* are unused by the heuristic engine but are
        accepted for API compatibility (Gemini notes path is optional).
        """
        notes: list[str] = []
        total: float = 0.0

        # ── Factor 1: Build recency (0-25 pts) ───────────────────────────────
        pts_recency = self._score_recency(release.build_date, notes)
        total += pts_recency

        # ── Factor 2: Android version freshness (0-20 pts) ───────────────────
        pts_android = self._score_android_ver(release.android_ver, notes)
        total += pts_android

        # ── Factor 3: Security patch recency (0-20 pts) ──────────────────────
        pts_patch = self._score_security_patch(release.security_patch, notes)
        total += pts_patch

        # ── Factor 4: Distro trust (0-20 pts) ────────────────────────────────
        pts_distro = self._score_distro(str(release.distro), notes)
        total += pts_distro

        # ── Factor 5: SHA-256 provided (0-10 pts) ────────────────────────────
        if release.sha256:
            notes.append("SHA-256 checksum provided")
            total += 10
        else:
            notes.append("No SHA-256 checksum")

        # ── Factor 6: File size sanity (0-5 pts) ─────────────────────────────
        if release.size_bytes >= 100 * 1024 * 1024:  # ≥ 100 MB
            notes.append("File size looks valid (≥100 MB)")
            total += 5
        else:
            notes.append("File size unknown or suspiciously small")

        score = min(100.0, max(0.0, total))
        grade = RomScore.grade_from_score(score)

        # ── Optional: Gemini notes (score not changed) ────────────────────────
        if gemini is not None:
            try:
                prompt = (
                    f"Summarise this Android ROM release in one sentence for a "
                    f"power user: distro={release.distro}, "
                    f"device={release.device}, version={release.version}, "
                    f"android_ver={release.android_ver}, "
                    f"security_patch={release.security_patch}, "
                    f"build_date={release.build_date}, score={score:.0f}/100."
                )
                gemini_note: str = gemini.chat(prompt, device_context="", page="rom_catalog")
                if gemini_note:
                    notes.insert(0, f"AI: {gemini_note[:120]}")
            except Exception as exc:
                logger.debug("Gemini note generation skipped: %s", exc)

        return RomScore(score=score, grade=grade, notes=notes)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _score_recency(self, build_date: str, notes: list[str]) -> float:
        """Score build recency: fresh = 25 pts, stale/unknown = 0."""
        try:
            parsed = _parse_date(build_date)
        except Exception:
            parsed = None

        if parsed is None:
            notes.append("Build date unknown")
            return 0.0

        delta = (date.today() - parsed).days
        if delta < 0:
            delta = 0

        if delta <= 30:
            pts = 25.0
            notes.append(f"Very recent build ({delta} days ago)")
        elif delta <= 60:
            pts = 20.0
            notes.append(f"Recent build ({delta} days ago)")
        elif delta <= 90:
            pts = 15.0
            notes.append(f"Moderately recent build ({delta} days ago)")
        elif delta <= 180:
            pts = 8.0
            notes.append(f"Older build ({delta} days ago)")
        else:
            pts = 0.0
            notes.append(f"Stale build ({delta} days ago)")

        return pts

    def _score_android_ver(self, android_ver: str, notes: list[str]) -> float:
        """Score Android version freshness: latest = 20 pts."""
        try:
            # Accept "14", "14.0", "android-14" etc.
            ver_str = android_ver.strip().removeprefix("android-").split(".")[0]
            ver = int(ver_str)
        except (ValueError, AttributeError):
            notes.append("Android version unknown")
            return 0.0

        diff = _LATEST_ANDROID_VER - ver
        if diff <= 0:
            pts = 20.0
            notes.append(f"Latest Android {ver}")
        elif diff == 1:
            pts = 14.0
            notes.append(f"Android {ver} (one version behind)")
        elif diff == 2:
            pts = 7.0
            notes.append(f"Android {ver} (two versions behind)")
        else:
            pts = 0.0
            notes.append(f"Android {ver} (outdated)")

        return pts

    def _score_security_patch(self, security_patch: str, notes: list[str]) -> float:
        """Score security patch recency: fresh = 20 pts."""
        if not security_patch:
            notes.append("Security patch level unknown")
            return 0.0

        try:
            # Formats: "2024-12", "2024-12-01", "202412"
            sp = security_patch.strip()
            if len(sp) >= 7 and sp[4] == "-":
                year, month = int(sp[:4]), int(sp[5:7])
            elif len(sp) >= 6:
                year, month = int(sp[:4]), int(sp[4:6])
            else:
                raise ValueError("unparseable")

            patch_date = date(year, month, 1)
            delta_days = (date.today() - patch_date).days

            if delta_days < 0:
                delta_days = 0

            if delta_days <= 30:
                pts = 20.0
                notes.append("Security patch very fresh (≤30 days)")
            elif delta_days <= 90:
                pts = 15.0
                notes.append(f"Security patch recent ({delta_days} days old)")
            elif delta_days <= 180:
                pts = 8.0
                notes.append(f"Security patch aging ({delta_days} days old)")
            else:
                pts = 0.0
                notes.append(f"Security patch stale ({delta_days} days old)")

            return pts

        except Exception:
            notes.append("Security patch level unreadable")
            return 0.0

    def _score_distro(self, distro: str, notes: list[str]) -> float:
        """Score distro trust from DISTRO_TRUST lookup table."""
        key = distro.lower().replace("-", "").replace("_", "")
        # Try direct match first, then prefix match
        pts_int = DISTRO_TRUST.get(key)
        if pts_int is None:
            for trust_key, trust_pts in DISTRO_TRUST.items():
                if trust_key in key or key in trust_key:
                    pts_int = trust_pts
                    break
        if pts_int is None:
            pts_int = 8  # unknown but present
            notes.append(f"Distro '{distro}' (trust: unknown, using default)")
        else:
            notes.append(f"Distro trust: {distro} ({pts_int}/20)")

        return float(pts_int)

    # ── Recommendation helper ─────────────────────────────────────────────────

    def recommend_best(
        self,
        entries: list[object],  # list[CatalogEntry]
        device: object | None = None,
    ) -> object | None:
        """Return the best-scoring CatalogEntry for a device.

        Prefers not-yet-downloaded entries; falls back to any entry.
        """
        if not entries:
            return None

        sorted_entries = sorted(entries, key=lambda e: getattr(e, "ai_score", 0), reverse=True)

        # Prefer not-yet-downloaded
        for entry in sorted_entries:
            if not getattr(entry, "download_path", ""):
                return entry

        return sorted_entries[0]


# ── Date parsing helper ───────────────────────────────────────────────────────


def _parse_date(build_date: str) -> date | None:
    """Parse a build_date string into a :class:`date`, or return None."""
    if not build_date:
        return None

    candidates: list[tuple[str, int]] = [
        ("%Y-%m-%dT%H:%M:%SZ", 20),
        ("%Y-%m-%dT%H:%M:%S", 19),
        ("%Y-%m-%d",           10),
        ("%Y%m%d_%H%M%S",      15),
        ("%Y%m%d",              8),
    ]
    for fmt, width in candidates:
        try:
            return datetime.strptime(build_date[:width], fmt).date()
        except (ValueError, TypeError):
            continue
    return None
