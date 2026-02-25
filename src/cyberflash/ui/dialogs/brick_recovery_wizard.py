"""brick_recovery_wizard.py — Device brick detection and recovery guidance.

4-step wizard: Detect → Diagnose → Recover → Verify.
No actual flash is triggered from this wizard; it guides the user to
the appropriate page/dialog for recovery.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────────


class BrickType(StrEnum):
    SOFT_BRICK     = "soft_brick"
    HARD_BRICK     = "hard_brick"
    BOOTLOOP       = "bootloop"
    EDL_MODE       = "edl_mode"
    FASTBOOT_STUCK = "fastboot_stuck"
    UNKNOWN        = "unknown"


_BRICK_DESCRIPTIONS: dict[BrickType, str] = {
    BrickType.SOFT_BRICK: (
        "Soft brick: Device boots but gets stuck before Android loads.\n"
        "Cause: Incompatible ROM, failed OTA, or bad system modification.\n"
        "Recovery difficulty: Low-Medium"
    ),
    BrickType.HARD_BRICK: (
        "Hard brick: Device does not respond to USB at all.\n"
        "Cause: Corrupted bootloader, empty battery, or hardware damage.\n"
        "Recovery difficulty: High"
    ),
    BrickType.BOOTLOOP: (
        "Boot loop: Device repeatedly boots and restarts.\n"
        "Cause: Corrupted system partition or bad kernel.\n"
        "Recovery difficulty: Low-Medium"
    ),
    BrickType.EDL_MODE: (
        "EDL mode: Device is in Qualcomm Emergency Download mode (9008).\n"
        "Cause: Bootloader is damaged or device entered EDL intentionally.\n"
        "Recovery difficulty: Medium (requires firehose + EDL tools)"
    ),
    BrickType.FASTBOOT_STUCK: (
        "Fastboot stuck: Device is in fastboot but cannot proceed.\n"
        "Cause: Locked bootloader, AVB failure, or partition mismatch.\n"
        "Recovery difficulty: Low"
    ),
    BrickType.UNKNOWN: (
        "Could not classify the brick type.\n"
        "Manual diagnosis required — check device LED, USB PID."
    ),
}

_RECOVERY_STEPS: dict[BrickType, list[str]] = {
    BrickType.SOFT_BRICK: [
        "1. Boot into recovery: hold Volume Up + Power",
        "2. Wipe cache partition and Dalvik cache",
        "3. If still stuck: Wipe Data / Factory Reset",
        "4. Flash stock ROM from CyberFlash → Flash page",
    ],
    BrickType.BOOTLOOP: [
        "1. Boot into TWRP/stock recovery",
        "2. Wipe cache + Dalvik/ART cache",
        "3. If loop persists: Flash stock boot.img via fastboot",
        "4. Nuclear option: full factory flash via Flash page",
    ],
    BrickType.EDL_MODE: [
        "1. Open CyberFlash → Rescue page",
        "2. Select firehose programmer for your device",
        "3. Flash stock firmware via EDL",
        "4. Alternative: Use Qualcomm QFIL tool",
    ],
    BrickType.FASTBOOT_STUCK: [
        "1. Run: fastboot devices (verify connection)",
        "2. Try: fastboot reboot-recovery",
        "3. If bootloader locked: fastboot flashing unlock",
        "4. Flash stock firmware from Flash page",
    ],
    BrickType.HARD_BRICK: [
        "1. Try charging for 30 min (may be empty battery)",
        "2. Try EDL mode: special key combo for your device",
        "3. Use CyberFlash → Rescue page for EDL flash",
        "4. Professional repair may be needed if still unresponsive",
    ],
    BrickType.UNKNOWN: [
        "1. Check device with: adb devices && fastboot devices",
        "2. Try volume key combos to enter recovery / fastboot",
        "3. Check device USB PID (e.g. 9008 = Qualcomm EDL)",
        "4. Look up your exact model on XDA Developers",
    ],
}


# ── Detection worker ──────────────────────────────────────────────────────────


class _DetectWorker(QThread):
    result_ready = Signal(str, str)  # mode ("adb"/"fastboot"/"edl"/"none"), brick_type

    def run(self) -> None:
        from cyberflash.core.adb_manager import AdbManager

        devices = AdbManager.list_devices()
        if devices:
            self.result_ready.emit("adb", BrickType.UNKNOWN)
            return

        # Try fastboot
        import subprocess

        from cyberflash.core.tool_manager import ToolManager
        try:
            adb_cmd = ToolManager.adb_cmd()
            r = subprocess.run(
                [*adb_cmd[:-1], "fastboot", "devices"],
                capture_output=True, text=True, timeout=5,
            )
            if r.stdout.strip():
                self.result_ready.emit("fastboot", BrickType.FASTBOOT_STUCK)
                return
        except Exception:
            pass

        self.result_ready.emit("none", BrickType.HARD_BRICK)


# ── Wizard pages ──────────────────────────────────────────────────────────────


class _DetectPage(QWidget):
    scan_done = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title = QLabel("Step 1: Detecting Device State")
        title.setStyleSheet("font-size: 18px; color: #00ff88; font-weight: bold;")
        layout.addWidget(title)

        self._status = QLabel("Connect your device and click Scan.")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setVisible(False)
        layout.addWidget(self._bar)

        self._scan_btn = QPushButton("Scan for Device")
        self._scan_btn.setObjectName("primaryButton")
        self._scan_btn.clicked.connect(self._scan)
        layout.addWidget(self._scan_btn)
        layout.addStretch()

        self._worker: _DetectWorker | None = None

    def _scan(self) -> None:
        self._scan_btn.setEnabled(False)
        self._bar.setVisible(True)
        self._status.setText("Scanning...")
        self._worker = _DetectWorker()
        self._worker.result_ready.connect(self._on_result)
        self._worker.start()

    def _on_result(self, mode: str, brick_type: str) -> None:
        self._bar.setVisible(False)
        self._scan_btn.setEnabled(True)
        msg = {
            "adb":     "Device found via ADB",
            "fastboot": "Device found via Fastboot",
            "none":    "No device detected",
        }.get(mode, "Unknown state")
        self._status.setText(msg)
        self.scan_done.emit(mode, brick_type)


class _DiagnosePage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Step 2: Diagnosis")
        title.setStyleSheet("font-size: 18px; color: #00ff88; font-weight: bold;")
        layout.addWidget(title)

        self._desc_lbl = QLabel("Awaiting scan result...")
        self._desc_lbl.setWordWrap(True)
        self._desc_lbl.setStyleSheet("color: #c9d1d9; font-size: 13px;")
        layout.addWidget(self._desc_lbl)
        layout.addStretch()

    def set_brick_type(self, brick_type: BrickType) -> None:
        self._desc_lbl.setText(_BRICK_DESCRIPTIONS.get(brick_type, "Unknown"))


class _RecoverPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Step 3: Recovery Steps")
        title.setStyleSheet("font-size: 18px; color: #00ff88; font-weight: bold;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self._steps_layout = QVBoxLayout(container)
        self._steps_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._steps_layout.setSpacing(8)
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def set_steps(self, steps: list[str]) -> None:
        while self._steps_layout.count():
            item = self._steps_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        for step in steps:
            lbl = QLabel(step)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color: #c9d1d9; font-size: 13px; padding: 4px;")
            self._steps_layout.addWidget(lbl)


class _VerifyPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Step 4: Verify Recovery")
        title.setStyleSheet("font-size: 18px; color: #00ff88; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel(
            "After performing the recovery steps:\n\n"
            "1. Device should boot into Android normally\n"
            "2. Run CyberFlash diagnostics for a health check\n"
            "3. Restore your data from backup\n\n"
            "If still not working, consult XDA Developers for your device."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #c9d1d9; font-size: 13px;")
        layout.addWidget(desc)
        layout.addStretch()


# ── Main wizard ────────────────────────────────────────────────────────────────


class BrickRecoveryWizard(QDialog):
    """Step-by-step device brick recovery wizard."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Brick Recovery Wizard")
        self.setMinimumSize(560, 400)
        self._brick_type = BrickType.UNKNOWN
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()

        self._detect_page = _DetectPage()
        self._detect_page.scan_done.connect(self._on_detect_done)
        self._stack.addWidget(self._detect_page)

        self._diagnose_page = _DiagnosePage()
        self._stack.addWidget(self._diagnose_page)

        self._recover_page = _RecoverPage()
        self._stack.addWidget(self._recover_page)

        self._verify_page = _VerifyPage()
        self._stack.addWidget(self._verify_page)

        root.addWidget(self._stack)

        # Navigation buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 8, 16, 16)

        self._back_btn = QPushButton("← Back")
        self._back_btn.setObjectName("secondaryButton")
        self._back_btn.setEnabled(False)
        self._back_btn.clicked.connect(self._prev)
        btn_row.addWidget(self._back_btn)
        btn_row.addStretch()

        self._next_btn = QPushButton("Next →")
        self._next_btn.setObjectName("primaryButton")
        self._next_btn.clicked.connect(self._next)
        btn_row.addWidget(self._next_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    def _on_detect_done(self, _mode: str, brick_type_str: str) -> None:
        self._brick_type = BrickType(brick_type_str)
        self._diagnose_page.set_brick_type(self._brick_type)
        steps = _RECOVERY_STEPS.get(self._brick_type, _RECOVERY_STEPS[BrickType.UNKNOWN])
        self._recover_page.set_steps(steps)

    def _next(self) -> None:
        idx = self._stack.currentIndex()
        if idx < self._stack.count() - 1:
            self._stack.setCurrentIndex(idx + 1)
            self._back_btn.setEnabled(True)
            if self._stack.currentIndex() == self._stack.count() - 1:
                self._next_btn.setEnabled(False)

    def _prev(self) -> None:
        idx = self._stack.currentIndex()
        if idx > 0:
            self._stack.setCurrentIndex(idx - 1)
            self._next_btn.setEnabled(True)
            if idx == 1:
                self._back_btn.setEnabled(False)
