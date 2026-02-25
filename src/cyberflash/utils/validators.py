# Placeholder stubs for future validation functions

from __future__ import annotations


def is_valid_sha256(value: str) -> bool:
    """Return True if value is a valid SHA-256 hex digest."""
    return len(value) == 64 and all(c in "0123456789abcdefABCDEF" for c in value)


def is_valid_device_serial(serial: str) -> bool:
    """Return True if serial looks like a valid ADB device serial."""
    return bool(serial and serial.strip())
