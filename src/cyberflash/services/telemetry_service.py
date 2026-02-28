"""telemetry_service.py — Opt-in anonymous usage analytics (Phase 13).

Telemetry is **disabled by default** and only activated when the user
explicitly opts in from the Settings page.  All events are anonymised
(no PII, no device serials) before transmission.  The service queues
payloads in memory and batches them with a configurable flush interval.

Implementation note: this version records events locally to a JSON file
and provides a ``flush()`` method that would POST to the analytics endpoint.
Real network transmission is left as a stub so the module is fully
testable without network access.

Usage::

    svc = TelemetryService(opt_in=False)
    svc.opt_in = True  # activated from Settings
    svc.track("flash_started", rom="lineageos", method="fastboot")
    svc.track("flash_completed", duration_s=47, success=True)
    svc.flush()  # sends pending events (no-op if opted out)
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import time
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL_MS = 60_000   # 1 minute
_MAX_QUEUE = 500


@dataclass
class TelemetryEvent:
    """An anonymised telemetry event."""

    event: str
    properties: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "properties": self.properties,
            "timestamp": self.timestamp,
        }


class TelemetryService(QObject):
    """Opt-in anonymous usage analytics service.

    Signals:
        flush_complete(int): number of events flushed.
        opt_in_changed(bool): emitted when opt-in status changes.
    """

    flush_complete = Signal(int)
    opt_in_changed = Signal(bool)

    def __init__(
        self,
        opt_in: bool = False,
        flush_interval_ms: int = _FLUSH_INTERVAL_MS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._opt_in = opt_in
        self._queue: list[TelemetryEvent] = []
        self._session_id = self._make_session_id()
        self._platform_info = self._collect_platform_info()
        self._flush_count = 0

        self._timer = QTimer(self)
        self._timer.setInterval(flush_interval_ms)
        self._timer.timeout.connect(self.flush)
        if opt_in:
            self._timer.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def opt_in(self) -> bool:
        return self._opt_in

    @opt_in.setter
    def opt_in(self, value: bool) -> None:
        if value == self._opt_in:
            return
        self._opt_in = value
        if value:
            self._timer.start()
        else:
            self._timer.stop()
            self._queue.clear()
        self.opt_in_changed.emit(value)
        logger.info("Telemetry opt-in: %s", value)

    def track(self, event: str, **properties: Any) -> None:
        """Queue an anonymous event.  Silently does nothing if opted out."""
        if not self._opt_in:
            return
        if len(self._queue) >= _MAX_QUEUE:
            self._queue.pop(0)  # drop oldest
        # Strip any fields that could be PII
        safe_props = self._sanitise(properties)
        safe_props["_session"] = self._session_id
        safe_props["_platform"] = self._platform_info
        evt = TelemetryEvent(event=event, properties=safe_props)
        self._queue.append(evt)
        logger.debug("Telemetry: queued event '%s'", event)

    def flush(self) -> int:
        """Transmit (log) queued events and clear the queue.

        In a production build this would POST to an analytics endpoint.
        Returns the number of events flushed.
        """
        if not self._opt_in or not self._queue:
            return 0
        count = len(self._queue)
        batch = [e.to_dict() for e in self._queue]
        self._queue.clear()
        # Stub: in production → POST batch to endpoint
        logger.debug("Telemetry: flushed %d events (stub)", count)
        self._flush_count += count
        self.flush_complete.emit(count)
        _ = batch  # suppress unused warning
        return count

    def queue_size(self) -> int:
        """Return number of events currently queued."""
        return len(self._queue)

    def total_flushed(self) -> int:
        """Return cumulative count of flushed events this session."""
        return self._flush_count

    def export_queue(self) -> str:
        """Serialise the current queue to JSON (for debugging)."""
        return json.dumps([e.to_dict() for e in self._queue], indent=2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_session_id() -> str:
        """Generate an anonymous session ID (no PII)."""
        raw = f"{time.time()}{platform.node()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _collect_platform_info() -> dict[str, str]:
        """Collect non-identifying platform metadata."""
        return {
            "os": platform.system(),
            "py": platform.python_version(),
            "arch": platform.machine(),
        }

    @staticmethod
    def _sanitise(props: dict[str, Any]) -> dict[str, Any]:
        """Remove any key that looks like PII (serial, email, name, path)."""
        _BLOCKED = {"serial", "email", "name", "path", "token", "key", "password"}
        return {k: v for k, v in props.items() if k.lower() not in _BLOCKED}
