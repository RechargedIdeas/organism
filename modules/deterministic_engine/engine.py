"""deterministic_engine — T0 GOVERNANCE / L4 ACTUATOR (E.4)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from organism_sdk.contract import (
    BudgetClass,
    CapabilityScopes,
    DataType,
    DegradationKind,
    Determinism,
    EmissionSignature,
    EscalationKind,
    FailureMode,
    FailureSignature,
    HardwareRequirement,
    HealthEscalationPolicy,
    HealthHttp,
    HealthProbe,
    Identity,
    JustificationKind,
    JustificationSpec,
    Lifecycle,
    MaxSafetyTier,
    MetabolicProfile,
    Modality,
    ModuleRole,
    OutputForm,
    PerceptionSignature,
    RecoveryKind,
    RecoveryProcedure,
    ReliabilityTier,
    ResourceVector,
    SafetyDeclaration,
    Shape,
    SubstrateContract,
    UncertaintyKind,
)
from organism_sdk.health import HealthReport
from organism_sdk.inputs import PerceptionInput
from organism_sdk.justification import Emission, JustificationToken
from organism_sdk.module import OrganismModule

MODULE_ID = "deterministic_engine"
MODULE_VERSION = "0.1.0"
RULEBOOK_ID = "organism.t0.default"
RULEBOOK_VERSION = "0.1.0"
RULE_TRACE_FORMAT = "typed-json:rule-trace/v1"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    priority: int
    precondition: str
    action_type: str
    action_body: dict[str, Any]
    constraints: tuple[str, ...] = ()
    documentation: str = ""


@dataclass
class Rulebook:
    rulebook_id: str
    version: str
    rules: list[Rule]
    declared_constraints: tuple[str, ...] = ("safety.hold", "safety.actuate")
    predicates_allowed: tuple[str, ...] = (
        "AND", "OR", "EQ", "IN", "SIGNAL", "LEVEL_IN", "DEADLINE_REMAINING",
    )

    def digest(self) -> bytes:
        body = json.dumps(
            {
                "rulebook_id": self.rulebook_id,
                "version": self.version,
                "rules": [
                    {
                        "rule_id": r.rule_id,
                        "priority": r.priority,
                        "precondition": r.precondition,
                        "action_type": r.action_type,
                        "action_body": r.action_body,
                        "constraints": list(r.constraints),
                    }
                    for r in sorted(self.rules, key=lambda x: x.priority)
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(body).digest()


def build_default_rulebook() -> Rulebook:
    return Rulebook(
        rulebook_id=RULEBOOK_ID,
        version=RULEBOOK_VERSION,
        rules=[
            Rule(
                rule_id="hold_on_critical_without_cert",
                priority=10,
                precondition=(
                    'AND(EQ(SIGNAL("form"),"control_actuation"),'
                    'EQ(SIGNAL("safety_tier"),"critical"))'
                ),
                action_type="HOLD",
                action_body={"reason": "critical_requires_human_path"},
                constraints=("safety.hold",),
                documentation="Hold critical actuation pending human path",
            ),
            Rule(
                rule_id="actuate_control",
                priority=20,
                precondition='EQ(SIGNAL("form"),"control_actuation")',
                action_type="ACTUATE",
                action_body={"disposition": "ALLOW"},
                constraints=("safety.actuate",),
                documentation="Allow non-critical control actuation",
            ),
            Rule(
                rule_id="govern_default",
                priority=100,
                precondition="TRUE",
                action_type="GOVERN",
                action_body={"disposition": "OBSERVE"},
                constraints=("safety.hold",),
                documentation="Default governance observe",
            ),
        ],
    )


def _split_args(s: str) -> list[str]:
    args: list[str] = []
    depth = 0
    in_str = False
    cur: list[str] = []
    quote = ""
    for ch in s:
        if in_str:
            cur.append(ch)
            if ch == quote:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote = ch
            cur.append(ch)
            continue
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        args.append("".join(cur).strip())
    return args


def _eval_atom(atom: str, signals: dict[str, str], level: str, deadline_ms: float) -> Any:
    atom = atom.strip()
    if atom.startswith("SIGNAL("):
        name = atom[len("SIGNAL(") : -1].strip().strip('"').strip("'")
        return signals.get(name)
    if atom.startswith("DEADLINE_REMAINING"):
        return int(deadline_ms)
    if (atom.startswith('"') and atom.endswith('"')) or (atom.startswith("'") and atom.endswith("'")):
        return atom[1:-1]
    return atom


def _eval_precondition(expr: str, signals: dict[str, str], level: str, deadline_ms: float) -> bool:
    expr = expr.strip()
    if expr == "TRUE":
        return True
    if expr.startswith("EQ("):
        parts = _split_args(expr[3:-1])
        if len(parts) != 2:
            return False
        return _eval_atom(parts[0], signals, level, deadline_ms) == _eval_atom(
            parts[1], signals, level, deadline_ms
        )
    if expr.startswith("AND("):
        return all(
            _eval_precondition(a, signals, level, deadline_ms) for a in _split_args(expr[4:-1])
        )
    if expr.startswith("OR("):
        return any(
            _eval_precondition(a, signals, level, deadline_ms) for a in _split_args(expr[3:-1])
        )
    if expr.startswith("LEVEL_IN("):
        body = expr[len("LEVEL_IN(") : -1].strip().strip("[]")
        levels = [x.strip().strip('"').strip("'") for x in body.split(",") if x.strip()]
        return level in levels
    return False


class DeterministicEngine(OrganismModule):
    def __init__(
        self,
        *,
        rulebook: Rulebook | None = None,
        health_port: int = 0,
        level: str = "L0",
    ) -> None:
        self._rulebook = rulebook or build_default_rulebook()
        self._level = level
        self._status = "HEALTHY"
        self._score = 1.0
        self._contract = self._build_contract(health_port)

    def _build_contract(self, health_port: int) -> SubstrateContract:
        # OQ-1 T0 defaults vs REG-9: use probe_interval_ms=1000 so
        # degraded_duration_ms=5000 >= 3*cadence. Documented in STATUS.md.
        url = f"http://127.0.0.1:{health_port or 8765}/health"
        return SubstrateContract(
            identity=Identity(
                module_id=MODULE_ID,
                version=MODULE_VERSION,
                author="organism-ref",
                license="Apache-2.0",
                role=ModuleRole.GOVERNANCE,
                artifact_digest=hashlib.sha256(b"deterministic_engine:0.1.0").digest(),
            ),
            perception=PerceptionSignature(
                modalities=(Modality.TABULAR, Modality.SYMBOL_GRAPH),
                required_modalities=(Modality.TABULAR,),
                shapes={"TABULAR": Shape(dims=(1, 8), dtype=DataType.FP32)},
            ),
            emission=EmissionSignature(
                output_form=OutputForm.SYMBOLIC_TRIPLE,
                shape=Shape(dims=(3,), dtype=DataType.INT64),
                uncertainty=UncertaintyKind.SYMBOLIC_PROOF,
                determinism=Determinism.DETERMINISTIC,
                requires_justification_for=("control_actuation", "govern"),
            ),
            metabolic=MetabolicProfile(
                latency_p50_ms=1.0,
                latency_p95_ms=3.0,
                latency_p99_ms=5.0,
                energy_per_inference_j=0.001,
                memory_footprint_mb=32.0,
                memory_peak_mb=64.0,
                metabolic_budget_class=BudgetClass.LEAN,
                declared_share=ResourceVector(cpu_cores=0.5, memory_mb=64.0),
                requires_special_hardware=HardwareRequirement.NONE,
            ),
            failure=FailureSignature(
                modes=(
                    FailureMode(
                        name="crash",
                        observable_signal="process.alive",
                        expected_degradation=DegradationKind.CRASH,
                        detection_latency_budget_ms=500.0,
                    ),
                ),
                probe=HealthProbe(HealthHttp(url=url, expected_status="200", timeout_ms=400)),
                recovery=RecoveryProcedure(kind=RecoveryKind.RESTART, max_attempts=3),
                escalation=HealthEscalationPolicy(
                    kind=EscalationKind.PROBE_OR_DURATION,
                    consecutive_probe_failures=2,
                    degraded_duration_ms=5000,
                    escalate_on_probe_timeout=True,
                    escalate_on_probe_unreachable=False,
                    probe_interval_ms=1000,
                ),
            ),
            safety=SafetyDeclaration(
                reliability_tier=ReliabilityTier.T0_DETERMINISTIC,
                may_actuate=True,
                requires_causal_certificate=False,
                requires_cross_check=False,
                max_safety_tier=MaxSafetyTier.CRITICAL,
            ),
            lifecycle=Lifecycle(hot_swap_supported=False, shadow_validation_required=False),
            capabilities=CapabilityScopes(
                read_roles=("governance", "memory"),
                write_roles=("governance",),
                read_tags=("*",),
                write_tags=("governance", "decision"),
                can_emit_control_affecting=True,
            ),
            justification=JustificationSpec(
                kind=JustificationKind.RULE_TRACE,
                format=RULE_TRACE_FORMAT,
                required_fields=("evaluation.rule_fired", "engine.rulebook_digest"),
                checkable_by=(ModuleRole.VERIFIER, ModuleRole.GOVERNANCE),
            ),
        )

    def declare_contract(self) -> SubstrateContract:
        return self._contract

    def set_level(self, level: str) -> None:
        self._level = level

    def set_health(self, status: str, score: float = 1.0) -> None:
        self._status = status
        self._score = score

    def health(self) -> HealthReport:
        return HealthReport(module_id=MODULE_ID, status=self._status, score=self._score)

    def handle(self, input: PerceptionInput) -> Emission:
        td = input.task_descriptor
        signals = {"form": td.form, "safety_tier": td.safety_tier, "task_id": td.task_id}
        chain: list[str] = []
        intermediates: list[dict[str, Any]] = []
        fired: Rule | None = None
        for rule in sorted(self._rulebook.rules, key=lambda r: r.priority):
            truth = _eval_precondition(
                rule.precondition, signals, self._level, input.deadline_remaining_ms
            )
            intermediates.append(
                {
                    "rule_id": rule.rule_id,
                    "predicate_truth": truth,
                    "signal_values_used": list(signals.keys()),
                }
            )
            chain.append(rule.rule_id)
            if truth:
                fired = rule
                break
        if fired is None:
            fired = self._rulebook.rules[-1]
        payload = json.dumps(
            {"subject": td.task_id, "predicate": fired.action_type, "object": fired.action_body},
            sort_keys=True,
        ).encode()
        action_class = td.form if td.form in ("control_actuation", "govern") else "govern"
        return Emission(
            action_class=action_class,
            payload=payload,
            metadata={
                "rule_fired": fired.rule_id,
                "rule_chain": ",".join(chain),
                "predicate": fired.precondition,
                "intermediates": json.dumps(intermediates),
            },
        )

    def justify(self, emission: Emission) -> JustificationToken | None:
        rb = self._rulebook
        emitted_at = datetime.now(timezone.utc).isoformat()
        body_obj: dict[str, Any] = {
            "format": RULE_TRACE_FORMAT,
            "engine": {
                "module_id": MODULE_ID,
                "module_version": MODULE_VERSION,
                "contract_digest": self._contract.identity.artifact_digest.hex(),
                "rulebook_id": rb.rulebook_id,
                "rulebook_version": rb.version,
                "rulebook_digest": rb.digest().hex(),
            },
            "input": {"signals_observed": []},
            "evaluation": {
                "rule_fired": emission.metadata.get("rule_fired", ""),
                "rule_chain": emission.metadata.get("rule_chain", "").split(","),
                "predicate_satisfied": emission.metadata.get("predicate", ""),
                "intermediate_results": json.loads(emission.metadata.get("intermediates", "[]")),
            },
            "output": {
                "action": json.loads(emission.payload.decode()),
                "confidence": {"kind": "FIXED_POINT_1E6", "value": 1_000_000},
                "constraints_checked": [],
            },
        }
        canonical = json.dumps(body_obj, sort_keys=True, separators=(",", ":")).encode()
        trace_id = hashlib.sha256(canonical).digest()
        body_obj["trace_id"] = trace_id.hex()
        body_obj["emitted_at"] = emitted_at
        body = json.dumps(body_obj, sort_keys=True, separators=(",", ":")).encode()
        signature = hashlib.sha256(b"t0-rulebook-key:" + body).digest()
        return JustificationToken(
            kind=JustificationKind.RULE_TRACE,
            format=RULE_TRACE_FORMAT,
            body=body,
            signature=signature,
        )
