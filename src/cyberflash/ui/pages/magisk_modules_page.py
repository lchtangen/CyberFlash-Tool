"""magisk_modules_page.py — Magisk Module Repository Browser.

Fetches the Magisk module repository JSON feed, shows searchable cards,
and allows one-click download + install via RootManager.

Module repo feed: https://raw.githubusercontent.com/Magisk-Modules-Alt-Repo/
                  json/main/modules.json  (community-maintained mirror)

The page also shows installed modules read from the connected device.
"""

from __future__ import annotations

import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.root_manager import RootManager
from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.cyber_card import CyberCard

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_REPO_FEED_URL = (
    "https://raw.githubusercontent.com/Magisk-Modules-Alt-Repo/json/main/modules.json"
)
_FALLBACK_URL  = (
    "https://raw.githubusercontent.com/Magisk-Modules-Repo/submission/main/modules.json"
)

_CATEGORIES = ["All", "Audio", "System", "Fonts", "Xposed", "Root", "Kernel", "Other"]


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class RepoModule:
    """A module entry from the repository feed."""
    mod_id:      str
    name:        str = ""
    version:     str = ""
    version_code: int = 0
    author:      str = ""
    description: str = ""
    stars:       int = 0
    download_url: str = ""
    category:    str = "Other"
    installed_version: str = ""   # non-empty if installed on device


# ── Workers ───────────────────────────────────────────────────────────────────

class _FeedWorker(QObject):
    """Fetch the module repository feed in the background."""

    feed_ready   = Signal(list)   # list[RepoModule]
    status       = Signal(str)
    error        = Signal(str)
    finished     = Signal()

    def __init__(self) -> None:
        super().__init__()

    @Slot()
    def start(self) -> None:
        self.status.emit("Fetching Magisk module repository…")
        try:
            modules = _fetch_repo_modules()
            self.feed_ready.emit(modules)
            self.status.emit(f"Loaded {len(modules)} modules from repository")
        except Exception as exc:
            logger.warning("Feed fetch failed: %s", exc)
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class _InstallWorker(QObject):
    """Download a module ZIP and install it on the device."""

    step_log   = Signal(str)
    done       = Signal(bool, str)   # success, message
    finished   = Signal()
    error      = Signal(str)

    def __init__(self, serial: str, module: RepoModule) -> None:
        super().__init__()
        self._serial  = serial
        self._module  = module

    @Slot()
    def start(self) -> None:
        import tempfile
        from pathlib import Path

        self.step_log.emit(f"Downloading {self._module.name}…")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_zip = Path(tmp) / f"{self._module.mod_id}.zip"
                _download_file(self._module.download_url, tmp_zip)
                self.step_log.emit(f"Installing {self._module.name}…")
                ok = RootManager.install_magisk_module(self._serial, tmp_zip)
                if ok:
                    self.step_log.emit("Module installed successfully (reboot to activate)")
                    self.done.emit(True, "Installed — reboot to activate")
                else:
                    self.done.emit(False, "Installation failed — check Magisk app for details")
        except Exception as exc:
            logger.exception("Module install error")
            self.error.emit(str(exc))
            self.done.emit(False, str(exc))
        finally:
            self.finished.emit()


class _DeviceModulesWorker(QObject):
    """Read installed Magisk modules from the connected device."""

    modules_ready = Signal(list)   # list[dict]
    finished      = Signal()
    error         = Signal(str)

    def __init__(self, serial: str) -> None:
        super().__init__()
        self._serial = serial

    @Slot()
    def start(self) -> None:
        try:
            modules = RootManager.get_magisk_modules(self._serial)
            self.modules_ready.emit(modules)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


# ── Helper functions ─────────────────────────────────────────────────────────

def _fetch_repo_modules() -> list[RepoModule]:
    """Download and parse the Magisk module repository JSON."""
    for url in (_REPO_FEED_URL, _FALLBACK_URL):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CyberFlash/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                import json
                data = json.loads(resp.read().decode("utf-8"))
                return _parse_feed(data)
        except Exception:
            continue
    return []


