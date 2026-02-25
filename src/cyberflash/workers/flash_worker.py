from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PySide6.QtCore import Signal, Slot

from cyberflash.core.flash_engine import FlashEngine
from cyberflash.models.flash_task import FlashStep, FlashTask, StepStatus
from cyberflash.models.profile import DeviceProfile
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class FlashWorker(BaseWorker):
    """Background worker that executes a FlashTask using FlashEngine.

    Use the moveToThread pattern — never instantiate QThread here.

    Signals:
        step_started(step_id)           — emitted when a step begins
        step_completed(step_id)         — emitted on step success
        step_failed(step_id, message)   — emitted on step failure
        log_line(text)                  — each log message from FlashEngine
        progress(current, total)        — step index progress
        flash_complete()                — all steps finished successfully
    """

    step_started = Signal(str)  # step.id
    step_completed = Signal(str)  # step.id
    step_failed = Signal(str, str)  # step.id, error_message
    log_line = Signal(str)  # raw log text
    progress = Signal(int, int)  # current_index, total
    flash_complete = Signal()

    def __init__(self, task: FlashTask, profile: DeviceProfile) -> None:
        super().__init__()
        self._task = task
        self._profile = profile

    @Slot()
    def start(self) -> None:
        """Execute all steps in the task sequentially."""
        task = self._task
        engine = FlashEngine(task.device_serial, log_cb=self._on_log)
        total = len(task.steps)

        self._on_log(
            f"Starting {'DRY RUN' if task.dry_run else 'flash'} for "
            f"{task.profile_codename} on {task.device_serial}"
        )

        for idx, step in enumerate(task.steps):
            task.current_step_index = idx
            step.status = StepStatus.ACTIVE
            self.step_started.emit(step.id)
            self.progress.emit(idx, total)

            ok = self._execute_step(engine, step, task)

            if ok:
                step.status = StepStatus.COMPLETED
                self.step_completed.emit(step.id)
            else:
                step.status = StepStatus.FAILED
                reason = f"Step '{step.label}' failed"
                self.step_failed.emit(step.id, reason)

                if not step.skippable:
                    task.failed_reason = reason
                    self.error.emit(reason)
                    self.finished.emit()
                    return

        self.progress.emit(total, total)
        self._on_log("Flash completed successfully.")
        self.flash_complete.emit()
        self.finished.emit()

    def _execute_step(self, engine: FlashEngine, step: FlashStep, task: FlashTask) -> bool:
        """Dispatch a step to the corresponding FlashEngine method."""
        dry = task.dry_run
        sid = step.id

        if sid == "reboot_bootloader":
            return engine.reboot_to_bootloader(dry_run=dry)
        if sid == "unlock_bootloader":
            return engine.unlock_bootloader(self._profile, dry_run=dry)
        if sid == "disable_vbmeta":
            return engine.disable_vbmeta_verification(
                self._profile.flash.vbmeta_disable_flags, dry_run=dry
            )
        if sid == "extract_payload":
            return self._do_extract_payload(engine, step, task)
        if sid.startswith("erase_"):
            partition = sid[len("erase_") :]
            return engine.wipe_partition(partition, dry_run=dry)
        if sid == "erase_userdata":
            return engine.wipe_partition("userdata", dry_run=dry)
        if sid.startswith("flash_"):
            partition = sid[len("flash_") :]
            # image path is stored in step metadata if present
            img_path = getattr(step, "_image_path", None)
            if img_path is None:
                self._on_log(f"No image path for step {sid} — skipping")
                return step.skippable
            return engine.flash_partition(partition, img_path, dry_run=dry)
        if sid == "wipe_dalvik":
            return engine.wipe_dalvik_cache(dry_run=dry)
        if sid.startswith("wipe_"):
            partition = sid[len("wipe_") :]
            return engine.wipe_partition(partition, dry_run=dry)
        if sid == "set_active_slot":
            slot = getattr(step, "_target_slot", "b")
            return engine.switch_slot(slot, dry_run=dry)
        if sid == "reboot_system":
            return engine.reboot_to_system(dry_run=dry)

        self._on_log(f"Unknown step id: {sid} — skipping")
        return True

    def _do_extract_payload(self, engine: FlashEngine, step: FlashStep, task: FlashTask) -> bool:
        """Extract partition images from payload.bin / OTA zip.

        Discovers ALL partitions inside the payload and extracts every one
        that has a corresponding ``flash_*`` step.  After extraction, wires
        ``_image_path`` onto each matching step so the flash dispatch finds it.
        """
        source: Path | None = getattr(step, "_source_path", None)
        if source is None:
            self._on_log("No source path for payload extraction — skipping")
            return False

        # Discover which partitions the subsequent flash steps actually need
        needed: list[str] = [s.id[len("flash_") :] for s in task.steps if s.id.startswith("flash_")]
        self._on_log(f"Partitions to extract: {needed}")

        # Create a temp directory for extracted images
        extract_dir = Path(tempfile.mkdtemp(prefix="cyberflash_extract_"))
        self._on_log(f"Extraction directory: {extract_dir}")

        extracted = engine.extract_payload(source, extract_dir, needed, dry_run=task.dry_run)

        if not extracted and not task.dry_run:
            self._on_log("CRITICAL: No partitions could be extracted from payload")
            return False

        # Wire up extracted image paths to subsequent flash_* steps
        for subsequent_step in task.steps:
            if subsequent_step.id.startswith("flash_"):
                partition = subsequent_step.id[len("flash_") :]
                if partition in extracted:
                    subsequent_step._image_path = extracted[partition]  # type: ignore[attr-defined]
                elif task.dry_run:
                    subsequent_step._image_path = extract_dir / f"{partition}.img"  # type: ignore[attr-defined]

        self._on_log(f"Payload extraction complete: {len(extracted)} images ready")
        return True

    def _on_log(self, line: str) -> None:
        self._task.log_lines.append(line)
        self.log_line.emit(line)
