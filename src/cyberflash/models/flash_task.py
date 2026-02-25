from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class StepStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FlashStep:
    id: str  # unique key, e.g. "flash_boot"
    label: str  # display text, e.g. "Flash boot partition"
    status: StepStatus = StepStatus.PENDING
    skippable: bool = False


@dataclass
class FlashTask:
    device_serial: str
    profile_codename: str
    steps: list[FlashStep]
    dry_run: bool = False
    log_lines: list[str] = field(default_factory=list)
    current_step_index: int = 0
    failed_reason: str = ""
