"""plugins/loader.py — Plugin discovery and loading (Phase 12)."""

from __future__ import annotations

import importlib
import json
import logging
import sys
from pathlib import Path

from cyberflash.plugins.base import PluginBase, PluginManifest

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "cyberflash_plugin.json"


class PluginLoadError(Exception):
    """Raised when a plugin fails to load."""


class PluginLoader:
    """Discovers, validates, and imports CyberFlash plugin packages.

    Usage::

        loader = PluginLoader(plugin_dir=Path("~/.cyberflash/plugins"))
        manifests = loader.discover()      # scan without importing
        plugin = loader.load("my_plugin")  # import + instantiate
    """

    def __init__(self, plugin_dir: Path | str | None = None) -> None:
        if plugin_dir is None:
            plugin_dir = Path.home() / ".cyberflash" / "plugins"
        self._plugin_dir = Path(plugin_dir)

    @property
    def plugin_dir(self) -> Path:
        return self._plugin_dir

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[PluginManifest]:
        """Scan *plugin_dir* for plugin packages. Returns manifest list."""
        manifests: list[PluginManifest] = []
        if not self._plugin_dir.is_dir():
            logger.debug("Plugin dir does not exist: %s", self._plugin_dir)
            return manifests
        for child in self._plugin_dir.iterdir():
            manifest_path = child / _MANIFEST_NAME
            if not manifest_path.is_file():
                continue
            try:
                manifest = self._read_manifest(manifest_path)
                if manifest.is_valid():
                    manifests.append(manifest)
                    logger.debug("Discovered plugin: %s", manifest.plugin_id)
                else:
                    logger.warning("Invalid manifest at %s", manifest_path)
            except Exception as exc:
                logger.warning("Failed to read manifest %s: %s", manifest_path, exc)
        return manifests

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, entry_module: str) -> PluginBase:
        """Import *entry_module*, find and instantiate its :class:`PluginBase`.

        The plugin directory is added to ``sys.path`` if needed.

        Raises :class:`PluginLoadError` on any failure.
        """
        # Ensure plugin_dir is importable
        parent = str(self._plugin_dir)
        if parent not in sys.path:
            sys.path.insert(0, parent)

        try:
            module = importlib.import_module(entry_module)
        except ImportError as exc:
            raise PluginLoadError(f"Cannot import '{entry_module}': {exc}") from exc

        # Find PluginBase subclass in the module
        plugin_cls = None
        for attr_name in dir(module):
            obj = getattr(module, attr_name, None)
            if (
                isinstance(obj, type)
                and issubclass(obj, PluginBase)
                and obj is not PluginBase
            ):
                plugin_cls = obj
                break

        if plugin_cls is None:
            # Try the conventional ``plugin`` attribute
            plugin_inst = getattr(module, "plugin", None)
            if isinstance(plugin_inst, PluginBase):
                return plugin_inst
            raise PluginLoadError(
                f"No PluginBase subclass found in module '{entry_module}'"
            )

        try:
            return plugin_cls()
        except Exception as exc:
            raise PluginLoadError(
                f"Failed to instantiate plugin from '{entry_module}': {exc}"
            ) from exc

    def load_from_path(self, plugin_path: Path) -> PluginBase:
        """Load a plugin directly from its directory path."""
        manifest_path = plugin_path / _MANIFEST_NAME
        manifest = self._read_manifest(manifest_path) if manifest_path.is_file() else None

        entry = manifest.entry if manifest else plugin_path.name
        plugin_dir_parent = str(plugin_path.parent)
        if plugin_dir_parent not in sys.path:
            sys.path.insert(0, plugin_dir_parent)

        plugin = self.load(entry)
        if manifest:
            plugin.manifest = manifest
        return plugin

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_manifest(path: Path) -> PluginManifest:
        data = json.loads(path.read_text(encoding="utf-8"))
        return PluginManifest.from_dict(data)
