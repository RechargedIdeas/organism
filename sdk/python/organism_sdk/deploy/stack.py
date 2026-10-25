"""Minimal in-process registry + workspace + router stack (v1.4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from organism_sdk.deploy.config import DeployConfig, default_cpu_only_config
from organism_sdk.device import RuntimeId, select_compute_backend
from organism_sdk.health import HealthReport
from organism_sdk.registry import CapabilityFilter, RegistryClient
from organism_sdk.router import Router
from organism_sdk.trace import TraceEmitter
from organism_sdk.workspace import WorkspaceClient


@dataclass
class MinimalStack:
    config: DeployConfig
    trace: TraceEmitter
    registry: RegistryClient
    workspace: WorkspaceClient
    router: Router
    modules: dict[str, Any] = field(default_factory=dict)
    device: dict[str, Any] = field(default_factory=dict)

    def status(self) -> dict[str, Any]:
        handles = []
        for h in self.registry.query(CapabilityFilter()):
            handles.append(
                {
                    "module_id": h.module_id,
                    "state": h.state,
                    "role": str(h.role),
                    "version": h.version,
                }
            )
        return {
            "profile": self.config.profile,
            "version": self.config.version,
            "device": self.device,
            "router_level": self.config.stack.router_level,
            "modules": handles,
            "module_count": len(handles),
            "registered_ids": sorted(self.modules.keys()),
            "workspace_bindings": self.workspace.binding_count,
            "health_host": self.config.health.host,
            "health_port": self.config.health.port,
            "prefer_gpu": self.config.runtime.prefer_gpu,
            "ok": True,
        }

    def health_report(self) -> HealthReport:
        return HealthReport(
            module_id="organism.serve",
            status="HEALTHY",
            score=1.0,
            probes={
                "profile": self.config.profile,
                "modules": sorted(self.modules.keys()),
                "device": self.device,
                "bindings": self.workspace.binding_count,
            },
        )


def build_minimal_stack(cfg: DeployConfig | None = None) -> MinimalStack:
    """Build registry/workspace/router with optional deterministic + learned modules."""
    cfg = cfg or default_cpu_only_config()

    prefer = RuntimeId.GPU_CUDA if cfg.runtime.prefer_gpu else RuntimeId.CPU_GENERAL
    sel = select_compute_backend(prefer=prefer)
    device = sel.as_dict()

    if cfg.runtime.enable_neuro_sim:
        import os

        os.environ.setdefault("ORGANISM_NEURO_SIM", "1")

    trace = TraceEmitter()
    reg = RegistryClient(trace=trace)
    ws = WorkspaceClient(
        write_tags=tuple(cfg.stack.workspace_write_tags),
        read_tags=tuple(cfg.stack.workspace_read_tags),
        trace=trace,
    )
    router = Router(
        reg,
        level=cfg.stack.router_level,
        trace=trace,
        plan_id_factory=lambda: "serve-plan",
    )
    if hasattr(trace, "attach_router_state"):
        trace.attach_router_state(router)

    modules: dict[str, Any] = {}
    if cfg.stack.register_deterministic:
        from deterministic_engine.engine import DeterministicEngine

        engine = DeterministicEngine()
        c = engine.declare_contract()
        mid = c.identity.module_id
        reg.register(
            c,
            artifact_digest=c.identity.artifact_digest,
            author_signature=b"deploy",
            module=engine,
            test_bypass_promote="DELIBERATION",
        )
        modules[mid] = engine

    if cfg.stack.register_learned:
        from learned_module.module import LearnedModule

        learned = LearnedModule(precalibrate=True)
        c = learned.declare_contract()
        mid = c.identity.module_id
        reg.register(
            c,
            artifact_digest=c.identity.artifact_digest,
            author_signature=b"deploy",
            module=learned,
            test_bypass_promote="DELIBERATION",
        )
        modules[mid] = learned

    return MinimalStack(
        config=cfg,
        trace=trace,
        registry=reg,
        workspace=ws,
        router=router,
        modules=modules,
        device=device,
    )
