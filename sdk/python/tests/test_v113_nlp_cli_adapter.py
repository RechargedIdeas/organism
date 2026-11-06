"""v1.13: NLP-CLI as an Organism module. The router proposes; the tool host decides."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from nlp_cli import (
    NlpCliRouter,
    RouterError,
    RouteResult,
    dispatch,
    load_spec,
    parse_result,
    path_args,
    register_tools,
    router_contract,
    tool_contracts,
)
from organism_sdk.contract import (
    MaxSafetyTier,
    OutputForm,
    ReliabilityTier,
    Severity,
    ToolConfinement,
    ToolConfirmation,
    ToolNetwork,
)
from organism_sdk.pathscope import PathScope
from organism_sdk.tool_host import ToolHost, ToolRefused

SPEC: dict[str, Any] = {
    "format": "nlpcli-tools",
    "version": 1,
    "tools": [
        {"name": "read_file", "risk": "read", "slots": [{"name": "path", "kind": "path"}]},
        {"name": "list_files", "risk": "read", "slots": []},
        {"name": "write_file", "risk": "write", "slots": [{"name": "path", "kind": "path"}]},
        {"name": "git_commit", "risk": "write", "slots": [{"name": "message", "kind": "message"}]},
        {"name": "delete_file", "risk": "destructive", "slots": [{"name": "path", "kind": "path"}]},
        {"name": "git_push", "risk": "destructive", "slots": []},
        {"name": "run_tests", "risk": "execute", "slots": []},
        {"name": "run_command", "risk": "execute", "slots": [{"name": "command", "kind": "command"}]},
    ],
}


class FakeRunner:
    """Stands in for the binary. Records the argv and returns a canned stdout."""

    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.argv: list[str] = []

    def __call__(self, argv: Any) -> subprocess.CompletedProcess[str]:
        self.argv = list(argv)
        return subprocess.CompletedProcess(list(argv), self.returncode, self.stdout, self.stderr)


@pytest.fixture()
def spec_path(tmp_path: Path) -> Path:
    path = tmp_path / "tools.json"
    path.write_text(json.dumps(SPEC), encoding="utf-8")
    return path


def _router(spec_path: Path, stdout: str, **kwargs: Any) -> NlpCliRouter:
    runner = FakeRunner(stdout, **kwargs)
    return NlpCliRouter("nlp-cli", spec_path, runner=runner)


def _decision(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


# ---------------------------------------------------------------- tool contracts (A2)


def _by_name(name: str) -> Any:
    return next(c for c in tool_contracts(SPEC) if c.name == name)


def test_every_tool_becomes_a_registrable_contract() -> None:
    contracts = tool_contracts(SPEC)
    assert [c.name for c in contracts] == [t["name"] for t in SPEC["tools"]]
    for contract in contracts:
        assert contract.is_registrable(), contract.name


def test_risk_levels_map_to_organism_tiers() -> None:
    read = _by_name("read_file")
    assert read.risk_tier == MaxSafetyTier.LOW and read.confirmation == ToolConfirmation.NONE
    assert read.confinement == ToolConfinement.SCOPED  # it takes a path

    listing = _by_name("list_files")
    assert listing.confinement == ToolConfinement.NONE  # read, no path

    write = _by_name("write_file")
    assert write.risk_tier == MaxSafetyTier.MEDIUM and write.confirmation == ToolConfirmation.ALWAYS

    delete = _by_name("delete_file")
    assert delete.risk_tier == MaxSafetyTier.HIGH and delete.confinement == ToolConfinement.STRICT

    push = _by_name("git_push")
    assert push.network == ToolNetwork.INTERNET and push.confinement == ToolConfinement.STRICT

    tests = _by_name("run_tests")
    assert tests.risk_tier == MaxSafetyTier.HIGH and tests.network == ToolNetwork.LOCAL


def test_schemas_refuse_unknown_arguments() -> None:
    schema = json.loads(_by_name("read_file").schema_json)
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["path"]


def test_path_arguments_are_listed_per_tool() -> None:
    paths = path_args(SPEC)
    assert paths["read_file"] == ("path",)
    assert paths["list_files"] == ()


def test_an_unknown_risk_or_slot_kind_is_refused() -> None:
    with pytest.raises(RouterError):
        tool_contracts({"tools": [{"name": "x", "risk": "reckless", "slots": []}]})
    with pytest.raises(RouterError):
        tool_contracts({"tools": [{"name": "x", "risk": "read", "slots": [{"name": "y", "kind": "shell"}]}]})


def test_a_spec_with_the_wrong_format_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": "other", "version": 1, "tools": []}), encoding="utf-8")
    with pytest.raises(RouterError):
        load_spec(bad)


# ---------------------------------------------------------------- the router is a proposer (contract)


def test_the_router_contract_proposes_and_never_actuates() -> None:
    contract = router_contract(version="0.5.0")
    assert not [i for i in contract.validate() if i.severity == Severity.ERROR]
    assert contract.emission.output_form == OutputForm.TOOL_CALL
    assert contract.safety.may_actuate is False
    assert contract.safety.reliability_tier == ReliabilityTier.T2_LEARNED_CALIBRATED


# ---------------------------------------------------------------- decisions (route --json)


@pytest.mark.parametrize(
    ("payload", "action"),
    [
        ({"action": "execute", "tool": "read_file", "args": {"path": "a.txt"}, "tier": "t0", "confidence": 1.0},
         "execute"),
        ({"action": "confirm", "tool": "delete_file", "args": {"path": "a"}, "tier": "t1", "confidence": 0.93,
          "risk": "destructive"}, "confirm"),
        ({"action": "no_tool", "tier": "t1", "confidence": 0.8}, "no_tool"),
        ({"action": "declined", "reason": "negated request: nothing was run", "tier": "t0"}, "declined"),
        ({"action": "abstain", "reason": "needs a path", "best_label": "read_file", "confidence": 0.4,
          "tier": "t1"}, "abstain"),
    ],
)
def test_each_decision_parses(payload: dict[str, Any], action: str) -> None:
    result = parse_result(payload)
    assert result.action == action


def test_an_abstention_names_its_best_guess_but_no_tool() -> None:
    result = parse_result({"action": "abstain", "reason": "low", "best_label": "read_file", "confidence": 0.4})
    assert result.tool is None and result.best_label == "read_file"


def test_unknown_decision_shapes_are_rejected() -> None:
    with pytest.raises(RouterError):
        parse_result({"action": "rm_rf"})
    with pytest.raises(RouterError):
        parse_result(["not", "a", "dict"])
    with pytest.raises(RouterError):
        parse_result({"action": "execute", "tool": 3, "args": {}})


def test_route_builds_the_command_line(spec_path: Path, tmp_path: Path) -> None:
    runner = FakeRunner(_decision({"action": "no_tool", "tier": "t1", "confidence": 0.1}))
    model = tmp_path / "t1.json"
    router = NlpCliRouter("nlp-cli", spec_path, model, runner=runner)
    router.route("say hi")
    assert runner.argv == ["nlp-cli", "route", "--json", "--spec", str(spec_path), "--model", str(model), "say hi"]


def test_route_refuses_empty_requests_and_leading_dashes(spec_path: Path) -> None:
    router = _router(spec_path, "{}")
    with pytest.raises(RouterError):
        router.route("   ")
    with pytest.raises(RouterError):
        router.route("--json")


def test_non_json_output_is_an_error(spec_path: Path) -> None:
    router = _router(spec_path, "error: no model", returncode=1, stderr="model missing")
    with pytest.raises(RouterError, match="not JSON"):
        router.route("list files")


# ---------------------------------------------------------------- dispatch: the host decides


def _host(tmp_path: Path, handlers: dict[str, Any]) -> tuple[ToolHost, list[str]]:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "a.txt").write_text("hello", encoding="utf-8")
    host = ToolHost(PathScope(root))
    ran: list[str] = []

    def wrap(name: str, fn: Any) -> Any:
        def handler(args: dict[str, Any]) -> str:
            ran.append(name)
            return fn(args)

        return handler

    register_tools(host, SPEC, {name: wrap(name, fn) for name, fn in handlers.items()})
    return host, ran


def test_an_execute_proposal_runs_a_read_tool_inside_the_scope(tmp_path: Path, spec_path: Path) -> None:
    host, ran = _host(tmp_path, {"read_file": lambda args: Path(args["path"]).read_text(encoding="utf-8")})
    proposal = parse_result(
        {"action": "execute", "tool": "read_file", "args": {"path": "a.txt"}, "tier": "t0", "confidence": 1.0}
    )
    result = dispatch(proposal, host)
    assert result is not None and result.ok and result.output == "hello"
    assert ran == ["read_file"]


def test_a_confirm_proposal_needs_a_person(tmp_path: Path) -> None:
    host, ran = _host(tmp_path, {"delete_file": lambda args: "deleted"})
    proposal = parse_result(
        {"action": "confirm", "tool": "delete_file", "args": {"path": "a.txt"}, "tier": "t0", "confidence": 1.0,
         "risk": "destructive"}
    )
    with pytest.raises(ToolRefused):
        dispatch(proposal, host)
    declined = dispatch(proposal, host, confirm=lambda name, args: None)
    assert declined is not None and not declined.ok and declined.outcome == "declined"
    approved = dispatch(proposal, host, confirm=lambda name, args: "alice")
    assert approved is not None and approved.ok
    assert approved.confirmation is not None and approved.confirmation.approver == "alice"
    assert ran == ["delete_file"]


def test_a_proposal_cannot_escape_the_scope(tmp_path: Path) -> None:
    host, ran = _host(tmp_path, {"read_file": lambda args: "secret"})
    proposal = RouteResult(action="execute", tool="read_file", args={"path": "../secret.txt"})
    with pytest.raises(ToolRefused):
        dispatch(proposal, host)
    assert ran == []


def test_a_proposal_for_an_unserved_tool_is_refused(tmp_path: Path) -> None:
    host, _ = _host(tmp_path, {"read_file": lambda args: "x"})
    with pytest.raises(ToolRefused):
        dispatch(RouteResult(action="confirm", tool="run_tests"), host, confirm=lambda n, a: "bob")


def test_non_proposals_never_reach_the_host(tmp_path: Path) -> None:
    host, _ = _host(tmp_path, {"read_file": lambda args: "x"})
    for action in ("no_tool", "declined", "abstain"):
        assert dispatch(RouteResult(action=action, best_label="read_file"), host) is None
    assert host.audit() == []


# ---------------------------------------------------------------- the real binary, when it is given


_REAL_BIN = os.environ.get("NLPCLI_BIN")
_REAL_SPEC = os.environ.get("NLPCLI_SPEC")


@pytest.mark.skipif(not (_REAL_BIN and _REAL_SPEC), reason="set NLPCLI_BIN and NLPCLI_SPEC to run")
def test_the_real_binary_gives_decisions_the_adapter_reads() -> None:
    router = NlpCliRouter(_REAL_BIN or "", _REAL_SPEC or "")
    listed = router.route("list files")
    assert listed.action == "execute" and listed.tool == "list_files"
    deleted = router.route("delete temp.txt")
    assert deleted.action == "confirm" and deleted.tool == "delete_file"
    assert deleted.args == {"path": "temp.txt"}
    negated = router.route("do not delete the readme")
    assert negated.action == "declined"
