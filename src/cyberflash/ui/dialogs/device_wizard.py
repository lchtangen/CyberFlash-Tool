"""device_wizard.py — First-run device setup wizard dialog.

Shown when an unrecognised device connects.  Guides the user through:

  Step 1 — Device identified (brand + codename auto-detected)
  Step 2 — Profile match (local profile found, or offer to download)
  Step 3 — Brand-specific setup guide (enable OEM unlock, ADB, etc.)
  Step 4 — Done

Usage::

    wizard = DeviceWizard(device_info, parent=self)
    if wizard.exec() == QDialog.DialogCode.Accepted:
        # Profile was downloaded / accepted — proceed
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)

# ── Step index constants ──────────────────────────────────────────────────────

_STEP_IDENTIFY   = 0
_STEP_PROFILE    = 1
_STEP_GUIDE      = 2
_STEP_DONE       = 3

_STEP_TITLES = [
    "Device Identified",
    "Device Profile",
    "Setup Guide",
    "Ready",
]

# ── Brand-specific setup guides ───────────────────────────────────────────────

_BRAND_GUIDES: dict[str, list[str]] = {
    "oneplus": [
        "Go to <b>Settings → About phone</b> and tap Build number 7 times to enable Developer Options.",
        "In <b>Developer Options</b>, enable <b>OEM unlocking</b> and <b>USB debugging</b>.",
        "On newer OnePlus devices, enable <b>Advanced reboot</b> in Developer Options.",
        "Connect via USB and confirm the ADB authorization prompt on your device.",
        "To enter fastboot: power off → hold Volume Down + Power.",
    ],
    "samsung": [
        "Go to <b>Settings → About phone → Software information</b> and tap Build number 7 times.",
        "In <b>Developer Options</b>, enable <b>OEM unlocking</b> and <b>USB debugging</b>.",
        "Install Samsung USB drivers or ensure heimdall-flash is installed on your PC.",
        "To enter Download Mode: power off → hold Volume Down + Volume Up + connect USB.",
        "Accept the Download Mode warning (press Volume Up to confirm).",
    ],
    "xiaomi": [
        "Go to <b>Settings → About phone</b> and tap MIUI version 7 times.",
        "In <b>Developer Options</b>, enable <b>USB debugging</b> and <b>USB debugging (Security settings)</b>.",
        "To unlock the bootloader, link your Mi Account in Developer Options → Mi Unlock status.",
        "Download the Mi Unlock Tool and wait the required 168 hours (7 days) after linking.",
        "To enter fastboot: power off → hold Volume Down + Power.",
    ],
    "google": [
        "Go to <b>Settings → About phone</b> and tap Build number 7 times.",
        "In <b>Developer Options</b>, enable <b>OEM unlocking</b> and <b>USB debugging</b>.",
        "To unlock: enter fastboot (Volume Down + Power), then use 'fastboot flashing unlock'.",
        "Confirm the unlock on the device screen using Volume keys + Power.",
        "To enter fastboot: power off → hold Volume Down, then connect USB.",
    ],
    "motorola": [
        "Go to <b>Settings → About phone</b> and tap Build number 7 times.",
        "In <b>Developer Options</b>, enable <b>OEM unlocking</b> and <b>USB debugging</b>.",
        "For carrier-unlocked devices: get an unlock code at motorola.com/unlockr.",
        "Run 'fastboot oem get_unlock_data' to obtain your device's unlock hash.",
        "To enter fastboot: power off → hold Volume Down + Power.",
    ],
    "default": [
        "Go to <b>Settings → About phone</b> and tap Build number 7 times.",
        "In <b>Developer Options</b>, enable <b>OEM unlocking</b> and <b>USB debugging</b>.",
        "Connect via USB and confirm the ADB authorization prompt on your device.",
        "Consult your manufacturer's documentation for fastboot/download mode key combo.",
    ],
}


# ── Profile check worker ──────────────────────────────────────────────────────


class _ProfileCheckWorker(BaseWorker):
    """Checks whether a device profile exists locally or in the remote hub."""

    profile_result = Signal(bool, str)   # (found, profile_path_or_message)

    def __init__(self, codename: str, brand: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._codename = codename
        self._brand    = brand

    @Slot()
    def start(self) -> None:
        self._run()

    def _run(self) -> None:
        try:
            from pathlib import Path

            # Search local profile store
            profiles_root = Path(__file__).parent.parent.parent.parent / "resources" / "profiles"

            # Check under brand subdirectory
            brand_dir = profiles_root / self._brand.lower()
            codename_file = brand_dir / f"{self._codename.lower()}.json"

            if codename_file.exists():
                logger.info("Profile found locally: %s", codename_file)
                self.profile_result.emit(True, str(codename_file))
            else:
                logger.info("No local profile for %s/%s", self._brand, self._codename)
                self.profile_result.emit(False, "")
        except Exception as exc:
            logger.error("Profile check failed: %s", exc)
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


# ── Step widgets ──────────────────────────────────────────────────────────────


def _step_indicator(step_index: int, current: int) -> QLabel:
    """Build a step indicator dot (filled = current, hollow = future, check = past)."""
    if step_index < current:
        icon = "✓"
        color = "#39d353"
    elif step_index == current:
        icon = str(step_index + 1)
        color = "#58a6ff"
    else:
        icon = str(step_index + 1)
        color = "#484f58"

    lbl = QLabel(icon)
    lbl.setFixedSize(28, 28)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"background: {color}; color: #0d1117; border-radius: 14px; "
        "font-weight: bold; font-size: 11px;"
    )
    return lbl


class _StepBar(QWidget):
    """Horizontal progress bar showing wizard steps."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._current = 0
        self._refresh()

    def set_step(self, step: int) -> None:
        self._current = step
        # Clear and rebuild
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._refresh()

    def _refresh(self) -> None:
        for i, title in enumerate(_STEP_TITLES):
            dot = _step_indicator(i, self._current)
            self._layout.addWidget(dot)

            lbl = QLabel(title)
            lbl.setStyleSheet(
                "color: #58a6ff; font-size: 11px;" if i == self._current
                else "color: #8b949e; font-size: 11px;"
            )
            self._layout.addWidget(lbl)

            if i < len(_STEP_TITLES) - 1:
                sep = QLabel("──")
                sep.setStyleSheet("color: #30363d; font-size: 10px;")
                self._layout.addWidget(sep)

        self._layout.addStretch()


