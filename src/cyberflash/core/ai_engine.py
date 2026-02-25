"""Local AI engine for CyberFlash — privacy-first, no external API calls.

This module provides intelligent device analysis, risk assessment, workflow
recommendations, and automated guidance based on rule-based reasoning and
heuristic scoring.  All processing runs locally on the user's machine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cyberflash.models.device import DeviceInfo

logger = logging.getLogger(__name__)


# ── Enumerations ─────────────────────────────────────────────────────────────


class RiskLevel(IntEnum):
    """Risk severity for an operation."""

    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return {
            RiskLevel.NONE: "None",
            RiskLevel.LOW: "Low",
            RiskLevel.MEDIUM: "Medium",
            RiskLevel.HIGH: "High",
            RiskLevel.CRITICAL: "Critical",
        }[self]

    @property
    def color_token(self) -> str:
        return {
            RiskLevel.NONE: "success",
            RiskLevel.LOW: "success",
            RiskLevel.MEDIUM: "warning",
            RiskLevel.HIGH: "error",
            RiskLevel.CRITICAL: "error",
        }[self]


class ActionCategory(StrEnum):
    FLASH = "flash"
    BACKUP = "backup"
    ROOT = "root"
    UNLOCK = "unlock"
    PARTITION = "partition"
    RESCUE = "rescue"
    DIAGNOSTICS = "diagnostics"
    NETHUNTER = "nethunter"
    GENERAL = "general"


class InsightSeverity(StrEnum):
    INFO = "info"
    TIP = "tip"
    WARNING = "warning"
    CRITICAL = "critical"


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class RiskAssessment:
    """Risk analysis result for a proposed operation."""

    level: RiskLevel
    summary: str
    factors: list[str] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)
    blocked: bool = False  # If True, the operation should NOT proceed


@dataclass
class Recommendation:
    """A single AI recommendation."""

    title: str
    description: str
    category: ActionCategory
    priority: int = 0  # higher = more important
    risk: RiskLevel = RiskLevel.NONE
    steps: list[str] = field(default_factory=list)
    auto_executable: bool = False  # Can the AI auto-run this?


@dataclass
class DeviceInsight:
    """An insight about the current device state."""

    severity: InsightSeverity
    title: str
    message: str
    action_hint: str = ""  # e.g. "Go to Backup page"


@dataclass
class WorkflowStep:
    """A single step in an automated workflow."""

    step_id: int
    title: str
    description: str
    category: ActionCategory
    risk: RiskLevel = RiskLevel.NONE
    completed: bool = False
    skippable: bool = False


@dataclass
class Workflow:
    """A multi-step automated workflow plan."""

    name: str
    description: str
    steps: list[WorkflowStep] = field(default_factory=list)
    current_step: int = 0

    @property
    def progress(self) -> float:
        if not self.steps:
            return 1.0
        return sum(1 for s in self.steps if s.completed) / len(self.steps)

    @property
    def is_complete(self) -> bool:
        return all(s.completed for s in self.steps)


# ── AI Engine ────────────────────────────────────────────────────────────────


class AIEngine:
    """Privacy-first local AI engine for device analysis and guidance.

    All analysis is rule-based and runs entirely on the local machine.
    No data is ever sent to external servers.
    """

    def __init__(self) -> None:
        self._knowledge_base: dict[str, list[str]] = self._build_knowledge_base()

    # ── Device Analysis ──────────────────────────────────────────────────────

    def analyze_device(self, device: DeviceInfo) -> list[DeviceInsight]:
        """Generate insights about the current device state."""
        from cyberflash.models.device import DeviceState

        insights: list[DeviceInsight] = []

        # Battery warnings
        if 0 <= device.battery_level < 20:
            insights.append(
                DeviceInsight(
                    severity=InsightSeverity.CRITICAL,
                    title="Low Battery",
                    message=(
                        f"Battery is at {device.battery_level}%. Flashing with low "
                        "battery can brick your device. Charge to at least 50% first."
                    ),
                    action_hint="Charge your device before proceeding",
                )
            )
        elif 20 <= device.battery_level < 50:
            insights.append(
                DeviceInsight(
                    severity=InsightSeverity.WARNING,
                    title="Battery Below 50%",
                    message=(
                        f"Battery is at {device.battery_level}%. For safety, charge "
                        "to at least 50% before flashing operations."
                    ),
                    action_hint="Consider charging before flash operations",
                )
            )

        # State-based insights
        if device.state == DeviceState.UNAUTHORIZED:
            insights.append(
                DeviceInsight(
                    severity=InsightSeverity.WARNING,
                    title="Unauthorized Device",
                    message=(
                        "The device is connected but not authorized. Check the device "
                        "screen for an authorization prompt and tap 'Allow'."
                    ),
                    action_hint="Authorize USB debugging on your device",
                )
            )

        if device.state == DeviceState.OFFLINE:
            insights.append(
                DeviceInsight(
                    severity=InsightSeverity.WARNING,
                    title="Device Offline",
                    message=(
                        "The device reports as 'offline'. Try disconnecting and "
                        "reconnecting the USB cable, or revoking USB debugging "
                        "authorizations in Developer Options."
                    ),
                    action_hint="Reconnect USB cable",
                )
            )

        if device.state == DeviceState.EDL:
            insights.append(
                DeviceInsight(
                    severity=InsightSeverity.CRITICAL,
                    title="Emergency Download Mode",
                    message=(
                        "Device is in Qualcomm EDL mode. This typically means the "
                        "device cannot boot normally. Use the Rescue page to restore "
                        "firmware via EDL."
                    ),
                    action_hint="Go to Rescue page",
                )
            )

        if device.state == DeviceState.RECOVERY:
            insights.append(
                DeviceInsight(
                    severity=InsightSeverity.INFO,
                    title="Recovery Mode",
                    message=(
                        "Device is in recovery mode. You can sideload ROMs or "
                        "perform factory resets from here."
                    ),
                    action_hint="Go to Flash page for sideload",
                )
            )

        if device.state == DeviceState.FASTBOOT:
            insights.append(
                DeviceInsight(
                    severity=InsightSeverity.INFO,
                    title="Fastboot Mode",
                    message=(
                        "Device is in fastboot mode. You can flash partitions, "
                        "unlock the bootloader, or switch slots."
                    ),
                    action_hint="Go to Flash or Partition page",
                )
            )

        # Bootloader insights
        if device.bootloader_unlocked is False:
            insights.append(
                DeviceInsight(
                    severity=InsightSeverity.TIP,
                    title="Bootloader Locked",
                    message=(
                        "The bootloader is locked. You'll need to unlock it before "
                        "flashing custom ROMs or rooting. This will factory reset "
                        "your device."
                    ),
                    action_hint="Backup data first, then unlock bootloader",
                )
            )

        if device.bootloader_unlocked is True and not device.is_rooted:
            insights.append(
                DeviceInsight(
                    severity=InsightSeverity.TIP,
                    title="Bootloader Unlocked",
                    message=(
                        "Your bootloader is unlocked and ready for custom operations. "
                        "Consider creating a full backup before making changes."
                    ),
                    action_hint="Go to Backup page",
                )
            )

        # A/B slot insights
        if device.has_ab_slots and device.active_slot:
            insights.append(
                DeviceInsight(
                    severity=InsightSeverity.INFO,
                    title=f"A/B Device — Slot {device.active_slot.upper()} Active",
                    message=(
                        f"This device uses A/B partitions. Currently booted from "
                        f"slot {device.active_slot.upper()}. Flash operations will "
                        f"target the inactive slot for seamless updates."
                    ),
                )
            )

        return insights

    # ── Risk Assessment ──────────────────────────────────────────────────────

    def assess_risk(
        self,
        action: ActionCategory,
        device: DeviceInfo | None = None,
    ) -> RiskAssessment:
        """Assess the risk of performing an action on the current device."""
        from cyberflash.models.device import DeviceState

        factors: list[str] = []
        mitigations: list[str] = []
        risk = RiskLevel.LOW
        blocked = False

        # Battery check
        if device and 0 <= device.battery_level < 20:
            factors.append(f"Battery critically low ({device.battery_level}%)")
            if action in (ActionCategory.FLASH, ActionCategory.UNLOCK, ActionCategory.PARTITION):
                risk = max(risk, RiskLevel.CRITICAL)
                blocked = True
                mitigations.append("Charge device to at least 50%")

        # Action-specific risk
        if action == ActionCategory.FLASH:
            risk = max(risk, RiskLevel.MEDIUM)
            factors.append("Flashing modifies device firmware")
            mitigations.append("Create a full backup before flashing")
            mitigations.append("Verify ROM hash before flashing")
            if device and device.bootloader_unlocked is False:
                risk = max(risk, RiskLevel.HIGH)
                factors.append("Bootloader is locked — flash will fail")
                blocked = True
                mitigations.append("Unlock bootloader first")

        elif action == ActionCategory.UNLOCK:
            risk = max(risk, RiskLevel.HIGH)
            factors.append("Bootloader unlock will factory reset the device")
            factors.append("All user data will be erased")
            mitigations.append("Create a full backup before unlocking")
            mitigations.append("Ensure OEM unlocking is enabled in Developer Options")

        elif action == ActionCategory.ROOT:
            risk = max(risk, RiskLevel.MEDIUM)
            factors.append("Root access modifies the system partition")
            factors.append("May trigger SafetyNet/Play Integrity failures")
            mitigations.append("Create a backup before rooting")
            mitigations.append("Use Magisk for systemless root")

        elif action == ActionCategory.PARTITION:
            risk = max(risk, RiskLevel.HIGH)
            factors.append("Partition operations can permanently damage the device")
            mitigations.append("Create a full backup first")
            mitigations.append("Double-check partition targets")

        elif action == ActionCategory.NETHUNTER:
            risk = max(risk, RiskLevel.MEDIUM)
            factors.append("NetHunter requires root and custom kernel")
            mitigations.append("Verify device compatibility first")
            mitigations.append("Ensure root is properly installed")

        elif action == ActionCategory.BACKUP:
            risk = RiskLevel.LOW
            factors.append("Backup operations are generally safe")

        elif action == ActionCategory.DIAGNOSTICS:
            risk = RiskLevel.NONE
            factors.append("Diagnostic scans are read-only")

        # Device state modifiers
        if device:
            if device.state == DeviceState.EDL:
                risk = max(risk, RiskLevel.HIGH)
                factors.append("Device is in EDL mode — limited recovery options")

            if device.state == DeviceState.UNKNOWN:
                risk = max(risk, RiskLevel.MEDIUM)
                factors.append("Device state is unknown — proceed with caution")

        summary = self._build_risk_summary(risk, factors, action)
        return RiskAssessment(
            level=risk,
            summary=summary,
            factors=factors,
            mitigations=mitigations,
            blocked=blocked,
        )

    # ── Recommendations ──────────────────────────────────────────────────────

    def get_recommendations(
        self,
        device: DeviceInfo | None = None,
        current_page: str = "dashboard",
    ) -> list[Recommendation]:
        """Generate context-aware recommendations based on device state and page."""
        from cyberflash.models.device import DeviceState

        recs: list[Recommendation] = []

        if device is None:
            recs.append(
                Recommendation(
                    title="Connect a Device",
                    description=(
                        "No device detected. Connect an Android device via USB with "
                        "USB debugging enabled."
                    ),
                    category=ActionCategory.GENERAL,
                    priority=10,
                    steps=[
                        "Enable Developer Options on your device",
                        "Enable USB Debugging in Developer Options",
                        "Connect device via USB cable",
                        "Allow USB debugging when prompted on device",
                    ],
                )
            )
            return recs

        # State-specific recommendations
        if device.state == DeviceState.UNAUTHORIZED:
            recs.append(
                Recommendation(
                    title="Authorize USB Debugging",
                    description="Check your device for the USB debugging authorization prompt.",
                    category=ActionCategory.GENERAL,
                    priority=10,
                )
            )

        if device.state == DeviceState.ONLINE:
            # Always recommend backup first
            recs.append(
                Recommendation(
                    title="Create a Backup",
                    description=(
                        "Before making any modifications, create a comprehensive "
                        "backup of your device data."
                    ),
                    category=ActionCategory.BACKUP,
                    priority=8,
                    risk=RiskLevel.LOW,
                    steps=[
                        "Go to Backup page",
                        "Select backup types (Full, Media, Apps)",
                        "Choose destination folder",
                        "Start backup",
                    ],
                )
            )

            # Diagnostics recommendation
            recs.append(
                Recommendation(
                    title="Run Diagnostics",
                    description=(
                        "Scan your device environment and health to identify any "
                        "potential issues before making changes."
                    ),
                    category=ActionCategory.DIAGNOSTICS,
                    priority=7,
                    risk=RiskLevel.NONE,
                    auto_executable=True,
                    steps=["Go to Diagnostics page", "Click 'Run Full Scan'"],
                )
            )

        if device.state == DeviceState.FASTBOOT:
            if device.bootloader_unlocked is False:
                recs.append(
                    Recommendation(
                        title="Unlock Bootloader",
                        description=(
                            "Your device is in fastboot with a locked bootloader. "
                            "Unlock it to enable custom flashing."
                        ),
                        category=ActionCategory.UNLOCK,
                        priority=9,
                        risk=RiskLevel.HIGH,
                        steps=[
                            "Backup all data first",
                            "Enable OEM unlock in Developer Options",
                            "Use Flash page to unlock bootloader",
                        ],
                    )
                )
            else:
                recs.append(
                    Recommendation(
                        title="Flash ROM or Recovery",
                        description=(
                            "Your device is in fastboot with an unlocked bootloader. "
                            "Ready to flash custom ROMs or recovery images."
                        ),
                        category=ActionCategory.FLASH,
                        priority=8,
                        risk=RiskLevel.MEDIUM,
                        steps=[
                            "Select ROM/image on Flash page",
                            "Verify hash integrity",
                            "Begin flash operation",
                        ],
                    )
                )

        if device.state == DeviceState.RECOVERY:
            recs.append(
                Recommendation(
                    title="Sideload ROM",
                    description="Device is in recovery. You can sideload a ROM via ADB.",
                    category=ActionCategory.FLASH,
                    priority=8,
                    risk=RiskLevel.MEDIUM,
                    steps=["Select ROM zip", "Start sideload from Flash page"],
                )
            )

        if device.state == DeviceState.EDL:
            recs.append(
                Recommendation(
                    title="EDL Rescue",
                    description=(
                        "Device is in Emergency Download mode. Use the Rescue page "
                        "to restore stock firmware."
                    ),
                    category=ActionCategory.RESCUE,
                    priority=10,
                    risk=RiskLevel.HIGH,
                    steps=[
                        "Go to Rescue page",
                        "Load firmware package for your device",
                        "Begin EDL restore",
                    ],
                )
            )

        # Page-specific recommendations
        recs.extend(self._page_recommendations(device, current_page))

        # Sort by priority (descending)
        recs.sort(key=lambda r: r.priority, reverse=True)
        return recs

    # ── Workflow Generation ──────────────────────────────────────────────────

    def plan_flash_workflow(
        self,
        device: DeviceInfo,
        has_backup: bool = False,
    ) -> Workflow:
        """Generate a step-by-step workflow for flashing a device."""
        steps: list[WorkflowStep] = []
        step_id = 1

        if not has_backup:
            steps.append(
                WorkflowStep(
                    step_id=step_id,
                    title="Create Backup",
                    description="Backup all important data before proceeding.",
                    category=ActionCategory.BACKUP,
                    risk=RiskLevel.LOW,
                )
            )
            step_id += 1

        if device.bootloader_unlocked is False:
            steps.append(
                WorkflowStep(
                    step_id=step_id,
                    title="Unlock Bootloader",
                    description=(
                        "Enable OEM unlock and run fastboot unlock. "
                        "WARNING: This will factory reset your device."
                    ),
                    category=ActionCategory.UNLOCK,
                    risk=RiskLevel.HIGH,
                )
            )
            step_id += 1

        steps.append(
            WorkflowStep(
                step_id=step_id,
                title="Select & Verify ROM",
                description="Choose your ROM image and verify its hash integrity.",
                category=ActionCategory.FLASH,
                risk=RiskLevel.NONE,
            )
        )
        step_id += 1

        steps.append(
            WorkflowStep(
                step_id=step_id,
                title="Flash ROM",
                description="Flash the ROM image to your device via fastboot or sideload.",
                category=ActionCategory.FLASH,
                risk=RiskLevel.MEDIUM,
            )
        )
        step_id += 1

        steps.append(
            WorkflowStep(
                step_id=step_id,
                title="Verify Flash",
                description="Reboot and verify the device boots successfully.",
                category=ActionCategory.FLASH,
                risk=RiskLevel.NONE,
            )
        )
        step_id += 1

        return Workflow(
            name="Flash ROM",
            description="Complete workflow for flashing a custom ROM.",
            steps=steps,
        )

    def plan_root_workflow(self, device: DeviceInfo) -> Workflow:
        """Generate a step-by-step workflow for rooting a device."""
        steps: list[WorkflowStep] = []
        step_id = 1

        steps.append(
            WorkflowStep(
                step_id=step_id,
                title="Backup Data",
                description="Create a full backup before rooting.",
                category=ActionCategory.BACKUP,
                risk=RiskLevel.LOW,
            )
        )
        step_id += 1

        if device.bootloader_unlocked is False:
            steps.append(
                WorkflowStep(
                    step_id=step_id,
                    title="Unlock Bootloader",
                    description="Bootloader must be unlocked for root.",
                    category=ActionCategory.UNLOCK,
                    risk=RiskLevel.HIGH,
                )
            )
            step_id += 1

        steps.append(
            WorkflowStep(
                step_id=step_id,
                title="Extract Boot Image",
                description="Pull the current boot.img from the device for patching.",
                category=ActionCategory.ROOT,
                risk=RiskLevel.LOW,
            )
        )
        step_id += 1

        steps.append(
            WorkflowStep(
                step_id=step_id,
                title="Patch Boot Image",
                description="Use Magisk to patch the boot image for systemless root.",
                category=ActionCategory.ROOT,
                risk=RiskLevel.MEDIUM,
            )
        )
        step_id += 1

        steps.append(
            WorkflowStep(
                step_id=step_id,
                title="Flash Patched Image",
                description="Flash the Magisk-patched boot image to the device.",
                category=ActionCategory.FLASH,
                risk=RiskLevel.MEDIUM,
            )
        )
        step_id += 1

        steps.append(
            WorkflowStep(
                step_id=step_id,
                title="Verify Root",
                description="Reboot and verify root access is working.",
                category=ActionCategory.ROOT,
                risk=RiskLevel.NONE,
            )
        )
        step_id += 1

        return Workflow(
            name="Root Device",
            description="Complete workflow for rooting via Magisk.",
            steps=steps,
        )

    # ── Smart Chat Responses ─────────────────────────────────────────────────

    def answer_query(
        self,
        query: str,
        device: DeviceInfo | None = None,
        current_page: str = "dashboard",
    ) -> str:
        """Process a user query and return an intelligent response.

        Uses keyword matching, device context, and the knowledge base to
        generate helpful responses — all locally, no network calls.
        """
        q = query.lower().strip()

        # Direct greetings
        if q in ("hi", "hello", "hey", "help"):
            return self._greeting_response(device)

        # Topic-based routing
        if any(kw in q for kw in ("flash", "rom", "install rom", "sideload")):
            return self._flash_guidance(device)

        if any(kw in q for kw in ("root", "magisk", "supersu")):
            return self._root_guidance(device)

        if any(kw in q for kw in ("backup", "back up", "save data")):
            return self._backup_guidance(device)

        if any(kw in q for kw in ("bootloader", "unlock", "oem")):
            return self._bootloader_guidance(device)

        if any(kw in q for kw in ("brick", "rescue", "edl", "emergency")):
            return self._rescue_guidance(device)

        if any(kw in q for kw in ("partition", "slot", "a/b")):
            return self._partition_guidance(device)

        if any(kw in q for kw in ("nethunter", "kali", "penetration")):
            return self._nethunter_guidance(device)

        if any(kw in q for kw in ("diagnos", "check", "health", "scan")):
            return self._diagnostics_guidance(device)

        if any(kw in q for kw in ("safe", "risk", "danger")):
            return self._safety_guidance(device)

        if any(kw in q for kw in ("battery", "charge")):
            return self._battery_guidance(device)

        if any(kw in q for kw in ("status", "state", "info", "about")):
            return self._device_status_response(device)

        # Fallback
        return self._general_help(device, current_page)

    # ── Private helpers ──────────────────────────────────────────────────────

    def _build_risk_summary(
        self,
        risk: RiskLevel,
        factors: list[str],
        action: ActionCategory,
    ) -> str:
        if risk == RiskLevel.NONE:
            return f"{action.value.title()} operation is safe to proceed."
        if risk == RiskLevel.LOW:
            return f"{action.value.title()} operation has minimal risk."
        if risk == RiskLevel.MEDIUM:
            return (
                f"{action.value.title()} operation carries moderate risk. "
                f"Key factor: {factors[0] if factors else 'N/A'}"
            )
        if risk == RiskLevel.HIGH:
            return (
                f"⚠ {action.value.title()} operation is HIGH RISK. "
                f"Factors: {'; '.join(factors[:2])}"
            )
        return (
            f"🛑 {action.value.title()} operation is CRITICAL RISK. "
            "Strongly recommend aborting unless absolutely necessary."
        )

    def _page_recommendations(
        self,
        device: DeviceInfo,
        page: str,
    ) -> list[Recommendation]:
        recs: list[Recommendation] = []

        if page == "flash" and device.bootloader_unlocked is True:
            recs.append(
                Recommendation(
                    title="Verify ROM Integrity",
                    description="Always check SHA-256 hash before flashing.",
                    category=ActionCategory.FLASH,
                    priority=6,
                    risk=RiskLevel.NONE,
                )
            )

        if page == "root" and device.is_rooted:
            recs.append(
                Recommendation(
                    title="Check Root Health",
                    description="Verify Magisk installation and SafetyNet status.",
                    category=ActionCategory.ROOT,
                    priority=5,
                    risk=RiskLevel.NONE,
                )
            )

        if page == "partition" and device.has_ab_slots:
            recs.append(
                Recommendation(
                    title="Switch Slot If Needed",
                    description=(
                        f"Currently on slot {device.active_slot.upper()}. "
                        "You can switch to the other slot if needed."
                    ),
                    category=ActionCategory.PARTITION,
                    priority=4,
                    risk=RiskLevel.LOW,
                )
            )

        return recs

    def _greeting_response(self, device: DeviceInfo | None) -> str:
        if device:
            return (
                f"Hello! I'm CyberFlash AI, your local device assistant. "
                f"I see you have **{device.display_name}** connected "
                f"({device.state.label}). How can I help you today?\n\n"
                "You can ask me about:\n"
                "• Flashing ROMs\n"
                "• Rooting your device\n"
                "• Creating backups\n"
                "• Unlocking bootloader\n"
                "• Partition management\n"
                "• Diagnostics & troubleshooting\n"
                "• Risk assessment for any operation"
            )
        return (
            "Hello! I'm CyberFlash AI, your local device assistant. "
            "No device is currently connected.\n\n"
            "**To get started:**\n"
            "1. Enable USB Debugging on your Android device\n"
            "2. Connect it via USB cable\n"
            "3. Approve the USB debugging prompt on the device\n\n"
            "Once connected, I can help with flashing, rooting, backups, "
            "and much more!"
        )

    def _flash_guidance(self, device: DeviceInfo | None) -> str:
        if not device:
            return "Connect a device first before flashing. I'll guide you through the process."
        lines = [f"**Flash Guidance for {device.display_name}:**\n"]
        if device.bootloader_unlocked is False:
            lines.append(
                "⚠ Your bootloader is **locked**. You must unlock it before "
                "flashing custom ROMs. This will erase all data!\n"
            )
        if device.state.value == "fastboot":
            lines.append("✓ Device is in fastboot mode — ready for flashing.\n")
        elif device.state.value == "recovery":
            lines.append("✓ Device is in recovery — you can sideload ROMs.\n")
        else:
            lines.append(
                "You'll need to reboot into fastboot or recovery mode to "
                "flash. Use `adb reboot bootloader` or `adb reboot recovery`.\n"
            )
        lines.append(
            "**Steps:**\n"
            "1. Ensure battery is above 50%\n"
            "2. Create a backup on the Backup page\n"
            "3. Go to Flash page and select your ROM\n"
            "4. Verify the hash integrity\n"
            "5. Start the flash operation"
        )
        return "\n".join(lines)

    def _root_guidance(self, device: DeviceInfo | None) -> str:
        if not device:
            return "Connect a device first to discuss rooting options."
        lines = [f"**Root Guidance for {device.display_name}:**\n"]
        if device.bootloader_unlocked is False:
            lines.append("⚠ Bootloader is **locked**. It must be unlocked before rooting.\n")
        if device.is_rooted:
            lines.append(
                "✓ Your device appears to be **already rooted**. Go to the "
                "Root page to manage modules and check SafetyNet.\n"
            )
        else:
            lines.append(
                "**Recommended: Magisk (Systemless Root)**\n"
                "1. Extract boot.img from your current ROM\n"
                "2. Patch it with Magisk on the device\n"
                "3. Flash the patched boot image via fastboot\n"
                "4. Reboot and verify root access"
            )
        return "\n".join(lines)

    def _backup_guidance(self, device: DeviceInfo | None) -> str:
        if not device:
            return "Connect a device to create backups."
        return (
            f"**Backup for {device.display_name}:**\n\n"
            "Available backup types:\n"
            "• **Full Backup** — Apps, data, settings via ADB backup\n"
            "• **Media Backup** — Pull photos, videos, music via ADB pull\n"
            "• **Partition Backup** — Raw partition images (requires root)\n\n"
            "Go to the **Backup page** to start. I recommend creating backups "
            "before any flash or root operation."
        )

    def _bootloader_guidance(self, device: DeviceInfo | None) -> str:
        if not device:
            return "Connect a device to check bootloader status."
        locked_str = device.bootloader_label
        return (
            f"**Bootloader Status: {locked_str}**\n\n"
            "To unlock your bootloader:\n"
            "1. Enable **OEM Unlocking** in Developer Options\n"
            "2. Reboot to fastboot: `adb reboot bootloader`\n"
            "3. Run: `fastboot flashing unlock`\n"
            "4. Confirm on device (this **ERASES ALL DATA**)\n\n"
            "⚠ **WARNING:** Unlocking the bootloader will factory reset "
            "your device. Create a backup first!"
        )

    def _rescue_guidance(self, device: DeviceInfo | None) -> str:
        return (
            "**Device Rescue / Unbrick:**\n\n"
            "If your device is bricked or stuck:\n"
            "1. Try holding Power + Volume Down for 15 sec to enter fastboot\n"
            "2. If fastboot works, flash stock firmware\n"
            "3. For Qualcomm devices: use EDL mode via the Rescue page\n"
            "4. For other chipsets: check manufacturer recovery tools\n\n"
            "Go to the **Rescue page** for guided recovery options."
        )

    def _partition_guidance(self, device: DeviceInfo | None) -> str:
        if not device:
            return "Connect a device to manage partitions."
        parts = [f"**Partition Info for {device.display_name}:**\n"]
        if device.has_ab_slots:
            parts.append(
                f"✓ A/B partition scheme detected. Active slot: "
                f"**{device.active_slot.upper() or 'Unknown'}**\n"
            )
        else:
            parts.append("Traditional (non-A/B) partition layout.\n")
        parts.append(
            "Use the **Partition page** to:\n"
            "• View partition table\n"
            "• Switch A/B slots\n"
            "• Dump, flash, or erase individual partitions\n\n"
            "⚠ **Caution:** Partition operations are dangerous — always "
            "have a backup ready."
        )
        return "\n".join(parts)

    def _nethunter_guidance(self, device: DeviceInfo | None) -> str:
        return (
            "**Kali NetHunter:**\n\n"
            "NetHunter turns your Android into a penetration testing platform.\n\n"
            "**Requirements:**\n"
            "• Unlocked bootloader\n"
            "• Root access (Magisk recommended)\n"
            "• Compatible custom kernel\n"
            "• Sufficient storage (2GB+ for chroot)\n\n"
            "Go to the **NetHunter page** to install the appropriate edition "
            "for your device."
        )

    def _diagnostics_guidance(self, device: DeviceInfo | None) -> str:
        return (
            "**Diagnostics:**\n\n"
            "The diagnostics scan checks:\n"
            "• ADB/fastboot tool availability\n"
            "• USB driver status\n"
            "• Device connectivity\n"
            "• Battery and storage health\n"
            "• Build properties\n"
            "• Logcat analysis\n\n"
            "Go to the **Diagnostics page** and click 'Run Full Scan' "
            "for a comprehensive check."
        )

    def _safety_guidance(self, device: DeviceInfo | None) -> str:
        return (
            "**Safety Tips:**\n\n"
            "• **Always backup** before flash, root, or partition operations\n"
            "• **Verify hashes** — check SHA-256 of ROMs before flashing\n"
            "• **Battery > 50%** — never flash with low battery\n"
            "• **Use official sources** — download ROMs from trusted sources\n"
            "• **Read changelogs** — understand what you're flashing\n"
            "• **Keep stock firmware** — save a copy for recovery\n\n"
            "I'll warn you about risks before any dangerous operation."
        )

    def _battery_guidance(self, device: DeviceInfo | None) -> str:
        if device and device.battery_level >= 0:
            lvl = device.battery_level
            if lvl >= 50:
                return f"Battery is at **{lvl}%** — safe for all operations. ✓"
            if lvl >= 20:
                return (
                    f"Battery is at **{lvl}%** — charge to 50% before "
                    "flashing or partition operations."
                )
            return (
                f"⚠ Battery is at **{lvl}%** — critically low! "
                "Charge to at least 50% before any operations."
            )
        return "Battery level unknown. Ensure your device is adequately charged."

    def _device_status_response(self, device: DeviceInfo | None) -> str:
        if not device:
            return "No device connected. Plug in an Android device to get started."
        lines = [
            f"**Device: {device.display_name}**\n",
            f"• Serial: `{device.serial}`",
            f"• State: **{device.state.label}**",
            f"• Android: {device.android_version or 'N/A'}",
            f"• Build: {device.build_number or 'N/A'}",
            f"• Bootloader: **{device.bootloader_label}**",
            f"• Battery: {device.battery_level}%"
            if device.battery_level >= 0
            else "• Battery: Unknown",
        ]
        if device.has_ab_slots:
            lines.append(f"• A/B Slot: **{device.active_slot.upper() or 'N/A'}**")
        if device.is_rooted:
            lines.append("• Root: ✓ Rooted")
        return "\n".join(lines)

    def _general_help(self, device: DeviceInfo | None, page: str) -> str:
        return (
            "I can help you with:\n\n"
            "• **flash** / **ROM** — Flashing guidance\n"
            "• **root** / **Magisk** — Rooting guidance\n"
            "• **backup** — Backup and restore\n"
            "• **bootloader** / **unlock** — Bootloader operations\n"
            "• **rescue** / **brick** — Device recovery\n"
            "• **partition** / **slot** — Partition management\n"
            "• **nethunter** — Kali NetHunter setup\n"
            "• **diagnostics** / **scan** — Health checks\n"
            "• **safety** / **risk** — Risk assessment\n"
            "• **status** / **info** — Device information\n\n"
            "Just type your question and I'll provide context-aware guidance!"
        )

    def _build_knowledge_base(self) -> dict[str, list[str]]:
        """Build the local knowledge base for common operations."""
        return {
            "flash_tips": [
                "Always verify ROM hash before flashing",
                "Keep a copy of stock firmware for recovery",
                "Ensure battery is above 50% before flashing",
                "Use dry-run mode to test flash commands first",
            ],
            "root_tips": [
                "Magisk is the recommended for systemless root",
                "SafetyNet can be bypassed with DenyList",
                "Always backup before rooting",
                "Root can be hidden from banking apps using Magisk modules",
            ],
            "safety_rules": [
                "Never flash firmware meant for a different device model",
                "Never interrupt a flash operation in progress",
                "Never disconnect USB during firmware operations",
                "Always have a recovery method ready before modifications",
            ],
            "edl_tips": [
                "EDL mode is Qualcomm-specific",
                "You need correct firehose programmer for your chipset",
                "EDL can recover devices that won't boot to fastboot",
                "Some devices require special cables for EDL mode",
            ],
        }
