"""Unit tests for UpdateService — mocked GitHub API."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from cyberflash.services.update_service import UpdateInfo, UpdateService


# Reset singleton between tests
@pytest.fixture(autouse=True)
def reset_singleton():
    import cyberflash.services.update_service as mod
    original = mod._instance
    mod._instance = None
    yield
    mod._instance = original


def _mock_urlopen(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = json.dumps(data).encode()
    resp.headers = {"Content-Length": str(len(json.dumps(data)))}
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestGetCurrentVersion:
    def test_returns_string(self) -> None:
        svc = UpdateService()
        ver = svc.get_current_version()
        assert isinstance(ver, str)
        assert len(ver) > 0


class TestIsNewer:
    def test_newer_patch(self) -> None:
        assert UpdateService._is_newer("1.0.1", "1.0.0") is True

    def test_newer_minor(self) -> None:
        assert UpdateService._is_newer("1.1.0", "1.0.9") is True

    def test_same_version(self) -> None:
        assert UpdateService._is_newer("1.0.0", "1.0.0") is False

    def test_older(self) -> None:
        assert UpdateService._is_newer("0.9.0", "1.0.0") is False

    def test_with_v_prefix(self) -> None:
        assert UpdateService._is_newer("2.0.0", "1.9.9") is True


class TestCheckUpdate:
    def test_newer_version_returns_update_info(self) -> None:
        data = {
            "tag_name": "v99.0.0",
            "body": "Bug fixes",
            "assets": [],
            "published_at": "2024-01-15T00:00:00Z",
        }
        svc = UpdateService()
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen(data)
            result = svc.check_update(force=True)
        assert result is not None
        assert result.tag == "v99.0.0"

    def test_same_version_returns_none(self) -> None:
        from cyberflash import __version__
        data = {
            "tag_name": f"v{__version__}",
            "body": "",
            "assets": [],
        }
        svc = UpdateService()
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen(data)
            result = svc.check_update(force=True)
        assert result is None

    def test_network_error_returns_none(self) -> None:
        import urllib.error
        svc = UpdateService()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
            result = svc.check_update(force=True)
        assert result is None

    def test_cache_prevents_double_check(self) -> None:
        data = {"tag_name": "v99.0.0", "body": "", "assets": []}
        svc = UpdateService()
        svc._last_check = 1e15  # far future — suppress check
        result = svc.check_update(force=False)
        assert result is None

    def test_force_bypasses_cache(self) -> None:
        data = {"tag_name": "v99.0.0", "body": "", "assets": []}
        svc = UpdateService()
        svc._last_check = 1e15
        with patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen(data)
            result = svc.check_update(force=True)
        assert result is not None


class TestUpdateInfo:
    def test_version_strips_v(self) -> None:
        info = UpdateInfo(tag="v2.1.0", body="", assets=[])
        assert info.version == "2.1.0"

    def test_version_no_v(self) -> None:
        info = UpdateInfo(tag="2.1.0", body="", assets=[])
        assert info.version == "2.1.0"
