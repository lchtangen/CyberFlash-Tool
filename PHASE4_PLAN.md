# CyberFlash Phase 4 — Cyberpunk Background + Complete All Pages

## Context

The app currently has 6 real pages (Dashboard, Device, Flash, ROM Library, Rescue + its EDL dialogs)
and 7 stubs showing only "Coming in Phase X" placeholder text: Backup, Root, NetHunter, Partition,
Terminal, Diagnostics, Settings. The content area also lacks visual character — it's a flat
`#0d1117` rectangle with no cyberpunk identity. This phase completes the app.

**Two goals:**
1. **Cyberpunk background** — a static circuit-board/grid pattern painted behind all page content,
   giving the app depth and identity without obscuring widgets.
2. **All 7 stub pages** — replace each placeholder with high-quality, functional UI wired to the
   real backend services/workers that already exist.

Working directory: `/home/lchtangen/Projects/CyberFlash-Original-2026/`

---

## Existing Backend to Reuse (nothing new in core/ needed)

| Backend | Pages that use it |
|---|---|
| `ConfigService.instance()` | SettingsPage |
| `DeviceService` (passed from main_window) | Diagnostics, Terminal, Partition, Backup, Root, NetHunter |
| `AdbManager` (called from workers) | Diagnostics, Backup, Terminal (via QProcess) |
| `FastbootManager` (called from workers) | Partition, Backup |
| `PartitionManager.get_slot_info()`, `set_active_slot()` | PartitionPage |
| `FlashWorker` (reuse) | Root, NetHunter (sideload method) |
| `StepTracker`, `LogPanel`, `ProgressPanel` | Diagnostics, Backup, Root, NetHunter |
| `CyberBadge`, `_DeviceBar` (from flash_page) | Diagnostics, Terminal, Partition, Backup, Root, NetHunter |

**Key APIs:**
- `ConfigService.instance().get(key)` / `.set(key, value)` / `.get_bool()` / `.get_int()` / `value_changed` signal
- `DeviceService.selected_device` (property) / `selected_device_changed(DeviceInfo|None)` signal
- `AdbManager.shell(serial, cmd, timeout)` → str
- `AdbManager.reboot(serial, mode)` → bool
- `PartitionManager.get_slot_info(serial)` → dict / `set_active_slot(serial, slot)` → bool
- `FlashWorker` constructor: `FlashWorker(task: FlashTask, profile: DeviceProfile)`
- `StepTracker.set_steps(list[FlashStep])` / `update_step(step_id, StepStatus)`
- `ProgressPanel.update_progress(current, total)` / `reset()`
- `LogPanel.append_line(text)` / `clear()`

---

## TASK 1 — Cyberpunk Background

**Problem:** The central widget paints a flat `#0d1117`. The content area has no visual depth.

**Solution:** Subclass QWidget → `_CyberCentralWidget` overrides `paintEvent` with QPainter.
The QStackedWidget holding pages gets `background: transparent` in QSS so the background
shows through behind widget-free areas. Individual content cards/frames retain their solid
surface colors.

### Changes

**`src/cyberflash/ui/main_window.py`** — add `_CyberCentralWidget(QWidget)` inner class:
```python
class _CyberCentralWidget(QWidget):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 1. Base fill
        p.fillRect(self.rect(), QColor("#0d1117"))

        # 2. Fine dot-grid (circuit board nodes) — 40px spacing, very faint cyan
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 212, 255, 14))
        for x in range(0, w, 40):
            for y in range(0, h, 40):
                p.drawEllipse(x - 1, y - 1, 3, 3)

        # 3. Horizontal trace lines — every 80px, 1px, opacity 6
        p.setPen(QPen(QColor(0, 212, 255, 6), 1))
        for y in range(0, h, 80):
            p.drawLine(0, y, w, y)

        # 4. Vertical trace lines — every 80px, 1px, opacity 6
        for x in range(0, w, 80):
            p.drawLine(x, 0, x, h)

        # 5. Corner bracket ornaments — 4 corners, 28px arms, opacity ~50
        pen = QPen(QColor(0, 212, 255, 50), 2)
        p.setPen(pen)
        arm = 28
        for (cx, cy, sx, sy) in [(0,0,1,1),(w,0,-1,1),(0,h,1,-1),(w,h,-1,-1)]:
            p.drawLine(cx, cy, cx + sx*arm, cy)
            p.drawLine(cx, cy, cx, cy + sy*arm)

        # 6. Diagonal scan gradient (top-left to bottom-right, very subtle)
        grad = QLinearGradient(0, 0, w*0.6, h*0.6)
        grad.setColorAt(0.0, QColor(0, 212, 255, 7))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), QBrush(grad))
```

