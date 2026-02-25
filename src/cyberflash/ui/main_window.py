from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Slot
from PySide6.QtGui import QBrush, QCloseEvent, QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cyberflash.services.ai_service import AIService
from cyberflash.services.device_service import DeviceService
from cyberflash.services.rom_link_service import RomLinkService

from .pages.backup_page import BackupPage
from .pages.dashboard_page import DashboardPage
from .pages.device_page import DevicePage
from .pages.diagnostics_page import DiagnosticsPage
from .pages.flash_page import FlashPage
from .pages.nethunter_page import NetHunterPage
from .pages.partition_page import PartitionPage
from .pages.rescue_page import RescuePage
from .pages.rom_library_page import RomLibraryPage
from .pages.root_page import RootPage
from .pages.settings_page import SettingsPage
from .pages.terminal_page import TerminalPage
from .panels.ai_assistant_panel import AIAssistantPanel
from .sidebar import Sidebar
from .status_bar import AppStatusBar
from .themes.theme_engine import THEMES, ThemeEngine
from .title_bar import TitleBar
from .widgets.resize_grip import ResizableFramelessMixin


class _CyberCentralWidget(QWidget):
    """Central widget that paints a theme-aware background.

    Dark/green themes get the cyberpunk circuit-board overlay.
    Light theme gets a clean plain background using the theme's BACKGROUND color.
    Registers with ThemeEngine so it repaints automatically on theme change.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        ThemeEngine.register_on_change(self.update)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        palette = THEMES.get(ThemeEngine.current_theme, THEMES["cyber_dark"])
        bg = QColor(palette.BACKGROUND)
        accent = QColor(palette.PRIMARY)

        # 1. Base fill — always uses current theme background
        p.fillRect(self.rect(), bg)

        # 2-6. Cyberpunk overlay — only for dark themes (skip for cyber_light)
        if ThemeEngine.current_theme == "cyber_light":
            return

        # 2. Dot grid — 40 px spacing, very faint accent nodes
        p.setPen(Qt.PenStyle.NoPen)
        dot_color = QColor(accent)
        dot_color.setAlpha(14)
        p.setBrush(dot_color)
        for x in range(0, w, 40):
            for y in range(0, h, 40):
                p.drawEllipse(x - 1, y - 1, 3, 3)

        # 3. Horizontal trace lines every 80 px
        line_color = QColor(accent)
        line_color.setAlpha(6)
        p.setPen(QPen(line_color, 1))
        for y in range(0, h, 80):
            p.drawLine(0, y, w, y)

        # 4. Vertical trace lines every 80 px
        for x in range(0, w, 80):
            p.drawLine(x, 0, x, h)

        # 5. Corner bracket ornaments
        bracket_color = QColor(accent)
        bracket_color.setAlpha(50)
        p.setPen(QPen(bracket_color, 2))
        arm = 28
        for cx, cy, sx, sy in [(0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1), (w, h, -1, -1)]:
            p.drawLine(cx, cy, cx + sx * arm, cy)
            p.drawLine(cx, cy, cx, cy + sy * arm)

        # 6. Diagonal scan gradient top-left → bottom-right, very subtle
        grad = QLinearGradient(0, 0, w * 0.6, h * 0.6)
        glow = QColor(accent)
        glow.setAlpha(7)
        grad.setColorAt(0.0, glow)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), QBrush(grad))


class FramelessMainWindow(ResizableFramelessMixin, QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self._drag_pos: QPoint | None = None

        # Create and start the device service owned by the main window
        self._device_service = DeviceService(self)

        # Create and start the ROM link monitoring service
        self._rom_link_service = RomLinkService(self)

        # Create the AI assistant service
        self._ai_service = AIService(self)

        self._setup_ui()
        self._setup_pages()
        self._connect_device_service()
        self._connect_ai_service()
        self.init_resize_grips()

        self._device_service.start()
        self._rom_link_service.start()
        self._ai_service.start()

    def _setup_ui(self) -> None:
        central = _CyberCentralWidget(self)
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Title bar
        self._title_bar = TitleBar(self)
        self._title_bar.minimize_clicked.connect(self.showMinimized)
        self._title_bar.maximize_clicked.connect(self._toggle_maximize)
        self._title_bar.close_clicked.connect(self.close)
        self._title_bar.ai_toggle_clicked.connect(self.toggle_ai_panel)
        root_layout.addWidget(self._title_bar)

        # Content area: sidebar + stacked pages
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._sidebar = Sidebar(self)
        self._sidebar.navigation_changed.connect(self.navigate_to)
        content_layout.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        content_layout.addWidget(self._stack)

        # AI assistant panel (right side, initially collapsed)
        self._ai_panel = AIAssistantPanel(self)
        content_layout.addWidget(self._ai_panel)

        root_layout.addWidget(content_widget)

        # Status bar
        self._status_bar = AppStatusBar(self)
        root_layout.addWidget(self._status_bar)

    def _setup_pages(self) -> None:
        svc = self._device_service
        ai = self._ai_service
        rom_page = RomLibraryPage()
        rom_page.set_service(self._rom_link_service)
        self._pages: dict[str, QWidget] = {
            "dashboard": DashboardPage(svc),
            "device": DevicePage(svc, ai_service=ai),
            "flash": FlashPage(svc, ai_service=ai),
            "rom_library": rom_page,
            "backup": BackupPage(svc, ai_service=ai),
            "root": RootPage(svc, ai_service=ai),
            "nethunter": NetHunterPage(svc),
            "partition": PartitionPage(svc, ai_service=ai),
            "terminal": TerminalPage(svc),
            "diagnostics": DiagnosticsPage(svc, ai_service=ai),
            "rescue": RescuePage(svc),
            "settings": SettingsPage(),
        }
        for page in self._pages.values():
            self._stack.addWidget(page)

    @Slot(str)
    def navigate_to(self, page_id: str) -> None:
        if page_id in self._pages:
            self._stack.setCurrentWidget(self._pages[page_id])
            # Notify AI of page context change
            self._ai_service.set_current_page(page_id)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ── Frameless window dragging ────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._title_bar.geometry().contains(
            event.pos()
        ):
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _connect_device_service(self) -> None:
        svc = self._device_service
        # Keep title bar device selector in sync
        svc.device_list_updated.connect(self._on_devices_updated)
        svc.selected_device_changed.connect(self._on_selected_device_changed)
        # When user picks a device in the title bar, notify the service
        self._title_bar.device_combo().currentTextChanged.connect(self._on_combo_device_selected)

    def _connect_ai_service(self) -> None:
        """Wire up the AI panel and feed device context to the AI service."""
        self._ai_panel.set_service(self._ai_service)
        # Forward device selection to the AI service
        self._device_service.selected_device_changed.connect(self._ai_service.set_device)

    @Slot(list)
    def _on_devices_updated(self, devices) -> None:
        combo = self._title_bar.device_combo()
        combo.blockSignals(True)
        combo.clear()
        if devices:
            for d in devices:
                label = f"{d.display_name} ({d.serial})" if d.display_name != d.serial else d.serial
                combo.addItem(label, userData=d.serial)
        else:
            combo.addItem("No device connected")
        combo.blockSignals(False)

        # Status bar feedback
        if devices:
            n = len(devices)
            self._status_bar.set_status(f"{n} device{'s' if n != 1 else ''} connected", "success")
        else:
            self._status_bar.set_status("No device connected", "ready")

    @Slot(object)
    def _on_selected_device_changed(self, info) -> None:
        if info is None:
            return
        combo = self._title_bar.device_combo()
        combo.blockSignals(True)
        for i in range(combo.count()):
            if combo.itemData(i) == info.serial:
                combo.setCurrentIndex(i)
                break
        combo.blockSignals(False)
        self._status_bar.set_status(f"Selected: {info.display_name}", "info")

    @Slot(str)
    def _on_combo_device_selected(self, text: str) -> None:
        combo = self._title_bar.device_combo()
        serial = combo.currentData()
        if serial:
            self._device_service.select_device(serial)

    # ── Public accessors ─────────────────────────────────────────────────────

    def title_bar(self) -> TitleBar:
        return self._title_bar

    def sidebar(self) -> Sidebar:
        return self._sidebar

    def status_bar(self) -> AppStatusBar:
        return self._status_bar

    def device_service(self) -> DeviceService:
        return self._device_service

    def rom_link_service(self) -> RomLinkService:
        return self._rom_link_service

    def ai_service(self) -> AIService:
        return self._ai_service

    def ai_panel(self) -> AIAssistantPanel:
        return self._ai_panel

    def toggle_ai_panel(self) -> None:
        """Toggle the AI assistant panel open/closed."""
        self._ai_panel.toggle()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._ai_service.stop()
        self._rom_link_service.stop()
        self._device_service.stop()
        super().closeEvent(event)
