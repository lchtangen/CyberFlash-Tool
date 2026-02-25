"""motorola_manager.py — Motorola device rescue and firmware flash engine.

Covers:
  - Motorola Rescue & Smart Assistant (ReadBack) firmware extraction workflow
  - Fastboot flash from Motorola stock firmware zip/tgz packages
  - XT-series device identification
  - Stock recovery sideload

Supported series: Edge, Edge+, Edge 50, G-series (G73, G84, G Power), Razr
Older: Moto E, Moto G, One series

All methods are synchronous and must be called from worker threads.

Usage::

    info = MotorolaManager.get_device_info(serial)
    MotorolaManager.flash_firmware(serial, firmware_dir, dry_run=False)
"""

from __future__ import annotations

import logging
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.fastboot_manager import FastbootManager

logger = logging.getLogger(__name__)

# ── Known Motorola codenames ──────────────────────────────────────────────────

MOTO_CODENAMES: dict[str, str] = {
    # Edge series
    "berlin":       "Motorola Edge 30 Pro",
    "dubai":        "Motorola Edge 30 Ultra",
    "eqs":          "Motorola Edge 50 Pro",
    "hiphala":      "Motorola Edge 50 Ultra",
    "bangkk":       "Motorola Edge 50 Fusion",
    "rtwo":         "Motorola Edge 40",
    "rjkarna":      "Motorola Edge 40 Pro",
    "nio":          "Motorola Edge+",
    "racer":        "Motorola Edge 30",
    "hiphi":        "Motorola Edge 50",
    # G series
    "devon":        "Moto G73",
    "hawao":        "Moto G84",
    "penangp":      "Moto G Power 5G",
    "manaus":       "Moto G 5G",
    "xpeng":        "Moto G Stylus",
    # Razr
    "felix":        "Motorola Razr 40 Ultra",
    "zeekr":        "Motorola Razr 40",
}

# Motorola vendor ID (USB)
_MOTO_VENDOR_ID = "22b8"

# Partition flash order for Motorola devices
_MOTO_FLASH_ORDER = [
    "partition",    # GPT partition table (if present)
    "xbl",
    "xbl_config",
    "abl",
    "tz",
    "hyp",
    "bluetooth",
    "dsp",
    "modem",
    "dtbo",
    "vbmeta",
    "vbmeta_system",
    "vbmeta_vendor",
    "recovery",
    "boot",
    "init_boot",
    "vendor_boot",
    "super",
    "userdata",
]

# Motorola ReadBack firmware archive marker files
_READBACK_MARKERS = {"flashfile.xml", "servicefile.xml", "partition.xml"}


# ── Enums ─────────────────────────────────────────────────────────────────────


class MotorolaFlashMethod(StrEnum):
    FASTBOOT   = "fastboot"      # Standard fastboot flash
    RESCUE     = "rescue"        # Motorola Rescue & Smart Assistant
    SIDELOAD   = "sideload"      # ADB sideload via recovery


class MotorolaUnlockStatus(StrEnum):
    LOCKED     = "locked"
    UNLOCKED   = "unlocked"
    UNKNOWN    = "unknown"


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class MotorolaDeviceInfo:
    """Motorola-specific device metadata."""

    serial:          str
    codename:        str = ""
    model:           str = ""
    sku:             str = ""    # e.g. XT2301-5
    android_version: str = ""
    build_id:        str = ""
    security_patch:  str = ""
    bl_status:       MotorolaUnlockStatus = MotorolaUnlockStatus.UNKNOWN
    oem_unlock_allowed: bool = False
    carrier_locked:  bool = False


@dataclass
class MotorolaFlashResult:
    """Result of a single Motorola flash step."""

    success:    bool
    partition:  str
    image:      str
    returncode: int = 0
    stderr:     str = ""
    skipped:    bool = False


@dataclass
class MotorolaFirmwareManifest:
    """Contents of a Motorola firmware package."""

    root_dir:        Path
    codename:        str = ""
    build:           str = ""
    found_images:    list[tuple[str, Path]] = field(default_factory=list)
    flashfile_xml:   str = ""    # Content of flashfile.xml if present
    has_flashfile:   bool = False
    has_super:       bool = False


# ── MotorolaManager ───────────────────────────────────────────────────────────


