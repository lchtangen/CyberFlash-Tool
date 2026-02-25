"""contacts_manager.py — Android contacts and SMS backup/restore via ADB.

Uses content provider queries for contacts and adb backup for SMS.
All methods are synchronous and UI-agnostic.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)

# Content provider URIs
_CONTACTS_URI = "content://com.android.contacts/contacts"
_SMS_URI = "content://sms"

# VCF template for a minimal contact entry
_VCF_HEADER = "BEGIN:VCARD\nVERSION:3.0\n"
_VCF_FOOTER = "END:VCARD\n"


class ContactsManager:
    """Classmethod-only contacts and SMS backup/restore utilities."""

    @classmethod
    def backup_contacts(cls, serial: str, dest_dir: Path) -> Path | None:
        """Backup all contacts to a VCF file in *dest_dir*.

        Uses ``adb shell content query`` against the contacts provider.
        Returns the Path of the saved file, or None on error.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        vcf_path = dest_dir / f"contacts_{serial}_{int(time.time())}.vcf"

        # Query contacts
        output = AdbManager.shell(
            serial,
            "content query --uri content://com.android.contacts/data "
            "--projection display_name:data1:mimetype",
            timeout=30,
        )
        if not output.strip():
            logger.warning("contacts_backup: empty output for %s", serial)
            return None

        vcf_lines: list[str] = []
        current: dict[str, str] = {}

        for line in output.splitlines():
            line = line.strip()
            if line.startswith("Row:"):
                if current:
                    vcf_lines.append(cls._dict_to_vcf(current))
                    current = {}
                # Parse fields from "Row: N display_name=..., data1=..., mimetype=..."
                for part in re.split(r",\s*(?=[a-z_]+=)", line[line.index(" ") + 1:]):
                    if "=" in part:
                        k, _, v = part.partition("=")
                        current[k.strip()] = v.strip()

        if current:
            vcf_lines.append(cls._dict_to_vcf(current))

        if not vcf_lines:
            return None

        vcf_content = "".join(vcf_lines)
        vcf_path.write_text(vcf_content, encoding="utf-8")
        return vcf_path

    @classmethod
    def _dict_to_vcf(cls, d: dict[str, str]) -> str:
        """Convert a contacts row dict to a minimal VCF entry."""
        lines = [_VCF_HEADER]
        name = d.get("display_name", "Unknown")
        lines.append(f"FN:{name}\n")
        mimetype = d.get("mimetype", "")
        data1 = d.get("data1", "")
        if data1:
            if "phone" in mimetype:
                lines.append(f"TEL:{data1}\n")
            elif "email" in mimetype:
                lines.append(f"EMAIL:{data1}\n")
        lines.append(_VCF_FOOTER)
        return "".join(lines)

    @classmethod
    def restore_contacts(cls, serial: str, vcf_path: Path) -> int:
        """Import contacts from *vcf_path* via Android intent.

        Returns the number of contacts imported (best-effort count).
        """
        if not vcf_path.exists():
            logger.error("restore_contacts: file not found: %s", vcf_path)
            return 0

        remote_path = f"/sdcard/cyberflash_contacts_{int(time.time())}.vcf"
        if not AdbManager.push(serial, str(vcf_path), remote_path):
            logger.error("restore_contacts: push failed")
            return 0

        # Count VCF entries for reporting
        content = vcf_path.read_text(encoding="utf-8", errors="replace")
        count = content.count("BEGIN:VCARD")

        # Import via implicit intent
        AdbManager.shell(
            serial,
            f"am start -a android.intent.action.VIEW "
            f"-d file://{remote_path} "
            f"-t text/x-vcard",
            timeout=10,
        )
        return count

    @classmethod
    def backup_sms(cls, serial: str, dest_dir: Path) -> Path | None:
        """Backup SMS messages to a JSON file via content query.

        Returns the Path of the saved file, or None on error.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        sms_path = dest_dir / f"sms_{serial}_{int(time.time())}.json"

        output = AdbManager.shell(
            serial,
            "content query --uri content://sms "
            "--projection address:body:date:type",
            timeout=60,
        )
        if not output.strip():
            logger.warning("backup_sms: no SMS data for %s", serial)
            return None

        import json
        messages: list[dict[str, str]] = []
        current: dict[str, str] = {}
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("Row:"):
                if current:
                    messages.append(current)
                    current = {}
                for part in re.split(r",\s*(?=[a-z_]+=)", line[line.index(" ") + 1:]):
                    if "=" in part:
                        k, _, v = part.partition("=")
                        current[k.strip()] = v.strip()
        if current:
            messages.append(current)

        if not messages:
            return None

        sms_path.write_text(json.dumps(messages, indent=2), encoding="utf-8")
        return sms_path

    @classmethod
    def count_contacts(cls, serial: str) -> int:
        """Return the number of contacts on the device."""
        output = AdbManager.shell(
            serial,
            "content query --uri content://com.android.contacts/contacts "
            "--projection _id",
            timeout=15,
        )
        return max(0, output.count("Row:"))

    @classmethod
    def count_sms(cls, serial: str) -> int:
        """Return the number of SMS messages on the device."""
        output = AdbManager.shell(
            serial,
            "content query --uri content://sms --projection _id",
            timeout=15,
        )
        return max(0, output.count("Row:"))
