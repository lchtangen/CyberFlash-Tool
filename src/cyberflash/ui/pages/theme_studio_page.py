"""theme_studio_page.py — Live Theme Studio.

Lets users browse the three built-in palettes (cyber_dark, cyber_light,
cyber_green), preview them instantly, customise accent colours, and
export the resulting QSS.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cyberflash.ui.themes.theme_engine import THEMES
from cyberflash.ui.themes.variables import ThemePalette
from cyberflash.ui.widgets.cyber_badge import CyberBadge

logger = logging.getLogger(__name__)


# ── Colour swatch button ──────────────────────────────────────────────────────


class _SwatchButton(QPushButton):
    """A colour picker button that shows its current hex value."""

    def __init__(self, label: str, initial: str, parent=None) -> None:
        super().__init__(parent)
        self._token = label
        self._color = initial
        self._update_display()
        self.clicked.connect(self._pick_color)

    def _update_display(self) -> None:
        self.setText(f"{self._token}\n{self._color}")
        text_color = "#000" if QColor(self._color).lightness() > 128 else "#fff"
        self.setStyleSheet(
            f"QPushButton {{ background: {self._color}; color: {text_color}; "
            f"border-radius: 6px; padding: 6px 12px; font-size: 10px; "
            f"min-width: 110px; }}"
        )

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._color), self, f"Pick {self._token}")
        if color.isValid():
            self._color = color.name()
            self._update_display()

    def color(self) -> str:
        return self._color

    def token(self) -> str:
        return self._token


# ── Page ──────────────────────────────────────────────────────────────────────


class ThemeStudioPage(QWidget):
    """Live Theme Studio — preview and customise palettes in real time.

    Args:
        theme_engine: The shared ThemeEngine instance.
        parent: Optional Qt parent.
    """

    def __init__(
        self, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._swatches: list[_SwatchButton] = []
        self._build_ui()
        self._load_palette(self._palette_combo.currentText())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()
        title = QLabel("Theme Studio")
        title.setObjectName("pageTitle")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self._palette_combo = QComboBox()
        for name in sorted(THEMES.keys()):
            self._palette_combo.addItem(name)
        self._palette_combo.currentTextChanged.connect(self._load_palette)
        toolbar.addWidget(QLabel("Base palette:"))
        toolbar.addWidget(self._palette_combo)

        self._btn_apply = QPushButton("Apply Theme")
        self._btn_apply.clicked.connect(self._apply_theme)
        self._btn_export = QPushButton("Export QSS…")
        self._btn_export.clicked.connect(self._export_qss)
        toolbar.addWidget(self._btn_apply)
        toolbar.addWidget(self._btn_export)
        root.addLayout(toolbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # Swatches area
        swatches_scroll = QScrollArea()
        swatches_scroll.setWidgetResizable(True)
        swatches_scroll.setMaximumHeight(200)
        self._swatches_container = QWidget()
        self._swatches_layout = QHBoxLayout(self._swatches_container)
        self._swatches_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        swatches_scroll.setWidget(self._swatches_container)
        root.addWidget(swatches_scroll)

        # QSS preview
        root.addWidget(QLabel("Generated QSS preview:"))
        self._qss_preview = QTextEdit()
        self._qss_preview.setReadOnly(True)
        self._qss_preview.setMaximumHeight(300)
        root.addWidget(self._qss_preview)

        # Live preview widget examples
        root.addWidget(QLabel("Live preview:"))
        preview_row = QHBoxLayout()
        self._preview_btn_ok = QPushButton("Primary Button")
        self._preview_btn_ok.setObjectName("primaryButton")
        self._preview_badge = CyberBadge("Active", "success")
        self._preview_label = QLabel("Sample text label")
        for w in [self._preview_btn_ok, self._preview_badge, self._preview_label]:
            preview_row.addWidget(w)
        preview_row.addStretch()
        root.addLayout(preview_row)

        root.addStretch()

    @Slot(str)
    def _load_palette(self, name: str) -> None:
        palette: ThemePalette | None = THEMES.get(name)
        if palette is None:
            return

        # Remove old swatches
        while self._swatches_layout.count():
            item = self._swatches_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._swatches.clear()

        # Build swatches for each token in the palette
        import dataclasses

        for f in dataclasses.fields(palette):
            val = getattr(palette, f.name)
            if isinstance(val, str) and val.startswith("#"):
                swatch = _SwatchButton(f.name, val)
                swatch.clicked.connect(self._update_qss_preview)
                self._swatches.append(swatch)
                self._swatches_layout.addWidget(swatch)

        self._update_qss_preview()

    def _build_custom_stylesheet(self, name: str) -> str:
        """Build QSS string from base template with custom swatch overrides."""
        from pathlib import Path as _Path

        themes_dir = _Path(__file__).parent.parent / "themes"
        qss_path = themes_dir / f"{name}.qss"
        if not qss_path.exists():
            qss_path = themes_dir / "cyber_dark.qss"
        try:
            template = qss_path.read_text(encoding="utf-8")
        except OSError:
            return ""
        import dataclasses
        palette = THEMES.get(name)
        if palette is None:
            return ""
        result = template
        # Apply base palette tokens first
        for f in dataclasses.fields(palette):
            result = result.replace(f"{{{f.name}}}", getattr(palette, f.name))
        # Then apply custom swatch overrides
        for swatch in self._swatches:
            result = result.replace(f"{{{swatch.token()}}}", swatch.color())
        return result

    def _update_qss_preview(self) -> None:
        """Regenerate QSS preview from current swatch values."""
        name = self._palette_combo.currentText()
        qss = self._build_custom_stylesheet(name)
        self._qss_preview.setPlainText(qss[:4000] if qss else "")

    def _apply_theme(self) -> None:
        name = self._palette_combo.currentText()
        qss = self._build_custom_stylesheet(name)
        if qss:
            app = QApplication.instance()
            if app:
                app.setStyleSheet(qss)
                logger.info("Applied customised theme: %s", name)

    def _export_qss(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export QSS", "custom_theme.qss", "QSS Files (*.qss);;All Files (*)"
        )
        if not path:
            return
        name = self._palette_combo.currentText()
        qss = self._build_custom_stylesheet(name)
        try:
            Path(path).write_text(qss or "", encoding="utf-8")
            QMessageBox.information(self, "Exported", f"QSS saved to:\n{path}")
        except OSError as exc:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{exc}")
