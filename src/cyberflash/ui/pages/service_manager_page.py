"""service_manager_page.py — Android System Service Manager.

Lists running Android services from ``dumpsys -l``, lets the user
stop / start services, view service status, and filter by name.

Note: Stopping system services may destabilise the device.  A
      confirmation dialog is shown before any destructive action.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cyberflash.models.device import DeviceInfo
from cyberflash.services.device_service import DeviceService
from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


# ── Worker ────────────────────────────────────────────────────────────────────


class _ServiceListWorker(BaseWorker):
    """Fetches the list of running services via dumpsys."""

    services_ready = Signal(list)  # list[str]

    def __init__(self, serial: str, parent=None) -> None:
        super().__init__(parent)
        self._serial = serial

    @Slot()
    def start(self) -> None:  # type: ignore[override]
        from cyberflash.core.adb_manager import AdbManager

        try:
            output = AdbManager.shell(self._serial, "dumpsys -l", timeout=20)
            services = [
                line.strip()
                for line in output.splitlines()
                if line.strip() and not line.startswith("Currently")
            ]
            self.services_ready.emit(services)
        except Exception as exc:
            logger.exception("ServiceListWorker error")
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


# ── Page ──────────────────────────────────────────────────────────────────────


class ServiceManagerPage(QWidget):
    """View and manage Android system services.

    Args:
        device_service: Shared DeviceService instance.
        parent: Optional Qt parent.
    """

    def __init__(
        self, device_service: DeviceService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._service = device_service
        self._thread: QThread | None = None
        self._all_services: list[str] = []

        self._build_ui()
        self._service.selected_device_changed.connect(self._on_device_changed)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()
        title = QLabel("Service Manager")
        title.setObjectName("pageTitle")
        toolbar.addWidget(title)
        toolbar.addStretch()
        self._device_badge = CyberBadge("No device", "neutral")
        toolbar.addWidget(self._device_badge)
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.clicked.connect(self._load_services)
        toolbar.addWidget(self._btn_refresh)
        root.addLayout(toolbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter services…")
        self._search.textChanged.connect(self._filter_services)
        root.addWidget(self._search)

        # Splitter: list | detail
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Service list
        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self._service_count = QLabel("0 services")
        self._service_count.setObjectName("kvKey")
        list_layout.addWidget(self._service_count)
        self._list = QListWidget()
        self._list.currentTextChanged.connect(self._on_service_selected)
        list_layout.addWidget(self._list)
        splitter.addWidget(list_container)

        # Detail panel
        detail = QWidget()
        det_layout = QVBoxLayout(detail)
        det_layout.setContentsMargins(0, 0, 0, 0)

        self._detail_name = QLabel("Select a service")
        self._detail_name.setObjectName("cardHeader")
        det_layout.addWidget(self._detail_name)

        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        det_layout.addWidget(self._detail_text)

        action_row = QHBoxLayout()
        self._btn_dump = QPushButton("Dump Info")
        self._btn_dump.clicked.connect(self._dump_service)
        self._btn_stop = QPushButton("Stop Service")
        self._btn_stop.clicked.connect(self._stop_service)
        self._btn_stop.setStyleSheet("color: #f85149;")
        for btn in [self._btn_dump, self._btn_stop]:
            btn.setEnabled(False)
            action_row.addWidget(btn)
        action_row.addStretch()
        det_layout.addLayout(action_row)

        splitter.addWidget(detail)
        splitter.setSizes([250, 500])
        root.addWidget(splitter, stretch=1)

    @Slot(object)
    def _on_device_changed(self, device: DeviceInfo | None) -> None:
        if device:
            self._device_badge.update_text(device.model or device.serial)
            self._device_badge.update_state("success")
            self._load_services()
        else:
            self._device_badge.update_text("No device")
            self._device_badge.update_state("neutral")
            self._list.clear()

    def _load_services(self) -> None:
        device = self._service.selected_device
        if not device:
            return

        self._btn_refresh.setEnabled(False)
        self._list.clear()
        self._all_services.clear()

        thread = QThread(self)
        worker = _ServiceListWorker(device.serial)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)
        worker.services_ready.connect(self._on_services_loaded)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._btn_refresh.setEnabled(True))
        thread.start()

    @Slot(list)
    def _on_services_loaded(self, services: list[str]) -> None:
        self._all_services = services
        self._apply_list(services)

    def _apply_list(self, services: list[str]) -> None:
        self._list.clear()
        for svc in services:
            self._list.addItem(QListWidgetItem(svc))
        self._service_count.setText(f"{len(services)} services")

    @Slot(str)
    def _filter_services(self, text: str) -> None:
        filtered = [s for s in self._all_services if text.lower() in s.lower()]
        self._apply_list(filtered)

    @Slot(str)
    def _on_service_selected(self, name: str) -> None:
        if not name:
            return
        self._detail_name.setText(name)
        self._detail_text.clear()
        self._btn_dump.setEnabled(True)
        self._btn_stop.setEnabled(True)

    def _dump_service(self) -> None:
        device = self._service.selected_device
        name = self._detail_name.text()
        if not device or not name or name == "Select a service":
            return

        from cyberflash.core.adb_manager import AdbManager

        try:
            output = AdbManager.shell(device.serial, f"dumpsys {name}", timeout=15)
            self._detail_text.setPlainText(output[:8000])  # cap at 8KB
        except Exception as exc:
            self._detail_text.setPlainText(f"Error: {exc}")

    def _stop_service(self) -> None:
        name = self._detail_name.text()
        if not name or name == "Select a service":
            return

        reply = QMessageBox.warning(
            self,
            "Stop Service",
            f"Stop service '{name}'?\n\nThis may destabilise your device.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        device = self._service.selected_device
        if not device:
            return

        from cyberflash.core.adb_manager import AdbManager

        try:
            AdbManager.shell(device.serial, f"service call {name} 1", timeout=10)
            self._detail_text.appendPlainText(f"\n[Sent stop signal to {name}]")
        except Exception as exc:
            self._detail_text.appendPlainText(f"\n[Error: {exc}]")
