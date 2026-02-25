import dataclasses

import pytest

from cyberflash.ui.themes.theme_engine import ThemeEngine
from cyberflash.ui.themes.variables import CYBER_DARK, ThemePalette


def test_palette_has_required_fields():
    fields = {f.name for f in dataclasses.fields(ThemePalette)}
    required = {
        "BACKGROUND", "SURFACE", "SURFACE_2", "PRIMARY", "PRIMARY_HOVER",
        "TEXT_PRIMARY", "TEXT_SECONDARY", "TEXT_DISABLED", "BORDER",
        "SUCCESS", "WARNING", "ERROR", "INFO",
    }
    assert required.issubset(fields)


def test_theme_engine_loads_cyber_dark():
    palette = ThemeEngine.get_palette("cyber_dark")
    assert isinstance(palette, ThemePalette)
    assert palette.BACKGROUND == "#0d1117"
    assert palette.PRIMARY == "#00d4ff"


def test_qss_token_substitution():
    template = "background: {BACKGROUND}; color: {TEXT_PRIMARY};"
    palette = CYBER_DARK
    result = ThemeEngine._substitute_tokens(template, palette)
    assert "{BACKGROUND}" not in result
    assert "{TEXT_PRIMARY}" not in result
    assert palette.BACKGROUND in result
    assert palette.TEXT_PRIMARY in result


def test_unknown_theme_raises():
    with pytest.raises(ValueError, match="Unknown theme"):
        ThemeEngine.get_palette("does_not_exist")
