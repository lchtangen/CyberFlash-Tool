"""Persistent application settings using QSettings.

This service provides typed access to all user-configurable options and
automatically persists them to the platform-native storage (INI on Linux,
plist on macOS, registry on Windows).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal

from cyberflash import __app_name__

# ── Default values ────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, object] = {
    "theme": "cyber_dark",
    "device/poll_interval_ms": 2000,
    "device/auto_select_single": True,
    "flash/dry_run_default": False,
    "flash/confirm_dangerous_ops": True,
    "flash/auto_verify_hash": True,
    "logging/file_enabled": True,
    "logging/max_file_size_mb": 10,
    "logging/backup_count": 5,
    "ui/sidebar_collapsed": False,
    "ui/geometry": b"",
    "ui/window_state": b"",
    "downloads/directory": "",
    "downloads/parallel_max": 2,
    "ai/gemini_api_key": "",
    "ai/gemini_model": "gemini-2.5-flash",
}


class ConfigService(QObject):
    """Type-safe wrapper around QSettings with defaults and change signals.

    Usage::

        config = ConfigService()
        theme = config.get_str("theme")
        config.set("theme", "cyber_green")
    """

    value_changed = Signal(str, object)  # key, new_value

    _instance: ConfigService | None = None

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings(__app_name__, __app_name__)

    # ── Singleton access (optional convenience) ──────────────────────────────

    @classmethod
    def instance(cls) -> ConfigService:
        if cls._instance is None:
            cls._instance = ConfigService()
        return cls._instance

    # ── Generic get / set ────────────────────────────────────────────────────

    def get(self, key: str) -> object:
        """Return stored value or the default from _DEFAULTS."""
        default = _DEFAULTS.get(key)
        return self._settings.value(key, default)

    def get_str(self, key: str) -> str:
        return str(self.get(key) or "")

    def get_int(self, key: str) -> int:
        val = self.get(key)
        try:
            return int(val)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return int(_DEFAULTS.get(key, 0))  # type: ignore[arg-type]

    def get_bool(self, key: str) -> bool:
        val = self.get(key)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return bool(val)

    def get_bytes(self, key: str) -> bytes:
        val = self._settings.value(key, _DEFAULTS.get(key, b""))
        if isinstance(val, (bytes, bytearray)):
            return bytes(val)
        return b""

    def set(self, key: str, value: object) -> None:
        self._settings.setValue(key, value)
        self.value_changed.emit(key, value)

    # ── Batch / reset ────────────────────────────────────────────────────────

    def reset_to_defaults(self) -> None:
        self._settings.clear()
        for key, value in _DEFAULTS.items():
            self._settings.setValue(key, value)

    def all_keys(self) -> list[str]:
        return list(_DEFAULTS.keys())

    def sync(self) -> None:
        """Flush pending writes to disk."""
        self._settings.sync()
