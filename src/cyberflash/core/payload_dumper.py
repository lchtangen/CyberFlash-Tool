"""payload_dumper.py — Extract partition images from Android OTA payload.bin files.

Supports:
  - .zip OTA archives (extracts embedded payload.bin automatically)
  - Raw payload.bin files
  - REPLACE   (raw copy)
  - REPLACE_XZ (lzma2-compressed)
  - REPLACE_BZ (bzip2-compressed)

No external dependencies beyond the standard library.  The protobuf manifest
is parsed with a minimal inline wire-format reader that covers exactly the
fields needed (field numbers from update_metadata.proto, AOSP).

Usage::

    from cyberflash.core.payload_dumper import PayloadDumper

    dumper = PayloadDumper("/path/to/ota.zip")
    boot_img = dumper.extract("boot", dest_dir="/tmp/extracted")
    # boot_img → Path("/tmp/extracted/boot.img")
"""

from __future__ import annotations

import bz2
import logging
import lzma
import struct
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ── Payload.bin constants ────────────────────────────────────────────────────

_MAGIC = b"CrAU"
_BLOCK_SIZE = 4096

# InstallOperation.Type values (update_metadata.proto)
_OP_REPLACE = 0
_OP_REPLACE_BZ = 1
_OP_REPLACE_XZ = 8