In `_setup_ui()`, use `_CyberCentralWidget` instead of `QWidget`:
```python
central = _CyberCentralWidget(self)
central.setObjectName("centralWidget")
self.setCentralWidget(central)
```

**`src/cyberflash/ui/themes/cyber_dark.qss`** — add at end:
```css
/* Content stack — transparent so cyberpunk background shows through */
QStackedWidget {
    background: transparent;
}
/* Page root widgets — transparent background; cards/frames remain solid */
QWidget#pageRoot {
    background: transparent;
}
```

Each of the 7 new pages sets `self.setObjectName("pageRoot")` in their constructor.
Existing real pages (Dashboard, Flash, etc.) are NOT changed.

---

## TASK 2 — SettingsPage

**File:** `src/cyberflash/ui/pages/settings_page.py` (replace stub, ~200 lines)

**Layout:** VBox — page header + scroll area with sections

**Sections (all use ConfigService.instance()):**

1. **Appearance** — 3 theme cards (Cyber Dark / Cyber Green / Cyber Light) with color swatch dots.
   Clicking a card calls `ConfigService.instance().set("theme", name)` and
   `ThemeEngine.apply_theme(name)` immediately for live preview.

2. **Device** — Poll interval: `QSpinBox` (1–30 s) bound to config key `"device_poll_interval"`.
   Auto-select first device: `QCheckBox` bound to `"auto_select_device"`.

3. **Flash Defaults** — Dry run by default: `QCheckBox` bound to `"flash_dry_run_default"`.

4. **Tools** — Shows resolved paths from ToolManager for adb, fastboot, edl.
   Greyed out if not found (`ToolManager.find_adb()` etc.).

5. **About** — App version (`cyberflash.__version__` or hardcoded "1.0.0"),
   Python version (`sys.version`), PySide6 version (`PySide6.__version__`).

6. **Reset** — `QPushButton("Reset to defaults")` → `ConfigService.instance().reset_to_defaults()`.

**Signal wiring:** `ConfigService.instance().value_changed` → re-read and refresh relevant control.

---

## TASK 3 — DiagnosticsPage + DiagnosticsWorker

### DiagnosticsWorker
**File:** `src/cyberflash/workers/diagnostics_worker.py` (new, ~120 lines)

```python
class DiagnosticsWorker(BaseWorker):
    result_ready = Signal(str, str, str)  # category, key, value
    log_line = Signal(str)
    diagnostics_complete = Signal()
```

Runs these ADB commands in `start()` @Slot:
- `adb -s {serial} shell getprop ro.product.model` etc. → "Device Info" category
- `adb -s {serial} shell df -h /data /system /sdcard` → "Storage"
- `adb -s {serial} shell cat /proc/meminfo | head -5` → "Memory"
- `adb -s {serial} shell dumpsys battery` → "Battery"
- `adb -s {serial} shell cat /proc/cpuinfo | grep -E "Hardware|processor|Processor"` → "CPU"
- `adb -s {serial} shell getenforce` → "Security"

Uses `AdbManager.shell(serial, cmd)` for each. Emits `result_ready(category, key, value)` per line parsed.

### DiagnosticsPage
**File:** `src/cyberflash/ui/pages/diagnostics_page.py` (replace stub, ~250 lines)

**Layout:**
- Page header + device bar (same `_DeviceBar` pattern as FlashPage)
- No-device overlay
- When device connected:
  - "Run Diagnostics" button (enabled) + "Export…" button (enabled after run)
  - Scrollable results area: one `QFrame` card per category (Device Info, Storage, Memory, Battery, CPU, Security)
  - Each card starts empty, populated by `result_ready` signals via key-value grid
  - LogPanel at bottom (collapsible, shows raw ADB output)

**Worker lifecycle:** moveToThread pattern. On `diagnostics_complete`: enable Export button.
Export: `QFileDialog.getSaveFileName` → write all results as plain text.

---

## TASK 4 — TerminalPage

