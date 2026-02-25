"""Terminal page — interactive ADB / fastboot shell.

Provides a terminal-like interface for running ADB and fastboot
commands directly with output display, command history, and
quick-action buttons for common operations.
"""

from __future__ import annotations

import logging
from collections import deque

from PySide6.QtCore import QProcess, Qt, Slot
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.cyber_card import CyberCard
from cyberflash.utils.platform_utils import get_tools_dir

logger = logging.getLogger(__name__)

_MAX_HISTORY = 200
_MAX_OUTPUT_LINES = 5000

_QUICK_COMMANDS: list[tuple[str, str, str]] = [
    ("Devices", "adb", "devices -l"),
    ("Shell", "adb", "shell"),
    ("Logcat", "adb", "logcat -d -t 100"),
    ("Get Prop", "adb", "shell getprop"),
    ("Reboot", "adb", "reboot"),
    ("Reboot BL", "adb", "reboot bootloader"),
    ("Reboot Rec", "adb", "reboot recovery"),
    ("FB Devices", "fastboot", "devices"),
    ("FB Getvar", "fastboot", "getvar all"),
    ("FB Reboot", "fastboot", "reboot"),
]


# ── Output display ───────────────────────────────────────────────────────────


class _TerminalOutput(QPlainTextEdit):
    """Read-only terminal output with monospace font."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("terminalOutput")
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("JetBrains Mono", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setMaximumBlockCount(_MAX_OUTPUT_LINES)

    def append_text(self, text: str) -> None:
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.insertPlainText(text)
        self.moveCursor(QTextCursor.MoveOperation.End)

    def append_line(self, line: str) -> None:
        self.append_text(line + "\n")


# ── Command input ────────────────────────────────────────────────────────────


class _CommandInput(QLineEdit):
    """Command input with history navigation (Up/Down arrows)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("terminalInput")
        self.setPlaceholderText("Type a command\u2026 (prefix with adb/fastboot optional)")
        self._history: deque[str] = deque(maxlen=_MAX_HISTORY)
        self._history_idx: int = -1

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Up:
            self._navigate_history(1)
        elif event.key() == Qt.Key.Key_Down:
            self._navigate_history(-1)
        else:
            super().keyPressEvent(event)

    def _navigate_history(self, direction: int) -> None:
        if not self._history:
            return
        self._history_idx = max(0, min(len(self._history) - 1, self._history_idx + direction))
        self.setText(self._history[self._history_idx])

    def add_to_history(self, cmd: str) -> None:
        if cmd and (not self._history or self._history[0] != cmd):
            self._history.appendleft(cmd)
        self._history_idx = -1


# ── Quick commands panel ─────────────────────────────────────────────────────


class _QuickPanel(CyberCard):
    """Panel with quick-action buttons for common ADB/fastboot commands."""

    command_requested = Signal = None  # set by parent

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self.card_layout()

        title = QLabel("Quick Commands")
        title.setObjectName("cardHeader")
        layout.addWidget(title)

        self._buttons: list[QPushButton] = []
        for label, tool, args in _QUICK_COMMANDS:
            btn = QPushButton(label)
            btn.setToolTip(f"{tool} {args}")
            btn.setFixedHeight(32)
            full_cmd = f"{tool} {args}"
            btn.clicked.connect(lambda _checked=False, c=full_cmd: self._on_clicked(c))
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch()

    def _on_clicked(self, cmd: str) -> None:
        # Delegate to parent via callback set after init
        if self._on_command:
            self._on_command(cmd)

    def set_command_callback(self, cb) -> None:
        self._on_command = cb

    _on_command = None


# ── No-device overlay ────────────────────────────────────────────────────────