# ── Minimal protobuf wire-format reader ─────────────────────────────────────


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decode a protobuf varint at *pos*; return (value, new_pos)."""
    result = 0
    shift = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, pos
        shift += 7


def _iter_fields(data: bytes) -> list[tuple[int, int, bytes | int]]:
    """Iterate over top-level protobuf fields.

    Yields ``(field_number, wire_type, value)`` where *value* is:
      - ``bytes`` for wire type 2 (length-delimited)
      - ``int``   for wire type 0 (varint)
    """
    pos = 0
    out: list[tuple[int, int, bytes | int]] = []
    while pos < len(data):
        tag, pos = _read_varint(data, pos)
        wire_type = tag & 0x07
        field_num = tag >> 3
        if wire_type == 0:  # varint
            val, pos = _read_varint(data, pos)
            out.append((field_num, wire_type, val))
        elif wire_type == 2:  # length-delimited
            length, pos = _read_varint(data, pos)
            out.append((field_num, wire_type, data[pos : pos + length]))
            pos += length
        elif wire_type == 1:  # 64-bit fixed
            out.append((field_num, wire_type, struct.unpack_from("<Q", data, pos)[0]))
            pos += 8
        elif wire_type == 5:  # 32-bit fixed
            out.append((field_num, wire_type, struct.unpack_from("<I", data, pos)[0]))
            pos += 4
        else:
            # Unknown wire type — cannot continue safely
            logger.debug("Unknown protobuf wire type %d at pos %d", wire_type, pos)
            break
    return out


# ── Parsed structures ────────────────────────────────────────────────────────


class _Extent(NamedTuple):
    start_block: int
    num_blocks: int


class _Operation(NamedTuple):
    op_type: int  # _OP_REPLACE / _OP_REPLACE_XZ / _OP_REPLACE_BZ
    data_offset: int  # byte offset into data blob
    data_length: int  # byte length in data blob
    dst_extents: list[_Extent]


class _Partition(NamedTuple):
    name: str
    operations: list[_Operation]
    new_size: int  # bytes (0 if unknown)


def _parse_extent(buf: bytes) -> _Extent:
    start_block = 0
    num_blocks = 0
    for fnum, wtype, val in _iter_fields(buf):
        if fnum == 1 and wtype == 0:
            start_block = int(val)  # type: ignore[arg-type]
        elif fnum == 2 and wtype == 0:
            num_blocks = int(val)  # type: ignore[arg-type]
    return _Extent(start_block, num_blocks)


def _parse_operation(buf: bytes) -> _Operation:
    op_type = data_offset = data_length = 0
    dst_extents: list[_Extent] = []
    for fnum, wtype, val in _iter_fields(buf):
        if fnum == 1 and wtype == 0:  # type
            op_type = int(val)  # type: ignore[arg-type]
        elif fnum == 7 and wtype == 0:  # data_offset
            data_offset = int(val)  # type: ignore[arg-type]
        elif fnum == 8 and wtype == 0:  # data_length
            data_length = int(val)  # type: ignore[arg-type]
        elif fnum == 4 and wtype == 2:  # dst_extents
            dst_extents.append(_parse_extent(bytes(val)))  # type: ignore[arg-type]
    return _Operation(op_type, data_offset, data_length, dst_extents)


def _parse_partition_update(buf: bytes) -> _Partition:
    name = ""
    operations: list[_Operation] = []
    new_size = 0
    for fnum, wtype, val in _iter_fields(buf):
        if fnum == 1 and wtype == 2:            # partition_name
            name = bytes(val).decode("utf-8", errors="replace")  # type: ignore[arg-type]
        elif fnum == 8 and wtype == 2:          # operations (repeated InstallOperation)
            operations.append(_parse_operation(bytes(val)))       # type: ignore[arg-type]
        elif fnum == 7 and wtype == 2:          # new_partition_info
            # PartitionInfo message: field 1 = size (varint)
            inner = _iter_fields(bytes(val))                       # type: ignore[arg-type]
            for ifnum, iwtype, ival in inner:
                if ifnum == 1 and iwtype == 0:
                    new_size = int(ival)  # type: ignore[arg-type]
    return _Partition(name, operations, new_size)


def _parse_manifest(manifest_bytes: bytes) -> list[_Partition]:
    """Parse DeltaArchiveManifest and return list of Partition objects."""
    partitions: list[_Partition] = []
    for fnum, wtype, val in _iter_fields(manifest_bytes):
        if fnum == 13 and wtype == 2:  # repeated PartitionUpdate
            partitions.append(_parse_partition_update(bytes(val)))  # type: ignore[arg-type]
    return partitions


# ── Header parsing ───────────────────────────────────────────────────────────


class _PayloadHeader(NamedTuple):
    version: int
    manifest_size: int
    metadata_sig_size: int  # v2 only
    data_offset: int  # byte offset where the data blob begins


def _parse_header(fobj) -> _PayloadHeader:
    magic = fobj.read(4)
    if magic != _MAGIC:
        raise ValueError(f"Not a valid payload.bin (bad magic: {magic!r})")

    version = struct.unpack(">Q", fobj.read(8))[0]
    manifest_size = struct.unpack(">Q", fobj.read(8))[0]

    metadata_sig_size = 0
    if version >= 2:
        metadata_sig_size = struct.unpack(">I", fobj.read(4))[0]

    # data blob starts after: magic(4) + version(8) + manifest_size(8) +
    # optional metadata_sig_size field(4) + manifest + metadata_signature
    header_size = 4 + 8 + 8 + (4 if version >= 2 else 0)
    data_offset = header_size + manifest_size + metadata_sig_size

    return _PayloadHeader(version, manifest_size, metadata_sig_size, data_offset)


# ── Main extractor ───────────────────────────────────────────────────────────


class PayloadDumper:
    """Extract partition images from an Android OTA payload.

    Args:
        source: Path to an OTA ``.zip`` file **or** a raw ``payload.bin``.
    """

    def __init__(self, source: str | Path) -> None:
        self._source = Path(source)
        if not self._source.exists():
            raise FileNotFoundError(f"Source not found: {self._source}")

        self._zip_file: zipfile.ZipFile | None = None
        self._payload_path: Path | None = None

        if self._source.suffix.lower() == ".zip":
            self._zip_file = zipfile.ZipFile(self._source, "r")
            names = self._zip_file.namelist()
            if "payload.bin" not in names:
                raise ValueError("payload.bin not found inside the OTA zip")
        else:
            self._payload_path = self._source

    def list_partitions(self) -> list[str]:
        """Return sorted list of partition names in the payload."""
        with self._open_payload() as fobj:
            header = _parse_header(fobj)
            manifest_bytes = fobj.read(header.manifest_size)
        return sorted(p.name for p in _parse_manifest(manifest_bytes))

    def extract(
        self,
        partition: str,
        dest_dir: str | Path,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Extract *partition* image to *dest_dir*.

        Args:
            partition: Partition name, e.g. ``"boot"``, ``"system"``.
            dest_dir: Directory where the ``.img`` file will be written.
            progress_cb: Optional ``(bytes_written, total_bytes)`` callback.

        Returns:
            Path to the extracted ``.img`` file.

        Raises:
            ValueError: Partition not found or operation type unsupported.
        """
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        out_path = dest_dir / f"{partition}.img"

        with self._open_payload() as fobj:
            header = _parse_header(fobj)
            manifest_bytes = fobj.read(header.manifest_size)
            partitions = _parse_manifest(manifest_bytes)

            target = next((p for p in partitions if p.name == partition), None)
            if target is None:
                available = [p.name for p in partitions]
                raise ValueError(f"Partition '{partition}' not found. Available: {available}")

            logger.info(
                "Extracting partition '%s' (%d operations, %d bytes)",
                partition,
                len(target.operations),
                target.new_size,
            )

            total_size = target.new_size or sum(op.data_length for op in target.operations)
            written = 0

            with out_path.open("wb") as out:
                for op in target.operations:
                    if op.op_type not in (_OP_REPLACE, _OP_REPLACE_XZ, _OP_REPLACE_BZ):
                        raise ValueError(
                            f"Unsupported operation type {op.op_type} in partition "
                            f"'{partition}'. Delta OTAs are not supported — use a "
                            "full OTA zip."
                        )

                    fobj.seek(header.data_offset + op.data_offset)
                    compressed = fobj.read(op.data_length)

                    if op.op_type == _OP_REPLACE:
                        raw = compressed
                    elif op.op_type == _OP_REPLACE_XZ:
                        raw = lzma.decompress(compressed)
                    else:  # _OP_REPLACE_BZ
                        raw = bz2.decompress(compressed)

                    # Write to correct block offset
                    if op.dst_extents:
                        for extent in op.dst_extents:
                            out.seek(extent.start_block * _BLOCK_SIZE)
                            out.write(raw[: extent.num_blocks * _BLOCK_SIZE])
                            raw = raw[extent.num_blocks * _BLOCK_SIZE :]
                    else:
                        out.write(raw)

                    written += op.data_length
                    if progress_cb:
                        progress_cb(written, total_size or written)

            logger.info("Extracted '%s' → %s", partition, out_path)
            return out_path

    def close(self) -> None:
        if self._zip_file:
            self._zip_file.close()

    def __enter__(self) -> PayloadDumper:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _open_payload(self):
        """Return an open binary file-like object positioned at start of payload."""
        if self._zip_file is not None:
            return self._zip_file.open("payload.bin")
        return self._source.open("rb")
