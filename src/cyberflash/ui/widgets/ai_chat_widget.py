"""Reusable chat message widget for the AI assistant panel.

Renders a scrollable conversation thread with styled user / AI message
bubbles, markdown-like formatting, and auto-scroll behaviour.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Timeout (ms) before "Thinking…" is replaced with a fallback message.
# Covers both slow Gemini responses and silent invocation failures.
_RESPONSE_TIMEOUT_MS = 30_000


class MessageRole(StrEnum):
    USER = "user"
    AI = "ai"
    SYSTEM = "system"


@dataclass
class ChatMessage:
    role: MessageRole
    text: str
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.datetime.now().strftime("%H:%M:%S")


class ChatBubble(QWidget):
    """A single styled chat message bubble."""

    def __init__(
        self,
        message: ChatMessage,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._message = message
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        # Role + timestamp header
        header = QHBoxLayout()
        role_label = QLabel(self._role_display())
        role_label.setObjectName("chatRoleLabel")
        role_label.setProperty("role", self._message.role.value)
        header.addWidget(role_label)
        header.addStretch()
        ts = QLabel(self._message.timestamp)
        ts.setObjectName("chatTimestamp")
        header.addWidget(ts)
        layout.addLayout(header)

        # Message body
        body = QLabel()
        body.setObjectName("chatBubbleBody")
        body.setProperty("role", self._message.role.value)
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setText(self._format_text(self._message.text))
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(body)

    def _role_display(self) -> str:
        return {
            MessageRole.USER: "You",
            MessageRole.AI: "CyberFlash AI",
            MessageRole.SYSTEM: "System",
        }[self._message.role]

    @staticmethod
    def _format_text(text: str) -> str:
        """Light Markdown→HTML conversion for bold, bullets, and code."""
        html = text

        # Bold: **text**
        html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)

        # Code: `text`
        html = re.sub(
            r"`(.+?)`",
            r'<span style="background:#21262d;padding:1px 4px;'
            r'border-radius:3px;font-family:monospace;">\1</span>',
            html,
        )

        # Bullet points
        lines: list[str] = []
        for line in html.split("\n"):
            stripped = line.lstrip()
            if stripped.startswith(("• ", "- ")) or re.match(r"^\d+\.\s", stripped):
                lines.append(f"&nbsp;&nbsp;{stripped}")
            else:
                lines.append(line)
        html = "<br>".join(lines)

        return html


# Prompt expansions for quick actions — makes Gemini answers much better
_QUICK_PROMPTS: dict[str, str] = {
    "status": (
        "Give me a complete status summary of my connected device including: "
        "device name, model, serial number, Android version, build number, "
        "bootloader state (locked/unlocked), root status, battery level, "
        "A/B slot info if applicable, and any issues I should know about."
    ),
    "backup": (
        "What backup options are available for my device right now? "
        "What should I back up first and why? Give me a prioritized list "
        "of what to back up (apps, data, media, partitions) and the best "
        "method for each. Warn me about anything that cannot be restored."
    ),
}


class AIChatWidget(QWidget):
    """Chat interface with message history, input field, and quick actions.

    Signals:
        message_sent(str)       — emitted when the user sends a message
        quick_action(str)       — emitted for chat-based quick actions (expanded prompts)
        assess_risk_requested() — emitted when user clicks the Risk button
        health_scan_requested() — emitted when user clicks the Health button
    """

    message_sent = Signal(str)
    quick_action = Signal(str)
    assess_risk_requested = Signal()
    health_scan_requested = Signal()

    _MAX_MESSAGES = 200

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aiChatWidget")
        self._messages: list[ChatMessage] = []
        self._thinking_bubble: QWidget | None = None
        self._awaiting_response = False
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.setInterval(_RESPONSE_TIMEOUT_MS)
        self._timeout_timer.timeout.connect(self._on_response_timeout)
        self._setup_ui()
        self._add_welcome_message()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Chat history scroll area ─────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setObjectName("aiChatScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._chat_container = QWidget()
        self._chat_container.setObjectName("aiChatContainer")
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(8, 8, 8, 8)
        self._chat_layout.setSpacing(6)
        self._chat_layout.addStretch()

        self._scroll.setWidget(self._chat_container)
        layout.addWidget(self._scroll, 1)

        # ── Quick actions bar ────────────────────────────────────────────────
        quick_bar = QWidget()
        quick_bar.setObjectName("aiQuickBar")
        quick_layout = QHBoxLayout(quick_bar)
        quick_layout.setContentsMargins(8, 4, 8, 4)
        quick_layout.setSpacing(4)

        # Status — expands to full natural-language prompt for AI
        for label, cmd in [("Status", "status"), ("Backup", "backup")]:
            btn = QPushButton(label)
            btn.setObjectName("aiQuickButton")
            btn.setFixedHeight(26)
            btn.setToolTip(f"Ask AI about {label.lower()} — sends a full query")
            btn.clicked.connect(
                lambda _c=False, c=cmd: self._on_quick_chat(c)
            )
            quick_layout.addWidget(btn)

        # Risk — triggers assess_risk signal (NOT a regular chat message)
        risk_btn = QPushButton("Risk")
        risk_btn.setObjectName("aiQuickButton")
        risk_btn.setFixedHeight(26)
        risk_btn.setToolTip("Run AI risk assessment for the current page context")
        risk_btn.clicked.connect(self.assess_risk_requested)
        quick_layout.addWidget(risk_btn)

        # Health — triggers health scan signal
        health_btn = QPushButton("Health")
        health_btn.setObjectName("aiQuickButton")
        health_btn.setFixedHeight(26)
        health_btn.setToolTip("Run device health scan and show metrics")
        health_btn.clicked.connect(self.health_scan_requested)
        quick_layout.addWidget(health_btn)

        quick_layout.addStretch()

        # Clear chat button
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("aiQuickButton")
        clear_btn.setFixedHeight(26)
        clear_btn.setToolTip("Clear chat history")
        clear_btn.clicked.connect(self.clear_chat)
        quick_layout.addWidget(clear_btn)

        layout.addWidget(quick_bar)

        # ── Input area ───────────────────────────────────────────────────────
        input_bar = QWidget()
        input_bar.setObjectName("aiInputBar")
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(8, 6, 8, 6)
        input_layout.setSpacing(6)

        self._input = QLineEdit()
        self._input.setObjectName("aiChatInput")
        self._input.setPlaceholderText("Ask CyberFlash AI anything…")
        self._input.returnPressed.connect(self._on_send)
        input_layout.addWidget(self._input, 1)

        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("aiSendButton")
        self._send_btn.setFixedWidth(60)
        self._send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(self._send_btn)

        layout.addWidget(input_bar)

    def _add_welcome_message(self) -> None:
        self.add_ai_message(
            "Welcome to **CyberFlash AI** — your device assistant.\n\n"
            "Ask me anything about flashing, rooting, backups, bootloaders, "
            "partitions, NetHunter, or device diagnostics.\n\n"
            "Quick actions:\n"
            "• **Status** — full device status summary\n"
            "• **Backup** — what to back up and how\n"
            "• **Risk** — risk assessment for current page\n"
            "• **Health** — device health scan & metrics"
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def add_user_message(self, text: str) -> None:
        self._append(ChatMessage(role=MessageRole.USER, text=text))

    def add_ai_message(self, text: str) -> None:
        self._timeout_timer.stop()
        self._remove_thinking_bubble()
        self._append(ChatMessage(role=MessageRole.AI, text=text))
        self._set_input_enabled(True)

    def add_system_message(self, text: str) -> None:
        self._append(ChatMessage(role=MessageRole.SYSTEM, text=text))

    def clear_chat(self) -> None:
        """Remove all messages from the chat."""
        self._timeout_timer.stop()
        while self._chat_layout.count() > 1:
            item = self._chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._messages.clear()
        self._thinking_bubble = None
        self._awaiting_response = False
        self._set_input_enabled(True)
        self._add_welcome_message()

    def on_ai_error(self) -> None:
        """Called when AI returns an error — re-enable input."""
        self._timeout_timer.stop()
        self._remove_thinking_bubble()
        self._set_input_enabled(True)

    # ── Private ──────────────────────────────────────────────────────────────

    def _append(self, message: ChatMessage) -> None:
        self._messages.append(message)

        # Cap message count
        while len(self._messages) > self._MAX_MESSAGES:
            self._messages.pop(0)
            item = self._chat_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        bubble = ChatBubble(message, self._chat_container)
        # Insert before the stretch
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)

        # Deferred scroll — wait for layout to update before scrolling
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _show_thinking_bubble(self) -> None:
        """Insert an animated 'thinking…' placeholder."""
        if self._thinking_bubble:
            return
        thinking_msg = ChatMessage(role=MessageRole.AI, text="Thinking…")
        bubble = ChatBubble(thinking_msg, self._chat_container)
        bubble.setObjectName("aiThinkingBubble")
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
        self._thinking_bubble = bubble
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _remove_thinking_bubble(self) -> None:
        if self._thinking_bubble:
            self._thinking_bubble.setParent(None)  # type: ignore[arg-type]
            self._thinking_bubble.deleteLater()
            self._thinking_bubble = None

    def _set_input_enabled(self, enabled: bool) -> None:
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)
        if enabled:
            self._awaiting_response = False

    def _on_quick_chat(self, cmd: str) -> None:
        """Send a quick-action expanded prompt through the regular chat path."""
        if self._awaiting_response:
            return
        prompt = _QUICK_PROMPTS.get(cmd, cmd)
        # Show a short user label (not the full expanded prompt)
        label = cmd.capitalize()
        self._append(ChatMessage(role=MessageRole.USER, text=f"[{label}]"))
        self._awaiting_response = True
        self._set_input_enabled(False)
        self._show_thinking_bubble()
        self._timeout_timer.start()
        self.quick_action.emit(prompt)

    def _on_send(self) -> None:
        if self._awaiting_response:
            return
        text = self._input.text().strip()
        if text:
            self.add_user_message(text)
            self._input.clear()
            self._awaiting_response = True
            self._set_input_enabled(False)
            self._show_thinking_bubble()
            self._timeout_timer.start()
            self.message_sent.emit(text)

    def _on_response_timeout(self) -> None:
        """Called if no AI response arrives within _RESPONSE_TIMEOUT_MS."""
        self._remove_thinking_bubble()
        self.add_system_message(
            "⚠ No response received. "
            "Check your API key in Settings or try again."
        )
        self._set_input_enabled(True)
