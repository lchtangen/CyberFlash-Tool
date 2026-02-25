"""Asynchronous HTTP link checker for ROM download sources.

All network I/O is performed via urllib (stdlib) to avoid extra dependencies.
This module lives in ``core/`` and contains no Qt imports.
"""

from __future__ import annotations

import logging
import ssl
import time
from http.client import HTTPException
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cyberflash.models.rom_source import LinkCheckResult, LinkHealth

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_TIMEOUT_S: Final[int] = 15
MAX_REDIRECTS: Final[int] = 10
SLOW_THRESHOLD_MS: Final[float] = 5000.0
USER_AGENT: Final[str] = "CyberFlash-LinkMonitor/1.0 (+https://github.com/cyberflash/cyberflash)"


class LinkChecker:
    """Performs HTTP HEAD/GET checks and produces :class:`LinkCheckResult`."""

    def __init__(
        self,
        timeout_s: int = DEFAULT_TIMEOUT_S,
        slow_threshold_ms: float = SLOW_THRESHOLD_MS,
    ) -> None:
        self._timeout = timeout_s
        self._slow_threshold = slow_threshold_ms
        self._ssl_ctx = self._build_ssl_context()

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self, url: str) -> LinkCheckResult:
        """Run a full availability check on *url*.

        Returns a :class:`LinkCheckResult` populated with status, timing,
        redirect chain info, SSL validity and content metadata.
        """
        result = LinkCheckResult(url=url, timestamp=time.time())

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            result.health = LinkHealth.UNREACHABLE
            result.error_message = f"Unsupported scheme: {parsed.scheme!r}"
            return result

        try:
            result = self._perform_head_check(url, result)
        except Exception as exc:
            logger.debug("Link check failed for %s: %s", url, exc)
            result.error_message = str(exc)

        # Classify slow responses
        if result.health == LinkHealth.OK and result.response_time_ms > self._slow_threshold:
            result.health = LinkHealth.SLOW

        return result

    def check_batch(self, urls: list[str]) -> list[LinkCheckResult]:
        """Check multiple URLs sequentially. Returns list of results."""
        return [self.check(url) for url in urls]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _perform_head_check(
        self,
        url: str,
        result: LinkCheckResult,
    ) -> LinkCheckResult:
        """Execute an HTTP HEAD request, falling back to GET on 405."""
        req = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})

        start = time.monotonic()
        try:
            resp = urlopen(req, timeout=self._timeout, context=self._ssl_ctx)
        except HTTPError as exc:
            elapsed = (time.monotonic() - start) * 1000
            result.response_time_ms = elapsed
            result.status_code = exc.code

            if exc.code == 405:
                # Server doesn't support HEAD — fall back to GET
                return self._perform_get_check(url, result)

            result.health = self._classify_status(exc.code)
            result.error_message = str(exc.reason)
            return result
        except URLError as exc:
            result.response_time_ms = (time.monotonic() - start) * 1000
            result = self._classify_url_error(result, exc)
            return result
        except (HTTPException, OSError) as exc:
            result.response_time_ms = (time.monotonic() - start) * 1000
            result.health = LinkHealth.UNREACHABLE
            result.error_message = str(exc)
            return result

        elapsed = (time.monotonic() - start) * 1000
        result.response_time_ms = elapsed
        result.status_code = resp.status
        result.content_type = resp.headers.get("Content-Type", "")
        length = resp.headers.get("Content-Length", "0")
        result.content_length = int(length) if length.isdigit() else 0
        result.final_url = resp.url
        result.redirect_count = self._count_redirects(url, resp.url)
        result.health = self._classify_status(resp.status)
        result.ssl_valid = True
        resp.close()
        return result

    def _perform_get_check(
        self,
        url: str,
        result: LinkCheckResult,
    ) -> LinkCheckResult:
        """Fallback GET with stream (reads only headers, not body)."""
        req = Request(url, method="GET", headers={"User-Agent": USER_AGENT})

        start = time.monotonic()
        try:
            resp = urlopen(req, timeout=self._timeout, context=self._ssl_ctx)
        except HTTPError as exc:
            result.response_time_ms = (time.monotonic() - start) * 1000
            result.status_code = exc.code
            result.health = self._classify_status(exc.code)
            result.error_message = str(exc.reason)
            return result
        except URLError as exc:
            result.response_time_ms = (time.monotonic() - start) * 1000
            return self._classify_url_error(result, exc)
        except (HTTPException, OSError) as exc:
            result.response_time_ms = (time.monotonic() - start) * 1000
            result.health = LinkHealth.UNREACHABLE
            result.error_message = str(exc)
            return result

        elapsed = (time.monotonic() - start) * 1000
        result.response_time_ms = elapsed
        result.status_code = resp.status
        result.content_type = resp.headers.get("Content-Type", "")
        length = resp.headers.get("Content-Length", "0")
        result.content_length = int(length) if length.isdigit() else 0
        result.final_url = resp.url
        result.redirect_count = self._count_redirects(url, resp.url)
        result.health = self._classify_status(resp.status)
        result.ssl_valid = True
        resp.close()
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_ssl_context() -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        return ctx

    @staticmethod
    def _classify_status(code: int) -> LinkHealth:
        if 200 <= code < 300:
            return LinkHealth.OK
        if 300 <= code < 400:
            return LinkHealth.REDIRECT
        if code == 404:
            return LinkHealth.NOT_FOUND
        if code == 403:
            return LinkHealth.BLOCKED
        if code >= 500:
            return LinkHealth.SERVER_ERROR
        return LinkHealth.UNREACHABLE

    @staticmethod
    def _classify_url_error(
        result: LinkCheckResult,
        exc: URLError,
    ) -> LinkCheckResult:
        reason = str(exc.reason) if exc.reason else str(exc)

        if isinstance(exc.reason, ssl.SSLError):
            result.health = LinkHealth.SSL_ERROR
            result.ssl_valid = False
        elif "timed out" in reason.lower() or isinstance(exc.reason, TimeoutError):
            result.health = LinkHealth.TIMEOUT
        elif "name or service not known" in reason.lower() or "nodename" in reason.lower():
            result.health = LinkHealth.DNS_ERROR
        else:
            result.health = LinkHealth.UNREACHABLE

        result.error_message = reason
        return result

    @staticmethod
    def _count_redirects(original: str, final: str) -> int:
        """Estimate redirect count from URL comparison."""
        if original.rstrip("/") == final.rstrip("/"):
            return 0
        # urllib follows redirects automatically; we can only know it happened
        return 1
