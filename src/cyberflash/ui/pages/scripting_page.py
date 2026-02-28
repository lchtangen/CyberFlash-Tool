"""scripting_page.py — ADB scripting IDE page.

Provides an in-app scripting environment where users can write and
run sequences of ADB shell commands against connected devices, view
output in real-time, and save/load scripts to disk.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from cyberflash.models.device import DeviceInfo
from cyberflash.services.device_service import DeviceService
from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)

_MONO_FONT = QFont("Fira Code, Consolas, monospace", 10)

_PLACEHOLDER_SCRIPT = """\
# ADB Script — one command per line.
# Lines starting with # are comments.
# Use {serial} placeholder for the device serial.
#
# Examples:
#   shell getprop ro.product.model
#   shell settings get system screen_brightness
#   shell pm list packages -3
"""


# ── Script runner worker ──────────────────────────────────────────────────────


class _ScriptWorker(BaseWorker):
    """Runs ADB script lines sequentially."""

    output_line = Signal(str)  # per-command output

    def __init__(self, serial: str, script: str, parent=None) -> None:
        super().__init__(parent)
        self._serial = serial
        self._script = script
        self._aborted = False

    @Slot()
    def start(self) -> None:  # type: ignore[override]
        from cyberflash.core.adb_manager import AdbManager

        lines = [
            ln.strip() for ln in self._script.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        try:
            for line in lines:
                if self._aborted:
                    self.output_line.emit("⚠ Script aborted by user.")
                    break
                cmd = line.replace("{serial}", self._serial)
                self.output_line.emit(f"$ {cmd}")
                if cmd.startswith("shell "):
                    result = AdbManager.shell(self._serial, cmd[6:], timeout=30)
                else:
                    result = AdbManager.run_adb(self._serial, cmd.split(), timeout=30)
                for out_line in result.splitlines():
                    self.output_line.emit(f"  {out_line}")
                self.output_line.emit("")
        except Exception as exc:
            logger.exception("ScriptWorker error")
            self.error.emit(str(exc))
            self.output_line.emit(f"[ERROR] {exc}")
        finally:
            self.output_line.emit("✓ Script finished.")
            self.finished.emit()

    def abort(self) -> None:
        self._aborted = True


# ── Page ──────────────────────────────────────────────────────────────────────


class ScriptingPage(QWidget):
    """In-app ADB Scripting IDE page.

    Args:
        device_service: Shared DeviceService for device selection.
        parent: Optional Qt parent.
    """

    def __init__(
        self, device_service: DeviceService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._service = device_service
        self._thread: QThread | None = None
        self._worker: _ScriptWorker | None = None

        self._build_ui()
        self._service.selected_device_changed.connect(self._on_device_changed)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()
        title = QLabel("Scripting IDE")
        title.setObjectName("pageTitle")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self._device_badge = CyberBadge("No device", "neutral")
        toolbar.addWidget(self._device_badge)
        root.addLayout(toolbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # Action bar
        action_bar = QHBoxLayout()
        self._btn_run = QPushButton("▶ Run Script")
        self._btn_run.clicked.connect(self._run_script)
        self._btn_stop = QPushButton("■ Stop")
        self._btn_stop.clicked.connect(self._stop_script)
        self._btn_stop.setEnabled(False)
        self._btn_open = QPushButton("Open…")
        self._btn_open.clicked.connect(self._open_script)
        self._btn_save = QPushButton("Save…")
        self._btn_save.clicked.connect(self._save_script)
        self._btn_clear_out = QPushButton("Clear Output")
        self._btn_clear_out.clicked.connect(self._clear_output)
        for btn in [self._btn_run, self._btn_stop, self._btn_open, self._btn_save, self._btn_clear_out]:
            action_bar.addWidget(btn)
        action_bar.addStretch()
        root.addLayout(action_bar)

        # Editor / output splitter
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Script editor
        editor_panel = QWidget()
        ep_layout = QVBoxLayout(editor_panel)
        ep_layout.setContentsMargins(0, 0, 0, 0)
        ep_layout.addWidget(QLabel("Script:"))
        self._editor = QPlainTextEdit()
        self._editor.setFont(_MONO_FONT)
        self._editor.setPlaceholderText("# Write ADB commands here…")
        self._editor.setPlainText(_PLACEHOLDER_SCRIPT)
        ep_layout.addWidget(self._editor)
        splitter.addWidget(editor_panel)

        # Output console
        out_panel = QWidget()
        op_layout = QVBoxLayout(out_panel)
        op_layout.setContentsMargins(0, 0, 0, 0)
        op_layout.addWidget(QLabel("Output:"))
        self._output = QPlainTextEdit()
        self._output.setFont(_MONO_FONT)
        self._output.setReadOnly(True)
        op_layout.addWidget(self._output)
        splitter.addWidget(out_panel)

        splitter.setSizes([300, 200])
        root.addWidget(splitter, stretch=1)

    @Slot(object)
    def _on_device_changed(self, device: DeviceInfo | None) -> None:
        if device:
            self._device_badge.update_text(device.model or device.serial)
            self._device_badge.update_state("success")
        else:
            self._device_badge.update_text("No device")
            self._device_badge.update_state("neutral")

    def _run_script(self) -> None:
        device = self._service.selected_device
        if not device:
            QMessageBox.warning(self, "No Device", "Please select a device first.")
            return

        script = self._editor.toPlainText().strip()
        if not script:
            return

        self._output.clear()
        self._btn_run.setEnabled(False)
        self._btn_stop.setEnabled(True)

        self._thread = QThread(self)
        self._worker = _ScriptWorker(device.serial, script)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._worker.output_line.connect(self._append_output)
        self._worker.finished.connect(self._on_script_done)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _stop_script(self) -> None:
        if self._worker:
            self._worker.abort()

    @Slot(str)
    def _append_output(self, line: str) -> None:
        self._output.appendPlainText(line)
        sb = self._output.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    @Slot()
    def _on_script_done(self) -> None:
        self._btn_run.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._thread = None
        self._worker = None

    def _open_script(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Script", "", "ADB Scripts (*.adb *.sh *.txt);;All Files (*)"
        )
        if path:
            try:
                self._editor.setPlainText(Path(path).read_text(encoding="utf-8"))
            except OSError as exc:
                QMessageBox.critical(self, "Error", f"Could not open file:\n{exc}")

    def _save_script(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Script", "script.adb", "ADB Scripts (*.adb *.sh *.txt);;All Files (*)"
        )
        if path:
            try:
                Path(path).write_text(self._editor.toPlainText(), encoding="utf-8")
            except OSError as exc:
                QMessageBox.critical(self, "Error", f"Could not save file:\n{exc}")

    def _clear_output(self) -> None:
        self._output.clear()
