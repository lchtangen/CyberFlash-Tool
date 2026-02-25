"""Unit tests for BackupWorker.

subprocess.Popen is mocked so no real ADB / device is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cyberflash.workers.backup_worker import BackupWorker


def _make_popen_mock(stdout_lines: list[str], returncode: int = 0) -> MagicMock:
    """Return a mock Popen object that yields given lines then exits."""
    mock_proc = MagicMock()
    mock_proc.stdout = iter(stdout_lines)
    mock_proc.returncode = returncode
    mock_proc.wait.return_value = returncode
    return mock_proc


# ── adb_backup mode ──────────────────────────────────────────────────────────


class TestAdbBackupMode:
    def test_backup_complete_emitted_on_success(self, tmp_path, qapp) -> None:
        out_file = tmp_path / "backup.ab"
        # Create a dummy file so stat() succeeds
        out_file.write_bytes(b"ANDROID BACKUP")

        completed: list[str] = []
        errors: list[str] = []

        mock_proc = _make_popen_mock(["Backing up...\n", "Done\n"])

        with (
            patch("cyberflash.workers.backup_worker.subprocess.Popen", return_value=mock_proc),
            patch(
                "cyberflash.workers.backup_worker.ToolManager.adb_cmd",
                return_value=["adb"],
            ),
        ):
            worker = BackupWorker("test_serial", "adb_backup", str(out_file))
            worker.backup_complete.connect(completed.append)
            worker.error.connect(errors.append)
            worker.start()

        assert errors == []
        assert len(completed) == 1
        assert completed[0] == str(out_file)

    def test_error_emitted_on_nonzero_exit(self, tmp_path, qapp) -> None:
        out_file = tmp_path / "backup.ab"
        errors: list[str] = []

        mock_proc = _make_popen_mock(["error line\n"], returncode=1)

        with (
            patch("cyberflash.workers.backup_worker.subprocess.Popen", return_value=mock_proc),
            patch(
                "cyberflash.workers.backup_worker.ToolManager.adb_cmd",
                return_value=["adb"],
            ),
        ):
            worker = BackupWorker("test_serial", "adb_backup", str(out_file))
            worker.error.connect(errors.append)
            worker.start()

        assert len(errors) == 1
        assert "1" in errors[0]

    def test_log_lines_emitted(self, tmp_path, qapp) -> None:
        out_file = tmp_path / "backup.ab"
        out_file.write_bytes(b"data")
        lines: list[str] = []

        mock_proc = _make_popen_mock(["line one\n", "line two\n"])

        with (
            patch("cyberflash.workers.backup_worker.subprocess.Popen", return_value=mock_proc),
            patch(
                "cyberflash.workers.backup_worker.ToolManager.adb_cmd",
                return_value=["adb"],
            ),
        ):
            worker = BackupWorker("test_serial", "adb_backup", str(out_file))
            worker.log_line.connect(lines.append)
            worker.start()

        # Should include command line + parsed lines
        assert any("adb" in line for line in lines)

    def test_finished_always_emitted(self, tmp_path, qapp) -> None:
        out_file = tmp_path / "backup.ab"
        finished: list[bool] = []

        mock_proc = _make_popen_mock([], returncode=0)

        with (
            patch("cyberflash.workers.backup_worker.subprocess.Popen", return_value=mock_proc),
            patch(
                "cyberflash.workers.backup_worker.ToolManager.adb_cmd",
                return_value=["adb"],
            ),
        ):
            worker = BackupWorker("test_serial", "adb_backup", str(out_file))
            worker.finished.connect(lambda: finished.append(True))
            worker.start()

        assert finished == [True]


# ── pull_media mode ──────────────────────────────────────────────────────────


class TestPullMediaMode:
    def test_backup_complete_emitted(self, tmp_path, qapp) -> None:
        dest = tmp_path / "media"
        completed: list[str] = []

        mock_proc = _make_popen_mock(["[100%] /sdcard/DCIM/photo.jpg\n"])

        with (
            patch("cyberflash.workers.backup_worker.subprocess.Popen", return_value=mock_proc),
            patch(
                "cyberflash.workers.backup_worker.ToolManager.adb_cmd",
                return_value=["adb"],
            ),
        ):
            worker = BackupWorker("serial", "pull_media", str(dest))
            worker.backup_complete.connect(completed.append)
            worker.start()

        assert len(completed) == 1
        assert completed[0] == str(dest)

    def test_dest_directory_created(self, tmp_path, qapp) -> None:
        dest = tmp_path / "new_subdir" / "media"
        assert not dest.exists()

        mock_proc = _make_popen_mock([])

        with (
            patch("cyberflash.workers.backup_worker.subprocess.Popen", return_value=mock_proc),
            patch(
                "cyberflash.workers.backup_worker.ToolManager.adb_cmd",
                return_value=["adb"],
            ),
        ):
            worker = BackupWorker("serial", "pull_media", str(dest))
            worker.start()

        assert dest.exists()


# ── Unknown mode ─────────────────────────────────────────────────────────────


class TestUnknownMode:
    def test_unknown_mode_emits_error(self, tmp_path, qapp) -> None:
        errors: list[str] = []

        worker = BackupWorker("serial", "unknown_mode", str(tmp_path / "out"))
        worker.error.connect(errors.append)
        worker.start()

        assert len(errors) == 1
        assert "unknown_mode" in errors[0]


# ── Abort ────────────────────────────────────────────────────────────────────


class TestAbort:
    def test_abort_sets_flag(self, tmp_path, qapp) -> None:
        worker = BackupWorker("serial", "adb_backup", str(tmp_path / "out.ab"))
        assert not worker._aborted
        worker.abort()
        assert worker._aborted


# ── adb_restore mode ────────────────────────────────────────────────────────


class TestAdbRestoreMode:
    def test_restore_complete_emitted(self, tmp_path, qapp) -> None:
        src_file = tmp_path / "backup.ab"
        src_file.write_bytes(b"ANDROID BACKUP")
        completed: list[str] = []
        errors: list[str] = []

        mock_proc = _make_popen_mock(["Restoring...\n", "Done\n"])

        with (
            patch("cyberflash.workers.backup_worker.subprocess.Popen", return_value=mock_proc),
            patch(
                "cyberflash.workers.backup_worker.ToolManager.adb_cmd",
                return_value=["adb"],
            ),
        ):
            worker = BackupWorker("serial", "adb_restore", str(src_file))
            worker.backup_complete.connect(completed.append)
            worker.error.connect(errors.append)
            worker.start()

        assert errors == []
        assert len(completed) == 1

    def test_restore_missing_file_emits_error(self, tmp_path, qapp) -> None:
        errors: list[str] = []

        worker = BackupWorker("serial", "adb_restore", str(tmp_path / "missing.ab"))
        worker.error.connect(errors.append)
        worker.start()

        assert len(errors) == 1
        assert "not found" in errors[0].lower()

    def test_restore_error_on_nonzero_exit(self, tmp_path, qapp) -> None:
        src_file = tmp_path / "backup.ab"
        src_file.write_bytes(b"data")
        errors: list[str] = []

        mock_proc = _make_popen_mock(["error\n"], returncode=1)

        with (
            patch("cyberflash.workers.backup_worker.subprocess.Popen", return_value=mock_proc),
            patch(
                "cyberflash.workers.backup_worker.ToolManager.adb_cmd",
                return_value=["adb"],
            ),
        ):
            worker = BackupWorker("serial", "adb_restore", str(src_file))
            worker.error.connect(errors.append)
            worker.start()

        assert len(errors) == 1


# ── partition_dump mode ──────────────────────────────────────────────────────


class TestPartitionDumpMode:
    def test_no_partitions_emits_error(self, tmp_path, qapp) -> None:
        errors: list[str] = []

        worker = BackupWorker("serial", "partition_dump", str(tmp_path / "out"))
        worker.error.connect(errors.append)
        worker.start()

        assert len(errors) == 1
        assert "no partitions" in errors[0].lower()

    def test_partition_dump_creates_dest_dir(self, tmp_path, qapp) -> None:
        dest = tmp_path / "partition_backup"
        assert not dest.exists()

        # Mock both subprocess.run (for finding block device) and Popen (for dd)
        mock_run = MagicMock()
        mock_run.stdout = "/dev/block/by-name/boot\n"

        mock_proc = MagicMock()
        mock_proc.wait.return_value = None

        lines: list[str] = []

        with (
            patch("cyberflash.workers.backup_worker.subprocess.run", return_value=mock_run),
            patch("cyberflash.workers.backup_worker.subprocess.Popen", return_value=mock_proc),
            patch(
                "cyberflash.workers.backup_worker.ToolManager.adb_cmd",
                return_value=["adb"],
            ),
        ):
            worker = BackupWorker("serial", "partition_dump", str(dest), partitions=["boot"])
            worker.log_line.connect(lines.append)
            worker.start()

        assert dest.exists()

    def test_partition_dump_finished_emitted(self, tmp_path, qapp) -> None:
        dest = tmp_path / "dump"
        finished: list[bool] = []

        worker = BackupWorker("serial", "partition_dump", str(dest), partitions=[])
        worker.finished.connect(lambda: finished.append(True))
        worker.start()

        assert finished == [True]
