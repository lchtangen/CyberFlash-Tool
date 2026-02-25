"""Tests for the domain reputation lists module."""

from __future__ import annotations

from cyberflash.core.domain_lists import (
    has_suspicious_tld,
    has_suspicious_url_fragment,
    is_blocked_domain,
    is_trusted_domain,
)


class TestIsTrustedDomain:
    def test_exact_match(self) -> None:
        assert is_trusted_domain("download.lineageos.org") is True

    def test_subdomain_match(self) -> None:
        assert is_trusted_domain("cdn.download.lineageos.org") is True

    def test_untrusted(self) -> None:
        assert is_trusted_domain("evil-roms.xyz") is False

    def test_case_insensitive(self) -> None:
        assert is_trusted_domain("Download.LineageOS.org") is True

    def test_grapheneos(self) -> None:
        assert is_trusted_domain("releases.grapheneos.org") is True

    def test_github(self) -> None:
        assert is_trusted_domain("github.com") is True


class TestIsBlockedDomain:
    def test_exact_blocked(self) -> None:
        assert is_blocked_domain("firmwarefile.com") is True

    def test_subdomain_blocked(self) -> None:
        assert is_blocked_domain("dl.firmwarefile.com") is True

    def test_not_blocked(self) -> None:
        assert is_blocked_domain("google.com") is False

    def test_case_insensitive(self) -> None:
        assert is_blocked_domain("NeedRom.com") is True


class TestHasSuspiciousTld:
    def test_suspicious_xyz(self) -> None:
        assert has_suspicious_tld("evil-roms.xyz") is True

    def test_suspicious_tk(self) -> None:
        assert has_suspicious_tld("free-roms.tk") is True

    def test_normal_com(self) -> None:
        assert has_suspicious_tld("example.com") is False

    def test_normal_org(self) -> None:
        assert has_suspicious_tld("example.org") is False


class TestHasSuspiciousUrlFragment:
    def test_link_shortener(self) -> None:
        assert has_suspicious_url_fragment("https://adf.ly/abc123") is True

    def test_ad_gateway(self) -> None:
        assert has_suspicious_url_fragment("https://linkvertise.com/12345") is True

    def test_clean_url(self) -> None:
        assert (
            has_suspicious_url_fragment("https://download.lineageos.org/devices/walleye") is False
        )

    def test_token_parameter(self) -> None:
        assert has_suspicious_url_fragment("https://sketchy.com/download?token=xyz") is True
