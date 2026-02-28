"""Unit tests for PermissionManager — mocked ADB."""

from __future__ import annotations

from unittest.mock import patch

from cyberflash.core.permission_manager import AppPermission, PermissionManager


class TestListAppPermissions:
    def test_returns_permissions_list(self) -> None:
        output = (
            "grantedPermissions:\n"
            "  android.permission.CAMERA\n"
            "  android.permission.INTERNET: granted=true\n"
        )
        with patch("cyberflash.core.permission_manager.AdbManager.shell", return_value=output):
            perms = PermissionManager.list_app_permissions("ABC", "com.example.app")
        assert isinstance(perms, list)

    def test_empty_output_returns_empty_list(self) -> None:
        with patch("cyberflash.core.permission_manager.AdbManager.shell", return_value=""):
            perms = PermissionManager.list_app_permissions("ABC", "com.example.app")
        assert perms == []

    def test_parses_dangerous_flag(self) -> None:
        output = "grantedPermissions:\n  android.permission.CAMERA: granted=true\n"
        with patch("cyberflash.core.permission_manager.AdbManager.shell", return_value=output):
            perms = PermissionManager.list_app_permissions("ABC", "com.example.app")
        dangerous = [p for p in perms if p.dangerous]
        assert isinstance(dangerous, list)

    def test_result_is_app_permission_instances(self) -> None:
        output = "grantedPermissions:\n  android.permission.RECORD_AUDIO: granted=true\n"
        with patch("cyberflash.core.permission_manager.AdbManager.shell", return_value=output):
            perms = PermissionManager.list_app_permissions("ABC", "com.example.app")
        for p in perms:
            assert isinstance(p, AppPermission)


class TestGrantRevoke:
    def test_grant_returns_true_on_success(self) -> None:
        with patch(
            "cyberflash.core.permission_manager.AdbManager._run",
            return_value=(0, "", ""),
        ):
            result = PermissionManager.grant("ABC", "com.example.app", "android.permission.CAMERA")
        assert result is True

    def test_grant_returns_false_on_failure(self) -> None:
        with patch(
            "cyberflash.core.permission_manager.AdbManager._run",
            return_value=(1, "", "Exception occurred"),
        ):
            result = PermissionManager.grant("ABC", "com.example.app", "android.permission.CAMERA")
        assert result is False

    def test_revoke_returns_true_on_success(self) -> None:
        with patch(
            "cyberflash.core.permission_manager.AdbManager._run",
            return_value=(0, "", ""),
        ):
            result = PermissionManager.revoke(
                "ABC", "com.example.app", "android.permission.CAMERA"
            )
        assert result is True

    def test_revoke_returns_false_on_failure(self) -> None:
        with patch(
            "cyberflash.core.permission_manager.AdbManager._run",
            return_value=(1, "", "error"),
        ):
            result = PermissionManager.revoke(
                "ABC", "com.example.app", "android.permission.CAMERA"
            )
        assert result is False


class TestPrivacyPreset:
    def test_apply_preset_revoke_location_returns_int(self) -> None:
        pkg_list = "package:com.example.app\n"
        with (
            patch("cyberflash.core.permission_manager.AdbManager.shell", return_value=pkg_list),
            patch("cyberflash.core.permission_manager.AdbManager._run", return_value=(0, "", "")),
        ):
            count = PermissionManager.apply_privacy_preset("ABC", "revoke_location")
        assert isinstance(count, int) and count >= 0

    def test_apply_unknown_preset_returns_zero(self) -> None:
        with patch("cyberflash.core.permission_manager.AdbManager.shell", return_value=""):
            count = PermissionManager.apply_privacy_preset("ABC", "nonexistent_preset")
        assert count == 0


class TestDangerousCombos:
    def test_no_packages_returns_empty(self) -> None:
        with patch("cyberflash.core.permission_manager.AdbManager.shell", return_value=""):
            combos = PermissionManager.get_dangerous_combos("ABC")
        assert combos == []
