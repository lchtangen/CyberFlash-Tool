"""Unit tests for RomDiscoveryWorker signals, abort, and catalog integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import cyberflash.core.rom_catalog as _catalog_module
from cyberflash.core.rom_ai_scorer import RomAiScorer, RomScore
from cyberflash.core.rom_catalog import CatalogEntry, RomCatalog
from cyberflash.core.rom_feed import RomDistro, RomRelease
from cyberflash.workers.rom_discovery_worker import RomDiscoveryWorker


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect catalog path and reset class state before each test."""
    catalog_path = tmp_path / "rom_catalog.json"
    monkeypatch.setattr(_catalog_module, "_CATALOG_PATH", catalog_path)
    RomCatalog._entries = {}
    RomCatalog._loaded = False


def _fake_release(codename: str, idx: int) -> RomRelease:
    return RomRelease(
        distro=RomDistro.LINEAGE,
        device=codename,
        version=f"21.{idx}",
        android_ver="15",
        security_patch="2025-01",
        url=f"https://example.com/{codename}_{idx}.zip",
        size_bytes=1_200_000_000,
        sha256="deadbeef",
        build_date="2025-01-15",
    )


def _fake_score(*args, **kwargs) -> RomScore:  # noqa: ANN002, ANN003
    return RomScore(score=80.0, grade="B", notes=["Test"])


def _make_worker(codenames: list[str]) -> tuple[RomDiscoveryWorker, MagicMock]:
    scorer = MagicMock(spec=RomAiScorer)
    scorer.score_release.side_effect = _fake_score
    worker = RomDiscoveryWorker(codenames=codenames, scorer=scorer)
    return worker, scorer


# ── Tests — call worker.start() directly in the test thread ──────────────────
# Running start() in-thread means all Qt signals are direct connections and
# are dispatched synchronously, so no event-loop / QThread.wait() needed.


def test_device_started_emitted_per_codename(qapp) -> None:  # noqa: ANN001
    codenames = ["oriole", "husky"]
    fake_releases = {c: [_fake_release(c, 0), _fake_release(c, 1)] for c in codenames}

    started: list[str] = []
    worker, _ = _make_worker(codenames)
    worker.device_started.connect(started.append)

    with patch(
        "cyberflash.workers.rom_discovery_worker.RomFeed.get_all_releases",
        side_effect=lambda c: fake_releases.get(c, []),
    ):
        worker.start()

    assert set(started) == set(codenames)


def test_rom_found_emitted_per_release(qapp) -> None:  # noqa: ANN001
    codenames = ["oriole"]
    fake_releases = {"oriole": [_fake_release("oriole", 0), _fake_release("oriole", 1)]}

    found: list[tuple[str, object]] = []
    worker, _ = _make_worker(codenames)
    worker.rom_found.connect(lambda cod, entry: found.append((cod, entry)))

    with patch(
        "cyberflash.workers.rom_discovery_worker.RomFeed.get_all_releases",
        side_effect=lambda c: fake_releases.get(c, []),
    ):
        worker.start()

    assert len(found) == 2
    assert all(cod == "oriole" for cod, _ in found)
    assert all(isinstance(entry, CatalogEntry) for _, entry in found)


def test_device_complete_count_matches_releases(qapp) -> None:  # noqa: ANN001
    codenames = ["oriole", "husky"]
    fake_releases = {
        "oriole": [_fake_release("oriole", i) for i in range(3)],
        "husky":  [_fake_release("husky", i) for i in range(2)],
    }

    complete_counts: dict[str, int] = {}
    worker, _ = _make_worker(codenames)
    worker.device_complete.connect(lambda cod, count: complete_counts.update({cod: count}))

    with patch(
        "cyberflash.workers.rom_discovery_worker.RomFeed.get_all_releases",
        side_effect=lambda c: fake_releases.get(c, []),
    ):
        worker.start()

    assert complete_counts["oriole"] == 3
    assert complete_counts["husky"] == 2


def test_discovery_complete_total_count(qapp) -> None:  # noqa: ANN001
    codenames = ["oriole", "husky"]
    fake_releases = {
        "oriole": [_fake_release("oriole", i) for i in range(2)],
        "husky":  [_fake_release("husky", i) for i in range(1)],
    }

    totals: list[int] = []
    worker, _ = _make_worker(codenames)
    worker.discovery_complete.connect(totals.append)

    with patch(
        "cyberflash.workers.rom_discovery_worker.RomFeed.get_all_releases",
        side_effect=lambda c: fake_releases.get(c, []),
    ):
        worker.start()

    assert totals == [3]  # 2 + 1


def test_abort_stops_loop_early(qapp) -> None:  # noqa: ANN001
    codenames = [f"device_{i}" for i in range(10)]
    fake_releases = {c: [_fake_release(c, 0)] for c in codenames}

    started: list[str] = []
    worker, _ = _make_worker(codenames)

    def _on_started(codename: str) -> None:
        started.append(codename)
        worker.abort()

    worker.device_started.connect(_on_started)

    with patch(
        "cyberflash.workers.rom_discovery_worker.RomFeed.get_all_releases",
        side_effect=lambda c: fake_releases.get(c, []),
    ):
        worker.start()

    # After abort on the first device_started, loop should stop
    assert len(started) < len(codenames)


def test_catalog_contains_upserted_entries_after_run(qapp) -> None:  # noqa: ANN001
    codenames = ["oriole"]
    fake_releases = {"oriole": [_fake_release("oriole", 0), _fake_release("oriole", 1)]}

    worker, _ = _make_worker(codenames)

    with patch(
        "cyberflash.workers.rom_discovery_worker.RomFeed.get_all_releases",
        side_effect=lambda c: fake_releases.get(c, []),
    ):
        worker.start()

    # Reload from disk to verify persistence
    RomCatalog._loaded = False
    RomCatalog.load()
    entries = RomCatalog.get_entries("oriole")
    assert len(entries) == 2
    assert all(e.ai_score == 80.0 for e in entries)
