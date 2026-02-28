from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.flash_engine import FlashEngine
from cyberflash.models.device import DeviceInfo
from cyberflash.models.flash_task import FlashStep, FlashTask, StepStatus
from cyberflash.models.profile import DeviceProfile
from cyberflash.profiles import ProfileRegistry
from cyberflash.services.device_service import DeviceService
from cyberflash.ui.dialogs.unlock_confirm import UnlockConfirmDialog
from cyberflash.ui.dialogs.wipe_confirm import WipeConfirmDialog
from cyberflash.ui.panels.log_panel import LogPanel
from cyberflash.ui.panels.progress_panel import ProgressPanel
from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.step_tracker import StepTracker
from cyberflash.workers.flash_worker import FlashWorker

logger = logging.getLogger(__name__)

# Default wipe options shown in the UI (label → profile wipe key)
_WIPE_OPTIONS: list[tuple[str, str, bool]] = [
    ("Dalvik / ART cache", "dalvik", True),
    ("Cache partition", "cache", True),
    ("Data (factory reset) \u26a0", "data", False),
    ("System", "system", False),
    ("Vendor", "vendor", False),
]

# Partitions that are safe to erase without bricking (high-level OS partitions).
# Used as fallback when profile.flash.erase_partitions is empty.
_SAFE_ERASE_DEFAULT: frozenset[str] = frozenset(
    {
        "boot",
        "dtbo",
        "vbmeta",
        "system",
        "vendor",
        "product",
        "odm",
        "LOGO",
        "oem_stanvbk",
    }
)

# Partitions where a flash failure is critical (non-skippable).
_CRITICAL_FLASH_PARTITIONS: frozenset[str] = frozenset(
    {
        "abl",
        "boot",
        "dtbo",
        "system",
        "vendor",
        "vbmeta",
        "xbl",
        "xbl_config",
        "tz",
        "hyp",
        "keymaster",
        "modem",
    }
)

_FLASH_STEPS_FASTBOOT: list[tuple[str, str, bool]] = [
    ("reboot_bootloader", "Reboot to bootloader", False),
    ("disable_vbmeta", "Disable vbmeta verification", False),
    ("flash_boot", "Flash boot partition", False),
    ("flash_dtbo", "Flash dtbo partition", False),
    ("flash_system", "Flash system partition", False),
    ("flash_vendor", "Flash vendor partition", False),
    ("flash_product", "Flash product partition", True),
    ("flash_odm", "Flash odm partition", True),
    ("set_active_slot", "Set active slot", False),
    ("reboot_system", "Reboot to system", False),
]

# Steps for Clean Slate (Erase + Reflash) — erases ALL partitions first
_FLASH_STEPS_CLEAN_SLATE: list[tuple[str, str, bool]] = [
    ("reboot_bootloader", "Reboot to bootloader", False),
    ("erase_boot", "\u2716 Erase boot", False),
    ("erase_dtbo", "\u2716 Erase dtbo", False),
    ("erase_system", "\u2716 Erase system", False),
    ("erase_vendor", "\u2716 Erase vendor", False),
    ("erase_product", "\u2716 Erase product", True),
    ("erase_odm", "\u2716 Erase odm", True),
    ("erase_userdata", "\u2716 Erase userdata (factory reset)", False),
    ("erase_cache", "\u2716 Erase cache", True),
    ("disable_vbmeta", "Disable vbmeta verification", False),
    ("flash_boot", "Flash boot partition", False),
    ("flash_dtbo", "Flash dtbo partition", False),
    ("flash_system", "Flash system partition", False),
    ("flash_vendor", "Flash vendor partition", False),
    ("flash_product", "Flash product partition", True),
    ("flash_odm", "Flash odm partition", True),
    ("flash_vbmeta", "Flash vbmeta partition", False),
    ("set_active_slot", "Set active slot", False),
    ("reboot_system", "Reboot to system", False),
]


