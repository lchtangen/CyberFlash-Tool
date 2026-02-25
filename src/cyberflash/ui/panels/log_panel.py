from __future__ import annotations

import datetime

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cyberflash.utils.ansi_utils import ansi_to_html, strip_ansi

_MAX_LINES = 2000


class LogPanel(QWidget):
    """Read-only HTML log output panel with auto-scroll and copy/clear actions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._line_count = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Header row ───────────────────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("Log Output")
        title.setObjectName("sectionLabel")
        header.addWidget(title)
        header.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("secondaryButton")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self.clear)
        header.addWidget(clear_btn)

        copy_btn = QPushButton("Copy All")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.setFixedWidth(70)
        copy_btn.clicked.connect(self._copy_all)
        header.addWidget(copy_btn)

        layout.addLayout(header)

        # ── Log text area ────────────────────────────────────────────────────
        self._edit = QTextEdit()
        self._edit.setReadOnly(True)
        self._edit.setObjectName("logOutput")
        self._edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._edit.setStyleSheet(
            "QTextEdit#logOutput {"
            "  background-color: #0d1117;"
            "  color: #3fb950;"
            "  font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;"
            "  font-size: 12px;"
            "  border: 1px solid #21262d;"
            "  border-radius: 4px;"
            "}"
        )
        layout.addWidget(self._edit)

    def append_line(self, text: str) -> None:
        """Append a log line, converting ANSI codes to HTML, with auto-scroll."""
        if self._line_count >= _MAX_LINES:
            # Remove oldest line
            cursor = QTextCursor(self._edit.document())
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # remove trailing newline
            self._line_count -= 1

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        clean = strip_ansi(text)
        html_line = ansi_to_html(clean)
        formatted = (
            f'<span style="color:#484f58">[{timestamp}]</span> {html_line}'
        )

        self._edit.append(formatted)
        self._line_count += 1

        # Auto-scroll to bottom
        self._edit.verticalScrollBar().setValue(
            self._edit.verticalScrollBar().maximum()
        )

    def clear(self) -> None:
        """Clear all log content."""
        self._edit.clear()
        self._line_count = 0

    def _copy_all(self) -> None:
        """Copy plain text of all log lines to clipboard."""
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._edit.toPlainText())
