"""Unit tests for PayloadDumper.

All tests use in-memory bytes to avoid touching the filesystem for the binary
parsing logic; extracted partition tests use tmp_path.
"""

from __future__ import annotations

import bz2
import lzma
import struct
import zipfile
from pathlib import Path

import pytest

from cyberflash.core.payload_dumper import PayloadDumper, _iter_fields, _read_varint

# ── Protobuf helpers ──────────────────────────────────────────────────────────


def _encode_varint(value: int) -> bytes:
    """Encode a non-negative integer as a protobuf varint."""
    buf = []
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            buf.append(b | 0x80)
        else:
            buf.append(b)
            break
    return bytes(buf)


def _encode_field_varint(field_num: int, value: int) -> bytes:
    tag = (field_num << 3) | 0
    return _encode_varint(tag) + _encode_varint(value)


def _encode_field_bytes(field_num: int, data: bytes) -> bytes:
    tag = (field_num << 3) | 2
    return _encode_varint(tag) + _encode_varint(len(data)) + data


# ── Build minimal payload.bin in memory ─────────────────────────────────────


def _build_partition_proto(name: str, data: bytes, op_type: int = 0) -> bytes:
    """Build a minimal PartitionUpdate protobuf for a REPLACE operation."""
    # Extent: start_block=0, num_blocks=1
    extent = _encode_field_varint(1, 0) + _encode_field_varint(2, 1)
    # InstallOperation: type, data_offset=0, data_length=len(data), dst_extents
    op = (
        _encode_field_varint(1, op_type)
        + _encode_field_varint(2, 0)  # data_offset
        + _encode_field_varint(3, len(data))  # data_length
        + _encode_field_bytes(6, extent)  # dst_extents
    )
    # PartitionInfo: size
    part_info = _encode_field_varint(1, len(data))
    return (
        _encode_field_bytes(1, name.encode())  # partition_name
        + _encode_field_bytes(4, op)  # operations
        + _encode_field_bytes(8, part_info)  # new_partition_info
    )


def _build_payload(partitions: list[tuple[str, bytes, int]]) -> bytes:
    """Build a valid v2 payload.bin bytes object for the given partitions."""
    data_sections: list[bytes] = []
    manifest_parts: list[bytes] = []

    # Assign sequential data offsets
    current_offset = 0
    adjusted_partitions = []
    for name, raw_data, op_type in partitions:
        adjusted_partitions.append((name, raw_data, op_type, current_offset))
        data_sections.append(raw_data)
        current_offset += len(raw_data)

    # Rebuild partition protos with correct data offsets
    for name, raw_data, op_type, data_offset in adjusted_partitions:
        extent = _encode_field_varint(1, 0) + _encode_field_varint(2, 1)
        op = (
            _encode_field_varint(1, op_type)
            + _encode_field_varint(2, data_offset)
            + _encode_field_varint(3, len(raw_data))
            + _encode_field_bytes(6, extent)
        )
        part_info = _encode_field_varint(1, len(raw_data))
        partition_proto = (
            _encode_field_bytes(1, name.encode())
            + _encode_field_bytes(4, op)
            + _encode_field_bytes(8, part_info)
        )
        manifest_parts.append(_encode_field_bytes(13, partition_proto))

    manifest = b"".join(manifest_parts)
    data_blob = b"".join(data_sections)

    # Header: magic + version(8) + manifest_size(8) + metadata_sig_size(4)
    header = (
        b"CrAU"
        + struct.pack(">Q", 2)  # version
        + struct.pack(">Q", len(manifest))  # manifest_size
        + struct.pack(">I", 0)  # metadata_sig_size
        + manifest
        + data_blob
    )
    return header


# ── _read_varint ─────────────────────────────────────────────────────────────


class TestReadVarint:
    def test_single_byte(self) -> None:
        val, pos = _read_varint(b"\x01", 0)
        assert val == 1
        assert pos == 1

    def test_max_single_byte(self) -> None:
        val, _pos = _read_varint(b"\x7f", 0)
        assert val == 127

    def test_two_bytes(self) -> None:
        # 300 = 0b100101100 → varint: 0xac 0x02
        val, pos = _read_varint(b"\xac\x02", 0)
        assert val == 300
        assert pos == 2

    def test_offset(self) -> None:
        data = b"\x00\x00\x05"
        val, pos = _read_varint(data, 2)
        assert val == 5
        assert pos == 3


# ── _iter_fields ─────────────────────────────────────────────────────────────


