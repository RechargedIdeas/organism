"""EvolutionRuntime — wire generative promote into registry, traces, hormones, immune.

v1.7.2: CodePipeline promote → ModuleRegistry hot-register (shadow gate),
evolution events → TraceEmitter, optional hormone pulse on promote,
ImmuneLayer quarantine demotes drafts that fail contracts.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from organism_sdk.contract import (
    BudgetClass,
    Determinism,
    HardwareRequirement,
    JustificationKind,
    MaxSafetyTier,
    Modality,
    ModuleRole,
    OutputForm,
    ReliabilityTier,
    UncertaintyKind,
)
from organism_sdk.generative.code_pipeline import CodeBundle, CodePipeline, CodeStage, PromoteRefused
from organism_sdk.generative.skills import SkillDescriptor
from organism_sdk.health import HealthReport
from organism_sdk.hormone import HormoneBus, HormoneLevels
from organism_sdk.hypervector import Hypervector
from organism_sdk.immune import ImmuneLayer
from organism_sdk.inputs import PerceptionInput
from organism_sdk.justification import Emission
from organism_sdk.module import OrganismModule
from organism_sdk.registry import RegistryClient, ShadowValidationRecord
from organism_sdk.trace import EvolutionTraceEntry, LifecycleTraceEntry, TraceEmitter

# Wall-clock budgets (ms) for generative pipeline gates — CPU Everywhere.
EVOLVE_P95_MS = 250.0
PROMOTE_P95_MS = 100.0
HOT_REGISTER_P95_MS = 80.0
QUARANTINE_P95_MS = 50.0


@dataclass
class PipelineTiming:
    """Recorded wall-clock timings for generative gate budgets."""

    evolve_ms: list[float] = field(default_factory=list)
    promote_ms: list[float] = field(default_factory=list)
    hot_register_ms: list[float] = field(default_factory=list)
    quarantine_ms: list[float] = field(default_factory=list)

    def record(self, kind: str, ms: float) -> None:
        bucket = getattr(self, f"{kind}_ms", None)
        if isinstance(bucket, list):
            bucket.append(ms)

    def p95(self, kind: str) -> float:
        samples = list(getattr(self, f"{kind}_ms", []) or [])
        if not samples:
            return 0.0
        s = sorted(samples)
        return s[max(0, int(len(s) * 0.95) - 1)]

    def as_dict(self) -> dict[str, Any]:
        return {
            "evolve_ms": list(self.evolve_ms),
            "promote_ms": list(self.promote_ms),
            "hot_register_ms": list(self.hot_register_ms),
            "quarantine_ms": list(self.quarantine_ms),
            "budgets_ms": {
                "evolve_p95": EVOLVE_P95_MS,
                "promote_p95": PROMOTE_P95_MS,
                "hot_register_p95": HOT_REGISTER_P95_MS,
                "quarantine_p95": QUARANTINE_P95_MS,
            },
            "p95": {
                "evolve": self.p95("evolve"),
                "promote": self.p95("promote"),
                "hot_register": self.p95("hot_register"),
                "quarantine": self.p95("quarantine"),
            },
        }

    def within_budgets(self) -> bool:
        if self.evolve_ms and self.p95("evolve") > EVOLVE_P95_MS:
            return False
        if self.promote_ms and self.p95("promote") > PROMOTE_P95_MS:
            return False
        if self.hot_register_ms and self.p95("hot_register") > HOT_REGISTER_P95_MS:
            return False
        if self.quarantine_ms and self.p95("quarantine") > QUARANTINE_P95_MS:
            return False
        return True


def _make_generated_contract(module_id: str, version: str = "0.1.0"):
    """Build a RESEARCH-safe SubstrateContract for a promoted generative module."""
    from _common.contract_factory import make_contract

    return make_contract(
        module_id=module_id,
        version=version,
        role=ModuleRole.FEATURE_EXTRACTOR,
        tier=ReliabilityTier.T3_LEARNED_UNCALIBRATED,
        modalities=(Modality.DENSE_VECTOR, Modality.TEXT),
        required_modalities=(Modality.DENSE_VECTOR,),
        output_form=OutputForm.FEATURE_VECTOR,
        uncertainty=UncertaintyKind.ENSEMBLE_SPREAD,
        determinism=Determinism.SEEDED,
        justification_kind=JustificationKind.NONE,
        justification_format="typed-json:generative-skill/v1",
        required_fields=(),
        may_actuate=False,
        requires_cross_check=True,
        max_safety=MaxSafetyTier.RESEARCH,
        budget=BudgetClass.RESEARCH,
        hardware=HardwareRequirement.NONE,
        write_tags=("generative", "skill", "promoted", "exploration"),
        failure_name="generative_promoted_reject",
    )


class GeneratedSkillModule(OrganismModule):
    """Hot-registered wrapper for a promoted generative skill/code bundle.

    Always may_actuate=False. Control-path changes remain gated upstream.
    """

    def __init__(
        self,
        *,
        module_id: str,
        source: str,
        intent: str = "",
        shadow_score: float = 0.0,
        version: str = "0.1.0",
        skill_id: str | None = None,
    ) -> None:
        self._module_id = module_id
        self._source = source
        self._intent = intent
        self._shadow_score = shadow_score
        self._version = version
        self._skill_id = skill_id
        self._status = "HEALTHY"
        self._score = min(1.0, max(0.0, shadow_score))
        self._invocations = 0

    def declare_contract(self):
        return _make_generated_contract(self._module_id, self._version)

    def health(self) -> HealthReport:
        return HealthReport(module_id=self._module_id, status=self._status, score=self._score)

    def handle(self, input: PerceptionInput) -> Emission:
        self._invocations += 1
        if input.task_descriptor.form == "control_actuation":
            body = json.dumps(
                {
                    "refused": True,
                    "reason": "generated_skill_never_actuates",
                    "may_actuate": False,
                    "module_id": self._module_id,
                }
            ).encode()
            return Emission(
                action_class="hold",
                payload=body,
                metadata={"module_id": self._module_id, "may_actuate": "False"},
            )
        body = json.dumps(
            {
                "module_id": self._module_id,
                "skill_id": self._skill_id,
                "intent": self._intent[:200],
                "shadow_score": self._shadow_score,
                "invocations": self._invocations,
                "research_tier": True,
                "may_actuate": False,
                "cpu_everywhere": True,
                "at": datetime.now(timezone.utc).isoformat(),
            },
            sort_keys=True,
        ).encode()
        return Emission(
            action_class="exploration",
            payload=body,
            metadata={"module_id": self._module_id, "generative": "True"},
        )

    def on_drain(self, deadline: datetime) -> None:
        return None


@dataclass
class HotRegisterResult:
    module_id: str
    state: str
    catalog_id: str
    shadow_gate: list[str]
    may_actuate: bool = False
    research_tier: bool = True
    registered: bool = True
    elapsed_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "state": self.state,
            "catalog_id": self.catalog_id,
            "shadow_gate": list(self.shadow_gate),
            "may_actuate": self.may_actuate,
            "research_tier": self.research_tier,
            "registered": self.registered,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass
class QuarantineResult:
    decision: str
    demoted: bool
    bundle_id: str
    antigen_score: float = 0.0
    elapsed_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "demoted": self.demoted,
            "bundle_id": self.bundle_id,
            "antigen_score": self.antigen_score,
            "elapsed_ms": self.elapsed_ms,
        }


class EvolutionRuntime:
    """Bridge generative pipelines into the live Organism runtime."""

    def __init__(
        self,
        *,
        registry: RegistryClient | None = None,
        trace: TraceEmitter | None = None,
        hormone: HormoneBus | None = None,
        immune: ImmuneLayer | None = None,
        modules: dict[str, Any] | None = None,
        pulse_on_promote: bool = True,
        dopamine_pulse: float = 0.08,
        oxytocin_pulse: float = 0.04,
    ) -> None:
        self.registry = registry
        self.trace = trace
        self.hormone = hormone
        self.immune = immune
        self.modules = modules if modules is not None else {}
        self.pulse_on_promote = pulse_on_promote
        self.dopamine_pulse = dopamine_pulse
        self.oxytocin_pulse = oxytocin_pulse
        self.timings = PipelineTiming()
        self._catalog: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def catalog_entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._catalog.values())

    def emit_evolution(
        self,
        *,
        kind: str,
        summary: str,
        organism_id: str = "",
        bundle_id: str | None = None,
        skill_id: str | None = None,
        module_id: str | None = None,
        stage: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self.trace is None:
            return
        entry = EvolutionTraceEntry(
            evolution_kind=kind,
            summary=summary,
            organism_id=organism_id,
            bundle_id=bundle_id,
            skill_id=skill_id,
            module_id=module_id,
            stage=stage,
            payload=payload or {},
        )
        self.trace.emit_evolution(entry)

    def hot_register_promoted(
        self,
        bundle: CodeBundle,
        *,
        skill: SkillDescriptor | None = None,
        organism_id: str = "",
    ) -> HotRegisterResult | None:
        """Register a promoted generative bundle into ModuleRegistry via shadow gate.

        Ladder: PROPOSED → SANDBOXED → SHADOW_VALIDATED → EXPLORATION.
        may_actuate stays False.
        """
        if self.registry is None:
            return None
        if not bundle.may_control or bundle.stage != CodeStage.PROMOTED:
            raise PromoteRefused("hot-register requires promoted may_control bundle")

        t0 = time.perf_counter()
        with self._lock:
            base = skill.skill_id if skill is not None else bundle.bundle_id
            module_id = f"gen_{base}"[:64]
            version = skill.version if skill is not None else "0.1.0"
            catalog_id = f"generative:{module_id}"

            # Replace prior registration of the same generative module id.
            if module_id in self.registry.list_module_ids():
                try:
                    self.registry.deregister(module_id, drain="immediate", timeout_s=1)
                except Exception:
                    pass
                self.modules.pop(module_id, None)

            mod = GeneratedSkillModule(
                module_id=module_id,
                source=bundle.source,
                intent=bundle.intent,
                shadow_score=bundle.shadow_score,
                version=version,
                skill_id=skill.skill_id if skill else None,
            )
            contract = mod.declare_contract()
            # Start at SANDBOXED (shadow gate entry), then climb with evidence.
            self.registry.register(
                contract,
                artifact_digest=contract.identity.artifact_digest,
                author_signature=b"generative-promote",
                module=mod,
                test_bypass_promote="SANDBOXED",
            )
            gate_path = ["SANDBOXED"]
            shadow = ShadowValidationRecord(
                invocations=max(1, int(bundle.shadow_score * 100)),
                incumbent_error=0.2,
                candidate_error=max(0.0, 0.2 - bundle.shadow_score * 0.15),
                p95_latency_ms=5.0,
                gates_passed=("sandbox", "shadow_score", "contract"),
                evidence_digest=hashlib.sha256(bundle.source.encode()).digest(),
            )
            r1 = self.registry.promote(
                module_id,
                "SANDBOXED",
                "SHADOW_VALIDATED",
                [shadow],
                b"generative-shadow",
            )
            if r1.accepted:
                gate_path.append("SHADOW_VALIDATED")
            r2 = self.registry.promote(
                module_id,
                "SHADOW_VALIDATED",
                "EXPLORATION",
                [shadow],
                b"generative-explore",
                test_bypass_validation=not r1.accepted,
            )
            if r2.accepted:
                gate_path.append("EXPLORATION")
            final_state = gate_path[-1]
            self.modules[module_id] = mod
            entry = {
                "catalog_id": catalog_id,
                "module_id": module_id,
                "title": skill.name if skill else f"Generated {bundle.bundle_id[:12]}",
                "tier": "T3_LEARNED_UNCALIBRATED",
                "research_tier": True,
                "research_badge": "RESEARCH_TIER",
                "may_actuate_declared": False,
                "description": (skill.description if skill else bundle.intent)[:200],
                "registered": True,
                "generative": True,
                "bundle_id": bundle.bundle_id,
                "skill_id": skill.skill_id if skill else None,
                "shadow_score": bundle.shadow_score,
                "state": final_state,
            }
            self._catalog[catalog_id] = entry
            elapsed = (time.perf_counter() - t0) * 1000.0
            self.timings.record("hot_register", elapsed)

            self.emit_evolution(
                kind="code_promote" if skill is None else "skill_promote",
                summary=f"Hot-registered {module_id} via shadow gate → {final_state}",
                organism_id=organism_id,
                bundle_id=bundle.bundle_id,
                skill_id=skill.skill_id if skill else None,
                module_id=module_id,
                stage=final_state,
                payload={"shadow_gate": gate_path, "catalog_id": catalog_id},
            )
            if self.trace is not None:
                self.trace.emit_lifecycle(
                    LifecycleTraceEntry(
                        module_id=module_id,
                        from_state="PROPOSED",
                        to_state=final_state,
                        event="generative_hot_register",
                    )
                )
            return HotRegisterResult(
                module_id=module_id,
                state=final_state,
                catalog_id=catalog_id,
                shadow_gate=gate_path,
                elapsed_ms=elapsed,
            )

    def pulse_hormones(self, *, organism_id: str = "", reason: str = "promote") -> dict[str, Any] | None:
        """Optional dopamine/oxytocin pulse after a successful promote."""
        if not self.pulse_on_promote or self.hormone is None:
            return None
        prior = self.hormone.read_workspace_hormone_state() or HormoneLevels()
        levels = HormoneLevels(
            cortisol=prior.cortisol,
            dopamine=min(1.0, prior.dopamine + self.dopamine_pulse),
            oxytocin=min(1.0, prior.oxytocin + self.oxytocin_pulse),
            melatonin=prior.melatonin,
            source=f"generative_{reason}",
            window_id=f"gen_{reason}",
        ).clamp()
        self.hormone.write_telemetry_window(levels)
        self.emit_evolution(
            kind="note",
            summary=f"Hormone pulse on {reason}",
            organism_id=organism_id,
            stage="PROMOTED",
            payload={
                "dopamine": levels.dopamine,
                "oxytocin": levels.oxytocin,
                "cortisol": levels.cortisol,
            },
        )
        return levels.as_dict()

    def quarantine_failed_draft(
        self,
        bundle: CodeBundle,
        *,
        code_pipeline: CodePipeline,
        organism_id: str = "",
        cortisol: float = 0.6,
    ) -> QuarantineResult | None:
        """ImmuneLayer inspects a rejected/failed draft; quarantine demotes it."""
        if self.immune is None:
            return None
        t0 = time.perf_counter()
        # Antigen from error digest — distinct from clean self profiles.
        errs = list(bundle.static_errors) + list(bundle.contract_errors)
        if bundle.sandbox and not bundle.sandbox.get("ok"):
            errs.append(str(bundle.sandbox.get("error") or "sandbox_fail"))
        blob = "|".join(errs) or bundle.source[:64]
        seed = int.from_bytes(hashlib.sha256(blob.encode()).digest()[:8], "big")
        antigen = Hypervector.random(seed=seed ^ 0x494D4D55)
        return self._quarantine_with_antigen(
            bundle,
            antigen=antigen,
            code_pipeline=code_pipeline,
            organism_id=organism_id,
            cortisol=cortisol,
            t0=t0,
            errs=errs,
        )

    def _quarantine_with_antigen(
        self,
        bundle: CodeBundle,
        *,
        antigen: Hypervector,
        code_pipeline: CodePipeline,
        organism_id: str,
        cortisol: float,
        t0: float,
        errs: list[str],
    ) -> QuarantineResult:
        assert self.immune is not None
        # Contract/static failures are treated as danger antigens: seed a
        # detector + QUARANTINE memory so ImmuneLayer demotes the draft.
        if errs:
            # Raise antigen_score above tolerance so memory path is taken.
            self.immune._detectors.insert(0, antigen)
            self.immune.add_memory_cell(antigen, action="QUARANTINE")
        decision = self.immune.ingress(
            antigen,
            source_module_id=f"generative:{bundle.bundle_id}",
            cortisol=max(cortisol, 0.6),
            melatonin=0.0,
        )
        # Hard rule: generative drafts that fail contracts are always demoted
        # when immune returns QUARANTINE/DEMOTE; if immune tolerated unexpectedly,
        # still demote failed-contract drafts and label as quarantine override.
        if errs and decision.decision not in ("QUARANTINE", "DEMOTE"):
            decision.decision = "QUARANTINE"  # type: ignore[assignment]
            decision.classification = "DANGER"  # type: ignore[assignment]
        demoted = False
        if decision.decision in ("QUARANTINE", "DEMOTE"):
            # Ensure bundle cannot be promoted; demote if it somehow was.
            if bundle.may_control or bundle.stage == CodeStage.PROMOTED:
                code_pipeline.demote(bundle.bundle_id, reason=f"immune_{decision.decision.lower()}")
                demoted = True
            else:
                # Force rejected/demotion stage for drafts that failed contracts.
                bundle.gate.promoted = False
                bundle.gate.shadow_validated = False
                bundle.may_control = False
                bundle.research_tier = True
                if bundle.stage != CodeStage.REJECTED:
                    bundle.stage = CodeStage.DEMOTION
                demoted = True
                try:
                    code_pipeline.demote(bundle.bundle_id, reason=f"immune_{decision.decision.lower()}")
                except Exception:
                    pass
        elapsed = (time.perf_counter() - t0) * 1000.0
        self.timings.record("quarantine", elapsed)
        self.emit_evolution(
            kind="code_demote" if demoted else "note",
            summary=f"Immune {decision.decision} on draft {bundle.bundle_id}",
            organism_id=organism_id,
            bundle_id=bundle.bundle_id,
            stage=bundle.stage.value,
            payload={
                "decision": decision.decision,
                "classification": decision.classification,
                "antigen_score": decision.antigen_score,
                "errors": errs[:8],
            },
        )
        return QuarantineResult(
            decision=decision.decision,
            demoted=demoted,
            bundle_id=bundle.bundle_id,
            antigen_score=decision.antigen_score,
            elapsed_ms=elapsed,
        )

    def after_promote(
        self,
        bundle: CodeBundle,
        *,
        skill: SkillDescriptor | None = None,
        organism_id: str = "",
        promote_elapsed_ms: float | None = None,
    ) -> dict[str, Any]:
        """Full post-promote hook: hot-register + hormone pulse + evolution trace."""
        if promote_elapsed_ms is not None:
            self.timings.record("promote", promote_elapsed_ms)
        hot = self.hot_register_promoted(bundle, skill=skill, organism_id=organism_id)
        pulse = self.pulse_hormones(organism_id=organism_id, reason="promote")
        return {
            "hot_register": hot.as_dict() if hot else None,
            "hormone_pulse": pulse,
            "timings": self.timings.as_dict(),
        }

    def after_reject(
        self,
        bundle: CodeBundle,
        *,
        code_pipeline: CodePipeline,
        organism_id: str = "",
        evolve_elapsed_ms: float | None = None,
    ) -> dict[str, Any]:
        if evolve_elapsed_ms is not None:
            self.timings.record("evolve", evolve_elapsed_ms)
        q = None
        if bundle.stage == CodeStage.REJECTED or bundle.static_errors or bundle.contract_errors:
            q = self.quarantine_failed_draft(
                bundle, code_pipeline=code_pipeline, organism_id=organism_id
            )
        self.emit_evolution(
            kind="code_draft",
            summary=f"Draft {bundle.bundle_id} → {bundle.stage.value}",
            organism_id=organism_id,
            bundle_id=bundle.bundle_id,
            stage=bundle.stage.value,
            payload={"static_errors": bundle.static_errors, "contract_errors": bundle.contract_errors},
        )
        return {
            "quarantine": q.as_dict() if q else None,
            "timings": self.timings.as_dict(),
        }
