"""Build the run report and render it for people. The JSON form is the machine contract."""

from __future__ import annotations

import os
import platform
from collections import Counter
from typing import Any

from organism_ci.execute import FAILING, GateResult
from organism_ci.preflight import Check

SCHEMA = 1
PASSED_STATUSES = frozenset({"PASS", "CACHED", "FLAKY"})


def build(
    *,
    tier: str,
    hook: str | None,
    started: str,
    duration_s: float,
    head: str,
    dirty_paths: int,
    checks: list[Check],
    gates: list[GateResult],
    run_dir: str,
    status: str,
    exit_code: int,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "tier": tier,
        "hook": hook,
        "started": started,
        "duration_s": round(duration_s, 3),
        "status": status,
        "exit_code": exit_code,
        "git": {"head": head, "dirty_paths": dirty_paths},
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpus": os.cpu_count() or 0,
        },
        "preflight": [
            {"name": c.name, "status": c.status, "detail": c.detail, "fix": c.fix} for c in checks
        ],
        "gates": [g.as_dict() for g in gates],
        "summary": summarize(gates),
        "run_dir": run_dir,
    }


def summarize(gates: list[GateResult]) -> dict[str, int]:
    counts: Counter[str] = Counter(g.status for g in gates)
    blocking_failed = sum(1 for g in gates if g.failing)
    advisory_failed = sum(1 for g in gates if not g.blocking and g.status in FAILING)
    return {
        "total": len(gates),
        "passed": sum(counts[s] for s in PASSED_STATUSES),
        "cached": counts["CACHED"],
        "flaky": counts["FLAKY"],
        "failed_blocking": blocking_failed,
        "failed_advisory": advisory_failed,
    }


def render(report: dict[str, Any], *, verbose: bool = False) -> str:
    """Summary for people. Non-verbose output lists only what needs attention; the JSON has all."""
    lines: list[str] = []
    git = report["git"]
    lines.append(
        f"Organism local pipeline | tier={report['tier']} | HEAD {git['head']} "
        f"({git['dirty_paths']} changed) | {report['started']}"
    )

    checks = [c for c in report["preflight"] if verbose or c["status"] != "PASS"]
    if checks:
        lines.append("")
        lines.append("Preflight")
        for check in checks:
            lines.append(f"  {check['status']:<4}  {check['name']:<18} {check['detail']}")
            if check["status"] != "PASS" and check["fix"]:
                lines.append(f"          fix: {check['fix']}")

    gates = [g for g in report["gates"] if verbose or g["status"] not in ("PASS", "CACHED")]
    if gates:
        lines.append("")
        lines.append(f"Gates needing attention ({len(gates)})" if not verbose else f"Gates ({len(gates)})")
    for gate in gates:
        mark = "" if gate["blocking"] else " (advisory)"
        timing = f"{gate['duration_s']:>7.1f}s" if gate["status"] != "CACHED" else "      0s"
        lines.append(f"  {gate['status']:<7} {gate['id']:<30} {timing}{mark}")
        if gate["note"]:
            lines.append(f"          {gate['note']}")
        if gate["log"] and gate["status"] != "PASS":
            lines.append(f"          log: {gate['log']}")

    summary = report["summary"]
    lines.append("")
    lines.append(
        f"Summary: {summary['passed']} passed ({summary['cached']} cached, "
        f"{summary['flaky']} flaky), {summary['failed_blocking']} blocking failure(s), "
        f"{summary['failed_advisory']} advisory failure(s), {report['duration_s']:.1f}s"
    )
    lines.append(f"RESULT: {report['status']} (exit {report['exit_code']})")
    return "\n".join(lines)
