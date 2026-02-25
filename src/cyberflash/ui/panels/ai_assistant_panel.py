"""Slide-out AI assistant panel with chat, insights, recommendations, and workflows.

This panel docks on the right side of the main window and provides a
comprehensive AI-powered interface for device management guidance.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cyberflash.core.ai_engine import (
    DeviceInsight,
    InsightSeverity,
    Recommendation,
    RiskAssessment,
    RiskLevel,
    Workflow,
)
from cyberflash.core.device_analyzer import DeviceHealthReport
from cyberflash.services.config_service import ConfigService
from cyberflash.ui.widgets.ai_chat_widget import AIChatWidget
from cyberflash.ui.widgets.cyber_card import CyberCard

if TYPE_CHECKING:
    from cyberflash.services.ai_service import AIService

logger = logging.getLogger(__name__)

_PANEL_WIDTH = 380
_COLLAPSED_WIDTH = 0


class AIAssistantPanel(QWidget):
    """Collapsible AI assistant panel with tabs for Chat, Insights, and Workflows.

    Signals:
        panel_toggled(bool) — emitted when panel opens/closes
    """

    panel_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aiAssistantPanel")
        self.setFixedWidth(_COLLAPSED_WIDTH)
        self._expanded = False
        self._ai_service: AIService | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────────────
        header = QWidget()
        header.setObjectName("aiPanelHeader")
        header.setFixedHeight(44)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 0, 8, 0)

        ai_icon = QLabel("⚡")
        ai_icon.setObjectName("aiPanelIcon")
        h_layout.addWidget(ai_icon)

        title = QLabel("CyberFlash AI")
        title.setObjectName("aiPanelTitle")
        h_layout.addWidget(title)
        h_layout.addStretch()

        # Privacy / engine badge — updates when Gemini key is configured
        self._privacy_label = QLabel("LOCAL")
        self._privacy_label.setObjectName("aiPrivacyBadge")
        self._privacy_label.setToolTip("All AI processing runs locally — no data leaves this app")
        h_layout.addWidget(self._privacy_label)
        self._refresh_engine_badge()

        close_btn = QPushButton("✕")
        close_btn.setObjectName("aiPanelClose")
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self.toggle)
        h_layout.addWidget(close_btn)

        layout.addWidget(header)

        # ── Tab widget ───────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setObjectName("aiTabs")

        # Tab 1: Chat
        self._chat = AIChatWidget()
        self._tabs.addTab(self._chat, "Chat")

        # Tab 2: Insights
        self._insights_tab = self._build_insights_tab()
        self._tabs.addTab(self._insights_tab, "Insights")

        # Tab 3: Workflows
        self._workflows_tab = self._build_workflows_tab()
        self._tabs.addTab(self._workflows_tab, "Workflows")

        layout.addWidget(self._tabs, 1)

    # ── Insights tab ─────────────────────────────────────────────────────────

    def _build_insights_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Health score card
        self._health_card = CyberCard()
        hc_layout = self._health_card.card_layout()

        health_header = QHBoxLayout()
        health_title = QLabel("Device Health")
        health_title.setObjectName("sectionLabel")
        health_header.addWidget(health_title)
        health_header.addStretch()
        self._health_grade_label = QLabel("—")
        self._health_grade_label.setObjectName("aiHealthGrade")
        health_header.addWidget(self._health_grade_label)
        hc_layout.addLayout(health_header)

        self._health_bar = QProgressBar()
        self._health_bar.setObjectName("aiHealthBar")
        self._health_bar.setRange(0, 100)
        self._health_bar.setValue(0)
        self._health_bar.setTextVisible(True)
        self._health_bar.setFormat("%v%")
        hc_layout.addWidget(self._health_bar)

        self._health_details = QLabel("Connect a device to see health analysis")
        self._health_details.setObjectName("aiHealthDetails")
        self._health_details.setWordWrap(True)
        hc_layout.addWidget(self._health_details)

        scan_btn = QPushButton("Run Health Scan")
        scan_btn.setObjectName("primaryButton")
        scan_btn.clicked.connect(self._on_run_health_scan)
        hc_layout.addWidget(scan_btn)

        layout.addWidget(self._health_card)

        # Insights list (scrollable)
        insights_scroll = QScrollArea()
        insights_scroll.setWidgetResizable(True)
        insights_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._insights_container = QWidget()
        self._insights_layout = QVBoxLayout(self._insights_container)
        self._insights_layout.setContentsMargins(0, 0, 0, 0)
        self._insights_layout.setSpacing(6)
        self._insights_layout.addStretch()

        insights_scroll.setWidget(self._insights_container)
        layout.addWidget(insights_scroll, 1)

        # Recommendations section
        rec_label = QLabel("Recommendations")
        rec_label.setObjectName("sectionLabel")
        layout.addWidget(rec_label)

        self._rec_container = QWidget()
        self._rec_layout = QVBoxLayout(self._rec_container)
        self._rec_layout.setContentsMargins(0, 0, 0, 0)
        self._rec_layout.setSpacing(4)

        rec_scroll = QScrollArea()
        rec_scroll.setWidgetResizable(True)
        rec_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rec_scroll.setWidget(self._rec_container)
        rec_scroll.setMaximumHeight(200)
        layout.addWidget(rec_scroll)

        return tab

    # ── Workflows tab ────────────────────────────────────────────────────────

    def _build_workflows_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        desc = QLabel(
            "AI-generated step-by-step workflows for common operations. "
            "Select a workflow type to get a guided plan."
        )
        desc.setWordWrap(True)
        desc.setObjectName("aiWorkflowDesc")
        layout.addWidget(desc)

        # Workflow buttons
        workflows = [
            ("Plan Full Flash", "full_flash", "Complete flash workflow with all safety steps"),
            ("Plan Root", "root", "Magisk root installation workflow"),
            ("Plan Rescue", "rescue", "Device recovery/unbrick workflow"),
            ("Plan NetHunter", "nethunter", "Kali NetHunter installation workflow"),
        ]

        for label, wf_type, tooltip in workflows:
            btn = QPushButton(label)
            btn.setObjectName("aiWorkflowButton")
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda _c=False, t=wf_type: self._on_plan_workflow(t))
            layout.addWidget(btn)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("aiSeparator")
        layout.addWidget(sep)

        # Active workflow display
        self._workflow_card = CyberCard()
        wf_layout = self._workflow_card.card_layout()

        self._wf_title = QLabel("No active workflow")
        self._wf_title.setObjectName("sectionLabel")
        wf_layout.addWidget(self._wf_title)

        self._wf_progress = QProgressBar()
        self._wf_progress.setObjectName("aiWorkflowProgress")
        self._wf_progress.setRange(0, 100)
        self._wf_progress.setValue(0)
        wf_layout.addWidget(self._wf_progress)

        # Steps container
        self._steps_container = QWidget()
        self._steps_layout = QVBoxLayout(self._steps_container)
        self._steps_layout.setContentsMargins(0, 0, 0, 0)
        self._steps_layout.setSpacing(4)
        wf_layout.addWidget(self._steps_container)

        layout.addWidget(self._workflow_card)
        layout.addStretch()

        return tab

    # ── Service binding ──────────────────────────────────────────────────────

    def _refresh_engine_badge(self) -> None:
        """Update badge to show GEMINI or LOCAL based on config."""
        config = ConfigService.instance()
        key = config.get_str("ai/gemini_api_key")
        if key:
            model = config.get_str("ai/gemini_model") or "gemini-2.5-flash"
            short = model.replace("gemini-", "").replace("-", " ").upper()
            self._privacy_label.setText(f"GEMINI · {short}")
            self._privacy_label.setToolTip(
                f"Using Google Gemini API ({model})\n"
                "Queries are sent to Google — see privacy policy."
            )
        else:
            self._privacy_label.setText("LOCAL")
            self._privacy_label.setToolTip(
                "All AI processing runs locally — no data leaves this app"
            )

    def set_service(self, service: AIService) -> None:
        """Bind the AI service and connect signals."""
        self._ai_service = service

        # Refresh badge after service is bound (config is available)
        self._refresh_engine_badge()

        # Chat → service: regular messages and expanded quick-action prompts
        self._chat.message_sent.connect(service.ask)
        self._chat.quick_action.connect(service.ask)

        # Quick action specials: risk and health have dedicated service methods
        self._chat.assess_risk_requested.connect(self._on_assess_risk_clicked)
        self._chat.health_scan_requested.connect(self._on_health_scan_clicked)

        # Service → chat
        service.chat_reply.connect(self._chat.add_ai_message)
        service.ai_error.connect(self._chat.on_ai_error)

        # Insight signals
        service.insights_updated.connect(self._on_insights_updated)
        service.health_updated.connect(self._on_health_updated)
        service.recommendations_updated.connect(self._on_recommendations_updated)
        service.risk_assessed.connect(self._on_risk_assessed)
        service.workflow_planned.connect(self._on_workflow_planned)
        service.ai_error.connect(self._on_error)

        # Automation signals
        if hasattr(service, "command_completed"):
            service.command_completed.connect(self._on_command_completed)
        if hasattr(service, "preflight_completed"):
            service.preflight_completed.connect(self._on_preflight_completed)
        if hasattr(service, "health_metrics_ready"):
            service.health_metrics_ready.connect(self._on_health_metrics_ready)

        # When config changes (key saved) refresh badge live
        ConfigService.instance().value_changed.connect(self._on_config_changed)

    # ── Config-change slot ────────────────────────────────────────────────────

    @Slot(str, object)
    def _on_config_changed(self, key: str, _value: object) -> None:
        if key in ("ai/gemini_api_key", "ai/gemini_model"):
            self._refresh_engine_badge()

    # ── Toggle animation ─────────────────────────────────────────────────────

    def toggle(self) -> None:
        """Animate the panel open/closed."""
        self._expanded = not self._expanded
        target = _PANEL_WIDTH if self._expanded else _COLLAPSED_WIDTH

        self._animation = QPropertyAnimation(self, b"maximumWidth")
        self._animation.setDuration(250)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._animation.setStartValue(self.width())
        self._animation.setEndValue(target)
        self._animation.start()

        # Also animate min width to keep things in sync
        self._min_anim = QPropertyAnimation(self, b"minimumWidth")
        self._min_anim.setDuration(250)
        self._min_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._min_anim.setStartValue(self.width())
        self._min_anim.setEndValue(target)
        self._min_anim.start()

        self.panel_toggled.emit(self._expanded)

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    # ── Signal handlers ──────────────────────────────────────────────────────

    @Slot(list)
    def _on_insights_updated(self, insights: list[DeviceInsight]) -> None:
        # Clear old insights
        while self._insights_layout.count() > 1:
            item = self._insights_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for insight in insights:
            card = self._create_insight_card(insight)
            self._insights_layout.insertWidget(self._insights_layout.count() - 1, card)

    @Slot(object)
    def _on_health_updated(self, report: DeviceHealthReport) -> None:
        self._health_bar.setValue(report.score)
        self._health_grade_label.setText(report.grade.value.upper())
        self._health_grade_label.setProperty("grade", report.grade.value)
        self._health_grade_label.style().unpolish(self._health_grade_label)
        self._health_grade_label.style().polish(self._health_grade_label)

        details = f"{report.passed_count}/{report.total_count} checks passed\n"
        if report.recommended_actions:
            details += "\nRecommended:\n"
            details += "\n".join(f"• {a}" for a in report.recommended_actions)
        self._health_details.setText(details)

    @Slot(list)
    def _on_recommendations_updated(self, recs: list[Recommendation]) -> None:
        # Clear old recommendations
        while self._rec_layout.count():
            item = self._rec_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for rec in recs[:6]:  # cap at 6 to avoid overflow
            widget = self._create_recommendation_widget(rec)
            self._rec_layout.addWidget(widget)

    @Slot(object)
    def _on_risk_assessed(self, assessment: RiskAssessment) -> None:
        msg = f"**Risk Assessment: {assessment.level.label}**\n\n"
        msg += f"{assessment.summary}\n\n"
        if assessment.factors:
            msg += "**Factors:**\n"
            msg += "\n".join(f"• {f}" for f in assessment.factors)
            msg += "\n\n"
        if assessment.mitigations:
            msg += "**Mitigations:**\n"
            msg += "\n".join(f"• {m}" for m in assessment.mitigations)
        if assessment.blocked:
            msg += "\n\n🛑 **Operation blocked** — resolve the above issues first."
        self._chat.add_ai_message(msg)

    @Slot(object)
    def _on_workflow_planned(self, workflow: Workflow) -> None:
        self._wf_title.setText(workflow.name)
        self._wf_progress.setValue(int(workflow.progress * 100))

        # Clear old steps
        while self._steps_layout.count():
            item = self._steps_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for step in workflow.steps:
            step_widget = self._create_step_widget(step)
            self._steps_layout.addWidget(step_widget)

        # Also announce in chat
        msg = f"**Workflow: {workflow.name}**\n\n{workflow.description}\n\n"
        msg += "**Steps:**\n"
        for step in workflow.steps:
            risk_str = f" [{step.risk.label}]" if step.risk != RiskLevel.NONE else ""
            skip_str = " (optional)" if step.skippable else ""
            msg += f"{step.step_id}. {step.title}{risk_str}{skip_str}\n"
        self._chat.add_ai_message(msg)

        # Switch to workflows tab
        self._tabs.setCurrentIndex(2)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._chat.add_system_message(f"Error: {message}")

    # ── Widget builders ──────────────────────────────────────────────────────

    def _create_insight_card(self, insight: DeviceInsight) -> QWidget:
        card = QFrame()
        card.setObjectName("aiInsightCard")
        card.setProperty("severity", insight.severity.value)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        icon = self._severity_icon(insight.severity)
        icon_label = QLabel(icon)
        icon_label.setObjectName("aiInsightIcon")
        header.addWidget(icon_label)

        title = QLabel(insight.title)
        title.setObjectName("aiInsightTitle")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        msg = QLabel(insight.message)
        msg.setWordWrap(True)
        msg.setObjectName("aiInsightMessage")
        layout.addWidget(msg)

        if insight.action_hint:
            hint = QLabel(f"→ {insight.action_hint}")
            hint.setObjectName("aiInsightHint")
            layout.addWidget(hint)

        return card

    def _create_recommendation_widget(self, rec: Recommendation) -> QWidget:
        widget = QFrame()
        widget.setObjectName("aiRecCard")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # Priority indicator
        dot = QLabel("●")
        dot.setObjectName("aiRecDot")
        dot.setProperty(
            "risk",
            "high"
            if rec.risk >= RiskLevel.HIGH
            else "medium"
            if rec.risk >= RiskLevel.MEDIUM
            else "low",
        )
        layout.addWidget(dot)

        text_layout = QVBoxLayout()
        title = QLabel(rec.title)
        title.setObjectName("aiRecTitle")
        text_layout.addWidget(title)
        desc = QLabel(rec.description)
        desc.setWordWrap(True)
        desc.setObjectName("aiRecDesc")
        text_layout.addWidget(desc)
        layout.addLayout(text_layout, 1)

        return widget

    def _create_step_widget(self, step) -> QWidget:
        """Build a single workflow step display widget with execute button."""
        widget = QFrame()
        widget.setObjectName("aiStepCard")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # Status indicator
        mark = "\u2713" if step.completed else f"{step.step_id}"
        indicator = QLabel(mark)
        indicator.setObjectName("aiStepIndicator")
        indicator.setProperty("completed", "true" if step.completed else "false")
        indicator.setFixedSize(24, 24)
        indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(indicator)

        text_layout = QVBoxLayout()
        title = QLabel(step.title)
        title.setObjectName("aiStepTitle")
        text_layout.addWidget(title)
        desc = QLabel(step.description)
        desc.setWordWrap(True)
        desc.setObjectName("aiStepDesc")
        text_layout.addWidget(desc)
        layout.addLayout(text_layout, 1)

        if step.risk != RiskLevel.NONE:
            risk_badge = QLabel(step.risk.label)
            risk_badge.setObjectName("aiStepRisk")
            risk_badge.setProperty("level", step.risk.label.lower())
            layout.addWidget(risk_badge)

        # Execute button — only if step is not completed and has a command
        if not step.completed and hasattr(step, "command") and step.command:
            exec_btn = QPushButton("\u25b6")
            exec_btn.setObjectName("aiStepExecBtn")
            exec_btn.setToolTip(f"Execute: {step.title}")
            exec_btn.setFixedSize(28, 28)
            exec_btn.clicked.connect(lambda _c=False, s=step: self._execute_workflow_step(s))
            layout.addWidget(exec_btn)
        elif not step.completed:
            # Generic execute button for non-command steps
            exec_btn = QPushButton("\u25b6")
            exec_btn.setObjectName("aiStepExecBtn")
            exec_btn.setToolTip(f"Execute: {step.title}")
            exec_btn.setFixedSize(28, 28)
            exec_btn.clicked.connect(lambda _c=False, s=step: self._execute_workflow_step(s))
            layout.addWidget(exec_btn)

        return widget

    @staticmethod
    def _severity_icon(severity: InsightSeverity) -> str:
        return {
            InsightSeverity.INFO: "(i)",
            InsightSeverity.TIP: "💡",
            InsightSeverity.WARNING: "⚠",
            InsightSeverity.CRITICAL: "🛑",
        }[severity]

    # ── Callbacks from panel buttons ─────────────────────────────────────────

    def _on_assess_risk_clicked(self) -> None:
        """Risk quick-action: run risk assessment for current device/page context."""
        if not self._ai_service:
            self._chat.add_system_message("No AI service connected.")
            return
        page = self._ai_service.current_page
        # Map page name → action category understood by AIEngine
        page_to_action: dict[str, str] = {
            "flash": "flash",
            "root": "root",
            "backup": "backup",
            "partition": "partition",
            "rescue": "rescue",
            "nethunter": "nethunter",
            "diagnostics": "diagnostics",
        }
        action = page_to_action.get(page, "general")
        self._chat.add_system_message(f"Assessing risk for: {action}…")
        self._ai_service.assess_risk(action)

    def _on_health_scan_clicked(self) -> None:
        """Health quick-action: collect metrics and run health check."""
        if not self._ai_service:
            self._chat.add_system_message("No AI service connected.")
            return
        self._chat.add_system_message("Running device health scan and metrics…")
        self._ai_service.collect_health_metrics()
        self._ai_service.run_health_check()
        # Switch to Insights tab so user sees results
        self._tabs.setCurrentIndex(1)

    def _on_run_health_scan(self) -> None:
        if self._ai_service:
            self._ai_service.run_health_check()
            self._chat.add_system_message("Running device health scan...")

    def _on_plan_workflow(self, workflow_type: str) -> None:
        if self._ai_service:
            self._ai_service.plan_workflow(workflow_type)

    # ── Automation handlers ──────────────────────────────────────────────────

    def _execute_workflow_step(self, step) -> None:
        """Execute a workflow step via the AI service automation layer."""
        if not self._ai_service:
            return

        from PySide6.QtWidgets import QMessageBox

        # Confirm execution of risky steps
        if hasattr(step, "risk") and step.risk >= RiskLevel.HIGH:
            reply = QMessageBox.warning(
                self,
                "High Risk Step",
                f"Step: {step.title}\n"
                f"Risk Level: {step.risk.label}\n\n"
                f"{step.description}\n\nProceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._chat.add_system_message(f"Executing: {step.title}\u2026")

        # Determine command from step
        cmd = getattr(step, "command", "") or step.title.lower()
        if "reboot" in cmd:
            mode = "system"
            if "bootloader" in cmd or "fastboot" in cmd:
                mode = "bootloader"
            elif "recovery" in cmd:
                mode = "recovery"
            self._ai_service.execute_reboot(mode)
        elif "preflight" in cmd or "check" in cmd:
            self._ai_service.run_preflight("flash")
        elif "shell" in cmd:
            self._ai_service.execute_shell(cmd, 30)
        else:
            self._chat.add_system_message(
                f"Step '{step.title}' requires manual execution on the appropriate page."
            )

    @Slot(object)
    def _on_command_completed(self, result) -> None:
        """Handle command completion from the automation worker."""
        status = getattr(result, "status", "unknown")
        cmd_type = getattr(result, "command_type", "command")
        output = getattr(result, "output", "")
        elapsed = getattr(result, "elapsed_str", "")

        if str(status) == "completed":
            msg = f"\u2705 **{cmd_type}** completed"
            if elapsed:
                msg += f" ({elapsed})"
            if output:
                msg += f"\n```\n{output[:500]}\n```"
        else:
            msg = f"\u274c **{cmd_type}** failed"
            if output:
                msg += f": {output[:300]}"

        self._chat.add_system_message(msg)

    @Slot(object)
    def _on_preflight_completed(self, result) -> None:
        """Handle preflight check results."""
        passed = getattr(result, "passed", False)
        summary = getattr(result, "summary", "")
        checks = getattr(result, "checks", [])

        if passed:
            msg = f"\u2705 **Preflight passed**: {summary}"
        else:
            msg = "\u26a0\ufe0f **Preflight issues**:\n"
            for check in checks:
                status_icon = {
                    "pass": "\u2705",
                    "warn": "\u26a0\ufe0f",
                    "fail": "\u274c",
                    "skip": "\u23ed",
                }.get(str(getattr(check, "status", "")), "\u2753")
                msg += f"{status_icon} {check.name}: {check.message}\n"

        self._chat.add_system_message(msg)

    @Slot(dict)
    def _on_health_metrics_ready(self, metrics: dict) -> None:
        """Display real-time health metrics in the chat."""
        parts = []
        if "battery" in metrics:
            parts.append(f"\U0001f50b Battery: {metrics['battery']}%")
        if "cpu_temp" in metrics:
            parts.append(f"\U0001f321 CPU: {metrics['cpu_temp']}\u00b0C")
        if "ram" in metrics:
            parts.append(f"\U0001f4be RAM: {metrics['ram']}")
        if "uptime" in metrics:
            parts.append(f"\u23f0 Uptime: {metrics['uptime']}")

        if parts:
            self._chat.add_system_message("**Device Metrics**: " + " | ".join(parts))
