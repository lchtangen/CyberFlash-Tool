"""prop_editor_page.py — Live getprop viewer and build.prop editor.

Features:
- Live getprop table with search/filter
- Pull + edit build.prop (root required for push)
- Diff viewer highlighting changed props
- Common presets (USB debug, debuggable, perf mode)
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)

# ── Presets ───────────────────────────────────────────────────────────────────

_PRESETS: list[tuple[str, str, str]] = [
    ("USB Debug",        "persist.sys.usb.config", "mtp,adb"),
    ("Debuggable",       "ro.debuggable",            "1"),
    ("Performance Mode", "persist.sys.cpu_gov",      "performance"),
]


# ── Workers ───────────────────────────────────────────────────────────────────


class _PropsWorker(QObject):
    props_ready = Signal(dict)   # dict[str, str]
    error       = Signal(str)
    finished    = Signal()

    def __init__(self, serial: str, parent=None) -> None:
        super().__init__(parent)
        self._serial = serial

    @Slot()
    def start(self) -> None:
        try:
            output = AdbManager.shell(self._serial, "getprop", timeout=15)
            props: dict[str, str] = {}
            import re
            for line in output.splitlines():
                m = re.match(r"\[(.+?)\]:\s*\[(.*)?\]", line)
                if m:
                    props[m.group(1)] = m.group(2)
            self.props_ready.emit(props)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class _PullPropWorker(QObject):
    content_ready = Signal(str)
    error         = Signal(str)
    finished      = Signal()

    def __init__(self, serial: str, parent=None) -> None:
        super().__init__(parent)
        self._serial = serial

    @Slot()
    def start(self) -> None:
        try:
            content = AdbManager.shell(
                self._serial, "cat /system/build.prop 2>/dev/null", timeout=10
            )
            self.content_ready.emit(content)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class _PushPropWorker(QObject):
    push_done = Signal(bool, str)  # success, message
    finished  = Signal()

    def __init__(self, serial: str, content: str, parent=None) -> None:
        super().__init__(parent)
        self._serial = serial
        self._content = content

    @Slot()
    def start(self) -> None:
        import tempfile
        from pathlib import Path
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".prop", delete=False, mode="w"
            ) as f:
                f.write(self._content)
                tmp_path = f.name

            ok = AdbManager.push(
                self._serial, tmp_path, "/sdcard/cyberflash_build.prop", timeout=15
            )
            if ok:
                result = AdbManager.shell(
                    self._serial,
                    "su -c 'mount -o rw,remount /system && "
                    "cp /sdcard/cyberflash_build.prop /system/build.prop && "
                    "mount -o ro,remount /system' 2>&1",
                    timeout=20,
                )
                success = "permission denied" not in result.lower()
                self.push_done.emit(success, result[:200])
            else:
                self.push_done.emit(False, "adb push failed")
            Path(tmp_path).unlink(missing_ok=True)
        except Exception as exc:
            self.push_done.emit(False, str(exc))
        finally:
            self.finished.emit()


# ── Main page ─────────────────────────────────────────────────────────────────


class PropEditorPage(QWidget):
    """Live getprop viewer and build.prop editor page."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._serial = ""
        self._original_prop_content = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Title
        title = QLabel("System Properties")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_getprop_tab(), "getprop Viewer")
        tabs.addTab(self._build_editor_tab(), "build.prop Editor")
        layout.addWidget(tabs)

    def _build_getprop_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search properties...")
        self._search_box.textChanged.connect(self._filter_props)
        toolbar.addWidget(self._search_box)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self._load_props)
        toolbar.addWidget(refresh_btn)
        vbox.addLayout(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["Property", "Value"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        vbox.addWidget(self._table)

        self._all_props: dict[str, str] = {}
        return w

    def _build_editor_tab(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()
        pull_btn = QPushButton("Pull build.prop")
        pull_btn.setObjectName("secondaryButton")
        pull_btn.clicked.connect(self._pull_prop)
        toolbar.addWidget(pull_btn)

        push_btn = QPushButton("Push (root)")
        push_btn.setObjectName("primaryButton")
        push_btn.clicked.connect(self._push_prop)
        toolbar.addWidget(push_btn)

        diff_btn = QPushButton("Show Diff")
        diff_btn.setObjectName("secondaryButton")
        diff_btn.clicked.connect(self._show_diff)
        toolbar.addWidget(diff_btn)
        toolbar.addStretch()

        # Presets
        for preset_name, _key, _val in _PRESETS:
            btn = QPushButton(preset_name)
            btn.setObjectName("chipButton")
            btn.clicked.connect(lambda _c=False, k=_key, v=_val: self._apply_preset(k, v))
            toolbar.addWidget(btn)

        vbox.addLayout(toolbar)

        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("Pull build.prop to edit...")
        self._editor.setStyleSheet(
            "QPlainTextEdit { font-family: monospace; font-size: 12px;"
            " background: #0d1117; color: #c9d1d9; }"
        )
        vbox.addWidget(self._editor)

        self._editor_status = QLabel("")
        self._editor_status.setStyleSheet("color: #484f58; font-size: 11px;")
        vbox.addWidget(self._editor_status)
        return w

    # ── Slot handlers ─────────────────────────────────────────────────────────

    def set_serial(self, serial: str) -> None:
        self._serial = serial
        self._load_props()

    def _load_props(self) -> None:
        if not self._serial:
            return
        thread = QThread(self)
        worker = _PropsWorker(self._serial)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.props_ready.connect(self._on_props_ready)
        worker.error.connect(lambda e: logger.warning("getprop error: %s", e))
        worker.finished.connect(thread.quit)
        thread.start()

    def _on_props_ready(self, props: dict[str, str]) -> None:
        self._all_props = props
        self._populate_table(props)

    def _populate_table(self, props: dict[str, str]) -> None:
        self._table.setRowCount(len(props))
        for row, (key, val) in enumerate(sorted(props.items())):
            self._table.setItem(row, 0, QTableWidgetItem(key))
            self._table.setItem(row, 1, QTableWidgetItem(val))

    def _filter_props(self, text: str) -> None:
        filtered = {
            k: v for k, v in self._all_props.items()
            if text.lower() in k.lower() or text.lower() in v.lower()
        }
        self._populate_table(filtered)

    def _pull_prop(self) -> None:
        if not self._serial:
            return
        thread = QThread(self)
        worker = _PullPropWorker(self._serial)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.content_ready.connect(self._on_prop_content)
        worker.error.connect(lambda e: self._editor_status.setText(f"Error: {e}"))
        worker.finished.connect(thread.quit)
        thread.start()

    def _on_prop_content(self, content: str) -> None:
        self._original_prop_content = content
        self._editor.setPlainText(content)
        self._editor_status.setText("Loaded build.prop")

    def _push_prop(self) -> None:
        if not self._serial:
            return
        content = self._editor.toPlainText()
        reply = QMessageBox.question(
            self,
            "Push build.prop",
            "This will overwrite /system/build.prop via root access.\nContinue?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        thread = QThread(self)
        worker = _PushPropWorker(self._serial, content)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.push_done.connect(self._on_push_done)
        worker.finished.connect(thread.quit)
        thread.start()

    def _on_push_done(self, success: bool, message: str) -> None:
        if success:
            self._editor_status.setText("Pushed successfully (reboot to apply)")
            self._original_prop_content = self._editor.toPlainText()
        else:
            self._editor_status.setText(f"Push failed: {message[:80]}")

    def _show_diff(self) -> None:
        import difflib
        original = self._original_prop_content.splitlines()
        current = self._editor.toPlainText().splitlines()
        diff = list(difflib.unified_diff(original, current, lineterm=""))
        if not diff:
            QMessageBox.information(self, "No Changes", "No changes to build.prop.")
            return
        diff_text = "\n".join(diff[:200])
        dlg = QMessageBox(self)
        dlg.setWindowTitle("build.prop Diff")
        dlg.setText("Changed lines:")
        dlg.setDetailedText(diff_text)
        dlg.exec()

    def _apply_preset(self, key: str, value: str) -> None:
        import re
        content = self._editor.toPlainText()
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        new_line = f"{key}={value}"
        if pattern.search(content):
            content = pattern.sub(new_line, content)
        else:
            content += f"\n{new_line}"
        self._editor.setPlainText(content)
