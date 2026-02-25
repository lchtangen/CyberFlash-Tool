"""Tests for ConfigService."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from cyberflash.services.config_service import ConfigService


@pytest.fixture
def config(qapp, tmp_path):
    """Provide a ConfigService backed by a temp INI file."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path),
    )
    svc = ConfigService()
    svc.reset_to_defaults()
    yield svc
    svc.reset_to_defaults()


def test_get_default_theme(config: ConfigService) -> None:
    assert config.get_str("theme") == "cyber_dark"


def test_set_and_get(config: ConfigService) -> None:
    config.set("theme", "cyber_green")
    assert config.get_str("theme") == "cyber_green"


def test_get_int_default(config: ConfigService) -> None:
    assert config.get_int("device/poll_interval_ms") == 2000


def test_get_bool_default(config: ConfigService) -> None:
    assert config.get_bool("device/auto_select_single") is True
    assert config.get_bool("flash/dry_run_default") is False


def test_reset_to_defaults(config: ConfigService) -> None:
    config.set("theme", "cyber_light")
    config.reset_to_defaults()
    assert config.get_str("theme") == "cyber_dark"


def test_value_changed_signal(config: ConfigService, qtbot) -> None:
    with qtbot.waitSignal(config.value_changed, timeout=1000) as blocker:
        config.set("theme", "cyber_green")
    assert blocker.args == ["theme", "cyber_green"]


def test_all_keys(config: ConfigService) -> None:
    keys = config.all_keys()
    assert "theme" in keys
    assert "device/poll_interval_ms" in keys
    assert "logging/file_enabled" in keys