**File:** `src/cyberflash/ui/pages/terminal_page.py` (replace stub, ~220 lines)

No worker needed — uses `QProcess` directly (interactive stdin/stdout).

**Layout:**
- Page header + device bar
- No-device overlay
- When device connected:
  - Mode selector: `QComboBox` — "ADB Shell" / "Fastboot"
  - Terminal output: `QTextEdit` (read-only, `font-family: monospace`, dark, green text `#3fb950`)
  - Input row: `QLineEdit` (command input, captures Up/Down for history) + `QPushButton("Run")`
  - Quick-command buttons row: "getprop", "df -h", "dumpsys battery", "top -n 1", "ls /sdcard"
  - Clear button

**QProcess setup (ADB Shell mode):**
```python
self._proc = QProcess(self)
self._proc.setProgram(ToolManager.adb_cmd()[0])
self._proc.setArguments(["-s", serial, "shell"])
self._proc.readyReadStandardOutput.connect(self._on_output)
self._proc.start()
```

**Input:** `input_line.returnPressed` → write `cmd + "\n"` to `self._proc.write()`.
**History:** `list[str]` + index, Up/Down arrow `eventFilter` on input field.
**Disconnect cleanup:** kill `_proc` when device changes or page hides.

---

## TASK 5 — PartitionPage

**File:** `src/cyberflash/ui/pages/partition_page.py` (replace stub, ~230 lines)

**Layout:** Page header + device bar + `QTabWidget` with 2 tabs

**Tab 1 — Slot Manager** (shown for A/B devices; grayed label "N/A — non-A/B device" otherwise):
- Large display: "Active Slot: A" with a `CyberBadge("success")`, "Inactive: B"
- Two buttons: "Set Active: Slot A" / "Set Active: Slot B"
  - Disabled if that slot is already active
  - On click: confirmation (checkbox "I understand this reboots the device") → `PartitionManager.set_active_slot(serial, slot)` in a one-shot QThread
- Note: "This takes effect after reboot"
- "Reboot now" button after switching

**Tab 2 — Partition Info**:
- "Scan" button → runs `AdbManager.shell(serial, "cat /proc/partitions")` in a one-shot QThread
- Results: `QTableWidget` with columns: major, minor, blocks, name
- Scrollable, sortable by name
- Status label: "X partitions found"

Minimal worker:
```python
class _ScanWorker(BaseWorker):
    result = Signal(str)
    def __init__(self, serial): ...
    @Slot()
    def start(self):
        out = AdbManager.shell(self._serial, "cat /proc/partitions")
        self.result.emit(out)
        self.finished.emit()
```

---

## TASK 6 — BackupPage + BackupWorker

### BackupWorker
**File:** `src/cyberflash/workers/backup_worker.py` (new, ~130 lines)

```python
class BackupWorker(BaseWorker):
    progress = Signal(int, int)   # current, total
    log_line = Signal(str)
    backup_complete = Signal(str) # output path
```

Operations dispatched by a `mode` field:
- `"adb_backup"` → `subprocess.run(adb_cmd + ["-s", serial, "backup", "-apk", "-shared", "-all", "-f", output_path])`
- `"pull_media"` → `subprocess.run(adb_cmd + ["-s", serial, "pull", "/sdcard/", dest_dir])`

### BackupPage
**File:** `src/cyberflash/ui/pages/backup_page.py` (replace stub, ~260 lines)

**Layout:** Page header + device bar + two sections + LogPanel

**Backup section:**
- Output directory: path label + "Browse…" button
- Backup type: `QCheckBox` rows:
  - "App data & APKs (ADB backup)" — `adb backup -apk -shared -all`
  - "Media files (DCIM, Downloads, etc.)" — `adb pull /sdcard/`
- Start Backup button → `BackupWorker` on QThread
- Progress panel below

**Restore section (collapsible frame):**
- "Select backup file…" → `QFileDialog.getOpenFileName` (`.ab` files)
- "Restore" button → `adb restore {file}` via one-shot QThread
- Warning: "Factory reset recommended before restoring"

**LogPanel** at bottom (shared by backup and restore).

---

## TASK 7 — RootPage

**File:** `src/cyberflash/ui/pages/root_page.py` (replace stub, ~250 lines)

**Layout:** Page header + device bar + scrollable wizard sections

