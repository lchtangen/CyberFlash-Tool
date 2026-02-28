"""split_view.py — Resizable two-panel split view widget.

Wraps ``QSplitter`` with a friendlier API for the common left/right (or
top/bottom) two-panel layout used throughout the CyberFlash UI.

Usage::

    split = SplitView(parent)
    split.set_left(editor_widget)
    split.set_right(preview_widget)
    split.set_ratio(0.4)   # left takes 40 % of width
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


class SplitView(QWidget):
    """Two-panel resizable split view backed by a ``QSplitter``.

    Args:
        parent: Optional parent widget.
        orientation: ``Qt.Horizontal`` (default) or ``Qt.Vertical``.
        collapsible: Whether panels can be collapsed to zero size.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        collapsible: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SplitView")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._splitter = QSplitter(orientation, self)
        self._splitter.setObjectName("SplitViewSplitter")
        self._splitter.setChildrenCollapsible(collapsible)
        layout.addWidget(self._splitter)

        self._left: QWidget | None = None
        self._right: QWidget | None = None

    def set_left(self, widget: QWidget) -> None:
        """Set (or replace) the left / top panel.

        If a panel was previously set it is removed first.
        """
        if self._left is not None:
            self._left.setParent(None)  # type: ignore[call-overload]
        self._left = widget
        self._splitter.insertWidget(0, widget)

    def set_right(self, widget: QWidget) -> None:
        """Set (or replace) the right / bottom panel."""
        if self._right is not None:
            self._right.setParent(None)  # type: ignore[call-overload]
        self._right = widget
        self._splitter.addWidget(widget)

    def set_orientation(self, orientation: Qt.Orientation) -> None:
        """Switch between horizontal and vertical split."""
        self._splitter.setOrientation(orientation)

    def set_ratio(self, ratio: float) -> None:
        """Set the size ratio of the first panel.

        *ratio* should be between 0.0 and 1.0; e.g. 0.3 gives the first
        panel 30 % of the total width/height.
        """
        ratio = max(0.0, min(1.0, ratio))
        total = self._splitter.width() if (
            self._splitter.orientation() == Qt.Orientation.Horizontal
        ) else self._splitter.height()
        if total <= 0:
            total = 1000  # placeholder before widget is shown
        first = int(total * ratio)
        second = total - first
        self._splitter.setSizes([first, second])

    def sizes(self) -> list[int]:
        """Return the current sizes of the two panels."""
        return self._splitter.sizes()

    def orientation(self) -> Qt.Orientation:
        """Return the current splitter orientation."""
        return self._splitter.orientation()

    @property
    def splitter(self) -> QSplitter:
        """Direct access to the underlying ``QSplitter`` (for advanced use)."""
        return self._splitter
