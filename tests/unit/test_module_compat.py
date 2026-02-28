"""Unit tests for ModuleCompat — Magisk module compatibility matrix."""

from __future__ import annotations

from pathlib import Path

import pytest

from cyberflash.core.module_compat import CompatResult, ModuleCompat, ModuleManifest


_BASIC_PROP = """\
id=mymodule
name=My Test Module
version=v1.0
versionCode=100
author=test
description=A test module
minMagisk=24000
minApi=28
maxApi=999
"""


class TestParseManifest:
    def test_parse_basic_fields(self) -> None:
        manifest = ModuleCompat.parse_manifest(_BASIC_PROP)
        assert manifest is not None
        assert manifest.id == "mymodule"
        assert manifest.name == "My Test Module"
        assert manifest.version == "v1.0"
        assert manifest.version_code == 100
        assert manifest.author == "test"
        assert manifest.min_magisk == 24000
        assert manifest.min_api == 28
        assert manifest.max_api == 999

    def test_parse_empty_returns_manifest_with_defaults(self) -> None:
        manifest = ModuleCompat.parse_manifest("")
        assert manifest is not None
        assert manifest.id == "unknown"
        assert manifest.min_api == 0
        assert manifest.max_api == 999

    def test_parse_comments_ignored(self) -> None:
        text = "# this is a comment\nid=foo\nname=Foo Module\n"
        manifest = ModuleCompat.parse_manifest(text)
        assert manifest is not None
        assert manifest.id == "foo"

    def test_parse_supported_archs(self) -> None:
        text = _BASIC_PROP + "supportedArchs=arm64-v8a,armeabi-v7a\n"
        manifest = ModuleCompat.parse_manifest(text)
        assert manifest is not None
        assert "arm64-v8a" in manifest.support_archs
        assert "armeabi-v7a" in manifest.support_archs

    def test_parse_manifest_path(self, tmp_path: Path) -> None:
        prop_file = tmp_path / "module.prop"
        prop_file.write_text(_BASIC_PROP)
        manifest = ModuleCompat.parse_manifest_path(prop_file)
        assert manifest is not None
        assert manifest.id == "mymodule"

    def test_parse_manifest_path_missing_file(self, tmp_path: Path) -> None:
        result = ModuleCompat.parse_manifest_path(tmp_path / "nope.prop")
        assert result is None


class TestCheckCompatibility:
    def _manifest(self, **kwargs) -> ModuleManifest:
        defaults = dict(
            id="test", name="Test", version="v1", version_code=1,
            author="x", description="y", min_magisk=0, min_api=0,
            max_api=999, support_archs=[],
        )
        defaults.update(kwargs)
        return ModuleManifest(**defaults)

    def test_compatible_device_passes(self) -> None:
        m = self._manifest(min_api=28)
        result = ModuleCompat.check(m, device_api=34, device_arch="arm64-v8a")
        assert result.compatible is True
        assert result.blockers == []

    def test_api_too_low_blocked(self) -> None:
        m = self._manifest(min_api=30)
        result = ModuleCompat.check(m, device_api=28, device_arch="arm64-v8a")
        assert result.compatible is False
        assert any("API" in b for b in result.blockers)

    def test_api_too_high_blocked(self) -> None:
        m = self._manifest(max_api=32)
        result = ModuleCompat.check(m, device_api=34, device_arch="arm64-v8a")
        assert result.compatible is False

    def test_unsupported_arch_blocked(self) -> None:
        m = self._manifest(support_archs=["arm64-v8a"])
        result = ModuleCompat.check(m, device_api=34, device_arch="x86_64")
        assert result.compatible is False
        assert any("arch" in b.lower() for b in result.blockers)

    def test_supported_arch_passes(self) -> None:
        m = self._manifest(support_archs=["arm64-v8a", "x86_64"])
        result = ModuleCompat.check(m, device_api=34, device_arch="x86_64")
        assert result.compatible is True

    def test_magisk_version_too_old_blocked(self) -> None:
        m = self._manifest(min_magisk=26000)
        result = ModuleCompat.check(m, device_api=34, device_arch="arm64-v8a",
                                    magisk_version_code=24000)
        assert result.compatible is False

    def test_magisk_version_sufficient_passes(self) -> None:
        m = self._manifest(min_magisk=24000)
        result = ModuleCompat.check(m, device_api=34, device_arch="arm64-v8a",
                                    magisk_version_code=26200)
        assert result.compatible is True

    def test_api_below_global_floor_blocked(self) -> None:
        m = self._manifest()
        result = ModuleCompat.check(m, device_api=21, device_arch="arm64-v8a")
        assert result.compatible is False

    def test_log_cb_called(self) -> None:
        m = self._manifest()
        logs: list[str] = []
        ModuleCompat.check(m, device_api=34, device_arch="arm64-v8a", log_cb=logs.append)
        assert len(logs) > 0

    def test_result_module_id(self) -> None:
        m = self._manifest(id="mymod")
        result = ModuleCompat.check(m, device_api=34, device_arch="arm64-v8a")
        assert result.module_id == "mymod"


class TestCheckDirectory:
    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        results = ModuleCompat.check_directory(tmp_path, device_api=34, device_arch="arm64-v8a")
        assert results == []

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        results = ModuleCompat.check_directory(
            tmp_path / "nonexistent", device_api=34, device_arch="arm64-v8a"
        )
        assert results == []

    def test_scans_module_props(self, tmp_path: Path) -> None:
        mod_dir = tmp_path / "module1"
        mod_dir.mkdir()
        (mod_dir / "module.prop").write_text("id=mod1\nname=Mod1\nversion=v1\nversionCode=1\n")
        results = ModuleCompat.check_directory(tmp_path, device_api=34, device_arch="arm64-v8a")
        assert len(results) == 1
        assert results[0].module_id == "mod1"
