"""Mixin that adds edge-resize capability to a frameless QMainWindow.

Usage::

    class MyWindow(ResizableFramelessMixin, QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
            self.init_resize_grips()

The mixin installs invisible grip widgets (4 edges + 4 corners) around
the window perimeter.  Cursor shape changes automatically on hover.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QMainWindow, QWidget

_GRIP_SIZE = 6  # pixels of the resize border


class _EdgeGrip(QWidget):
    """Transparent grip overlay on one edge / corner of the window."""

    def __init__(
        self,
        parent: QMainWindow,
        cursor: Qt.CursorShape,
        edge_flags: Qt.Edge | int,
    ) -> None:
        super().__init__(parent)
        self.setCursor(cursor)
        self._parent_window = parent
        self._edge_flags = edge_flags
        self.setMouseTracking(True)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._parent_window.windowHandle().startSystemResize(
                Qt.Edge(self._edge_flags)  # type: ignore[arg-type]
            )
        super().mousePressEvent(event)


class ResizableFramelessMixin:
    """Adds 8 edge/corner resize grips to a QMainWindow subclass."""

    def init_resize_grips(self) -> None:
        """Call once after __init__ to create resize handles."""
        self._grips: list[_EdgeGrip] = []

        grip_defs: list[tuple[Qt.CursorShape, int]] = [
            # Edges
            (Qt.CursorShape.SizeHorCursor, Qt.Edge.LeftEdge),
            (Qt.CursorShape.SizeHorCursor, Qt.Edge.RightEdge),
            (Qt.CursorShape.SizeVerCursor, Qt.Edge.TopEdge),
            (Qt.CursorShape.SizeVerCursor, Qt.Edge.BottomEdge),
            # Corners
            (Qt.CursorShape.SizeFDiagCursor, Qt.Edge.TopEdge | Qt.Edge.LeftEdge),
            (Qt.CursorShape.SizeBDiagCursor, Qt.Edge.TopEdge | Qt.Edge.RightEdge),
            (Qt.CursorShape.SizeBDiagCursor, Qt.Edge.BottomEdge | Qt.Edge.LeftEdge),
            (Qt.CursorShape.SizeFDiagCursor, Qt.Edge.BottomEdge | Qt.Edge.RightEdge),
        ]

        for cursor, flags in grip_defs:
            grip = _EdgeGrip(self, cursor, flags)  # type: ignore[arg-type]
            grip.setVisible(True)
            self._grips.append(grip)

        self._update_grip_geometry()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)  # type: ignore[misc]
        if hasattr(self, "_grips"):
            self._update_grip_geometry()

    def _update_grip_geometry(self) -> None:
        g = _GRIP_SIZE
        w = self.width()  # type: ignore[attr-defined]
        h = self.height()  # type: ignore[attr-defined]

        # left, right, top, bottom
        self._grips[0].setGeometry(0, g, g, h - 2 * g)
        self._grips[1].setGeometry(w - g, g, g, h - 2 * g)
        self._grips[2].setGeometry(g, 0, w - 2 * g, g)
        self._grips[3].setGeometry(g, h - g, w - 2 * g, g)

        # top-left, top-right, bottom-left, bottom-right
        self._grips[4].setGeometry(0, 0, g, g)
        self._grips[5].setGeometry(w - g, 0, g, g)
        self._grips[6].setGeometry(0, h - g, g, g)
        self._grips[7].setGeometry(w - g, h - g, g, g)
