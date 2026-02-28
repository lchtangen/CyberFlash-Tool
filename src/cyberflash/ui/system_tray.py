"""system_tray.py — System tray icon and menu for CyberFlash."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from cyberflash.services.device_service import DeviceService

logger = logging.getLogger(__name__)

_COLOR_CONNECTED    = "#00e676"   # green
_COLOR_DISCONNECTED = "#f44336"   # red


class CyberFlashTrayIcon(QObject):
    """System tray icon providing quick access to CyberFlash actions.

    Reflects device connection state via icon colour and shows toast
    notifications when devices connect or disconnect.
    """

    def __init__(
        self,
        device_service: DeviceService,
        main_window: object,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._main_window = main_window
        self._prev_device_count = 0

        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._make_icon(_COLOR_DISCONNECTED))
        self._tray.setToolTip("CyberFlash — No device connected")
        self._tray.activated.connect(self._on_tray_activated)

        self._build_menu()

        device_service.device_list_updated.connect(self._on_device_list_updated)

    # ── Menu ─────────────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        menu = QMenu()

        show_action = menu.addAction("Show CyberFlash")
        show_action.triggered.connect(self._show_main_window)

        menu.addSeparator()

        flash_action = menu.addAction("Flash Last ROM")
        flash_action.triggered.connect(lambda: self._navigate_to("flash"))

        terminal_action = menu.addAction("Open Terminal")
        terminal_action.triggered.connect(lambda: self._navigate_to("terminal"))

        menu.addSeparator()

        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self._quit_app)

        self._tray.setContextMenu(menu)

    # ── Public interface ─────────────────────────────────────────────────────

    def show(self) -> None:
        """Show the tray icon."""
        self._tray.show()

    def hide(self) -> None:
        """Hide the tray icon."""
        self._tray.hide()

    # ── Icon helpers ─────────────────────────────────────────────────────────

    def _make_icon(self, color: str) -> QIcon:
        px = QPixmap(16, 16)
        px.fill(QColor(color))
        return QIcon(px)

    # ── Slots ────────────────────────────────────────────────────────────────

    @Slot(list)
    def _on_device_list_updated(self, devices: list) -> None:
        count = len(devices)
        if count > 0:
            self._tray.setIcon(self._make_icon(_COLOR_CONNECTED))
            self._tray.setToolTip(
                f"CyberFlash — {count} device(s) connected"
            )
        else:
            self._tray.setIcon(self._make_icon(_COLOR_DISCONNECTED))
            self._tray.setToolTip("CyberFlash — No device connected")

        if count > self._prev_device_count:
            added = count - self._prev_device_count
            self._tray.showMessage(
                "CyberFlash",
                f"{added} device(s) connected.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        elif count < self._prev_device_count:
            removed = self._prev_device_count - count
            self._tray.showMessage(
                "CyberFlash",
                f"{removed} device(s) disconnected.",
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )

        self._prev_device_count = count

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_main_window()

    def _show_main_window(self) -> None:
        mw = self._main_window
        if mw is None:
            return
        try:
            mw.show()
            mw.raise_()
            mw.activateWindow()
        except Exception:
            logger.exception("Failed to show main window from tray")

    def _navigate_to(self, page: str) -> None:
        self._show_main_window()
        mw = self._main_window
        if mw is None:
            return
        navigate = getattr(mw, "navigate_to", None)
        if callable(navigate):
            navigate(page)
        else:
            logger.warning("main_window has no navigate_to method")

    def _quit_app(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()