# ── Main dialog ───────────────────────────────────────────────────────────────


class DeviceWizard(QDialog):
    """Multi-step device setup wizard.

    Shown automatically when an unrecognised device connects.

    Args:
        serial:   ADB serial of the device.
        brand:    Brand string (``ro.product.brand``).
        model:    Model string (``ro.product.model``).
        codename: Device codename (``ro.product.device``).
        parent:   Parent widget.
    """

    def __init__(
        self,
        serial:   str,
        brand:    str,
        model:    str,
        codename: str,
        parent:   QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._serial   = serial
        self._brand    = brand.lower()
        self._model    = model
        self._codename = codename
        self._profile_path: str = ""

        self.setWindowTitle("Device Setup Wizard")
        self.setMinimumSize(560, 480)
        self.setModal(True)

        self._setup_ui()
        self._go_to_step(_STEP_IDENTIFY)

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        header = QFrame()
        header.setObjectName("wizardHeader")
        header.setStyleSheet(
            "QFrame#wizardHeader {"
            "  background: #161b22;"
            "  border-bottom: 1px solid #30363d;"
            "}"
        )
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 16, 24, 16)

        title_lbl = QLabel("Device Setup Wizard")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #58a6ff;")
        header_layout.addWidget(title_lbl)

        self._step_bar = _StepBar()
        header_layout.addWidget(self._step_bar)

        root.addWidget(header)

        # Content area — stacked pages
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: #0d1117;")

        self._page_identify = self._build_identify_page()
        self._page_profile  = self._build_profile_page()
        self._page_guide    = self._build_guide_page()
        self._page_done     = self._build_done_page()

        self._stack.addWidget(self._page_identify)
        self._stack.addWidget(self._page_profile)
        self._stack.addWidget(self._page_guide)
        self._stack.addWidget(self._page_done)

        root.addWidget(self._stack, 1)

        # Navigation buttons
        nav = QFrame()
        nav.setStyleSheet(
            "QFrame {"
            "  background: #161b22;"
            "  border-top: 1px solid #30363d;"
            "}"
        )
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(24, 12, 24, 12)

        self._back_btn = QPushButton("Back")
        self._back_btn.setObjectName("secondaryButton")
        self._back_btn.setFixedWidth(90)
        self._back_btn.clicked.connect(self._on_back)

        self._next_btn = QPushButton("Next")
        self._next_btn.setObjectName("primaryButton")
        self._next_btn.setFixedWidth(90)
        self._next_btn.clicked.connect(self._on_next)

        skip_btn = QPushButton("Skip")
        skip_btn.setObjectName("secondaryButton")
        skip_btn.setFixedWidth(70)
        skip_btn.clicked.connect(self.reject)

        nav_layout.addWidget(skip_btn)
        nav_layout.addStretch()
        nav_layout.addWidget(self._back_btn)
        nav_layout.addWidget(self._next_btn)

        root.addWidget(nav)

    # ── Step pages ────────────────────────────────────────────────────────────

    def _build_identify_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        icon_lbl = QLabel("📱")
        icon_lbl.setStyleSheet("font-size: 48px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        headline = QLabel("New Device Detected")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        headline.setStyleSheet("font-size: 20px; font-weight: bold; color: #e6edf3;")
        layout.addWidget(headline)

        brand_cap = self._brand.capitalize()
        info_text = (
            f"<b style='color:#58a6ff'>{self._model}</b><br>"
            f"Codename: <span style='color:#39d353'>{self._codename}</span><br>"
            f"Brand: {brand_cap} &nbsp;·&nbsp; Serial: {self._serial}"
        )
        self._identify_info = QLabel(info_text)
        self._identify_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._identify_info.setStyleSheet("color: #8b949e; line-height: 1.6;")
        self._identify_info.setWordWrap(True)
        layout.addWidget(self._identify_info)

        layout.addStretch()
        return page

    def _build_profile_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        headline = QLabel("Device Profile")
        headline.setStyleSheet("font-size: 18px; font-weight: bold; color: #e6edf3;")
        layout.addWidget(headline)

        desc = QLabel(
            "CyberFlash uses device profiles to know which partitions to flash and "
            "what safety checks to apply."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #8b949e;")
        layout.addWidget(desc)

        self._profile_status = QLabel("Checking for profile…")
        self._profile_status.setStyleSheet("color: #58a6ff; font-size: 13px;")
        self._profile_status.setWordWrap(True)
        layout.addWidget(self._profile_status)

        self._profile_progress = QProgressBar()
        self._profile_progress.setRange(0, 0)
        self._profile_progress.setFixedHeight(4)
        self._profile_progress.setStyleSheet(
            "QProgressBar { border: none; background: #21262d; }"
            "QProgressBar::chunk { background: #58a6ff; }"
        )
        layout.addWidget(self._profile_progress)

        self._profile_note = QLabel(
            "If no profile is found, CyberFlash will use generic defaults. "
            "You can contribute a profile for this device to help other users."
        )
        self._profile_note.setWordWrap(True)
        self._profile_note.setStyleSheet("color: #6e7681; font-size: 11px;")
        self._profile_note.hide()
        layout.addWidget(self._profile_note)

        layout.addStretch()
        return page

    def _build_guide_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        brand_cap = self._brand.capitalize()
        headline = QLabel(f"{brand_cap} Setup Guide")
        headline.setStyleSheet("font-size: 18px; font-weight: bold; color: #e6edf3;")
        layout.addWidget(headline)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { background: #161b22; width: 6px; }"
            "QScrollBar::handle:vertical { background: #30363d; border-radius: 3px; }"
        )

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 8, 0)
        scroll_layout.setSpacing(12)

        steps = _BRAND_GUIDES.get(self._brand, _BRAND_GUIDES["default"])
        for i, step_text in enumerate(steps, 1):
            row = QFrame()
            row.setStyleSheet(
                "QFrame {"
                "  background: #161b22;"
                "  border: 1px solid #30363d;"
                "  border-radius: 6px;"
                "}"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(12)

            num = QLabel(str(i))
            num.setFixedSize(24, 24)
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setStyleSheet(
                "background: #1f6feb; color: white; border-radius: 12px; "
                "font-weight: bold; font-size: 11px;"
            )
            row_layout.addWidget(num)

            text_lbl = QLabel(step_text)
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet("color: #c9d1d9; font-size: 13px;")
            row_layout.addWidget(text_lbl, 1)

            scroll_layout.addWidget(row)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        return page

    def _build_done_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)
        layout.addStretch()

        icon_lbl = QLabel("✅")
        icon_lbl.setStyleSheet("font-size: 56px;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        headline = QLabel("Device Ready")
        headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        headline.setStyleSheet("font-size: 22px; font-weight: bold; color: #39d353;")
        layout.addWidget(headline)

        self._done_msg = QLabel(
            f"<b>{self._model}</b> is configured and ready to use with CyberFlash."
        )
        self._done_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._done_msg.setWordWrap(True)
        self._done_msg.setStyleSheet("color: #8b949e;")
        layout.addWidget(self._done_msg)

        layout.addStretch()
        return page

    # ── Step navigation ───────────────────────────────────────────────────────

    def _go_to_step(self, step: int) -> None:
        self._current_step = step
        self._stack.setCurrentIndex(step)
        self._step_bar.set_step(step)

        self._back_btn.setVisible(step > 0)
        is_last = step == _STEP_DONE
        self._next_btn.setText("Finish" if is_last else "Next")

        if step == _STEP_PROFILE:
            self._start_profile_check()

    def _on_next(self) -> None:
        if self._current_step == _STEP_DONE:
            self.accept()
        elif self._current_step < _STEP_DONE:
            self._go_to_step(self._current_step + 1)

    def _on_back(self) -> None:
        if self._current_step > 0:
            self._go_to_step(self._current_step - 1)

    # ── Profile check ─────────────────────────────────────────────────────────

    def _start_profile_check(self) -> None:
        self._profile_progress.show()
        self._profile_status.setText("Checking for local profile…")
        self._next_btn.setEnabled(False)

        self._profile_worker = _ProfileCheckWorker(self._codename, self._brand)
        self._profile_thread = QThread()
        self._profile_worker.moveToThread(self._profile_thread)

        self._profile_thread.started.connect(self._profile_worker.start)
        self._profile_worker.profile_result.connect(self._on_profile_result)
        self._profile_worker.finished.connect(self._profile_thread.quit)
        self._profile_worker.finished.connect(self._profile_worker.deleteLater)
        self._profile_thread.finished.connect(self._profile_thread.deleteLater)

        self._profile_thread.start()

    @Slot(bool, str)
    def _on_profile_result(self, found: bool, profile_path: str) -> None:
        self._profile_progress.hide()
        self._next_btn.setEnabled(True)

        if found:
            self._profile_path = profile_path
            self._profile_status.setText(
                f"✓ Profile found for <b>{self._codename}</b>"
            )
            self._profile_status.setStyleSheet("color: #39d353; font-size: 13px;")
        else:
            self._profile_status.setText(
                f"No profile found for <b>{self._codename}</b>. "
                "Generic defaults will be used."
            )
            self._profile_status.setStyleSheet("color: #e3b341; font-size: 13px;")
            self._profile_note.show()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def profile_path(self) -> str:
        """Path to the matched profile file, or '' if none found."""
        return self._profile_path
