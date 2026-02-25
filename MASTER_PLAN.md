# CyberFlash — Master Plan & Development Roadmap

> **Status**: Active Development — Phases 0–4 + ROM Engine COMPLETE
> **Framework**: Python 3.12+ + PySide6 6.x (Qt 6) — confirmed production decision
> **Dev Environment**: VS Code + GitHub Copilot (agents) + Claude Code
> **Start Device**: OnePlus 7 Pro (guacamole) with Kali NetHunter
> **Target Platforms**: Linux · macOS · Windows
> **License**: MIT Open Source
> **Test Suite**: 471 tests passing · Lint: ruff clean
> **Vision**: The definitive all-in-one Android device management and ROM flashing
>             desktop application — no competitor covers every feature in a single package.
>             195+ planned features across 21 development phases.

---

## Why Python + PySide6 (Not Tauri / Electron)

After evaluating Tauri 2 + React + Rust and Electron + Node.js alternatives, Python + PySide6
remains the correct foundation for CyberFlash because:

- `adbutils` v2.12 (Nov 2025, 31k downloads/week) is battle-tested for Android automation
- Zero existing Tauri-based Android flashing tools = no precedent for debugging ADB edge cases
- Python flash sequences are debuggable instantly with no compile cycle
- ADB protocol quirks and device-specific bugs already solved in the Python ecosystem
- Community can contribute automation scripts, profiles, and plugins without knowing Rust/Go
- `QProcess` gives us native async subprocess streaming, perfect for ADB/fastboot output
- Distribution size (~300 MB) is acceptable for a professional-grade desktop tool
- Qt 6's signal/slot system is the gold standard for multi-threaded desktop app architecture
- PySide6 QSS allows pixel-perfect cyberpunk visual identity unachievable in webview apps

**Core principle:** A bad flash can brick a device. **Reliability > aesthetics.**
Python gives us both — reliable automation first, beautiful UI second.

---

## Product Vision

CyberFlash is the **market-leading all-in-one Android device management and ROM flashing desktop
application**. It replaces every fragmented tool in the Android modding ecosystem:

| Replaced Tool | CyberFlash Equivalent |
|---|---|
| ADB / fastboot CLI | GUI wrapper + terminal emulator |
| Samsung Odin / Heimdall | Built-in Samsung flash engine |
| MIUI Unlock Tool | Xiaomi unlock flow |
| MSMDownloadTool | EDL (Emergency Download Mode) |
| Magisk Manager (PC-side) | Root page + module browser |
| MindTheGapps installer | Extras installer |
| TWRP installer scripts | Recovery flasher |
| ROM Manager (dead) | ROM Library + download queue |
| scrcpy | Screen capture / mirror (Phase 9) |
| adbcontrol | App manager + file manager |
| FlashFire | Automated flash workflow builder |

**No competitor — TWRP App, Universal Android Flasher, Flashify, or Minimal ADB — covers
even 30% of CyberFlash's planned feature set in a single cross-platform desktop package.**

---

## Confirmed Technical Decisions

| Decision | Choice | Reason |
|---|---|---|
| GUI framework | **PySide6 (Qt 6.x)** | QProcess, QThread, LGPL, mature ecosystem |
| Language | **Python 3.12+** | ADB tooling, pip ecosystem, instant debugging |
| Theme system | **Custom QSS + ThemeEngine** | Token substitution, runtime switching, cyberpunk aesthetic |
| ADB execution | **QProcess (primary) + adbutils** | Streaming output + device enumeration |
| Packaging | **pyside6-deploy + GitHub Actions** | Official Qt tool, CI matrix builds |
| Test framework | **pytest + pytest-qt** | QApplication fixture, signal testing |
| Linter | **ruff** | Fast, zero-config, enforced in CI |
| Type checker | **mypy** | Public API type safety |
| Workers | **QObject.moveToThread** | Never subclass QThread; BaseWorker pattern |
| License | **MIT** | Community-friendly, PySide6 LGPL compatible |
| Device profiles | **JSON files** | Pluggable, version-controlled, community-contributable |
| Config storage | **QSettings (INI)** | Cross-platform, typed getters, value_changed signal |
| Download history | **JSON flat file** | Portable, human-readable, no SQLite dep |

---

## Architecture Layer Boundaries (STRICT)

```
┌─────────────────────────────────────────────┐
│  ui/pages/  ui/panels/  ui/widgets/         │  Qt widgets only — no subprocess/IO
│  ui/dialogs/  ui/themes/                    │
├─────────────────────────────────────────────┤
│  workers/        (QObject + moveToThread)   │  Async bridge — signals/slots only
├─────────────────────────────────────────────┤
│  services/       (own workers, emit to UI)  │  Long-running monitors
├─────────────────────────────────────────────┤
│  core/           (NO Qt widget imports)     │  Pure logic — callable from tests
├─────────────────────────────────────────────┤
│  models/         (dataclasses only)         │  Data transfer objects
├─────────────────────────────────────────────┤
│  utils/          (stdlib + platform utils)  │  Helpers — no business logic
└─────────────────────────────────────────────┘
```

**Rules enforced in code review:**
- `core/` never imports from `PySide6.QtWidgets`
- Workers never call `core/` from the main thread
- Pages never call ADB/fastboot directly — always through workers or services
- QSS color tokens live exclusively in `ui/themes/variables.py`

---

## Complete Feature Inventory

### TIER 1 — Core Flash Engine (Production Ready)
- [x] ADB device detection + hot-plug polling
- [x] fastboot device detection
- [x] Multi-device selector (title bar combo)
- [x] Device info page (model, Android, BL status, slot, serial)
- [x] Flash engine — sequential step orchestration with dry-run
- [x] OnePlus 7 Pro (guacamole) full device profile
- [x] Bootloader unlock flow with danger confirmation
- [x] Custom ROM flash (fastboot + recovery sideload methods)
- [x] A/B slot management + active slot switching
- [x] vbmeta patching (disable-verity flag)
- [x] Wipe operations: cache, dalvik, data, system, vendor, userdata
- [x] ANSI-colorized real-time log panel
- [x] Step tracker widget with status indicators
- [x] Dry-run mode (all operations simulated)

### TIER 2 — Root & Security (Production Ready)
- [x] Root state detection (Magisk / KernelSU / APatch / other / unrooted)
- [x] Magisk boot image patching workflow (push → launch → poll → pull → flash)
- [x] KernelSU + APatch detection
- [x] Magisk module list, install, uninstall, enable/disable
- [x] payload.bin OTA extractor (inline protobuf parser, no deps)
- [x] Root page fully wired with QThread workers
- [x] Auto root detection on device connect
- [x] Flash patched boot via fastboot

### TIER 3 — ROM Library & Downloads (Production Ready)
- [x] ROM source monitoring with trust scoring (AI-powered)
- [x] Trust dimensions: Availability, Safety, Speed, Reputation
- [x] Source flagging + warning system
- [x] Resumable chunked HTTP/HTTPS download (DownloadWorker)
- [x] SHA-256 post-download verification (HashWorker)
- [x] Download history persistence (RomManager)
- [x] Download progress panel + speed display per source card
- [x] Already-downloaded detection on page load
- [x] Cancel active download

### TIER 4 — Diagnostics & Terminal (Production Ready)
- [x] 31-command ADB diagnostics across 6 categories
- [x] Device health card (battery, temp, storage, RAM)
- [x] Streaming logcat via QProcess (AdbLogWorker)
- [x] Priority filter (V/D/I/W/E/F/S)
- [x] Interactive ADB shell terminal with command history
- [x] Quick-command toolbar
- [x] Application log viewer (last 50K chars)
- [x] Environment check card (adb/fastboot/python/udev)

### TIER 5 — Backup & Partition (Production Ready)
- [x] ADB backup (-apk -shared -all)
- [x] ADB pull media (DCIM, Downloads, etc.)
- [x] Backup abort/cancel
- [x] Partition table scan (/proc/partitions)
- [x] A/B slot manager with safety confirmation
- [x] NetHunter install page (sideload + TWRP methods)

