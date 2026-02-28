"""Settings page — application configuration.

Provides a full settings UI for theme selection, device polling,
flash safety, logging, download preferences, and UI layout.
Reads from and writes to :class:`ConfigService`.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.rom_catalog import RomCatalog
from cyberflash.services.config_service import ConfigService
from cyberflash.ui.themes.theme_engine import ThemeEngine
from cyberflash.ui.widgets.cyber_card import CyberCard

logger = logging.getLogger(__name__)


# ── Theme card widget ─────────────────────────────────────────────────────────

_THEME_META: dict[str, dict[str, str]] = {
    "cyber_dark": {
        "label": "Cyber Dark",
        "desc": "Dark space · neon cyan",
        "bg": "#0d1117",
        "surface": "#161b22",
        "accent": "#00d4ff",
        "text": "#e6edf3",
        "success": "#3fb950",
    },
    "cyber_light": {
        "label": "Cyber Light",
        "desc": "Clean light · blue accents",
        "bg": "#f6f8fa",
        "surface": "#ffffff",
        "accent": "#0969da",
        "text": "#1f2328",
        "success": "#1a7f37",
    },
    "cyber_green": {
        "label": "Cyber Green",
        "desc": "Terminal · matrix green",
        "bg": "#0a0f0a",
        "surface": "#0d1a0d",
        "accent": "#00ff41",
        "text": "#ccffcc",
        "success": "#00ff41",
    },
}


class _ThemeCard(QFrame):
    """Clickable theme preview card with colour swatches."""

    clicked = Signal(str)  # emits theme name

    def __init__(self, theme_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = theme_name
        self._selected = False
        meta = _THEME_META[theme_name]

        self.setFixedSize(160, 120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Mini preview strip (5 colour dots)
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(5)
        swatch_row.setContentsMargins(0, 0, 0, 0)
        for color in (meta["bg"], meta["surface"], meta["accent"], meta["text"], meta["success"]):
            dot = QLabel()
            dot.setFixedSize(18, 18)
            dot.setStyleSheet(
                f"background:{color}; border-radius:9px; border:1px solid rgba(255,255,255,0.15);"
            )
            swatch_row.addWidget(dot)
        swatch_row.addStretch()
        layout.addLayout(swatch_row)

        layout.addStretch()

        # Theme name
        name_lbl = QLabel(meta["label"])
        name_lbl.setStyleSheet(
            f"color:{meta['text']}; font-size:13px; font-weight:bold; background:transparent;"
        )
        layout.addWidget(name_lbl)

        # Description
        desc_lbl = QLabel(meta["desc"])
        desc_lbl.setStyleSheet(
            f"color:{meta['accent']}; font-size:10px; background:transparent;"
        )
        layout.addWidget(desc_lbl)

        self._bg_color = meta["bg"]
        self._accent_color = meta["accent"]
        self._refresh_style()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._refresh_style()

    def _refresh_style(self) -> None:
        border_color = self._accent_color if self._selected else "rgba(255,255,255,0.12)"
        border_width = "2px" if self._selected else "1px"
        self.setStyleSheet(
            f"QFrame {{"
            f"  background:{self._bg_color};"
            f"  border:{border_width} solid {border_color};"
            f"  border-radius:8px;"
            f"}}"
        )

    def mousePressEvent(self, event: object) -> None:
        self.clicked.emit(self._name)


# ── Section builders ─────────────────────────────────────────────────────────


class _AppearanceSection(CyberCard):
    """Theme picker with live instant apply and colour swatch previews."""

    def __init__(self, config: ConfigService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._pending_theme: str = config.get_str("theme") or "cyber_dark"
        layout = self.card_layout()

        # Header row
        header_row = QHBoxLayout()
        title = QLabel("Appearance")
        title.setObjectName("cardHeader")
        header_row.addWidget(title)
        header_row.addStretch()

        # Status label (shows confirmation after apply)
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("subtitleLabel")
        header_row.addWidget(self._status_lbl)
        layout.addLayout(header_row)

        # ── Theme cards ──────────────────────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        cards_row.setContentsMargins(0, 8, 0, 8)

        self._cards: dict[str, _ThemeCard] = {}
        for theme_name in ("cyber_dark", "cyber_light", "cyber_green"):
            card = _ThemeCard(theme_name, self)
            card.set_selected(theme_name == self._pending_theme)
            card.clicked.connect(self._on_card_clicked)
            cards_row.addWidget(card)
            self._cards[theme_name] = card

        cards_row.addStretch()
        layout.addLayout(cards_row)

        # ── Apply button + sidebar toggle ────────────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        self._apply_btn = QPushButton("Apply Theme")
        self._apply_btn.setObjectName("primaryButton")
        self._apply_btn.setFixedWidth(130)
        self._apply_btn.clicked.connect(self._apply_theme)
        bottom_row.addWidget(self._apply_btn)

        bottom_row.addSpacing(20)

        self._sidebar_cb = QCheckBox("Start sidebar collapsed")
        self._sidebar_cb.setChecked(config.get_bool("ui/sidebar_collapsed"))
        self._sidebar_cb.toggled.connect(lambda v: config.set("ui/sidebar_collapsed", v))
        bottom_row.addWidget(self._sidebar_cb)

        bottom_row.addStretch()
        layout.addLayout(bottom_row)

    def _on_card_clicked(self, theme_name: str) -> None:
        """Select card and apply the theme instantly across the whole app."""
        self._pending_theme = theme_name
        for name, card in self._cards.items():
            card.set_selected(name == theme_name)
        self._apply_theme()

    def _apply_theme(self) -> None:
        """Apply selected theme to the entire application immediately."""
        ThemeEngine.apply_theme(self._pending_theme)
        self._config.set("theme", self._pending_theme)
        meta = _THEME_META.get(self._pending_theme, {})
        label = meta.get("label", self._pending_theme)
        self._status_lbl.setText(f"✓ {label} applied")
        logger.info("Theme applied: %s", self._pending_theme)


class _DeviceSection(CyberCard):
    """Device detection and polling settings."""

    def __init__(self, config: ConfigService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        layout = self.card_layout()

        title = QLabel("Device Detection")
        title.setObjectName("cardHeader")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(10)

        # Poll interval
        grid.addWidget(QLabel("Poll interval (ms):"), 0, 0)
        poll_row = QHBoxLayout()
        self._poll_slider = QSlider(Qt.Orientation.Horizontal)
        self._poll_slider.setRange(500, 10000)
        self._poll_slider.setSingleStep(500)
        self._poll_slider.setValue(config.get_int("device/poll_interval_ms"))
        poll_row.addWidget(self._poll_slider)

        self._poll_label = QLabel(f"{self._poll_slider.value()} ms")
        self._poll_label.setObjectName("kvValue")
        self._poll_label.setFixedWidth(70)
        poll_row.addWidget(self._poll_label)
        grid.addLayout(poll_row, 0, 1)

        self._poll_slider.valueChanged.connect(self._on_poll_changed)

        # Auto-select
        grid.addWidget(QLabel("Auto-select:"), 1, 0)
        self._auto_select_cb = QCheckBox("Automatically select the only connected device")
        self._auto_select_cb.setChecked(config.get_bool("device/auto_select_single"))
        self._auto_select_cb.toggled.connect(lambda v: config.set("device/auto_select_single", v))
        grid.addWidget(self._auto_select_cb, 1, 1)

        layout.addLayout(grid)

    def _on_poll_changed(self, val: int) -> None:
        self._poll_label.setText(f"{val} ms")
        self._config.set("device/poll_interval_ms", val)


class _FlashSection(CyberCard):
    """Flash safety and verification settings."""

    def __init__(self, config: ConfigService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        layout = self.card_layout()

        title = QLabel("Flash & Safety")
        title.setObjectName("cardHeader")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(10)

        # Dry run default
        grid.addWidget(QLabel("Dry run:"), 0, 0)
        self._dry_run_cb = QCheckBox("Enable dry-run by default")
        self._dry_run_cb.setChecked(config.get_bool("flash/dry_run_default"))
        self._dry_run_cb.toggled.connect(lambda v: config.set("flash/dry_run_default", v))
        grid.addWidget(self._dry_run_cb, 0, 1)

        # Confirm dangerous ops
        grid.addWidget(QLabel("Confirmation:"), 1, 0)
        self._confirm_cb = QCheckBox("Ask confirmation before dangerous operations")
        self._confirm_cb.setChecked(config.get_bool("flash/confirm_dangerous_ops"))
        self._confirm_cb.toggled.connect(lambda v: config.set("flash/confirm_dangerous_ops", v))
        grid.addWidget(self._confirm_cb, 1, 1)

        # Auto hash verify
        grid.addWidget(QLabel("Verification:"), 2, 0)
        self._hash_cb = QCheckBox("Verify file hashes after download")
        self._hash_cb.setChecked(config.get_bool("flash/auto_verify_hash"))
        self._hash_cb.toggled.connect(lambda v: config.set("flash/auto_verify_hash", v))
        grid.addWidget(self._hash_cb, 2, 1)

        layout.addLayout(grid)


class _LoggingSection(CyberCard):
    """Logging configuration."""

    def __init__(self, config: ConfigService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        layout = self.card_layout()

        title = QLabel("Logging")
        title.setObjectName("cardHeader")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(10)

        # File logging
        grid.addWidget(QLabel("File logging:"), 0, 0)
        self._file_cb = QCheckBox("Write logs to file")
        self._file_cb.setChecked(config.get_bool("logging/file_enabled"))
        self._file_cb.toggled.connect(lambda v: config.set("logging/file_enabled", v))
        grid.addWidget(self._file_cb, 0, 1)

        # Max file size
        grid.addWidget(QLabel("Max log size:"), 1, 0)
        size_row = QHBoxLayout()
        self._size_spin = QSpinBox()
        self._size_spin.setRange(1, 100)
        self._size_spin.setSuffix(" MB")
        self._size_spin.setValue(config.get_int("logging/max_file_size_mb"))
        self._size_spin.valueChanged.connect(lambda v: config.set("logging/max_file_size_mb", v))
        size_row.addWidget(self._size_spin)
        size_row.addStretch()
        grid.addLayout(size_row, 1, 1)

        # Backup count
        grid.addWidget(QLabel("Backup count:"), 2, 0)
        count_row = QHBoxLayout()
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 20)
        self._count_spin.setValue(config.get_int("logging/backup_count"))
        self._count_spin.valueChanged.connect(lambda v: config.set("logging/backup_count", v))
        count_row.addWidget(self._count_spin)
        count_row.addStretch()
        grid.addLayout(count_row, 2, 1)

        layout.addLayout(grid)


class _DownloadsSection(CyberCard):
    """Download directory and parallel download settings."""

    def __init__(self, config: ConfigService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        layout = self.card_layout()

        title = QLabel("Downloads")
        title.setObjectName("cardHeader")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(10)

        # Download directory
        grid.addWidget(QLabel("Directory:"), 0, 0)
        dir_row = QHBoxLayout()
        self._dir_input = QLineEdit(config.get_str("downloads/directory"))
        self._dir_input.setPlaceholderText("Default (platform downloads folder)")
        self._dir_input.setReadOnly(True)
        dir_row.addWidget(self._dir_input)
        browse_btn = QPushButton("Browse\u2026")
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse_btn)
        grid.addLayout(dir_row, 0, 1)

        # Parallel downloads
        grid.addWidget(QLabel("Parallel downloads:"), 1, 0)
        par_row = QHBoxLayout()
        self._parallel_spin = QSpinBox()
        self._parallel_spin.setRange(1, 8)
        self._parallel_spin.setValue(config.get_int("downloads/parallel_max"))
        self._parallel_spin.valueChanged.connect(lambda v: config.set("downloads/parallel_max", v))
        par_row.addWidget(self._parallel_spin)
        par_row.addStretch()
        grid.addLayout(par_row, 1, 1)

        layout.addLayout(grid)

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Download Directory",
        )
        if path:
            self._dir_input.setText(path)
            self._config.set("downloads/directory", path)


# ── AI Assistant section ──────────────────────────────────────────────────────


class _AISection(CyberCard):
    """AI assistant status card — Gemini is pre-configured, no setup required."""

    def __init__(self, config: ConfigService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        layout = self.card_layout()

        # Header
        hdr = QHBoxLayout()
        title = QLabel("AI Assistant  —  Gemini")
        title.setObjectName("cardHeader")
        hdr.addWidget(title)
        hdr.addStretch()
        badge = QLabel("✓ Active")
        badge.setObjectName("subtitleLabel")
        hdr.addWidget(badge)
        layout.addLayout(hdr)

        # Status info
        info = QLabel(
            "CyberFlash AI is powered by <b>Google Gemini 2.5 Flash</b> — "
            "fully configured and ready to use. No API key setup required."
        )
        info.setObjectName("subtitleLabel")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Model selector — users can still switch model
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        self._model_combo = QComboBox()

        from cyberflash.core.gemini_client import AVAILABLE_MODELS

        model_labels = {
            "gemini-2.5-flash": "Gemini 2.5 Flash  (default — fast & smart)",
            "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite  (fastest)",
            "gemini-2.5-pro": "Gemini 2.5 Pro  (most capable)",
        }
        saved_model = config.get_str("ai/gemini_model") or "gemini-2.5-flash"
        for model in AVAILABLE_MODELS:
            self._model_combo.addItem(model_labels.get(model, model), userData=model)
        for i in range(self._model_combo.count()):
            if self._model_combo.itemData(i) == saved_model:
                self._model_combo.setCurrentIndex(i)
                break

        model_row.addWidget(self._model_combo)

        save_btn = QPushButton("Apply")
        save_btn.setObjectName("primaryButton")
        save_btn.setFixedWidth(70)
        save_btn.clicked.connect(self._save_model)
        model_row.addWidget(save_btn)
        model_row.addStretch()
        layout.addLayout(model_row)

        self._saved_lbl = QLabel("")
        self._saved_lbl.setObjectName("subtitleLabel")
        layout.addWidget(self._saved_lbl)

    def _save_model(self) -> None:
        model = self._model_combo.currentData() or "gemini-2.5-flash"
        self._config.set("ai/gemini_model", model)
        self._saved_lbl.setText(f"✓ Model set to {model}")
        logger.info("Gemini model updated to %s", model)


# ── ROM Discovery section ─────────────────────────────────────────────────────


class _DiscoverySection(CyberCard):
    """ROM auto-discovery configuration and controls."""

    discover_all_requested = Signal()

    def __init__(self, config: ConfigService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        layout = self.card_layout()

        # Header row
        hdr = QHBoxLayout()
        title = QLabel("ROM Discovery")
        title.setObjectName("cardHeader")
        hdr.addWidget(title)
        hdr.addStretch()
        self._discover_now_btn = QPushButton("Discover All Now")
        self._discover_now_btn.setObjectName("primaryButton")
        self._discover_now_btn.setFixedWidth(150)
        self._discover_now_btn.clicked.connect(self.discover_all_requested)
        hdr.addWidget(self._discover_now_btn)
        layout.addLayout(hdr)

        grid = QGridLayout()
        grid.setSpacing(10)

        # Auto-discover on startup
        grid.addWidget(QLabel("Auto-discover:"), 0, 0)
        self._auto_cb = QCheckBox("Scan ROM feeds on startup")
        self._auto_cb.setChecked(config.get_bool("discovery/auto_start"))
        self._auto_cb.toggled.connect(lambda v: config.set("discovery/auto_start", v))
        grid.addWidget(self._auto_cb, 0, 1)

        # Download directory
        grid.addWidget(QLabel("Download dir:"), 1, 0)
        dl_row = QHBoxLayout()
        self._dl_dir_input = QLineEdit(config.get_str("discovery/download_dir"))
        self._dl_dir_input.setPlaceholderText("Default (~/CyberFlash/Downloads)")
        self._dl_dir_input.setReadOnly(True)
        dl_row.addWidget(self._dl_dir_input)
        dl_browse_btn = QPushButton("Browse\u2026")
        dl_browse_btn.clicked.connect(self._browse_dl_dir)
        dl_row.addWidget(dl_browse_btn)
        grid.addLayout(dl_row, 1, 1)

        # Max age days
        grid.addWidget(QLabel("Max build age:"), 2, 0)
        age_row = QHBoxLayout()
        self._age_spin = QSpinBox()
        self._age_spin.setRange(7, 730)
        self._age_spin.setSuffix(" days")
        self._age_spin.setValue(config.get_int("discovery/max_age_days") or 90)
        self._age_spin.valueChanged.connect(lambda v: config.set("discovery/max_age_days", v))
        age_row.addWidget(self._age_spin)
        age_row.addStretch()
        grid.addLayout(age_row, 2, 1)

        # Last discovery timestamp
        grid.addWidget(QLabel("Last scan:"), 3, 0)
        try:
            RomCatalog.load()
            last = RomCatalog.last_scan_time()
            last_text = last[:19].replace("T", " ") if last else "Never"
        except Exception:
            last_text = "Never"
        self._last_lbl = QLabel(last_text)
        self._last_lbl.setObjectName("kvValue")
        grid.addWidget(self._last_lbl, 3, 1)

        layout.addLayout(grid)

    def _browse_dl_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select ROM Download Directory")
        if path:
            self._dl_dir_input.setText(path)
            self._config.set("discovery/download_dir", path)


# ── App update section ────────────────────────────────────────────────────────


class _UpdateSection(CyberCard):
    """App update checker — shows current version and allows manual update check."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self.card_layout()

        from cyberflash.services.update_service import UpdateService

        self._update_svc = UpdateService.instance()

        hdr = QHBoxLayout()
        title = QLabel("App Updates")
        title.setObjectName("cardHeader")
        hdr.addWidget(title)
        hdr.addStretch()
        layout.addLayout(hdr)

        version_row = QHBoxLayout()
        version_row.addWidget(QLabel("Current version:"))
        self._ver_lbl = QLabel(self._update_svc.get_current_version())
        self._ver_lbl.setObjectName("kvValue")
        version_row.addWidget(self._ver_lbl)
        version_row.addStretch()
        layout.addLayout(version_row)

        btn_row = QHBoxLayout()
        self._check_btn = QPushButton("Check for Updates")
        self._check_btn.setObjectName("primaryButton")
        self._check_btn.setFixedWidth(160)
        self._check_btn.clicked.connect(self._check_update)
        btn_row.addWidget(self._check_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("subtitleLabel")
        self._status_lbl.setWordWrap(True)
        layout.addWidget(self._status_lbl)

    def _check_update(self) -> None:
        from PySide6.QtCore import QThread

        self._check_btn.setEnabled(False)
        self._status_lbl.setText("Checking…")

        svc = self._update_svc

        class _Worker(QThread):
            def run(self) -> None:
                self.result = svc.check_update(force=True)

        self._worker = _Worker(self)
        self._worker.finished.connect(self._on_check_done)
        self._worker.start()

    def _on_check_done(self) -> None:
        self._check_btn.setEnabled(True)
        info = getattr(self._worker, "result", None)
        if info is None:
            self._status_lbl.setText("Up to date.")
        else:
            excerpt = (info.body[:120] + "…") if len(info.body) > 120 else info.body
            self._status_lbl.setText(f"Update available: v{info.version}\n{excerpt}")
        self._worker = None  # type: ignore[assignment]


# ── Main page ────────────────────────────────────────────────────────────────


class SettingsPage(QWidget):
    """Application settings — preferences, safety, logging, and downloads."""

    def __init__(
        self,
        config_service: ConfigService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._config = config_service or ConfigService.instance()
        self._discovery_service: object | None = None
        self._discovery_section: _DiscoverySection | None = None
        self._setup_ui()

    def set_discovery_service(self, svc: object) -> None:
        """Bind the ROM discovery service so the 'Discover All Now' button works."""
        self._discovery_service = svc
        if self._discovery_section is not None:
            self._discovery_section.discover_all_requested.connect(
                lambda: svc.discover_all()  # type: ignore[union-attr]
            )

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        subtitle = QLabel("Application preferences and configuration")
        subtitle.setObjectName("pageSubtitle")
        header.addWidget(subtitle)
        header.addStretch()
        root.addLayout(header)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        scroll_inner = QWidget()
        sl = QVBoxLayout(scroll_inner)
        sl.setAlignment(Qt.AlignmentFlag.AlignTop)
        sl.setSpacing(16)

        # Section cards
        sl.addWidget(_AppearanceSection(self._config))
        sl.addWidget(_AISection(self._config))
        sl.addWidget(_DeviceSection(self._config))
        sl.addWidget(_FlashSection(self._config))
        sl.addWidget(_LoggingSection(self._config))
        sl.addWidget(_DownloadsSection(self._config))
        self._discovery_section = _DiscoverySection(self._config)
        sl.addWidget(self._discovery_section)
        sl.addWidget(_UpdateSection())

        # Reset button
        reset_row = QHBoxLayout()
        reset_row.addStretch()
        self._reset_btn = QPushButton("Reset All to Defaults")
        self._reset_btn.setObjectName("dangerButton")
        self._reset_btn.setFixedWidth(200)
        self._reset_btn.clicked.connect(self._reset_defaults)
        reset_row.addWidget(self._reset_btn)
        sl.addLayout(reset_row)

        # Version info
        from cyberflash import __version__

        ver = QLabel(f"CyberFlash v{__version__}")
        ver.setObjectName("subtitleLabel")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(ver)
        sl.addStretch()

        scroll.setWidget(scroll_inner)
        root.addWidget(scroll)

    def _reset_defaults(self) -> None:
        self._config.reset_to_defaults()
        logger.info("Settings reset to defaults")
        # Rebuild UI to reflect defaults — simplest approach is to
        # remove and re-add scroll content (would be done via signal
        # in a production implementation)
