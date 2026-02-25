"""Unit tests for PixelManager."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

from cyberflash.core.pixel_manager import (
    PIXEL_CODENAMES,
    PixelManager,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_factory_zip(
    tmp_path: Path,
    codename: str = "cheetah",
    build_id: str = "TD1A.220804.031",
    *,
    inner_images: list[str] | None = None,
) -> Path:
    """Build a fake Pixel factory image ZIP for testing."""
    zip_path = tmp_path / f"{codename}-{build_id}.zip"
    inner_images = inner_images or ["boot.img", "system.img", "vendor.img"]

    # Build inner image zip
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as iz:
        for img_name in inner_images:
            iz.writestr(img_name, f"fake {img_name}")
    inner_buf.seek(0)

    with zipfile.ZipFile(str(zip_path), "w") as zf:
        zf.writestr(f"bootloader-{codename}-slider-1.0.img", "bootloader data")
        zf.writestr(f"radio-{codename}-g5300b-2.0.img", "radio data")
        zf.writestr(f"image-{codename}-{build_id}.zip", inner_buf.read())
        zf.writestr("flash-all.sh", "#!/bin/bash\nfastboot flash boot boot.img\n")
        zf.writestr("flash-all.bat", "fastboot flash boot boot.img\n")
    return zip_path


# ── model_name ────────────────────────────────────────────────────────────────

class TestModelName:
    def test_known_codename(self) -> None:
        assert PixelManager.model_name("cheetah") == "Pixel 7 Pro"

    def test_unknown_codename_returns_codename(self) -> None:
        assert PixelManager.model_name("unknown_device") == "unknown_device"

    def test_all_known_codenames_present(self) -> None:
        for codename in PIXEL_CODENAMES:
            assert PixelManager.model_name(codename) != ""


# ── get_device_info ───────────────────────────────────────────────────────────

class TestGetDeviceInfo:
    def _mock_shell(self, serial: str, cmd: str, **kw) -> str:
        props = {
            "ro.product.device":              "cheetah",
            "ro.product.model":               "Pixel 7 Pro",
            "ro.build.version.release":       "13",
            "ro.build.id":                    "TD1A.220804.031",
            "ro.build.version.security_patch": "2022-08-05",
            "ro.boot.flash.locked":           "0",
        }
        for key, value in props.items():
            if key in cmd:
                return value
        return ""

    def test_returns_populated_info(self) -> None:
        with patch("cyberflash.core.pixel_manager.AdbManager.shell",
                   side_effect=self._mock_shell):
            info = PixelManager.get_device_info("abc123")

        assert info.codename == "cheetah"
        assert info.model == "Pixel 7 Pro"
        assert info.android_version == "13"
        assert info.bl_unlocked is True

    def test_locked_device(self) -> None:
        def shell(serial, cmd, **kw):
            if "flash.locked" in cmd:
                return "1"
            return ""

        with patch("cyberflash.core.pixel_manager.AdbManager.shell",
                   side_effect=shell):
            info = PixelManager.get_device_info("abc")
        assert info.bl_unlocked is False

    def test_unknown_lock_state(self) -> None:
        with patch("cyberflash.core.pixel_manager.AdbManager.shell",
                   return_value=""):
            info = PixelManager.get_device_info("abc")
        assert info.bl_unlocked is None


# ── inspect_factory_image ─────────────────────────────────────────────────────

class TestInspectFactoryImage:
    def test_detects_bootloader_radio_image_zip(self, tmp_path: Path) -> None:
        zip_path = _build_factory_zip(tmp_path)
        manifest = PixelManager.inspect_factory_image(zip_path)
        assert manifest is not None
        assert manifest.bootloader_img is not None
        assert manifest.radio_img is not None
        assert manifest.image_zip is not None

    def test_extracts_codename_and_build(self, tmp_path: Path) -> None:
        zip_path = _build_factory_zip(tmp_path, codename="lynx", build_id="TQ3A.230605.011")
        manifest = PixelManager.inspect_factory_image(zip_path)
        assert manifest is not None
        assert manifest.codename == "lynx"
        assert manifest.build_id.lower() == "tq3a.230605.011"

    def test_reads_flash_sh(self, tmp_path: Path) -> None:
        zip_path = _build_factory_zip(tmp_path)
        manifest = PixelManager.inspect_factory_image(zip_path)
        assert manifest is not None
        assert "fastboot flash boot" in manifest.flash_sh

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        result = PixelManager.inspect_factory_image(tmp_path / "missing.zip")
        assert result is None

    def test_bad_zip_returns_none(self, tmp_path: Path) -> None:
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_bytes(b"NOT A ZIP FILE")
        result = PixelManager.inspect_factory_image(bad_zip)
        assert result is None


# ── flash_factory_image ───────────────────────────────────────────────────────

class TestFlashFactoryImage:
    def test_dry_run_all_pass(self, tmp_path: Path) -> None:
        zip_path = _build_factory_zip(tmp_path)
        results = PixelManager.flash_factory_image("abc", zip_path, dry_run=True)
        failed = [r for r in results if not r.success and not r.skipped]
        assert failed == []

    def test_wipe_false_skips_userdata(self, tmp_path: Path) -> None:
        zip_path = _build_factory_zip(tmp_path)
        results = PixelManager.flash_factory_image("abc", zip_path, wipe=False, dry_run=True)
        userdata = [r for r in results if r.partition == "userdata"]
        assert all(r.skipped for r in userdata) or all(r.success for r in userdata)

    def test_missing_zip_returns_empty(self, tmp_path: Path) -> None:
        results = PixelManager.flash_factory_image("abc", tmp_path / "missing.zip")
        assert results == []


# ── flash_bootloader ──────────────────────────────────────────────────────────

class TestFlashBootloader:
    def test_dry_run_returns_success(self, tmp_path: Path) -> None:
        img = tmp_path / "bootloader.img"
        img.write_bytes(b"data")
        result = PixelManager.flash_bootloader("abc", img, dry_run=True)
        assert result.success is True

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        result = PixelManager.flash_bootloader("abc", tmp_path / "missing.img")
        assert result.success is False

    def test_success(self, tmp_path: Path) -> None:
        img = tmp_path / "bootloader.img"
        img.write_bytes(b"data")
        with patch("cyberflash.core.pixel_manager.FastbootManager._run",
                   return_value=(0, "", "")):
            result = PixelManager.flash_bootloader("abc", img)
        assert result.success is True

    def test_failure(self, tmp_path: Path) -> None:
        img = tmp_path / "bootloader.img"
        img.write_bytes(b"data")
        with patch("cyberflash.core.pixel_manager.FastbootManager._run",
                   return_value=(1, "", "FAILED")):
            result = PixelManager.flash_bootloader("abc", img)
        assert result.success is False


# ── flashing_unlock / lock ────────────────────────────────────────────────────

class TestFlashingUnlock:
    def test_dry_run_unlock(self) -> None:
        assert PixelManager.flashing_unlock("abc", dry_run=True) is True

    def test_dry_run_lock(self) -> None:
        assert PixelManager.flashing_lock("abc", dry_run=True) is True

    def test_unlock_success(self) -> None:
        with patch("cyberflash.core.pixel_manager.FastbootManager._run",
                   return_value=(0, "", "")):
            assert PixelManager.flashing_unlock("abc") is True

    def test_unlock_failure(self) -> None:
        with patch("cyberflash.core.pixel_manager.FastbootManager._run",
                   return_value=(1, "", "FAILED")):
            assert PixelManager.flashing_unlock("abc") is False
