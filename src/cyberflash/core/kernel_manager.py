"""kernel_manager.py — AnyKernel3 kernel flash + rollback manager.

AnyKernel3 is the de-facto standard for flashing custom kernels on Android.
The ZIP contains a META-INF/com/google/android/update-binary script that
handles partition detection and flashing automatically.

Flash paths supported:
  1. Recovery sideload (ADB sideload)
  2. Direct ADB push + Magisk / TWRP install via intent

All methods are synchronous and UI-agnostic.
"""

from __future__ import annotations

import logging
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.fastboot_manager import FastbootManager
from cyberflash.core.tool_manager import ToolManager

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# AnyKernel3 identification marker inside the ZIP
_AK3_MARKER     = "META-INF/com/google/android/update-binary"
_AK3_PROP_FILE  = "anykernel.sh"

# Where to push kernel ZIPs on device
_REMOTE_FLASH_DIR = "/sdcard/Download/"

# Backup filename template
_KERNEL_BACKUP_NAME = "kernel_backup_{serial}.img"


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class KernelInfo:
    """Metadata extracted from an AnyKernel3 ZIP."""
    kernel_name:  str = ""
    kernel_ver:   str = ""
    author:       str = ""
    device:       str = ""
    do_devicecheck: bool = True
    anykernel_ver:  int = 3
    is_valid:     bool = False
    raw_props:    dict[str, str] = field(default_factory=dict)


@dataclass
class KernelFlashResult:
    success:     bool
    method:      str          # "sideload" | "adb_push" | "dry_run"
    kernel_ver:  str = ""
    error:       str = ""


# ── Main class ────────────────────────────────────────────────────────────────

