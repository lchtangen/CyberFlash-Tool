"""changelog_diff_dialog.py — ROM changelog diff viewer dialog.

Displays a side-by-side or unified diff between two ROM changelog texts,
with syntax highlighting for additions (green), deletions (red), and
unchanged lines (normal).
"""

from __future__ import annotations

import difflib
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# ── Diff highlighter ──────────────────────────────────────────────────────────


class _DiffHighlighter(QSyntaxHighlighter):
    """Highlights unified diff output: + lines green, - lines red, @ lines blue."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self._add_fmt = QTextCharFormat()
        self._add_fmt.setForeground(QColor("#2ea043"))
        self._add_fmt.setBackground(QColor("#0d2a14"))

        self._del_fmt = QTextCharFormat()
        self._del_fmt.setForeground(QColor("#f85149"))
        self._del_fmt.setBackground(QColor("#2d1117"))

        self._hunk_fmt = QTextCharFormat()
        self._hunk_fmt.setForeground(QColor("#58a6ff"))
        self._hunk_fmt.setFontWeight(QFont.Weight.Bold)

    def highlightBlock(self, text: str) -> None:  # type: ignore[override]
        if text.startswith("+"):
            self.setFormat(0, len(text), self._add_fmt)
        elif text.startswith("-"):
            self.setFormat(0, len(text), self._del_fmt)
        elif text.startswith("@@"):
            self.setFormat(0, len(text), self._hunk_fmt)


# ── Dialog ────────────────────────────────────────────────────────────────────


class ChangelogDiffDialog(QDialog):
    """Show a unified diff between two ROM changelogs.

    Args:
        old_text: The baseline changelog (e.g. previously installed ROM).
        new_text: The new changelog (e.g. ROM being considered for flashing).
        old_label: Display label for the left/old pane (default "Old").
        new_label: Display label for the right/new pane (default "New").
        parent: Optional Qt parent widget.
    """

    def __init__(
        self,
        old_text: str,
        new_text: str,
        old_label: str = "Old",
        new_label: str = "New",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._old_text = old_text
        self._new_text = new_text
        self._old_label = old_label
        self._new_label = new_label
        self._unified_diff: str = ""

        self.setWindowTitle("Changelog Diff")
        self.setMinimumSize(900, 600)
        self._build_ui()
        self._compute_diff()
        self._populate()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Toolbar row
        toolbar = QHBoxLayout()
        self._stats_label = QLabel()
        toolbar.addWidget(self._stats_label)
        toolbar.addStretch()

        self._btn_copy = QPushButton("Copy Diff")
        self._btn_copy.clicked.connect(self._copy_diff)
        toolbar.addWidget(self._btn_copy)

        root.addLayout(toolbar)

        # Splitter: left (old) | right (diff)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._old_view = self._make_editor(self._old_label)
        self._diff_view = self._make_editor(f"Unified Diff ({self._old_label} → {self._new_label})")
        self._new_view = self._make_editor(self._new_label)

        splitter.addWidget(self._old_view)
        splitter.addWidget(self._diff_view)
        splitter.addWidget(self._new_view)
        splitter.setSizes([300, 400, 300])
        root.addWidget(splitter)

        # Button box
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def _make_editor(title: str) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(f"<b>{title}</b>")
        layout.addWidget(lbl)
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setProperty("mono", True)
        font = QFont("Fira Code, Consolas, monospace")
        font.setPointSize(9)
        editor.setFont(font)
        layout.addWidget(editor)
        wrapper._editor = editor  # type: ignore[attr-defined]
        return wrapper

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _compute_diff(self) -> None:
        old_lines = self._old_text.splitlines(keepends=True)
        new_lines = self._new_text.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=self._old_label,
            tofile=self._new_label,
            lineterm="",
        ))
        self._unified_diff = "\n".join(diff_lines)

        added = sum(1 for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++"))
        removed = sum(1 for ln in diff_lines if ln.startswith("-") and not ln.startswith("---"))
        self._stats_label.setText(
            f"<span style='color:#2ea043'>+{added} lines added</span> &nbsp;&nbsp;"
            f"<span style='color:#f85149'>-{removed} lines removed</span>"
        )

    def _populate(self) -> None:
        self._old_view._editor.setPlainText(self._old_text)  # type: ignore[attr-defined]
        self._new_view._editor.setPlainText(self._new_text)  # type: ignore[attr-defined]
        self._diff_view._editor.setPlainText(self._unified_diff)  # type: ignore[attr-defined]
        _DiffHighlighter(self._diff_view._editor.document())  # type: ignore[attr-defined]

    def _copy_diff(self) -> None:
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._unified_diff)

    # ── Public helpers ────────────────────────────────────────────────────────

    def unified_diff(self) -> str:
        """Return the computed unified diff text."""
        return self._unified_diff

    def has_changes(self) -> bool:
        """Return True if there are any additions or deletions."""
        return bool(self._unified_diff.strip())
