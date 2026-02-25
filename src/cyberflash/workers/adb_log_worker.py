"""adb_log_worker.py — Streaming logcat capture via QProcess.

Streams ``adb -s <serial> logcat`` output line-by-line, applying optional
tag / priority filters.  Uses QProcess so that the event loop can stop it
cleanly without blocking the thread.

Filter syntax (``tag_filter`` parameter)
-----------------------------------------
Same as the ``adb logcat`` filter expression, e.g.::

    "*:S MyApp:D OtherTag:V"

An empty string means no filter (show everything).

Priority levels (``min_priority``)
-----------------------------------
V(2) D(3) I(4) W(5) E(6) F(7) S(8)

Usage
-----
    worker = AdbLogWorker(serial)
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.start)
    worker.log_line.connect(on_line)
    worker.finished.connect(thread.quit)
    thread.start()
    ...
    worker.stop()   # call from any thread to request a clean stop
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QProcess, QProcessEnvironment, Signal, Slot

from cyberflash.core.tool_manager import ToolManager
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)

# Priority tag → numeric level
_PRIORITY = {"V": 2, "D": 3, "I": 4, "W": 5, "E": 6, "F": 7, "S": 8}


class AdbLogWorker(BaseWorker):
    """Stream logcat output for a connected device.

    Signals:
        log_line(text): One decoded logcat line.
        error(message): Inherited from BaseWorker.
        finished(): Inherited — always emitted last.
    """

    log_line = Signal(str)

    def __init__(
        self,
        serial: str,
        tag_filter: str = "",
        min_priority: str = "V",
        clear_on_start: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._serial = serial
        self._tag_filter = tag_filter.strip()
        self._min_priority = min_priority.upper()
        self._clear_on_start = clear_on_start
        self._process: QProcess | None = None

    def stop(self) -> None:
        """Request graceful termination (safe to call from any thread)."""
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.terminate()

    @Slot()
    def start(self) -> None:
        try:
            self._run()
        except Exception as exc:
            logger.exception("AdbLogWorker unexpected error")
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        adb = ToolManager.adb_cmd()

        # Optionally clear the logcat buffer first
        if self._clear_on_start:
            clear_proc = QProcess()
            clear_proc.setProcessEnvironment(QProcessEnvironment.systemEnvironment())
            clear_proc.start(adb[0], [*adb[1:], "-s", self._serial, "logcat", "-c"])
            clear_proc.waitForFinished(5000)

        self._process = QProcess()
        self._process.setProcessEnvironment(QProcessEnvironment.systemEnvironment())
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_ready_read)
        self._process.finished.connect(self._on_process_finished)

        args = [*adb[1:], "-s", self._serial, "logcat", "-v", "threadtime"]
        if self._tag_filter:
            args.append(self._tag_filter)

        logger.info("Starting logcat: %s %s", adb[0], " ".join(args))
        self._process.start(adb[0], args)

        if not self._process.waitForStarted(5000):
            self.error.emit(f"Failed to start adb logcat for {self._serial}")
            return

        # Block until the process exits (stop() will terminate it)
        self._process.waitForFinished(-1)

    @Slot()
    def _on_ready_read(self) -> None:
        if self._process is None:
            return
        while self._process.canReadLine():
            raw = self._process.readLine()
            line = bytes(raw).decode("utf-8", errors="replace").rstrip("\r\n")
            if self._passes_filter(line):
                self.log_line.emit(line)

    @Slot(int, QProcess.ExitStatus)
    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if exit_status == QProcess.ExitStatus.CrashExit:
            logger.warning("adb logcat process crashed")
        else:
            logger.info("adb logcat exited with code %d", exit_code)

    def _passes_filter(self, line: str) -> bool:
        """Return True if the line meets the minimum priority requirement."""
        min_level = _PRIORITY.get(self._min_priority, 2)
        if min_level <= 2:
            return True  # V = show everything
        # Standard logcat threadtime format: "MM-DD HH:MM:SS.mmm PID TID PRIORITY TAG: msg"
        parts = line.split(maxsplit=6)
        if len(parts) >= 5:
            priority_char = parts[4][:1].upper()
            level = _PRIORITY.get(priority_char, 2)
            return level >= min_level
        return True
