"""privacy_page.py — Privacy & Tracking Scanner page."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cyberflash.services.device_service import DeviceService
from cyberflash.workers.privacy_scanner_worker import AppPrivacyScore, PrivacyScannerWorker

logger = logging.getLogger(__name__)

# ── Grade thresholds ──────────────────────────────────────────────────────────

_GRADE_THRESHOLDS: list[tuple[int, str]] = [
    (90, "A"),
    (75, "B"),
    (60, "C"),
    (40, "D"),
    (0,  "F"),
]


def _score_to_grade(score: int) -> str:
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


# ── Page ──────────────────────────────────────────────────────────────────────


class PrivacyScannerPage(QWidget):
    """Privacy & Tracking Scanner page.

    Scans installed apps on the connected device for tracking SDKs and
    dangerous permissions, then displays per-app scores and details.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._serial = ""
        self._scores: list[AppPrivacyScore] = []
        self._thread: QThread | None = None
        self._worker: PrivacyScannerWorker | None = None
        self._setup_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Header row
        header = QHBoxLayout()
        title = QLabel("Privacy Scanner")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self._export_btn = QPushButton("EXPORT JSON")
        self._export_btn.setObjectName("secondaryButton")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export_json)
        header.addWidget(self._export_btn)

        self._scan_btn = QPushButton("SCAN DEVICE")
        self._scan_btn.setObjectName("primaryButton")
        self._scan_btn.clicked.connect(self._start_scan)
        header.addWidget(self._scan_btn)

        self._abort_btn = QPushButton("ABORT")
        self._abort_btn.setObjectName("dangerButton")
        self._abort_btn.setEnabled(False)
        self._abort_btn.clicked.connect(self._abort_scan)
        header.addWidget(self._abort_btn)

        layout.addLayout(header)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel — app list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._app_list = QListWidget()
        self._app_list.currentItemChanged.connect(self._on_item_selected)
        left_layout.addWidget(self._app_list)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("Sort:"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["Name", "Score (worst first)", "SDK Count"])
        self._sort_combo.currentIndexChanged.connect(self._apply_sort)
        sort_row.addWidget(self._sort_combo, 1)
        left_layout.addLayout(sort_row)

        splitter.addWidget(left_panel)

        # Right panel — detail view
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        self._score_label = QLabel("Select an app to view details")
        self._score_label.setObjectName("detailHeading")
        self._score_label.setWordWrap(True)
        right_layout.addWidget(self._score_label)

        self._detail_view = QTextEdit()
        self._detail_view.setReadOnly(True)
        self._detail_view.setObjectName("detailView")
        right_layout.addWidget(self._detail_view)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter, 1)

        # Log panel at bottom
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setObjectName("logOutput")
        self._log.setFixedHeight(120)
        layout.addWidget(self._log)

    # ── Service wiring ───────────────────────────────────────────────────────

    def set_service(self, device_service: DeviceService) -> None:
        """Connect to the DeviceService to receive selected device updates."""
        device_service.selected_device_changed.connect(self._on_device_changed)

    @Slot(object)
    def _on_device_changed(self, device: object) -> None:
        if device is None:
            self._serial = ""
            self._log_message("No device selected.")
        else:
            self._serial = getattr(device, "serial", "")
            self._log_message(f"Device selected: {self._serial}")

    # ── Scan lifecycle ───────────────────────────────────────────────────────

    def _start_scan(self) -> None:
        if not self._serial:
            self._log_message("No device connected. Cannot start scan.")
            return

        self._scores.clear()
        self._app_list.clear()
        self._score_label.setText("Scanning…")
        self._detail_view.clear()
        self._scan_btn.setEnabled(False)
        self._abort_btn.setEnabled(True)
        self._export_btn.setEnabled(False)
        self._log_message(f"Starting privacy scan on {self._serial}…")

        self._thread = QThread(self)
        self._worker = PrivacyScannerWorker(self._serial)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._worker.app_scanned.connect(self._on_app_scanned)
        self._worker.scan_complete.connect(self._on_scan_complete)
        self._worker.error.connect(self._on_scan_error)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _abort_scan(self) -> None:
        if self._worker is not None:
            self._worker.abort()
            self._log_message("Abort requested — finishing current app…")
        self._abort_btn.setEnabled(False)

    @Slot(object)
    def _on_app_scanned(self, score: AppPrivacyScore) -> None:
        self._scores.append(score)
        grade = _score_to_grade(score.score)
        item = QListWidgetItem(f"{score.package}  Score: {score.score} [{grade}]")
        item.setData(Qt.ItemDataRole.UserRole, score)
        self._app_list.addItem(item)
        self._log_message(f"Scanned: {score.package} — {score.score}/100 [{grade}]")

    @Slot(list)
    def _on_scan_complete(self, results: list) -> None:
        self._scan_btn.setEnabled(True)
        self._abort_btn.setEnabled(False)
        self._export_btn.setEnabled(bool(results))
        count = len(results)
        self._log_message(f"Scan complete. {count} app(s) analysed.")
        self._score_label.setText(f"Scan complete — {count} apps. Select an app for details.")

    @Slot(str)
    def _on_scan_error(self, message: str) -> None:
        self._scan_btn.setEnabled(True)
        self._abort_btn.setEnabled(False)
        self._log_message(f"Error: {message}")

    # ── Detail view ──────────────────────────────────────────────────────────

    @Slot()
    def _on_item_selected(self) -> None:
        item = self._app_list.currentItem()
        if item is None:
            return
        score: AppPrivacyScore = item.data(Qt.ItemDataRole.UserRole)
        self._show_detail(score)

    def _show_detail(self, score: AppPrivacyScore) -> None:
        grade = _score_to_grade(score.score)
        self._score_label.setText(
            f"Privacy Score: {score.score}/100   Grade: {grade}"
        )

        lines: list[str] = []

        lines.append(f"Tracking SDKs ({len(score.sdks)}):")
        if score.sdks:
            for sdk in score.sdks:
                stars = "★" * sdk.risk_level + "☆" * (5 - sdk.risk_level)
                lines.append(f"  {sdk.name}  {stars}")
        else:
            lines.append("  None detected")

        lines.append("")
        lines.append(f"Dangerous Permissions ({len(score.dangerous_perms)}):")
        if score.dangerous_perms:
            for perm in score.dangerous_perms:
                lines.append(f"  {perm}")
        else:
            lines.append("  None granted")

        self._detail_view.setPlainText("\n".join(lines))

    # ── Sorting ──────────────────────────────────────────────────────────────

    def _apply_sort(self) -> None:
        mode = self._sort_combo.currentText()
        if mode == "Name":
            self._scores.sort(key=lambda s: s.package)
        elif mode == "Score (worst first)":
            self._scores.sort(key=lambda s: s.score)
        else:  # SDK Count
            self._scores.sort(key=lambda s: len(s.sdks), reverse=True)

        self._app_list.clear()
        for score in self._scores:
            grade = _score_to_grade(score.score)
            item = QListWidgetItem(f"{score.package}  Score: {score.score} [{grade}]")
            item.setData(Qt.ItemDataRole.UserRole, score)
            self._app_list.addItem(item)

    # ── Export ───────────────────────────────────────────────────────────────

    def _export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Privacy Report", "privacy_report.json", "JSON Files (*.json)"
        )
        if not path:
            return
        data = [
            {
                "package": s.package,
                "score": s.score,
                "grade": _score_to_grade(s.score),
                "sdks": [
                    {"name": sdk.name, "risk_level": sdk.risk_level}
                    for sdk in s.sdks
                ],
                "dangerous_permissions": s.dangerous_perms,
            }
            for s in self._scores
        ]
        try:
            Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
            self._log_message(f"Report exported to {path}")
        except OSError as exc:
            self._log_message(f"Export failed: {exc}")
            logger.exception("Privacy report export failed")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _log_message(self, message: str) -> None:
        self._log.append(message)
        logger.debug("PrivacyScannerPage: %s", message)
