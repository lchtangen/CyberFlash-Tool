"""Unit tests for BootInspector — binary header parsing, marker detection."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from cyberflash.core.boot_inspector import BootInspector, _BOOT_MAGIC, _MAGISK_MARKER


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_minimal_boot_img(
    tmp_path: Path,
    ramdisk_size: int = 1024,
    header_version: int = 0,
    extra_bytes: bytes = b"",
) -> Path:
    """Create a minimal valid Android boot image for testing."""
    path = tmp_path / "boot.img"

    # Build a minimal v0 header (magic + zeroes)
    header = bytearray(4096)
    header[:8] = _BOOT_MAGIC
    # kernel_size at offset 8
    struct.pack_into("<I", header, 8, 512)
    # ramdisk_size at offset 16
    struct.pack_into("<I", header, 16, ramdisk_size)
    # page_size at offset 36
    struct.pack_into("<I", header, 36, 4096)
    # header_version at offset 160
    struct.pack_into("<I", header, 160, header_version)
    # cmdline at offset 64 (31 bytes including null terminator)
    header[64:64 + 31] = b"androidboot.hardware=guacamole\x00"

    path.write_bytes(bytes(header) + b"\x00" * 512 + b"\x00" * ramdisk_size + extra_bytes)
    return path


# ── inspect ───────────────────────────────────────────────────────────────────


class TestInspect:
    def test_valid_header_parsed(self, tmp_path: Path) -> None:
        img = _make_minimal_boot_img(tmp_path, ramdisk_size=2048)
        info = BootInspector.inspect(img)
        assert info.ramdisk_size == 2048
        assert "guacamole" in info.cmdline

    def test_no_magic_returns_default(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.img"
        p.write_bytes(b"\x00" * 1024)
        info = BootInspector.inspect(p)
        assert info.ramdisk_size == 0

    def test_missing_file_returns_default(self, tmp_path: Path) -> None:
        info = BootInspector.inspect(tmp_path / "missing.img")
        assert info.ramdisk_size == 0

    def test_header_version_parsed(self, tmp_path: Path) -> None:
        img = _make_minimal_boot_img(tmp_path, header_version=1)
        info = BootInspector.inspect(img)
        assert info.header_version == 1


# ── detect_magisk_patch ───────────────────────────────────────────────────────


class TestDetectMagiskPatch:
    def test_detects_magisk_marker(self, tmp_path: Path) -> None:
        img = _make_minimal_boot_img(tmp_path, extra_bytes=b"MAGISK_EXTRA_DATA")
        # Magisk marker in first 8KB
        path = tmp_path / "magisk_boot.img"
        path.write_bytes(_BOOT_MAGIC + b"\x00" * 100 + b"MAGISK" + b"\x00" * 1000)
        assert BootInspector.detect_magisk_patch(path) is True

    def test_no_magisk_marker(self, tmp_path: Path) -> None:
        img = _make_minimal_boot_img(tmp_path)
        assert BootInspector.detect_magisk_patch(img) is False

    def test_detect_magisk_patch_bytes(self) -> None:
        assert BootInspector.detect_magisk_patch_bytes(b"some MAGISK data") is True
        assert BootInspector.detect_magisk_patch_bytes(b"clean boot image") is False


# ── detect_kernelsu_patch ─────────────────────────────────────────────────────


class TestDetectKernelsuPatch:
    def test_detects_kernelsu_marker(self, tmp_path: Path) -> None:
        p = tmp_path / "ksu_boot.img"
        p.write_bytes(b"ANDROID!" + b"\x00" * 100 + b"KernelSU" + b"\x00" * 1000)
        assert BootInspector.detect_kernelsu_patch(p) is True

    def test_no_ksu_marker(self, tmp_path: Path) -> None:
        img = _make_minimal_boot_img(tmp_path)
        assert BootInspector.detect_kernelsu_patch(img) is False

    def test_detect_kernelsu_bytes(self) -> None:
        assert BootInspector.detect_kernelsu_patch_bytes(b"data KernelSU more") is True
        assert BootInspector.detect_kernelsu_patch_bytes(b"no markers here") is False


# ── compare ───────────────────────────────────────────────────────────────────


class TestCompare:
    def test_identical_images_no_diff(self, tmp_path: Path) -> None:
        img = _make_minimal_boot_img(tmp_path)
        diff = BootInspector.compare(img, img)
        assert diff == {}

    def test_different_ramdisk_sizes_detected(self, tmp_path: Path) -> None:
        img_a = _make_minimal_boot_img(tmp_path, ramdisk_size=1024)
        img_a2 = tmp_path / "boot_a.img"
        img_a2.write_bytes(img_a.read_bytes())

        img_b_path = tmp_path / "boot_b.img"
        img_b_data = bytearray(img_a2.read_bytes())
        struct.pack_into("<I", img_b_data, 16, 2048)  # different ramdisk_size
        img_b_path.write_bytes(bytes(img_b_data))

        diff = BootInspector.compare(img_a2, img_b_path)
        assert "ramdisk_size" in diff


# ── unpack ────────────────────────────────────────────────────────────────────


class TestUnpack:
    def test_unpack_creates_files(self, tmp_path: Path) -> None:
        img = _make_minimal_boot_img(tmp_path, ramdisk_size=512)
        dest = tmp_path / "unpacked"
        result = BootInspector.unpack(img, dest)
        assert result is True
        assert (dest / "kernel").exists()
