from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from cyberflash.utils.platform_utils import get_platform, get_resources_dir

logger = logging.getLogger(__name__)


class EdlManager:
    """Cross-platform EDL (Emergency Download) USB device detection and setup helpers."""

    EDL_VID = "05c6"
    EDL_PID = "9008"

    @classmethod
    def list_edl_devices(cls) -> list[str]:
        """Return list of pseudo-serials ('edl:0', 'edl:1') for each EDL device found."""
        platform = get_platform()
        try:
            if platform == "linux":
                return cls._linux_list()
            if platform == "macos":
                return cls._macos_list()
            return cls._windows_list()
        except Exception as exc:
            logger.warning("EDL device list failed on %s: %s", platform, exc)
            return []

    @classmethod
    def _linux_list(cls) -> list[str]:
        """Scan /sys/bus/usb/devices for Qualcomm EDL (no external tool needed)."""
        found: list[str] = []
        sys_usb = Path("/sys/bus/usb/devices")
        if not sys_usb.exists():
            return cls._linux_lsusb_list()

        idx = 0
        for dev_dir in sorted(sys_usb.iterdir()):
            vid_file = dev_dir / "idVendor"
            pid_file = dev_dir / "idProduct"
            if vid_file.exists() and pid_file.exists():
                try:
                    vid = vid_file.read_text().strip().lower()
                    pid = pid_file.read_text().strip().lower()
                    if vid == cls.EDL_VID and pid == cls.EDL_PID:
                        found.append(f"edl:{idx}")
                        idx += 1
                except OSError:
                    pass
        return found

    @classmethod
    def _linux_lsusb_list(cls) -> list[str]:
        """Fallback: parse lsusb output."""
        try:
            result = subprocess.run(
                ["lsusb"], capture_output=True, text=True, timeout=5
            )
            count = result.stdout.lower().count(f"id {cls.EDL_VID}:{cls.EDL_PID}")
            return [f"edl:{i}" for i in range(count)]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

    @classmethod
    def _macos_list(cls) -> list[str]:
        """Parse system_profiler USB data for EDL devices."""
        try:
            result = subprocess.run(
                ["system_profiler", "SPUSBDataType"],
                capture_output=True, text=True, timeout=10,
            )
            output = result.stdout.lower()
            # Look for vendor/product IDs in the output
            # system_profiler shows "Vendor ID: 0x05c6" and "Product ID: 0x9008"
            vid_hex = f"0x{cls.EDL_VID}"
            pid_hex = f"0x{cls.EDL_PID}"
            count = 0
            lines = output.splitlines()
            for i, line in enumerate(lines):
                if vid_hex in line:
                    # Check surrounding lines for product ID
                    context = "\n".join(lines[max(0, i - 3):i + 4])
                    if pid_hex in context:
                        count += 1
            return [f"edl:{i}" for i in range(count)]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

    @classmethod
    def _windows_list(cls) -> list[str]:
        """Query Windows WMI for Qualcomm EDL devices."""
        try:
            ps_cmd = (
                "Get-WmiObject Win32_PnPEntity | "
                f"Where-Object {{$_.DeviceID -like '*VID_{cls.EDL_VID.upper()}*PID_{cls.EDL_PID.upper()}*'}} | "
                "Measure-Object | Select-Object -ExpandProperty Count"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10,
            )
            count = int(result.stdout.strip() or "0")
            return [f"edl:{i}" for i in range(count)]
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            return []

    # ── Linux udev setup ──────────────────────────────────────────────────────

    @classmethod
    def get_udev_rule_path(cls) -> Path:
        return Path("/etc/udev/rules.d/51-cyberflash-edl.rules")

    @classmethod
    def get_udev_rule(cls) -> str:
        """Return the udev rule string for this app."""
        return (
            f'SUBSYSTEM=="usb", ATTRS{{idVendor}}=="{cls.EDL_VID}", '
            f'ATTRS{{idProduct}}=="{cls.EDL_PID}", MODE="0666", TAG+="uaccess"\n'
        )

    @classmethod
    def is_udev_configured(cls) -> bool:
        """Linux only: check if the CyberFlash EDL udev rule exists."""
        return cls.get_udev_rule_path().exists()

    @classmethod
    def get_bundled_udev_rule_path(cls) -> Path:
        """Return the path to the bundled udev rules file in resources/."""
        return get_resources_dir() / "udev" / "51-cyberflash-edl.rules"

    # ── Per-platform setup instructions ──────────────────────────────────────

    @classmethod
    def get_setup_instructions(cls) -> list[str]:
        """Per-platform driver setup steps as human-readable strings."""
        platform = get_platform()
        if platform == "linux":
            rule = cls.get_udev_rule().strip()
            rule_path = cls.get_udev_rule_path()
            return [
                "1. Install the udev rule to allow non-root USB access:",
                f"   echo '{rule}' | sudo tee {rule_path}",
                "2. Reload udev rules:",
                "   sudo udevadm control --reload-rules && sudo udevadm trigger",
                "3. Reconnect the device.",
            ]
        if platform == "macos":
            return [
                "1. Install libusb (required for pyusb):",
                "   brew install libusb",
                "2. Install pyusb if not already installed:",
                "   pip install pyusb",
                "3. Reconnect the device.",
            ]
        # Windows
        return [
            "1. Download Zadig from https://zadig.akeo.ie/",
            "2. In Zadig: Options → 'List All Devices'",
            "3. Select 'Qualcomm HS-USB QDLoader 9008'",
            "4. Choose 'WinUSB' as the driver and click 'Replace Driver'",
            "5. Reconnect the device.",
        ]
