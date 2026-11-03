"""Shadow evaluation for capability routing (v1.11).

Runs the capability scorer over a labeled set and reports per-domain precision.
This is the Phase 2 promote gate from the upgrade plan:

- capability routing: per-domain precision ≥ ``PRECISION_GATE`` with at least
  ``MIN_PREDICTIONS`` expert-routed items per domain;
- structural baseline (form-given items only): precision ≥ ``PRECISION_GATE``,
  so the router's behavior has not regressed.

A label is an expert id, or ``"unsure"`` for queries that no expert should answer.

The labeled set in the repo is synthetic. Passing this gate does not establish
precision on real traffic.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from organism_sdk.moa.experts import Expert
from organism_sdk.moa.scorer import ROUTE_EXPERT, CapabilityScorer

PRECISION_GATE = 0.90
MIN_PREDICTIONS = 5
UNSURE = "unsure"


@dataclass(frozen=True)
class LabeledQuery:
    query: str
    form: str | None
    label: str


@dataclass
class DomainPrecision:
    domain: str
    predicted: int = 0
    correct: int = 0

    @property
    def precision(self) -> float | None:
        return self.correct / self.predicted if self.predicted else None


@dataclass
class RoutingReport:
    total: int
    domains: dict[str, DomainPrecision] = field(default_factory=dict)
    unsure_correct: int = 0
    unsure_total: int = 0
    structural_predicted: int = 0
    structural_correct: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def structural_precision(self) -> float | None:
        if not self.structural_predicted:
            return None
        return self.structural_correct / self.structural_predicted

    @property
    def passed(self) -> bool:
        return not self.failures


def load_labeled(path: Path) -> list[LabeledQuery]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [LabeledQuery(r["query"], r.get("form"), r["label"]) for r in rows]


def _structural_choice(form: str | None, experts: list[Expert]) -> str | None:
    """Stage 1 alone: the expert for a form, when exactly one expert serves it."""
    if form is None:
        return None
    serving = [e.descriptor.expert_id for e in experts if form in e.descriptor.task_forms]
    return serving[0] if len(serving) == 1 else None


def evaluate(
    labeled: Iterable[LabeledQuery],
    experts: list[Expert],
    scorer: CapabilityScorer,
) -> RoutingReport:
    """Score every labeled query and gate the result."""
    by_id = {e.descriptor.expert_id: e for e in experts}
    items = list(labeled)
    report = RoutingReport(total=len(items))

    for item in items:
        candidates = [e for e in experts if item.form is None or item.form in e.descriptor.task_forms]
        decision = scorer.decide(item.query, candidates)

        if item.label == UNSURE:
            report.unsure_total += 1
            if decision.route != ROUTE_EXPERT:
                report.unsure_correct += 1
        if decision.route == ROUTE_EXPERT and decision.expert_id is not None:
            domain = by_id[decision.expert_id].descriptor.domain
            entry = report.domains.setdefault(domain, DomainPrecision(domain))
            entry.predicted += 1
            if decision.expert_id == item.label:
                entry.correct += 1

        if item.form is not None and item.label != UNSURE:
            predicted = _structural_choice(item.form, experts)
            if predicted is not None:
                report.structural_predicted += 1
                if predicted == item.label:
                    report.structural_correct += 1

    for domain, entry in sorted(report.domains.items()):
        if entry.predicted < MIN_PREDICTIONS:
            report.failures.append(f"{domain}: only {entry.predicted} predictions (need {MIN_PREDICTIONS})")
        elif entry.precision is not None and entry.precision < PRECISION_GATE:
            report.failures.append(f"{domain}: precision {entry.precision:.2f} < {PRECISION_GATE}")
    if not report.domains:
        report.failures.append("no expert-routed predictions in any domain")
    if report.structural_precision is not None and report.structural_precision < PRECISION_GATE:
        report.failures.append(
            f"structural baseline precision {report.structural_precision:.2f} < {PRECISION_GATE}"
        )
    return report
