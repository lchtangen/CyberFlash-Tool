"""Automated device analysis with health scoring and compatibility checks.

All analysis runs locally — no external calls.  This module aggregates data
from ADB properties, fastboot variables, and heuristic rules to produce a
holistic device health report.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum

from cyberflash.models.device import DeviceInfo, DeviceState

logger = logging.getLogger(__name__)


class HealthGrade(StrEnum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"

    @property
    def score_range(self) -> tuple[int, int]:
        return {
            HealthGrade.EXCELLENT: (90, 100),
            HealthGrade.GOOD: (70, 89),
            HealthGrade.FAIR: (50, 69),
            HealthGrade.POOR: (25, 49),
            HealthGrade.CRITICAL: (0, 24),
        }[self]

    @property
    def badge_variant(self) -> str:
        return {
            HealthGrade.EXCELLENT: "success",
            HealthGrade.GOOD: "success",
            HealthGrade.FAIR: "warning",
            HealthGrade.POOR: "error",
            HealthGrade.CRITICAL: "error",
        }[self]


@dataclass
class HealthCheckItem:
    """A single health-check result."""

    name: str
    passed: bool
    details: str
    weight: int = 10  # contribution to total score (0-100)


@dataclass
class DeviceHealthReport:
    """Aggregate health report for a device."""

    device_name: str
    serial: str
    checks: list[HealthCheckItem] = field(default_factory=list)
    compatibility_notes: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        if not self.checks:
            return 0
        total_weight = sum(c.weight for c in self.checks)
        if total_weight == 0:
            return 0
        earned = sum(c.weight for c in self.checks if c.passed)
        return round(earned / total_weight * 100)

    @property
    def grade(self) -> HealthGrade:
        s = self.score
        if s >= 90:
            return HealthGrade.EXCELLENT
        if s >= 70:
            return HealthGrade.GOOD
        if s >= 50:
            return HealthGrade.FAIR
        if s >= 25:
            return HealthGrade.POOR
        return HealthGrade.CRITICAL

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def total_count(self) -> int:
        return len(self.checks)


class DeviceAnalyzer:
    """Analyse a :class:`DeviceInfo` and produce a health report.

    All analysis is based on the data already present in DeviceInfo
    (populated by DevicePollWorker).  No I/O is performed here.
    """

    def analyze(self, device: DeviceInfo) -> DeviceHealthReport:
        """Run all checks and return a comprehensive report."""
        report = DeviceHealthReport(
            device_name=device.display_name,
            serial=device.serial,
        )

        report.checks = [
            self._check_connectivity(device),
            self._check_authorization(device),
            self._check_battery(device),
            self._check_bootloader(device),
            self._check_android_version(device),
            self._check_ab_slots(device),
            self._check_identity(device),
        ]

        report.compatibility_notes = self._compatibility_notes(device)
        report.recommended_actions = self._recommended_actions(device)
        return report

    # ── Individual checks ────────────────────────────────────────────────────

    @staticmethod
    def _check_connectivity(device: DeviceInfo) -> HealthCheckItem:
        connected = device.state not in (DeviceState.OFFLINE, DeviceState.UNKNOWN)
        return HealthCheckItem(
            name="Device Connectivity",
            passed=connected,
            details=(
                f"Device is {device.state.label}"
                if connected
                else "Device is offline or in an unknown state"
            ),
            weight=20,
        )

    @staticmethod
    def _check_authorization(device: DeviceInfo) -> HealthCheckItem:
        authorized = device.state != DeviceState.UNAUTHORIZED
        return HealthCheckItem(
            name="USB Authorization",
            passed=authorized,
            details=(
                "USB debugging authorized"
                if authorized
                else "Device is unauthorized — approve the USB debugging prompt"
            ),
            weight=15,
        )

    @staticmethod
    def _check_battery(device: DeviceInfo) -> HealthCheckItem:
        if device.battery_level < 0:
            return HealthCheckItem(
                name="Battery Level",
                passed=True,  # can't penalise if we don't know
                details="Battery level not available",
                weight=15,
            )
        ok = device.battery_level >= 50
        return HealthCheckItem(
            name="Battery Level",
            passed=ok,
            details=(
                f"Battery at {device.battery_level}%"
                if ok
                else f"Battery at {device.battery_level}% — charge to 50%+"
            ),
            weight=15,
        )

    @staticmethod
    def _check_bootloader(device: DeviceInfo) -> HealthCheckItem:
        if device.bootloader_unlocked is None:
            return HealthCheckItem(
                name="Bootloader Status",
                passed=True,
                details="Bootloader state unknown (requires fastboot)",
                weight=10,
            )
        return HealthCheckItem(
            name="Bootloader Status",
            passed=True,  # both locked/unlocked are valid states
            details=(
                "Bootloader unlocked — ready for custom operations"
                if device.bootloader_unlocked
                else "Bootloader locked — unlock required for custom ROMs"
            ),
            weight=10,
        )

    @staticmethod
    def _check_android_version(device: DeviceInfo) -> HealthCheckItem:
        if not device.android_version:
            return HealthCheckItem(
                name="Android Version",
                passed=True,
                details="Android version not available",
                weight=10,
            )
        try:
            major = int(device.android_version.split(".")[0])
        except (ValueError, IndexError):
            major = 0

        ok = major >= 10
        return HealthCheckItem(
            name="Android Version",
            passed=ok,
            details=(
                f"Android {device.android_version}"
                if ok
                else f"Android {device.android_version} — older OS, limited support"
            ),
            weight=10,
        )

    @staticmethod
    def _check_ab_slots(device: DeviceInfo) -> HealthCheckItem:
        if not device.has_ab_slots:
            return HealthCheckItem(
                name="Partition Scheme",
                passed=True,
                details="Traditional (non-A/B) partition layout",
                weight=10,
            )
        ok = bool(device.active_slot)
        return HealthCheckItem(
            name="Partition Scheme",
            passed=ok,
            details=(
                f"A/B slots — active slot {device.active_slot.upper()}"
                if ok
                else "A/B device but active slot unknown"
            ),
            weight=10,
        )

    @staticmethod
    def _check_identity(device: DeviceInfo) -> HealthCheckItem:
        has_info = bool(device.model or device.codename)
        return HealthCheckItem(
            name="Device Identity",
            passed=has_info,
            details=(
                f"{device.brand} {device.model} ({device.codename})"
                if has_info
                else "Device model/codename not detected"
            ),
            weight=10,
        )

    # ── Aggregated notes ─────────────────────────────────────────────────────

    @staticmethod
    def _compatibility_notes(device: DeviceInfo) -> list[str]:
        notes: list[str] = []
        if device.state == DeviceState.EDL:
            notes.append("Device is in EDL mode. Only EDL-based operations are available.")
        if device.has_ab_slots:
            notes.append("A/B partition device — flash operations target the inactive slot.")
        if device.android_version:
            try:
                major = int(device.android_version.split(".")[0])
                if major < 10:
                    notes.append(
                        f"Android {device.android_version} is outdated. "
                        "Some features may not be supported."
                    )
            except (ValueError, IndexError):
                pass
        return notes

    @staticmethod
    def _recommended_actions(device: DeviceInfo) -> list[str]:
        actions: list[str] = []
        if device.state == DeviceState.UNAUTHORIZED:
            actions.append("Approve USB debugging on the device screen")
        if device.state == DeviceState.OFFLINE:
            actions.append("Reconnect USB cable or restart ADB server")
        if 0 <= device.battery_level < 50:
            actions.append(f"Charge battery to 50%+ (currently {device.battery_level}%)")
        if device.bootloader_unlocked is False:
            actions.append("Unlock bootloader before custom ROM operations")
        return actions