### TIER 6 — Visual & UX (Production Ready)
- [x] Frameless window with custom title bar
- [x] Collapsible navigation sidebar with icons
- [x] Cyberpunk circuit-board background (dot grid + trace lines + corner brackets)
- [x] CyberCard, CyberBadge, CyberButton widget library
- [x] Transparent page roots over cyberpunk background
- [x] Settings page (theme, device, flash, logging, downloads)
- [x] Custom status bar with severity levels
- [x] Resizable frameless window grips
- [x] AI assistant panel (collapsible right panel)

---

## Implementation Phases — Completed

### ✅ Phase 0: Project Scaffold
- Python package structure, pyproject.toml, ruff, mypy, pytest-qt
- PySide6 main window skeleton (frameless, sidebar, stacked pages)
- ThemeEngine with QSS token substitution
- GitHub Actions CI (lint + test on push)
- Bundled ADB/fastboot binaries (fetch_tools.py)

### ✅ Phase 1: Device Detection MVP
- `core/adb_manager.py` — QProcess ADB wrapper
- `core/fastboot_manager.py` — QProcess fastboot wrapper
- `core/device_detector.py` — polling + adbutils enumeration
- `workers/device_poll_worker.py` — QTimer 2s polling
- Dashboard page with live device cards
- Device selector combo in title bar + device info page

### ✅ Phase 2: OnePlus 7 Pro — Full Flash Workflow
- `profiles/oneplus/guacamole.json` — complete device profile
- `core/flash_engine.py` — sequence orchestrator
- `workers/flash_worker.py` — background flash thread
- Flash page with step tracker + real-time log
- Bootloader unlock, OrangeFox Recovery, custom ROM flash
- Wipe operations, A/B slots, vbmeta patcher
- EDL (Emergency Download Mode) page + dialogs

### ✅ Phase 3: Root & NetHunter Core
- `core/root_manager.py` — Magisk/KernelSU/APatch
- `core/payload_dumper.py` — OTA payload.bin extractor
- Root page + NetHunter page fully implemented

### ✅ Phase 4: All Pages + Workers + ROM Engine
- Cyberpunk `_CyberCentralWidget` background
- All 7 stub pages replaced with full implementations
- `workers/diagnostics_worker.py` — 31 ADB commands
- `workers/backup_worker.py` — adb_backup + pull_media
- `workers/download_worker.py` — resumable chunked download
- `workers/hash_worker.py` — background SHA256/MD5/SHA1
- `workers/adb_log_worker.py` — QProcess streaming logcat
- `core/rom_manager.py` — DownloadRecord + history persistence
- ROM Library page wired with download queue
- DiagnosticsPage logcat + health card wired
- RootPage fully wired (push → patch → flash)
- **342 tests passing · ruff lint clean**
- AI assistant service + panel integrated

---

## Implementation Phases — Completed (cont.)

### ✅ Phase 5: Multi-Brand Device Support
**Goal:** Expand beyond OnePlus to cover the 4 biggest Android brands.

- [x] **Samsung Heimdall engine** — `core/heimdall_manager.py`
  - Heimdall CLI wrapper (TAR → Odin package format)
  - Binary PIT partition table parser (magic validation + entry iteration)
  - Flash BL, AP, CP, CSC partitions individually + re-partition support
  - `inspect_odin_package()` — section→filenames mapping from TAR

- [x] **Xiaomi fastboot unlock** — `core/xiaomi_manager.py`
  - Mi Unlock guidance + `oem unlock` + `flashing unlock` support
  - MIUI/HyperOS fastboot flash from tgz/directory (full partition map)
  - Anti-rollback level check (`check_anti_rollback()`)
  - Device info via `getprop`: ARB level, region, MIUI version

- [x] **Google Pixel factory images** — `core/pixel_manager.py`
  - `flash_factory_image()` — full flash-all.sh automation in Python
  - Inner image ZIP extraction + partition ordered flash
  - `flash_bootloader()`, `flash_radio()`, `sideload_ota()` helpers
  - All Pixel 4a–9 Pro codenames mapped
  - `flashing_unlock()` + `flashing_lock()` bootloader management

- [x] **Motorola rescue** — `core/motorola_manager.py`
  - `rescue_flash()` — parses `flashfile.xml` (RSA firmware format)
  - `inspect_firmware()` — supports zip/tgz/directory firmware packages
  - `get_unlock_code()` — retrieves hash for motorola.com/unlockr
  - Edge/G/Razr codename map, carrier lock detection

- [x] **Device Wizard** — `ui/dialogs/device_wizard.py`
  - 4-step QDialog wizard: Identify → Profile → Setup Guide → Done
  - Auto-check local profile via `_ProfileCheckWorker` (QThread)
  - Brand-specific setup guides (OnePlus, Samsung, Xiaomi, Google, Motorola)
  - `_StepBar` widget with progress indicators

- **129 new tests** · Total: **471 tests passing** · ruff clean

---

## Implementation Phases — Upcoming

---

### Phase 6: Advanced Root & Security Tooling
**Goal:** The most capable root management suite on any desktop platform.

- [x] **Magisk Module Repository Browser** — `ui/pages/magisk_modules_page.py`
  - Browse official Magisk module repo (JSON feed)
  - Search by name, category (Audio, System, Xposed)
  - One-click download + install via RootManager
  - Installed module version comparison / update checker
  - Community-rated modules with star badges

- [x] **KernelSU Manager** — extend `core/root_manager.py`
  - KernelSU module support (`/data/adb/ksu/modules/`)
  - Root profile management (per-app grant/deny)
  - Superuser log viewer (which apps requested root)

- [x] **Play Integrity / SafetyNet Checker** — `workers/integrity_worker.py`
  - Run BASIC + DEVICE + STRONG attestation via device-side helper
  - Visual result card (pass/fail per tier)
  - Suggestions for fixing failures (Shamiko, DenyList, etc.)
  - Historical results log

- [x] **dm-verity & Force-Encryption Manager** — extend `core/root_manager.py`
  - Toggle dm-verity in vbmeta via fastboot
  - Force-encryption flag management
  - AVB key revocation guidance

- [x] **AnyKernel3 Flasher** — `core/kernel_manager.py`
  - AnyKernel3 zip detection (META-INF/com/google/android/update-binary)
  - Automated flash via recovery sideload or direct ADB push
  - Kernel version verification post-flash
  - Rollback support (save current kernel before flash)

- [x] **Secure Token Vault** — `core/token_vault.py`
  - AES-256-GCM encrypted storage for Mi Unlock tokens, Samsung lock codes
  - OS keychain integration (libsecret / macOS Keychain / Windows DPAPI)
  - Per-device credential management

---

### Phase 7: ROM Intelligence & Community Integration
**Goal:** Transform ROM Library from a link monitor into a full ROM management platform.

- [ ] **Live ROM Feed Aggregator** — `core/rom_feed.py`
  - Parse official release feeds: LineageOS, PixelExperience, crDroid, ArrowOS,
    CalyxOS, GrapheneOS, /e/OS, Evolution X, Nameless AOSP
  - Filter by device codename (auto-matched to connected device)
  - Sort by: release date, download count, changelog quality
  - Async background refresh with configurable interval

- [ ] **ROM Metadata Engine** — `core/rom_metadata.py`
  - Parse Android version from ROM filename or manifest
  - Security patch level extraction
  - GApps inclusion detection (stock / vanilla / MicroG)
  - Kernel source link detection
  - Changelog parser (XDA thread scraper + official release notes)

- [ ] **Download Queue Manager** — `ui/panels/download_queue_panel.py`
  - Simultaneous downloads with configurable concurrency (1-4)
  - Pause / resume individual downloads
  - Priority reordering (drag-to-reorder)
  - Bandwidth throttle slider (KB/s limit)
  - Auto-verify hash after every download
  - Total downloaded / remaining display

- [ ] **ROM Comparison Tool** — `ui/dialogs/rom_compare_dialog.py`
  - Side-by-side comparison of 2 ROM versions/builds
  - Highlight: Android version change, security patch delta, size diff
  - Show shared vs. unique features

- [ ] **Device Profile Community Hub** — `services/profile_hub_service.py`
  - Browse device profiles from `cyberflash-profiles` GitHub repo
  - Download and install profiles in one click
  - Submit new profiles via PR (open GitHub in browser)
  - Profile version tracking + auto-update notifications

