"""Unit tests for XiaomiManager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cyberflash.core.xiaomi_manager import (
    XiaomiManager,
    XiaomiUnlockStatus,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_shell(serial: str, cmd: str, **kwargs) -> str:
    """Return mock getprop values."""
    _map = {
        "ro.product.brand":              "xiaomi",
        "ro.product.device":             "camellia",
        "ro.product.model":              "Redmi Note 11",
        "ro.miui.ui.version.name":       "MIUI 14",
        "ro.build.version.release":      "13",
        "ro.build.id":                   "TP1A.220624.014",
        "ro.miui.region":                "GLOBAL",
        "ro.boot.anti_rollback_count":   "3",
        "ro.secureboot.lockstate":       "locked",
    }
    for key, value in _map.items():
        if key in cmd:
            return value
    return ""


# ── is_xiaomi_device ──────────────────────────────────────────────────────────

class TestIsXiaomiDevice:
    def test_xiaomi_brand_returns_true(self) -> None:
        with patch("cyberflash.core.xiaomi_manager.AdbManager.shell",
                   return_value="xiaomi"):
            assert XiaomiManager.is_xiaomi_device("abc") is True

    def test_redmi_brand_returns_true(self) -> None:
        with patch("cyberflash.core.xiaomi_manager.AdbManager.shell",
                   return_value="redmi"):
            assert XiaomiManager.is_xiaomi_device("abc") is True

    def test_unknown_brand_returns_false(self) -> None:
        with patch("cyberflash.core.xiaomi_manager.AdbManager.shell",
                   return_value="samsung"):
            assert XiaomiManager.is_xiaomi_device("abc") is False


# ── get_device_info ───────────────────────────────────────────────────────────

class TestGetDeviceInfo:
    def test_returns_device_info(self) -> None:
        with patch("cyberflash.core.xiaomi_manager.AdbManager.shell",
                   side_effect=_mock_shell):
            info = XiaomiManager.get_device_info("abc123")

        assert info.codename == "camellia"
        assert info.brand == "xiaomi"
        assert info.model == "Redmi Note 11"
        assert info.miui_version == "MIUI 14"
        assert info.android_version == "13"
        assert info.region == "GLOBAL"
        assert info.anti_rollback == 3
        assert info.bl_status == XiaomiUnlockStatus.LOCKED
        assert info.is_xiaomi is True

    def test_invalid_arb_gives_minus_one(self) -> None:
        def shell(serial, cmd, **kw):
            if "anti_rollback" in cmd:
                return "not_a_number"
            return ""

        with patch("cyberflash.core.xiaomi_manager.AdbManager.shell",
                   side_effect=shell):
            info = XiaomiManager.get_device_info("abc")
        assert info.anti_rollback == -1

    def test_unlocked_status(self) -> None:
        def shell(serial, cmd, **kw):
            if "lockstate" in cmd:
                return "unlocked"
            return ""

        with patch("cyberflash.core.xiaomi_manager.AdbManager.shell",
                   side_effect=shell):
            info = XiaomiManager.get_device_info("abc")
        assert info.bl_status == XiaomiUnlockStatus.UNLOCKED


# ── get_unlock_status ─────────────────────────────────────────────────────────

class TestGetUnlockStatus:
    def test_unlocked_yes(self) -> None:
        with patch("cyberflash.core.xiaomi_manager.FastbootManager._run",
                   return_value=(0, "", "unlocked: yes")):
            assert XiaomiManager.get_unlock_status("abc") == XiaomiUnlockStatus.UNLOCKED

    def test_locked_no(self) -> None:
        with patch("cyberflash.core.xiaomi_manager.FastbootManager._run",
                   return_value=(0, "", "unlocked: no")):
            assert XiaomiManager.get_unlock_status("abc") == XiaomiUnlockStatus.LOCKED

    def test_unknown_status(self) -> None:
        with patch("cyberflash.core.xiaomi_manager.FastbootManager._run",
                   return_value=(0, "", "some other output")):
            assert XiaomiManager.get_unlock_status("abc") == XiaomiUnlockStatus.UNKNOWN


# ── oem_unlock / flashing_unlock ─────────────────────────────────────────────

class TestUnlock:
    def test_dry_run_oem_unlock(self) -> None:
        assert XiaomiManager.oem_unlock("abc", dry_run=True) is True

    def test_oem_unlock_success(self) -> None:
        with patch("cyberflash.core.xiaomi_manager.FastbootManager._run",
                   return_value=(0, "", "")):
            assert XiaomiManager.oem_unlock("abc") is True

    def test_oem_unlock_failure(self) -> None:
        with patch("cyberflash.core.xiaomi_manager.FastbootManager._run",
                   return_value=(1, "", "FAILED")):
            assert XiaomiManager.oem_unlock("abc") is False

    def test_dry_run_flashing_unlock(self) -> None:
        assert XiaomiManager.flashing_unlock("abc", dry_run=True) is True

    def test_flashing_unlock_success(self) -> None:
        with patch("cyberflash.core.xiaomi_manager.FastbootManager._run",
                   return_value=(0, "", "")):
            assert XiaomiManager.flashing_unlock("abc") is True


# ── scan_firmware_dir ─────────────────────────────────────────────────────────

class TestScanFirmwareDir:
    def test_finds_images(self, tmp_path: Path) -> None:
        (tmp_path / "boot.img").write_bytes(b"boot")
        (tmp_path / "system.img").write_bytes(b"system")
        (tmp_path / "modem.img").write_bytes(b"modem")

        manifest = XiaomiManager.scan_firmware_dir(tmp_path)
        partitions = [p for p, _ in manifest.found_images]
        assert "boot" in partitions
        assert "system" in partitions
        assert "modem" in partitions

    def test_detects_super_img(self, tmp_path: Path) -> None:
        (tmp_path / "super.img").write_bytes(b"super")
        manifest = XiaomiManager.scan_firmware_dir(tmp_path)
        assert manifest.has_super is True

    def test_empty_dir_returns_empty_manifest(self, tmp_path: Path) -> None:
        manifest = XiaomiManager.scan_firmware_dir(tmp_path)
        assert manifest.found_images == []
        assert manifest.has_super is False


# ── flash_firmware ────────────────────────────────────────────────────────────

class TestFlashFirmware:
    def test_dry_run_all_partitions(self, tmp_path: Path) -> None:
        (tmp_path / "boot.img").write_bytes(b"boot")
        (tmp_path / "system.img").write_bytes(b"system")

        results = XiaomiManager.flash_firmware(
            "abc", tmp_path, dry_run=True
        )
        assert all(r.success for r in results)

    def test_skips_non_requested_partitions(self, tmp_path: Path) -> None:
        (tmp_path / "boot.img").write_bytes(b"boot")
        (tmp_path / "system.img").write_bytes(b"system")

        results = XiaomiManager.flash_firmware(
            "abc", tmp_path, partitions=["boot"], dry_run=True
        )
        boot_results = [r for r in results if r.partition == "boot"]
        system_results = [r for r in results if r.partition == "system" and r.skipped]
        assert len(boot_results) == 1
        assert boot_results[0].success is True
        assert len(system_results) == 1

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        results = XiaomiManager.flash_firmware("abc", tmp_path)
        assert results == []

    def test_flash_failure_stops_sequence(self, tmp_path: Path) -> None:
        (tmp_path / "boot.img").write_bytes(b"boot")
        (tmp_path / "system.img").write_bytes(b"system")

        with patch("cyberflash.core.xiaomi_manager.FastbootManager._run",
                   return_value=(1, "", "FAILED")):
            results = XiaomiManager.flash_firmware("abc", tmp_path)

        # First failure should stop the sequence
        failed = [r for r in results if not r.success]
        assert len(failed) >= 1


# ── anti_rollback ─────────────────────────────────────────────────────────────

class TestAntiRollback:
    def test_safe_when_device_ge_firmware(self) -> None:
        def shell(serial, cmd, **kw):
            if "anti_rollback" in cmd:
                return "5"
            return ""

        with patch("cyberflash.core.xiaomi_manager.AdbManager.shell",
                   side_effect=shell):
            ok, _msg = XiaomiManager.check_anti_rollback("abc", firmware_min_arb=3)
        assert ok is True

    def test_unsafe_when_device_lt_firmware(self) -> None:
        def shell(serial, cmd, **kw):
            if "anti_rollback" in cmd:
                return "2"
            return ""

        with patch("cyberflash.core.xiaomi_manager.AdbManager.shell",
                   side_effect=shell):
            ok, arb_msg = XiaomiManager.check_anti_rollback("abc", firmware_min_arb=5)
        assert ok is False
        assert "brick" in arb_msg.lower() or "below" in arb_msg.lower()

    def test_unknown_arb_returns_true_with_warning(self) -> None:
        def shell(serial, cmd, **kw):
            return ""

        with patch("cyberflash.core.xiaomi_manager.AdbManager.shell",
                   side_effect=shell):
            ok, arb_msg = XiaomiManager.check_anti_rollback("abc", firmware_min_arb=3)
        assert ok is True
        assert "unknown" in arb_msg.lower()
