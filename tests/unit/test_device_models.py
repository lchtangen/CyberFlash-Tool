from cyberflash.models.device import DeviceInfo, DeviceState


def test_device_state_labels():
    assert DeviceState.ONLINE.label == "Online"
    assert DeviceState.FASTBOOT.label == "Fastboot"
    assert DeviceState.UNAUTHORIZED.label == "Unauthorized"


def test_device_state_badge_variants():
    assert DeviceState.ONLINE.badge_variant == "success"
    assert DeviceState.UNAUTHORIZED.badge_variant == "warning"
    assert DeviceState.OFFLINE.badge_variant == "neutral"


def test_device_info_display_name():
    d = DeviceInfo(serial="abc123", state=DeviceState.ONLINE)
    assert d.display_name == "abc123"  # no brand/model yet

    d.brand = "OnePlus"
    d.model = "7 Pro"
    assert d.display_name == "OnePlus 7 Pro"


def test_device_info_is_adb():
    online = DeviceInfo(serial="x", state=DeviceState.ONLINE)
    assert online.is_adb_device
    assert not online.is_fastboot_device

    fb = DeviceInfo(serial="x", state=DeviceState.FASTBOOT)
    assert fb.is_fastboot_device
    assert not fb.is_adb_device


def test_device_info_bootloader_label():
    d = DeviceInfo(serial="x", state=DeviceState.ONLINE)
    assert d.bootloader_label == "Unknown"

    d.bootloader_unlocked = True
    assert d.bootloader_label == "Unlocked"

    d.bootloader_unlocked = False
    assert d.bootloader_label == "Locked"


def test_device_info_slot_label():
    d = DeviceInfo(serial="x", state=DeviceState.ONLINE)
    assert d.slot_label == "N/A"

    d.has_ab_slots = True
    d.active_slot = "a"
    assert d.slot_label == "Slot A"
