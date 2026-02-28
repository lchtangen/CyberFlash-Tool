"""Unit tests for BenchmarkRunner — mocked ADB."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cyberflash.core.benchmark_runner import BenchmarkResult, BenchmarkRunner


class TestRunStorageIO:
    def test_returns_benchmark_result(self) -> None:
        with patch("cyberflash.core.benchmark_runner.AdbManager.shell", return_value=""):
            result = BenchmarkRunner.run_storage_io("ABC")
        assert isinstance(result, BenchmarkResult)
        assert result.test_name == "storage_io"
        assert result.unit == "MB/s"

    def test_parses_dd_speed(self) -> None:
        dd_out = "8192+0 records in\n8192+0 records out\n33554432 bytes (34 MB) copied, 1.5 s, 22.4 MB/s"
        with patch("cyberflash.core.benchmark_runner.AdbManager.shell", return_value=dd_out):
            result = BenchmarkRunner.run_storage_io("ABC")
        assert result.score >= 0.0

    def test_device_serial_stored(self) -> None:
        with patch("cyberflash.core.benchmark_runner.AdbManager.shell", return_value=""):
            result = BenchmarkRunner.run_storage_io("SERIAL123")
        assert result.device_serial == "SERIAL123"


class TestRunCpu:
    def test_returns_benchmark_result(self) -> None:
        with patch("cyberflash.core.benchmark_runner.AdbManager.shell", return_value=""):
            result = BenchmarkRunner.run_cpu("ABC")
        assert isinstance(result, BenchmarkResult)
        assert result.test_name == "cpu"

    def test_score_is_positive(self) -> None:
        with patch("cyberflash.core.benchmark_runner.AdbManager.shell", return_value=""):
            result = BenchmarkRunner.run_cpu("ABC")
        assert result.score > 0.0


class TestRunMemory:
    def test_returns_benchmark_result(self) -> None:
        meminfo = "MemTotal:        6291456 kB\nMemFree:         1048576 kB\n"
        with patch("cyberflash.core.benchmark_runner.AdbManager.shell", return_value=meminfo):
            result = BenchmarkRunner.run_memory("ABC")
        assert isinstance(result, BenchmarkResult)
        assert result.test_name == "memory"

    def test_score_equals_mem_total_mb(self) -> None:
        meminfo = "MemTotal:        4194304 kB\n"
        with patch("cyberflash.core.benchmark_runner.AdbManager.shell", return_value=meminfo):
            result = BenchmarkRunner.run_memory("ABC")
        # 4194304 KB = 4096 MB
        assert result.score == 4096.0

    def test_empty_meminfo_score_zero(self) -> None:
        with patch("cyberflash.core.benchmark_runner.AdbManager.shell", return_value=""):
            result = BenchmarkRunner.run_memory("ABC")
        assert result.score == 0.0


class TestRunAll:
    def test_returns_three_results(self) -> None:
        meminfo = "MemTotal: 4194304 kB\n"
        with patch("cyberflash.core.benchmark_runner.AdbManager.shell", return_value=meminfo):
            results = BenchmarkRunner.run_all("ABC")
        assert len(results) == 3

    def test_all_results_are_benchmark_result(self) -> None:
        with patch("cyberflash.core.benchmark_runner.AdbManager.shell", return_value=""):
            results = BenchmarkRunner.run_all("ABC")
        for r in results:
            assert isinstance(r, BenchmarkResult)


class TestCompare:
    def test_positive_delta_when_b_better(self) -> None:
        a = [BenchmarkResult("storage_io", 50.0, "MB/s", 2.0, "ABC")]
        b = [BenchmarkResult("storage_io", 100.0, "MB/s", 1.0, "ABC")]
        delta = BenchmarkRunner.compare(a, b)
        assert delta["storage_io"] == 100.0

    def test_negative_delta_when_a_better(self) -> None:
        a = [BenchmarkResult("cpu", 80.0, "MB/s (sha256)", 2.0, "ABC")]
        b = [BenchmarkResult("cpu", 40.0, "MB/s (sha256)", 4.0, "ABC")]
        delta = BenchmarkRunner.compare(a, b)
        assert delta["cpu"] < 0

    def test_zero_delta_when_equal(self) -> None:
        a = [BenchmarkResult("memory", 4096.0, "MB total", 0.1, "ABC")]
        b = [BenchmarkResult("memory", 4096.0, "MB total", 0.1, "ABC")]
        delta = BenchmarkRunner.compare(a, b)
        assert delta["memory"] == 0.0
