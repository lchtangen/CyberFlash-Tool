"""journal_viewer.py — Flash journal timeline viewer dialog."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)

# Try to import FlashJournal; page degrades gracefully if unavailable.
try:
    from cyberflash.core.flash_journal import FlashJournal as _FlashJournal
    _JOURNAL_AVAILABLE = True
except ImportError:
    _FlashJournal = None  # type: ignore[assignment,misc]
    _JOURNAL_AVAILABLE = False
    logger.debug("FlashJournal not available — journal viewer will show placeholder")


class JournalViewerDialog(QDialog):
    """Flash journal timeline viewer.

    Displays a list of past flash operations (newest first) with full
    step-by-step logs for the selected entry. Supports rollback if
    FlashJournal is available.
    """

    def __init__(
        self,
        journal_path: str = "~/.cyberflash/flash_journal.json",
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self.setWindowTitle("Flash Journal")
        self.setMinimumSize(800, 500)
        self._journal_path = journal_path
        self._setup_ui()
        if _JOURNAL_AVAILABLE:
            self._load_entries()

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("Flash Journal")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        if not _JOURNAL_AVAILABLE:
            placeholder = QLabel("Flash journal not available")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setObjectName("placeholderLabel")
            layout.addWidget(placeholder, 1)
            self._add_close_buttons(layout, rollback_enabled=False)
            return

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left — entry list
        self._entry_list = QListWidget()
        self._entry_list.currentItemChanged.connect(self._on_entry_selected)
        splitter.addWidget(self._entry_list)

        # Right — step log
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setObjectName("logOutput")
        splitter.addWidget(self._log_view)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self._rollback_btn = QPushButton("Rollback from this entry")
        self._rollback_btn.setObjectName("dangerButton")
        self._rollback_btn.setEnabled(False)
        self._rollback_btn.clicked.connect(self._on_rollback)
        self._add_close_buttons(layout, rollback_btn=self._rollback_btn)

    def _add_close_buttons(
        self,
        layout: QVBoxLayout,
        rollback_enabled: bool = True,
        rollback_btn: QPushButton | None = None,
    ) -> None:
        button_row = QHBoxLayout()
        if rollback_btn is not None:
            button_row.addWidget(rollback_btn)
        button_row.addStretch()
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        button_row.addWidget(box)
        layout.addLayout(button_row)

    # ── Journal loading ──────────────────────────────────────────────────────

    def _load_entries(self) -> None:
        if _FlashJournal is None:
            return
        try:
            journal = _FlashJournal(self._journal_path)
            entries = journal.load_entries()
        except Exception as exc:
            logger.exception("Failed to load flash journal")
            self._log_view.setPlainText(f"Failed to load journal:\n{exc}")
            return

        # Newest first
        for entry in reversed(entries):
            device  = getattr(entry, "device",  "unknown")
            rom     = getattr(entry, "rom",     "unknown")
            date    = getattr(entry, "date",    "unknown")
            success = getattr(entry, "success", None)
            result  = "PASS" if success else "FAIL"
            label   = f"{device} — {rom} — {date} — {result}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self._entry_list.addItem(item)

    # ── Slots ────────────────────────────────────────────────────────────────

    def _on_entry_selected(self) -> None:
        item = self._entry_list.currentItem()
        if item is None:
            self._rollback_btn.setEnabled(False)
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        steps = getattr(entry, "steps", [])
        if steps:
            self._log_view.setPlainText("\n".join(str(s) for s in steps))
        else:
            self._log_view.setPlainText("No step log available for this entry.")
        self._rollback_btn.setEnabled(True)

    def _on_rollback(self) -> None:
        item = self._entry_list.currentItem()
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if _FlashJournal is None:
            return
        try:
            journal = _FlashJournal(self._journal_path)
            journal.rollback(entry)
            logger.info("Rollback initiated from journal entry: %s", item.text())
        except Exception as exc:
            logger.exception("Rollback failed")
            self._log_view.append(f"\nRollback failed: {exc}")
