from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QClipboard, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.edl_manager import EdlManager
from cyberflash.utils.platform_utils import get_platform


def _make_instructions_widget(lines: list[str]) -> QWidget:
    """Build a simple widget displaying a list of instruction lines."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)
    for line in lines:
        lbl = QLabel(line)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(lbl)
    layout.addStretch()
    return widget


class EdlSetupDialog(QDialog):
    """Per-platform driver setup wizard for EDL (Qualcomm QDLoader 9008) access."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("EDL Setup — Driver Configuration")
        self.setMinimumWidth(560)
        self.setMinimumHeight(420)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        title = QLabel("EDL USB Driver Setup")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel(
            "To communicate with a Qualcomm device in EDL mode "
            "(VID 05C6, PID 9008), the host OS needs USB access."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Status indicator
        self._status_label = QLabel()
        self._status_label.setStyleSheet("font-weight: bold;")
        self._refresh_status()
        layout.addWidget(self._status_label)

        # Tabs: Linux / macOS / Windows
        tabs = QTabWidget()
        tabs.addTab(self._make_linux_tab(), "Linux")
        tabs.addTab(self._make_macos_tab(), "macOS")
        tabs.addTab(self._make_windows_tab(), "Windows")

        # Switch to the current platform's tab
        platform = get_platform()
        tab_map = {"linux": 0, "macos": 1, "windows": 2}
        tabs.setCurrentIndex(tab_map.get(platform, 0))

        layout.addWidget(tabs, stretch=1)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _refresh_status(self) -> None:
        platform = get_platform()
        if platform == "linux":
            configured = EdlManager.is_udev_configured()
            if configured:
                self._status_label.setText("✓ udev rule installed — setup complete")
                self._status_label.setStyleSheet("font-weight: bold; color: #3fb950;")
            else:
                self._status_label.setText("✗ udev rule not installed — setup needed")
                self._status_label.setStyleSheet("font-weight: bold; color: #f85149;")
        else:
            self._status_label.setText("See the tab for your platform below.")
            self._status_label.setStyleSheet("font-weight: bold; color: #8b949e;")

    def _make_linux_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        rule = EdlManager.get_udev_rule().strip()
        rule_path = EdlManager.get_udev_rule_path()

        layout.addWidget(QLabel("<b>Step 1:</b> Install the udev rule:"))

        rule_box = QTextEdit()
        rule_box.setReadOnly(True)
        rule_box.setMaximumHeight(60)
        rule_box.setPlainText(rule)
        rule_box.setStyleSheet("font-family: monospace; background: #0d1117; color: #c9d1d9;")
        layout.addWidget(rule_box)

        copy_btn = QPushButton("Copy rule to clipboard")
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(rule))
        layout.addWidget(copy_btn)

        install_cmd = f"echo '{rule}' | sudo tee {rule_path}"
        layout.addWidget(QLabel("<b>Run as root:</b>"))
        cmd_box = QTextEdit()
        cmd_box.setReadOnly(True)
        cmd_box.setMaximumHeight(60)
        cmd_box.setPlainText(install_cmd)
        cmd_box.setStyleSheet("font-family: monospace; background: #0d1117; color: #c9d1d9;")
        layout.addWidget(cmd_box)

        copy_cmd_btn = QPushButton("Copy install command to clipboard")
        copy_cmd_btn.clicked.connect(lambda: self._copy_to_clipboard(install_cmd))
        layout.addWidget(copy_cmd_btn)

        layout.addWidget(QLabel("<b>Step 2:</b> Reload udev rules:"))
        reload_cmd = "sudo udevadm control --reload-rules && sudo udevadm trigger"
        reload_box = QTextEdit()
        reload_box.setReadOnly(True)
        reload_box.setMaximumHeight(44)
        reload_box.setPlainText(reload_cmd)
        reload_box.setStyleSheet("font-family: monospace; background: #0d1117; color: #c9d1d9;")
        layout.addWidget(reload_box)

        copy_reload_btn = QPushButton("Copy reload command to clipboard")
        copy_reload_btn.clicked.connect(lambda: self._copy_to_clipboard(reload_cmd))
        layout.addWidget(copy_reload_btn)

        layout.addWidget(QLabel("<b>Step 3:</b> Reconnect the device."))
        layout.addStretch()
        return widget

    def _make_macos_tab(self) -> QWidget:
        lines = [
            "1. Install libusb (required for pyusb to access USB devices):",
            "   brew install libusb",
            "",
            "2. Install pyusb if not already installed:",
            "   pip install pyusb",
            "",
            "3. Reconnect the device.",
            "",
            "Note: macOS does not require a separate driver — libusb handles USB access.",
        ]
        return _make_instructions_widget(lines)

    def _make_windows_tab(self) -> QWidget:
        lines = [
            "1. Download Zadig from: https://zadig.akeo.ie/",
            "",
            "2. Open Zadig, go to: Options → List All Devices",
            "",
            "3. Find 'Qualcomm HS-USB QDLoader 9008' in the device list.",
            "",
            "4. Select 'WinUSB' as the target driver.",
            "",
            "5. Click 'Replace Driver' and wait for installation to complete.",
            "",
            "6. Reconnect the device.",
            "",
            "Alternative: Install the official Qualcomm QDLoader driver from your",
            "device manufacturer's support page.",
        ]
        return _make_instructions_widget(lines)

    @staticmethod
    def _copy_to_clipboard(text: str) -> None:
        clipboard: QClipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
