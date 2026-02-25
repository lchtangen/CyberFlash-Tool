"""Tests for the SourceScorer AI trust engine."""

from __future__ import annotations

from cyberflash.core.source_scorer import SourceScorer
from cyberflash.models.rom_source import (
    LinkCheckResult,
    LinkHealth,
    RomSource,
    SourceStatus,
)


def _make_source(url: str = "https://example.com/rom.zip") -> RomSource:
    return RomSource(url=url)


def _add_healthy_checks(source: RomSource, count: int = 10) -> None:
    for _ in range(count):
        source.record_check(
            LinkCheckResult(
                url=source.url,
                health=LinkHealth.OK,
                response_time_ms=500.0,
                ssl_valid=True,
            )
        )


def _add_failing_checks(source: RomSource, count: int = 5) -> None:
    for _ in range(count):
        source.record_check(
            LinkCheckResult(
                url=source.url,
                health=LinkHealth.TIMEOUT,
                response_time_ms=0.0,
                ssl_valid=True,
            )
        )


class TestSourceScorer:
    def setup_method(self) -> None:
        self.scorer = SourceScorer()

    # ── Availability scoring ─────────────────────────────────────────────────

    def test_availability_no_checks(self) -> None:
        s = _make_source()
        trust = self.scorer.score(s)
        assert trust.availability == 0.0

    def test_availability_all_healthy(self) -> None:
        s = _make_source()
        _add_healthy_checks(s, 10)
        trust = self.scorer.score(s)
        assert trust.availability > 0.9

    def test_availability_penalised_by_failures(self) -> None:
        s = _make_source()
        _add_healthy_checks(s, 5)
        _add_failing_checks(s, 5)
        trust = self.scorer.score(s)
        assert trust.availability < 0.6

    def test_availability_confidence_penalty(self) -> None:
        """Sources with < 5 checks get a confidence penalty."""
        s = _make_source()
        _add_healthy_checks(s, 2)
        trust = self.scorer.score(s)
        assert trust.availability < 0.5  # penalised for low sample

    # ── Safety scoring ───────────────────────────────────────────────────────

    def test_safety_blocked_domain(self) -> None:
        s = _make_source("https://firmwarefile.com/rom.zip")
        trust = self.scorer.score(s)
        assert trust.safety == 0.0

    def test_safety_suspicious_tld(self) -> None:
        s = _make_source("https://roms.xyz/rom.zip")
        trust = self.scorer.score(s)
        assert trust.safety < 0.8

    def test_safety_suspicious_url_fragment(self) -> None:
        s = _make_source("https://adf.ly/abc123")
        trust = self.scorer.score(s)
        assert trust.safety < 0.7  # penalised for suspicious fragment

    def test_safety_ssl_failures(self) -> None:
        s = _make_source()
        for _ in range(5):
            s.record_check(LinkCheckResult(url=s.url, health=LinkHealth.OK, ssl_valid=False))
        trust = self.scorer.score(s)
        assert trust.safety < 0.8

    def test_safety_cross_domain_redirect(self) -> None:
        s = _make_source("https://legit.com/rom.zip")
        s.record_check(
            LinkCheckResult(
                url=s.url,
                health=LinkHealth.OK,
                final_url="https://sketchy-cdn.xyz/rom.zip",
                redirect_count=1,
            )
        )
        trust = self.scorer.score(s)
        assert trust.safety < 0.8

    def test_safety_clean_source(self) -> None:
        s = _make_source("https://download.lineageos.org/rom.zip")
        _add_healthy_checks(s, 5)
        trust = self.scorer.score(s)
        assert trust.safety >= 0.9

    # ── Speed scoring ────────────────────────────────────────────────────────

    def test_speed_excellent(self) -> None:
        s = _make_source()
        for _ in range(5):
            s.record_check(LinkCheckResult(url=s.url, health=LinkHealth.OK, response_time_ms=200.0))
        trust = self.scorer.score(s)
        assert trust.speed == 1.0

    def test_speed_slow(self) -> None:
        s = _make_source()
        for _ in range(5):
            s.record_check(
                LinkCheckResult(url=s.url, health=LinkHealth.OK, response_time_ms=6000.0)
            )
        trust = self.scorer.score(s)
        assert trust.speed < 0.2

    def test_speed_no_data(self) -> None:
        s = _make_source()
        trust = self.scorer.score(s)
        assert trust.speed == 0.5  # neutral

    # ── Reputation scoring ───────────────────────────────────────────────────

    def test_reputation_trusted(self) -> None:
        s = _make_source("https://download.lineageos.org/rom.zip")
        trust = self.scorer.score(s)
        assert trust.reputation == 1.0

    def test_reputation_blocked(self) -> None:
        s = _make_source("https://firmwarefile.com/rom.zip")
        trust = self.scorer.score(s)
        assert trust.reputation == 0.0

    def test_reputation_suspicious_tld(self) -> None:
        s = _make_source("https://roms.xyz/rom.zip")
        trust = self.scorer.score(s)
        assert trust.reputation == 0.2

    def test_reputation_unknown_domain(self) -> None:
        s = _make_source("https://unknown-rom-site.com/rom.zip")
        trust = self.scorer.score(s)
        assert 0.4 <= trust.reputation <= 0.6

    def test_reputation_unknown_improves_with_history(self) -> None:
        s = _make_source("https://unknown-rom-site.com/rom.zip")
        _add_healthy_checks(s, 10)
        trust = self.scorer.score(s)
        assert trust.reputation > 0.6

    # ── Status derivation ────────────────────────────────────────────────────

    def test_status_blocked(self) -> None:
        s = _make_source("https://firmwarefile.com/rom.zip")
        self.scorer.score_and_update(s)
        assert s.status == SourceStatus.BLOCKED

    def test_status_flagged_low_safety(self) -> None:
        # Combine multiple suspicious signals to trigger low safety
        s = _make_source("https://adf.ly/abc123")
        # Add SSL failures + cross-domain redirects
        for _ in range(5):
            s.record_check(
                LinkCheckResult(
                    url=s.url,
                    health=LinkHealth.OK,
                    ssl_valid=False,
                    final_url="https://evil.xyz/payload",
                    redirect_count=3,
                    response_time_ms=500.0,
                )
            )
        self.scorer.score_and_update(s)
        assert s.status == SourceStatus.FLAGGED

    def test_status_broken_many_failures(self) -> None:
        s = _make_source()
        _add_failing_checks(s, 6)
        self.scorer.score_and_update(s)
        assert s.status == SourceStatus.BROKEN

    def test_status_degraded_some_failures(self) -> None:
        s = _make_source()
        _add_healthy_checks(s, 5)
        _add_failing_checks(s, 3)
        self.scorer.score_and_update(s)
        assert s.status == SourceStatus.DEGRADED

    def test_status_verified_trusted_healthy(self) -> None:
        s = _make_source("https://download.lineageos.org/rom.zip")
        _add_healthy_checks(s, 10)
        self.scorer.score_and_update(s)
        assert s.status == SourceStatus.VERIFIED

    def test_status_active_unknown_domain_healthy(self) -> None:
        s = _make_source("https://good-rom-mirror.com/rom.zip")
        _add_healthy_checks(s, 10)
        self.scorer.score_and_update(s)
        assert s.status == SourceStatus.ACTIVE

    def test_status_unknown_few_checks(self) -> None:
        s = _make_source()
        _add_healthy_checks(s, 2)
        self.scorer.score_and_update(s)
        assert s.status == SourceStatus.UNKNOWN


class TestOverallGrade:
    def setup_method(self) -> None:
        self.scorer = SourceScorer()

    def test_trusted_healthy_gets_a(self) -> None:
        s = _make_source("https://download.lineageos.org/rom.zip")
        _add_healthy_checks(s, 10)
        self.scorer.score_and_update(s)
        assert s.trust.grade == "A"

    def test_blocked_gets_f(self) -> None:
        s = _make_source("https://firmwarefile.com/rom.zip")
        self.scorer.score_and_update(s)
        assert s.trust.grade == "F"
