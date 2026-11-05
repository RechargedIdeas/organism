"""v1.12 W7, the status route of `organism serve`: it answers beside the writer, and says when there is
no store."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from organism_sdk.deploy.serve import serve_stack
from organism_sdk.work.domain import (
    Assignment,
    AssignmentState,
    Mandate,
    Strength,
    Ticket,
    Via,
)
from organism_sdk.work.store import WorkStore


def get(port: int, path: str) -> tuple[int, dict[str, Any]]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_the_status_route_answers_beside_the_writer(tmp_path: Path) -> None:
    path = tmp_path / "work.sqlite"
    mandate = Mandate(
        policy_version="sha256:test",
        strength=Strength.EXPLICIT,
        via=Via.ADDRESSED,
        source="github",
        row="repo",
        sender="alice",
    )
    assignment = Assignment(id="a1", ticket_id="t1", state=AssignmentState.RUNNING)
    with WorkStore(path) as store:
        store.save_ticket(Ticket(id="t1", mandate=mandate, assignment=assignment))
        result = serve_stack(port=0, work_store=path)
        server = result.pop("_server")
        try:
            code, body = get(result["bound_port"], "/work/status")
        finally:
            server.shutdown()
    assert code == 200
    assert body["open_tickets"] == 1


def test_the_status_route_says_when_there_is_no_store(tmp_path: Path) -> None:
    result = serve_stack(port=0, work_store=tmp_path / "missing.sqlite")
    server = result.pop("_server")
    try:
        code, body = get(result["bound_port"], "/work/status")
    finally:
        server.shutdown()
    assert (code, body) == (404, {"error": "no_work_store"})


def test_the_status_route_is_absent_without_a_work_store() -> None:
    result = serve_stack(port=0)
    server = result.pop("_server")
    try:
        code, body = get(result["bound_port"], "/work/status")
    finally:
        server.shutdown()
    assert (code, body) == (404, {"error": "not_found"})
