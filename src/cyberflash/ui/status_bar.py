from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from cyberflash import __version__


class AppStatusBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusBar")
        self.setFixedHeight(28)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(6)

        # Left: status icon + text
        self._status_icon = QLabel("\u25cf")
        self._status_icon.setObjectName("statusIcon")
        self._status_icon.setProperty("status", "ready")
        self._status_icon.setStyleSheet("font-size: 10px;")
        layout.addWidget(self._status_icon)

        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("secondaryLabel")
        layout.addWidget(self._status_label)

        layout.addStretch()

        # Right: version
        self._version_label = QLabel(f"v{__version__}")
        self._version_label.setObjectName("secondaryLabel")
        align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        self._version_label.setAlignment(align)
        layout.addWidget(self._version_label)

    def set_status(self, message: str, status_type: str = "ready") -> None:
        self._status_icon.setProperty("status", status_type)
        self._status_icon.style().unpolish(self._status_icon)
        self._status_icon.style().polish(self._status_icon)
        self._status_label.setText(message)
