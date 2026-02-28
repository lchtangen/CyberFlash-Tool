"""command_palette.py — Ctrl+P style searchable command overlay.

Usage::

    palette = CommandPalette(parent_widget)
    palette.command_selected.connect(on_command)
    palette.show_palette(["Flash ROM", "Reboot to Recovery", "Open Profile…"])
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QSortFilterProxyModel, QStringListModel, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QLineEdit,
    QListView,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class CommandPalette(QFrame):
    """Overlay widget that filters a list of commands by text search.

    Args:
        parent: Widget to anchor/overlay over.
    """

    command_selected = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("CommandPalette")
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._model = QStringListModel(self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._search = QLineEdit(self)
        self._search.setObjectName("PaletteSearch")
        self._search.setPlaceholderText("Type a command…")
        self._search.textChanged.connect(self._proxy.setFilterFixedString)
        self._search.returnPressed.connect(self._confirm_selection)
        layout.addWidget(self._search)

        self._list = QListView(self)
        self._list.setObjectName("PaletteList")
        self._list.setModel(self._proxy)
        self._list.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self._list.activated.connect(self._on_activated)
        layout.addWidget(self._list)

        self.setMaximumHeight(420)
        self.setMinimumWidth(480)

    def show_palette(self, commands: list[str]) -> None:
        """Populate the palette with *commands* and display it."""
        self._model.setStringList(commands)
        self._search.clear()
        parent = self.parent()
        if isinstance(parent, QWidget):
            pw, ph = parent.width(), parent.height()
            w = min(600, pw)
            h = min(380, ph)
            self.setGeometry(QFrame.geometry(self))
            self.setFixedSize(w, h)
            self.move((pw - w) // 2, 60)
        self.show()
        self.raise_()
        self._search.setFocus()

    def _confirm_selection(self) -> None:
        idx = self._list.currentIndex()
        if not idx.isValid() and self._proxy.rowCount() > 0:
            idx = self._proxy.index(0, 0)
        if idx.isValid():
            self._on_activated(idx)

    def _on_activated(self, index: object) -> None:
        from PySide6.QtCore import QModelIndex
        if isinstance(index, QModelIndex) and index.isValid():
            cmd = index.data(Qt.ItemDataRole.DisplayRole)
            if cmd:
                logger.debug("Command selected: %s", cmd)
                self.command_selected.emit(str(cmd))
        self.hide()
        self._search.clear()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        elif event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._list.setFocus()
            super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)
