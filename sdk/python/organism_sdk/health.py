"""HealthServer — A3.1. Serves HealthReport over HTTP for M1 probes."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urlparse

if TYPE_CHECKING:
    from organism_sdk.module import OrganismModule


@dataclass
class HealthReport:
    module_id: str
    status: str  # HEALTHY | DEGRADED | FAILED
    score: float = 1.0
    active_failures: list[dict[str, Any]] = field(default_factory=list)
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_json(self) -> bytes:
        payload = {
            "module_id": self.module_id,
            "status": self.status,
            "score": self.score,
            "active_failures": self.active_failures,
            "observed_at": self.observed_at.isoformat(),
        }
        return json.dumps(payload).encode("utf-8")


class HealthServer:
    """Minimal HTTP health probe server (HealthHttp).

    For M1: binds to host/port derived from the contract probe URL path.
    """

    def __init__(
        self,
        module: OrganismModule,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        path: str = "/health",
    ) -> None:
        self._module = module
        self._host = host
        self._port = port
        self._path = path
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._httpd is None:
            return self._port
        return self._httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self.port}{self._path}"

    def serve_forever(self, *, background: bool = True) -> None:
        module = self._module
        path = self._path

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != path:
                    self.send_response(404)
                    self.end_headers()
                    return
                report = module.health()
                body = report.to_json()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args: Any) -> None:
                return

        self._httpd = HTTPServer((self._host, self._port), Handler)
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
