"""heimdall_manager.py — Samsung Heimdall flash engine.

Wraps the ``heimdall`` CLI for flashing Samsung devices in Download Mode.
Supports Odin-compatible TAR packages, PIT partition table parsing, and
individual partition flashing (BL, AP, CP, CSC).

All methods are synchronous and must be called from worker threads.

Usage::

    pit = HeimdallManager.read_pit(serial)
    HeimdallManager.flash_package(serial, tar_path, dry_run=False)
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_HEIMDALL_BIN = "heimdall"

# Known partition names per Odin package section
_ODIN_SECTION_MAP: dict[str, list[str]] = {
    "BL":  ["BOOTLOADER", "BOOT", "LK", "SBOOT", "TZSW", "PARAM", "EFS"],
    "AP":  ["SYSTEM", "RECOVERY", "BOOT", "USERDATA", "CACHE", "HIDDEN", "RADIO"],
    "CP":  ["MODEM", "CPB", "RADIO"],
    "CSC": ["CSC", "SYSTEM", "HOME_CSC"],
    "PIT": ["PIT"],
}

# Samsung Download Mode detection via lsusb (Vendor ID 04e8)
_SAMSUNG_VENDOR_ID = "04e8"

# PIT partition flash order (must flash BL before AP)
_FLASH_ORDER = ["BL", "CP", "CSC", "AP"]


# ── Enums ─────────────────────────────────────────────────────────────────────


class SamsungPartition(StrEnum):
    BL  = "BL"
    AP  = "AP"
    CP  = "CP"
    CSC = "CSC"
    PIT = "PIT"


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class PitEntry:
    """Represents a single partition entry from a Samsung PIT file."""

    partition_id:   int
    partition_type: int
    filesystem_id:  int
    start_block:    int
    block_count:    int
    name:           str
    filename:       str

    @property
    def size_mb(self) -> float:
        """Estimated partition size in MB (512-byte blocks)."""
        return (self.block_count * 512) / (1024 * 1024)


@dataclass
class PitTable:
    """Parsed PIT partition table."""

    entries: list[PitEntry] = field(default_factory=list)
    pit_version: int = 0

    def find(self, name: str) -> PitEntry | None:
        for e in self.entries:
            if e.name.upper() == name.upper():
                return e
        return None


@dataclass
class HeimdallFlashResult:
    """Result of a heimdall flash operation."""

    success:   bool
    partition: str
    file_path: str
    stderr:    str = ""
    returncode: int = 0


# ── HeimdallManager ───────────────────────────────────────────────────────────


class HeimdallManager:
    """Wraps the heimdall CLI for Samsung Download Mode flashing.

    All methods are classmethods; no instance state required.
    """

    # ── Tool availability ─────────────────────────────────────────────────────

    @staticmethod
    def is_available() -> bool:
        """Return True if heimdall binary is on PATH."""
        return shutil.which(_HEIMDALL_BIN) is not None

    @classmethod
    def version(cls) -> str:
        """Return heimdall version string or '' if not found."""
        rc, out, _ = cls._run(["version"])
        return out.strip().splitlines()[0] if rc == 0 and out.strip() else ""

    # ── Device detection ──────────────────────────────────────────────────────

    @classmethod
    def detect_download_mode(cls) -> bool:
        """Return True if a Samsung device in Download Mode is connected.

        Uses ``heimdall detect`` which returns 0 if a device is found.
        """
        rc, _, stderr = cls._run(["detect"], timeout=5)
        if rc == 0:
            logger.info("Samsung device in Download Mode detected")
            return True
        logger.debug("heimdall detect: %s", stderr.strip())
        return False

    # ── PIT operations ────────────────────────────────────────────────────────

    @classmethod
    def read_pit(cls, output_path: str | Path | None = None) -> tuple[bool, Path | None]:
        """Download the PIT partition table from the connected device.

        Args:
            output_path: Where to save the PIT file.  If None, uses a temp dir.

        Returns:
            (success, pit_file_path)
        """
        if output_path is None:
            tmp = tempfile.mkdtemp(prefix="cf_pit_")
            pit_file = Path(tmp) / "device.pit"
        else:
            pit_file = Path(output_path)
            pit_file.parent.mkdir(parents=True, exist_ok=True)

        rc, _, stderr = cls._run(
            ["download-pit", "--output", str(pit_file)], timeout=30
        )
        if rc != 0:
            logger.error("Failed to download PIT: %s", stderr.strip())
            return False, None

        logger.info("PIT downloaded to %s (%d bytes)", pit_file, pit_file.stat().st_size)
        return True, pit_file

    @classmethod
    def parse_pit(cls, pit_path: str | Path) -> PitTable | None:
        """Parse a binary PIT file and return a PitTable.

        PIT binary format (Samsung):
          - Magic: 0x12349876 (4 bytes LE)
          - Entry count: 4 bytes LE
          - Unknown: 4 bytes
          - For each entry (136 bytes):
              - Partition ID: 4 bytes LE
              - Partition type: 4 bytes LE
              - Filesystem ID: 4 bytes LE
              - Start block: 4 bytes LE
              - Block count: 4 bytes LE
              - Unknown: 4 bytes LE
              - Unknown: 4 bytes LE
              - Partition name: 32 bytes (null-padded)
              - Filename: 32 bytes (null-padded)
              - FOTA name: 32 bytes (null-padded)

        Returns None if the file is not a valid PIT.
        """
        pit_path = Path(pit_path)
        if not pit_path.exists():
            logger.error("PIT file not found: %s", pit_path)
            return None

        data = pit_path.read_bytes()
        if len(data) < 8:
            logger.error("PIT file too small")
            return None

        import struct

        magic = struct.unpack_from("<I", data, 0)[0]
        if magic != 0x12349876:
            logger.warning("PIT magic mismatch (got 0x%08x) — trying anyway", magic)

        try:
            entry_count = struct.unpack_from("<I", data, 4)[0]
            pit_version = struct.unpack_from("<I", data, 8)[0]
        except struct.error:
            logger.error("PIT header parse error")
            return None

        # Cap to avoid runaway parsing on corrupt files
        max_entries = min(entry_count, 128)
        entries: list[PitEntry] = []
        offset = 12

        for _ in range(max_entries):
            if offset + 136 > len(data):
                break
            try:
                pid, ptype, fsid, start, count, _, _ = struct.unpack_from("<7I", data, offset)
                name = data[offset + 28: offset + 60].split(b"\x00", 1)[0].decode("ascii", errors="replace")
                fname = data[offset + 60: offset + 92].split(b"\x00", 1)[0].decode("ascii", errors="replace")
                entries.append(PitEntry(
                    partition_id=pid,
                    partition_type=ptype,
                    filesystem_id=fsid,
                    start_block=start,
                    block_count=count,
                    name=name,
                    filename=fname,
                ))
            except Exception as exc:
                logger.warning("PIT entry parse error at offset %d: %s", offset, exc)
            offset += 136

        logger.info("Parsed PIT: %d entries (version %d)", len(entries), pit_version)
        return PitTable(entries=entries, pit_version=pit_version)

    # ── Package inspection ────────────────────────────────────────────────────

    @classmethod
    def inspect_odin_package(cls, tar_path: str | Path) -> dict[str, list[str]]:
        """Return a dict mapping Odin section → list of filenames in a TAR.

        Args:
            tar_path: Path to an Odin .tar or .tar.md5 package.

        Returns:
            e.g. ``{"AP": ["system.img.lz4", "boot.img.lz4"], "BL": [...]}``
        """
        tar_path = Path(tar_path)
        if not tar_path.exists():
            logger.error("TAR not found: %s", tar_path)
            return {}

        result: dict[str, list[str]] = {}
        try:
            with tarfile.open(str(tar_path), "r:*") as tf:
                names = [m.name for m in tf.getmembers() if not m.isdir()]
        except (tarfile.TarError, OSError) as exc:
            logger.error("Cannot inspect TAR %s: %s", tar_path.name, exc)
            return {}

        for name in names:
            base = Path(name).stem.upper()  # e.g. "BOOT" from "boot.img.lz4"
            placed = False
            for section, keywords in _ODIN_SECTION_MAP.items():
                if any(kw in base for kw in keywords):
                    result.setdefault(section, []).append(name)
                    placed = True
                    break
            if not placed:
                result.setdefault("UNKNOWN", []).append(name)

        return result

    # ── Flashing ──────────────────────────────────────────────────────────────

    @classmethod
    def flash_partition(
        cls,
        partition_name: str,
        file_path: str | Path,
        dry_run: bool = False,
    ) -> HeimdallFlashResult:
        """Flash a single partition using heimdall.

        Args:
            partition_name: PIT partition name (e.g. ``"BOOT"``, ``"SYSTEM"``).
            file_path: Local file to flash.
            dry_run: Log what would happen without executing.

        Returns:
            HeimdallFlashResult
        """
        file_path = Path(file_path)
        if not file_path.exists():
            msg = f"File not found: {file_path}"
            logger.error(msg)
            return HeimdallFlashResult(
                success=False, partition=partition_name,
                file_path=str(file_path), stderr=msg
            )

        if dry_run:
            logger.info(
                "[dry-run] heimdall flash --%s %s",
                partition_name.upper(), file_path.name
            )
            return HeimdallFlashResult(
                success=True, partition=partition_name,
                file_path=str(file_path)
            )

        logger.info("Flashing %s ← %s", partition_name.upper(), file_path.name)
        rc, _, stderr = cls._run(
            ["flash", f"--{partition_name.upper()}", str(file_path)],
            timeout=300,
        )
        ok = rc == 0
        if not ok:
            logger.error("heimdall flash %s failed: %s", partition_name, stderr.strip())
        return HeimdallFlashResult(
            success=ok,
            partition=partition_name,
            file_path=str(file_path),
            stderr=stderr,
            returncode=rc,
        )

    @classmethod
    def flash_package(
        cls,
        tar_path: str | Path,
        sections: list[str] | None = None,
        dry_run: bool = False,
    ) -> list[HeimdallFlashResult]:
        """Flash an Odin TAR package, extracting and flashing each section.

        Automatically respects the correct flash order (BL → CP → CSC → AP).

        Args:
            tar_path: Path to ``.tar`` or ``.tar.md5`` Odin package.
            sections: Subset of sections to flash (e.g. ``["AP"]``).
                      Defaults to all sections found in the package.
            dry_run: Simulate without executing heimdall.

        Returns:
            List of HeimdallFlashResult, one per partition flashed.
        """
        tar_path = Path(tar_path)
        if not tar_path.exists():
            logger.error("TAR package not found: %s", tar_path)
            return []

        contents = cls.inspect_odin_package(tar_path)
        if not contents:
            return []

        # Filter to requested sections only
        to_flash = {
            s: files for s, files in contents.items()
            if sections is None or s in sections
        }

        results: list[HeimdallFlashResult] = []

        with tempfile.TemporaryDirectory(prefix="cf_odin_") as tmpdir:
            # Extract TAR
            try:
                with tarfile.open(str(tar_path), "r:*") as tf:
                    tf.extractall(tmpdir)
            except (tarfile.TarError, OSError) as exc:
                logger.error("TAR extraction failed: %s", exc)
                return []

            # Flash in correct order
            for section in _FLASH_ORDER:
                if section not in to_flash:
                    continue
                for fname in to_flash[section]:
                    local = Path(tmpdir) / Path(fname).name
                    if not local.exists():
                        logger.warning("Expected file not found after extraction: %s", fname)
                        continue
                    # Determine PIT partition name from filename
                    part = Path(fname).stem.split(".")[0].upper()
                    result = cls.flash_partition(part, local, dry_run=dry_run)
                    results.append(result)
                    if not result.success and not dry_run:
                        logger.error("Aborting package flash after error on %s", part)
                        return results

        return results

    @classmethod
    def repartition(
        cls,
        pit_path: str | Path,
        dry_run: bool = False,
    ) -> bool:
        """Re-partition the device using a PIT file.

        WARNING: Destructive operation — erases all device partitions.

        Args:
            pit_path: Path to the new PIT file to apply.
            dry_run: Log without executing.

        Returns:
            True on success.
        """
        pit_path = Path(pit_path)
        if not pit_path.exists():
            logger.error("PIT file not found: %s", pit_path)
            return False

        if dry_run:
            logger.info("[dry-run] heimdall flash --repartition --pit %s", pit_path.name)
            return True

        logger.warning("Re-partitioning device with PIT: %s", pit_path.name)
        rc, _, stderr = cls._run(
            ["flash", "--repartition", "--pit", str(pit_path)],
            timeout=120,
        )
        ok = rc == 0
        if not ok:
            logger.error("Re-partition failed: %s", stderr.strip())
        return ok

    # ── Internal ──────────────────────────────────────────────────────────────

    @classmethod
    def _run(
        cls,
        args: list[str],
        timeout: int = 30,
    ) -> tuple[int, str, str]:
        cmd = [_HEIMDALL_BIN, *args]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            return r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            logger.warning("heimdall timeout: %s", " ".join(args))
            return -1, "", "timeout"
        except FileNotFoundError:
            logger.error("heimdall binary not found — install heimdall-flash")
            return -1, "", "heimdall not found"
        except Exception as exc:
            logger.error("heimdall error: %s", exc)
            return -1, "", str(exc)
