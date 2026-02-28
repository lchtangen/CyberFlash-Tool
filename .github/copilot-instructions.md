# CyberFlash — GitHub Copilot Instructions

CyberFlash is a safety-critical Android ROM flashing tool (Python 3.12+ / PySide6). Bad flash sequences brick physical devices. Follow these rules exactly.

---

## Mandatory Header

Every Python file must start with:
```python
from __future__ import annotations
```

---

## Layer Boundaries

| Layer | Location | Rules |
|-------|----------|-------|
| `core/` | `src/cyberflash/core/` | Pure Python — **no Qt imports**. Methods return `bool` (never raise). Accept `log_cb: Callable[[str], None]`. |
| `workers/` | `src/cyberflash/workers/` | `QObject` subclasses. Use `moveToThread(QThread)` — never subclass `QThread`. Inherit `BaseWorker`. |
| `services/` | `src/cyberflash/services/` | `QObject`s that own workers and expose high-level signals to the UI. |
| `ui/` | `src/cyberflash/ui/` | Widgets/pages that consume services. Never import from `core/` directly. |

---

## Worker Launch Pattern

Always use this exact pattern — never subclass `QThread`:

```python
from __future__ import annotations

from PySide6.QtCore import QMetaObject, QThread, Qt

thread = QThread(parent)
worker = MyWorker()
worker.moveToThread(thread)
thread.started.connect(worker.start)
worker.finished.connect(thread.quit)
worker.finished.connect(worker.deleteLater)
thread.finished.connect(thread.deleteLater)
thread.start()

# To stop gracefully:
QMetaObject.invokeMethod(worker, "stop", Qt.QueuedConnection)
```

---

## Coding Standards

- **Type hints required** on all public functions and methods
- **Line length: 100 characters** (ruff-enforced)
- **No `print()` statements** — use `logging` (`T20` ruff rule)
- **No wildcard imports** — `from module import *` is forbidden
- **No hardcoded hex colors** — all colors go in `ui/themes/variables.py` as `ThemePalette` fields
- **Modern generics**: use `list[str]`, `dict[str, Any]`, `tuple[int, ...]` (not `List`, `Dict`, `Tuple` from `typing`)
- **`from __future__ import annotations`** at the top of every file

---

## Theme System

- Three palettes: `cyber_dark`, `cyber_light`, `cyber_green` — defined in `ui/themes/variables.py`
- QSS files use `{TOKEN}` placeholders substituted by `ThemeEngine.apply_theme(name)`
- All themes fall back to `cyber_dark.qss` if their QSS file doesn't exist
- **Never hardcode hex colors in QSS or Python** — always use `{TOKEN}` in QSS

---

## Flash Safety Rules

- Every flash operation must have a confirmation dialog before execution
- All `FlashEngine` methods must accept a `dry_run: bool` parameter
- `FlashEngine` methods return `False` on failure — they never raise exceptions
- Log every step via `log_cb` before and after execution

---

## Device Profiles

- JSON files under `resources/profiles/**/{codename}.json`
- Schema: `DeviceProfile`, `BootloaderConfig`, `FlashConfig`, `EdlConfig`, `RecoveryEntry` (in `models/profile.py`)
- `ab_slots: bool` — A/B partition scheme; `flash.method` is `"fastboot"` or `"sideload"`
- Load via `ProfileRegistry` — never parse profile JSON directly in UI or worker code

---

## Testing

- All Qt tests require the `qapp` fixture from `tests/conftest.py`
- Use `qtbot` for widget interaction
- Never make real ADB/fastboot calls in tests — mock `subprocess.run` or use dry-run mode
- Test files go in `tests/unit/` (pure logic) or `tests/integration/` (Qt integration)

---

## Do Not Modify

- `src/cyberflash/ui/main_window.py` — `AIService` and `AIAssistantPanel` are already integrated; do not overwrite
- `src/cyberflash/ui/themes/variables.py` — add new tokens; never remove existing ones
- `resources/profiles/` — only add new JSON files; never delete existing profiles
