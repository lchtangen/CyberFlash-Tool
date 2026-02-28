"""tests/unit/test_plugin_base.py — Unit tests for PluginManifest and PluginBase."""

from __future__ import annotations

from cyberflash.plugins.base import PluginBase, PluginManifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SimplePlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "com.example.simple"

    @property
    def name(self) -> str:
        return "Simple Plugin"


class _CustomPlugin(PluginBase):
    def __init__(self) -> None:
        super().__init__()
        self._activated_services: dict = {}
        self._deactivated = False

    @property
    def plugin_id(self) -> str:
        return "com.example.custom"

    @property
    def name(self) -> str:
        return "Custom Plugin"

    @property
    def version(self) -> str:
        return "2.5.0"

    @property
    def author(self) -> str:
        return "Bob"

    def activate(self, services: dict | None = None) -> bool:
        self._activated_services = services or {}
        return super().activate(services)

    def deactivate(self) -> None:
        self._deactivated = True
        super().deactivate()


# ---------------------------------------------------------------------------
# PluginManifest
# ---------------------------------------------------------------------------


class TestPluginManifest:
    def test_from_dict_valid(self) -> None:
        data = {
            "id": "com.example.test",
            "name": "Test Plugin",
            "version": "1.2.3",
            "author": "Alice",
            "entry": "test_plugin",
            "tags": ["rom", "dev"],
        }
        m = PluginManifest.from_dict(data)
        assert m.plugin_id == "com.example.test"
        assert m.version == "1.2.3"
        assert m.author == "Alice"
        assert "rom" in m.tags

    def test_from_dict_defaults(self) -> None:
        m = PluginManifest.from_dict({"id": "x", "name": "Y", "entry": "e"})
        assert m.version == "1.0.0"
        assert m.min_cyberflash == "1.0.0"
        assert m.tags == []

    def test_is_valid_with_all_required(self) -> None:
        m = PluginManifest.from_dict({"id": "a", "name": "B", "entry": "e"})
        assert m.is_valid() is True

    def test_is_valid_missing_id(self) -> None:
        m = PluginManifest.from_dict({"id": "", "name": "B", "entry": "e"})
        assert m.is_valid() is False

    def test_is_valid_missing_name(self) -> None:
        m = PluginManifest.from_dict({"id": "a", "name": "", "entry": "e"})
        assert m.is_valid() is False

    def test_is_valid_missing_entry(self) -> None:
        m = PluginManifest.from_dict({"id": "a", "name": "B", "entry": ""})
        assert m.is_valid() is False


# ---------------------------------------------------------------------------
# PluginBase lifecycle
# ---------------------------------------------------------------------------


class TestPluginBase:
    def test_not_active_by_default(self) -> None:
        plugin = _SimplePlugin()
        assert plugin.is_active is False

    def test_activate_sets_active(self) -> None:
        plugin = _SimplePlugin()
        result = plugin.activate({})
        assert result is True
        assert plugin.is_active is True

    def test_deactivate_clears_active(self) -> None:
        plugin = _SimplePlugin()
        plugin.activate({})
        plugin.deactivate()
        assert plugin.is_active is False

    def test_plugin_id_property(self) -> None:
        assert _SimplePlugin().plugin_id == "com.example.simple"

    def test_name_property(self) -> None:
        assert _SimplePlugin().name == "Simple Plugin"

    def test_version_default(self) -> None:
        assert _SimplePlugin().version == "1.0.0"

    def test_custom_version(self) -> None:
        assert _CustomPlugin().version == "2.5.0"

    def test_custom_author(self) -> None:
        assert _CustomPlugin().author == "Bob"

    def test_activate_receives_services(self) -> None:
        plugin = _CustomPlugin()
        services = {"event_bus": object()}
        plugin.activate(services)
        assert plugin._activated_services is services

    def test_deactivate_hook(self) -> None:
        plugin = _CustomPlugin()
        plugin.activate()
        plugin.deactivate()
        assert plugin._deactivated is True

    def test_pages_default_empty(self) -> None:
        assert _SimplePlugin().pages() == []

    def test_workers_default_empty(self) -> None:
        assert _SimplePlugin().workers() == {}

    def test_on_device_connected_no_crash(self) -> None:
        _SimplePlugin().on_device_connected("SER001")

    def test_on_device_disconnected_no_crash(self) -> None:
        _SimplePlugin().on_device_disconnected("SER001")

    def test_repr(self) -> None:
        plugin = _SimplePlugin()
        r = repr(plugin)
        assert "com.example.simple" in r
        assert "active=False" in r

    def test_repr_after_activate(self) -> None:
        plugin = _SimplePlugin()
        plugin.activate()
        assert "active=True" in repr(plugin)
