"""Unit tests for RootManager and RootState.

All ADB/fastboot calls are mocked — no real device needed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cyberflash.core.root_manager import (
    _KERNELSU_PKG,
    _MAGISK_PKG,
    RootManager,
    RootState,
)

# ── RootState ─────────────────────────────────────────────────────────────────


class TestRootState:
    def test_labels_are_strings(self) -> None:
        for state in RootState:
            assert isinstance(state.label, str)
            assert len(state.label) > 0

    def test_rooted_states_have_success_badge(self) -> None:
        for state in (
            RootState.ROOTED_MAGISK,
            RootState.ROOTED_KERNELSU,
            RootState.ROOTED_APATCH,
            RootState.ROOTED_OTHER,
        ):
            assert state.badge_variant == "success"

    def test_unauthorized_is_warning(self) -> None:
        assert RootState.UNAUTHORIZED.badge_variant == "warning"

    def test_unknown_and_not_rooted_are_neutral(self) -> None:
        assert RootState.UNKNOWN.badge_variant == "neutral"
        assert RootState.NOT_ROOTED.badge_variant == "neutral"


# ── detect_root_state ─────────────────────────────────────────────────────────


class TestDetectRootState:
    def _mock_shell(self, side_effect):
        return patch("cyberflash.core.root_manager.AdbManager.shell", side_effect=side_effect)

    def test_magisk_rooted(self) -> None:
        def shell(serial, cmd, **kw):
            if "su -c id" in cmd:
                return "uid=0(root) gid=0(root)"
            if _MAGISK_PKG in cmd:
                return f"package:{_MAGISK_PKG}"
            return ""

        with self._mock_shell(shell):
            state = RootManager.detect_root_state("serial")
        assert state == RootState.ROOTED_MAGISK

    def test_kernelsu_rooted(self) -> None:
        def shell(serial, cmd, **kw):
            if "su -c id" in cmd:
                return "uid=0(root) gid=0(root)"
            if _KERNELSU_PKG in cmd:
                return f"package:{_KERNELSU_PKG}"
            return ""

        with self._mock_shell(shell):
            state = RootManager.detect_root_state("serial")
        assert state == RootState.ROOTED_KERNELSU

    def test_rooted_other_when_no_known_pkg(self) -> None:
        def shell(serial, cmd, **kw):
            if "su -c id" in cmd:
                return "uid=0(root)"
            return ""

        with self._mock_shell(shell):
            state = RootManager.detect_root_state("serial")
        assert state == RootState.ROOTED_OTHER

    def test_not_rooted_when_su_fails(self) -> None:
        with self._mock_shell(lambda *a, **kw: ""):
            state = RootManager.detect_root_state("serial")
        assert state == RootState.NOT_ROOTED


# ── get_magisk_version ────────────────────────────────────────────────────────


class TestGetMagiskVersion:
    def test_parses_version(self) -> None:
        output = "    versionName=26.4\n    versionCode=26400\n"
        with patch("cyberflash.core.root_manager.AdbManager.shell", return_value=output):
            ver = RootManager.get_magisk_version("serial")
        assert ver == "26.4"

    def test_returns_empty_when_not_installed(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell", return_value=""):
            ver = RootManager.get_magisk_version("serial")
        assert ver == ""


# ── push_boot_for_patching ────────────────────────────────────────────────────


class TestPushBootForPatching:
    def test_success(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_bytes(b"boot_data")
        with patch("cyberflash.core.root_manager.AdbManager.push", return_value=True) as mock_push:
            ok = RootManager.push_boot_for_patching("serial", img)
        assert ok is True
        mock_push.assert_called_once()

    def test_file_not_found(self, tmp_path: Path) -> None:
        ok = RootManager.push_boot_for_patching("serial", tmp_path / "missing.img")
        assert ok is False

    def test_push_failure(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_bytes(b"data")
        with patch("cyberflash.core.root_manager.AdbManager.push", return_value=False):
            ok = RootManager.push_boot_for_patching("serial", img)
        assert ok is False


# ── poll_for_patched_boot ─────────────────────────────────────────────────────


class TestPollForPatchedBoot:
    def test_finds_file(self) -> None:
        with patch(
            "cyberflash.core.root_manager.AdbManager.shell",
            return_value="/sdcard/Download/magisk_patched_abc123.img\n",
        ), patch("cyberflash.core.root_manager.time.sleep"):
            result = RootManager.poll_for_patched_boot("serial", poll_interval=0.01, timeout=5.0)
        assert result.endswith(".img")

    def test_timeout_returns_empty(self) -> None:
        with patch(
            "cyberflash.core.root_manager.AdbManager.shell",
            return_value="",
        ), patch("cyberflash.core.root_manager.time.sleep"):
            result = RootManager.poll_for_patched_boot("serial", poll_interval=0.01, timeout=0.05)
        assert result == ""


# ── pull_patched_boot ─────────────────────────────────────────────────────────


class TestPullPatchedBoot:
    def test_success(self, tmp_path: Path) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.pull", return_value=True):
            result = RootManager.pull_patched_boot(
                "serial",
                "/sdcard/Download/magisk_patched_abc.img",
                tmp_path,
            )
        assert result is not None
        assert result.name == "magisk_patched_abc.img"

    def test_failure(self, tmp_path: Path) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.pull", return_value=False):
            result = RootManager.pull_patched_boot("serial", "/sdcard/x.img", tmp_path)
        assert result is None


# ── flash_boot ────────────────────────────────────────────────────────────────


class TestFlashBoot:
    def test_dry_run_returns_true(self, tmp_path: Path) -> None:
        img = tmp_path / "patched_boot.img"
        img.write_bytes(b"data")
        result = RootManager.flash_boot("serial", img, dry_run=True)
        assert result is True

    def test_file_not_found(self, tmp_path: Path) -> None:
        result = RootManager.flash_boot("serial", tmp_path / "missing.img")
        assert result is False

    def test_fastboot_success(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_bytes(b"data")
        with patch(
            "cyberflash.core.root_manager.FastbootManager._run",
            return_value=(0, "", ""),
        ):
            result = RootManager.flash_boot("serial", img)
        assert result is True

    def test_fastboot_failure(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_bytes(b"data")
        with patch(
            "cyberflash.core.root_manager.FastbootManager._run",
            return_value=(1, "", "FAILED"),
        ):
            result = RootManager.flash_boot("serial", img)
        assert result is False


# ── Magisk module management ──────────────────────────────────────────────────


class TestMagiskModules:
    def test_get_modules_empty(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell", return_value=""):
            mods = RootManager.get_magisk_modules("serial")
        assert mods == []

    def test_get_modules_parses_props(self) -> None:
        def shell(serial, cmd, **kw):
            if "ls -1" in cmd:
                return "lsposed\n"
            return "id=lsposed\nname=LSPosed\nversion=1.9.2\nauthor=LSPosed\n"

        with patch("cyberflash.core.root_manager.AdbManager.shell", side_effect=shell):
            mods = RootManager.get_magisk_modules("serial")
        assert len(mods) == 1
        assert mods[0]["name"] == "LSPosed"

    def test_install_module_dry_run(self, tmp_path: Path) -> None:
        z = tmp_path / "module.zip"
        z.write_bytes(b"PK...")
        ok = RootManager.install_magisk_module("serial", z, dry_run=True)
        assert ok is True

    def test_uninstall_module_dry_run(self) -> None:
        ok = RootManager.uninstall_magisk_module("serial", "lsposed", dry_run=True)
        assert ok is True

    def test_toggle_module_dry_run(self) -> None:
        ok = RootManager.toggle_magisk_module("serial", "lsposed", enable=True, dry_run=True)
        assert ok is True
