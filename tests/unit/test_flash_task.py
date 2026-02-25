"""Tests for models/flash_task.py"""
from __future__ import annotations

from cyberflash.models.flash_task import FlashStep, FlashTask, StepStatus


def test_step_status_enum_values() -> None:
    assert StepStatus.PENDING == "pending"
    assert StepStatus.ACTIVE == "active"
    assert StepStatus.COMPLETED == "completed"
    assert StepStatus.FAILED == "failed"
    assert StepStatus.SKIPPED == "skipped"


def test_flash_task_current_step_default() -> None:
    task = FlashTask(
        device_serial="ABC123",
        profile_codename="guacamole",
        steps=[],
    )
    assert task.current_step_index == 0
    assert task.dry_run is False
    assert task.log_lines == []
    assert task.failed_reason == ""


def test_flash_step_label_and_status() -> None:
    step = FlashStep(id="flash_boot", label="Flash boot partition")
    assert step.id == "flash_boot"
    assert step.label == "Flash boot partition"
    assert step.status == StepStatus.PENDING
    assert step.skippable is False

    step.status = StepStatus.COMPLETED
    assert step.status == StepStatus.COMPLETED
