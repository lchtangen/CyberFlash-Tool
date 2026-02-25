"""pixel_manager.py — Google Pixel factory image flash automation.

Automates flashing Pixel factory images (equivalent to flash-all.sh) and
OTA sideload via ``update_engine_client`` from a host PC.

Supported series: Pixel 6a · 7 · 7a · 7 Pro · 8 · 8a · 8 Pro · 9 · 9 Pro · 9 Pro XL
Also covers Pixel 5 / 5a (older A13 builds).

All methods are synchronous and must be called from worker threads.

Usage::

    manifest = PixelManager.inspect_factory_image(zip_path)
    PixelManager.flash_factory_image(serial, zip_path, wipe=True, dry_run=False)
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.fastboot_manager import FastbootManager

logger = logging.getLogger(__name__)

# ── Known Pixel codenames ─────────────────────────────────────────────────────

PIXEL_CODENAMES: dict[str, str] = {
    "sunfish":    "Pixel 4a",
    "bramble":    "Pixel 4a 5G",
    "redfin":     "Pixel 5",
    "barbet":     "Pixel 5a",
    "oriole":     "Pixel 6",
    "raven":      "Pixel 6 Pro",
    "bluejay":    "Pixel 6a",
    "panther":    "Pixel 7",
    "cheetah":    "Pixel 7 Pro",
    "lynx":       "Pixel 7a",
    "felix":      "Pixel Fold",
    "shiba":      "Pixel 8",
    "husky":      "Pixel 8 Pro",
    "akita":      "Pixel 8a",
    "tokay":      "Pixel 9",
    "caiman":     "Pixel 9 Pro",
    "komodo":     "Pixel 9 Pro XL",
    "comet":      "Pixel 9 Pro Fold",
    "porbeagle":  "Pixel 9a",
}

# Android Beta Program OTA feed URL
_BETA_FEED_URL = "https://developer.android.com/about/versions"

# Partitions flashed by flash-all.sh in order
_FLASH_ALL_PARTITIONS: list[str] = [
    "bootloader",
    "radio",
    "boot",
    "init_boot",
    "vendor_boot",
    "dtbo",
    "vbmeta",
    "vbmeta_system",
    "super",
    "userdata",
]

# Partitions excluded when wipe=False (preserve userdata)
_NO_WIPE_SKIP = {"userdata"}


# ── Enums ─────────────────────────────────────────────────────────────────────


class PixelFlashMode(StrEnum):
    FACTORY_IMAGE = "factory_image"   # Full factory zip (flash-all)
    OTA_SIDELOAD  = "ota_sideload"    # OTA zip via adb sideload
    BOOTLOADER    = "bootloader_only"
    RADIO         = "radio_only"


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class PixelDeviceInfo:
    """Google Pixel device metadata."""

    serial:          str
    codename:        str = ""
    model:           str = ""
    android_version: str = ""
    build_id:        str = ""
    security_patch:  str = ""
    bl_unlocked:     bool | None = None
    bootloader_ver:  str = ""
    radio_ver:       str = ""


@dataclass
class FactoryImageManifest:
    """Parsed contents of a Pixel factory image ZIP."""

    zip_path:       Path
    codename:       str = ""
    build_id:       str = ""
    android_ver:    str = ""
    bootloader_img: Path | None = None
    radio_img:      Path | None = None
    image_zip:      Path | None = None   # images/[codename]-img-[build].zip
    flash_sh:       str = ""             # Content of flash-all.sh
    partitions:     list[tuple[str, Path]] = field(default_factory=list)
    extracted_dir:  Path | None = None


@dataclass
class PixelFlashResult:
    """Result of a single flash step."""

    success:    bool
    partition:  str
    image:      str
    returncode: int = 0
    stderr:     str = ""
    skipped:    bool = False


# ── PixelManager ──────────────────────────────────────────────────────────────


class PixelManager:
    """Google Pixel factory image flash engine.

    All classmethods; no instance state required.
    """

    # ── Device info ───────────────────────────────────────────────────────────

    @classmethod
    def get_device_info(cls, serial: str) -> PixelDeviceInfo:
        """Return Pixel-specific device metadata via ADB.

        Args:
            serial: ADB device serial.
        """
        def prop(key: str) -> str:
            return AdbManager.shell(
                serial, f"getprop {key} 2>/dev/null", timeout=5
            ).strip()

        codename    = prop("ro.product.device")
        model       = prop("ro.product.model")
        android     = prop("ro.build.version.release")
        build_id    = prop("ro.build.id")
        sec_patch   = prop("ro.build.version.security_patch")

        # BL status from props (unreliable — prefer fastboot getvar)
        bl_str  = prop("ro.boot.flash.locked").lower()
        if bl_str == "0":
            bl_unlocked = True
        elif bl_str == "1":
            bl_unlocked = False
        else:
            bl_unlocked = None

        return PixelDeviceInfo(
            serial=serial,
            codename=codename,
            model=model,
            android_version=android,
            build_id=build_id,
            security_patch=sec_patch,
            bl_unlocked=bl_unlocked,
        )

    @classmethod
    def get_fastboot_info(cls, serial: str) -> PixelDeviceInfo:
        """Return Pixel device metadata from fastboot mode.

        Args:
            serial: Device serial in fastboot mode.
        """
        _, out, stderr = FastbootManager._run(
            ["-s", serial, "getvar", "all"], timeout=15
        )
        raw = out + stderr
        props: dict[str, str] = {}
        for line in raw.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                props[k.strip().lower()] = v.strip()

        unlocked_str = props.get("unlocked", "").lower()
        bl_unlocked = (
            True if unlocked_str in ("yes", "true")
            else False if unlocked_str in ("no", "false")
            else None
        )

        return PixelDeviceInfo(
            serial=serial,
            codename=props.get("product", ""),
            model=props.get("model", ""),
            build_id=props.get("version-baseband", ""),
            bl_unlocked=bl_unlocked,
            bootloader_ver=props.get("version-bootloader", ""),
            radio_ver=props.get("version-baseband", ""),
        )

    @classmethod
    def model_name(cls, codename: str) -> str:
        """Return the human-readable model name for a codename.

        Returns the codename itself if not in the known list.
        """
        return PIXEL_CODENAMES.get(codename.lower(), codename)

    # ── Factory image inspection ──────────────────────────────────────────────

    @classmethod
    def inspect_factory_image(cls, zip_path: str | Path) -> FactoryImageManifest | None:
        """Parse a Pixel factory image ZIP and return its manifest.

        Factory image ZIP structure::

            [codename]-[build]/
              flash-all.sh
              flash-all.bat
              bootloader-[codename]-[ver].img
              radio-[codename]-[ver].img
              image-[codename]-[build].zip  ← inner ZIP with partition images

        Args:
            zip_path: Path to the factory image ``.zip``.

        Returns:
            FactoryImageManifest or None on error.
        """
        zip_path = Path(zip_path)
        if not zip_path.exists():
            logger.error("Factory image not found: %s", zip_path)
            return None

        try:
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                names = zf.namelist()
        except zipfile.BadZipFile as exc:
            logger.error("Invalid ZIP: %s — %s", zip_path.name, exc)
            return None

        manifest = FactoryImageManifest(zip_path=zip_path)

        for name in names:
            base = Path(name).name.lower()
            if base.startswith("bootloader-") and base.endswith(".img"):
                manifest.bootloader_img = Path(name)
            elif base.startswith("radio-") and base.endswith(".img"):
                manifest.radio_img = Path(name)
            elif base.startswith("image-") and base.endswith(".zip"):
                manifest.image_zip = Path(name)
                # Extract codename + build from "image-[codename]-[build].zip"
                parts = base.removeprefix("image-").removesuffix(".zip").rsplit("-", 1)
                if len(parts) == 2:
                    manifest.codename, manifest.build_id = parts
            elif base == "flash-all.sh":
                try:
                    with zipfile.ZipFile(str(zip_path)) as zf:
                        manifest.flash_sh = zf.read(name).decode("utf-8", errors="replace")
                except Exception:
                    pass

        # Extract Android version from build ID heuristic (first letter)
        if manifest.build_id:
            _ANDROID_BUILD_LETTERS = {
                "A": "14", "B": "15", "C": "12", "D": "13",
                "E": "14", "F": "15", "G": "16",
            }
            first = manifest.build_id[0].upper()
            manifest.android_ver = _ANDROID_BUILD_LETTERS.get(first, "")

        logger.info(
            "Factory image: %s build %s (Android %s)",
            manifest.codename, manifest.build_id, manifest.android_ver
        )
        return manifest

    # ── Flashing ──────────────────────────────────────────────────────────────

    @classmethod
    def flash_factory_image(
        cls,
        serial: str,
        zip_path: str | Path,
        wipe: bool = True,
        dry_run: bool = False,
    ) -> list[PixelFlashResult]:
        """Flash a Pixel factory image to a device in fastboot mode.

        Equivalent to running ``flash-all.sh`` but cross-platform and with
        progress reporting.

        Args:
            serial: Device serial in fastboot mode.
            zip_path: Path to factory image ZIP.
            wipe: Wipe userdata (``fastboot -w``).  Default True.
            dry_run: Simulate without running fastboot.

        Returns:
            List of PixelFlashResult per partition attempted.
        """
        zip_path = Path(zip_path)
        manifest = cls.inspect_factory_image(zip_path)
        if manifest is None:
            return []

        results: list[PixelFlashResult] = []

        with tempfile.TemporaryDirectory(prefix="cf_pixel_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            logger.info("Extracting factory image to %s", tmpdir)

            try:
                with zipfile.ZipFile(str(zip_path)) as zf:
                    zf.extractall(tmpdir)
            except zipfile.BadZipFile as exc:
                logger.error("Extraction failed: %s", exc)
                return []

            # Find extracted files
            all_imgs = list(tmpdir_path.rglob("*.img"))
            img_map: dict[str, Path] = {}
            for img in all_imgs:
                stem = img.stem.lower()
                # e.g. bootloader-cheetah-slider-1.2-9626199.img → bootloader
                for part in _FLASH_ALL_PARTITIONS:
                    if stem.startswith(part):
                        img_map[part] = img
                        break

            # Also extract inner image ZIP if present
            if manifest.image_zip:
                inner_zip = tmpdir_path / manifest.image_zip.name
                # Search recursively
                found_inner = list(tmpdir_path.rglob("image-*.zip"))
                if found_inner:
                    inner_zip = found_inner[0]
                if inner_zip.exists():
                    try:
                        with zipfile.ZipFile(str(inner_zip)) as izf:
                            izf.extractall(tmpdir)
                        for img in tmpdir_path.rglob("*.img"):
                            stem = img.stem.lower()
                            if stem not in img_map:
                                img_map[stem] = img
                    except zipfile.BadZipFile as exc:
                        logger.warning("Inner image ZIP error: %s", exc)

            # Flash in order
            for partition in _FLASH_ALL_PARTITIONS:
                if partition not in img_map:
                    results.append(PixelFlashResult(
                        success=True, partition=partition, image="", skipped=True
                    ))
                    continue

                if not wipe and partition in _NO_WIPE_SKIP:
                    results.append(PixelFlashResult(
                        success=True, partition=partition,
                        image=img_map[partition].name, skipped=True
                    ))
                    continue

                img_path = img_map[partition]

                if dry_run:
                    logger.info("[dry-run] fastboot -s %s flash %s %s",
                                serial, partition, img_path.name)
                    results.append(PixelFlashResult(
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
                results.append(PixelFlashResult(
                    success=ok, partition=partition, image=img_path.name,
                    returncode=rc, stderr=stderr,
                ))
                if not ok:
                    break

        return results

    @classmethod
    def flash_bootloader(
        cls,
        serial: str,
        bootloader_img: str | Path,
        dry_run: bool = False,
    ) -> PixelFlashResult:
        """Flash only the bootloader image.

        Returns:
            PixelFlashResult.
        """
        bootloader_img = Path(bootloader_img)
        if not bootloader_img.exists():
            return PixelFlashResult(
                success=False, partition="bootloader",
                image=str(bootloader_img), stderr="File not found"
            )

        if dry_run:
            logger.info("[dry-run] fastboot -s %s flash bootloader %s",
                        serial, bootloader_img.name)
            return PixelFlashResult(success=True, partition="bootloader",
                                    image=bootloader_img.name)

        logger.info("Flashing bootloader: %s", bootloader_img.name)
        rc, _, stderr = FastbootManager._run(
            ["-s", serial, "flash", "bootloader", str(bootloader_img)],
            timeout=120,
        )
        ok = rc == 0
        if not ok:
            logger.error("Bootloader flash failed: %s", stderr.strip())
        return PixelFlashResult(
            success=ok, partition="bootloader",
            image=bootloader_img.name, returncode=rc, stderr=stderr,
        )

    @classmethod
    def flash_radio(
        cls,
        serial: str,
        radio_img: str | Path,
        dry_run: bool = False,
    ) -> PixelFlashResult:
        """Flash only the radio/baseband image.

        Returns:
            PixelFlashResult.
        """
        radio_img = Path(radio_img)
        if not radio_img.exists():
            return PixelFlashResult(
                success=False, partition="radio",
                image=str(radio_img), stderr="File not found"
            )

        if dry_run:
            logger.info("[dry-run] fastboot -s %s flash radio %s",
                        serial, radio_img.name)
            return PixelFlashResult(success=True, partition="radio", image=radio_img.name)

        logger.info("Flashing radio: %s", radio_img.name)
        rc, _, stderr = FastbootManager._run(
            ["-s", serial, "flash", "radio", str(radio_img)],
            timeout=120,
        )
        ok = rc == 0
        if not ok:
            logger.error("Radio flash failed: %s", stderr.strip())
        return PixelFlashResult(
            success=ok, partition="radio",
            image=radio_img.name, returncode=rc, stderr=stderr,
        )

    # ── OTA sideload ──────────────────────────────────────────────────────────

    @classmethod
    def sideload_ota(
        cls,
        serial: str,
        ota_zip: str | Path,
        timeout: int = 600,
    ) -> bool:
        """Sideload an OTA ZIP via ``adb sideload`` (device in sideload mode).

        Args:
            serial: ADB serial of device in sideload mode.
            ota_zip: Path to the OTA ``.zip`` file.
            timeout: Max seconds to wait for sideload completion.

        Returns:
            True on success.
        """
        ota_zip = Path(ota_zip)
        if not ota_zip.exists():
            logger.error("OTA ZIP not found: %s", ota_zip)
            return False

        from cyberflash.core.tool_manager import ToolManager
        cmd = [*ToolManager.adb_cmd(), "-s", serial, "sideload", str(ota_zip)]
        logger.info("Sideloading OTA: %s (%d MB)",
                    ota_zip.name, ota_zip.stat().st_size // (1024 * 1024))
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            ok = r.returncode == 0
            if not ok:
                logger.error("adb sideload failed: %s", r.stderr.strip())
            return ok
        except subprocess.TimeoutExpired:
            logger.error("adb sideload timeout after %ds", timeout)
            return False

    # ── Bootloader unlock ─────────────────────────────────────────────────────

    @classmethod
    def flashing_unlock(cls, serial: str, dry_run: bool = False) -> bool:
        """Issue ``fastboot flashing unlock`` to unlock the Pixel bootloader.

        The device must have OEM unlocking enabled in Developer Options.

        Returns:
            True on success (user confirmation on device required).
        """
        if dry_run:
            logger.info("[dry-run] fastboot -s %s flashing unlock", serial)
            return True

        logger.warning("Unlocking bootloader on %s — data will be wiped", serial)
        rc, _, stderr = FastbootManager._run(
            ["-s", serial, "flashing", "unlock"], timeout=60
        )
        ok = rc == 0
        if not ok:
            logger.error("flashing unlock failed: %s", stderr.strip())
        return ok

    @classmethod
    def flashing_lock(cls, serial: str, dry_run: bool = False) -> bool:
        """Re-lock the Pixel bootloader via ``fastboot flashing lock``.

        Returns:
            True on success.
        """
        if dry_run:
            logger.info("[dry-run] fastboot -s %s flashing lock", serial)
            return True

        logger.warning("Locking bootloader on %s — data will be wiped", serial)
        rc, _, stderr = FastbootManager._run(
            ["-s", serial, "flashing", "lock"], timeout=60
        )
        ok = rc == 0
        if not ok:
            logger.error("flashing lock failed: %s", stderr.strip())
        return ok
