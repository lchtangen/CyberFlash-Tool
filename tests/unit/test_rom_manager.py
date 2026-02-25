"""Unit tests for RomManager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cyberflash.core.rom_manager import DownloadRecord, DownloadState, RomManager

# ── filename_for_url ──────────────────────────────────────────────────────────


class TestFilenameForUrl:
    def test_simple_path(self) -> None:
        assert RomManager.filename_for_url("https://example.com/files/boot.img") == "boot.img"

    def test_zip_file(self) -> None:
        assert (
            RomManager.filename_for_url("https://dl.example.org/releases/rom_v12.zip")
            == "rom_v12.zip"
        )

    def test_trailing_slash_fallback(self) -> None:
        name = RomManager.filename_for_url("https://example.com/")
        assert name == "rom.zip"

    def test_no_path_fallback(self) -> None:
        assert RomManager.filename_for_url("https://example.com") == "rom.zip"

    def test_url_encoded_spaces(self) -> None:
        name = RomManager.filename_for_url("https://example.com/my%20file.zip")
        assert name == "my file.zip"

    def test_deep_path(self) -> None:
        name = RomManager.filename_for_url("https://example.com/a/b/c/d/target.img")
        assert name == "target.img"


# ── dest_for_url ──────────────────────────────────────────────────────────────


class TestDestForUrl:
    def test_returns_path_inside_downloads_dir(self, tmp_path: Path) -> None:
        with patch.object(RomManager, "get_downloads_dir", return_value=tmp_path):
            dest = RomManager.dest_for_url("https://example.com/boot.img")
        assert dest == tmp_path / "boot.img"

    def test_filename_matches(self, tmp_path: Path) -> None:
        with patch.object(RomManager, "get_downloads_dir", return_value=tmp_path):
            dest = RomManager.dest_for_url("https://example.com/lineage.zip")
        assert dest.name == "lineage.zip"


# ── download history ──────────────────────────────────────────────────────────


class TestDownloadHistory:
    def _rom_manager(self, tmp_path: Path):
        """Patch downloads dir to tmp_path for isolation."""
        return patch.object(RomManager, "get_downloads_dir", return_value=tmp_path)

    def test_load_history_empty_when_no_file(self, tmp_path: Path) -> None:
        with self._rom_manager(tmp_path):
            assert RomManager.load_history() == []

    def test_record_and_load(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_bytes(b"x" * 1024)
        with self._rom_manager(tmp_path):
            RomManager.record_download("https://example.com/boot.img", img)
            history = RomManager.load_history()

        assert len(history) == 1
        assert history[0].url == "https://example.com/boot.img"
        assert history[0].filename == "boot.img"
        assert history[0].size_bytes == 1024
        assert history[0].state == DownloadState.COMPLETE

    def test_record_replaces_existing(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_bytes(b"v1")
        with self._rom_manager(tmp_path):
            RomManager.record_download("https://example.com/boot.img", img)
            img.write_bytes(b"v2" * 512)
            RomManager.record_download("https://example.com/boot.img", img)
            history = RomManager.load_history()

        assert len(history) == 1
        assert history[0].size_bytes == 1024  # v2

    def test_multiple_urls(self, tmp_path: Path) -> None:
        for name in ("boot.img", "system.img"):
            f = tmp_path / name
            f.write_bytes(b"data")
            with self._rom_manager(tmp_path):
                RomManager.record_download(f"https://example.com/{name}", f)

        with self._rom_manager(tmp_path):
            history = RomManager.load_history()
        assert len(history) == 2

    def test_get_record_returns_correct(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_bytes(b"data")
        with self._rom_manager(tmp_path):
            RomManager.record_download("https://example.com/boot.img", img, sha256="abc123")
            rec = RomManager.get_record("https://example.com/boot.img")

        assert rec is not None
        assert rec.sha256 == "abc123"

    def test_get_record_none_for_missing(self, tmp_path: Path) -> None:
        with self._rom_manager(tmp_path):
            rec = RomManager.get_record("https://example.com/missing.img")
        assert rec is None

    def test_is_downloaded_true_when_file_exists(self, tmp_path: Path) -> None:
        img = tmp_path / "boot.img"
        img.write_bytes(b"data")
        with self._rom_manager(tmp_path):
            RomManager.record_download("https://example.com/boot.img", img)
            assert RomManager.is_downloaded("https://example.com/boot.img") is True

    def test_is_downloaded_false_when_file_missing(self, tmp_path: Path) -> None:
        img = tmp_path / "ghost.img"
        # Don't create the file — record it anyway
        with self._rom_manager(tmp_path):
            RomManager.record_download("https://example.com/ghost.img", img)
            assert RomManager.is_downloaded("https://example.com/ghost.img") is False

    def test_is_downloaded_false_for_unknown_url(self, tmp_path: Path) -> None:
        with self._rom_manager(tmp_path):
            assert RomManager.is_downloaded("https://example.com/never.img") is False

    def test_corrupt_history_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "history.json").write_text("NOT JSON{{{")
        with self._rom_manager(tmp_path):
            assert RomManager.load_history() == []


# ── DownloadRecord dataclass ──────────────────────────────────────────────────


class TestDownloadRecord:
    def test_exists_true_when_file_present(self, tmp_path: Path) -> None:
        f = tmp_path / "file.img"
        f.write_bytes(b"data")
        rec = DownloadRecord(
            url="u", filename="file.img", local_path=str(f), state=str(DownloadState.COMPLETE)
        )
        assert rec.exists is True

    def test_exists_false_when_missing(self, tmp_path: Path) -> None:
        rec = DownloadRecord(
            url="u",
            filename="x.img",
            local_path=str(tmp_path / "missing.img"),
            state=str(DownloadState.COMPLETE),
        )
        assert rec.exists is False

    def test_is_complete_false_when_file_missing(self, tmp_path: Path) -> None:
        rec = DownloadRecord(
            url="u",
            filename="x.img",
            local_path=str(tmp_path / "missing.img"),
            state=str(DownloadState.COMPLETE),
        )
        assert rec.is_complete is False

    def test_is_complete_false_when_state_not_complete(self, tmp_path: Path) -> None:
        f = tmp_path / "file.img"
        f.write_bytes(b"data")
        rec = DownloadRecord(
            url="u", filename="file.img", local_path=str(f), state=str(DownloadState.FAILED)
        )
        assert rec.is_complete is False
