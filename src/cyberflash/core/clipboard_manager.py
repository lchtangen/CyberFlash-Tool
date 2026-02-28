"""clipboard_manager.py — Phone ↔ Desktop clipboard synchronisation via ADB.

Pushes desktop clipboard content to a device or pulls device clipboard
content to the desktop using ``adb shell`` and ``content`` provider commands.

All public methods are classmethods;  none raise exceptions — failures are
reported via the return value / log_cb.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)

# ── ADB clipboard content URIs ────────────────────────────────────────────────

_CLIP_URI = "content://com.android.providers.clipboard/primaryclip"
_INPUT_CMD = "input text"    # fallback: simulates key-event paste

# Clipboard Binder helper available on Android 9+ / Magisk root shells
_GET_CMD = "service call clipboard 2 s16 com.android.providers.clipboard"


class ClipboardManager:
    """Sync clipboard content between the host machine and an Android device."""

    @classmethod
    def push_to_device(
        cls,
        serial: str,
        text: str,
        log_cb: Callable[[str], None] | None = None,
    ) -> bool:
        """Push ``text`` to the device clipboard.

        Uses ``am broadcast`` with ``CLIP_DATA_TEXT`` which works on Android 7+
        without root by relying on the ``am`` command.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        def _log(msg: str) -> None:
            logger.debug(msg)
            if log_cb:
                log_cb(msg)

        if not text:
            _log(f"[{serial}] push_to_device: empty text — nothing to push")
            return True

        # Escape single-quotes for the shell command
        escaped = text.replace("'", "'\\''")
        cmd = (
            f"am broadcast -a clipper.SET --es text '{escaped}' "
            f"com.example.clipper 2>/dev/null "
            f"|| content insert --uri {_CLIP_URI} --bind data:s:{escaped}"
        )
        _log(f"[{serial}] Pushing {len(text)} chars to device clipboard")
        output = AdbManager.shell(serial, cmd, timeout=10)
        success = "Exception" not in output and "Error" not in output
        if success:
            _log(f"[{serial}] Clipboard push succeeded")
        else:
            _log(f"[{serial}] Clipboard push may have failed: {output[:120]}")
        return success

    @classmethod
    def pull_from_device(
        cls,
        serial: str,
        log_cb: Callable[[str], None] | None = None,
    ) -> str:
        """Pull the current device clipboard content.

        Returns the clipboard text string, or ``""`` on failure.
        """
        def _log(msg: str) -> None:
            logger.debug(msg)
            if log_cb:
                log_cb(msg)

        _log(f"[{serial}] Pulling clipboard from device")
        # Try content provider query first (Android 10+)
        output = AdbManager.shell(
            serial,
            "content query --uri content://com.android.providers.clipboard/primaryclip",
            timeout=10,
        )
        if output and "Row:" in output:
            for part in output.split(","):
                if "data=" in part:
                    text = part.split("data=", 1)[1].strip()
                    _log(f"[{serial}] Pulled {len(text)} chars from clipboard")
                    return text

        # Fallback: dumpsys clipboard (requires root or debug mode)
        output = AdbManager.shell(serial, "dumpsys clipboard 2>/dev/null | head -20", timeout=10)
        if output:
            for line in output.splitlines():
                if "mText=" in line:
                    text = line.split("mText=", 1)[1].strip().strip("'\"")
                    _log(f"[{serial}] Pulled text via dumpsys: {len(text)} chars")
                    return text

        _log(f"[{serial}] Could not read device clipboard (may require root)")
        return ""

    @classmethod
    def sync_to_device(
        cls,
        serial: str,
        log_cb: Callable[[str], None] | None = None,
    ) -> bool:
        """Convenience: copy the HOST clipboard to the device.

        Reads the host's clipboard via ``xclip`` / ``xsel`` / ``pbpaste`` and
        pushes the result to the device.  Best effort — returns ``True`` if the
        push was attempted.
        """
        text = cls._get_host_clipboard()
        if text is None:
            if log_cb:
                log_cb("Cannot read host clipboard (install xclip or xsel)")
            return False
        return cls.push_to_device(serial, text, log_cb=log_cb)

    @classmethod
    def sync_to_host(
        cls,
        serial: str,
        log_cb: Callable[[str], None] | None = None,
    ) -> bool:
        """Convenience: copy the device clipboard to the HOST clipboard.

        Returns ``True`` if host clipboard was updated.
        """
        text = cls.pull_from_device(serial, log_cb=log_cb)
        if not text:
            return False
        return cls._set_host_clipboard(text)

    # ── Internal host-clipboard helpers ──────────────────────────────────────

    @staticmethod
    def _get_host_clipboard() -> str | None:
        """Try to read the host clipboard.  Returns ``None`` if unavailable."""
        import subprocess

        for cmd in [["xclip", "-o", "-sel", "clip"], ["xsel", "--clipboard", "--output"],
                    ["pbpaste"], ["wl-paste"]]:
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=3, check=False
                )
                if result.returncode == 0:
                    return result.stdout
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return None

    @staticmethod
    def _set_host_clipboard(text: str) -> bool:
        """Try to write the host clipboard.  Returns ``True`` on success."""
        import subprocess

        for cmd in [
            ["xclip", "-sel", "clip"],
            ["xsel", "--clipboard", "--input"],
            ["pbcopy"],
            ["wl-copy"],
        ]:
            try:
                result = subprocess.run(
                    cmd, input=text, text=True, timeout=3, check=False
                )
                if result.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return False
