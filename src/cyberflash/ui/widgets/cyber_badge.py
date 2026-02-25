from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget


class CyberBadge(QLabel):
    """Small colored pill label for status indicators.

    Variant is set via a dynamic Qt property ``variant`` so QSS can style
    each variant purely in the stylesheet (see ``cyber_dark.qss``):

        QLabel#cyberBadge[variant="success"] { ... }
    """

    VALID_VARIANTS = frozenset({"success", "warning", "error", "info", "neutral"})

    def __init__(
        self,
        text: str,
        variant: str = "neutral",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("cyberBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        if variant not in self.VALID_VARIANTS:
            variant = "neutral"
        self.setProperty("variant", variant)
        # Force QSS re-evaluation after property change
        self.style().unpolish(self)
        self.style().polish(self)

    def set_text_and_variant(self, text: str, variant: str) -> None:
        self.setText(text)
        self.set_variant(variant)
