"""Data models for ROM source monitoring and trust scoring.

These models track ROM download sources, their availability history,
and computed trust metrics used by the AI scoring engine.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum


class SourceStatus(StrEnum):
    """Current status of a ROM download source."""

    UNKNOWN = "unknown"
    VERIFIED = "verified"
    ACTIVE = "active"
    DEGRADED = "degraded"
    BROKEN = "broken"
    FLAGGED = "flagged"
    BLOCKED = "blocked"


class LinkHealth(StrEnum):
    """Result of a single link health check."""

    OK = "ok"
    REDIRECT = "redirect"
    SLOW = "slow"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    SERVER_ERROR = "server_error"
    SSL_ERROR = "ssl_error"
    DNS_ERROR = "dns_error"
    BLOCKED = "blocked"
    UNREACHABLE = "unreachable"


@dataclass
class LinkCheckResult:
    """Result from a single HTTP availability check."""

    url: str
    timestamp: float = field(default_factory=time.time)
    health: LinkHealth = LinkHealth.OK
    status_code: int = 0
    response_time_ms: float = 0.0
    content_type: str = ""
    content_length: int = 0
    final_url: str = ""
    redirect_count: int = 0
    ssl_valid: bool = True
    error_message: str = ""

    @property
    def is_healthy(self) -> bool:
        return self.health in {LinkHealth.OK, LinkHealth.REDIRECT}

    @property
    def was_redirected(self) -> bool:
        return self.redirect_count > 0 and self.final_url != self.url


@dataclass
class TrustScore:
    """Composite trust score for a ROM source (0.0-1.0 per dimension)."""

    availability: float = 0.0
    safety: float = 0.0
    speed: float = 0.0
    reputation: float = 0.0

    @property
    def overall(self) -> float:
        """Weighted composite score (0.0-1.0)."""
        return (
            self.availability * 0.30
            + self.safety * 0.35
            + self.speed * 0.10
            + self.reputation * 0.25
        )

    @property
    def grade(self) -> str:
        """Letter grade derived from overall score."""
        score = self.overall
        if score >= 0.90:
            return "A"
        if score >= 0.75:
            return "B"
        if score >= 0.60:
            return "C"
        if score >= 0.40:
            return "D"
        return "F"


@dataclass
class RomSource:
    """A tracked ROM download source with history and trust metrics.

    This is the primary model managed by the ROM link monitoring system.
    """

    url: str
    domain: str = ""
    display_name: str = ""
    status: SourceStatus = SourceStatus.UNKNOWN
    trust: TrustScore = field(default_factory=TrustScore)
    check_history: list[LinkCheckResult] = field(default_factory=list)
    first_seen: float = field(default_factory=time.time)
    last_checked: float = 0.0
    check_count: int = 0
    consecutive_failures: int = 0
    flagged_reason: str = ""
    is_user_added: bool = False

    def __post_init__(self) -> None:
        if not self.domain:
            self.domain = _extract_domain(self.url)
        if not self.display_name:
            self.display_name = self.domain

    def record_check(self, result: LinkCheckResult) -> None:
        """Append a check result and update counters."""
        self.check_history.append(result)
        self.last_checked = result.timestamp
        self.check_count += 1

        if result.is_healthy:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

        # Keep history bounded (last 100 checks)
        if len(self.check_history) > 100:
            self.check_history = self.check_history[-100:]

    @property
    def recent_availability(self) -> float:
        """Availability ratio over the last 20 checks (0.0-1.0)."""
        recent = self.check_history[-20:]
        if not recent:
            return 0.0
        healthy = sum(1 for r in recent if r.is_healthy)
        return healthy / len(recent)

    @property
    def avg_response_time_ms(self) -> float:
        """Average response time of healthy checks in the last 20."""
        recent = [r.response_time_ms for r in self.check_history[-20:] if r.is_healthy]
        if not recent:
            return 0.0
        return sum(recent) / len(recent)


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL string."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return parsed.netloc or url
    except Exception:
        return url
