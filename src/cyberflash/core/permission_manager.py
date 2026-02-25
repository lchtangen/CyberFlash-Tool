"""permission_manager.py — Android app permission management via ADB.

Supports listing, granting, revoking, and applying privacy presets
using ``pm grant/revoke`` shell commands.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)

# ── Dangerous permission list ─────────────────────────────────────────────────

_DANGEROUS_PERMISSIONS: frozenset[str] = frozenset({
    "android.permission.READ_CONTACTS",
    "android.permission.WRITE_CONTACTS",
    "android.permission.READ_CALL_LOG",
    "android.permission.WRITE_CALL_LOG",
    "android.permission.PROCESS_OUTGOING_CALLS",
    "android.permission.READ_SMS",
    "android.permission.RECEIVE_SMS",
    "android.permission.SEND_SMS",
    "android.permission.RECEIVE_MMS",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.ACCESS_BACKGROUND_LOCATION",
    "android.permission.RECORD_AUDIO",
    "android.permission.CAMERA",
    "android.permission.READ_EXTERNAL_STORAGE",
    "android.permission.WRITE_EXTERNAL_STORAGE",
    "android.permission.READ_MEDIA_IMAGES",
    "android.permission.READ_MEDIA_VIDEO",
    "android.permission.READ_MEDIA_AUDIO",
    "android.permission.GET_ACCOUNTS",
    "android.permission.READ_PHONE_STATE",
    "android.permission.CALL_PHONE",
    "android.permission.USE_BIOMETRIC",
    "android.permission.BODY_SENSORS",
    "android.permission.ACTIVITY_RECOGNITION",
})

# Known tracking/advertising permissions
_TRACKING_PERMISSIONS: frozenset[str] = frozenset({
    "com.google.android.gms.permission.AD_ID",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_BACKGROUND_LOCATION",
    "android.permission.READ_CONTACTS",
    "android.permission.RECORD_AUDIO",
})

# ── Privacy presets ───────────────────────────────────────────────────────────

_PRIVACY_PRESETS: dict[str, list[str]] = {
    "revoke_tracking": list(_TRACKING_PERMISSIONS),
    "revoke_location": [
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.ACCESS_BACKGROUND_LOCATION",
    ],
    "revoke_microphone": ["android.permission.RECORD_AUDIO"],
    "revoke_camera": ["android.permission.CAMERA"],
}

# High-risk permission combinations
_RISKY_COMBOS: list[tuple[str, str, str]] = [
    (
        "android.permission.READ_SMS",
        "android.permission.SEND_SMS",
        "SMS read+send combo — spyware risk",
    ),
    (
        "android.permission.RECORD_AUDIO",
        "android.permission.ACCESS_FINE_LOCATION",
        "Microphone + GPS — surveillance risk",
    ),
    (
        "android.permission.CAMERA",
        "android.permission.INTERNET",
        "Camera + Internet — potential remote surveillance",
    ),
]


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class AppPermission:
    """A single app permission entry."""

    package: str
    permission: str
    granted: bool
    dangerous: bool


# ── Main class ────────────────────────────────────────────────────────────────


class PermissionManager:
    """Classmethod-only permission manager."""

    @classmethod
    def list_app_permissions(cls, serial: str, package: str) -> list[AppPermission]:
        """List all permissions for *package*, granted and denied."""
        output = AdbManager.shell(
            serial,
            f"dumpsys package {package} 2>/dev/null",
            timeout=15,
        )
        permissions: list[AppPermission] = []
        in_granted = False

        for line in output.splitlines():
            stripped = line.strip()

            if "grantedPermissions:" in stripped or "install permissions:" in stripped:
                in_granted = True
                continue
            if "requestedPermissions:" in stripped or "denied permissions:" in stripped:
                in_granted = False
                continue
            if stripped and not stripped.startswith("android.permission.") and "." not in stripped[:20]:
                in_granted = False

            m = re.match(r"(android\.\w+(?:\.\w+)+)(?::\s*granted=(\w+))?", stripped)
            if m:
                perm_name = m.group(1)
                granted_str = m.group(2)
                granted = granted_str.lower() == "true" if granted_str is not None else in_granted

                permissions.append(AppPermission(
                    package=package,
                    permission=perm_name,
                    granted=granted,
                    dangerous=perm_name in _DANGEROUS_PERMISSIONS,
                ))

        return permissions

    @classmethod
    def grant(cls, serial: str, package: str, permission: str) -> bool:
        """Grant *permission* to *package* via ``pm grant``."""
        rc, _, stderr = AdbManager._run(
            ["-s", serial, "shell", "pm", "grant", package, permission],
            timeout=10,
        )
        if rc != 0:
            logger.warning("pm grant failed: %s", stderr.strip())
        return rc == 0

    @classmethod
    def revoke(cls, serial: str, package: str, permission: str) -> bool:
        """Revoke *permission* from *package* via ``pm revoke``."""
        rc, _, stderr = AdbManager._run(
            ["-s", serial, "shell", "pm", "revoke", package, permission],
            timeout=10,
        )
        if rc != 0:
            logger.warning("pm revoke failed: %s", stderr.strip())
        return rc == 0

    @classmethod
    def get_dangerous_combos(cls, serial: str) -> list[dict[str, object]]:
        """Return high-risk permission combinations found on device apps.

        Checks third-party packages only.
        """
        packages_output = AdbManager.shell(
            serial, "pm list packages -3", timeout=15
        )
        packages = [
            line.replace("package:", "").strip()
            for line in packages_output.splitlines()
            if line.startswith("package:")
        ]

        results: list[dict[str, object]] = []
        for pkg in packages[:50]:  # limit to avoid excessive ADB calls
            perms = cls.list_app_permissions(serial, pkg)
            granted_set = {p.permission for p in perms if p.granted}
            for perm_a, perm_b, reason in _RISKY_COMBOS:
                if perm_a in granted_set and perm_b in granted_set:
                    results.append({
                        "package": pkg,
                        "permissions": [perm_a, perm_b],
                        "reason": reason,
                    })
        return results

    @classmethod
    def apply_privacy_preset(cls, serial: str, preset: str) -> int:
        """Revoke permissions defined by *preset* across all third-party apps.

        Returns the number of successful revokes.
        """
        permissions_to_revoke = _PRIVACY_PRESETS.get(preset, [])
        if not permissions_to_revoke:
            logger.warning("Unknown privacy preset: %s", preset)
            return 0

        packages_output = AdbManager.shell(serial, "pm list packages -3", timeout=15)
        packages = [
            line.replace("package:", "").strip()
            for line in packages_output.splitlines()
            if line.startswith("package:")
        ]

        revoked = 0
        for pkg in packages:
            for perm in permissions_to_revoke:
                if cls.revoke(serial, pkg, perm):
                    revoked += 1
        return revoked
