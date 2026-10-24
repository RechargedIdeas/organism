"""Structural router — Artifact C decision procedure (M3).

Stateless evaluator over RouterPolicyArtifact + registry snapshot + level.
Deterministic given identical inputs (C.4 invariant 8).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from organism_sdk.contract import ModuleRole, ReliabilityTier
from organism_sdk.registry import ModuleHandle, RegistryClient
from organism_sdk.autonomic import RouterExposedParams
from organism_sdk.hormone import HormoneBus, HormoneReading
from organism_sdk.trace import RoutingTraceEntry, TraceEmitter

Level = Literal["L0", "L1", "L2", "L3", "L4"]
PlanType = Literal["DispatchPlan", "DegradedDispatchPlan"]

# Default form → roles (C.3 Step 1)
DEFAULT_FORM_TO_ROLES: dict[str, tuple[str, ...]] = {
    "temporal_prediction": ("PREDICTION", "FRONTEND", "FEATURE_EXTRACTOR"),
    "pattern_recognition": ("PERCEPTION", "PREDICTION"),
    "anomaly_detection": ("SENTINEL", "PREDICTION"),
    "constrained_allocation": ("SOLVER",),
    "causal_inference": ("VERIFIER", "GOVERNANCE"),
    "symbolic_reasoning": ("VERIFIER", "GOVERNANCE", "MEMORY"),
    "signal_analysis": ("FRONTEND", "FEATURE_EXTRACTOR"),
    "feature_extraction": ("FEATURE_EXTRACTOR", "FRONTEND"),
    "retrieval": ("MEMORY",),
    "generation": ("PREDICTION", "PERCEPTION"),
    "calibration": ("VERIFIER", "GOVERNANCE"),
    "verification": ("VERIFIER", "GOVERNANCE"),
    "control_actuation": ("ACTUATOR", "GOVERNANCE", "VERIFIER"),
}

# Safety tier → allowed module tiers (C.3 Step 2)
# Correction 1.1: control_actuation may use T0 at high/critical (overrides medium/high table).
TIER_ELIGIBILITY: dict[str, set[str]] = {
    "critical": {"T0_DETERMINISTIC", "T1_CALIBRATED_NONLEARNED"},
    "high": {"T0_DETERMINISTIC", "T1_CALIBRATED_NONLEARNED", "T2_LEARNED_CALIBRATED"},
    "medium": {
        "T0_DETERMINISTIC",
        "T1_CALIBRATED_NONLEARNED",
        "T2_LEARNED_CALIBRATED",
        "T3_LEARNED_UNCALIBRATED",
    },
    "low": {
        "T0_DETERMINISTIC",
        "T1_CALIBRATED_NONLEARNED",
        "T2_LEARNED_CALIBRATED",
        "T3_LEARNED_UNCALIBRATED",
    },
    "research": {
        "T0_DETERMINISTIC",
        "T1_CALIBRATED_NONLEARNED",
        "T2_LEARNED_CALIBRATED",
        "T3_LEARNED_UNCALIBRATED",
    },
}

LEVEL_ELIGIBILITY: dict[str, tuple[set[str], PlanType]] = {
    "L0": (
        {
            "PERCEPTION", "PREDICTION", "SENTINEL", "SOLVER", "VERIFIER",
            "GOVERNANCE", "FEATURE_EXTRACTOR", "MEMORY", "ACTUATOR", "FRONTEND",
        },
        "DispatchPlan",
    ),
    "L1": (
        {
            "PERCEPTION", "PREDICTION", "SENTINEL", "SOLVER", "VERIFIER",
            "GOVERNANCE", "FEATURE_EXTRACTOR", "MEMORY", "ACTUATOR", "FRONTEND",
        },
        "DispatchPlan",
    ),
    "L2": (
        {"SOLVER", "VERIFIER", "GOVERNANCE", "FRONTEND", "FEATURE_EXTRACTOR", "MEMORY", "ACTUATOR"},
        "DegradedDispatchPlan",
    ),
    "L3": ({"MEMORY", "GOVERNANCE"}, "DegradedDispatchPlan"),
    "L4": ({"GOVERNANCE"}, "DegradedDispatchPlan"),  # deterministic engine only
}

_TIER_RANK = {
    "T0_DETERMINISTIC": 0,
    "T1_CALIBRATED_NONLEARNED": 1,
    "T2_LEARNED_CALIBRATED": 2,
    "T3_LEARNED_UNCALIBRATED": 3,
}


@dataclass(frozen=True)
class RouterTask:
    task_id: str
    form: str
    safety_tier: str
    deadline_ms: float = 1000.0
    energy_budget_j: float = 10.0
    requires_uncertainty: bool = False
    requires_interpretability: bool = False
    requires_determinism: bool = False
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RouterPolicyArtifact:
    policy_id: str
    version: str
    digest: bytes
    lifecycle_state: str = "DELIBERATION"
    form_to_roles: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(DEFAULT_FORM_TO_ROLES)
    )


@dataclass
class Excluded:
    module_id: str
    reason_code: str
    reason_params: dict[str, str] = field(default_factory=dict)


@dataclass
class DispatchPlan:
    plan_id: str
    task_id: str
    policy_id: str
    policy_digest: bytes
    level: Level
    plan_type: PlanType
    primary: ModuleHandle | None
    fallbacks: list[ModuleHandle]
    constraints_applied: list[str]
    excluded: list[Excluded]
    ranking_trace: list[str]
    cross_check_required: bool
    cross_check_module: ModuleHandle | None
    justification_required: str
    disposition: str = "DISPATCH"  # DISPATCH | HOLD (degraded)
    hold_reason: str | None = None
    candidate_roles: list[str] = field(default_factory=list)

    def to_canonical_bytes(self) -> bytes:
        """Byte-stable serialization for determinism tests (excludes plan_id randomness if fixed)."""
        body = {
            "task_id": self.task_id,
            "policy_id": self.policy_id,
            "policy_digest": self.policy_digest.hex(),
            "level": self.level,
            "plan_type": self.plan_type,
            "primary": None if self.primary is None else self.primary.module_id,
            "fallbacks": [f.module_id for f in self.fallbacks],
            "constraints_applied": self.constraints_applied,
            "excluded": [(e.module_id, e.reason_code) for e in self.excluded],
            "ranking_trace": self.ranking_trace,
            "cross_check_required": self.cross_check_required,
            "cross_check_module": None
            if self.cross_check_module is None
            else self.cross_check_module.module_id,
            "justification_required": self.justification_required,
            "disposition": self.disposition,
            "hold_reason": self.hold_reason,
            "candidate_roles": self.candidate_roles,
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def default_bootstrap_policy() -> RouterPolicyArtifact:
    body = json.dumps({"form_to_roles": DEFAULT_FORM_TO_ROLES}, sort_keys=True).encode()
    return RouterPolicyArtifact(
        policy_id="organism.router.bootstrap",
        version="0.1.0",
        digest=hashlib.sha256(body).digest(),
        lifecycle_state="DELIBERATION",
    )


class Router:
    """Artifact C evaluator."""

    def __init__(
        self,
        registry: RegistryClient,
        policy: RouterPolicyArtifact | None = None,
        *,
        level: Level = "L0",
        health: dict[str, str] | None = None,
        trace: TraceEmitter | None = None,
        plan_id_factory: Any = None,
        hormone_bus: HormoneBus | None = None,
        autonomic_params: RouterExposedParams | None = None,
    ) -> None:
        self._registry = registry
        self._policy = policy or default_bootstrap_policy()
        self._level: Level = level
        self._health = health or {}
        self._trace = trace or TraceEmitter()
        self._plan_id_factory = plan_id_factory or (lambda: str(uuid4()))
        self._hormone_bus = hormone_bus
        self._autonomic = autonomic_params or RouterExposedParams()

    def set_level(self, level: Level) -> None:
        self._level = level

    def set_autonomic_params(self, params: RouterExposedParams) -> None:
        self._autonomic = params

    def attach_hormone_bus(self, bus: HormoneBus) -> None:
        self._hormone_bus = bus

    @property
    def autonomic_params(self) -> RouterExposedParams:
        return self._autonomic

    def current_policy_id(self) -> str:
        return self._policy.policy_id

    def current_policy_digest(self) -> bytes:
        return self._policy.digest

    def current_level(self) -> str:
        return self._level

    def decide(self, task: RouterTask) -> DispatchPlan:
        # Step 0
        if not task.task_id or not task.form or task.safety_tier in ("", "UNSPECIFIED"):
            return self._hold(task, "invalid_task_descriptor", [])

        if self._policy.lifecycle_state != "DELIBERATION":
            return self._hold(task, "policy_not_deliberation", [])

        hormone_reading: HormoneReading | None = None
        if self._hormone_bus is not None:
            hormone_reading = self._hormone_bus.read_mirror(consumer="router")

        # Step 1
        roles = list(self._policy.form_to_roles.get(task.form, ()))
        if not roles:
            return self._hold(task, "unknown_form", [])

        # Step 3 plan type
        eligible_roles, plan_type = LEVEL_ELIGIBILITY[self._level]
        constraints = [f"level:{self._level}", f"form:{task.form}", f"safety:{task.safety_tier}"]

        # Gather modules
        all_handles = self._registry.query(
            __import__("organism_sdk.registry", fromlist=["CapabilityFilter"]).CapabilityFilter(
                min_lifecycle_state="DELIBERATION"
            )
        )
        excluded: list[Excluded] = []
        candidates: list[ModuleHandle] = []

        allowed_tiers = TIER_ELIGIBILITY.get(task.safety_tier, set())
        # Correction 1.1: control_actuation at high/critical prefers T0 GOVERNANCE/ACTUATOR
        if task.form == "control_actuation":
            allowed_tiers = {"T0_DETERMINISTIC", "T1_CALIBRATED_NONLEARNED"}

        for h in all_handles:
            role = h.role.value if hasattr(h.role, "value") else str(h.role)
            tier = h.tier.value if hasattr(h.tier, "value") else str(h.tier)
            if role not in roles:
                excluded.append(Excluded(h.module_id, "role_mismatch", {"role": role}))
                continue
            if role not in eligible_roles:
                excluded.append(Excluded(h.module_id, "level_ineligible", {"level": self._level}))
                continue
            if tier not in allowed_tiers:
                excluded.append(Excluded(h.module_id, "tier_ineligible", {"tier": tier}))
                continue
            # C.4.4: critical never to T2/T3
            if task.safety_tier == "critical" and tier in (
                "T2_LEARNED_CALIBRATED",
                "T3_LEARNED_UNCALIBRATED",
            ):
                excluded.append(Excluded(h.module_id, "critical_forbids_learned", {}))
                continue
            # L4: deterministic engine only (module_id check)
            if self._level == "L4" and h.module_id != "deterministic_engine":
                excluded.append(Excluded(h.module_id, "l4_deterministic_only", {}))
                continue
            hs = self._health.get(h.module_id, "HEALTHY")
            if hs == "FAILED":
                excluded.append(Excluded(h.module_id, "health_failed", {}))
                continue
            # interpretability: require T0/T1 if requested (correction 1.3)
            if task.requires_interpretability and tier in (
                "T2_LEARNED_CALIBRATED",
                "T3_LEARNED_UNCALIBRATED",
            ):
                excluded.append(Excluded(h.module_id, "interpretability_required", {}))
                continue
            candidates.append(h)

        # Step 5 re-rank
        ranking_trace: list[str] = []

        def sort_key(h: ModuleHandle) -> tuple:
            tier = h.tier.value if hasattr(h.tier, "value") else str(h.tier)
            hs = self._health.get(h.module_id, "HEALTHY")
            health_rank = 0 if hs == "HEALTHY" else 1
            return (health_rank, _TIER_RANK.get(tier, 9), h.module_id)

        candidates.sort(key=sort_key)
        ranking_trace.append(f"order={[c.module_id for c in candidates]}")

        cross_check_required = task.form == "control_actuation" or self._level in ("L2", "L3", "L4")
        if self._autonomic.cross_check_frequency > 1.0:
            cross_check_required = True
        if hormone_reading is not None and hormone_reading.levels.cortisol >= 0.5:
            cross_check_required = True
        if self._autonomic.exploration_budget <= 0.0 and task.safety_tier == "research":
            return self._hold(task, "exploration_budget_exhausted", [])
        if self._autonomic.preemption_class == "PREEMPT_RESEARCH" and task.safety_tier == "research":
            return self._hold(task, "preempt_research", [])
        # T0 proposer does not require cross-check for control (E.4)
        cross_mod = None
        if candidates:
            primary_tier = (
                candidates[0].tier.value if hasattr(candidates[0].tier, "value") else str(candidates[0].tier)
            )
            if primary_tier == "T0_DETERMINISTIC" and task.form == "control_actuation":
                cross_check_required = False
            elif cross_check_required:
                for h in all_handles:
                    role = h.role.value if hasattr(h.role, "value") else str(h.role)
                    if role in ("VERIFIER", "GOVERNANCE") and h.module_id != (
                        candidates[0].module_id if candidates else ""
                    ):
                        cross_mod = h
                        break
                if cross_check_required and cross_mod is None and self._level in ("L2", "L3", "L4"):
                    # correction 1.6 — null cross-check forces HOLD when required
                    return self._hold(
                        task,
                        "cross_check_unavailable",
                        excluded,
                        roles=roles,
                        constraints=constraints,
                        plan_type=plan_type,
                    )

        justification = "RULE_TRACE" if task.form == "control_actuation" else "NONE"
        if self._level in ("L2", "L3", "L4") and task.form == "control_actuation":
            justification = "RULE_TRACE"

        if not candidates:
            return self._hold(
                task,
                "no_eligible_candidates",
                excluded,
                roles=roles,
                constraints=constraints,
                plan_type=plan_type,
            )

        primary = candidates[0]
        fallbacks = candidates[1:] if plan_type == "DispatchPlan" else []

        plan = DispatchPlan(
            plan_id=self._plan_id_factory(),
            task_id=task.task_id,
            policy_id=self._policy.policy_id,
            policy_digest=self._policy.digest,
            level=self._level,
            plan_type=plan_type,
            primary=primary,
            fallbacks=fallbacks,
            constraints_applied=constraints,
            excluded=excluded,
            ranking_trace=ranking_trace,
            cross_check_required=cross_check_required,
            cross_check_module=cross_mod,
            justification_required=justification,
            disposition="DISPATCH",
            candidate_roles=roles,
        )
        rationale: dict[str, Any] = {
            "ranking_trace": ranking_trace,
            "excluded": [e.reason_code for e in excluded],
            "autonomic": self._autonomic.as_dict(),
        }
        if hormone_reading is not None:
            rationale["hormone"] = {
                "cortisol": hormone_reading.levels.cortisol,
                "dopamine": hormone_reading.levels.dopamine,
                "oxytocin": hormone_reading.levels.oxytocin,
                "melatonin": hormone_reading.levels.melatonin,
                "staleness_ms": hormone_reading.staleness_ms,
                "digest": hormone_reading.digest,
                "source": hormone_reading.source,
            }
        self._trace.emit_routing(
            RoutingTraceEntry(
                task_id=task.task_id,
                form=task.form,
                plan_type=plan_type,
                primary_module_id=primary.module_id,
                rationale=rationale,
            )
        )
        return plan

    def _hold(
        self,
        task: RouterTask,
        reason: str,
        excluded: list[Excluded],
        *,
        roles: list[str] | None = None,
        constraints: list[str] | None = None,
        plan_type: PlanType | None = None,
    ) -> DispatchPlan:
        _, default_pt = LEVEL_ELIGIBILITY[self._level]
        pt = plan_type or default_pt
        plan = DispatchPlan(
            plan_id=self._plan_id_factory(),
            task_id=task.task_id,
            policy_id=self._policy.policy_id,
            policy_digest=self._policy.digest,
            level=self._level,
            plan_type=pt if pt == "DegradedDispatchPlan" else "DegradedDispatchPlan",
            primary=None,
            fallbacks=[],
            constraints_applied=constraints or [],
            excluded=excluded,
            ranking_trace=[],
            cross_check_required=True,
            cross_check_module=None,
            justification_required="NONE",
            disposition="HOLD",
            hold_reason=reason,
            candidate_roles=list(roles or []),
        )
        self._trace.emit_routing(
            RoutingTraceEntry(
                task_id=task.task_id,
                form=task.form,
                plan_type="DegradedDispatchPlan",
                primary_module_id="",
                rationale={"hold_reason": reason},
            )
        )
        return plan
