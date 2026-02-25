"""Unit tests for MotorolaManager."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from unittest.mock import patch

from cyberflash.core.motorola_manager import (
    MotorolaManager,
    MotorolaUnlockStatus,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_firmware_zip(tmp_path: Path, images: list[str]) -> Path:
    """Create a Motorola-style firmware zip with .img files."""
    zip_path = tmp_path / "firmware.zip"
    with zipfile.ZipFile(str(zip_path), "w") as zf:
        for img in images:
            zf.writestr(img, f"fake {img}")
    return zip_path


def _build_firmware_dir(tmp_path: Path, images: list[str]) -> Path:
    """Create a flat firmware directory with .img files."""
    for img in images:
        (tmp_path / img).write_bytes(f"fake {img}".encode())
    return tmp_path


def _build_flashfile_xml(steps: list[tuple[str, str]]) -> str:
    """Build a minimal flashfile.xml with given (partition, filename) steps."""
    root = ET.Element("steps")
    for partition, filename in steps:
        step = ET.SubElement(root, "step")
        step.set("operation", "flash")
        step.set("partition", partition)
        step.set("filename", filename)
    return ET.tostring(root, encoding="unicode")


# ── model_name ────────────────────────────────────────────────────────────────

class TestModelName:
    def test_known_codename(self) -> None:
        assert MotorolaManager.model_name("berlin") == "Motorola Edge 30 Pro"

    def test_unknown_returns_codename(self) -> None:
        assert MotorolaManager.model_name("unknown_moto") == "unknown_moto"


# ── get_device_info ───────────────────────────────────────────────────────────

class TestGetDeviceInfo:
    def _mock_shell(self, serial: str, cmd: str, **kw) -> str:
        props = {
            "ro.product.device":              "berlin",
            "ro.product.model":               "Motorola Edge 30 Pro",
            "ro.product.name":                "XT2201-1",
            "ro.build.version.release":       "12",
            "ro.build.id":                    "S3SPS32.20-42-10",
            "ro.build.version.security_patch": "2022-09-01",
            "sys.oem_unlock_allowed":         "1",
            "ro.carrier":                     "retail",
            "ro.secureboot.lockstate":        "unlocked",
        }
        for key, value in props.items():
            if key in cmd:
                return value
        return ""

    def test_returns_device_info(self) -> None:
        with patch("cyberflash.core.motorola_manager.AdbManager.shell",
                   side_effect=self._mock_shell):
            info = MotorolaManager.get_device_info("abc123")

        assert info.codename == "berlin"
        assert info.model == "Motorola Edge 30 Pro"
        assert info.android_version == "12"
        assert info.bl_status == MotorolaUnlockStatus.UNLOCKED
        assert info.oem_unlock_allowed is True
        assert info.carrier_locked is False

    def test_carrier_locked_device(self) -> None:
        def shell(serial, cmd, **kw):
            if "ro.carrier" in cmd:
                return "att"
            return ""

        with patch("cyberflash.core.motorola_manager.AdbManager.shell",
                   side_effect=shell):
            info = MotorolaManager.get_device_info("abc")
        assert info.carrier_locked is True

    def test_locked_bootloader(self) -> None:
        def shell(serial, cmd, **kw):
            if "lockstate" in cmd:
                return "locked"
            return ""

        with patch("cyberflash.core.motorola_manager.AdbManager.shell",
                   side_effect=shell):
            info = MotorolaManager.get_device_info("abc")
        assert info.bl_status == MotorolaUnlockStatus.LOCKED


# ── get_unlock_status ─────────────────────────────────────────────────────────

class TestGetUnlockStatus:
    def test_unlocked(self) -> None:
        with patch("cyberflash.core.motorola_manager.FastbootManager._run",
                   return_value=(0, "", "unlocked: yes")):
            assert MotorolaManager.get_unlock_status("abc") == MotorolaUnlockStatus.UNLOCKED

    def test_locked(self) -> None:
        with patch("cyberflash.core.motorola_manager.FastbootManager._run",
                   return_value=(0, "", "unlocked: no")):
            assert MotorolaManager.get_unlock_status("abc") == MotorolaUnlockStatus.LOCKED

    def test_unknown(self) -> None:
        with patch("cyberflash.core.motorola_manager.FastbootManager._run",
                   return_value=(0, "", "some output")):
            assert MotorolaManager.get_unlock_status("abc") == MotorolaUnlockStatus.UNKNOWN


# ── get_unlock_code ───────────────────────────────────────────────────────────

class TestGetUnlockCode:
    def test_parses_bootloader_lines(self) -> None:
        output = (
            "(bootloader) AABB\n"
            "(bootloader) CCDD\n"
            "(bootloader) EEFF\n"
            "OKAY [  0.125s]\n"
        )
        with patch("cyberflash.core.motorola_manager.FastbootManager._run",
                   return_value=(0, output, "")):
            code = MotorolaManager.get_unlock_code("abc")
        assert "AABB" in code
        assert "CCDD" in code

    def test_returns_empty_on_no_output(self) -> None:
        with patch("cyberflash.core.motorola_manager.FastbootManager._run",
                   return_value=(0, "", "")):
            code = MotorolaManager.get_unlock_code("abc")
        assert code == ""


# ── inspect_firmware / scan_dir ───────────────────────────────────────────────

class TestInspectFirmware:
    def test_scans_flat_dir(self, tmp_path: Path) -> None:
        _build_firmware_dir(tmp_path, ["boot.img", "recovery.img", "modem.img"])
        manifest = MotorolaManager.inspect_firmware(tmp_path)
        assert manifest is not None
        partitions = [p for p, _ in manifest.found_images]
        assert "boot" in partitions
        assert "recovery" in partitions
        assert "modem" in partitions

    def test_detects_super(self, tmp_path: Path) -> None:
        _build_firmware_dir(tmp_path, ["super.img"])
        manifest = MotorolaManager.inspect_firmware(tmp_path)
        assert manifest is not None
        assert manifest.has_super is True

    def test_zip_extraction(self, tmp_path: Path) -> None:
        zip_path = _build_firmware_zip(tmp_path, ["boot.img", "system.img"])
        manifest = MotorolaManager.inspect_firmware(zip_path)
        assert manifest is not None
        partitions = [p for p, _ in manifest.found_images]
        assert "boot" in partitions

    def test_missing_returns_none(self, tmp_path: Path) -> None:
        result = MotorolaManager.inspect_firmware(tmp_path / "missing.zip")
        assert result is None

    def test_detects_flashfile_xml(self, tmp_path: Path) -> None:
        (tmp_path / "flashfile.xml").write_text("<steps/>")
        (tmp_path / "boot.img").write_bytes(b"data")
        manifest = MotorolaManager.inspect_firmware(tmp_path)
        assert manifest is not None
        assert manifest.has_flashfile is True


# ── flash_firmware ────────────────────────────────────────────────────────────

class TestFlashFirmware:
    def test_dry_run_all_pass(self, tmp_path: Path) -> None:
        _build_firmware_dir(tmp_path, ["boot.img", "recovery.img"])
        results = MotorolaManager.flash_firmware("abc", tmp_path, dry_run=True)
        assert all(r.success for r in results)

    def test_skips_non_requested_partitions(self, tmp_path: Path) -> None:
        _build_firmware_dir(tmp_path, ["boot.img", "recovery.img"])
        results = MotorolaManager.flash_firmware(
            "abc", tmp_path, partitions=["boot"], dry_run=True
        )
        boot_results = [r for r in results if r.partition == "boot" and not r.skipped]
        assert len(boot_results) == 1
        skipped = [r for r in results if r.skipped]
        assert any(r.partition == "recovery" for r in skipped)

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        results = MotorolaManager.flash_firmware("abc", tmp_path)
        assert results == []


# ── rescue_flash ──────────────────────────────────────────────────────────────

class TestRescueFlash:
    def test_parses_flashfile_xml(self, tmp_path: Path) -> None:
        xml_content = _build_flashfile_xml([
            ("boot", "boot.img"),
            ("recovery", "recovery.img"),
        ])
        (tmp_path / "flashfile.xml").write_text(xml_content)
        (tmp_path / "boot.img").write_bytes(b"boot data")
        (tmp_path / "recovery.img").write_bytes(b"recovery data")

        results = MotorolaManager.rescue_flash("abc", tmp_path, dry_run=True)
        partitions = [r.partition for r in results]
        assert "boot" in partitions
        assert "recovery" in partitions
        assert all(r.success for r in results)

    def test_missing_image_in_flashfile(self, tmp_path: Path) -> None:
        xml_content = _build_flashfile_xml([("boot", "boot.img")])
        (tmp_path / "flashfile.xml").write_text(xml_content)
        # Don't create boot.img

        results = MotorolaManager.rescue_flash("abc", tmp_path)
        assert len(results) == 1
        assert results[0].success is False

    def test_no_flashfile_falls_back_to_dir_scan(self, tmp_path: Path) -> None:
        (tmp_path / "boot.img").write_bytes(b"boot data")
        results = MotorolaManager.rescue_flash("abc", tmp_path, dry_run=True)
        # Should fall through to flash_firmware
        assert any(r.partition == "boot" for r in results)


# ── oem_unlock ────────────────────────────────────────────────────────────────

class TestOemUnlock:
    def test_dry_run_returns_true(self) -> None:
        assert MotorolaManager.oem_unlock("abc", dry_run=True) is True

    def test_success(self) -> None:
        with patch("cyberflash.core.motorola_manager.FastbootManager._run",
                   return_value=(0, "", "")):
            assert MotorolaManager.oem_unlock("abc") is True

    def test_failure(self) -> None:
        with patch("cyberflash.core.motorola_manager.FastbootManager._run",
                   return_value=(1, "", "FAILED")):
            assert MotorolaManager.oem_unlock("abc") is False
