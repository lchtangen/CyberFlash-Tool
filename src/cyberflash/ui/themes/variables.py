from dataclasses import dataclass


@dataclass
class ThemePalette:
    BACKGROUND: str
    SURFACE: str
    SURFACE_2: str
    PRIMARY: str
    PRIMARY_HOVER: str
    TEXT_PRIMARY: str
    TEXT_SECONDARY: str
    TEXT_DISABLED: str
    BORDER: str
    SUCCESS: str
    WARNING: str
    ERROR: str
    INFO: str


CYBER_DARK = ThemePalette(
    BACKGROUND="#0d1117",
    SURFACE="#161b22",
    SURFACE_2="#21262d",
    PRIMARY="#00d4ff",
    PRIMARY_HOVER="#33ddff",
    TEXT_PRIMARY="#e6edf3",
    TEXT_SECONDARY="#8b949e",
    TEXT_DISABLED="#484f58",
    BORDER="#30363d",
    SUCCESS="#3fb950",
    WARNING="#d29922",
    ERROR="#f85149",
    INFO="#58a6ff",
)

CYBER_LIGHT = ThemePalette(
    BACKGROUND="#f6f8fa",
    SURFACE="#ffffff",
    SURFACE_2="#f0f2f5",
    PRIMARY="#0969da",
    PRIMARY_HOVER="#0550ae",
    TEXT_PRIMARY="#1f2328",
    TEXT_SECONDARY="#57606a",
    TEXT_DISABLED="#8c959f",
    BORDER="#d0d7de",
    SUCCESS="#1a7f37",
    WARNING="#9a6700",
    ERROR="#cf222e",
    INFO="#0969da",
)

CYBER_GREEN = ThemePalette(
    BACKGROUND="#0a0f0a",
    SURFACE="#0d1a0d",
    SURFACE_2="#152315",
    PRIMARY="#00ff41",
    PRIMARY_HOVER="#33ff66",
    TEXT_PRIMARY="#ccffcc",
    TEXT_SECONDARY="#66aa66",
    TEXT_DISABLED="#335533",
    BORDER="#1a3a1a",
    SUCCESS="#00ff41",
    WARNING="#ffaa00",
    ERROR="#ff3333",
    INFO="#00aaff",
)
