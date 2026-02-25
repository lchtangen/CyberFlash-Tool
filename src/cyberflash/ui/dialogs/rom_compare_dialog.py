"""rom_compare_dialog.py — Side-by-side ROM release comparison dialog.

Accepts two RomRelease objects and displays a comparison table with
highlighted delta cells (green=improvement, red=regression).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from cyberflash.core.rom_feed import RomRelease

logger = logging.getLogger(__name__)

_GREEN = "#00ff88"
_RED   = "#ff4444"
_GREY  = "#484f58"
_BLUE  = "#00aaff"


def _badge(text: str, color: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"QLabel {{ color: {color}; background: {color}22; border-radius: 4px;"
        f" padding: 2px 8px; font-weight: bold; font-size: 11px; }}"
    )
    return lbl


class RomCompareDialog(QDialog):
    """Compare two ROM releases side-by-side in a table layout."""

    download_left  = lambda self: None   # type: ignore[assignment]  # noqa: E731
    download_right = lambda self: None   # type: ignore[assignment]  # noqa: E731

    # Signals for external connection
    from PySide6.QtCore import Signal as _Signal
    download_requested = _Signal(object)   # RomRelease

    def __init__(
        self,
        release_a: RomRelease,
        release_b: RomRelease,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._a = release_a
        self._b = release_b
        self.setWindowTitle("Compare ROM Releases")
        self.setMinimumWidth(640)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 20, 20, 20)

        # Column headers
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("Field"), 1)
        lbl_a = QLabel(f"{self._a.distro.upper()} — {self._a.version}")
        lbl_a.setStyleSheet(f"color: {_GREEN}; font-weight: bold;")
        hdr.addWidget(lbl_a, 2)
        lbl_b = QLabel(f"{self._b.distro.upper()} — {self._b.version}")
        lbl_b.setStyleSheet(f"color: {_BLUE}; font-weight: bold;")
        hdr.addWidget(lbl_b, 2)
        root.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_GREY}33;")
        root.addWidget(sep)

        # Comparison grid
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 2)

        rows = [
            ("Distro",          str(self._a.distro),        str(self._b.distro),        None),
            ("Android Version", self._a.android_ver,        self._b.android_ver,        "higher"),
            ("Security Patch",  self._a.security_patch,     self._b.security_patch,     "newer"),
            ("Build Date",      self._a.build_date,         self._b.build_date,         "newer"),
            ("Device",          self._a.device,             self._b.device,             None),
            ("Size",
             f"{self._a.size_bytes / 1_048_576:.0f} MB" if self._a.size_bytes else "—",
             f"{self._b.size_bytes / 1_048_576:.0f} MB" if self._b.size_bytes else "—",
             None),
        ]

        for row_idx, (field, val_a, val_b, compare_mode) in enumerate(rows):
            # Field label
            field_lbl = QLabel(field)
            field_lbl.setStyleSheet(f"color: {_GREY}; font-size: 12px;")
            grid.addWidget(field_lbl, row_idx, 0)

            # Value A
            badge_a = _badge(val_a or "—", _GREEN)
            badge_b = _badge(val_b or "—", _BLUE)

            if compare_mode and val_a and val_b and val_a != val_b:
                # Highlight better value
                if val_b > val_a:
                    badge_b = _badge(val_b, _GREEN)
                    badge_a = _badge(val_a, _RED)
                else:
                    badge_a = _badge(val_a, _GREEN)
                    badge_b = _badge(val_b, _RED)

            grid.addWidget(badge_a, row_idx, 1)
            grid.addWidget(badge_b, row_idx, 2)

        root.addLayout(grid)

        # Download buttons
        btn_row = QHBoxLayout()
        dl_a = QPushButton(f"Download {self._a.distro.upper()}")
        dl_a.setObjectName("primaryButton")
        dl_a.clicked.connect(lambda: self.download_requested.emit(self._a))
        btn_row.addWidget(dl_a)

        dl_b = QPushButton(f"Download {self._b.distro.upper()}")
        dl_b.setObjectName("primaryButton")
        dl_b.clicked.connect(lambda: self.download_requested.emit(self._b))
        btn_row.addWidget(dl_b)
        root.addLayout(btn_row)

        # Close button
        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn.rejected.connect(self.reject)
        root.addWidget(close_btn)
