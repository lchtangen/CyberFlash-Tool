"""Unit tests for HashWorker."""

from __future__ import annotations

import hashlib
from pathlib import Path

from cyberflash.workers.hash_worker import HashWorker


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# ── hash_complete signal ──────────────────────────────────────────────────────


class TestHashComplete:
    def test_sha256_correct(self, tmp_path: Path, qapp) -> None:
        data = b"test data for hashing"
        f = tmp_path / "file.bin"
        f.write_bytes(data)
        results: list[tuple[str, str]] = []

        worker = HashWorker(f)
        worker.hash_complete.connect(lambda alg, dig: results.append((alg, dig)))
        worker.start()

        assert len(results) == 1
        assert results[0][0] == "sha256"
        assert results[0][1] == _sha256(data)

    def test_md5_algorithm(self, tmp_path: Path, qapp) -> None:
        data = b"md5 test"
        f = tmp_path / "file.bin"
        f.write_bytes(data)
        results: list[tuple[str, str]] = []

        worker = HashWorker(f, algorithm="md5")
        worker.hash_complete.connect(lambda alg, dig: results.append((alg, dig)))
        worker.start()

        assert results[0][0] == "md5"
        assert results[0][1] == _md5(data)

    def test_sha1_algorithm(self, tmp_path: Path, qapp) -> None:
        data = b"sha1 test"
        f = tmp_path / "file.bin"
        f.write_bytes(data)
        results: list[tuple[str, str]] = []

        worker = HashWorker(f, algorithm="sha1")
        worker.hash_complete.connect(lambda alg, dig: results.append((alg, dig)))
        worker.start()

        assert len(results) == 1
        assert results[0][0] == "sha1"

    def test_finished_always_emitted(self, tmp_path: Path, qapp) -> None:
        f = tmp_path / "file.bin"
        f.write_bytes(b"data")
        finished: list[bool] = []

        worker = HashWorker(f)
        worker.finished.connect(lambda: finished.append(True))
        worker.start()

        assert finished == [True]


# ── Verification ──────────────────────────────────────────────────────────────


class TestHashVerification:
    def test_verified_true(self, tmp_path: Path, qapp) -> None:
        data = b"verify me"
        f = tmp_path / "file.bin"
        f.write_bytes(data)
        verified: list[tuple[bool, str, str]] = []

        worker = HashWorker(f, expected_hash=_sha256(data))
        worker.verified.connect(lambda ok, exp, act: verified.append((ok, exp, act)))
        worker.start()

        assert len(verified) == 1
        assert verified[0][0] is True

    def test_verified_false_on_mismatch(self, tmp_path: Path, qapp) -> None:
        data = b"wrong hash test"
        f = tmp_path / "file.bin"
        f.write_bytes(data)
        verified: list[tuple[bool, str, str]] = []

        worker = HashWorker(f, expected_hash="0" * 64)
        worker.verified.connect(lambda ok, exp, act: verified.append((ok, exp, act)))
        worker.start()

        assert verified[0][0] is False

    def test_verified_not_emitted_without_expected(self, tmp_path: Path, qapp) -> None:
        f = tmp_path / "file.bin"
        f.write_bytes(b"data")
        verified: list = []

        worker = HashWorker(f)
        worker.verified.connect(verified.append)
        worker.start()

        assert verified == []


# ── Progress ──────────────────────────────────────────────────────────────────


class TestHashProgress:
    def test_progress_emitted(self, tmp_path: Path, qapp) -> None:
        f = tmp_path / "file.bin"
        f.write_bytes(b"x" * 10000)
        progress: list[tuple[int, int]] = []

        worker = HashWorker(f)
        worker.progress.connect(lambda d, t: progress.append((d, t)))
        worker.start()

        assert len(progress) >= 1
        assert progress[-1][0] == 10000
        assert progress[-1][1] == 10000


# ── Error cases ───────────────────────────────────────────────────────────────


class TestHashErrors:
    def test_file_not_found(self, tmp_path: Path, qapp) -> None:
        errors: list[str] = []
        worker = HashWorker(tmp_path / "missing.bin")
        worker.error.connect(errors.append)
        worker.start()

        assert len(errors) == 1
        assert "not found" in errors[0].lower()

    def test_unknown_algorithm(self, tmp_path: Path, qapp) -> None:
        f = tmp_path / "file.bin"
        f.write_bytes(b"data")
        errors: list[str] = []

        worker = HashWorker(f, algorithm="notarealhashalgorithm")
        worker.error.connect(errors.append)
        worker.start()

        assert len(errors) == 1
        assert "algorithm" in errors[0].lower() or "Unknown" in errors[0]
