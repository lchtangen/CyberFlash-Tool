"""network_scanner.py — Wireless ADB device discovery dialog."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)

# Try to import WirelessAdb; fall back to stub behaviour.
try:
    from cyberflash.core.wireless_adb import WirelessAdb as _WirelessAdb
    _WIRELESS_ADB_AVAILABLE = True
except ImportError:
    _WirelessAdb = None  # type: ignore[assignment,misc]
    _WIRELESS_ADB_AVAILABLE = False
    logger.debug("WirelessAdb not available — network scanner uses stub")

# Column indices
_COL_IP_PORT   = 0
_COL_MODEL     = 1
_COL_API_LEVEL = 2
_COL_STATUS    = 3


# ── Scan worker ───────────────────────────────────────────────────────────────


class _ScanWorker(QObject):
    """Probes a subnet for ADB-over-TCP devices on ports 5555-5585.

    Signals:
        device_found(ip_port, model, api_level) — emitted for each responsive host
        finished()                               — emitted when scan is done
    """

    device_found = Signal(str, str, str)   # ip_port, model, api_level
    finished     = Signal()

    def __init__(self, subnet: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._subnet = subnet
        self._aborted = False

    def abort(self) -> None:
        self._aborted = True

    @Slot()
    def start(self) -> None:
        try:
            self._scan()
        except Exception:
            logger.exception("_ScanWorker error")
        finally:
            self.finished.emit()

    def _scan(self) -> None:
        if _WIRELESS_ADB_AVAILABLE and _WirelessAdb is not None:
            self._scan_with_wireless_adb()
        else:
            self._scan_stub()

    def _scan_with_wireless_adb(self) -> None:
        assert _WirelessAdb is not None
        for port in range(5555, 5586):
            if self._aborted:
                break
            ip_port = f"{self._subnet}.1:{port}"
            result = _WirelessAdb.probe(ip_port)
            if result:
                model     = getattr(result, "model",     "Unknown")
                api_level = getattr(result, "api_level", "—")
                self.device_found.emit(ip_port, str(model), str(api_level))

    def _scan_stub(self) -> None:
        """Stub scan: tries common ADB ports using AdbManager if available."""
        try:
            from cyberflash.core.adb_manager import AdbManager
            for last_octet in range(1, 255):
                if self._aborted:
                    break
                ip = f"{self._subnet}.{last_octet}"
                for port in (5555, 5556):
                    ip_port = f"{ip}:{port}"
                    try:
                        out = AdbManager.shell(ip_port, "getprop ro.product.model", timeout=2)
                        if out.strip():
                            api_out = AdbManager.shell(
                                ip_port, "getprop ro.build.version.sdk", timeout=2
                            )
                            self.device_found.emit(
                                ip_port,
                                out.strip() or "Unknown",
                                api_out.strip() or "—",
                            )
                    except Exception:
                        pass
        except ImportError:
            logger.debug("AdbManager not available for stub scan")


# ── Dialog ────────────────────────────────────────────────────────────────────


class NetworkScannerDialog(QDialog):
    """Wireless ADB device scanner dialog.

    Discovers ADB-over-TCP devices on the local network and allows
    connecting to them with a single click.
    """

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self.setWindowTitle("Wireless ADB Scanner")
        self.setMinimumSize(640, 420)
        self._thread: QThread | None = None
        self._worker: _ScanWorker | None = None
        self._setup_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("Wireless ADB Scanner")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # Scan controls row
        scan_row = QHBoxLayout()
        scan_row.addWidget(QLabel("Subnet:"))
        self._subnet_edit = QLineEdit("192.168.1")
        self._subnet_edit.setPlaceholderText("e.g. 192.168.1")
        self._subnet_edit.setFixedWidth(150)
        scan_row.addWidget(self._subnet_edit)

        self._scan_btn = QPushButton("Scan")
        self._scan_btn.setObjectName("primaryButton")
        self._scan_btn.clicked.connect(self._start_scan)
        scan_row.addWidget(self._scan_btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setVisible(False)
        scan_row.addWidget(self._progress, 1)
        scan_row.addStretch()
        layout.addLayout(scan_row)

        # Results table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["IP:Port", "Model", "API Level", "Status"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table)

        # Connect button + dialog buttons
        btn_row = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setObjectName("primaryButton")
        self._connect_btn.setEnabled(False)
        self._connect_btn.clicked.connect(self._connect_selected)
        btn_row.addWidget(self._connect_btn)
        btn_row.addStretch()
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        btn_row.addWidget(box)
        layout.addLayout(btn_row)

    # ── Scan ─────────────────────────────────────────────────────────────────

    def _start_scan(self) -> None:
        subnet = self._subnet_edit.text().strip()
        if not subnet:
            return

        self._table.setRowCount(0)
        self._scan_btn.setEnabled(False)
        self._progress.setVisible(True)

        self._thread = QThread(self)
        self._worker = _ScanWorker(subnet)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._worker.device_found.connect(self._on_device_found)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    @Slot(str, str, str)
    def _on_device_found(self, ip_port: str, model: str, api_level: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        for col, text in enumerate((ip_port, model, api_level, "Available")):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, col, item)

    @Slot()
    def _on_scan_finished(self) -> None:
        self._scan_btn.setEnabled(True)
        self._progress.setVisible(False)
        if self._table.rowCount() == 0:
            logger.info("Network scan complete — no ADB devices found")

    # ── Connect ──────────────────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        self._connect_btn.setEnabled(bool(self._table.selectedItems()))

    def _connect_selected(self) -> None:
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        if not rows:
            return
        row = next(iter(rows))
        ip_item = self._table.item(row, _COL_IP_PORT)
        if ip_item is None:
            return
        ip_port = ip_item.text()
        self._do_connect(ip_port, row)

    def _do_connect(self, ip_port: str, row: int) -> None:
        status_item = self._table.item(row, _COL_STATUS)

        if _WIRELESS_ADB_AVAILABLE and _WirelessAdb is not None:
            try:
                _WirelessAdb.connect(ip_port)
                if status_item:
                    status_item.setText("Connected")
                logger.info("Connected to wireless ADB device: %s", ip_port)
            except Exception as exc:
                if status_item:
                    status_item.setText(f"Failed: {exc}")
                logger.warning("Failed to connect to %s: %s", ip_port, exc)
        else:
            try:
                from cyberflash.core.adb_manager import AdbManager
                AdbManager._run(["connect", ip_port], timeout=10)
                if status_item:
                    status_item.setText("Connected")
                logger.info("ADB connect: %s", ip_port)
            except Exception as exc:
                if status_item:
                    status_item.setText(f"Error: {exc}")
                logger.warning("ADB connect error for %s: %s", ip_port, exc)
