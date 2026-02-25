from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .variables import CYBER_DARK, CYBER_GREEN, CYBER_LIGHT, ThemePalette

_THEMES_DIR = Path(__file__).parent

THEMES: dict[str, ThemePalette] = {
    "cyber_dark": CYBER_DARK,
    "cyber_light": CYBER_LIGHT,
    "cyber_green": CYBER_GREEN,
}


class ThemeEngine:
    current_theme: str = "cyber_dark"
    _callbacks: list[Callable[[], None]] = []

    @classmethod
    def register_on_change(cls, cb: Callable[[], None]) -> None:
        """Register a callback invoked after every theme change."""
        if cb not in cls._callbacks:
            cls._callbacks.append(cb)

    @classmethod
    def unregister_on_change(cls, cb: Callable[[], None]) -> None:
        cls._callbacks = [c for c in cls._callbacks if c is not cb]

    @classmethod
    def apply_theme(cls, name: str, app: QApplication | None = None) -> None:
        palette = cls.get_palette(name)
        qss_path = _THEMES_DIR / f"{name}.qss"

        if not qss_path.exists():
            # Fall back to cyber_dark stylesheet for all themes
            qss_path = _THEMES_DIR / "cyber_dark.qss"

        template = qss_path.read_text(encoding="utf-8")
        stylesheet = cls._substitute_tokens(template, palette)

        target_app = app or QApplication.instance()
        if target_app is not None:
            target_app.setStyleSheet(stylesheet)

        cls.current_theme = name

        # Notify registered widgets (e.g. custom paintEvent widgets)
        for cb in list(cls._callbacks):
            try:
                cb()
            except RuntimeError:
                # Widget was deleted — clean it up
                cls._callbacks = [c for c in cls._callbacks if c is not cb]

    @classmethod
    def get_palette(cls, name: str) -> ThemePalette:
        if name not in THEMES:
            raise ValueError(f"Unknown theme: {name!r}. Available: {list(THEMES)}")
        return THEMES[name]

    @staticmethod
    def _substitute_tokens(template: str, palette: ThemePalette) -> str:
        result = template
        for field in dataclasses.fields(palette):
            token = f"{{{field.name}}}"
            value = getattr(palette, field.name)
            result = result.replace(token, value)
        # QSS uses {{ }} to escape literal braces (Python format-string style).
        # Unescape them so Qt receives valid CSS syntax.
        result = result.replace("{{", "{").replace("}}", "}")
        return result
