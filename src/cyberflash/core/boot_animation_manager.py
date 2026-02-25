"""boot_animation_manager.py — Android boot animation manager.

Android boot animations are ZIP archives (``bootanimation.zip``) containing:
  - ``desc.txt``   — animation descriptor: width height fps, followed by part lines
  - ``partN/``     — directories of PNG frames for each animation part

Part line format in desc.txt:
  p <count> <pause> <folder>   (count=0 → loop forever)
  c <count> <pause> <folder>   (c = "complete" variant)

All methods are synchronous and UI-agnostic (no Qt imports).
Root access is required for most device operations.
"""

from __future__ import annotations

import logging
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# Standard bootanimation location on AOSP devices
_BOOTANIM_PATHS = [
    "/system/media/bootanimation.zip",
    "/product/media/bootanimation.zip",
    "/vendor/media/bootanimation.zip",
    "/oem/media/bootanimation.zip",
]

_BACKUP_SUFFIX = ".bak"
_BOOTANIM_FILENAME = "bootanimation.zip"


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class AnimationPart:
    """One animation segment from desc.txt."""
    count:    int      # 0 = loop forever
    pause:    int      # frames to pause after part
    folder:   str      # sub-directory name
    variant:  str = "p"   # "p" or "c"


@dataclass
class BootAnimationInfo:
    """Metadata parsed from a bootanimation.zip desc.txt."""
    width:    int = 0
    height:   int = 0
    fps:      int = 0
    parts:    list[AnimationPart] = field(default_factory=list)
    total_frames: int = 0
    is_valid: bool = False
    error:    str = ""


@dataclass
class BootAnimResult:
    success:  bool
    path:     str = ""
    error:    str = ""


# ── Main class ────────────────────────────────────────────────────────────────

