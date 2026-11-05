"""HTTP serve for minimal Organism stack (v1.4)."""

from __future__ import annotations

import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from organism_sdk.deploy.config import DeployConfig
from organism_sdk.deploy.stack import MinimalStack, build_minimal_stack

WORK_STATUS_PATH = "/work/status"


def _work_status(path: Path) -> tuple[bytes, int]:
    """The work agent's status, read beside its writer. 404 without a store, 503 if unreadable."""
    from organism_sdk.work import operator
    from organism_sdk.work.store import WorkStore

    if not path.exists():
        return b'{"error":"no_work_store"}', 404
    try:
        with WorkStore(path, read_only=True) as store:
            return json.dumps(operator.status(store)).encode("utf-8"), 200
    except sqlite3.Error:
        return b'{"error":"work_store_unreadable"}', 503


class StackServer:
    """Serves /health and /status for a MinimalStack, and /work/status when a work store is given."""

    def __init__(self, stack: MinimalStack, *, work_store: Path | None = None) -> None:
        self.stack = stack
        self.work_store = work_store
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._httpd is None:
            return self.stack.config.health.port
        return int(self._httpd.server_address[1])

    @property
    def url_health(self) -> str:
        h = self.stack.config.health
        return f"http://{h.host}:{self.port}{h.path}"

    def start(self, *, background: bool = True, port: int | None = None) -> None:
        stack = self.stack
        health_path = stack.config.health.path
        status_path = stack.config.health.status_path
        host = stack.config.health.host
        bind_port = stack.config.health.port if port is None else port
        work_store = self.work_store

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == health_path:
                    body = stack.health_report().to_json()
                    code = 200
                elif parsed.path == status_path:
                    body = json.dumps(stack.status()).encode("utf-8")
                    code = 200
                elif parsed.path == WORK_STATUS_PATH and work_store is not None:
                    body, code = _work_status(work_store)
                else:
                    body = b'{"error":"not_found"}'
                    code = 404
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args: Any) -> None:
                return

        self._httpd = HTTPServer((host, bind_port), Handler)
        if background:
            self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
            self._thread.start()
        else:
            self._httpd.serve_forever()

    def shutdown(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


def serve_stack(
    cfg: DeployConfig | None = None,
    *,
    dry_run: bool = False,
    port: int | None = None,
    work_store: Path | None = None,
) -> dict[str, Any]:
    """Build stack; optionally bind health HTTP. dry_run never binds.

    ``work_store`` is the work agent's store, whose status the server answers at /work/status.
    """
    stack = build_minimal_stack(cfg)
    status = stack.status()
    if dry_run or (cfg and cfg.serve.dry_run):
        status["dry_run"] = True
        status["listening"] = False
        return status

    server = StackServer(stack, work_store=work_store)
    # port 0 for ephemeral in tests when requested
    bind = 0 if port == 0 else (port if port is not None else None)
    server.start(background=True, port=bind)
    status["dry_run"] = False
    status["listening"] = True
    status["health_url"] = server.url_health
    status["bound_port"] = server.port
    status["_server"] = server  # caller may shutdown
    return status