class MotorolaManager:
    """Orchestrates Motorola firmware flash and rescue operations.

    All classmethods; no instance state required.
    """

    # ── Device identification ─────────────────────────────────────────────────

    @classmethod
    def get_device_info(cls, serial: str) -> MotorolaDeviceInfo:
        """Return Motorola-specific device metadata via ADB.

        Args:
            serial: ADB device serial.
        """
        def prop(key: str) -> str:
            return AdbManager.shell(
                serial, f"getprop {key} 2>/dev/null", timeout=5
            ).strip()

        codename = prop("ro.product.device")
        model    = prop("ro.product.model")
        sku      = prop("ro.product.name")
        android  = prop("ro.build.version.release")
        build_id = prop("ro.build.id")
        sec_patch = prop("ro.build.version.security_patch")

        # OEM unlock allowed (set by user in Developer Options)
        oem_raw  = prop("sys.oem_unlock_allowed").lower()
        oem_ok   = oem_raw in ("1", "true", "yes")

        # Carrier lock detection
        carrier_raw = prop("ro.carrier").lower()
        carrier_locked = carrier_raw not in ("", "wifi", "unknown", "retail")

        bl_raw = prop("ro.secureboot.lockstate").lower()
        if bl_raw == "unlocked":
            bl_status = MotorolaUnlockStatus.UNLOCKED
        elif bl_raw == "locked":
            bl_status = MotorolaUnlockStatus.LOCKED
        else:
            bl_status = MotorolaUnlockStatus.UNKNOWN

        return MotorolaDeviceInfo(
            serial=serial,
            codename=codename,
            model=model,
            sku=sku,
            android_version=android,
            build_id=build_id,
            security_patch=sec_patch,
            bl_status=bl_status,
            oem_unlock_allowed=oem_ok,
            carrier_locked=carrier_locked,
        )

    @classmethod
    def model_name(cls, codename: str) -> str:
        """Return human-readable model name for a Motorola codename."""
        return MOTO_CODENAMES.get(codename.lower(), codename)

    @classmethod
    def get_fastboot_info(cls, serial: str) -> dict[str, str]:
        """Return fastboot variables for a device in fastboot mode."""
        _, out, stderr = FastbootManager._run(
            ["-s", serial, "getvar", "all"], timeout=15
        )
        raw = out + stderr
        result: dict[str, str] = {}
        for line in raw.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                result[k.strip().lower()] = v.strip()
        return result

    # ── Bootloader unlock ─────────────────────────────────────────────────────

    @classmethod
    def get_unlock_status(cls, serial: str) -> MotorolaUnlockStatus:
        """Return bootloader lock status for a device in fastboot mode."""
        _, out, stderr = FastbootManager._run(
            ["-s", serial, "getvar", "unlocked"], timeout=10
        )
        raw = (out + stderr).lower()
        if "unlocked: yes" in raw or "unlocked: true" in raw:
            return MotorolaUnlockStatus.UNLOCKED
        if "unlocked: no" in raw or "unlocked: false" in raw:
            return MotorolaUnlockStatus.LOCKED
        return MotorolaUnlockStatus.UNKNOWN

    @classmethod
    def oem_unlock(cls, serial: str, dry_run: bool = False) -> bool:
        """Issue ``fastboot oem unlock`` for Motorola devices.

        Motorola uses OEM-specific unlock codes for carrier-locked devices.
        This method works for unbranded / developer-unlocked variants.

        Returns:
            True on success.
        """
        if dry_run:
            logger.info("[dry-run] fastboot -s %s oem unlock", serial)
            return True

        logger.warning("Issuing OEM unlock on %s — data will be wiped", serial)
        rc, _, stderr = FastbootManager._run(
            ["-s", serial, "oem", "unlock"], timeout=60
        )
        ok = rc == 0
        if not ok:
            logger.error("OEM unlock failed: %s", stderr.strip())
        return ok

    @classmethod
    def get_unlock_code(cls, serial: str) -> str:
        """Retrieve the device-specific unlock code hash.

        Motorola's unlock portal (motorola.com/unlockr) requires this hash.
        The hash is obtained via ``fastboot oem get_unlock_data``.

        Returns:
            Raw unlock data string, or '' on failure.
        """
        _, out, stderr = FastbootManager._run(
            ["-s", serial, "oem", "get_unlock_data"], timeout=15
        )
        raw = out + stderr
        # Unlock data is split across multiple lines prefixed with "(bootloader)"
        lines = [
            ln.split(")")[-1].strip()
            for ln in raw.splitlines()
            if "(bootloader)" in ln and ln.split(")")[-1].strip()
        ]
        data = "".join(lines)
        if data:
            logger.info("Retrieved unlock data (%d chars)", len(data))
        else:
            logger.warning("No unlock data retrieved: %s", raw.strip())
        return data

    # ── Firmware package ──────────────────────────────────────────────────────

    @classmethod
    def inspect_firmware(cls, package_path: str | Path) -> MotorolaFirmwareManifest | None:
        """Inspect a Motorola firmware package (zip or tgz).

        Supports:
          - ``.zip`` — standard Motorola stock firmware (Lenovo-era)
          - ``.tgz`` / ``.tar.gz`` — older Moto G/E/X packages
          - Flat directory of ``.img`` files

        Args:
            package_path: Path to firmware archive or directory.

        Returns:
            MotorolaFirmwareManifest or None on error.
        """
        package_path = Path(package_path)
        if not package_path.exists():
            logger.error("Firmware not found: %s", package_path)
            return None

        if package_path.is_dir():
            return cls._scan_dir(package_path)

        # Extract to temp dir
        tmpdir = tempfile.mkdtemp(prefix="cf_moto_")
        logger.info("Extracting %s → %s", package_path.name, tmpdir)

        try:
            if package_path.suffix.lower() == ".zip":
                with zipfile.ZipFile(str(package_path)) as zf:
                    zf.extractall(tmpdir)
            elif package_path.name.endswith((".tgz", ".tar.gz", ".tar")):
                with tarfile.open(str(package_path), "r:*") as tf:
                    tf.extractall(tmpdir)
            else:
                logger.error("Unknown firmware format: %s", package_path.suffix)
                return None
        except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
            logger.error("Extraction error: %s", exc)
            return None

        return cls._scan_dir(Path(tmpdir))

    @classmethod
    def _scan_dir(cls, root: Path) -> MotorolaFirmwareManifest:
        manifest = MotorolaFirmwareManifest(root_dir=root)

        # Look for flashfile.xml (Motorola Rescue & Smart Assistant marker)
        flashfile = next(root.rglob("flashfile.xml"), None)
        if flashfile:
            manifest.has_flashfile = True
            import contextlib
            with contextlib.suppress(OSError):
                manifest.flashfile_xml = flashfile.read_text(errors="replace")

        # Look for build info
        for candidate in ("build.prop", "system/build.prop"):
            bp = root / candidate
            if bp.exists():
                for line in bp.read_text(errors="replace").splitlines():
                    if line.startswith("ro.build.id="):
                        manifest.build = line.split("=")[-1].strip()
                    elif line.startswith("ro.product.device="):
                        manifest.codename = line.split("=")[-1].strip()
                break

        # Scan images
        found: list[tuple[str, Path]] = []
        for img in sorted(root.rglob("*.img")):
            stem = img.stem.lower()
            for partition in _MOTO_FLASH_ORDER:
                if stem == partition or stem.startswith(partition + "_"):
                    found.append((partition, img))
                    if partition == "super":
                        manifest.has_super = True
                    break

        manifest.found_images = found
        logger.info("Motorola firmware scan: %d images, hasFlashfile=%s",
                    len(found), manifest.has_flashfile)
        return manifest

    # ── Flashing ──────────────────────────────────────────────────────────────

    @classmethod
    def flash_firmware(
        cls,
        serial: str,
        firmware_source: str | Path,
        partitions: list[str] | None = None,
        dry_run: bool = False,
    ) -> list[MotorolaFlashResult]:
        """Flash Motorola firmware from a package or directory.

        Args:
            serial: Device serial in fastboot mode.
            firmware_source: Path to firmware archive or directory.
            partitions: Subset of partition names to flash.  None = all.
            dry_run: Simulate without running fastboot.

        Returns:
            List of MotorolaFlashResult per partition.
        """
        manifest = cls.inspect_firmware(firmware_source)
        if manifest is None:
            return []

        if not manifest.found_images:
            logger.error("No flashable images found in %s", firmware_source)
            return []

        results: list[MotorolaFlashResult] = []

        for partition, img_path in manifest.found_images:
            if partitions and partition not in partitions:
                results.append(MotorolaFlashResult(
                    success=True, partition=partition,
                    image=img_path.name, skipped=True
                ))
                continue

            if dry_run:
                logger.info("[dry-run] fastboot -s %s flash %s %s",
                            serial, partition, img_path.name)
                results.append(MotorolaFlashResult(
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
            results.append(MotorolaFlashResult(
                success=ok, partition=partition, image=img_path.name,
                returncode=rc, stderr=stderr,
            ))
            if not ok:
                logger.error("Aborting firmware flash after error on %s", partition)
                break

        return results

    @classmethod
    def rescue_flash(
        cls,
        serial: str,
        firmware_dir: str | Path,
        dry_run: bool = False,
    ) -> list[MotorolaFlashResult]:
        """Flash a Motorola Rescue & Smart Assistant firmware image set.

        RSA packages include a ``flashfile.xml`` that specifies flash commands.
        This method parses the XML and replays the flash commands via fastboot.

        Args:
            serial: Device serial in fastboot mode.
            firmware_dir: Directory containing RSA firmware files.
            dry_run: Simulate without executing.

        Returns:
            List of MotorolaFlashResult per step.
        """
        firmware_dir = Path(firmware_dir)
        flashfile = firmware_dir / "flashfile.xml"
        if not flashfile.exists():
            flashfile = next(firmware_dir.rglob("flashfile.xml"), None)
        if not flashfile or not flashfile.exists():
            logger.warning("flashfile.xml not found — falling back to directory scan")
            return cls.flash_firmware(serial, firmware_dir, dry_run=dry_run)

        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(str(flashfile))
            root_el = tree.getroot()
        except Exception as exc:
            logger.error("Failed to parse flashfile.xml: %s", exc)
            return []

        results: list[MotorolaFlashResult] = []
        img_dir = flashfile.parent

        # flashfile.xml schema: <steps> <step operation="flash" partition="..." filename="..."/> </steps>
        for step in root_el.iter("step"):
            op        = step.get("operation", "").lower()
            partition = step.get("partition", step.get("name", ""))
            filename  = step.get("filename", step.get("file", ""))

            if op != "flash" or not partition or not filename:
                continue

            img_path = img_dir / filename
            if not img_path.exists():
                logger.warning("Rescue image not found: %s", filename)
                results.append(MotorolaFlashResult(
                    success=False, partition=partition, image=filename,
                    stderr="File not found"
                ))
                continue

            if dry_run:
                logger.info("[dry-run] fastboot -s %s flash %s %s",
                            serial, partition, filename)
                results.append(MotorolaFlashResult(
                    success=True, partition=partition, image=filename
                ))
                continue

            logger.info("Rescue flash: %s ← %s", partition, filename)
            rc, _, stderr = FastbootManager._run(
                ["-s", serial, "flash", partition, str(img_path)],
                timeout=300,
            )
            ok = rc == 0
            if not ok:
                logger.error("Rescue flash %s failed: %s", partition, stderr.strip())
            results.append(MotorolaFlashResult(
                success=ok, partition=partition, image=filename,
                returncode=rc, stderr=stderr,
            ))
            if not ok:
                break

        logger.info("Rescue flash complete: %d steps, %d failed",
                    len(results), sum(1 for r in results if not r.success))
        return results

    @classmethod
    def sideload_ota(
        cls,
        serial: str,
        ota_zip: str | Path,
        timeout: int = 600,
    ) -> bool:
        """Sideload an OTA ZIP via ``adb sideload`` in recovery/sideload mode.

        Args:
            serial: ADB serial in sideload mode.
            ota_zip: Path to Motorola OTA ``.zip``.
            timeout: Max seconds to wait.

        Returns:
            True on success.
        """
        ota_zip = Path(ota_zip)
        if not ota_zip.exists():
            logger.error("OTA ZIP not found: %s", ota_zip)
            return False

        from cyberflash.core.tool_manager import ToolManager
        cmd = [*ToolManager.adb_cmd(), "-s", serial, "sideload", str(ota_zip)]
        logger.info("Sideloading Motorola OTA: %s", ota_zip.name)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            ok = r.returncode == 0
            if not ok:
                logger.error("Sideload failed: %s", r.stderr.strip())
            return ok
        except subprocess.TimeoutExpired:
            logger.error("Sideload timeout after %ds", timeout)
            return False

    @classmethod
    def wipe_data(cls, serial: str, dry_run: bool = False) -> bool:
        """Wipe userdata via ``fastboot erase userdata``.

        Returns:
            True on success.
        """
        if dry_run:
            logger.info("[dry-run] fastboot -s %s erase userdata", serial)
            return True

        logger.warning("Erasing userdata on %s", serial)
        rc, _, stderr = FastbootManager._run(
            ["-s", serial, "erase", "userdata"], timeout=120
        )
        ok = rc == 0
        if not ok:
            logger.error("Erase userdata failed: %s", stderr.strip())
        return ok
