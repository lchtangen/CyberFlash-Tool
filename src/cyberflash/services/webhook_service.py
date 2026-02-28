"""webhook_service.py — Localhost HTTP trigger server (Phase 9).

Runs a minimal ``http.server``-based HTTP server in a background QThread
so external tools (Jenkins, GitHub Actions) can trigger CyberFlash workflows
via HTTP POST requests on localhost.

Endpoints::

    POST /api/v1/run/{workflow_name}
         Body (JSON): {"device_serial": "...", "params": {...}}
         Response:    {"job_id": "<uuid>", "status": "queued"}

    GET  /api/v1/status/{job_id}
         Response:    {"job_id": "...", "status": "running|done|failed"}

Usage::

    svc = WebhookService(port=9876, parent=main_window)
    svc.workflow_triggered.connect(on_workflow_triggered)
    svc.start_server()
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

_DEFAULT_PORT = 9876


class WebhookService(QObject):
    """Lightweight localhost HTTP trigger server for CI/CD integration.

    Signals:
        workflow_triggered(str, str, dict): workflow_name, job_id, params
        server_started(int): port number when the server starts successfully
        server_stopped(): emitted when server stops
        server_error(str): emitted on binding failure
    """

    workflow_triggered = Signal(str, str, dict)  # name, job_id, params
    server_started = Signal(int)
    server_stopped = Signal()
    server_error = Signal(str)

    def __init__(self, port: int = _DEFAULT_PORT, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._jobs: dict[str, dict[str, Any]] = {}  # job_id → status dict
        self._running = False

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def start_server(self) -> bool:
        """Start the HTTP server in a daemon thread. Returns ``False`` on error."""
        if self._running:
            return True
        try:
            svc_ref = self

            class _Handler(BaseHTTPRequestHandler):
                def log_message(self, fmt: str, *args: object) -> None:
                    logger.debug("WebhookService: " + fmt, *args)

                def do_GET(self) -> None:
                    self._handle_get(svc_ref)

                def do_POST(self) -> None:
                    self._handle_post(svc_ref)

                def _handle_get(self, svc: WebhookService) -> None:
                    # /api/v1/status/<job_id>
                    if self.path.startswith("/api/v1/status/"):
                        job_id = self.path.split("/")[-1]
                        record = svc._jobs.get(job_id)
                        if record:
                            self._respond(200, record)
                        else:
                            self._respond(404, {"error": "Job not found"})
                    else:
                        self._respond(404, {"error": "Not found"})

                def _handle_post(self, svc: WebhookService) -> None:
                    # /api/v1/run/<workflow_name>
                    if not self.path.startswith("/api/v1/run/"):
                        self._respond(404, {"error": "Not found"})
                        return
                    workflow_name = self.path[len("/api/v1/run/"):]
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length) if length else b"{}"
                    try:
                        payload = json.loads(body)
                    except json.JSONDecodeError:
                        self._respond(400, {"error": "Invalid JSON"})
                        return
                    job_id = str(uuid.uuid4())
                    svc._jobs[job_id] = {"job_id": job_id, "status": "queued"}
                    params = payload.get("params", {})
                    if not isinstance(params, dict):
                        params = {}
                    # Use invokeMethod-safe cross-thread signal via Qt
                    from PySide6.QtCore import QMetaObject, Qt
                    QMetaObject.invokeMethod(
                        svc,
                        "_emit_workflow_triggered",
                        Qt.ConnectionType.QueuedConnection,
                        workflow_name,
                        job_id,
                        params,
                    )
                    self._respond(200, {"job_id": job_id, "status": "queued"})

                def _respond(self, code: int, data: dict[str, Any]) -> None:
                    body = json.dumps(data).encode()
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            self._server = HTTPServer(("127.0.0.1", self._port), _Handler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="CyberFlash-WebhookServer",
            )
            self._running = True
            self._thread.start()
            logger.info("WebhookService listening on port %d", self._port)
            self.server_started.emit(self._port)
            return True
        except OSError as exc:
            msg = f"WebhookService: failed to start on port {self._port}: {exc}"
            logger.warning(msg)
            self._running = False
            self.server_error.emit(msg)
            return False

    def stop_server(self) -> None:
        """Shut down the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        self._running = False
        self.server_stopped.emit()
        logger.info("WebhookService stopped")

    # ------------------------------------------------------------------
    # Job status management
    # ------------------------------------------------------------------

    def update_job_status(self, job_id: str, status: str) -> bool:
        """Update the status of a queued job. Returns ``False`` if not found."""
        if job_id not in self._jobs:
            return False
        self._jobs[job_id]["status"] = status
        return True

    def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        """Return status dict for *job_id*, or ``None``."""
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return all job records."""
        return list(self._jobs.values())

    def _emit_workflow_triggered(
        self, workflow_name: str, job_id: str, params: dict[str, Any]
    ) -> None:
        """Called from the main thread via QMetaObject.invokeMethod."""
        self.workflow_triggered.emit(workflow_name, job_id, params)
