"""Unit tests for GsiChecker — mocked ADB props."""

from __future__ import annotations

from unittest.mock import patch

from cyberflash.core.gsi_checker import GsiChecker, GsiCompatibility, GsiType


def _mock_props(treble: str, vndk: str, dynamic: str, abi: str, ab: str, codename: str = "guacamole"):
    """Build a mock for AdbManager.get_props_batch and get_prop."""
    props = {
        "ro.treble.enabled": treble,
        "ro.vndk.version": vndk,
        "ro.boot.dynamic_partitions": dynamic,
        "ro.product.cpu.abi": abi,
        "ro.build.ab_update": ab,
    }

    def _get_props_batch(serial, keys):  # noqa: ARG001
        return {k: props.get(k, "") for k in keys}

    return _get_props_batch, codename


class TestCheckDevice:
    def test_treble_enabled_arm64_ab(self) -> None:
        _get_batch, codename = _mock_props("true", "30", "true", "arm64-v8a", "true")
        with (
            patch("cyberflash.core.gsi_checker.AdbManager.get_props_batch", side_effect=_get_batch),
            patch("cyberflash.core.gsi_checker.AdbManager.get_prop", return_value=codename),
        ):
            compat = GsiChecker.check_device("ABC")
        assert compat.treble_enabled is True
        assert compat.recommended_gsi_type == GsiType.ARM64_AB

    def test_treble_disabled_generates_warning(self) -> None:
        _get_batch, codename = _mock_props("false", "30", "true", "arm64-v8a", "true")
        with (
            patch("cyberflash.core.gsi_checker.AdbManager.get_props_batch", side_effect=_get_batch),
            patch("cyberflash.core.gsi_checker.AdbManager.get_prop", return_value=codename),
        ):
            compat = GsiChecker.check_device("ABC")
        assert compat.treble_enabled is False
        assert len(compat.warnings) >= 1

    def test_arm64_a_only_when_no_ab(self) -> None:
        _get_batch, codename = _mock_props("true", "30", "true", "arm64-v8a", "false")
        with (
            patch("cyberflash.core.gsi_checker.AdbManager.get_props_batch", side_effect=_get_batch),
            patch("cyberflash.core.gsi_checker.AdbManager.get_prop", return_value=codename),
        ):
            compat = GsiChecker.check_device("ABC")
        assert compat.recommended_gsi_type == GsiType.ARM64_A_ONLY

    def test_x86_64_ab_detected(self) -> None:
        _get_batch, codename = _mock_props("true", "30", "true", "x86_64", "true")
        with (
            patch("cyberflash.core.gsi_checker.AdbManager.get_props_batch", side_effect=_get_batch),
            patch("cyberflash.core.gsi_checker.AdbManager.get_prop", return_value=codename),
        ):
            compat = GsiChecker.check_device("ABC")
        assert compat.recommended_gsi_type == GsiType.X86_64_AB

    def test_returns_gsi_compatibility(self) -> None:
        _get_batch, codename = _mock_props("true", "30", "true", "arm64-v8a", "true")
        with (
            patch("cyberflash.core.gsi_checker.AdbManager.get_props_batch", side_effect=_get_batch),
            patch("cyberflash.core.gsi_checker.AdbManager.get_prop", return_value=codename),
        ):
            compat = GsiChecker.check_device("ABC")
        assert isinstance(compat, GsiCompatibility)

    def test_missing_vndk_generates_warning(self) -> None:
        _get_batch, codename = _mock_props("true", "", "true", "arm64-v8a", "true")
        with (
            patch("cyberflash.core.gsi_checker.AdbManager.get_props_batch", side_effect=_get_batch),
            patch("cyberflash.core.gsi_checker.AdbManager.get_prop", return_value=codename),
        ):
            compat = GsiChecker.check_device("ABC")
        assert any("vndk" in w.lower() for w in compat.warnings)


class TestListCompatibleGsis:
    def test_treble_enabled_returns_projects(self) -> None:
        compat = GsiCompatibility(
            device_codename="guacamole",
            treble_enabled=True,
            vndk_version="30",
            dynamic_partitions=True,
            recommended_gsi_type=GsiType.ARM64_AB,
        )
        projects = GsiChecker.list_compatible_gsis(compat)
        assert len(projects) >= 1

    def test_treble_disabled_returns_empty(self) -> None:
        compat = GsiCompatibility(
            device_codename="guacamole",
            treble_enabled=False,
            vndk_version="",
            dynamic_partitions=False,
            recommended_gsi_type=GsiType.UNKNOWN,
        )
        projects = GsiChecker.list_compatible_gsis(compat)
        assert projects == []


class TestRecommendGsiType:
    def test_recommend_returns_stored_type(self) -> None:
        compat = GsiCompatibility(
            device_codename="guacamole",
            treble_enabled=True,
            vndk_version="30",
            dynamic_partitions=True,
            recommended_gsi_type=GsiType.ARM64_AB,
        )
        assert GsiChecker.recommend_gsi_type(compat) == GsiType.ARM64_AB
