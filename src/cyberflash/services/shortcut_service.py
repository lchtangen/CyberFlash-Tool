"""shortcut_service.py — Global keyboard shortcut manager.

Manages QShortcut objects on the main window, supporting user-configurable
key bindings persisted via ConfigService.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QShortcut, QWidget

logger = logging.getLogger(__name__)

# ── Pre-defined actions ───────────────────────────────────────────────────────

_ACTIONS: list[tuple[str, str, str]] = [
    # (action_name, default_key, description)
    ("navigate_dashboard",   "Ctrl+1",       "Navigate to Dashboard page"),
    ("navigate_flash",       "Ctrl+2",       "Navigate to Flash page"),
    ("navigate_root",        "Ctrl+3",       "Navigate to Root page"),
    ("navigate_backup",      "Ctrl+4",       "Navigate to Backup page"),
    ("navigate_diagnostics", "Ctrl+5",       "Navigate to Diagnostics page"),
    ("navigate_settings",    "Ctrl+,",       "Open Settings page"),
    ("refresh_devices",      "F5",           "Refresh device list"),
    ("start_flash",          "Ctrl+Return",  "Start flash operation"),
    ("toggle_sidebar",       "Ctrl+\\",      "Toggle sidebar"),
    ("open_terminal",        "Ctrl+`",       "Open terminal page"),
    ("open_journal",         "Ctrl+J",       "Open flash journal"),
    ("show_shortcuts",       "Ctrl+Shift+/", "Show this cheatsheet"),
]


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class ShortcutAction:
    """A named keyboard shortcut action."""

    name: str
    default_key: str
    description: str


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: ShortcutService | None = None


class ShortcutService:
    """Singleton keyboard shortcut registry."""

    def __init__(self) -> None:
        self._actions: dict[str, ShortcutAction] = {}
        self._shortcuts: dict[str, QShortcut] = {}
        self._bindings: dict[str, str] = {}  # action_name → key string
        self._load_defaults()

    def _load_defaults(self) -> None:
        for name, key, desc in _ACTIONS:
            self._actions[name] = ShortcutAction(name=name, default_key=key, description=desc)
            self._bindings[name] = key

    @classmethod
    def instance(cls) -> ShortcutService:
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    # ── Public API ────────────────────────────────────────────────────────────

    def register(
        self,
        action: str,
        callback: Callable[[], None],
        parent_widget: QWidget,
    ) -> QShortcut | None:
        """Create a QShortcut for *action* on *parent_widget*.

        Returns the created QShortcut, or None if action is unknown.
        """
        shortcut_action = self._actions.get(action)
        if not shortcut_action:
            logger.warning("ShortcutService: unknown action %s", action)
            return None

        key = self._bindings.get(action, shortcut_action.default_key)
        shortcut = QShortcut(QKeySequence(key), parent_widget)
        shortcut.activated.connect(callback)
        self._shortcuts[action] = shortcut
        logger.debug("Registered shortcut %s → %s", key, action)
        return shortcut

    def set_binding(self, action: str, key: str) -> None:
        """Update key binding for *action*.  Resets existing QShortcut if any."""
        self._bindings[action] = key
        shortcut = self._shortcuts.get(action)
        if shortcut:
            shortcut.setKey(QKeySequence(key))

    def get_binding(self, action: str) -> str:
        """Return current key string for *action*."""
        default = self._actions.get(action)
        return self._bindings.get(action, default.default_key if default else "")

    def get_cheatsheet(self) -> list[tuple[str, str]]:
        """Return list of (key, description) pairs for all registered actions."""
        result: list[tuple[str, str]] = []
        for name, action in self._actions.items():
            key = self._bindings.get(name, action.default_key)
            result.append((key, action.description))
        return result

    def save_bindings(self) -> None:
        """Persist current bindings to ConfigService."""
        try:
            from cyberflash.services.config_service import ConfigService
            cfg = ConfigService.instance()
            for name, key in self._bindings.items():
                cfg.set(f"shortcuts/{name}", key)
        except Exception as exc:
            logger.warning("ShortcutService: save_bindings failed: %s", exc)

    def load_bindings(self) -> None:
        """Load persisted bindings from ConfigService."""
        try:
            from cyberflash.services.config_service import ConfigService
            cfg = ConfigService.instance()
            for name in self._actions:
                key = cfg.get_str(f"shortcuts/{name}")
                if key:
                    self._bindings[name] = key
        except Exception as exc:
            logger.warning("ShortcutService: load_bindings failed: %s", exc)
