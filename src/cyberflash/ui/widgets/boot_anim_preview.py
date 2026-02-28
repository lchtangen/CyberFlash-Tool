"""boot_anim_preview.py — Boot animation preview and management dialog."""
from __future__ import annotations

import contextlib
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)

# Try to import BootAnimationManager; degrade gracefully if unavailable.
try:
    from cyberflash.core.boot_animation_manager import (
        BootAnimationManager as _BootAnimationManager,
    )
    _BAM_AVAILABLE = True
except ImportError:
    _BootAnimationManager = None  # type: ignore[assignment,misc]
    _BAM_AVAILABLE = False
    logger.debug("BootAnimationManager not available — preview will be limited")

_FRAME_INTERVAL_MS = 50


class BootAnimPreviewDialog(QDialog):
    """Boot animation preview and management dialog.

    Allows loading, previewing, and optionally installing custom boot
    animations to the connected device. Accepts .zip files via button or
    drag-and-drop.
    """

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self.setWindowTitle("Boot Animation Preview")
        self.setMinimumSize(480, 560)
        self._frames: list[object] = []
        self._current_frame_index = 0
        self._manager: object | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_INTERVAL_MS)
        self._timer.timeout.connect(self._advance_frame)

        self._setup_ui()
        self.setAcceptDrops(True)

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Boot Animation Preview")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # Frame display label
        self._frame_label = QLabel("Drop bootanimation.zip here")
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_label.setFixedSize(250, 250)
        self._frame_label.setObjectName("frameDisplay")
        self._frame_label.setStyleSheet(
            "QLabel#frameDisplay {"
            "  border: 2px dashed #444;"
            "  background: #1a1a2e;"
            "  color: #666;"
            "}"
        )

        center_row = QHBoxLayout()
        center_row.addStretch()
        center_row.addWidget(self._frame_label)
        center_row.addStretch()
        layout.addLayout(center_row)

        # Metadata
        self._meta_label = QLabel("Resolution: —  |  FPS: —  |  Parts: —")
        self._meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._meta_label.setObjectName("metaLabel")
        layout.addWidget(self._meta_label)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        load_btn = QPushButton("Load .zip")
        load_btn.setObjectName("secondaryButton")
        load_btn.clicked.connect(self._load_zip)
        btn_row.addWidget(load_btn)

        self._preview_btn = QPushButton("Preview")
        self._preview_btn.setObjectName("primaryButton")
        self._preview_btn.setEnabled(False)
        self._preview_btn.clicked.connect(self._start_preview)
        btn_row.addWidget(self._preview_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("secondaryButton")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_preview)
        btn_row.addWidget(self._stop_btn)

        layout.addLayout(btn_row)

        device_row = QHBoxLayout()
        device_row.setSpacing(6)

        install_btn = QPushButton("Install to Device")
        install_btn.setObjectName("primaryButton")
        install_btn.clicked.connect(self._install_to_device)
        device_row.addWidget(install_btn)

        backup_btn = QPushButton("Backup Current")
        backup_btn.setObjectName("secondaryButton")
        backup_btn.clicked.connect(self._backup_current)
        device_row.addWidget(backup_btn)

        reset_btn = QPushButton("Reset to Stock")
        reset_btn.setObjectName("dangerButton")
        reset_btn.clicked.connect(self._reset_to_stock)
        device_row.addWidget(reset_btn)

        layout.addLayout(device_row)

        layout.addStretch()

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    # ── Drag and drop ────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: object) -> None:  # type: ignore[override]
        from PySide6.QtGui import QDragEnterEvent
        if isinstance(event, QDragEnterEvent):
            mime = event.mimeData()
            if mime is not None and mime.hasUrls():
                urls = mime.urls()
                if urls and urls[0].toLocalFile().lower().endswith(".zip"):
                    event.acceptProposedAction()
                    return
        with contextlib.suppress(Exception):
            event.ignore()  # type: ignore[union-attr]

    def dropEvent(self, event: object) -> None:  # type: ignore[override]
        from PySide6.QtGui import QDropEvent
        if isinstance(event, QDropEvent):
            mime = event.mimeData()
            if mime is not None and mime.hasUrls():
                path = mime.urls()[0].toLocalFile()
                self._load_zip_from_path(path)

    # ── Load & preview ───────────────────────────────────────────────────────

    def _load_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Boot Animation", "", "Zip Files (*.zip)"
        )
        if path:
            self._load_zip_from_path(path)

    def _load_zip_from_path(self, path: str) -> None:
        logger.info("Loading boot animation from: %s", path)
        self._frames = []
        self._current_frame_index = 0

        if _BAM_AVAILABLE and _BootAnimationManager is not None:
            try:
                self._manager = _BootAnimationManager(path)
                frames = self._manager.extract_frames()  # type: ignore[union-attr]
                self._frames = frames if frames else []
                meta = self._manager.get_metadata()  # type: ignore[union-attr]
                resolution = getattr(meta, "resolution", "—")
                fps        = getattr(meta, "fps",        "—")
                parts      = getattr(meta, "parts",      "—")
                self._meta_label.setText(
                    f"Resolution: {resolution}  |  FPS: {fps}  |  Parts: {parts}"
                )
            except Exception as exc:
                logger.exception("Failed to load boot animation")
                self._frame_label.setText(f"Load error:\n{exc}")
                return
        else:
            self._frame_label.setText(f"Loaded (preview unavailable):\n{path.rsplit('/', maxsplit=1)[-1]}")

        self._preview_btn.setEnabled(bool(self._frames))
        if self._frames:
            self._show_frame(0)

    def _show_frame(self, index: int) -> None:
        if not self._frames:
            return
        frame = self._frames[index % len(self._frames)]
        from PySide6.QtGui import QPixmap
        if isinstance(frame, QPixmap):
            self._frame_label.setPixmap(
                frame.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio)
            )
        else:
            self._frame_label.setText(f"Frame {index + 1}/{len(self._frames)}")

    def _start_preview(self) -> None:
        if not self._frames:
            return
        self._current_frame_index = 0
        self._timer.start()
        self._preview_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

    def _stop_preview(self) -> None:
        self._timer.stop()
        self._preview_btn.setEnabled(bool(self._frames))
        self._stop_btn.setEnabled(False)

    def _advance_frame(self) -> None:
        if not self._frames:
            self._timer.stop()
            return
        self._current_frame_index = (self._current_frame_index + 1) % len(self._frames)
        self._show_frame(self._current_frame_index)

    # ── Device actions ───────────────────────────────────────────────────────

    def _install_to_device(self) -> None:
        if _BAM_AVAILABLE and self._manager is not None:
            try:
                self._manager.install()  # type: ignore[union-attr]
                logger.info("Boot animation installed to device")
            except Exception:
                logger.exception("Install to device failed")
        else:
            logger.warning("BootAnimationManager not available — cannot install")

    def _backup_current(self) -> None:
        if _BAM_AVAILABLE and _BootAnimationManager is not None:
            try:
                _BootAnimationManager.backup_current()
                logger.info("Current boot animation backed up")
            except Exception:
                logger.exception("Backup current boot animation failed")
        else:
            logger.warning("BootAnimationManager not available — cannot backup")

    def _reset_to_stock(self) -> None:
        if _BAM_AVAILABLE and _BootAnimationManager is not None:
            try:
                _BootAnimationManager.reset_to_stock()
                logger.info("Boot animation reset to stock")
            except Exception:
                logger.exception("Reset to stock failed")
        else:
            logger.warning("BootAnimationManager not available — cannot reset")