class TestIterFields:
    def test_varint_field(self) -> None:
        data = _encode_field_varint(1, 42)
        fields = _iter_fields(data)
        assert len(fields) == 1
        fnum, wtype, val = fields[0]
        assert fnum == 1
        assert wtype == 0
        assert val == 42

    def test_bytes_field(self) -> None:
        payload = b"hello"
        data = _encode_field_bytes(3, payload)
        fields = _iter_fields(data)
        assert len(fields) == 1
        fnum, wtype, val = fields[0]
        assert fnum == 3
        assert wtype == 2
        assert val == payload

    def test_multiple_fields(self) -> None:
        data = _encode_field_varint(1, 10) + _encode_field_bytes(2, b"world")
        fields = _iter_fields(data)
        assert len(fields) == 2


# ── PayloadDumper integration ─────────────────────────────────────────────────


class TestPayloadDumperRaw:
    def test_list_partitions(self, tmp_path: Path) -> None:
        raw = b"\x00" * 4096
        payload_bytes = _build_payload([("boot", raw, 0), ("system", raw, 0)])
        p = tmp_path / "payload.bin"
        p.write_bytes(payload_bytes)
        dumper = PayloadDumper(p)
        parts = dumper.list_partitions()
        assert "boot" in parts
        assert "system" in parts
        assert sorted(parts) == parts

    def test_extract_replace(self, tmp_path: Path) -> None:
        data = b"A" * 4096
        payload_bytes = _build_payload([("boot", data, 0)])
        p = tmp_path / "payload.bin"
        p.write_bytes(payload_bytes)
        dumper = PayloadDumper(p)
        out = dumper.extract("boot", tmp_path / "out")
        assert out.exists()
        assert out.name == "boot.img"

    def test_extract_xz(self, tmp_path: Path) -> None:
        raw = b"B" * 4096
        compressed = lzma.compress(raw)
        payload_bytes = _build_payload([("vendor", compressed, 8)])
        p = tmp_path / "payload.bin"
        p.write_bytes(payload_bytes)
        dumper = PayloadDumper(p)
        out = dumper.extract("vendor", tmp_path / "out")
        assert out.exists()

    def test_extract_bz2(self, tmp_path: Path) -> None:
        raw = b"C" * 4096
        compressed = bz2.compress(raw)
        payload_bytes = _build_payload([("recovery", compressed, 1)])
        p = tmp_path / "payload.bin"
        p.write_bytes(payload_bytes)
        dumper = PayloadDumper(p)
        out = dumper.extract("recovery", tmp_path / "out")
        assert out.exists()

    def test_unknown_partition_raises(self, tmp_path: Path) -> None:
        raw = b"\x00" * 4096
        payload_bytes = _build_payload([("boot", raw, 0)])
        p = tmp_path / "payload.bin"
        p.write_bytes(payload_bytes)
        dumper = PayloadDumper(p)
        with pytest.raises(ValueError, match="dtbo"):
            dumper.extract("dtbo", tmp_path / "out")

    def test_progress_callback(self, tmp_path: Path) -> None:
        raw = b"X" * 4096
        payload_bytes = _build_payload([("boot", raw, 0)])
        p = tmp_path / "payload.bin"
        p.write_bytes(payload_bytes)
        calls: list[tuple[int, int]] = []
        dumper = PayloadDumper(p)
        dumper.extract("boot", tmp_path / "out", progress_cb=lambda d, t: calls.append((d, t)))
        assert len(calls) >= 1

    def test_bad_magic_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.bin"
        p.write_bytes(b"BAD!" + b"\x00" * 100)
        with pytest.raises(ValueError, match="bad magic"):
            PayloadDumper(p).list_partitions()

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            PayloadDumper(tmp_path / "nonexistent.bin")


class TestPayloadDumperZip:
    def test_list_partitions_from_zip(self, tmp_path: Path) -> None:
        raw = b"\x00" * 4096
        payload_bytes = _build_payload([("boot", raw, 0)])
        z = tmp_path / "ota.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("payload.bin", payload_bytes)
        dumper = PayloadDumper(z)
        assert "boot" in dumper.list_partitions()

    def test_zip_without_payload_raises(self, tmp_path: Path) -> None:
        z = tmp_path / "empty.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("metadata", "nothing")
        with pytest.raises(ValueError, match=r"payload.bin not found"):
            PayloadDumper(z)

    def test_context_manager(self, tmp_path: Path) -> None:
        raw = b"\x00" * 4096
        payload_bytes = _build_payload([("boot", raw, 0)])
        p = tmp_path / "payload.bin"
        p.write_bytes(payload_bytes)
        with PayloadDumper(p) as dumper:
            parts = dumper.list_partitions()
        assert "boot" in parts
