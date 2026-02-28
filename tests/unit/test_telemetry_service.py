"""tests/unit/test_telemetry_service.py — Unit tests for TelemetryService."""

from __future__ import annotations

import json

from cyberflash.services.telemetry_service import TelemetryEvent, TelemetryService

# ---------------------------------------------------------------------------
# TelemetryEvent
# ---------------------------------------------------------------------------


class TestTelemetryEvent:
    def test_to_dict_keys(self) -> None:
        evt = TelemetryEvent(event="test_event", properties={"x": 1})
        d = evt.to_dict()
        assert d["event"] == "test_event"
        assert d["properties"]["x"] == 1
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# TelemetryService — opt-out (default)
# ---------------------------------------------------------------------------


class TestTelemetryServiceOptOut:
    def test_default_is_opted_out(self, qapp: object) -> None:
        svc = TelemetryService()
        assert svc.opt_in is False

    def test_track_does_nothing_when_opted_out(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=False)
        svc.track("flash_started", rom="lineageos")
        assert svc.queue_size() == 0

    def test_flush_returns_zero_when_opted_out(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=False)
        assert svc.flush() == 0


# ---------------------------------------------------------------------------
# TelemetryService — opt-in
# ---------------------------------------------------------------------------


class TestTelemetryServiceOptIn:
    def test_opt_in_enables_tracking(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=True)
        svc.track("flash_started")
        assert svc.queue_size() == 1

    def test_track_adds_to_queue(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=True)
        svc.track("ev1", method="fastboot")
        svc.track("ev2", duration_s=10)
        assert svc.queue_size() == 2

    def test_flush_clears_queue(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=True)
        svc.track("ev1")
        svc.track("ev2")
        count = svc.flush()
        assert count == 2
        assert svc.queue_size() == 0

    def test_flush_returns_event_count(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=True)
        svc.track("a")
        svc.track("b")
        svc.track("c")
        assert svc.flush() == 3

    def test_flush_complete_signal(self, qapp: object) -> None:
        from PySide6.QtTest import QSignalSpy

        svc = TelemetryService(opt_in=True)
        spy = QSignalSpy(svc.flush_complete)
        svc.track("ev")
        svc.flush()
        assert len(spy) == 1
        assert spy[0][0] == 1

    def test_total_flushed_accumulates(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=True)
        svc.track("a")
        svc.flush()
        svc.track("b")
        svc.track("c")
        svc.flush()
        assert svc.total_flushed() == 3


# ---------------------------------------------------------------------------
# PII sanitisation
# ---------------------------------------------------------------------------


class TestTelemetryPIISanitisation:
    def test_serial_stripped(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=True)
        svc.track("ev", serial="ABC123", method="fastboot")
        exported = json.loads(svc.export_queue())
        props = exported[0]["properties"]
        assert "serial" not in props
        assert "method" in props

    def test_email_stripped(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=True)
        svc.track("reg", email="user@example.com", plan="free")
        exported = json.loads(svc.export_queue())
        props = exported[0]["properties"]
        assert "email" not in props
        assert "plan" in props

    def test_path_stripped(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=True)
        svc.track("file.op", path="/home/user/rom.zip", size_mb=250)
        exported = json.loads(svc.export_queue())
        props = exported[0]["properties"]
        assert "path" not in props
        assert "size_mb" in props

    def test_token_and_key_stripped(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=True)
        svc.track("api.call", token="secret-t", key="secret-k", action="get")
        exported = json.loads(svc.export_queue())
        props = exported[0]["properties"]
        assert "token" not in props
        assert "key" not in props
        assert "action" in props

    def test_sanitise_direct(self) -> None:
        result = TelemetryService._sanitise(
            {"serial": "S1", "rom": "LineageOS", "password": "pw123"}
        )
        assert "serial" not in result
        assert "password" not in result
        assert result["rom"] == "LineageOS"


# ---------------------------------------------------------------------------
# opt-in toggle
# ---------------------------------------------------------------------------


class TestTelemetryOptInToggle:
    def test_opt_in_signal_emitted(self, qapp: object) -> None:
        from PySide6.QtTest import QSignalSpy

        svc = TelemetryService(opt_in=False)
        spy = QSignalSpy(svc.opt_in_changed)
        svc.opt_in = True
        assert len(spy) == 1
        assert spy[0][0] is True

    def test_opt_out_clears_queue(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=True)
        svc.track("ev1")
        svc.track("ev2")
        svc.opt_in = False
        assert svc.queue_size() == 0

    def test_toggle_same_value_no_signal(self, qapp: object) -> None:
        from PySide6.QtTest import QSignalSpy

        svc = TelemetryService(opt_in=True)
        spy = QSignalSpy(svc.opt_in_changed)
        svc.opt_in = True  # same value — no signal
        assert len(spy) == 0


# ---------------------------------------------------------------------------
# queue overflow
# ---------------------------------------------------------------------------


class TestTelemetryQueueOverflow:
    def test_queue_capped_at_max(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=True)
        for i in range(550):  # _MAX_QUEUE = 500
            svc.track(f"ev{i}")
        assert svc.queue_size() == 500


# ---------------------------------------------------------------------------
# export_queue
# ---------------------------------------------------------------------------


class TestTelemetryExportQueue:
    def test_export_queue_is_valid_json(self, qapp: object) -> None:
        svc = TelemetryService(opt_in=True)
        svc.track("export_test", duration_s=5)
        raw = svc.export_queue()
        data = json.loads(raw)
        assert isinstance(data, list)
        assert data[0]["event"] == "export_test"
