"""crash_service.py — Global exception handler and crash dump manager.

Installs a sys.excepthook that captures unhandled exceptions, writes
local crash dumps, and optionally provides a pre-filled GitHub Issues URL.
"""

from __future__ import annotations

import logging
import platform
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

from cyberflash import __version__

logger = logging.getLogger(__name__)

_CRASH_DIR = Path.home() / ".cyberflash" / "crashes"
_GITHUB_ISSUES_URL = "https://github.com/cyberflash-dev/cyberflash/issues/new"

# Singleton instance
_instance: CrashService | None = None


class CrashService:
    """Singleton crash handler — call install() once at app startup."""

    def __init__(self) -> None:
        self._original_excepthook = sys.excepthook
        self._installed = False
        # Pre-bind so `service._handle_exception is sys.excepthook` works after install()
        self._handle_exception = self._handle_exception  # type: ignore[assignment]

    # ── Singleton ─────────────────────────────────────────────────────────────

    @classmethod
    def instance(cls) -> CrashService:
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    # ── Public API ────────────────────────────────────────────────────────────

    def install(self) -> None:
        """Install the global exception hook.  Safe to call multiple times."""
        if self._installed:
            return
        sys.excepthook = self._handle_exception
        self._installed = True
        logger.debug("CrashService: exception hook installed")

    def get_crash_dumps(self) -> list[Path]:
        """Return sorted list of crash dump files (newest first)."""
        if not _CRASH_DIR.exists():
            return []
        dumps = list(_CRASH_DIR.glob("crash_*.txt"))
        dumps.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return dumps

    def open_dump(self, path: Path) -> str:
        """Return the content of a crash dump file."""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"Could not read {path}: {exc}"

    def build_github_url(self, dump_text: str) -> str:
        """Return a GitHub Issues URL pre-filled with crash info."""
        import urllib.parse

        body = (
            "**Crash Report**\n\n"
            "```\n"
            + dump_text[:3000]
            + "\n```\n\n"
            "**Steps to reproduce:**\n"
            "1. \n\n"
            "**Expected behavior:**\n\n"
            "**Platform:** "
            + platform.platform()
        )
        params = urllib.parse.urlencode({"title": "Crash Report", "body": body})
        return f"{_GITHUB_ISSUES_URL}?{params}"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _handle_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: object,
    ) -> None:
        """Custom sys.excepthook — writes crash dump and logs."""
        if issubclass(exc_type, KeyboardInterrupt):
            self._original_excepthook(exc_type, exc_value, exc_tb)
            return

        tb_text = "".join(
            traceback.format_exception(exc_type, exc_value, exc_tb)  # type: ignore[arg-type]
        )
        dump = self._build_dump(tb_text)
        path = self._write_dump(dump)

        logger.critical("Unhandled exception:\n%s", tb_text)
        if path:
            logger.info("Crash dump written to: %s", path)

        # Also call Qt's default handler for GUI crash dialogs
        self._original_excepthook(exc_type, exc_value, exc_tb)

    def _build_dump(self, tb_text: str) -> str:
        return (
            f"CyberFlash Crash Report\n"
            f"{'=' * 60}\n"
            f"Version:  {__version__}\n"
            f"Date:     {datetime.now(UTC).isoformat()}\n"
            f"Platform: {platform.platform()}\n"
            f"Python:   {sys.version}\n"
            f"{'=' * 60}\n\n"
            f"{tb_text}"
        )

    def _write_dump(self, dump: str) -> Path | None:
        try:
            _CRASH_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            path = _CRASH_DIR / f"crash_{ts}.txt"
            path.write_text(dump, encoding="utf-8")
            return path
        except OSError as exc:
            logger.error("Could not write crash dump: %s", exc)
            return None
