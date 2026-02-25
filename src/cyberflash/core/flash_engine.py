from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.fastboot_manager import FastbootManager
from cyberflash.core.partition_manager import PartitionManager
from cyberflash.core.payload_dumper import PayloadDumper
from cyberflash.models.profile import DeviceProfile

logger = logging.getLogger(__name__)


class FlashEngine:
    """Pure-Python orchestrator for flash operations.

    All methods call ``self._log(msg)`` before/after major operations and
    return ``False`` on failure — they never raise.
    ``log_cb`` is called with each log line (used by FlashWorker to emit signals).
    """

    FLASH_TIMEOUT = 300  # seconds per partition

    def __init__(
        self,
        serial: str,
        log_cb: Callable[[str], None] | None = None,
    ) -> None:
        self.serial = serial
        self._log_cb = log_cb

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        logger.info("[%s] %s", self.serial, msg)
        if self._log_cb:
            self._log_cb(msg)

    # ── Source detection & extraction ────────────────────────────────────────

    @staticmethod
    def detect_source_type(source: Path) -> str:
        """Detect the firmware source format.

        Returns:
            ``"payload_bin"`` — raw payload.bin file
            ``"ota_zip"``     — OTA zip containing payload.bin
            ``"img_dir"``     — directory of pre-extracted .img files
            ``"unknown"``     — unrecognised format
        """
        if source.is_dir():
            # Check if directory contains .img files
            imgs = list(source.glob("*.img"))
            if imgs:
                return "img_dir"
            # Maybe a payload.bin inside the directory?
            if (source / "payload.bin").exists():
                return "payload_bin"
            return "unknown"

        if source.is_file():
            name_lower = source.name.lower()
            if name_lower == "payload.bin" or name_lower.endswith("payload.bin"):
                return "payload_bin"
            if name_lower.endswith(".zip"):
                return "ota_zip"
            if name_lower.endswith(".img"):
                return "img_dir"  # single image file

        return "unknown"

    def extract_payload(
        self,
        source: Path,
        dest_dir: Path,
        partitions: list[str],
        *,
        dry_run: bool = False,
    ) -> dict[str, Path]:
        """Extract partition images from a payload.bin or OTA zip.

        Args:
            source: Path to ``payload.bin`` or OTA ``.zip`` file.
            dest_dir: Directory to write extracted ``.img`` files.
            partitions: List of partition names to extract.
            dry_run: If True, simulate without extracting.

        Returns:
            Dict mapping partition name → extracted .img path.
            Only partitions successfully extracted are included.
        """
        self._log(f"Extracting firmware from: {source.name}")
        self._log(f"Target partitions: {partitions}")

        if dry_run:
            result: dict[str, Path] = {}
            for p in partitions:
                self._log(f"[dry-run] Would extract: {p}.img")
                result[p] = dest_dir / f"{p}.img"
            return result

        if not source.exists():
            self._log(f"Source not found: {source}")
            return {}

        # If source is a directory containing payload.bin, use it
        actual_source = source
        if source.is_dir() and (source / "payload.bin").exists():
            actual_source = source / "payload.bin"

        try:
            dumper = PayloadDumper(actual_source)
        except (FileNotFoundError, ValueError) as exc:
            self._log(f"Failed to open payload: {exc}")
            return {}

        available = dumper.list_partitions()
        self._log(f"Payload contains {len(available)} partitions: {available}")

        extracted: dict[str, Path] = {}
        with dumper:
            for partition in partitions:
                if partition not in available:
                    self._log(f"Partition '{partition}' not in payload — skipping")
                    continue
                try:
                    part_name = partition  # bind for lambda
                    img_path = dumper.extract(
                        partition,
                        dest_dir,
                        progress_cb=lambda done, tot, p=part_name: (
                            self._log(f"  {p}: {done}/{tot} bytes")
                            if logger.isEnabledFor(logging.DEBUG)
                            else None
                        ),
                    )
                    extracted[partition] = img_path
                    self._log(f"Extracted: {partition}.img ({img_path.stat().st_size:,} bytes)")
                except Exception as exc:
                    self._log(f"Failed to extract '{partition}': {exc}")

        self._log(f"Extraction complete: {len(extracted)}/{len(partitions)} partitions extracted")
        return extracted

    # ── Bootloader ───────────────────────────────────────────────────────────

    def is_bootloader_unlocked(self) -> bool:
        """Check whether the bootloader reports as unlocked via fastboot."""
        val = FastbootManager.get_var(self.serial, "unlocked").lower()
        return val == "yes"

    def unlock_bootloader(self, profile: DeviceProfile, dry_run: bool = False) -> bool:
        """Unlock the bootloader using the profile's unlock command.

        Returns True on success, False on any error.
        """
        self._log("Checking bootloader state…")
        if self.is_bootloader_unlocked():
            self._log("Bootloader already unlocked — skipping.")
            return True

        cmd_parts = profile.bootloader.unlock_command.split()
        self._log(f"Unlocking bootloader: {' '.join(cmd_parts)}")

        if dry_run:
            self._log(f"[dry-run] Would run: fastboot {' '.join(cmd_parts)}")
            return True

        rc, stdout, stderr = FastbootManager._run(["-s", self.serial, *cmd_parts], timeout=60)
        output = (stderr or stdout).strip()
        if rc != 0:
            self._log(f"Bootloader unlock FAILED: {output}")
            return False

        self._log(f"Bootloader unlock completed: {output}")
        return True

    # ── Partition flashing ───────────────────────────────────────────────────

    def flash_partition(self, partition: str, image: Path, dry_run: bool = False) -> bool:
        """Flash a single partition image via fastboot.

        Returns True on success.
        """
        self._log(f"Flashing {partition} ← {image.name}")
        if dry_run:
            self._log(f"[dry-run] Would flash {partition} with {image}")
            return True

        if not image.exists():
            self._log(f"Image not found: {image}")
            return False

        ok, output = FastbootManager.flash(
            self.serial, partition, image, timeout=self.FLASH_TIMEOUT
        )
        if not ok:
            self._log(f"Flash {partition} FAILED: {output}")
            return False

        self._log(f"Flash {partition} OK")
        return True

    def flash_multiple(self, images: dict[str, Path], dry_run: bool = False) -> dict[str, bool]:
        """Flash multiple partitions in order.

        ``images`` is an ordered dict mapping partition name → image path.
        Returns a dict of partition → success.
        """
        results: dict[str, bool] = {}
        for partition, image in images.items():
            results[partition] = self.flash_partition(partition, image, dry_run=dry_run)
        return results

    def disable_vbmeta_verification(
        self, flags: str = "--disable-verity --disable-verification", dry_run: bool = False
    ) -> bool:
        """Flash vbmeta with verification-disabling flags.

        Returns True on success.
        """
        self._log(f"Disabling vbmeta verification ({flags})")
        if dry_run:
            self._log(f"[dry-run] Would run: fastboot flash vbmeta {flags} <vbmeta.img>")
            return True

        flag_parts = flags.split()
        rc, _, stderr = FastbootManager._run(
            ["-s", self.serial, *flag_parts, "flash", "vbmeta"],
            timeout=60,
        )
        if rc != 0:
            self._log(f"vbmeta flag flash FAILED: {stderr}")
            return False

        self._log("vbmeta verification disabled")
        return True

    # ── Recovery ────────────────────────────────────────────────────────────

    def flash_recovery(self, recovery_img: Path, dry_run: bool = False) -> bool:
        """Flash a custom recovery image."""
        return self.flash_partition("recovery", recovery_img, dry_run=dry_run)

    def sideload_zip(self, zip_path: Path, dry_run: bool = False) -> bool:
        """Sideload a zip via ``adb sideload`` (device must be in sideload mode).

        Returns True on success.
        """
        self._log(f"Sideloading {zip_path.name}")
        if dry_run:
            self._log(f"[dry-run] Would sideload: {zip_path}")
            return True

        if not zip_path.exists():
            self._log(f"Zip not found: {zip_path}")
            return False

        rc, _, stderr = AdbManager._run(["-s", self.serial, "sideload", str(zip_path)], timeout=600)
        if rc != 0:
            self._log(f"Sideload FAILED: {stderr}")
            return False

        self._log("Sideload completed")
        return True

    # ── Wipe ────────────────────────────────────────────────────────────────

    def wipe_partition(self, partition: str, dry_run: bool = False) -> bool:
        """Erase a fastboot partition.

        Returns True on success.
        """
        self._log(f"Erasing partition: {partition}")
        if dry_run:
            self._log(f"[dry-run] Would erase: {partition}")
            return True

        ok = FastbootManager.erase(self.serial, partition)
        if not ok:
            self._log(f"Erase {partition} FAILED")
            return False

        self._log(f"Erase {partition} OK")
        return True

    def wipe_dalvik_cache(self, dry_run: bool = False) -> bool:
        """Wipe Dalvik/ART cache via ADB shell (device must be in recovery mode).

        Returns True on success.
        """
        self._log("Wiping Dalvik/ART cache…")
        if dry_run:
            self._log("[dry-run] Would run: adb shell rm -rf /data/dalvik-cache/*")
            return True

        output = AdbManager.shell(self.serial, "rm -rf /data/dalvik-cache/*", timeout=30)
        self._log(f"Dalvik cache wipe output: {output.strip() or '(none)'}")
        return True

    # ── Slot management ──────────────────────────────────────────────────────

    def switch_slot(self, target_slot: str, dry_run: bool = False) -> bool:
        """Switch the active A/B slot via fastboot set_active.

        Returns True on success.
        """
        self._log(f"Switching active slot to: {target_slot}")
        return PartitionManager.set_active_slot(self.serial, target_slot, dry_run=dry_run)

    # ── Clean Slate (Erase + Reflash) ──────────────────────────────────────

    def erase_all_partitions(self, partitions: list[str], dry_run: bool = False) -> dict[str, bool]:
        """Erase all specified partitions before reflashing.

        Returns a dict of partition → success.
        """
        self._log(f"Erasing {len(partitions)} partitions (clean slate)…")
        results: dict[str, bool] = {}
        for partition in partitions:
            results[partition] = self.wipe_partition(partition, dry_run=dry_run)
        passed = sum(1 for ok in results.values() if ok)
        self._log(f"Erase complete: {passed}/{len(partitions)} succeeded")
        return results

    def clean_slate_reflash(
        self,
        profile: DeviceProfile,
        images: dict[str, Path],
        *,
        wipe_userdata: bool = True,
        dry_run: bool = False,
    ) -> bool:
        """Full clean slate: erase all partitions, flash fresh images, reset.

        This is the nuclear recovery option for soft-bricked devices.
        Steps:
          1. Erase all flash partitions defined in the profile
          2. Erase userdata (factory reset) if requested
          3. Disable vbmeta verification
          4. Flash all provided partition images
          5. Switch A/B slot to inactive (for A/B devices)
          6. Reboot to system

        Returns True only if all critical steps succeed.
        """
        self._log("=" * 60)
        self._log("CLEAN SLATE REFLASH — Erase + Reflash")
        self._log(f"Device: {profile.name} ({profile.codename})")
        self._log(f"Partitions to erase: {profile.flash.partitions}")
        self._log(f"Images to flash: {list(images.keys())}")
        self._log(f"Wipe userdata: {wipe_userdata}")
        self._log("=" * 60)

        # Step 1: Erase all flash partitions
        erase_targets = list(profile.flash.partitions)
        if wipe_userdata and "userdata" not in erase_targets:
            erase_targets.append("userdata")

        erase_results = self.erase_all_partitions(erase_targets, dry_run=dry_run)
        erase_failures = [p for p, ok in erase_results.items() if not ok]
        if erase_failures:
            self._log(f"WARNING: Failed to erase: {erase_failures}")
            # Non-fatal for erase — the flash will overwrite anyway

        # Step 2: Disable vbmeta verification
        if profile.flash.vbmeta_disable_flags:
            ok = self.disable_vbmeta_verification(
                profile.flash.vbmeta_disable_flags, dry_run=dry_run
            )
            if not ok:
                self._log("WARNING: vbmeta disable failed — continuing anyway")

        # Step 3: Flash all provided images
        flash_results = self.flash_multiple(images, dry_run=dry_run)
        flash_failures = [p for p, ok in flash_results.items() if not ok]
        if flash_failures:
            self._log(f"CRITICAL: Failed to flash: {flash_failures}")
            return False

        # Step 4: Switch A/B slot (for A/B devices)
        if profile.ab_slots:
            inactive = PartitionManager.get_inactive_slot(self.serial)
            if inactive:
                ok = self.switch_slot(inactive, dry_run=dry_run)
                if not ok:
                    self._log("WARNING: Slot switch failed")

        self._log("=" * 60)
        self._log("CLEAN SLATE REFLASH COMPLETE — Ready to reboot")
        self._log("=" * 60)
        return True

    # ── Reboot helpers ───────────────────────────────────────────────────────

    def reboot_to_bootloader(self, dry_run: bool = False) -> bool:
        """Reboot the device to fastboot/bootloader mode."""
        self._log("Rebooting to bootloader…")
        if dry_run:
            self._log("[dry-run] Would reboot to bootloader")
            return True
        ok = AdbManager.reboot(self.serial, "bootloader")
        if not ok:
            # Already in fastboot — try fastboot reboot-bootloader
            ok = FastbootManager.reboot(self.serial, "bootloader")
        return ok

    def reboot_to_system(self, dry_run: bool = False) -> bool:
        """Reboot the device to the normal Android system."""
        self._log("Rebooting to system…")
        if dry_run:
            self._log("[dry-run] Would reboot to system")
            return True
        return FastbootManager.reboot(self.serial)
