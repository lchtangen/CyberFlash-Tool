"""hash_worker.py — Background file checksum verification worker.

Supported algorithms: sha256, sha1, md5 (and any other name accepted by
``hashlib.new()``).

Usage
-----
    worker = HashWorker(file_path, expected_hex, algorithm="sha256")
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.start)
    worker.progress.connect(on_progress)
    worker.hash_complete.connect(on_hash)
    worker.verified.connect(on_verified)
    worker.finished.connect(thread.quit)
    thread.start()
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from PySide6.QtCore import Signal, Slot

from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)

# Read block size (256 KiB)
_BLOCK_SIZE = 262_144


class HashWorker(BaseWorker):
    """Compute the checksum of a local file and optionally verify it.

    Signals:
        progress(bytes_done, total_bytes): Emitted after each read block.
        hash_complete(algorithm, hex_digest): Always emitted on success.
        verified(success, expected, actual): Only emitted when expected_hash
            is non-empty.
        error(message): Inherited from BaseWorker.
        finished(): Inherited — always emitted last.
    """

    progress = Signal(int, int)          # bytes_done, total_bytes
    hash_complete = Signal(str, str)     # algorithm, hex_digest
    verified = Signal(bool, str, str)    # success, expected_hex, actual_hex

    def __init__(
        self,
        file_path: str | Path,
        expected_hash: str = "",
        algorithm: str = "sha256",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._path = Path(file_path)
        self._expected = expected_hash.lower().strip()
        self._algorithm = algorithm.lower()

    @Slot()
    def start(self) -> None:
        try:
            self._run()
        except Exception as exc:
            logger.exception("Hash worker error")
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        if not self._path.exists():
            self.error.emit(f"File not found: {self._path}")
            return

        try:
            h = hashlib.new(self._algorithm)
        except ValueError:
            self.error.emit(f"Unknown hash algorithm: {self._algorithm!r}")
            return

        total = self._path.stat().st_size
        done = 0

        logger.info("Hashing %s (%s, %d bytes)", self._path.name, self._algorithm, total)

        with self._path.open("rb") as f:
            for block in iter(lambda: f.read(_BLOCK_SIZE), b""):
                h.update(block)
                done += len(block)
                self.progress.emit(done, total)

        digest = h.hexdigest()
        logger.info("%s(%s) = %s", self._algorithm, self._path.name, digest)
        self.hash_complete.emit(self._algorithm, digest)

        if self._expected:
            ok = digest == self._expected
            if not ok:
                logger.warning(
                    "Checksum mismatch: expected %s, got %s",
                    self._expected, digest,
                )
            self.verified.emit(ok, self._expected, digest)
