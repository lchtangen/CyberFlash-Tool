"""Tests for file_utils module."""

from __future__ import annotations

from pathlib import Path

from cyberflash.utils.file_utils import ensure_dir, sha256_file


def test_sha256_file(tmp_path: Path) -> None:
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"hello world")
    digest = sha256_file(test_file)
    assert len(digest) == 64
    # Known SHA-256 of b"hello world"
    assert digest == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_sha256_empty_file(tmp_path: Path) -> None:
    test_file = tmp_path / "empty.bin"
    test_file.write_bytes(b"")
    digest = sha256_file(test_file)
    # Known SHA-256 of empty bytes
    assert digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_ensure_dir_creates_nested(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c"
    result = ensure_dir(nested)
    assert result == nested
    assert nested.is_dir()


def test_ensure_dir_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    result = ensure_dir(target)
    assert result == target
    assert target.is_dir()
