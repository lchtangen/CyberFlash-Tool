"""security_auditor.py — Android device security audit.

Checks key security properties via ADB and produces a scored report.
All methods are synchronous and UI-agnostic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.root_manager import RootManager, RootState

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────


class Finding(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"
    INFO     = "INFO"


# Numeric severity for scoring
_SEVERITY_PENALTY: dict[Finding, int] = {
    Finding.CRITICAL: 30,
    Finding.HIGH:     15,
    Finding.MEDIUM:    8,
    Finding.LOW:       3,
    Finding.INFO:      0,
}


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class AuditFinding:
    """A single security audit finding."""

    severity: Finding
    title: str
    detail: str
    remediation: str


@dataclass
class AuditReport:
    """Full security audit report."""

    serial: str
    findings: list[AuditFinding] = field(default_factory=list)
    score: int = 100            # starts at 100, penalised per finding
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"


# ── Main class ────────────────────────────────────────────────────────────────


class SecurityAuditor:
    """Classmethod-only device security auditor."""

    @classmethod
    def check_selinux(cls, serial: str) -> AuditFinding:
        """Check SELinux enforce status."""
        output = AdbManager.shell(serial, "getenforce 2>/dev/null", timeout=8).strip().lower()
        if "enforcing" in output:
            return AuditFinding(
                severity=Finding.INFO,
                title="SELinux: Enforcing",
                detail="SELinux is in enforcing mode — good.",
                remediation="No action required.",
            )
        if "permissive" in output:
            return AuditFinding(
                severity=Finding.HIGH,
                title="SELinux: Permissive",
                detail="SELinux is in permissive mode — policies are not enforced.",
                remediation="Re-lock SELinux or flash an enforcing kernel.",
            )
        return AuditFinding(
            severity=Finding.MEDIUM,
            title="SELinux: Unknown",
            detail=f"Could not determine SELinux status (output: {output!r}).",
            remediation="Verify SELinux manually with 'getenforce' on device.",
        )

    @classmethod
    def check_bootloader(cls, serial: str) -> AuditFinding:
        """Check bootloader lock status."""
        output = AdbManager.get_prop(serial, "ro.boot.flash.locked")
        unlocked = AdbManager.get_prop(serial, "ro.boot.verifiedbootstate")

        if output == "1" or unlocked in ("green", "yellow"):
            return AuditFinding(
                severity=Finding.INFO,
                title="Bootloader: Locked",
                detail="Bootloader is locked — verified boot active.",
                remediation="No action required.",
            )
        return AuditFinding(
            severity=Finding.HIGH,
            title="Bootloader: Unlocked",
            detail="Bootloader is unlocked — full dm-verity bypass possible.",
            remediation="Re-lock bootloader if not actively developing. "
                        "Note: locking will wipe data.",
        )

    @classmethod
    def check_root(cls, serial: str) -> AuditFinding:
        """Check for root access on the device."""
        state = RootManager.detect_root_state(serial)
        if state == RootState.NOT_ROOTED:
            return AuditFinding(
                severity=Finding.INFO,
                title="Root: Not detected",
                detail="No root manager detected.",
                remediation="No action required.",
            )
        return AuditFinding(
            severity=Finding.MEDIUM,
            title=f"Root: Detected ({state.label})",
            detail=f"Root access is active via {state.label}.",
            remediation="Ensure DenyList/Magisk Hide is configured for banking/payment apps.",
        )

    @classmethod
    def check_debug_flags(cls, serial: str) -> AuditFinding:
        """Check developer options and USB debugging status."""
        adb_enabled = AdbManager.shell(
            serial, "settings get global adb_enabled", timeout=8
        ).strip()
        dev_opts = AdbManager.shell(
            serial, "settings get global development_settings_enabled", timeout=8
        ).strip()

        issues: list[str] = []
        if adb_enabled == "1":
            issues.append("USB debugging enabled")
        if dev_opts == "1":
            issues.append("Developer options enabled")

        if not issues:
            return AuditFinding(
                severity=Finding.INFO,
                title="Debug flags: Disabled",
                detail="Developer options and USB debugging are off.",
                remediation="No action required.",
            )
        severity = Finding.MEDIUM if "USB debugging" in issues else Finding.LOW
        return AuditFinding(
            severity=severity,
            title="Debug flags: Active",
            detail=", ".join(issues),
            remediation="Disable developer options when not actively debugging.",
        )

    @classmethod
    def check_encryption(cls, serial: str) -> AuditFinding:
        """Check FBE/FDE encryption status."""
        fbe = AdbManager.get_prop(serial, "ro.crypto.type")
        state = AdbManager.get_prop(serial, "ro.crypto.state")

        if fbe == "file" or state == "encrypted":
            enc_type = "FBE (File-Based Encryption)" if fbe == "file" else "FDE (Full-Disk)"
            return AuditFinding(
                severity=Finding.INFO,
                title=f"Encryption: {enc_type}",
                detail=f"Storage is encrypted ({enc_type}).",
                remediation="No action required.",
            )
        return AuditFinding(
            severity=Finding.CRITICAL,
            title="Encryption: Not detected",
            detail="Device storage may not be encrypted.",
            remediation="Enable full disk or file-based encryption in device settings.",
        )

    @classmethod
    def run_audit(cls, serial: str) -> AuditReport:
        """Run all security checks and return a scored AuditReport."""
        findings = [
            cls.check_selinux(serial),
            cls.check_bootloader(serial),
            cls.check_root(serial),
            cls.check_debug_flags(serial),
            cls.check_encryption(serial),
        ]

        score = 100
        for f in findings:
            score -= _SEVERITY_PENALTY.get(f.severity, 0)
        score = max(0, score)

        return AuditReport(serial=serial, findings=findings, score=score)
