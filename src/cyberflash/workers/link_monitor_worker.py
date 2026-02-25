"""QThread-based periodic ROM link monitor worker.

Runs on a dedicated QThread, periodically checking batches of ROM
download links and emitting signals when source trust/status changes.
Follows the same pattern as :class:`DevicePollWorker`.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QTimer, Signal, Slot

from cyberflash.core.link_checker import LinkChecker
from cyberflash.core.source_scorer import SourceScorer
from cyberflash.models.rom_source import RomSource, SourceStatus
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_MS = 300_000  # 5 minutes between full sweeps
_BATCH_SIZE = 5  # Check N sources per tick to avoid flooding


class LinkMonitorWorker(BaseWorker):
    """Periodically checks ROM source links and scores their trust.

    Signals:
        source_updated(RomSource) — emitted when a source's status changes.
        source_flagged(RomSource) — emitted when a source is newly flagged/blocked.
        sweep_completed(int) — emitted after a full sweep; int = number checked.
    """

    source_updated = Signal(object)  # RomSource
    source_flagged = Signal(object)  # RomSource
    sweep_completed = Signal(int)  # number of sources checked

    def __init__(
        self,
        interval_ms: int = _DEFAULT_INTERVAL_MS,
        batch_size: int = _BATCH_SIZE,
    ) -> None:
        super().__init__()
        self._interval_ms = interval_ms
        self._batch_size = batch_size
        self._timer: QTimer | None = None
        self._checker = LinkChecker()
        self._scorer = SourceScorer()
        self._sources: list[RomSource] = []
        self._current_index: int = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @Slot()
    def start_monitoring(self) -> None:
        """Start the periodic check timer. Call from the worker's thread."""
        self._timer = QTimer(self)
        self._timer.setInterval(self._check_interval_ms())
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        logger.info(
            "LinkMonitorWorker started (sweep every %d ms, batch=%d)",
            self._interval_ms,
            self._batch_size,
        )
        # Run an initial tick immediately
        self._tick()

    @Slot()
    def stop_monitoring(self) -> None:
        """Stop the timer and signal finished."""
        if self._timer:
            self._timer.stop()
        self.finished.emit()
        logger.info("LinkMonitorWorker stopped")

    # ── Source management ─────────────────────────────────────────────────────

    @Slot(list)
    def set_sources(self, sources: list[RomSource]) -> None:
        """Replace the entire source list (thread-safe via queued signal)."""
        self._sources = list(sources)
        self._current_index = 0
        logger.info("LinkMonitorWorker: loaded %d sources", len(self._sources))

    @Slot(object)
    def add_source(self, source: RomSource) -> None:
        """Add a single source to the monitoring pool."""
        # Dedup by URL
        for existing in self._sources:
            if existing.url == source.url:
                return
        self._sources.append(source)

    @Slot(str)
    def remove_source(self, url: str) -> None:
        """Remove a source by URL."""
        self._sources = [s for s in self._sources if s.url != url]

    # ── Internal tick ─────────────────────────────────────────────────────────

    @Slot()
    def _tick(self) -> None:
        """Check the next batch of sources."""
        if not self._sources:
            return

        batch = self._get_next_batch()
        for source in batch:
            self._check_single(source)

        # Detect end of sweep
        if self._current_index >= len(self._sources):
            self._current_index = 0
            self.sweep_completed.emit(len(self._sources))
            logger.debug("Sweep completed (%d sources)", len(self._sources))

    def _get_next_batch(self) -> list[RomSource]:
        """Get the next slice of sources to check."""
        end = min(self._current_index + self._batch_size, len(self._sources))
        batch = self._sources[self._current_index : end]
        self._current_index = end
        return batch

    def _check_single(self, source: RomSource) -> None:
        """Run link check + scoring on a single source."""
        old_status = source.status

        try:
            result = self._checker.check(source.url)
            source.record_check(result)
        except Exception as exc:
            logger.warning("Check failed for %s: %s", source.url, exc)
            self.error.emit(f"Check failed for {source.domain}: {exc}")
            return

        try:
            self._scorer.score_and_update(source)
        except Exception as exc:
            logger.warning("Scoring failed for %s: %s", source.url, exc)
            return

        # Emit update signal
        self.source_updated.emit(source)

        # Emit flagged signal on new flags
        if source.status in {SourceStatus.FLAGGED, SourceStatus.BLOCKED} and old_status not in {
            SourceStatus.FLAGGED,
            SourceStatus.BLOCKED,
        }:
            logger.warning("Source flagged: %s — %s", source.domain, source.flagged_reason)
            self.source_flagged.emit(source)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _check_interval_ms(self) -> int:
        """Compute the timer tick interval.

        The timer fires more frequently than the sweep interval so batches
        are spread out evenly across the full sweep period.
        """
        if not self._sources:
            return self._interval_ms

        num_ticks = max(1, len(self._sources) // self._batch_size)
        return max(1000, self._interval_ms // num_ticks)
