"""Tests for the AI engine, device analyzer, and workflow engine."""

from __future__ import annotations

import pytest

from cyberflash.core.ai_engine import (
    ActionCategory,
    AIEngine,
    RiskLevel,
    Workflow,
    WorkflowStep,
)
from cyberflash.core.device_analyzer import (
    DeviceAnalyzer,
    DeviceHealthReport,
    HealthCheckItem,
    HealthGrade,
)
from cyberflash.core.workflow_engine import (
    WorkflowEngine,
    WorkflowStatus,
)
from cyberflash.models.device import DeviceInfo, DeviceState

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def engine() -> AIEngine:
    return AIEngine()


@pytest.fixture()
def analyzer() -> DeviceAnalyzer:
    return DeviceAnalyzer()


@pytest.fixture()
def workflow_engine() -> WorkflowEngine:
    return WorkflowEngine()


@pytest.fixture()
def online_device() -> DeviceInfo:
    return DeviceInfo(
        serial="ABC123",
        state=DeviceState.ONLINE,
        model="Pixel 8",
        brand="Google",
        codename="shiba",
        android_version="14",
        battery_level=85,
        bootloader_unlocked=True,
        has_ab_slots=True,
        active_slot="a",
    )


@pytest.fixture()
def low_battery_device() -> DeviceInfo:
    return DeviceInfo(
        serial="LOW001",
        state=DeviceState.ONLINE,
        model="Test Phone",
        brand="Test",
        battery_level=10,
        bootloader_unlocked=False,
    )


@pytest.fixture()
def fastboot_device() -> DeviceInfo:
    return DeviceInfo(
        serial="FB001",
        state=DeviceState.FASTBOOT,
        model="Test Phone",
        brand="Test",
        battery_level=70,
        bootloader_unlocked=False,
    )


