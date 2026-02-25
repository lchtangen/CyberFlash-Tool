from __future__ import annotations

_UNITS = ["B", "KB", "MB", "GB", "TB"]


def format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    if size_bytes < 0:
        return "Unknown"
    if size_bytes == 0:
        return "0 B"
    value = float(size_bytes)
    for unit in _UNITS[:-1]:
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} {_UNITS[-1]}"
