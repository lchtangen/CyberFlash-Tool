"""scheduler_service.py — Scheduled device operation service (Phase 9).

Manages a list of ScheduledJob entries.  Each job has a QTimer that fires
at the requested interval or at a specific UTC time and emits :pyobj:`job_triggered`.
The UI can connect to that signal to launch the corresponding worker.

Usage::

    svc = SchedulerService(parent_widget)
    job_id = svc.schedule_once(
        name="Nightly Backup",
        target_utc="02:00",
        payload={"operation": "backup", "serial": "ABC123"},
    )
    svc.job_triggered.connect(on_job_triggered)
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass

from PySide6.QtCore import QObject, QTimer, Signal

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    """A single scheduled job descriptor."""

    job_id: str
    name: str
    payload: dict[str, object]
    repeat_interval_ms: int = 0   # 0 = one-shot
    target_utc_hhmm: str = ""     # "HH:MM" wall-clock daily trigger
    enabled: bool = True
    last_run_iso: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ScheduledJob:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class SchedulerService(QObject):
    """QObject service that owns and fires scheduled jobs.

    Signals:
        job_triggered(str, dict): job_id + payload when a job fires.
        job_added(str): job_id of a newly registered job.
        job_removed(str): job_id of a removed job.
    """

    job_triggered = Signal(str, dict)
    job_added = Signal(str)
    job_removed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._jobs: dict[str, ScheduledJob] = {}
        self._timers: dict[str, QTimer] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schedule_interval(
        self,
        name: str,
        interval_ms: int,
        payload: dict[str, object] | None = None,
    ) -> str:
        """Register a repeating job that fires every *interval_ms* ms."""
        job = ScheduledJob(
            job_id=str(uuid.uuid4()),
            name=name,
            payload=payload or {},
            repeat_interval_ms=interval_ms,
        )
        self._register(job)
        return job.job_id

    def schedule_daily(
        self,
        name: str,
        hhmm: str,
        payload: dict[str, object] | None = None,
    ) -> str:
        """Register a job that fires every day at *hhmm* UTC (e.g. ``"02:30"``)."""
        job = ScheduledJob(
            job_id=str(uuid.uuid4()),
            name=name,
            payload=payload or {},
            target_utc_hhmm=hhmm,
        )
        self._register(job)
        # Use a 60-s poll timer to check wall clock
        timer = QTimer(self)
        timer.setInterval(60_000)
        timer.timeout.connect(lambda jid=job.job_id: self._check_daily(jid))
        timer.start()
        self._timers[job.job_id] = timer
        logger.info("Scheduled daily job '%s' at %s UTC", name, hhmm)
        self.job_added.emit(job.job_id)
        return job.job_id

    def remove_job(self, job_id: str) -> bool:
        """Cancel and remove a job. Returns ``False`` if not found."""
        if job_id not in self._jobs:
            return False
        timer = self._timers.pop(job_id, None)
        if timer:
            timer.stop()
            timer.deleteLater()
        del self._jobs[job_id]
        logger.info("Removed scheduled job %s", job_id)
        self.job_removed.emit(job_id)
        return True

    def enable_job(self, job_id: str, enabled: bool = True) -> bool:
        """Enable or disable a job without removing it."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.enabled = enabled
        timer = self._timers.get(job_id)
        if timer:
            if enabled:
                timer.start()
            else:
                timer.stop()
        return True

    def list_jobs(self) -> list[ScheduledJob]:
        """Return a snapshot of all registered jobs."""
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> ScheduledJob | None:
        """Return the job descriptor for *job_id*, or ``None``."""
        return self._jobs.get(job_id)

    def export_jobs(self) -> str:
        """Serialise all jobs to a JSON string."""
        return json.dumps(
            [j.to_dict() for j in self._jobs.values()], indent=2
        )

    def import_jobs(self, json_str: str) -> int:
        """Import jobs from a JSON string. Returns number of jobs imported."""
        try:
            data = json.loads(json_str)
            count = 0
            for entry in data:
                job = ScheduledJob.from_dict(entry)
                self._register(job)
                count += 1
            return count
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning("import_jobs failed: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _register(self, job: ScheduledJob) -> None:
        """Register a job and create its QTimer."""
        self._jobs[job.job_id] = job
        if job.repeat_interval_ms > 0:
            timer = QTimer(self)
            timer.setInterval(job.repeat_interval_ms)
            timer.timeout.connect(lambda jid=job.job_id: self._fire(jid))
            timer.start()
            self._timers[job.job_id] = timer
        logger.info("Registered job '%s' (%s)", job.name, job.job_id)
        self.job_added.emit(job.job_id)

    def _fire(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job or not job.enabled:
            return
        import datetime
        job.last_run_iso = datetime.datetime.now(datetime.UTC).isoformat()
        logger.info("Job fired: %s (%s)", job.name, job_id)
        self.job_triggered.emit(job_id, job.payload)

        if job.repeat_interval_ms == 0:
            # one-shot — remove timer but keep job record
            timer = self._timers.pop(job_id, None)
            if timer:
                timer.stop()
                timer.deleteLater()

    def _check_daily(self, job_id: str) -> None:
        import datetime

        job = self._jobs.get(job_id)
        if not job or not job.enabled or not job.target_utc_hhmm:
            return
        now = datetime.datetime.now(datetime.UTC)
        current_hhmm = now.strftime("%H:%M")
        if current_hhmm == job.target_utc_hhmm:
            # Fire only once per minute
            today_prefix = now.strftime("%Y-%m-%dT%H:%M")
            if not job.last_run_iso.startswith(today_prefix):
                self._fire(job_id)
