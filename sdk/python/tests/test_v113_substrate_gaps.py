"""v1.13 gap fills needed by NLP-CLI (D2, D3, G1, G2 partly): calibration, learned backend, path scope, tool host."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from organism_sdk.calibration import (
    AbstentionPolicy,
    choose_threshold,
    expected_calibration_error,
    fit_temperature,
    softmax,
)
from organism_sdk.canonical import canonical_text
from organism_sdk.contract import (
    MaxSafetyTier,
    ToolConfinement,
    ToolConfirmation,
    ToolContract,
    ToolNetwork,
)
from organism_sdk.learned import ModelRef, decide_label
from organism_sdk.pathscope import PathEscape, PathScope
from organism_sdk.tool_host import (
    AuditRecord,
    Confirm,
    Handler,
    ToolHost,
    ToolRefused,
    ToolRegistrationError,
    check_schema,
    validate_args,
    verify_chain,
)


def _approve(log: list[str], answer: str | None) -> Confirm:
    """A confirmation callback that records the tool name it was asked about, then gives ``answer``."""

    def confirm(name: str, args: Mapping[str, Any]) -> str | None:
        log.append(name)
        return answer

    return confirm


def _recorded(log: list[str], tag: str, result: str) -> Handler:
    """A handler that records its call under ``tag`` and returns ``result``."""

    def handler(args: Mapping[str, Any]) -> str:
        log.append(tag)
        return result

    return handler


# ---------------------------------------------------------------- calibration (D3)


def test_softmax_is_a_distribution_and_stable_for_large_logits() -> None:
    probs = softmax([1000.0, 999.0, -1000.0])
    assert math.isclose(sum(probs), 1.0)
    assert probs[0] > probs[1] > probs[2]


def test_softmax_rejects_bad_temperature_and_non_finite_logits() -> None:
    with pytest.raises(ValueError):
        softmax([1.0, 2.0], 0.0)
    with pytest.raises(ValueError):
        softmax([1.0, math.nan])


def test_fit_temperature_softens_overconfident_logits() -> None:
    # The model is right 60% of the time but its logits say 10 to 0 every time: too confident.
    rows = [[10.0, 0.0]] * 10
    labels = [0] * 6 + [1] * 4
    temperature = fit_temperature(rows, labels)

    def nll(t: float) -> float:
        return -sum(math.log(softmax(r, t)[y]) for r, y in zip(rows, labels, strict=True)) / len(labels)

    assert temperature > 1.0
    assert nll(temperature) < nll(1.0)


def test_fit_temperature_is_deterministic() -> None:
    rows = [[2.0, 0.5, -1.0], [0.1, 0.2, 0.3], [3.0, 0.0, 0.0]]
    labels = [0, 2, 1]
    assert fit_temperature(rows, labels) == fit_temperature(rows, labels)


def test_fit_temperature_checks_its_inputs() -> None:
    with pytest.raises(ValueError):
        fit_temperature([[1.0, 2.0]], [0, 1])
    with pytest.raises(ValueError):
        fit_temperature([[1.0, 2.0]], [5])
    with pytest.raises(ValueError):
        fit_temperature([[1.0]], [0])


def test_ece_is_zero_when_confidence_matches_accuracy() -> None:
    assert expected_calibration_error([1.0, 1.0], [True, True]) == 0.0


def test_ece_measures_the_gap_in_its_bin() -> None:
    # Confidence 0.9 falls in the top bin, and every answer there is right: the gap is 0.1.
    assert math.isclose(expected_calibration_error([0.9, 0.9], [True, True]), 0.1)


def test_choose_threshold_takes_the_lowest_threshold_that_meets_the_target() -> None:
    confidences = [0.9, 0.9, 0.8, 0.8, 0.7, 0.6, 0.5]
    correct = [True, True, True, False, True, False, False]
    policy = choose_threshold(confidences, correct, target_precision=0.7, min_support=2)
    assert policy is not None
    assert policy.threshold == 0.7
    assert policy.support == 5
    assert math.isclose(policy.precision, 0.8)
    assert math.isclose(policy.coverage, 5 / 7)


def test_choose_threshold_respects_the_target_and_support() -> None:
    confidences = [0.9, 0.9, 0.8, 0.8, 0.7, 0.6, 0.5]
    correct = [True, True, True, False, True, False, False]
    strict = choose_threshold(confidences, correct, target_precision=0.95, min_support=2)
    assert strict is not None and strict.threshold == 0.9
    assert choose_threshold(confidences, correct, target_precision=0.95, min_support=3) is None


def test_choose_threshold_returns_none_when_nothing_meets_the_target() -> None:
    assert choose_threshold([0.9, 0.8], [False, False], target_precision=0.9, min_support=1) is None


def test_abstention_policy_answers_at_and_above_its_threshold() -> None:
    policy = AbstentionPolicy(threshold=0.8, target_precision=0.9, precision=0.95, coverage=0.5, support=10)
    assert policy.answers(0.8)
    assert not policy.answers(0.79)


# ---------------------------------------------------------------- learned backend (D2)


class _Stub:
    def __init__(self, logits: list[float], labels: tuple[str, ...] = ("read", "delete")) -> None:
        self._logits = logits
        self._labels = labels

    @property
    def labels(self) -> tuple[str, ...]:
        return self._labels

    def logits(self, text: str) -> list[float]:
        return list(self._logits)


_POLICY = AbstentionPolicy(threshold=0.8, target_precision=0.9, precision=0.95, coverage=0.5, support=10)


def test_decide_label_answers_when_the_probability_clears_the_threshold() -> None:
    decision = decide_label(
        _Stub([6.0, 0.0]), "show a file", temperature=1.0, policy=_POLICY,
        model=ModelRef(name="t1", digest="ab" * 32, provenance="test"),
    )
    assert not decision.abstained
    assert decision.label == "read"
    assert decision.model is not None and decision.model.name == "t1"


def test_decide_label_abstains_below_the_threshold_and_keeps_the_best_guess() -> None:
    decision = decide_label(_Stub([0.1, 0.0]), "unclear", temperature=1.0, policy=_POLICY)
    assert decision.abstained
    assert decision.label is None
    assert decision.best_label == "read"


@pytest.mark.parametrize(
    ("backend", "temperature", "why"),
    [
        (_Stub([1.0, 2.0, 3.0]), 1.0, "wrong number of logits"),
        (_Stub([math.nan, 0.0]), 1.0, "non-finite logit"),
        (_Stub([9.0, 0.0]), 0.0, "invalid temperature"),
        (_Stub([9.0], labels=("only",)), 1.0, "too few labels"),
    ],
)
def test_decide_label_fails_closed(backend: _Stub, temperature: float, why: str) -> None:
    decision = decide_label(backend, "x", temperature=temperature, policy=_POLICY)
    assert decision.abstained and decision.label is None, why


# ---------------------------------------------------------------- path scope (G2, partly)


@pytest.fixture()
def scope(tmp_path: Path) -> PathScope:
    root = tmp_path / "workspace"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.rs").write_text("fn main() {}", encoding="utf-8")
    return PathScope(root)


def test_paths_inside_the_scope_resolve(scope: PathScope) -> None:
    assert scope.resolve("src/main.rs") == scope.root / "src" / "main.rs"
    assert scope.resolve("src\\main.rs") == scope.root / "src" / "main.rs"
    assert scope.resolve(".") == scope.root
    assert scope.resolve("new/not-yet.txt") == scope.root / "new" / "not-yet.txt"


@pytest.mark.parametrize(
    "bad",
    [
        "../secret.txt",
        "src/../../secret.txt",
        "/etc/passwd",
        "\\\\server\\share\\file",
        "C:evil.txt",
        "C:\\Windows\\win.ini",
        "notes.txt:hidden",
        "CON",
        "con.txt",
        "nul.log",
        "COM1",
        "lpt9.txt",
        "",
        "bad\x00name",
    ],
)
def test_escaping_or_unsafe_paths_are_refused(scope: PathScope, bad: str) -> None:
    with pytest.raises(PathEscape):
        scope.resolve(bad)


def test_a_sibling_folder_with_the_same_prefix_is_outside(tmp_path: Path) -> None:
    root = tmp_path / "scope"
    sibling = tmp_path / "scope-evil"
    root.mkdir()
    sibling.mkdir()
    (sibling / "f.txt").write_text("x", encoding="utf-8")
    scoped = PathScope(root)
    assert not scoped.contains(sibling / "f.txt")
    assert scoped.contains(root)


def test_a_link_out_of_the_scope_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "scope"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "f.txt").write_text("x", encoding="utf-8")
    try:
        os.symlink(outside, root / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("creating symbolic links needs a privilege on this host")
    with pytest.raises(PathEscape):
        PathScope(root).resolve("link/f.txt")


def test_the_scope_root_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        PathScope(tmp_path / "missing")


# ---------------------------------------------------------------- tool host (A2, A3, G1)


def _contract(
    name: str,
    schema: dict[str, object],
    *,
    risk: MaxSafetyTier = MaxSafetyTier.LOW,
    confirmation: ToolConfirmation = ToolConfirmation.NONE,
    network: ToolNetwork = ToolNetwork.NONE,
    confinement: ToolConfinement = ToolConfinement.NONE,
) -> ToolContract:
    return ToolContract(
        name=name,
        schema_json=canonical_text(schema),
        risk_tier=risk,
        confirmation=confirmation,
        network=network,
        confinement=confinement,
    )


_PATH_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 200}},
    "required": ["path"],
    "additionalProperties": False,
}


def test_a_read_tool_runs_and_is_audited(scope: PathScope) -> None:
    host = ToolHost(scope)
    seen: list[dict[str, object]] = []

    def handler(args: Mapping[str, Any]) -> str:
        seen.append(dict(args))
        return "contents"

    host.register(
        _contract("read_file", _PATH_SCHEMA, confinement=ToolConfinement.SCOPED), handler, path_args=("path",)
    )
    result = host.call("read_file", {"path": "src/main.rs"})
    assert result.ok and result.output == "contents" and result.outcome == "ran"
    assert seen[0]["path"] == str(scope.root / "src" / "main.rs")
    assert len(host.audit()) == 1
    assert verify_chain(host.audit())


def test_unknown_tools_and_bad_arguments_are_refused(scope: PathScope) -> None:
    host = ToolHost(scope)
    host.register(
        _contract("read_file", _PATH_SCHEMA, confinement=ToolConfinement.SCOPED),
        lambda args: "x",
        path_args=("path",),
    )
    with pytest.raises(ToolRefused):
        host.call("delete_everything", {})
    with pytest.raises(ToolRefused):
        host.call("read_file", {})
    with pytest.raises(ToolRefused):
        host.call("read_file", {"path": "src/main.rs", "extra": "x"})
    with pytest.raises(ToolRefused):
        host.call("read_file", {"path": 5})
    assert [r.outcome for r in host.audit()] == ["refused_unknown", "refused_invalid", "refused_invalid", "refused_invalid"]


def test_a_path_outside_the_scope_is_refused_before_anyone_is_asked(scope: PathScope) -> None:
    host = ToolHost(scope)
    asked: list[str] = []
    host.register(
        _contract("write_file", _PATH_SCHEMA, risk=MaxSafetyTier.MEDIUM, confirmation=ToolConfirmation.ALWAYS,
                  confinement=ToolConfinement.SCOPED),
        lambda args: "written",
        path_args=("path",),
    )
    with pytest.raises(ToolRefused):
        host.call("write_file", {"path": "../escape.txt"}, confirm=_approve(asked, "alice"))
    assert asked == []
    assert host.audit()[-1].outcome == "refused_path"


def test_an_always_confirmed_tool_needs_a_person_each_time() -> None:
    host = ToolHost()
    ran: list[str] = []
    host.register(
        _contract("run_tests", {"type": "object", "properties": {}, "additionalProperties": False},
                  risk=MaxSafetyTier.HIGH, confirmation=ToolConfirmation.ALWAYS,
                  confinement=ToolConfinement.SCOPED),
        _recorded(ran, "ran", "green"),
    )
    with pytest.raises(ToolRefused):
        host.call("run_tests", {})
    declined = host.call("run_tests", {}, confirm=lambda n, a: None)
    assert not declined.ok and declined.outcome == "declined"
    approved = host.call("run_tests", {}, confirm=lambda n, a: "alice")
    assert approved.ok and approved.confirmation is not None and approved.confirmation.approver == "alice"
    assert ran == ["ran"]
    assert verify_chain(host.audit())


def test_an_on_first_use_tool_asks_once() -> None:
    host = ToolHost()
    asked: list[str] = []
    host.register(
        _contract("list_files", {"type": "object", "properties": {}, "additionalProperties": False},
                  confirmation=ToolConfirmation.ON_FIRST_USE),
        lambda args: "a.txt",
    )
    host.call("list_files", {}, confirm=_approve(asked, "bob"))
    host.call("list_files", {}, confirm=_approve(asked, "bob"))
    assert asked == ["list_files"]


def test_a_failing_handler_is_recorded_and_reported() -> None:
    host = ToolHost()

    def broken(args: Mapping[str, Any]) -> str:
        raise OSError("disk gone")

    host.register(_contract("noop", {"type": "object", "properties": {}, "additionalProperties": False}), broken)
    result = host.call("noop", {})
    assert not result.ok and result.outcome == "failed" and "disk gone" in result.output
    assert host.audit()[-1].outcome == "failed"


def test_the_audit_chain_detects_tampering() -> None:
    host = ToolHost()
    host.register(_contract("noop", {"type": "object", "properties": {}, "additionalProperties": False}),
                  lambda args: "ok")
    host.call("noop", {})
    host.call("noop", {})
    records = host.audit()
    assert verify_chain(records)
    tampered = [records[0], replace(records[1], outcome="ran_twice")]
    assert not verify_chain(tampered)
    assert not verify_chain([records[1]])


def test_the_sink_sees_every_record() -> None:
    seen: list[AuditRecord] = []
    host = ToolHost(sink=seen.append)
    with pytest.raises(ToolRefused):
        host.call("missing", {})
    assert [r.outcome for r in seen] == ["refused_unknown"]


def test_registration_refuses_contracts_it_cannot_serve(scope: PathScope) -> None:
    host = ToolHost(scope)
    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    # HIGH risk with no confirmation fails the contract's own rule.
    with pytest.raises(ToolRegistrationError):
        host.register(_contract("bad_high", empty, risk=MaxSafetyTier.HIGH, confinement=ToolConfinement.SCOPED),
                      lambda a: "x")
    # A keyword the validator does not enforce is refused, so the host fails closed.
    with pytest.raises(ToolRegistrationError):
        host.register(_contract("bad_pattern", {"type": "object", "properties": {"p": {"type": "string",
                                                                                     "pattern": ".*"}}}),
                      lambda a: "x")
    # Path arguments need confinement.
    with pytest.raises(ToolRegistrationError):
        host.register(_contract("bad_path", _PATH_SCHEMA), lambda a: "x", path_args=("path",))
    host.register(_contract("ok", empty), lambda a: "x")
    with pytest.raises(ToolRegistrationError):
        host.register(_contract("ok", empty), lambda a: "x")


def test_schema_helpers_check_what_they_claim() -> None:
    check_schema(_PATH_SCHEMA)
    with pytest.raises(ToolRegistrationError):
        check_schema({"type": "string"})
    assert validate_args(_PATH_SCHEMA, {"path": "a"}) == []
    assert validate_args(_PATH_SCHEMA, {}) == ["missing path"]
    assert validate_args(_PATH_SCHEMA, {"path": "a", "x": "b"}) == ["unexpected x"]
    assert validate_args(_PATH_SCHEMA, {"path": True}) == ["path must be a string"]