def _parse_feed(data: dict | list) -> list[RepoModule]:
    """Convert raw JSON to list of RepoModule objects."""
    modules: list[RepoModule] = []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("modules", []) or list(data.values())
        if items and isinstance(items[0], str):
            # It's a dict of id→module
            items = list(data.values())
    else:
        return modules

    for item in items:
        if not isinstance(item, dict):
            continue
        mod_id = item.get("id") or item.get("name", "").lower().replace(" ", "_")
        if not mod_id:
            continue

        # Try multiple field names used across different repo formats
        dl_url = (
            item.get("zip_url")
            or item.get("download")
            or item.get("url", "")
        )

        modules.append(RepoModule(
            mod_id=mod_id,
            name=item.get("name", mod_id),
            version=item.get("version", ""),
            version_code=int(item.get("versionCode", 0) or 0),
            author=item.get("author", ""),
            description=item.get("description", ""),
            stars=int(item.get("stars", 0) or 0),
            download_url=dl_url,
            category=item.get("category", "Other"),
        ))

    return modules


def _download_file(url: str, dest: Path) -> None:
    """Download *url* to *dest* with progress logging."""
    req = urllib.request.Request(url, headers={"User-Agent": "CyberFlash/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        Path(dest).write_bytes(resp.read())


# ── UI widgets ────────────────────────────────────────────────────────────────

class _ModuleCard(CyberCard):
    """Card widget displaying a single module from the repository or device."""

    install_requested = Signal(object)   # RepoModule
    toggle_requested  = Signal(str, bool)  # module_id, enable
    remove_requested  = Signal(str)        # module_id

    def __init__(
        self,
        module: RepoModule,
        installed: bool = False,
        enabled: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._module    = module
        self._installed = installed
        self._enabled   = enabled
        self._build_ui()

    def _build_ui(self) -> None:
        layout = self.card_layout()

        # ── Row 1: name + badges ─────────────────────────────────────────────
        row1 = QHBoxLayout()
        name_lbl = QLabel(self._module.name or self._module.mod_id)
        name_lbl.setObjectName("kvValue")
        row1.addWidget(name_lbl)

        if self._module.version:
            row1.addWidget(CyberBadge(self._module.version, "neutral"))

        if self._installed:
            state = "success" if self._enabled else "warning"
            row1.addWidget(CyberBadge("Installed" if self._enabled else "Disabled", state))

        if self._module.stars > 0:
            row1.addWidget(QLabel(f"★ {self._module.stars}"))

        row1.addStretch()
        layout.addLayout(row1)

        # ── Author ────────────────────────────────────────────────────────────
        if self._module.author:
            author_lbl = QLabel(f"by {self._module.author}")
            author_lbl.setObjectName("kvKey")
            layout.addWidget(author_lbl)

        # ── Description ───────────────────────────────────────────────────────
        if self._module.description:
            desc_lbl = QLabel(self._module.description[:120] + ("…" if len(self._module.description) > 120 else ""))
            desc_lbl.setWordWrap(True)
            desc_lbl.setObjectName("subtitleLabel")
            layout.addWidget(desc_lbl)

        # ── Actions ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        if self._installed:
            toggle_lbl = "Disable" if self._enabled else "Enable"
            toggle_btn = QPushButton(toggle_lbl)
            toggle_btn.setFixedWidth(80)
            toggle_btn.clicked.connect(
                lambda: self.toggle_requested.emit(self._module.mod_id, not self._enabled)
            )
            btn_row.addWidget(toggle_btn)

            rm_btn = QPushButton("Remove")
            rm_btn.setObjectName("dangerButton")
            rm_btn.setFixedWidth(80)
            rm_btn.clicked.connect(lambda: self.remove_requested.emit(self._module.mod_id))
            btn_row.addWidget(rm_btn)
        elif self._module.download_url:
            install_btn = QPushButton("Install")
            install_btn.setObjectName("primaryButton")
            install_btn.setFixedWidth(90)
            install_btn.clicked.connect(lambda: self.install_requested.emit(self._module))
            btn_row.addWidget(install_btn)

        layout.addLayout(btn_row)


# ── Main page ──────────────────────────────────────────────────────────────────

class MagiskModulesPage(QWidget):
    """Magisk Module Repository Browser page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._serial: str = ""
        self._repo_modules: list[RepoModule] = []
        self._installed_modules: list[dict] = []
        self._active_category = "All"
        self._threads: list[QThread] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("Magisk Modules")
        title.setObjectName("titleLabel")
        header.addWidget(title)
        header.addStretch()

        self._status_lbl = QLabel("No device connected")
        self._status_lbl.setObjectName("secondaryLabel")
        header.addWidget(self._status_lbl)

        refresh_btn = QPushButton("Refresh Repository")
        refresh_btn.clicked.connect(self._fetch_repo)
        header.addWidget(refresh_btn)
        root.addLayout(header)

        # ── Search + category bar ─────────────────────────────────────────────
        filter_row = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search modules…")
        self._search_box.setObjectName("searchBox")
        self._search_box.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._search_box, stretch=2)

        for cat in _CATEGORIES:
            btn = QPushButton(cat)
            btn.setCheckable(True)
            btn.setChecked(cat == "All")
            btn.setObjectName("categoryChip")
            btn.clicked.connect(lambda checked, c=cat: self._set_category(c))
            filter_row.addWidget(btn)
            setattr(self, f"_cat_btn_{cat}", btn)

        root.addLayout(filter_row)

        # ── Tabs: Repository / Installed ──────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setObjectName("cyberTabs")

        # Repository tab
        repo_tab = QWidget()
        repo_layout = QVBoxLayout(repo_tab)
        repo_layout.setContentsMargins(0, 8, 0, 0)

        self._repo_scroll = QScrollArea()
        self._repo_scroll.setWidgetResizable(True)
        self._repo_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._repo_cards_widget = QWidget()
        self._repo_cards_layout = QVBoxLayout(self._repo_cards_widget)
        self._repo_cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._repo_cards_layout.setSpacing(8)
        self._repo_scroll.setWidget(self._repo_cards_widget)
        repo_layout.addWidget(self._repo_scroll)

        self._repo_empty = QLabel("Press 'Refresh Repository' to load the module feed")
        self._repo_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._repo_empty.setObjectName("subtitleLabel")
        repo_layout.addWidget(self._repo_empty)

        self._tabs.addTab(repo_tab, "Repository")

        # Installed tab
        installed_tab = QWidget()
        installed_layout = QVBoxLayout(installed_tab)
        installed_layout.setContentsMargins(0, 8, 0, 0)

        inst_actions = QHBoxLayout()
        inst_actions.addStretch()
        scan_btn = QPushButton("Scan Device Modules")
        scan_btn.clicked.connect(self._scan_device_modules)
        inst_actions.addWidget(scan_btn)

        local_btn = QPushButton("Install from File…")
        local_btn.clicked.connect(self._install_from_file)
        inst_actions.addWidget(local_btn)
        installed_layout.addLayout(inst_actions)

        self._inst_scroll = QScrollArea()
        self._inst_scroll.setWidgetResizable(True)
        self._inst_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._inst_cards_widget = QWidget()
        self._inst_cards_layout = QVBoxLayout(self._inst_cards_widget)
        self._inst_cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._inst_cards_layout.setSpacing(8)
        self._inst_scroll.setWidget(self._inst_cards_widget)
        installed_layout.addWidget(self._inst_scroll)

        self._inst_empty = QLabel("Connect a rooted device and press 'Scan Device Modules'")
        self._inst_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._inst_empty.setObjectName("subtitleLabel")
        installed_layout.addWidget(self._inst_empty)

        self._tabs.addTab(installed_tab, "Installed")

        root.addWidget(self._tabs)

    # ── Device connection ─────────────────────────────────────────────────────

    def set_serial(self, serial: str) -> None:
        self._serial = serial
        if serial:
            self._status_lbl.setText(f"Device: {serial}")
            self._scan_device_modules()
        else:
            self._status_lbl.setText("No device connected")

    # ── Repository fetch ──────────────────────────────────────────────────────

    def _fetch_repo(self) -> None:
        self._status_lbl.setText("Loading repository…")
        self._repo_empty.setText("Fetching module feed…")
        self._repo_empty.setVisible(True)

        thread = QThread(self)
        worker = _FeedWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.feed_ready.connect(self._on_feed_ready)
        worker.status.connect(self._status_lbl.setText)
        worker.error.connect(lambda e: self._status_lbl.setText(f"Error: {e}"))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        thread.start()

    @Slot(list)
    def _on_feed_ready(self, modules: list) -> None:
        self._repo_modules = modules
        self._apply_filter(self._search_box.text())

    def _apply_filter(self, text: str) -> None:
        query = text.strip().lower()
        filtered = [
            m for m in self._repo_modules
            if (not query or query in m.name.lower() or query in m.description.lower()
                or query in m.author.lower())
            and (self._active_category == "All" or m.category == self._active_category)
        ]
        self._populate_repo_cards(filtered)

    def _set_category(self, category: str) -> None:
        self._active_category = category
        for cat in _CATEGORIES:
            btn = getattr(self, f"_cat_btn_{cat}", None)
            if btn:
                btn.setChecked(cat == category)
        self._apply_filter(self._search_box.text())

    def _populate_repo_cards(self, modules: list[RepoModule]) -> None:
        # Clear existing cards
        while self._repo_cards_layout.count():
            item = self._repo_cards_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self._repo_empty.setVisible(not modules)
        if not modules:
            self._repo_empty.setText("No modules match the current filter")
            return

        installed_ids = {m.get("id", "") for m in self._installed_modules}
        for mod in modules[:100]:  # cap at 100 cards for performance
            is_inst = mod.mod_id in installed_ids
            card = _ModuleCard(mod, installed=is_inst)
            card.install_requested.connect(self._on_install_requested)
            self._repo_cards_layout.addWidget(card)

    # ── Device modules ────────────────────────────────────────────────────────

    def _scan_device_modules(self) -> None:
        if not self._serial:
            return

        thread = QThread(self)
        worker = _DeviceModulesWorker(self._serial)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.modules_ready.connect(self._on_device_modules_ready)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        thread.start()

    @Slot(list)
    def _on_device_modules_ready(self, modules: list) -> None:
        self._installed_modules = modules
        self._populate_installed_cards(modules)

    def _populate_installed_cards(self, modules: list[dict]) -> None:
        while self._inst_cards_layout.count():
            item = self._inst_cards_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self._inst_empty.setVisible(not modules)
        if not modules:
            self._inst_empty.setText("No Magisk modules found on device")
            return

        for m in modules:
            mod = RepoModule(
                mod_id=m.get("id", ""),
                name=m.get("name", m.get("id", "Unknown")),
                version=m.get("version", ""),
                author=m.get("author", ""),
                description=m.get("description", ""),
            )
            enabled = m.get("enabled", "true") == "true"
            card = _ModuleCard(mod, installed=True, enabled=enabled)
            card.toggle_requested.connect(self._on_toggle_module)
            card.remove_requested.connect(self._on_remove_module)
            self._inst_cards_layout.addWidget(card)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_install_requested(self, module: RepoModule) -> None:
        if not self._serial:
            self._status_lbl.setText("No device connected — cannot install module")
            return

        thread = QThread(self)
        worker = _InstallWorker(self._serial, module)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.step_log.connect(self._status_lbl.setText)
        worker.done.connect(lambda ok, msg: self._status_lbl.setText(msg))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        thread.start()

    @Slot(str, bool)
    def _on_toggle_module(self, module_id: str, enable: bool) -> None:
        if not self._serial:
            return
        RootManager.toggle_magisk_module(self._serial, module_id, enable)
        self._scan_device_modules()

    @Slot(str)
    def _on_remove_module(self, module_id: str) -> None:
        if not self._serial:
            return
        RootManager.uninstall_magisk_module(self._serial, module_id)
        self._scan_device_modules()

    def _install_from_file(self) -> None:
        if not self._serial:
            self._status_lbl.setText("Connect a device first")
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Select Magisk Module ZIP", "", "ZIP Files (*.zip)"
        )
        if not path:
            return

        thread = QThread(self)

        class _LocalInstallWorker(QObject):
            step_log = Signal(str)
            done     = Signal(bool, str)
            finished = Signal()
            error    = Signal(str)

            def __init__(self, serial: str, zip_path: str) -> None:
                super().__init__()
                self._serial   = serial
                self._zip_path = zip_path

            @Slot()
            def start(self) -> None:
                self.step_log.emit(f"Installing {self._zip_path}…")
                ok = RootManager.install_magisk_module(self._serial, self._zip_path)
                self.done.emit(ok, "Installed" if ok else "Failed")
                self.finished.emit()

        worker = _LocalInstallWorker(self._serial, path)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.step_log.connect(self._status_lbl.setText)
        worker.done.connect(lambda ok, msg: self._status_lbl.setText(msg))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._threads.append(thread)
        thread.start()
