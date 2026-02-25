from __future__ import annotations

import json
import logging
from pathlib import Path

from cyberflash.models.profile import (
    BootloaderConfig,
    DeviceProfile,
    EdlConfig,
    FlashConfig,
    RecoveryEntry,
)

logger = logging.getLogger(__name__)

# Resolve the profiles directory relative to this package's location.
# Going up: profiles → cyberflash → src → project root → resources/profiles
_PACKAGE_DIR = Path(__file__).parent
_PROJECT_ROOT = _PACKAGE_DIR.parents[2]
_PROFILES_DIR = _PROJECT_ROOT / "resources" / "profiles"


def _parse_profile(data: dict) -> DeviceProfile:
    bl_data = data["bootloader"]
    bootloader = BootloaderConfig(
        unlock_command=bl_data["unlock_command"],
        requires_oem_unlock_menu=bl_data["requires_oem_unlock_menu"],
        warn_data_wipe=bl_data["warn_data_wipe"],
    )

    fl_data = data["flash"]
    flash = FlashConfig(
        method=fl_data["method"],
        partitions=fl_data["partitions"],
        vbmeta_partition=fl_data.get("vbmeta_partition", "vbmeta"),
        vbmeta_disable_flags=fl_data.get(
            "vbmeta_disable_flags", "--disable-verity --disable-verification"
        ),
    )

    recoveries = [
        RecoveryEntry(
            name=r["name"],
            filename_pattern=r["filename_pattern"],
            flash_partition=r["flash_partition"],
        )
        for r in data.get("recoveries", [])
    ]

    edl_data = data.get("edl")
    edl = None
    if edl_data:
        edl = EdlConfig(
            vid=edl_data.get("vid", "05C6"),
            pid=edl_data.get("pid", "9008"),
            programmer_filename=edl_data.get("programmer_filename", ""),
            msm_package_url=edl_data.get("msm_package_url", ""),
            edl_entry_methods=edl_data.get("edl_entry_methods", []),
        )

    return DeviceProfile(
        codename=data["codename"],
        name=data["name"],
        brand=data["brand"],
        model=data["model"],
        ab_slots=data["ab_slots"],
        bootloader=bootloader,
        flash=flash,
        wipe_partitions=data.get("wipe_partitions", {}),
        recoveries=recoveries,
        chipset=data.get("chipset", ""),
        notes=data.get("notes", ""),
        edl=edl,
    )


class ProfileRegistry:
    """Loads device profiles from resources/profiles/**/{codename}.json."""

    @classmethod
    def load(cls, codename: str) -> DeviceProfile | None:
        """Return a DeviceProfile for the given codename, or None if not found."""
        for path in _PROFILES_DIR.rglob("*.json"):
            if path.stem == codename and path.name != "schema.json":
                try:
                    with path.open(encoding="utf-8") as f:
                        data = json.load(f)
                    return _parse_profile(data)
                except Exception as exc:
                    logger.error("Failed to load profile %s: %s", path, exc)
                    return None
        logger.debug("No profile found for codename: %s", codename)
        return None

    @classmethod
    def list_all(cls) -> list[str]:
        """Return all available codenames by scanning the profiles directory."""
        codenames: list[str] = []
        for path in _PROFILES_DIR.rglob("*.json"):
            if path.stem != "schema":
                codenames.append(path.stem)
        return sorted(codenames)
