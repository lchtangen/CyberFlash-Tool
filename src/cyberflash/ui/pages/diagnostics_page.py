"""Diagnostics page — system health, environment validation, device logs.

Provides comprehensive diagnostic tools: environment check (ADB/fastboot
binaries, Python, platform info), device health monitoring, and a
device log viewer.
"""

from __future__ import annotations

import logging
import platform
import shutil
import sys

from PySide6.QtCore import QThread, Slot
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.cyber_card import CyberCard
from cyberflash.utils.platform_utils import get_app_data_dir, get_tools_dir
from cyberflash.workers.adb_log_worker import AdbLogWorker
from cyberflash.workers.diagnostics_worker import DiagnosticsWorker
from cyberflash.workers.integrity_worker import AttestationReport, IntegrityResult, IntegrityWorker

logger = logging.getLogger(__name__)


# ── Environment check card ───────────────────────────────────────────────────


class _EnvCheckCard(CyberCard):
    """Shows status of required external tools and environment."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self.card_layout()

        hdr = QHBoxLayout()
        title = QLabel("Environment")
        title.setObjectName("cardHeader")
        hdr.addWidget(title)
        hdr.addStretch()
        self._overall_badge = CyberBadge("Not Checked", "neutral")
        hdr.addWidget(self._overall_badge)
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        layout.addWidget(sep)

        self._grid = QGridLayout()
        self._grid.setSpacing(8)
        self._rows: dict[str, tuple[QLabel, CyberBadge]] = {}

        checks = [
            "ADB Binary",
            "Fastboot Binary",
            "Python Version",
            "PySide6 / Qt",
            "Platform",
            "Tools Directory",
            "Data Directory",
            "USB Permissions",
        ]
        for i, label in enumerate(checks):
            k = QLabel(label)
            k.setObjectName("kvKey")
            v = QLabel("\u2014")
            v.setObjectName("kvValue")
            badge = CyberBadge("\u2022", "neutral")
            self._rows[label] = (v, badge)
            self._grid.addWidget(k, i, 0)
            self._grid.addWidget(v, i, 1)
            self._grid.addWidget(badge, i, 2)
        layout.addLayout(self._grid)

        # Run check button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._check_btn = QPushButton("\u21bb  Run Checks")
        self._check_btn.setObjectName("primaryButton")
        self._check_btn.setFixedWidth(140)
        self._check_btn.clicked.connect(self.run_checks)
        btn_row.addWidget(self._check_btn)
        layout.addLayout(btn_row)

    def _set_row(self, label: str, value: str, variant: str) -> None:
        if label in self._rows:
            val_lbl, badge = self._rows[label]
            val_lbl.setText(value)
            badge.set_variant(variant)

    def run_checks(self) -> None:
        """Perform all environment checks."""
        all_ok = True

        # ADB
        adb = shutil.which("adb") or str(get_tools_dir() / "adb")
        adb_found = shutil.which("adb") is not None or (get_tools_dir() / "adb").exists()
        self._set_row(
            "ADB Binary", adb if adb_found else "Not found", "success" if adb_found else "error"
        )
        all_ok &= adb_found

        # Fastboot
        fb = shutil.which("fastboot") or str(get_tools_dir() / "fastboot")
        fb_found = shutil.which("fastboot") is not None or (get_tools_dir() / "fastboot").exists()
        self._set_row(
            "Fastboot Binary", fb if fb_found else "Not found", "success" if fb_found else "error"
        )
        all_ok &= fb_found

        # Python
        py_ver = sys.version.split()[0]
        py_ok = sys.version_info >= (3, 12)
        self._set_row("Python Version", py_ver, "success" if py_ok else "warning")

        # PySide6
        try:
            from PySide6 import __version__ as pyside_ver

            self._set_row("PySide6 / Qt", pyside_ver, "success")
        except ImportError:
            self._set_row("PySide6 / Qt", "Not installed", "error")
            all_ok = False

        # Platform
        plat = f"{platform.system()} {platform.release()} ({platform.machine()})"
        self._set_row("Platform", plat, "info")

        # Tools directory
        tools = get_tools_dir()
        t_ok = tools.exists()
        self._set_row("Tools Directory", str(tools), "success" if t_ok else "warning")

        # Data directory
        data = get_app_data_dir()
        d_ok = data.exists()
        self._set_row("Data Directory", str(data), "success" if d_ok else "warning")

        # USB permissions (Linux-specific)
        if platform.system() == "Linux":
            import os

            rules_path = "/etc/udev/rules.d"
            has_rules = (
                os.path.isdir(rules_path)
                and any("android" in f.lower() or "51-android" in f for f in os.listdir(rules_path))
                if os.path.isdir(rules_path)
                else False
            )
            self._set_row(
                "USB Permissions",
                "udev rules found" if has_rules else "No Android udev rules",
                "success" if has_rules else "warning",
            )
        else:
            self._set_row("USB Permissions", "N/A (non-Linux)", "info")

        self._overall_badge.set_text_and_variant(
            "All OK" if all_ok else "Issues Found",
            "success" if all_ok else "warning",
        )


# ── Device health card ───────────────────────────────────────────────────────


class _DeviceHealthCard(CyberCard):
    """Device health metrics — battery, temperature, storage."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self.card_layout()

        hdr = QHBoxLayout()
        title = QLabel("Device Health")
        title.setObjectName("cardHeader")
        hdr.addWidget(title)
        hdr.addStretch()
        self._health_badge = CyberBadge("No Device", "neutral")
        hdr.addWidget(self._health_badge)
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        layout.addWidget(sep)

        grid = QGridLayout()
        grid.setSpacing(8)
        self._labels: dict[str, QLabel] = {}
        metrics = [
            ("Battery Level", "battery"),
            ("Battery Health", "bat_health"),
            ("Battery Temperature", "bat_temp"),
            ("CPU Temperature", "cpu_temp"),
            ("Storage Used", "storage"),
            ("RAM Available", "ram"),
            ("Uptime", "uptime"),
            ("USB Mode", "usb_mode"),
        ]
        for i, (text, key) in enumerate(metrics):
            k = QLabel(text)
            k.setObjectName("kvKey")
            v = QLabel("\u2014")
            v.setObjectName("kvValue")
            self._labels[key] = v
            grid.addWidget(k, i, 0)
            grid.addWidget(v, i, 1)
        layout.addLayout(grid)

        # Storage bar
        storage_lbl = QLabel("Storage:")
        storage_lbl.setObjectName("kvKey")
        layout.addWidget(storage_lbl)
        self._storage_bar = QProgressBar()
        self._storage_bar.setValue(0)
        self._storage_bar.setFormat("%p% used")
        layout.addWidget(self._storage_bar)

    def update_health(self, **fields: str) -> None:
        for key, val in fields.items():
            if key in self._labels:
                self._labels[key].setText(val)


