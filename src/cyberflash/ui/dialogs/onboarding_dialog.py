"""onboarding_dialog.py — First-run onboarding wizard.

6-step walkthrough covering: Welcome, Connect Device, Flash ROM,
Root Device, Diagnostics, and Ready!

Completion is persisted via ConfigService (only shown on first launch).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# Config key for completion flag
_CONFIG_KEY = "ui/onboarding_complete"

# Step data: (title, icon_text, description)
_STEPS: list[tuple[str, str, str]] = [
    (
        "Welcome to CyberFlash",
        "⚡",
        "CyberFlash is a professional Android ROM flashing tool.\n\n"
        "This short tour will guide you through the main features.\n"
        "You can skip at any time and revisit via Settings.",
    ),
    (
        "Connect Your Device",
        "📱",
        "Connect your Android device via USB.\n\n"
        "1. Enable Developer Options (tap Build Number 7 times)\n"
        "2. Enable USB Debugging in Developer Options\n"
        "3. Accept the RSA fingerprint prompt on your device\n\n"
        "CyberFlash will auto-detect connected devices.",
    ),
    (
        "Flash a ROM",
        "💾",
        "Navigate to the Flash page to flash a custom ROM.\n\n"
        "• Select a ROM zip from the library or pick a local file\n"
        "• CyberFlash verifies checksums before flashing\n"
        "• Use Dry Run mode to simulate the process safely\n"
        "• All operations are logged for review",
    ),
    (
        "Root Your Device",
        "🔓",
        "Navigate to the Root page for one-click rooting.\n\n"
        "Supported root solutions:\n"
        "• Magisk — most compatible, with DenyList for SafetyNet\n"
        "• KernelSU — kernel-level root for better security\n"
        "• APatch — patching-based approach\n\n"
        "Always backup before rooting!",
    ),
    (
        "Run Diagnostics",
        "🩺",
        "The Diagnostics page gives real-time device health insights.\n\n"
        "• Live logcat with priority filtering\n"
        "• Battery health, storage, CPU, memory scores\n"
        "• Security audit (SELinux, bootloader, encryption)\n"
        "• Privacy scanner for tracking SDKs",
    ),
    (
        "You're All Set! 🚀",
        "✅",
        "CyberFlash is ready to use.\n\n"
        "Quick tips:\n"
        "• Ctrl+1-5 navigate between pages\n"
        "• F5 refreshes the device list\n"
        "• Flash Journal records all operations\n"
        "• Settings → Theme to switch between cyber themes\n\n"
        "Happy flashing!",
    ),
]


# ── Step page widget ──────────────────────────────────────────────────────────


class _StepPage(QWidget):
    def __init__(self, title: str, icon: str, description: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Icon
        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 64px;")
        layout.addWidget(icon_lbl)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #00ff88;"
        )
        title_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #00ff8833;")
        layout.addWidget(sep)

        # Description
        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        desc_lbl.setStyleSheet("font-size: 13px; color: #c9d1d9; line-height: 160%;")
        layout.addWidget(desc_lbl)
        layout.addStretch()


# ── Onboarding dialog ─────────────────────────────────────────────────────────


class OnboardingDialog(QDialog):
    """First-run 6-step onboarding wizard."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to CyberFlash")
        self.setMinimumSize(560, 440)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Stacked pages ─────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        for title, icon, desc in _STEPS:
            self._stack.addWidget(_StepPage(title, icon, desc))
        root.addWidget(self._stack)

        # ── Progress dots ─────────────────────────────────────────────────────
        dots_row = QHBoxLayout()
        dots_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dots: list[QLabel] = []
        for _i in range(len(_STEPS)):
            dot = QLabel("●")
            dot.setStyleSheet("color: #21262d; font-size: 10px;")
            dots_row.addWidget(dot)
            self._dots.append(dot)
        root.addLayout(dots_row)

        # ── Navigation buttons ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 8, 16, 16)

        skip_btn = QPushButton("Skip Tour")
        skip_btn.setObjectName("secondaryButton")
        skip_btn.clicked.connect(self._skip)
        btn_row.addWidget(skip_btn)
        btn_row.addStretch()

        self._back_btn = QPushButton("← Back")
        self._back_btn.setObjectName("secondaryButton")
        self._back_btn.clicked.connect(self._prev)
        self._back_btn.setEnabled(False)
        btn_row.addWidget(self._back_btn)

        self._next_btn = QPushButton("Next →")
        self._next_btn.setObjectName("primaryButton")
        self._next_btn.clicked.connect(self._next)
        btn_row.addWidget(self._next_btn)

        root.addLayout(btn_row)

        self._update_dots()

    def _update_dots(self) -> None:
        idx = self._stack.currentIndex()
        for i, dot in enumerate(self._dots):
            color = "#00ff88" if i == idx else "#21262d"
            dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        self._back_btn.setEnabled(idx > 0)
        is_last = idx == len(_STEPS) - 1
        self._next_btn.setText("Finish ✓" if is_last else "Next →")

    def _next(self) -> None:
        idx = self._stack.currentIndex()
        if idx < len(_STEPS) - 1:
            self._stack.setCurrentIndex(idx + 1)
            self._update_dots()
        else:
            self._complete()

    def _prev(self) -> None:
        idx = self._stack.currentIndex()
        if idx > 0:
            self._stack.setCurrentIndex(idx - 1)
            self._update_dots()

    def _skip(self) -> None:
        self._mark_complete()
        self.reject()

    def _complete(self) -> None:
        self._mark_complete()
        self.accept()

    def _mark_complete(self) -> None:
        try:
            from cyberflash.services.config_service import ConfigService
            ConfigService.instance().set(_CONFIG_KEY, True)
        except Exception as exc:
            logger.debug("OnboardingDialog: could not persist completion: %s", exc)

    @staticmethod
    def should_show() -> bool:
        """Return True if the onboarding tour has not been completed."""
        try:
            from cyberflash.services.config_service import ConfigService
            return not ConfigService.instance().get_bool(_CONFIG_KEY)
        except Exception:
            return True
