"""neurosymbolic — T0 VERIFIER: three-level causal check certificates."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from organism_sdk.contract import (
    Determinism,
    JustificationKind,
    MaxSafetyTier,
    Modality,
    ModuleRole,
    OutputForm,
    ReliabilityTier,
    UncertaintyKind,
)
from organism_sdk.health import HealthReport
from organism_sdk.inputs import PerceptionInput
from organism_sdk.justification import Emission, JustificationToken
from organism_sdk.module import OrganismModule
from _common.contract_factory import make_contract

MODULE_ID = "neurosymbolic"
MODULE_VERSION = "1.0.0"
FMT = "typed-json:causal-cert/v1"


@dataclass
class CausalGraph:
    version: str = "1.0.0"
    edges: dict[str, list[tuple[str, float]]] = field(default_factory=dict)

    def add_edge(self, parent: str, child: str, strength: float = 1.0) -> None:
        self.edges.setdefault(parent, []).append((child, strength))

    def intervene(self, node: str, value: float, state: dict[str, float]) -> dict[str, float]:
        out = dict(state)
        out[node] = value
        for child, strength in self.edges.get(node, []):
            out[child] = out.get(child, 0.0) * 0.5 + strength * value
        return out


@dataclass
class ThreeLevelResult:
    factual_score: float
    interventional_score: float
    counterfactual_score: float
    recognition: float
    explanation: list[str]
    passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "factual_score": self.factual_score,
            "interventional_score": self.interventional_score,
            "counterfactual_score": self.counterfactual_score,
            "recognition": self.recognition,
            "explanation": self.explanation,
            "passed": self.passed,
        }


class NeurosymbolicVerifier(OrganismModule):
    def __init__(self, *, min_recognition: float = 0.7) -> None:
        self.min_recognition = min_recognition
        self.graph = CausalGraph()
        self.graph.add_edge("thermal", "power_alloc", 0.8)
        self.graph.add_edge("calibration", "prediction", 0.9)
        self.graph.add_edge("viability", "actuation", 1.0)
        self._status = "HEALTHY"
        self._score = 1.0

    def declare_contract(self):
        return make_contract(
            module_id=MODULE_ID,
            version=MODULE_VERSION,
            role=ModuleRole.VERIFIER,
            tier=ReliabilityTier.T0_DETERMINISTIC,
            modalities=(Modality.SYMBOL_GRAPH, Modality.TABULAR, Modality.DENSE_VECTOR),
            required_modalities=(Modality.TABULAR,),
            output_form=OutputForm.JUSTIFICATION_TOKEN,
            uncertainty=UncertaintyKind.SYMBOLIC_PROOF,
            determinism=Determinism.DETERMINISTIC,
            justification_kind=JustificationKind.CAUSAL_CERT,
            justification_format=FMT,
            required_fields=("causal.factual", "causal.interventional", "causal.counterfactual"),
            may_actuate=False,
            max_safety=MaxSafetyTier.CRITICAL,
            requires_justification_for=("control_actuation", "verify"),
            write_tags=("causal", "governance"),
            failure_name="symbol_grounding_failure",
        )

    def health(self) -> HealthReport:
        return HealthReport(module_id=MODULE_ID, status=self._status, score=self._score)

    def three_level_check(
        self,
        *,
        state: dict[str, float],
        action_node: str,
        action_value: float,
        observed: dict[str, float] | None = None,
    ) -> ThreeLevelResult:
        observed = observed or state
        factual_err = 0.0
        n = 0
        for k, v in observed.items():
            factual_err += abs(v - state.get(k, v))
            n += 1
        factual = max(0.0, 1.0 - factual_err / max(1, n))
        intervened = self.graph.intervene(action_node, action_value, state)
        interv = max(0.0, min(1.0, intervened.get("viability", state.get("viability", 0.5))))
        if action_node == "actuation" and state.get("thermal", 0) > 0.9:
            interv *= 0.2
        cf = max(0.0, min(1.0, state.get("viability", 0.5)))
        recognition = (factual + interv + (1.0 if interv >= cf * 0.9 else 0.5)) / 3.0
        explanation = [
            f"factual={factual:.3f}",
            f"interventional({action_node}={action_value})={interv:.3f}",
            f"counterfactual_no_action={cf:.3f}",
            f"graph_version={self.graph.version}",
        ]
        return ThreeLevelResult(
            factual_score=factual,
            interventional_score=interv,
            counterfactual_score=cf,
            recognition=recognition,
            explanation=explanation,
            passed=recognition >= self.min_recognition,
        )

    def handle(self, input: PerceptionInput) -> Emission:
        state = {
            "thermal": 0.2,
            "calibration": 0.9,
            "viability": 0.8,
            "power_alloc": 0.5,
            "prediction": 0.7,
            "actuation": 0.0,
        }
        meta = dict(input.task_descriptor.metadata or {})
        # Optional overlay from TABULAR bytes as JSON
        tab = input.modalities.get(Modality.TABULAR)
        if tab is not None:
            try:
                overlay = json.loads(tab.data.decode())
                if isinstance(overlay, dict):
                    for k, v in overlay.items():
                        if isinstance(v, (int, float)):
                            state[k] = float(v)
                        else:
                            meta[k] = str(v)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        action_node = str(meta.get("action_node", "actuation"))
        action_value = float(meta.get("action_value", "1.0"))
        result = self.three_level_check(
            state=state, action_node=action_node, action_value=action_value
        )
        body = json.dumps(result.as_dict(), sort_keys=True).encode()
        return Emission(
            action_class="verify",
            payload=body,
            metadata={"module_id": MODULE_ID, "graph_version": self.graph.version},
        )

    def justify(self, emission: Emission) -> JustificationToken | None:
        try:
            p = json.loads(emission.payload.decode())
        except json.JSONDecodeError:
            p = {}
        body_obj = {
            "format": FMT,
            "causal.factual": p.get("factual_score"),
            "causal.interventional": p.get("interventional_score"),
            "causal.counterfactual": p.get("counterfactual_score"),
            "causal.recognition": p.get("recognition"),
            "causal.passed": p.get("passed"),
            "emission_digest": hashlib.sha256(emission.payload).hexdigest(),
        }
        body = json.dumps(body_obj, sort_keys=True, separators=(",", ":")).encode()
        return JustificationToken(
            kind=JustificationKind.CAUSAL_CERT,
            format=FMT,
            body=body,
            signature=hashlib.sha256(b"causal-key:" + body).digest(),
        )
