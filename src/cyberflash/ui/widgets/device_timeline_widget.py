"""device_timeline_widget.py — Scrollable event timeline for device operations.

Usage::

    timeline = DeviceTimelineWidget(parent)
    timeline.add_event("2025-01-15 12:00:01", "Flash started", "info")
    timeline.add_event("2025-01-15 12:01:45", "Partition wiped", "warning")
    timeline.add_event("2025-01-15 12:02:03", "Flash complete", "success")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_TYPE_COLORS: dict[str, str] = {
    "success": "#2ea043",
    "warning": "#e3b341",
    "error":   "#f85149",
    "info":    "#58a6ff",
    "neutral": "#8b949e",
}


@dataclass
class TimelineEvent:
    """A single timestamped event entry."""

    timestamp: str
    label: str
    event_type: str = "neutral"


class _EventRow(QFrame):
    """Compact one-line event row with a coloured type badge."""

    def __init__(self, event: TimelineEvent, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TimelineEventRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(8)

        badge = QLabel(event.event_type.upper(), self)
        badge.setObjectName("TimelineTypeBadge")
        color = _TYPE_COLORS.get(event.event_type, _TYPE_COLORS["neutral"])
        badge.setStyleSheet(
            f"QLabel {{ color: {color}; font-size: 10px; font-weight: 700; "
            f"min-width: 58px; max-width: 58px; }}"
        )
        layout.addWidget(badge)

        ts_label = QLabel(event.timestamp, self)
        ts_label.setObjectName("TimelineTimestamp")
        ts_label.setStyleSheet("QLabel { color: #8b949e; font-size: 11px; }")
        ts_label.setFixedWidth(160)
        layout.addWidget(ts_label)

        msg_label = QLabel(event.label, self)
        msg_label.setObjectName("TimelineMessage")
        msg_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(msg_label)


class DeviceTimelineWidget(QWidget):
    """Chronological event list with coloured type badges.

    Args:
        parent: Optional parent widget.
        max_events: Maximum number of events kept (oldest are discarded).
    """

    def __init__(self, parent: QWidget | None = None, max_events: int = 500) -> None:
        super().__init__(parent)
        self._events: list[TimelineEvent] = []
        self._max_events = max_events
        self.setObjectName("DeviceTimelineWidget")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setObjectName("TimelineScrollArea")
        outer.addWidget(self._scroll)

        self._inner = QWidget()
        self._inner.setObjectName("TimelineInner")
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(1)
        self._inner_layout.addStretch(1)
        self._scroll.setWidget(self._inner)

    def add_event(
        self,
        timestamp: str,
        label: str,
        event_type: str = "neutral",
    ) -> None:
        """Append an event row at the bottom of the timeline."""
        evt = TimelineEvent(timestamp=timestamp, label=label, event_type=event_type)
        self._events.append(evt)
        if len(self._events) > self._max_events:
            excess = len(self._events) - self._max_events
            self._events = self._events[excess:]
            # Remove oldest rows from layout (before the stretch)
            for _ in range(excess):
                item = self._inner_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()

        row = _EventRow(evt, self._inner)
        # Insert before the trailing stretch
        stretch_idx = self._inner_layout.count() - 1
        self._inner_layout.insertWidget(stretch_idx, row)

        # Auto-scroll to bottom
        sb = self._scroll.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def clear(self) -> None:
        """Remove all events from the timeline."""
        self._events = []
        while self._inner_layout.count() > 1:
            item = self._inner_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

    def event_count(self) -> int:
        """Return the number of events currently displayed."""
        return len(self._events)
