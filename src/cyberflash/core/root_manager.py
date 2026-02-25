"""root_manager.py — Magisk / KernelSU / APatch root workflow orchestration.

All methods are synchronous and must be called from worker threads (never the
main thread).  They communicate via return values — the calling worker emits
signals.

Supported root managers:
  - Magisk  (com.topjohnwu.magisk)
  - KernelSU (me.weishu.kernelsu)
  - APatch  (me.bmax.apatch)
"""

from __future__ import annotations

import logging
import time
from enum import StrEnum
from pathlib import Path

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.fastboot_manager import FastbootManager

logger = logging.getLogger(__name__)

# ── Package identifiers ──────────────────────────────────────────────────────

_MAGISK_PKG     = "com.topjohnwu.magisk"
_KERNELSU_PKG   = "me.weishu.kernelsu"
_APATCH_PKG     = "me.bmax.apatch"

_ROOT_PACKAGES = {
    _MAGISK_PKG:   "Magisk",
    _KERNELSU_PKG: "KernelSU",
    _APATCH_PKG:   "APatch",
}

# Remote path where boot images are pushed for patching
_REMOTE_BOOT_DIR  = "/sdcard/Download/"
_REMOTE_BOOT_NAME = "cyberflash_boot.img"
_REMOTE_BOOT_PATH = _REMOTE_BOOT_DIR + _REMOTE_BOOT_NAME

# Module install path used by Magisk
_MAGISK_MODULES_DIR = "/data/adb/modules/"


# ── Root state enum ──────────────────────────────────────────────────────────

class RootState(StrEnum):
    ROOTED_MAGISK   = "rooted_magisk"
    ROOTED_KERNELSU = "rooted_kernelsu"
    ROOTED_APATCH   = "rooted_apatch"
    ROOTED_OTHER    = "rooted_other"
    NOT_ROOTED      = "not_rooted"
    UNAUTHORIZED    = "unauthorized"
    UNKNOWN         = "unknown"

    @property
    def label(self) -> str:
        return {
            RootState.ROOTED_MAGISK:   "Rooted (Magisk)",
            RootState.ROOTED_KERNELSU: "Rooted (KernelSU)",
            RootState.ROOTED_APATCH:   "Rooted (APatch)",
            RootState.ROOTED_OTHER:    "Rooted",
            RootState.NOT_ROOTED:      "Not Rooted",
            RootState.UNAUTHORIZED:    "Unauthorized",
            RootState.UNKNOWN:         "Unknown",
        }[self]

    @property
    def badge_variant(self) -> str:
        if self in (
            RootState.ROOTED_MAGISK,
            RootState.ROOTED_KERNELSU,
            RootState.ROOTED_APATCH,
            RootState.ROOTED_OTHER,
        ):
            return "success"
        if self == RootState.UNAUTHORIZED:
            return "warning"
        return "neutral"


# ── Main class ───────────────────────────────────────────────────────────────