class _NoDeviceOverlay(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        icon = QLabel("\u2328\ufe0f")
        icon.setObjectName("emptyIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        title = QLabel("Terminal")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = QLabel(
            "Connect a device to use ADB/fastboot commands,\n"
            "or use 'adb devices' to check connections."
        )
        hint.setObjectName("subtitleLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._open_btn = QPushButton("Open Terminal Anyway")
        self._open_btn.setObjectName("primaryButton")
        self._open_btn.setFixedWidth(180)
        layout.addWidget(self._open_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def open_button(self) -> QPushButton:
        return self._open_btn


# ── Main page ────────────────────────────────────────────────────────────────


class TerminalPage(QWidget):
    """Interactive ADB/fastboot terminal with command history."""

    def __init__(
        self,
        device_service=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._device_service = device_service
        self._process: QProcess | None = None
        self._setup_ui()

        if device_service is not None:
            device_service.device_list_updated.connect(self._on_devices_updated)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("Terminal")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        subtitle = QLabel("ADB & Fastboot shell")
        subtitle.setObjectName("pageSubtitle")
        header.addWidget(subtitle)
        header.addStretch()

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["ADB", "Fastboot", "Custom"])
        self._mode_combo.setFixedWidth(120)
        header.addWidget(self._mode_combo)

        self._device_badge = CyberBadge("No Device", "neutral")
        header.addWidget(self._device_badge)
        root.addLayout(header)

        # Main content splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Quick panel
        self._quick_panel = _QuickPanel()
        self._quick_panel.set_command_callback(self._run_command)
        self._quick_panel.setMaximumWidth(200)
        splitter.addWidget(self._quick_panel)

        # Right: Terminal output + input
        term_widget = QWidget()
        tl = QVBoxLayout(term_widget)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)

        self._output = _TerminalOutput()
        self._output.append_line(
            "CyberFlash Terminal v1.0 \u2014 Type commands below.\n"
            "Commands are automatically prefixed with adb/fastboot "
            "based on mode selection.\n"
        )
        tl.addWidget(self._output)

        # Input row
        input_row = QHBoxLayout()
        prompt = QLabel("\u276f")
        prompt.setObjectName("terminalPrompt")
        prompt.setFixedWidth(20)
        input_row.addWidget(prompt)

        self._input = _CommandInput()
        self._input.returnPressed.connect(self._on_enter)
        input_row.addWidget(self._input)

        self._run_btn = QPushButton("Run")
        self._run_btn.setObjectName("primaryButton")
        self._run_btn.setFixedWidth(60)
        self._run_btn.clicked.connect(self._on_enter)
        input_row.addWidget(self._run_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("dangerButton")
        self._stop_btn.setFixedWidth(60)
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self._stop_process)
        input_row.addWidget(self._stop_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedWidth(60)
        self._clear_btn.clicked.connect(self._output.clear)
        input_row.addWidget(self._clear_btn)
        tl.addLayout(input_row)

        # Status bar
        status_row = QHBoxLayout()
        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("subtitleLabel")
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        self._history_label = QLabel("History: 0 commands")
        self._history_label.setObjectName("subtitleLabel")
        status_row.addWidget(self._history_label)
        tl.addLayout(status_row)

        splitter.addWidget(term_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    # ── Command execution ────────────────────────────────────────────────

    def _on_enter(self) -> None:
        cmd = self._input.text().strip()
        if not cmd:
            return
        self._input.add_to_history(cmd)
        self._input.clear()
        self._run_command(cmd)
        self._history_label.setText(f"History: {len(self._input._history)} commands")

    def _run_command(self, cmd: str) -> None:
        """Execute a command via QProcess."""
        # Auto-prefix with mode if no tool specified
        mode = self._mode_combo.currentText().lower()
        if mode != "custom" and not cmd.startswith(("adb", "fastboot")):
            cmd = f"{mode} {cmd}"

        self._output.append_line(f"\u276f {cmd}")
        self._status_label.setText(f"Running: {cmd}")

        parts = cmd.split()
        if not parts:
            return

        program = parts[0]
        args = parts[1:]

        # Resolve tool path from bundled tools if available
        tools_dir = get_tools_dir()
        tool_path = tools_dir / program
        if tool_path.exists():
            program = str(tool_path)

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

        self._run_btn.setVisible(False)
        self._stop_btn.setVisible(True)

        self._process.start(program, args)

    @Slot()
    def _on_stdout(self) -> None:
        if self._process:
            data = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
            self._output.append_text(data)

    @Slot(int, object)
    def _on_finished(self, exit_code: int, _status: object) -> None:
        self._output.append_line(f"\n[Process exited with code {exit_code}]\n")
        self._status_label.setText("Ready")
        self._run_btn.setVisible(True)
        self._stop_btn.setVisible(False)
        self._process = None

    @Slot(object)
    def _on_error(self, error: object) -> None:
        self._output.append_line(f"\n[Error: {error}]\n")
        self._status_label.setText("Error occurred")
        self._run_btn.setVisible(True)
        self._stop_btn.setVisible(False)

    def _stop_process(self) -> None:
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
            self._output.append_line("\n[Process killed by user]\n")

    @Slot(list)
    def _on_devices_updated(self, devices: list) -> None:
        if devices:
            d = devices[0]
            name = getattr(d, "display_name", getattr(d, "serial", "Device"))
            self._device_badge.set_text_and_variant(f"\u2713 {name}", "success")
        else:
            self._device_badge.set_text_and_variant("No Device", "neutral")
