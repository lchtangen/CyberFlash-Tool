"""inline_console.py — Embeddable ADB terminal console widget.

Provides a scrolling output pane (QPlainTextEdit) stacked above an optional
single-line command input (QLineEdit).

Usage::

    console = InlineConsole(parent)
    console.command_entered.connect(on_command)
    console.append_line("device online", "success")
    console.set_input_enabled(True)
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_STYLE_COLORS: dict[str, str] = {
    "success": "#2ea043",
    "warning": "#e3b341",
    "error":   "#f85149",
    "info":    "#58a6ff",
    "muted":   "#8b949e",
    "default": "#e6edf3",
}


class InlineConsole(QWidget):
    """Terminal-like output + optional command input widget.

    Signals:
        command_entered (str): Emitted when the user submits a command.

    Args:
        parent: Optional parent widget.
        show_input: Whether the command input bar is visible at startup.
        max_lines: Maximum lines kept in the output buffer (default 2000).
    """

    command_entered = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        show_input: bool = True,
        max_lines: int = 2000,
    ) -> None:
        super().__init__(parent)
        self._max_lines = max_lines
        self.setObjectName("InlineConsole")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Output area
        self._output = QPlainTextEdit(self)
        self._output.setObjectName("InlineConsoleOutput")
        self._output.setReadOnly(True)
        self._output.setMaximumBlockCount(max_lines)
        self._output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._output)

        # Input bar
        self._input_bar = QWidget(self)
        input_layout = QHBoxLayout(self._input_bar)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(4)

        self._prompt = QLineEdit(self._input_bar)
        self._prompt.setObjectName("InlineConsoleInput")
        self._prompt.setPlaceholderText("Enter ADB command…")
        self._prompt.returnPressed.connect(self._on_submit)
        input_layout.addWidget(self._prompt)

        send_btn = QPushButton("▶", self._input_bar)
        send_btn.setObjectName("InlineConsoleSendBtn")
        send_btn.setFixedWidth(32)
        send_btn.clicked.connect(self._on_submit)
        input_layout.addWidget(send_btn)

        layout.addWidget(self._input_bar)
        self._input_bar.setVisible(show_input)

    def append_line(self, line: str, style: str = "default") -> None:
        """Append *line* to the output pane with the given *style* colour.

        *style* values: ``"success"``, ``"warning"``, ``"error"``,
        ``"info"``, ``"muted"``, ``"default"``.
        """
        color_hex = _STYLE_COLORS.get(style, _STYLE_COLORS["default"])
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color_hex))
        cursor.setCharFormat(fmt)
        cursor.insertText(line + "\n")
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

    def clear(self) -> None:
        """Clear all output text."""
        self._output.clear()

    def set_input_enabled(self, enabled: bool) -> None:
        """Show or hide (and enable/disable) the command input bar."""
        self._input_bar.setVisible(enabled)
        self._prompt.setEnabled(enabled)

    def set_placeholder(self, text: str) -> None:
        """Change the placeholder text of the input field."""
        self._prompt.setPlaceholderText(text)

    def _on_submit(self) -> None:
        cmd = self._prompt.text().strip()
        if cmd:
            logger.debug("InlineConsole command: %s", cmd)
            self.append_line(f"$ {cmd}", "muted")
            self.command_entered.emit(cmd)
            self._prompt.clear()