class RootManager:
    """Orchestrates boot-image patching and root-manager operations.

    All classmethods; no instance state needed.
    """

    # ── Detection ────────────────────────────────────────────────────────────

    @classmethod
    def detect_root_state(cls, serial: str) -> RootState:
        """Determine root state by checking su and installed root packages.

        Tries ADB shell ``su -c id`` first; on success identifies which
        package manages root by checking installed packages.
        """
        # Check su access
        out = AdbManager.shell(serial, "su -c id 2>/dev/null", timeout=6).strip()
        is_rooted = "uid=0" in out

        if not is_rooted:
            # Might still have a root app installed but not yet granted
            for pkg, name in _ROOT_PACKAGES.items():
                installed = AdbManager.shell(
                    serial, f"pm list packages {pkg} 2>/dev/null", timeout=5
                )
                if pkg in installed:
                    logger.info("Root package found but su not granted: %s", name)
                    return RootState.NOT_ROOTED
            return RootState.NOT_ROOTED

        # Identify which manager is present
        for pkg, state_key in [
            (_MAGISK_PKG,   RootState.ROOTED_MAGISK),
            (_KERNELSU_PKG, RootState.ROOTED_KERNELSU),
            (_APATCH_PKG,   RootState.ROOTED_APATCH),
        ]:
            check = AdbManager.shell(
                serial, f"pm list packages {pkg} 2>/dev/null", timeout=5
            )
            if pkg in check:
                logger.info("Root detected: %s", state_key)
                return state_key

        logger.info("Root detected: unrecognised root manager")
        return RootState.ROOTED_OTHER

    @classmethod
    def get_magisk_version(cls, serial: str) -> str:
        """Return Magisk version string or '' if not installed."""
        out = AdbManager.shell(
            serial,
            f"dumpsys package {_MAGISK_PKG} 2>/dev/null | grep versionName",
            timeout=5,
        )
        for line in out.splitlines():
            if "versionName" in line:
                return line.split("=", 1)[-1].strip()
        return ""

    @classmethod
    def is_magisk_installed(cls, serial: str) -> bool:
        out = AdbManager.shell(
            serial, f"pm list packages {_MAGISK_PKG} 2>/dev/null", timeout=5
        )
        return _MAGISK_PKG in out

    # ── Boot image patching workflow ─────────────────────────────────────────

    @classmethod
    def push_boot_for_patching(cls, serial: str, local_img: str | Path) -> bool:
        """Push a boot.img to the device for Magisk to patch.

        Places the file at ``/sdcard/Download/cyberflash_boot.img``.

        Returns:
            True on success.
        """
        local_img = Path(local_img)
        if not local_img.exists():
            logger.error("boot.img not found: %s", local_img)
            return False

        logger.info("Pushing %s → %s", local_img.name, _REMOTE_BOOT_PATH)
        ok = AdbManager.push(serial, str(local_img), _REMOTE_BOOT_PATH, timeout=120)
        if not ok:
            logger.error("Push failed")
        return ok

    @classmethod
    def launch_magisk(cls, serial: str) -> bool:
        """Launch the Magisk app on the device via ADB intent."""
        cmd = (
            f"am start -n {_MAGISK_PKG}/.ui.MainActivity "
            f"--es 'action' 'install' 2>/dev/null"
        )
        out = AdbManager.shell(serial, cmd, timeout=8)
        ok = "Error" not in out and "Exception" not in out
        if ok:
            logger.info("Magisk launched on %s", serial)
        else:
            logger.warning("Failed to launch Magisk: %s", out.strip())
        return ok

    @classmethod
    def poll_for_patched_boot(
        cls,
        serial: str,
        poll_interval: float = 3.0,
        timeout: float = 300.0,
    ) -> str:
        """Wait for Magisk to finish patching and return the remote path.

        Polls ``/sdcard/Download/`` for a ``magisk_patched_*.img`` file.

        Returns:
            Remote path string, or ``""`` if timed out.
        """
        deadline = time.monotonic() + timeout
        logger.info("Polling for patched boot image (timeout=%ds)…", int(timeout))

        while time.monotonic() < deadline:
            out = AdbManager.shell(
                serial,
                "ls /sdcard/Download/magisk_patched_*.img 2>/dev/null",
                timeout=5,
            )
            lines = [ln.strip() for ln in out.splitlines() if ln.strip().endswith(".img")]
            if lines:
                # Take the newest one
                newest = sorted(lines)[-1]
                logger.info("Patched boot found: %s", newest)
                return newest
            time.sleep(poll_interval)

        logger.warning("Timed out waiting for patched boot image")
        return ""

    @classmethod
    def pull_patched_boot(
        cls, serial: str, remote_path: str, dest_dir: str | Path
    ) -> Path | None:
        """Pull a patched boot image from device to local *dest_dir*.

        Returns:
            Local Path on success, None on failure.
        """
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        filename = remote_path.rsplit("/", maxsplit=1)[-1]
        local_path = dest_dir / filename

        ok = AdbManager.pull(serial, remote_path, str(local_path), timeout=120)
        if ok:
            logger.info("Pulled patched boot → %s", local_path)
            return local_path
        logger.error("Failed to pull patched boot from %s", remote_path)
        return None

    # ── Boot flashing ─────────────────────────────────────────────────────────

    @classmethod
    def flash_boot(
        cls,
        serial: str,
        img_path: str | Path,
        dry_run: bool = False,
    ) -> bool:
        """Flash a boot.img via fastboot.

        Device must already be in fastboot mode.

        Returns:
            True on success.
        """
        img_path = Path(img_path)
        if not img_path.exists():
            logger.error("Image not found: %s", img_path)
            return False

        if dry_run:
            logger.info("[dry-run] fastboot flash boot %s", img_path)
            return True

        logger.info("Flashing boot: %s on %s", img_path.name, serial)
        rc, _, stderr = FastbootManager._run(
            ["-s", serial, "flash", "boot", str(img_path)]
        )
        if rc != 0:
            logger.error("fastboot flash boot failed: %s", stderr)
            return False
        return True

    # ── Magisk modules ────────────────────────────────────────────────────────

    @classmethod
    def get_magisk_modules(cls, serial: str) -> list[dict[str, str]]:
        """Return list of installed Magisk modules.

        Each dict has keys: ``id``, ``name``, ``version``, ``author``,
        ``description``, ``enabled``.

        Returns empty list if not rooted or Magisk not installed.
        """
        out = AdbManager.shell(
            serial,
            f"su -c 'ls -1 {_MAGISK_MODULES_DIR}' 2>/dev/null",
            timeout=8,
        )
        module_ids = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if not module_ids:
            return []

        modules: list[dict[str, str]] = []
        for mod_id in module_ids:
            mod_dir = _MAGISK_MODULES_DIR + mod_id
            props = AdbManager.shell(
                serial,
                f"su -c 'cat {mod_dir}/module.prop 2>/dev/null'",
                timeout=5,
            )
            info: dict[str, str] = {"id": mod_id, "enabled": "true"}
            for line in props.splitlines():
                if "=" in line:
                    key, _, val = line.partition("=")
                    info[key.strip()] = val.strip()

            # Check if module is disabled (disabled file exists)
            dis = AdbManager.shell(
                serial,
                f"su -c 'test -f {mod_dir}/.disable && echo disabled'",
                timeout=4,
            )
            if "disabled" in dis:
                info["enabled"] = "false"

            modules.append(info)

        logger.info("Found %d Magisk modules on %s", len(modules), serial)
        return modules

    @classmethod
    def install_magisk_module(
        cls, serial: str, zip_path: str | Path, dry_run: bool = False
    ) -> bool:
        """Install a Magisk module ZIP via Magisk's module install mechanism.

        Pushes the ZIP to ``/sdcard/Download/``, then triggers installation
        via the Magisk app intent.

        Returns:
            True if push and intent launch succeeded.
        """
        zip_path = Path(zip_path)
        if not zip_path.exists():
            logger.error("Module ZIP not found: %s", zip_path)
            return False

        remote = _REMOTE_BOOT_DIR + zip_path.name
        if dry_run:
            logger.info("[dry-run] push %s → %s and launch Magisk install", zip_path, remote)
            return True

        logger.info("Pushing module: %s → %s", zip_path.name, remote)
        if not AdbManager.push(serial, str(zip_path), remote, timeout=120):
            logger.error("Failed to push module ZIP")
            return False

        # Trigger Magisk's local install via intent
        intent = (
            f"am start -n {_MAGISK_PKG}/.ui.MainActivity "
            f"--es 'action' 'flash' --es 'uri' 'file://{remote}' 2>/dev/null"
        )
        out = AdbManager.shell(serial, intent, timeout=8)
        ok = "Error" not in out and "Exception" not in out
        if not ok:
            logger.warning("Magisk install intent may have failed: %s", out.strip())
        return ok

    @classmethod
    def uninstall_magisk_module(
        cls, serial: str, module_id: str, dry_run: bool = False
    ) -> bool:
        """Mark a module for removal (creates .remove flag; takes effect on next reboot)."""
        flag = _MAGISK_MODULES_DIR + module_id + "/.remove"
        if dry_run:
            logger.info("[dry-run] touch %s", flag)
            return True
        out = AdbManager.shell(serial, f"su -c 'touch {flag}' 2>/dev/null", timeout=5)
        ok = "Permission denied" not in out and "not found" not in out
        logger.info("Marked module %s for removal (reboot required)", module_id)
        return ok

    @classmethod
    def toggle_magisk_module(
        cls, serial: str, module_id: str, enable: bool, dry_run: bool = False
    ) -> bool:
        """Enable or disable a Magisk module (takes effect on next reboot)."""
        flag = _MAGISK_MODULES_DIR + module_id + "/.disable"
        cmd = f"su -c 'rm -f {flag}' 2>/dev/null" if enable else f"su -c 'touch {flag}' 2>/dev/null"

        if dry_run:
            logger.info("[dry-run] %s module %s", "enable" if enable else "disable", module_id)
            return True

        AdbManager.shell(serial, cmd, timeout=5)
        logger.info("%s module %s (reboot required)", "Enabled" if enable else "Disabled", module_id)
        return True

    # ── KernelSU ─────────────────────────────────────────────────────────────

    @classmethod
    def get_kernelsu_version(cls, serial: str) -> str:
        """Return KernelSU version string or '' if not installed."""
        out = AdbManager.shell(
            serial,
            f"dumpsys package {_KERNELSU_PKG} 2>/dev/null | grep versionName",
            timeout=5,
        )
        for line in out.splitlines():
            if "versionName" in line:
                return line.split("=", 1)[-1].strip()
        return ""

    @classmethod
    def get_kernelsu_modules(cls, serial: str) -> list[dict[str, str]]:
        """Return list of installed KernelSU modules.

        Each dict has keys: ``id``, ``name``, ``version``, ``author``,
        ``description``, ``enabled``.
        """
        out = AdbManager.shell(
            serial,
            "su -c 'ls -1 /data/adb/ksu/modules/ 2>/dev/null'",
            timeout=8,
        )
        module_ids = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if not module_ids:
            return []

        modules: list[dict[str, str]] = []
        for mod_id in module_ids:
            mod_dir = f"/data/adb/ksu/modules/{mod_id}"
            props = AdbManager.shell(
                serial,
                f"su -c 'cat {mod_dir}/module.prop 2>/dev/null'",
                timeout=5,
            )
            info: dict[str, str] = {"id": mod_id, "enabled": "true"}
            for line in props.splitlines():
                if "=" in line:
                    key, _, val = line.partition("=")
                    info[key.strip()] = val.strip()

            dis = AdbManager.shell(
                serial,
                f"su -c 'test -f {mod_dir}/.disable && echo disabled'",
                timeout=4,
            )
            if "disabled" in dis:
                info["enabled"] = "false"

            modules.append(info)

        logger.info("Found %d KernelSU modules on %s", len(modules), serial)
        return modules

    @classmethod
    def install_kernelsu_module(
        cls, serial: str, zip_path: str | Path, dry_run: bool = False
    ) -> bool:
        """Install a KernelSU module ZIP via ksud."""
        zip_path = Path(zip_path)
        if not zip_path.exists():
            logger.error("Module ZIP not found: %s", zip_path)
            return False

        remote = _REMOTE_BOOT_DIR + zip_path.name
        if dry_run:
            logger.info("[dry-run] ksud module install %s", remote)
            return True

        if not AdbManager.push(serial, str(zip_path), remote, timeout=120):
            logger.error("Failed to push KernelSU module ZIP")
            return False

        out = AdbManager.shell(
            serial,
            f"su -c 'ksud module install {remote} 2>&1'",
            timeout=30,
        )
        ok = "Success" in out or "success" in out or "installed" in out.lower()
        if not ok:
            logger.warning("KernelSU module install may have failed: %s", out.strip())
        return ok

    @classmethod
    def get_root_profiles(cls, serial: str) -> list[dict[str, str]]:
        """Return per-app KernelSU root grant profiles.

        Each dict has keys: ``uid``, ``package``, ``profile``, ``allow``.
        Reads from KernelSU's profile database.
        """
        out = AdbManager.shell(
            serial,
            "su -c 'ksud profile list 2>/dev/null'",
            timeout=8,
        )
        profiles: list[dict[str, str]] = []
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                profiles.append({"uid": parts[0], "package": parts[1],
                                  "allow": parts[2] if len(parts) > 2 else "unknown"})
        return profiles

    @classmethod
    def get_superuser_log(cls, serial: str, limit: int = 50) -> list[dict[str, str]]:
        """Return recent superuser grant/deny log entries.

        Works with Magisk and KernelSU. Each dict has:
        ``time``, ``package``, ``action``.
        """
        # Try Magisk log first
        out = AdbManager.shell(
            serial,
            f"su -c 'cat /data/adb/magisk/magisk.log 2>/dev/null | tail -n {limit}'",
            timeout=8,
        )
        entries: list[dict[str, str]] = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            # Typical format: "I  [timestamp] policy: allow/deny package=..."
            if "allow" in line.lower() or "deny" in line.lower():
                action = "allow" if "allow" in line.lower() else "deny"
                pkg = ""
                for tok in line.split():
                    if tok.startswith(("package=", "pkg=")):
                        pkg = tok.split("=", 1)[1]
                entries.append({"time": "", "package": pkg or line[:40], "action": action})

        if not entries:
            # Try KernelSU audit log
            out = AdbManager.shell(
                serial,
                f"su -c 'ksud log list 2>/dev/null | tail -n {limit}'",
                timeout=8,
            )
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                action = "allow" if "allow" in line.lower() else "deny"
                entries.append({"time": "", "package": line[:60], "action": action})

        return entries[-limit:]

    # ── dm-verity & Force-Encryption ─────────────────────────────────────────

    @classmethod
    def disable_dm_verity(cls, serial: str, dry_run: bool = False) -> bool:
        """Disable dm-verity by flashing vbmeta with --disable-verity flag via fastboot.

        Device must already be in fastboot mode.
        """
        if dry_run:
            logger.info("[dry-run] fastboot --disable-verity flash vbmeta")
            return True

        # Check if vbmeta partition exists; use vbmeta_a for A/B devices
        rc, out, _ = FastbootManager._run(["-s", serial, "getvar", "partition-type:vbmeta"])
        partition = "vbmeta_a" if rc != 0 and "vbmeta" not in out else "vbmeta"

        rc, _, stderr = FastbootManager._run([
            "-s", serial, "--disable-verity", "--disable-verification",
            "flash", partition,
        ])
        if rc != 0:
            logger.error("Failed to disable dm-verity: %s", stderr)
            return False
        logger.info("dm-verity disabled on %s", serial)
        return True

    @classmethod
    def disable_force_encryption(cls, serial: str, dry_run: bool = False) -> bool:
        """Disable forced encryption by patching fstab via root ADB.

        Requires root access (device in ADB mode, rooted).
        """
        if dry_run:
            logger.info("[dry-run] sed forceencrypt→encryptable in fstab")
            return True

        # Find fstab file(s) — location varies by device
        out = AdbManager.shell(
            serial,
            "su -c 'find /vendor /system -name \"fstab.*\" 2>/dev/null | head -5'",
            timeout=8,
        )
        fstabs = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if not fstabs:
            logger.warning("No fstab found — cannot disable encryption")
            return False

        patched = 0
        for fstab in fstabs:
            res = AdbManager.shell(
                serial,
                f"su -c 'sed -i s/forceencrypt/encryptable/g {fstab} 2>&1'",
                timeout=8,
            )
            if "Permission denied" not in res:
                patched += 1
                logger.info("Patched force-encryption in %s", fstab)

        return patched > 0

    @classmethod
    def get_avb_info(cls, serial: str) -> dict[str, str]:
        """Return AVB (Android Verified Boot) info from fastboot.

        Returns dict with keys: ``vbmeta_digest``, ``avb_state``,
        ``verity_mode``, ``verified_boot_state``.
        """
        info: dict[str, str] = {}
        for var in ("vbmeta-digest", "avb-state", "verity-mode", "verified-boot-state"):
            rc, out, _ = FastbootManager._run(["-s", serial, "getvar", var])
            if rc == 0:
                for line in (out or "").splitlines():
                    if var in line and ":" in line:
                        info[var.replace("-", "_")] = line.split(":", 1)[1].strip()
        return info

    # ── Root Hide / DenyList Manager ─────────────────────────────────────────

    @classmethod
    def get_denylist(cls, serial: str) -> list[str]:
        """Return packages on the Magisk / Zygisk DenyList.

        Returns a list of package names.
        """
        out = AdbManager.shell(
            serial,
            "su -c 'magisk --denylist ls 2>/dev/null'",
            timeout=8,
        )
        packages: list[str] = []
        for line in out.splitlines():
            line = line.strip()
            if line and "/" not in line:  # skip component lines like pkg/activity
                packages.append(line.split("|")[0].strip())
        return [p for p in packages if p]

    @classmethod
    def add_to_denylist(
        cls, serial: str, package: str, dry_run: bool = False
    ) -> bool:
        """Add a package to the Magisk DenyList."""
        if dry_run:
            logger.info("[dry-run] magisk --denylist add %s", package)
            return True
        out = AdbManager.shell(
            serial,
            f"su -c 'magisk --denylist add {package} 2>&1'",
            timeout=6,
        )
        ok = "Error" not in out and "failed" not in out.lower()
        logger.info("Added %s to DenyList: %s", package, ok)
        return ok

    @classmethod
    def remove_from_denylist(
        cls, serial: str, package: str, dry_run: bool = False
    ) -> bool:
        """Remove a package from the Magisk DenyList."""
        if dry_run:
            logger.info("[dry-run] magisk --denylist rm %s", package)
            return True
        out = AdbManager.shell(
            serial,
            f"su -c 'magisk --denylist rm {package} 2>&1'",
            timeout=6,
        )
        ok = "Error" not in out and "failed" not in out.lower()
        logger.info("Removed %s from DenyList: %s", package, ok)
        return ok

    @classmethod
    def get_zygisk_enabled(cls, serial: str) -> bool | None:
        """Return True if Zygisk is enabled, False if disabled, None if unknown."""
        out = AdbManager.shell(
            serial,
            "su -c 'magisk --env 2>/dev/null | grep -i zygisk'",
            timeout=5,
        )
        if "enable" in out.lower():
            return True
        if "disable" in out.lower():
            return False
        # Fallback: check Magisk settings DB
        out = AdbManager.shell(
            serial,
            "su -c 'sqlite3 /data/adb/magisk/magisk.db "
            "\"SELECT value FROM settings WHERE key=\\\"zygisk\\\"\" 2>/dev/null'",
            timeout=6,
        )
        if out.strip() == "1":
            return True
        if out.strip() == "0":
            return False
        return None

    _BANKING_PACKAGES: list[str] = [
        "com.chase.sig",
        "com.google.android.apps.walletnfcrel",
        "com.samsung.android.spay",
        "com.paypal.android.p2pmobile",
        "com.squareup.cash",
        "com.venmo",
        "com.coinbase.android",
        "com.netflix.mediaclient",
    ]

    @classmethod
    def apply_banking_safe_preset(
        cls, serial: str, dry_run: bool = False
    ) -> tuple[int, int]:
        """Add all known banking/SafetyNet-sensitive apps to DenyList.

        Returns:
            Tuple of (added_count, already_present_count).
        """
        added = 0
        skipped = 0
        existing = set(cls.get_denylist(serial))
        for pkg in cls._BANKING_PACKAGES:
            if pkg in existing:
                skipped += 1
                continue
            if cls.add_to_denylist(serial, pkg, dry_run=dry_run):
                added += 1
        logger.info("Banking-safe preset: added=%d skipped=%d", added, skipped)
        return added, skipped
