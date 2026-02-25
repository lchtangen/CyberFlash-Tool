"""benchmark_runner.py — Android device performance benchmarks via ADB.

Runs storage I/O, CPU, and memory benchmarks using standard shell
commands (dd, sha256sum) that are available on all Android devices.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime

from cyberflash.core.adb_manager import AdbManager

logger = logging.getLogger(__name__)

_BENCH_TMP = "/data/local/tmp/cyberflash_bench"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class BenchmarkResult:
    """Result of a single benchmark test."""

    test_name: str
    score: float
    unit: str
    duration_s: float
    device_serial: str
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"


# ── Main class ────────────────────────────────────────────────────────────────


class BenchmarkRunner:
    """Classmethod-only Android benchmark runner."""

    @classmethod
    def run_storage_io(cls, serial: str) -> BenchmarkResult:
        """Benchmark sequential write + read speed via dd.

        Returns throughput in MB/s.
        """
        write_file = f"{_BENCH_TMP}_write.tmp"

        # Write 32MB of zeros
        t0 = time.monotonic()
        write_out = AdbManager.shell(
            serial,
            f"dd if=/dev/zero of={write_file} bs=4096 count=8192 2>&1 && sync",
            timeout=60,
        )
        write_elapsed = max(0.001, time.monotonic() - t0)

        write_mb_s = cls._parse_dd_speed(write_out)
        if write_mb_s <= 0:
            write_mb_s = (8192 * 4096 / 1_048_576) / write_elapsed

        # Read back
        t0 = time.monotonic()
        read_out = AdbManager.shell(
            serial,
            f"dd if={write_file} of=/dev/null bs=4096 2>&1",
            timeout=60,
        )
        read_elapsed = max(0.001, time.monotonic() - t0)

        read_mb_s = cls._parse_dd_speed(read_out)
        if read_mb_s <= 0:
            read_mb_s = (8192 * 4096 / 1_048_576) / read_elapsed

        # Cleanup
        AdbManager.shell(serial, f"rm -f {write_file}", timeout=5)

        # Report average
        avg = (write_mb_s + read_mb_s) / 2
        return BenchmarkResult(
            test_name="storage_io",
            score=round(avg, 2),
            unit="MB/s",
            duration_s=round(write_elapsed + read_elapsed, 2),
            device_serial=serial,
        )

    @classmethod
    def _parse_dd_speed(cls, output: str) -> float:
        """Extract MB/s from dd stderr output."""
        # Pattern: "X bytes (X MB) copied, X s, X MB/s"
        m = re.search(r"([\d.]+)\s*(MB|GB|KB)/s", output, re.IGNORECASE)
        if not m:
            return 0.0
        val = float(m.group(1))
        unit = m.group(2).upper()
        if unit == "GB":
            val *= 1024
        elif unit == "KB":
            val /= 1024
        return val

    @classmethod
    def run_cpu(cls, serial: str) -> BenchmarkResult:
        """CPU benchmark: time a sha256sum loop over /dev/urandom data."""
        t0 = time.monotonic()
        AdbManager.shell(
            serial,
            "dd if=/dev/urandom bs=1M count=16 2>/dev/null | sha256sum",
            timeout=60,
        )
        elapsed = max(0.001, time.monotonic() - t0)

        # Score: MB processed per second
        score = 16.0 / elapsed
        return BenchmarkResult(
            test_name="cpu",
            score=round(score, 2),
            unit="MB/s (sha256)",
            duration_s=round(elapsed, 2),
            device_serial=serial,
        )

    @classmethod
    def run_memory(cls, serial: str) -> BenchmarkResult:
        """Memory benchmark: parse /proc/meminfo for available RAM score."""
        t0 = time.monotonic()
        output = AdbManager.shell(serial, "cat /proc/meminfo", timeout=10)
        elapsed = time.monotonic() - t0

        mem_total = 0
        for line in output.splitlines():
            m = re.match(r"MemTotal:\s+(\d+)", line)
            if m:
                mem_total = int(m.group(1))

        # Score = total RAM in MB (more RAM = higher score ceiling)
        score = mem_total / 1024 if mem_total else 0.0
        return BenchmarkResult(
            test_name="memory",
            score=round(score, 1),
            unit="MB total",
            duration_s=round(elapsed, 3),
            device_serial=serial,
            timestamp=datetime.utcnow().isoformat() + "Z",
        )

    @classmethod
    def run_all(cls, serial: str) -> list[BenchmarkResult]:
        """Run all benchmarks sequentially and return results."""
        results: list[BenchmarkResult] = []
        for runner in (cls.run_storage_io, cls.run_cpu, cls.run_memory):
            try:
                results.append(runner(serial))
            except Exception as exc:
                logger.warning("benchmark failed (%s): %s", runner.__name__, exc)
        return results

    @classmethod
    def compare(
        cls,
        results_a: list[BenchmarkResult],
        results_b: list[BenchmarkResult],
    ) -> dict[str, float]:
        """Return delta percentages between two result sets.

        Positive = B is better; negative = A is better.
        """
        map_a = {r.test_name: r.score for r in results_a}
        map_b = {r.test_name: r.score for r in results_b}
        delta: dict[str, float] = {}
        for name in set(map_a) | set(map_b):
            score_a = map_a.get(name, 0.0)
            score_b = map_b.get(name, 0.0)
            if score_a > 0:
                delta[name] = round((score_b - score_a) / score_a * 100, 1)
            else:
                delta[name] = 0.0
        return delta
