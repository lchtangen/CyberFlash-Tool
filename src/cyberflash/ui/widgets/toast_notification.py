"""toast_notification.py — Transient toast / snackbar notification widget.

Displays a brief message in the bottom-right corner of the parent window
that fades out automatically after a configurable duration.

Usage::

    ToastNotification.show(parent_widget, "Profile downloaded!", variant="success")
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget

logger = logging.getLogger(__name__)

_VARIANTS: dict[str, str] = {
    "success": "#1a472a",
    "warning": "#4d3800",
    "error":   "#4d1010",
    "info":    "#0a2a4d",
    "neutral": "#1e1e2e",
}
_TEXT_COLORS: dict[str, str] = {
    "success": "#2ea043",
    "warning": "#e3b341",
    "error":   "#f85149",
    "info":    "#58a6ff",
    "neutral": "#c9d1d9",
}


class ToastNotification(QLabel):
    """Floating toast message that auto-dismisses.

    Args:
        parent: Parent widget (controls positioning).
        message: Text to display.
        variant: "success" | "warning" | "error" | "info" | "neutral".
        duration_ms: How long before the toast fades out (default 3000 ms).
    """

    def __init__(
        self,
        parent: QWidget,
        message: str,
        variant: str = "neutral",
        duration_ms: int = 3000,
    ) -> None:
        super().__init__(message, parent)
        bg = _VARIANTS.get(variant, _VARIANTS["neutral"])
        fg = _TEXT_COLORS.get(variant, _TEXT_COLORS["neutral"])
        self.setStyleSheet(
            f"QLabel {{ background: {bg}; color: {fg}; border-radius: 8px; "
            f"padding: 10px 18px; font-size: 13px; font-weight: 500; }}"
        )
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.adjustSize()
        self._position_in_parent()
        super().show()
        self.raise_()

        QTimer.singleShot(duration_ms, self._start_fade)

    def _position_in_parent(self) -> None:
        parent = self.parent()
        if not isinstance(parent, QWidget):
            return
        pw, ph = parent.width(), parent.height()
        margin = 20
        self.move(pw - self.width() - margin, ph - self.height() - margin)

    def _start_fade(self) -> None:
        self.deleteLater()

    @classmethod
    def show_toast(
        cls,
        parent: QWidget,
        message: str,
        variant: str = "neutral",
        duration_ms: int = 3000,
    ) -> ToastNotification:
        """Convenience factory.  Returns the created toast."""
        return cls(parent, message, variant=variant, duration_ms=duration_ms)
