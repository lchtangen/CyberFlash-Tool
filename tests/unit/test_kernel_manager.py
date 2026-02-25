"""Unit tests for KernelManager (AnyKernel3 flasher)."""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import patch

from cyberflash.core.kernel_manager import KernelManager

# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_ak3_zip(tmp_path: Path, props: dict[str, str] | None = None) -> Path:
    """Create a minimal AnyKernel3 ZIP in tmp_path."""
    zip_path = tmp_path / "kernel.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        # Required marker
        zf.writestr(
            "META-INF/com/google/android/update-binary",
            "#!/bin/bash\necho 'AnyKernel3'",
        )
        # anykernel.sh with properties
        if props is None:
            props = {
                "kernel.string": "CyberKernel",
                "version": "6.1.0-cyberflash",
                "author": "CyberDev",
                "device.name1": "guacamole",
                "do.devicecheck": "0",
            }
        prop_lines = "\n".join(f'{k}={v}' for k, v in props.items())
        zf.writestr("anykernel.sh", prop_lines)
    return zip_path


def _build_non_ak3_zip(tmp_path: Path) -> Path:
    """Create a ZIP that is NOT an AnyKernel3 package."""
    zip_path = tmp_path / "not_ak3.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("some_file.txt", "hello")
    return zip_path


# ── is_anykernel3_zip ─────────────────────────────────────────────────────────

class TestIsAnykernel3Zip:
    def test_valid_ak3_returns_true(self, tmp_path: Path) -> None:
        zip_path = _build_ak3_zip(tmp_path)
        assert KernelManager.is_anykernel3_zip(zip_path) is True

    def test_non_ak3_returns_false(self, tmp_path: Path) -> None:
        zip_path = _build_non_ak3_zip(tmp_path)
        assert KernelManager.is_anykernel3_zip(zip_path) is False

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        assert KernelManager.is_anykernel3_zip(tmp_path / "missing.zip") is False

    def test_corrupt_zip_returns_false(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"\x00\x01\x02\x03")
        assert KernelManager.is_anykernel3_zip(bad) is False


# ── inspect_zip ───────────────────────────────────────────────────────────────

class TestInspectZip:
    def test_reads_metadata(self, tmp_path: Path) -> None:
        zip_path = _build_ak3_zip(tmp_path)
        info = KernelManager.inspect_zip(zip_path)
        assert info.is_valid is True
        assert info.kernel_name == "CyberKernel"
        assert info.kernel_ver == "6.1.0-cyberflash"
        assert info.author == "CyberDev"
        assert info.device == "guacamole"
        assert info.do_devicecheck is False

    def test_invalid_zip_returns_is_valid_false(self, tmp_path: Path) -> None:
        zip_path = _build_non_ak3_zip(tmp_path)
        info = KernelManager.inspect_zip(zip_path)
        assert info.is_valid is False

    def test_missing_file_returns_invalid(self, tmp_path: Path) -> None:
        info = KernelManager.inspect_zip(tmp_path / "nope.zip")
        assert info.is_valid is False

    def test_custom_props(self, tmp_path: Path) -> None:
        zip_path = _build_ak3_zip(tmp_path, props={
            "kernel.string": "MyCoolKernel",
            "version": "5.15-lts",
            "author": "HackDev",
            "do.devicecheck": "1",
        })
        info = KernelManager.inspect_zip(zip_path)
        assert info.kernel_name == "MyCoolKernel"
        assert info.do_devicecheck is True


# ── get_kernel_version ────────────────────────────────────────────────────────

class TestGetKernelVersion:
    def test_returns_uname(self) -> None:
        with patch("cyberflash.core.kernel_manager.AdbManager.shell",
                   return_value="6.1.25-android13-8-g2d1a5e4a\n"):
            ver = KernelManager.get_kernel_version("abc")
        assert ver == "6.1.25-android13-8-g2d1a5e4a"

    def test_empty_on_no_device(self) -> None:
        with patch("cyberflash.core.kernel_manager.AdbManager.shell", return_value=""):
            assert KernelManager.get_kernel_version("abc") == ""


# ── backup_boot ───────────────────────────────────────────────────────────────

