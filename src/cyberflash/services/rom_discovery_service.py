"""rom_discovery_service.py — Service layer for ROM auto-discovery & downloads.

Owns the ``RomDiscoveryWorker`` thread and all ``DownloadWorker`` threads.
Exposes high-level signals and API methods to the UI layer; the UI never
touches workers directly.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from cyberflash.core.rom_ai_scorer import RomAiScorer
from cyberflash.core.rom_catalog import CatalogEntry, RomCatalog
from cyberflash.profiles import ProfileRegistry
from cyberflash.workers.download_worker import DownloadWorker
from cyberflash.workers.rom_discovery_worker import RomDiscoveryWorker

logger = logging.getLogger(__name__)

_DEFAULT_DOWNLOAD_DIR = Path.home() / "CyberFlash" / "Downloads"


class RomDiscoveryService(QObject):
    """Orchestrates ROM discovery and downloads.

    Discovery signals:
        discovery_started()
        device_discovered(codename, count)
        rom_found(codename, entry)
        discovery_complete(total_count)
        catalog_updated()

    Download signals:
        download_started(url, dest_path)
        download_progress(url, bytes_done, total_bytes)
        download_complete(url, local_path)
        download_failed(url, error_msg)
        download_verified(url, sha_matched)
    """

    # ── Discovery signals ─────────────────────────────────────────────────────
    discovery_started = Signal()
    device_discovered = Signal(str, int)    # codename, count
    rom_found = Signal(str, object)         # codename, CatalogEntry
    discovery_complete = Signal(int)        # total catalog entries
    catalog_updated = Signal()

    # ── Download signals ──────────────────────────────────────────────────────
    download_started = Signal(str, str)     # url, dest_path
    download_progress = Signal(str, int, int)  # url, done, total
    download_complete = Signal(str, str)    # url, local_path
    download_failed = Signal(str, str)      # url, error_msg
    download_verified = Signal(str, bool)   # url, sha_matched

    def __init__(self, ai_service: object | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ai_service = ai_service
        self._scorer = RomAiScorer()
        self._discovery_thread: QThread | None = None
        self._discovery_worker: RomDiscoveryWorker | None = None
        self._active_downloads: dict[str, tuple[DownloadWorker, QThread]] = {}
        self._download_dir = _DEFAULT_DOWNLOAD_DIR

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Load the catalog from disk (no network activity)."""
        RomCatalog.load()
        logger.info("RomDiscoveryService started")

    def stop(self) -> None:
        """Abort any in-progress discovery and all downloads."""
        if self._discovery_worker:
            self._discovery_worker.abort()
        if self._discovery_thread:
            self._discovery_thread.quit()
            self._discovery_thread.wait(5000)

        for url in list(self._active_downloads):
            self.abort_download(url)

        logger.info("RomDiscoveryService stopped")

    # ── Discovery API ─────────────────────────────────────────────────────────

    def discover_all(self) -> None:
        """Start background discovery for all 21 device codenames."""
        self.discover_codenames(ProfileRegistry.list_all())

    def discover_device(self, codename: str) -> None:
        """Start background discovery for a single device."""
        self.discover_codenames([codename])

    def discover_codenames(self, codenames: list[str]) -> None:
        """Start background discovery for *codenames* (replaces current scan)."""
        if self._discovery_thread and self._discovery_thread.isRunning():
            logger.info("Discovery already running; aborting previous scan")
            if self._discovery_worker:
                self._discovery_worker.abort()
            self._discovery_thread.quit()
            self._discovery_thread.wait(5000)

        gemini: object | None = None
        if self._ai_service is not None:
            # Try to access gemini_client property if available
            gemini = getattr(self._ai_service, "gemini_client", None)

        worker = RomDiscoveryWorker(codenames, self._scorer, gemini)
        thread = QThread(self)

        worker.moveToThread(thread)
        thread.started.connect(worker.start)

        worker.device_started.connect(self._on_device_started)
        worker.rom_found.connect(self._on_rom_found)
        worker.device_complete.connect(self._on_device_complete)
        worker.discovery_complete.connect(self._on_discovery_complete)
        worker.error.connect(self._on_worker_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._discovery_thread = thread
        self._discovery_worker = worker
        self.discovery_started.emit()
        thread.start()
        logger.info("Discovery started for %d codenames", len(codenames))

    # ── Catalog API ───────────────────────────────────────────────────────────

    def get_catalog(self, codename: str) -> list[CatalogEntry]:
        return RomCatalog.get_entries(codename)

    def get_all_catalogs(self) -> dict[str, list[CatalogEntry]]:
        return RomCatalog.get_all()

    def get_recommended(self, codename: str) -> CatalogEntry | None:
        entries = RomCatalog.get_entries(codename)
        return self._scorer.recommend_best(entries)  # type: ignore[return-value]

    # ── Download API ──────────────────────────────────────────────────────────

    def set_download_dir(self, path: Path | str) -> None:
        self._download_dir = Path(path)

    def download_entry(self, entry: CatalogEntry, dest_dir: Path | None = None) -> None:
        """Start downloading *entry* to *dest_dir* (default: service download dir)."""
        url = entry.url
        if not url:
            logger.warning("Cannot download entry with no URL")
            return
        if url in self._active_downloads:
            logger.debug("Download already in progress: %s", url)
            return

        target_dir = dest_dir or self._download_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = url.split("/")[-1] or f"{entry.codename}_{entry.distro}.zip"
        dest = target_dir / filename

        worker = DownloadWorker(url, dest, expected_hash=entry.sha256)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)

        worker.progress.connect(
            lambda done, total, u=url: self.download_progress.emit(u, done, total)
        )
        worker.download_complete.connect(
            lambda path, u=url: self._on_download_complete(u, path)
        )
        worker.verified.connect(
            lambda ok, _exp, _act, u=url: self._on_download_verified(u, ok)
        )
        worker.error.connect(
            lambda msg, u=url: self._on_download_error(u, msg)
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._active_downloads[url] = (worker, thread)
        self.download_started.emit(url, str(dest))
        thread.start()
        logger.info("Download started: %s → %s", url, dest)

    def abort_download(self, url: str) -> None:
        """Abort the download for *url* if active."""
        entry = self._active_downloads.pop(url, None)
        if entry:
            worker, thread = entry
            worker.abort()
            thread.quit()
            thread.wait(3000)
            logger.info("Download aborted: %s", url)

    def download_recovery(self, codename: str) -> None:
        """Download the first recovery image listed in the device profile."""
        profile = ProfileRegistry.load(codename)
        if not profile or not profile.recoveries:
            logger.warning("No recoveries in profile for %s", codename)
            return
        recovery = profile.recoveries[0]
        # Recovery entries have a name and filename_pattern but no direct URL
        # in the profile schema — log a hint for future implementation
        logger.info(
            "download_recovery: %s — recovery name=%s, partition=%s "
            "(direct URL not in profile; implement per-distro recovery URLs separately)",
            codename,
            recovery.name,
            recovery.flash_partition,
        )

    @property
    def active_downloads(self) -> dict[str, DownloadWorker]:
        return {url: w for url, (w, _) in self._active_downloads.items()}

    @property
    def is_discovering(self) -> bool:
        return bool(self._discovery_thread and self._discovery_thread.isRunning())

    # ── Worker signal handlers ────────────────────────────────────────────────

    @Slot(str)
    def _on_device_started(self, codename: str) -> None:
        logger.debug("Discovery: scanning %s", codename)

    @Slot(str, object)
    def _on_rom_found(self, codename: str, entry: object) -> None:
        self.rom_found.emit(codename, entry)
        self.catalog_updated.emit()

    @Slot(str, int)
    def _on_device_complete(self, codename: str, count: int) -> None:
        self.device_discovered.emit(codename, count)

    @Slot(int)
    def _on_discovery_complete(self, total: int) -> None:
        self.discovery_complete.emit(total)
        logger.info("Discovery complete: %d total entries in catalog", total)

    @Slot(str)
    def _on_worker_error(self, msg: str) -> None:
        logger.warning("RomDiscoveryWorker error: %s", msg)

    @Slot()
    def _on_thread_finished(self) -> None:
        self._discovery_thread = None
        self._discovery_worker = None

    def _on_download_complete(self, url: str, path: str) -> None:
        self._active_downloads.pop(url, None)
        RomCatalog.mark_downloaded(url, path, verified=False)
        self.download_complete.emit(url, path)

    def _on_download_verified(self, url: str, ok: bool) -> None:
        if ok:
            RomCatalog.mark_downloaded(url, "", verified=True)
        self.download_verified.emit(url, ok)

    def _on_download_error(self, url: str, msg: str) -> None:
        self._active_downloads.pop(url, None)
        self.download_failed.emit(url, msg)
