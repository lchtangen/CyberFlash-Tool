"""batch_worker.py — Multi-device batch operation worker.

Runs the same operation (flash, backup, root) on multiple devices
simultaneously using per-device QThreads.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

from PySide6.QtCore import QThread, Signal, Slot

from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class BatchTask:
    """A single operation to perform on one device."""

    serial: str
    operation: str          # "flash" | "backup" | "root"
    args: dict[str, object] = field(default_factory=dict)
    status: str = "pending"  # "pending" | "running" | "done" | "failed" | "aborted"
    error: str = ""
    started_at: str = ""
    finished_at: str = ""


@dataclass
class BatchResult:
    """Summary of a completed batch run."""

    tasks: list[BatchTask] = field(default_factory=list)
    succeeded: int = 0
    failed: int = 0
    duration_s: float = 0.0


# ── Per-task inner worker ─────────────────────────────────────────────────────


class _TaskWorker(BaseWorker):
    """Runs a single BatchTask in its own thread."""

    task_result = Signal(str, bool, str)  # serial, success, error

    def __init__(self, task: BatchTask, parent=None) -> None:
        super().__init__(parent)
        self._task = task

    @Slot()
    def start(self) -> None:
        serial = self._task.serial
        try:
            self._task.started_at = datetime.utcnow().isoformat() + "Z"
            self._task.status = "running"
            success = self._execute()
            self._task.status = "done" if success else "failed"
            self._task.finished_at = datetime.utcnow().isoformat() + "Z"
            self.task_result.emit(serial, success, self._task.error)
        except Exception as exc:
            self._task.error = str(exc)
            self._task.status = "failed"
            self._task.finished_at = datetime.utcnow().isoformat() + "Z"
            self.task_result.emit(serial, False, str(exc))
        finally:
            self.finished.emit()

    def _execute(self) -> bool:
        op = self._task.operation
        serial = self._task.serial
        args = self._task.args

        if op == "backup":
            from pathlib import Path

            from cyberflash.core.contacts_manager import ContactsManager
            dest = Path(str(args.get("dest", "/tmp/cyberflash_batch")))
            ContactsManager.backup_contacts(serial, dest)
            return True

        if op == "flash":
            from pathlib import Path

            from cyberflash.core.flash_engine import FlashEngine
            rom = args.get("rom", "")
            if not rom:
                self._task.error = "No ROM specified"
                return False
            engine = FlashEngine(
                serial=serial,
                rom_path=Path(str(rom)),
                dry_run=bool(args.get("dry_run", False)),
            )
            return engine.run()

        if op == "root":
            from cyberflash.core.root_manager import RootManager
            RootManager.detect_root_state(serial)
            return True

        self._task.error = f"Unknown operation: {op}"
        return False


# ── Main batch worker ─────────────────────────────────────────────────────────


class BatchWorker(BaseWorker):
    """Run an operation on multiple devices simultaneously.

    Spawns one QThread per task and collects results.
    """

    task_started  = Signal(str)          # serial
    task_done     = Signal(str, bool)    # serial, success
    batch_complete = Signal(object)      # BatchResult

    def __init__(self, tasks: list[BatchTask], parent=None) -> None:
        super().__init__(parent)
        self._tasks = tasks
        self._abort_serials: set[str] = set()
        self._threads: dict[str, QThread] = {}
        self._workers: dict[str, _TaskWorker] = {}
        self._results: dict[str, bool] = {}

    @Slot()
    def start(self) -> None:
        t0 = time.monotonic()
        try:
            self._run_all()
        except Exception as exc:
            logger.exception("BatchWorker error")
            self.error.emit(str(exc))
        finally:
            elapsed = time.monotonic() - t0
            succeeded = sum(1 for v in self._results.values() if v)
            failed = sum(1 for v in self._results.values() if not v)
            result = BatchResult(
                tasks=self._tasks,
                succeeded=succeeded,
                failed=failed,
                duration_s=round(elapsed, 2),
            )
            self.batch_complete.emit(result)
            self.finished.emit()

    def _run_all(self) -> None:
        """Spawn per-task threads and wait for all to finish."""
        for task in self._tasks:
            if task.serial in self._abort_serials:
                task.status = "aborted"
                self._results[task.serial] = False
                continue

            self.task_started.emit(task.serial)
            thread = QThread()
            worker = _TaskWorker(task)
            worker.moveToThread(thread)
            thread.started.connect(worker.start)
            worker.finished.connect(thread.quit)
            worker.task_result.connect(
                lambda s, ok, _err, serial=task.serial: self._on_task_done(s, ok)
            )

            self._threads[task.serial] = thread
            self._workers[task.serial] = worker
            thread.start()

        # Wait for all threads
        for _serial, thread in self._threads.items():
            thread.wait(30_000)  # max 30s per device

    def _on_task_done(self, serial: str, success: bool) -> None:
        self._results[serial] = success
        self.task_done.emit(serial, success)

    def abort_device(self, serial: str) -> None:
        """Mark a device for abort; running tasks cannot be recalled."""
        self._abort_serials.add(serial)
        # Signal the worker if it has started
        worker = self._workers.get(serial)
        if worker:
            worker.error.emit(f"Aborted by user: {serial}")
