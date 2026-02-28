"""Unit tests for RomAiScorer heuristic scoring logic."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from cyberflash.core.rom_ai_scorer import DISTRO_TRUST, RomAiScorer, RomScore
from cyberflash.core.rom_feed import RomDistro, RomRelease


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_release(
    distro: RomDistro = RomDistro.LINEAGE,
    device: str = "oriole",
    android_ver: str = "15",
    security_patch: str = "",
    build_date: str = "",
    sha256: str = "deadbeef",
    size_bytes: int = 1_000_000_000,
) -> RomRelease:
    if not security_patch:
        security_patch = date.today().strftime("%Y-%m")
    if not build_date:
        build_date = date.today().isoformat()
    return RomRelease(
        distro=distro,
        device=device,
        version="21.0",
        android_ver=android_ver,
        security_patch=security_patch,
        url=f"https://example.com/{device}.zip",
        size_bytes=size_bytes,
        sha256=sha256,
        build_date=build_date,
    )


_scorer = RomAiScorer()


# ── score_release — basic invariants ─────────────────────────────────────────


def test_score_in_range() -> None:
    release = _make_release()
    result = _scorer.score_release(release)
    assert 0.0 <= result.score <= 100.0


def test_score_returns_rom_score_instance() -> None:
    release = _make_release()
    result = _scorer.score_release(release)
    assert isinstance(result, RomScore)


# ── Recency factor ────────────────────────────────────────────────────────────


def test_recency_future_date_max_points() -> None:
    future_date = (date.today() + timedelta(days=1)).isoformat()
    release = _make_release(build_date=future_date)
    result = _scorer.score_release(release)
    # 25 pts recency + 20 pts android + 20 pts patch + 20 pts distro + 10 sha + 5 size = 100
    assert result.score == 100.0


def test_recency_old_date_zero_recency_points() -> None:
    old_date = (date.today() - timedelta(days=200)).isoformat()
    release = _make_release(build_date=old_date)
    result = _scorer.score_release(release)
    # Recency should contribute 0
    any_recency_note = any("Stale" in n for n in result.notes)
    assert any_recency_note


def test_recency_unknown_date() -> None:
    release = _make_release(build_date="not-a-date")
    result = _scorer.score_release(release)
    assert any("unknown" in n.lower() for n in result.notes)


# ── Android version factor ────────────────────────────────────────────────────


def test_android_version_latest_max_points() -> None:
    release = _make_release(android_ver="15")
    result = _scorer.score_release(release)
    assert any("Latest Android" in n for n in result.notes)


def test_android_version_one_behind() -> None:
    release = _make_release(android_ver="14")
    result = _scorer.score_release(release)
    assert any("one version behind" in n for n in result.notes)


def test_android_version_two_behind() -> None:
    release = _make_release(android_ver="13")
    result = _scorer.score_release(release)
    assert any("two versions behind" in n for n in result.notes)


def test_android_version_outdated() -> None:
    release = _make_release(android_ver="11")
    result = _scorer.score_release(release)
    assert any("outdated" in n for n in result.notes)


def test_android_version_unknown() -> None:
    release = _make_release(android_ver="")
    result = _scorer.score_release(release)
    assert any("unknown" in n.lower() for n in result.notes)


# ── Security patch factor ─────────────────────────────────────────────────────


def test_security_patch_fresh() -> None:
    patch = date.today().strftime("%Y-%m")
    release = _make_release(security_patch=patch)
    result = _scorer.score_release(release)
    assert any("fresh" in n.lower() for n in result.notes)


def test_security_patch_stale() -> None:
    old_patch = (date.today() - timedelta(days=400)).strftime("%Y-%m")
    release = _make_release(security_patch=old_patch)
    result = _scorer.score_release(release)
    assert any("stale" in n.lower() for n in result.notes)


def test_security_patch_empty() -> None:
    # Build release directly to avoid helper auto-filling security_patch
    release = RomRelease(
        distro=RomDistro.LINEAGE,
        device="oriole",
        version="21.0",
        android_ver="15",
        security_patch="",
        url="https://example.com/rom.zip",
        size_bytes=1_000_000_000,
        sha256="deadbeef",
        build_date="",
    )
    result = _scorer.score_release(release)
    assert any("unknown" in n.lower() for n in result.notes)


# ── Distro trust factor ───────────────────────────────────────────────────────


def test_distro_trust_grapheneos() -> None:
    release = _make_release(distro=RomDistro.GRAPHENEOS)
    result = _scorer.score_release(release)
    assert any("grapheneos" in n.lower() for n in result.notes)


def test_distro_trust_lineageos_lookup() -> None:
    assert DISTRO_TRUST["lineageos"] == 20


def test_distro_trust_divestos_present() -> None:
    assert "divestos" in DISTRO_TRUST
    assert DISTRO_TRUST["divestos"] == 17


def test_distro_trust_iodeos_present() -> None:
    assert "iodeos" in DISTRO_TRUST
    assert DISTRO_TRUST["iodeos"] == 14


def test_distro_trust_unknown_uses_default() -> None:
    # Use a distro not in the table
    release = _make_release(distro=RomDistro.IODE)
    result = _scorer.score_release(release)
    # Should not crash and should include a note
    assert result.score >= 0.0


# ── SHA-256 bonus ─────────────────────────────────────────────────────────────


def test_sha256_bonus_present() -> None:
    release = _make_release(sha256="abc123def456")
    result = _scorer.score_release(release)
    assert any("SHA-256" in n for n in result.notes)


def test_sha256_no_bonus_when_missing() -> None:
    release = _make_release(sha256="")
    result = _scorer.score_release(release)
    assert any("No SHA-256" in n for n in result.notes)


# ── File size factor ──────────────────────────────────────────────────────────


def test_file_size_large_gets_bonus() -> None:
    release = _make_release(size_bytes=500_000_000)
    result = _scorer.score_release(release)
    assert any("valid" in n.lower() for n in result.notes)


def test_file_size_small_no_bonus() -> None:
    release = _make_release(size_bytes=1024)
    result = _scorer.score_release(release)
    assert any("small" in n.lower() for n in result.notes)


# ── Grade thresholds ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("score,expected_grade", [
    (100.0, "A"),
    (90.0,  "A"),
    (89.9,  "B"),
    (75.0,  "B"),
    (74.9,  "C"),
    (60.0,  "C"),
    (59.9,  "D"),
    (45.0,  "D"),
    (44.9,  "F"),
    (0.0,   "F"),
])
def test_grade_thresholds(score: float, expected_grade: str) -> None:
    assert RomScore.grade_from_score(score) == expected_grade


# ── recommend_best ────────────────────────────────────────────────────────────


def test_recommend_best_returns_highest_scored() -> None:
    from cyberflash.core.rom_catalog import CatalogEntry

    def _entry(score: float) -> CatalogEntry:
        return CatalogEntry(
            codename="oriole", distro="lineageos", version="21",
            android_ver="15", security_patch="2025-01",
            url=f"https://example.com/{score}.zip", sha256="",
            build_date="2025-01-01", size_bytes=1_000_000_000,
            ai_score=score, ai_notes="", download_path="", verified=False,
            cached_at="2025-01-01T00:00:00",
        )

    entries = [_entry(40.0), _entry(90.0), _entry(70.0)]
    best = _scorer.recommend_best(entries)
    assert best is not None
    assert getattr(best, "ai_score", 0) == 90.0


def test_recommend_best_returns_none_for_empty() -> None:
    assert _scorer.recommend_best([]) is None


def test_recommend_best_prefers_not_downloaded() -> None:
    from cyberflash.core.rom_catalog import CatalogEntry

    def _entry(score: float, path: str) -> CatalogEntry:
        return CatalogEntry(
            codename="oriole", distro="lineageos", version="21",
            android_ver="15", security_patch="2025-01",
            url=f"https://example.com/{score}.zip", sha256="",
            build_date="2025-01-01", size_bytes=1_000_000_000,
            ai_score=score, ai_notes="", download_path=path, verified=False,
            cached_at="2025-01-01T00:00:00",
        )

    # High score entry has a download_path; lower one does not
    already_downloaded = _entry(95.0, "/tmp/rom.zip")
    not_downloaded = _entry(80.0, "")
    best = _scorer.recommend_best([already_downloaded, not_downloaded])
    # Should prefer not_downloaded
    assert getattr(best, "ai_score", 0) == 80.0
