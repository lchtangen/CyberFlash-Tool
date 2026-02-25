from __future__ import annotations

import logging
import subprocess

from cyberflash.core.tool_manager import ToolManager
from cyberflash.models.device import DeviceInfo, DeviceState

logger = logging.getLogger(__name__)

_ADB_STATE_MAP: dict[str, DeviceState] = {
    "device": DeviceState.ONLINE,
    "offline": DeviceState.OFFLINE,
    "unauthorized": DeviceState.UNAUTHORIZED,
    "recovery": DeviceState.RECOVERY,
    "sideload": DeviceState.SIDELOAD,
}


class AdbManager:
    """Synchronous ADB command executor. Always call from worker threads."""

    DEFAULT_TIMEOUT = 10

    @classmethod
    def _run(
        cls,
        args: list[str],
        timeout: int | None = None,
    ) -> tuple[int, str, str]:
        cmd = ToolManager.adb_cmd() + args
        t = timeout or cls.DEFAULT_TIMEOUT
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
            return r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            logger.warning("ADB timeout: %s", " ".join(cmd))
            return -1, "", "timeout"
        except FileNotFoundError:
            logger.error("ADB binary not found")
            return -1, "", "adb not found"
        except Exception as exc:
            logger.error("ADB error: %s", exc)
            return -1, "", str(exc)

    # ── Server management ────────────────────────────────────────────────────

    @classmethod
    def start_server(cls) -> bool:
        rc, _, _ = cls._run(["start-server"])
        return rc == 0

    @classmethod
    def kill_server(cls) -> bool:
        rc, _, _ = cls._run(["kill-server"])
        return rc == 0

    # ── Device listing ───────────────────────────────────────────────────────

    @classmethod
    def list_devices(cls) -> list[tuple[str, str]]:
        """Return list of (serial, state_string) pairs."""
        _, stdout, _ = cls._run(["devices"])
        devices: list[tuple[str, str]] = []
        for line in stdout.splitlines()[1:]:  # skip header
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                devices.append((parts[0], parts[1]))
        return devices

    # ── Property access ──────────────────────────────────────────────────────

    @classmethod
    def get_prop(cls, serial: str, prop: str) -> str:
        _, stdout, _ = cls._run(["-s", serial, "shell", "getprop", prop], timeout=5)
        return stdout.strip()

    @classmethod
    def get_props_batch(cls, serial: str, props: list[str]) -> dict[str, str]:
        """Fetch multiple props with a single shell call."""
        cmd = "; ".join(f"getprop {p}" for p in props)
        _, stdout, _ = cls._run(["-s", serial, "shell", cmd], timeout=8)
        values = stdout.strip().splitlines()
        result: dict[str, str] = {}
        for prop, value in zip(props, values, strict=False):
            result[prop] = value.strip()
        return result

    # ── Shell / file ops ─────────────────────────────────────────────────────

    @classmethod
    def shell(cls, serial: str, command: str, timeout: int | None = None) -> str:
        _, stdout, _ = cls._run(["-s", serial, "shell", command], timeout=timeout)
        return stdout

    @classmethod
    def push(cls, serial: str, local: str, remote: str, timeout: int = 120) -> bool:
        rc, _, _ = cls._run(["-s", serial, "push", local, remote], timeout=timeout)
        return rc == 0

    @classmethod
    def pull(cls, serial: str, remote: str, local: str, timeout: int = 120) -> bool:
        rc, _, _ = cls._run(["-s", serial, "pull", remote, local], timeout=timeout)
        return rc == 0

    # ── Device control ───────────────────────────────────────────────────────

    @classmethod
    def reboot(cls, serial: str, mode: str = "") -> bool:
        """mode: "" (normal) | "recovery" | "bootloader" | "fastboot" | "sideload" """
        args = ["-s", serial, "reboot"]
        if mode:
            args.append(mode)
        rc, _, _ = cls._run(args, timeout=15)
        return rc == 0

    # ── Device enrichment ────────────────────────────────────────────────────

    @classmethod
    def get_battery_level(cls, serial: str) -> int:
        output = cls.shell(serial, "dumpsys battery | grep level", timeout=5)
        for line in output.splitlines():
            if "level:" in line:
                try:
                    return int(line.split(":")[1].strip())
                except ValueError:
                    pass
        return -1

    @classmethod
    def enrich_device_info(cls, info: DeviceInfo) -> DeviceInfo:
        """Populate all available properties for an ADB-connected device."""
        prop_keys = [
            "ro.product.model",
            "ro.product.brand",
            "ro.product.device",
            "ro.build.version.release",
            "ro.build.version.sdk",
            "ro.build.display.id",
            "ro.boot.slot_suffix",
            "ro.boot.verifiedbootstate",
        ]
        props = cls.get_props_batch(info.serial, prop_keys)

        info.model = props.get("ro.product.model", "")
        info.brand = props.get("ro.product.brand", "")
        info.codename = props.get("ro.product.device", "")
        info.android_version = props.get("ro.build.version.release", "")
        info.sdk_version = props.get("ro.build.version.sdk", "")
        info.build_number = props.get("ro.build.display.id", "")

        slot_suffix = props.get("ro.boot.slot_suffix", "")
        if slot_suffix:
            info.has_ab_slots = True
            info.active_slot = slot_suffix.lstrip("_")  # "_a" → "a"

        boot_state = props.get("ro.boot.verifiedbootstate", "")
        if boot_state == "orange":
            info.bootloader_unlocked = True
        elif boot_state in ("green", "yellow", "red"):
            info.bootloader_unlocked = False

        if info.state == DeviceState.ONLINE:
            info.battery_level = cls.get_battery_level(info.serial)

        return info
