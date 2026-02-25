from cyberflash.utils.platform_utils import get_platform


def test_get_platform_returns_valid_string():
    platform = get_platform()
    assert platform in ("linux", "macos", "windows")
