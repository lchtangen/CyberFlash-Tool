"""plugins/base.py — Abstract base class for CyberFlash plugins (Phase 12)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PluginManifest:
    """Parsed contents of ``cyberflash_plugin.json``."""

    plugin_id: str
    name: str
    version: str
    author: str = ""
    description: str = ""
    min_cyberflash: str = "1.0.0"
    entry: str = ""
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        """Parse a manifest from a JSON-decoded dictionary."""
        return cls(
            plugin_id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            description=data.get("description", ""),
            min_cyberflash=data.get("min_cyberflash", "1.0.0"),
            entry=data.get("entry", ""),
            tags=data.get("tags", []),
        )

    def is_valid(self) -> bool:
        """Return ``True`` if the manifest has at least id + name + entry."""
        return bool(self.plugin_id and self.name and self.entry)


class PluginBase(ABC):
    """Abstract base class every CyberFlash plugin must subclass.

    Lifecycle::

        plugin = MyPlugin()
        plugin.activate(services)   ← called when plugin is enabled
        plugin.deactivate()         ← called when plugin is disabled/removed

    Attributes:
        manifest: The plugin's :class:`PluginManifest`.
        _active: ``True`` after :meth:`activate`; ``False`` after :meth:`deactivate`.
    """

    def __init__(self) -> None:
        self.manifest: PluginManifest | None = None
        self._active: bool = False

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique, dotted-namespace ID, e.g. ``"com.example.my_plugin"``."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable plugin name."""

    @property
    def version(self) -> str:
        """Plugin version string (default ``"1.0.0"``)."""
        return "1.0.0"

    @property
    def author(self) -> str:
        """Plugin author name."""
        return ""

    @property
    def description(self) -> str:
        """Short description shown in the plugin manager UI."""
        return ""

    # ------------------------------------------------------------------
    # Lifecycle hooks (override in subclass)
    # ------------------------------------------------------------------

    def activate(self, services: dict[str, Any] | None = None) -> bool:
        """Called when the plugin is enabled.

        *services* is a dict of core service objects the plugin may use
        (e.g. ``{"event_bus": EventBus.instance(), "worker_registry": ...}``).

        Return ``True`` on success, ``False`` to abort activation.
        """
        self._active = True
        logger.info("Plugin '%s' activated", self.plugin_id)
        return True

    def deactivate(self) -> None:
        """Called when the plugin is disabled or CyberFlash exits."""
        self._active = False
        logger.info("Plugin '%s' deactivated", self.plugin_id)

    def on_device_connected(self, serial: str) -> None:  # noqa: B027
        """Optional hook: called when a new device is detected."""

    def on_device_disconnected(self, serial: str) -> None:  # noqa: B027
        """Optional hook: called when a device is removed."""

    # ------------------------------------------------------------------
    # Page registration
    # ------------------------------------------------------------------

    def pages(self) -> list[dict[str, Any]]:
        """Return a list of page descriptors for the sidebar.

        Each dict must have::

            {"id": str, "label": str, "icon": str, "widget_factory": callable}

        The ``widget_factory`` is called with no args and must return a QWidget.
        """
        return []

    # ------------------------------------------------------------------
    # Worker registration
    # ------------------------------------------------------------------

    def workers(self) -> dict[str, type]:
        """Return a ``{name: WorkerClass}`` mapping for :class:`WorkerRegistry`."""
        return {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self._active

    def __repr__(self) -> str:
        return f"<Plugin {self.plugin_id!r} v{self.version} active={self._active}>"