---

### Phase 8: Device Interaction & Management
**Goal:** Replace every ADB-side GUI tool with built-in CyberFlash features.

- [ ] **ADB Wireless Pairing** — `core/wireless_adb.py`
  - Android 11+ WiFi debugging via `adb pair` (QR code or PIN)
  - mDNS device discovery on local network
  - QR code generator widget + scan instructions
  - Auto-reconnect on IP change

- [ ] **App Manager** — `ui/pages/app_manager_page.py`
  - List all installed APKs (user + system) with icons, version, size
  - Batch uninstall / disable system apps (with safety warnings)
  - APK backup (pull to local + auto-name with package + version)
  - APK install from local file or URL (side-loading)
  - Freeze/unfreeze apps without root (ADB disable)

- [ ] **File Manager** — `ui/pages/file_manager_page.py`
  - ADB-based file browser (tree view + list view)
  - Drag-and-drop push/pull between local and device
  - Preview images and text files inline
  - Root file access (via `su -c ls`) when rooted
  - Batch operations: copy, move, delete, compress

- [ ] **Screen Capture & Mirror** — `core/screen_manager.py`
  - ADB `screencap` single screenshot (PNG save)
  - `screenrecord` video capture with configurable bitrate/resolution
  - Real-time screen mirror via scrcpy subprocess integration
  - Input injection (keyboard + mouse → device events)

- [ ] **Clipboard Sync** — `core/clipboard_manager.py`
  - Push desktop clipboard to device: `adb shell am broadcast --es text "..."`
  - Pull device clipboard to desktop
  - Auto-sync mode (bidirectional, poll every 2s)
  - History of last 20 clipboard entries

