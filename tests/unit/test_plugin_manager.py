"""tests/unit/test_plugin_manager.py — Unit tests for PluginManager."""

from __future__ import annotations

from unittest.mock import MagicMock

from cyberflash.plugins.base import PluginBase, PluginManifest
from cyberflash.plugins.loader import PluginLoader, PluginLoadError
from cyberflash.plugins.manager import PluginManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _WorkingPlugin(PluginBase):
    activate_called: bool = False
    deactivate_called: bool = False

    @property
    def plugin_id(self) -> str:
        return "com.test.working"

    @property
    def name(self) -> str:
        return "Working Plugin"

    def activate(self, services: dict | None = None) -> bool:
        _WorkingPlugin.activate_called = True
        return super().activate(services)

    def deactivate(self) -> None:
        _WorkingPlugin.deactivate_called = True
        super().deactivate()


class _FailPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "com.test.fail"

    @property
    def name(self) -> str:
        return "Fail Plugin"

    def activate(self, services: dict | None = None) -> bool:
        return False  # refuses to activate


def _make_loader_with(plugin: PluginBase | None = None, manifest_list: list | None = None) -> PluginLoader:
    """Return a PluginLoader whose methods are pre-mocked."""
    loader = MagicMock(spec=PluginLoader)
    loader.discover.return_value = manifest_list or []
    if plugin is not None:
        loader.load.return_value = plugin
    else:
        loader.load.side_effect = PluginLoadError("module not found")
    return loader


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


class TestPluginManagerInit:
    def test_empty_on_init(self, qapp: object) -> None:
        mgr = PluginManager()
        assert mgr.count() == 0
        assert mgr.list_plugins() == []


# ---------------------------------------------------------------------------
# load_plugin
# ---------------------------------------------------------------------------


class TestPluginManagerLoadPlugin:
    def test_load_plugin_activates_and_stores(self, qapp: object) -> None:
        plugin = _WorkingPlugin()
        loader = _make_loader_with(plugin)
        mgr = PluginManager(loader=loader)
        ok = mgr.load_plugin("com.test.working")
        assert ok is True
        assert mgr.is_loaded("com.test.working")
        assert mgr.count() == 1

    def test_load_plugin_emits_signal(self, qapp: object) -> None:
        from PySide6.QtTest import QSignalSpy

        plugin = _WorkingPlugin()
        loader = _make_loader_with(plugin)
        mgr = PluginManager(loader=loader)
        spy = QSignalSpy(mgr.plugin_loaded)
        mgr.load_plugin("com.test.working")
        assert len(spy) == 1
        assert spy[0][0] == "com.test.working"

    def test_load_plugin_returns_false_on_load_error(self, qapp: object) -> None:
        loader = _make_loader_with(None)
        mgr = PluginManager(loader=loader)
        ok = mgr.load_plugin("nonexistent.module")
        assert ok is False
        assert mgr.count() == 0

    def test_load_plugin_emits_error_signal_on_failure(self, qapp: object) -> None:
        from PySide6.QtTest import QSignalSpy

        loader = _make_loader_with(None)
        mgr = PluginManager(loader=loader)
        spy = QSignalSpy(mgr.plugin_error)
        mgr.load_plugin("bad.module")
        assert len(spy) == 1

    def test_load_plugin_fails_when_activation_returns_false(self, qapp: object) -> None:
        plugin = _FailPlugin()
        loader = _make_loader_with(plugin)
        mgr = PluginManager(loader=loader)
        ok = mgr.load_plugin("com.test.fail")
        assert ok is False
        assert not mgr.is_loaded("com.test.fail")

    def test_load_same_plugin_twice_is_no_op(self, qapp: object) -> None:
        plugin = _WorkingPlugin()
        loader = _make_loader_with(plugin)
        loader.load.return_value = plugin  # same object each time
        mgr = PluginManager(loader=loader)
        mgr.load_plugin("com.test.working")
        mgr.load_plugin("com.test.working")  # second call — skipped
        assert mgr.count() == 1


# ---------------------------------------------------------------------------
# enable / disable
# ---------------------------------------------------------------------------


