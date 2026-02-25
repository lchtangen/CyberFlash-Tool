from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class DeviceState(StrEnum):
    ONLINE = "device"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"
    RECOVERY = "recovery"
    SIDELOAD = "sideload"
    FASTBOOT = "fastboot"
    FASTBOOTD = "fastbootd"
    UNKNOWN = "unknown"
    EDL = "edl"  # Qualcomm Emergency Download mode (VID 05C6, PID 9008)
    DISCONNECTED = "disconnected"  # No USB connection detected

    @property
    def label(self) -> str:
        return {
            DeviceState.ONLINE: "Online",
            DeviceState.OFFLINE: "Offline",
            DeviceState.UNAUTHORIZED: "Unauthorized",
            DeviceState.RECOVERY: "Recovery",
            DeviceState.SIDELOAD: "Sideload",
            DeviceState.FASTBOOT: "Fastboot",
            DeviceState.FASTBOOTD: "FastbootD",
            DeviceState.UNKNOWN: "Unknown",
            DeviceState.EDL: "EDL (Emergency)",
            DeviceState.DISCONNECTED: "Disconnected",
        }[self]

    @property
    def badge_variant(self) -> str:
        return {
            DeviceState.ONLINE: "success",
            DeviceState.OFFLINE: "neutral",
            DeviceState.UNAUTHORIZED: "warning",
            DeviceState.RECOVERY: "info",
            DeviceState.SIDELOAD: "info",
            DeviceState.FASTBOOT: "warning",
            DeviceState.FASTBOOTD: "warning",
            DeviceState.UNKNOWN: "neutral",
            DeviceState.EDL: "error",
            DeviceState.DISCONNECTED: "neutral",
        }[self]


@dataclass
class DeviceInfo:
    serial: str
    state: DeviceState

    # Basic identity (populated after ADB connection)
    model: str = ""
    brand: str = ""
    codename: str = ""  # ro.product.device
    android_version: str = ""  # ro.build.version.release
    sdk_version: str = ""  # ro.build.version.sdk
    build_number: str = ""  # ro.build.display.id

    # Partition / slot info
    active_slot: str = ""  # "a" or "b" — empty if non-A/B
    has_ab_slots: bool = False

    # Security state (None = unknown)
    bootloader_unlocked: bool | None = None
    is_rooted: bool | None = None

    # Runtime
    battery_level: int = -1  # -1 = unknown

    # Raw fastboot vars (populated for fastboot devices)
    fastboot_vars: dict[str, str] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        if self.brand and self.model:
            return f"{self.brand} {self.model}"
        return self.model or self.serial

    @property
    def is_adb_device(self) -> bool:
        return self.state in (
            DeviceState.ONLINE,
            DeviceState.RECOVERY,
            DeviceState.SIDELOAD,
            DeviceState.UNAUTHORIZED,
        )

    @property
    def is_fastboot_device(self) -> bool:
        return self.state in (DeviceState.FASTBOOT, DeviceState.FASTBOOTD)

    @property
    def bootloader_label(self) -> str:
        if self.bootloader_unlocked is True:
            return "Unlocked"
        if self.bootloader_unlocked is False:
            return "Locked"
        return "Unknown"

    @property
    def slot_label(self) -> str:
        if not self.has_ab_slots:
            return "N/A"
        return f"Slot {self.active_slot.upper()}" if self.active_slot else "A/B"
