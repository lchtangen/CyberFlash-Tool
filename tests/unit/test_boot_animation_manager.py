"""Unit tests for BootAnimationManager."""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import patch

from cyberflash.core.boot_animation_manager import (
    BootAnimationManager,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_bootanim_zip(tmp_path: Path, desc: str | None = None) -> Path:
    """Create a valid bootanimation.zip in tmp_path."""
    zip_path = tmp_path / "bootanimation.zip"
    if desc is None:
        desc = "720 1280 30\np 1 0 part0\np 0 0 part1\n"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("desc.txt", desc)
        # Add some fake PNG frames
        for part in ("part0", "part1"):
            for i in range(3):
                zf.writestr(f"{part}/{i:05d}.png", b"\x89PNG\r\n\x1a\n")
    return zip_path


# ── parse_zip ─────────────────────────────────────────────────────────────────

class TestParseZip:
    def test_parses_valid_zip(self, tmp_path: Path) -> None:
        zip_path = _build_bootanim_zip(tmp_path)
        info = BootAnimationManager.parse_zip(zip_path)
        assert info.is_valid is True
        assert info.width == 720
        assert info.height == 1280
        assert info.fps == 30
        assert len(info.parts) == 2

    def test_parts_have_correct_data(self, tmp_path: Path) -> None:
        desc = "1080 1920 60\np 1 0 intro\np 0 5 loop\n"
        zip_path = _build_bootanim_zip(tmp_path, desc)
        info = BootAnimationManager.parse_zip(zip_path)
        assert info.parts[0].folder == "intro"
        assert info.parts[0].count == 1
        assert info.parts[1].folder == "loop"
        assert info.parts[1].count == 0   # loops forever

    def test_missing_file(self, tmp_path: Path) -> None:
        info = BootAnimationManager.parse_zip(tmp_path / "missing.zip")
        assert info.is_valid is False
        assert info.error != ""

    def test_missing_desc_txt(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "bad.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("some_other_file.txt", "content")
        info = BootAnimationManager.parse_zip(zip_path)
        assert info.is_valid is False

    def test_bad_header_returns_invalid(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "bad_header.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("desc.txt", "not_a_valid_header\n")
        info = BootAnimationManager.parse_zip(zip_path)
        assert info.is_valid is False

    def test_total_frames_counted(self, tmp_path: Path) -> None:
        zip_path = _build_bootanim_zip(tmp_path)
        info = BootAnimationManager.parse_zip(zip_path)
        # 3 frames in part0 + 3 frames in part1
        assert info.total_frames == 6

    def test_corrupt_zip_returns_invalid(self, tmp_path: Path) -> None:
        bad = tmp_path / "corrupt.zip"
        bad.write_bytes(b"\x00\x01\x02\x03")
        info = BootAnimationManager.parse_zip(bad)
        assert info.is_valid is False


# ── _parse_desc ───────────────────────────────────────────────────────────────

class TestParseDesc:
    def test_minimal_desc(self) -> None:
        desc = "360 640 24\np 1 0 folder1\n"
        info = BootAnimationManager._parse_desc(desc)
        assert info.is_valid is True
        assert info.width == 360
        assert info.height == 640
        assert info.fps == 24

    def test_complete_variant(self) -> None:
        desc = "720 1280 30\nc 1 0 complete_part\n"
        info = BootAnimationManager._parse_desc(desc)
        assert info.is_valid is True
        assert info.parts[0].variant == "c"

    def test_empty_desc_returns_invalid(self) -> None:
        info = BootAnimationManager._parse_desc("")
        assert info.is_valid is False

    def test_no_parts_returns_invalid(self) -> None:
        desc = "720 1280 30\n# just a comment\n"
        info = BootAnimationManager._parse_desc(desc)
        assert info.is_valid is False


# ── get_active_path ───────────────────────────────────────────────────────────

class TestGetActivePath:
    def test_finds_system_media(self) -> None:
        def shell(serial, cmd, **kw):
            if "/system/media/bootanimation.zip" in cmd:
                return "exists"
            return ""

        with patch("cyberflash.core.boot_animation_manager.AdbManager.shell",
                   side_effect=shell):
            path = BootAnimationManager.get_active_path("abc")
        assert path == "/system/media/bootanimation.zip"

    def test_returns_empty_when_not_found(self) -> None:
        with patch("cyberflash.core.boot_animation_manager.AdbManager.shell",
                   return_value=""):
            path = BootAnimationManager.get_active_path("abc")
        assert path == ""


# ── backup ────────────────────────────────────────────────────────────────────

class TestBackup:
    def test_no_active_animation_fails(self, tmp_path: Path) -> None:
        with patch("cyberflash.core.boot_animation_manager.AdbManager.shell",
                   return_value=""):
            result = BootAnimationManager.backup("abc", tmp_path)
        assert result.success is False

    def test_dry_run_with_active(self, tmp_path: Path) -> None:
        with patch.object(BootAnimationManager, "get_active_path",
                          return_value="/system/media/bootanimation.zip"):
            result = BootAnimationManager.backup("abc", tmp_path, dry_run=True)
        assert result.success is True

    def test_pull_success(self, tmp_path: Path) -> None:
        with (patch.object(BootAnimationManager, "get_active_path",
                           return_value="/system/media/bootanimation.zip"),
              patch("cyberflash.core.boot_animation_manager.AdbManager.pull",
                    return_value=True)):
            result = BootAnimationManager.backup("abc", tmp_path)
        assert result.success is True

    def test_pull_failure(self, tmp_path: Path) -> None:
        with (patch.object(BootAnimationManager, "get_active_path",
                           return_value="/system/media/bootanimation.zip"),
              patch("cyberflash.core.boot_animation_manager.AdbManager.pull",
                    return_value=False)):
            result = BootAnimationManager.backup("abc", tmp_path)
        assert result.success is False


# ── install ───────────────────────────────────────────────────────────────────

class TestInstall:
    def test_missing_zip_fails(self, tmp_path: Path) -> None:
        result = BootAnimationManager.install("abc", tmp_path / "missing.zip")
        assert result.success is False

    def test_invalid_zip_fails(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"\x00\x01\x02\x03")
        result = BootAnimationManager.install("abc", bad)
        assert result.success is False

    def test_dry_run_valid_zip(self, tmp_path: Path) -> None:
        zip_path = _build_bootanim_zip(tmp_path)
        with patch.object(BootAnimationManager, "get_active_path",
                          return_value="/system/media/bootanimation.zip"):
            result = BootAnimationManager.install("abc", zip_path, dry_run=True)
        assert result.success is True

    def test_push_failure_fails(self, tmp_path: Path) -> None:
        zip_path = _build_bootanim_zip(tmp_path)
        with (patch.object(BootAnimationManager, "get_active_path",
                           return_value="/system/media/bootanimation.zip"),
              patch("cyberflash.core.boot_animation_manager.AdbManager.push",
                    return_value=False)):
            result = BootAnimationManager.install("abc", zip_path)
        assert result.success is False


# ── reset_to_stock ────────────────────────────────────────────────────────────

class TestResetToStock:
    def test_no_active_returns_true(self) -> None:
        with patch.object(BootAnimationManager, "get_active_path", return_value=""):
            result = BootAnimationManager.reset_to_stock("abc")
        assert result.success is True

    def test_dry_run(self) -> None:
        with patch.object(BootAnimationManager, "get_active_path",
                          return_value="/system/media/bootanimation.zip"):
            result = BootAnimationManager.reset_to_stock("abc", dry_run=True)
        assert result.success is True

    def test_root_removed(self) -> None:
        with (patch.object(BootAnimationManager, "get_active_path",
                           return_value="/system/media/bootanimation.zip"),
              patch("cyberflash.core.boot_animation_manager.AdbManager.shell",
                    return_value="")):
            result = BootAnimationManager.reset_to_stock("abc")
        assert result.success is True


# ── list_frames ───────────────────────────────────────────────────────────────

class TestListFrames:
    def test_lists_frames_by_part(self, tmp_path: Path) -> None:
        zip_path = _build_bootanim_zip(tmp_path)
        frames = BootAnimationManager.list_frames(zip_path)
        assert "part0" in frames
        assert "part1" in frames
        assert len(frames["part0"]) == 3

    def test_empty_on_bad_zip(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"\x00\x01")
        frames = BootAnimationManager.list_frames(bad)
        assert frames == {}


# ── extract_frame ─────────────────────────────────────────────────────────────

class TestExtractFrame:
    def test_extracts_png_bytes(self, tmp_path: Path) -> None:
        zip_path = _build_bootanim_zip(tmp_path)
        data = BootAnimationManager.extract_frame(zip_path, "part0/00000.png")
        assert data is not None
        assert len(data) > 0

    def test_missing_frame_returns_none(self, tmp_path: Path) -> None:
        zip_path = _build_bootanim_zip(tmp_path)
        assert BootAnimationManager.extract_frame(zip_path, "nonexistent/frame.png") is None
