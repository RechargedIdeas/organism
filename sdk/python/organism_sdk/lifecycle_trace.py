"""Lifecycle-trace invariants (LCT), including OC-2 / OC-12.

LCT-3 (R-38): WARNING-severity ``validation_issues`` do not reject an otherwise
accepted operation. LCT-12 (R-37): a ROLLBACK entry that names
``rollback_of_entry_id`` must point at a prior promote (or register) entry for
the same target.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from organism_sdk.contract import Severity, ValidationIssue
from organism_sdk.trace import LifecycleTraceEntry


@dataclass(frozen=True)
class LCTViolation:
    code: str
    field_path: str
    message: str


def _severity_of(issue: Any) -> str:
    sev = getattr(issue, "severity", None)
    if sev is None and isinstance(issue, dict):
        sev = issue.get("severity")
    if hasattr(sev, "value"):
        return str(sev.value)
    return str(sev or "")


def validate_lct3(entry: LifecycleTraceEntry) -> list[LCTViolation]:
    """LCT-3: WARNING issues are tolerated on accepted operations; ERRORs are not
    silently dropped. This helper only flags ERROR issues left on an entry whose
    event/operation claims acceptance (promote/rollback/register without reject).
    """
    out: list[LCTViolation] = []
    issues = list(entry.validation_issues or [])
    errors = [i for i in issues if _severity_of(i) == Severity.ERROR.value or _severity_of(i) == "ERROR"]
    warnings = [i for i in issues if _severity_of(i) == Severity.WARNING.value or _severity_of(i) == "WARNING"]
    # Warnings alone never constitute a violation (R-38).
    _ = warnings
    op = (entry.operation or entry.event or "").upper()
    accepted_ops = {"PROMOTE", "ROLLBACK", "REGISTER", "promote", "rollback", "register"}
    if errors and (op in accepted_ops or entry.event in ("promote", "rollback", "register")):
        # Callers that already rejected should clear ERROR issues or set outcome rejected.
        # We only warn via LCT when the entry looks accepted but still carries ERRORs.
        if not any(_severity_of(i) == "ERROR" and getattr(i, "code", "") == "rejected" for i in errors):
            out.append(
                LCTViolation(
                    code="lct3_error_on_accepted",
                    field_path="validation_issues",
                    message=f"accepted {op} carries ERROR validation_issues",
                )
            )
    return out


def validate_lct12(
    entry: LifecycleTraceEntry,
    prior: Sequence[LifecycleTraceEntry],
) -> list[LCTViolation]:
    """LCT-12: ROLLBACK with rollback_of_entry_id must reference a prior entry."""
    out: list[LCTViolation] = []
    op = (entry.operation or entry.event or "").upper()
    if op != "ROLLBACK" and entry.event != "rollback":
        return out
    rid = entry.rollback_of_entry_id
    if not rid:
        # Optional: a rollback may omit the link (operator demotion), but when
        # present it must resolve. Absence is allowed.
        return out
    by_id = {e.entry_id: e for e in prior if e.entry_id}
    target = by_id.get(rid)
    if target is None:
        out.append(
            LCTViolation(
                code="lct12_unknown_rollback_target",
                field_path="rollback_of_entry_id",
                message=f"no prior entry with entry_id={rid!r}",
            )
        )
        return out
    if target.module_id and entry.module_id and target.module_id != entry.module_id:
        out.append(
            LCTViolation(
                code="lct12_module_mismatch",
                field_path="rollback_of_entry_id",
                message="rollback target belongs to a different module",
            )
        )
    target_op = (target.operation or target.event or "").upper()
    if target_op not in {"PROMOTE", "REGISTER", "HOT_SWAP", "promote", "register", "hot_swap", "HOT_SWAP"}:
        out.append(
            LCTViolation(
                code="lct12_target_not_promote",
                field_path="rollback_of_entry_id",
                message=f"rollback target operation is {target_op!r}, not a promote/register",
            )
        )
    return out


def validate_lifecycle_entry(
    entry: LifecycleTraceEntry,
    prior: Sequence[LifecycleTraceEntry] = (),
) -> list[ValidationIssue]:
    """Run LCT-3 and LCT-12; return SDK ValidationIssues (ERROR severity)."""
    violations = [*validate_lct3(entry), *validate_lct12(entry, prior)]
    return [
        ValidationIssue(Severity.ERROR, v.code, v.field_path, v.message) for v in violations
    ]


__all__ = [
    "LCTViolation",
    "validate_lct3",
    "validate_lct12",
    "validate_lifecycle_entry",
]
