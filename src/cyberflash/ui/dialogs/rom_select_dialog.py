"""rom_select_dialog.py — Modal ROM picker dialog.

Wraps ``RomCatalogWidget`` in a ``QDialog`` for use by the Flash page and
any other consumer that needs a single-ROM selection pop-up.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.rom_catalog import CatalogEntry
from cyberflash.ui.widgets.rom_catalog_widget import RomCatalogWidget

logger = logging.getLogger(__name__)


class RomSelectDialog(QDialog):
    """Modal dialog for picking a ROM from the AI-discovered catalog.

    Signals:
        rom_selected(CatalogEntry) — emitted when the user confirms a selection
    """

    rom_selected = Signal(object)  # CatalogEntry

    def __init__(
        self,
        service: object,
        device_codename: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Browse ROM Catalog")
        self.setMinimumSize(860, 560)
        self.resize(960, 620)

        self._selected_entry: CatalogEntry | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Catalog widget
        self._catalog = RomCatalogWidget()
        self._catalog.set_discovery_service(service)
        if device_codename:
            self._catalog.select_device(device_codename)
        self._catalog.flash_requested.connect(self._on_entry_activated)
        root.addWidget(self._catalog, stretch=1)

        # Button box
        self._btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("Select ROM")
        self._btn_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self._btn_box.accepted.connect(self._on_accepted)
        self._btn_box.rejected.connect(self.reject)
        root.addWidget(self._btn_box)

        # Enable OK when table row is selected
        self._catalog._table.itemSelectionChanged.connect(self._on_selection_changed)

    # ── Slot handlers ─────────────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        rows = self._catalog._table.selectedItems()
        ok_btn = self._btn_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setEnabled(bool(rows))

    def _on_entry_activated(self, entry: object) -> None:
        """Called when the user clicks 'Flash →' in the catalog table."""
        if isinstance(entry, CatalogEntry):
            self._selected_entry = entry
            self.rom_selected.emit(entry)
            self.accept()

    def _on_accepted(self) -> None:
        """Called when the user clicks 'Select ROM' in the button box."""
        # Find the entry for the selected row
        rows = self._catalog._table.selectionModel().selectedRows()
        if not rows:
            self.reject()
            return

        row = rows[0].row()
        # Reverse-look up the CatalogEntry by URL stored in the row map
        inv_map = {v: k for k, v in self._catalog._row_map.items()}
        url = inv_map.get(row, "")

        from cyberflash.core.rom_catalog import RomCatalog

        for entry in RomCatalog.get_entries(self._catalog._current_codename):
            if entry.url == url:
                self._selected_entry = entry
                self.rom_selected.emit(entry)
                self.accept()
                return

        self.reject()

    # ── Accessor ──────────────────────────────────────────────────────────────

    @property
    def selected_entry(self) -> CatalogEntry | None:
        return self._selected_entry