@pytest.fixture()
def edl_device() -> DeviceInfo:
    return DeviceInfo(
        serial="EDL001",
        state=DeviceState.EDL,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  AIEngine Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAIEngineAnalyzeDevice:
    def test_low_battery_insight(self, engine: AIEngine, low_battery_device: DeviceInfo) -> None:
        insights = engine.analyze_device(low_battery_device)
        titles = [i.title for i in insights]
        assert "Low Battery" in titles

    def test_online_device_bootloader_insight(
        self, engine: AIEngine, online_device: DeviceInfo
    ) -> None:
        insights = engine.analyze_device(online_device)
        titles = [i.title for i in insights]
        # Bootloader unlocked, so we should see the unlocked tip
        assert "Bootloader Unlocked" in titles

    def test_fastboot_insight(self, engine: AIEngine, fastboot_device: DeviceInfo) -> None:
        insights = engine.analyze_device(fastboot_device)
        titles = [i.title for i in insights]
        assert "Fastboot Mode" in titles

    def test_edl_insight(self, engine: AIEngine, edl_device: DeviceInfo) -> None:
        insights = engine.analyze_device(edl_device)
        titles = [i.title for i in insights]
        assert "Emergency Download Mode" in titles

    def test_ab_slot_insight(self, engine: AIEngine, online_device: DeviceInfo) -> None:
        insights = engine.analyze_device(online_device)
        ab_insights = [i for i in insights if "Slot" in i.title]
        assert len(ab_insights) == 1

    def test_unauthorized_insight(self, engine: AIEngine) -> None:
        device = DeviceInfo(serial="UNAUTH", state=DeviceState.UNAUTHORIZED)
        insights = engine.analyze_device(device)
        assert any(i.title == "Unauthorized Device" for i in insights)


class TestAIEngineRiskAssessment:
    def test_flash_risk_medium_by_default(self, engine: AIEngine) -> None:
        risk = engine.assess_risk(ActionCategory.FLASH)
        assert risk.level >= RiskLevel.MEDIUM

    def test_flash_blocked_with_low_battery(
        self, engine: AIEngine, low_battery_device: DeviceInfo
    ) -> None:
        risk = engine.assess_risk(ActionCategory.FLASH, low_battery_device)
        assert risk.blocked is True
        assert risk.level == RiskLevel.CRITICAL

    def test_backup_is_low_risk(self, engine: AIEngine) -> None:
        risk = engine.assess_risk(ActionCategory.BACKUP)
        assert risk.level == RiskLevel.LOW

    def test_diagnostics_is_no_risk(self, engine: AIEngine) -> None:
        risk = engine.assess_risk(ActionCategory.DIAGNOSTICS)
        assert risk.level == RiskLevel.NONE

    def test_unlock_is_high_risk(self, engine: AIEngine) -> None:
        risk = engine.assess_risk(ActionCategory.UNLOCK)
        assert risk.level >= RiskLevel.HIGH

    def test_risk_has_mitigations(self, engine: AIEngine, online_device: DeviceInfo) -> None:
        risk = engine.assess_risk(ActionCategory.FLASH, online_device)
        assert len(risk.mitigations) > 0

    def test_flash_locked_bootloader_blocked(
        self, engine: AIEngine, fastboot_device: DeviceInfo
    ) -> None:
        risk = engine.assess_risk(ActionCategory.FLASH, fastboot_device)
        assert risk.blocked is True


class TestAIEngineRecommendations:
    def test_no_device_recommends_connect(self, engine: AIEngine) -> None:
        recs = engine.get_recommendations(device=None)
        assert len(recs) == 1
        assert "Connect" in recs[0].title

    def test_online_device_has_recommendations(
        self, engine: AIEngine, online_device: DeviceInfo
    ) -> None:
        recs = engine.get_recommendations(online_device)
        assert len(recs) > 0

    def test_fastboot_locked_recommends_unlock(
        self, engine: AIEngine, fastboot_device: DeviceInfo
    ) -> None:
        recs = engine.get_recommendations(fastboot_device)
        titles = [r.title for r in recs]
        assert any("Unlock" in t for t in titles)

    def test_edl_recommends_rescue(self, engine: AIEngine, edl_device: DeviceInfo) -> None:
        recs = engine.get_recommendations(edl_device)
        titles = [r.title for r in recs]
        assert any("Rescue" in t or "EDL" in t for t in titles)

    def test_recommendations_sorted_by_priority(
        self, engine: AIEngine, online_device: DeviceInfo
    ) -> None:
        recs = engine.get_recommendations(online_device)
        for i in range(1, len(recs)):
            assert recs[i - 1].priority >= recs[i].priority


class TestAIEngineWorkflows:
    def test_flash_workflow_has_steps(self, engine: AIEngine, online_device: DeviceInfo) -> None:
        wf = engine.plan_flash_workflow(online_device)
        assert len(wf.steps) >= 3
        assert wf.name == "Flash ROM"

    def test_flash_workflow_includes_backup_when_no_backup(
        self, engine: AIEngine, online_device: DeviceInfo
    ) -> None:
        wf = engine.plan_flash_workflow(online_device, has_backup=False)
        titles = [s.title for s in wf.steps]
        assert "Create Backup" in titles

    def test_flash_workflow_skips_backup_when_backed_up(
        self, engine: AIEngine, online_device: DeviceInfo
    ) -> None:
        wf = engine.plan_flash_workflow(online_device, has_backup=True)
        titles = [s.title for s in wf.steps]
        assert "Create Backup" not in titles

    def test_root_workflow_has_steps(self, engine: AIEngine, online_device: DeviceInfo) -> None:
        wf = engine.plan_root_workflow(online_device)
        assert len(wf.steps) >= 3
        assert wf.name == "Root Device"


class TestAIEngineChatResponses:
    def test_greeting(self, engine: AIEngine) -> None:
        response = engine.answer_query("hello")
        assert "CyberFlash AI" in response

    def test_flash_query(self, engine: AIEngine, online_device: DeviceInfo) -> None:
        response = engine.answer_query("how to flash a ROM", online_device)
        assert "flash" in response.lower() or "Flash" in response

    def test_root_query(self, engine: AIEngine) -> None:
        response = engine.answer_query("root my device")
        assert "root" in response.lower() or "Root" in response

    def test_status_query(self, engine: AIEngine, online_device: DeviceInfo) -> None:
        response = engine.answer_query("status", online_device)
        assert "Pixel 8" in response

    def test_battery_query(self, engine: AIEngine, online_device: DeviceInfo) -> None:
        response = engine.answer_query("battery", online_device)
        assert "85%" in response

    def test_unknown_query_gives_help(self, engine: AIEngine) -> None:
        response = engine.answer_query("xyzzy123")
        assert "help" in response.lower() or "can help" in response.lower()


# ═══════════════════════════════════════════════════════════════════════════════
#  DeviceAnalyzer Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeviceAnalyzer:
    def test_healthy_device_high_score(
        self, analyzer: DeviceAnalyzer, online_device: DeviceInfo
    ) -> None:
        report = analyzer.analyze(online_device)
        assert report.score >= 80
        assert report.grade in (HealthGrade.EXCELLENT, HealthGrade.GOOD)

    def test_report_has_checks(self, analyzer: DeviceAnalyzer, online_device: DeviceInfo) -> None:
        report = analyzer.analyze(online_device)
        assert report.total_count >= 5
        assert report.passed_count >= 4

    def test_low_battery_reduces_score(
        self, analyzer: DeviceAnalyzer, low_battery_device: DeviceInfo
    ) -> None:
        report = analyzer.analyze(low_battery_device)
        assert report.score < 100

    def test_unauthorized_device(self, analyzer: DeviceAnalyzer) -> None:
        device = DeviceInfo(serial="UNAUTH", state=DeviceState.UNAUTHORIZED)
        report = analyzer.analyze(device)
        auth_check = [c for c in report.checks if "Authorization" in c.name]
        assert len(auth_check) == 1
        assert auth_check[0].passed is False

    def test_edl_device_notes(self, analyzer: DeviceAnalyzer, edl_device: DeviceInfo) -> None:
        report = analyzer.analyze(edl_device)
        assert any("EDL" in n for n in report.compatibility_notes)

    def test_recommended_actions_for_low_battery(
        self, analyzer: DeviceAnalyzer, low_battery_device: DeviceInfo
    ) -> None:
        report = analyzer.analyze(low_battery_device)
        assert any("Charge" in a or "charge" in a for a in report.recommended_actions)


class TestHealthReport:
    def test_score_empty_report(self) -> None:
        report = DeviceHealthReport(device_name="Test", serial="X")
        assert report.score == 0
        assert report.grade == HealthGrade.CRITICAL

    def test_score_all_passed(self) -> None:
        report = DeviceHealthReport(
            device_name="Test",
            serial="X",
            checks=[
                HealthCheckItem(name="A", passed=True, details="ok", weight=50),
                HealthCheckItem(name="B", passed=True, details="ok", weight=50),
            ],
        )
        assert report.score == 100
        assert report.grade == HealthGrade.EXCELLENT

    def test_score_half_passed(self) -> None:
        report = DeviceHealthReport(
            device_name="Test",
            serial="X",
            checks=[
                HealthCheckItem(name="A", passed=True, details="ok", weight=50),
                HealthCheckItem(name="B", passed=False, details="fail", weight=50),
            ],
        )
        assert report.score == 50
        assert report.grade == HealthGrade.FAIR


# ═══════════════════════════════════════════════════════════════════════════════
#  WorkflowEngine Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkflowEngine:
    def test_plan_full_flash(
        self, workflow_engine: WorkflowEngine, online_device: DeviceInfo
    ) -> None:
        wf = workflow_engine.plan_full_flash(online_device)
        assert wf.name == "Full Flash"
        assert len(wf.steps) >= 4

    def test_plan_full_flash_with_unlock(
        self, workflow_engine: WorkflowEngine, online_device: DeviceInfo
    ) -> None:
        wf = workflow_engine.plan_full_flash(online_device, needs_unlock=True)
        titles = [s.title for s in wf.steps]
        assert "Unlock Bootloader" in titles

    def test_plan_rescue(self, workflow_engine: WorkflowEngine, edl_device: DeviceInfo) -> None:
        wf = workflow_engine.plan_rescue(edl_device)
        assert wf.name == "Device Rescue"
        assert len(wf.steps) >= 3

    def test_plan_nethunter(
        self, workflow_engine: WorkflowEngine, online_device: DeviceInfo
    ) -> None:
        wf = workflow_engine.plan_nethunter_install(online_device)
        assert wf.name == "NetHunter Install"
        assert len(wf.steps) >= 4


class TestWorkflowExecution:
    def test_start_execution(
        self, workflow_engine: WorkflowEngine, online_device: DeviceInfo
    ) -> None:
        wf = workflow_engine.plan_full_flash(online_device)
        ex = workflow_engine.start_execution(wf)
        assert ex.status == WorkflowStatus.RUNNING
        assert ex.started_at > 0

    def test_complete_step(
        self, workflow_engine: WorkflowEngine, online_device: DeviceInfo
    ) -> None:
        wf = workflow_engine.plan_full_flash(online_device)
        ex = workflow_engine.start_execution(wf)
        first_step_id = wf.steps[0].step_id
        workflow_engine.complete_step(ex, first_step_id)
        assert wf.steps[0].completed is True
        assert len(ex.events) == 1

    def test_complete_all_steps(
        self, workflow_engine: WorkflowEngine, online_device: DeviceInfo
    ) -> None:
        wf = workflow_engine.plan_full_flash(online_device)
        ex = workflow_engine.start_execution(wf)
        for step in wf.steps:
            workflow_engine.complete_step(ex, step.step_id)
        assert wf.is_complete
        assert ex.status == WorkflowStatus.COMPLETED

    def test_fail_step(self, workflow_engine: WorkflowEngine, online_device: DeviceInfo) -> None:
        wf = workflow_engine.plan_full_flash(online_device)
        ex = workflow_engine.start_execution(wf)
        workflow_engine.fail_step(ex, wf.steps[0].step_id, "Timeout")
        assert ex.status == WorkflowStatus.FAILED
        assert ex.error_message == "Timeout"

    def test_cancel_execution(
        self, workflow_engine: WorkflowEngine, online_device: DeviceInfo
    ) -> None:
        wf = workflow_engine.plan_full_flash(online_device)
        ex = workflow_engine.start_execution(wf)
        workflow_engine.cancel_execution(ex)
        assert ex.status == WorkflowStatus.CANCELLED

    def test_skip_step(self, workflow_engine: WorkflowEngine, online_device: DeviceInfo) -> None:
        wf = workflow_engine.plan_full_flash(online_device, has_backup=False)
        ex = workflow_engine.start_execution(wf)
        # The backup step should be skippable
        backup_steps = [s for s in wf.steps if s.skippable]
        if backup_steps:
            workflow_engine.skip_step(ex, backup_steps[0].step_id)
            assert backup_steps[0].completed

    def test_execution_summary(
        self, workflow_engine: WorkflowEngine, online_device: DeviceInfo
    ) -> None:
        wf = workflow_engine.plan_full_flash(online_device)
        ex = workflow_engine.start_execution(wf)
        summary = workflow_engine.get_execution_summary(ex)
        assert "Full Flash" in summary
        assert "Running" in summary

    def test_active_execution(
        self, workflow_engine: WorkflowEngine, online_device: DeviceInfo
    ) -> None:
        wf = workflow_engine.plan_full_flash(online_device)
        ex = workflow_engine.start_execution(wf)
        assert workflow_engine.active_execution is ex


# ═══════════════════════════════════════════════════════════════════════════════
#  Data class Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRiskLevel:
    def test_labels(self) -> None:
        assert RiskLevel.NONE.label == "None"
        assert RiskLevel.CRITICAL.label == "Critical"

    def test_ordering(self) -> None:
        assert RiskLevel.NONE < RiskLevel.LOW < RiskLevel.MEDIUM
        assert RiskLevel.MEDIUM < RiskLevel.HIGH < RiskLevel.CRITICAL

    def test_color_tokens(self) -> None:
        assert RiskLevel.NONE.color_token == "success"
        assert RiskLevel.CRITICAL.color_token == "error"


class TestWorkflow:
    def test_progress_empty(self) -> None:
        wf = Workflow(name="test", description="test")
        assert wf.progress == 1.0
        assert wf.is_complete

    def test_progress_half(self) -> None:
        wf = Workflow(
            name="test",
            description="test",
            steps=[
                WorkflowStep(
                    step_id=1,
                    title="A",
                    description="",
                    category=ActionCategory.GENERAL,
                    completed=True,
                ),
                WorkflowStep(
                    step_id=2,
                    title="B",
                    description="",
                    category=ActionCategory.GENERAL,
                    completed=False,
                ),
            ],
        )
        assert wf.progress == 0.5
        assert not wf.is_complete


class TestHealthGrade:
    def test_grade_badge_variant(self) -> None:
        assert HealthGrade.EXCELLENT.badge_variant == "success"
        assert HealthGrade.FAIR.badge_variant == "warning"
        assert HealthGrade.CRITICAL.badge_variant == "error"

    def test_grade_score_ranges(self) -> None:
        low, high = HealthGrade.EXCELLENT.score_range
        assert low == 90
        assert high == 100
