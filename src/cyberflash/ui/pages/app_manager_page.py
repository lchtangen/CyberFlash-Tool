"""app_manager_page.py — Installed app manager page.

Shows installed user/system apps in a table with batch actions:
uninstall, disable, freeze, and backup.  APK install via file picker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class AppInfo:
    package: str
    label: str
    version: str
    size_mb: float
    app_type: str    # "user" | "system"
    disabled: bool


# ── Workers ───────────────────────────────────────────────────────────────────


class _ListWorker(QObject):
    apps_ready = Signal(list)   # list[AppInfo]
    error      = Signal(str)
    finished   = Signal()

    def __init__(self, serial: str, parent=None) -> None:
        super().__init__(parent)
        self._serial = serial

    @Slot()
    def start(self) -> None:
        try:
            apps = self._list_apps()
            self.apps_ready.emit(apps)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    def _list_apps(self) -> list[AppInfo]:
        # List all user apps
        user_out = AdbManager.shell(self._serial, "pm list packages -3 -i", timeout=20)
        sys_out  = AdbManager.shell(self._serial, "pm list packages -s -i", timeout=20)
        apps: list[AppInfo] = []

        for line in user_out.splitlines():
            pkg = self._parse_package_line(line)
            if pkg:
                apps.append(AppInfo(
                    package=pkg, label=pkg.split(".")[-1],
                    version="", size_mb=0.0, app_type="user", disabled=False,
                ))

        for line in sys_out.splitlines():
            pkg = self._parse_package_line(line)
            if pkg:
                apps.append(AppInfo(
                    package=pkg, label=pkg.split(".")[-1],
                    version="", size_mb=0.0, app_type="system", disabled=False,
                ))

        return apps

    @staticmethod
    def _parse_package_line(line: str) -> str:
        if line.startswith("package:"):
            return line.split("package:")[1].split(maxsplit=1)[0].strip()
        return ""


class _ActionWorker(QObject):
    done    = Signal(bool, str)  # success, message
    finished = Signal()

    def __init__(self, serial: str, packages: list[str], action: str, parent=None) -> None:
        super().__init__(parent)
        self._serial = serial
        self._packages = packages
        self._action = action

    @Slot()
    def start(self) -> None:
        results: list[str] = []
        try:
            for pkg in self._packages:
                msg = self._do_action(pkg)
                results.append(msg)
            self.done.emit(True, "\n".join(results))
        except Exception as exc:
            self.done.emit(False, str(exc))
        finally:
            self.finished.emit()

    def _do_action(self, package: str) -> str:
        if self._action == "uninstall":
            rc, _, _ = AdbManager._run(["-s", self._serial, "uninstall", package], timeout=30)
            return f"{'✓' if rc == 0 else '✗'} {package} uninstall"
        if self._action == "disable":
            AdbManager.shell(self._serial, f"pm disable-user {package}", timeout=10)
            return f"Disabled: {package}"
        if self._action == "enable":
            AdbManager.shell(self._serial, f"pm enable {package}", timeout=10)
            return f"Enabled: {package}"
        if self._action == "clear":
            AdbManager.shell(self._serial, f"pm clear {package}", timeout=10)
            return f"Cleared: {package}"
        return f"Unknown action: {self._action}"


# ── Main page ─────────────────────────────────────────────────────────────────


class AppManagerPage(QWidget):
    """Installed app manager with batch operations."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._serial = ""
        self._apps: list[AppInfo] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Title
        title = QLabel("App Manager")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search apps...")
        self._search.textChanged.connect(self._filter_table)
        toolbar.addWidget(self._search, 1)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All", "User", "System"])
        self._filter_combo.currentTextChanged.connect(self._filter_table)
        toolbar.addWidget(self._filter_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self._load_apps)
        toolbar.addWidget(refresh_btn)

        install_btn = QPushButton("Install APK")
        install_btn.setObjectName("primaryButton")
        install_btn.clicked.connect(self._install_apk)
        toolbar.addWidget(install_btn)
        layout.addLayout(toolbar)

        # ── Batch action toolbar ──────────────────────────────────────────────
        batch = QHBoxLayout()
        batch.addWidget(QLabel("Selected:"))

        for label, action in [
            ("Uninstall", "uninstall"),
            ("Disable", "disable"),
            ("Enable", "enable"),
            ("Clear Data", "clear"),
        ]:
            btn = QPushButton(label)
            btn.setObjectName("secondaryButton")
            btn.clicked.connect(lambda _c=False, a=action: self._batch_action(a))
            batch.addWidget(btn)
        batch.addStretch()
        layout.addLayout(batch)

        # ── Table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Package", "Version", "Size", "Type"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

        self._status = QLabel("")
        self._status.setStyleSheet("color: #484f58; font-size: 11px;")
        layout.addWidget(self._status)

    # ── Slot handlers ─────────────────────────────────────────────────────────

    def set_serial(self, serial: str) -> None:
        self._serial = serial
        self._load_apps()

    def _load_apps(self) -> None:
        if not self._serial:
            return
        self._status.setText("Loading...")
        thread = QThread(self)
        worker = _ListWorker(self._serial)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.apps_ready.connect(self._on_apps_ready)
        worker.error.connect(lambda e: self._status.setText(f"Error: {e}"))
        worker.finished.connect(thread.quit)
        thread.start()

    def _on_apps_ready(self, apps: list[AppInfo]) -> None:
        self._apps = apps
        self._populate_table(apps)
        self._status.setText(f"{len(apps)} apps loaded")

    def _populate_table(self, apps: list[AppInfo]) -> None:
        self._table.setRowCount(len(apps))
        for row, app in enumerate(apps):
            self._table.setItem(row, 0, QTableWidgetItem(app.package))
            self._table.setItem(row, 1, QTableWidgetItem(app.version or "—"))
            self._table.setItem(row, 2, QTableWidgetItem(
                f"{app.size_mb:.1f} MB" if app.size_mb else "—"
            ))
            type_item = QTableWidgetItem(app.app_type)
            if app.app_type == "system":
                type_item.setForeground(Qt.GlobalColor.yellow)
            self._table.setItem(row, 3, type_item)

    def _filter_table(self) -> None:
        text = self._search.text().lower()
        ftype = self._filter_combo.currentText().lower()
        filtered = [
            a for a in self._apps
            if (not text or text in a.package.lower())
            and (ftype == "all" or ftype == a.app_type)
        ]
        self._populate_table(filtered)

    def _get_selected_packages(self) -> list[str]:
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        return [self._table.item(r, 0).text() for r in rows if self._table.item(r, 0)]

    def _batch_action(self, action: str) -> None:
        packages = self._get_selected_packages()
        if not packages:
            QMessageBox.warning(self, "No Selection", "Select apps to act on.")
            return
        if action == "uninstall":
            reply = QMessageBox.question(
                self, "Uninstall",
                f"Uninstall {len(packages)} app(s)?",
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._status.setText(f"Running {action} on {len(packages)} app(s)...")
        thread = QThread(self)
        worker = _ActionWorker(self._serial, packages, action)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.done.connect(lambda ok, msg: self._on_action_done(ok, msg, action))
        worker.finished.connect(thread.quit)
        thread.start()

    def _on_action_done(self, success: bool, message: str, action: str) -> None:
        self._status.setText(
            f"{'✓' if success else '✗'} {action} complete"
        )
        self._load_apps()

    def _install_apk(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select APK", "", "APK Files (*.apk)"
        )
        if not path or not self._serial:
            return
        self._status.setText(f"Installing {path.split('/')[-1]}...")
        rc, _, stderr = AdbManager._run(
            ["-s", self._serial, "install", "-r", path], timeout=60
        )
        if rc == 0:
            self._status.setText("APK installed successfully")
            self._load_apps()
        else:
            self._status.setText(f"Install failed: {stderr.strip()[:80]}")
