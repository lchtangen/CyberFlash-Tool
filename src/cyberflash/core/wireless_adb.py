"""wireless_adb.py — Wireless ADB (TCP/IP) pairing and connection helpers.

Supports Android 11+ wireless debugging (ADB over Wi-Fi) including:
- QR-code pairing (adb pair)
- mDNS service discovery
- Standard TCP connect/disconnect
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)

# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class PairingResult:
    """Result of an ADB pairing or connection attempt."""

    success: bool
    ip: str = ""
    port: int = 0
    serial: str = ""
    error: str = ""


# ── Main class ────────────────────────────────────────────────────────────────


class WirelessAdb:
    """Classmethod-only wrapper for wireless ADB operations."""

    @classmethod
    def pair(cls, ip: str, port: int, code: str) -> PairingResult:
        """Pair with a device using the numeric pairing code.

        Runs: ``adb pair <ip>:<port> <code>``
        """
        rc, stdout, stderr = AdbManager._run(
            ["pair", f"{ip}:{port}", code], timeout=20
        )
        output = (stdout + stderr).strip()
        if rc == 0 and "successfully" in output.lower():
            return PairingResult(success=True, ip=ip, port=port, serial=f"{ip}:{port}")
        return PairingResult(
            success=False, ip=ip, port=port,
            error=output or "pairing failed",
        )

    @classmethod
    def connect(cls, ip: str, port: int = 5555) -> PairingResult:
        """Connect to a device over TCP/IP.

        Runs: ``adb connect <ip>:<port>``
        """
        rc, stdout, stderr = AdbManager._run(
            ["connect", f"{ip}:{port}"], timeout=15
        )
        output = (stdout + stderr).strip()
        if rc == 0 and "connected" in output.lower():
            return PairingResult(success=True, ip=ip, port=port, serial=f"{ip}:{port}")
        return PairingResult(
            success=False, ip=ip, port=port,
            error=output or "connection failed",
        )

    @classmethod
    def disconnect(cls, serial: str) -> bool:
        """Disconnect a specific device by serial (ip:port).

        Runs: ``adb disconnect <serial>``
        """
        rc, stdout, _ = AdbManager._run(["disconnect", serial], timeout=10)
        output = stdout.strip().lower()
        return rc == 0 and ("disconnected" in output or "error" not in output)

    @classmethod
    def discover_mdns(cls, timeout: float = 5.0) -> list[dict[str, str]]:
        """Discover wireless ADB services via mDNS.

        Parses ``adb mdns services`` output, returning a list of dicts with
        keys: ``service_name``, ``transport_id``, ``ip``, ``port``.
        """
        rc, stdout, _ = AdbManager._run(["mdns", "services"], timeout=int(timeout) + 2)
        services: list[dict[str, str]] = []
        if rc != 0:
            return services

        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("List"):
                continue
            # Typical format: serviceName  transportId  ip:port
            parts = line.split()
            if len(parts) >= 3:
                addr = parts[-1]
                m = re.match(r"(.+):(\d+)$", addr)
                if m:
                    services.append({
                        "service_name": parts[0],
                        "transport_id": parts[1] if len(parts) >= 3 else "",
                        "ip": m.group(1),
                        "port": m.group(2),
                    })
        return services

    @classmethod
    def generate_qr_data(cls, ip: str, port: int, code: str) -> str:
        """Generate a Wi-Fi ADB pairing QR code URI string.

        Format: ``WIFI:T:ADB;S:<service>;P:<password>;H:<host>;PORT:<port>;;``
        """
        service = f"adbwifi_{ip.replace('.', '_')}_{port}"
        return f"WIFI:T:ADB;S:{service};P:{code};H:{ip};PORT:{port};;"

    @classmethod
    def get_connected_wifi_devices(cls) -> list[str]:
        """Return serials of currently connected Wi-Fi (TCP) ADB devices.

        Filters ``adb devices`` output for IP:port-style serials.
        """
        devices = AdbManager.list_devices()
        ip_serial_re = re.compile(r"^\d{1,3}(\.\d{1,3}){3}:\d+$")
        return [
            serial
            for serial, state in devices
            if ip_serial_re.match(serial) and state in ("device", "online")
        ]
