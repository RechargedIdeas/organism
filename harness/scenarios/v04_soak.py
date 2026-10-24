"""v0.4-M1 — Multi-window soak / stability harness (virtual clock)."""
from __future__ import annotations

from dataclasses import dataclass, field

from deterministic_engine.engine import DeterministicEngine
from learned_module.module import LearnedModule
from organism_sdk.degradation import DegradationMachine, FaultInjector, HealthSignals, T_DOWN_FAST, T_UP_FAST
from organism_sdk.hormone import HormoneBus
from organism_sdk.hypervector import Hypervector
from organism_sdk.registry import RegistryClient
from organism_sdk.router import Router, RouterTask
from organism_sdk.trace import DegradationTraceEntry, RoutingTraceEntry, TraceEmitter
from organism_sdk.workspace import WorkspaceClient


@dataclass
class SoakResult:
    windows: int
    simulated_s: float
    levels_seen: list[str] = field(default_factory=list)
    transitions: list[tuple[str, str, str]] = field(default_factory=list)
    binding_count_peak: int = 0
    binding_count_final: int = 0
    plans: int = 0
    hormone_windows: int = 0
    routing_trace_count: int = 0
    degradation_trace_count: int = 0
    flapping: bool = False


def run_soak(
    *,
    windows: int = 24,
    dt_s: float = 1.0,
    max_bindings: int = 64,
    stress_every: int = 8,
) -> SoakResult:
    """Register modules, route, publish hormone windows, degrade, GC.

    Uses virtual clock on DegradationMachine. Assert-friendly result.
    """
    trace = TraceEmitter()
    reg = RegistryClient(trace=trace)
    engine = DeterministicEngine()
    learned = LearnedModule(precalibrate=True)
    for mod in (engine, learned):
        c = mod.declare_contract()
        reg.register(
            c,
            artifact_digest=c.identity.artifact_digest,
            author_signature=b"s",
            module=mod,
            test_bypass_promote="DELIBERATION",
        )

    ws = WorkspaceClient(write_tags=("*",), read_tags=("*",), trace=trace)
    bus = HormoneBus(ws, trace=trace)
    router = Router(reg, level="L0", trace=trace, plan_id_factory=lambda: "soak-plan")
    trace.attach_router_state(router)

    deg = DegradationMachine(
        signals=HealthSignals(
            h_m={"learned_module_t2": "HEALTHY", "deterministic_engine": "HEALTHY"},
            c_m={"learned_module_t2": 0.96, "deterministic_engine": 1.0},
            neural_modules=("learned_module_t2",),
            leading_predictive=("learned_module_t2",),
            thermal=0.9,
        ),
        t_down=dict(T_DOWN_FAST),
        t_up=dict(T_UP_FAST),
        trace=trace,
    )
    inj = FaultInjector(deg)

    result = SoakResult(windows=windows, simulated_s=0.0)
    peak = 0
    role = Hypervector.random(seed=0x50455246)  # 'PERF'

    for i in range(windows):
        # Route alternating forms
        form = "pattern_recognition" if i % 2 == 0 else "control_actuation"
        tier = "medium" if form == "pattern_recognition" else "high"
        plan = router.decide(RouterTask(task_id=f"soak-{i}", form=form, safety_tier=tier))
        assert plan.disposition in ("DISPATCH", "HOLD", "REJECT")
        result.plans += 1

        # Ephemeral workspace pressure
        filler = Hypervector.random(seed=0x1000 + i)
        ws.bind_exact(role, filler, tags=("soak_ephemeral",), module_id="soak")
        peak = max(peak, ws.binding_count)

        # Hormone telemetry window
        stress = 0.7 if (i % stress_every == 0 and i > 0) else 0.1
        levels = bus.compute_release(
            stress_load=stress,
            viability_score=0.9,
            mean_recent_reward=0.2,
            adapter_acceptance_rate=0.5,
            circadian_phase=0.2,
            dt_s=dt_s,
        )
        bus.write_telemetry_window(levels)
        result.hormone_windows += 1
        assert ws.read_by_tag(["hormone_state"]), "hormone_state must remain queryable"

        # Degradation pulse mid-soak then recover (no flapping)
        if i == windows // 3:
            inj.kill_module("learned_module_t2")
            deg.signals.thermal = 0.1
        if i == windows // 3 + 1:
            deg.tick()
            deg.advance(T_DOWN_FAST["L1"])
        if i == (2 * windows) // 3:
            inj.restore_module("learned_module_t2")
            deg.signals.thermal = 0.9
            deg.tick()
            deg.advance(T_UP_FAST["L1"])

        router.set_level(deg.level)
        result.levels_seen.append(deg.level)
        result.simulated_s += dt_s

        # GC under pressure
        ws.gc_ephemeral(max_bindings=max_bindings)
        peak = max(peak, ws.binding_count)

    result.binding_count_peak = peak
    result.binding_count_final = ws.binding_count
    result.transitions = list(deg.transitions)
    result.routing_trace_count = sum(1 for e in trace.entries if isinstance(e, RoutingTraceEntry))
    result.degradation_trace_count = sum(
        1 for e in trace.entries if isinstance(e, DegradationTraceEntry)
    )

    # Flapping: same from→to oscillating more than twice without holding
    downs = [t for t in deg.transitions if t[0] < t[1] or (t[0].startswith("L") and t[1].startswith("L"))]
    # Detect L0↔L1 flip-flops > 2 cycles in short soak
    pairs = [(a, b) for a, b, _ in deg.transitions]
    flap = 0
    for j in range(1, len(pairs)):
        if pairs[j] == (pairs[j - 1][1], pairs[j - 1][0]):
            flap += 1
    result.flapping = flap > 2

    # Traces reconstructible: every plan has a routing entry
    assert result.routing_trace_count >= result.plans
    # Workspace still queryable
    assert ws.binding_count >= 1
    assert ws.read_by_tag(["hormone_state"])
    # Bound memory proxy
    assert result.binding_count_final <= max_bindings + 8  # protect control bindings slack
    assert not result.flapping
    return result


def run_soak_extended(*, windows: int = 240) -> SoakResult:
    """Longer simulated soak (opt-in slow)."""
    return run_soak(windows=windows, dt_s=1.0, max_bindings=96, stress_every=12)