**Section 1 — Root Status:**
- Auto-populated from `DeviceInfo.is_rooted` (True/False/None)
- `CyberBadge("success", "Rooted")` / `CyberBadge("warning", "Not Rooted")` / `CyberBadge("neutral", "Unknown")`
- Check root manually: "Verify" button → `AdbManager.shell(serial, "su -c id")` in one-shot thread, looks for `uid=0`

**Section 2 — Root via Magisk (static workflow guide + actions):**
Four numbered steps, each with a status indicator and action button:
1. **Ensure bootloader is unlocked** — reads `DeviceInfo.bootloader_unlocked`, shows ✓/✗
2. **Obtain stock boot image** — informational text + optional file picker
3. **Patch boot image** — file picker for boot.img → `AdbManager.push` to `/sdcard/Download/` → launch Magisk on device via `AdbManager.shell(serial, "am start -n com.topjohnwu.magisk/.ui.MainActivity")`
4. **Flash patched boot image** — file picker for patched_boot.img → uses `FlashEngine.flash_partition("boot", path)` in one-shot QThread

**Section 3 — Unroot (visible only if rooted):**
- "Restore stock boot image" — file picker + flash via FlashEngine
- Warning: "Unrooting removes Magisk and all its modules"

**Section 4 — Notes:**
- SafetyNet/Play Integrity notice
- Banking app compatibility warning
- Link text: "Learn more at topjohnwu.github.io/Magisk"

---

## TASK 8 — NetHunterPage

**File:** `src/cyberflash/ui/pages/nethunter_page.py` (replace stub, ~220 lines)

**Layout:** Page header + device bar + scrollable content

**Section 1 — Prerequisites** (status cards with ✓/✗):
- Bootloader unlocked — from `DeviceInfo.bootloader_unlocked`
- Custom recovery installed — from `DeviceInfo.state == DeviceState.RECOVERY` or inferred
- Sufficient storage — runs `AdbManager.shell(serial, "df -h /data")` to check

**Section 2 — NetHunter Package:**
- Source info: "Download from kali.org/get-kali/#kali-mobile" (displayed as text, not auto-downloaded)
- File picker: "Select NetHunter zip…" → stores path
- Package info: show filename, size once selected

**Section 3 — Installation Method:**
- Radio buttons: "Sideload via ADB" / "Flash via Recovery (TWRP)"
- For sideload: instructions "Put device in sideload mode first"
- For recovery: instructions "Device must be in recovery mode"

**Section 4 — Install:**
- "Start Installation" button → creates `FlashTask` with one `FlashStep(id="sideload_nethunter", label="Sideload NetHunter zip")` and dispatches to `FlashWorker`
- StepTracker (single step) + LogPanel showing output

**Section 5 — Post-Install Notes:**
- Static text: required reboots, Magisk add-on, NetHunter app setup

---

## Implementation Order

```
1.  main_window.py                     — _CyberCentralWidget (background)
2.  themes/cyber_dark.qss              — transparent QStackedWidget + #pageRoot rules
3.  workers/diagnostics_worker.py      — DiagnosticsWorker (new)
4.  workers/backup_worker.py           — BackupWorker (new)
5.  ui/pages/settings_page.py          — full Settings (ConfigService)
6.  ui/pages/diagnostics_page.py       — full Diagnostics + DiagnosticsWorker
7.  ui/pages/terminal_page.py          — full Terminal (QProcess ADB shell)
8.  ui/pages/partition_page.py         — full Partition (slot manager + scan)
9.  ui/pages/backup_page.py            — full Backup + BackupWorker
10. ui/pages/root_page.py              — full Root (Magisk workflow)
11. ui/pages/nethunter_page.py         — full NetHunter (sideload + FlashWorker)
12. tests/unit/test_diagnostics_worker.py   — mock ADB, dry checks
13. tests/unit/test_backup_worker.py        — mock subprocess, verify signals
```

---

## Status

- [ ] Task 1: Cyberpunk background (_CyberCentralWidget)
- [ ] Task 2: SettingsPage
- [ ] Task 3: DiagnosticsPage + DiagnosticsWorker
- [ ] Task 4: TerminalPage
- [ ] Task 5: PartitionPage
- [ ] Task 6: BackupPage + BackupWorker
- [ ] Task 7: RootPage
- [ ] Task 8: NetHunterPage
- [ ] Tests
