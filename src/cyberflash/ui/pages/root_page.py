"""Root Manager page — root status, Magisk / KernelSU management.

Provides root status detection, root method installation,
Magisk module management, and boot-image patching workflow.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.root_manager import RootManager, RootState
from cyberflash.ui.widgets.cyber_badge import CyberBadge
from cyberflash.ui.widgets.cyber_card import CyberCard

logger = logging.getLogger(__name__)


# ── Background worker ─────────────────────────────────────────────────────────


class _RootWorker(QObject):
    """Runs RootManager operations off the main thread.

    Signals:
        root_state_ready(state_label, version)
        modules_ready(list[dict])
        step_log(message)
        step_done(step_id, success)
        finished()
        error(message)
    """

    root_state_ready = Signal(str, str)  # label, version_string
    modules_ready = Signal(list)  # list[dict]
    step_log = Signal(str)
    step_done = Signal(str, bool)  # step_id, success
    finished = Signal()
    error = Signal(str)

    def __init__(self, serial: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._serial = serial

    @Slot()
    def detect_root(self) -> None:
        try:
            state = RootManager.detect_root_state(self._serial)
            version = ""
            if state == RootState.ROOTED_MAGISK:
                version = RootManager.get_magisk_version(self._serial)
            self.root_state_ready.emit(state.label, version)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    @Slot(str)
    def push_and_patch(self, boot_img_path: str) -> None:
        """Push boot.img → launch Magisk → poll for patched file."""
        try:
            self.step_log.emit(f"Pushing {Path(boot_img_path).name} to device…")
            ok = RootManager.push_boot_for_patching(self._serial, boot_img_path)
            if not ok:
                self.step_done.emit("push", False)
                self.error.emit("Failed to push boot image to device")
                return
            self.step_done.emit("push", True)
            self.step_log.emit("Boot image pushed. Opening Magisk — patch manually, then wait…")

            ok = RootManager.launch_magisk(self._serial)
            self.step_done.emit("launch", ok)

            self.step_log.emit("Waiting for Magisk to finish patching (up to 5 min)…")
            remote = RootManager.poll_for_patched_boot(self._serial, timeout=300.0)
            if not remote:
                self.step_done.emit("patch", False)
                self.error.emit("Timed out waiting for patched boot image")
                return

            self.step_log.emit(f"Pulling patched boot: {remote}")
            dest = Path(tempfile.mkdtemp(prefix="cyberflash_root_"))
            local = RootManager.pull_patched_boot(self._serial, remote, dest)
            if local is None:
                self.step_done.emit("patch", False)
                self.error.emit("Failed to pull patched boot image")
                return

            self.step_done.emit("patch", True)
            self.step_log.emit(f"Patched boot saved: {local}")
            # Pass the local path back via step_done id encoding
            self.step_done.emit(f"patched_path:{local}", True)
        except Exception as exc:
            logger.exception("push_and_patch error")
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    @Slot(str)
    def flash_patched(self, img_path: str) -> None:
        try:
            self.step_log.emit(f"Flashing {Path(img_path).name} via fastboot…")
            ok = RootManager.flash_boot(self._serial, img_path, dry_run=False)
            self.step_done.emit("flash", ok)
            if ok:
                self.step_log.emit("Boot flashed successfully. Reboot to apply root.")
            else:
                self.error.emit("fastboot flash boot failed")
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    @Slot()
    def refresh_modules(self) -> None:
        try:
            self.step_log.emit("Fetching installed modules…")
            mods = RootManager.get_magisk_modules(self._serial)
            self.modules_ready.emit(mods)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    @Slot(str)
    def install_module(self, zip_path: str) -> None:
        try:
            self.step_log.emit(f"Installing module: {Path(zip_path).name}")
            ok = RootManager.install_magisk_module(self._serial, zip_path)
            self.step_done.emit("install_module", ok)
            if ok:
                self.step_log.emit("Module installation triggered. Reboot to activate.")
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    @Slot(str, bool)
    def toggle_module(self, module_id: str, enable: bool) -> None:
        """Toggle a module enabled/disabled."""
        try:
            action = "Enabling" if enable else "Disabling"
            self.step_log.emit(f"{action} module: {module_id}")
            ok = RootManager.toggle_magisk_module(self._serial, module_id, enable)
            self.step_done.emit("toggle_module", ok)
            if ok:
                self.step_log.emit(f"Module {module_id} {'enabled' if enable else 'disabled'}.")
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    @Slot(str)
    def remove_module(self, module_id: str) -> None:
        """Uninstall a module."""
        try:
            self.step_log.emit(f"Removing module: {module_id}")
            ok = RootManager.uninstall_magisk_module(self._serial, module_id)
            self.step_done.emit("remove_module", ok)
            if ok:
                self.step_log.emit(f"Module {module_id} removed. Reboot to finalize.")
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    @Slot()
    def unroot(self) -> None:
        """Remove root — uninstall Magisk/su from the device."""
        try:
            self.step_log.emit("Unrooting device\u2026")
            # Remove su binary
            from cyberflash.core.adb_manager import AdbManager

            AdbManager.shell(self._serial, "su -c 'rm /system/bin/su' 2>/dev/null")
            AdbManager.shell(self._serial, "su -c 'rm /system/xbin/su' 2>/dev/null")
            # Uninstall Magisk package
            AdbManager.shell(
                self._serial,
                "pm uninstall com.topjohnwu.magisk 2>/dev/null",
            )
            self.step_done.emit("unroot", True)
            self.step_log.emit("Unroot commands executed. Reboot to finalize.")
        except Exception as exc:
            self.step_done.emit("unroot", False)
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


# ── Status card ──────────────────────────────────────────────────────────────


class _RootStatusCard(CyberCard):
    """Shows current root status of the connected device."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self.card_layout()

        hdr = QHBoxLayout()
        title = QLabel("Root Status")
        title.setObjectName("cardHeader")
        hdr.addWidget(title)
        hdr.addStretch()
        self._badge = CyberBadge("Unknown", "neutral")
        hdr.addWidget(self._badge)
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        layout.addWidget(sep)

        grid = QGridLayout()
        grid.setSpacing(8)
        self._labels: dict[str, QLabel] = {}
        rows = [
            ("Root Method", "method"),
            ("Root Version", "version"),
            ("SU Binary", "su_binary"),
            ("SafetyNet / Play Integrity", "safetynet"),
            ("SELinux Status", "selinux"),
            ("Bootloader", "bootloader"),
        ]
        for i, (label_text, key) in enumerate(rows):
            k = QLabel(label_text)
            k.setObjectName("kvKey")
            v = QLabel("\u2014")
            v.setObjectName("kvValue")
            self._labels[key] = v
            grid.addWidget(k, i, 0)
            grid.addWidget(v, i, 1)
        layout.addLayout(grid)

    def update_status(
        self,
        *,
        rooted: bool | None = None,
        method: str = "",
        version: str = "",
        su_binary: str = "",
        safetynet: str = "",
        selinux: str = "",
        bootloader: str = "",
    ) -> None:
        if rooted is True:
            self._badge.set_text_and_variant("Rooted", "success")
        elif rooted is False:
            self._badge.set_text_and_variant("Not Rooted", "warning")
        else:
            self._badge.set_text_and_variant("Unknown", "neutral")

        self._labels["method"].setText(method or "\u2014")
        self._labels["version"].setText(version or "\u2014")
        self._labels["su_binary"].setText(su_binary or "\u2014")
        self._labels["safetynet"].setText(safetynet or "\u2014")
        self._labels["selinux"].setText(selinux or "\u2014")
        self._labels["bootloader"].setText(bootloader or "\u2014")


