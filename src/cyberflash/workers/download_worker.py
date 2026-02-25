"""download_worker.py — Chunked, resumable HTTP/HTTPS download worker.

Features
--------
- Resume support: sends ``Range: bytes=N-`` if the destination file already
  exists and the server supports ``Accept-Ranges``.
- Progress reporting: emits ``progress(bytes_done, total_bytes)`` on every
  chunk so the UI can show a live progress bar and ETA.
- Speed reporting: emits ``speed_update(bytes_per_sec)`` once per second.
- Abort: call ``abort()`` from any thread; the download loop checks the flag
  between chunks and exits cleanly.
- Checksum: if ``expected_hash`` is provided (SHA-256 hex string) the file is
  verified after download; ``verified(bool)`` is emitted on completion.

Usage
-----
    worker = DownloadWorker(url, dest_path)
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.start)
    worker.progress.connect(on_progress)
    worker.download_complete.connect(on_complete)
    worker.finished.connect(thread.quit)
    thread.start()
"""

from __future__ import annotations

import hashlib
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import Signal, Slot

from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)

# Chunk size for streaming reads (512 KiB)
_CHUNK_SIZE = 524_288

# Connection / read timeout in seconds
_TIMEOUT = 30


class DownloadWorker(BaseWorker):
    """Stream a file from *url* to *dest_path* with resume and progress.

    Signals:
        progress(bytes_done, total_bytes): Emitted every chunk. total_bytes is
            -1 when the server does not send Content-Length.
        speed_update(bytes_per_sec): Emitted approximately once per second.
        download_complete(dest_path): Emitted on success with the local path.
        verified(success, expected, actual): Emitted when expected_hash is set.
        error(message): Inherited from BaseWorker.
        finished(): Inherited from BaseWorker — always emitted last.
    """

    progress = Signal(int, int)          # bytes_done, total_bytes (-1 = unknown)
    speed_update = Signal(float)         # bytes per second
    download_complete = Signal(str)      # local file path
    verified = Signal(bool, str, str)    # success, expected_hex, actual_hex

    def __init__(
        self,
        url: str,
        dest_path: str | Path,
        expected_hash: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._dest = Path(dest_path)
        self._expected_hash = expected_hash.lower().strip()
        self._aborted = False

    def abort(self) -> None:
        """Signal the worker to stop after the current chunk."""
        self._aborted = True

    @Slot()
    def start(self) -> None:
        try:
            self._download()
        except Exception as exc:
            logger.exception("Unexpected download error")
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _download(self) -> None:
        self._dest.parent.mkdir(parents=True, exist_ok=True)

        # Determine resume offset
        resume_offset = self._dest.stat().st_size if self._dest.exists() else 0
        request = urllib.request.Request(self._url)
        request.add_header("User-Agent", "CyberFlash/2026")
        if resume_offset:
            request.add_header("Range", f"bytes={resume_offset}-")
            logger.info("Resuming download from byte %d: %s", resume_offset, self._url)
        else:
            logger.info("Starting download: %s → %s", self._url, self._dest)

        try:
            response = urllib.request.urlopen(request, timeout=_TIMEOUT)
        except urllib.error.HTTPError as exc:
            if exc.code == 416:
                # Range not satisfiable — file already complete
                logger.info("File already fully downloaded (416): %s", self._dest)
                self._maybe_verify()
                self.download_complete.emit(str(self._dest))
                return
            raise

        status = response.status
        # 206 = partial content (resume accepted), 200 = full download
        if status not in (200, 206):
            raise RuntimeError(f"Unexpected HTTP status {status} for {self._url}")

        content_length = response.headers.get("Content-Length")
        server_total = int(content_length) if content_length else -1
        total_bytes = (resume_offset + server_total) if server_total >= 0 else -1

        # If server returned 200 for a resumed request, restart from 0
        if status == 200 and resume_offset:
            logger.debug("Server ignored Range header; restarting from 0")
            resume_offset = 0

        mode = "ab" if resume_offset else "wb"
        bytes_done = resume_offset

        speed_window_start = time.monotonic()
        speed_window_bytes = 0

        with self._dest.open(mode) as fout:
            while not self._aborted:
                chunk = response.read(_CHUNK_SIZE)
                if not chunk:
                    break
                fout.write(chunk)
                n = len(chunk)
                bytes_done += n
                speed_window_bytes += n

                self.progress.emit(bytes_done, total_bytes)

                # Emit speed roughly once per second
                elapsed = time.monotonic() - speed_window_start
                if elapsed >= 1.0:
                    self.speed_update.emit(speed_window_bytes / elapsed)
                    speed_window_bytes = 0
                    speed_window_start = time.monotonic()

        if self._aborted:
            logger.info("Download aborted: %s", self._dest)
            self.error.emit("Download aborted by user")
            return

        logger.info("Download complete (%d bytes): %s", bytes_done, self._dest)
        self._maybe_verify()
        self.download_complete.emit(str(self._dest))

    def _maybe_verify(self) -> None:
        if not self._expected_hash:
            return
        actual = self._checksum_sha256(self._dest)
        ok = actual == self._expected_hash
        if ok:
            logger.info("Checksum verified: %s", self._dest.name)
        else:
            logger.warning(
                "Checksum mismatch for %s: expected %s, got %s",
                self._dest.name, self._expected_hash, actual,
            )
        self.verified.emit(ok, self._expected_hash, actual)

    @staticmethod
    def _checksum_sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
        return h.hexdigest()
