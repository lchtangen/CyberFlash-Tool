from __future__ import annotations

import sys
from pathlib import Path


def get_platform() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    elif sys.platform == "darwin":
        return "macos"
    elif sys.platform == "win32":
        return "windows"
    return "linux"


def _is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _project_root() -> Path:
    """Locate the project root, works in dev mode and when frozen."""
    if _is_frozen():
        # PyInstaller unpacks to sys._MEIPASS
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # Dev mode: navigate up from this file to the repo root
    return Path(__file__).resolve().parent.parent.parent.parent


def get_tools_dir() -> Path:
    platform = get_platform()
    return _project_root() / "resources" / "tools" / platform


def get_resources_dir() -> Path:
    """Return the top-level resources/ directory."""
    return _project_root() / "resources"


def get_app_data_dir() -> Path:
    platform = get_platform()
    if platform == "linux":
        base = Path.home() / ".local" / "share" / "CyberFlash"
    elif platform == "macos":
        base = Path.home() / "Library" / "Application Support" / "CyberFlash"
    else:
        import os

        appdata = os.environ.get("APPDATA", str(Path.home()))
        base = Path(appdata) / "CyberFlash"
    return base
