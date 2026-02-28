from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from .themes.icons import get_icon

_EXPANDED_WIDTH  = 210
_COLLAPSED_WIDTH = 68
_ICON_SIZE       = 32  # Premium 3D icons — rendered at 32x32


@dataclass
class NavItem:
    nav_id: str
    label: str
    icon_name: str


_NAV_ITEMS: list[NavItem] = [
    NavItem("dashboard",        "Dashboard",        "dashboard"),
    NavItem("device",           "Device",           "device"),
    NavItem("fleet",            "Fleet Dashboard",  "fleet"),
    NavItem("flash",            "Flash",            "flash"),
    NavItem("rom_library",      "ROM Library",      "rom_library"),
    NavItem("backup",           "Backup",           "backup"),
    NavItem("root",             "Root",             "root"),
    NavItem("magisk_modules",   "Magisk Modules",   "magisk"),
    NavItem("nethunter",        "NetHunter",        "nethunter"),
    NavItem("app_manager",      "App Manager",      "app_manager"),
    NavItem("file_manager",     "File Manager",     "file_manager"),
    NavItem("prop_editor",      "Prop Editor",      "prop_editor"),
    NavItem("privacy",          "Privacy Scan",     "privacy"),
    NavItem("batch",            "Batch Ops",        "batch"),
    NavItem("workflow",         "Workflow",         "workflow"),
    NavItem("scripting",        "Scripting IDE",    "scripting"),
    NavItem("partition",        "Partition",        "partition"),
    NavItem("terminal",         "Terminal",         "terminal"),
    NavItem("service_manager",  "Services",         "service_manager"),
    NavItem("diagnostics",      "Diagnostics",      "diagnostics"),
    NavItem("rescue",           "Rescue",           "rescue"),
    NavItem("theme_studio",     "Theme Studio",     "theme_studio"),
    NavItem("settings",         "Settings",         "settings"),
]


class SidebarItem(QPushButton):
    def __init__(self, nav_item: NavItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.nav_id = nav_item.nav_id
        self.setObjectName("sidebarItem")
        self.setCheckable(False)
        self.setFixedHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._icon_name = nav_item.icon_name
        self._label_text = nav_item.label
        self._is_active = False
        self._collapsed = False

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(14, 0, 14, 0)
        self._layout.setSpacing(12)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        self._icon_label.setScaledContents(True)
        self._update_icon("#8b949e")
        self._layout.addWidget(self._icon_label)

        self._text_label = QLabel(nav_item.label)
        self._text_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._layout.addWidget(self._text_label)

    def _update_icon(self, color: str) -> None:
        icon = get_icon(self._icon_name, color, size=_ICON_SIZE)
        self._icon_label.setPixmap(icon.pixmap(_ICON_SIZE, _ICON_SIZE))

    def set_active(self, active: bool) -> None:
        self._is_active = active
        color = "#00d4ff" if active else "#8b949e"
        self._update_icon(color)
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self._text_label.setVisible(not collapsed)
        if collapsed:
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)
            self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self._layout.setContentsMargins(14, 0, 14, 0)
            self._layout.setSpacing(12)


class Sidebar(QWidget):
    navigation_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(_EXPANDED_WIDTH)
        self._collapsed = False
        self._items: list[SidebarItem] = []
        self._active_id: str = "dashboard"
        self._setup_ui()
        self._navigate_to("dashboard")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(3)

        for nav_item in _NAV_ITEMS:
            item = SidebarItem(nav_item, self)
            item.clicked.connect(
                lambda checked=False, nid=nav_item.nav_id: self._on_item_clicked(nid)
            )
            self._items.append(item)
            layout.addWidget(item)

        layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self._toggle_btn = QPushButton("\u25c0")
        self._toggle_btn.setObjectName("sidebarToggle")
        self._toggle_btn.setFixedHeight(36)
        self._toggle_btn.clicked.connect(self._toggle_collapse)
        layout.addWidget(self._toggle_btn)

    def _on_item_clicked(self, nav_id: str) -> None:
        self._navigate_to(nav_id)
        self.navigation_changed.emit(nav_id)

    def _navigate_to(self, nav_id: str) -> None:
        self._active_id = nav_id
        for item in self._items:
            item.set_active(item.nav_id == nav_id)

    def _toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        target_width = _COLLAPSED_WIDTH if self._collapsed else _EXPANDED_WIDTH
        self._toggle_btn.setText("\u25b6" if self._collapsed else "\u25c0")

        self._animation = QPropertyAnimation(self, b"minimumWidth")
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._animation.setStartValue(self.width())
        self._animation.setEndValue(target_width)
        self._animation.start()

        self._max_animation = QPropertyAnimation(self, b"maximumWidth")
        self._max_animation.setDuration(200)
        self._max_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._max_animation.setStartValue(self.width())
        self._max_animation.setEndValue(target_width)
        self._max_animation.start()

        for item in self._items:
            item.set_collapsed(self._collapsed)

    def active_id(self) -> str:
        return self._active_id
