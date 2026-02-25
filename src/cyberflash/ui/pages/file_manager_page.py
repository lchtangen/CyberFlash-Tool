"""file_manager_page.py — Dual-pane file manager (local + device).

Left pane: local filesystem tree.
Right pane: device filesystem via ADB (ls -la).
Supports drag-drop push/pull and root-mode browsing.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)

_DEVICE_ROOT = "/"


# ── Workers ───────────────────────────────────────────────────────────────────


class _LsWorker(QObject):
    ls_ready = Signal(str, list)   # path, list[tuple[str, bool, str]]
    error    = Signal(str)
    finished = Signal()

    def __init__(self, serial: str, path: str, use_root: bool, parent=None) -> None:
        super().__init__(parent)
        self._serial = serial
        self._path = path
        self._root = use_root

    @Slot()
    def start(self) -> None:
        try:
            cmd = f"ls -la {self._path} 2>/dev/null"
            if self._root:
                cmd = f"su -c '{cmd}'"
            output = AdbManager.shell(self._serial, cmd, timeout=15)
            entries = self._parse_ls(output)
            self.ls_ready.emit(self._path, entries)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    @staticmethod
    def _parse_ls(output: str) -> list[tuple[str, bool, str]]:
        """Parse ls -la output.  Returns list of (name, is_dir, perms)."""
        entries: list[tuple[str, bool, str]] = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 8:
                continue
            perms = parts[0]
            name = parts[-1]
            if name in (".", ".."):
                continue
            is_dir = perms.startswith("d")
            entries.append((name, is_dir, perms))
        return entries


class _TransferWorker(QObject):
    progress = Signal(int, int)     # current, total
    done     = Signal(bool, str)    # success, message
    finished = Signal()

    def __init__(
        self,
        serial: str,
        local: str,
        remote: str,
        direction: str,  # "push" | "pull"
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._serial = serial
        self._local = local
        self._remote = remote
        self._direction = direction

    @Slot()
    def start(self) -> None:
        try:
            if self._direction == "push":
                ok = AdbManager.push(self._serial, self._local, self._remote)
                self.done.emit(ok, f"Pushed to {self._remote}" if ok else "Push failed")
            else:
                ok = AdbManager.pull(self._serial, self._remote, self._local)
                self.done.emit(ok, f"Pulled to {self._local}" if ok else "Pull failed")
        except Exception as exc:
            self.done.emit(False, str(exc))
        finally:
            self.finished.emit()


# ── Device tree widget ────────────────────────────────────────────────────────


class DeviceTreeWidget(QTreeWidget):
    """Device-side file browser."""

    navigate_requested = Signal(str)  # new path

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHeaderLabels(["Name", "Permissions"])
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setAcceptDrops(True)
        self.itemDoubleClicked.connect(self._on_double_click)

    def _on_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        if item.data(0, Qt.ItemDataRole.UserRole):  # is_dir
            path = item.data(1, Qt.ItemDataRole.UserRole)
            if path:
                self.navigate_requested.emit(path)

    def populate(self, path: str, entries: list[tuple[str, bool, str]]) -> None:
        self.clear()
        parent_item = QTreeWidgetItem([".."])
        parent_item.setData(0, Qt.ItemDataRole.UserRole, True)
        parent_path = str(Path(path).parent)
        parent_item.setData(1, Qt.ItemDataRole.UserRole, parent_path)
        self.addTopLevelItem(parent_item)

        for name, is_dir, perms in sorted(entries, key=lambda e: (not e[1], e[0])):
            item = QTreeWidgetItem([name, perms])
            item.setData(0, Qt.ItemDataRole.UserRole, is_dir)
            item.setData(1, Qt.ItemDataRole.UserRole, f"{path.rstrip('/')}/{name}")
            if is_dir:
                item.setForeground(0, Qt.GlobalColor.cyan)
            self.addTopLevelItem(item)


# ── Main page ─────────────────────────────────────────────────────────────────


class FileManagerPage(QWidget):
    """Dual-pane local ↔ device file manager."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._serial = ""
        self._device_path = _DEVICE_ROOT
        self._use_root = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Title
        title = QLabel("File Manager")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # Root toggle
        toolbar = QHBoxLayout()
        self._root_check = QCheckBox("Root Mode")
        self._root_check.toggled.connect(self._on_root_toggle)
        toolbar.addWidget(self._root_check)
        toolbar.addStretch()

        push_btn = QPushButton("Push Selected →")
        push_btn.setObjectName("primaryButton")
        push_btn.clicked.connect(self._push_selected)
        toolbar.addWidget(push_btn)

        pull_btn = QPushButton("← Pull Selected")
        pull_btn.setObjectName("primaryButton")
        pull_btn.clicked.connect(self._pull_selected)
        toolbar.addWidget(pull_btn)
        layout.addLayout(toolbar)

        # ── Dual pane splitter ────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: local filesystem
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        local_hdr = QHBoxLayout()
        local_hdr.addWidget(QLabel("Local"))
        self._local_path_lbl = QLabel(str(Path.home()))
        self._local_path_lbl.setStyleSheet("color: #484f58; font-size: 11px;")
        local_hdr.addWidget(self._local_path_lbl, 1)
        left_layout.addLayout(local_hdr)

        self._local_model = QFileSystemModel()
        self._local_model.setRootPath(str(Path.home()))
        self._local_tree = QTreeView()
        self._local_tree.setModel(self._local_model)
        self._local_tree.setRootIndex(self._local_model.index(str(Path.home())))
        self._local_tree.setDragEnabled(True)
        left_layout.addWidget(self._local_tree)
        splitter.addWidget(left)

        # Right: device filesystem
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_hdr = QHBoxLayout()
        right_hdr.addWidget(QLabel("Device"))
        self._device_path_edit = QLineEdit(self._device_path)
        self._device_path_edit.returnPressed.connect(self._on_path_entered)
        right_hdr.addWidget(self._device_path_edit, 1)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(24, 24)
        refresh_btn.clicked.connect(self._load_device_dir)
        right_hdr.addWidget(refresh_btn)
        right_layout.addLayout(right_hdr)

        self._device_tree = DeviceTreeWidget()
        self._device_tree.navigate_requested.connect(self._navigate_device)
        right_layout.addWidget(self._device_tree)
        splitter.addWidget(right)

        layout.addWidget(splitter)

        self._status = QLabel("")
        self._status.setStyleSheet("color: #484f58; font-size: 11px;")
        layout.addWidget(self._status)

    # ── Slot handlers ─────────────────────────────────────────────────────────

    def set_serial(self, serial: str) -> None:
        self._serial = serial
        self._load_device_dir()

    def _on_root_toggle(self, checked: bool) -> None:
        self._use_root = checked
        self._load_device_dir()

    def _on_path_entered(self) -> None:
        self._device_path = self._device_path_edit.text()
        self._load_device_dir()

    def _navigate_device(self, path: str) -> None:
        self._device_path = path
        self._device_path_edit.setText(path)
        self._load_device_dir()

    def _load_device_dir(self) -> None:
        if not self._serial:
            return
        thread = QThread(self)
        worker = _LsWorker(self._serial, self._device_path, self._use_root)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.ls_ready.connect(self._on_ls_ready)
        worker.error.connect(lambda e: self._status.setText(f"Error: {e}"))
        worker.finished.connect(thread.quit)
        thread.start()

    def _on_ls_ready(self, path: str, entries: list[tuple[str, bool, str]]) -> None:
        self._device_tree.populate(path, entries)
        self._status.setText(f"{len(entries)} entries in {path}")

    def _push_selected(self) -> None:
        local_idx = self._local_tree.currentIndex()
        if not local_idx.isValid():
            QMessageBox.warning(self, "No Selection", "Select a local file to push.")
            return
        local_path = self._local_model.filePath(local_idx)
        remote_path = f"{self._device_path.rstrip('/')}/{Path(local_path).name}"
        self._transfer(local_path, remote_path, "push")

    def _pull_selected(self) -> None:
        items = self._device_tree.selectedItems()
        if not items:
            QMessageBox.warning(self, "No Selection", "Select a device file to pull.")
            return
        item = items[0]
        remote_path = item.data(1, Qt.ItemDataRole.UserRole) or ""
        if not remote_path:
            return
        local_path = str(Path.home() / "Downloads" / item.text(0))
        self._transfer(local_path, remote_path, "pull")

    def _transfer(self, local: str, remote: str, direction: str) -> None:
        self._status.setText(f"{direction.capitalize()}ing...")
        thread = QThread(self)
        worker = _TransferWorker(self._serial, local, remote, direction)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.done.connect(lambda ok, msg: self._status.setText(msg))
        worker.finished.connect(thread.quit)
        thread.start()