- [ ] **Shell Script Executor** — extend terminal page
  - Script editor (syntax-highlighted, Python's `QSyntaxHighlighter`)
  - Run `.sh` scripts on device via `adb shell < script.sh`
  - Built-in script library: system tune-ups, log capture, benchmark
  - Save / load script presets

---

### Phase 9: Automation & Workflow Engine
**Goal:** Enable power users and CI/CD pipelines to automate complex multi-step device workflows.

- [ ] **Visual Workflow Builder** — `ui/pages/workflow_page.py`
  - Drag-and-drop step composer (cards on a canvas)
  - Step types: flash partition, reboot mode, run ADB command, wait, verify, install APK
  - Conditional steps: "if root check fails → run Magisk patch"
  - Save workflows as `.cyberflow` JSON files (shareable)
  - Template library: "Fresh install", "Root + NetHunter", "Clean ROM swap"

- [ ] **Multi-Device Batch Operations** — `workers/batch_worker.py`
  - Select N devices from device list
  - Run same workflow on all simultaneously (per-device QThread)
  - Progress dashboard showing all device states in parallel
  - Stop individual device without affecting others
  - Summary report: X/N succeeded

- [ ] **Flash History & Audit Journal** — `core/flash_journal.py`
  - Append-only JSON log of every flash operation
  - Stores: timestamp, device serial, model, operation, steps, success/fail, duration
  - Journal page: searchable, filterable by date/device/operation type
  - Export journal as CSV or HTML report

- [ ] **Scheduled Operations** — `services/scheduler_service.py`
  - Schedule flash jobs: "Run at 2am when device is connected"
  - Powered by QTimer + system idle detection
  - Notification when scheduled job completes
  - Useful for overnight ROM testing workflows

- [ ] **CLI Mode / Headless** — `cyberflash/cli.py`
  - `python -m cyberflash flash --device guacamole --rom /path/to/rom.zip`
  - `python -m cyberflash root --method magisk --boot-img boot.img`
  - `python -m cyberflash backup --serial DEVICE1234 --dest /backups/`
  - Machine-readable JSON output (`--json` flag) for CI integration
  - All flash engine features accessible without GUI

---

### Phase 10: Advanced Diagnostics & Analytics
**Goal:** Give users unparalleled insight into device health, performance, and security.

- [ ] **Device Health Score** — `core/health_scorer.py`
  - AI-computed score 0–100 from: battery health, storage health,
    CPU temp, uptime, root integrity, boot warnings
  - Score history chart (sparkline over last 30 days)
  - Actionable recommendations per score component
  - Export health report as PDF

- [ ] **Battery Analytics** — `workers/battery_monitor_worker.py`
  - Real-time battery level + charge rate monitoring (poll every 30s)
  - Charge cycle count estimation
  - Capacity degradation graph over time
  - Alert on temperature spike (> 45°C)

- [ ] **Performance Profiler** — `workers/perf_worker.py`
  - CPU frequency + governor monitoring per core
  - RAM pressure tracking (MemAvailable trend)
  - I/O stats from `/proc/diskstats`
  - Real-time charts (QChart if available, else ASCII sparklines)
  - Export as JSON for analysis

- [ ] **Logcat Intelligence** — enhance `AdbLogWorker`
  - Auto-detect crash signatures (FATAL EXCEPTION, ANR, native crash)
  - Highlight stack traces in the log viewer
  - One-click export of crash context (10s before crash)
  - Filter presets: crashes only, app-specific, system only

- [ ] **Security Audit Report** — `core/security_auditor.py`
  - Check: SELinux mode, bootloader state, root status, debug flags
  - Detect developer options, USB debugging, unknown sources
  - Check for known CVEs in installed Android version (NVD API)
  - Generate pass/warn/fail report card

---

### Phase 11: UI/UX Polish & Accessibility
**Goal:** Match professional desktop software in every interaction detail.

- [ ] **Animated Cyberpunk Transitions** — enhance ThemeEngine
  - Page transition: slide + fade between sidebar navigation items
  - Scan-line reveal animation on page load
  - Button press ripple effects (QPropertyAnimation)
  - Progress bars with glow pulse animation

- [ ] **Theme Studio** — `ui/pages/theme_studio_page.py`
  - Visual color token editor (pick any of the 20 ThemePalette values)
  - Live preview as you change colors
  - Save custom themes as `.cybertheme` JSON files
  - Import community themes from URL

- [ ] **Collapsible Sidebar Mega-Menu** — enhance Sidebar
  - Two-level navigation: main icon → sub-items flyout panel
  - Sub-pages per main section (e.g., Root → Modules / Integrity / Boot)
  - Recent pages history (last 5 visited)
  - Keyboard navigation (Alt+1 through Alt+9)

- [ ] **Keyboard Shortcuts System** — `services/shortcut_service.py`
  - Configurable global hotkeys (QShortcut)
  - Default bindings: Ctrl+D=Dashboard, Ctrl+F=Flash, Ctrl+T=Terminal
  - Shortcut cheat sheet dialog (? key)
  - Import/export shortcut presets

- [ ] **Notification Center** — `ui/panels/notification_panel.py`
  - System tray icon with badge count
  - In-app notification drawer (slide-in from right)
  - Notification types: flash complete, download done, device connected, error
  - Platform notifications (libnotify / macOS NSUserNotification / Win10 toast)

- [ ] **Onboarding Tour** — `ui/dialogs/onboarding_dialog.py`
  - First-launch interactive walkthrough (6 steps)
  - Highlight key UI elements with animated spotlight
  - Feature discovery hints ("Did you know? Drag files onto Flash page to auto-select")
  - Skip / resume from settings

- [ ] **Accessibility Mode** — extend ThemeEngine
  - High-contrast variant of Cyber Dark (WCAG AA compliant contrast ratios)
  - Font size scaling (75% to 150%) affecting all UI text
  - Reduced motion mode (disable all animations)
  - Full keyboard navigation (tab order, focus rings)
  - Screen reader compatible QAccessible labels

---

### Phase 12: Plugin & Extension System
**Goal:** Allow community developers to extend CyberFlash without forking the codebase.

- [ ] **Plugin API** — `cyberflash/plugins/`
  - `PluginBase` abstract class: `name`, `version`, `author`, `pages`, `workers`
  - Plugins as Python packages installed via pip or local folder
  - Plugin manifest: `cyberflash_plugin.json` (schema validated)
  - Hot-reload in dev mode; sandboxed in production
  - Plugin manager page: list, enable/disable, update, remove

- [ ] **Custom Page Slots** — extend Sidebar
  - Plugins can register additional sidebar pages
  - Plugin pages appear in an "Extensions" section
  - Plugin pages inherit CyberCard / CyberBadge widget library

- [ ] **Custom Worker Registry** — `services/worker_registry.py`
  - Plugins register background workers by name
  - Workers can be invoked from the workflow builder
  - Inter-plugin signals via event bus

- [ ] **Scripting Console** — `ui/pages/scripting_page.py`
  - In-app Python REPL with full access to `adb_manager`, `flash_engine`, `root_manager`
  - Syntax highlighting + auto-complete (jedi integration)
  - Save/load scripts as `.py` files
  - Script output in log panel

---

### Phase 13: CI/CD, Packaging & Release
**Goal:** Professional release pipeline across all 3 platforms.

- [ ] **GitHub Actions matrix build**
  - `build-linux.yml` → Ubuntu 22.04 → AppImage + .deb
  - `build-macos.yml` → macOS 13 → .app + .dmg (codesigned)
  - `build-windows.yml` → Windows Server 2022 → .exe (NSIS installer) + .msi (WiX)
  - `release.yml` → tag push triggers all 3 + attaches artifacts to GitHub Release
  - `tests.yml` → pytest on all 3 platforms on every PR

- [ ] **In-App Update System** — `services/update_service.py`
  - Check GitHub Releases API on startup (non-blocking)
  - Show update banner if newer version available
  - Download update in background (DownloadWorker)
  - Verify installer SHA-256 before launching
  - Delta update support (binary patch for minor versions)

- [ ] **Crash Reporter** — `services/crash_service.py`
  - Uncaught exception hook (QApplication.instance().notify override)
  - Collect: traceback, OS info, Python/Qt version, last 100 log lines
  - Optionally send to GitHub Issues (user consent prompt)
  - Local crash dump written to `~/.local/share/CyberFlash/crashes/`

- [ ] **Telemetry (opt-in)** — `services/telemetry_service.py`
  - Anonymous usage stats: feature usage counts, flash success/fail ratio
  - Zero PII — no serial numbers, no file paths
  - Opt-in prompt on first launch; disable anytime in settings
  - Helps prioritize which features to invest in

- [ ] **Documentation Generator** — `scripts/generate_docs.py`
  - Auto-generate device profile schema docs from JSON schema
  - Generate plugin API reference from docstrings (pdoc)
  - GitHub Pages deployment in CI

---

### Phase 14: Community & Ecosystem
**Goal:** Build CyberFlash into a community-driven platform, not just a tool.

- [ ] **Profile Repository** — `cyberflash-profiles` GitHub org repo
  - JSON schema v2 with extended fields: flash_method, edl_config, unlock_guide_url
  - CI validation on every PR (schema check + lint)
  - Profile count badge in README (target: 200+ devices at launch)
  - Auto-import to CyberFlash via Profile Hub (Phase 7)

- [ ] **ROM Source Directory** — community-curated ROM feed
  - Verified trusted ROM sources (LineageOS, PixelExperience, etc.)
  - Community-submitted sources with trust score history
  - Automated takedown workflow for flagged/broken sources

- [ ] **Discord Integration (optional)** — `services/discord_service.py`
  - Post flash completion / error to user's configured Discord webhook
  - Flash summary embed: device, ROM, result, duration
  - Useful for flashing meetup groups and ROM testers

- [ ] **Localization (i18n)** — `utils/i18n.py`
  - Qt Linguist `.ts` file workflow
  - Languages at launch: English, Spanish, French, German, Portuguese, Chinese (Simplified)
  - RTL layout support (Arabic, Hebrew) via Qt's built-in mirroring
  - Community translation via Weblate

- [ ] **User Guide & Wiki** — `docs/`
  - MkDocs + Material theme
  - Per-page feature guides with screenshots
  - Device-specific flashing guides (auto-generated from profiles)
  - Plugin development tutorial
  - GitHub Pages auto-deploy

---

### Phase 15: AI Intelligence & Autonomous Operations
**Goal:** Elevate the AI agent from advisory to a full autonomous operations engine
that can reason, plan, and execute multi-step device workflows end-to-end.

- [ ] **AI Autonomous Flash Wizard** — `core/ai_flash_planner.py`
  - End-to-end: detect device → select compatible ROM → preflight → flash → verify
  - Multi-turn planning: AI generates a step-by-step plan, user approves, AI executes
  - Rollback-aware: saves boot/recovery images before destructive steps
  - Natural language progress narration during execution
  - Post-flash health check + root state verification

- [ ] **Natural Language Device Control** — extend `core/ai_engine.py`
  - Parse commands like "unlock bootloader and flash LineageOS 21"
  - Intent classification: flash, root, backup, diagnose, reboot, shell
  - Entity extraction: ROM name, device codename, partition names
  - Ambiguity resolution dialog ("Did you mean LineageOS for guacamole or guacamoleb?")
  - Context memory: "flash the same ROM on my other device"

- [ ] **AI Error Diagnosis Engine** — `core/ai_error_analyzer.py`
  - Automatic stack trace analysis from logcat / flash logs
  - Pattern library: 100+ known failure signatures (FAILED (remote: unknown), etc.)
  - Root cause classification: USB issue, firmware mismatch, locked BL, corrupt image
  - Multi-step fix suggestions with one-click execution
  - Community-fed error knowledge base (anonymized error → fix pairs)

- [ ] **Predictive Device Health** — `core/ai_health_predictor.py`
  - Battery degradation curve fitting — predict months until < 80% capacity
  - Storage wear-level estimation from eMMC/UFS stats
  - Flash failure risk score based on device age + battery + USB quality
  - Proactive alerts: "Battery health declining — recommend backup before flash"

- [ ] **AI ROM Compatibility Checker** — `core/ai_rom_matcher.py`
  - Cross-reference ROM requirements (Treble, A/B, vendor version) against device
  - Parse ROM metadata from XDA threads + official changelogs
  - Warn about known incompatibilities before download begins
  - Suggest alternative ROMs when selected ROM is incompatible
  - GApps compatibility matrix (OpenGApps variant → ROM requirements)

- [ ] **AI Workflow Generator** — extend `core/workflow_engine.py`
  - "Generate a workflow for clean ROM install with root" → complete .cyberflow file
  - Context-aware: adapts steps to Samsung vs Pixel vs OnePlus
  - Safety-first: auto-inserts preflight checks and backup steps
  - Iterative refinement: "add a wipe step before flash" mid-generation

---

### Phase 16: Cloud Sync & Remote Operations
**Goal:** Break free from local-only operation — enable cloud backup, cross-machine
sync, and remote device management for power users and teams.

- [ ] **Cloud Backup Destinations** — `services/cloud_backup_service.py`
  - Google Drive, Dropbox, S3-compatible storage backends
  - Encrypted (AES-256-GCM) backup archives before upload
  - Incremental backup: only changed partitions / new APKs since last backup
  - Configurable auto-backup schedule (daily/weekly + on-connect)
  - Restore from cloud directly to device in one flow

- [ ] **Cross-Machine Profile Sync** — `services/sync_service.py`
  - Sync device profiles, flash workflows, and settings across machines
  - Backend: Git-based (private GitHub/GitLab repo) or local network share
  - Conflict resolution: last-writer-wins with diff viewer for manual merge
  - Selective sync: choose which categories to sync

- [ ] **Remote Device Management** — `services/remote_device_service.py`
  - Manage a device connected to another CyberFlash instance over encrypted WebSocket
  - Relay ADB commands with latency compensation
  - Use case: flash a friend's device remotely or manage lab devices from home
  - Secure pairing via one-time PIN code
  - Real-time screen + log streaming over relay

- [ ] **Flash Configuration Bundles** — `core/flash_bundle.py`
  - Export complete flash config as `.cyberflash-bundle`: ROM + profile + workflow + settings
  - Signed bundles with SHA-256 manifest (tamper detection)
  - One-click import: loads ROM, creates profile, configures flash page
  - Share bundles via URL, QR code, or direct file transfer
  - Version-pinned: bundle specifies minimum CyberFlash version required

---

### Phase 17: Advanced Forensics & Recovery
**Goal:** Provide the deepest device inspection and recovery capabilities, turning
CyberFlash into the go-to tool for brick recovery and firmware analysis.

- [ ] **Brick Recovery Wizard** — `ui/dialogs/brick_recovery_wizard.py`
  - Guided recovery flow: identify brick type → suggest recovery path
  - Soft-brick: force reboot → wipe cache → re-flash stock → verify
  - Hard-brick: EDL mode guidance (testpoint diagrams per device)
  - Bootloop detector: auto-detect via repeated fastboot reconnections
  - Samsung Download Mode + Odin fallback path
  - Xiaomi EDL authorization + flash-all recovery

- [ ] **Partition Image Analyzer** — `core/image_analyzer.py`
  - Mount and browse raw partition images (ext4 / f2fs / erofs) read-only
  - File tree viewer: navigate system/vendor/product partitions
  - Extract individual files from partition images
  - Diff two partition images: new/modified/deleted files
  - Build.prop reader: extract ROM info from mounted system image

- [ ] **Boot Image Inspector** — `core/boot_inspector.py`
  - Unpack boot.img / vendor_boot.img (AOSP mkbootimg format)
  - Display: kernel version, cmdline, ramdisk contents, DTB presence
  - Detect Magisk/KernelSU patches in ramdisk
  - Repack boot.img with modified cmdline or ramdisk
  - Compare two boot images side-by-side (original vs patched)

- [ ] **eMMC/UFS Health Monitor** — `workers/storage_health_worker.py`
  - Read eMMC SMART-equivalent data via `/sys/class/mmc_host/` and debugfs
  - UFS health descriptor (bDeviceLifeTimeEstA/B) on supported devices
  - Bad block count, program/erase cycle counts where available
  - Visual lifetime gauge: "eMMC estimated at 73% remaining life"
  - Alert threshold: warn when lifetime drops below 20%

- [ ] **Firmware Diff Tool** — `ui/dialogs/firmware_diff_dialog.py`
  - Compare two firmware packages (zip/tgz) partition-by-partition
  - Highlight: new partitions, size changes, hash mismatches
  - Changelog inference: "system.img changed, boot.img unchanged"
  - Export diff report as HTML or Markdown
  - Useful for verifying incremental OTA contents

---

### Phase 18: Testing & Hardware Quality Assurance
**Goal:** Provide automated testing tools for ROM developers, device testers, and
quality assurance workflows.

- [ ] **Automated Flash Regression Suite** — `core/regression_runner.py`
  - Define test matrices: device × ROM × flash method × wipe mode
  - Execute matrix overnight with progress dashboard
  - Per-combination: flash → boot → verify connectivity → check root → report
  - HTML report with pass/fail matrix, timing, and failure logs
  - CI integration: `--matrix /path/to/matrix.json --report junit`

- [ ] **Device Stability Tester** — `workers/stability_worker.py`
  - Automated stress tests: configurable reboot cycles (50×, 100×, 500×)
  - Flash cycle test: flash ROM A → verify → flash ROM B → verify → repeat
  - Benchmark loop: run Geekbench/storage-bench script after each cycle
  - Thermal monitoring throughout: abort if temperature exceeds threshold
  - Summary: success rate, average boot time, thermal peaks

- [ ] **A/B Update Simulator** — `core/ab_simulator.py`
  - Simulate A/B OTA update flow in dry-run mode end-to-end
  - Verify slot switching logic, rollback triggers, and mark-successful path
  - Test inactive slot write → switch → boot → mark-good sequence
  - Validate against Google's A/B update specification
  - Report: slot states at each stage, expected vs actual

- [ ] **USB Connection Quality Monitor** — `workers/usb_monitor_worker.py`
  - Track USB disconnect/reconnect events during operations
  - Measure sustained transfer speed (push large file, measure throughput)
  - Cable quality detection: USB 2.0 vs 3.0, data-only vs charge-only
  - Warn before flash if USB connection is unstable (>2 disconnects in 60s)
  - History graph: connection stability over time

- [ ] **Screenshot Comparison Testing** — `core/visual_tester.py`
  - Capture device screenshot after boot, compare against reference image
  - Pixel-diff with configurable threshold (for boot animation / lock screen)
  - Verify ROM branding appears correctly after flash
  - Useful for automated ROM CI: "does the home screen render correctly?"
  - Store reference images per ROM-device combination

---

### Phase 19: Enterprise & Fleet Management
**Goal:** Scale CyberFlash from single-user tool to enterprise device provisioning
and fleet management platform for organizations.

- [ ] **Multi-Device Fleet Dashboard** — `ui/pages/fleet_dashboard_page.py`
  - Manage 50+ simultaneously connected devices in a grid/table view
  - Per-device status badges: idle, flashing, error, completed
  - Bulk select → apply operation (flash, wipe, reboot, install APK)
  - Filter by: model, state, ROM version, root status, battery level
  - Real-time refresh with color-coded health indicators

- [ ] **Device Provisioning Templates** — `core/provisioning_engine.py`
  - Define templates: "Corporate Device Setup" = flash stock → install MDM → lock BL
  - Template steps: flash ROM, install APKs, push configs, set props, lock bootloader
  - Variable substitution: `{DEVICE_SERIAL}`, `{EMPLOYEE_ID}`, `{WIFI_SSID}`
  - Templates stored as `.cyberflash-provision` JSON (shareable, version-controlled)
  - Dry-run mode: preview all steps before execution

- [ ] **Compliance Policy Engine** — `core/compliance_checker.py`
  - Define security policies: encryption=ON, debug=OFF, bootloader=LOCKED, min_patch=2025-01
  - Scan connected devices against policy → pass/warn/fail per device
  - Auto-remediation option: "Fix non-compliant settings automatically"
  - Export compliance report for SOC 2 / ISO 27001 audit evidence
  - Scheduled compliance scans with email/webhook alert on violations

- [ ] **Enterprise Audit Trail** — `core/enterprise_audit.py`
  - Append-only cryptographically-chained audit log (hash-linked entries)
  - Every operation logged: operator, device, action, timestamp, result
  - Export formats: JSON, CSV, SIEM-compatible syslog
  - Log retention policies configurable (30/90/365 days)
  - Tamper detection: verify chain integrity on load

- [ ] **LDAP/SSO Operator Authentication** — `services/auth_service.py`
  - Authenticate operators via LDAP / Active Directory / SAML SSO
  - Role-based access: Admin (all ops), Technician (flash + backup), Viewer (read-only)
  - Operator name attached to every audit log entry
  - Session timeout + re-authentication for destructive operations
  - Offline mode with cached credentials (grace period)

---

### Phase 6 Additions (Advanced Root & Security)

- [x] **Root Hide Manager** — extend `core/root_manager.py`
  - Configure MagiskHide / Zygisk DenyList / Shamiko from desktop
  - Per-app root visibility toggle: banking apps, games, SafetyNet-sensitive
  - Preset profiles: "Banking Safe" (hide from all finance apps)
  - Sync deny-list between CyberFlash and device Magisk Manager
  - Test hide effectiveness: run SafetyNet check after config change

- [x] **Boot Animation Manager** — `core/boot_animation_manager.py`
  - Preview boot animations (bootanimation.zip) in a Qt widget player
  - Browse community boot animation libraries
  - Install custom boot animation via ADB push (root required)
  - Backup current boot animation before replacing
  - Create simple boot animations from image sequences

---

### Phase 8 Additions (Device Interaction & Management)

- [ ] **Device Migration Wizard** — `ui/dialogs/migration_wizard.py`
  - Transfer data between two connected Android devices
  - Migrate: contacts (VCF), SMS (content provider), photos, app APKs + data
  - Progress dashboard showing per-category transfer status
  - Verify transferred data via count comparison (source vs destination)
  - Support: ADB backup → ADB restore, or file-level pull → push

- [ ] **SMS & Contacts Backup/Restore** — `core/contacts_manager.py`
  - Export contacts via ADB content provider → VCF file
  - Export SMS database (`mmssms.db`) via root or ADB backup
  - Import VCF contacts to new device via ADB intent
  - Import SMS database back to stock messaging app
  - Merge mode vs overwrite mode for contacts

---

### Phase 9 Additions (Automation & Workflow Engine)

- [ ] **Workflow Marketplace** — `services/workflow_marketplace_service.py`
  - Browse community-published workflows from GitHub-backed catalog
  - Download, rate, and review workflows
  - Verified publisher badges for trusted contributors
  - Auto-update installed workflows when new versions available
  - Submit your workflows: export → PR → review → publish

- [ ] **Webhook & API Triggers** — `services/webhook_service.py`
  - Lightweight HTTP server (localhost only) listening for POST triggers
  - Trigger any saved workflow by name via `POST /api/v1/run/{workflow_name}`
  - JSON payload: `{"device_serial": "...", "params": {...}}`
  - Status polling endpoint: `GET /api/v1/status/{job_id}`
  - Perfect for Jenkins/GitHub Actions CI/CD device testing pipelines

---

### Phase 10 Additions (Advanced Diagnostics & Analytics)

- [ ] **Thermal Throttling Detector** — extend `workers/perf_worker.py`
  - Monitor CPU frequency per core during flash/benchmark operations
  - Detect throttling: flag when any core drops below 70% of max frequency
  - Temperature correlation graph (CPU temp vs clock speed vs time)
  - Throttle alert: "Device is thermal-throttling — flash may take longer"
  - Cooldown recommendation: pause operations until temp drops below threshold

- [ ] **Storage Health Analyzer** — `core/storage_analyzer.py`
  - f2fs/ext4 filesystem integrity check via `fsck` (read-only mode)
  - Bad block detection via eMMC/UFS kernel interfaces
  - TRIM status verification: is TRIM enabled and functioning?
  - Storage fragmentation analysis (f2fs GC status)
  - Actionable: "Run fstrim to reclaim 2.3 GB of unTRIMmed blocks"

---

### Phase 11 Additions (UI/UX Polish & Accessibility)

- [ ] **Dashboard Widget System** — extend `ui/pages/dashboard_page.py`
  - User-configurable dashboard with drag-and-drop widget cards
  - Available widgets: device info, battery gauge, storage pie, recent flashes,
    download queue, health score, quick actions, AI assistant snippet
  - Layout persistence: save widget arrangement per user
  - Widget resize handles (small / medium / large card sizes)
  - "Reset to default" option for factory layout

- [ ] **Multi-Monitor Panel Detachment** — extend `ui/main_window.py`
  - Right-click any panel (log, terminal, AI assistant) → "Detach to Window"
  - Detached panels become independent top-level windows
  - Full functionality preserved in detached state
  - Re-dock via drag back to main window or button click
  - Window positions remembered across sessions

---

### Phase 20: Developer & Power User Toolkit
**Goal:** Provide deep system-level tools that replace a dozen standalone Android
development utilities — from property editing to packet capture.

- [ ] **System Property Editor** — `ui/pages/prop_editor_page.py`
  - Live `getprop` viewer: browse all system properties in a searchable table
  - Edit `build.prop` / `default.prop` with syntax highlighting + validation
  - Presets: spoof device model, change DPI, enable hidden features
  - Diff viewer: show changes before applying (original vs modified)
  - Requires root; safe rollback: backup original file before every write
  - Property change takes effect after reboot or runtime `setprop` where possible

- [ ] **SQLite Database Browser** — `core/sqlite_browser.py`
  - Pull any app's database from `/data/data/{package}/databases/` (root required)
  - Read-only SQLite viewer: table list → row browser → SQL query editor
  - Schema inspector: indexes, triggers, foreign keys
  - Export query results as CSV / JSON
  - Common presets: call log, SMS, WiFi passwords, app preferences
  - Privacy warning before pulling sensitive databases

- [ ] **Network Packet Capture** — `workers/pcap_worker.py`
  - Start `tcpdump` on device via root shell → pull `.pcap` to host
  - Real-time packet count + bandwidth display during capture
  - Filter by: interface (wlan0 / rmnet0), protocol (TCP/UDP/ICMP), port
  - Auto-stop after configurable duration or file size limit
  - One-click "Open in Wireshark" (detect Wireshark/tshark on host PATH)
  - Non-root alternative: `VPNService`-based capture via helper APK

- [ ] **Layout Inspector & GPU Debugger** — `core/layout_inspector.py`
  - Dump device UI hierarchy via `uiautomator dump` → parse XML tree
  - Interactive tree view: click element → highlight on device screenshot overlay
  - Display: resource ID, text, bounds, class name, clickable/scrollable flags
  - GPU rendering profiler: `adb shell dumpsys gfxinfo` → frame time chart
  - GPU overdraw visualization: pull screenshot with overdraw enabled
  - Useful for ROM devs verifying UI performance post-flash

- [ ] **Device Benchmarking Suite** — `core/benchmark_runner.py`
  - Built-in benchmarks: sequential read/write (dd), random I/O (fio-like via shell)
  - CPU benchmark: integer + floating-point workloads via shell script
  - Memory bandwidth test: `/dev/urandom` → `/dev/null` throughput
  - Results stored per-device with timestamp for trend comparisons
  - Exportable as JSON / Markdown report
  - Compare benchmark results between two ROMs on the same device

- [ ] **Init.d & Service Manager** — `ui/pages/service_manager_page.py`
  - List all Android system services via `dumpsys -l` (grouped by category)
  - Start / stop / restart individual services (root required)
  - init.d script manager: browse `/system/etc/init.d/` (or Magisk equivalent)
  - Upload custom init scripts from host to device
  - View service crash history from `dumpsys procstats`
  - Cron-like scheduled service toggling (WiFi off at night, etc.)

- [ ] **Permission Manager** — `core/permission_manager.py`
  - List all runtime permissions per app with grant/deny status
  - Batch grant / revoke permissions via `pm grant` / `pm revoke`
  - "Privacy mode" presets: revoke camera+mic+location for selected apps
  - Detect apps with dangerous permission combos (camera + network + storage)
  - Export permission audit report per device
  - Auto-apply permission profile after ROM flash (restore previous grants)

---

### Phase 21: Data & Privacy Management
**Goal:** Give users complete control over their device data — from forensic-level
recovery to military-grade secure erasure and privacy auditing.

- [ ] **Data Recovery Engine** — `core/data_recovery.py`
  - Scan unallocated blocks on ext4/f2fs partitions for deleted files (root required)
  - Recover: photos (JPEG/PNG/HEIF), videos (MP4), documents (PDF/DOCX)
  - File carving by magic bytes + file structure validation
  - Preview recoverable files before extraction
  - Save recovered files directly to host disk
  - Limitations disclosure: TRIM/encryption may prevent recovery

- [ ] **Secure Data Wiper** — `core/secure_wiper.py`
  - Multi-pass overwrite (DoD 5220.22-M 3-pass, Gutmann 35-pass options)
  - Wipe targets: free space only, entire partition, specific directories
  - Verification pass: read back and confirm zero/pattern bytes
  - Certificate of destruction: timestamped log + hash proof of wipe completion
  - Progress bar with ETA for long wipe operations
  - Required confirmation dialog: type "ERASE" to proceed

- [ ] **Privacy Scanner** — `workers/privacy_scanner_worker.py`
  - Scan installed APKs for known tracking SDKs (Firebase Analytics, Facebook SDK, etc.)
  - Detect apps with excessive permissions vs. actual permission usage
  - Network analysis: which apps connect to known ad/tracking domains
  - Privacy score per app (0–100) based on permissions, trackers, network behavior
  - Aggregated device privacy report with actionable recommendations
  - Blocklist integration: suggest DenyList / NetGuard rules for worst offenders

- [ ] **Encryption Manager** — `core/encryption_manager.py`
  - Display FBE (File-Based Encryption) / FDE (Full-Disk Encryption) status
  - Credential Encrypted (CE) vs Device Encrypted (DE) storage size breakdown
  - Encryption key escrow status check (enterprise MDM detection)
  - Adopt portable storage ↔ internal storage migration assistant
  - Decryption status on boot: track `vold` state for encrypted partitions
  - Warn if encryption is disabled on a rooted device (security risk)

- [ ] **App Data Vault** — `core/app_data_manager.py`
  - Per-app data backup: `/data/data/{pkg}/` → compressed archive on host (root)
  - Selective restore: pick which app data to push back post-flash
  - App list snapshot: save list of installed APKs + versions for reinstall
  - "Titanium Backup"-style batch backup/restore across ROM changes
  - Differential backup: only archive files changed since last backup
  - Encrypted archives with user-provided passphrase (AES-256-GCM)

- [ ] **Digital Wellbeing Exporter** — `workers/wellbeing_worker.py`
  - Pull screen time data via `dumpsys usagestats` (no root needed)
  - App usage breakdown: daily/weekly chart per app
  - Notification count per app over time
  - Export usage data as CSV for external analysis
  - Compare usage patterns between ROM configurations
  - Privacy-first: all data stays local, never uploaded

---

### Phase 7 Additions (ROM Intelligence)

- [ ] **GSI Compatibility Checker** — `core/gsi_checker.py`
  - Detect Project Treble support via `getprop ro.treble.enabled`
  - Identify vendor VNDK version for GSI compatibility assessment
  - Check system-as-root, dynamic partitions, and VNDK apex
  - Recommend correct GSI type: A/B vs A-only, arm64 vs binder bitness
  - Direct links to PHH-Treble and other GSI downloads for detected config
  - Flash GSI to system partition with auto-detected method

- [ ] **ROM Changelog Diff Viewer** — `ui/dialogs/changelog_diff_dialog.py`
  - Parse changelogs from two ROM builds (text, markdown, or HTML)
  - Side-by-side diff view with added/removed entries highlighted
  - Extract security patch level changes, new features, and bug fixes
  - Commit-level diff for ROMs with Git-based changelogs (LineageOS, AOSP)
  - "What's new since my current build?" auto-comparison

- [ ] **Magisk Module Compatibility Matrix** — `core/module_compat.py`
  - Crowdsourced database: which Magisk modules work on which ROM + Android version
  - Auto-detect installed ROM → filter modules to known-compatible list
  - Community voting: "works" / "broken" / "partial" per module-ROM combination
  - Conflict detection: warn when two installed modules modify the same files
  - Suggest tested module sets: "Gaming bundle", "Privacy bundle", "Battery saver"

---

### Phase 12 Additions (Plugin & Extension System)

- [ ] **Plugin Sandbox & Security Model** — `plugins/sandbox.py`
  - Permission manifest: plugins declare required capabilities (ADB, filesystem, network)
  - Resource limits: max memory, CPU time, disk I/O per plugin
  - API surface control: plugins cannot access other plugins' data without explicit grant
  - Signature verification: plugins signed by author keypair (Ed25519)
  - Sandbox violation logging + user alert on suspicious behavior

- [ ] **Plugin Template Generator** — `scripts/create_plugin.py`
  - CLI scaffolding: `python -m cyberflash create-plugin --name my-tool`
  - Generates: `cyberflash_plugin.json`, `__init__.py`, `page.py`, `worker.py`, tests
  - Includes example page with CyberCard layout + example worker with signals
  - README template with plugin API documentation links
  - Integrated with `pip install -e .` for local development iteration

- [ ] **Inter-Plugin Event Bus** — `services/event_bus.py`
  - Publish/subscribe pattern: plugins emit events, others can listen
  - Built-in event types: `device_connected`, `flash_started`, `root_changed`, `download_complete`
  - Custom event registration with typed payloads (dataclass schemas)
  - Event history log: last 1000 events browsable in debug panel
  - Rate limiting: prevent runaway plugins from flooding the bus

---

### Phase 13 Additions (CI/CD, Packaging & Release)

- [ ] **Portable Mode** — `utils/portable.py`
  - Detect `portable.ini` next to executable → store all config/data alongside app
  - Zero installation: run from USB drive on any machine
  - Self-contained: bundled ADB/fastboot + Python runtime + all settings
  - Config migration: import settings from installed version ↔ portable version
  - No registry entries, no `~/.config` writes, no `AppData` pollution

- [ ] **Crash-Recovery State Persistence** — `services/state_persistence_service.py`
  - Periodically snapshot running operation state to disk (every 5s during flash)
  - On restart after crash: detect incomplete operation → offer resume or rollback
  - State includes: current flash step, downloaded files, device serial, slot state
  - Journaled writes: atomic save via temp file + rename (no corruption on power loss)
  - User prompt: "CyberFlash was interrupted during flash. Resume from step 4/7?"

---

### Phase 14 Additions (Community & Ecosystem)

- [ ] **XDA Thread Integration** — `services/xda_service.py`
  - Parse XDA ROM threads: extract download links, changelogs, install instructions
  - Auto-detect device from thread URL → match to local device profile
  - Display thread reputation: post count, thanks, last activity date
  - "Import ROM from XDA" button → parse download link → add to ROM Library
  - Thread watchlist: notify user when watched ROM threads get new replies

- [ ] **Telegram Bot Integration** — `services/telegram_service.py`
  - Send flash completion / error notifications to user's Telegram via Bot API
  - Rich message format: device name, ROM, result, duration, battery after flash
  - Command support: `/status` → current operation, `/devices` → connected list
  - Photo attachment: send device screenshot after successful boot
  - Group chat support for team flashing sessions

- [ ] **Contributor Leaderboard** — community feature
  - Track contributions: device profiles submitted, workflows shared, bug reports filed
  - Badges: "First Profile", "10 Workflows", "Beta Tester", "Bug Hunter"
  - Monthly contributor highlights in CyberFlash release notes
  - Opt-in anonymous contribution stats (no PII)
  - GitHub Integration: auto-detect CyberFlash-related PRs from contributor

---

### Phase 15 Additions (AI Intelligence)

- [ ] **AI Conversation Memory** — `core/ai_memory.py`
  - Persist AI assistant context across sessions (last 50 conversations)
  - Device-specific memory: AI remembers past issues and solutions per device serial
  - "You had this same error last month — the fix was re-flashing vbmeta with --disable-verity"
  - Searchable history: find past AI recommendations by keyword
  - Memory pruning: auto-expire stale entries older than 90 days

- [ ] **AI Device Comparison Engine** — `core/ai_comparator.py`
  - Natural language: "compare my OnePlus 7 Pro with Samsung S24"
  - Pull specs from connected devices + online spec databases
  - Comparison table: SoC, RAM, storage, Android version, root status, flash compatibility
  - ROM availability comparison: which ROMs support both devices
  - Recommendation: "For NetHunter, the OnePlus 7 Pro is better because..."

- [ ] **AI Knowledge Graph** — `core/ai_knowledge_graph.py`
  - Relationship mapping: ROM → compatible devices → required tools → known issues
  - Graph queries: "which ROMs work on Snapdragon 855 devices with unlocked BL?"
  - Auto-populated from: device profiles, flash history, community error reports
  - Visual graph explorer widget (force-directed layout in QGraphicsScene)
  - Inference: "Users who flashed LineageOS on guacamole also installed these Magisk modules"

---

## Feature Count Summary

| Phase | Features | Status |
|---|---|---|
| 0–4 + ROM | 55+ core features | ✅ Complete |
| 5: Multi-Brand | Samsung + Xiaomi + Pixel + Motorola + Device Wizard | ✅ Complete |
| 6: Advanced Root | Module browser + KernelSU + Play Integrity + dm-verity + AnyKernel3 + Vault + Root Hide + Boot Anim | 🔲 Planned |
| 7: ROM Intelligence | Live feed + metadata + download queue + comparison + profile hub + GSI checker + changelog diff + module compat | 🔲 Planned |
| 8: Device Interaction | Wireless ADB + App manager + File manager + Screen capture + Clipboard + Migration + SMS/Contacts | 🔲 Planned |
| 9: Automation | Workflow builder + batch ops + journal + scheduler + CLI + marketplace + webhooks | 🔲 Planned |
| 10: Diagnostics | Health score + battery analytics + perf profiler + logcat AI + security audit + thermal + storage | 🔲 Planned |
| 11: UI Polish | Animations + theme studio + mega-menu + shortcuts + notifications + onboarding + a11y + widgets + detach | 🔲 Planned |
| 12: Plugins | Plugin API + custom pages + worker registry + scripting + sandbox + template gen + event bus | 🔲 Planned |
| 13: Release | GitHub Actions CI + update system + crash reporter + telemetry + portable mode + state recovery | 🔲 Planned |
| 14: Community | Profile repo + ROM directory + Discord + i18n + docs + XDA threads + Telegram + leaderboard | 🔲 Planned |
| 15: AI Intelligence | Autonomous flash + NLP control + error diagnosis + predictive health + ROM matcher + workflow gen + memory + comparator + knowledge graph | 🔲 Planned |
| 16: Cloud & Remote | Cloud backup + cross-machine sync + remote device mgmt + flash bundles | 🔲 Planned |
| 17: Forensics | Brick recovery wizard + partition analyzer + boot inspector + eMMC health + firmware diff | 🔲 Planned |
| 18: Testing & QA | Regression suite + stability tester + A/B simulator + USB monitor + screenshot testing | 🔲 Planned |
| 19: Enterprise | Fleet dashboard + provisioning templates + compliance + audit trail + LDAP/SSO | 🔲 Planned |
| 20: Developer Toolkit | Prop editor + SQLite browser + packet capture + layout inspector + benchmarks + service manager + permissions | 🔲 Planned |
| 21: Data & Privacy | Data recovery + secure wiper + privacy scanner + encryption mgr + app data vault + wellbeing exporter | 🔲 Planned |

**Total planned features: 195+**

---

## Project Directory Structure (Current)

```
CyberFlash-2026/
├── src/cyberflash/
│   ├── app.py                       ✅ QApplication entry point
│   ├── core/
│   │   ├── adb_manager.py           ✅
│   │   ├── fastboot_manager.py      ✅
│   │   ├── device_detector.py       ✅
│   │   ├── flash_engine.py          ✅
│   │   ├── edl_manager.py           ✅
│   │   ├── edl_engine.py            ✅
│   │   ├── root_manager.py          ✅ NEW — Magisk/KernelSU/APatch
│   │   ├── payload_dumper.py        ✅ NEW — OTA payload.bin extractor
│   │   ├── rom_manager.py           ✅ NEW — download tracking + history
│   │   ├── partition_manager.py     ✅
│   │   ├── tool_manager.py          ✅
│   │   ├── source_scorer.py         ✅ AI trust scoring
│   │   ├── link_checker.py          ✅
│   │   ├── domain_lists.py          ✅
│   │   ├── ai_engine.py             ✅
│   │   ├── device_analyzer.py       ✅
│   │   ├── workflow_engine.py       ✅
│   │   └── preflight_checker.py     ✅
│   ├── workers/
│   │   ├── base_worker.py           ✅
│   │   ├── flash_worker.py          ✅
│   │   ├── backup_worker.py         ✅ NEW
│   │   ├── diagnostics_worker.py    ✅ NEW — 31 ADB commands
│   │   ├── download_worker.py       ✅ NEW — resumable HTTP
│   │   ├── hash_worker.py           ✅ NEW — SHA256/MD5/SHA1
│   │   ├── adb_log_worker.py        ✅ NEW — streaming logcat
│   │   ├── device_poll_worker.py    ✅
│   │   ├── link_monitor_worker.py   ✅
│   │   ├── ai_worker.py             ✅
│   │   └── edl_worker.py            ✅
│   ├── ui/pages/
│   │   ├── dashboard_page.py        ✅
│   │   ├── device_page.py           ✅
│   │   ├── flash_page.py            ✅
│   │   ├── rom_library_page.py      ✅ + download wiring
│   │   ├── backup_page.py           ✅ wired to BackupWorker
│   │   ├── root_page.py             ✅ fully wired
│   │   ├── nethunter_page.py        ✅
│   │   ├── partition_page.py        ✅
│   │   ├── terminal_page.py         ✅
│   │   ├── diagnostics_page.py      ✅ logcat + health wired
│   │   ├── rescue_page.py           ✅
│   │   └── settings_page.py         ✅
│   └── services/
│       ├── device_service.py        ✅
│       ├── rom_link_service.py      ✅
│       ├── ai_service.py            ✅
│       └── config_service.py        ✅
│
├── tests/unit/                      ✅ 342 tests passing
│   ├── test_payload_dumper.py       ✅ 13 tests
│   ├── test_root_manager.py         ✅ 20 tests
│   ├── test_rom_manager.py          ✅ 22 tests
│   ├── test_download_worker.py      ✅ 9 tests
│   ├── test_hash_worker.py          ✅ 11 tests
│   ├── test_backup_worker.py        ✅ 8 tests
│   └── test_diagnostics_worker.py   ✅ 11 tests
│
└── CLAUDE.md                        ✅ Claude Code instructions
```

---

## Quality Standards (Non-Negotiable)

Every feature merged to main must satisfy:

1. **Tests first** — unit tests before or alongside implementation, mocking all ADB/fastboot
2. **Zero ruff errors** — `ruff check src/` passes clean on every commit
3. **Layer boundaries** — core/ never imports Qt widgets; workers never block main thread
4. **Dry-run parity** — every destructive operation has a `dry_run=True` mode
5. **Error signals** — every worker emits `error(str)` and `finished()` unconditionally
6. **Confirmation dialogs** — bootloader unlock, wipe, format, unroot all require explicit confirmation
7. **Log everything** — every ADB command and result goes to Python logging at DEBUG level
8. **Type hints** — all public functions have complete type annotations
9. **No hardcoded colors** — all palette values in `ui/themes/variables.py` only
10. **Accessibility** — every interactive widget has a tooltip and accessible name

---

## Market Positioning

| Competitor | Weakness | CyberFlash Advantage |
|---|---|---|
| Odin (Windows only) | Samsung-only, closed source, no root tools | Cross-platform, all brands, open source |
| Universal Android Flasher | Minimal UI, no ROM library, no diagnostics | Full feature suite, AI trust scoring |
| ADB AppControl | App management only | Complete ecosystem (flash + root + backup + diagnose) |
| ROM Manager (dead) | Android app, not desktop | Professional desktop GUI, all PC platforms |
| Minimal ADB & Fastboot | CLI wrapper only, no UI | Full cyberpunk GUI, workflow automation |
| Flashify | Android app, rooted devices only | Desktop control, works before root exists |
| TWRP App | Recovery installation only | End-to-end: unlock → recovery → ROM → root |

**CyberFlash wins because:**
- Only tool with AI-powered ROM source trust scoring
- Only tool with autonomous AI flash wizard (natural language → device operations)
- Only tool with visual workflow automation builder
- Only tool with built-in logcat, terminal, app manager, file manager in one package
- Only tool supporting Magisk + KernelSU + APatch + SafetyNet in one UI
- Only tool with community plugin API
- Only tool with CLI mode for CI/CD integration
- Only tool with enterprise fleet management and compliance engine
- Only tool with brick recovery wizard covering soft-brick, hard-brick, and EDL paths
- Only open-source cross-platform tool at this feature level

---

## Release Milestones

| Milestone | Target | Contents |
|---|---|---|
| **v0.1 Alpha** | Current | Phases 0–4 complete; OnePlus 7 Pro fully supported |
| **v0.2 Beta** | Phase 5 | Samsung + Pixel + Device Wizard |
| **v0.3 Beta** | Phase 6–7 | Full root suite + ROM intelligence |
| **v0.4 Beta** | Phase 8–9 | App/file manager + workflow builder + CLI |
| **v0.5 RC** | Phase 10–11 | Diagnostics AI + UI polish + accessibility |
| **v0.6 RC** | Phase 15 | AI autonomous operations + NLP device control |
| **v0.7 RC** | Phase 16–17 | Cloud sync + forensics + recovery tools |
| **v0.8 RC** | Phase 18 | Testing & QA automation suite |
| **v1.0 Release** | Phase 12–14 | Plugin system + CI/CD + community hub + i18n |
| **v1.5 Enterprise** | Phase 19 | Fleet management + provisioning + compliance + SSO |
| **v2.0 Developer** | Phase 20–21 | Developer toolkit + data & privacy management suite |
| **v2.x** | Ongoing | Community profiles, new devices, new ROM sources |
