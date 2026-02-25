"""notification_panel.py — Slide-in notification drawer.

Provides a right-edge notification drawer with badge count, per-notification
levels, and mark-all-read / clear-all functionality.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# ── Enums / Dataclasses ──────────────────────────────────────────────────────


class NotificationLevel(StrEnum):
    INFO    = "info"
    WARNING = "warning"
    ERROR   = "error"
    SUCCESS = "success"


@dataclass
class Notification:
    """A single notification entry."""

    id: str
    level: NotificationLevel
    title: str
    body: str
    timestamp: str
    read: bool = False


_LEVEL_COLORS: dict[NotificationLevel, str] = {
    NotificationLevel.INFO:    "#00aaff",
    NotificationLevel.WARNING: "#ffaa00",
    NotificationLevel.ERROR:   "#ff4444",
    NotificationLevel.SUCCESS: "#00ff88",
}


# ── Notification card widget ──────────────────────────────────────────────────


class _NotificationCard(QFrame):
    dismissed = Signal(str)  # notification id

    def __init__(self, notification: Notification, parent=None) -> None:
        super().__init__(parent)
        self._notification = notification
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("notificationCard")
        color = _LEVEL_COLORS.get(self._notification.level, "#00aaff")
        self.setStyleSheet(
            f"QFrame#notificationCard {{"
            f"  border-left: 3px solid {color};"
            f"  background: #0d1117;"
            f"  border-radius: 4px;"
            f"  margin: 2px 0;"
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        # Header row
        header = QHBoxLayout()
        title_lbl = QLabel(self._notification.title)
        title_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 12px;")
        header.addWidget(title_lbl)
        header.addStretch()

        ts_lbl = QLabel(self._notification.timestamp[:19] if self._notification.timestamp else "")
        ts_lbl.setStyleSheet("color: #484f58; font-size: 10px;")
        header.addWidget(ts_lbl)

        dismiss_btn = QPushButton("x")
        dismiss_btn.setFixedSize(16, 16)
        dismiss_btn.setStyleSheet("QPushButton { color: #484f58; border: none; background: transparent; }")
        dismiss_btn.clicked.connect(lambda: self.dismissed.emit(self._notification.id))
        header.addWidget(dismiss_btn)
        layout.addLayout(header)

        if self._notification.body:
            body_lbl = QLabel(self._notification.body)
            body_lbl.setWordWrap(True)
            body_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
            layout.addWidget(body_lbl)


# ── Main panel ────────────────────────────────────────────────────────────────


class NotificationPanel(QWidget):
    """Notification drawer panel.

    Signals:
        notification_added(Notification)  — when a notification is added
    """

    notification_added = Signal(object)  # Notification

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._notifications: list[Notification] = []
        self._counter = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("notificationPanel")
        self.setMinimumWidth(320)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(6)

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        self._title_lbl = QLabel("Notifications")
        self._title_lbl.setObjectName("sectionLabel")
        header.addWidget(self._title_lbl)
        header.addStretch()

        self._badge = QLabel("0")
        self._badge.setFixedSize(20, 20)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setStyleSheet(
            "QLabel { background: #ff4444; color: white; border-radius: 10px;"
            " font-size: 10px; font-weight: bold; }"
        )
        self._badge.setVisible(False)
        header.addWidget(self._badge)

        read_all_btn = QPushButton("Mark read")
        read_all_btn.setObjectName("secondaryButton")
        read_all_btn.clicked.connect(self.mark_all_read)
        header.addWidget(read_all_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("secondaryButton")
        clear_btn.clicked.connect(self.clear_all)
        header.addWidget(clear_btn)

        root_layout.addLayout(header)

        # ── Scroll area ───────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._list_layout.setSpacing(4)
        self._list_layout.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self._list_widget)
        root_layout.addWidget(scroll)

    def add_notification(
        self,
        level: NotificationLevel,
        title: str,
        body: str = "",
    ) -> Notification:
        """Add a notification.  Safe to call from any thread via Qt's queued connection."""
        import datetime

        self._counter += 1
        notif = Notification(
            id=f"notif_{self._counter}",
            level=level,
            title=title,
            body=body,
            timestamp=datetime.datetime.utcnow().isoformat() + "Z",
        )
        self._notifications.append(notif)

        card = _NotificationCard(notif)
        card.dismissed.connect(self._remove_notification)
        self._list_layout.insertWidget(0, card)

        self._update_badge()
        self.notification_added.emit(notif)
        return notif

    def _remove_notification(self, notif_id: str) -> None:
        self._notifications = [n for n in self._notifications if n.id != notif_id]
        # Remove card widget from layout
        for i in range(self._list_layout.count()):
            item = self._list_layout.itemAt(i)
            if item and item.widget():
                card = item.widget()
                if isinstance(card, _NotificationCard) and card._notification.id == notif_id:
                    card.deleteLater()
                    break
        self._update_badge()

    def mark_all_read(self) -> None:
        """Mark all notifications as read and hide badge."""
        for n in self._notifications:
            n.read = True
        self._update_badge()

    def clear_all(self) -> None:
        """Remove all notifications."""
        self._notifications.clear()
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._update_badge()

    def _update_badge(self) -> None:
        unread = sum(1 for n in self._notifications if not n.read)
        self._badge.setText(str(unread))
        self._badge.setVisible(unread > 0)
