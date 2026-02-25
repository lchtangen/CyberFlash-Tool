"""boot_inspector.py — Android boot image inspector and unpacker.

Parses mkbootimg format headers (v0-v4), detects Magisk/KernelSU patches,
and provides image comparison.

References:
  https://source.android.com/docs/core/architecture/bootloader/boot-image-header
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Boot image magic bytes
_BOOT_MAGIC = b"ANDROID!"
_BOOT_MAGIC_SIZE = 8

# Magisk detection marker
_MAGISK_MARKER = b"MAGISK"

# KernelSU detection markers
_KSU_MARKERS = (b"KernelSU", b"kernelsu", b"\x4b\x53\x55\x00")

# Header sizes per version
_HEADER_V0_SIZE = 632
_HEADER_V3_SIZE = 1580


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class BootImageInfo:
    """Parsed metadata from an Android boot image."""

    kernel_ver: str = ""
    cmdline: str = ""
    ramdisk_size: int = 0
    os_version: str = ""
    os_patch_level: str = ""
    magisk_patched: bool = False
    kernelsu_patched: bool = False
    header_version: int = 0
    extra: dict[str, object] = field(default_factory=dict)


# ── Main class ────────────────────────────────────────────────────────────────


class BootInspector:
    """Classmethod-only boot image analysis utility."""

    # ── Inspection ────────────────────────────────────────────────────────────

    @classmethod
    def inspect(cls, img_path: Path) -> BootImageInfo:
        """Parse boot image header and detect patches.

        Returns a BootImageInfo; on error returns a default instance.
        """
        info = BootImageInfo()
        try:
            with open(img_path, "rb") as fh:
                header = fh.read(4096)
        except OSError as exc:
            logger.warning("boot_inspector: cannot read %s: %s", img_path, exc)
            return info

        if header[:_BOOT_MAGIC_SIZE] != _BOOT_MAGIC:
            logger.debug("boot_inspector: no ANDROID! magic in %s", img_path)
            return info

        # Version is at offset 160 in v1+ headers, 0 for v0
        # v0 struct offsets (all uint32):
        #   8  kernel_size, 12 kernel_addr, 16 ramdisk_size, ...
        #   512 cmdline (512 bytes), 1024 name (16 bytes), ...
        try:
            # header_version is at offset 160 in v1+; for v0 it doesn't exist
            if len(header) >= 164:
                (header_version,) = struct.unpack_from("<I", header, 160)
                info.header_version = header_version
            else:
                info.header_version = 0

            (ramdisk_size,) = struct.unpack_from("<I", header, 16)
            info.ramdisk_size = ramdisk_size

            # cmdline: 512 bytes at offset 64 (v0-v2) or 568 (v3+)
            cmdline_offset = 568 if info.header_version >= 3 else 64
            cmdline_raw = header[cmdline_offset: cmdline_offset + 512]
            info.cmdline = cmdline_raw.split(b"\x00")[0].decode(errors="replace").strip()

            # os_version at offset 156 (v1+)
            if len(header) >= 160 and info.header_version >= 1:
                (os_ver_raw,) = struct.unpack_from("<I", header, 156)
                info.os_version = cls._decode_os_version(os_ver_raw)
                info.os_patch_level = cls._decode_patch_level(os_ver_raw)

        except struct.error as exc:
            logger.debug("boot_inspector: struct parse error: %s", exc)

        # Patch detection (check first 8KB)
        sample = header[:8192]
        info.magisk_patched = cls.detect_magisk_patch_bytes(sample)
        info.kernelsu_patched = cls.detect_kernelsu_patch_bytes(sample)

        return info

    @classmethod
    def _decode_os_version(cls, raw: int) -> str:
        """Decode packed os_version from boot header."""
        # Upper 23 bits: os version (A.B.C packed in 7-7-7 bits)
        ver = raw >> 11
        a = (ver >> 14) & 0x7F
        b = (ver >> 7) & 0x7F
        c = ver & 0x7F
        return f"{a}.{b}.{c}"

    @classmethod
    def _decode_patch_level(cls, raw: int) -> str:
        """Decode security patch level from boot header."""
        # Lower 11 bits: YYYY-MM (year * 12 + month - 1)
        patch = raw & 0x7FF
        year = 2000 + (patch >> 4)
        month = patch & 0xF
        return f"{year}-{month:02d}-01"

    @classmethod
    def unpack(cls, img_path: Path, dest_dir: Path) -> bool:
        """Write kernel and ramdisk bytes to *dest_dir*.

        This is a simplified unpack — extracts raw blobs without
        decompression.  Returns True on success.
        """
        info = cls.inspect(img_path)
        if info.ramdisk_size == 0:
            logger.warning("unpack: cannot determine ramdisk size from %s", img_path)
            return False

        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(img_path, "rb") as fh:
                raw = fh.read()
        except OSError:
            return False

        # Simplified: find ANDROID! magic, then skip header page(s)
        # Page size is usually 4096 or 2048 bytes
        page_size = 4096
        page_size_offset = 36  # uint32 at offset 36 in v0 header
        if len(raw) >= 40:
            (ps,) = struct.unpack_from("<I", raw, page_size_offset)
            if ps in (2048, 4096, 8192, 16384):
                page_size = ps

        kernel_size_offset = 8
        (kernel_size,) = struct.unpack_from("<I", raw, kernel_size_offset)

        # Kernel starts at first page after header
        kernel_offset = page_size
        kernel_data = raw[kernel_offset: kernel_offset + kernel_size]
        (dest_dir / "kernel").write_bytes(kernel_data)

        # Ramdisk follows kernel (rounded to page size)
        ramdisk_offset = kernel_offset + (
            (kernel_size + page_size - 1) // page_size * page_size
        )
        ramdisk_data = raw[ramdisk_offset: ramdisk_offset + info.ramdisk_size]
        (dest_dir / "ramdisk.img").write_bytes(ramdisk_data)

        return True

    @classmethod
    def detect_magisk_patch(cls, img_path: Path) -> bool:
        """Return True if *img_path* appears to be Magisk-patched."""
        try:
            with open(img_path, "rb") as fh:
                sample = fh.read(8192)
            return cls.detect_magisk_patch_bytes(sample)
        except OSError:
            return False

    @classmethod
    def detect_magisk_patch_bytes(cls, data: bytes) -> bool:
        """Return True if *data* contains the MAGISK marker."""
        return _MAGISK_MARKER in data

    @classmethod
    def detect_kernelsu_patch(cls, img_path: Path) -> bool:
        """Return True if *img_path* appears to be KernelSU-patched."""
        try:
            with open(img_path, "rb") as fh:
                sample = fh.read(8192)
            return cls.detect_kernelsu_patch_bytes(sample)
        except OSError:
            return False

    @classmethod
    def detect_kernelsu_patch_bytes(cls, data: bytes) -> bool:
        """Return True if *data* contains a KernelSU marker."""
        return any(marker in data for marker in _KSU_MARKERS)

    @classmethod
    def compare(cls, img_a: Path, img_b: Path) -> dict[str, object]:
        """Return a dict of fields that differ between two boot images."""
        info_a = cls.inspect(img_a)
        info_b = cls.inspect(img_b)
        diff: dict[str, object] = {}
        fields = (
            "kernel_ver", "cmdline", "ramdisk_size",
            "os_version", "os_patch_level",
            "magisk_patched", "kernelsu_patched", "header_version",
        )
        for f in fields:
            val_a = getattr(info_a, f)
            val_b = getattr(info_b, f)
            if val_a != val_b:
                diff[f] = {"a": val_a, "b": val_b}
        return diff
