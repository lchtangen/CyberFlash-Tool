from __future__ import annotations

import logging

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.edl_manager import EdlManager
from cyberflash.core.fastboot_manager import FastbootManager
from cyberflash.models.device import DeviceInfo, DeviceState

logger = logging.getLogger(__name__)

_ADB_STATE_MAP: dict[str, DeviceState] = {
    "device": DeviceState.ONLINE,
    "offline": DeviceState.OFFLINE,
    "unauthorized": DeviceState.UNAUTHORIZED,
    "recovery": DeviceState.RECOVERY,
    "sideload": DeviceState.SIDELOAD,
}


class DeviceDetector:
    """Enumerates connected Android devices over ADB and fastboot."""

    @classmethod
    def list_serials(cls) -> dict[str, DeviceState]:
        """Fast path: return {serial: state} without enrichment."""
        result: dict[str, DeviceState] = {}

        try:
            for serial, state_str in AdbManager.list_devices():
                result[serial] = _ADB_STATE_MAP.get(state_str, DeviceState.UNKNOWN)
        except Exception as exc:
            logger.warning("ADB list failed: %s", exc)

        try:
            for serial, state_str in FastbootManager.list_devices():
                state = (
                    DeviceState.FASTBOOTD
                    if state_str == "fastbootd"
                    else DeviceState.FASTBOOT
                )
                result[serial] = state
        except Exception as exc:
            logger.warning("Fastboot list failed: %s", exc)

        try:
            for edl_serial in EdlManager.list_edl_devices():
                result[edl_serial] = DeviceState.EDL
        except Exception as exc:
            logger.warning("EDL scan failed: %s", exc)

        return result

    @classmethod
    def enrich(cls, serial: str, state: DeviceState) -> DeviceInfo:
        """Create a fully-populated DeviceInfo for a single device."""
        info = DeviceInfo(serial=serial, state=state)

        if state in (DeviceState.ONLINE, DeviceState.RECOVERY):
            try:
                info = AdbManager.enrich_device_info(info)
            except Exception as exc:
                logger.warning("ADB enrich failed for %s: %s", serial, exc)

        elif state in (DeviceState.FASTBOOT, DeviceState.FASTBOOTD):
            try:
                info = FastbootManager.enrich_device_info(info)
            except Exception as exc:
                logger.warning("Fastboot enrich failed for %s: %s", serial, exc)

        elif state == DeviceState.EDL:
            # No ADB/fastboot enrichment possible in EDL mode.
            # Try to identify device by matching EDL VID/PID against all profiles.
            info.model = "EDL Device"
            info.brand = "Qualcomm"
            try:
                from cyberflash.profiles import ProfileRegistry
                for codename in ProfileRegistry.list_all():
                    profile = ProfileRegistry.load(codename)
                    if (
                        profile
                        and profile.edl
                        and profile.edl.vid.lower() == EdlManager.EDL_VID
                    ):
                        info.codename = codename
                        info.model = profile.model
                        info.brand = profile.brand
                        break
            except Exception as exc:
                logger.warning("EDL profile match failed for %s: %s", serial, exc)

        return info