class TestBackupBoot:
    def test_dry_run_returns_path(self, tmp_path: Path) -> None:
        result = KernelManager.backup_boot("abc123", tmp_path, dry_run=True)
        assert result is not None
        assert "abc123" in result.name

    def test_real_backup_success(self, tmp_path: Path) -> None:
        def run_side(args):
            # Simulate successful fetch by writing a file
            for _i, arg in enumerate(args):
                if arg.startswith("/") and arg.endswith(".img"):
                    Path(arg).write_bytes(b"boot_image_data")
                    break
            return (0, "", "")

        with patch("cyberflash.core.kernel_manager.FastbootManager._run",
                   side_effect=run_side):
            result = KernelManager.backup_boot("abc", tmp_path)
        assert result is not None

    def test_failure_returns_none(self, tmp_path: Path) -> None:
        with patch("cyberflash.core.kernel_manager.FastbootManager._run",
                   return_value=(1, "", "FAILED")):
            result = KernelManager.backup_boot("abc", tmp_path)
        assert result is None


# ── flash_via_sideload ────────────────────────────────────────────────────────

class TestFlashViaSideload:
    def test_dry_run(self, tmp_path: Path) -> None:
        zip_path = _build_ak3_zip(tmp_path)
        result = KernelManager.flash_via_sideload("abc", zip_path, dry_run=True)
        assert result.success is True
        assert result.method == "dry_run"

    def test_missing_zip_fails(self, tmp_path: Path) -> None:
        result = KernelManager.flash_via_sideload("abc", tmp_path / "missing.zip")
        assert result.success is False

    def test_non_ak3_zip_fails(self, tmp_path: Path) -> None:
        zip_path = _build_non_ak3_zip(tmp_path)
        result = KernelManager.flash_via_sideload("abc", zip_path)
        assert result.success is False


# ── flash_via_adb_push ────────────────────────────────────────────────────────

class TestFlashViaAdbPush:
    def test_dry_run(self, tmp_path: Path) -> None:
        zip_path = _build_ak3_zip(tmp_path)
        result = KernelManager.flash_via_adb_push("abc", zip_path, dry_run=True)
        assert result.success is True
        assert result.method == "dry_run"

    def test_missing_zip_fails(self, tmp_path: Path) -> None:
        result = KernelManager.flash_via_adb_push("abc", tmp_path / "nope.zip")
        assert result.success is False

    def test_push_failure_fails(self, tmp_path: Path) -> None:
        zip_path = _build_ak3_zip(tmp_path)
        with patch("cyberflash.core.kernel_manager.AdbManager.push", return_value=False):
            result = KernelManager.flash_via_adb_push("abc", zip_path)
        assert result.success is False

    def test_success_path(self, tmp_path: Path) -> None:
        zip_path = _build_ak3_zip(tmp_path)
        with (patch("cyberflash.core.kernel_manager.AdbManager.push", return_value=True),
              patch("cyberflash.core.kernel_manager.AdbManager.shell", return_value="Starting")):
            result = KernelManager.flash_via_adb_push("abc", zip_path)
        assert result.method == "adb_push"


# ── verify_kernel_version ─────────────────────────────────────────────────────

class TestVerifyKernelVersion:
    def test_matching_version(self) -> None:
        with patch("cyberflash.core.kernel_manager.AdbManager.shell",
                   return_value="6.1.0-cyberflash"):
            matches, actual = KernelManager.verify_kernel_version("abc", "6.1.0-cyberflash")
        assert matches is True
        assert actual == "6.1.0-cyberflash"

    def test_mismatched_version(self) -> None:
        with patch("cyberflash.core.kernel_manager.AdbManager.shell",
                   return_value="5.15.0-stock"):
            matches, _actual = KernelManager.verify_kernel_version("abc", "6.1.0-cyberflash")
        assert matches is False


# ── restore_boot_backup ───────────────────────────────────────────────────────

class TestRestoreBootBackup:
    def test_dry_run(self, tmp_path: Path) -> None:
        backup = tmp_path / "boot.img"
        backup.write_bytes(b"boot")
        assert KernelManager.restore_boot_backup("abc", backup, dry_run=True) is True

    def test_missing_backup_fails(self, tmp_path: Path) -> None:
        assert KernelManager.restore_boot_backup("abc", tmp_path / "missing.img") is False

    def test_success(self, tmp_path: Path) -> None:
        backup = tmp_path / "boot.img"
        backup.write_bytes(b"boot")
        with patch("cyberflash.core.kernel_manager.FastbootManager._run",
                   return_value=(0, "", "")):
            assert KernelManager.restore_boot_backup("abc", backup) is True

    def test_failure(self, tmp_path: Path) -> None:
        backup = tmp_path / "boot.img"
        backup.write_bytes(b"boot")
        with patch("cyberflash.core.kernel_manager.FastbootManager._run",
                   return_value=(1, "", "FAILED")):
            assert KernelManager.restore_boot_backup("abc", backup) is False
