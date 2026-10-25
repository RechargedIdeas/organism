"""Headless UI service layer — all Desktop panels talk to Organism through this.

Safety: bio/wet-lab actuation is hard-refused here. Panels must not bypass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from organism_sdk import __version__ as sdk_version
from organism_sdk.autonomic import AutonomicController
from organism_sdk.degradation import (
    T_DOWN_FAST,
    T_UP_FAST,
    DegradationMachine,
    HealthSignals,
)
from organism_sdk.deploy.config import DeployConfig, default_cpu_only_config, load_deploy_config
from organism_sdk.deploy.stack import MinimalStack, build_minimal_stack
from organism_sdk.device import accelerator_selection_summary, select_compute_backend
from organism_sdk.hormone import HormoneBus
from organism_sdk.hypervector import Hypervector
from organism_sdk.immune import ImmuneLayer
from organism_sdk.metamodel import MetamodelTracker
from organism_sdk.registry import CapabilityFilter
from organism_sdk.router import DispatchPlan, RouterTask
from organism_sdk.trace import (
    DegradationTraceEntry,
    HormoneTraceEntry,
    RoutingTraceEntry,
    TraceEmitter,
    V02TraceSink,
)
from organism_sdk.workspace import BindingRecord

DESKTOP_VERSION = "1.5.1"

CoreKind = Literal["deterministic", "learned"]


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
    metamodel: MetamodelTracker = field(
        default_factory=lambda: MetamodelTracker(enabled=True, exploration_mode=True)
    )
    bio_modules: dict[str, Any] = field(default_factory=dict)
    _repo_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    _last_plan: DispatchPlan | None = None
    _bio_register_error: str | None = None
    _hal: Any = None

    @classmethod
    def create(cls, cfg: DeployConfig | None = None) -> "DesktopService":
        stack = build_minimal_stack(cfg or default_cpu_only_config())
        stack.trace.attach_v02_sink(V02TraceSink())
        # Share TraceEmitter so physiology transitions appear in Traces panel.
        degrade = DegradationMachine(
            trace=stack.trace,
            t_down=dict(T_DOWN_FAST),
            t_up=dict(T_UP_FAST),
        )
        svc = cls(stack=stack, degrade=degrade)
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
                # Soft-fail: hormone attachment is optional for bare desktop.
                svc._hormone_attach_error = "attach_hormone_bus unavailable"  # type: ignore[attr-defined]
        svc._register_bio_modules()
        svc._init_hal()
        return svc

    def _init_hal(self) -> None:
        try:
            from bio_digital.hal import BioDigitalHAL
            from bio_digital.limits import PHYSARUM_LIMITS

            self._hal = BioDigitalHAL(PHYSARUM_LIMITS, node_id="desktop-twin", backend="stub")
        except Exception as exc:
            self._hal = None
            self._bio_register_error = (self._bio_register_error or "") + f";hal:{exc}"

    def _register_bio_modules(self) -> None:
        """Register exploration-only bio modules when importable."""
        try:
            from bio_digital.slime_mold import SlimeMoldModule
            from bio_digital.mycelium import MyceliumModule

            for mod in (SlimeMoldModule(), MyceliumModule()):
                c = mod.declare_contract()
                mid = c.identity.module_id
                self.stack.registry.register(
                    c,
                    artifact_digest=c.identity.artifact_digest,
                    author_signature=b"desktop",
                    module=mod,
                    test_bypass_promote="EXPLORATION",
                )
                self.bio_modules[mid] = mod
        except Exception as exc:
            self._bio_register_error = str(exc)
            self.bio_modules = {
                k: v for k, v in self.bio_modules.items() if not str(k).startswith("_")
            }

    # ----- Home / Status -----

    def home_status(self) -> dict[str, Any]:
        st = self.stack.status()
        device = select_compute_backend().as_dict()
        return {
            "organism_version": sdk_version,
            "desktop_version": DESKTOP_VERSION,
            "profile": st.get("profile"),
            "cpu_everywhere": True,
            "device": device,
            "accelerator_summary": accelerator_selection_summary(),
            "degradation_level": str(self.degrade.level),
            "router_level": st.get("router_level"),
            "module_count": st.get("module_count"),
            "modules": st.get("modules"),
            "workspace_bindings": st.get("workspace_bindings"),
            "health_host": st.get("health_host"),
            "health_port": st.get("health_port"),
            "serve_hint": "organism serve -c deploy/config/cpu_only.yaml",
            "ok": True,
        }

    # ----- Registry -----

    def list_modules(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for h in self.stack.registry.query(CapabilityFilter()):
            may = False
            try:
                mod = self.stack.modules.get(h.module_id) or self.bio_modules.get(h.module_id)
                if mod is None:
                    mod = self.stack.registry.get_module(h.module_id)
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

    def register_core_module(self, kind: CoreKind) -> dict[str, Any]:
        """Register (or re-register) deterministic_engine / learned_module from the UI."""
        if kind == "deterministic":
            from deterministic_engine.engine import DeterministicEngine

            mod: Any = DeterministicEngine()
            promote = "DELIBERATION"
        elif kind == "learned":
            from learned_module.module import LearnedModule

            mod = LearnedModule(precalibrate=True)
            promote = "DELIBERATION"
        else:
            raise ValueError(f"unknown core kind: {kind}")

        c = mod.declare_contract()
        mid = c.identity.module_id
        # Re-register overwrites existing entry (registry allows replace).
        if mid in self.stack.modules or mid in {
            h.module_id for h in self.stack.registry.query(CapabilityFilter())
        }:
            try:
                self.stack.registry.deregister(mid, drain="immediate", timeout_s=1)
            except Exception:
                pass
            self.stack.modules.pop(mid, None)

        resp = self.stack.registry.register(
            c,
            artifact_digest=c.identity.artifact_digest,
            author_signature=b"desktop",
            module=mod,
            test_bypass_promote=promote,  # type: ignore[arg-type]
        )
        self.stack.modules[mid] = mod
        return {
            "module_id": mid,
            "state": resp.initial_state,
            "kind": kind,
            "registered": True,
        }

    def deregister_module(self, module_id: str) -> dict[str, Any]:
        if module_id in self.bio_modules:
            raise ActuationRefused(
                f"Desktop refuses deregister of bio module {module_id!r} via destructive path "
                f"that could confuse exploration safety; use registry lifecycle APIs offline."
            )
        self.stack.registry.deregister(module_id, drain="immediate", timeout_s=1)
        self.stack.modules.pop(module_id, None)
        return {"module_id": module_id, "deregistered": True}

    # ----- Workspace -----

    def _all_bindings(self) -> list[Any]:
        ws = self.stack.workspace
        if hasattr(ws, "_bindings"):
            return list(getattr(ws, "_bindings").values())
        # Fallback: union common desktop tags
        seen: dict[str, Any] = {}
        for tag in ("desktop.demo", "desktop", "*"):
            try:
                for r in ws.read_by_tag([tag]):
                    seen[str(r.binding_id)] = r
            except Exception:
                continue
        return list(seen.values())

    def list_bindings(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = []
        for r in self._all_bindings()[:limit]:
            role = getattr(r, "role", None)
            filler = getattr(r, "filler", None)
            rows.append(
                {
                    "binding_id": str(getattr(r, "binding_id", "")),
                    "tags": list(getattr(r, "tags", ()) or ()),
                    "module_id": getattr(r, "module_id", "") or "",
                    "role_prefix": role.to_bytes_be()[:8].hex()
                    if hasattr(role, "to_bytes_be")
                    else "",
                    "filler_prefix": filler.to_bytes_be()[:8].hex()
                    if hasattr(filler, "to_bytes_be")
                    else "",
                }
            )
        return rows

    def write_demo_binding(self, tag: str = "desktop.demo") -> dict[str, Any]:
        role = Hypervector.random()
        filler = Hypervector.random()
        try:
            rec = self.stack.workspace.bind_exact(
                role, filler, tags=(tag,), module_id="organism.desktop"
            )
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

    def unbind_binding(self, binding_id: str) -> dict[str, Any]:
        prior = self.stack.workspace.unbind(UUID(binding_id))
        return {
            "binding_id": binding_id,
            "unbound": prior is not None,
            "remaining": self.stack.workspace.binding_count
            if hasattr(self.stack.workspace, "binding_count")
            else len(self._all_bindings()),
        }

    def hypervector_preview(self, seed: int = 0) -> dict[str, Any]:
        hv = Hypervector.random(seed=seed)
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
                "requires_interpretability": requires_interpretability,
                "requires_determinism": requires_determinism,
            },
            plan=plan_dict,
            ranking_trace=list(plan.ranking_trace or []),
            disposition=plan.disposition,
        )

    # ----- Physiology -----

    def physiology_snapshot(self) -> dict[str, Any]:
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
        immune: dict[str, Any] = {"available": self.immune is not None}
        if self.immune is not None:
            dlc = getattr(self.immune, "direct_lifecycle_calls", 0)
            immune["direct_lifecycle_calls"] = dlc() if callable(dlc) else dlc
        auto: dict[str, Any] = {"available": self.autonomic is not None}
        if self.autonomic is not None:
            auto["has_force_mode"] = hasattr(self.autonomic, "force_mode")
        return {
            "degradation_level": str(self.degrade.level),
            "router_level": self.stack.router.current_level(),
            "degrade_now_s": self.degrade.now_s,
            "transitions": list(self.degrade.transitions),
            "signals": {
                "thermal": self.degrade.signals.thermal,
                "h_m": dict(self.degrade.signals.h_m),
                "c_m": dict(self.degrade.signals.c_m),
                "det_ok": self.degrade.signals.det_ok,
                "trace_ok": self.degrade.signals.trace_ok,
            },
            "hormones": hormones,
            "immune": immune,
            "autonomic": auto,
        }

    def set_degradation_level(self, level: str) -> str:
        """Best-effort set router level (display / ops). Does not fake physiology."""
        self.stack.router.set_level(level)  # type: ignore[arg-type]
        return self.stack.router.current_level()

    def simulate_l0_to_l1(self) -> dict[str, Any]:
        """Safe physiology demo: drive DegradationMachine L0→L1 with FAST hysteresis.

        Does not touch wet-lab / bio actuation. Emits degradation traces onto the
        shared TraceEmitter. Uses virtual clock only.
        """
        if self.degrade.level != "L0":
            # Reset machine for a clean demo (keep shared trace).
            self.degrade = DegradationMachine(
                trace=self.stack.trace,
                t_down=dict(T_DOWN_FAST),
                t_up=dict(T_UP_FAST),
            )
        self.degrade.signals = HealthSignals(
            h_m={"learned_module_t2": "DEGRADED"},
            c_m={"learned_module_t2": 0.5},
            thermal=0.05,
            det_ok=True,
            trace_ok=True,
        )
        steps = 0
        while self.degrade.level == "L0" and steps < 40:
            self.degrade.advance(0.2)
            steps += 1
        # Mirror display level onto router for Home/Physiology consistency.
        if self.degrade.level == "L1":
            try:
                self.stack.router.set_level("L1")  # type: ignore[arg-type]
            except Exception:
                pass
        return {
            "ok": self.degrade.level == "L1",
            "level": self.degrade.level,
            "steps": steps,
            "now_s": self.degrade.now_s,
            "transitions": list(self.degrade.transitions),
            "safe": True,
            "note": "Virtual-clock L0→L1 demo; no bio actuation.",
        }

    def reset_physiology_demo(self) -> dict[str, Any]:
        self.degrade = DegradationMachine(
            trace=self.stack.trace,
            t_down=dict(T_DOWN_FAST),
            t_up=dict(T_UP_FAST),
        )
        try:
            self.stack.router.set_level("L0")  # type: ignore[arg-type]
        except Exception:
            pass
        return {"level": self.degrade.level, "router_level": self.stack.router.current_level()}

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
        twin = self.refresh_bio_twin()
        return {
            "modules": mods,
            "safety_policy": policy.as_dict(),
            "control_actuation_default": False,
            "twin": twin,
            "hal_available": self._hal is not None,
            "register_error": self._bio_register_error,
            "warning": "Bio-Digital panels are exploration-only. Actuation is refused.",
        }

    def refresh_bio_twin(self) -> dict[str, Any]:
        """Read HAL telemetry + twin sample (stub backend; CPU). Never actuates."""
        if self._hal is None:
            self._init_hal()
        if self._hal is None:
            return {"error": "HAL unavailable", "ok": False}
        try:
            tel = self._hal.read_telemetry()
            twin: dict[str, Any] = {
                "ok": True,
                "backend": getattr(self._hal, "backend", "stub"),
                "node_id": getattr(self._hal, "node_id", ""),
            }
            if hasattr(tel, "__dict__"):
                twin["telemetry"] = {
                    k: v for k, v in vars(tel).items() if not k.startswith("_")
                }
            else:
                twin["telemetry"] = str(tel)
            if hasattr(self._hal, "sample_twin"):
                twin["sample"] = self._hal.sample_twin()
            return twin
        except Exception as e:
            return {"ok": False, "error": str(e)}

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

    def list_traces(self, limit: int = 100, *, kind: str | None = None) -> list[dict[str, Any]]:
        raw = self.stack.trace.entries
        if callable(raw):
            raw = raw()
        entries = []
        for e in list(raw)[-limit:]:
            tname = type(e).__name__
            if kind and kind.lower() not in tname.lower():
                continue
            row: dict[str, Any] = {"type": tname}
            for attr in (
                "task_id",
                "form",
                "plan_type",
                "primary_module_id",
                "from_level",
                "to_level",
                "trigger_kind",
                "operation",
                "module_id",
                "event",
                "decision",
                "cortisol",
                "dopamine",
                "oxytocin",
                "source",
                "level",
            ):
                if hasattr(e, attr):
                    val = getattr(e, attr)
                    if isinstance(val, (bytes, bytearray)):
                        val = bytes(val)[:8].hex()
                    row[attr] = val
            if len(row) <= 1:
                row["repr"] = repr(e)[:500]
            entries.append(row)
        return entries

    def emit_demo_traces(self) -> dict[str, Any]:
        """Append routing + degradation + hormone sample entries for Traces panel."""
        trace: TraceEmitter = self.stack.trace
        before = len(trace.entries)
        # Routing via real decide
        result = self.run_pipeline(form="pattern_recognition", safety_tier="medium")
        # Explicit degradation sample (does not change machine level)
        trace.emit_degradation(
            DegradationTraceEntry(
                from_level="L0",
                to_level="L0",
                trigger_kind="desktop_demo_heartbeat",
                diagnosis_code="DEMO",
                event_class="heartbeat",
            )
        )
        # Hormone sample (v02 sink attached in create)
        try:
            trace.emit_hormone(
                HormoneTraceEntry(
                    hormone_state_digest="desktop-demo",
                    cortisol=0.1,
                    dopamine=0.2,
                    oxytocin=0.0,
                    melatonin=0.0,
                    staleness_ms=0.0,
                    source="desktop_demo",
                )
            )
        except NotImplementedError:
            pass
        after = len(trace.entries)
        return {
            "emitted": after - before,
            "pipeline_disposition": result.disposition,
            "count": after,
            "kinds": sorted({e["type"] for e in self.list_traces(limit=after)}),
        }

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
            "desktop_version": DESKTOP_VERSION,
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
