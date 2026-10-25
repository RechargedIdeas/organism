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
from organism_sdk.deploy.status_facts import PARITY_KEYS, common_status_facts
from organism_sdk.device import accelerator_selection_summary, select_compute_backend
from organism_sdk.hormone import HormoneBus
from organism_sdk.hypervector import Hypervector
from organism_sdk.immune import ImmuneLayer
from organism_sdk.metamodel import MetamodelTracker
from organism_sdk.generative import (
    ArtifactStore,
    AssetPipeline,
    CodePipeline,
    LLMStubBackend,
    OrganismStore,
    PromoteRefused,
    SkillRegistry,
    TemplateDraftBackend,
)
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

from organism_desktop.catalog import CATALOG, catalog_as_dicts, find_entry, instantiate

DESKTOP_VERSION = "1.7.0"

CoreKind = Literal["deterministic", "learned"]


def _parse_ranking_line(line: str) -> dict[str, Any]:
    """Best-effort parse of router ranking_trace strings into structured fields."""
    text = str(line)
    out: dict[str, Any] = {"raw": text}
    if text.startswith("order=") or "order=" in text:
        out["kind"] = "order"
        # order=['a', 'b'] or order=["a"]
        try:
            start = text.index("[")
            end = text.rindex("]") + 1
            inner = text[start + 1 : end - 1]
            parts = [p.strip().strip("'\"") for p in inner.split(",") if p.strip()]
            out["modules"] = parts
        except ValueError:
            out["modules"] = []
    elif "exclude" in text.lower():
        out["kind"] = "exclude"
    elif "constraint" in text.lower():
        out["kind"] = "constraint"
    else:
        out["kind"] = "note"
    return out




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
    artifact_store: ArtifactStore | None = None
    code_pipeline: CodePipeline | None = None
    asset_pipeline: AssetPipeline | None = None
    skill_registry: SkillRegistry | None = None
    organism_store: OrganismStore | None = None
    _last_organism_action: dict | None = None
    bio_modules: dict[str, Any] = field(default_factory=dict)
    _repo_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    _last_plan: DispatchPlan | None = None
    _last_pipeline: PipelineResult | None = None
    _last_contract_results: list[dict[str, Any]] = field(default_factory=list)
    _active_config_path: Path | None = None
    _bio_register_error: str | None = None
    _hal: Any = None
    _last_hormone_timeline: list[dict[str, Any]] = field(default_factory=list)
    _last_drillbook: dict[str, Any] | None = None
    _last_federation_stub: dict[str, Any] | None = None
    _last_harness_result: dict[str, Any] | None = None
    _last_rust_status: dict[str, Any] | None = None

    @classmethod
    def create(
        cls,
        cfg: DeployConfig | None = None,
        *,
        config_path: Path | str | None = None,
    ) -> "DesktopService":
        path = Path(config_path) if config_path else None
        if cfg is None and path is not None:
            cfg = load_deploy_config(path)
        elif cfg is None:
            # Prefer on-disk cpu_only when present so profile path is real.
            default_path = Path(__file__).resolve().parents[2] / "deploy" / "config" / "cpu_only.yaml"
            if default_path.is_file():
                path = default_path
                cfg = load_deploy_config(default_path)
            else:
                cfg = default_cpu_only_config()
        stack = build_minimal_stack(cfg)
        stack.trace.attach_v02_sink(V02TraceSink())
        # Share TraceEmitter so physiology transitions appear in Traces panel.
        degrade = DegradationMachine(
            trace=stack.trace,
            t_down=dict(T_DOWN_FAST),
            t_up=dict(T_UP_FAST),
        )
        svc = cls(stack=stack, degrade=degrade, _active_config_path=path)
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
        svc._init_generative()
        return svc

    def _init_generative(self) -> None:
        """Wire Organism generative evolution pipelines (CPU-only artifact roots)."""
        root = self._repo_root / "organism_data"
        art = ArtifactStore(root / "artifacts")
        self.artifact_store = art
        self.code_pipeline = CodePipeline(art)
        self.asset_pipeline = AssetPipeline(art, assets_root=root / "assets")
        self.skill_registry = SkillRegistry(art)
        self.organism_store = OrganismStore(root / "organisms")
        self.organism_store.ensure_default()
        self._last_organism_action = None

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
        common = common_status_facts(self.stack)
        device = common.get("device") or select_compute_backend().as_dict()
        return {
            "organism_version": common["organism_version"],
            "desktop_version": DESKTOP_VERSION,
            "profile": common["profile"],
            "version": common["version"],
            "cpu_everywhere": True,
            "device": device,
            "device_runtime": common["device_runtime"],
            "device_backend": common["device_backend"],
            "prefer_gpu": common["prefer_gpu"],
            "accelerator_summary": common["accelerator_summary"],
            "degradation_level": str(self.degrade.level),
            "router_level": self.stack.router.current_level(),
            "router_level_config": common["router_level_config"],
            "module_count": st.get("module_count"),
            "modules": st.get("modules"),
            "registered_ids": list(st.get("registered_ids") or []),
            "workspace_bindings": st.get("workspace_bindings"),
            "health_host": common["health_host"],
            "health_port": common["health_port"],
            "serve_hint": "organism serve -c deploy/config/cpu_only.yaml",
            "cli_parity": self.status_parity(),
            "soak": self.soak_snapshot(),
            "ok": True,
        }

    def status_parity(self) -> dict[str, Any]:
        """Subset of facts that must match `organism status` (enrich_cli_status).

        Compared against a freshly built MinimalStack with the same DeployConfig
        (Desktop may register extra bio modules; those are excluded from parity).
        """
        common = common_status_facts(self.stack)
        return {k: common[k] for k in PARITY_KEYS}

    def soak_snapshot(self) -> dict[str, Any]:
        """Lightweight ops soak snapshot for Home/Ops panels (no long soak)."""
        runbook = self._repo_root / "docs" / "ops" / "SOAK_RUNBOOK.md"
        script = self._repo_root / "scripts" / "soak_target.sh"
        try:
            from harness.scenarios.v04_soak import run_soak, soak_reconstructibility_ok

            # Tiny virtual-clock soak — UI/ops friendly, not the full suite.
            result = run_soak(windows=4, max_bindings=16)
            recon = soak_reconstructibility_ok(result)
            soak_body: dict[str, Any] = {
                "ok": True,
                "reconstructible": recon,
                "windows": result.windows,
                "plans": result.plans,
                "binding_count_final": result.binding_count_final,
                "flapping": result.flapping,
                "levels_seen": list(result.levels_seen),
            }
        except Exception as exc:
            soak_body = {"ok": False, "error": str(exc)}
        soak_body.update(
            {
                "runbook_path": str(runbook),
                "runbook_exists": runbook.is_file(),
                "script_path": str(script),
                "script_exists": script.is_file(),
                "cpu_everywhere": True,
            }
        )
        return soak_body

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
        result = PipelineResult(
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
        self._last_pipeline = result
        return result

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


    def last_hormone_timeline(self) -> list[dict[str, Any]]:
        return list(self._last_hormone_timeline)

    def run_hormone_timeline(
        self,
        *,
        windows: int = 12,
        dt_s: float = 1.0,
    ) -> dict[str, Any]:
        """Virtual-clock hormone_state demo → timeline rows + HormoneTraceEntry.

        Does not enable bio actuation. Links to Traces via shared TraceEmitter.
        """
        if self.hormone is None:
            return {
                "ok": False,
                "error": "hormone_bus_unavailable",
                "rows": [],
                "safe": True,
                "note": "HormoneBus not attached; timeline empty.",
            }
        windows = max(1, min(int(windows), 64))
        dt_s = float(dt_s) if dt_s > 0 else 1.0
        rows: list[dict[str, Any]] = []
        t_s = 0.0
        for i in range(windows):
            stress = 0.15 + 0.7 * (i / max(1, windows - 1))
            reward = 0.05 * (i % 4)
            accept = 0.4 + 0.5 * ((i % 5) / 4.0)
            phase = (i % 24) / 24.0
            levels = self.hormone.compute_release(
                stress_load=stress,
                viability_score=max(0.0, 1.0 - stress * 0.35),
                crisis_precursor_count=float(i // 8),
                mean_recent_reward=reward,
                adapter_acceptance_rate=accept,
                circadian_phase=phase,
                dt_s=dt_s,
            )
            self.hormone.write_telemetry_window(levels)
            reading = self.hormone.read_mirror(consumer="desktop_timeline")
            dig = levels.digest() if hasattr(levels, "digest") else ""
            try:
                self.stack.trace.emit_hormone(
                    HormoneTraceEntry(
                        hormone_state_digest=str(dig),
                        cortisol=float(levels.cortisol),
                        dopamine=float(levels.dopamine),
                        oxytocin=float(levels.oxytocin),
                        melatonin=float(levels.melatonin),
                        staleness_ms=float(getattr(reading, "staleness_ms", 0.0) or 0.0),
                        source=str(getattr(reading, "source", "hormone_bus_mirror")),
                    )
                )
            except Exception:
                pass
            row = {
                "t_s": round(t_s, 3),
                "window_id": levels.window_id,
                "cortisol": round(float(levels.cortisol), 6),
                "dopamine": round(float(levels.dopamine), 6),
                "oxytocin": round(float(levels.oxytocin), 6),
                "melatonin": round(float(levels.melatonin), 6),
                "stress_load": round(stress, 4),
                "source": str(getattr(reading, "source", levels.source)),
            }
            rows.append(row)
            t_s += dt_s
        self._last_hormone_timeline = rows
        return {
            "ok": True,
            "rows": rows,
            "windows": windows,
            "dt_s": dt_s,
            "safe": True,
            "note": "Virtual-clock hormone timeline; no bio actuation. Open Traces for Hormone entries.",
        }

    def run_degradation_drillbook(
        self,
        *,
        confirm: bool = False,
        target: str = "L4",
        max_steps_per_level: int = 48,
    ) -> dict[str, Any]:
        """Scripted L0→L4 physiology drill (virtual clock + FAST hysteresis).

        Requires ``confirm=True`` (Desktop shows a confirmation dialog). Never
        enables bio/wet-lab actuation. Emits DegradationTraceEntry per transition.
        """
        if not confirm:
            return {
                "ok": False,
                "error": "confirm_required",
                "safe": True,
                "note": "Drillbook refused without confirm=True. See docs/ops/DEGRADATION_DRILLBOOK.md",
            }
        order = ["L1", "L2", "L3", "L4"]
        if target not in ("L1", "L2", "L3", "L4"):
            return {"ok": False, "error": f"bad_target:{target}", "safe": True}
        stop_at = order.index(target)

        self.reset_physiology_demo()
        steps: list[dict[str, Any]] = []
        steps.append(
            {
                "phase": "start",
                "level": self.degrade.level,
                "now_s": self.degrade.now_s,
                "trigger": None,
            }
        )

        # Signal scripts for each downward hop (FAST hysteresis).
        scripts: list[tuple[str, HealthSignals]] = [
            (
                "L0→L1",
                HealthSignals(
                    h_m={"learned_module_t2": "DEGRADED"},
                    c_m={"learned_module_t2": 0.5},
                    thermal=0.05,
                    det_ok=True,
                    trace_ok=True,
                    causal_ok=True,
                ),
            ),
            (
                "L1→L2",
                HealthSignals(
                    h_m={"learned_module_t2": "FAILED"},
                    c_m={"learned_module_t2": 0.4},
                    thermal=0.05,
                    det_ok=True,
                    trace_ok=True,
                    causal_ok=False,
                ),
            ),
            (
                "L2→L3",
                HealthSignals(
                    h_m={"learned_module_t2": "FAILED"},
                    c_m={"learned_module_t2": 0.3},
                    thermal=0.05,
                    gc=0.65,
                    q_p95=80.0,
                    det_ok=True,
                    trace_ok=True,
                    causal_ok=False,
                ),
            ),
            (
                "L3→L4",
                HealthSignals(
                    h_m={"learned_module_t2": "FAILED"},
                    c_m={"learned_module_t2": 0.2},
                    thermal=0.05,
                    gc=0.9,
                    mem=0.95,
                    q_p95=300.0,
                    byz=True,
                    byz_count=3,
                    det_ok=False,
                    trace_ok=False,
                    causal_ok=False,
                ),
            ),
        ]

        for idx in range(stop_at + 1):
            phase, signals = scripts[idx]
            expect = order[idx]
            self.degrade.signals = signals
            advanced = 0
            while self.degrade.level != expect and advanced < max_steps_per_level:
                self.degrade.advance(0.2)
                advanced += 1
            steps.append(
                {
                    "phase": phase,
                    "level": self.degrade.level,
                    "expected": expect,
                    "now_s": round(self.degrade.now_s, 3),
                    "ticks": advanced,
                    "ok": self.degrade.level == expect,
                    "transitions": list(self.degrade.transitions),
                }
            )
            if self.degrade.level != expect:
                break

        # Mirror display level onto router
        try:
            self.stack.router.set_level(self.degrade.level)  # type: ignore[arg-type]
        except Exception:
            pass

        result = {
            "ok": self.degrade.level == target,
            "level": self.degrade.level,
            "target": target,
            "steps": steps,
            "transitions": list(self.degrade.transitions),
            "now_s": self.degrade.now_s,
            "safe": True,
            "bio_actuation": False,
            "note": (
                "Virtual-clock degradation drillbook; no bio actuation. "
                "Reset with reset_physiology_demo(). See docs/ops/DEGRADATION_DRILLBOOK.md"
            ),
        }
        self._last_drillbook = result
        return result

    def last_drillbook(self) -> dict[str, Any] | None:
        return dict(self._last_drillbook) if self._last_drillbook else None

    def run_federation_stub(self) -> dict[str, Any]:
        """Exploration-only multi-node mirror lag + oxytocin quorum (not WAN BFT)."""
        from organism_sdk.multinode import MultiNodeCluster

        cluster = MultiNodeCluster(
            ["node_a", "node_b", "node_c"],
            default_lag_ms=2.0,
            lag_slo_ms=50.0,
        )
        levels = cluster.release_and_mirror(
            "node_a",
            lag_ms=2.0,
            stress_load=0.55,
            viability_score=0.7,
            adapter_acceptance_rate=0.9,
        )
        applied = cluster.advance(wait_ms=5.0)
        try:
            cluster.assert_lag_slo()
            lag_ok = True
            lag_error = None
        except AssertionError as exc:
            lag_ok = False
            lag_error = str(exc)
        quorum = cluster.federated_oxytocin(
            votes={"node_a": 0.9, "node_b": 0.85, "node_c": 0.8},
            accept_threshold=0.5,
        )
        # Partition demo (safe degrade path)
        cluster.partition("node_c")
        quorum_part = cluster.federated_oxytocin(
            votes={"node_a": 0.9, "node_b": 0.85, "node_c": 0.1},
            accept_threshold=0.5,
        )
        cluster.heal("node_c")
        result = {
            "ok": True,
            "safe": True,
            "stub_only": True,
            "not_production_bft": True,
            "note": (
                "Software multi-node stub only — not production WAN BFT + TPM. "
                "See STATUS.md external deps."
            ),
            "release": levels.as_dict() if hasattr(levels, "as_dict") else {},
            "mirrors_applied": applied,
            "max_lag_ms": cluster.max_observed_lag_ms(),
            "lag_slo_ok": lag_ok,
            "lag_error": lag_error,
            "quorum": quorum.as_dict(),
            "quorum_after_partition_c": quorum_part.as_dict(),
            "nodes": list(cluster.nodes.keys()),
        }
        self._last_federation_stub = result
        return result

    def last_federation_stub(self) -> dict[str, Any] | None:
        return dict(self._last_federation_stub) if self._last_federation_stub else None

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

    def list_traces(
        self,
        limit: int = 100,
        *,
        kind: str | None = None,
        task_id: str | None = None,
        since_iso: str | None = None,
    ) -> list[dict[str, Any]]:
        raw = self.stack.trace.entries
        if callable(raw):
            raw = raw()
        all_raw = list(raw)
        entries = []
        # Walk full buffer for seq; then filter + tail limit
        for seq, e in enumerate(all_raw):
            tname = type(e).__name__
            kind_label = tname.replace("TraceEntry", "") or tname
            if kind and kind.lower() not in tname.lower() and kind.lower() not in kind_label.lower():
                continue
            row: dict[str, Any] = {
                "seq": seq,
                "type": tname,
                "kind": kind_label,
            }
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
                "emitted_at",
            ):
                if hasattr(e, attr):
                    val = getattr(e, attr)
                    if isinstance(val, (bytes, bytearray)):
                        val = bytes(val)[:8].hex()
                    elif hasattr(val, "isoformat"):
                        val = val.isoformat()
                    row[attr] = val
            if task_id and str(row.get("task_id") or "") != task_id:
                continue
            if since_iso:
                emitted = str(row.get("emitted_at") or "")
                if emitted and emitted < since_iso:
                    continue
            if len(row) <= 3:
                row["repr"] = repr(e)[:500]
            entries.append(row)
        return entries[-limit:]

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

    def export_traces_json(
        self,
        path: str | Path,
        *,
        kind: str | None = None,
        task_id: str | None = None,
        limit: int = 10_000,
    ) -> dict[str, Any]:
        """Write filtered traces to a JSON file; returns summary metadata."""
        import json

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        entries = self.list_traces(limit=limit, kind=kind, task_id=task_id)
        payload = {
            "organism_desktop": DESKTOP_VERSION,
            "count": len(entries),
            "filter": {"kind": kind, "task_id": task_id, "limit": limit},
            "entries": entries,
        }
        p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return {"ok": True, "path": str(p.resolve()), "count": len(entries)}

    def traces_for_last_pipeline(self, limit: int = 200) -> dict[str, Any]:
        """Jump helper: traces tied to the last pipeline decide task_id."""
        if self._last_pipeline is None:
            return {"ok": False, "error": "no pipeline result yet", "entries": []}
        tid = self._last_pipeline.task.get("task_id")
        entries = self.list_traces(limit=limit, task_id=str(tid) if tid else None)
        # Also include recent routing if task filter empty
        if not entries:
            entries = self.list_traces(limit=limit, kind="Routing")
        return {
            "ok": True,
            "task_id": tid,
            "disposition": self._last_pipeline.disposition,
            "count": len(entries),
            "entries": entries,
        }

    def inspect_plan(self) -> dict[str, Any]:
        """Structured router/plan inspector for the last DispatchPlan (not raw-only)."""
        if self._last_pipeline is None:
            return {"ok": False, "error": "no plan yet — run decide first"}
        plan = self._last_pipeline.plan
        ranking = list(self._last_pipeline.ranking_trace or plan.get("ranking_trace") or [])
        steps: list[dict[str, Any]] = []
        for i, line in enumerate(ranking):
            steps.append({"step": i, "text": line, "parsed": _parse_ranking_line(line)})
        primary = plan.get("primary") or {}
        return {
            "ok": True,
            "task": self._last_pipeline.task,
            "disposition": self._last_pipeline.disposition,
            "summary": {
                "plan_id": plan.get("plan_id"),
                "task_id": plan.get("task_id"),
                "level": plan.get("level"),
                "plan_type": plan.get("plan_type"),
                "primary_module": primary.get("module_id"),
                "primary_role": primary.get("role"),
                "primary_tier": primary.get("tier"),
                "fallbacks": list(plan.get("fallbacks") or []),
                "excluded_count": len(plan.get("excluded") or []),
                "cross_check_required": plan.get("cross_check_required"),
                "hold_reason": plan.get("hold_reason"),
                "constraints_applied": list(plan.get("constraints_applied") or []),
                "candidate_roles": list(plan.get("candidate_roles") or []),
            },
            "excluded": list(plan.get("excluded") or []),
            "ranking_steps": steps,
            "ranking_trace": ranking,
            "plan": plan,
        }

    # ----- Deploy profiles -----

    def list_deploy_profiles(self) -> list[dict[str, Any]]:
        cfg_dir = self._repo_root / "deploy" / "config"
        out: list[dict[str, Any]] = []
        active = self.stack.config.profile
        active_path = str(self._active_config_path) if self._active_config_path else None
        for p in sorted(cfg_dir.glob("*.yaml")):
            try:
                cfg = load_deploy_config(p)
                issues = []
                try:
                    from organism_sdk.deploy.config import validate_deploy_config

                    issues = validate_deploy_config(cfg)
                except Exception as exc:
                    issues = [str(exc)]
                out.append(
                    {
                        "name": cfg.profile,
                        "path": str(p),
                        "prefer_gpu": cfg.runtime.prefer_gpu,
                        "health_port": cfg.health.port,
                        "router_level": cfg.stack.router_level,
                        "ok": not issues,
                        "issues": issues,
                        "active": cfg.profile == active and (
                            active_path is None or str(p) == active_path
                        ),
                    }
                )
            except Exception as exc:
                out.append(
                    {
                        "name": p.stem,
                        "path": str(p),
                        "ok": False,
                        "issues": [str(exc)],
                        "active": False,
                    }
                )
        return out

    def switch_deploy_profile(self, profile: str) -> dict[str, Any]:
        """Rebuild Desktop stack under a named deploy profile (cpu_only / default / …).

        Preserves shared TraceEmitter entries by copying after rebuild is not
        attempted — a clean stack is intentional so status_facts reflect the
        new profile. Bio modules re-register. Actuation remains refused.
        """
        profiles = {p["name"]: p for p in self.list_deploy_profiles() if p.get("ok")}
        # Also match by path stem
        if profile not in profiles:
            for p in self.list_deploy_profiles():
                if Path(p["path"]).stem == profile and p.get("ok"):
                    profiles[profile] = p
                    break
        if profile not in profiles:
            raise ValueError(
                f"unknown or invalid deploy profile {profile!r}; "
                f"known={[p['name'] for p in self.list_deploy_profiles()]}"
            )
        meta = profiles[profile]
        path = Path(meta["path"])
        before = self.status_parity()
        new_svc = DesktopService.create(config_path=path)
        # Transplant rebuilt state into this instance (panels hold self.service ref).
        self.stack = new_svc.stack
        self.degrade = new_svc.degrade
        self.hormone = new_svc.hormone
        self.immune = new_svc.immune
        self.autonomic = new_svc.autonomic
        self.metamodel = new_svc.metamodel
        self.artifact_store = new_svc.artifact_store
        self.code_pipeline = new_svc.code_pipeline
        self.asset_pipeline = new_svc.asset_pipeline
        self.skill_registry = new_svc.skill_registry
        self.organism_store = new_svc.organism_store
        self._last_organism_action = new_svc._last_organism_action
        self.bio_modules = new_svc.bio_modules
        self._hal = new_svc._hal
        self._bio_register_error = new_svc._bio_register_error
        self._active_config_path = new_svc._active_config_path
        self._last_plan = None
        self._last_pipeline = None
        after = self.status_parity()
        return {
            "ok": True,
            "profile": self.stack.config.profile,
            "path": str(path),
            "before": before,
            "after": after,
            "delta": {
                k: {"before": before.get(k), "after": after.get(k)}
                for k in sorted(set(before) | set(after))
                if before.get(k) != after.get(k)
            },
            "cpu_everywhere": True,
        }

    # ----- Module catalog -----

    def module_catalog(self) -> list[dict[str, Any]]:
        registered = {m["module_id"] for m in self.list_modules()}
        return catalog_as_dicts(registered_ids=registered)

    def register_catalog_module(self, catalog_id: str) -> dict[str, Any]:
        """One-click register from the substrate catalog.

        RESEARCH_TIER modules register with exploration promote; Desktop never
        flips may_actuate to True for research entries.
        """
        entry = find_entry(catalog_id)
        if entry is None:
            raise KeyError(f"unknown catalog_id: {catalog_id}")
        # Reuse core path for deterministic / learned
        if catalog_id == "deterministic_engine":
            return self.register_core_module("deterministic")
        if catalog_id == "learned_module":
            return self.register_core_module("learned")

        _entry, mod = instantiate(catalog_id)
        # Special-case learned already handled; physical/snn always may_actuate False
        c = mod.declare_contract()
        mid = c.identity.module_id
        may = bool(getattr(getattr(c, "safety", None), "may_actuate", False))
        if entry.research_tier and may:
            raise ActuationRefused(
                f"REFUSE: RESEARCH_TIER catalog entry {catalog_id!r} declared may_actuate=True"
            )
        if mid in self.stack.modules or mid in {
            h.module_id for h in self.stack.registry.query(CapabilityFilter())
        }:
            try:
                self.stack.registry.deregister(mid, drain="immediate", timeout_s=1)
            except Exception:
                pass
            self.stack.modules.pop(mid, None)

        promote = "EXPLORATION" if entry.research_tier else entry.promote
        resp = self.stack.registry.register(
            c,
            artifact_digest=c.identity.artifact_digest,
            author_signature=b"desktop-catalog",
            module=mod,
            test_bypass_promote=promote,  # type: ignore[arg-type]
        )
        self.stack.modules[mid] = mod
        return {
            "module_id": mid,
            "catalog_id": catalog_id,
            "state": resp.initial_state,
            "research_tier": entry.research_tier,
            "research_badge": "RESEARCH_TIER" if entry.research_tier else "",
            "may_actuate": may,
            "registered": True,
        }

    # ----- Contract / assert -----

    def run_contract_checks(self, *, module_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Validate SubstrateContracts for registered modules; store last results."""
        want = set(module_ids) if module_ids else None
        results: list[dict[str, Any]] = []
        for mid, mod in list(self.stack.modules.items()):
            if want is not None and mid not in want:
                continue
            if not hasattr(mod, "declare_contract"):
                results.append(
                    {
                        "module_id": mid,
                        "ok": False,
                        "error": "no declare_contract",
                        "issues": [],
                        "issue_count": 0,
                        "may_actuate": False,
                        "research_tier": False,
                    }
                )
                continue
            try:
                contract = mod.declare_contract()
                issues = contract.validate() if hasattr(contract, "validate") else []
                issue_rows = [
                    {
                        "severity": str(getattr(i, "severity", "")),
                        "code": getattr(i, "code", ""),
                        "field_path": getattr(i, "field_path", ""),
                        "message": getattr(i, "message", str(i)),
                    }
                    for i in issues
                ]
                may = bool(getattr(getattr(contract, "safety", None), "may_actuate", False))
                tier = str(
                    getattr(getattr(contract, "safety", None), "reliability_tier", "")
                    or getattr(getattr(contract, "identity", None), "role", "")
                )
                max_safety = str(
                    getattr(getattr(contract, "safety", None), "max_safety_tier", "")
                )
                research = "RESEARCH" in max_safety.upper() or mid == "physical_research"
                errors = [i for i in issue_rows if "ERROR" in str(i.get("severity", "")).upper()]
                results.append(
                    {
                        "module_id": mid,
                        "ok": len(errors) == 0,
                        "issue_count": len(issue_rows),
                        "error_count": len(errors),
                        "issues": issue_rows,
                        "may_actuate": may,
                        "reliability_tier": tier,
                        "max_safety_tier": max_safety,
                        "research_tier": research,
                        "research_badge": "RESEARCH_TIER" if research else "",
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "module_id": mid,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                        "issues": [],
                        "issue_count": 0,
                        "may_actuate": False,
                        "research_tier": False,
                    }
                )
        # Include bio modules not copied into stack.modules
        for mid, mod in self.bio_modules.items():
            if mid in {r["module_id"] for r in results}:
                continue
            if want is not None and mid not in want:
                continue
            try:
                contract = mod.declare_contract()
                issues = contract.validate() if hasattr(contract, "validate") else []
                issue_rows = [
                    {
                        "severity": str(getattr(i, "severity", "")),
                        "code": getattr(i, "code", ""),
                        "field_path": getattr(i, "field_path", ""),
                        "message": getattr(i, "message", str(i)),
                    }
                    for i in issues
                ]
                may = bool(getattr(getattr(contract, "safety", None), "may_actuate", False))
                results.append(
                    {
                        "module_id": mid,
                        "ok": not any("ERROR" in str(i.get("severity", "")).upper() for i in issue_rows),
                        "issue_count": len(issue_rows),
                        "issues": issue_rows,
                        "may_actuate": may,
                        "research_tier": True,
                        "research_badge": "RESEARCH_TIER",
                        "bio_exploration": True,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "module_id": mid,
                        "ok": False,
                        "error": str(exc),
                        "issues": [],
                        "may_actuate": False,
                        "research_tier": True,
                    }
                )
        self._last_contract_results = results
        return results

    def last_contract_results(self) -> list[dict[str, Any]]:
        return list(self._last_contract_results)

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

        validate = self.validate_deploy_config()
        runbook = self._repo_root / "docs" / "ops" / "SOAK_RUNBOOK.md"
        script = self._repo_root / "scripts" / "soak_target.sh"
        cfg_path = self._repo_root / "deploy" / "config" / "cpu_only.yaml"
        profiles = self.list_deploy_profiles()
        active_path = str(self._active_config_path) if self._active_config_path else str(cfg_path)
        return {
            "cpu_everywhere": True,
            "cpu_everywhere_badge": "CPU Everywhere ●",
            "deploy_profile": self.stack.config.profile,
            "deploy_config_path": active_path,
            "deploy_config_exists": Path(active_path).is_file() if active_path else cfg_path.is_file(),
            "profiles": profiles,
            "active_profile": self.stack.config.profile,
            "status_parity": self.status_parity(),
            "validate": validate,
            "soak_runbook": str(runbook),
            "soak_runbook_exists": runbook.is_file(),
            "soak_script": str(script),
            "soak_script_exists": script.is_file(),
            "soak_snapshot": self.soak_snapshot(),
            "cli_parity": self.status_parity(),
            "wetlab_policy_doc": str(self._repo_root / "docs" / "ops" / "WETLAB_SAFETY_POLICY.md"),
            "wetlab_policy": SafetyPolicy.deny_all().as_dict(),
            "cpu_everywhere_doc": str(self._repo_root / "docs" / "CPU_EVERYWHERE.md"),
            "api_freeze": str(self._repo_root / "docs" / "API_FREEZE_v1.0.md"),
            "desktop_version": DESKTOP_VERSION,
            "organism_version": sdk_version,
            "rust_runtime": self.rust_runtime_status(probe_cargo=False),
            "last_harness_result": self._last_harness_result,
            "drillbook_doc": str(self._repo_root / "docs" / "ops" / "DEGRADATION_DRILLBOOK.md"),
        }

    def refresh_bundle(self) -> dict[str, Any]:
        """Aggregate snapshot used by Refresh-All (Ctrl+Shift+R)."""
        return {
            "home": self.home_status(),
            "ops": self.ops_info(),
            "physiology": self.physiology_snapshot(),
            "modules": len(self.list_modules()),
            "bindings": len(self.list_bindings()),
            "traces": len(self.list_traces(limit=500)),
            "catalog": len(self.module_catalog()),
            "contracts": len(self._last_contract_results),
            "profile": self.stack.config.profile,
            "ok": True,
        }


    def rust_runtime_status(self, *, probe_cargo: bool = True) -> dict[str, Any]:
        """Read-only Rust workspace parity probe (no build forced on every refresh)."""
        import json
        import shutil
        import subprocess

        root = self._repo_root
        cargo_toml = root / "Cargo.toml"
        member_dirs = [
            "runtime/registry",
            "runtime/workspace",
            "runtime/router",
            "runtime/degradation",
            "runtime/control_loop",
            "sdk/rust/organism-proto",
            "sdk/rust/organism-client",
            "modules/kernel",
            "modules/hdc",
            "harness/runner",
            "harness/injector",
            "harness/observer",
            "harness/assertions",
        ]
        crates = []
        present = 0
        for rel in member_dirs:
            p = root / rel
            lib_rs = p / "src" / "lib.rs"
            main_rs = p / "src" / "main.rs"
            ok = lib_rs.is_file() or main_rs.is_file()
            if ok:
                present += 1
            crates.append(
                {
                    "path": rel,
                    "present": ok,
                    "lib_rs": lib_rs.is_file(),
                    "main_rs": main_rs.is_file(),
                }
            )
        cargo_bin = shutil.which("cargo")
        rustc_bin = shutil.which("rustc")
        meta: dict[str, Any] = {"probed": False}
        if probe_cargo and cargo_bin and cargo_toml.is_file():
            try:
                proc = subprocess.run(
                    [cargo_bin, "metadata", "--no-deps", "--format-version", "1"],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                meta["probed"] = True
                meta["returncode"] = proc.returncode
                if proc.returncode == 0 and proc.stdout.strip():
                    data = json.loads(proc.stdout)
                    meta["package_names"] = [p.get("name") for p in data.get("packages", [])]
                    meta["package_count"] = len(meta["package_names"])
                    ws = data.get("workspace_root")
                    meta["workspace_root"] = ws
                else:
                    meta["stderr"] = (proc.stderr or "")[:500]
            except Exception as exc:
                meta["probed"] = True
                meta["error"] = str(exc)

        # Workspace package version from Cargo.toml (best-effort)
        ws_version = None
        if cargo_toml.is_file():
            for line in cargo_toml.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip().startswith("version"):
                    # first version= under [workspace.package] typically
                    if '"' in line:
                        ws_version = line.split('"')[1]
                        break

        result = {
            "ok": cargo_toml.is_file() and present > 0,
            "read_only": True,
            "cargo_toml_exists": cargo_toml.is_file(),
            "workspace_package_version": ws_version,
            "crates_present": present,
            "crates_expected": len(member_dirs),
            "crates": crates,
            "cargo_bin": cargo_bin,
            "rustc_bin": rustc_bin,
            "cargo_metadata": meta,
            "note": (
                "Read-only inventory. Desktop never force-builds Rust on panel refresh. "
                "Use `cargo test -q` locally for full parity."
            ),
        }
        self._last_rust_status = result
        return result

    def last_rust_status(self) -> dict[str, Any] | None:
        return dict(self._last_rust_status) if self._last_rust_status else None

    def run_short_soak_harness(self, *, windows: int = 8) -> dict[str, Any]:
        """Trigger a short virtual-clock soak; write JSON under desktop/artifacts/."""
        import json
        from datetime import datetime, timezone

        from harness.scenarios.v04_soak import run_soak, soak_reconstructibility_ok

        windows = max(2, min(int(windows), 48))
        result = run_soak(windows=windows, max_bindings=16)
        recon = soak_reconstructibility_ok(result)
        out_dir = self._repo_root / "desktop" / "artifacts"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = out_dir / f"soak_{stamp}.json"
        payload = {
            "kind": "soak",
            "ok": True,
            "windows": result.windows,
            "simulated_s": result.simulated_s,
            "levels_seen": list(result.levels_seen),
            "transitions": [list(t) for t in result.transitions],
            "binding_count_peak": result.binding_count_peak,
            "binding_count_final": result.binding_count_final,
            "plans": result.plans,
            "hormone_windows": result.hormone_windows,
            "flapping": result.flapping,
            "reconstructible": recon,
            "written_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        out = {
            "ok": True,
            "kind": "soak",
            "result_path": str(path),
            "reconstructible": recon,
            "windows": result.windows,
            "flapping": result.flapping,
            "levels_seen": list(result.levels_seen),
            "safe": True,
            "progress": [
                {"step": "init", "pct": 0},
                {"step": "soak_windows", "pct": 70, "windows": windows},
                {"step": "write_artifact", "pct": 100, "path": str(path)},
            ],
        }
        self._last_harness_result = out
        return out

    def run_short_fuzz_harness(self, *, trials: int = 16) -> dict[str, Any]:
        """Trigger short security fuzz helpers; write JSON under desktop/artifacts/."""
        import json
        from datetime import datetime, timezone

        from harness.scenarios.v04_security_fuzz import (
            fuzz_immune_forgeries,
            fuzz_malformed_contracts,
        )

        trials = max(4, min(int(trials), 64))
        contracts = fuzz_malformed_contracts(trials=trials)
        forgeries = fuzz_immune_forgeries(trials=trials)
        out_dir = self._repo_root / "desktop" / "artifacts"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = out_dir / f"fuzz_{stamp}.json"
        payload = {
            "kind": "fuzz",
            "ok": True,
            "contracts": {
                "trials": contracts.trials,
                "rejected_contracts": contracts.rejected_contracts,
            },
            "forgeries": {
                "trials": forgeries.trials,
                "rejected_forgeries": forgeries.rejected_forgeries,
            },
            "written_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        out = {
            "ok": True,
            "kind": "fuzz",
            "result_path": str(path),
            "contracts_rejected": contracts.rejected_contracts,
            "forgeries_rejected": forgeries.rejected_forgeries,
            "trials": trials,
            "safe": True,
            "progress": [
                {"step": "init", "pct": 0},
                {"step": "fuzz_contracts", "pct": 40, "rejected": contracts.rejected_contracts},
                {"step": "fuzz_forgeries", "pct": 80, "rejected": forgeries.rejected_forgeries},
                {"step": "write_artifact", "pct": 100, "path": str(path)},
            ],
        }
        self._last_harness_result = out
        return out

    def last_harness_result(self) -> dict[str, Any] | None:
        return dict(self._last_harness_result) if self._last_harness_result else None


    # ----- Organism generative evolution (v1.7) -----

    def _require_generative(self) -> None:
        if self.code_pipeline is None or self.organism_store is None:
            self._init_generative()

    def organism_snapshot(self) -> dict:
        self._require_generative()
        assert self.organism_store is not None and self.skill_registry is not None
        assert self.asset_pipeline is not None
        profile = self.organism_store.ensure_default()
        # keep skills synced from registry
        self.organism_store.sync_skills(profile.organism_id, self.skill_registry.list_skills())
        self.organism_store.sync_appearance(profile.organism_id, self.asset_pipeline.appearance)
        profile = self.organism_store.get(profile.organism_id)
        assert profile is not None
        d = profile.as_dict()
        d["cpu_everywhere"] = True
        d["may_actuate"] = False
        return d

    def last_organism_action(self) -> dict | None:
        return dict(self._last_organism_action) if self._last_organism_action else None

    def list_code_bundles(self) -> list:
        self._require_generative()
        assert self.code_pipeline is not None
        return self.code_pipeline.list_bundles()

    def evolve_organism_skill(
        self,
        name: str,
        *,
        intent: str,
        auto_promote: bool = False,
        backend: str = "template",
    ) -> dict:
        self._require_generative()
        assert self.skill_registry and self.code_pipeline and self.organism_store
        profile = self.organism_store.ensure_default()
        skill, bundle = self.skill_registry.generate_skill(
            name,
            intent=intent,
            code_pipeline=self.code_pipeline,
            auto_promote=auto_promote,
            backend_name=backend,
        )
        self.organism_store.sync_skills(profile.organism_id, self.skill_registry.list_skills())
        self.organism_store.add_code_revision(profile.organism_id, bundle.as_dict())
        self.organism_store.log(
            profile.organism_id,
            "skill_generate",
            f"Generated skill {skill.name} stage={bundle.stage.value}",
            payload={"skill_id": skill.skill_id, "bundle_id": bundle.bundle_id},
        )
        out = {
            "ok": bundle.stage.value != "REJECTED",
            "skill": skill.as_dict(),
            "bundle": bundle.as_dict(),
            "gate_ready": bundle.gate.ready() or bundle.may_control,
        }
        self._last_organism_action = out
        return out

    def promote_organism_skill(self, skill_id: str) -> dict:
        self._require_generative()
        assert self.skill_registry and self.code_pipeline and self.organism_store
        profile = self.organism_store.ensure_default()
        try:
            skill = self.skill_registry.promote_skill(skill_id, code_pipeline=self.code_pipeline)
        except PromoteRefused as e:
            raise ActuationRefused(f"REFUSE unsafe skill promote: {e}") from e
        self.organism_store.sync_skills(profile.organism_id, self.skill_registry.list_skills())
        self.organism_store.log(
            profile.organism_id,
            "skill_promote",
            f"Promoted skill {skill_id}",
            payload={"skill_id": skill_id, "may_control": skill.may_control},
        )
        out = {"ok": True, "skill": skill.as_dict()}
        self._last_organism_action = out
        return out

    def evolve_organism_looks(self, brief: str, *, kind: str = "avatar") -> dict:
        self._require_generative()
        assert self.asset_pipeline and self.organism_store
        profile = self.organism_store.ensure_default()
        result = self.asset_pipeline.evolve_looks(brief, kind=kind)  # type: ignore[arg-type]
        if result.get("ok"):
            self.organism_store.sync_appearance(profile.organism_id, self.asset_pipeline.appearance)
            self.organism_store.log(
                profile.organism_id,
                "looks_apply",
                f"Applied {kind} from brief",
                payload=result.get("appearance") or {},
            )
        self._last_organism_action = result
        return result

    def evolve_organism_code(
        self,
        intent: str,
        *,
        auto_promote: bool = False,
        backend: str = "template",
    ) -> dict:
        self._require_generative()
        assert self.code_pipeline and self.organism_store
        profile = self.organism_store.ensure_default()
        be = LLMStubBackend() if backend == "llm_stub" else TemplateDraftBackend()
        bundle = self.code_pipeline.evolve(
            intent,
            spec={"skill_name": "organism_code", "may_actuate": False},
            backend=be,
            auto_promote=auto_promote,
        )
        self.organism_store.add_code_revision(profile.organism_id, bundle.as_dict())
        self.organism_store.log(
            profile.organism_id,
            "code_draft",
            f"Code pipeline → {bundle.stage.value}",
            payload={"bundle_id": bundle.bundle_id, "stage": bundle.stage.value},
        )
        out = {
            "ok": bundle.stage.value != "REJECTED",
            "bundle": bundle.as_dict(),
            "gate_ready": bundle.gate.ready() or bundle.may_control,
        }
        self._last_organism_action = out
        return out

    def promote_organism_code(self, bundle_id: str) -> dict:
        self._require_generative()
        assert self.code_pipeline and self.organism_store
        profile = self.organism_store.ensure_default()
        try:
            bundle = self.code_pipeline.promote(bundle_id)
        except PromoteRefused as e:
            raise ActuationRefused(f"REFUSE unsafe code promote: {e}") from e
        self.organism_store.add_code_revision(profile.organism_id, bundle.as_dict())
        self.organism_store.log(
            profile.organism_id,
            "code_promote",
            f"Promoted code bundle {bundle_id}",
            payload={"bundle_id": bundle_id, "may_control": bundle.may_control},
        )
        out = {"ok": True, "bundle": bundle.as_dict()}
        self._last_organism_action = out
        return out

    def demote_organism_code(self, bundle_id: str, *, reason: str = "desktop_demote") -> dict:
        self._require_generative()
        assert self.code_pipeline and self.organism_store
        profile = self.organism_store.ensure_default()
        bundle = self.code_pipeline.demote(bundle_id, reason=reason)
        self.organism_store.add_code_revision(profile.organism_id, bundle.as_dict())
        self.organism_store.log(
            profile.organism_id,
            "code_demote",
            f"Demoted code bundle {bundle_id}",
            payload={"bundle_id": bundle_id, "reason": reason},
        )
        out = {"ok": True, "bundle": bundle.as_dict()}
        self._last_organism_action = out
        return out

    def docs_links(self) -> list[dict[str, str]]:
        root = self._repo_root / "docs"
        return [
            {"title": "CPU Everywhere", "path": str(root / "CPU_EVERYWHERE.md")},
            {"title": "Soak Runbook", "path": str(root / "ops" / "SOAK_RUNBOOK.md")},
            {"title": "Degradation Drillbook", "path": str(root / "ops" / "DEGRADATION_DRILLBOOK.md")},
            {"title": "Wet-lab Safety Policy", "path": str(root / "ops" / "WETLAB_SAFETY_POLICY.md")},
            {"title": "Organism Generative Evolution", "path": str(root / "v1.7" / "ORGANISM_GENERATIVE_EVOLUTION.md")},
            {"title": "Desktop v1.7", "path": str(root / "v1.7" / "DESKTOP.md")},
            {"title": "Desktop v1.6.1", "path": str(root / "v1.6.1" / "DESKTOP.md")},
            {"title": "API Freeze v1.0", "path": str(root / "API_FREEZE_v1.0.md")},
            {"title": "Desktop Design", "path": str(root / "v1.5" / "DESKTOP.md")},
            {"title": "Desktop v1.6", "path": str(root / "v1.6" / "DESKTOP.md")},
            {"title": "Packaging", "path": str(self._repo_root / "desktop" / "docs" / "PACKAGING.md")},
            {"title": "Deploy README", "path": str(self._repo_root / "deploy" / "README.md")},
        ]
