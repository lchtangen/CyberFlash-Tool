from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cyberflash.models.profile import DeviceProfile


class EdlEntryDialog(QDialog):
    """Shows device-specific instructions for entering EDL mode.

    Populated from profile.edl.edl_entry_methods.
    """

    def __init__(
        self,
        profile: DeviceProfile,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"How to Enter EDL Mode — {profile.name}")
        self.setMinimumWidth(500)
        self._profile = profile
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title
        title = QLabel(f"Entering EDL Mode: {self._profile.name}")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        # Warning banner
        warning = QLabel(
            "⚠  You have approximately 10 seconds once in EDL mode.\n"
            "   Have CyberFlash ready and click Start BEFORE connecting the device."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background: #2d1f00; color: #e3b341; border: 1px solid #bb8009;"
            " border-radius: 4px; padding: 8px;"
        )
        layout.addWidget(warning)

        # Methods
        methods = (
            self._profile.edl.edl_entry_methods
            if self._profile.edl
            else []
        )
        if methods:
            for i, method in enumerate(methods, start=1):
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(10)

                num = QLabel(f"{i}.")
                num.setFixedWidth(20)
                num.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
                num.setStyleSheet("color: #00d4ff; font-weight: bold;")
                row_layout.addWidget(num)

                text = QLabel(method)
                text.setWordWrap(True)
                text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                row_layout.addWidget(text, stretch=1)

                layout.addWidget(row)
        else:
            layout.addWidget(QLabel("No EDL entry instructions available for this device."))

        layout.addStretch()

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
