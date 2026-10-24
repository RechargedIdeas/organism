"""Artifact J — Morphogenesis / DevelopmentalGenome stubs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

StageStatus = Literal["PENDING", "PASSED", "FAILED"]


@dataclass
class DevelopmentalStage:
    index: int
    name: str
    status: StageStatus = "PENDING"
    locus: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class DevelopmentalGenome:
    genome_id: str
    stages: list[DevelopmentalStage]
    developmental: bool = True
    mutation_locus: str | None = None

    @property
    def all_passed(self) -> bool:
        return all(s.status == "PASSED" for s in self.stages)


class MorphogenesisTracker:
    def __init__(self) -> None:
        self._genomes: dict[str, DevelopmentalGenome] = {}
        self._module_stage: dict[str, int] = {}

    def register_genome(self, module_id: str, genome: DevelopmentalGenome) -> None:
        self._genomes[module_id] = genome
        self._module_stage[module_id] = 0

    def get(self, module_id: str) -> DevelopmentalGenome | None:
        return self._genomes.get(module_id)

    def run_stage(self, module_id: str, *, pass_stage: bool = True) -> DevelopmentalStage:
        g = self._genomes[module_id]
        idx = self._module_stage[module_id]
        if idx >= len(g.stages):
            raise RuntimeError("no pending stages")
        stage = g.stages[idx]
        if pass_stage:
            stage.status = "PASSED"
            self._module_stage[module_id] = idx + 1
        else:
            stage.status = "FAILED"
            g.mutation_locus = stage.locus or stage.name
        return stage

    def may_enter_deliberation(self, module_id: str) -> bool:
        g = self._genomes.get(module_id)
        return True if g is None else g.all_passed

    def exploration_restrictions_apply(self, module_id: str) -> bool:
        g = self._genomes.get(module_id)
        return g is not None and g.developmental and not g.all_passed


    def offer_control_actuation(self, module_id: str) -> dict[str, object]:
        """O2: DEVELOPMENT modules cannot take control_actuation (EXPLORATION restrictions)."""
        if self.exploration_restrictions_apply(module_id):
            return {"accepted": False, "reason": "DEVELOPMENT_EXPLORATION_RESTRICTION", "held": True}
        return {"accepted": True, "reason": "ok", "held": False}

    def leave_development(self, module_id: str) -> bool:
        """O3: all stages valid → leave DEVELOPMENT (same gates as EXPLORATION promotion)."""
        return self.may_enter_deliberation(module_id)
