from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cyberflash.models.flash_task import FlashStep, StepStatus

_STATUS_ICON: dict[StepStatus, str] = {
    StepStatus.PENDING: "○",
    StepStatus.ACTIVE: "▶",
    StepStatus.COMPLETED: "✓",
    StepStatus.FAILED: "✗",
    StepStatus.SKIPPED: "—",
}

_STATUS_COLOR: dict[StepStatus, str] = {
    StepStatus.PENDING: "#6e7681",
    StepStatus.ACTIVE: "#00d4ff",
    StepStatus.COMPLETED: "#3fb950",
    StepStatus.FAILED: "#f85149",
    StepStatus.SKIPPED: "#6e7681",
}


class _StepRow(QWidget):
    """Single row in the step tracker."""

    def __init__(self, step: FlashStep, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._step_id = step.id
        self.setObjectName("stepRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        self._icon_label = QLabel(_STATUS_ICON[step.status])
        self._icon_label.setFixedWidth(16)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon_label)

        self._text_label = QLabel(step.label)
        self._text_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self._text_label)

        self._apply_status(step.status)

    def update_status(self, status: StepStatus) -> None:
        self._icon_label.setText(_STATUS_ICON[status])
        self._apply_status(status)

    def _apply_status(self, status: StepStatus) -> None:
        color = _STATUS_COLOR[status]
        self._icon_label.setStyleSheet(f"color: {color}; font-weight: bold;")

        if status == StepStatus.ACTIVE:
            self.setStyleSheet(
                "QWidget#stepRow {"
                "  border-left: 3px solid #00d4ff;"
                "  background: rgba(0, 212, 255, 0.06);"
                "}"
            )
            self._text_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        elif status == StepStatus.COMPLETED:
            self.setStyleSheet("")
            self._text_label.setStyleSheet(f"color: {color};")
        elif status == StepStatus.FAILED:
            self.setStyleSheet(
                "QWidget#stepRow {"
                "  border-left: 3px solid #f85149;"
                "}"
            )
            self._text_label.setStyleSheet(f"color: {color};")
        else:
            self.setStyleSheet("")
            self._text_label.setStyleSheet("color: #6e7681;")


class StepTracker(QWidget):
    """Vertical list of flash step rows with live status updates."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, _StepRow] = {}  # step_id → row widget

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.frameShape().NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._layout.addStretch()

        scroll.setWidget(self._content)
        outer.addWidget(scroll)

    def set_steps(self, steps: list[FlashStep]) -> None:
        """Rebuild all rows from a fresh list of steps."""
        # Clear existing
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._rows.clear()

        for step in steps:
            row = _StepRow(step)
            self._rows[step.id] = row
            self._layout.insertWidget(self._layout.count() - 1, row)

    def update_step(self, step_id: str, status: StepStatus) -> None:
        """Update the status icon and color for a single step row."""
        row = self._rows.get(step_id)
        if row:
            row.update_status(status)

    def reset(self) -> None:
        """Set all rows back to PENDING status."""
        for row in self._rows.values():
            row.update_status(StepStatus.PENDING)
