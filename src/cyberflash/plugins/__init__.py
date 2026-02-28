"""CyberFlash Plugin System — base abstractions (Phase 12).

Plugins are Python packages that expose a class derived from
:class:`PluginBase`.  The :class:`PluginLoader` discovers and loads them;
the :class:`PluginManager` owns the lifecycle (enable / disable / reload).

Example plugin structure::

    my_plugin/
        __init__.py          ← exposes ``plugin = MyPlugin()``
        cyberflash_plugin.json  ← manifest
        my_worker.py

    # cyberflash_plugin.json
    {
        "id": "my_plugin",
        "name": "My Plugin",
        "version": "1.0.0",
        "author": "Alice",
        "description": "Does something useful.",
        "min_cyberflash": "1.0.0",
        "entry": "my_plugin"
    }
"""

from __future__ import annotations

from cyberflash.plugins.base import PluginBase, PluginManifest
from cyberflash.plugins.loader import PluginLoader
from cyberflash.plugins.manager import PluginManager

__all__ = ["PluginBase", "PluginLoader", "PluginManager", "PluginManifest"]
