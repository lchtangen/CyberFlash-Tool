from __future__ import annotations

from unittest.mock import MagicMock, patch

from cyberflash.core.edl_manager import EdlManager


def test_list_edl_devices_no_devices():
    """Empty /sys path and lsusb with no matches → returns []."""
    with (
        patch("cyberflash.core.edl_manager.get_platform", return_value="linux"),
        patch("cyberflash.core.edl_manager.Path") as mock_path_cls,
    ):
        # Make /sys/bus/usb/devices appear to not exist
        mock_sys = MagicMock()
        mock_sys.exists.return_value = False
        mock_path_cls.return_value = mock_sys

        # Fallback to lsusb: no matches
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub\n",
                returncode=0,
            )
            result = EdlManager._linux_lsusb_list()

    assert result == []


def test_list_edl_devices_found():
    """lsusb with matching EDL line → returns ['edl:0']."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout=(
                "Bus 001 Device 003: ID 05c6:9008 Qualcomm, Inc. Gobi Wireless Modem\n"
                "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub\n"
            ),
            returncode=0,
        )
        result = EdlManager._linux_lsusb_list()

    assert result == ["edl:0"]


def test_get_udev_rule_contains_vid_pid():
    """The udev rule string must contain both VID and PID."""
    rule = EdlManager.get_udev_rule()
    assert "05c6" in rule.lower()
    assert "9008" in rule.lower()


def test_is_udev_configured_false(tmp_path):
    """Rule file not present → is_udev_configured returns False."""
    fake_path = tmp_path / "51-cyberflash-edl.rules"
    with patch.object(EdlManager, "get_udev_rule_path", return_value=fake_path):
        result = EdlManager.is_udev_configured()
    assert result is False


def test_is_udev_configured_true(tmp_path):
    """Rule file present → is_udev_configured returns True."""
    fake_path = tmp_path / "51-cyberflash-edl.rules"
    fake_path.write_text('SUBSYSTEM=="usb"\n')
    with patch.object(EdlManager, "get_udev_rule_path", return_value=fake_path):
        result = EdlManager.is_udev_configured()
    assert result is True


def test_get_setup_instructions_linux_contains_udev():
    """Linux setup instructions mention udev and the rule path."""
    with patch("cyberflash.core.edl_manager.get_platform", return_value="linux"):
        instructions = EdlManager.get_setup_instructions()
    combined = "\n".join(instructions)
    assert "udev" in combined.lower()
    assert "udevadm" in combined


def test_get_setup_instructions_macos_contains_libusb():
    """macOS setup instructions mention libusb."""
    with patch("cyberflash.core.edl_manager.get_platform", return_value="macos"):
        instructions = EdlManager.get_setup_instructions()
    combined = "\n".join(instructions)
    assert "libusb" in combined


def test_get_setup_instructions_windows_contains_zadig():
    """Windows setup instructions mention Zadig."""
    with patch("cyberflash.core.edl_manager.get_platform", return_value="windows"):
        instructions = EdlManager.get_setup_instructions()
    combined = "\n".join(instructions)
    assert "zadig" in combined.lower()
