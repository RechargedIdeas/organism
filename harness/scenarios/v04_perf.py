"""v0.4-M2 — Perf measurement helpers + budget constants."""
from __future__ import annotations

import time
from dataclasses import dataclass

from deterministic_engine.engine import DeterministicEngine
from organism_sdk.degradation import DegradationMachine, HealthSignals, T_DOWN_FAST
from organism_sdk.hormone import HormoneBus
from organism_sdk.hypervector import Hypervector
from organism_sdk.registry import RegistryClient
from organism_sdk.router import Router, RouterTask
from organism_sdk.workspace import WorkspaceClient

# Budgets (ms) — see docs/v0.4/PERF.md
ROUTER_P50_MS = 2.0
ROUTER_P95_MS = 5.0
WS_BIND_P95_MS = 5.0
WS_QUERY_P95_MS = 1.0
WS_UNBIND_P95_MS = 2.0
HORMONE_P95_MS = 5.0
DEGRADE_P95_MS = 2.0


@dataclass
class Percentiles:
    p50: float
    p95: float
    n: int


def _pct(samples: list[float]) -> Percentiles:
    s = sorted(samples)
    n = len(s)
    if n == 0:
        return Percentiles(0.0, 0.0, 0)
    return Percentiles(p50=s[n // 2], p95=s[max(0, int(n * 0.95) - 1)], n=n)


def measure_router(n: int = 200, warmup: int = 20) -> Percentiles:
    reg = RegistryClient()
    eng = DeterministicEngine()
    c = eng.declare_contract()
    reg.register(
        c,
        artifact_digest=c.identity.artifact_digest,
        author_signature=b"s",
        module=eng,
        test_bypass_promote="DELIBERATION",
    )
    router = Router(reg, level="L0", plan_id_factory=lambda: "perf")
    for i in range(warmup):
        router.decide(RouterTask(task_id=f"w{i}", form="control_actuation", safety_tier="high"))
    samples: list[float] = []
    for i in range(n):
        t0 = time.perf_counter()
        router.decide(RouterTask(task_id=f"t{i}", form="control_actuation", safety_tier="high"))
        samples.append((time.perf_counter() - t0) * 1000.0)
    return _pct(samples)


def measure_workspace(n: int = 200) -> dict[str, Percentiles]:
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    role = Hypervector.random(seed=0x5753)
    binds: list[float] = []
    queries: list[float] = []
    unbinds: list[float] = []
    ids = []
    for i in range(n):
        filler = Hypervector.random(seed=0x10000 + i)
        t0 = time.perf_counter()
        rec = ws.bind_exact(role, filler, tags=("perf",), module_id="perf")
        binds.append((time.perf_counter() - t0) * 1000.0)
        ids.append(rec.binding_id)
    for bid in ids:
        t0 = time.perf_counter()
        ws.read_by_binding_id(bid)
        queries.append((time.perf_counter() - t0) * 1000.0)
    for bid in ids:
        t0 = time.perf_counter()
        ws.unbind(bid)
        unbinds.append((time.perf_counter() - t0) * 1000.0)
    return {"bind": _pct(binds), "query": _pct(queries), "unbind": _pct(unbinds)}


def measure_hormone(n: int = 100) -> Percentiles:
    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",))
    bus = HormoneBus(ws)
    samples: list[float] = []
    for _ in range(n):
        levels = bus.compute_release(stress_load=0.2, viability_score=0.9, dt_s=1.0)
        t0 = time.perf_counter()
        bus.write_telemetry_window(levels)
        samples.append((time.perf_counter() - t0) * 1000.0)
    return _pct(samples)


def measure_degradation_confirm(n: int = 50) -> Percentiles:
    samples: list[float] = []
    for _ in range(n):
        deg = DegradationMachine(
            signals=HealthSignals(
                h_m={"learned_module_t2": "DEGRADED"},
                c_m={"learned_module_t2": 0.5},
                neural_modules=("learned_module_t2",),
                leading_predictive=("learned_module_t2",),
                thermal=0.1,
            ),
            t_down=dict(T_DOWN_FAST),
        )
        t0 = time.perf_counter()
        deg.tick()
        deg.advance(T_DOWN_FAST["L1"])
        samples.append((time.perf_counter() - t0) * 1000.0)
        assert deg.level == "L1"
    return _pct(samples)
