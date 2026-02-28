"""storage_analyzer.py — Android storage health analysis (Phase 10).

Checks f2fs/ext4 filesystem health, bad-block status, TRIM state, and
fragmentation metrics.  All methods are pure functions accepting a ``serial``
string and an optional ``log_cb``; they return ``bool`` on failure, never raise.

Usage::

    result = StorageAnalyzer.analyze(serial, log_cb=print)
    if result:
        print(result.summary())
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class FilesystemInfo:
    """Metadata about a single mounted filesystem."""

    mount_point: str = "/"
    fs_type: str = "unknown"
    total_kb: int = 0
    used_kb: int = 0
    available_kb: int = 0
    use_percent: int = 0

    @property
    def free_ratio(self) -> float:
        if self.total_kb <= 0:
            return 0.0
        return max(0.0, self.available_kb / self.total_kb)


@dataclass
class TrimStatus:
    """TRIM / fstrim readiness."""

    supported: bool = False
    last_fstrim_output: str = ""
    untrimmed_kb: int = 0  # estimate from f2fs GC stats


@dataclass
class StorageReport:
    """Aggregated storage health analysis result."""

    serial: str = ""
    filesystems: list[FilesystemInfo] = field(default_factory=list)
    trim: TrimStatus = field(default_factory=TrimStatus)
    emmc_life_estimate: str = ""  # from /sys/block/mmcblk0/device/life_time_est
    bad_block_count: int = -1     # -1 = unknown
    f2fs_gc_status: str = ""
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Return a human-readable one-paragraph summary."""
        lines: list[str] = [f"Storage report for {self.serial}"]
        for fs in self.filesystems:
            lines.append(
                f"  {fs.mount_point}: {fs.fs_type} "
                f"{fs.used_kb // 1024} MB / {fs.total_kb // 1024} MB "
                f"({fs.use_percent}% used)"
            )
        if self.trim.supported:
            lines.append(f"  TRIM: supported, untrimmed ~{self.trim.untrimmed_kb} KB")
        if self.emmc_life_estimate:
            lines.append(f"  eMMC life estimate: {self.emmc_life_estimate}")
        if self.bad_block_count >= 0:
            lines.append(f"  Bad blocks: {self.bad_block_count}")
        if self.errors:
            lines.append(f"  Errors: {'; '.join(self.errors)}")
        return "\n".join(lines)

    @property
    def health_ok(self) -> bool:
        """Quick health gate: no errors and no bad blocks."""
        return not self.errors and self.bad_block_count <= 0


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class StorageAnalyzer:
    """Static helper class for Android storage health analysis.

    All public methods:
    - Accept ``serial`` + optional ``log_cb`` + optional ``dry_run``.
    - Return the result object or ``False`` on failure.
    - Never raise exceptions.
    """

    @classmethod
    def analyze(
        cls,
        serial: str,
        log_cb: object = None,
        dry_run: bool = False,
    ) -> StorageReport | bool:
        """Run a full storage analysis and return a :class:`StorageReport`."""
        log = log_cb or (lambda m: logger.debug(m))
        log(f"[StorageAnalyzer] starting analysis for {serial}")
        report = StorageReport(serial=serial)

        if dry_run:
            log("[StorageAnalyzer] dry-run — returning empty report")
            return report

        try:
            report.filesystems = cls._list_filesystems(serial, log)
            report.trim = cls._check_trim(serial, log)
            report.emmc_life_estimate = cls._read_emmc_life(serial, log)
            report.bad_block_count = cls._count_bad_blocks(serial, log)
            report.f2fs_gc_status = cls._read_f2fs_gc(serial, log)
        except Exception as exc:
            msg = f"analyze error: {exc}"
            logger.warning(msg)
            report.errors.append(msg)
            return False
        log("[StorageAnalyzer] analysis complete")
        return report

    @classmethod
    def run_fstrim(
        cls,
        serial: str,
        mount_point: str = "/data",
        log_cb: object = None,
        dry_run: bool = False,
    ) -> bool:
        """Run ``fstrim`` on *mount_point* (requires root)."""
        log = log_cb or (lambda m: logger.debug(m))
        log(f"[StorageAnalyzer] fstrim {mount_point} on {serial}")
        if dry_run:
            log("[StorageAnalyzer] dry-run — skipping fstrim")
            return True
        try:
            from cyberflash.core.adb_manager import AdbManager

            out = AdbManager.shell(serial, f"fstrim -v {mount_point}") or ""
            log(f"[StorageAnalyzer] fstrim output: {out[:200]}")
            return True
        except Exception as exc:
            logger.warning("fstrim failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _list_filesystems(serial: str, log: object) -> list[FilesystemInfo]:
        from cyberflash.core.adb_manager import AdbManager

        raw = AdbManager.shell(serial, "df -k") or ""
        result: list[FilesystemInfo] = []
        for line in raw.splitlines():
            parts = line.split()
            # Expected: filesystem  size  used  available  use%  mount
            if len(parts) < 6:
                continue
            try:
                fs = FilesystemInfo(
                    mount_point=parts[5],
                    fs_type="unknown",
                    total_kb=int(parts[1]),
                    used_kb=int(parts[2]),
                    available_kb=int(parts[3]),
                    use_percent=int(parts[4].rstrip("%")),
                )
                result.append(fs)
            except (ValueError, IndexError):
                pass
        # Enrich with fs type from /proc/mounts
        mounts_raw = AdbManager.shell(serial, "cat /proc/mounts") or ""
        for line in mounts_raw.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            for fs in result:
                if fs.mount_point == parts[1]:
                    fs.fs_type = parts[2]
                    break
        return result

    @staticmethod
    def _check_trim(serial: str, log: object) -> TrimStatus:
        from cyberflash.core.adb_manager import AdbManager

        status = TrimStatus()
        # Check if fstrim binary exists
        which = AdbManager.shell(serial, "which fstrim") or ""
        status.supported = bool(which.strip())
        if not status.supported:
            return status
        # Try to read f2fs GC status
        gc_raw = AdbManager.shell(
            serial, "cat /sys/fs/f2fs/*/dirty_segments 2>/dev/null"
        ) or ""
        try:
            total_dirty = sum(
                int(v) for v in gc_raw.split() if v.isdigit()
            )
            status.untrimmed_kb = total_dirty * 2048  # ≈2 MiB per segment
        except ValueError:
            pass
        return status

    @staticmethod
    def _read_emmc_life(serial: str, log: object) -> str:
        from cyberflash.core.adb_manager import AdbManager

        for path in (
            "/sys/block/mmcblk0/device/life_time_est_typ_a",
            "/sys/block/mmcblk0/device/life_time_est_typ_b",
        ):
            val = AdbManager.shell(serial, f"cat {path} 2>/dev/null") or ""
            val = val.strip()
            if val:
                return val
        return ""

    @staticmethod
    def _count_bad_blocks(serial: str, log: object) -> int:
        from cyberflash.core.adb_manager import AdbManager

        # Read from sysfs if available
        raw = AdbManager.shell(
            serial, "cat /sys/block/mmcblk0/device/erase_group_def 2>/dev/null"
        ) or ""
        # Most devices won't expose this — return -1 (unknown)
        if raw.strip().isdigit():
            return int(raw.strip())
        return -1

    @staticmethod
    def _read_f2fs_gc(serial: str, log: object) -> str:
        from cyberflash.core.adb_manager import AdbManager

        raw = AdbManager.shell(
            serial, "cat /sys/fs/f2fs/*/gc_stat 2>/dev/null"
        ) or ""
        return raw[:500].strip()
