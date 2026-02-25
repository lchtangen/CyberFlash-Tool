"""AI service — owns AI + automation worker threads and exposes high-level signals.

Follows the same pattern as :class:`DeviceService` and :class:`RomLinkService`:
a ``QObject`` that owns ``QThread`` + ``BaseWorker`` pairs, provides convenience
methods, and re-emits worker signals for the UI layer.

Enhanced with command execution, pre-flight checks, logcat streaming, and
device health monitoring via the :class:`AutomationWorker`.

Cross-thread calls use Qt Signals (not QMetaObject.invokeMethod) — signals with
AutoConnection automatically queue across thread boundaries, which is safer and
more reliable when passing Python objects.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from cyberflash.models.device import DeviceInfo
from cyberflash.services.config_service import ConfigService
from cyberflash.workers.ai_worker import AIWorker
from cyberflash.workers.automation_worker import AutomationWorker

logger = logging.getLogger(__name__)


class AIService(QObject):
    """Service layer for the CyberFlash AI assistant and automation engine.

    Connect to:
        insights_updated(list)    — list[DeviceInsight]
        health_updated(object)    — DeviceHealthReport
        recommendations_updated(list) — list[Recommendation]
        risk_assessed(object)     — RiskAssessment
        chat_reply(str)           — AI text response
        workflow_planned(object)  — Workflow
        ai_error(str)             — error message

    Automation signals:
        command_completed(object)  — CommandResult after execution
        preflight_completed(object) — PreflightResult after checks
        logcat_output(str)         — Single logcat line
        logcat_ended()             — Logcat streaming stopped
        health_metrics_ready(dict) — Device health metrics
        audit_updated(list)        — Updated command audit trail
    """

    # ── Public AI signals ─────────────────────────────────────────────────────
    insights_updated = Signal(list)
    health_updated = Signal(object)
    recommendations_updated = Signal(list)
    risk_assessed = Signal(object)
    chat_reply = Signal(str)
    workflow_planned = Signal(object)
    ai_error = Signal(str)

    # ── Public automation signals ─────────────────────────────────────────────
    command_completed = Signal(object)   # CommandResult
    preflight_completed = Signal(object)  # PreflightResult
    logcat_output = Signal(str)
    logcat_ended = Signal()
    health_metrics_ready = Signal(dict)
    audit_updated = Signal(list)

    # ── Private cross-thread request signals → AI worker ─────────────────────
    # These are connected to worker slots in start() with AutoConnection.
    # Qt automatically uses QueuedConnection when signal and slot live on
    # different threads, making this the safe way to invoke worker methods.
    _sig_analyze_device = Signal(object)
    _sig_health_check = Signal(object)
    _sig_get_recommendations = Signal(object, str)
    _sig_assess_risk = Signal(str, object)
    _sig_answer_query = Signal(str, object, str)
    _sig_plan_workflow = Signal(str, object)
    _sig_reload_gemini = Signal()

    # ── Private cross-thread request signals → automation worker ──────────────
    _sig_auto_set_device = Signal(object)
    _sig_run_preflight = Signal(str)
    _sig_run_preflight_flash = Signal(str, str)
    _sig_execute_reboot = Signal(str)
    _sig_execute_shell = Signal(str, int)
    _sig_execute_slot_switch = Signal(str)
    _sig_execute_erase = Signal(str)
    _sig_execute_flash_partition = Signal(str, str)
    _sig_execute_get_info = Signal()
    _sig_execute_get_slot_info = Signal()
    _sig_collect_health = Signal()
    _sig_start_logcat = Signal(str)
    _sig_stop_logcat = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: AIWorker | None = None
        self._auto_thread: QThread | None = None
        self._auto_worker: AutomationWorker | None = None
        self._current_device: DeviceInfo | None = None
        self._current_page: str = "dashboard"

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the AI and automation worker threads."""
        # ── AI worker ──────────────────────────────────────────────────────
        self._thread = QThread(self)
        self._worker = AIWorker()
        self._worker.moveToThread(self._thread)

        # Forward worker output signals → service public signals
        self._worker.insights_ready.connect(self.insights_updated)
        self._worker.health_ready.connect(self.health_updated)
        self._worker.recommendations_ready.connect(self.recommendations_updated)
        self._worker.risk_ready.connect(self.risk_assessed)
        self._worker.chat_response.connect(self.chat_reply)
        self._worker.workflow_ready.connect(self.workflow_planned)
        self._worker.error.connect(self.ai_error)

        # Wire private request signals → worker slots (auto-queued cross-thread)
        self._sig_analyze_device.connect(self._worker.analyze_device)
        self._sig_health_check.connect(self._worker.run_health_check)
        self._sig_get_recommendations.connect(self._worker.get_recommendations)
        self._sig_assess_risk.connect(self._worker.assess_risk)
        self._sig_answer_query.connect(self._worker.answer_query)
        self._sig_plan_workflow.connect(self._worker.plan_workflow)
        self._sig_reload_gemini.connect(self._worker.reload_gemini)

        self._thread.start()

        # Reload Gemini whenever the API key or model is saved in Settings
        config = ConfigService.instance()
        config.value_changed.connect(self._on_config_changed)

        # ── Automation worker ──────────────────────────────────────────────
        self._auto_thread = QThread(self)
        self._auto_worker = AutomationWorker()
        self._auto_worker.moveToThread(self._auto_thread)

        self._auto_worker.command_result.connect(self.command_completed)
        self._auto_worker.preflight_result.connect(self.preflight_completed)
        self._auto_worker.logcat_line.connect(self.logcat_output)
        self._auto_worker.logcat_stopped.connect(self.logcat_ended)
        self._auto_worker.health_metrics.connect(self.health_metrics_ready)
        self._auto_worker.audit_log.connect(self.audit_updated)
        self._auto_worker.error.connect(self.ai_error)

        # Wire private request signals → automation worker slots
        self._sig_auto_set_device.connect(self._auto_worker.set_device)
        self._sig_run_preflight.connect(self._auto_worker.run_preflight)
        self._sig_run_preflight_flash.connect(self._auto_worker.run_preflight_flash)
        self._sig_execute_reboot.connect(self._auto_worker.execute_reboot)
        self._sig_execute_shell.connect(self._auto_worker.execute_shell)
        self._sig_execute_slot_switch.connect(self._auto_worker.execute_slot_switch)
        self._sig_execute_erase.connect(self._auto_worker.execute_erase)
        self._sig_execute_flash_partition.connect(self._auto_worker.execute_flash_partition)
        self._sig_execute_get_info.connect(self._auto_worker.execute_get_info)
        self._sig_execute_get_slot_info.connect(self._auto_worker.execute_get_slot_info)
        self._sig_collect_health.connect(self._auto_worker.collect_health_metrics)
        self._sig_start_logcat.connect(self._auto_worker.start_logcat)
        self._sig_stop_logcat.connect(self._auto_worker.stop_logcat)

        self._auto_thread.start()

        logger.info("AIService started (AI + Automation workers)")

        # If a device was selected before start() was called, trigger analysis now.
        # Use a short delay so the worker event loop is guaranteed to be running.
        if self._current_device is not None:
            QTimer.singleShot(500, self._deferred_initial_analysis)

    def stop(self) -> None:
        """Stop all worker threads."""
        self._sig_stop_logcat.emit()
        if self._auto_thread:
            self._auto_thread.quit()
            self._auto_thread.wait(3000)
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        logger.info("AIService stopped")

    # ── Context management ───────────────────────────────────────────────────

    @Slot(object)
    def set_device(self, device: DeviceInfo | None) -> None:
        """Update the current device context and trigger analysis."""
        self._current_device = device

        if device:
            if self._auto_worker:
                self._sig_auto_set_device.emit(device)
            if self._worker:
                self._sig_analyze_device.emit(device)
                self._sig_get_recommendations.emit(device, self._current_page)

    @Slot(str)
    def set_current_page(self, page: str) -> None:
        """Update the current page context and refresh recommendations."""
        self._current_page = page
        if self._worker and self._current_device is not None:
            self._sig_get_recommendations.emit(self._current_device, page)

    # ── AI actions ───────────────────────────────────────────────────────────

    def ask(self, query: str) -> None:
        """Send a chat query to the AI."""
        if self._worker:
            self._sig_answer_query.emit(query, self._current_device, self._current_page)

    def run_health_check(self) -> None:
        """Request a full device health check."""
        if self._current_device and self._worker:
            self._sig_health_check.emit(self._current_device)

    def assess_risk(self, action: str) -> None:
        """Request a risk assessment for a specific action category."""
        if self._worker:
            self._sig_assess_risk.emit(action, self._current_device)

    def plan_workflow(self, workflow_type: str) -> None:
        """Request a workflow plan for an operation type."""
        if self._current_device and self._worker:
            self._sig_plan_workflow.emit(workflow_type, self._current_device)

    def refresh_recommendations(self) -> None:
        """Explicitly refresh recommendations for the current context."""
        if self._worker:
            self._sig_get_recommendations.emit(self._current_device, self._current_page)

    # ── Automation: pre-flight checks ────────────────────────────────────────

    def run_preflight(self, operation: str) -> None:
        """Run pre-flight checks for an operation type."""
        if self._auto_worker:
            self._sig_run_preflight.emit(operation)

    def run_preflight_flash(self, source_path: str, expected_hash: str = "") -> None:
        """Run flash-specific pre-flight with source and hash validation."""
        if self._auto_worker:
            self._sig_run_preflight_flash.emit(source_path, expected_hash)

    # ── Automation: command execution ────────────────────────────────────────

    def execute_reboot(self, mode: str = "") -> None:
        """Reboot device to specified mode (system/bootloader/recovery)."""
        if self._auto_worker:
            self._sig_execute_reboot.emit(mode)

    def execute_shell(self, command: str, timeout: int = 10) -> None:
        """Execute an ADB shell command on the device."""
        if self._auto_worker:
            self._sig_execute_shell.emit(command, timeout)

    def execute_slot_switch(self, slot: str) -> None:
        """Switch the active A/B partition slot."""
        if self._auto_worker:
            self._sig_execute_slot_switch.emit(slot)

    def execute_erase(self, partition: str) -> None:
        """Erase a device partition."""
        if self._auto_worker:
            self._sig_execute_erase.emit(partition)

    def execute_flash_partition(self, partition: str, image_path: str) -> None:
        """Flash an image to a device partition."""
        if self._auto_worker:
            self._sig_execute_flash_partition.emit(partition, image_path)

    def execute_get_info(self) -> None:
        """Collect comprehensive device information."""
        if self._auto_worker:
            self._sig_execute_get_info.emit()

    def execute_get_slot_info(self) -> None:
        """Query A/B slot information."""
        if self._auto_worker:
            self._sig_execute_get_slot_info.emit()

    # ── Automation: diagnostics and monitoring ───────────────────────────────

    def collect_health_metrics(self) -> None:
        """Collect current device health metrics."""
        if self._auto_worker:
            self._sig_collect_health.emit()

    def start_logcat(self, filter_tag: str = "") -> None:
        """Start streaming logcat from the device."""
        if self._auto_worker:
            self._sig_start_logcat.emit(filter_tag)

    def stop_logcat(self) -> None:
        """Stop logcat streaming."""
        if self._auto_worker:
            self._sig_stop_logcat.emit()

    # ── Deferred startup analysis ────────────────────────────────────────────

    def _deferred_initial_analysis(self) -> None:
        """Run analysis for a device that was set before start() was called."""
        if self._current_device and self._worker:
            self._sig_analyze_device.emit(self._current_device)
            self._sig_get_recommendations.emit(self._current_device, self._current_page)

    # ── Gemini hot-reload ────────────────────────────────────────────────────

    @Slot(str, object)
    def _on_config_changed(self, key: str, _value: object) -> None:
        """Reload the Gemini client whenever the API key or model changes."""
        if key in ("ai/gemini_api_key", "ai/gemini_model"):
            self.reload_gemini()

    def reload_gemini(self) -> None:
        """Tell the AI worker to rebuild its GeminiClient from current config."""
        if self._worker:
            self._sig_reload_gemini.emit()
            logger.info("Gemini reload requested")

    # ── Convenience accessors ────────────────────────────────────────────────

    @property
    def current_device(self) -> DeviceInfo | None:
        return self._current_device

    @property
    def current_page(self) -> str:
        return self._current_page
