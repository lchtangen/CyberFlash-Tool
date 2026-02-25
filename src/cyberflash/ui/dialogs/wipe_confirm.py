from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class WipeConfirmDialog(QDialog):
    """Confirmation dialog listing selected wipe targets before proceeding."""

    def __init__(
        self,
        targets: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm Wipe Operations")
        self.setMinimumWidth(400)
        self.setModal(True)
        self._targets = targets
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        # ── Title ─────────────────────────────────────────────────────────────
        title = QLabel("The following partitions will be wiped:")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #e6edf3;")
        layout.addWidget(title)

        # ── Wipe target list ──────────────────────────────────────────────────
        targets_frame = QFrame()
        targets_frame.setStyleSheet(
            "QFrame {"
            "  background: #161b22;"
            "  border: 1px solid #21262d;"
            "  border-radius: 4px;"
            "}"
        )
        tf_layout = QVBoxLayout(targets_frame)
        tf_layout.setContentsMargins(12, 10, 12, 10)
        tf_layout.setSpacing(6)

        includes_data = False
        for target in self._targets:
            row = QLabel(f"\u2022  {target}")
            row.setStyleSheet("color: #e6edf3; border: none;")
            tf_layout.addWidget(row)
            if target.lower() in ("data", "userdata"):
                includes_data = True

        layout.addWidget(targets_frame)

        # ── Data wipe warning ─────────────────────────────────────────────────
        if includes_data:
            warn = QLabel(
                "\u26a0  Factory reset \u2014 ALL user data will be permanently lost"
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(
                "color: #f85149;"
                "font-weight: bold;"
                "padding: 8px;"
                "background: rgba(248,81,73,0.10);"
                "border: 1px solid rgba(248,81,73,0.35);"
                "border-radius: 4px;"
            )
            layout.addWidget(warn)

        # ── Understand checkbox ───────────────────────────────────────────────
        self._checkbox = QCheckBox("I understand this operation cannot be undone")
        self._checkbox.stateChanged.connect(self._on_checkbox_changed)
        layout.addWidget(self._checkbox)

        # ── Buttons ───────────────────────────────────────────────────────────
        self._buttons = QDialogButtonBox()
        self._confirm_btn = self._buttons.addButton(
            "Confirm Wipe", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.setStyleSheet(
            "QPushButton {"
            "  background: #b91c1c;"
            "  color: white;"
            "  border: none;"
            "  padding: 6px 16px;"
            "  border-radius: 4px;"
            "}"
            "QPushButton:enabled {"
            "  background: #f85149;"
            "}"
            "QPushButton:disabled {"
            "  background: #3d1f1f;"
            "  color: #6e7681;"
            "}"
        )
        self._buttons.addButton(QDialogButtonBox.StandardButton.Cancel)

        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _on_checkbox_changed(self, state: int) -> None:
        self._confirm_btn.setEnabled(
            state == Qt.CheckState.Checked.value
        )
