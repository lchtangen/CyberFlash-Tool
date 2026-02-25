from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget


class TitleBar(QWidget):
    minimize_clicked = Signal()
    maximize_clicked = Signal()
    close_clicked = Signal()
    ai_toggle_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(40)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)

        # App name label (left)
        self._app_label = QLabel("CyberFlash")
        layout.addWidget(self._app_label)

        layout.addStretch()

        # Device selector (center)
        self._device_combo = QComboBox()
        self._device_combo.addItem("No device connected")
        self._device_combo.setToolTip("Select connected device")
        self._device_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._device_combo)

        layout.addStretch()

        # AI Assistant toggle button
        self._ai_btn = QPushButton("⚡ AI")
        self._ai_btn.setObjectName("aiToggleBtn")
        self._ai_btn.setToolTip("Toggle AI Assistant")
        self._ai_btn.setFixedSize(52, 28)
        self._ai_btn.clicked.connect(self.ai_toggle_clicked)
        layout.addWidget(self._ai_btn)

        # Window control buttons (right)
        self._minimize_btn = QPushButton("\u2500")
        self._minimize_btn.setObjectName("titleBarBtn")
        self._minimize_btn.setToolTip("Minimize")
        self._minimize_btn.setFixedSize(32, 32)
        self._minimize_btn.clicked.connect(self.minimize_clicked)

        self._maximize_btn = QPushButton("\u25a1")
        self._maximize_btn.setObjectName("titleBarBtn")
        self._maximize_btn.setToolTip("Maximize / Restore")
        self._maximize_btn.setFixedSize(32, 32)
        self._maximize_btn.clicked.connect(self.maximize_clicked)

        self._close_btn = QPushButton("\u2715")
        self._close_btn.setObjectName("closeBtn")
        self._close_btn.setToolTip("Close")
        self._close_btn.setFixedSize(32, 32)
        self._close_btn.clicked.connect(self.close_clicked)

        layout.addWidget(self._minimize_btn)
        layout.addWidget(self._maximize_btn)
        layout.addWidget(self._close_btn)

    def device_combo(self) -> QComboBox:
        return self._device_combo

    def set_devices(self, devices: list[str]) -> None:
        self._device_combo.clear()
        if devices:
            for device in devices:
                self._device_combo.addItem(device)
        else:
            self._device_combo.addItem("No device connected")

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximize_clicked.emit()
        super().mouseDoubleClickEvent(event)
