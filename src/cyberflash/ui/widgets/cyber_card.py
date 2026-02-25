from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget


class CyberCard(QFrame):
    """Styled card container — all colors come from QSS theme.

    QSS selector: QFrame#cyberCard (see cyber_dark.qss)
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("cyberCard")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(8)

    def card_layout(self) -> QVBoxLayout:
        return self._layout
