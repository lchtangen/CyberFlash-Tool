"""Tests for validators module."""

from __future__ import annotations

from cyberflash.utils.validators import is_valid_device_serial, is_valid_sha256


class TestIsValidSha256:
    def test_valid_hash(self) -> None:
        h = "a" * 64
        assert is_valid_sha256(h) is True

    def test_valid_mixed_case(self) -> None:
        h = "aAbBcCdDeEfF00112233445566778899001122334455667788990011AABBCCDD"
        assert is_valid_sha256(h) is True

    def test_too_short(self) -> None:
        assert is_valid_sha256("abc123") is False

    def test_too_long(self) -> None:
        assert is_valid_sha256("a" * 65) is False

    def test_invalid_chars(self) -> None:
        assert is_valid_sha256("g" * 64) is False

    def test_empty(self) -> None:
        assert is_valid_sha256("") is False


class TestIsValidDeviceSerial:
    def test_valid_serial(self) -> None:
        assert is_valid_device_serial("ABCD1234") is True

    def test_empty_string(self) -> None:
        assert is_valid_device_serial("") is False

    def test_whitespace_only(self) -> None:
        assert is_valid_device_serial("   ") is False

    def test_none_like(self) -> None:
        assert is_valid_device_serial("device:1234") is True
