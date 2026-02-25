"""xiaomi_manager.py — Xiaomi / Redmi / POCO fastboot flash engine.

Covers:
  - Bootloader unlock guidance (Mi Unlock protocol notes + fastboot OEM unlock)
  - MIUI / HyperOS fastboot flash from tgz firmware packages
  - Xiaomi fastboot flash image selection (partition map)
  - Anti-rollback level detection

All methods are synchronous and must be called from worker threads.

Usage::

    info = XiaomiManager.get_device_info(serial)
    XiaomiManager.flash_firmware(serial, firmware_dir, dry_run=False)
"""

from __future__ import annotations

import logging
import tarfile
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.fastboot_manager import FastbootManager

logger = logging.getLogger(__name__)

# ── Partition maps ─────────────────────────────────────────────────────────────

# Partitions flashed from Xiaomi fastboot packages (MIUI / HyperOS)
# Order matters — boot partitions flashed last for safety
_XIAOMI_PARTITION_MAP: list[tuple[str, str]] = [
    # (image_stem_pattern, fastboot_partition)
    ("cust",            "cust"),
    ("system_ext",      "system_ext"),
    ("system",          "system"),
    ("product",         "product"),
    ("vendor",          "vendor"),
    ("odm",             "odm"),
    ("dtbo",            "dtbo"),
    ("vbmeta",          "vbmeta"),
    ("vbmeta_system",   "vbmeta_system"),
    ("vbmeta_vendor",   "vbmeta_vendor"),
    ("super",           "super"),
    ("recovery",        "recovery"),
    ("boot",            "boot"),
    ("init_boot",       "init_boot"),
    ("vendor_boot",     "vendor_boot"),
    ("xbl",             "xbl"),
    ("xbl_config",      "xbl_config"),
    ("abl",             "abl"),
    ("tz",              "tz"),
    ("hyp",             "hyp"),
    ("keymaster",       "keymaster"),
    ("modem",           "modem"),
    ("bluetooth",       "bluetooth"),
    ("dsp",             "dsp"),
    ("devcfg",          "devcfg"),
    ("shrm",            "shrm"),
    ("storsec",         "storsec"),
]

# Props used to identify Xiaomi / Redmi / POCO devices
_XIAOMI_BRANDS = {"xiaomi", "redmi", "poco", "blackshark"}


# ── Enums ─────────────────────────────────────────────────────────────────────


class XiaomiUnlockStatus(StrEnum):
    LOCKED              = "locked"
    UNLOCKED            = "unlocked"
    UNKNOWN             = "unknown"


class XiaomiFlashMethod(StrEnum):
    FASTBOOT_ROM        = "fastboot_rom"   # Full ROM tgz via fastboot
    FASTBOOT_PARTITION  = "fastboot_part"  # Individual partition images
    EDL                 = "edl"            # Emergency Download Mode (9008)


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class XiaomiDeviceInfo:
    """Xiaomi-specific device metadata."""

    serial:          str
    codename:        str = ""
    brand:           str = ""
    model:           str = ""
    miui_version:    str = ""
    android_version: str = ""
    bl_status:       XiaomiUnlockStatus = XiaomiUnlockStatus.UNKNOWN
    anti_rollback:   int = -1
    region:          str = ""    # CN / EEA / GLOBAL / IN
    is_xiaomi:       bool = False


@dataclass
class XiaomiFlashResult:
    """Result of a Xiaomi firmware flash step."""

    success:   bool
    partition: str
    image:     str
    stderr:    str = ""
    skipped:   bool = False


@dataclass
class XiaomiFirmwareManifest:
    """Contents of a Xiaomi fastboot ROM package."""

    root_dir:        Path
    found_images:    list[tuple[str, Path]] = field(default_factory=list)  # (partition, path)
    miui_version:    str = ""
    codename:        str = ""
    has_super:       bool = False


# ── XiaomiManager ─────────────────────────────────────────────────────────────


