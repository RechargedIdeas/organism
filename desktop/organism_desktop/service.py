"""Headless UI service layer — all Desktop panels talk to Organism through this.

Safety: bio/wet-lab actuation is hard-refused here. Panels must not bypass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from organism_sdk import __version__ as sdk_version
from organism_sdk.autonomic import AutonomicController
from organism_sdk.degradation import DegradationMachine, HealthSignals
from organism_sdk.deploy.config import DeployConfig, default_cpu_only_config, load_deploy_config
from organism_sdk.deploy.stack import MinimalStack, build_minimal_stack
from organism_sdk.device import accelerator_selection_summary, select_compute_backend
from organism_sdk.hormone import HormoneBus, HormoneLevels
from organism_sdk.hypervector import Hypervector
from organism_sdk.immune import ImmuneLayer
from organism_sdk.metamodel import MetamodelTracker
from organism_sdk.registry import CapabilityFilter
from organism_sdk.router import DispatchPlan, RouterTask
from organism_sdk.trace import V02TraceSink
from organism_sdk.workspace import BindingRecord


class ActuationRefused(PermissionError):
    """Raised when Desktop refuses bio/wet-lab control actuation."""


@dataclass
class PipelineResult:
    task: dict[str, Any]
    plan: dict[str, Any]
    ranking_trace: list[str]
    disposition: str


@dataclass
class DesktopService:
    """Façade over MinimalStack + physiology + bio safety."""

    stack: MinimalStack
    degrade: DegradationMachine = field(default_factory=DegradationMachine)
    hormone: HormoneBus | None = None
    immune: ImmuneLayer | None = None
    autonomic: AutonomicController | None = None
    metamodel: MetamodelTracker = field(default_factory=lambda: MetamodelTracker(enabled=True, exploration_mode=True))
    bio_modules: dict[str, Any] = field(default_factory=dict)
    _repo_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    _last_plan: DispatchPlan | None = None

    @classmethod
    def create(cls, cfg: DeployConfig | None = None) -> "DesktopService":
        stack = build_minimal_stack(cfg or default_cpu_only_config())
        stack.trace.attach_v02_sink(V02TraceSink())
        svc = cls(stack=stack)
        # Hormone bus needs a workspace; attach soft-fail if ctor signature differs
        try:
            svc.hormone = HormoneBus(workspace=stack.workspace, trace=stack.trace)
        except TypeError:
            try:
                svc.hormone = HormoneBus(stack.workspace)
            except Exception:
                svc.hormone = None
        try:
            svc.immune = ImmuneLayer(workspace=stack.workspace, trace=stack.trace)
        except TypeError:
            try:
                svc.immune = ImmuneLayer(stack.workspace)
            except Exception:
                svc.immune = None
        try:
            svc.autonomic = AutonomicController()
        except Exception:
            svc.autonomic = None
        if svc.hormone is not None:
            try:
                stack.router.attach_hormone_bus(svc.hormone)
            except Exception:
                pass
        svc._register_bio_modules()
        return svc

    def _register_bio_modules(self) -> None:
        """Register exploration-only bio modules when importable."""
        try:
            from bio_digital.slime_mold import SlimeMoldModule
            from bio_digital.mycelium import MyceliumModule

            for mod in (SlimeMoldModule(), MyceliumModule()):
                c = mod.declare_contract()
                mid = c.identity.module_id
                # Contract is frozen; slime/mycelium already declare may_actuate=False
                self.stack.registry.register(
                    c,
                    artifact_digest=c.identity.artifact_digest,
                    author_signature=b"desktop",
                    module=mod,
                    test_bypass_promote="EXPLORATION",
                )
                self.bio_modules[mid] = mod
        except Exception as exc:
            # Bio package optional for bare desktop; keep desktop usable
            self.bio_modules["_register_error"] = str(exc)  # type: ignore[assignment]
            # Ensure dict remains str->module only for real modules
            self.bio_modules = {k: v for k, v in self.bio_modules.items() if not str(k).startswith("_")}
            self._bio_register_error = str(exc)

    # ----- Home / Status -----

    def home_status(self) -> dict[str, Any]:
        st = self.stack.status()
        device = select_compute_backend().as_dict()
        return {
            "organism_version": sdk_version,
            "desktop_version": "1.5.0",
            "profile": st.get("profile"),
            "cpu_everywhere": True,
            "device": device,
            "accelerator_summary": accelerator_selection_summary(),
            "degradation_level": str(getattr(self.degrade, "level", "L0")),
            "router_level": st.get("router_level"),
            "module_count": st.get("module_count"),
            "modules": st.get("modules"),
            "workspace_bindings": st.get("workspace_bindings"),
            "health_host": st.get("health_host"),
            "health_port": st.get("health_port"),
            "serve_hint": f"organism serve -c deploy/config/cpu_only.yaml",
            "ok": True,
        }

    # ----- Registry -----

    def list_modules(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for h in self.stack.registry.query(CapabilityFilter()):
            contract = None
            may = False
            try:
                # ModuleHandle may carry contract via registry internals
                mod = self.stack.modules.get(h.module_id) or self.bio_modules.get(h.module_id)
                if mod is not None and hasattr(mod, "declare_contract"):
                    contract = mod.declare_contract()
                    may = bool(getattr(getattr(contract, "safety", None), "may_actuate", False))
            except Exception:
                may = False
            out.append(
                {
                    "module_id": h.module_id,
                    "version": h.version,
                    "role": str(h.role),
                    "tier": str(getattr(h, "tier", "")),
                    "state": h.state,
                    "may_actuate": may,
                    "bio_exploration": h.module_id in self.bio_modules,
                }
            )
        return out

    # ----- Workspace -----

    def list_bindings(self, limit: int = 50) -> list[dict[str, Any]]:
        recs = self.stack.workspace.read_by_tag(["*"]) if hasattr(self.stack.workspace, "read_by_tag") else []
        # Fallback: use internal if tagged read empty
        if not recs and hasattr(self.stack.workspace, "_bindings"):
            recs = list(getattr(self.stack.workspace, "_bindings").values())
        rows = []
        for r in list(recs)[:limit]:
            rows.append(
                {
                    "binding_id": str(getattr(r, "binding_id", "")),
                    "tags": list(getattr(r, "tags", ()) or ()),
                    "role_prefix": getattr(r, "role", Hypervector.zeros()).to_bytes_be()[:8].hex()
                    if hasattr(getattr(r, "role", None), "to_bytes_be")
                    else "",
                    "filler_prefix": getattr(r, "filler", Hypervector.zeros()).to_bytes_be()[:8].hex()
                    if hasattr(getattr(r, "filler", None), "to_bytes_be")
                    else "",
                }
            )
        return rows

    def write_demo_binding(self, tag: str = "desktop.demo") -> dict[str, Any]:
        role = Hypervector.random()
        filler = Hypervector.random()
        try:
            rec = self.stack.workspace.bind_exact(role, filler, tags=(tag,))
        except TypeError:
            hv = role.bind(filler) if hasattr(role, "bind") else role
            rec = BindingRecord(
                binding_id=uuid4(),
                hypervector=hv,
                role=role,
                filler=filler,
                tags=(tag,),
                module_id="organism.desktop",
            )
            self.stack.workspace.write(rec)
        return {"binding_id": str(rec.binding_id), "tags": list(rec.tags)}

    def hypervector_preview(self, seed: int = 0) -> dict[str, Any]:
        hv = Hypervector.random(seed=seed)
        # First 16 packed words as a simple viz sample
        sample = [int(w) for w in hv.words[:16]]
        digest = hv.to_bytes_be()[:16].hex()
        return {"dim": Hypervector.dim(), "sample_words": sample, "digest_prefix": digest}

    # ----- Pipelines -----

    def run_pipeline(
        self,
        *,
        form: str = "pattern_recognition",
        safety_tier: str = "medium",
        deadline_ms: float = 1000.0,
        task_id: str | None = None,
        requires_interpretability: bool = False,
        requires_determinism: bool = False,
    ) -> PipelineResult:
        tid = task_id or f"desktop-{uuid4().hex[:8]}"
        task = RouterTask(
            task_id=tid,
            form=form,
            safety_tier=safety_tier,
            deadline_ms=deadline_ms,
            requires_interpretability=requires_interpretability,
            requires_determinism=requires_determinism,
        )
        plan = self.stack.router.decide(task)
        self._last_plan = plan
        primary = None
        if plan.primary is not None:
            primary = {
                "module_id": plan.primary.module_id,
                "role": str(plan.primary.role),
                "tier": str(plan.primary.tier),
                "state": plan.primary.state,
            }
        excluded = [
            {"module_id": e.module_id, "reason": e.reason_code}
            for e in (plan.excluded or [])
        ]
        plan_dict = {
            "plan_id": plan.plan_id,
            "task_id": plan.task_id,
            "level": plan.level,
            "plan_type": plan.plan_type,
            "primary": primary,
            "fallbacks": [f.module_id for f in (plan.fallbacks or [])],
            "constraints_applied": list(plan.constraints_applied or []),
            "excluded": excluded,
            "ranking_trace": list(plan.ranking_trace or []),
            "disposition": plan.disposition,
            "cross_check_required": plan.cross_check_required,
            "hold_reason": plan.hold_reason,
            "candidate_roles": list(plan.candidate_roles or []),
        }
        return PipelineResult(
            task={
                "task_id": tid,
                "form": form,
                "safety_tier": safety_tier,
                "deadline_ms": deadline_ms,
            },
            plan=plan_dict,
            ranking_trace=list(plan.ranking_trace or []),
            disposition=plan.disposition,
        )

    # ----- Physiology -----

    def physiology_snapshot(self) -> dict[str, Any]:
        level = getattr(self.degrade, "level", "L0")
        hormones: dict[str, Any] = {}
        if self.hormone is not None:
            try:
                reading = self.hormone.read_mirror(consumer="desktop")
                levels = getattr(reading, "levels", None)
                if levels is not None and hasattr(levels, "as_dict"):
                    hormones = levels.as_dict()
                elif isinstance(levels, dict):
                    hormones = levels
            except Exception as e:
                hormones = {"error": str(e)}
        immune = {"available": self.immune is not None}
        if self.immune is not None:
            dlc = getattr(self.immune, "direct_lifecycle_calls", 0)
            immune["direct_lifecycle_calls"] = dlc() if callable(dlc) else dlc
        auto = {"available": self.autonomic is not None}
        if self.autonomic is not None:
            try:
                params = self.autonomic.force_mode  # type: ignore[attr-defined]
                auto["has_force_mode"] = True
            except Exception:
                auto["has_force_mode"] = False
        return {
            "degradation_level": str(level or self.stack.router.current_level()),
            "router_level": self.stack.router.current_level(),
            "hormones": hormones,
            "immune": immune,
            "autonomic": auto,
        }

    def set_degradation_level(self, level: str) -> str:
        """Best-effort set router level (physiology display)."""
        self.stack.router.set_level(level)  # type: ignore[arg-type]
        return self.stack.router.current_level()

    # ----- Metamodel -----

    def metamodel_synthesize(self, name: str = "desktop_organ") -> dict[str, Any]:
        organ = self.metamodel.synthesize(
            {
                "module_id": name,
                "name": name,
                "input_modality": "DENSE_VECTOR",
                "output_form": "FEATURE_VECTOR",
                "safety_declared": True,
                "may_actuate_until_promoted": False,
                "reliability_tier": "T3_LEARNED_UNCALIBRATED",
                "readout_dim": 4,
                "exploration": True,
            }
        )
        return organ.as_dict() if hasattr(organ, "as_dict") else {"organ_id": getattr(organ, "organ_id", str(organ))}

    def metamodel_advance(self, organ_id: str, stage: str, *, pass_rate: float = 0.95) -> dict[str, Any]:
        if stage == "sandbox":
            organ = self.metamodel.sandbox(organ_id)
        elif stage == "shadow":
            organ = self.metamodel.shadow_validate(organ_id, pass_rate=pass_rate)
        elif stage == "promote":
            organ = self.metamodel.promote(organ_id)
        elif stage == "reject":
            organ = self.metamodel.reject(organ_id, "desktop_reject")
        else:
            raise ValueError(f"unknown stage {stage}")
        return organ.as_dict() if hasattr(organ, "as_dict") else {"organ_id": organ_id, "stage": stage}

    # ----- Bio-Digital (HARD refuse actuation) -----

    def bio_status(self) -> dict[str, Any]:
        from bio_digital.wetlab.safety import SafetyPolicy

        policy = SafetyPolicy.deny_all()
        mods = []
        for mid, mod in self.bio_modules.items():
            c = mod.declare_contract()
            may = bool(getattr(getattr(c, "safety", None), "may_actuate", False))
            mods.append({"module_id": mid, "may_actuate": may, "exploration_only": True})
        twin = {}
        try:
            from bio_digital.hal import BioDigitalHAL

            hal = BioDigitalHAL()
            twin = {"telemetry": hal.read_telemetry().__dict__ if hasattr(hal.read_telemetry(), "__dict__") else str(hal.read_telemetry())}
            if hasattr(hal, "sample_twin"):
                twin["sample"] = hal.sample_twin()
        except Exception as e:
            twin = {"error": str(e)}
        return {
            "modules": mods,
            "safety_policy": policy.as_dict(),
            "control_actuation_default": False,
            "twin": twin,
            "warning": "Bio-Digital panels are exploration-only. Actuation is refused.",
        }

    def request_bio_actuation(
        self,
        *,
        module_id: str | None = None,
        electrode_id: str = "e0",
        voltage: float = 0.1,
    ) -> dict[str, Any]:
        """HARD REFUSE — Desktop never enables control_actuation for bio."""
        raise ActuationRefused(
            f"Desktop hard-refuses bio actuation "
            f"(module={module_id!r}, electrode={electrode_id!r}, voltage={voltage}). "
            f"may_actuate=False; SafetyPolicy.deny_all; exploration-only."
        )

    def try_bio_actuation(self, **kwargs: Any) -> dict[str, Any]:
        """UI-safe wrapper that returns a refused payload instead of raising."""
        try:
            self.request_bio_actuation(**kwargs)
            return {"refused": False}  # unreachable
        except ActuationRefused as e:
            return {"refused": True, "reason": str(e), "may_actuate": False}

    # ----- Traces -----

    def list_traces(self, limit: int = 100) -> list[dict[str, Any]]:
        raw = self.stack.trace.entries
        if callable(raw):
            raw = raw()
        entries = []
        for e in list(raw)[-limit:]:
            entries.append(
                {
                    "type": type(e).__name__,
                    "repr": repr(e)[:500],
                }
            )
        return entries

    # ----- Ops -----

    def validate_deploy_config(self, path: str | Path | None = None) -> dict[str, Any]:
        p = Path(path) if path else self._repo_root / "deploy" / "config" / "cpu_only.yaml"
        try:
            cfg = load_deploy_config(p)
            return {"ok": True, "path": str(p), "profile": cfg.profile, "version": cfg.version}
        except Exception as e:
            return {"ok": False, "path": str(p), "error": str(e)}

    def ops_info(self) -> dict[str, Any]:
        from bio_digital.wetlab.safety import SafetyPolicy

        return {
            "cpu_everywhere": True,
            "validate": self.validate_deploy_config(),
            "soak_runbook": str(self._repo_root / "docs" / "ops" / "SOAK_RUNBOOK.md"),
            "soak_script": str(self._repo_root / "scripts" / "soak_target.sh"),
            "wetlab_policy_doc": str(self._repo_root / "docs" / "ops" / "WETLAB_SAFETY_POLICY.md"),
            "wetlab_policy": SafetyPolicy.deny_all().as_dict(),
            "cpu_everywhere_doc": str(self._repo_root / "docs" / "CPU_EVERYWHERE.md"),
            "api_freeze": str(self._repo_root / "docs" / "API_FREEZE_v1.0.md"),
        }

    def docs_links(self) -> list[dict[str, str]]:
        root = self._repo_root / "docs"
        return [
            {"title": "CPU Everywhere", "path": str(root / "CPU_EVERYWHERE.md")},
            {"title": "Soak Runbook", "path": str(root / "ops" / "SOAK_RUNBOOK.md")},
            {"title": "Wet-lab Safety Policy", "path": str(root / "ops" / "WETLAB_SAFETY_POLICY.md")},
            {"title": "API Freeze v1.0", "path": str(root / "API_FREEZE_v1.0.md")},
            {"title": "Desktop Design", "path": str(root / "v1.5" / "DESKTOP.md")},
            {"title": "Deploy README", "path": str(self._repo_root / "deploy" / "README.md")},
        ]
