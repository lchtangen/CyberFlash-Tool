from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

_CONFIRM_WORD = "UNLOCK"

_CONSEQUENCES = [
    "ALL user data will be permanently wiped (factory reset)",
    "Device warranty may be voided",
    "Unsigned/unverified software can be installed",
    "Risk of bricking the device if interrupted",
    "OEM Unlock must be enabled in Developer Options first",
]


class UnlockConfirmDialog(QDialog):
    """Danger confirmation dialog for bootloader unlock operations."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bootloader Unlock")
        self.setMinimumWidth(440)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # ── Red-tinted header ─────────────────────────────────────────────────
        header_frame = QFrame()
        header_frame.setStyleSheet(
            "QFrame {"
            "  background: rgba(248, 81, 73, 0.12);"
            "  border: 1px solid rgba(248, 81, 73, 0.4);"
            "  border-radius: 6px;"
            "}"
        )
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 12, 16, 12)

        title = QLabel("\u26a0  WARNING: Bootloader Unlock")
        title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #f85149; border: none;"
        )
        header_layout.addWidget(title)
        layout.addWidget(header_frame)

        # ── Consequences list ─────────────────────────────────────────────────
        for item in _CONSEQUENCES:
            row = QLabel(f"\u2022  {item}")
            row.setWordWrap(True)
            row.setStyleSheet("color: #e6edf3;")
            layout.addWidget(row)

        # ── Type-to-confirm ───────────────────────────────────────────────────
        prompt = QLabel(f'Type <b style="color:#f85149">{_CONFIRM_WORD}</b> to confirm:')
        prompt.setStyleSheet("color: #e6edf3;")
        layout.addWidget(prompt)

        self._input = QLineEdit()
        self._input.setPlaceholderText(_CONFIRM_WORD)
        self._input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._input)

        # ── Buttons ───────────────────────────────────────────────────────────
        self._buttons = QDialogButtonBox()
        self._confirm_btn = self._buttons.addButton(
            "Unlock Bootloader", QDialogButtonBox.ButtonRole.AcceptRole
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

    def _on_text_changed(self, text: str) -> None:
        self._confirm_btn.setEnabled(text.strip() == _CONFIRM_WORD)
