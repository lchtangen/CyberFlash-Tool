"""BackupWorker — executes ADB backup, restore, and partition dump operations.

Runs in a background QThread — all I/O is off the main thread.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from PySide6.QtCore import Signal, Slot

from cyberflash.core.tool_manager import ToolManager
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class BackupWorker(BaseWorker):
    """Run device backup / restore operations off the main thread.

    Modes:
        ``"adb_backup"``     — ``adb backup -apk -shared -all -f <output_path>``
        ``"adb_restore"``    — ``adb restore <input_path>``
        ``"pull_media"``     — ``adb pull /sdcard/ <dest_dir>``
        ``"partition_dump"`` — ``dd`` each partition via ADB shell or fastboot

    Signals:
        progress(current_bytes, total_bytes)  current=0 if indeterminate
        log_line(text)                        status/progress messages
        backup_complete(output_path)          absolute path of the result
    """

    progress = Signal(int, int)  # current_bytes, total_bytes
    log_line = Signal(str)
    backup_complete = Signal(str)  # output path

    def __init__(
        self,
        serial: str,
        mode: str,
        output_path: str,
        *,
        include_apks: bool = True,
        include_shared: bool = False,
        include_all: bool = True,
        partitions: list[str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._serial = serial
        self._mode = mode
        self._output_path = output_path
        self._include_apks = include_apks
        self._include_shared = include_shared
        self._include_all = include_all
        self._partitions = partitions or []
        self._aborted = False

    @Slot()
    def start(self) -> None:
        try:
            if self._mode == "adb_backup":
                self._run_adb_backup()
            elif self._mode == "adb_restore":
                self._run_adb_restore()
            elif self._mode == "pull_media":
                self._run_pull_media()
            elif self._mode == "partition_dump":
                self._run_partition_dump()
            else:
                self.error.emit(f"Unknown backup mode: {self._mode}")
        except Exception as exc:
            logger.exception("BackupWorker error")
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    def abort(self) -> None:
        """Signal the worker to stop at the next safe opportunity."""
        self._aborted = True

    # ── Private helpers ──────────────────────────────────────────────────────

    def _run_adb_backup(self) -> None:
        adb = ToolManager.adb_cmd()
        out = Path(self._output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        cmd = [*adb, "-s", self._serial, "backup"]
        if self._include_apks:
            cmd.append("-apk")
        if self._include_shared:
            cmd.append("-shared")
        if self._include_all:
            cmd.append("-all")
        cmd += ["-f", str(out)]

        self.log_line.emit(f"Running: {' '.join(cmd)}")
        self.log_line.emit("Waiting for backup confirmation on device…")
        self.progress.emit(0, 0)  # indeterminate

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            if self._aborted:
                proc.terminate()
                self.log_line.emit("Backup aborted by user.")
                self.error.emit("Backup aborted")
                return
            stripped = line.rstrip()
            if stripped:
                self.log_line.emit(stripped)

        proc.wait()
        if proc.returncode != 0:
            self.error.emit(f"adb backup exited with code {proc.returncode}")
            return

        size = out.stat().st_size if out.exists() else 0
        self.log_line.emit(f"Backup saved: {out.name} ({size // 1024} KB)")
        self.progress.emit(1, 1)
        self.backup_complete.emit(str(out))

    def _run_pull_media(self) -> None:
        adb = ToolManager.adb_cmd()
        dest = Path(self._output_path)
        dest.mkdir(parents=True, exist_ok=True)

        cmd = [*adb, "-s", self._serial, "pull", "/sdcard/", str(dest)]
        self.log_line.emit(f"Running: {' '.join(cmd)}")
        self.progress.emit(0, 0)  # indeterminate

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        pulled = 0
        for line in proc.stdout:
            if self._aborted:
                proc.terminate()
                self.log_line.emit("Pull aborted by user.")
                self.error.emit("Pull aborted")
                return
            stripped = line.rstrip()
            if stripped:
                self.log_line.emit(stripped)
                if stripped.startswith("["):
                    pulled += 1
                    if pulled % 50 == 0:
                        self.progress.emit(pulled, 0)

        proc.wait()
        if proc.returncode != 0:
            self.error.emit(f"adb pull exited with code {proc.returncode}")
            return

        self.log_line.emit(f"Media pulled to: {dest}")
        self.progress.emit(1, 1)
        self.backup_complete.emit(str(dest))

    def _run_adb_restore(self) -> None:
        """Restore from an ADB backup archive (.ab file)."""
        adb = ToolManager.adb_cmd()
        src = Path(self._output_path)
        if not src.exists():
            self.error.emit(f"Backup file not found: {src}")
            return

        cmd = [*adb, "-s", self._serial, "restore", str(src)]
        self.log_line.emit(f"Running: {' '.join(cmd)}")
        self.log_line.emit("Confirm restore on device screen\u2026")
        self.progress.emit(0, 0)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            if self._aborted:
                proc.terminate()
                self.log_line.emit("Restore aborted by user.")
                self.error.emit("Restore aborted")
                return
            stripped = line.rstrip()
            if stripped:
                self.log_line.emit(stripped)

        proc.wait()
        if proc.returncode != 0:
            self.error.emit(f"adb restore exited with code {proc.returncode}")
            return

        self.log_line.emit("Restore completed successfully.")
        self.progress.emit(1, 1)
        self.backup_complete.emit(str(src))

    def _run_partition_dump(self) -> None:
        """Dump selected partitions using dd via ADB shell (requires root)."""
        if not self._partitions:
            self.error.emit("No partitions selected for backup")
            return

        adb = ToolManager.adb_cmd()
        dest = Path(self._output_path)
        dest.mkdir(parents=True, exist_ok=True)

        total = len(self._partitions)
        for idx, part_name in enumerate(self._partitions):
            if self._aborted:
                self.log_line.emit("Partition dump aborted by user.")
                self.error.emit("Partition dump aborted")
                return

            self.log_line.emit(f"Dumping partition: {part_name} ({idx + 1}/{total})")
            self.progress.emit(idx, total)

            # Find the block device for this partition
            find_cmd = [
                *adb,
                "-s",
                self._serial,
                "shell",
                f"su -c 'ls -la /dev/block/by-name/{part_name} 2>/dev/null "
                f"|| readlink -f /dev/block/bootdevice/by-name/{part_name} 2>/dev/null'",
            ]
            try:
                result = subprocess.run(
                    find_cmd,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                block_dev = result.stdout.strip().split("\n")[-1].strip()
                if not block_dev or "No such file" in block_dev:
                    block_dev = f"/dev/block/by-name/{part_name}"
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                block_dev = f"/dev/block/by-name/{part_name}"

            out_file = dest / f"{part_name}.img"
            dd_cmd = [
                *adb,
                "-s",
                self._serial,
                "shell",
                f"su -c 'dd if={block_dev} 2>/dev/null'",
            ]
            self.log_line.emit(f"  Reading {block_dev} \u2192 {out_file.name}")

            try:
                with out_file.open("wb") as fh:
                    proc = subprocess.Popen(
                        dd_cmd,
                        stdout=fh,
                        stderr=subprocess.PIPE,
                        text=False,
                    )
                    proc.wait(timeout=300)

                if out_file.exists() and out_file.stat().st_size > 0:
                    sz = out_file.stat().st_size / (1024 * 1024)
                    self.log_line.emit(f"  Saved {part_name}.img ({sz:.1f} MB)")
                else:
                    self.log_line.emit(f"  Warning: {part_name}.img is empty — may need root")
            except subprocess.TimeoutExpired:
                self.log_line.emit(f"  Timeout dumping {part_name}")
            except Exception as exc:
                self.log_line.emit(f"  Error dumping {part_name}: {exc}")

        self.progress.emit(total, total)
        self.log_line.emit(f"Partition dump complete: {dest}")
        self.backup_complete.emit(str(dest))
