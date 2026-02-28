"""tests/unit/test_plugin_loader.py — Unit tests for PluginLoader."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from cyberflash.plugins.base import PluginBase
from cyberflash.plugins.loader import PluginLoader, PluginLoadError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakePlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "com.test.fake"

    @property
    def name(self) -> str:
        return "Fake Plugin"


# ---------------------------------------------------------------------------
# PluginManifest discovery (on-disk)
# ---------------------------------------------------------------------------


class TestPluginLoaderDiscover:
    def test_discover_empty_dir(self, tmp_path: Path) -> None:
        loader = PluginLoader(plugin_dir=str(tmp_path))
        manifests = loader.discover()
        assert manifests == []

    def test_discover_finds_manifest(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "myplugin"
        plugin_dir.mkdir()
        manifest_data = {
            "id": "com.test.myplugin",
            "name": "My Plugin",
            "version": "1.0.0",
            "entry": "myplugin",
        }
        (plugin_dir / "cyberflash_plugin.json").write_text(json.dumps(manifest_data))
        loader = PluginLoader(plugin_dir=str(tmp_path))
        manifests = loader.discover()
        assert len(manifests) == 1
        assert manifests[0].plugin_id == "com.test.myplugin"

    def test_discover_skips_invalid_manifests(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "broken"
        plugin_dir.mkdir()
        (plugin_dir / "cyberflash_plugin.json").write_text("{invalid json{")
        loader = PluginLoader(plugin_dir=str(tmp_path))
        manifests = loader.discover()
        assert manifests == []

    def test_discover_skips_incomplete_manifests(self, tmp_path: Path) -> None:
        """Manifests without id+name+entry should be skipped."""
        plugin_dir = tmp_path / "incomplete"
        plugin_dir.mkdir()
        (plugin_dir / "cyberflash_plugin.json").write_text(
            json.dumps({"id": "x", "name": "", "entry": "e"})
        )
        loader = PluginLoader(plugin_dir=str(tmp_path))
        manifests = loader.discover()
        assert manifests == []


# ---------------------------------------------------------------------------
# PluginLoader.load — module-level fake
# ---------------------------------------------------------------------------


class TestPluginLoaderLoad:
    def test_load_finds_plugin_class_in_module(self) -> None:
        module_name = "_test_plugin_mod_abc"
        fake_module = types.ModuleType(module_name)
        fake_module._FakePlugin = _FakePlugin  # type: ignore[attr-defined]
        sys.modules[module_name] = fake_module

        loader = PluginLoader()
        try:
            plugin = loader.load(module_name)
            assert isinstance(plugin, PluginBase)
        finally:
            del sys.modules[module_name]

    def test_load_finds_plugin_attribute(self) -> None:
        module_name = "_test_plugin_attr_xyz"
        fake_module = types.ModuleType(module_name)
        fake_module.plugin = _FakePlugin()  # type: ignore[attr-defined]
        sys.modules[module_name] = fake_module

        loader = PluginLoader()
        try:
            plugin = loader.load(module_name)
            assert isinstance(plugin, PluginBase)
        finally:
            del sys.modules[module_name]

    def test_load_raises_on_no_plugin_in_module(self) -> None:
        module_name = "_test_plugin_empty_zzz"
        fake_module = types.ModuleType(module_name)
        sys.modules[module_name] = fake_module

        loader = PluginLoader()
        try:
            with pytest.raises(PluginLoadError, match="No PluginBase subclass"):
                loader.load(module_name)
        finally:
            del sys.modules[module_name]

    def test_load_raises_on_import_error(self) -> None:
        loader = PluginLoader()
        with pytest.raises(PluginLoadError):
            loader.load("module_that_absolutely_does_not_exist_xyz987")


# ---------------------------------------------------------------------------
# PluginLoader.load_from_path
# ---------------------------------------------------------------------------


class TestPluginLoaderFromPath:
    def test_load_from_path_with_manifest(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "mypkg"
        plugin_dir.mkdir()

        manifest_data = {
            "id": "com.test.frompath",
            "name": "FromPath Plugin",
            "entry": "_test_frompath_module_99",
        }
        (plugin_dir / "cyberflash_plugin.json").write_text(json.dumps(manifest_data))

        module_name = "_test_frompath_module_99"
        fake_mod = types.ModuleType(module_name)
        fake_mod._FakePlugin = _FakePlugin  # type: ignore[attr-defined]
        sys.modules[module_name] = fake_mod

        loader = PluginLoader()
        try:
            plugin = loader.load_from_path(plugin_dir)
            assert isinstance(plugin, PluginBase)
        finally:
            del sys.modules[module_name]

    def test_load_from_path_no_manifest_uses_dir_name(self, tmp_path: Path) -> None:
        """Falls back to directory name as entry module when no manifest."""
        dir_name = "_testpkg_nomanifest_88"
        plugin_dir = tmp_path / dir_name
        plugin_dir.mkdir()

        module_name = dir_name
        fake_mod = types.ModuleType(module_name)
        fake_mod._FakePlugin = _FakePlugin  # type: ignore[attr-defined]
        sys.modules[module_name] = fake_mod

        loader = PluginLoader()
        try:
            plugin = loader.load_from_path(plugin_dir)
            assert isinstance(plugin, PluginBase)
        finally:
            del sys.modules[module_name]
