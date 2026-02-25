"""ROM Library page with AI-powered link monitoring and trust scoring.

Displays tracked ROM download sources with real-time trust grades,
source status badges, and controls for adding/removing/refreshing sources.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.rom_manager import DownloadState, RomManager
from cyberflash.models.rom_source import RomSource, SourceStatus
from cyberflash.services.rom_link_service import RomLinkService
from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.cyber_card import CyberCard
from cyberflash.workers.download_worker import DownloadWorker

# ── Status → badge variant mapping ───────────────────────────────────────────

_STATUS_BADGE: dict[SourceStatus, tuple[str, str]] = {
    SourceStatus.VERIFIED: ("Verified", "success"),
    SourceStatus.ACTIVE: ("Active", "info"),
    SourceStatus.DEGRADED: ("Degraded", "warning"),
    SourceStatus.BROKEN: ("Broken", "error"),
    SourceStatus.FLAGGED: ("Flagged", "error"),
    SourceStatus.BLOCKED: ("Blocked", "error"),
    SourceStatus.UNKNOWN: ("Checking…", "neutral"),
}


class RomLibraryPage(QWidget):
    """Main ROM Library page with source monitoring UI."""

    source_added = Signal(str)  # url

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service: RomLinkService | None = None
        self._source_cards: dict[str, _SourceCard] = {}          # url → card widget
        self._active_downloads: dict[str, tuple[DownloadWorker, QThread]] = {}  # url → (worker, thread)
        self._setup_ui()

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Header
        header = self._build_header()
        root.addLayout(header)

        # Stats bar
        self._stats_bar = _StatsBar()
        root.addWidget(self._stats_bar)

        # Add-source input row
        input_row = self._build_input_row()
        root.addLayout(input_row)

        # Scrollable source list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("romSourceScroll")

        self._source_container = QWidget()
        self._source_layout = QVBoxLayout(self._source_container)
        self._source_layout.setContentsMargins(0, 0, 0, 0)
        self._source_layout.setSpacing(8)
        self._source_layout.addStretch()

        scroll.setWidget(self._source_container)
        root.addWidget(scroll)

        # Empty state
        self._empty_label = QLabel("No ROM sources added yet.\nPaste a URL above to start.")
        self._empty_label.setObjectName("emptyHint")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._source_layout.insertWidget(0, self._empty_label)

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        title = QLabel("ROM Library")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        subtitle = QLabel("AI-monitored download sources with trust scoring")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)
        layout.addStretch()
        return layout

    def _build_input_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        self._url_input = QLineEdit()
        self._url_input.setObjectName("romUrlInput")
        self._url_input.setPlaceholderText("https://download.lineageos.org/...")
        self._url_input.returnPressed.connect(self._on_add_clicked)
        layout.addWidget(self._url_input)

        add_btn = QPushButton("Add Source")
        add_btn.setObjectName("romAddBtn")
        add_btn.clicked.connect(self._on_add_clicked)
        layout.addWidget(add_btn)

        return layout

    # ── Service binding ───────────────────────────────────────────────────────

    def set_service(self, service: RomLinkService) -> None:
        """Bind the ROM link monitoring service to this page."""
        self._service = service
        service.source_updated.connect(self._on_source_updated)
        service.source_flagged.connect(self._on_source_flagged)
        service.sweep_completed.connect(self._on_sweep_completed)

        # Populate existing sources
        for source in service.get_sources():
            self._add_source_card(source)
        self._update_empty_state()
        self._stats_bar.update_stats(service)

    # ── Slots ─────────────────────────────────────────────────────────────────

    @Slot()
    def _on_add_clicked(self) -> None:
        url = self._url_input.text().strip()
        if not url or not url.startswith(("http://", "https://")):
            return

        if self._service:
            source = self._service.add_source(url)
            self._add_source_card(source)
            self._update_empty_state()
            self._stats_bar.update_stats(self._service)
        self._url_input.clear()
        self.source_added.emit(url)

    @Slot(object)
    def _on_source_updated(self, source: RomSource) -> None:
        card = self._source_cards.get(source.url)
        if card:
            card.update_from_source(source)
        if self._service:
            self._stats_bar.update_stats(self._service)

    @Slot(object)
    def _on_source_flagged(self, source: RomSource) -> None:
        card = self._source_cards.get(source.url)
        if card:
            card.update_from_source(source)
            card.show_flagged_warning(source.flagged_reason)

    @Slot(int)
    def _on_sweep_completed(self, count: int) -> None:
        if self._service:
            self._stats_bar.update_stats(self._service)

    # ── Card management ───────────────────────────────────────────────────────

    def _add_source_card(self, source: RomSource) -> None:
        if source.url in self._source_cards:
            return

        card = _SourceCard(source)
        card.remove_requested.connect(self._on_remove_source)
        card.download_requested.connect(self._on_download_requested)
        card.cancel_requested.connect(self._on_cancel_requested)

        # Mark already-downloaded files
        if RomManager.is_downloaded(source.url):
            card.set_download_state(DownloadState.COMPLETE)

        self._source_cards[source.url] = card
        # Insert before the stretch
        idx = self._source_layout.count() - 1
        self._source_layout.insertWidget(idx, card)

    @Slot(str)
    def _on_remove_source(self, url: str) -> None:
        card = self._source_cards.pop(url, None)
        if card:
            self._source_layout.removeWidget(card)
            card.deleteLater()
        if self._service:
            self._service.remove_source(url)
            self._stats_bar.update_stats(self._service)
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        self._empty_label.setVisible(len(self._source_cards) == 0)

    # ── Download management ───────────────────────────────────────────────────

    @Slot(str)
    def _on_download_requested(self, url: str) -> None:
        if url in self._active_downloads:
            return  # already downloading
        card = self._source_cards.get(url)
        if not card:
            return

        dest = RomManager.dest_for_url(url)
        worker = DownloadWorker(url, dest)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.start)

        worker.progress.connect(
            lambda done, total, u=url: self._on_download_progress(u, done, total)
        )
        worker.speed_update.connect(
            lambda bps, u=url: self._on_download_speed(u, bps)
        )
        worker.download_complete.connect(
            lambda path, u=url: self._on_download_complete(u, path)
        )
        worker.error.connect(
            lambda msg, u=url: self._on_download_error(u, msg)
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._active_downloads[url] = (worker, thread)
        card.set_download_state(DownloadState.DOWNLOADING)
        thread.start()

    @Slot(str)
    def _on_cancel_requested(self, url: str) -> None:
        entry = self._active_downloads.pop(url, None)
        if entry:
            worker, _ = entry
            worker.abort()
        card = self._source_cards.get(url)
        if card:
            card.set_download_state(DownloadState.IDLE)

    def _on_download_progress(self, url: str, done: int, total: int) -> None:
        card = self._source_cards.get(url)
        if card:
            card.update_download_progress(done, total)

    def _on_download_speed(self, url: str, bps: float) -> None:
        card = self._source_cards.get(url)
        if card:
            card.update_download_speed(bps)

    def _on_download_complete(self, url: str, path: str) -> None:
        self._active_downloads.pop(url, None)
        RomManager.record_download(url, RomManager.dest_for_url(url))
        card = self._source_cards.get(url)
        if card:
            card.set_download_state(DownloadState.COMPLETE, path)

    def _on_download_error(self, url: str, msg: str) -> None:
        self._active_downloads.pop(url, None)
        card = self._source_cards.get(url)
        if card:
            card.set_download_state(DownloadState.FAILED, msg)


# ── StatsBar widget ──────────────────────────────────────────────────────────


class _StatsBar(QFrame):
    """Compact horizontal bar showing aggregate monitoring stats."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("romStatsBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(24)

        self._total_label = QLabel("Sources: 0")
        self._total_label.setObjectName("romStatLabel")
        layout.addWidget(self._total_label)

        self._healthy_label = QLabel("Healthy: 0")
        self._healthy_label.setObjectName("romStatLabel")
        layout.addWidget(self._healthy_label)

        self._flagged_label = QLabel("Flagged: 0")
        self._flagged_label.setObjectName("romStatLabel")
        layout.addWidget(self._flagged_label)

        layout.addStretch()

    def update_stats(self, service: RomLinkService) -> None:
        self._total_label.setText(f"Sources: {service.source_count}")
        self._healthy_label.setText(f"Healthy: {service.healthy_count}")
        self._flagged_label.setText(f"Flagged: {service.flagged_count}")


