from __future__ import annotations

from unittest.mock import patch

import pytest

from cyberflash.core.edl_engine import EdlEngine


@pytest.fixture
def engine(tmp_path):
    logs = []
    e = EdlEngine("edl:0", log_cb=logs.append)
    e._tmp_path = tmp_path
    e._logs = logs
    return e


def test_dry_run_does_not_call_edl_subprocess(engine, tmp_path):
    """dry_run=True must not invoke subprocess.Popen."""
    programmer = tmp_path / "prog.elf"
    programmer.write_bytes(b"\x7fELF")
    xml = tmp_path / "rawprogram0.xml"
    xml.write_text("<xml/>")

    with patch("cyberflash.core.edl_engine.subprocess.Popen") as mock_popen:
        result = engine.flash_with_rawprogram(
            programmer=programmer,
            rawprogram_xml=xml,
            patch_xml=None,
            package_dir=tmp_path,
            dry_run=True,
        )

    mock_popen.assert_not_called()
    assert result is True


def test_dry_run_logs_operations(engine, tmp_path):
    """dry_run=True should produce log entries describing what would happen."""
    programmer = tmp_path / "prog.elf"
    programmer.write_bytes(b"\x7fELF")
    xml = tmp_path / "rawprogram0.xml"
    xml.write_text("<xml/>")

    engine.flash_with_rawprogram(
        programmer=programmer,
        rawprogram_xml=xml,
        patch_xml=None,
        package_dir=tmp_path,
        dry_run=True,
    )

    combined = "\n".join(engine._logs)
    assert "dry-run" in combined.lower() or "dry_run" in combined.lower()


def test_missing_programmer_returns_false(engine, tmp_path):
    """Nonexistent programmer .elf → flash_with_rawprogram returns False."""
    programmer = tmp_path / "nonexistent.elf"
    xml = tmp_path / "rawprogram0.xml"
    xml.write_text("<xml/>")

    result = engine.flash_with_rawprogram(
        programmer=programmer,
        rawprogram_xml=xml,
        patch_xml=None,
        package_dir=tmp_path,
        dry_run=False,
    )

    assert result is False


def test_missing_rawprogram_xml_returns_false(engine, tmp_path):
    """Nonexistent rawprogram XML → flash_with_rawprogram returns False."""
    programmer = tmp_path / "prog.elf"
    programmer.write_bytes(b"\x7fELF")
    xml = tmp_path / "rawprogram0.xml"  # does NOT exist

    result = engine.flash_with_rawprogram(
        programmer=programmer,
        rawprogram_xml=xml,
        patch_xml=None,
        package_dir=tmp_path,
        dry_run=False,
    )

    assert result is False


def test_flash_partition_dry_run_no_subprocess(engine, tmp_path):
    """flash_partition dry_run=True must not call subprocess."""
    image = tmp_path / "boot.bin"
    image.write_bytes(b"\x00" * 16)

    with patch("cyberflash.core.edl_engine.subprocess.Popen") as mock_popen:
        result = engine.flash_partition("boot", image, dry_run=True)

    mock_popen.assert_not_called()
    assert result is True


def test_flash_partition_missing_image_returns_false(engine, tmp_path):
    """flash_partition with nonexistent image → returns False."""
    image = tmp_path / "nonexistent.bin"
    result = engine.flash_partition("boot", image, dry_run=False)
    assert result is False


def test_is_edl_tool_available_returns_bool(engine):
    """is_edl_tool_available() must always return a bool."""
    result = engine.is_edl_tool_available()
    assert isinstance(result, bool)