class XiaomiManager:
    """Orchestrates Xiaomi / MIUI / HyperOS fastboot operations.

    All classmethods; no instance state required.
    """

    # ── Device identification ─────────────────────────────────────────────────

    @classmethod
    def is_xiaomi_device(cls, serial: str) -> bool:
        """Return True if the connected ADB device is a Xiaomi/Redmi/POCO."""
        brand = AdbManager.shell(
            serial, "getprop ro.product.brand 2>/dev/null", timeout=5
        ).strip().lower()
        return brand in _XIAOMI_BRANDS

    @classmethod
    def get_device_info(cls, serial: str) -> XiaomiDeviceInfo:
        """Return Xiaomi-specific device metadata via ADB.

        Args:
            serial: ADB device serial.

        Returns:
            XiaomiDeviceInfo populated from ``getprop`` calls.
        """
        def prop(key: str) -> str:
            return AdbManager.shell(
                serial, f"getprop {key} 2>/dev/null", timeout=5
            ).strip()

        brand    = prop("ro.product.brand").lower()
        codename = prop("ro.product.device")
        model    = prop("ro.product.model")
        miui_ver = prop("ro.miui.ui.version.name") or prop("ro.build.version.incremental")
        android  = prop("ro.build.version.release")
        region   = prop("ro.miui.region") or prop("ro.product.locale.region") or ""

        # Anti-rollback level (MIUI security)
        arb_raw  = prop("ro.boot.anti_rollback_count")
        try:
            anti_rb = int(arb_raw)
        except (ValueError, TypeError):
            anti_rb = -1

        # BL unlock status (available in fastboot; fallback via prop)
        bl_prop  = prop("ro.secureboot.lockstate").lower()
        if bl_prop == "unlocked":
            bl_status = XiaomiUnlockStatus.UNLOCKED
        elif bl_prop == "locked":
            bl_status = XiaomiUnlockStatus.LOCKED
        else:
            bl_status = XiaomiUnlockStatus.UNKNOWN

        logger.info("Xiaomi device: %s %s (%s) MIUI %s ARB %d",
                    brand, model, codename, miui_ver, anti_rb)

        return XiaomiDeviceInfo(
            serial=serial,
            codename=codename,
            brand=brand,
            model=model,
            miui_version=miui_ver,
            android_version=android,
            bl_status=bl_status,
            anti_rollback=anti_rb,
            region=region.upper(),
            is_xiaomi=brand in _XIAOMI_BRANDS,
        )

    @classmethod
    def get_fastboot_device_info(cls, serial: str) -> dict[str, str]:
        """Return fastboot variables for a device in fastboot mode.

        Returns a dict of variable → value pairs from ``fastboot getvar all``.
        """
        _, out, stderr = FastbootManager._run(
            ["-s", serial, "getvar", "all"], timeout=15
        )
        # fastboot getvar all writes to stderr on some versions
        raw = out + stderr
        result: dict[str, str] = {}
        for line in raw.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                result[k.strip().lower()] = v.strip()
        logger.debug("fastboot getvar: %d entries for %s", len(result), serial)
        return result

    # ── Bootloader unlock ─────────────────────────────────────────────────────

    @classmethod
    def get_unlock_status(cls, serial: str) -> XiaomiUnlockStatus:
        """Return bootloader lock status via fastboot (device must be in fastboot)."""
        _, out, stderr = FastbootManager._run(
            ["-s", serial, "getvar", "unlocked"], timeout=10
        )
        raw = (out + stderr).lower()
        if "unlocked: yes" in raw or "unlocked: true" in raw:
            return XiaomiUnlockStatus.UNLOCKED
        if "unlocked: no" in raw or "unlocked: false" in raw:
            return XiaomiUnlockStatus.LOCKED
        return XiaomiUnlockStatus.UNKNOWN

    @classmethod
    def oem_unlock(cls, serial: str, dry_run: bool = False) -> bool:
        """Issue ``fastboot oem unlock`` for older Xiaomi devices.

        Newer devices require Mi Unlock app + account binding (7/30-day wait).
        This command only works on devices that support legacy OEM unlock.

        Returns:
            True if the command succeeded (rc == 0).
        """
        if dry_run:
            logger.info("[dry-run] fastboot -s %s oem unlock", serial)
            return True

        logger.warning("Issuing OEM unlock — device data will be wiped")
        rc, _, stderr = FastbootManager._run(
            ["-s", serial, "oem", "unlock"], timeout=60
        )
        ok = rc == 0
        if not ok:
            logger.error("oem unlock failed: %s", stderr.strip())
        return ok

    @classmethod
    def flashing_unlock(cls, serial: str, dry_run: bool = False) -> bool:
        """Issue ``fastboot flashing unlock`` for A/B Xiaomi devices.

        Returns:
            True on success.
        """
        if dry_run:
            logger.info("[dry-run] fastboot -s %s flashing unlock", serial)
            return True

        logger.warning("Issuing flashing unlock — device data will be wiped")
        rc, _, stderr = FastbootManager._run(
            ["-s", serial, "flashing", "unlock"], timeout=60
        )
        ok = rc == 0
        if not ok:
            logger.error("flashing unlock failed: %s", stderr.strip())
        return ok

    # ── Firmware package ──────────────────────────────────────────────────────

    @classmethod
    def extract_firmware(cls, tgz_path: str | Path) -> XiaomiFirmwareManifest | None:
        """Extract a Xiaomi fastboot ROM .tgz to a temp directory and scan contents.

        Args:
            tgz_path: Path to a Xiaomi fastboot ROM ``.tgz`` file.

        Returns:
            XiaomiFirmwareManifest or None on failure.
        """
        tgz_path = Path(tgz_path)
        if not tgz_path.exists():
            logger.error("Firmware package not found: %s", tgz_path)
            return None

        tmpdir = tempfile.mkdtemp(prefix="cf_xiaomi_")
        logger.info("Extracting %s → %s", tgz_path.name, tmpdir)

        try:
            with tarfile.open(str(tgz_path), "r:gz") as tf:
                tf.extractall(tmpdir)
        except (tarfile.TarError, OSError) as exc:
            logger.error("Extraction failed: %s", exc)
            return None

        root = Path(tmpdir)
        # Xiaomi ROMs often have a sub-directory with the codename
        subdirs = [d for d in root.iterdir() if d.is_dir()]
        if len(subdirs) == 1:
            root = subdirs[0]

        manifest = cls._scan_firmware_dir(root)
        return manifest

    @classmethod
    def scan_firmware_dir(cls, directory: str | Path) -> XiaomiFirmwareManifest:
        """Scan a pre-extracted Xiaomi firmware directory for flashable images.

        Supports both flat layouts and nested ``images/`` subdirectory.
        """
        return cls._scan_firmware_dir(Path(directory))

    @classmethod
    def _scan_firmware_dir(cls, root: Path) -> XiaomiFirmwareManifest:
        manifest = XiaomiFirmwareManifest(root_dir=root)

        # Check for flash_all.sh to extract MIUI version and codename
        flash_sh = root / "flash_all.sh"
        if flash_sh.exists():
            lines = flash_sh.read_text(errors="replace").splitlines()
            for line in lines:
                if "fastboot flash" in line and "vbmeta" not in line:
                    break

        # Check for META-INF or android-info.txt
        info_file = root / "android-info.txt"
        if info_file.exists():
            for line in info_file.read_text(errors="replace").splitlines():
                if line.startswith("require board="):
                    manifest.codename = line.split("=")[-1].strip()

        # Scan image directories
        search_dirs = [root, root / "images"]
        found: list[tuple[str, Path]] = []

        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            for img in sorted(search_dir.glob("*.img")):
                stem = img.stem.lower()
                for pattern, partition in _XIAOMI_PARTITION_MAP:
                    if stem == pattern or stem.startswith(pattern + "_"):
                        found.append((partition, img))
                        if partition == "super":
                            manifest.has_super = True
                        break

        manifest.found_images = found
        logger.info(
            "Firmware scan: %d flashable images, super=%s, codename=%s",
            len(found), manifest.has_super, manifest.codename
        )
        return manifest

    # ── Flashing ──────────────────────────────────────────────────────────────

    @classmethod
    def flash_firmware(
        cls,
        serial: str,
        firmware_dir: str | Path,
        partitions: list[str] | None = None,
        dry_run: bool = False,
    ) -> list[XiaomiFlashResult]:
        """Flash a Xiaomi fastboot firmware from a directory.

        Args:
            serial: Device serial in fastboot mode.
            firmware_dir: Directory containing ``.img`` files.
            partitions: Subset of partitions to flash.  None = all.
            dry_run: Simulate without running fastboot.

        Returns:
            List of XiaomiFlashResult, one per partition attempted.
        """
        manifest = cls.scan_firmware_dir(firmware_dir)
        if not manifest.found_images:
            logger.error("No flashable images found in %s", firmware_dir)
            return []

        results: list[XiaomiFlashResult] = []

        for partition, img_path in manifest.found_images:
            if partitions and partition not in partitions:
                results.append(XiaomiFlashResult(
                    success=True, partition=partition,
                    image=img_path.name, skipped=True
                ))
                continue

            if dry_run:
                logger.info("[dry-run] fastboot -s %s flash %s %s",
                            serial, partition, img_path.name)
                results.append(XiaomiFlashResult(
                    success=True, partition=partition, image=img_path.name
                ))
                continue

            logger.info("Flashing %s ← %s", partition, img_path.name)
            rc, _, stderr = FastbootManager._run(
                ["-s", serial, "flash", partition, str(img_path)],
                timeout=300,
            )
            ok = rc == 0
            if not ok:
                logger.error("Flash %s failed: %s", partition, stderr.strip())
            results.append(XiaomiFlashResult(
                success=ok, partition=partition,
                image=img_path.name, stderr=stderr,
            ))
            if not ok:
                logger.error("Aborting firmware flash after error on %s", partition)
                break

        return results

    @classmethod
    def flash_super(
        cls,
        serial: str,
        super_img: str | Path,
        dry_run: bool = False,
    ) -> bool:
        """Flash a super.img (dynamic partition) to a Xiaomi device.

        Args:
            serial: Device serial in fastboot mode.
            super_img: Path to super.img.
            dry_run: Simulate without executing.

        Returns:
            True on success.
        """
        super_img = Path(super_img)
        if not super_img.exists():
            logger.error("super.img not found: %s", super_img)
            return False

        if dry_run:
            logger.info("[dry-run] fastboot -s %s flash super %s", serial, super_img.name)
            return True

        logger.info("Flashing super.img (%d MB) to %s",
                    super_img.stat().st_size // (1024 * 1024), serial)
        rc, _, stderr = FastbootManager._run(
            ["-s", serial, "flash", "super", str(super_img)],
            timeout=600,
        )
        ok = rc == 0
        if not ok:
            logger.error("super.img flash failed: %s", stderr.strip())
        return ok

    @classmethod
    def wipe_data(cls, serial: str, dry_run: bool = False) -> bool:
        """Issue ``fastboot -w`` to wipe userdata + cache.

        Returns:
            True on success.
        """
        if dry_run:
            logger.info("[dry-run] fastboot -s %s -w", serial)
            return True

        logger.warning("Wiping userdata on %s", serial)
        rc, _, stderr = FastbootManager._run(["-s", serial, "-w"], timeout=120)
        ok = rc == 0
        if not ok:
            logger.error("Wipe failed: %s", stderr.strip())
        return ok

    # ── Anti-rollback safety ──────────────────────────────────────────────────

    @classmethod
    def check_anti_rollback(
        cls,
        serial: str,
        firmware_min_arb: int,
    ) -> tuple[bool, str]:
        """Verify the device ARB level is compatible with the firmware.

        Args:
            serial: ADB serial.
            firmware_min_arb: Minimum ARB level required by the firmware.

        Returns:
            (safe_to_flash, message)
        """
        info = cls.get_device_info(serial)
        if info.anti_rollback < 0:
            return True, "ARB level unknown — proceed with caution"

        if info.anti_rollback < firmware_min_arb:
            msg = (
                f"Device ARB level {info.anti_rollback} is BELOW firmware minimum "
                f"{firmware_min_arb}.  Flashing this ROM may permanently brick your device."
            )
            logger.error(msg)
            return False, msg

        msg = f"ARB check passed (device {info.anti_rollback} ≥ firmware {firmware_min_arb})"
        logger.info(msg)
        return True, msg
