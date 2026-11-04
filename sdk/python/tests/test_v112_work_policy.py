"""v1.12 policy: the version digest, the shape of admission rows, and the purity of the domain."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest
from organism_sdk import work
from organism_sdk.work.policy import (
    AcceptMode,
    AdmissionRow,
    Cell,
    Policy,
    Rule,
    SourcePolicy,
    may_accept_inferred,
    policy_version,
)

# Pinned: the digest of the empty Policy. A change here means every stored version changed.
EMPTY_POLICY_VERSION = "sha256:7852bfc47aaa792f073e0f8c0c3daf4704b1b1044f2921fec4c772cd84b25fe8"


def base() -> Policy:
    return Policy(
        mode=AcceptMode.OBSERVE,
        rules=(Rule(id="ci-fix", instruction="fix failing CI"),),
        sources=(
            SourcePolicy(
                source="github",
                allowed=frozenset({"Alice"}),
                bots=frozenset({"dependabot[bot]"}),
                rows={"repo": AdmissionRow()},
            ),
        ),
    )


def test_the_empty_policy_has_its_pinned_version() -> None:
    assert policy_version(Policy()) == EMPTY_POLICY_VERSION


def test_equal_policies_have_equal_versions() -> None:
    assert policy_version(base()) == policy_version(base())
    assert base().version == policy_version(base())


def test_sources_order_does_not_change_the_version() -> None:
    github = SourcePolicy(source="github")
    feishu = SourcePolicy(source="feishu")
    assert policy_version(Policy(sources=(github, feishu))) == policy_version(
        Policy(sources=(feishu, github))
    )


def test_ids_compare_case_insensitively() -> None:
    upper = SourcePolicy(source="github", allowed=frozenset({"Alice"}))
    lower = SourcePolicy(source="github", allowed=frozenset({"alice"}))
    assert policy_version(Policy(sources=(upper,))) == policy_version(Policy(sources=(lower,)))


def _with_source(part: SourcePolicy) -> Policy:
    return Policy(mode=AcceptMode.OBSERVE, sources=(part,))


CHANGES: list[tuple[str, Callable[[], Policy]]] = [
    (
        "accept mode",
        lambda: Policy(mode=AcceptMode.AUTO, rules=base().rules, sources=base().sources),
    ),
    (
        "rule text",
        lambda: Policy(
            mode=AcceptMode.OBSERVE,
            rules=(Rule(id="ci-fix", instruction="fix CI differently"),),
            sources=base().sources,
        ),
    ),
    (
        "rule disabled",
        lambda: Policy(
            mode=AcceptMode.OBSERVE,
            rules=(Rule(id="ci-fix", instruction="fix failing CI", enabled=False),),
            sources=base().sources,
        ),
    ),
    (
        "rule added",
        lambda: Policy(
            mode=AcceptMode.OBSERVE,
            rules=base().rules + (Rule(id="docs", instruction="fix docs"),),
            sources=base().sources,
        ),
    ),
    (
        "rule order",
        lambda: Policy(
            mode=AcceptMode.OBSERVE,
            rules=(
                Rule(id="docs", instruction="fix docs"),
                Rule(id="ci-fix", instruction="fix failing CI"),
            ),
            sources=base().sources,
        ),
    ),
    (
        "allowed sender",
        lambda: _with_source(
            SourcePolicy(
                source="github",
                allowed=frozenset({"Alice", "Bob"}),
                bots=frozenset({"dependabot[bot]"}),
                rows={"repo": AdmissionRow()},
            )
        ),
    ),
    (
        "bot list",
        lambda: _with_source(
            SourcePolicy(
                source="github",
                allowed=frozenset({"Alice"}),
                bots=frozenset(),
                rows={"repo": AdmissionRow()},
            )
        ),
    ),
    (
        "admission cell",
        lambda: _with_source(
            SourcePolicy(
                source="github",
                allowed=frozenset({"Alice"}),
                bots=frozenset({"dependabot[bot]"}),
                rows={"repo": AdmissionRow(unlisted_addressed=Cell.EXPLICIT)},
            )
        ),
    ),
    ("source removed", lambda: Policy(mode=AcceptMode.OBSERVE, rules=base().rules)),
]


@pytest.mark.parametrize(("label", "change"), CHANGES, ids=[label for label, _ in CHANGES])
def test_each_decision_input_changes_the_version(label: str, change: Callable[[], Policy]) -> None:
    assert policy_version(change()) != policy_version(base()), label


def test_admission_rows_refuse_an_explicit_unaddressed_cell() -> None:
    with pytest.raises(ValueError, match="addressed"):
        AdmissionRow(listed_unaddressed=Cell.EXPLICIT)
    with pytest.raises(ValueError, match="addressed"):
        AdmissionRow(unlisted_unaddressed=Cell.EXPLICIT)
    AdmissionRow(unlisted_addressed=Cell.EXPLICIT)


def test_a_source_has_one_part_and_a_rule_has_one_id() -> None:
    with pytest.raises(ValueError, match="one part"):
        Policy(sources=(SourcePolicy(source="github"), SourcePolicy(source="github")))
    with pytest.raises(ValueError, match="unique"):
        Policy(rules=(Rule(id="x", instruction="a"), Rule(id="x", instruction="b")))


def test_a_source_part_is_found_by_name() -> None:
    pol = base()
    assert pol.source("github") is not None
    assert pol.source("feishu") is None


@pytest.mark.parametrize(
    ("mode", "matched", "expected"),
    [
        (AcceptMode.AUTO, ["ci-fix"], True),
        (AcceptMode.AUTO, ["docs"], False),
        (AcceptMode.AUTO, [], False),
        (AcceptMode.OBSERVE, ["ci-fix"], False),
        (AcceptMode.OFF, ["ci-fix"], False),
    ],
)
def test_inferred_accept_needs_auto_and_a_matched_enabled_rule(
    mode: AcceptMode, matched: list[str], expected: bool
) -> None:
    pol = Policy(mode=mode, rules=(Rule(id="ci-fix", instruction="fix CI"),))
    assert may_accept_inferred(pol, matched) is expected


def test_a_disabled_rule_does_not_admit_inferred_work() -> None:
    pol = Policy(mode=AcceptMode.AUTO, rules=(Rule(id="ci-fix", instruction="x", enabled=False),))
    assert may_accept_inferred(pol, ["ci-fix"]) is False


FORBIDDEN_IMPORTS = {
    "datetime",
    "http",
    "importlib",
    "logging",
    "os",
    "pathlib",
    "random",
    "shutil",
    "socket",
    "sqlite3",
    "subprocess",
    "sys",
    "tempfile",
    "threading",
    "time",
    "urllib",
}
FORBIDDEN_CALLS = {"input", "open", "print"}
# The store is the only module that does I/O (v1.12 W2); the rest stay pure.
IO_MODULES = {"store.py"}


def _io_findings(path: Path) -> list[str]:
    """The forbidden imports and calls in one module of the package."""
    findings: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                findings.append(f"calls {node.func.id}")
            continue
        else:
            continue
        findings.extend(
            f"imports {name}" for name in names if name.split(".")[0] in FORBIDDEN_IMPORTS
        )
    return findings


def test_the_work_domain_does_no_io() -> None:
    root = Path(work.__file__).parent
    for path in sorted(root.glob("*.py")):
        if path.name not in IO_MODULES:
            assert _io_findings(path) == [], path.name


def test_only_the_store_does_io() -> None:
    root = Path(work.__file__).parent
    assert {path.name for path in root.glob("*.py") if _io_findings(path)} == IO_MODULES
