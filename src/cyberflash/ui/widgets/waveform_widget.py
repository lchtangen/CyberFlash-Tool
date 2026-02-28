"""waveform_widget.py — Signal / audio waveform visualisation widget.

Usage::

    wave = WaveformWidget(parent)
    wave.set_color("#58a6ff")
    wave.set_data([0.1, 0.5, -0.3, 0.9, -0.8, 0.0])   # values -1.0 to 1.0
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

logger = logging.getLogger(__name__)

_DEFAULT_COLOR = "#58a6ff"


class WaveformWidget(QWidget):
    """Draws a filled waveform from normalised samples (-1.0 to 1.0).

    Args:
        parent: Parent widget.
        color: Initial waveform colour (CSS hex string).
    """

    def __init__(self, parent: QWidget | None = None, color: str = _DEFAULT_COLOR) -> None:
        super().__init__(parent)
        self._samples: list[float] = []
        self._color = QColor(color)
        self.setObjectName("WaveformWidget")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(60)

    def set_data(self, samples: list[float]) -> None:
        """Replace the current waveform data. Values outside -1 to 1 are clamped."""
        self._samples = [max(-1.0, min(1.0, float(s))) for s in samples]
        self.update()

    def set_color(self, hex_str: str) -> None:
        """Set the waveform draw colour (CSS hex, e.g. ``"#2ea043"``)."""
        self._color = QColor(hex_str)
        self.update()

    def clear(self) -> None:
        """Remove all samples."""
        self._samples = []
        self.update()

    def sample_count(self) -> int:
        """Return the number of samples currently loaded."""
        return len(self._samples)

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()
            mid = h / 2.0

            # Background — transparent, let QSS handle it
            painter.fillRect(0, 0, w, h, Qt.GlobalColor.transparent)

            if not self._samples:
                pen = QPen(self._color, 1, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.drawLine(0, int(mid), w, int(mid))
                return

            n = len(self._samples)
            step = w / n
            pen = QPen(self._color, 2)
            painter.setPen(pen)

            color_fill = QColor(self._color)
            color_fill.setAlpha(60)
            painter.setBrush(color_fill)

            poly = QPolygonF()
            poly.append(QPointF(0.0, mid))
            for i, sample in enumerate(self._samples):
                x = (i + 0.5) * step
                y = mid - sample * (mid * 0.85)
                poly.append(QPointF(x, y))
            poly.append(QPointF(w, mid))
            painter.drawPolygon(poly)
        finally:
            painter.end()
