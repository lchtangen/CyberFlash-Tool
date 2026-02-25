"""Unit tests for CrashService — dump write and hook install."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cyberflash.services.crash_service import CrashService


# Reset singleton between tests
@pytest.fixture(autouse=True)
def reset_singleton():
    import cyberflash.services.crash_service as mod
    original = mod._instance
    mod._instance = None
    yield
    mod._instance = original


class TestInstall:
    def test_install_sets_excepthook(self) -> None:
        original_hook = sys.excepthook
        service = CrashService()
        service.install()
        assert sys.excepthook is service._handle_exception
        # Restore
        sys.excepthook = original_hook

    def test_install_idempotent(self) -> None:
        service = CrashService()
        service.install()
        first_hook = sys.excepthook
        service.install()  # second call
        assert sys.excepthook is first_hook
        sys.excepthook = service._original_excepthook

    def test_instance_singleton(self) -> None:
        a = CrashService.instance()
        b = CrashService.instance()
        assert a is b


class TestDumpWrite:
    def test_write_dump_creates_file(self, tmp_path: Path) -> None:
        service = CrashService()
        with patch("cyberflash.services.crash_service._CRASH_DIR", tmp_path / "crashes"):
            path = service._write_dump(service._build_dump("Test crash content"))
        assert path is not None
        assert path.exists()
        assert "CyberFlash" in path.read_text()

    def test_get_crash_dumps_empty_dir(self, tmp_path: Path) -> None:
        service = CrashService()
        with patch("cyberflash.services.crash_service._CRASH_DIR", tmp_path / "crashes"):
            dumps = service.get_crash_dumps()
        assert dumps == []

    def test_get_crash_dumps_returns_list(self, tmp_path: Path) -> None:
        crash_dir = tmp_path / "crashes"
        crash_dir.mkdir()
        (crash_dir / "crash_20240115_120000.txt").write_text("crash1")
        (crash_dir / "crash_20240116_120000.txt").write_text("crash2")
        service = CrashService()
        with patch("cyberflash.services.crash_service._CRASH_DIR", crash_dir):
            dumps = service.get_crash_dumps()
        assert len(dumps) == 2

    def test_open_dump_returns_content(self, tmp_path: Path) -> None:
        p = tmp_path / "crash.txt"
        p.write_text("test content")
        service = CrashService()
        content = service.open_dump(p)
        assert content == "test content"

    def test_open_dump_missing_file(self, tmp_path: Path) -> None:
        service = CrashService()
        content = service.open_dump(tmp_path / "missing.txt")
        assert "Could not read" in content

    def test_build_dump_contains_version(self) -> None:
        service = CrashService()
        dump = service._build_dump("Traceback (most recent call last): ...")
        assert "CyberFlash" in dump
        assert "Traceback" in dump

    def test_keyboard_interrupt_not_handled(self) -> None:
        """KeyboardInterrupt should delegate to original hook."""
        original = sys.excepthook
        service = CrashService()
        service.install()
        called = []
        service._original_excepthook = lambda *a: called.append(a)
        service._handle_exception(KeyboardInterrupt, KeyboardInterrupt(), None)
        assert len(called) == 1
        sys.excepthook = original
