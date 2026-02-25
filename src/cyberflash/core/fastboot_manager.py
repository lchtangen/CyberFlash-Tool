from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from cyberflash.core.tool_manager import ToolManager
from cyberflash.models.device import DeviceInfo

logger = logging.getLogger(__name__)


class FastbootManager:
    """Synchronous fastboot command executor. Always call from worker threads."""

    DEFAULT_TIMEOUT = 15

    @classmethod
    def _run(
        cls,
        args: list[str],
        timeout: int | None = None,
    ) -> tuple[int, str, str]:
        cmd = ToolManager.fastboot_cmd() + args
        t = timeout or cls.DEFAULT_TIMEOUT
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
            return r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            logger.warning("Fastboot timeout: %s", " ".join(cmd))
            return -1, "", "timeout"
        except FileNotFoundError:
            logger.error("Fastboot binary not found")
            return -1, "", "fastboot not found"
        except Exception as exc:
            logger.error("Fastboot error: %s", exc)
            return -1, "", str(exc)

    # ── Device listing ───────────────────────────────────────────────────────

    @classmethod
    def list_devices(cls) -> list[tuple[str, str]]:
        """Return list of (serial, state_string) pairs."""
        _, stdout, stderr = cls._run(["devices"])
        devices: list[tuple[str, str]] = []
        for line in (stdout + stderr).splitlines():
            line = line.strip()
            if not line or "\t" not in line:
                continue
            serial, _, state = line.partition("\t")
            serial = serial.strip()
            state = state.strip()
            if serial and state:
                devices.append((serial, state))
        return devices

    # ── Variable access ──────────────────────────────────────────────────────

    @classmethod
    def get_var(cls, serial: str, variable: str) -> str:
        """fastboot getvar prints to stderr."""
        _, stdout, stderr = cls._run(["-s", serial, "getvar", variable])
        for line in (stderr + stdout).splitlines():
            if line.lower().startswith(f"{variable}:"):
                return line.split(":", 1)[1].strip()
        return ""

    @classmethod
    def get_all_vars(cls, serial: str) -> dict[str, str]:
        _, stdout, stderr = cls._run(["-s", serial, "getvar", "all"])
        result: dict[str, str] = {}
        for line in (stderr + stdout).splitlines():
            if ":" not in line:
                continue
            if line.startswith(("OKAY", "FAILED")):
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key and value:
                result[key] = value
        return result

    # ── Flash operations ─────────────────────────────────────────────────────

    @classmethod
    def flash(
        cls, serial: str, partition: str, image_path: Path, timeout: int = 300
    ) -> tuple[bool, str]:
        rc, stdout, stderr = cls._run(
            ["-s", serial, "flash", partition, str(image_path)], timeout=timeout
        )
        return rc == 0, stderr or stdout

    @classmethod
    def erase(cls, serial: str, partition: str) -> bool:
        rc, _, _ = cls._run(["-s", serial, "erase", partition])
        return rc == 0

    @classmethod
    def reboot(cls, serial: str, mode: str = "") -> bool:
        """mode: "" (system) | "recovery" | "fastboot" (fastbootd) | "bootloader" """
        args = ["-s", serial, "reboot"]
        if mode:
            args.append(mode)
        rc, _, _ = cls._run(args, timeout=20)
        return rc == 0

    # ── Device enrichment ────────────────────────────────────────────────────

    @classmethod
    def enrich_device_info(cls, info: DeviceInfo) -> DeviceInfo:
        """Populate device info from fastboot variables."""
        vars_to_fetch = [
            "product",
            "unlocked",
            "slot-count",
            "current-slot",
            "version-baseband",
        ]
        for var in vars_to_fetch:
            value = cls.get_var(info.serial, var)
            if value:
                info.fastboot_vars[var] = value

        info.model = info.fastboot_vars.get("product", info.model)

        unlocked = info.fastboot_vars.get("unlocked", "").lower()
        if unlocked == "yes":
            info.bootloader_unlocked = True
        elif unlocked == "no":
            info.bootloader_unlocked = False

        slot_count_str = info.fastboot_vars.get("slot-count", "")
        if slot_count_str.isdigit() and int(slot_count_str) > 1:
            info.has_ab_slots = True
            current_slot = info.fastboot_vars.get("current-slot", "")
            if current_slot:
                info.active_slot = current_slot

        return info
