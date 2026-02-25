"""Unit tests for HeimdallManager."""

from __future__ import annotations

import io
import struct
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from cyberflash.core.heimdall_manager import (
    HeimdallManager,
    PitEntry,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_pit(entries: list[dict]) -> bytes:
    """Build a minimal PIT binary for testing.

    Each PIT entry is exactly 136 bytes:
      7 x uint32 (28 bytes) + name (32) + filename (32) + fota (32) + pad (12)
    """
    header = struct.pack("<III", 0x12349876, len(entries), 1)
    body = b""
    for e in entries:
        name = e.get("name", "TEST").encode("ascii")[:32].ljust(32, b"\x00")
        fname = e.get("filename", "test.img").encode("ascii")[:32].ljust(32, b"\x00")
        fota = b"\x00" * 32
        pad = b"\x00" * 12  # pad to reach 136 bytes per entry
        chunk = struct.pack(
            "<7I",
            e.get("id", 1),
            e.get("type", 0),
            e.get("fs", 0),
            e.get("start", 0),
            e.get("count", 1024),
            0,
            0,
        )
        body += chunk + name + fname + fota + pad
    return header + body


def _make_tar(tmp_path: Path, files: dict[str, bytes]) -> Path:
    """Create a TAR archive with given filename→content mapping."""
    tar_path = tmp_path / "package.tar"
    with tarfile.open(str(tar_path), "w") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return tar_path


# ── is_available / version ────────────────────────────────────────────────────


class TestIsAvailable:
    def test_true_when_found(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/heimdall"):
            assert HeimdallManager.is_available() is True

    def test_false_when_missing(self) -> None:
        with patch("shutil.which", return_value=None):
            assert HeimdallManager.is_available() is False

    def test_version_returns_string(self) -> None:
        with patch.object(HeimdallManager, "_run", return_value=(0, "v1.4.2\n", "")):
            assert HeimdallManager.version() == "v1.4.2"

    def test_version_returns_empty_on_error(self) -> None:
        with patch.object(HeimdallManager, "_run", return_value=(-1, "", "not found")):
            assert HeimdallManager.version() == ""


# ── detect_download_mode ──────────────────────────────────────────────────────


class TestDetectDownloadMode:
    def test_true_when_rc_zero(self) -> None:
        with patch.object(HeimdallManager, "_run", return_value=(0, "detected", "")):
            assert HeimdallManager.detect_download_mode() is True

    def test_false_when_rc_nonzero(self) -> None:
        with patch.object(HeimdallManager, "_run", return_value=(1, "", "no device")):
            assert HeimdallManager.detect_download_mode() is False


# ── parse_pit ─────────────────────────────────────────────────────────────────


class TestParsePit:
    def test_parse_single_entry(self, tmp_path: Path) -> None:
        pit_bytes = _build_pit([{"name": "BOOT", "filename": "boot.img", "count": 2048}])
        pit_file = tmp_path / "device.pit"
        pit_file.write_bytes(pit_bytes)

        table = HeimdallManager.parse_pit(pit_file)
        assert table is not None
        assert len(table.entries) == 1
        assert table.entries[0].name == "BOOT"
        assert table.entries[0].filename == "boot.img"
        assert table.entries[0].block_count == 2048

    def test_parse_multiple_entries(self, tmp_path: Path) -> None:
        entries = [
            {"name": "BOOT", "filename": "boot.img", "count": 1024},
            {"name": "SYSTEM", "filename": "system.img", "count": 8192},
            {"name": "MODEM", "filename": "modem.bin", "count": 512},
        ]
        pit_bytes = _build_pit(entries)
        pit_file = tmp_path / "device.pit"
        pit_file.write_bytes(pit_bytes)

        table = HeimdallManager.parse_pit(pit_file)
        assert table is not None
        assert len(table.entries) == 3
        names = [e.name for e in table.entries]
        assert "BOOT" in names
        assert "SYSTEM" in names

    def test_find_entry_by_name(self, tmp_path: Path) -> None:
        pit_bytes = _build_pit(
            [
                {"name": "RECOVERY", "filename": "recovery.img", "count": 512},
            ]
        )
        pit_file = tmp_path / "device.pit"
        pit_file.write_bytes(pit_bytes)

        table = HeimdallManager.parse_pit(pit_file)
        assert table is not None
        entry = table.find("recovery")
        assert entry is not None
        assert entry.name == "RECOVERY"

    def test_find_returns_none_for_missing(self, tmp_path: Path) -> None:
        pit_bytes = _build_pit([{"name": "BOOT"}])
        pit_file = tmp_path / "device.pit"
        pit_file.write_bytes(pit_bytes)
        table = HeimdallManager.parse_pit(pit_file)
        assert table is not None
        assert table.find("NONEXISTENT") is None

    def test_file_not_found(self, tmp_path: Path) -> None:
        result = HeimdallManager.parse_pit(tmp_path / "missing.pit")
        assert result is None

    def test_too_small(self, tmp_path: Path) -> None:
        pit_file = tmp_path / "small.pit"
        pit_file.write_bytes(b"\x00\x01")
        result = HeimdallManager.parse_pit(pit_file)
        assert result is None


# ── inspect_odin_package ──────────────────────────────────────────────────────


class TestInspectOdinPackage:
    def test_detects_ap_and_bl(self, tmp_path: Path) -> None:
        tar_path = _make_tar(
            tmp_path,
            {
                "boot.img.lz4": b"boot",
                "bootloader.img": b"bl",
                "modem.bin": b"cp",
            },
        )
        contents = HeimdallManager.inspect_odin_package(tar_path)
        # boot maps to AP, bootloader maps to BL
        assert any("boot" in f.lower() for f in contents.get("AP", []) + contents.get("BL", []))

    def test_empty_tar_returns_empty(self, tmp_path: Path) -> None:
        tar_path = _make_tar(tmp_path, {})
        contents = HeimdallManager.inspect_odin_package(tar_path)
        assert contents == {}

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = HeimdallManager.inspect_odin_package(tmp_path / "missing.tar")
        assert result == {}


# ── flash_partition ───────────────────────────────────────────────────────────


class TestFlashPartition:
    def test_dry_run_returns_success(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_bytes(b"data")
        result = HeimdallManager.flash_partition("BOOT", img, dry_run=True)
        assert result.success is True
        assert result.partition == "BOOT"

    def test_missing_file_returns_failure(self, tmp_path: Path) -> None:
        result = HeimdallManager.flash_partition("BOOT", tmp_path / "missing.img")
        assert result.success is False

    def test_real_flash_success(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_bytes(b"data")
        with patch.object(HeimdallManager, "_run", return_value=(0, "", "")):
            result = HeimdallManager.flash_partition("BOOT", img)
        assert result.success is True

    def test_real_flash_failure(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_bytes(b"data")
        with patch.object(HeimdallManager, "_run", return_value=(1, "", "Error")):
            result = HeimdallManager.flash_partition("BOOT", img)
        assert result.success is False
        assert result.returncode == 1


# ── repartition ───────────────────────────────────────────────────────────────


class TestRepartition:
    def test_dry_run_returns_true(self, tmp_path: Path) -> None:
        pit = tmp_path / "new.pit"
        pit.write_bytes(b"\x00" * 8)
        assert HeimdallManager.repartition(pit, dry_run=True) is True

    def test_missing_pit_returns_false(self, tmp_path: Path) -> None:
        assert HeimdallManager.repartition(tmp_path / "missing.pit") is False

    def test_success(self, tmp_path: Path) -> None:
        pit = tmp_path / "new.pit"
        pit.write_bytes(b"\x00" * 8)
        with patch.object(HeimdallManager, "_run", return_value=(0, "", "")):
            assert HeimdallManager.repartition(pit) is True


# ── PitEntry helpers ──────────────────────────────────────────────────────────


class TestPitEntry:
    def test_size_mb(self) -> None:
        e = PitEntry(
            partition_id=1,
            partition_type=0,
            filesystem_id=0,
            start_block=0,
            block_count=2048,
            name="TEST",
            filename="test.img",
        )
        # 2048 blocks x 512 bytes / 1 MiB
        assert e.size_mb == pytest.approx(1.0)
