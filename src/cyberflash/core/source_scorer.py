"""AI-driven trust scoring engine for ROM download sources.

Combines multiple heuristic signals — domain reputation, availability
history, response-time metrics, redirect analysis, and URL pattern
detection — into a composite :class:`TrustScore`.

This module lives in ``core/`` and contains no Qt imports.
"""

from __future__ import annotations

import logging
import math
from typing import Final

from cyberflash.core.domain_lists import (
    has_suspicious_tld,
    has_suspicious_url_fragment,
    is_blocked_domain,
    is_trusted_domain,
)
from cyberflash.models.rom_source import (
    RomSource,
    SourceStatus,
    TrustScore,
)

logger = logging.getLogger(__name__)

# ── Tuning constants ──────────────────────────────────────────────────────────

# Sources with fewer checks than this get a "not enough data" penalty
MIN_CHECKS_FOR_CONFIDENCE: Final[int] = 5

# Response-time brackets (ms) for the speed score
SPEED_EXCELLENT_MS: Final[float] = 500.0
SPEED_GOOD_MS: Final[float] = 2000.0
SPEED_POOR_MS: Final[float] = 5000.0

# Consecutive failures threshold to mark as BROKEN
BROKEN_FAILURE_THRESHOLD: Final[int] = 5

# Consecutive failures threshold to mark as DEGRADED
DEGRADED_FAILURE_THRESHOLD: Final[int] = 2


class SourceScorer:
    """Computes and updates :class:`TrustScore` for :class:`RomSource` objects.

    The scorer examines:
      1. **Domain reputation** — trusted/blocked/suspicious lists
      2. **Availability history** — recent success ratio, consecutive failures
      3. **Response speed** — average latency of healthy checks
      4. **Safety heuristics** — SSL validity, redirect chains, URL patterns

    The resulting :class:`TrustScore` has four dimensions (0.0-1.0) and
    a weighted ``overall`` composite used for sorting and display.
    """

    def score(self, source: RomSource) -> TrustScore:
        """Compute a fresh :class:`TrustScore` for *source*."""
        trust = TrustScore(
            availability=self._score_availability(source),
            safety=self._score_safety(source),
            speed=self._score_speed(source),
            reputation=self._score_reputation(source),
        )
        return trust

    def score_and_update(self, source: RomSource) -> None:
        """Compute and apply a new trust score + status to *source*."""
        source.trust = self.score(source)
        source.status = self._derive_status(source)
        logger.debug(
            "Scored %s: overall=%.2f grade=%s status=%s",
            source.domain,
            source.trust.overall,
            source.trust.grade,
            source.status.value,
        )

    # ── Dimension scorers ────────────────────────────────────────────────────

    def _score_availability(self, source: RomSource) -> float:
        """Score based on recent check availability ratio (0.0-1.0)."""
        if source.check_count == 0:
            return 0.0

        availability = source.recent_availability

        # Apply confidence penalty if too few checks
        if source.check_count < MIN_CHECKS_FOR_CONFIDENCE:
            confidence = source.check_count / MIN_CHECKS_FOR_CONFIDENCE
            availability *= confidence

        # Penalise consecutive failures with exponential decay
        if source.consecutive_failures > 0:
            penalty = 1.0 - math.exp(-0.5 * source.consecutive_failures)
            availability *= 1.0 - penalty

        return max(0.0, min(1.0, availability))

    def _score_safety(self, source: RomSource) -> float:
        """Score based on SSL, redirects, URL patterns, and domain lists."""
        score = 1.0

        # Blocked domain → immediate zero
        if is_blocked_domain(source.domain):
            return 0.0

        # Suspicious TLD
        if has_suspicious_tld(source.domain):
            score -= 0.3

        # Suspicious URL fragments (link shorteners, ad gateways)
        if has_suspicious_url_fragment(source.url):
            score -= 0.4

        # Check SSL validity from recent history
        recent = source.check_history[-10:]
        if recent:
            ssl_failures = sum(1 for r in recent if not r.ssl_valid)
            if ssl_failures > 0:
                score -= 0.25 * (ssl_failures / len(recent))

        # Excessive redirects are suspicious
        redirect_checks = [r for r in recent if r.redirect_count > 0]
        if redirect_checks:
            avg_redirects = sum(r.redirect_count for r in redirect_checks) / len(redirect_checks)
            if avg_redirects > 2:
                score -= 0.2

        # Cross-domain redirects (likely ad gateway)
        for result in recent:
            if result.was_redirected:
                orig_domain = _extract_base_domain(source.url)
                final_domain = _extract_base_domain(result.final_url)
                if orig_domain != final_domain:
                    score -= 0.3
                    break

        return max(0.0, min(1.0, score))

    def _score_speed(self, source: RomSource) -> float:
        """Score based on average response time of healthy checks."""
        avg = source.avg_response_time_ms
        if avg <= 0:
            return 0.5  # neutral when no data

        if avg <= SPEED_EXCELLENT_MS:
            return 1.0
        if avg <= SPEED_GOOD_MS:
            # Linear interpolation between excellent and good
            return 1.0 - 0.3 * (avg - SPEED_EXCELLENT_MS) / (SPEED_GOOD_MS - SPEED_EXCELLENT_MS)
        if avg <= SPEED_POOR_MS:
            return 0.7 - 0.5 * (avg - SPEED_GOOD_MS) / (SPEED_POOR_MS - SPEED_GOOD_MS)
        return 0.1  # extremely slow

    def _score_reputation(self, source: RomSource) -> float:
        """Score based on domain reputation lists."""
        if is_blocked_domain(source.domain):
            return 0.0
        if is_trusted_domain(source.domain):
            return 1.0
        if has_suspicious_tld(source.domain):
            return 0.2
        # Unknown domain starts at 0.5 and can improve with history
        base = 0.5
        if source.check_count >= MIN_CHECKS_FOR_CONFIDENCE:
            # Bonus for consistent availability
            base += source.recent_availability * 0.3
        return max(0.0, min(1.0, base))

    # ── Status derivation ────────────────────────────────────────────────────

    def _derive_status(self, source: RomSource) -> SourceStatus:
        """Derive the overall :class:`SourceStatus` from trust and history."""
        # Blocked by reputation
        if is_blocked_domain(source.domain):
            source.flagged_reason = "Domain is on the blocked list"
            return SourceStatus.BLOCKED

        # Flagged by safety score
        if source.trust.safety < 0.3:
            source.flagged_reason = "Low safety score — suspicious patterns detected"
            return SourceStatus.FLAGGED

        # Broken — persistent failures
        if source.consecutive_failures >= BROKEN_FAILURE_THRESHOLD:
            return SourceStatus.BROKEN

        # Degraded — intermittent failures
        if source.consecutive_failures >= DEGRADED_FAILURE_THRESHOLD:
            return SourceStatus.DEGRADED

        # Not enough data yet
        if source.check_count < MIN_CHECKS_FOR_CONFIDENCE:
            return SourceStatus.UNKNOWN

        # Verified trusted domain with healthy track record
        if is_trusted_domain(source.domain) and source.trust.overall >= 0.75:
            return SourceStatus.VERIFIED

        # Active — healthy but not from a verified domain
        if source.recent_availability >= 0.8:
            return SourceStatus.ACTIVE

        return SourceStatus.DEGRADED


def _extract_base_domain(url: str) -> str:
    """Extract the registrable base domain from a URL."""
    try:
        from urllib.parse import urlparse

        netloc = urlparse(url).netloc
        parts = netloc.split(".")
        # Return last two parts (e.g., "example.com" from "sub.example.com")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return netloc
    except Exception:
        return url
