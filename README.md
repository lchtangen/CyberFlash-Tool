<div align="center">

# ⚡ CyberFlash Tool

**The definitive open-source, AI-powered Android ROM flashing and device management desktop app.**

[![Tests](https://img.shields.io/badge/tests-622%2B%20passing-brightgreen?style=flat-square&logo=pytest)](https://github.com/lchtangen/CyberFlash-Tool/actions)
[![Devices](https://img.shields.io/badge/device%20profiles-21-blueviolet?style=flat-square)]()
[![Themes](https://img.shields.io/badge/themes-3%20fully%20functional-orange?style=flat-square)]()
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square&logo=python)](https://python.org)
[![PySide6](https://img.shields.io/badge/PySide6-Qt%206-41cd52?style=flat-square&logo=qt)](https://doc.qt.io/qtforpython/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey?style=flat-square)]()
[![Phases](https://img.shields.io/badge/phases-7%20of%2021%20complete-cyan?style=flat-square)]()
[![Lint](https://img.shields.io/badge/lint-ruff%20clean-orange?style=flat-square)](https://github.com/astral-sh/ruff)

[**🌐 Website**](https://lchtangen.github.io/CyberFlash-Tool/) · [**📸 Screenshots**](https://lchtangen.github.io/CyberFlash-Tool/screenshots.html) · [**🗺️ Roadmap**](https://lchtangen.github.io/CyberFlash-Tool/roadmap.html) · [**📋 Changelog**](https://lchtangen.github.io/CyberFlash-Tool/changelog.html) · [**🤝 Contributing**](https://lchtangen.github.io/CyberFlash-Tool/features.html)

</div>

---

## What is CyberFlash?

CyberFlash replaces every fragmented tool in the Android modding ecosystem with a single
professional cross-platform desktop application. No more juggling five terminals, three
GUI tools, and a stack of outdated scripts.

Built with **Python 3.12 + PySide6 (Qt 6)**, it combines a pixel-perfect cyberpunk UI
with a rigorously tested, strictly layered architecture. **622+ tests passing.** Lint-clean.
AI-powered features baked in from day one. **21 device profiles. 18 navigation pages. 3 themes.**

> **Reliability first.** A bad flash can brick a device. Every destructive operation
> has dry-run mode, danger confirmation, and journal logging before it executes.

---

## Feature Overview

### ⚡ Core Flash Engine
- Fastboot ROM flash + ADB sideload with **dry-run mode** and step tracker
- A/B slot management, vbmeta patching, wipe operations (cache / dalvik / data / system)
- Real-time ANSI-colorized log panel, flash journal with rollback

### 🏢 Multi-Brand Support
| Brand | Engine | Features |
|---|---|---|
| **Samsung** | Heimdall | PIT parser, TAR flash, repartition |
| **Xiaomi** | MIUI/HyperOS | fastboot flash, ARB check, unlock flow |
| **Google Pixel** | Factory image | bootloader/radio flash, OTA sideload |
| **Motorola** | RSA rescue | flashfile.xml parser, firmware dir flash, unlock code |
| **Any device** | EDL | Emergency Download Mode engine |

### 🔓 Root & Security
- Detect **Magisk / KernelSU / APatch** root state automatically on device connect
- Boot image patch workflow (push → launch → poll → pull → flash)
- Module browser, DenyList manager, Root Hide, dm-verity / force-encryption control
- **Banking-safe preset** — one click to configure hiding for financial apps
- AnyKernel3 flash with boot backup and rollback

### 🛡️ Integrity & Privacy
- Play Integrity / SafetyNet 3-tier checker (BASIC / DEVICE / STRONG) with JSON history
- **AES-256-GCM Token Vault** — encrypted credential storage with OS keychain integration
- Security auditor: SELinux, dangerous permissions, developer options, network posture
- **Privacy Scanner page** — per-app tracking SDK detection (20 known SDKs), dangerous permission scoring, A–F grade badges, JSON export

### 🎨 Theme System
- Three full themes: **Cyber Dark** (cyberpunk), **Cyber Light** (professional), **Cyber Green** (matrix terminal)
- All themes cover 1285+ QSS selectors including sidebar, terminal, AI panel, ROM library, automation components

### 📱 Device Profiles
- **21 supported devices** across 5 brands: Samsung, Google Pixel, Xiaomi/POCO, OnePlus, Motorola
- Each profile: partitions, wipe targets, recovery entries, EDL config, unlock instructions

### ⚙️ Batch & Advanced Tools
- **Batch Operations** — flash/backup/root multiple devices simultaneously with per-device progress
- **App Manager** — uninstall/disable/enable/clear user and system apps in bulk
- **File Manager** — ADB-powered device filesystem browser
- **Prop Editor** — read/write build.prop and system properties
- **Magisk Modules** — repo browser, search, install worker

### 📦 ROM Library & Downloads
- AI-powered **trust scoring** for ROM sources (Availability · Safety · Speed · Reputation)
- Resumable chunked HTTP downloads with SHA-256 post-download verification
- Download history persistence, per-source progress panel, cancel support
- OTA `payload.bin` extractor — inline protobuf parser, zero extra dependencies

### 🔬 Diagnostics & Monitoring
- 31 ADB diagnostic commands across 6 categories
- Device health card (battery %, temperature, storage, RAM)
- Streaming logcat via QProcess with priority filter (V/D/I/W/E/F/S)
- Battery monitor worker, crash service with auto-reporting

### 🤖 AI Features
- **ROM source trust scoring** — AI evaluates sources before you download
- **Error analyzer** — plain-English explanations for failed flash/ADB operations
- **AI Assistant Panel** — built-in chat assistant in the main window
- **Health scoring** — AI-driven device health combining all sensor data
- **Security auditor** — AI-assisted device configuration analysis
- Optional **Google Gemini** integration (key stored in Token Vault)

### 🛠️ Device Management
- Wireless ADB pairing (Android 11+ TCP)
- App manager, file manager, prop editor
- Boot animation manager (parse / preview / install / backup)
- Screen manager (capture / mirror — Phase 9)
- Backup worker (ADB backup + media pull modes)

---

## Quick Start

```bash
# Clone
git clone https://github.com/lchtangen/CyberFlash-Tool.git
cd CyberFlash-Tool

# Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install (editable + dev deps)
pip install -e ".[dev]"

# Launch
python -m cyberflash
```

**Linux only** — install udev rules for EDL mode:
```bash
sudo cp resources/udev/51-cyberflash-edl.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
```

---

## Development

```bash
pytest tests/          # run all 622+ tests
ruff check src/        # lint
ruff format --check src/  # format check
mypy src/              # type check
```

See [CLAUDE.md](CLAUDE.md) for architecture conventions and coding standards.

---

## Architecture

CyberFlash enforces **strict layer boundaries** so every module is independently testable:

```
┌─────────────────────────────────────────────┐
│  ui/pages  ui/panels  ui/widgets  ui/dialogs │  Qt only — no subprocess/IO
├─────────────────────────────────────────────┤
│  workers/        (QObject + moveToThread)    │  Async bridge — signals/slots only
├─────────────────────────────────────────────┤
│  services/       (own workers, emit to UI)   │  Long-running monitors
├─────────────────────────────────────────────┤
│  core/           (NO Qt widget imports)      │  Pure logic — callable from tests
├─────────────────────────────────────────────┤
│  models/         (dataclasses only)          │  Data transfer objects
└─────────────────────────────────────────────┘
```

**Key rules:**
- `core/` never imports from `PySide6.QtWidgets`
- Workers never call `core/` from the main thread
- Pages never call ADB/fastboot directly — always through workers or services
- QSS color tokens live exclusively in `ui/themes/variables.py`

---

## Device Profiles

Device support is defined in pluggable JSON files under `resources/profiles/`:

```json
{
  "codename": "guacamole",
  "name": "OnePlus 7 Pro",
  "brand": "oneplus",
  "ab_slots": true,
  "bootloader": { "unlock_command": "oem unlock" },
  "flash": { "method": "fastboot" }
}
```

Add your device by creating a new profile — no Python required.
See `resources/profiles/schema.json` for the full schema.

---

## Roadmap

| Phase | Status | Description |
|---|---|---|
| 0–4 + ROM | ✅ Complete | Scaffold, flash engine, root, diagnostics, backup, downloads |
| 5 | ✅ Complete | Samsung, Xiaomi, Pixel, Motorola + Device Wizard |
| 6 | ✅ Complete | KernelSU, Play Integrity, AnyKernel3, Token Vault, boot anim |
| 7 | 🔄 Active | ROM feed, metadata, flash journal, wireless ADB, health scoring |
| 8 | ⏳ Planned | App manager, file manager, APK tools |
| 9 | ⏳ Planned | Screen mirror, recording, input automation |
| 10–21 | ⏳ Planned | Workflow builder, plugins, NetHunter, partition editor, and more |

Full roadmap → [lchtangen.github.io/CyberFlash-Tool/roadmap.html](https://lchtangen.github.io/CyberFlash-Tool/roadmap.html)

---

## Contributing

CyberFlash is MIT-licensed and designed for community contribution:

- **Add a device profile** — create a JSON file in `resources/profiles/your-brand/`
- **Fix a bug** — fork, branch off `master`, write a test, open a PR
- **Write tests** — core modules are pure Python, easy to test without a device
- **Report issues** — include your device codename and the full log output

Please read [CLAUDE.md](CLAUDE.md) for coding standards before submitting a PR.

---

## Tech Stack

| Component | Choice | Reason |
|---|---|---|
| Language | Python 3.12+ | ADB ecosystem, instant debugging, pip |
| GUI | PySide6 (Qt 6) | QProcess, QThread, LGPL, signal/slot |
| Tests | pytest + pytest-qt | QApplication fixture, signal testing |
| Lint | ruff | Fast, zero-config, CI enforced |
| Types | mypy | Public API type safety |
| Packaging | pyside6-deploy + GitHub Actions | Cross-platform CI matrix |
| Config | QSettings (INI) | Cross-platform, typed getters |

---

## License

MIT © 2026 [Lchtangen](https://github.com/lchtangen) and Contributors

Built with ❤️ for the Android modding community.
