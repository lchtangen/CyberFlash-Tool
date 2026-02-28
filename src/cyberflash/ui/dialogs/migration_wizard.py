"""migration_wizard.py — Device-to-device data migration wizard.

A multi-step dialog that guides users through transferring contacts,
SMS, app data, and media between two connected Android devices.

Steps:
  0 — Select source and destination devices
  1 — Choose what to migrate (contacts, SMS, apps, media)
  2 — Review summary and confirm
  3 — Migration in progress
  4 — Done / results
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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

# ── Step constants ────────────────────────────────────────────────────────────

_STEP_SELECT   = 0
_STEP_OPTIONS  = 1
_STEP_CONFIRM  = 2
_STEP_RUNNING  = 3
_STEP_DONE     = 4

_STEP_TITLES = [
    "Select Devices",
    "Migration Options",
    "Review & Confirm",
    "Migrating…",
    "Migration Complete",
]


# ── Data ──────────────────────────────────────────────────────────────────────


@dataclass
class MigrationOptions:
    """What to migrate."""

    contacts: bool = True
    sms: bool = True
    call_log: bool = False
    media: bool = False
    app_data: bool = False


@dataclass
class MigrationResult:
    """Result summary after migration completes."""

    contacts_copied: int = 0
    sms_copied: int = 0
    media_copied: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


# ── Worker ────────────────────────────────────────────────────────────────────


class _MigrationWorker(BaseWorker):
    """Performs the actual migration in a background thread."""

    progress    = Signal(int, str)   # percent, message
    completed   = Signal(object)     # MigrationResult

    def __init__(
        self,
        source: str,
        destination: str,
        options: MigrationOptions,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._destination = destination
        self._options = options

    @Slot()
    def start(self) -> None:  # type: ignore[override]
        result = MigrationResult()
        try:
            step = 0
            total = sum([
                self._options.contacts,
                self._options.sms,
                self._options.call_log,
                self._options.media,
                self._options.app_data,
            ]) or 1

            if self._options.contacts:
                self.progress.emit(int(step / total * 90), "Migrating contacts…")
                result.contacts_copied = self._migrate_contacts()
                step += 1

            if self._options.sms:
                self.progress.emit(int(step / total * 90), "Migrating SMS…")
                result.sms_copied = self._migrate_sms()
                step += 1

            if self._options.media:
                self.progress.emit(int(step / total * 90), "Migrating media…")
                self._migrate_media()
                step += 1

            self.progress.emit(100, "Done")
            self.completed.emit(result)

        except Exception as exc:
            result.errors.append(str(exc))
            logger.exception("MigrationWorker error")
            self.error.emit(str(exc))
            self.completed.emit(result)
        finally:
            self.finished.emit()

    def _migrate_contacts(self) -> int:
        """Pull contacts from source and push to destination."""
        import tempfile
        from pathlib import Path

        from cyberflash.core.contacts_manager import ContactsManager

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            if not ContactsManager.backup_contacts(self._source, tmp_path, log_cb=logger.debug):
                return 0
            vcf_files = list(tmp_path.glob("*.vcf"))
            if not vcf_files:
                return 0
            ok = ContactsManager.restore_contacts(self._destination, vcf_files[0], log_cb=logger.debug)
            return ContactsManager.count_contacts(self._source) if ok else 0

    def _migrate_sms(self) -> int:
        """Pull SMS from source and push to destination."""
        import tempfile
        from pathlib import Path

        from cyberflash.core.contacts_manager import ContactsManager

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            if not ContactsManager.backup_sms(self._source, tmp_path, log_cb=logger.debug):
                return 0
            xml_files = list(tmp_path.glob("*.xml"))
            if not xml_files:
                return 0
            ok = ContactsManager.restore_sms(self._destination, xml_files[0], log_cb=logger.debug)
            return ContactsManager.count_sms(self._source) if ok else 0

    def _migrate_media(self) -> None:
        """Basic media sync via adb pull / adb push."""
        import tempfile
        from pathlib import Path

        from cyberflash.core.adb_manager import AdbManager

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            AdbManager.pull(self._source, "/sdcard/DCIM/", str(tmp_path / "dcim"))
            AdbManager.push(self._destination, str(tmp_path / "dcim"), "/sdcard/DCIM/")


# ── Wizard ────────────────────────────────────────────────────────────────────


class MigrationWizard(QDialog):
    """Step-by-step dialog for phone-to-phone data migration.

    Args:
        devices: List of connected device serials (at least two required).
        parent: Optional Qt parent widget.
    """

    migration_completed = Signal(object)  # MigrationResult

    def __init__(self, devices: list[str], parent=None) -> None:
        super().__init__(parent)
        self._devices = devices
        self._options = MigrationOptions()
        self._thread: QThread | None = None
        self._worker: _MigrationWorker | None = None
        self._result: MigrationResult | None = None

        self.setWindowTitle("Device Migration Wizard")
        self.setMinimumSize(520, 420)
        self._build_ui()
        self._go_to(0)

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Header
        self._header_label = QLabel()
        self._header_label.setStyleSheet("font-size: 15px; font-weight: bold; padding: 8px 0;")
        root.addWidget(self._header_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # Stacked pages
        self._stack = QStackedWidget()
        root.addWidget(self._stack, stretch=1)

        self._stack.addWidget(self._make_select_page())
        self._stack.addWidget(self._make_options_page())
        self._stack.addWidget(self._make_confirm_page())
        self._stack.addWidget(self._make_running_page())
        self._stack.addWidget(self._make_done_page())

        # Nav buttons
        nav = QHBoxLayout()
        nav.addStretch()
        self._btn_back = QPushButton("← Back")
        self._btn_back.clicked.connect(self._on_back)
        self._btn_next = QPushButton("Next →")
        self._btn_next.clicked.connect(self._on_next)
        self._btn_close = QPushButton("Close")
        self._btn_close.clicked.connect(self.reject)
        nav.addWidget(self._btn_back)
        nav.addWidget(self._btn_next)
        nav.addWidget(self._btn_close)
        root.addLayout(nav)

    def _make_select_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Select source and destination devices:"))
        layout.addSpacing(8)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Source device:"))
        self._src_combo = QComboBox()
        for d in self._devices:
            self._src_combo.addItem(d)
        row1.addWidget(self._src_combo)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Destination:"))
        self._dst_combo = QComboBox()
        for d in self._devices:
            self._dst_combo.addItem(d)
        if len(self._devices) > 1:
            self._dst_combo.setCurrentIndex(1)
        row2.addWidget(self._dst_combo)
        layout.addLayout(row2)

        layout.addStretch()
        return w

    def _make_options_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Choose what to migrate:"))
        self._chk_contacts = QCheckBox("Contacts")
        self._chk_contacts.setChecked(True)
        self._chk_sms = QCheckBox("SMS Messages")
        self._chk_sms.setChecked(True)
        self._chk_call_log = QCheckBox("Call Log")
        self._chk_media = QCheckBox("Photos & Videos (DCIM)")
        self._chk_app_data = QCheckBox("App data (requires root)")
        for chk in [self._chk_contacts, self._chk_sms, self._chk_call_log,
                    self._chk_media, self._chk_app_data]:
            layout.addWidget(chk)
        layout.addStretch()
        return w

    def _make_confirm_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self._confirm_label = QLabel()
        self._confirm_label.setWordWrap(True)
        scroll = QScrollArea()
        scroll.setWidget(self._confirm_label)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        return w

    def _make_running_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self._progress_bar = QProgressBar()
        self._progress_label = QLabel("Preparing…")
        layout.addStretch()
        layout.addWidget(self._progress_label)
        layout.addWidget(self._progress_bar)
        layout.addStretch()
        return w

    def _make_done_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self._done_label = QLabel()
        self._done_label.setWordWrap(True)
        self._done_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        layout.addWidget(self._done_label)
        layout.addStretch()
        return w

    # ── Navigation ────────────────────────────────────────────────────────────

    def _go_to(self, step: int) -> None:
        self._stack.setCurrentIndex(step)
        self._header_label.setText(
            f"Step {step + 1}/{len(_STEP_TITLES)}: {_STEP_TITLES[step]}"
        )
        self._btn_back.setVisible(0 < step < _STEP_RUNNING)
        self._btn_next.setVisible(step < _STEP_RUNNING)
        self._btn_close.setVisible(step in (_STEP_SELECT, _STEP_DONE))
        self._btn_next.setText("Start Migration" if step == _STEP_CONFIRM else "Next →")

    def _on_next(self) -> None:
        current = self._stack.currentIndex()
        if current == _STEP_SELECT:
            self._go_to(_STEP_OPTIONS)
        elif current == _STEP_OPTIONS:
            self._collect_options()
            self._update_confirm_page()
            self._go_to(_STEP_CONFIRM)
        elif current == _STEP_CONFIRM:
            self._go_to(_STEP_RUNNING)
            self._start_migration()

    def _on_back(self) -> None:
        current = self._stack.currentIndex()
        if current > 0:
            self._go_to(current - 1)

    # ── Option collection / confirm ───────────────────────────────────────────

    def _collect_options(self) -> None:
        self._options.contacts = self._chk_contacts.isChecked()
        self._options.sms = self._chk_sms.isChecked()
        self._options.call_log = self._chk_call_log.isChecked()
        self._options.media = self._chk_media.isChecked()
        self._options.app_data = self._chk_app_data.isChecked()

    def _update_confirm_page(self) -> None:
        src = self._src_combo.currentText()
        dst = self._dst_combo.currentText()
        items = []
        if self._options.contacts:
            items.append("✓ Contacts")
        if self._options.sms:
            items.append("✓ SMS Messages")
        if self._options.call_log:
            items.append("✓ Call Log")
        if self._options.media:
            items.append("✓ Photos & Videos")
        if self._options.app_data:
            items.append("✓ App Data")
        item_str = "<br>".join(items) if items else "(nothing selected)"
        self._confirm_label.setText(
            f"<b>Source:</b> {src}<br>"
            f"<b>Destination:</b> {dst}<br><br>"
            f"<b>Will migrate:</b><br>{item_str}<br><br>"
            "<i>This will not delete data from the source device.</i>"
        )

    # ── Migration ─────────────────────────────────────────────────────────────

    def _start_migration(self) -> None:
        src = self._src_combo.currentText()
        dst = self._dst_combo.currentText()
        self._thread = QThread(self)
        self._worker = _MigrationWorker(src, dst, self._options)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._worker.progress.connect(self._on_progress)
        self._worker.completed.connect(self._on_completed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_progress(self, pct: int, msg: str) -> None:
        self._progress_bar.setValue(pct)
        self._progress_label.setText(msg)

    def _on_completed(self, result: MigrationResult) -> None:
        self._result = result
        if result.success:
            details = (
                f"<b style='color:#2ea043'>Migration completed successfully!</b><br><br>"
                f"Contacts copied: {result.contacts_copied}<br>"
                f"SMS copied: {result.sms_copied}<br>"
            )
        else:
            errors = "<br>".join(f"• {e}" for e in result.errors)
            details = f"<b style='color:#f85149'>Errors occurred:</b><br>{errors}"
        self._done_label.setText(details)
        self._go_to(_STEP_DONE)
        self.migration_completed.emit(result)
