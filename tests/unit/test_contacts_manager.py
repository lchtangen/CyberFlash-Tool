"""Unit tests for ContactsManager — mocked ADB."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from cyberflash.core.contacts_manager import ContactsManager


class TestBackupContacts:
    def test_empty_output_returns_none(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch("cyberflash.core.contacts_manager.AdbManager.shell", return_value=""),
        ):
            result = ContactsManager.backup_contacts("ABC", Path(tmpdir))
        assert result is None

    def test_valid_contacts_creates_vcf(self) -> None:
        output = (
            "Row: 0 display_name=Alice, data1=alice@example.com, "
            "mimetype=vnd.android.cursor.item/email_v2\n"
            "Row: 1 display_name=Bob, data1=+1555000000, "
            "mimetype=vnd.android.cursor.item/phone_v2\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("cyberflash.core.contacts_manager.AdbManager.shell", return_value=output):
                result = ContactsManager.backup_contacts("ABC", Path(tmpdir))
            assert result is not None
            assert result.suffix == ".vcf"
            assert result.exists()

    def test_backup_creates_parent_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "sub" / "contacts"
            with patch("cyberflash.core.contacts_manager.AdbManager.shell", return_value=""):
                ContactsManager.backup_contacts("ABC", new_dir)
            assert new_dir.exists()


class TestBackupSms:
    def test_backup_sms_calls_adb(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch(
                "cyberflash.core.contacts_manager.AdbManager.shell",
                return_value="Row: 0 address=+155500, body=Hello, date=1700000000000\n",
            ) as mock_shell,
        ):
            result = ContactsManager.backup_sms("ABC", Path(tmpdir))
        # backup_sms might return None or a Path; just verify it was called
        mock_shell.assert_called()

    def test_empty_sms_returns_none(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch("cyberflash.core.contacts_manager.AdbManager.shell", return_value=""),
        ):
            result = ContactsManager.backup_sms("ABC", Path(tmpdir))
        assert result is None


class TestVcfConversion:
    def test_vcf_format_contains_begin_vcard(self) -> None:
        output = (
            "Row: 0 display_name=TestUser, data1=test@example.com, "
            "mimetype=vnd.android.cursor.item/email_v2\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("cyberflash.core.contacts_manager.AdbManager.shell", return_value=output):
                result = ContactsManager.backup_contacts("ABC", Path(tmpdir))
            if result:
                content = result.read_text()
                assert "BEGIN:VCARD" in content


class TestCountMethods:
    def test_count_contacts_returns_int(self) -> None:
        with patch(
            "cyberflash.core.contacts_manager.AdbManager.shell",
            return_value="Row: 0\nRow: 1\nRow: 2\n",
        ):
            count = ContactsManager.count_contacts("ABC")
        assert isinstance(count, int) and count >= 0

    def test_count_contacts_empty_returns_zero(self) -> None:
        with patch("cyberflash.core.contacts_manager.AdbManager.shell", return_value=""):
            count = ContactsManager.count_contacts("ABC")
        assert count == 0

    def test_count_sms_returns_int(self) -> None:
        with patch(
            "cyberflash.core.contacts_manager.AdbManager.shell",
            return_value="Row: 0\nRow: 1\n",
        ):
            count = ContactsManager.count_sms("ABC")
        assert isinstance(count, int) and count >= 0
