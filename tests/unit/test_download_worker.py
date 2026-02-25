"""Unit tests for DownloadWorker.

All network I/O is mocked — no real HTTP requests are made.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from cyberflash.workers.download_worker import DownloadWorker


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_response(body: bytes, status: int = 200, content_length: bool = True):
    """Build a minimal mock urllib response."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.headers = {}
    if content_length:
        mock_resp.headers["Content-Length"] = str(len(body))
    data = [body]  # read once

    def read(n):
        if data:
            chunk = data.pop(0)[:n]
            return chunk
        return b""

    mock_resp.read.side_effect = read
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ── Basic download ────────────────────────────────────────────────────────────


class TestDownloadWorkerBasic:
    def test_download_complete_emitted(self, tmp_path: Path, qapp) -> None:
        body = b"file content" * 100
        dest = tmp_path / "file.bin"
        completed: list[str] = []

        mock_resp = _make_response(body)
        with patch("cyberflash.workers.download_worker.urllib.request.urlopen", return_value=mock_resp):
            worker = DownloadWorker("http://example.com/file.bin", dest)
            worker.download_complete.connect(completed.append)
            worker.start()

        assert len(completed) == 1
        assert completed[0] == str(dest)
        assert dest.exists()

    def test_progress_emitted(self, tmp_path: Path, qapp) -> None:
        body = b"x" * 1024
        dest = tmp_path / "file.bin"
        progress: list[tuple[int, int]] = []

        mock_resp = _make_response(body)
        with patch("cyberflash.workers.download_worker.urllib.request.urlopen", return_value=mock_resp):
            worker = DownloadWorker("http://example.com/file.bin", dest)
            worker.progress.connect(lambda d, t: progress.append((d, t)))
            worker.start()

        assert len(progress) >= 1
        assert progress[-1][0] > 0

    def test_finished_always_emitted(self, tmp_path: Path, qapp) -> None:
        dest = tmp_path / "file.bin"
        finished: list[bool] = []

        mock_resp = _make_response(b"data")
        with patch("cyberflash.workers.download_worker.urllib.request.urlopen", return_value=mock_resp):
            worker = DownloadWorker("http://example.com/file.bin", dest)
            worker.finished.connect(lambda: finished.append(True))
            worker.start()

        assert finished == [True]

    def test_error_on_http_failure(self, tmp_path: Path, qapp) -> None:
        import urllib.error

        dest = tmp_path / "file.bin"
        errors: list[str] = []

        with patch(
            "cyberflash.workers.download_worker.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError("url", 404, "Not Found", {}, None),
        ):
            worker = DownloadWorker("http://example.com/file.bin", dest)
            worker.error.connect(errors.append)
            worker.start()

        assert len(errors) == 1

    def test_parent_dirs_created(self, tmp_path: Path, qapp) -> None:
        dest = tmp_path / "deep" / "nested" / "file.bin"
        mock_resp = _make_response(b"data")
        with patch("cyberflash.workers.download_worker.urllib.request.urlopen", return_value=mock_resp):
            worker = DownloadWorker("http://example.com/file.bin", dest)
            worker.start()
        assert dest.parent.exists()


# ── Checksum verification ─────────────────────────────────────────────────────


class TestDownloadWorkerVerification:
    def test_verified_true_on_correct_hash(self, tmp_path: Path, qapp) -> None:
        body = b"correct data"
        dest = tmp_path / "file.bin"
        verified: list[tuple[bool, str, str]] = []

        mock_resp = _make_response(body)
        with patch("cyberflash.workers.download_worker.urllib.request.urlopen", return_value=mock_resp):
            worker = DownloadWorker(
                "http://example.com/file.bin", dest, expected_hash=_sha256(body)
            )
            worker.verified.connect(lambda ok, exp, act: verified.append((ok, exp, act)))
            worker.start()

        assert len(verified) == 1
        assert verified[0][0] is True

    def test_verified_false_on_wrong_hash(self, tmp_path: Path, qapp) -> None:
        body = b"wrong data"
        dest = tmp_path / "file.bin"
        verified: list[tuple[bool, str, str]] = []

        mock_resp = _make_response(body)
        with patch("cyberflash.workers.download_worker.urllib.request.urlopen", return_value=mock_resp):
            worker = DownloadWorker(
                "http://example.com/file.bin", dest, expected_hash="deadbeef" * 8
            )
            worker.verified.connect(lambda ok, exp, act: verified.append((ok, exp, act)))
            worker.start()

        assert len(verified) == 1
        assert verified[0][0] is False

    def test_verified_not_emitted_without_expected_hash(self, tmp_path: Path, qapp) -> None:
        dest = tmp_path / "file.bin"
        verified: list = []

        mock_resp = _make_response(b"data")
        with patch("cyberflash.workers.download_worker.urllib.request.urlopen", return_value=mock_resp):
            worker = DownloadWorker("http://example.com/file.bin", dest)
            worker.verified.connect(verified.append)
            worker.start()

        assert verified == []


# ── Abort ─────────────────────────────────────────────────────────────────────


class TestDownloadWorkerAbort:
    def test_abort_sets_flag(self, tmp_path: Path) -> None:
        worker = DownloadWorker("http://example.com/f", tmp_path / "f")
        assert not worker._aborted
        worker.abort()
        assert worker._aborted