# ── SourceCard widget ────────────────────────────────────────────────────────


class _SourceCard(CyberCard):
    """Card displaying a single ROM source with trust info and download controls."""

    remove_requested   = Signal(str)  # url
    download_requested = Signal(str)  # url
    cancel_requested   = Signal(str)  # url

    def __init__(
        self,
        source: RomSource,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._url = source.url
        self._setup_card_ui()
        self.update_from_source(source)

    def _setup_card_ui(self) -> None:
        layout = self.card_layout()

        # Row 1: domain + badge + grade + download + remove
        top_row = QHBoxLayout()
        self._domain_label = QLabel()
        self._domain_label.setObjectName("romSourceDomain")
        top_row.addWidget(self._domain_label)

        self._status_badge = CyberBadge("Unknown", "neutral")
        top_row.addWidget(self._status_badge)

        top_row.addStretch()

        self._grade_label = QLabel()
        self._grade_label.setObjectName("romTrustGrade")
        top_row.addWidget(self._grade_label)

        self._download_btn = QPushButton("\u2193 Download")
        self._download_btn.setObjectName("primaryButton")
        self._download_btn.setFixedWidth(100)
        self._download_btn.clicked.connect(lambda: self.download_requested.emit(self._url))
        top_row.addWidget(self._download_btn)

        remove_btn = QPushButton("x")
        remove_btn.setObjectName("romRemoveBtn")
        remove_btn.setFixedSize(24, 24)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self._url))
        top_row.addWidget(remove_btn)

        layout.addLayout(top_row)

        # Row 2: URL
        self._url_label = QLabel()
        self._url_label.setObjectName("romSourceUrl")
        self._url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._url_label)

        # Row 3: trust dimensions bar
        dims_row = QHBoxLayout()
        dims_row.setSpacing(16)

        self._avail_bar = _TrustDimBar("Availability")
        dims_row.addWidget(self._avail_bar)

        self._safety_bar = _TrustDimBar("Safety")
        dims_row.addWidget(self._safety_bar)

        self._speed_bar = _TrustDimBar("Speed")
        dims_row.addWidget(self._speed_bar)

        self._rep_bar = _TrustDimBar("Reputation")
        dims_row.addWidget(self._rep_bar)

        layout.addLayout(dims_row)

        # Row 4: meta info
        self._meta_label = QLabel()
        self._meta_label.setObjectName("romSourceMeta")
        layout.addWidget(self._meta_label)

        # Row 5: download progress panel (hidden initially)
        self._dl_panel = QWidget()
        dl_layout = QHBoxLayout(self._dl_panel)
        dl_layout.setContentsMargins(0, 4, 0, 0)
        dl_layout.setSpacing(8)

        self._dl_progress = QProgressBar()
        self._dl_progress.setRange(0, 100)
        self._dl_progress.setValue(0)
        self._dl_progress.setFixedHeight(14)
        self._dl_progress.setFormat("%p%")
        dl_layout.addWidget(self._dl_progress, stretch=1)

        self._dl_speed_label = QLabel("")
        self._dl_speed_label.setObjectName("romSourceMeta")
        self._dl_speed_label.setFixedWidth(80)
        dl_layout.addWidget(self._dl_speed_label)

        self._dl_status_label = QLabel("")
        self._dl_status_label.setObjectName("romSourceMeta")
        dl_layout.addWidget(self._dl_status_label)

        self._dl_cancel_btn = QPushButton("Cancel")
        self._dl_cancel_btn.setObjectName("dangerButton")
        self._dl_cancel_btn.setFixedWidth(70)
        self._dl_cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self._url))
        dl_layout.addWidget(self._dl_cancel_btn)

        self._dl_panel.setVisible(False)
        layout.addWidget(self._dl_panel)

        # Warning area (hidden by default)
        self._warning_label = QLabel()
        self._warning_label.setObjectName("romWarningLabel")
        self._warning_label.setVisible(False)
        layout.addWidget(self._warning_label)

    # ── Download state control ────────────────────────────────────────────────

    def set_download_state(self, state: DownloadState, detail: str = "") -> None:
        """Update the card's download UI for the given state."""
        if state == DownloadState.IDLE:
            self._dl_panel.setVisible(False)
            self._download_btn.setText("\u2193 Download")
            self._download_btn.setEnabled(True)

        elif state == DownloadState.DOWNLOADING:
            self._dl_panel.setVisible(True)
            self._dl_progress.setRange(0, 0)   # indeterminate until first progress
            self._dl_status_label.setText("Downloading\u2026")
            self._dl_cancel_btn.setEnabled(True)
            self._download_btn.setEnabled(False)

        elif state == DownloadState.COMPLETE:
            self._dl_panel.setVisible(False)
            self._download_btn.setText("\u2713 Downloaded")
            self._download_btn.setEnabled(False)

        elif state == DownloadState.FAILED:
            self._dl_panel.setVisible(True)
            self._dl_progress.setRange(0, 100)
            self._dl_progress.setValue(0)
            self._dl_status_label.setText(f"Failed: {detail[:40]}" if detail else "Failed")
            self._dl_cancel_btn.setText("Dismiss")
            self._dl_cancel_btn.clicked.disconnect()
            self._dl_cancel_btn.clicked.connect(
                lambda: self.set_download_state(DownloadState.IDLE)
            )
            self._download_btn.setEnabled(True)

    def update_download_progress(self, bytes_done: int, total_bytes: int) -> None:
        if total_bytes > 0:
            self._dl_progress.setRange(0, 100)
            pct = min(100, int(bytes_done * 100 / total_bytes))
            self._dl_progress.setValue(pct)
            done_mb = bytes_done / 1_048_576
            total_mb = total_bytes / 1_048_576
            self._dl_status_label.setText(f"{done_mb:.1f} / {total_mb:.1f} MB")
        else:
            self._dl_progress.setRange(0, 0)
            self._dl_status_label.setText(f"{bytes_done / 1_048_576:.1f} MB")

    def update_download_speed(self, bps: float) -> None:
        if bps >= 1_048_576:
            self._dl_speed_label.setText(f"{bps / 1_048_576:.1f} MB/s")
        elif bps >= 1024:
            self._dl_speed_label.setText(f"{bps / 1024:.0f} KB/s")
        else:
            self._dl_speed_label.setText(f"{bps:.0f} B/s")

    def update_from_source(self, source: RomSource) -> None:
        """Refresh all labels/bars from the source model."""
        self._domain_label.setText(source.display_name or source.domain)
        self._url_label.setText(source.url)

        # Status badge
        text, variant = _STATUS_BADGE.get(source.status, ("Unknown", "neutral"))
        self._status_badge.set_text_and_variant(text, variant)

        # Trust grade
        grade = source.trust.grade
        self._grade_label.setText(grade)
        self._grade_label.setProperty("grade", grade)
        self._grade_label.style().unpolish(self._grade_label)
        self._grade_label.style().polish(self._grade_label)

        # Trust dimension bars
        self._avail_bar.set_value(source.trust.availability)
        self._safety_bar.set_value(source.trust.safety)
        self._speed_bar.set_value(source.trust.speed)
        self._rep_bar.set_value(source.trust.reputation)

        # Meta info
        meta_parts: list[str] = []
        if source.check_count > 0:
            meta_parts.append(f"Checks: {source.check_count}")
        if source.avg_response_time_ms > 0:
            meta_parts.append(f"Avg: {source.avg_response_time_ms:.0f}ms")
        if source.consecutive_failures > 0:
            meta_parts.append(f"Failures: {source.consecutive_failures}")
        self._meta_label.setText(
            "  ·  ".join(meta_parts) if meta_parts else "Awaiting first check…"
        )

    def show_flagged_warning(self, reason: str) -> None:
        self._warning_label.setText(f"⚠ {reason}")
        self._warning_label.setVisible(True)


# ── TrustDimBar widget ───────────────────────────────────────────────────────


class _TrustDimBar(QWidget):
    """Labeled progress bar for a single trust dimension (0.0-1.0)."""

    def __init__(
        self,
        label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._label = QLabel(label)
        self._label.setObjectName("romDimLabel")
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setObjectName("romTrustBar")
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._bar)

    def set_value(self, score: float) -> None:
        """Set the bar value from a 0.0-1.0 score."""
        pct = max(0, min(100, int(score * 100)))
        self._bar.setValue(pct)
