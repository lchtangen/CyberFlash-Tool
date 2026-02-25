from __future__ import annotations

import logging
import re

from PySide6.QtCore import Signal, Slot

from cyberflash.core.edl_engine import EdlEngine
from cyberflash.core.edl_manager import EdlManager
from cyberflash.models.edl_task import EdlTask
from cyberflash.models.profile import DeviceProfile
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)

# Regex patterns to extract progress hints from bkerler/edl output
_PARTITION_PATTERN = re.compile(r"(?:Writing|Flashing|Sending)\s+(\S+)", re.IGNORECASE)
_PROGRESS_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)", re.IGNORECASE)


class EdlWorker(BaseWorker):
    """Runs the full automated EDL restore in a background thread.

    Automated steps (shown in StepTracker, no user action needed):
      1. Verify EDL device still present
      2. Send firehose programmer to device (Sahara) + flash all partitions via rawprogram.xml
      3. Reboot to system
    All steps execute automatically — one call to EdlEngine.flash_with_rawprogram()
    drives steps 2-3 internally via bkerler/edl.
    """

    step_started = Signal(str)       # step label
    step_completed = Signal(str)     # step label
    step_failed = Signal(str, str)   # step label, error message
    log_line = Signal(str)           # raw log text
    progress = Signal(int, int)      # current, total
    rescue_complete = Signal()

    _STEPS = [
        "verify_device",
        "flash_restore",
        "reboot",
    ]

    def __init__(self, task: EdlTask, profile: DeviceProfile) -> None:
        super().__init__()
        self._task = task
        self._profile = profile
        self._total_partitions = 0
        self._current_partition = 0

    @Slot()
    def start(self) -> None:
        """Execute the automated EDL rescue."""
        task = self._task
        self._on_log(
            f"Starting {'DRY RUN' if task.dry_run else 'EDL rescue'} for "
            f"{task.profile_codename} on {task.device_serial}"
        )

        # Step 1: Verify device is still present
        self.step_started.emit("verify_device")
        self.progress.emit(0, len(self._STEPS))
        if not self._verify_device():
            reason = "EDL device not detected — ensure device is in EDL mode and connected"
            self.step_failed.emit("verify_device", reason)
            self.error.emit(reason)
            self.finished.emit()
            return
        self.step_completed.emit("verify_device")
        self.progress.emit(1, len(self._STEPS))

        # Step 2: Full automated restore (programmer + all partitions + patches)
        self.step_started.emit("flash_restore")
        engine = EdlEngine(task.device_serial, log_cb=self._on_log)

        ok = engine.flash_with_rawprogram(
            programmer=task.programmer,
            rawprogram_xml=task.rawprogram_xml,
            patch_xml=task.patch_xml,
            package_dir=task.package_dir,
            dry_run=task.dry_run,
        )

        if not ok:
            reason = "EDL restore failed — check log for details"
            self.step_failed.emit("flash_restore", reason)
            self.error.emit(reason)
            self.finished.emit()
            return

        self.step_completed.emit("flash_restore")
        self.progress.emit(2, len(self._STEPS))

        # Step 3: Reboot (handled by edl internally, but mark as complete)
        self.step_started.emit("reboot")
        self._on_log("Device rebooting to system…")
        self.step_completed.emit("reboot")
        self.progress.emit(3, len(self._STEPS))

        self._on_log("EDL rescue completed successfully.")
        self.rescue_complete.emit()
        self.finished.emit()

    def _verify_device(self) -> bool:
        """Check the EDL device is still present (or skip in dry run)."""
        if self._task.dry_run:
            self._on_log("[dry-run] Skipping device presence check")
            return True
        devices = EdlManager.list_edl_devices()
        if devices:
            self._on_log(f"EDL device confirmed: {devices[0]}")
            return True
        self._on_log("No EDL device found")
        return False

    def _on_log(self, line: str) -> None:
        self._task.log_lines.append(line)
        self.log_line.emit(line)
        self._parse_progress(line)

    def _parse_progress(self, line: str) -> None:
        """Parse edl output for partition progress hints."""
        # Look for "X / Y" style progress
        m = _PROGRESS_PATTERN.search(line)
        if m:
            try:
                current = int(m.group(1))
                total = int(m.group(2))
                if total > 0:
                    self.progress.emit(current, total)
                    return
            except ValueError:
                pass
