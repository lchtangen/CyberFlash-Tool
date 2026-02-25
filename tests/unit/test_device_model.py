"""Tests for DeviceInfo model."""

from __future__ import annotations

from cyberflash.models.device import DeviceInfo, DeviceState


class TestDeviceState:
    def test_label(self) -> None:
        assert DeviceState.ONLINE.label == "Online"
        assert DeviceState.FASTBOOT.label == "Fastboot"
        assert DeviceState.UNKNOWN.label == "Unknown"

    def test_badge_variant(self) -> None:
        assert DeviceState.ONLINE.badge_variant == "success"
        assert DeviceState.UNAUTHORIZED.badge_variant == "warning"
        assert DeviceState.OFFLINE.badge_variant == "neutral"


class TestDeviceInfo:
    def test_display_name_with_brand_and_model(self) -> None:
        info = DeviceInfo(serial="ABC123", state=DeviceState.ONLINE, brand="OnePlus", model="7 Pro")
        assert info.display_name == "OnePlus 7 Pro"

    def test_display_name_model_only(self) -> None:
        info = DeviceInfo(serial="ABC123", state=DeviceState.ONLINE, model="Pixel 6")
        assert info.display_name == "Pixel 6"

    def test_display_name_fallback_to_serial(self) -> None:
        info = DeviceInfo(serial="ABC123", state=DeviceState.ONLINE)
        assert info.display_name == "ABC123"

    def test_is_adb_device(self) -> None:
        assert DeviceInfo(serial="x", state=DeviceState.ONLINE).is_adb_device is True
        assert DeviceInfo(serial="x", state=DeviceState.RECOVERY).is_adb_device is True
        assert DeviceInfo(serial="x", state=DeviceState.FASTBOOT).is_adb_device is False

    def test_is_fastboot_device(self) -> None:
        assert DeviceInfo(serial="x", state=DeviceState.FASTBOOT).is_fastboot_device is True
        assert DeviceInfo(serial="x", state=DeviceState.FASTBOOTD).is_fastboot_device is True
        assert DeviceInfo(serial="x", state=DeviceState.ONLINE).is_fastboot_device is False

    def test_bootloader_label(self) -> None:
        info = DeviceInfo(serial="x", state=DeviceState.ONLINE)
        assert info.bootloader_label == "Unknown"
        info.bootloader_unlocked = True
        assert info.bootloader_label == "Unlocked"
        info.bootloader_unlocked = False
        assert info.bootloader_label == "Locked"

    def test_slot_label_no_ab(self) -> None:
        info = DeviceInfo(serial="x", state=DeviceState.ONLINE)
        assert info.slot_label == "N/A"

    def test_slot_label_with_ab(self) -> None:
        info = DeviceInfo(serial="x", state=DeviceState.ONLINE, has_ab_slots=True, active_slot="a")
        assert info.slot_label == "Slot A"

    def test_slot_label_ab_no_active(self) -> None:
        info = DeviceInfo(serial="x", state=DeviceState.ONLINE, has_ab_slots=True)
        assert info.slot_label == "A/B"
