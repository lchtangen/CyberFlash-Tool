"""tests/unit/test_scheduler_service.py — Unit tests for SchedulerService."""

from __future__ import annotations

import json

from cyberflash.services.scheduler_service import ScheduledJob, SchedulerService

# ---------------------------------------------------------------------------
# ScheduledJob dataclass
# ---------------------------------------------------------------------------


class TestScheduledJob:
    def test_to_dict_roundtrip(self) -> None:
        job = ScheduledJob(
            job_id="abc-123",
            name="Daily backup",
            payload={"op": "backup"},
            repeat_interval_ms=3600000,
            enabled=True,
        )
        d = job.to_dict()
        job2 = ScheduledJob.from_dict(d)
        assert job2.job_id == job.job_id
        assert job2.name == job.name
        assert job2.repeat_interval_ms == job.repeat_interval_ms

    def test_from_dict_ignores_extra_keys(self) -> None:
        data = {
            "job_id": "x",
            "name": "test",
            "payload": {},
            "unknown_key": "ignored",
        }
        job = ScheduledJob.from_dict(data)
        assert job.name == "test"


# ---------------------------------------------------------------------------
# SchedulerService
# ---------------------------------------------------------------------------


class TestSchedulerService:
    def test_schedule_interval_returns_id(self, qapp: object) -> None:
        svc = SchedulerService()
        job_id = svc.schedule_interval("MyJob", 5000, {"x": 1})
        assert isinstance(job_id, str)
        assert len(job_id) > 0

    def test_schedule_interval_adds_job(self, qapp: object) -> None:
        svc = SchedulerService()
        job_id = svc.schedule_interval("MyJob", 5000)
        assert svc.get_job(job_id) is not None

    def test_schedule_daily_returns_id(self, qapp: object) -> None:
        svc = SchedulerService()
        job_id = svc.schedule_daily("NightlyBackup", "02:30")
        assert isinstance(job_id, str)
        job = svc.get_job(job_id)
        assert job is not None
        assert job.target_utc_hhmm == "02:30"

    def test_remove_job_returns_true(self, qapp: object) -> None:
        svc = SchedulerService()
        job_id = svc.schedule_interval("TempJob", 1000)
        assert svc.remove_job(job_id) is True
        assert svc.get_job(job_id) is None

    def test_remove_nonexistent_returns_false(self, qapp: object) -> None:
        svc = SchedulerService()
        assert svc.remove_job("does-not-exist") is False

    def test_list_jobs_empty_initially(self, qapp: object) -> None:
        svc = SchedulerService()
        assert svc.list_jobs() == []

    def test_list_jobs_after_add(self, qapp: object) -> None:
        svc = SchedulerService()
        svc.schedule_interval("A", 1000)
        svc.schedule_interval("B", 2000)
        assert len(svc.list_jobs()) == 2

    def test_enable_disable_job(self, qapp: object) -> None:
        svc = SchedulerService()
        job_id = svc.schedule_interval("ToggleMe", 1000)
        assert svc.enable_job(job_id, enabled=False) is True
        assert svc.get_job(job_id).enabled is False
        assert svc.enable_job(job_id, enabled=True) is True
        assert svc.get_job(job_id).enabled is True

    def test_enable_nonexistent_returns_false(self, qapp: object) -> None:
        svc = SchedulerService()
        assert svc.enable_job("ghost-id") is False

    def test_export_jobs_valid_json(self, qapp: object) -> None:
        svc = SchedulerService()
        svc.schedule_interval("ExportMe", 1000, {"k": "v"})
        export_str = svc.export_jobs()
        data = json.loads(export_str)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "ExportMe"

    def test_import_jobs_restores_count(self, qapp: object) -> None:
        svc = SchedulerService()
        svc.schedule_interval("A", 1000)
        svc.schedule_interval("B", 2000)
        export_str = svc.export_jobs()

        svc2 = SchedulerService()
        count = svc2.import_jobs(export_str)
        assert count == 2
        assert len(svc2.list_jobs()) == 2

    def test_job_added_signal(self, qapp: object) -> None:
        from PySide6.QtTest import QSignalSpy

        svc = SchedulerService()
        spy = QSignalSpy(svc.job_added)
        svc.schedule_interval("SignalJob", 500)
        assert len(spy) >= 1

    def test_job_removed_signal(self, qapp: object) -> None:
        from PySide6.QtTest import QSignalSpy

        svc = SchedulerService()
        spy = QSignalSpy(svc.job_removed)
        job_id = svc.schedule_interval("RemoveMeSignal", 500)
        svc.remove_job(job_id)
        assert len(spy) >= 1
