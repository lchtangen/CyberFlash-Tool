"""Workflow orchestrator for multi-step automated operations.

Generates, validates, and tracks progress of complex workflows such as
full-flash, root, and rescue sequences.  Pure Python, no Qt dependency.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum

from cyberflash.core.ai_engine import (
    ActionCategory,
    RiskLevel,
    Workflow,
    WorkflowStep,
)
from cyberflash.models.device import DeviceInfo

logger = logging.getLogger(__name__)


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowEvent:
    """Timestamped event in a workflow execution."""

    timestamp: float
    step_id: int
    event_type: str  # "started" | "completed" | "failed" | "skipped"
    message: str


@dataclass
class WorkflowExecution:
    """Tracks the runtime state of a workflow."""

    workflow: Workflow
    status: WorkflowStatus = WorkflowStatus.PENDING
    events: list[WorkflowEvent] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0
    error_message: str = ""

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at == 0:
            return 0.0
        end = self.finished_at if self.finished_at else time.time()
        return end - self.started_at

    @property
    def current_step(self) -> WorkflowStep | None:
        for step in self.workflow.steps:
            if not step.completed:
                return step
        return None


class WorkflowEngine:
    """Plan and execute multi-step workflows.

    The engine generates workflow plans and tracks their execution.
    Actual step execution is delegated to callbacks provided by the caller
    (typically the AI worker/service layer).
    """

    def __init__(self) -> None:
        self._executions: list[WorkflowExecution] = []

    @property
    def executions(self) -> list[WorkflowExecution]:
        return list(self._executions)

    @property
    def active_execution(self) -> WorkflowExecution | None:
        for ex in self._executions:
            if ex.status == WorkflowStatus.RUNNING:
                return ex
        return None

    # ── Workflow templates ────────────────────────────────────────────────────

    def plan_full_flash(
        self,
        device: DeviceInfo,
        has_backup: bool = False,
        needs_unlock: bool = False,
    ) -> Workflow:
        """Create a comprehensive flash workflow."""
        steps: list[WorkflowStep] = []
        sid = 1

        # Pre-flight checks
        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Pre-flight Checks",
                description="Verify battery, connectivity, and tool availability.",
                category=ActionCategory.DIAGNOSTICS,
                risk=RiskLevel.NONE,
            )
        )
        sid += 1

        if not has_backup:
            steps.append(
                WorkflowStep(
                    step_id=sid,
                    title="Create Backup",
                    description="Back up all important data before proceeding.",
                    category=ActionCategory.BACKUP,
                    risk=RiskLevel.LOW,
                    skippable=True,
                )
            )
            sid += 1

        if needs_unlock:
            steps.append(
                WorkflowStep(
                    step_id=sid,
                    title="Unlock Bootloader",
                    description=("Unlock the bootloader. WARNING: This erases all data."),
                    category=ActionCategory.UNLOCK,
                    risk=RiskLevel.HIGH,
                )
            )
            sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Verify ROM Image",
                description="Check SHA-256 hash and file integrity.",
                category=ActionCategory.FLASH,
                risk=RiskLevel.NONE,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Reboot to Fastboot",
                description="Reboot the device into fastboot/bootloader mode.",
                category=ActionCategory.FLASH,
                risk=RiskLevel.LOW,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Flash Partitions",
                description="Flash all partition images to the device.",
                category=ActionCategory.FLASH,
                risk=RiskLevel.MEDIUM,
            )
        )
        sid += 1

        if device.has_ab_slots:
            steps.append(
                WorkflowStep(
                    step_id=sid,
                    title="Switch Active Slot",
                    description="Set the newly flashed slot as active.",
                    category=ActionCategory.PARTITION,
                    risk=RiskLevel.LOW,
                )
            )
            sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Reboot & Verify",
                description="Reboot and verify the device boots correctly.",
                category=ActionCategory.FLASH,
                risk=RiskLevel.NONE,
            )
        )

        return Workflow(
            name="Full Flash",
            description=f"Complete flash workflow for {device.display_name}",
            steps=steps,
        )

    def plan_rescue(self, device: DeviceInfo) -> Workflow:
        """Create a rescue/unbrick workflow."""
        steps: list[WorkflowStep] = []
        sid = 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Detect Device Mode",
                description="Identify current device state (EDL, fastboot, etc.).",
                category=ActionCategory.DIAGNOSTICS,
                risk=RiskLevel.NONE,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Load Firmware Package",
                description="Select and validate firmware/firehose images.",
                category=ActionCategory.RESCUE,
                risk=RiskLevel.NONE,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Restore Firmware",
                description="Flash stock firmware to restore the device.",
                category=ActionCategory.RESCUE,
                risk=RiskLevel.HIGH,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Reboot & Verify",
                description="Reboot and confirm the device starts normally.",
                category=ActionCategory.RESCUE,
                risk=RiskLevel.NONE,
            )
        )

        return Workflow(
            name="Device Rescue",
            description=f"Rescue workflow for {device.display_name}",
            steps=steps,
        )

    def plan_clean_slate(self, device: DeviceInfo) -> Workflow:
        """Create a clean-slate erase + reflash workflow for unbricking."""
        steps: list[WorkflowStep] = []
        sid = 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Pre-flight Checks",
                description="Verify device is in fastboot, battery OK, tools available.",
                category=ActionCategory.DIAGNOSTICS,
                risk=RiskLevel.NONE,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Load Firmware Images",
                description="Select directory containing extracted .img firmware files.",
                category=ActionCategory.FLASH,
                risk=RiskLevel.NONE,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Erase All Partitions",
                description=(
                    "Erase boot, dtbo, system, vendor, product, odm, "
                    "userdata, and cache partitions."
                ),
                category=ActionCategory.PARTITION,
                risk=RiskLevel.CRITICAL,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Disable vbmeta Verification",
                description="Flash vbmeta with --disable-verity --disable-verification.",
                category=ActionCategory.FLASH,
                risk=RiskLevel.LOW,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Flash All Partitions",
                description="Flash fresh images to every partition.",
                category=ActionCategory.FLASH,
                risk=RiskLevel.HIGH,
            )
        )
        sid += 1

        if device.has_ab_slots:
            steps.append(
                WorkflowStep(
                    step_id=sid,
                    title="Switch Active Slot",
                    description="Set the newly flashed slot as active.",
                    category=ActionCategory.PARTITION,
                    risk=RiskLevel.LOW,
                )
            )
            sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Reboot & Verify",
                description="Reboot to system and confirm device boots correctly.",
                category=ActionCategory.RESCUE,
                risk=RiskLevel.NONE,
            )
        )

        return Workflow(
            name="Clean Slate Reflash",
            description=f"Erase + reflash for {device.display_name} (unbrick)",
            steps=steps,
        )

    def plan_nethunter_install(self, device: DeviceInfo) -> Workflow:
        """Create a NetHunter installation workflow."""
        steps: list[WorkflowStep] = []
        sid = 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Verify Prerequisites",
                description="Check root, kernel, and storage requirements.",
                category=ActionCategory.DIAGNOSTICS,
                risk=RiskLevel.NONE,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Backup Current Setup",
                description="Back up current system state.",
                category=ActionCategory.BACKUP,
                risk=RiskLevel.LOW,
                skippable=True,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Flash Custom Kernel",
                description="Flash NetHunter-compatible kernel.",
                category=ActionCategory.NETHUNTER,
                risk=RiskLevel.MEDIUM,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Install NetHunter",
                description="Flash NetHunter zip via recovery.",
                category=ActionCategory.NETHUNTER,
                risk=RiskLevel.MEDIUM,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Setup Chroot",
                description="Configure Kali Linux chroot environment.",
                category=ActionCategory.NETHUNTER,
                risk=RiskLevel.LOW,
            )
        )
        sid += 1

        steps.append(
            WorkflowStep(
                step_id=sid,
                title="Verify Installation",
                description="Confirm NetHunter app and tools are functional.",
                category=ActionCategory.NETHUNTER,
                risk=RiskLevel.NONE,
            )
        )

        return Workflow(
            name="NetHunter Install",
            description=f"NetHunter setup for {device.display_name}",
            steps=steps,
        )

    # ── Execution tracking ───────────────────────────────────────────────────

    def start_execution(self, workflow: Workflow) -> WorkflowExecution:
        """Begin tracking a workflow execution."""
        execution = WorkflowExecution(
            workflow=workflow,
            status=WorkflowStatus.RUNNING,
            started_at=time.time(),
        )
        self._executions.append(execution)
        logger.info("Started workflow: %s", workflow.name)
        return execution

    def complete_step(
        self,
        execution: WorkflowExecution,
        step_id: int,
        message: str = "",
    ) -> None:
        """Mark a step as completed."""
        for step in execution.workflow.steps:
            if step.step_id == step_id:
                step.completed = True
                execution.events.append(
                    WorkflowEvent(
                        timestamp=time.time(),
                        step_id=step_id,
                        event_type="completed",
                        message=message or f"Completed: {step.title}",
                    )
                )
                logger.info("Step %d completed: %s", step_id, step.title)

                if execution.workflow.is_complete:
                    execution.status = WorkflowStatus.COMPLETED
                    execution.finished_at = time.time()
                    logger.info("Workflow completed: %s", execution.workflow.name)
                return
        logger.warning("Step %d not found in workflow", step_id)

    def fail_step(
        self,
        execution: WorkflowExecution,
        step_id: int,
        error: str,
    ) -> None:
        """Mark a step and the workflow as failed."""
        execution.status = WorkflowStatus.FAILED
        execution.error_message = error
        execution.finished_at = time.time()
        execution.events.append(
            WorkflowEvent(
                timestamp=time.time(),
                step_id=step_id,
                event_type="failed",
                message=error,
            )
        )
        logger.error("Workflow failed at step %d: %s", step_id, error)

    def skip_step(
        self,
        execution: WorkflowExecution,
        step_id: int,
    ) -> None:
        """Skip an optional step."""
        for step in execution.workflow.steps:
            if step.step_id == step_id and step.skippable:
                step.completed = True
                execution.events.append(
                    WorkflowEvent(
                        timestamp=time.time(),
                        step_id=step_id,
                        event_type="skipped",
                        message=f"Skipped: {step.title}",
                    )
                )
                logger.info("Skipped step %d: %s", step_id, step.title)
                return

    def cancel_execution(self, execution: WorkflowExecution) -> None:
        """Cancel a running workflow."""
        execution.status = WorkflowStatus.CANCELLED
        execution.finished_at = time.time()
        logger.info("Workflow cancelled: %s", execution.workflow.name)

    def get_execution_summary(self, execution: WorkflowExecution) -> str:
        """Return a human-readable summary of a workflow execution."""
        wf = execution.workflow
        lines = [
            f"**{wf.name}** — {execution.status.value.title()}",
            f"{wf.description}",
            "",
            "**Steps:**",
        ]
        for step in wf.steps:
            mark = "✓" if step.completed else "○"
            risk_str = f" [{step.risk.label}]" if step.risk != RiskLevel.NONE else ""
            lines.append(f"  {mark} {step.title}{risk_str}")
        lines.append("")
        lines.append(f"Progress: {wf.progress:.0%} | Elapsed: {execution.elapsed_seconds:.0f}s")
        if execution.error_message:
            lines.append(f"Error: {execution.error_message}")
        return "\n".join(lines)
