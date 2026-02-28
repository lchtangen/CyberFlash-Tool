"""tachometer_gauge.py — Circular arc gauge for performance / health metrics.

Usage::

    gauge = TachometerGauge(parent)
    gauge.set_label("Battery")
    gauge.set_max(100.0)
    gauge.set_value(73.0)
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

logger = logging.getLogger(__name__)

# Arc from 225° to 315° (clockwise, -225 deg start, 270 deg span)
_ARC_START_DEG = 225
_ARC_SPAN_DEG = 270


def _value_to_color(ratio: float) -> QColor:
    """Return green->yellow->red depending on *ratio* (0.0-1.0)."""
    if ratio < 0.5:
        r = int(ratio * 2 * 255)
        g = 200
    else:
        r = 200
        g = int((1.0 - ratio) * 2 * 255)
    return QColor(max(0, min(255, r)), max(0, min(255, g)), 40)


class TachometerGauge(QWidget):
    """Circular arc gauge widget drawn with QPainter.

    Args:
        parent: Optional parent widget.
        value: Initial value (default 0.0).
        maximum: Maximum value (default 100.0).
        label: Label text shown below the numeric readout.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        value: float = 0.0,
        maximum: float = 100.0,
        label: str = "",
    ) -> None:
        super().__init__(parent)
        self._value = float(value)
        self._max = float(maximum) if maximum > 0 else 100.0
        self._label = label
        self.setObjectName("TachometerGauge")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(80, 80)

    def set_value(self, value: float) -> None:
        """Update the gauge needle position."""
        self._value = max(0.0, min(float(value), self._max))
        self.update()

    def set_max(self, maximum: float) -> None:
        """Change the scale maximum."""
        self._max = float(maximum) if maximum > 0 else 100.0
        self.update()

    def set_label(self, label: str) -> None:
        """Set the label displayed under the numeric value."""
        self._label = label
        self.update()

    def value(self) -> float:
        """Return the current gauge value."""
        return self._value

    def maximum(self) -> float:
        """Return the gauge maximum."""
        return self._max

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            side = min(self.width(), self.height())
            painter.translate((self.width() - side) / 2, (self.height() - side) / 2)
            scale_f = side / 200.0
            painter.scale(scale_f, scale_f)

            rect = QRectF(16, 16, 168, 168)

            # Background circle
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#161b22"))
            painter.drawEllipse(rect)

            # Track arc (dim)
            track_pen = QPen(QColor("#30363d"), 14, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(track_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(rect, _ARC_START_DEG * 16, -_ARC_SPAN_DEG * 16)

            # Value arc
            ratio = self._value / self._max if self._max > 0 else 0.0
            span = int(ratio * _ARC_SPAN_DEG)
            val_pen = QPen(
                _value_to_color(ratio), 14, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap
            )
            painter.setPen(val_pen)
            painter.drawArc(rect, _ARC_START_DEG * 16, -span * 16)

            # Numeric value text
            painter.setPen(QColor("#e6edf3"))
            val_font = QFont()
            val_font.setPointSize(28)
            val_font.setBold(True)
            painter.setFont(val_font)
            val_str = f"{self._value:.0f}"
            painter.drawText(QRectF(0, 60, 200, 70), Qt.AlignmentFlag.AlignCenter, val_str)

            # Label text
            if self._label:
                painter.setPen(QColor("#8b949e"))
                lbl_font = QFont()
                lbl_font.setPointSize(10)
                painter.setFont(lbl_font)
                painter.drawText(
                    QRectF(0, 118, 200, 30), Qt.AlignmentFlag.AlignCenter, self._label
                )
        finally:
            painter.end()
