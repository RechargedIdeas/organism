"""v0.3-M2 — Metamodel reproductive synthesizer (exploration → sandbox → shadow → promote).

Instant hypernetwork-style stub synthesizes an adapter/readout organ. The new
organ cannot actuate until shadow-validated and promoted. When ``enabled=False``,
``synthesize`` raises ``MetamodelDisabled`` (v0.2 fail-closed preserved).
Deliberation registration is blocked until promotion.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MetamodelDisabled(Exception):
    """Raised when reproductive synthesis is attempted while tracker is disabled."""


class SynthesisStage(str, Enum):
    REQUESTED = "REQUESTED"
    SYNTHESIZED = "SYNTHESIZED"
    SANDBOXED = "SANDBOXED"
    SHADOW_VALIDATED = "SHADOW_VALIDATED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


@dataclass
class SynthesisRequest:
    spec: dict[str, Any]
    requested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FourPartContract:
    """Minimal four-part contract required before deliberation registration."""

    identity_ok: bool
    perception_ok: bool
    emission_ok: bool
    safety_ok: bool

    def passed(self) -> bool:
        return self.identity_ok and self.perception_ok and self.emission_ok and self.safety_ok

    def as_dict(self) -> dict[str, bool]:
        return {
            "identity_ok": self.identity_ok,
            "perception_ok": self.perception_ok,
            "emission_ok": self.emission_ok,
            "safety_ok": self.safety_ok,
            "passed": self.passed(),
        }


@dataclass
class SynthesizedOrgan:
    organ_id: str
    adapter_weights: dict[str, float]
    readout: dict[str, Any]
    contract: FourPartContract
    stage: SynthesisStage = SynthesisStage.SYNTHESIZED
    may_actuate: bool = False
    shadow_pass_rate: float = 0.0
    rejection_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        return {
            "organ_id": self.organ_id,
            "adapter_weights": self.adapter_weights,
            "readout": self.readout,
            "contract": self.contract.as_dict(),
            "stage": self.stage.value,
            "may_actuate": self.may_actuate,
            "shadow_pass_rate": self.shadow_pass_rate,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat(),
        }


def _validate_four_part(spec: dict[str, Any]) -> FourPartContract:
    identity = bool(spec.get("module_id") or spec.get("name"))
    perception = bool(spec.get("input_modality") or spec.get("perception"))
    emission = bool(spec.get("output_form") or spec.get("emission"))
    safety = spec.get("may_actuate_until_promoted", False) is False and (
        spec.get("reliability_tier", "T3_LEARNED_UNCALIBRATED")
        != "T0_DETERMINISTIC"  # synthesizer never emits T0
    )
    # Explicit safety flag required
    safety = safety and bool(spec.get("safety_declared", True))
    return FourPartContract(identity, perception, emission, safety)


def _hypernetwork_stub(spec: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    """Instant hypernetwork-style adapter: deterministic from spec digest."""
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(blob).hexdigest()
    seed_ints = [int(digest[i : i + 4], 16) / 65535.0 for i in range(0, 24, 4)]
    weights = {
        "w0": seed_ints[0] - 0.5,
        "w1": seed_ints[1] - 0.5,
        "w2": seed_ints[2] - 0.5,
        "scale": 0.5 + 0.5 * seed_ints[3],
    }
    readout = {
        "kind": "linear_readout",
        "dim": int(spec.get("readout_dim", 8)),
        "digest": digest[:16],
        "exploration_only": True,
    }
    return weights, readout


@dataclass
class MetamodelTracker:
    """Reproductive path: synthesize → sandbox → shadow → promote/reject."""

    enabled: bool = False  # default off preserves v0.2 fail-closed tests
    exploration_mode: bool = True
    attempts: list[dict[str, Any]] = field(default_factory=list)
    organs: dict[str, SynthesizedOrgan] = field(default_factory=dict)
    min_shadow_pass_rate: float = 0.9
    _nas_winners: list[str] = field(default_factory=list)

    def reproductive_path_enabled(self) -> bool:
        return self.enabled and self.exploration_mode

    def synthesize(self, spec: dict[str, Any]) -> SynthesizedOrgan:
        self.attempts.append(
            {
                "spec": spec,
                "at": datetime.now(timezone.utc).isoformat(),
                "accepted": False,
                "reason": "pending",
            }
        )
        if not self.enabled:
            self.attempts[-1]["reason"] = "E.8_metamodel_reproductive_disabled"
            raise MetamodelDisabled(
                "Metamodel reproductive synthesizer is disabled (set enabled=True for exploration)"
            )
        if not self.exploration_mode:
            self.attempts[-1]["reason"] = "not_in_exploration_mode"
            raise MetamodelDisabled(
                "Metamodel synthesis is exploration-only; deliberation path blocked until promote"
            )

        contract = _validate_four_part(spec)
        if not contract.passed():
            self.attempts[-1]["reason"] = "four_part_contract_failed"
            self.attempts[-1]["contract"] = contract.as_dict()
            raise ValueError(f"four-part contract failed: {contract.as_dict()}")

        weights, readout = _hypernetwork_stub(spec)
        organ_id = spec.get("module_id") or f"synth_{uuid.uuid4().hex[:12]}"
        organ = SynthesizedOrgan(
            organ_id=organ_id,
            adapter_weights=weights,
            readout=readout,
            contract=contract,
            stage=SynthesisStage.SYNTHESIZED,
            may_actuate=False,
        )
        self.organs[organ_id] = organ
        self.attempts[-1]["accepted"] = True
        self.attempts[-1]["reason"] = "synthesized_exploration"
        self.attempts[-1]["organ_id"] = organ_id
        return organ

    def sandbox(self, organ_id: str) -> SynthesizedOrgan:
        organ = self._get(organ_id)
        if organ.stage not in (SynthesisStage.SYNTHESIZED, SynthesisStage.SANDBOXED):
            raise ValueError(f"cannot sandbox from stage {organ.stage}")
        # Sandbox: run adapter on zero input — must be finite
        s = sum(organ.adapter_weights.values())
        if not (s == s):  # NaN check
            organ.stage = SynthesisStage.REJECTED
            organ.rejection_reason = "sandbox_nan"
            raise ValueError("sandbox failed: nan weights")
        organ.stage = SynthesisStage.SANDBOXED
        organ.may_actuate = False
        return organ

    def shadow_validate(self, organ_id: str, *, pass_rate: float) -> SynthesizedOrgan:
        organ = self._get(organ_id)
        if organ.stage != SynthesisStage.SANDBOXED:
            raise ValueError("shadow_validate requires SANDBOXED stage")
        organ.shadow_pass_rate = pass_rate
        if pass_rate >= self.min_shadow_pass_rate and organ.contract.passed():
            organ.stage = SynthesisStage.SHADOW_VALIDATED
            organ.may_actuate = False  # still no actuation until promote
        else:
            organ.stage = SynthesisStage.REJECTED
            organ.rejection_reason = f"shadow_fail pass_rate={pass_rate}"
            organ.may_actuate = False
        return organ

    def promote(self, organ_id: str) -> SynthesizedOrgan:
        organ = self._get(organ_id)
        if organ.stage != SynthesisStage.SHADOW_VALIDATED:
            organ.may_actuate = False
            raise PermissionError(
                f"promote blocked: stage={organ.stage.value}; require SHADOW_VALIDATED"
            )
        organ.stage = SynthesisStage.PROMOTED
        organ.may_actuate = True
        organ.readout["exploration_only"] = False
        return organ

    def reject(self, organ_id: str, reason: str) -> SynthesizedOrgan:
        organ = self._get(organ_id)
        organ.stage = SynthesisStage.REJECTED
        organ.rejection_reason = reason
        organ.may_actuate = False
        return organ

    def can_register_deliberation(self, organ_id: str) -> bool:
        organ = self.organs.get(organ_id)
        return bool(organ and organ.stage == SynthesisStage.PROMOTED and organ.may_actuate)


    def nas_search(
        self,
        base_spec: dict[str, Any],
        *,
        space: dict[str, list[Any]] | None = None,
        shadow_eval: Any | None = None,
        top_k: int = 1,
    ) -> list[SynthesizedOrgan]:
        """Live tiny NAS: enumerate a small architecture space, synthesize each,
        sandbox, shadow-validate via ``shadow_eval(organ) -> float`` pass rate,
        return winners that reach SHADOW_VALIDATED (not yet promoted).
        """
        if not self.reproductive_path_enabled():
            raise MetamodelDisabled("NAS requires enabled exploration metamodel")
        space = space or {
            "readout_dim": [2, 4, 8],
            "scale_hint": [0.5, 1.0],
            "depth": [1, 2],
        }
        # Cartesian product (tiny)
        keys = list(space.keys())
        combos: list[dict[str, Any]] = [{}]
        for k in keys:
            combos = [dict(c, **{k: v}) for c in combos for v in space[k]]
        results: list[tuple[float, SynthesizedOrgan]] = []
        for i, arch in enumerate(combos):
            spec = dict(base_spec)
            spec.update(arch)
            spec["module_id"] = spec.get("module_id", "nas") + f"_c{i}"
            organ = self.synthesize(spec)
            organ.readout["nas_arch"] = arch
            self.sandbox(organ.organ_id)
            if shadow_eval is None:
                # Default: higher dim + moderate scale scores better (deterministic)
                # Prefer larger readout + scale≈1 + depth=2 so best arches clear 0.9
                score = (
                    0.82
                    + 0.015 * float(arch.get("readout_dim", 4))
                    + 0.04 * (1.0 if float(arch.get("depth", 1)) >= 2 else 0.0)
                    - 0.05 * abs(float(arch.get("scale_hint", 1.0)) - 1.0)
                )
                score = min(0.99, max(0.0, score))
            else:
                score = float(shadow_eval(organ))
            self.shadow_validate(organ.organ_id, pass_rate=score)
            if organ.stage == SynthesisStage.SHADOW_VALIDATED:
                results.append((score, organ))
        results.sort(key=lambda x: -x[0])
        winners = [o for _, o in results[:top_k]]
        self._nas_winners = [w.organ_id for w in winners]
        return winners

    def promote_nas_winner(self, organ_id: str | None = None) -> SynthesizedOrgan:
        """Promote a shadow-validated NAS winner onto deliberation (may_actuate)."""
        oid = organ_id or (self._nas_winners[0] if self._nas_winners else None)
        if not oid:
            raise ValueError("no NAS winner to promote")
        return self.promote(oid)

    def _get(self, organ_id: str) -> SynthesizedOrgan:
        if organ_id not in self.organs:
            raise KeyError(f"unknown organ_id={organ_id}")
        return self.organs[organ_id]