class KernelManager:
    """AnyKernel3 kernel flash, inspection, and rollback."""

    # ── Inspection ────────────────────────────────────────────────────────────

    @classmethod
    def is_anykernel3_zip(cls, zip_path: str | Path) -> bool:
        """Return True if *zip_path* is an AnyKernel3 flashable ZIP."""
        try:
            with zipfile.ZipFile(zip_path) as zf:
                return _AK3_MARKER in zf.namelist()
        except (zipfile.BadZipFile, OSError):
            return False

    @classmethod
    def inspect_zip(cls, zip_path: str | Path) -> KernelInfo:
        """Parse AnyKernel3 properties from the ZIP.

        Reads ``anykernel.sh`` for name/version/device metadata.
        """
        info = KernelInfo()
        zip_path = Path(zip_path)

        if not zip_path.exists():
            return info

        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                if _AK3_MARKER not in names:
                    return info

                info.is_valid = True

                # Try to read anykernel.sh properties
                if _AK3_PROP_FILE in names:
                    try:
                        content = zf.read(_AK3_PROP_FILE).decode("utf-8", errors="replace")
                        for line in content.splitlines():
                            line = line.strip()
                            if "=" in line and not line.startswith("#"):
                                key, _, val = line.partition("=")
                                key = key.strip().strip('"')
                                val = val.strip().strip('"').strip("'").strip(";")
                                info.raw_props[key] = val
                    except (KeyError, OSError):
                        pass

                info.kernel_name  = info.raw_props.get("kernel.string", "")
                info.author       = info.raw_props.get("author", "")
                info.device       = info.raw_props.get("device.name1", "")
                info.kernel_ver   = info.raw_props.get("version", "")
                dc = info.raw_props.get("do.devicecheck", "1")
                info.do_devicecheck = dc not in ("0", "false", "no")

                try:
                    info.anykernel_ver = int(info.raw_props.get("do.modules", "3"))
                except ValueError:
                    info.anykernel_ver = 3

        except (zipfile.BadZipFile, OSError) as exc:
            logger.warning("Failed to inspect AnyKernel3 zip: %s", exc)

        return info

    # ── Current kernel version ────────────────────────────────────────────────

    @classmethod
    def get_kernel_version(cls, serial: str) -> str:
        """Return ``uname -r`` output from the connected device."""
        out = AdbManager.shell(serial, "uname -r 2>/dev/null", timeout=6)
        return out.strip()

    # ── Backup ────────────────────────────────────────────────────────────────

    @classmethod
    def backup_boot(
        cls,
        serial:   str,
        dest_dir: str | Path,
        dry_run:  bool = False,
    ) -> Path | None:
        """Pull the current boot.img from the device as a rollback backup.

        Requires fastboot mode; device must already be in fastboot.

        Returns:
            Local Path to backed-up image, or None on failure.
        """
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        safe_serial = serial.replace(":", "_").replace("/", "_")
        dest_file = dest_dir / _KERNEL_BACKUP_NAME.format(serial=safe_serial)

        if dry_run:
            logger.info("[dry-run] fastboot fetch boot → %s", dest_file)
            return dest_file

        with TemporaryDirectory() as tmp:
            tmp_img = Path(tmp) / "boot.img"
            rc, _, stderr = FastbootManager._run(
                ["-s", serial, "fetch:boot", str(tmp_img)]
            )
            if rc != 0:
                # Some devices don't support fetch — try fetch:boot_a
                rc, _, stderr = FastbootManager._run(
                    ["-s", serial, "fetch:boot_a", str(tmp_img)]
                )
            if rc != 0:
                logger.error("Failed to fetch boot image: %s", stderr)
                return None

            shutil.copy2(str(tmp_img), str(dest_file))
            logger.info("Boot backup saved → %s", dest_file)
            return dest_file

    # ── Flash via sideload ────────────────────────────────────────────────────

    @classmethod
    def flash_via_sideload(
        cls,
        serial:   str,
        zip_path: str | Path,
        dry_run:  bool = False,
    ) -> KernelFlashResult:
        """Flash AnyKernel3 ZIP via ADB sideload (recovery must be in sideload mode).

        The caller is responsible for booting the device into recovery / sideload mode.
        """
        zip_path = Path(zip_path)

        if not zip_path.exists():
            return KernelFlashResult(success=False, method="sideload",
                                     error=f"ZIP not found: {zip_path}")

        if not cls.is_anykernel3_zip(zip_path):
            return KernelFlashResult(success=False, method="sideload",
                                     error="Not a valid AnyKernel3 ZIP")

        if dry_run:
            info = cls.inspect_zip(zip_path)
            return KernelFlashResult(success=True, method="dry_run",
                                     kernel_ver=info.kernel_ver)

        logger.info("Sideloading AnyKernel3 ZIP: %s on %s", zip_path.name, serial)
        cmd = [*ToolManager.adb_cmd(), "-s", serial, "sideload", str(zip_path)]
        import subprocess
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                return KernelFlashResult(
                    success=False, method="sideload",
                    error=proc.stderr.strip() or proc.stdout.strip(),
                )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return KernelFlashResult(success=False, method="sideload", error=str(exc))

        logger.info("Sideload complete")
        return KernelFlashResult(success=True, method="sideload")

    # ── Flash via ADB push + Magisk ───────────────────────────────────────────

    @classmethod
    def flash_via_adb_push(
        cls,
        serial:   str,
        zip_path: str | Path,
        dry_run:  bool = False,
    ) -> KernelFlashResult:
        """Push AnyKernel3 ZIP to device and trigger install via Magisk intent.

        Device must be booted normally with Magisk installed and ADB root.
        """
        zip_path = Path(zip_path)

        if not zip_path.exists():
            return KernelFlashResult(success=False, method="adb_push",
                                     error=f"ZIP not found: {zip_path}")

        if not cls.is_anykernel3_zip(zip_path):
            return KernelFlashResult(success=False, method="adb_push",
                                     error="Not a valid AnyKernel3 ZIP")

        remote = _REMOTE_FLASH_DIR + zip_path.name

        if dry_run:
            info = cls.inspect_zip(zip_path)
            return KernelFlashResult(success=True, method="dry_run",
                                     kernel_ver=info.kernel_ver)

        logger.info("Pushing kernel ZIP: %s → %s", zip_path.name, remote)
        if not AdbManager.push(serial, str(zip_path), remote, timeout=180):
            return KernelFlashResult(success=False, method="adb_push",
                                     error="ADB push failed")

        # Trigger install via Magisk flash intent
        intent = (
            "am start -n com.topjohnwu.magisk/.ui.MainActivity "
            f"--es 'action' 'flash' --es 'uri' 'file://{remote}' 2>/dev/null"
        )
        out = AdbManager.shell(serial, intent, timeout=10)
        ok = "Error" not in out and "Exception" not in out

        if not ok:
            logger.warning("Magisk flash intent may have failed: %s", out.strip())

        return KernelFlashResult(success=ok, method="adb_push",
                                 error="" if ok else out.strip())

    # ── Post-flash verification ───────────────────────────────────────────────

    @classmethod
    def verify_kernel_version(
        cls,
        serial:   str,
        expected: str,
    ) -> tuple[bool, str]:
        """Verify the running kernel version matches *expected* after a flash.

        Returns:
            (matches, actual_version) tuple.
        """
        actual = cls.get_kernel_version(serial)
        if not actual:
            return False, ""
        # Partial match — kernel string may include extra build info
        matches = expected.strip() in actual or actual in expected.strip()
        if matches:
            logger.info("Kernel version verified: %s", actual)
        else:
            logger.warning("Kernel mismatch: expected=%r actual=%r", expected, actual)
        return matches, actual

    # ── Rollback ──────────────────────────────────────────────────────────────

    @classmethod
    def restore_boot_backup(
        cls,
        serial:      str,
        backup_path: str | Path,
        dry_run:     bool = False,
    ) -> bool:
        """Flash a previously backed-up boot.img via fastboot.

        Device must be in fastboot mode.
        """
        backup_path = Path(backup_path)
        if not backup_path.exists():
            logger.error("Backup not found: %s", backup_path)
            return False

        if dry_run:
            logger.info("[dry-run] fastboot flash boot %s", backup_path)
            return True

        logger.info("Restoring boot backup: %s on %s", backup_path.name, serial)
        rc, _, stderr = FastbootManager._run(
            ["-s", serial, "flash", "boot", str(backup_path)]
        )
        if rc != 0:
            logger.error("Failed to restore boot: %s", stderr)
            return False

        # Try boot_a slot as well for A/B devices
        FastbootManager._run(["-s", serial, "flash", "boot_a", str(backup_path)])
        logger.info("Boot backup restored on %s", serial)
        return True
