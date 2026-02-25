# Changelog

All notable changes to CyberFlash are documented here.
Organized by development phase. Dates are approximate release milestones.

---

## [Phase 6] — 2026-02-25 — Advanced Root & Security

### Added
- `core/root_manager.py` extended — KernelSU module management, root profiles, superuser log
- `core/root_manager.py` — dm-verity control, force-encryption toggle, Root Hide / DenyList manager
- `core/root_manager.py` — banking-safe preset (one-click hiding for financial apps)
- `workers/integrity_worker.py` — Play Integrity / SafetyNet 3-tier checker (BASIC / DEVICE / STRONG)
- `workers/integrity_worker.py` — history logging to JSON file
- `core/kernel_manager.py` — AnyKernel3 flash via sideload and ADB push
- `core/kernel_manager.py` — boot image backup, rollback, kernel version verification
- `core/token_vault.py` — AES-256-GCM encrypted token storage
- `core/token_vault.py` — OS keychain integration via `keyring`, PBKDF2 key derivation
- `core/boot_animation_manager.py` — bootanimation.zip parse, install, backup, reset, frame extraction
- `ui/pages/magisk_modules_page.py` — Magisk module repo browser, search/filter, install worker
- `ui/pages/dashboard_page.py` — 3D hero phone pixmap via `get_hero_phone_pixmap()`

### Tests
- `test_root_manager_phase6.py` — 29 tests
- `test_kernel_manager.py` — 26 tests
- `test_token_vault.py` — 21 tests
- `test_boot_animation_manager.py` — 27 tests
- `test_integrity_worker.py` — 19 tests
- **Cumulative: 622 tests passing**

---

## [Phase 5] — 2026-02-24 — Multi-Brand Flash Support

### Added
- `core/heimdall_manager.py` — Samsung Heimdall: PIT parser, TAR flash, repartition support
- `core/xiaomi_manager.py` — MIUI/HyperOS: fastboot flash, ARB check, bootloader unlock flow
- `core/pixel_manager.py` — Google Pixel: factory image flash, bootloader/radio, OTA sideload
- `core/motorola_manager.py` — Motorola: RSA rescue (flashfile.xml), firmware dir flash, unlock code
- `ui/dialogs/device_wizard.py` — 4-step first-run wizard, brand-specific setup guides, profile check

### Tests
- `test_heimdall_manager.py` — 28 tests
- `test_xiaomi_manager.py` — 24 tests
- `test_pixel_manager.py` — 23 tests
- `test_motorola_manager.py` — 18 tests
- **Cumulative: 471 tests passing**

---

## [Phase 4 + ROM Engine] — 2026-02-20 — Diagnostics, Backup & ROM Downloads

### Added
- `workers/diagnostics_worker.py` — 31 ADB commands across 6 diagnostic categories
- `workers/diagnostics_worker.py` — `result_ready(category, key, value)` signal
- `workers/adb_log_worker.py` — Streaming logcat via QProcess with priority filter (V/D/I/W/E/F/S)
- `workers/backup_worker.py` — `adb_backup` and `pull_media` modes with abort flag
- `workers/download_worker.py` — Resumable chunked HTTP/HTTPS download with SHA-256 verification
- `workers/hash_worker.py` — Background SHA-256 / MD5 / SHA1 file checksum worker
- `core/rom_manager.py` — `DownloadState` / `DownloadRecord`, path helpers, JSON history persistence
- `ui/pages/diagnostics_page.py` — Logcat Start/Stop, device health card, wired to workers
- `ui/pages/rom_library_page.py` — Per-source download progress panel, history persistence

### Tests
- `test_diagnostics_worker.py` — 11 tests
- `test_backup_worker.py` — 8 tests
- `test_download_worker.py` — 9 tests
- `test_hash_worker.py` — 11 tests
- `test_rom_manager.py` — 22 tests
- **Cumulative: 342 tests passing**

---

## [Phase 3] — 2026-02-15 — Root Management

### Added
- `core/root_manager.py` — Magisk / KernelSU / APatch detection and boot patching
- `core/root_manager.py` — Module list, install, uninstall, enable/disable
- `core/payload_dumper.py` — Android OTA payload.bin extractor (inline protobuf, no external deps)
- `ui/pages/root_page.py` — Fully wired with `_RootWorker` inline, auto detect-root on device connect
- `ui/pages/root_page.py` — Flash patched boot image via fastboot

### Tests
- `test_root_manager.py` — 20 tests
- `test_payload_dumper.py` — 13 tests

---

## [Phase 2] — 2026-02-10 — Device Detection & Flash Engine

### Added
- `core/flash_engine.py` — Sequential flash step orchestrator with dry-run mode
- `core/flash_engine.py` — Returns `False` on failure (never raises), accepts `log_cb`
- `workers/flash_worker.py` — Wraps `FlashEngine` in a worker thread
- `services/device_service.py` — Owns `DevicePollWorker`, emits `device_list_updated`
- `ui/pages/flash_page.py` — Full flash workflow UI with step tracker and log panel
- `ui/pages/device_page.py` — Model, Android version, BL status, slot, serial display
- `ui/main_window.py` — `FramelessMainWindow`, `_CyberCentralWidget` (dot grid, trace lines, corner brackets)
- `ui/title_bar.py` — Frameless window controls, multi-device selector combo
- ADB + fastboot hot-plug device polling

### Tests
- `test_flash_engine_dry_run.py`
- `test_device_model.py`

---

## [Phase 1] — 2026-02-05 — Theme System & UI Scaffold

### Added
- `ui/themes/variables.py` — `ThemePalette` dataclasses for `cyber_dark`, `cyber_light`, `cyber_green`
- `ui/themes/theme_engine.py` — `ThemeEngine.apply_theme(name)` with `{TOKEN}` QSS substitution
- `ui/themes/cyber_dark.qss` — Primary cyberpunk dark theme
- `ui/sidebar.py` — Icon-based sidebar navigation
- `ui/widgets/` — `CyberCard`, `CyberBadge`, `StepTracker`, `ResizeGrip`
- All 7 page stubs with `setObjectName("pageRoot")` for transparent cyberpunk background
- `resources/profiles/oneplus/guacamole.json` — OnePlus 7 Pro device profile

---

## [Phase 0] — 2026-02-01 — Project Scaffold

### Added
- `pyproject.toml` — PySide6 6.x, adbutils, keyring, cryptography, requests, pytest-qt
- `src/cyberflash/` — Full package structure: `core/`, `workers/`, `services/`, `ui/`, `models/`, `utils/`
- `tests/conftest.py` — Session-scoped `QApplication` fixture (`qapp`)
- `.github/workflows/` — CI matrix for Linux, macOS, Windows
- `resources/profiles/schema.json` — Device profile JSON schema
- `resources/udev/51-cyberflash-edl.rules` — Linux udev rules for EDL devices
- `CLAUDE.md` — Architecture conventions and coding standards
- MIT License

---

*For the full feature roadmap see [ROADMAP](https://lchtangen.github.io/CyberFlash-Tool/roadmap.html)*
