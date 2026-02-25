from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.edl_manager import EdlManager
from cyberflash.core.tool_manager import ToolManager
from cyberflash.models.device import DeviceInfo, DeviceState
from cyberflash.models.edl_task import EdlTask
from cyberflash.models.flash_task import FlashStep, StepStatus
from cyberflash.models.profile import DeviceProfile
from cyberflash.profiles import ProfileRegistry
from cyberflash.ui.panels.log_panel import LogPanel
from cyberflash.ui.panels.progress_panel import ProgressPanel
from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.step_tracker import StepTracker
from cyberflash.utils.platform_utils import get_app_data_dir, get_platform
from cyberflash.workers.edl_worker import EdlWorker

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "rescue_settings.json"

_RESCUE_STEPS = [
    ("verify_device", "Verify EDL device present"),
    ("flash_restore", "Flash all partitions (rawprogram.xml)"),
    ("reboot", "Reboot to system"),
]


class _SectionFrame(QFrame):
    """Styled section box with a title label."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #161b22; border: 1px solid #21262d; border-radius: 6px; }"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 10)
        outer.setSpacing(6)

        hdr = QLabel(title)
        hdr.setStyleSheet("font-weight: bold; font-size: 12px; color: #8b949e;"
                          " border: none; background: transparent;")
        outer.addWidget(hdr)

        self._content = QVBoxLayout()
        self._content.setContentsMargins(0, 0, 0, 0)
        self._content.setSpacing(4)
        outer.addLayout(self._content)

    def content(self) -> QVBoxLayout:
        return self._content


# ── Tab 1: Setup ─────────────────────────────────────────────────────────────

class _SetupTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # EDL Device Status
        self._device_section = _SectionFrame("EDL Device Status")
        self._device_status_lbl = QLabel("Scanning for EDL devices (VID 05C6, PID 9008)…")
        self._device_status_lbl.setWordWrap(True)
        self._device_badge: CyberBadge | None = None
        self._device_row = QHBoxLayout()
        self._device_row.setContentsMargins(0, 0, 0, 0)
        self._device_row.addWidget(self._device_status_lbl, stretch=1)
        self._device_section.content().addLayout(self._device_row)
        layout.addWidget(self._device_section)

        # System Requirements
        self._req_section = _SectionFrame("System Requirements")
        self._udev_row = self._make_udev_row()
        self._req_section.content().addLayout(self._udev_row)
        self._edl_tool_lbl = QLabel()
        self._req_section.content().addWidget(self._edl_tool_lbl)
        self._refresh_requirements()
        layout.addWidget(self._req_section)

        # How to Enter EDL Mode
        self._entry_section = _SectionFrame("How to Enter EDL Mode")
        self._entry_device_lbl = QLabel()
        self._entry_section.content().addWidget(self._entry_device_lbl)
        self._entry_methods_lbl = QLabel()
        self._entry_methods_lbl.setWordWrap(True)
        self._entry_section.content().addWidget(self._entry_methods_lbl)
        self._show_full_btn = QPushButton("Show full instructions…")
        self._show_full_btn.setMaximumWidth(220)
        self._entry_section.content().addWidget(self._show_full_btn)
        layout.addWidget(self._entry_section)

        layout.addStretch()

        self._profile: DeviceProfile | None = None
        self._load_default_profile()

    def _make_udev_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._udev_lbl = QLabel()
        row.addWidget(self._udev_lbl, stretch=1)
        if get_platform() == "linux":
            setup_btn = QPushButton("Run Setup")
            setup_btn.setMaximumWidth(100)
            setup_btn.clicked.connect(self._open_setup_dialog)
            row.addWidget(setup_btn)
        guide_btn = QPushButton("View Guide")
        guide_btn.setMaximumWidth(100)
        guide_btn.clicked.connect(self._open_setup_dialog)
        row.addWidget(guide_btn)
        return row

    def _refresh_requirements(self) -> None:
        platform = get_platform()

        # udev / driver status
        if platform == "linux":
            configured = EdlManager.is_udev_configured()
            icon = "✓" if configured else "✗"
            color = "#3fb950" if configured else "#f85149"
            self._udev_lbl.setText(f"<span style='color:{color}'>{icon}</span> udev rule: "
                                   f"{'configured' if configured else 'not configured'}")
        elif platform == "macos":
            self._udev_lbl.setText("macOS: ensure libusb is installed (brew install libusb)")
        else:
            self._udev_lbl.setText("Windows: ensure WinUSB / QDLoader driver is installed")

        # edl tool
        edl_path = ToolManager.find_edl()
        if edl_path:
            self._edl_tool_lbl.setText(
                f"<span style='color:#3fb950'>✓</span> edl tool: {edl_path}"
            )
        else:
            self._edl_tool_lbl.setText(
                "<span style='color:#f85149'>✗</span> edl tool not found — "
                "install: <code>pip install edl</code>"
            )
        self._edl_tool_lbl.setTextFormat(Qt.TextFormat.RichText)

    def _load_default_profile(self) -> None:
        """Try to load the first profile that has EDL config."""
        for codename in ProfileRegistry.list_all():
            profile = ProfileRegistry.load(codename)
            if profile and profile.edl:
                self.set_profile(profile)
                return

    def set_profile(self, profile: DeviceProfile) -> None:
        self._profile = profile
        self._entry_device_lbl.setText(
            f"<b>Device:</b> {profile.brand} {profile.model} ({profile.codename})"
        )
        self._entry_device_lbl.setTextFormat(Qt.TextFormat.RichText)

        if profile.edl and profile.edl.edl_entry_methods:
            methods = profile.edl.edl_entry_methods
            # Show first two methods inline, rest via dialog
            preview = "\n".join(f"  {m}" for m in methods[:2])
            if len(methods) > 2:
                preview += f"\n  … ({len(methods) - 2} more)"
            self._entry_methods_lbl.setText(preview)
        else:
            self._entry_methods_lbl.setText("No EDL entry instructions available.")

    def update_device_status(self, edl_devices: list[DeviceInfo]) -> None:
        """Update the device status section when EDL devices are detected."""
        # Remove old badge if present
        if self._device_badge is not None:
            self._device_row.removeWidget(self._device_badge)
            self._device_badge.deleteLater()
            self._device_badge = None

        if edl_devices:
            dev = edl_devices[0]
            self._device_status_lbl.setText(
                f"DETECTED: {dev.brand} {dev.model or dev.serial} in EDL mode"
            )
            badge = CyberBadge("EDL", "error")
            self._device_badge = badge
            self._device_row.addWidget(badge)
            if dev.codename:
                profile = ProfileRegistry.load(dev.codename)
                if profile:
                    self.set_profile(profile)
        else:
            self._device_status_lbl.setText(
                "Scanning for EDL devices (VID 05C6, PID 9008)…"
            )

    def _open_setup_dialog(self) -> None:
        from cyberflash.ui.dialogs.edl_setup_dialog import EdlSetupDialog
        dlg = EdlSetupDialog(self)
        dlg.exec()

    def profile(self) -> DeviceProfile | None:
        return self._profile

    def show_entry_dialog(self) -> None:
        if self._profile:
            from cyberflash.ui.dialogs.edl_entry_dialog import EdlEntryDialog
            dlg = EdlEntryDialog(self._profile, self)
            dlg.exec()


# ── Tab 2: Firmware Package ───────────────────────────────────────────────────

class _PackageTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Package dir browser
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Source:"))
        self._dir_lbl = QLabel("<no package selected>")
        self._dir_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._dir_lbl.setStyleSheet("color: #8b949e; font-family: monospace;")
        dir_row.addWidget(self._dir_lbl, stretch=1)
        browse_btn = QPushButton("Browse MSM package folder…")
        browse_btn.clicked.connect(self._browse_package)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        # Auto-detected contents
        self._contents_section = _SectionFrame("Auto-detected Contents")
        self._rawprogram_lbl = QLabel("○ rawprogram0.xml")
        self._patch_lbl = QLabel("○ patch0.xml")
        self._programmer_lbl = QLabel("○ programmer .elf")
        self._images_lbl = QLabel("○ partition .bin images")
        for lbl in (
            self._rawprogram_lbl,
            self._patch_lbl,
            self._programmer_lbl,
            self._images_lbl,
        ):
            self._contents_section.content().addWidget(lbl)

        # Manual programmer picker (shown if not auto-found)
        self._programmer_browse_row = QHBoxLayout()
        self._programmer_browse_btn = QPushButton("Browse for programmer .elf…")
        self._programmer_browse_btn.clicked.connect(self._browse_programmer)
        self._programmer_browse_row.addWidget(self._programmer_browse_btn)
        self._programmer_browse_row.addStretch()
        self._contents_section.content().addLayout(self._programmer_browse_row)
        self._programmer_browse_btn.hide()

        layout.addWidget(self._contents_section)

        # Profile info
        self._profile_section = _SectionFrame("Device Profile")
        self._profile_lbl = QLabel("No profile loaded")
        self._msm_link_btn = QPushButton("Where to get the MSM firmware package? ↗")
        self._msm_link_btn.setFlat(True)
        self._msm_link_btn.setStyleSheet("color: #58a6ff; text-align: left;")
        self._msm_link_btn.clicked.connect(self._open_msm_url)
        self._profile_section.content().addWidget(self._profile_lbl)
        self._profile_section.content().addWidget(self._msm_link_btn)
        layout.addWidget(self._profile_section)

        layout.addStretch()

        # Internal state
        self._package_dir: Path | None = None
        self._programmer: Path | None = None
        self._rawprogram_xml: Path | None = None
        self._patch_xml: Path | None = None
        self._profile: DeviceProfile | None = None

    def _browse_package(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select MSM Firmware Package Folder", str(Path.home())
        )
        if d:
            self.set_package_dir(Path(d))

    def _browse_programmer(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Firehose Programmer (.elf)",
            str(self._package_dir or Path.home()),
            "ELF files (*.elf);;All files (*)"
        )
        if path:
            self._programmer = Path(path)
            self._validate_package()

    def _open_msm_url(self) -> None:
        if self._profile and self._profile.edl and self._profile.edl.msm_package_url:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(self._profile.edl.msm_package_url))

    def set_package_dir(self, path: Path) -> None:
        self._package_dir = path
        self._dir_lbl.setText(str(path))
        self._validate_package()

    def _validate_package(self) -> None:
        if not self._package_dir or not self._package_dir.exists():
            return

        d = self._package_dir

        # rawprogram XML
        rawprogram_files = list(d.glob("rawprogram*.xml"))
        if rawprogram_files:
            self._rawprogram_xml = rawprogram_files[0]
            self._rawprogram_lbl.setText(
                f"<span style='color:#3fb950'>✓</span> {self._rawprogram_xml.name}"
            )
        else:
            self._rawprogram_xml = None
            self._rawprogram_lbl.setText(
                "<span style='color:#f85149'>✗</span> rawprogram*.xml not found"
            )
        self._rawprogram_lbl.setTextFormat(Qt.TextFormat.RichText)

        # patch XML (optional)
        patch_files = list(d.glob("patch*.xml"))
        if patch_files:
            self._patch_xml = patch_files[0]
            self._patch_lbl.setText(
                f"<span style='color:#3fb950'>✓</span> {self._patch_xml.name}"
            )
        else:
            self._patch_xml = None
            self._patch_lbl.setText("○ patch*.xml not found (optional)")
        self._patch_lbl.setTextFormat(Qt.TextFormat.RichText)

        # Programmer .elf — check in package dir first, then by profile filename
        if self._programmer is None or not self._programmer.exists():
            self._programmer = None
            elf_files = list(d.glob("*.elf"))
            if elf_files:
                # Prefer profile-specified filename if we have a profile
                if self._profile and self._profile.edl:
                    preferred = d / self._profile.edl.programmer_filename
                    if preferred.exists():
                        self._programmer = preferred
                if self._programmer is None:
                    self._programmer = elf_files[0]

        if self._programmer and self._programmer.exists():
            self._programmer_lbl.setText(
                f"<span style='color:#3fb950'>✓</span> {self._programmer.name}"
            )
            self._programmer_browse_btn.hide()
        else:
            prog_name = (
                self._profile.edl.programmer_filename
                if self._profile and self._profile.edl
                else "programmer .elf"
            )
            self._programmer_lbl.setText(
                f"<span style='color:#f85149'>✗</span> {prog_name} not found"
            )
            self._programmer_browse_btn.show()
        self._programmer_lbl.setTextFormat(Qt.TextFormat.RichText)

        # Count .bin images
        bin_files = list(d.glob("*.bin"))
        if bin_files:
            self._images_lbl.setText(
                f"<span style='color:#3fb950'>✓</span> {len(bin_files)} partition .bin images"
            )
        else:
            self._images_lbl.setText(
                "<span style='color:#f85149'>✗</span> No .bin partition images found"
            )
        self._images_lbl.setTextFormat(Qt.TextFormat.RichText)

    def set_profile(self, profile: DeviceProfile) -> None:
        self._profile = profile
        prog = profile.edl.programmer_filename if profile.edl else ""
        self._profile_lbl.setText(
            f"Device: {profile.brand} {profile.model} ({profile.codename})  |  "
            f"Programmer: {prog or 'N/A'}  |  "
            f"Method: Fully automated rawprogram restore"
        )
        if self._package_dir:
            self._validate_package()

    def is_valid(self) -> bool:
        return (
            self._package_dir is not None
            and self._rawprogram_xml is not None
            and self._programmer is not None
            and self._programmer.exists()
        )

    def package_dir(self) -> Path | None:
        return self._package_dir

    def programmer(self) -> Path | None:
        return self._programmer

    def rawprogram_xml(self) -> Path | None:
        return self._rawprogram_xml

    def patch_xml(self) -> Path | None:
        return self._patch_xml

    def profile(self) -> DeviceProfile | None:
        return self._profile


# ── Tab 3: Automated Rescue ────────────────────────────────────────────────────

class _RescueTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Top area: StepTracker + LogPanel side by side
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: step tracker
        step_widget = QWidget()
        step_layout = QVBoxLayout(step_widget)
        step_layout.setContentsMargins(0, 0, 0, 0)
        step_layout.addWidget(QLabel("<b>Rescue Steps (automated)</b>"))
        self._step_tracker = StepTracker()
        self._step_tracker.set_steps([
            FlashStep(id=step_id, label=step_label)
            for step_id, step_label in _RESCUE_STEPS
        ])
        step_layout.addWidget(self._step_tracker)
        step_layout.addStretch()
        step_widget.setMinimumWidth(220)
        splitter.addWidget(step_widget)

        # Right: log panel
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(QLabel("<b>Log</b>"))
        self._log_panel = LogPanel()
        log_layout.addWidget(self._log_panel)
        splitter.addWidget(log_widget)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

        # Progress bar
        self._progress_panel = ProgressPanel()
        layout.addWidget(self._progress_panel)

        # Info note
        info = QLabel("i  All steps run automatically. No user action needed once started.")
        info.setStyleSheet("color: #8b949e; font-style: italic;")
        layout.addWidget(info)

        # Controls row
        ctrl_row = QHBoxLayout()
        self._dry_run_cb = QCheckBox("Dry Run")
        self._dry_run_cb.setToolTip("Log all operations without sending any data to the device")
        ctrl_row.addWidget(self._dry_run_cb)
        ctrl_row.addStretch()
        self._abort_btn = QPushButton("Abort")
        self._abort_btn.setStyleSheet("color: #f85149;")
        self._abort_btn.hide()
        ctrl_row.addWidget(self._abort_btn)
        self._start_btn = QPushButton("▶  Start EDL Rescue")
        self._start_btn.setStyleSheet("background: #238636; color: white; font-weight: bold;")
        self._start_btn.setEnabled(False)
        ctrl_row.addWidget(self._start_btn)
        layout.addLayout(ctrl_row)

    def step_tracker(self) -> StepTracker:
        return self._step_tracker

    def log_panel(self) -> LogPanel:
        return self._log_panel

    def progress_panel(self) -> ProgressPanel:
        return self._progress_panel

    def start_btn(self) -> QPushButton:
        return self._start_btn

    def abort_btn(self) -> QPushButton:
        return self._abort_btn

    def dry_run_cb(self) -> QCheckBox:
        return self._dry_run_cb

    def set_running(self, running: bool) -> None:
        self._start_btn.setEnabled(not running)
        self._dry_run_cb.setEnabled(not running)
        self._abort_btn.setVisible(running)

    def reset_steps(self) -> None:
        self._step_tracker.set_steps([
            FlashStep(id=step_id, label=step_label)
            for step_id, step_label in _RESCUE_STEPS
        ])
        self._log_panel.clear()
        self._progress_panel.reset()


# ── Main RescuePage ────────────────────────────────────────────────────────────

class RescuePage(QWidget):
    """Phase 3 EDL Rescue page — 3 tabs: Setup, Firmware Package, Automated Rescue."""

    def __init__(
        self,
        device_service=None,  # DeviceService | None
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._device_service = device_service
        self._thread: QThread | None = None
        self._worker: EdlWorker | None = None
        self._edl_devices: list[DeviceInfo] = []

        self._setup_ui()
        self._load_settings()

        if device_service is not None:
            device_service.device_list_updated.connect(self._on_devices_updated)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Page header
        header = QWidget()
        header.setStyleSheet("background: #0d1117; border-bottom: 1px solid #21262d;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        title = QLabel("EDL Rescue")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #f85149;")
        header_layout.addWidget(title)
        subtitle = QLabel("Emergency Device Restore — Qualcomm Firehose")
        subtitle.setStyleSheet("color: #8b949e;")
        header_layout.addWidget(subtitle)
        header_layout.addStretch()
        layout.addWidget(header)

        # Tabs
        self._tabs = QTabWidget()
        self._setup_tab = _SetupTab()
        self._package_tab = _PackageTab()
        self._rescue_tab = _RescueTab()

        self._tabs.addTab(self._setup_tab, "Setup")
        self._tabs.addTab(self._package_tab, "Firmware Package")
        self._tabs.addTab(self._rescue_tab, "Automated Rescue")
        layout.addWidget(self._tabs, stretch=1)

        # Connect show-instructions button
        self._setup_tab._show_full_btn.clicked.connect(self._setup_tab.show_entry_dialog)

        # Connect package tab profile changes
        self._package_tab._msm_link_btn.clicked.connect(self._package_tab._open_msm_url)

        # Connect rescue tab start button
        self._rescue_tab.start_btn().clicked.connect(self._start_rescue)
        self._rescue_tab.abort_btn().clicked.connect(self._abort_rescue)

        # Share profile between setup and package tabs
        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        # Sync profile from setup tab to package tab
        profile = self._setup_tab.profile()
        if profile:
            self._package_tab.set_profile(profile)
        # Refresh start button state when switching to rescue tab
        if index == 2:
            self._refresh_start_btn()

    def _refresh_start_btn(self) -> None:
        enabled = (
            self._package_tab.is_valid()
            and len(self._edl_devices) > 0
        )
        self._rescue_tab.start_btn().setEnabled(enabled)

    @Slot(list)
    def _on_devices_updated(self, devices: list[DeviceInfo]) -> None:
        self._edl_devices = [d for d in devices if d.state == DeviceState.EDL]
        self._setup_tab.update_device_status(self._edl_devices)
        self._refresh_start_btn()

        # If EDL device appeared, share its profile
        if self._edl_devices:
            dev = self._edl_devices[0]
            if dev.codename:
                profile = ProfileRegistry.load(dev.codename)
                if profile:
                    self._setup_tab.set_profile(profile)
                    self._package_tab.set_profile(profile)

    def _start_rescue(self) -> None:
        pkg_tab = self._package_tab
        if not pkg_tab.is_valid():
            return

        profile = pkg_tab.profile()
        codename = profile.codename if profile else "unknown"

        # Pick device serial — use first EDL device, or "edl:0" as fallback
        device_serial = self._edl_devices[0].serial if self._edl_devices else "edl:0"

        task = EdlTask(
            device_serial=device_serial,
            profile_codename=codename,
            package_dir=pkg_tab.package_dir(),
            programmer=pkg_tab.programmer(),
            rawprogram_xml=pkg_tab.rawprogram_xml(),
            patch_xml=pkg_tab.patch_xml(),
            dry_run=self._rescue_tab.dry_run_cb().isChecked(),
        )

        self._rescue_tab.reset_steps()
        self._rescue_tab.set_running(True)
        self._tabs.setCurrentIndex(2)

        # Save settings
        self._save_settings()

        # Set up worker thread
        self._thread = QThread(self)
        self._worker = EdlWorker(task, profile or _dummy_profile())
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.start)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        tracker = self._rescue_tab.step_tracker()
        self._worker.step_started.connect(
            lambda sid: tracker.update_step(sid, StepStatus.ACTIVE)
        )
        self._worker.step_completed.connect(
            lambda sid: tracker.update_step(sid, StepStatus.COMPLETED)
        )
        self._worker.step_failed.connect(
            lambda sid, _msg: tracker.update_step(sid, StepStatus.FAILED)
        )
        self._worker.log_line.connect(self._rescue_tab.log_panel().append_line)
        self._worker.progress.connect(
            lambda cur, tot: self._rescue_tab.progress_panel().update_progress(cur, tot)
        )
        self._worker.rescue_complete.connect(self._on_rescue_complete)
        self._worker.error.connect(self._on_rescue_error)
        self._worker.finished.connect(lambda: self._rescue_tab.set_running(False))

        self._thread.start()

    def _abort_rescue(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()
            self._rescue_tab.log_panel().append_line("[Abort requested by user]")
            self._rescue_tab.set_running(False)

    @Slot()
    def _on_rescue_complete(self) -> None:
        self._rescue_tab.log_panel().append_line(
            "\n✓ EDL Rescue complete. Device rebooted to system."
        )

    @Slot(str)
    def _on_rescue_error(self, message: str) -> None:
        self._rescue_tab.log_panel().append_line(f"\n✗ Error: {message}")

    # ── Settings persistence ──────────────────────────────────────────────────

    def _settings_path(self) -> Path:
        return get_app_data_dir() / _SETTINGS_FILE

    def _save_settings(self) -> None:
        settings: dict = {}
        pkg = self._package_tab.package_dir()
        if pkg:
            settings["package_dir"] = str(pkg)
        try:
            path = self._settings_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
        except OSError as exc:
            logger.warning("Could not save rescue settings: %s", exc)

    def _load_settings(self) -> None:
        path = self._settings_path()
        if not path.exists():
            return
        try:
            with path.open(encoding="utf-8") as f:
                settings = json.load(f)
            pkg_dir = settings.get("package_dir")
            if pkg_dir:
                p = Path(pkg_dir)
                if p.exists():
                    self._package_tab.set_package_dir(p)
        except Exception as exc:
            logger.warning("Could not load rescue settings: %s", exc)


def _dummy_profile() -> DeviceProfile:
    """Return a minimal DeviceProfile for workers that need one."""
    from cyberflash.models.profile import BootloaderConfig, FlashConfig
    return DeviceProfile(
        codename="unknown",
        name="Unknown",
        brand="Unknown",
        model="Unknown",
        ab_slots=False,
        bootloader=BootloaderConfig("", False, False),
        flash=FlashConfig("fastboot", []),
        wipe_partitions={},
    )
