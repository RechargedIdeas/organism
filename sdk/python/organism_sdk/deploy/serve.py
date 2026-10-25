"""HTTP serve for minimal Organism stack (v1.4)."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

from organism_sdk.deploy.config import DeployConfig
from organism_sdk.deploy.stack import MinimalStack, build_minimal_stack


class StackServer:
    """Serves /health and /status for a MinimalStack."""

    def __init__(self, stack: MinimalStack) -> None:
        self.stack = stack
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

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path == health_path:
                    body = stack.health_report().to_json()
                    code = 200
                elif parsed.path == status_path:
                    body = json.dumps(stack.status()).encode("utf-8")
                    code = 200
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
) -> dict[str, Any]:
    """Build stack; optionally bind health HTTP. dry_run never binds."""
    stack = build_minimal_stack(cfg)
    status = stack.status()
    if dry_run or (cfg and cfg.serve.dry_run):
        status["dry_run"] = True
        status["listening"] = False
        return status

    server = StackServer(stack)
    # port 0 for ephemeral in tests when requested
    bind = 0 if port == 0 else (port if port is not None else None)
    server.start(background=True, port=bind)
    status["dry_run"] = False
    status["listening"] = True
    status["health_url"] = server.url_health
    status["bound_port"] = server.port
    status["_server"] = server  # caller may shutdown
    return status
