from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class ProgressPanel(QWidget):
    """Shows a progress bar, step counter, and status message for flash operations."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── Step counter + status row ─────────────────────────────────────────
        info_row = QHBoxLayout()
        self._step_label = QLabel("Ready")
        self._step_label.setObjectName("sectionLabel")
        info_row.addWidget(self._step_label)
        info_row.addStretch()
        self._status_label = QLabel("")
        self._status_label.setObjectName("secondaryLabel")
        info_row.addWidget(self._status_label)
        layout.addLayout(info_row)

        # ── Progress bar ─────────────────────────────────────────────────────
        self._bar = QProgressBar()
        self._bar.setObjectName("flashProgressBar")
        self._bar.setMinimum(0)
        self._bar.setMaximum(100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        self._bar.setStyleSheet(
            "QProgressBar#flashProgressBar {"
            "  background: #21262d;"
            "  border: none;"
            "  border-radius: 4px;"
            "}"
            "QProgressBar#flashProgressBar::chunk {"
            "  background: #00d4ff;"
            "  border-radius: 4px;"
            "}"
        )
        layout.addWidget(self._bar)

    @Slot(int, int, str)
    def update_progress(self, current: int, total: int, message: str = "") -> None:
        """Update the progress bar and labels.

        Args:
            current: Current step index (0-based).
            total: Total number of steps.
            message: Short status message shown to the right.
        """
        if total > 0:
            pct = int(current / total * 100)
            self._bar.setValue(pct)
            self._step_label.setText(f"Step {current} of {total}")
        else:
            self._bar.setValue(0)
            self._step_label.setText("Ready")

        if message:
            self._status_label.setText(message)

    @Slot()
    def reset(self) -> None:
        """Reset bar to zero and clear labels."""
        self._bar.setValue(0)
        self._step_label.setText("Ready")
        self._status_label.setText("")