class TestPluginManagerEnableDisable:
    def test_disable_plugin(self, qapp: object) -> None:
        plugin = _WorkingPlugin()
        loader = _make_loader_with(plugin)
        mgr = PluginManager(loader=loader)
        mgr.load_plugin("com.test.working")
        ok = mgr.disable_plugin("com.test.working")
        assert ok is True
        assert not plugin.is_active

    def test_enable_plugin_after_disable(self, qapp: object) -> None:
        plugin = _WorkingPlugin()
        loader = _make_loader_with(plugin)
        mgr = PluginManager(loader=loader)
        mgr.load_plugin("com.test.working")
        mgr.disable_plugin("com.test.working")
        ok = mgr.enable_plugin("com.test.working")
        assert ok is True
        assert plugin.is_active

    def test_enable_already_active_is_true(self, qapp: object) -> None:
        plugin = _WorkingPlugin()
        loader = _make_loader_with(plugin)
        mgr = PluginManager(loader=loader)
        mgr.load_plugin("com.test.working")
        assert mgr.enable_plugin("com.test.working") is True

    def test_enable_unknown_returns_false(self, qapp: object) -> None:
        mgr = PluginManager()
        assert mgr.enable_plugin("does.not.exist") is False

    def test_disable_unknown_returns_false(self, qapp: object) -> None:
        mgr = PluginManager()
        assert mgr.disable_plugin("does.not.exist") is False


# ---------------------------------------------------------------------------
# unload / unload_all
# ---------------------------------------------------------------------------


class TestPluginManagerUnload:
    def test_unload_plugin(self, qapp: object) -> None:
        plugin = _WorkingPlugin()
        loader = _make_loader_with(plugin)
        mgr = PluginManager(loader=loader)
        mgr.load_plugin("com.test.working")
        ok = mgr.unload_plugin("com.test.working")
        assert ok is True
        assert not mgr.is_loaded("com.test.working")

    def test_unload_emits_signal(self, qapp: object) -> None:
        from PySide6.QtTest import QSignalSpy

        plugin = _WorkingPlugin()
        loader = _make_loader_with(plugin)
        mgr = PluginManager(loader=loader)
        mgr.load_plugin("com.test.working")
        spy = QSignalSpy(mgr.plugin_unloaded)
        mgr.unload_plugin("com.test.working")
        assert len(spy) == 1
        assert spy[0][0] == "com.test.working"

    def test_unload_unknown_returns_false(self, qapp: object) -> None:
        mgr = PluginManager()
        assert mgr.unload_plugin("ghost.id") is False

    def test_unload_all_clears_registry(self, qapp: object) -> None:
        plugin = _WorkingPlugin()
        loader = _make_loader_with(plugin)
        mgr = PluginManager(loader=loader)
        mgr.load_plugin("com.test.working")
        mgr.unload_all()
        assert mgr.count() == 0


# ---------------------------------------------------------------------------
# load_all
# ---------------------------------------------------------------------------


class TestPluginManagerLoadAll:
    def test_load_all_with_manifests(self, qapp: object) -> None:
        manifest = PluginManifest(
            plugin_id="com.test.all",
            name="All Plugin",
            version="1.0.0",
            entry="com.test.all",
        )
        plugin = _WorkingPlugin()

        loader = MagicMock(spec=PluginLoader)
        loader.discover.return_value = [manifest]
        loader.load.return_value = plugin

        mgr = PluginManager(loader=loader)
        loaded = mgr.load_all()
        assert "com.test.working" in loaded

    def test_load_all_empty(self, qapp: object) -> None:
        loader = _make_loader_with(manifest_list=[])
        mgr = PluginManager(loader=loader)
        loaded = mgr.load_all()
        assert loaded == []

    def test_load_all_skips_failed(self, qapp: object) -> None:
        manifest = PluginManifest(
            plugin_id="com.test.broken",
            name="Broken",
            version="1.0.0",
            entry="broken.module",
        )
        loader = MagicMock(spec=PluginLoader)
        loader.discover.return_value = [manifest]
        loader.load.side_effect = PluginLoadError("module not found")

        mgr = PluginManager(loader=loader)
        loaded = mgr.load_all()
        assert loaded == []
        assert mgr.count() == 0