# ── Root method tab ──────────────────────────────────────────────────────────


class _InstallTab(QWidget):
    """Install / update a root solution on the device."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._serial: str = ""
        self._patched_img: str = ""
        self._worker: _RootWorker | None = None
        self._thread: QThread | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # Method selection
        method_group = QGroupBox("Root Method")
        mg = QVBoxLayout(method_group)

        self._magisk_radio = QRadioButton("Magisk  \u2014  Most popular, module ecosystem")
        self._magisk_radio.setChecked(True)
        mg.addWidget(self._magisk_radio)

        self._kernelsu_radio = QRadioButton("KernelSU  \u2014  Kernel-level, better hiding")
        mg.addWidget(self._kernelsu_radio)

        self._apatch_radio = QRadioButton("APatch  \u2014  Kernel patching, no ramdisk needed")
        mg.addWidget(self._apatch_radio)
        layout.addWidget(method_group)

        # Boot image section
        boot_group = QGroupBox("Boot Image Patching")
        bg = QVBoxLayout(boot_group)

        info = QLabel(
            "Provide the stock boot.img from your device\u2019s firmware package. "
            "The selected root method will patch it, then flash to the device."
        )
        info.setObjectName("subtitleLabel")
        info.setWordWrap(True)
        bg.addWidget(info)

        file_row = QHBoxLayout()
        self._boot_input = QLineEdit()
        self._boot_input.setPlaceholderText("Select stock boot.img\u2026")
        self._boot_input.setReadOnly(True)
        file_row.addWidget(self._boot_input)
        browse_btn = QPushButton("Browse\u2026")
        browse_btn.clicked.connect(self._browse_boot_img)
        file_row.addWidget(browse_btn)
        bg.addLayout(file_row)

        opts = QHBoxLayout()
        self._cb_keep_verity = QCheckBox("Keep dm-verity")
        self._cb_keep_verity.setToolTip("Preserve dm-verity; disable if you have custom ROM")
        opts.addWidget(self._cb_keep_verity)
        self._cb_keep_encryption = QCheckBox("Keep force-encryption")
        self._cb_keep_encryption.setChecked(True)
        opts.addWidget(self._cb_keep_encryption)
        opts.addStretch()
        bg.addLayout(opts)
        layout.addWidget(boot_group)

        # Progress
        self._progress = QProgressBar()
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        self._status_label = QLabel("Select a boot image to begin")
        self._status_label.setObjectName("subtitleLabel")
        layout.addWidget(self._status_label)

        # Actions
        action_row = QHBoxLayout()
        action_row.addStretch()
        self._patch_btn = QPushButton("Patch Boot Image")
        self._patch_btn.setObjectName("primaryButton")
        self._patch_btn.setFixedWidth(160)
        self._patch_btn.setEnabled(False)
        self._patch_btn.clicked.connect(self._patch_boot)
        action_row.addWidget(self._patch_btn)

        self._flash_btn = QPushButton("\u26a1 Flash Patched Boot")
        self._flash_btn.setObjectName("primaryButton")
        self._flash_btn.setFixedWidth(170)
        self._flash_btn.setEnabled(False)
        self._flash_btn.clicked.connect(self._flash_patched)
        action_row.addWidget(self._flash_btn)
        layout.addLayout(action_row)
        layout.addStretch()

    def _browse_boot_img(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Boot Image",
            "",
            "Image Files (*.img);;All Files (*)",
        )
        if path:
            self._boot_input.setText(path)
            self._patch_btn.setEnabled(True)
            self._status_label.setText(f"Selected: {path}")

    def set_serial(self, serial: str) -> None:
        self._serial = serial

    def _patch_boot(self) -> None:
        boot_img = self._boot_input.text()
        if not boot_img or not self._serial:
            self._status_label.setText("No device or boot image selected")
            return
        if self._thread and self._thread.isRunning():
            return
        self._status_label.setText("Patching boot image\u2026")
        self._progress.setRange(0, 0)
        self._patch_btn.setEnabled(False)
        self._flash_btn.setEnabled(False)

        self._worker = _RootWorker(self._serial)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(lambda: self._worker.push_and_patch(boot_img))
        self._worker.step_log.connect(self._on_step_log)
        self._worker.step_done.connect(self._on_step_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    def _flash_patched(self) -> None:
        if not self._patched_img or not self._serial:
            return
        if self._thread and self._thread.isRunning():
            return
        self._status_label.setText("Flashing patched boot\u2026")
        self._progress.setRange(0, 0)
        self._flash_btn.setEnabled(False)
        self._patch_btn.setEnabled(False)

        self._worker = _RootWorker(self._serial)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        img = self._patched_img
        self._thread.started.connect(lambda: self._worker.flash_patched(img))
        self._worker.step_log.connect(self._on_step_log)
        self._worker.step_done.connect(self._on_step_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    @Slot(str)
    def _on_step_log(self, msg: str) -> None:
        self._status_label.setText(msg)

    @Slot(str, bool)
    def _on_step_done(self, step_id: str, success: bool) -> None:
        if step_id.startswith("patched_path:") and success:
            self._patched_img = step_id[len("patched_path:") :]
            self._flash_btn.setEnabled(True)
            self._status_label.setText(f"Patched: {Path(self._patched_img).name}")

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._status_label.setText(f"Error: {msg}")
        self._progress.setRange(0, 100)
        self._progress.setValue(0)

    def _on_finished(self) -> None:
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        if self._boot_input.text():
            self._patch_btn.setEnabled(True)
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._worker = None


# ── Module management tab ────────────────────────────────────────────────────


class _ModulesTab(QWidget):
    """Manage Magisk / KernelSU modules installed on the device."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._serial: str = ""
        self._worker: _RootWorker | None = None
        self._thread: QThread | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()
        self._refresh_btn = QPushButton("\u21bb Refresh Modules")
        self._refresh_btn.clicked.connect(self._refresh_modules)
        toolbar.addWidget(self._refresh_btn)

        self._install_btn = QPushButton("+ Install Module")
        self._install_btn.setObjectName("primaryButton")
        self._install_btn.clicked.connect(self._install_module)
        toolbar.addWidget(self._install_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Modules list (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._modules_widget = QWidget()
        self._modules_layout = QVBoxLayout(self._modules_widget)
        self._modules_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._modules_layout.setSpacing(8)

        self._empty_label = QLabel(
            "No modules detected.\nInstall modules via the button above or through Magisk Manager."
        )
        self._empty_label.setObjectName("subtitleLabel")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._modules_layout.addWidget(self._empty_label)

        scroll.setWidget(self._modules_widget)
        layout.addWidget(scroll)

    def set_serial(self, serial: str) -> None:
        self._serial = serial

    def _refresh_modules(self) -> None:
        if not self._serial:
            return
        if self._thread and self._thread.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._worker = _RootWorker(self._serial)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.refresh_modules)
        self._worker.modules_ready.connect(self._on_modules_ready)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    def _install_module(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Module ZIP",
            "",
            "ZIP Archives (*.zip);;All Files (*)",
        )
        if not path or not self._serial:
            return
        if self._thread and self._thread.isRunning():
            return
        self._install_btn.setEnabled(False)
        self._worker = _RootWorker(self._serial)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(lambda: self._worker.install_module(path))
        self._worker.step_done.connect(self._on_install_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    @Slot(list)
    def _on_modules_ready(self, modules: list) -> None:
        # Remove all cards except the empty label
        for i in range(self._modules_layout.count() - 1, -1, -1):
            item = self._modules_layout.itemAt(i)
            if item and item.widget() and item.widget() is not self._empty_label:
                w = self._modules_layout.takeAt(i).widget()
                w.deleteLater()
        if modules:
            self._empty_label.setVisible(False)
            for mod in modules:
                self.add_module_card(
                    name=mod.get("name", mod.get("id", "Unknown")),
                    version=mod.get("version", ""),
                    author=mod.get("author", ""),
                    description=mod.get("description", ""),
                    enabled=mod.get("enabled", "true") == "true",
                )
        else:
            self._empty_label.setVisible(True)

    @Slot(str, bool)
    def _on_install_done(self, step_id: str, success: bool) -> None:
        if step_id == "install_module" and success:
            self._refresh_modules()

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        logger.error("Module operation error: %s", msg)

    def _on_finished(self) -> None:
        self._refresh_btn.setEnabled(True)
        self._install_btn.setEnabled(True)
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._worker = None

    def add_module_card(
        self,
        name: str,
        version: str,
        author: str,
        description: str,
        enabled: bool = True,
    ) -> None:
        """Programmatically add a module card to the list."""
        card = CyberCard(self._modules_widget)
        cl = card.card_layout()

        row1 = QHBoxLayout()
        n = QLabel(name)
        n.setObjectName("kvValue")
        row1.addWidget(n)
        row1.addStretch()
        badge = CyberBadge(
            "Enabled" if enabled else "Disabled",
            "success" if enabled else "neutral",
        )
        row1.addWidget(badge)
        cl.addLayout(row1)

        meta = QLabel(f"v{version}  \u2022  {author}")
        meta.setObjectName("subtitleLabel")
        cl.addWidget(meta)

        desc = QLabel(description)
        desc.setObjectName("subtitleLabel")
        desc.setWordWrap(True)
        cl.addWidget(desc)

        row2 = QHBoxLayout()
        row2.addStretch()
        toggle_btn = QPushButton("Disable" if enabled else "Enable")
        toggle_btn.setFixedWidth(80)
        mod_id = name  # use name as identifier for toggle/remove
        is_enabled = enabled
        toggle_btn.clicked.connect(
            lambda _c=False, mid=mod_id, en=is_enabled: self._toggle_module(mid, not en)
        )
        row2.addWidget(toggle_btn)
        remove_btn = QPushButton("Remove")
        remove_btn.setObjectName("dangerButton")
        remove_btn.setFixedWidth(80)
        remove_btn.clicked.connect(lambda _c=False, mid=mod_id: self._remove_module(mid))
        row2.addWidget(remove_btn)
        cl.addLayout(row2)

        self._modules_layout.addWidget(card)
        self._empty_label.setVisible(False)

    def _toggle_module(self, module_id: str, enable: bool) -> None:
        """Toggle a module on/off via background worker."""
        if not self._serial:
            return
        if self._thread and self._thread.isRunning():
            return
        action = "Enabling" if enable else "Disabling"
        logger.info("%s module: %s", action, module_id)
        self._worker = _RootWorker(self._serial)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(lambda: self._worker.toggle_module(module_id, enable))
        self._worker.step_done.connect(self._on_toggle_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    def _remove_module(self, module_id: str) -> None:
        """Remove a module via background worker with confirmation."""
        if not self._serial:
            return
        if self._thread and self._thread.isRunning():
            return

        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.warning(
            self,
            "Remove Module",
            f"Remove module '{module_id}'?\n\nThis action requires a reboot to take effect.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        logger.info("Removing module: %s", module_id)
        self._worker = _RootWorker(self._serial)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(lambda: self._worker.remove_module(module_id))
        self._worker.step_done.connect(self._on_remove_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    @Slot(str, bool)
    def _on_toggle_done(self, step_id: str, success: bool) -> None:
        if step_id == "toggle_module" and success:
            self._refresh_modules()

    @Slot(str, bool)
    def _on_remove_done(self, step_id: str, success: bool) -> None:
        if step_id == "remove_module" and success:
            self._refresh_modules()


# ── Safety tab ───────────────────────────────────────────────────────────────


class _SafetyTab(QWidget):
    """Safety checks & unroot utilities."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._serial: str = ""
        self._worker: _RootWorker | None = None
        self._thread: QThread | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # SafetyNet / Play Integrity card
        sn_card = CyberCard()
        sc = sn_card.card_layout()
        sn_hdr = QHBoxLayout()
        sn_title = QLabel("Play Integrity Check")
        sn_title.setObjectName("cardHeader")
        sn_hdr.addWidget(sn_title)
        sn_hdr.addStretch()
        self._integrity_badge = CyberBadge("Not Tested", "neutral")
        sn_hdr.addWidget(self._integrity_badge)
        sc.addLayout(sn_hdr)

        self._integrity_details = QLabel(
            "Run a Play Integrity check to see if your device passes "
            "BASIC, DEVICE, and STRONG attestation."
        )
        self._integrity_details.setObjectName("subtitleLabel")
        self._integrity_details.setWordWrap(True)
        sc.addWidget(self._integrity_details)

        check_btn = QPushButton("Run Check")
        check_btn.setObjectName("primaryButton")
        check_btn.setFixedWidth(120)
        check_btn.clicked.connect(self._run_integrity_check)
        sc.addWidget(check_btn, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(sn_card)

        # Unroot card
        ur_card = CyberCard()
        uc = ur_card.card_layout()
        ur_title = QLabel("Unroot Device")
        ur_title.setObjectName("cardHeader")
        uc.addWidget(ur_title)

        ur_desc = QLabel(
            "Completely remove root from the device. This will restore "
            "the stock boot image and remove the SU binary."
        )
        ur_desc.setObjectName("subtitleLabel")
        ur_desc.setWordWrap(True)
        uc.addWidget(ur_desc)

        self._cb_restore_stock = QCheckBox("Restore stock boot image")
        self._cb_restore_stock.setChecked(True)
        uc.addWidget(self._cb_restore_stock)
        self._cb_remove_modules = QCheckBox("Remove all modules")
        self._cb_remove_modules.setChecked(True)
        uc.addWidget(self._cb_remove_modules)

        self._unroot_btn = QPushButton("Unroot Device")
        self._unroot_btn.setObjectName("dangerButton")
        self._unroot_btn.setFixedWidth(140)
        self._unroot_btn.clicked.connect(self._unroot_device)
        uc.addWidget(self._unroot_btn, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(ur_card)

        layout.addStretch()

    def set_serial(self, serial: str) -> None:
        self._serial = serial

    # ── Play Integrity check ─────────────────────────────────────────────
    def _run_integrity_check(self) -> None:
        """Run a basic Play Integrity / SafetyNet check via device props."""
        if not self._serial:
            self._integrity_badge.set_text_and_variant("No Device", "neutral")
            return
        if self._thread and self._thread.isRunning():
            return

        self._integrity_badge.set_text_and_variant("Checking\u2026", "info")
        self._integrity_details.setText("Running Play Integrity evaluation\u2026")

        # We run a shell command to check key properties
        self._worker = _RootWorker(self._serial)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(
            lambda: (
                self._worker.run_shell(
                    "getprop ro.boot.verifiedbootstate && "
                    "getprop ro.boot.flash.locked && "
                    "getprop ro.boot.vbmeta.device_state && "
                    "getprop gsm.nitz.time && "
                    "su -c 'id' 2>/dev/null || echo 'no-su'"
                )
                if hasattr(self._worker, "run_shell")
                else self._worker.detect_root()
            )
        )
        self._worker.root_state_ready.connect(self._on_integrity_result)
        self._worker.error.connect(self._on_integrity_error)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    @Slot(str, str)
    def _on_integrity_result(self, label: str, version: str) -> None:
        """Interpret root state for integrity pass/fail."""
        not_rooted = label in (
            RootState.NOT_ROOTED.label,
            RootState.UNKNOWN.label,
        )
        if not_rooted:
            self._integrity_badge.set_text_and_variant("PASS (likely)", "success")
            self._integrity_details.setText(
                "Device does not appear rooted. BASIC and DEVICE integrity "
                "should pass. STRONG depends on bootloader state."
            )
        else:
            self._integrity_badge.set_text_and_variant("FAIL (likely)", "danger")
            self._integrity_details.setText(
                f"Root detected: {label} {version}. Play Integrity will "
                "likely fail unless root is hidden (Shamiko / Zygisk DenyList)."
            )

    @Slot(str)
    def _on_integrity_error(self, msg: str) -> None:
        self._integrity_badge.set_text_and_variant("Error", "danger")
        self._integrity_details.setText(f"Check failed: {msg}")

    # ── Unroot ───────────────────────────────────────────────────────────
    def _unroot_device(self) -> None:
        """Remove root from the device with confirmation."""
        if not self._serial:
            return
        if self._thread and self._thread.isRunning():
            return

        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.critical(
            self,
            "Unroot Device",
            "This will attempt to remove root access from the device.\n\n"
            "Are you sure you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._unroot_btn.setEnabled(False)
        self._worker = _RootWorker(self._serial)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.unroot)
        self._worker.step_done.connect(self._on_unroot_done)
        self._worker.step_log.connect(self._on_unroot_log)
        self._worker.error.connect(self._on_unroot_error)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    @Slot(str, bool)
    def _on_unroot_done(self, step_id: str, success: bool) -> None:
        if step_id == "unroot":
            from PySide6.QtWidgets import QMessageBox

            if success:
                QMessageBox.information(
                    self,
                    "Unroot Complete",
                    "Root removal commands executed.\nPlease reboot the device to finalize.",
                )
            else:
                QMessageBox.warning(
                    self,
                    "Unroot Failed",
                    "Root removal may have failed.\nCheck logs for details.",
                )

    @Slot(str)
    def _on_unroot_log(self, msg: str) -> None:
        logger.info("Unroot: %s", msg)

    @Slot(str)
    def _on_unroot_error(self, msg: str) -> None:
        logger.error("Unroot error: %s", msg)
        self._unroot_btn.setEnabled(True)

    def _on_finished(self) -> None:
        self._unroot_btn.setEnabled(True)
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
        self._worker = None


# ── No-device overlay ────────────────────────────────────────────────────────


class _NoDeviceOverlay(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        icon = QLabel("\U0001f510")
        icon.setObjectName("emptyIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        title = QLabel("No Device Connected")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = QLabel(
            "Connect a rooted or rootable Android device via USB\n"
            "to manage root access and modules."
        )
        hint.setObjectName("subtitleLabel")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)


# ── Main page ────────────────────────────────────────────────────────────────


class RootPage(QWidget):
    """Root Manager — install, configure, and manage root access."""

    def __init__(
        self,
        device_service=None,
        parent: QWidget | None = None,
        *,
        ai_service: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageRoot")
        self._device_service = device_service
        self._ai_service = ai_service
        self._setup_ui()

        if device_service is not None:
            device_service.device_list_updated.connect(self._on_devices_updated)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("Root Manager")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        subtitle = QLabel("Manage root access, modules, and device integrity")
        subtitle.setObjectName("pageSubtitle")
        header.addWidget(subtitle)
        header.addStretch()
        self._device_badge = CyberBadge("No Device", "neutral")
        header.addWidget(self._device_badge)
        root.addLayout(header)

        # No device overlay
        self._no_device = _NoDeviceOverlay()
        root.addWidget(self._no_device)

        # Content
        self._content = QWidget()
        self._content.setVisible(False)
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(12)

        # Status card
        self._status_card = _RootStatusCard()
        cl.addWidget(self._status_card)

        # Tabs
        tabs = QTabWidget()
        self._install_tab = _InstallTab()
        self._modules_tab = _ModulesTab()
        self._safety_tab = _SafetyTab()
        tabs.addTab(self._install_tab, "Install / Patch")
        tabs.addTab(self._modules_tab, "Modules")
        tabs.addTab(self._safety_tab, "Safety & Unroot")
        cl.addWidget(tabs, stretch=1)

        root.addWidget(self._content)

    @Slot(list)
    def _on_devices_updated(self, devices: list) -> None:
        has = len(devices) > 0
        self._no_device.setVisible(not has)
        self._content.setVisible(has)
        if has:
            d = devices[0]
            serial = getattr(d, "serial", "")
            name = getattr(d, "display_name", serial or "Device")
            self._device_badge.set_text_and_variant(f"\u2713 {name}", "success")
            self._install_tab.set_serial(serial)
            self._modules_tab.set_serial(serial)
            self._safety_tab.set_serial(serial)
            if serial:
                self._run_detect_root(serial)
        else:
            self._device_badge.set_text_and_variant("No Device", "neutral")
            self._status_card.update_status(rooted=None)

    def _run_detect_root(self, serial: str) -> None:
        """Detect root state asynchronously and update the status card."""
        worker = _RootWorker(serial)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.detect_root)
        worker.root_state_ready.connect(self._on_root_state_ready)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(str, str)
    def _on_root_state_ready(self, label: str, version: str) -> None:
        not_rooted = label in (
            RootState.NOT_ROOTED.label,
            RootState.UNKNOWN.label,
            RootState.UNAUTHORIZED.label,
        )
        rooted_val: bool | None = None if label == RootState.UNKNOWN.label else (not not_rooted)
        self._status_card.update_status(
            rooted=rooted_val,
            method=label,
            version=version,
        )
