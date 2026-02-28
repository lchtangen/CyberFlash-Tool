"""rom_discovery_worker.py — Background ROM auto-discovery worker.

Iterates over all provided codenames, fetches ROM releases from every
supported distro via ``RomFeed``, scores each release with
``RomAiScorer``, and upserts results into the ``RomCatalog``.

Signals are emitted so the service / UI layers can stream live progress.
"""

from __future__ import annotations

import logging
from datetime import datetime

from PySide6.QtCore import Signal, Slot

from cyberflash.core.rom_catalog import CatalogEntry, RomCatalog
from cyberflash.core.rom_feed import RomFeed, RomRelease
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class RomDiscoveryWorker(BaseWorker):
    """Scan all ROM feeds for a list of device codenames.

    Signals:
        device_started(codename)        — about to scan a device
        rom_found(codename, entry)      — a scored entry was upserted
        device_complete(codename, count) — scan for one device finished
        discovery_complete(total)       — all devices done; total = catalog count
    """

    device_started = Signal(str)           # codename
    rom_found = Signal(str, object)        # codename, CatalogEntry
    device_complete = Signal(str, int)     # codename, count
    discovery_complete = Signal(int)       # total catalog entries

    def __init__(
        self,
        codenames: list[str],
        scorer: object,                    # RomAiScorer instance
        gemini: object | None = None,      # GeminiClient | None
        max_age_days: int = 0,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)           # type: ignore[arg-type]
        self._codenames = codenames
        self._scorer = scorer
        self._gemini = gemini
        self._max_age_days = max_age_days
        self._aborted = False

    def abort(self) -> None:
        """Request graceful stop after the current release batch."""
        self._aborted = True

    @Slot()
    def start(self) -> None:
        """Entry point: iterates codenames → fetches → scores → emits."""
        RomCatalog.load()
        try:
            self._run()
        except Exception as exc:
            logger.exception("RomDiscoveryWorker unexpected error")
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    def _run(self) -> None:
        for codename in self._codenames:
            if self._aborted:
                break

            self.device_started.emit(codename)
            logger.debug("Discovering ROMs for %s", codename)

            releases: list[RomRelease] = []
            try:
                releases = RomFeed.get_all_releases(codename)
            except Exception as exc:
                logger.warning("RomFeed failed for %s: %s", codename, exc)

            count = 0
            for release in releases:
                if self._aborted:
                    break
                try:
                    score = self._scorer.score_release(release, None, self._gemini)
                    entry = CatalogEntry(
                        codename=codename,
                        distro=str(release.distro),
                        version=release.version,
                        android_ver=release.android_ver,
                        security_patch=release.security_patch,
                        url=release.url,
                        sha256=release.sha256,
                        build_date=release.build_date,
                        size_bytes=release.size_bytes,
                        ai_score=score.score,
                        ai_notes="; ".join(score.notes),
                        download_path="",
                        verified=False,
                        cached_at=datetime.utcnow().isoformat(),
                    )
                    RomCatalog.upsert(entry)
                    self.rom_found.emit(codename, entry)
                    count += 1
                except Exception as exc:
                    logger.warning("Scoring failed for %s/%s: %s", codename, release.url, exc)

            self.device_complete.emit(codename, count)
            logger.debug("Device %s: %d entries found", codename, count)

        # Persist to disk and emit final count
        RomCatalog.save()
        self.discovery_complete.emit(RomCatalog.total_count())
