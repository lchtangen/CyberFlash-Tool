"""device_compare_dialog.py — Side-by-side device comparison dialog."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)

# Amber highlight for differing cells
_DIFF_COLOR = "#fff3cd"

# Rows: (display label, attribute name on DeviceInfo)
_METRICS: list[tuple[str, str]] = [
    ("Model",              "model"),
    ("Android Version",    "android_version"),
    ("SDK Level",          "sdk_level"),
    ("CPU / Chipset",      "chipset"),
    ("Bootloader State",   "bootloader_state"),
    ("Root Status",        "root_status"),
    ("Battery %",          "battery_percent"),
    ("Storage",            "storage"),
]


class DeviceCompareDialog(QDialog):
    """Side-by-side device comparison dialog.

    Displays a table comparing two DeviceInfo objects across a set of
    hardware and software metrics. Cells that differ are highlighted amber.
    """

    def __init__(
        self,
        device_a: object,
        device_b: object,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self.setWindowTitle("Device Comparison")
        self.setMinimumSize(600, 400)
        self._device_a = device_a
        self._device_b = device_b
        self._setup_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("Device Comparison")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # Column headers use device serial/model if available
        label_a = self._device_label(self._device_a, "Device A")
        label_b = self._device_label(self._device_b, "Device B")

        self._table = QTableWidget(len(_METRICS), 3)
        self._table.setHorizontalHeaderLabels(["Metric", label_a, label_b])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self._populate_table()
        layout.addWidget(self._table)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    # ── Table population ─────────────────────────────────────────────────────

    def _populate_table(self) -> None:
        for row, (label, attr) in enumerate(_METRICS):
            val_a = self._get_attr(self._device_a, attr)
            val_b = self._get_attr(self._device_b, attr)

            metric_item = QTableWidgetItem(label)
            metric_item.setFlags(metric_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, metric_item)

            item_a = QTableWidgetItem(str(val_a))
            item_a.setFlags(item_a.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_a.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, item_a)

            item_b = QTableWidgetItem(str(val_b))
            item_b.setFlags(item_b.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_b.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 2, item_b)

            if str(val_a) != str(val_b):
                from PySide6.QtGui import QColor
                highlight = QColor(_DIFF_COLOR)
                item_a.setBackground(highlight)
                item_b.setBackground(highlight)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_attr(device: object, attr: str) -> object:
        try:
            value = getattr(device, attr, None)
            return value if value is not None else "—"
        except AttributeError:
            return "—"

    @staticmethod
    def _device_label(device: object, fallback: str) -> str:
        serial = getattr(device, "serial", None)
        model  = getattr(device, "model",  None)
        if model and serial:
            return f"{model} ({serial})"
        if serial:
            return serial
        if model:
            return model
        return fallback
