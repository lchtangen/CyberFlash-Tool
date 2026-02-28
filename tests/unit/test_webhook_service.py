"""tests/unit/test_webhook_service.py — Unit tests for WebhookService."""

from __future__ import annotations

import json
import urllib.request
from time import sleep

import pytest

from cyberflash.services.webhook_service import WebhookService


@pytest.fixture()
def svc(qapp: object) -> WebhookService:
    """WebhookService on a high ephemeral port."""
    service = WebhookService(port=19876)
    return service


class TestWebhookServiceInit:
    def test_port_property(self, svc: WebhookService) -> None:
        assert svc.port == 19876

    def test_not_running_initially(self, svc: WebhookService) -> None:
        assert svc.is_running is False

    def test_list_jobs_empty(self, svc: WebhookService) -> None:
        assert svc.list_jobs() == {}

    def test_get_job_status_unknown(self, svc: WebhookService) -> None:
        assert svc.get_job_status("no-such-id") is None


class TestWebhookServiceJobStatus:
    def test_update_and_get_job_status(self, svc: WebhookService) -> None:
        svc.update_job_status("job-1", "running")
        record = svc.get_job_status("job-1")
        assert record is not None
        assert record["status"] == "running"

    def test_update_overwrites_status(self, svc: WebhookService) -> None:
        svc.update_job_status("job-x", "queued")
        svc.update_job_status("job-x", "done")
        assert svc.get_job_status("job-x")["status"] == "done"

    def test_list_jobs_contains_all(self, svc: WebhookService) -> None:
        svc.update_job_status("j1", "done")
        svc.update_job_status("j2", "failed")
        jobs = svc.list_jobs()
        assert "j1" in jobs
        assert "j2" in jobs


class TestWebhookServiceLifecycle:
    def test_start_server_sets_running(self, svc: WebhookService) -> None:
        ok = svc.start_server()
        assert ok is True
        assert svc.is_running is True
        svc.stop_server()

    def test_start_server_is_idempotent(self, svc: WebhookService) -> None:
        svc.start_server()
        assert svc.start_server() is True  # returns True without re-binding
        svc.stop_server()

    def test_stop_server(self, svc: WebhookService) -> None:
        svc.start_server()
        svc.stop_server()
        assert svc.is_running is False

    def test_server_started_signal(self, qapp: object) -> None:
        from PySide6.QtTest import QSignalSpy

        service = WebhookService(port=19877)
        spy = QSignalSpy(service.server_started)
        service.start_server()
        assert len(spy) == 1
        assert spy[0][0] == 19877
        service.stop_server()


class TestWebhookServiceHTTP:
    """Live HTTP tests — requires server actually on port 19878."""

    PORT = 19878

    @pytest.fixture()
    def live_svc(self, qapp: object) -> WebhookService:
        service = WebhookService(port=self.PORT)
        service.start_server()
        sleep(0.1)  # brief warmup
        yield service
        service.stop_server()

    def test_post_run_returns_job_id(self, live_svc: WebhookService) -> None:
        url = f"http://127.0.0.1:{self.PORT}/api/v1/run/my_workflow"
        req = urllib.request.Request(
            url,
            data=json.dumps({}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())
        assert "job_id" in body
        assert body["status"] == "queued"

    def test_get_status_not_found(self, live_svc: WebhookService) -> None:
        import urllib.error

        url = f"http://127.0.0.1:{self.PORT}/api/v1/status/no-such-job"
        try:
            urllib.request.urlopen(url)
            raise AssertionError("Expected 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_get_status_found(self, live_svc: WebhookService) -> None:
        live_svc.update_job_status("known-job", "done")
        url = f"http://127.0.0.1:{self.PORT}/api/v1/status/known-job"
        with urllib.request.urlopen(url) as resp:
            body = json.loads(resp.read())
        assert body["status"] == "done"

    def test_post_invalid_endpoint_returns_404(self, live_svc: WebhookService) -> None:
        import urllib.error

        url = f"http://127.0.0.1:{self.PORT}/api/v1/unknown"
        try:
            urllib.request.urlopen(
                urllib.request.Request(url, data=b"{}", method="POST")
            )
            raise AssertionError("Expected 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
