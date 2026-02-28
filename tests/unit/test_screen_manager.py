"""Unit tests for ScreenManager — mocked ADB and subprocess."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from cyberflash.core.screen_manager import CaptureResult, ScreenManager


class TestScreenshot:
    def test_screenshot_success(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch(
                "cyberflash.core.screen_manager.AdbManager._run",
                return_value=(0, "", ""),
            ),
            patch("cyberflash.core.screen_manager.AdbManager.pull", return_value=True),
            patch("cyberflash.core.screen_manager.AdbManager.shell", return_value=""),
        ):
            result = ScreenManager.screenshot("ABC", Path(tmpdir))
        assert isinstance(result, CaptureResult)
        assert result.success is True

    def test_screenshot_screencap_failure(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch(
                "cyberflash.core.screen_manager.AdbManager._run",
                return_value=(1, "", "permission denied"),
            ),
        ):
            result = ScreenManager.screenshot("ABC", Path(tmpdir))
        assert result.success is False
        assert "screencap failed" in result.error

    def test_screenshot_pull_failure(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch(
                "cyberflash.core.screen_manager.AdbManager._run",
                return_value=(0, "", ""),
            ),
            patch("cyberflash.core.screen_manager.AdbManager.pull", return_value=False),
            patch("cyberflash.core.screen_manager.AdbManager.shell", return_value=""),
        ):
            result = ScreenManager.screenshot("ABC", Path(tmpdir))
        assert result.success is False

    def test_screenshot_creates_parent_dir(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch("cyberflash.core.screen_manager.AdbManager._run", return_value=(0, "", "")),
            patch("cyberflash.core.screen_manager.AdbManager.pull", return_value=True),
            patch("cyberflash.core.screen_manager.AdbManager.shell", return_value=""),
        ):
            new_dir = Path(tmpdir) / "shots"
            ScreenManager.screenshot("ABC", new_dir)
            assert new_dir.exists()


class TestRecord:
    def test_record_failure_returns_error(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch(
                "cyberflash.core.screen_manager.AdbManager._run",
                return_value=(1, "", "screenrecord not found"),
            ),
        ):
            result = ScreenManager.record("ABC", Path(tmpdir), duration_s=5)
        assert result.success is False

    def test_record_success_returns_path(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch("cyberflash.core.screen_manager.AdbManager._run", return_value=(0, "", "")),
            patch("cyberflash.core.screen_manager.AdbManager.pull", return_value=True),
            patch("cyberflash.core.screen_manager.AdbManager.shell", return_value=""),
        ):
            result = ScreenManager.record("ABC", Path(tmpdir), duration_s=5)
        assert result.success is True
        assert result.local_path is not None


class TestCaptureResultDefaults:
    def test_failure_has_no_path(self) -> None:
        r = CaptureResult(success=False, error="something failed")
        assert r.local_path is None
        assert r.success is False

    def test_success_stores_path(self) -> None:
        p = Path("/tmp/shot.png")
        r = CaptureResult(success=True, local_path=p)
        assert r.local_path == p