# ── Log viewer tab ───────────────────────────────────────────────────────────


class _LogViewerTab(QWidget):
    """Device log (logcat) viewer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._serial: str = ""
        self._log_worker: AdbLogWorker | None = None
        self._log_thread: QThread | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._start_btn = QPushButton("\u25b6 Start Logcat")
        self._start_btn.setObjectName("primaryButton")
        self._start_btn.clicked.connect(self._start_logcat)
        toolbar.addWidget(self._start_btn)

        self._stop_btn = QPushButton("\u25a0 Stop")
        self._stop_btn.setObjectName("dangerButton")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_logcat)
        toolbar.addWidget(self._stop_btn)

        self._clear_btn = QPushButton("Clear")
        toolbar.addWidget(self._clear_btn)

        toolbar.addStretch()

        self._filter_input = QLabel("Filter:")
        toolbar.addWidget(self._filter_input)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Tag or keyword\u2026")
        self._filter.setFixedWidth(200)
        toolbar.addWidget(self._filter)
        layout.addLayout(toolbar)

        self._log_output = QPlainTextEdit()
        self._log_output.setObjectName("terminalOutput")
        self._log_output.setReadOnly(True)
        self._log_output.setMaximumBlockCount(10000)
        layout.addWidget(self._log_output)

        self._clear_btn.clicked.connect(self._log_output.clear)

    def set_serial(self, serial: str) -> None:
        self._serial = serial

    def _start_logcat(self) -> None:
        if not self._serial or (self._log_thread and self._log_thread.isRunning()):
            return
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        tag_filter = self._filter.text().strip()
        self._log_worker = AdbLogWorker(self._serial, tag_filter=tag_filter, clear_on_start=False)
        self._log_thread = QThread(self)
        self._log_worker.moveToThread(self._log_thread)
        self._log_thread.started.connect(self._log_worker.start)
        self._log_worker.log_line.connect(self._on_log_line)
        self._log_worker.finished.connect(self._on_log_finished)
        self._log_worker.finished.connect(self._log_thread.quit)
        self._log_worker.finished.connect(self._log_worker.deleteLater)
        self._log_thread.finished.connect(self._log_thread.deleteLater)
        self._log_thread.start()

    def _stop_logcat(self) -> None:
        if self._log_worker:
            self._log_worker.stop()

    @Slot(str)
    def _on_log_line(self, line: str) -> None:
        self._log_output.appendPlainText(line)

    def _on_log_finished(self) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._log_worker = None
        self._log_thread = None


# ── App logs tab ─────────────────────────────────────────────────────────────


class _AppLogsTab(QWidget):
    """CyberFlash application log viewer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        refresh_btn = QPushButton("\u21bb Refresh")
        refresh_btn.clicked.connect(self._load_logs)
        toolbar.addWidget(refresh_btn)

        open_btn = QPushButton("Open Log File")
        toolbar.addWidget(open_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._log_output = QPlainTextEdit()
        self._log_output.setObjectName("terminalOutput")
        self._log_output.setReadOnly(True)
        layout.addWidget(self._log_output)

        self._load_logs()

    def _load_logs(self) -> None:
        log_dir = get_app_data_dir() / "logs"
        if not log_dir.exists():
            self._log_output.setPlainText("No log files found.")
            return
        log_files = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not log_files:
            self._log_output.setPlainText("No log files found.")
            return
        try:
            content = log_files[0].read_text(encoding="utf-8", errors="replace")
            self._log_output.setPlainText(content[-50000:])  # last 50K chars
        except OSError as exc:
            self._log_output.setPlainText(f"Error reading log: {exc}")


# ── Play Integrity tab ───────────────────────────────────────────────────────


class _IntegrityTab(QWidget):
    """Play Integrity / SafetyNet attestation check UI."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._serial: str = ""
        self._thread: QThread | None = None
        self._worker: IntegrityWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        self._run_btn = QPushButton("Run Integrity Check")
        self._run_btn.setObjectName("primaryButton")
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._run_check)
        toolbar.addWidget(self._run_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Badge rows for each tier
        tiers_layout = QGridLayout()
        tiers_layout.setSpacing(8)

        self._badges: dict[str, CyberBadge] = {}
        for row_idx, tier_name in enumerate(("BASIC", "DEVICE", "STRONG")):
            lbl = QLabel(tier_name)
            lbl.setObjectName("kvKey")
            badge = CyberBadge("—", "neutral")
            self._badges[tier_name] = badge
            tiers_layout.addWidget(lbl, row_idx, 0)
            tiers_layout.addWidget(badge, row_idx, 1)
        layout.addLayout(tiers_layout)

        # Suggestions / raw output
        self._suggestions = QPlainTextEdit()
        self._suggestions.setObjectName("terminalOutput")
        self._suggestions.setReadOnly(True)
        self._suggestions.setMaximumHeight(150)
        layout.addWidget(self._suggestions)
        layout.addStretch()

    def set_serial(self, serial: str) -> None:
        self._serial = serial
        self._run_btn.setEnabled(bool(serial))

    def _run_check(self) -> None:
        if not self._serial:
            return
        self._run_btn.setEnabled(False)
        self._suggestions.setPlainText("Running integrity check…")
        for badge in self._badges.values():
            badge.set_text_and_variant("…", "neutral")

        self._worker = IntegrityWorker(self._serial)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._worker.result_ready.connect(self._on_result)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    @Slot(object)
    def _on_result(self, report: object) -> None:
        self._run_btn.setEnabled(bool(self._serial))
        if not isinstance(report, AttestationReport):
            return

        _variant_map = {
            IntegrityResult.PASS:    "success",
            IntegrityResult.FAIL:    "error",
            IntegrityResult.UNKNOWN: "neutral",
        }
        for tier_result in report.tiers:
            badge = self._badges.get(tier_result.tier.upper())
            if badge:
                variant = _variant_map.get(tier_result.result, "neutral")
                badge.set_text_and_variant(tier_result.result.upper(), variant)

        lines: list[str] = []
        if report.error:
            lines.append(f"Error: {report.error}")
        if report.suggestions:
            lines.append("Suggestions:")
            lines.extend(f"  • {s}" for s in report.suggestions)
        if report.raw_output:
            lines.append("\nRaw output:")
            lines.append(report.raw_output)
        self._suggestions.setPlainText("\n".join(lines))

        self._worker = None
        self._thread = None


# ── Main page ────────────────────────────────────────────────────────────────


class DiagnosticsPage(QWidget):
    """Diagnostics — environment checks, device health, and log viewer."""

    def __init__(
        self,
        device_service=None,
        ai_service=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._device_service = device_service
        self._ai_service = ai_service
        self._logcat_active = False
        self._setup_ui()

        if device_service is not None:
            device_service.device_list_updated.connect(self._on_devices_updated)

        if ai_service is not None:
            ai_service.health_metrics_ready.connect(self._on_health_metrics)
            ai_service.logcat_output.connect(self._on_logcat_line)
            ai_service.logcat_ended.connect(self._on_logcat_stopped)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("Diagnostics")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        subtitle = QLabel("System health, environment checks, and logs")
        subtitle.setObjectName("pageSubtitle")
        header.addWidget(subtitle)
        header.addStretch()
        self._device_badge = CyberBadge("No Device", "neutral")
        header.addWidget(self._device_badge)
        root.addLayout(header)

        # Top section: env checks + device health side by side
        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self._env_card = _EnvCheckCard()
        top_row.addWidget(self._env_card)

        self._health_card = _DeviceHealthCard()
        top_row.addWidget(self._health_card)
        root.addLayout(top_row)

        # Bottom: tabbed logs
        tabs = QTabWidget()
        self._logcat_tab = _LogViewerTab()
        self._app_logs_tab = _AppLogsTab()
        self._integrity_tab = _IntegrityTab()
        tabs.addTab(self._logcat_tab, "Device Logcat")
        tabs.addTab(self._app_logs_tab, "Application Logs")
        tabs.addTab(self._integrity_tab, "Play Integrity")
        root.addWidget(tabs, stretch=1)

        # Auto-run env checks on load
        self._env_card.run_checks()

    @Slot(list)
    def _on_devices_updated(self, devices: list) -> None:
        if devices:
            d = devices[0]
            serial = getattr(d, "serial", "")
            name = getattr(d, "display_name", serial or "Device")
            self._device_badge.set_text_and_variant(f"\u2713 {name}", "success")
            self._health_card._health_badge.set_text_and_variant("Scanning\u2026", "info")
            self._logcat_tab.set_serial(serial)
            self._integrity_tab.set_serial(serial)
            if serial:
                self._run_diagnostics(serial)
        else:
            self._device_badge.set_text_and_variant("No Device", "neutral")
            self._health_card._health_badge.set_text_and_variant("No Device", "neutral")

    def _run_diagnostics(self, serial: str) -> None:
        """Run DiagnosticsWorker and feed results into the health card."""
        worker = DiagnosticsWorker(serial)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.result_ready.connect(self._on_diag_result)
        worker.diagnostics_complete.connect(
            lambda: self._health_card._health_badge.set_text_and_variant("Updated", "success")
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    # Map (category, key) from DiagnosticsWorker → _DeviceHealthCard field name
    _HEALTH_MAP: dict[tuple[str, str], str] = {
        ("Battery", "Level"): "battery",
        ("Battery", "Health"): "bat_health",
        ("Battery", "Temperature (\u00b0C)"): "bat_temp",
        ("Memory", "Available RAM"): "ram",
        ("Storage", "/data usage"): "storage",
    }

    @Slot(str, str, str)
    def _on_diag_result(self, category: str, key: str, value: str) -> None:
        field = self._HEALTH_MAP.get((category, key))
        if field:
            self._health_card.update_health(**{field: value})

    # ── AI service health metrics (secondary data source) ────────────────────

    @Slot(dict)
    def _on_health_metrics(self, metrics: dict) -> None:
        """Update health card with live metrics from AutomationWorker."""
        mapping = {
            "battery": "battery",
            "bat_health": "bat_health",
            "bat_temp": "bat_temp",
            "cpu_temp": "cpu_temp",
            "ram": "ram",
            "uptime": "uptime",
            "usb_mode": "usb_mode",
        }
        update_kwargs: dict[str, str] = {}
        for src_key, dst_key in mapping.items():
            if src_key in metrics:
                update_kwargs[dst_key] = metrics[src_key]
        if update_kwargs:
            self._health_card.update_health(**update_kwargs)

    @Slot(str)
    def _on_logcat_line(self, line: str) -> None:
        """Append an AI-service logcat line to the log viewer."""
        self._logcat_tab._log_output.appendPlainText(line)

    @Slot()
    def _on_logcat_stopped(self) -> None:
        """Handle AI-service logcat stream ending."""
        self._logcat_active = False
