"""screen_manager.py — Android screen capture, recording, and mirror helpers.

Provides screenshot, screenrecord (via ADB), and optional scrcpy mirror.
All methods are synchronous and UI-agnostic.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from cyberflash.core.adb_manager import AdbManager
from cyberflash.core.tool_manager import ToolManager

logger = logging.getLogger(__name__)

# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class CaptureResult:
    """Result of a screenshot or screen recording operation."""

    success: bool
    local_path: Path | None = None
    error: str = ""


# ── Main class ────────────────────────────────────────────────────────────────


class ScreenManager:
    """Classmethod-only screen capture and control utilities."""

    @classmethod
    def screenshot(cls, serial: str, dest_dir: Path) -> CaptureResult:
        """Capture a screenshot from *serial* and save to *dest_dir*.

        Runs ``adb shell screencap -p`` and pulls the result.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        remote_path = "/sdcard/cyberflash_screenshot.png"
        local_path = dest_dir / f"screenshot_{serial}.png"

        # Take screenshot on device
        rc, _, stderr = AdbManager._run(
            ["-s", serial, "shell", "screencap", "-p", remote_path], timeout=15
        )
        if rc != 0:
            return CaptureResult(success=False, error=f"screencap failed: {stderr.strip()}")

        # Pull to local
        ok = AdbManager.pull(serial, remote_path, str(local_path))
        AdbManager.shell(serial, f"rm -f {remote_path}")  # cleanup

        if not ok:
            return CaptureResult(success=False, error="adb pull failed")
        return CaptureResult(success=True, local_path=local_path)

    @classmethod
    def record(
        cls,
        serial: str,
        dest_dir: Path,
        duration_s: int = 30,
        bitrate: int = 4_000_000,
    ) -> CaptureResult:
        """Record device screen for *duration_s* seconds.

        Uses ``adb shell screenrecord`` (Android 4.4+).
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        remote_path = "/sdcard/cyberflash_record.mp4"
        local_path = dest_dir / f"screenrecord_{serial}.mp4"

        rc, _, stderr = AdbManager._run(
            [
                "-s", serial, "shell", "screenrecord",
                "--time-limit", str(duration_s),
                "--bit-rate", str(bitrate),
                remote_path,
            ],
            timeout=duration_s + 10,
        )
        if rc != 0:
            return CaptureResult(success=False, error=f"screenrecord failed: {stderr.strip()}")

        ok = AdbManager.pull(serial, remote_path, str(local_path))
        AdbManager.shell(serial, f"rm -f {remote_path}")

        if not ok:
            return CaptureResult(success=False, error="adb pull failed")
        return CaptureResult(success=True, local_path=local_path)

    @classmethod
    def start_mirror(cls, serial: str) -> subprocess.Popen | None:  # type: ignore[type-arg]
        """Launch scrcpy for live screen mirroring.  Returns the Popen handle."""
        scrcpy = ToolManager.find_tool("scrcpy")
        if not scrcpy:
            logger.warning("scrcpy not found in PATH")
            return None
        try:
            proc = subprocess.Popen(
                [scrcpy, "--serial", serial],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return proc
        except OSError as exc:
            logger.warning("scrcpy launch failed: %s", exc)
            return None

    @classmethod
    def stop_mirror(cls, proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
        """Terminate a running scrcpy process."""
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    @classmethod
    def inject_tap(cls, serial: str, x: int, y: int) -> bool:
        """Inject a tap event at screen coordinates (x, y)."""
        result = AdbManager.shell(serial, f"input tap {x} {y}", timeout=5)
        return "error" not in result.lower()

    @classmethod
    def inject_key(cls, serial: str, keycode: int) -> bool:
        """Inject a key event by Android keycode."""
        result = AdbManager.shell(serial, f"input keyevent {keycode}", timeout=5)
        return "error" not in result.lower()
