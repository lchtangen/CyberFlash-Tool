"""Unit tests for Phase 6 additions to RootManager.

Tests KernelSU support, dm-verity, root profile management,
superuser log, and DenyList manager.
"""

from __future__ import annotations

from unittest.mock import patch

from cyberflash.core.root_manager import RootManager

# ── KernelSU ─────────────────────────────────────────────────────────────────

class TestKernelSUVersion:
    def test_returns_version(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell",
                   return_value="  versionName=1.0.5"):
            assert RootManager.get_kernelsu_version("abc") == "1.0.5"

    def test_returns_empty_when_not_installed(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell", return_value=""):
            assert RootManager.get_kernelsu_version("abc") == ""


class TestKernelSUModules:
    def test_returns_modules_list(self) -> None:
        def shell(serial, cmd, **kw):
            if "ls -1" in cmd:
                return "module_a\nmodule_b"
            if "module.prop" in cmd:
                return "id=module_a\nname=Test Module\nversion=v1\nauthor=Dev"
            if ".disable" in cmd:
                return ""
            return ""

        with patch("cyberflash.core.root_manager.AdbManager.shell", side_effect=shell):
            modules = RootManager.get_kernelsu_modules("abc")

        assert len(modules) == 2
        assert modules[0]["id"] == "module_a"

    def test_empty_when_no_modules(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell", return_value=""):
            assert RootManager.get_kernelsu_modules("abc") == []

    def test_disabled_module_flagged(self) -> None:
        def shell(serial, cmd, **kw):
            if "ls -1" in cmd:
                return "mod_x"
            if "module.prop" in cmd:
                return "id=mod_x\nname=X"
            if ".disable" in cmd:
                return "disabled"
            return ""

        with patch("cyberflash.core.root_manager.AdbManager.shell", side_effect=shell):
            modules = RootManager.get_kernelsu_modules("abc")

        assert modules[0]["enabled"] == "false"


class TestKernelSUInstall:
    def test_dry_run_returns_true(self, tmp_path) -> None:
        zip_f = tmp_path / "module.zip"
        zip_f.write_bytes(b"data")
        assert RootManager.install_kernelsu_module("abc", zip_f, dry_run=True) is True

    def test_missing_zip_returns_false(self, tmp_path) -> None:
        assert RootManager.install_kernelsu_module("abc", tmp_path / "missing.zip") is False

    def test_success_output(self, tmp_path) -> None:
        zip_f = tmp_path / "module.zip"
        zip_f.write_bytes(b"data")

        def shell(serial, cmd, **kw):
            return "Success installed"

        with (patch("cyberflash.core.root_manager.AdbManager.shell", side_effect=shell),
              patch("cyberflash.core.root_manager.AdbManager.push", return_value=True)):
            ok = RootManager.install_kernelsu_module("abc", zip_f)
        assert ok is True


# ── Root Profiles ─────────────────────────────────────────────────────────────

class TestRootProfiles:
    def test_returns_profiles(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell",
                   return_value="1000 com.example.app allow\n1001 com.test.bank deny"):
            profiles = RootManager.get_root_profiles("abc")
        assert len(profiles) == 2
        assert profiles[0]["package"] == "com.example.app"
        assert profiles[0]["allow"] == "allow"

    def test_empty_output_returns_empty(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell", return_value=""):
            assert RootManager.get_root_profiles("abc") == []


# ── Superuser Log ─────────────────────────────────────────────────────────────

class TestSuperuserLog:
    def test_returns_entries(self) -> None:
        log_lines = (
            "I [12:00:00] policy: allow package=com.foo.app uid=10050\n"
            "I [12:00:01] policy: deny package=com.bar.app uid=10051"
        )
        with patch("cyberflash.core.root_manager.AdbManager.shell", return_value=log_lines):
            entries = RootManager.get_superuser_log("abc")
        assert any(e["action"] == "allow" for e in entries)
        assert any(e["action"] == "deny" for e in entries)

    def test_empty_log_returns_empty(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell", return_value=""):
            entries = RootManager.get_superuser_log("abc")
        assert entries == []


# ── dm-verity ─────────────────────────────────────────────────────────────────

class TestDmVerity:
    def test_dry_run(self) -> None:
        assert RootManager.disable_dm_verity("abc", dry_run=True) is True

    def test_success(self) -> None:
        with patch("cyberflash.core.root_manager.FastbootManager._run",
                   return_value=(0, "vbmeta", "")):
            assert RootManager.disable_dm_verity("abc") is True

    def test_failure(self) -> None:
        with patch("cyberflash.core.root_manager.FastbootManager._run",
                   return_value=(1, "", "FAILED")):
            assert RootManager.disable_dm_verity("abc") is False


class TestDisableForceEncryption:
    def test_dry_run(self) -> None:
        assert RootManager.disable_force_encryption("abc", dry_run=True) is True

    def test_no_fstab_returns_false(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell", return_value=""):
            assert RootManager.disable_force_encryption("abc") is False

    def test_patches_fstab(self) -> None:
        def shell(serial, cmd, **kw):
            if "find" in cmd:
                return "/vendor/etc/fstab.qcom"
            return ""  # no Permission denied

        with patch("cyberflash.core.root_manager.AdbManager.shell", side_effect=shell):
            ok = RootManager.disable_force_encryption("abc")
        assert ok is True


class TestGetAvbInfo:
    def test_returns_dict(self) -> None:
        with patch("cyberflash.core.root_manager.FastbootManager._run",
                   return_value=(0, "vbmeta-digest: abc123", "")):
            info = RootManager.get_avb_info("abc")
        assert isinstance(info, dict)


# ── DenyList Manager ──────────────────────────────────────────────────────────

class TestDenyList:
    def test_get_denylist(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell",
                   return_value="com.example.bank\ncom.google.android.gms"):
            pkgs = RootManager.get_denylist("abc")
        assert "com.example.bank" in pkgs

    def test_add_to_denylist_dry_run(self) -> None:
        assert RootManager.add_to_denylist("abc", "com.foo", dry_run=True) is True

    def test_add_to_denylist_success(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell", return_value="Done"):
            assert RootManager.add_to_denylist("abc", "com.foo") is True

    def test_add_to_denylist_failure(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell",
                   return_value="failed to add"):
            assert RootManager.add_to_denylist("abc", "com.foo") is False

    def test_remove_from_denylist_dry_run(self) -> None:
        assert RootManager.remove_from_denylist("abc", "com.foo", dry_run=True) is True

    def test_get_zygisk_enabled_true(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell",
                   return_value="zygisk: enable"):
            result = RootManager.get_zygisk_enabled("abc")
        assert result is True

    def test_get_zygisk_enabled_false(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell",
                   return_value="zygisk: disable"):
            result = RootManager.get_zygisk_enabled("abc")
        assert result is False

    def test_get_zygisk_unknown(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell", return_value=""):
            result = RootManager.get_zygisk_enabled("abc")
        assert result is None


# ── Banking-safe preset ───────────────────────────────────────────────────────

class TestBankingSafePreset:
    def test_dry_run_adds_all(self) -> None:
        with patch("cyberflash.core.root_manager.AdbManager.shell", return_value=""):
            added, skipped = RootManager.apply_banking_safe_preset("abc", dry_run=True)
        total = len(RootManager._BANKING_PACKAGES)
        assert added + skipped == total

    def test_skips_already_present(self) -> None:
        existing = RootManager._BANKING_PACKAGES[0]

        def shell(serial, cmd, **kw):
            if "--denylist ls" in cmd:
                return existing
            return "Done"

        with patch("cyberflash.core.root_manager.AdbManager.shell", side_effect=shell):
            _added, skipped = RootManager.apply_banking_safe_preset("abc", dry_run=True)
        assert skipped >= 1
