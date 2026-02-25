from __future__ import annotations

import logging

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.fastboot_manager import FastbootManager

logger = logging.getLogger(__name__)


class PartitionManager:
    """Utilities for querying and managing A/B partition slots."""

    @classmethod
    def get_active_slot(cls, serial: str) -> str:
        """Return the active slot ('a' or 'b').

        Tries fastboot getvar first; falls back to adb getprop.
        Returns "" if slot info is unavailable.
        """
        slot = FastbootManager.get_var(serial, "current-slot").lower().strip()
        if slot in ("a", "b"):
            return slot

        # Fallback: ADB (device may be online, not in fastboot)
        suffix = AdbManager.get_prop(serial, "ro.boot.slot_suffix").strip()
        slot = suffix.lstrip("_").lower()
        if slot in ("a", "b"):
            return slot

        logger.warning("Could not determine active slot for %s", serial)
        return ""

    @classmethod
    def get_inactive_slot(cls, serial: str) -> str:
        """Return the inactive slot (opposite of active)."""
        active = cls.get_active_slot(serial)
        if active == "a":
            return "b"
        if active == "b":
            return "a"
        return ""

    @classmethod
    def set_active_slot(cls, serial: str, slot: str, dry_run: bool = False) -> bool:
        """Set the active slot via fastboot set_active.

        Returns True on success.
        """
        slot = slot.lower()
        if slot not in ("a", "b"):
            logger.error("Invalid slot: %s", slot)
            return False
        if dry_run:
            logger.info("[dry-run] fastboot set_active %s", slot)
            return True
        rc, _, stderr = FastbootManager._run(["-s", serial, "set_active", slot])
        if rc != 0:
            logger.error("set_active %s failed: %s", slot, stderr)
            return False
        return True

    @classmethod
    def get_slot_info(cls, serial: str) -> dict[str, str]:
        """Return a dict of slot-related fastboot variables."""
        keys = ["slot-count", "current-slot", "has-slot:boot", "has-slot:system"]
        result: dict[str, str] = {}
        for key in keys:
            value = FastbootManager.get_var(serial, key)
            if value:
                result[key] = value
        return result