class _DeviceBar(QWidget):
    """Top bar showing selected device info and status badges."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("deviceBar")
        self.setStyleSheet(
            "QWidget#deviceBar {  background: #161b22;  border-bottom: 1px solid #21262d;}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        self._name_label = QLabel("No device selected")
        self._name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self._name_label)

        self._state_badge = CyberBadge("—", "neutral")
        layout.addWidget(self._state_badge)

        self._slot_badge = CyberBadge("—", "neutral")
        layout.addWidget(self._slot_badge)

        self._bl_badge = CyberBadge("BL: —", "neutral")
        layout.addWidget(self._bl_badge)

        layout.addStretch()

    def update_device(self, info: DeviceInfo | None) -> None:
        if info is None:
            self._name_label.setText("No device selected")
            self._state_badge.set_text_and_variant("—", "neutral")
            self._slot_badge.set_text_and_variant("—", "neutral")
            self._bl_badge.set_text_and_variant("BL: —", "neutral")
            return

        self._name_label.setText(f"{info.display_name}  ({info.codename or info.serial})")
        self._state_badge.set_text_and_variant(info.state.label, info.state.badge_variant)
        self._slot_badge.set_text_and_variant(
            info.slot_label, "info" if info.has_ab_slots else "neutral"
        )

        if info.bootloader_unlocked is True:
            self._bl_badge.set_text_and_variant("BL: Unlocked", "success")
        elif info.bootloader_unlocked is False:
            self._bl_badge.set_text_and_variant("BL: Locked", "warning")
        else:
            self._bl_badge.set_text_and_variant("BL: Unknown", "neutral")


class _NoDeviceOverlay(QWidget):
    """Centered overlay shown when no device is selected."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        icon = QLabel("\U0001f4f1")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        layout.addWidget(icon)

        title = QLabel("No device selected")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = QLabel(
            "Select a device from the dropdown in the title bar,\n"
            "then return to the Flash page to begin."
        )
        hint.setObjectName("subtitleLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)


class FlashPage(QWidget):
    """Full flash workflow page for Phase 2."""

    def __init__(
        self,
        device_service: DeviceService | None = None,
        parent: QWidget | None = None,
        *,
        ai_service: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = device_service
        self._ai_service = ai_service
        self._discovery_service: object | None = None  # RomDiscoveryService
        self._current_device: DeviceInfo | None = None
        self._profile: DeviceProfile | None = None
        self._source_path: Path | None = None
        self._flash_thread: QThread | None = None
        self._flash_worker: FlashWorker | None = None

        self._setup_ui()
        self._connect_service()

        # Update device bar immediately if service already has a selection
        if self._service and self._service.selected_device:
            self._on_device_changed(self._service.selected_device)

    # ── UI setup ─────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Device info bar
        self._device_bar = _DeviceBar()
        root.addWidget(self._device_bar)

        # Stacked: overlay vs main content
        self._overlay = _NoDeviceOverlay()
        root.addWidget(self._overlay)

        self._main_content = self._build_main_content()
        root.addWidget(self._main_content)

        self._set_has_device(False)

    def _build_main_content(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Page title
        title_row = QHBoxLayout()
        title = QLabel("Flash ROM")
        title.setObjectName("titleLabel")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        # Splitter: left setup pane | right steps+log pane
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([420, 580])

        layout.addWidget(splitter, stretch=1)
        return container

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(16)

        # ── ROM / Image Source ────────────────────────────────────────────────
        layout.addWidget(self._section_label("ROM / Image Source"))

        source_row = QHBoxLayout()
        self._source_edit = QLineEdit()
        self._source_edit.setPlaceholderText("Select a directory, payload.bin, or OTA .zip…")
        self._source_edit.setReadOnly(True)
        source_row.addWidget(self._source_edit)

        self._source_type_label = QLabel("")
        self._source_type_label.setStyleSheet("font-size: 11px; color: #8b949e; margin-left: 4px;")

        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("secondaryButton")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_source)
        source_row.addWidget(browse_btn)

        self._catalog_btn = QPushButton("\u2605 Browse Catalog")
        self._catalog_btn.setObjectName("primaryButton")
        self._catalog_btn.setFixedWidth(130)
        self._catalog_btn.clicked.connect(self._browse_catalog)
        source_row.addWidget(self._catalog_btn)

        layout.addLayout(source_row)
        layout.addWidget(self._source_type_label)

        self._catalog_score_label = QLabel("")
        self._catalog_score_label.setObjectName("subtitleLabel")
        self._catalog_score_label.setStyleSheet("font-size: 11px; margin-left: 4px;")
        layout.addWidget(self._catalog_score_label)

        # ── Flash Method ──────────────────────────────────────────────────────
        layout.addWidget(self._section_label("Flash Method"))
        self._method_group = QButtonGroup(self)
        self._rb_fastboot = QRadioButton("Fastboot (images directory)")
        self._rb_clean_slate = QRadioButton("\u26a0 Clean Slate — Erase ALL + Reflash (unbrick)")
        self._rb_clean_slate.setStyleSheet("QRadioButton { color: #f0883e; font-weight: bold; }")
        self._rb_sideload = QRadioButton("Sideload (zip via ADB)")
        self._rb_recovery = QRadioButton("Recovery only (.img)")
        self._rb_fastboot.setChecked(True)
        for i, rb in enumerate(
            [self._rb_fastboot, self._rb_clean_slate, self._rb_sideload, self._rb_recovery]
        ):
            self._method_group.addButton(rb, i)
            layout.addWidget(rb)

        # Clean-slate helper text
        clean_hint = QLabel(
            "  Erases every partition, factory resets userdata, then flashes "
            "fresh images.\n  Use this to recover a soft-bricked device."
        )
        clean_hint.setObjectName("hintLabel")
        clean_hint.setStyleSheet(
            "QLabel#hintLabel { color: #8b949e; font-size: 11px; margin-left: 24px; }"
        )
        clean_hint.setWordWrap(True)
        layout.addWidget(clean_hint)

        # Reconnect method change to update step tracker
        self._method_group.idToggled.connect(self._on_method_changed)

        # ── Wipe Options ──────────────────────────────────────────────────────
        layout.addWidget(self._section_label("Wipe Options"))
        self._wipe_checkboxes: dict[str, QCheckBox] = {}
        for label, key, default in _WIPE_OPTIONS:
            cb = QCheckBox(label)
            cb.setChecked(default)
            self._wipe_checkboxes[key] = cb
            layout.addWidget(cb)

        layout.addStretch()

        # ── Action buttons ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()

        self._unlock_btn = QPushButton("\u26a0 Unlock BL")
        self._unlock_btn.setObjectName("dangerButton")
        self._unlock_btn.setStyleSheet(
            "QPushButton#dangerButton {"
            "  background: #b91c1c;"
            "  color: white;"
            "  border: none;"
            "  padding: 6px 12px;"
            "  border-radius: 4px;"
            "}"
            "QPushButton#dangerButton:hover { background: #f85149; }"
        )
        self._unlock_btn.clicked.connect(self._on_unlock_bl)
        btn_row.addWidget(self._unlock_btn)

        btn_row.addStretch()

        self._dry_run_btn = QPushButton("\u23fb Dry Run")
        self._dry_run_btn.setObjectName("secondaryButton")
        self._dry_run_btn.clicked.connect(lambda: self._start_flash(dry_run=True))
        btn_row.addWidget(self._dry_run_btn)

        self._start_btn = QPushButton("\u25b6 Start Flash")
        self._start_btn.setObjectName("primaryButton")
        self._start_btn.clicked.connect(lambda: self._start_flash(dry_run=False))
        btn_row.addWidget(self._start_btn)

        layout.addLayout(btn_row)

        # Abort button (hidden until flash in progress)
        self._abort_btn = QPushButton("\u25a0 Abort")
        self._abort_btn.setObjectName("dangerButton")
        self._abort_btn.setStyleSheet(
            "QPushButton#dangerButton { background: #b91c1c; color: white;"
            " border: none; padding: 6px 12px; border-radius: 4px; }"
        )
        self._abort_btn.setVisible(False)
        self._abort_btn.clicked.connect(self._on_abort)
        layout.addWidget(self._abort_btn)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(self._section_label("Flash Steps"))
        self._step_tracker = StepTracker()
        self._step_tracker.setMinimumHeight(200)
        layout.addWidget(self._step_tracker)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        layout.addWidget(sep)

        layout.addWidget(self._section_label("Log"))
        self._log_panel = LogPanel()
        self._log_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._log_panel, stretch=2)

        self._progress_panel = ProgressPanel()
        layout.addWidget(self._progress_panel)

        return panel

    # ── Section label helper ─────────────────────────────────────────────────

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionLabel")
        lbl.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #6e7681; text-transform: uppercase;"
        )
        return lbl

    # ── Device service wiring ─────────────────────────────────────────────────

    def _connect_service(self) -> None:
        if self._service:
            self._service.selected_device_changed.connect(self._on_device_changed)

    @Slot(object)
    def _on_device_changed(self, info: DeviceInfo | None) -> None:
        self._current_device = info
        self._device_bar.update_device(info)
        self._set_has_device(info is not None)

        if info:
            self._profile = ProfileRegistry.load(info.codename)
            self._populate_steps()

    def _set_has_device(self, has_device: bool) -> None:
        self._overlay.setVisible(not has_device)
        self._main_content.setVisible(has_device)

    # ── Steps population ─────────────────────────────────────────────────────

    def _populate_steps(self) -> None:
        if self._rb_clean_slate.isChecked():
            step_defs = self._build_clean_slate_step_defs()
        else:
            step_defs = _FLASH_STEPS_FASTBOOT
        steps = [
            FlashStep(id=sid, label=label, skippable=skippable)
            for sid, label, skippable in step_defs
        ]
        self._step_tracker.set_steps(steps)
        self._progress_panel.reset()

    def _build_clean_slate_step_defs(
        self,
    ) -> list[tuple[str, str, bool]]:
        """Build step definitions from the profile's actual partition list.

        Erase phase uses ``erase_partitions`` (safe subset — never includes
        low-level firmware like xbl/abl that are needed for fastboot).
        Flash phase uses the full ``partitions`` list, or — when a payload.bin
        is selected — dynamically discovers ALL partitions from the payload.
        """
        if self._profile:
            flash_parts = list(self._profile.flash.partitions)
            erase_parts = (
                list(self._profile.flash.erase_partitions)
                if self._profile.flash.erase_partitions
                else [p for p in flash_parts if p in _SAFE_ERASE_DEFAULT]
            )
        else:
            flash_parts = ["boot", "dtbo", "system", "vendor", "odm"]
            erase_parts = list(flash_parts)

        # If source is a payload, discover its partition list for the flash phase
        payload_parts: list[str] | None = None
        needs_extraction = False
        if self._source_path:
            src_type = FlashEngine.detect_source_type(self._source_path)
            if src_type in ("payload_bin", "ota_zip"):
                needs_extraction = True
                payload_parts = self._discover_payload_partitions(self._source_path)

        # Use payload partitions for flash phase when available
        if payload_parts is not None:
            flash_parts = payload_parts

        step_defs: list[tuple[str, str, bool]] = []
        step_defs.append(("reboot_bootloader", "Reboot to bootloader", False))

        # Insert extraction step if source is payload.bin or OTA zip
        if needs_extraction:
            step_defs.append(
                (
                    "extract_payload",
                    "\U0001f4e6 Extract partition images from payload",
                    False,
                )
            )

        # Erase phase — ONLY safe-to-erase partitions
        for p in erase_parts:
            step_defs.append((f"erase_{p}", f"\u2716 Erase {p}", p in ("odm", "oem_stanvbk")))
        step_defs.append(("erase_userdata", "\u2716 Erase userdata (factory reset)", False))
        step_defs.append(("erase_cache", "\u2716 Erase cache", True))

        # Flash phase — ALL partitions (from payload or profile)
        step_defs.append(("disable_vbmeta", "Disable vbmeta verification", False))
        for p in flash_parts:
            skippable = p not in _CRITICAL_FLASH_PARTITIONS
            step_defs.append((f"flash_{p}", f"Flash {p}", skippable))

        step_defs.append(("set_active_slot", "Set active slot", False))
        step_defs.append(("reboot_system", "Reboot to system", False))
        return step_defs

    @staticmethod
    def _discover_payload_partitions(source: Path) -> list[str] | None:
        """Read partition names from a payload.bin or OTA zip.

        Returns the list of partition names, or None if the payload
        could not be opened.
        """
        try:
            from cyberflash.core.payload_dumper import PayloadDumper

            actual = source
            if source.is_dir() and (source / "payload.bin").exists():
                actual = source / "payload.bin"
            dumper = PayloadDumper(actual)
            parts = dumper.list_partitions()
            dumper.close()
            return parts
        except Exception:
            return None

    @Slot(int, bool)
    def _on_method_changed(self, button_id: int, checked: bool) -> None:
        """Repopulate step tracker when flash method changes."""
        if checked and self._current_device:
            self._populate_steps()

    # ── Discovery service wiring ──────────────────────────────────────────────

    def set_discovery_service(self, svc: object) -> None:
        """Bind the ROM discovery service (enables Browse Catalog button)."""
        self._discovery_service = svc

    def _browse_catalog(self) -> None:
        """Open the ROM catalog picker and populate the source field."""
        from cyberflash.ui.dialogs.rom_select_dialog import RomSelectDialog

        if self._discovery_service is None:
            return

        codename = (
            self._current_device.codename
            if self._current_device and self._current_device.codename
            else ""
        )
        dlg = RomSelectDialog(self._discovery_service, codename, self)
        dlg.rom_selected.connect(self._on_catalog_rom_selected)
        dlg.exec()

    @Slot(object)
    def _on_catalog_rom_selected(self, entry: object) -> None:
        """Populate the ROM source field from a CatalogEntry."""
        from cyberflash.core.rom_catalog import CatalogEntry

        if not isinstance(entry, CatalogEntry):
            return

        if entry.download_path:
            self._set_source(Path(entry.download_path))
        else:
            # Show URL as placeholder — user needs to download first
            self._source_edit.setText(entry.url)
            self._source_edit.setToolTip(
                "ROM not downloaded yet. Use the ROM Catalog tab to download it first."
            )

        from cyberflash.core.rom_ai_scorer import RomScore

        grade = RomScore.grade_from_score(entry.ai_score)
        self._catalog_score_label.setText(
            f"\u2605 Catalog pick: {entry.distro} {entry.version} — "
            f"AI score [{grade}] {entry.ai_score:.0f}/100"
        )

    # ── Browse for ROM source ─────────────────────────────────────────────────

    def _browse_source(self) -> None:
        if self._rb_sideload.isChecked():
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Sideload Zip", "", "Zip Files (*.zip)"
            )
            if path:
                self._set_source(Path(path))
        elif self._rb_recovery.isChecked():
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Recovery Image", "", "Image Files (*.img)"
            )
            if path:
                self._set_source(Path(path))
        else:
            # Fastboot / Clean Slate: accept dir, payload.bin, or OTA zip
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Firmware Source",
                "",
                "All Supported (payload.bin *.zip);;OTA Zip (*.zip);;"
                "Payload Binary (payload.bin);;All Files (*)",
            )
            if path:
                self._set_source(Path(path))
            else:
                # Fall back to directory selection
                dir_path = QFileDialog.getExistingDirectory(self, "Select Images Directory", "")
                if dir_path:
                    self._set_source(Path(dir_path))

    def _set_source(self, path: Path) -> None:
        """Set the source path and detect its type."""
        self._source_path = path
        self._source_edit.setText(str(path))

        source_type = FlashEngine.detect_source_type(path)
        type_labels = {
            "payload_bin": "\u2705 Detected: Android OTA payload.bin",
            "ota_zip": "\u2705 Detected: OTA zip (contains payload.bin)",
            "img_dir": "\u2705 Detected: Directory with .img files",
            "unknown": "\u26a0 Unknown source type — may not contain flashable images",
        }
        self._source_type_label.setText(type_labels.get(source_type, ""))

        if source_type == "unknown":
            self._source_type_label.setStyleSheet(
                "font-size: 11px; color: #f0883e; margin-left: 4px;"
            )
        else:
            self._source_type_label.setStyleSheet(
                "font-size: 11px; color: #3fb950; margin-left: 4px;"
            )

        # Re-populate steps in case we need to insert extract step
        if self._current_device:
            self._populate_steps()

    # ── Unlock bootloader ─────────────────────────────────────────────────────

    def _on_unlock_bl(self) -> None:
        if not self._current_device:
            return
        if not self._profile:
            QMessageBox.warning(
                self,
                "No Profile",
                f"No device profile found for codename '{self._current_device.codename}'.",
            )
            return

        dlg = UnlockConfirmDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._log_panel.append_line("Starting bootloader unlock…")
        from cyberflash.core.flash_engine import FlashEngine

        engine = FlashEngine(
            self._current_device.serial,
            log_cb=self._log_panel.append_line,
        )
        ok = engine.unlock_bootloader(self._profile)
        if ok:
            self._log_panel.append_line("Bootloader unlock completed.")
        else:
            self._log_panel.append_line("Bootloader unlock FAILED — check log above.")

    # ── Start / abort flash ───────────────────────────────────────────────────

    def _start_flash(self, dry_run: bool = False) -> None:
        if not self._current_device:
            return

        if not dry_run and not self._source_path:
            QMessageBox.warning(
                self,
                "No Source Selected",
                "Please select a ROM directory or zip file before starting.",
            )
            return

        # Clean Slate requires extra confirmation
        is_clean_slate = self._rb_clean_slate.isChecked()
        if is_clean_slate and not dry_run:
            reply = QMessageBox.warning(
                self,
                "\u26a0 Clean Slate — Erase EVERYTHING",
                "This will ERASE ALL PARTITIONS including userdata "
                "(factory reset) and then flash fresh images.\n\n"
                "ALL DATA ON THE DEVICE WILL BE PERMANENTLY LOST.\n\n"
                "This operation is intended for unbricking soft-bricked "
                "devices. Are you absolutely sure?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Check for data wipe confirmation
        selected_wipes = [k for k, cb in self._wipe_checkboxes.items() if cb.isChecked()]
        if selected_wipes and not dry_run and not is_clean_slate:
            dlg = WipeConfirmDialog(selected_wipes, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

        # ── Preflight safety checks ──────────────────────────────────────
        if not dry_run and self._source_path:
            try:
                from cyberflash.core.preflight_checker import PreflightChecker
                from cyberflash.ui.dialogs.preflight_dialog import PreflightDialog

                checker = PreflightChecker(
                    self._current_device.serial if self._current_device else "",
                )
                result = checker.check_flash(str(self._source_path))

                if not result.passed:
                    dlg = PreflightDialog(result, parent=self)
                    if dlg.exec() != QDialog.DialogCode.Accepted:
                        self._log_panel.append_line("Flash aborted — preflight checks not passed.")
                        return
                    self._log_panel.append_line("Preflight warnings acknowledged — proceeding.")
                else:
                    self._log_panel.append_line(f"Preflight passed: {result.summary}")
            except Exception as exc:
                logger.warning("Preflight check failed: %s", exc)
                self._log_panel.append_line(f"Preflight check error (proceeding): {exc}")

        profile = self._profile
        if not profile and not dry_run:
            codename = self._current_device.codename or "unknown"
            QMessageBox.warning(
                self,
                "No Profile",
                f"No device profile found for '{codename}'.\n"
                "Flash will proceed with generic steps.",
            )

        if is_clean_slate:
            steps = self._build_clean_slate_steps()
        else:
            steps = self._build_flash_steps(selected_wipes)
        task = FlashTask(
            device_serial=self._current_device.serial,
            profile_codename=(profile.codename if profile else "generic"),
            steps=steps,
            dry_run=dry_run,
        )

        if profile is None:
            from cyberflash.models.profile import BootloaderConfig, FlashConfig

            profile = DeviceProfile(
                codename="generic",
                name="Generic Device",
                brand="",
                model="",
                ab_slots=self._current_device.has_ab_slots,
                bootloader=BootloaderConfig(
                    unlock_command="fastboot oem unlock",
                    requires_oem_unlock_menu=True,
                    warn_data_wipe=True,
                ),
                flash=FlashConfig(method="fastboot", partitions=[]),
                wipe_partitions={},
            )

        self._run_flash_worker(task, profile)

    def _build_clean_slate_steps(self) -> list[FlashStep]:
        """Build the step list for clean-slate erase + reflash."""
        step_defs = self._build_clean_slate_step_defs()
        steps: list[FlashStep] = []

        # Detect source type to decide how to wire image paths
        src_type = (
            FlashEngine.detect_source_type(self._source_path) if self._source_path else "unknown"
        )
        needs_extraction = src_type in ("payload_bin", "ota_zip")

        for sid, label, skippable in step_defs:
            step = FlashStep(id=sid, label=label, skippable=skippable)

            if sid == "extract_payload" and self._source_path:
                step._source_path = self._source_path  # type: ignore[attr-defined]

            # Attach image paths for flash_* steps from pre-extracted directory
            if sid.startswith("flash_") and self._source_path and not needs_extraction:
                partition = sid[len("flash_") :]
                img = self._source_path / f"{partition}.img"
                if img.exists():
                    step._image_path = img  # type: ignore[attr-defined]
            # If needs_extraction, _image_path will be set by the worker
            # after the extract_payload step runs

            steps.append(step)
        return steps

    def _build_flash_steps(self, wipe_keys: list[str]) -> list[FlashStep]:
        steps: list[FlashStep] = []

        if self._rb_fastboot.isChecked():
            for sid, label, skippable in _FLASH_STEPS_FASTBOOT:
                steps.append(FlashStep(id=sid, label=label, skippable=skippable))
        elif self._rb_sideload.isChecked():
            steps.append(FlashStep(id="reboot_bootloader", label="Reboot to bootloader"))
            steps.append(FlashStep(id="reboot_system", label="Reboot to recovery"))
        else:
            steps.append(FlashStep(id="reboot_bootloader", label="Reboot to bootloader"))
            steps.append(FlashStep(id="flash_recovery", label="Flash recovery image"))
            steps.append(FlashStep(id="reboot_system", label="Reboot to system"))

        for key in wipe_keys:
            if key == "dalvik":
                steps.append(FlashStep(id="wipe_dalvik", label="Wipe Dalvik/ART cache"))
            else:
                steps.append(
                    FlashStep(
                        id=f"wipe_{key}",
                        label=f"Wipe {key} partition",
                        skippable=True,
                    )
                )

        return steps

    def _run_flash_worker(self, task: FlashTask, profile: DeviceProfile) -> None:
        self._step_tracker.set_steps(task.steps)
        self._progress_panel.reset()
        self._log_panel.append_line(
            f"Preparing {'DRY RUN' if task.dry_run else 'flash'} for "
            f"{task.profile_codename} on {task.device_serial}…"
        )

        self._set_controls_enabled(False)
        self._abort_btn.setVisible(True)

        worker = FlashWorker(task, profile)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.start)
        worker.step_started.connect(self._on_step_started)
        worker.step_completed.connect(self._on_step_completed)
        worker.step_failed.connect(self._on_step_failed)
        worker.log_line.connect(self._log_panel.append_line)
        worker.progress.connect(self._on_progress)
        worker.flash_complete.connect(self._on_flash_complete)
        worker.error.connect(self._on_flash_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self._flash_thread = thread
        self._flash_worker = worker
        thread.start()

    def _on_abort(self) -> None:
        if self._flash_thread and self._flash_thread.isRunning():
            self._flash_thread.requestInterruption()
            self._log_panel.append_line("Abort requested — waiting for current step…")

    # ── Worker signal handlers ────────────────────────────────────────────────

    @Slot(str)
    def _on_step_started(self, step_id: str) -> None:
        self._step_tracker.update_step(step_id, StepStatus.ACTIVE)

    @Slot(str)
    def _on_step_completed(self, step_id: str) -> None:
        self._step_tracker.update_step(step_id, StepStatus.COMPLETED)

    @Slot(str, str)
    def _on_step_failed(self, step_id: str, message: str) -> None:
        self._step_tracker.update_step(step_id, StepStatus.FAILED)
        self._log_panel.append_line(f"FAILED [{step_id}]: {message}")

    @Slot(int, int)
    def _on_progress(self, current: int, total: int) -> None:
        self._progress_panel.update_progress(current, total, "")

    @Slot()
    def _on_flash_complete(self) -> None:
        self._log_panel.append_line("Flash completed successfully!")
        self._progress_panel.update_progress(1, 1, "Complete")
        QMessageBox.information(
            self, "Flash Complete", "Flash completed successfully!\nYou may now reboot your device."
        )

    @Slot(str)
    def _on_flash_error(self, message: str) -> None:
        self._log_panel.append_line(f"ERROR: {message}")
        QMessageBox.critical(self, "Flash Failed", f"Flash failed:\n\n{message}")

    @Slot()
    def _on_thread_finished(self) -> None:
        self._flash_thread = None
        self._flash_worker = None
        self._set_controls_enabled(True)
        self._abort_btn.setVisible(False)

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in [
            self._unlock_btn,
            self._dry_run_btn,
            self._start_btn,
            self._rb_fastboot,
            self._rb_clean_slate,
            self._rb_sideload,
            self._rb_recovery,
        ]:
            widget.setEnabled(enabled)
        for cb in self._wipe_checkboxes.values():
            cb.setEnabled(enabled)
