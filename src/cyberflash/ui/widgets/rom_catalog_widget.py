"""rom_catalog_widget.py — Live ROM catalog browser widget.

Displays a filterable, sortable table of AI-scored ROM releases for a
selected device.  Streams live results from ``RomDiscoveryService`` as
discovery progresses.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal, Slot
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

from cyberflash.core.rom_catalog import CatalogEntry, RomCatalog
from cyberflash.profiles import ProfileRegistry

logger = logging.getLogger(__name__)

_COLUMNS = ("Distro", "Version", "Android", "Patch", "Score", "Downloaded", "Action")
_COL_DISTRO = 0
_COL_VER = 1
_COL_ANDROID = 2
_COL_PATCH = 3
_COL_SCORE = 4
_COL_DL = 5
_COL_ACTION = 6


def _grade_variant(grade: str) -> str:
    return {"A": "success", "B": "info", "C": "warning", "D": "warning", "F": "error"}.get(
        grade, "neutral"
    )


class RomCatalogWidget(QWidget):
    """Browsable, sortable ROM catalog with one-click download and flash."""

    flash_requested = Signal(object)   # CatalogEntry

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service: object | None = None          # RomDiscoveryService
        self._current_codename: str = ""
        self._row_map: dict[str, int] = {}           # url → table row
        self._devices_scanned = 0
        self._total_found = 0
        self._setup_ui()

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # ── Top controls bar ──────────────────────────────────────────────────
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        ctrl_row.addWidget(QLabel("Device:"))
        self._device_combo = QComboBox()
        self._device_combo.setMinimumWidth(200)
        self._device_combo.currentTextChanged.connect(self._on_device_changed)
        ctrl_row.addWidget(self._device_combo)

        ctrl_row.addStretch()

        self._discover_btn = QPushButton("Discover All")
        self._discover_btn.setObjectName("primaryButton")
        self._discover_btn.clicked.connect(self._on_discover_all)
        ctrl_row.addWidget(self._discover_btn)

        self._abort_btn = QPushButton("Abort")
        self._abort_btn.setObjectName("dangerButton")
        self._abort_btn.setVisible(False)
        self._abort_btn.clicked.connect(self._on_abort)
        ctrl_row.addWidget(self._abort_btn)

        root.addLayout(ctrl_row)

        # ── Status bar ────────────────────────────────────────────────────────
        status_row = QHBoxLayout()
        self._status_label = QLabel("No discovery run yet")
        self._status_label.setObjectName("subtitleLabel")
        status_row.addWidget(self._status_label)
        status_row.addStretch()
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 21)
        self._progress_bar.setFixedWidth(160)
        self._progress_bar.setFixedHeight(12)
        self._progress_bar.setVisible(False)
        status_row.addWidget(self._progress_bar)
        root.addLayout(status_row)

        # ── Table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_DISTRO, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_ACTION, QHeaderView.ResizeMode.Fixed
        )
        self._table.setColumnWidth(_COL_ACTION, 110)
        self._table.setColumnWidth(_COL_SCORE, 70)
        self._table.setColumnWidth(_COL_DL, 80)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        root.addWidget(self._table, stretch=1)

        # ── AI top pick bar ───────────────────────────────────────────────────
        pick_row = QHBoxLayout()
        self._pick_label = QLabel("AI Top Pick: —")
        self._pick_label.setObjectName("subtitleLabel")
        pick_row.addWidget(self._pick_label)
        pick_row.addStretch()
        self._flash_btn = QPushButton("Flash This ROM →")
        self._flash_btn.setObjectName("primaryButton")
        self._flash_btn.setEnabled(False)
        self._flash_btn.clicked.connect(self._on_flash_top_pick)
        pick_row.addWidget(self._flash_btn)
        root.addLayout(pick_row)

        # Populate device combo
        self._populate_device_combo()

    def _populate_device_combo(self) -> None:
        try:
            codenames = ProfileRegistry.list_all()
        except Exception:
            codenames = []
        self._device_combo.blockSignals(True)
        self._device_combo.clear()
        for codename in codenames:
            self._device_combo.addItem(codename)
        self._device_combo.blockSignals(False)
        if codenames:
            self._current_codename = codenames[0]
            self._refresh_table_for_device(codenames[0])

    # ── Service binding ───────────────────────────────────────────────────────

    def set_discovery_service(self, service: object) -> None:
        """Bind a ``RomDiscoveryService`` and connect its signals."""
        self._service = service
        svc = service  # type: ignore[assignment]
        svc.discovery_started.connect(self._on_discovery_started)
        svc.device_discovered.connect(self._on_device_discovered)
        svc.rom_found.connect(self._on_rom_found)
        svc.discovery_complete.connect(self._on_discovery_complete)
        svc.download_started.connect(self._on_download_started)
        svc.download_progress.connect(self._on_download_progress)
        svc.download_complete.connect(self._on_download_complete)
        svc.download_failed.connect(self._on_download_failed)
        svc.download_verified.connect(self._on_download_verified)

        # Load existing catalog data
        self._refresh_table_for_device(self._current_codename)

    def select_device(self, codename: str) -> None:
        """Pre-select a device codename in the combo box."""
        for i in range(self._device_combo.count()):
            if self._device_combo.itemText(i) == codename:
                self._device_combo.setCurrentIndex(i)
                return

    # ── Table management ──────────────────────────────────────────────────────

    def _refresh_table_for_device(self, codename: str) -> None:
        """Populate the table from cached catalog entries."""
        self._table.setRowCount(0)
        self._row_map.clear()
        self._flash_btn.setEnabled(False)
        self._pick_label.setText("AI Top Pick: —")

        if not codename:
            return

        entries = RomCatalog.get_entries(codename)
        for entry in entries:
            self._add_or_update_row(entry)

        self._update_top_pick(codename)

    def _add_or_update_row(self, entry: CatalogEntry) -> None:
        """Insert a new row or refresh an existing one for *entry*."""
        url = entry.url
        if url in self._row_map:
            row = self._row_map[url]
        else:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._row_map[url] = row

        def _item(text: str, sort_val: object | None = None) -> QTableWidgetItem:
            item = QTableWidgetItem(text)
            if sort_val is not None:
                item.setData(Qt.ItemDataRole.UserRole, sort_val)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            return item

        self._table.setItem(row, _COL_DISTRO, _item(entry.distro))
        self._table.setItem(row, _COL_VER, _item(entry.version))
        self._table.setItem(row, _COL_ANDROID, _item(entry.android_ver))
        self._table.setItem(row, _COL_PATCH, _item(entry.security_patch))

        grade = _score_to_grade(entry.ai_score)
        score_text = f"[{grade}] {entry.ai_score:.0f}"
        self._table.setItem(row, _COL_SCORE, _item(score_text, entry.ai_score))

        dl_text = "✓ Ready" if entry.download_path else "—"
        self._table.setItem(row, _COL_DL, _item(dl_text))

        # Action button widget
        self._set_action_cell(row, entry)

    def _set_action_cell(self, row: int, entry: CatalogEntry) -> None:
        if entry.download_path:
            btn = QPushButton("Flash →")
            btn.setObjectName("primaryButton")
            btn.clicked.connect(lambda checked=False, e=entry: self.flash_requested.emit(e))
        else:
            btn = QPushButton("↓ Download")
            btn.setObjectName("secondaryButton")
            btn.clicked.connect(lambda checked=False, e=entry: self._on_download_entry(e))
        self._table.setCellWidget(row, _COL_ACTION, btn)

    def _update_top_pick(self, codename: str) -> None:
        if not self._service:
            return
        try:
            best = self._service.get_recommended(codename)  # type: ignore[union-attr]
        except Exception:
            best = None

        if best:
            grade = _score_to_grade(best.ai_score)
            self._pick_label.setText(
                f"AI Top Pick: {best.distro} {best.version} [{grade}] — "
                f"{best.ai_notes.split(';')[0] if best.ai_notes else ''}"
            )
            self._flash_btn.setEnabled(bool(best.download_path))
        else:
            self._pick_label.setText("AI Top Pick: — (run discovery first)")
            self._flash_btn.setEnabled(False)

    # ── Slot: UI controls ─────────────────────────────────────────────────────

    @Slot(str)
    def _on_device_changed(self, text: str) -> None:
        self._current_codename = text
        self._refresh_table_for_device(text)

    @Slot()
    def _on_discover_all(self) -> None:
        if self._service:
            self._service.discover_all()  # type: ignore[union-attr]

    @Slot()
    def _on_abort(self) -> None:
        if self._service:
            self._service.stop()  # type: ignore[union-attr]

    def _on_download_entry(self, entry: CatalogEntry) -> None:
        if self._service:
            self._service.download_entry(entry)  # type: ignore[union-attr]

    @Slot()
    def _on_flash_top_pick(self) -> None:
        if not self._service:
            return
        best = self._service.get_recommended(self._current_codename)  # type: ignore[union-attr]
        if best:
            self.flash_requested.emit(best)

    # ── Slot: discovery signals ───────────────────────────────────────────────

    @Slot()
    def _on_discovery_started(self) -> None:
        self._devices_scanned = 0
        self._total_found = 0
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._discover_btn.setEnabled(False)
        self._abort_btn.setVisible(True)
        self._status_label.setText("Scanning feeds…")

    @Slot(str, int)
    def _on_device_discovered(self, codename: str, count: int) -> None:
        self._devices_scanned += 1
        self._total_found += count
        self._progress_bar.setValue(self._devices_scanned)
        self._status_label.setText(
            f"{self._devices_scanned}/21 devices scanned — {self._total_found} ROMs found"
        )
        if codename == self._current_codename:
            self._update_top_pick(codename)

    @Slot(str, object)
    def _on_rom_found(self, codename: str, entry: object) -> None:
        if codename != self._current_codename:
            return
        ce: CatalogEntry = entry  # type: ignore[assignment]
        self._add_or_update_row(ce)

    @Slot(int)
    def _on_discovery_complete(self, total: int) -> None:
        self._progress_bar.setVisible(False)
        self._discover_btn.setEnabled(True)
        self._abort_btn.setVisible(False)
        self._status_label.setText(f"Discovery complete — {total} total entries")
        self._update_top_pick(self._current_codename)

    # ── Slot: download signals ────────────────────────────────────────────────

    @Slot(str, str)
    def _on_download_started(self, url: str, dest: str) -> None:
        row = self._row_map.get(url)
        if row is not None:
            lbl = QLabel("Downloading…")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setCellWidget(row, _COL_ACTION, lbl)

    @Slot(str, int, int)
    def _on_download_progress(self, url: str, done: int, total: int) -> None:
        row = self._row_map.get(url)
        if row is None:
            return
        widget = self._table.cellWidget(row, _COL_ACTION)
        if isinstance(widget, QProgressBar):
            if total > 0:
                widget.setValue(int(done * 100 / total))
        else:
            pb = QProgressBar()
            pb.setRange(0, 100 if total > 0 else 0)
            pb.setValue(int(done * 100 / total) if total > 0 else 0)
            self._table.setCellWidget(row, _COL_ACTION, pb)

    @Slot(str, str)
    def _on_download_complete(self, url: str, path: str) -> None:
        row = self._row_map.get(url)
        if row is not None:
            entries = RomCatalog.get_entries(self._current_codename)
            for entry in entries:
                if entry.url == url:
                    dl_item = self._table.item(row, _COL_DL)
                    if dl_item:
                        dl_item.setText("✓ Ready")
                    self._set_action_cell(row, entry)
                    break
        self._update_top_pick(self._current_codename)

    @Slot(str, str)
    def _on_download_failed(self, url: str, msg: str) -> None:
        row = self._row_map.get(url)
        if row is not None:
            btn = QPushButton("Retry ↓")
            btn.setObjectName("secondaryButton")
            entries = RomCatalog.get_entries(self._current_codename)
            for entry in entries:
                if entry.url == url:
                    btn.clicked.connect(
                        lambda checked=False, e=entry: self._on_download_entry(e)
                    )
                    break
            self._table.setCellWidget(row, _COL_ACTION, btn)

    @Slot(str, bool)
    def _on_download_verified(self, url: str, ok: bool) -> None:
        row = self._row_map.get(url)
        if row is None:
            return
        dl_item = self._table.item(row, _COL_DL)
        if dl_item:
            dl_item.setText("✓ Verified" if ok else "⚠ Hash mismatch")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _score_to_grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 45:
        return "D"
    return "F"
