"""gsi_checker.py — Project Treble / GSI compatibility checker.

Detects whether a device supports GSI flashing by reading system properties
via ADB, and recommends the correct GSI type.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)

# ── Known GSI project download pages ─────────────────────────────────────────

_GSI_PROJECTS: dict[str, str] = {
    "Generic System Image (AOSP)":
        "https://developer.android.com/topic/generic-system-image",
    "phhusson/treble_experimentations":
        "https://github.com/phhusson/treble_experimentations/releases",
    "AndyYan/GSI (Evolution X GSI)":
        "https://github.com/AndyYan/GSI/releases",
    "lineageos4microg (Lineage GSI)":
        "https://github.com/lineageos4microg/docker-lineage-cicd",
}


# ── Enums ────────────────────────────────────────────────────────────────────


class GsiType(StrEnum):
    ARM64_AB = "arm64-ab"
    ARM64_A_ONLY = "arm64-a-only"
    ARM_AB = "arm-ab"
    X86_64_AB = "x86_64-ab"
    UNKNOWN = "unknown"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class GsiCompatibility:
    """GSI compatibility results for a single device."""

    device_codename: str
    treble_enabled: bool
    vndk_version: str
    dynamic_partitions: bool
    recommended_gsi_type: GsiType
    warnings: list[str] = field(default_factory=list)


# ── Main class ────────────────────────────────────────────────────────────────


class GsiChecker:
    """Classmethod-only GSI compatibility checker."""

    # Prop names
    _PROP_TREBLE      = "ro.treble.enabled"
    _PROP_VNDK        = "ro.vndk.version"
    _PROP_DYNAMIC     = "ro.boot.dynamic_partitions"
    _PROP_ABI         = "ro.product.cpu.abi"
    _PROP_AB_UPDATE   = "ro.build.ab_update"

    @classmethod
    def check_device(cls, serial: str) -> GsiCompatibility:
        """Query device props via ADB and compute GSI compatibility."""
        props = AdbManager.get_props_batch(serial, [
            cls._PROP_TREBLE,
            cls._PROP_VNDK,
            cls._PROP_DYNAMIC,
            cls._PROP_ABI,
            cls._PROP_AB_UPDATE,
        ])

        treble_enabled = props.get(cls._PROP_TREBLE, "").lower() == "true"
        vndk_version = props.get(cls._PROP_VNDK, "").strip()
        dynamic_partitions = props.get(cls._PROP_DYNAMIC, "").lower() == "true"
        abi = props.get(cls._PROP_ABI, "").lower()
        ab_update = props.get(cls._PROP_AB_UPDATE, "").lower() == "true"

        warnings: list[str] = []
        if not treble_enabled:
            warnings.append("Project Treble not enabled — GSI may not boot")
        if not vndk_version:
            warnings.append("VNDK version unknown — compatibility uncertain")
        if not dynamic_partitions:
            warnings.append("Dynamic partitions not detected — may need resize")

        gsi_type = cls._determine_type(abi, ab_update)
        return GsiCompatibility(
            device_codename=AdbManager.get_prop(serial, "ro.product.device"),
            treble_enabled=treble_enabled,
            vndk_version=vndk_version,
            dynamic_partitions=dynamic_partitions,
            recommended_gsi_type=gsi_type,
            warnings=warnings,
        )

    @classmethod
    def _determine_type(cls, abi: str, ab_update: bool) -> GsiType:
        """Map ABI + A/B flag to the recommended GsiType."""
        if "x86_64" in abi:
            return GsiType.X86_64_AB if ab_update else GsiType.UNKNOWN
        if "arm64" in abi:
            return GsiType.ARM64_AB if ab_update else GsiType.ARM64_A_ONLY
        if "armeabi" in abi or "arm" in abi:
            return GsiType.ARM_AB if ab_update else GsiType.UNKNOWN
        return GsiType.UNKNOWN

    @classmethod
    def recommend_gsi_type(cls, compat: GsiCompatibility) -> GsiType:
        """Return the recommended GSI type from a GsiCompatibility object."""
        return compat.recommended_gsi_type

    @classmethod
    def list_compatible_gsis(cls, compat: GsiCompatibility) -> list[str]:
        """Return names of known GSI projects compatible with *compat*."""
        if not compat.treble_enabled:
            return []
        return list(_GSI_PROJECTS.keys())
