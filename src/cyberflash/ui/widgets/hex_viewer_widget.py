"""hex_viewer_widget.py — Read-only hex dump viewer widget.

Displays binary data as: ``OFFSET  | HEX BYTES (16/row)  | ASCII``.

Usage::

    viewer = HexViewerWidget(parent)
    viewer.load_bytes(b"Hello World\\x00\\x01\\x02")
    viewer.load_file(Path("/tmp/boot.img"))
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)

_ROW_WIDTH = 16  # bytes per row


def _render_hex(data: bytes, max_bytes: int = 65536) -> str:
    """Convert *data* to a formatted hex dump string (offset | hex | ascii)."""
    truncated = data[:max_bytes]
    lines: list[str] = []
    for row_start in range(0, len(truncated), _ROW_WIDTH):
        chunk = truncated[row_start : row_start + _ROW_WIDTH]
        offset = f"{row_start:08X}"
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        hex_padded = hex_part.ljust(_ROW_WIDTH * 3 - 1)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{offset}  {hex_padded}  {ascii_part}")
    if len(data) > max_bytes:
        lines.append(f"… (truncated — showing {max_bytes} of {len(data)} bytes)")
    return "\n".join(lines)


class HexViewerWidget(QWidget):
    """Read-only hex dump viewer with monospaced output.

    Args:
        parent: Optional parent widget.
        max_bytes: Maximum bytes rendered (default 64 KiB).
    """

    def __init__(self, parent: QWidget | None = None, max_bytes: int = 65536) -> None:
        super().__init__(parent)
        self._max_bytes = max_bytes
        self._data: bytes = b""
        self.setObjectName("HexViewerWidget")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._editor = QPlainTextEdit(self)
        self._editor.setObjectName("HexViewerEditor")
        self._editor.setReadOnly(True)
        font = QFont("monospace")
        font.setPointSize(10)
        self._editor.setFont(font)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._editor.setPlaceholderText("No data loaded.")
        layout.addWidget(self._editor)

    def load_bytes(self, data: bytes) -> None:
        """Render *data* as a hex dump."""
        self._data = data
        self._editor.setPlainText(_render_hex(data, self._max_bytes))
        # Move cursor to top
        cursor = self._editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self._editor.setTextCursor(cursor)

    def load_file(self, path: Path) -> bool:
        """Load a file from *path* and render it. Returns ``False`` on error."""
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            logger.warning("HexViewerWidget.load_file failed: %s", exc)
            self._editor.setPlainText(f"Error: {exc}")
            return False
        self.load_bytes(data)
        return True

    def clear(self) -> None:
        """Clear the viewer."""
        self._data = b""
        self._editor.clear()

    def byte_count(self) -> int:
        """Return the number of bytes currently loaded."""
        return len(self._data)

    def rendered_text(self) -> str:
        """Return the current hex dump as a plain string (for testing)."""
        return self._editor.toPlainText()
