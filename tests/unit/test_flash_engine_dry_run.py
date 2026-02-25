"""Tests for core/flash_engine.py — dry-run and error handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cyberflash.core.flash_engine import FlashEngine
from cyberflash.models.profile import BootloaderConfig, DeviceProfile, FlashConfig


def _make_profile() -> DeviceProfile:
    return DeviceProfile(
        codename="guacamole",
        name="OnePlus 7 Pro",
        brand="OnePlus",
        model="GM1913",
        ab_slots=True,
        bootloader=BootloaderConfig(
            unlock_command="fastboot oem unlock",
            requires_oem_unlock_menu=True,
            warn_data_wipe=True,
        ),
        flash=FlashConfig(
            method="fastboot",
            partitions=["boot", "system"],
            vbmeta_disable_flags="--disable-verity --disable-verification",
        ),
        wipe_partitions={"data": "userdata"},
    )


def test_dry_run_does_not_call_fastboot_flash() -> None:
    """In dry-run mode, FastbootManager.flash must never be called."""
    log_lines: list[str] = []
    engine = FlashEngine("ABC123", log_cb=log_lines.append)

    with patch("cyberflash.core.flash_engine.FastbootManager") as mock_fb:
        ok = engine.flash_partition("boot", Path("/tmp/boot.img"), dry_run=True)

    assert ok is True
    mock_fb.flash.assert_not_called()


def test_dry_run_logs_operations() -> None:
    """Dry-run should still emit log messages for each operation."""
    log_lines: list[str] = []
    engine = FlashEngine("ABC123", log_cb=log_lines.append)
    profile = _make_profile()

    with patch("cyberflash.core.flash_engine.FastbootManager"):
        engine.unlock_bootloader(profile, dry_run=True)

    assert any("dry-run" in line.lower() or "unlock" in line.lower() for line in log_lines)


def test_flash_engine_returns_false_on_error() -> None:
    """flash_partition returns False when the image file does not exist."""
    log_lines: list[str] = []
    engine = FlashEngine("ABC123", log_cb=log_lines.append)

    nonexistent = Path("/tmp/__does_not_exist_xyz__.img")
    ok = engine.flash_partition("boot", nonexistent, dry_run=False)

    assert ok is False
    assert any("not found" in line.lower() for line in log_lines)
