"""Tests for the LinkChecker core module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from cyberflash.core.link_checker import LinkChecker
from cyberflash.models.rom_source import LinkHealth


class TestLinkCheckerClassify:
    """Test the static classification methods without network I/O."""

    def test_classify_200(self) -> None:
        assert LinkChecker._classify_status(200) == LinkHealth.OK

    def test_classify_301(self) -> None:
        assert LinkChecker._classify_status(301) == LinkHealth.REDIRECT

    def test_classify_404(self) -> None:
        assert LinkChecker._classify_status(404) == LinkHealth.NOT_FOUND

    def test_classify_403(self) -> None:
        assert LinkChecker._classify_status(403) == LinkHealth.BLOCKED

    def test_classify_500(self) -> None:
        assert LinkChecker._classify_status(500) == LinkHealth.SERVER_ERROR

    def test_classify_418(self) -> None:
        assert LinkChecker._classify_status(418) == LinkHealth.UNREACHABLE


class TestLinkCheckerCheck:
    def setup_method(self) -> None:
        self.checker = LinkChecker(timeout_s=5)

    def test_unsupported_scheme(self) -> None:
        result = self.checker.check("ftp://example.com/rom.zip")
        assert result.health == LinkHealth.UNREACHABLE
        assert "Unsupported scheme" in result.error_message

    @patch("cyberflash.core.link_checker.urlopen")
    def test_successful_head(self, mock_urlopen: MagicMock) -> None:
        resp = MagicMock()
        resp.status = 200
        resp.url = "https://example.com/rom.zip"
        resp.headers = {"Content-Type": "application/zip", "Content-Length": "1048576"}
        mock_urlopen.return_value = resp

        result = self.checker.check("https://example.com/rom.zip")
        assert result.health == LinkHealth.OK
        assert result.status_code == 200
        assert result.content_type == "application/zip"
        assert result.content_length == 1048576

    @patch("cyberflash.core.link_checker.urlopen")
    def test_http_404(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = HTTPError(
            url="https://example.com/rom.zip",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )

        result = self.checker.check("https://example.com/rom.zip")
        assert result.health == LinkHealth.NOT_FOUND
        assert result.status_code == 404

    @patch("cyberflash.core.link_checker.urlopen")
    def test_timeout(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = URLError(reason=TimeoutError("timed out"))

        result = self.checker.check("https://example.com/rom.zip")
        assert result.health == LinkHealth.TIMEOUT

    @patch("cyberflash.core.link_checker.urlopen")
    def test_dns_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = URLError(reason=OSError("Name or service not known"))

        result = self.checker.check("https://nonexistent.example.com/rom.zip")
        assert result.health == LinkHealth.DNS_ERROR

    @patch("cyberflash.core.link_checker.urlopen")
    def test_ssl_error(self, mock_urlopen: MagicMock) -> None:
        import ssl

        mock_urlopen.side_effect = URLError(reason=ssl.SSLError("certificate verify failed"))

        result = self.checker.check("https://expired-ssl.example.com/rom.zip")
        assert result.health == LinkHealth.SSL_ERROR
        assert result.ssl_valid is False

    @patch("cyberflash.core.link_checker.urlopen")
    def test_slow_response(self, mock_urlopen: MagicMock) -> None:
        """Responses above the slow threshold are marked SLOW."""
        resp = MagicMock()
        resp.status = 200
        resp.url = "https://example.com/rom.zip"
        resp.headers = {"Content-Type": "application/zip", "Content-Length": "0"}

        # Simulate slow response by patching time.monotonic

        call_count = [0]

        def slow_monotonic() -> float:
            call_count[0] += 1
            # Return 6 seconds apart for start/end
            if call_count[0] % 2 == 1:
                return 0.0
            return 6.0

        mock_urlopen.return_value = resp

        with patch("cyberflash.core.link_checker.time.monotonic", side_effect=slow_monotonic):
            # Use a checker with a low threshold to ensure SLOW detection
            checker = LinkChecker(timeout_s=5, slow_threshold_ms=5000.0)
            result = checker.check("https://example.com/rom.zip")
            assert result.health == LinkHealth.SLOW

    @patch("cyberflash.core.link_checker.urlopen")
    def test_redirect_detection(self, mock_urlopen: MagicMock) -> None:
        resp = MagicMock()
        resp.status = 200
        resp.url = "https://cdn.example.com/rom.zip"
        resp.headers = {"Content-Type": "application/zip", "Content-Length": "0"}
        mock_urlopen.return_value = resp

        result = self.checker.check("https://example.com/rom.zip")
        assert result.redirect_count == 1
        assert result.final_url == "https://cdn.example.com/rom.zip"

    def test_batch_check(self) -> None:
        urls = [
            "ftp://bad-scheme.com",
            "ftp://another-bad.com",
        ]
        results = self.checker.check_batch(urls)
        assert len(results) == 2
        assert all(r.health == LinkHealth.UNREACHABLE for r in results)


class TestCountRedirects:
    def test_no_redirect(self) -> None:
        assert (
            LinkChecker._count_redirects(
                "https://example.com/rom.zip",
                "https://example.com/rom.zip",
            )
            == 0
        )

    def test_trailing_slash_no_redirect(self) -> None:
        assert (
            LinkChecker._count_redirects(
                "https://example.com/path",
                "https://example.com/path/",
            )
            == 0
        )

    def test_redirect_detected(self) -> None:
        assert (
            LinkChecker._count_redirects(
                "https://example.com/rom.zip",
                "https://cdn.example.com/rom.zip",
            )
            == 1
        )
