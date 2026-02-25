"""Tests for ROM source data models."""

from __future__ import annotations

from cyberflash.models.rom_source import (
    LinkCheckResult,
    LinkHealth,
    RomSource,
    SourceStatus,
    TrustScore,
    _extract_domain,
)


class TestLinkCheckResult:
    def test_defaults(self) -> None:
        r = LinkCheckResult(url="https://example.com/rom.zip")
        assert r.url == "https://example.com/rom.zip"
        assert r.health == LinkHealth.OK
        assert r.status_code == 0
        assert r.ssl_valid is True

    def test_is_healthy_ok(self) -> None:
        r = LinkCheckResult(url="https://x.com", health=LinkHealth.OK)
        assert r.is_healthy is True

    def test_is_healthy_redirect(self) -> None:
        r = LinkCheckResult(url="https://x.com", health=LinkHealth.REDIRECT)
        assert r.is_healthy is True

    def test_is_not_healthy(self) -> None:
        for h in (LinkHealth.TIMEOUT, LinkHealth.NOT_FOUND, LinkHealth.SSL_ERROR):
            r = LinkCheckResult(url="https://x.com", health=h)
            assert r.is_healthy is False

    def test_was_redirected(self) -> None:
        r = LinkCheckResult(
            url="https://a.com",
            final_url="https://b.com",
            redirect_count=1,
        )
        assert r.was_redirected is True

    def test_was_not_redirected_same_url(self) -> None:
        r = LinkCheckResult(
            url="https://a.com",
            final_url="https://a.com",
            redirect_count=1,
        )
        assert r.was_redirected is False


class TestTrustScore:
    def test_overall_weighted(self) -> None:
        t = TrustScore(availability=1.0, safety=1.0, speed=1.0, reputation=1.0)
        assert abs(t.overall - 1.0) < 1e-9

    def test_overall_zero(self) -> None:
        t = TrustScore()
        assert t.overall == 0.0

    def test_grade_a(self) -> None:
        t = TrustScore(availability=1.0, safety=1.0, speed=1.0, reputation=1.0)
        assert t.grade == "A"

    def test_grade_f(self) -> None:
        t = TrustScore()
        assert t.grade == "F"

    def test_grade_c(self) -> None:
        # overall = 0.30*0.7 + 0.35*0.7 + 0.10*0.7 + 0.25*0.7 = 0.7 → C grade
        t = TrustScore(availability=0.7, safety=0.7, speed=0.7, reputation=0.7)
        assert t.grade == "C"


class TestRomSource:
    def test_auto_domain_extraction(self) -> None:
        s = RomSource(url="https://download.lineageos.org/devices/walleye")
        assert s.domain == "download.lineageos.org"
        assert s.display_name == "download.lineageos.org"

    def test_custom_display_name(self) -> None:
        s = RomSource(url="https://example.com", display_name="My ROM")
        assert s.display_name == "My ROM"

    def test_record_check_updates_counters(self) -> None:
        s = RomSource(url="https://x.com")
        r = LinkCheckResult(url="https://x.com", health=LinkHealth.OK)
        s.record_check(r)
        assert s.check_count == 1
        assert s.consecutive_failures == 0
        assert len(s.check_history) == 1

    def test_record_check_counts_failures(self) -> None:
        s = RomSource(url="https://x.com")
        for _ in range(3):
            r = LinkCheckResult(url="https://x.com", health=LinkHealth.TIMEOUT)
            s.record_check(r)
        assert s.consecutive_failures == 3
        assert s.check_count == 3

    def test_consecutive_failures_reset_on_success(self) -> None:
        s = RomSource(url="https://x.com")
        s.record_check(LinkCheckResult(url="https://x.com", health=LinkHealth.TIMEOUT))
        s.record_check(LinkCheckResult(url="https://x.com", health=LinkHealth.TIMEOUT))
        assert s.consecutive_failures == 2
        s.record_check(LinkCheckResult(url="https://x.com", health=LinkHealth.OK))
        assert s.consecutive_failures == 0

    def test_history_bounded_to_100(self) -> None:
        s = RomSource(url="https://x.com")
        for _ in range(120):
            s.record_check(LinkCheckResult(url="https://x.com"))
        assert len(s.check_history) == 100

    def test_recent_availability(self) -> None:
        s = RomSource(url="https://x.com")
        for _ in range(10):
            s.record_check(LinkCheckResult(url="https://x.com", health=LinkHealth.OK))
        for _ in range(10):
            s.record_check(LinkCheckResult(url="https://x.com", health=LinkHealth.TIMEOUT))
        assert s.recent_availability == 0.5

    def test_avg_response_time(self) -> None:
        s = RomSource(url="https://x.com")
        for ms in (100.0, 200.0, 300.0):
            s.record_check(
                LinkCheckResult(url="https://x.com", health=LinkHealth.OK, response_time_ms=ms)
            )
        assert s.avg_response_time_ms == 200.0

    def test_avg_response_time_ignores_unhealthy(self) -> None:
        s = RomSource(url="https://x.com")
        s.record_check(
            LinkCheckResult(url="https://x.com", health=LinkHealth.OK, response_time_ms=100.0)
        )
        s.record_check(
            LinkCheckResult(url="https://x.com", health=LinkHealth.TIMEOUT, response_time_ms=9999.0)
        )
        assert s.avg_response_time_ms == 100.0


class TestExtractDomain:
    def test_https(self) -> None:
        assert _extract_domain("https://example.com/path") == "example.com"

    def test_with_port(self) -> None:
        assert _extract_domain("https://example.com:8080/path") == "example.com:8080"

    def test_fallback(self) -> None:
        assert _extract_domain("not-a-url") == "not-a-url"


class TestSourceStatus:
    def test_str_enum_values(self) -> None:
        assert SourceStatus.VERIFIED == "verified"
        assert SourceStatus.BLOCKED == "blocked"


class TestLinkHealth:
    def test_str_enum_values(self) -> None:
        assert LinkHealth.OK == "ok"
        assert LinkHealth.SSL_ERROR == "ssl_error"
