from unittest.mock import patch

from cyberflash.core.tool_manager import ToolManager


def test_tool_manager_returns_list_for_adb_cmd():
    cmd = ToolManager.adb_cmd()
    assert isinstance(cmd, list)
    assert len(cmd) >= 1
    assert "adb" in cmd[-1] or cmd[-1].endswith("adb")


def test_tool_manager_returns_list_for_fastboot_cmd():
    cmd = ToolManager.fastboot_cmd()
    assert isinstance(cmd, list)
    assert len(cmd) >= 1


def test_tool_manager_clear_cache():
    ToolManager.adb_cmd()  # populate cache
    ToolManager.clear_cache()
    assert not ToolManager._cache  # cache is empty


def test_tool_availability_returns_bool():
    # Just check it returns bool, not that ADB is installed
    result = ToolManager.is_adb_available()
    assert isinstance(result, bool)


def test_fastboot_availability_returns_bool():
    result = ToolManager.is_fastboot_available()
    assert isinstance(result, bool)


def test_cache_is_reused():
    ToolManager.clear_cache()
    ToolManager.find_adb()
    ToolManager.find_adb()
    assert "adb" in ToolManager._cache


@patch("shutil.which", return_value=None)
def test_not_found_when_no_bundled_or_system(mock_which):
    ToolManager.clear_cache()
    with patch.object(ToolManager, "_find_tool", wraps=ToolManager._find_tool):
        # Force no bundled path by using a tool name that doesn't exist
        result = ToolManager._find_tool("nonexistent_tool_xyz")
    assert result is None
