# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
CyberFlash is a professional cross-platform Android ROM flashing tool built with Python + PySide6.

## Setup & Commands

```bash
# Install (editable + dev deps)
pip install -e ".[dev]"

# Run
python -m cyberflash

# Lint
ruff check src/

# Format check
ruff format --check src/

# Type check
mypy src/

# All tests
pytest tests/

# Single test file
pytest tests/unit/test_flash_engine_dry_run.py -v

# Single test by name
pytest tests/ -k "test_name" -v
```

Tests require a session-scoped `QApplication`; the `qapp` fixture in `tests/conftest.py` provides it. Qt tests must request `qapp` as a fixture parameter.

## Architecture

### Layer Boundaries
- **`core/`** — pure Python, no Qt imports. Orchestrates ADB/fastboot/EDL operations.
- **`workers/`** — `QObject` subclasses using `moveToThread(QThread)` pattern (not `QThread` subclassing). All ADB/file I/O goes here. Inherit from `BaseWorker` which provides `error = Signal(str)` and `finished = Signal()`.
- **`services/`** — `QObject`s that own workers and expose high-level signals to the UI (e.g. `DeviceService` owns `DevicePollWorker` and emits `device_list_updated`).
- **`ui/`** — widgets and pages that consume services; never call `core/` directly.

### Worker Pattern
```python
thread = QThread(parent)
worker = MyWorker()
worker.moveToThread(thread)
thread.started.connect(worker.start)
thread.start()
# Stop: QMetaObject.invokeMethod(worker, "stop", Qt.QueuedConnection)
```

### Theme System
- Three built-in palettes: `cyber_dark`, `cyber_light`, `cyber_green` — all defined in `ui/themes/variables.py` as `ThemePalette` dataclasses.
- `ThemeEngine.apply_theme(name)` loads `ui/themes/{name}.qss`, substitutes `{TOKEN}` placeholders with palette field values, and calls `app.setStyleSheet()`.
- All themes fall back to `cyber_dark.qss` if their own QSS file doesn't exist.
- Never hardcode hex colors outside `ui/themes/variables.py`.

### Device Profiles
- JSON files under `resources/profiles/**/{codename}.json`.
- `ProfileRegistry` in `src/cyberflash/profiles/__init__.py` loads them by codename via `rglob`.
- Schema/dataclasses in `models/profile.py`: `DeviceProfile`, `BootloaderConfig`, `FlashConfig`, `EdlConfig`, `RecoveryEntry`.
- `ab_slots: bool` — A/B partition scheme. `flash.method` is `"fastboot"` or `"sideload"`.

### Key Files
- `src/cyberflash/app.py` — `QApplication` entry point, applies theme, shows `FramelessMainWindow`
- `src/cyberflash/ui/main_window.py` — `FramelessMainWindow` owns `DeviceService` and `RomLinkService`, instantiates all pages
- `src/cyberflash/core/flash_engine.py` — pure-Python flash orchestrator; methods return `False` on failure, never raise; accepts `log_cb: Callable[[str], None]`
- `src/cyberflash/workers/flash_worker.py` — wraps `FlashEngine` in a worker thread

## Coding Standards
- Python 3.12+, type hints required on all public functions
- Line length: 100 characters (ruff enforced)
- Signals: `Signal(type)` from `PySide6.QtCore`
- Constants: `UPPER_CASE`
- No wildcard imports
- `print()` statements are flagged by ruff (T20) — use `logging` instead
- `from __future__ import annotations` at top of every module