class BootAnimationManager:
    """Manage Android boot animations on a connected device."""

    # ── Inspection ────────────────────────────────────────────────────────────

    @classmethod
    def parse_zip(cls, zip_path: str | Path) -> BootAnimationInfo:
        """Parse metadata from a bootanimation.zip file.

        Reads ``desc.txt`` and counts PNG frames across all part folders.
        """
        info = BootAnimationInfo()
        zip_path = Path(zip_path)

        if not zip_path.exists():
            info.error = f"File not found: {zip_path}"
            return info

        try:
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                if "desc.txt" not in names:
                    info.error = "Missing desc.txt — not a valid bootanimation.zip"
                    return info

                desc = zf.read("desc.txt").decode("utf-8", errors="replace")
                info = cls._parse_desc(desc)
                if not info.is_valid:
                    return info

                # Count total PNG frames
                total = 0
                for part in info.parts:
                    total += sum(1 for n in names if n.startswith(part.folder + "/") and n.endswith(".png"))
                info.total_frames = total

        except (zipfile.BadZipFile, OSError) as exc:
            info.error = str(exc)

        return info

    @classmethod
    def _parse_desc(cls, desc: str) -> BootAnimationInfo:
        info = BootAnimationInfo()
        lines = [ln.strip() for ln in desc.splitlines() if ln.strip()]
        if not lines:
            info.error = "Empty desc.txt"
            return info

        # First line: width height fps
        try:
            parts = lines[0].split()
            info.width, info.height, info.fps = int(parts[0]), int(parts[1]), int(parts[2])
        except (IndexError, ValueError) as exc:
            info.error = f"Bad desc.txt header: {exc}"
            return info

        # Remaining lines: p/c <count> <pause> <folder>
        for line in lines[1:]:
            tokens = line.split()
            if len(tokens) < 4:
                continue
            variant, count_s, pause_s, folder = tokens[0], tokens[1], tokens[2], tokens[3]
            if variant not in ("p", "c"):
                continue
            try:
                info.parts.append(AnimationPart(
                    count=int(count_s),
                    pause=int(pause_s),
                    folder=folder,
                    variant=variant,
                ))
            except ValueError:
                continue

        info.is_valid = bool(info.parts)
        if not info.is_valid:
            info.error = "No valid animation parts found in desc.txt"

        return info

    # ── Device operations ─────────────────────────────────────────────────────

    @classmethod
    def get_active_path(cls, serial: str) -> str:
        """Return the path of the active bootanimation.zip on the device."""
        for path in _BOOTANIM_PATHS:
            out = AdbManager.shell(
                serial,
                f"su -c 'test -f {path} && echo exists'",
                timeout=5,
            )
            if "exists" in out:
                return path
        return ""

    @classmethod
    def backup(
        cls,
        serial:   str,
        dest_dir: str | Path,
        dry_run:  bool = False,
    ) -> BootAnimResult:
        """Pull the current bootanimation.zip from the device to *dest_dir*.

        Creates a backup with ``.bak`` extension alongside any existing file.
        """
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        active = cls.get_active_path(serial)
        if not active:
            return BootAnimResult(success=False, error="No bootanimation.zip found on device")

        dest = dest_dir / _BOOTANIM_FILENAME

        if dry_run:
            logger.info("[dry-run] adb pull %s → %s", active, dest)
            return BootAnimResult(success=True, path=str(dest))

        # Backup existing if present
        if dest.exists():
            shutil.move(str(dest), str(dest.with_suffix(_BACKUP_SUFFIX)))

        ok = AdbManager.pull(serial, active, str(dest), timeout=60)
        if not ok:
            return BootAnimResult(success=False, error=f"Failed to pull {active}")

        logger.info("Boot animation backed up → %s", dest)
        return BootAnimResult(success=True, path=str(dest))

    @classmethod
    def install(
        cls,
        serial:   str,
        zip_path: str | Path,
        dry_run:  bool = False,
    ) -> BootAnimResult:
        """Push and install a bootanimation.zip to the device.

        Requires root. Installs to the first writable path in ``_BOOTANIM_PATHS``.
        """
        zip_path = Path(zip_path)
        if not zip_path.exists():
            return BootAnimResult(success=False, error=f"File not found: {zip_path}")

        # Validate the ZIP first
        info = cls.parse_zip(zip_path)
        if not info.is_valid:
            return BootAnimResult(success=False, error=f"Invalid bootanimation.zip: {info.error}")

        target = cls.get_active_path(serial) or _BOOTANIM_PATHS[0]
        remote_tmp = "/sdcard/Download/bootanimation_cyberflash.zip"

        if dry_run:
            logger.info("[dry-run] install %s → %s", zip_path.name, target)
            return BootAnimResult(success=True, path=target)

        # Push to /sdcard first (no root needed for this step)
        if not AdbManager.push(serial, str(zip_path), remote_tmp, timeout=60):
            return BootAnimResult(success=False, error="Failed to push bootanimation.zip to device")

        # Move to system path with root
        res = AdbManager.shell(
            serial,
            f"su -c 'cp {remote_tmp} {target} && chmod 644 {target}' 2>&1",
            timeout=15,
        )
        if "Permission denied" in res or "error" in res.lower():
            return BootAnimResult(success=False, error=f"Root copy failed: {res.strip()}")

        # Cleanup temp file
        AdbManager.shell(serial, f"rm -f {remote_tmp} 2>/dev/null", timeout=5)
        logger.info("Boot animation installed: %s → %s", zip_path.name, target)
        return BootAnimResult(success=True, path=target)

    @classmethod
    def restore_backup(
        cls,
        serial:      str,
        backup_path: str | Path,
        dry_run:     bool = False,
    ) -> BootAnimResult:
        """Restore a previously backed-up bootanimation.zip to the device."""
        return cls.install(serial, backup_path, dry_run=dry_run)

    @classmethod
    def reset_to_stock(
        cls,
        serial:  str,
        dry_run: bool = False,
    ) -> BootAnimResult:
        """Remove any custom bootanimation so the device falls back to the built-in one.

        Simply deletes the bootanimation.zip from the system partition (root required).
        The default OEM animation is embedded in the system image and cannot be deleted.
        """
        active = cls.get_active_path(serial)
        if not active:
            return BootAnimResult(success=True, path="", error="No custom bootanimation found")

        if dry_run:
            logger.info("[dry-run] su -c 'rm %s'", active)
            return BootAnimResult(success=True, path=active)

        out = AdbManager.shell(
            serial,
            f"su -c 'rm -f {active}' 2>&1",
            timeout=10,
        )
        if "Permission denied" in out:
            return BootAnimResult(success=False, error=f"Root required to remove {active}")

        logger.info("Removed custom bootanimation from %s", active)
        return BootAnimResult(success=True, path=active)

    # ── Local ZIP utilities ───────────────────────────────────────────────────

    @classmethod
    def list_frames(cls, zip_path: str | Path) -> dict[str, list[str]]:
        """Return a dict mapping part folder → list of PNG frame names.

        Useful for building a preview widget.
        """
        frames: dict[str, list[str]] = {}
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for name in sorted(zf.namelist()):
                    if "/" in name and name.endswith(".png"):
                        folder, filename = name.split("/", 1)
                        frames.setdefault(folder, []).append(filename)
        except (zipfile.BadZipFile, OSError):
            pass
        return frames

    @classmethod
    def extract_frame(cls, zip_path: str | Path, frame_path: str) -> bytes | None:
        """Extract a single PNG frame from the ZIP.  Returns raw bytes or None."""
        try:
            with zipfile.ZipFile(zip_path) as zf:
                return zf.read(frame_path)
        except (KeyError, zipfile.BadZipFile, OSError):
            return None
