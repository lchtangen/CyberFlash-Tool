"""plugins/manager.py — Plugin lifecycle manager (Phase 12)."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from cyberflash.plugins.base import PluginBase, PluginManifest
from cyberflash.plugins.loader import PluginLoader, PluginLoadError

logger = logging.getLogger(__name__)


class PluginManager(QObject):
    """Manages the full lifecycle of installed plugins.

    Plugins can be loaded from any directory by calling :meth:`load_plugin`
    or auto-loaded from the default plugin directory via :meth:`load_all`.

    Signals:
        plugin_loaded(str): plugin_id after successful load + activate.
        plugin_unloaded(str): plugin_id after deactivate + removal.
        plugin_error(str, str): plugin_id, error message on failure.
    """

    plugin_loaded = Signal(str)
    plugin_unloaded = Signal(str)
    plugin_error = Signal(str, str)

    def __init__(
        self,
        loader: PluginLoader | None = None,
        services: dict[str, Any] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._loader = loader or PluginLoader()
        self._services = services or {}
        self._plugins: dict[str, PluginBase] = {}   # plugin_id → instance

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_all(self) -> list[str]:
        """Discover and load all plugins in the plugin directory.

        Returns the list of successfully loaded plugin IDs.
        """
        manifests: list[PluginManifest] = self._loader.discover()
        loaded: list[str] = []
        for manifest in manifests:
            try:
                plugin = self._loader.load(manifest.entry)
                plugin.manifest = manifest
                self._add_plugin(plugin)
                loaded.append(plugin.plugin_id)
            except (PluginLoadError, Exception) as exc:
                logger.warning("Failed to load plugin '%s': %s", manifest.plugin_id, exc)
                self.plugin_error.emit(manifest.plugin_id, str(exc))
        return loaded

    def load_plugin(self, entry_module: str) -> bool:
        """Import and activate a plugin by its entry module name.

        Returns ``True`` on success.
        """
        try:
            plugin = self._loader.load(entry_module)
            self._add_plugin(plugin)
            return True
        except (PluginLoadError, Exception) as exc:
            msg = str(exc)
            logger.warning("load_plugin '%s' failed: %s", entry_module, msg)
            self.plugin_error.emit(entry_module, msg)
            return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def enable_plugin(self, plugin_id: str) -> bool:
        """Enable (re-activate) a previously disabled plugin."""
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return False
        if plugin.is_active:
            return True
        return plugin.activate(self._services)

    def disable_plugin(self, plugin_id: str) -> bool:
        """Deactivate a plugin without removing it from the registry."""
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return False
        plugin.deactivate()
        return True

    def unload_plugin(self, plugin_id: str) -> bool:
        """Deactivate and remove a plugin from the registry."""
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return False
        if plugin.is_active:
            plugin.deactivate()
        del self._plugins[plugin_id]
        self.plugin_unloaded.emit(plugin_id)
        return True

    def unload_all(self) -> None:
        """Deactivate and remove all loaded plugins."""
        for pid in list(self._plugins.keys()):
            self.unload_plugin(pid)

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def get_plugin(self, plugin_id: str) -> PluginBase | None:
        return self._plugins.get(plugin_id)

    def list_plugins(self) -> list[PluginBase]:
        return list(self._plugins.values())

    def is_loaded(self, plugin_id: str) -> bool:
        return plugin_id in self._plugins

    def count(self) -> int:
        return len(self._plugins)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _add_plugin(self, plugin: PluginBase) -> None:
        plugin_id = plugin.plugin_id
        if plugin_id in self._plugins:
            logger.debug("Plugin '%s' already loaded — skipping", plugin_id)
            return
        ok = plugin.activate(self._services)
        if not ok:
            raise PluginLoadError(f"Plugin '{plugin_id}' activation returned False")
        self._plugins[plugin_id] = plugin
        logger.info("Plugin loaded: %s v%s", plugin.name, plugin.version)
        self.plugin_loaded.emit(plugin_id)
