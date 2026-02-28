"""Background worker for AI analysis tasks.

Follows the standard CyberFlash worker pattern: ``BaseWorker`` subclass that
is moved to a ``QThread`` via ``moveToThread()``.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal, Slot

from cyberflash.core.ai_engine import (
    ActionCategory,
    AIEngine,
)
from cyberflash.core.device_analyzer import DeviceAnalyzer
from cyberflash.core.gemini_client import _BUILTIN_API_KEY, GeminiClient
from cyberflash.core.workflow_engine import WorkflowEngine
from cyberflash.models.device import DeviceInfo
from cyberflash.services.config_service import ConfigService
from cyberflash.workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class AIWorker(BaseWorker):
    """Runs AI analysis off the main thread.

    Signals:
        insights_ready(list)   — DeviceInsight list after device analysis
        health_ready(object)   — DeviceHealthReport after full health check
        recommendations_ready(list) — Recommendation list
        risk_ready(object)     — RiskAssessment for a specific action
        chat_response(str)     — AI answer to a user query
        workflow_ready(object) — Generated Workflow plan
    """

    insights_ready = Signal(list)  # list[DeviceInsight]
    health_ready = Signal(object)  # DeviceHealthReport
    recommendations_ready = Signal(list)  # list[Recommendation]
    risk_ready = Signal(object)  # RiskAssessment
    chat_response = Signal(str)
    workflow_ready = Signal(object)  # Workflow
    rom_scored = Signal(object)  # RomScore

    def __init__(self) -> None:
        super().__init__()
        self._engine = AIEngine()
        self._analyzer = DeviceAnalyzer()
        self._workflow_engine = WorkflowEngine()
        self._gemini: GeminiClient | None = self._build_gemini_client()

    def _build_gemini_client(self) -> GeminiClient | None:
        """Build a GeminiClient from stored config, falling back to built-in key."""
        config = ConfigService.instance()
        api_key = config.get_str("ai/gemini_api_key") or _BUILTIN_API_KEY
        model = config.get_str("ai/gemini_model") or "gemini-2.5-flash"
        client = GeminiClient(api_key=api_key, model=model)
        if client.is_configured():
            logger.info("Gemini AI enabled with model=%s", model)
            return client
        return None

    @Slot()
    def reload_gemini(self) -> None:
        """Re-read API key from config (called after settings change)."""
        self._gemini = self._build_gemini_client()
        if self._gemini:
            logger.info("GeminiClient reloaded successfully")
        else:
            logger.info("GeminiClient cleared (no API key)")

    # ── Slot: analyse device ─────────────────────────────────────────────────

    @Slot(object)
    def analyze_device(self, device: DeviceInfo) -> None:
        """Run full device analysis and emit insights."""
        try:
            insights = self._engine.analyze_device(device)
            self.insights_ready.emit(insights)
        except Exception as exc:
            logger.exception("AI analyze_device failed")
            self.error.emit(str(exc))

    @Slot(object)
    def run_health_check(self, device: DeviceInfo) -> None:
        """Run a comprehensive health check and emit the report."""
        try:
            report = self._analyzer.analyze(device)
            self.health_ready.emit(report)
        except Exception as exc:
            logger.exception("AI health_check failed")
            self.error.emit(str(exc))

    # ── Slot: get recommendations ────────────────────────────────────────────

    @Slot(object, str)
    def get_recommendations(self, device: DeviceInfo | None, page: str) -> None:
        """Generate recommendations for the current context."""
        try:
            recs = self._engine.get_recommendations(device, page)
            self.recommendations_ready.emit(recs)
        except Exception as exc:
            logger.exception("AI get_recommendations failed")
            self.error.emit(str(exc))

    # ── Slot: assess risk ────────────────────────────────────────────────────

    @Slot(str, object)
    def assess_risk(self, action: str, device: DeviceInfo | None) -> None:
        """Assess risk for a given action category."""
        try:
            category = ActionCategory(action)
            assessment = self._engine.assess_risk(category, device)
            self.risk_ready.emit(assessment)
        except Exception as exc:
            logger.exception("AI assess_risk failed")
            self.error.emit(str(exc))

    # ── Slot: answer chat query ──────────────────────────────────────────────

    @Slot(str, object, str)
    def answer_query(
        self,
        query: str,
        device: DeviceInfo | None,
        page: str,
    ) -> None:
        """Process a chat query — uses Gemini if configured, else local engine."""
        try:
            # Try Gemini first
            if self._gemini and self._gemini.is_configured():
                device_ctx = ""
                if device:
                    device_ctx = (
                        f"{device.display_name} (serial={device.serial}, "
                        f"state={device.state.label}, "
                        f"android={device.android_version or 'unknown'}, "
                        f"bootloader={'unlocked' if device.bootloader_unlocked else 'locked'}, "
                        f"battery={device.battery_level}%)"
                    )
                try:
                    response = self._gemini.chat(query, device_context=device_ctx, page=page)
                    self.chat_response.emit(response)
                    return
                except Exception as gemini_exc:
                    logger.warning("Gemini call failed, falling back to local: %s", gemini_exc)

            # Local heuristic fallback
            response = self._engine.answer_query(query, device, page)
            self.chat_response.emit(response)
        except Exception as exc:
            logger.exception("AI answer_query failed")
            self.error.emit(str(exc))

    # ── Slot: score ROM release ──────────────────────────────────────────────

    @Slot(object, object)
    def score_rom(self, release: object, profile: object) -> None:
        """Score a RomRelease and emit the RomScore result."""
        try:
            from cyberflash.core.rom_ai_scorer import RomAiScorer

            scorer = RomAiScorer()
            score = scorer.score_release(release, profile, self._gemini)
            self.rom_scored.emit(score)
        except Exception as exc:
            logger.exception("AI score_rom failed")
            self.error.emit(str(exc))

    # ── Slot: plan workflow ──────────────────────────────────────────────────

    @Slot(str, object)
    def plan_workflow(self, workflow_type: str, device: DeviceInfo) -> None:
        """Generate a workflow plan."""
        try:
            if workflow_type == "flash":
                wf = self._engine.plan_flash_workflow(device)
            elif workflow_type == "root":
                wf = self._engine.plan_root_workflow(device)
            elif workflow_type == "rescue":
                wf = self._workflow_engine.plan_rescue(device)
            elif workflow_type == "nethunter":
                wf = self._workflow_engine.plan_nethunter_install(device)
            elif workflow_type == "full_flash":
                wf = self._workflow_engine.plan_full_flash(
                    device,
                    has_backup=False,
                    needs_unlock=device.bootloader_unlocked is False,
                )
            else:
                self.error.emit(f"Unknown workflow type: {workflow_type}")
                return

            self.workflow_ready.emit(wf)
        except Exception as exc:
            logger.exception("AI plan_workflow failed")
            self.error.emit(str(exc))
