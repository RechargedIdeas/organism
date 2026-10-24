"""Degradation state machine — Artifact B + A0 (M6).

Default path uses a virtual clock (`advance` / `now_s`) so hysteresis SLOs
are testable without wall-clock waits. Wall-clock physiology is exercised
by driving `sync_wall_clock()` / `tick()` against `time.monotonic()` with
optional scaled `t_down`/`t_up` overrides (see harness + perf:slo).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from organism_sdk.trace import DegradationTraceEntry, TraceEmitter

Level = Literal["L0", "L1", "L2", "L3", "L4"]

# B.4 hysteresis defaults (seconds)
T_DOWN = {"L1": 5.0, "L2": 30.0, "L3": 60.0, "L4": 10.0}
T_UP = {"L1": 120.0, "L2": 300.0, "L3": 600.0, "L4": 900.0}

# CI-scaled hysteresis: same physiology, T_up ≥ 5·T_down, finishes in ~10s wall.
T_DOWN_FAST = {"L1": 0.4, "L2": 0.6, "L3": 0.8, "L4": 0.4}
T_UP_FAST = {"L1": 2.0, "L2": 3.0, "L3": 4.0, "L4": 5.0}

ALPHA = 0.10
DELTA_1 = 0.05
DELTA_2 = 0.15
THERMAL_L1 = 0.20
THERMAL_L0 = 0.50
GC_L3 = 0.50
GC_L4 = 0.85
MEM_L4 = 0.90
Q_P95_L3 = 50.0
Q_P95_L4 = 250.0
BYZ_COUNT_L4 = 3


@dataclass
class HealthSignals:
    h_m: dict[str, str] = field(default_factory=dict)  # module -> HEALTHY|DEGRADED|FAILED
    c_m: dict[str, float] = field(default_factory=dict)
    thermal: float = 1.0
    power: float = 1.0
    mem: float = 0.0
    q_p95: float = 1.0
    gc: float = 0.0
    byz: bool = False
    byz_count: int = 0
    trace_ok: bool = True
    det_ok: bool = True
    causal_ok: bool = True
    neural_modules: tuple[str, ...] = ("learned_module_t2",)
    leading_predictive: tuple[str, ...] = ("learned_module_t2",)


@dataclass
class DegradationMachine:
    level: Level = "L0"
    signals: HealthSignals = field(default_factory=HealthSignals)
    now_s: float = 0.0
    last_transition_at: float = 0.0
    human_ack: bool = False
    transitions: list[tuple[str, str, str]] = field(default_factory=list)  # from,to,trigger
    trace: TraceEmitter = field(default_factory=TraceEmitter)
    _cond_since: dict[str, float | None] = field(default_factory=dict)
    t_down: dict[str, float] = field(default_factory=lambda: dict(T_DOWN))
    t_up: dict[str, float] = field(default_factory=lambda: dict(T_UP))
    _wall_origin: float | None = None

    def advance(self, dt: float) -> None:
        self.now_s += dt
        self.tick()

    def sync_wall_clock(self, monotonic_now: float) -> None:
        """Drive `now_s` from wall-clock monotonic time (perf:slo / Category I)."""
        if self._wall_origin is None:
            self._wall_origin = monotonic_now
            self.now_s = 0.0
        else:
            self.now_s = monotonic_now - self._wall_origin
        self.tick()

    def _confirmed(self, key: str, holding: bool, window: float) -> bool:
        if not holding:
            self._cond_since[key] = None
            return False
        since = self._cond_since.get(key)
        if since is None:
            self._cond_since[key] = self.now_s
            return window <= 0.0
        return (self.now_s - since) >= window

    def _sustained(self, key: str, holding: bool, window: float) -> bool:
        return self._confirmed(f"up:{key}", holding, window)

    def _any_confirmed(self, specs: list[tuple[str, bool, float]]) -> bool:
        """Evaluate all specs (arms timers) then OR — avoids short-circuit arming loss."""
        results = [self._confirmed(k, h, w) for k, h, w in specs]
        return any(results)

    def _all_sustained(self, specs: list[tuple[str, bool, float]]) -> bool:
        """Evaluate all specs (arms timers) then AND."""
        results = [self._sustained(k, h, w) for k, h, w in specs]
        return all(results)

    def tick(self) -> Level | None:
        """Evaluate transitions once. Returns new level if transitioned."""
        s = self.signals
        L = self.level
        prev = L
        td = self.t_down
        tu = self.t_up

        def neural_degraded() -> bool:
            return any(s.h_m.get(m) == "DEGRADED" for m in s.neural_modules)

        def neural_failed() -> bool:
            return any(s.h_m.get(m) == "FAILED" for m in s.leading_predictive)

        def neural_healthy() -> bool:
            return all(s.h_m.get(m, "HEALTHY") == "HEALTHY" for m in s.neural_modules)

        def neural_calib_ok(delta: float = 0.0) -> bool:
            return all(s.c_m.get(m, 1.0) >= 1.0 - ALPHA + delta for m in s.neural_modules)

        def neural_calib_bad(delta: float) -> bool:
            # A0.1: c_m < 1 − α − δ_k (sign correction)
            return all(s.c_m.get(m, 1.0) < 1.0 - ALPHA - delta for m in s.neural_modules)

        new: Level | None = None
        trigger = ""

        if L == "L0":
            down = self._any_confirmed([
                ("l0_thermal", s.thermal < THERMAL_L1, td["L1"]),
                ("l0_calib", neural_calib_bad(DELTA_1) and bool(s.neural_modules), td["L1"]),
                ("l0_hm", neural_degraded(), td["L1"]),
            ])
            if s.det_ok and s.trace_ok and down:
                new, trigger = "L1", "module_degraded_or_thermal"

        elif L == "L1":
            down = self._any_confirmed([
                ("l1_failed", neural_failed(), td["L2"]),
                ("l1_calib2", neural_calib_bad(DELTA_2), td["L2"]),
                ("l1_causal", not s.causal_ok, td["L2"]),
            ])
            up = self._all_sustained([
                ("l1_thermal", s.thermal > THERMAL_L0, tu["L1"]),
                ("l1_calib", neural_calib_ok(0.0), tu["L1"]),
                ("l1_hm", neural_healthy(), tu["L1"]),
            ])
            if s.det_ok and s.trace_ok and down:
                new, trigger = "L2", "module_failed"
            elif up:
                new, trigger = "L0", "recovery"

        elif L == "L2":
            down = self._confirmed(
                "l2_gc",
                (s.gc > GC_L3 or s.q_p95 > Q_P95_L3)
                or all(
                    s.h_m.get(m) == "FAILED" or s.c_m.get(m, 1.0) < 1.0 - ALPHA - DELTA_2
                    for m in s.leading_predictive
                ),
                td["L3"],
            )
            up = self._all_sustained([
                ("l2_calib", any(s.c_m.get(m, 0) >= 1 - ALPHA for m in s.neural_modules), tu["L2"]),
                ("l2_hm", neural_healthy(), tu["L2"]),
                ("l2_causal", s.causal_ok, tu["L2"]),
            ])
            if s.det_ok and s.trace_ok and down:
                new, trigger = "L3", "workspace_pressure"
            elif up:
                new, trigger = "L1", "recovery"

        elif L == "L3":
            down = self._any_confirmed([
                ("l3_trace", not s.trace_ok, td["L4"]),
                ("l3_det", not s.det_ok, td["L4"]),
                ("l3_gc", s.gc > GC_L4 or s.mem > MEM_L4, td["L4"]),
                ("l3_qp", s.q_p95 > Q_P95_L4, td["L4"]),
                ("l3_byz", s.byz_count >= BYZ_COUNT_L4, td["L4"]),
            ])
            up = self._all_sustained([
                ("l3_ok", s.trace_ok and s.det_ok, tu["L3"]),
                ("l3_gc", s.gc < GC_L3 and s.q_p95 < Q_P95_L3, tu["L3"]),
                ("l3_byz", not s.byz, tu["L3"]),
            ])
            if down:
                new, trigger = "L4", "trace_or_byzantine"
            elif up:
                new, trigger = "L2", "recovery"

        elif L == "L4":
            up = self._all_sustained([
                ("l4_ok", s.trace_ok and s.det_ok, tu["L4"]),
                ("l4_gc", s.gc < GC_L3 and s.mem < MEM_L4, tu["L4"]),
                ("l4_qp", s.q_p95 < Q_P95_L3, tu["L4"]),
                ("l4_byz", not s.byz, tu["L4"]),
            ]) and self.human_ack
            if up:
                new, trigger = "L3", "human_ack_recovery"
                self.human_ack = False

        if new and new != prev:
            self.transitions.append((prev, new, trigger))
            self.trace.emit_degradation(
                DegradationTraceEntry(
                    from_level=prev,
                    to_level=new,
                    trigger_kind=trigger,
                    diagnosis_code=trigger,
                )
            )
            self.level = new
            self.last_transition_at = self.now_s
            # Clear condition timers on transition (A0 sequencing)
            self._cond_since.clear()
            return new
        return None


class FaultInjector:
    """Minimal harness injector (Artifact F subset for M6/M7)."""

    def __init__(self, machine: DegradationMachine) -> None:
        self.machine = machine

    def kill_module(self, module_id: str) -> None:
        self.machine.signals.h_m[module_id] = "DEGRADED"

    def fail_module(self, module_id: str) -> None:
        self.machine.signals.h_m[module_id] = "FAILED"

    def restore_module(self, module_id: str) -> None:
        self.machine.signals.h_m[module_id] = "HEALTHY"
        self.machine.signals.c_m[module_id] = 1.0 - ALPHA + 0.05

    def corrupt_trace_sink(self) -> None:
        self.machine.signals.trace_ok = False

    def restore_trace_sink(self) -> None:
        self.machine.signals.trace_ok = True

    def byzantine_strike(self) -> None:
        self.machine.signals.byz_count += 1
        if self.machine.signals.byz_count >= BYZ_COUNT_L4:
            self.machine.signals.byz = True
