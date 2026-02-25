"""Preflight results dialog — shows pre-flight check results before operations."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_STATUS_ICONS = {
    "pass": "\u2705",
    "warn": "\u26a0\ufe0f",
    "fail": "\u274c",
    "skip": "\u23ed\ufe0f",
}

_SEVERITY_COLORS = {
    "blocking": "#f85149",
    "warning": "#d29922",
    "info": "#58a6ff",
}


class PreflightDialog(QDialog):
    """Modal dialog that displays pre-flight check results.

    Usage::

        from cyberflash.core.preflight_checker import PreflightChecker
        checker = PreflightChecker(serial)
        result = checker.check_flash(source_path)
        dlg = PreflightDialog(result, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # user chose to proceed
            ...
    """

    def __init__(self, result, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._result = result
        self.setWindowTitle("Pre-flight Check Results")
        self.setMinimumSize(480, 400)
        self.resize(520, 500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        icon_text = "\u2705" if self._result.passed else "\u26a0\ufe0f"
        icon = QLabel(icon_text)
        icon.setStyleSheet("font-size: 28px;")
        hdr.addWidget(icon)

        title = QLabel("Pre-flight Checks")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        hdr.addWidget(title)
        hdr.addStretch()
        layout.addLayout(hdr)

        # Summary
        summary = QLabel(self._result.summary)
        summary.setWordWrap(True)
        summary.setStyleSheet("font-size: 13px; color: #8b949e;")
        layout.addWidget(summary)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #21262d;")
        layout.addWidget(sep)

        # Checks list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        checks_widget = QWidget()
        checks_layout = QVBoxLayout(checks_widget)
        checks_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        checks_layout.setSpacing(6)

        for check in self._result.checks:
            card = self._create_check_card(check)
            checks_layout.addWidget(card)

        checks_layout.addStretch()
        scroll.setWidget(checks_widget)
        layout.addWidget(scroll, stretch=1)

        # Blocking failures warning
        if self._result.blocking_failures:
            warn = QLabel(
                f"\u274c {self._result.blocking_failures} blocking failure(s) — "
                "proceeding is NOT recommended"
            )
            warn.setStyleSheet(
                "color: #f85149; font-weight: bold; padding: 8px; "
                "background: rgba(248, 81, 73, 0.1); border-radius: 4px;"
            )
            warn.setWordWrap(True)
            layout.addWidget(warn)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        proceed_btn = QPushButton("Proceed Anyway" if not self._result.passed else "Continue")
        proceed_btn.setObjectName("dangerButton" if not self._result.passed else "primaryButton")
        proceed_btn.setFixedWidth(140)
        proceed_btn.clicked.connect(self.accept)
        btn_row.addWidget(proceed_btn)
        layout.addLayout(btn_row)

    def _create_check_card(self, check) -> QWidget:
        """Build a card for a single check result."""
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #161b22; border: 1px solid #21262d; "
            "border-radius: 6px; padding: 8px; }"
        )
        layout = QHBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Status icon
        status_str = (
            str(check.status.value) if hasattr(check.status, "value") else str(check.status)
        )
        icon = QLabel(_STATUS_ICONS.get(status_str, "\u2753"))
        icon.setFixedSize(24, 24)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 16px;")
        layout.addWidget(icon)

        # Text
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        name_lbl = QLabel(check.name)
        name_lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        text_col.addWidget(name_lbl)

        msg_lbl = QLabel(check.message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("font-size: 11px; color: #8b949e;")
        text_col.addWidget(msg_lbl)
        layout.addLayout(text_col, 1)

        # Severity badge
        severity_str = (
            str(check.severity.value) if hasattr(check.severity, "value") else str(check.severity)
        )
        color = _SEVERITY_COLORS.get(severity_str, "#8b949e")
        badge = QLabel(severity_str.upper())
        badge.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: bold; "
            f"padding: 2px 6px; border: 1px solid {color}; border-radius: 3px;"
        )
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge)

        return card
