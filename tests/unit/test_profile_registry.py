"""Tests for profiles/__init__.py ProfileRegistry."""
from __future__ import annotations

from cyberflash.profiles import ProfileRegistry


def test_load_guacamole_returns_profile() -> None:
    profile = ProfileRegistry.load("guacamole")
    assert profile is not None
    assert profile.codename == "guacamole"
    assert profile.name == "OnePlus 7 Pro"
    assert profile.brand == "OnePlus"


def test_guacamole_profile_has_ab_slots() -> None:
    profile = ProfileRegistry.load("guacamole")
    assert profile is not None
    assert profile.ab_slots is True


def test_load_unknown_codename_returns_none() -> None:
    profile = ProfileRegistry.load("nonexistent_device_xyz")
    assert profile is None


def test_profile_bootloader_config() -> None:
    profile = ProfileRegistry.load("guacamole")
    assert profile is not None
    bl = profile.bootloader
    assert bl.unlock_command == "fastboot oem unlock"
    assert bl.requires_oem_unlock_menu is True
    assert bl.warn_data_wipe is True
