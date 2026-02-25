"""Service layer bridging the link-monitor worker with the UI.

:class:`RomLinkService` owns the :class:`LinkMonitorWorker` on a dedicated
:class:`QThread`, exposes a high-level API for adding/removing sources, and
re-emits worker signals on the main thread for safe UI consumption.

Follows the same ownership pattern as :class:`DeviceService`.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, Signal, Slot

from cyberflash.models.rom_source import RomSource, SourceStatus
from cyberflash.workers.link_monitor_worker import LinkMonitorWorker

logger = logging.getLogger(__name__)


class RomLinkService(QObject):
    """Manages ROM source monitoring lifecycle and provides UI-safe signals.

    Signals:
        source_updated(RomSource) — a source's trust/status was recalculated.
        source_flagged(RomSource) — a source was newly flagged as dangerous.
        sweep_completed(int) — a full monitoring sweep finished.
        sources_loaded(int) — initial source list was loaded.
    """

    source_updated = Signal(object)  # RomSource
    source_flagged = Signal(object)  # RomSource
    sweep_completed = Signal(int)
    sources_loaded = Signal(int)

    def __init__(
        self,
        parent: QObject | None = None,
        interval_ms: int = 300_000,
    ) -> None:
        super().__init__(parent)
        self._sources: dict[str, RomSource] = {}  # url → RomSource
        self._thread: QThread | None = None
        self._worker: LinkMonitorWorker | None = None
        self._interval_ms = interval_ms

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spin up the monitor worker on a background thread."""
        self._thread = QThread(self)
        self._worker = LinkMonitorWorker(interval_ms=self._interval_ms)
        self._worker.moveToThread(self._thread)

        # Wire worker signals to service slots (queued by default cross-thread)
        self._thread.started.connect(self._worker.start_monitoring)
        self._worker.source_updated.connect(self._on_source_updated)
        self._worker.source_flagged.connect(self._on_source_flagged)
        self._worker.sweep_completed.connect(self.sweep_completed)
        self._worker.error.connect(self._on_worker_error)

        # Push current sources to the worker
        if self._sources:
            source_list = list(self._sources.values())
            self._worker.set_sources(source_list)

        self._thread.start()
        logger.info("RomLinkService started with %d sources", len(self._sources))

    def stop(self) -> None:
        """Gracefully stop the worker and thread."""
        if self._worker:
            QMetaObject.invokeMethod(
                self._worker, "stop_monitoring", Qt.ConnectionType.QueuedConnection
            )
        if self._thread:
            self._thread.quit()
            self._thread.wait(5000)
        logger.info("RomLinkService stopped")

    # ── Source management (main thread) ───────────────────────────────────────

    def add_source(self, url: str, display_name: str = "") -> RomSource:
        """Add a new ROM source URL to be monitored.

        Returns the created :class:`RomSource` (or existing if duplicate URL).
        """
        if url in self._sources:
            return self._sources[url]

        source = RomSource(url=url, display_name=display_name, is_user_added=True)
        self._sources[url] = source

        # Push to worker if running
        if self._worker:
            QMetaObject.invokeMethod(
                self._worker,
                "add_source",
                Qt.ConnectionType.QueuedConnection,
                source,
            )

        logger.info("Added ROM source: %s (%s)", source.domain, url)
        return source

    def remove_source(self, url: str) -> None:
        """Remove a ROM source from monitoring."""
        self._sources.pop(url, None)
        if self._worker:
            QMetaObject.invokeMethod(
                self._worker,
                "remove_source",
                Qt.ConnectionType.QueuedConnection,
                url,
            )

    def get_sources(
        self,
        *,
        sort_by_trust: bool = True,
        exclude_blocked: bool = False,
    ) -> list[RomSource]:
        """Return current sources, optionally sorted and filtered."""
        sources = list(self._sources.values())

        if exclude_blocked:
            sources = [
                s for s in sources if s.status not in {SourceStatus.BLOCKED, SourceStatus.FLAGGED}
            ]

        if sort_by_trust:
            sources.sort(key=lambda s: s.trust.overall, reverse=True)

        return sources

    def get_source(self, url: str) -> RomSource | None:
        """Look up a single source by URL."""
        return self._sources.get(url)

    @property
    def source_count(self) -> int:
        return len(self._sources)

    @property
    def flagged_count(self) -> int:
        return sum(
            1
            for s in self._sources.values()
            if s.status in {SourceStatus.FLAGGED, SourceStatus.BLOCKED}
        )

    @property
    def healthy_count(self) -> int:
        return sum(
            1
            for s in self._sources.values()
            if s.status in {SourceStatus.VERIFIED, SourceStatus.ACTIVE}
        )

    # ── Persistence ───────────────────────────────────────────────────────────

    def load_sources_from_json(self, path: Path) -> int:
        """Load ROM source URLs from a JSON file.

        Expected format::

            [
                {"url": "https://...", "display_name": "LineageOS"},
                {"url": "https://..."}
            ]

        Returns the number of sources loaded.
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load sources from %s: %s", path, exc)
            return 0

        count = 0
        for entry in data:
            if isinstance(entry, dict) and "url" in entry:
                url = entry["url"]
                name = entry.get("display_name", "")
                if url not in self._sources:
                    self._sources[url] = RomSource(url=url, display_name=name)
                    count += 1

        # Push full list to worker
        if self._worker and count > 0:
            QMetaObject.invokeMethod(
                self._worker,
                "set_sources",
                Qt.ConnectionType.QueuedConnection,
                list(self._sources.values()),
            )

        self.sources_loaded.emit(count)
        logger.info("Loaded %d sources from %s", count, path)
        return count

    def save_sources_to_json(self, path: Path) -> None:
        """Persist current source URLs to a JSON file."""
        data = [
            {
                "url": s.url,
                "display_name": s.display_name,
                "status": s.status.value,
                "trust_overall": round(s.trust.overall, 3),
                "trust_grade": s.trust.grade,
                "check_count": s.check_count,
                "consecutive_failures": s.consecutive_failures,
            }
            for s in self._sources.values()
        ]

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("Saved %d sources to %s", len(data), path)
        except OSError as exc:
            logger.error("Failed to save sources to %s: %s", path, exc)

    # ── Worker signal handlers ────────────────────────────────────────────────

    @Slot(object)
    def _on_source_updated(self, source: RomSource) -> None:
        """Relay worker updates to the main thread."""
        self._sources[source.url] = source
        self.source_updated.emit(source)

    @Slot(object)
    def _on_source_flagged(self, source: RomSource) -> None:
        """Relay flagged-source warnings to the UI."""
        self._sources[source.url] = source
        self.source_flagged.emit(source)

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        logger.error("LinkMonitorWorker error: %s", message)
