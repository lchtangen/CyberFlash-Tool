"""download_queue_panel.py — Active download queue panel.

Embeddable widget showing queued downloads with per-item progress bars,
concurrency control, bandwidth throttling, and pause/resume/cancel.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# ── Per-download row widget ───────────────────────────────────────────────────


class _DownloadRow(QFrame):
    """A single row in the download queue."""

    cancel_requested = Signal(str)   # url
    pause_requested  = Signal(str)   # url
    resume_requested = Signal(str)   # url
    open_folder      = Signal(str)   # local path

    def __init__(self, url: str, dest: str, parent=None) -> None:
        super().__init__(parent)
        self.url = url
        self.dest = dest
        self._paused = False
        self._done = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("downloadRow")
        self.setStyleSheet(
            "QFrame#downloadRow { background: #0d1117; border: 1px solid #21262d;"
            " border-radius: 4px; margin: 2px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Top row: filename + buttons
        top = QHBoxLayout()
        filename = Path(self.url.split("?")[0]).name or "download"
        self._name_lbl = QLabel(filename[:60])
        self._name_lbl.setStyleSheet("color: #00ff88; font-size: 12px;")
        top.addWidget(self._name_lbl, 1)

        self._pause_btn = QPushButton("⏸")
        self._pause_btn.setFixedSize(24, 24)
        self._pause_btn.setToolTip("Pause / Resume")
        self._pause_btn.clicked.connect(self._toggle_pause)
        top.addWidget(self._pause_btn)

        cancel_btn = QPushButton("✕")
        cancel_btn.setFixedSize(24, 24)
        cancel_btn.setToolTip("Cancel")
        cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.url))
        top.addWidget(cancel_btn)

        folder_btn = QPushButton("📁")
        folder_btn.setFixedSize(24, 24)
        folder_btn.setToolTip("Open folder")
        folder_btn.clicked.connect(lambda: self.open_folder.emit(self.dest))
        top.addWidget(folder_btn)
        layout.addLayout(top)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setStyleSheet(
            "QProgressBar { background: #1c2128; border-radius: 3px; height: 8px; }"
            "QProgressBar::chunk { background: #00ff88; border-radius: 3px; }"
        )
        layout.addWidget(self._progress)

        # Status line
        self._status_lbl = QLabel("Queued")
        self._status_lbl.setStyleSheet("color: #484f58; font-size: 10px;")
        layout.addWidget(self._status_lbl)

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self._pause_btn.setText("▶")
            self.pause_requested.emit(self.url)
        else:
            self._pause_btn.setText("⏸")
            self.resume_requested.emit(self.url)

    def set_progress(self, current: int, total: int) -> None:
        if total > 0:
            pct = int(current * 100 / total)
            self._progress.setValue(pct)
            cur_mb = current / 1_048_576
            tot_mb = total / 1_048_576
            self._status_lbl.setText(f"{cur_mb:.1f} / {tot_mb:.1f} MB")
        else:
            self._progress.setRange(0, 0)  # indeterminate

    def set_complete(self) -> None:
        self._done = True
        self._progress.setValue(100)
        self._progress.setRange(0, 100)
        self._status_lbl.setText("Complete")
        self._pause_btn.setEnabled(False)

    def set_error(self, error: str) -> None:
        self._status_lbl.setText(f"Error: {error[:60]}")
        self._status_lbl.setStyleSheet("color: #ff4444; font-size: 10px;")


# ── Main panel ────────────────────────────────────────────────────────────────


class DownloadQueuePanel(QWidget):
    """Download queue management panel.

    Signals:
        download_queued(url, dest)  — when a download is enqueued
        all_complete()              — when queue becomes empty
    """

    download_queued = Signal(str, str)  # url, dest
    all_complete    = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: dict[str, _DownloadRow] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(6)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("Downloads:"))
        toolbar.addStretch()

        toolbar.addWidget(QLabel("Concurrent:"))
        self._concurrency_spin = QSpinBox()
        self._concurrency_spin.setRange(1, 4)
        self._concurrency_spin.setValue(2)
        self._concurrency_spin.setFixedWidth(50)
        toolbar.addWidget(self._concurrency_spin)

        toolbar.addWidget(QLabel("Bandwidth:"))
        self._bw_slider = QSlider(Qt.Orientation.Horizontal)
        self._bw_slider.setRange(0, 100)
        self._bw_slider.setValue(0)
        self._bw_slider.setFixedWidth(100)
        self._bw_slider.setToolTip("Bandwidth limit (0=unlimited, 100=10MB/s)")
        toolbar.addWidget(self._bw_slider)

        self._bw_lbl = QLabel("Unlimited")
        self._bw_lbl.setFixedWidth(80)
        self._bw_slider.valueChanged.connect(self._on_bw_changed)
        toolbar.addWidget(self._bw_lbl)

        root_layout.addLayout(toolbar)

        # ── Stats row ─────────────────────────────────────────────────────────
        stats = QHBoxLayout()
        self._total_lbl = QLabel("Total: 0 MB downloaded")
        self._total_lbl.setStyleSheet("color: #484f58; font-size: 11px;")
        stats.addWidget(self._total_lbl)
        stats.addStretch()
        self._eta_lbl = QLabel("")
        self._eta_lbl.setStyleSheet("color: #484f58; font-size: 11px;")
        stats.addWidget(self._eta_lbl)
        root_layout.addLayout(stats)

        # ── Scroll list ───────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._list_layout.setSpacing(2)
        self._list_layout.setContentsMargins(0, 0, 0, 0)

        scroll.setWidget(self._list_widget)
        root_layout.addWidget(scroll)

    def _on_bw_changed(self, value: int) -> None:
        if value == 0:
            self._bw_lbl.setText("Unlimited")
        else:
            mb_s = value / 10.0
            self._bw_lbl.setText(f"{mb_s:.1f} MB/s")

    # ── Public API ────────────────────────────────────────────────────────────

    def enqueue(self, url: str, dest: str) -> None:
        """Add *url* → *dest* to the queue."""
        if url in self._rows:
            return
        row = _DownloadRow(url, dest)
        row.cancel_requested.connect(self._cancel_download)
        self._rows[url] = row
        self._list_layout.addWidget(row)
        self.download_queued.emit(url, dest)

    def update_progress(self, url: str, current: int, total: int) -> None:
        """Update progress for a specific download."""
        row = self._rows.get(url)
        if row:
            row.set_progress(current, total)

    def mark_complete(self, url: str) -> None:
        """Mark a download as complete."""
        row = self._rows.get(url)
        if row:
            row.set_complete()
        if all(r._done for r in self._rows.values()):
            self.all_complete.emit()

    def mark_error(self, url: str, error: str) -> None:
        """Mark a download as failed."""
        row = self._rows.get(url)
        if row:
            row.set_error(error)

    def _cancel_download(self, url: str) -> None:
        row = self._rows.pop(url, None)
        if row:
            row.deleteLater()

    def get_max_concurrent(self) -> int:
        return self._concurrency_spin.value()

    def get_bandwidth_limit_bytes(self) -> int:
        """Return bandwidth limit in bytes/s.  0 = unlimited."""
        val = self._bw_slider.value()
        if val == 0:
            return 0
        return int(val / 10.0 * 1_048_576)
