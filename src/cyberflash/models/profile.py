from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EdlConfig:
    vid: str = "05C6"
    pid: str = "9008"
    programmer_filename: str = ""  # e.g. "prog_ufs_firehose_sm8150.elf"
    msm_package_url: str = ""  # doc URL for downloading MSM package
    edl_entry_methods: list[str] = field(default_factory=list)
    # human-readable list of how to enter EDL on this specific device


@dataclass
class BootloaderConfig:
    unlock_command: str  # e.g. "fastboot oem unlock"
    requires_oem_unlock_menu: bool
    warn_data_wipe: bool


@dataclass
class RecoveryEntry:
    name: str  # e.g. "OrangeFox"
    filename_pattern: str  # glob pattern for image file
    flash_partition: str  # e.g. "recovery"


@dataclass
class FlashConfig:
    method: str  # "fastboot" | "sideload"
    partitions: list[str]  # ordered list to flash
    vbmeta_partition: str = "vbmeta"
    vbmeta_disable_flags: str = "--disable-verity --disable-verification"
    erase_partitions: list[str] = field(default_factory=list)
    # Partitions safe to erase in a clean-slate without bricking.
    # If empty, defaults to the high-level entries from `partitions`.
    # NEVER include low-level firmware (xbl, abl, tz, hyp) — erasing
    # those removes fastboot access and causes a HARD BRICK.


@dataclass
class DeviceProfile:
    codename: str
    name: str
    brand: str
    model: str
    ab_slots: bool
    bootloader: BootloaderConfig
    flash: FlashConfig
    wipe_partitions: dict[str, str | None]  # label → fastboot partition or None (adb)
    recoveries: list[RecoveryEntry] = field(default_factory=list)
    chipset: str = ""
    notes: str = ""
    edl: EdlConfig | None = None
