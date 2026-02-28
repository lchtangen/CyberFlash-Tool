"""batch_page.py — Batch Device Operations page."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cyberflash.services.device_service import DeviceService
from cyberflash.workers.batch_worker import BatchTask, BatchWorker

logger = logging.getLogger(__name__)

# Column indices
_COL_SERIAL   = 0
_COL_STATUS   = 1
_COL_PROGRESS = 2
_COL_ACTION   = 3


class BatchPage(QWidget):
    """Batch Device Operations page.

    Allows running Flash ROM / Backup / Root operations on multiple connected
    devices simultaneously, showing per-device status and progress.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._service: DeviceService | None = None
        self._worker: BatchWorker | None = None
        self._serial_to_row: dict[str, int] = {}
        self._setup_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Header
        title = QLabel("Batch Operations")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # Toolbar
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("Operation:"))
        self._op_combo = QComboBox()
        self._op_combo.addItems(["Flash ROM", "Backup", "Root"])
        toolbar.addWidget(self._op_combo)

        toolbar.addStretch()

        add_btn = QPushButton("+ Add Connected Devices")
        add_btn.setObjectName("secondaryButton")
        add_btn.clicked.connect(self._add_all_devices)
        toolbar.addWidget(add_btn)

        self._run_btn = QPushButton("RUN BATCH")
        self._run_btn.setObjectName("primaryButton")
        self._run_btn.clicked.connect(self._run_batch)
        toolbar.addWidget(self._run_btn)

        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Device Serial", "Status", "Progress", "Action"])
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_SERIAL, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_STATUS, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_PROGRESS, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_ACTION, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

        # Footer counts
        self._footer_label = QLabel("0/0 Complete  •  0 Running  •  0 Failed")
        self._footer_label.setObjectName("footerLabel")
        layout.addWidget(self._footer_label)

        # Log output
        self._log_label = QLabel("")
        self._log_label.setWordWrap(True)
        self._log_label.setObjectName("logLabel")
        layout.addWidget(self._log_label)

    # ── Service wiring ───────────────────────────────────────────────────────

    def set_service(self, device_service: DeviceService) -> None:
        """Connect to the DeviceService for device list updates."""
        self._service = device_service
        device_service.device_list_updated.connect(self._on_device_list_updated)

    @Slot(list)
    def _on_device_list_updated(self, devices: list) -> None:
        logger.debug("BatchPage: device list updated (%d devices)", len(devices))

    # ── Table management ─────────────────────────────────────────────────────

    def _add_all_devices(self) -> None:
        if self._service is None:
            self._set_log("No device service connected.")
            return
        devices = self._service.devices
        if not devices:
            self._set_log("No connected devices found.")
            return
        for device in devices:
            serial = device.serial
            if serial not in self._serial_to_row:
                self._add_device_row(serial)
        self._set_log(f"Added {len(devices)} device(s) to batch.")

    def _add_device_row(self, serial: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._serial_to_row[serial] = row

        serial_item = QTableWidgetItem(serial)
        serial_item.setFlags(serial_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(row, _COL_SERIAL, serial_item)

        status_item = QTableWidgetItem("Pending")
        status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(row, _COL_STATUS, status_item)

        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.setTextVisible(True)
        self._table.setCellWidget(row, _COL_PROGRESS, progress)

        abort_btn = QPushButton("Abort")
        abort_btn.setObjectName("dangerButton")
        abort_btn.clicked.connect(lambda _checked=False, s=serial: self._abort_device(s))
        self._table.setCellWidget(row, _COL_ACTION, abort_btn)

    def _set_row_status(self, serial: str, status: str) -> None:
        row = self._serial_to_row.get(serial)
        if row is None:
            return
        item = self._table.item(row, _COL_STATUS)
        if item is not None:
            item.setText(status)

    def _set_row_progress(self, serial: str, value: int, indeterminate: bool = False) -> None:
        row = self._serial_to_row.get(serial)
        if row is None:
            return
        bar = self._table.cellWidget(row, _COL_PROGRESS)
        if isinstance(bar, QProgressBar):
            if indeterminate:
                bar.setRange(0, 0)
            else:
                bar.setRange(0, 100)
                bar.setValue(value)

    # ── Batch execution ──────────────────────────────────────────────────────

    def _run_batch(self) -> None:
        if self._table.rowCount() == 0:
            self._set_log("No devices in batch. Add connected devices first.")
            return

        op_text = self._op_combo.currentText()
        op_map = {
            "Flash ROM": "flash",
            "Backup":    "backup",
            "Root":      "root",
        }
        operation = op_map.get(op_text, "backup")

        tasks: list[BatchTask] = []
        for serial in self._serial_to_row:
            tasks.append(BatchTask(serial=serial, operation=operation))

        self._run_btn.setEnabled(False)
        self._set_log(f"Starting batch {operation} on {len(tasks)} device(s)…")

        from PySide6.QtCore import QThread
        thread = QThread(self)
        self._worker = BatchWorker(tasks)
        self._worker.moveToThread(thread)
        thread.started.connect(self._worker.start)
        self._worker.task_started.connect(self._on_task_started)
        self._worker.task_done.connect(self._on_task_done)
        self._worker.batch_complete.connect(self._on_batch_complete)
        self._worker.error.connect(self._on_batch_error)
        self._worker.finished.connect(thread.quit)
        thread.finished.connect(lambda: self._run_btn.setEnabled(True))
        thread.start()

    @Slot(str)
    def _on_task_started(self, serial: str) -> None:
        self._set_row_status(serial, "Running")
        self._set_row_progress(serial, 0, indeterminate=True)
        self._set_log(f"Started: {serial}")
        self._refresh_footer()

    @Slot(str, bool)
    def _on_task_done(self, serial: str, success: bool) -> None:
        if success:
            self._set_row_status(serial, "Done \u2713")
            self._set_row_progress(serial, 100)
        else:
            self._set_row_status(serial, "Failed \u2717")
            self._set_row_progress(serial, 0)
        self._set_log(f"{'Done' if success else 'Failed'}: {serial}")
        self._refresh_footer()

    @Slot(object)
    def _on_batch_complete(self, result: object) -> None:
        succeeded = getattr(result, "succeeded", 0)
        failed = getattr(result, "failed", 0)
        duration = getattr(result, "duration_s", 0.0)
        self._set_log(
            f"Batch complete — {succeeded} succeeded, {failed} failed "
            f"in {duration:.1f}s"
        )
        self._run_btn.setEnabled(True)
        self._refresh_footer()

    @Slot(str)
    def _on_batch_error(self, message: str) -> None:
        self._set_log(f"Batch error: {message}")
        logger.error("BatchPage error: %s", message)

    def _abort_device(self, serial: str) -> None:
        if self._worker is not None:
            self._worker.abort_device(serial)
            self._set_row_status(serial, "Aborting…")
            self._set_log(f"Abort requested for {serial}")

    # ── Footer ───────────────────────────────────────────────────────────────

    def _refresh_footer(self) -> None:
        total = self._table.rowCount()
        done = 0
        running = 0
        failed = 0
        for row in range(total):
            item = self._table.item(row, _COL_STATUS)
            if item is None:
                continue
            text = item.text()
            if "Done" in text:
                done += 1
            elif "Running" in text or "Aborting" in text:
                running += 1
            elif "Failed" in text:
                failed += 1
        self._footer_label.setText(
            f"{done}/{total} Complete  \u2022  {running} Running  \u2022  {failed} Failed"
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _set_log(self, message: str) -> None:
        self._log_label.setText(message)
        logger.debug("BatchPage: %s", message)
