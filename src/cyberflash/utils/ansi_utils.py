from __future__ import annotations

import re

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from a string."""
    return _ANSI_ESCAPE.sub("", text)


def ansi_to_html(text: str) -> str:
    """Convert basic ANSI color codes to HTML <span> tags."""
    _COLORS = {
        "30": "#484f58", "31": "#f85149", "32": "#3fb950",
        "33": "#d29922", "34": "#58a6ff", "35": "#bc8cff",
        "36": "#00d4ff", "37": "#e6edf3", "0": None,
    }
    result = []
    open_span = False
    i = 0
    while i < len(text):
        if text[i] == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
            end = text.find("m", i + 2)
            if end != -1:
                code = text[i + 2:end]
                if open_span:
                    result.append("</span>")
                    open_span = False
                color = _COLORS.get(code)
                if color:
                    result.append(f'<span style="color:{color}">')
                    open_span = True
                i = end + 1
                continue
        result.append(text[i].replace("<", "&lt;").replace(">", "&gt;"))
        i += 1
    if open_span:
        result.append("</span>")
    return "".join(result)
