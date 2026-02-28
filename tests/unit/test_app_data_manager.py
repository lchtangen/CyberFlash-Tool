"""Unit tests for AppDataManager — mocked ADB."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from cyberflash.core.app_data_manager import AppBackup, AppDataManager


class TestBackupApp:
    def test_returns_app_backup(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch("cyberflash.core.app_data_manager.AdbManager._run", return_value=(0, "", "")),
            patch(
                "cyberflash.core.app_data_manager.AdbManager.shell",
                return_value="versionName=1.2.3",
            ),
        ):
            backup = AppDataManager.backup_app(
                "ABC", "com.example.app", Path(tmpdir), encrypt=False
            )
        assert isinstance(backup, AppBackup)
        assert backup.package == "com.example.app"
        assert backup.version == "1.2.3"

    def test_backup_stored_in_dest_dir(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch("cyberflash.core.app_data_manager.AdbManager._run", return_value=(0, "", "")),
            patch("cyberflash.core.app_data_manager.AdbManager.shell", return_value=""),
        ):
            backup = AppDataManager.backup_app(
                "ABC", "com.example.app", Path(tmpdir), encrypt=False
            )
        assert str(Path(tmpdir)) in str(backup.backup_path)

    def test_unknown_version_fallback(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch("cyberflash.core.app_data_manager.AdbManager._run", return_value=(0, "", "")),
            patch("cyberflash.core.app_data_manager.AdbManager.shell", return_value=""),
        ):
            backup = AppDataManager.backup_app(
                "ABC", "com.example.app", Path(tmpdir), encrypt=False
            )
        assert backup.version == "unknown"


class TestListBackups:
    def test_empty_dir_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backups = AppDataManager.list_backups(Path(tmpdir))
        assert backups == []

    def test_ab_file_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # list_backups scans for .ab and .aes files by filename
            ab_file = Path(tmpdir) / "com.example.app_1700000000.ab"
            ab_file.write_bytes(b"AB backup content")
            backups = AppDataManager.list_backups(Path(tmpdir))
        assert len(backups) == 1
        assert backups[0].package == "com.example.app"


class TestAppBackupSerialization:
    def test_to_dict_roundtrip(self) -> None:
        original = AppBackup(
            package="com.test",
            version="2.0",
            backup_path=Path("/tmp/test.ab"),
            created_at="2026-01-01",
            size_bytes=512,
            encrypted=False,
        )
        d = original.to_dict()
        restored = AppBackup.from_dict(d)
        assert restored.package == original.package
        assert restored.version == original.version
        assert restored.encrypted is False

    def test_from_dict_handles_missing_keys(self) -> None:
        backup = AppBackup.from_dict({})
        assert backup.package == ""
        assert backup.encrypted is False
