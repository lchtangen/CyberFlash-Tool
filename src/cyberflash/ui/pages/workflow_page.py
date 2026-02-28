"""workflow_page.py — Visual Workflow Builder.

Allows users to compose multi-step device operations (flash, root,
backup, wipe, reboot) into named workflows, save them as JSON, and
run them on a selected device with a step-by-step progress tracker.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cyberflash.models.device import DeviceInfo
from cyberflash.services.device_service import DeviceService
from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class WorkflowStep:
    """One step in a workflow."""

    action: str           # "backup" | "reboot" | "reboot_recovery" | "wait" | "shell"
    label: str = ""
    args: dict[str, str] = field(default_factory=dict)
    status: str = "pending"  # "pending" | "running" | "done" | "failed"


@dataclass
class Workflow:
    """A named sequence of WorkflowStep objects."""

    name: str
    steps: list[WorkflowStep] = field(default_factory=list)
    description: str = ""


_PRESET_STEPS: list[tuple[str, str]] = [
    ("backup",          "Backup Contacts"),
    ("reboot_recovery", "Reboot to Recovery"),
    ("reboot",          "Reboot to System"),
    ("shell",           "ADB Shell Command"),
    ("wait",            "Wait 10 seconds"),
]


# ── Worker ────────────────────────────────────────────────────────────────────


class _WorkflowWorker(BaseWorker):
    """Runs a Workflow sequentially on a device."""

    step_started  = Signal(int, str)   # step index, label
    step_done     = Signal(int, bool)  # step index, success
    log_line      = Signal(str)

    def __init__(self, serial: str, workflow: Workflow, parent=None) -> None:
        super().__init__(parent)
        self._serial = serial
        self._workflow = workflow
        self._aborted = False

    @Slot()
    def start(self) -> None:  # type: ignore[override]
        from cyberflash.core.adb_manager import AdbManager

        try:
            for i, step in enumerate(self._workflow.steps):
                if self._aborted:
                    self.log_line.emit("⚠ Workflow aborted.")
                    break

                self.step_started.emit(i, step.label or step.action)
                step.status = "running"
                success = False

                def log_cb(msg: str) -> None:
                    self.log_line.emit(msg)

                try:
                    if step.action == "backup":
                        from pathlib import Path as _Path

                        from cyberflash.core.contacts_manager import (
                            ContactsManager,
                        )
                        dest = _Path(step.args.get("dest", "/tmp/workflow_backup"))
                        success = ContactsManager.backup_contacts(self._serial, dest, log_cb=log_cb)

                    elif step.action == "reboot":
                        AdbManager.shell(self._serial, "reboot", timeout=5)
                        success = True

                    elif step.action == "reboot_recovery":
                        AdbManager.shell(self._serial, "reboot recovery", timeout=5)
                        success = True

                    elif step.action == "shell":
                        cmd = step.args.get("cmd", "echo no-op")
                        out = AdbManager.shell(self._serial, cmd, timeout=30)
                        self.log_line.emit(out)
                        success = True

                    elif step.action == "wait":
                        import time
                        secs = int(step.args.get("seconds", "10"))
                        self.log_line.emit(f"Waiting {secs}s…")
                        time.sleep(secs)
                        success = True

                    else:
                        self.log_line.emit(f"Unknown action: {step.action}")
                        success = False

                except Exception as exc:
                    logger.exception("Step %d failed", i)
                    self.log_line.emit(f"[ERROR] Step {i}: {exc}")
                    success = False

                step.status = "done" if success else "failed"
                self.step_done.emit(i, success)

                if not success and step.args.get("stop_on_fail", "true").lower() == "true":
                    self.log_line.emit("Stopping workflow due to step failure.")
                    break

        except Exception as exc:
            logger.exception("WorkflowWorker error")
            self.error.emit(str(exc))
        finally:
            self.log_line.emit("✓ Workflow complete.")
            self.finished.emit()

    def abort(self) -> None:
        self._aborted = True


# ── Page ──────────────────────────────────────────────────────────────────────


class WorkflowPage(QWidget):
    """Visual Workflow Builder page.

    Args:
        device_service: Shared DeviceService.
        parent: Optional Qt parent.
    """

    def __init__(
        self, device_service: DeviceService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._service = device_service
        self._workflow = Workflow(name="My Workflow")
        self._thread: QThread | None = None
        self._worker: _WorkflowWorker | None = None

        self._build_ui()
        self._refresh_steps()
        self._service.selected_device_changed.connect(self._on_device_changed)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()
        title = QLabel("Workflow Builder")
        title.setObjectName("pageTitle")
        toolbar.addWidget(title)
        toolbar.addStretch()
        self._device_badge = CyberBadge("No device", "neutral")
        toolbar.addWidget(self._device_badge)
        root.addLayout(toolbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # Workflow name + actions
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Workflow:"))
        self._name_label = QLabel(self._workflow.name)
        self._name_label.setObjectName("cardHeader")
        name_row.addWidget(self._name_label)
        name_row.addStretch()
        btn_rename = QPushButton("Rename")
        btn_rename.clicked.connect(self._rename_workflow)
        btn_load = QPushButton("Load…")
        btn_load.clicked.connect(self._load_workflow)
        btn_save = QPushButton("Save…")
        btn_save.clicked.connect(self._save_workflow)
        for b in [btn_rename, btn_load, btn_save]:
            name_row.addWidget(b)
        root.addLayout(name_row)

        # Step editor row
        mid = QHBoxLayout()

        # Left: step list
        left = QVBoxLayout()
        left.addWidget(QLabel("Steps:"))
        self._steps_list = QListWidget()
        self._steps_list.setMaximumWidth(280)
        left.addWidget(self._steps_list)

        step_btns = QHBoxLayout()
        self._step_combo = QComboBox()
        for action, label in _PRESET_STEPS:
            self._step_combo.addItem(label, action)
        step_btns.addWidget(self._step_combo)
        btn_add = QPushButton("Add")
        btn_add.clicked.connect(self._add_step)
        btn_remove = QPushButton("Remove")
        btn_remove.clicked.connect(self._remove_step)
        btn_up = QPushButton("↑")
        btn_down = QPushButton("↓")
        btn_up.clicked.connect(self._move_up)
        btn_down.clicked.connect(self._move_down)
        for b in [btn_add, btn_remove, btn_up, btn_down]:
            step_btns.addWidget(b)
        left.addLayout(step_btns)
        mid.addLayout(left)

        # Right: log + run
        right = QVBoxLayout()
        right.addWidget(QLabel("Output:"))
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        right.addWidget(self._log)

        run_row = QHBoxLayout()
        self._btn_run = QPushButton("▶ Run Workflow")
        self._btn_run.clicked.connect(self._run_workflow)
        self._btn_abort = QPushButton("■ Abort")
        self._btn_abort.clicked.connect(self._abort_workflow)
        self._btn_abort.setEnabled(False)
        for b in [self._btn_run, self._btn_abort]:
            run_row.addWidget(b)
        run_row.addStretch()
        right.addLayout(run_row)
        mid.addLayout(right)

        root.addLayout(mid, stretch=1)

    # ── Step management ───────────────────────────────────────────────────────

    def _add_step(self) -> None:
        action = self._step_combo.currentData()
        label = self._step_combo.currentText()
        self._workflow.steps.append(WorkflowStep(action=action, label=label))
        self._refresh_steps()

    def _remove_step(self) -> None:
        row = self._steps_list.currentRow()
        if 0 <= row < len(self._workflow.steps):
            self._workflow.steps.pop(row)
            self._refresh_steps()

    def _move_up(self) -> None:
        row = self._steps_list.currentRow()
        if row > 0:
            steps = self._workflow.steps
            steps[row - 1], steps[row] = steps[row], steps[row - 1]
            self._refresh_steps()
            self._steps_list.setCurrentRow(row - 1)

    def _move_down(self) -> None:
        row = self._steps_list.currentRow()
        if row < len(self._workflow.steps) - 1:
            steps = self._workflow.steps
            steps[row], steps[row + 1] = steps[row + 1], steps[row]
            self._refresh_steps()
            self._steps_list.setCurrentRow(row + 1)

    def _refresh_steps(self) -> None:
        self._steps_list.clear()
        for i, step in enumerate(self._workflow.steps, 1):
            icon = {"done": "✓", "failed": "✗", "running": "▶"}.get(step.status, f"{i}.")
            self._steps_list.addItem(QListWidgetItem(f"{icon} {step.label or step.action}"))

    def _rename_workflow(self) -> None:
        name, ok = QInputDialog.getText(self, "Rename Workflow", "Workflow name:", text=self._workflow.name)
        if ok and name:
            self._workflow.name = name
            self._name_label.setText(name)

    def _save_workflow(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Workflow", f"{self._workflow.name}.json", "JSON (*.json)"
        )
        if path:
            data = {"name": self._workflow.name, "steps": [asdict(s) for s in self._workflow.steps]}
            Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load_workflow(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Workflow", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self._workflow.name = data.get("name", "Workflow")
            self._workflow.steps = [WorkflowStep(**s) for s in data.get("steps", [])]
            self._name_label.setText(self._workflow.name)
            self._refresh_steps()
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", f"Could not load workflow:\n{exc}")

    # ── Execution ─────────────────────────────────────────────────────────────

    @Slot(object)
    def _on_device_changed(self, device: DeviceInfo | None) -> None:
        if device:
            self._device_badge.update_text(device.model or device.serial)
            self._device_badge.update_state("success")
        else:
            self._device_badge.update_text("No device")
            self._device_badge.update_state("neutral")

    def _run_workflow(self) -> None:
        device = self._service.selected_device
        if not device:
            QMessageBox.warning(self, "No Device", "Select a device first.")
            return
        if not self._workflow.steps:
            QMessageBox.information(self, "Empty", "Add steps to the workflow first.")
            return

        # Reset step statuses
        for step in self._workflow.steps:
            step.status = "pending"
        self._refresh_steps()
        self._log.clear()

        self._btn_run.setEnabled(False)
        self._btn_abort.setEnabled(True)

        self._thread = QThread(self)
        self._worker = _WorkflowWorker(device.serial, self._workflow)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._worker.log_line.connect(lambda line: self._log.append(line))
        self._worker.step_done.connect(lambda i, ok: self._refresh_steps())
        self._worker.finished.connect(self._on_run_done)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _abort_workflow(self) -> None:
        if self._worker:
            self._worker.abort()

    @Slot()
    def _on_run_done(self) -> None:
        self._btn_run.setEnabled(True)
        self._btn_abort.setEnabled(False)
        self._refresh_steps()
        self._thread = None
        self._worker = None
