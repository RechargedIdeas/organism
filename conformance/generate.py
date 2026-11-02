"""Generate language-neutral conformance vectors from the Python reference SDK.

Every SDK (Kotlin, Rust, ...) must reproduce these byte for byte. Run:
    PYTHONPATH=sdk/python:modules:. python conformance/generate.py
Vectors are checked in; regenerate only with a reviewed reference change (see docs/INTEROP.md).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from organism_sdk.degradation import DegradationMachine, HealthSignals
from organism_sdk.hypervector import DIM, WORD_COUNT, Hypervector

OUT = Path(__file__).parent / "vectors"
SCHEMA = 1


def hx(hv: Hypervector) -> list[str]:
    return [f"{w:016x}" for w in hv.words]


def hv_from(h: list[str]) -> Hypervector:
    return Hypervector(tuple(int(x, 16) for x in h))


def hypervector_vectors() -> dict:
    rng = random.Random(1010)
    hvs = [Hypervector.random(rng=rng) for _ in range(6)]
    cases = []
    cases.append({"op": "bind", "a": hx(hvs[0]), "b": hx(hvs[1]), "out": hx(hvs[0].bind(hvs[1]))})
    for k in (0, 1, 63, 64, 65, 9999, 10000, 12345, 1_000_003):
        cases.append({"op": "permute", "a": hx(hvs[2]), "k": k, "out": hx(hvs[2].permute(k))})
    for i, j in ((0, 1), (2, 2), (3, 4)):
        cases.append({"op": "similarity", "a": hx(hvs[i]), "b": hx(hvs[j]), "out": hvs[i].similarity(hvs[j])})
    for n in (1, 2, 3, 4, 5, 6):
        sel = hvs[:n]
        cases.append({"op": "bundle", "in": [hx(h) for h in sel], "out": hx(Hypervector.bundle(sel))})
    cases.append({"op": "bundle", "in": [], "out": hx(Hypervector.bundle([]))})
    return {"schema": SCHEMA, "dim": DIM, "word_count": WORD_COUNT, "cases": cases}


NEURAL = ["learned_module_t2"]


def sig_dict(**kw) -> dict:
    d = {"h_m": {}, "c_m": {}, "thermal": 1.0, "power": 1.0, "mem": 0.0, "q_p95": 1.0, "gc": 0.0,
         "byz": False, "byz_count": 0, "trace_ok": True, "det_ok": True, "causal_ok": True,
         "neural_modules": NEURAL, "leading_predictive": NEURAL}
    d.update(kw)
    return d


def to_signals(d: dict) -> HealthSignals:
    return HealthSignals(h_m=dict(d["h_m"]), c_m=dict(d["c_m"]), thermal=d["thermal"], power=d["power"],
                         mem=d["mem"], q_p95=d["q_p95"], gc=d["gc"], byz=d["byz"], byz_count=d["byz_count"],
                         trace_ok=d["trace_ok"], det_ok=d["det_ok"], causal_ok=d["causal_ok"],
                         neural_modules=tuple(d["neural_modules"]), leading_predictive=tuple(d["leading_predictive"]))


def run_scenario(steps: list[dict]) -> dict:
    m = DegradationMachine()
    levels = []
    for st in steps:
        m.signals = to_signals(st["signals"])
        m.human_ack = bool(st.get("human_ack", False))
        m.advance(float(st["dt"]))
        levels.append(m.level)
    return {"steps": steps, "levels": levels, "transitions": [list(t) for t in m.transitions],
            "final_human_ack": m.human_ack}


def degradation_vectors() -> dict:
    sc = []
    # thermal drop -> L1 -> recover
    st = [{"dt": 1.0, "signals": sig_dict(thermal=0.1)} for _ in range(8)]
    st += [{"dt": 10.0, "signals": sig_dict(thermal=0.9)} for _ in range(15)]
    sc.append({"name": "thermal_down_up", **run_scenario(st)})
    # full descent and human-ack recovery
    st = []
    st += [{"dt": 2.0, "signals": sig_dict(h_m={NEURAL[0]: "DEGRADED"})} for _ in range(4)]
    st += [{"dt": 10.0, "signals": sig_dict(h_m={NEURAL[0]: "FAILED"})} for _ in range(5)]
    st += [{"dt": 20.0, "signals": sig_dict(h_m={NEURAL[0]: "FAILED"}, gc=0.6)} for _ in range(5)]
    st += [{"dt": 5.0, "signals": sig_dict(trace_ok=False)} for _ in range(5)]
    st += [{"dt": 100.0, "signals": sig_dict(), "human_ack": True} for _ in range(30)]
    sc.append({"name": "descent_and_ack_recovery", **run_scenario(st)})
    # randomized stress, seeded
    rng = random.Random(77)
    for n in range(24):
        steps = []
        for _ in range(60):
            kw = {}
            if rng.random() < 0.3: kw["thermal"] = rng.choice([0.05, 0.15, 0.3, 0.6, 1.0])
            if rng.random() < 0.3: kw["h_m"] = {NEURAL[0]: rng.choice(["HEALTHY", "DEGRADED", "FAILED"])}
            if rng.random() < 0.3: kw["c_m"] = {NEURAL[0]: rng.choice([0.5, 0.75, 0.84, 0.92, 1.0])}
            if rng.random() < 0.2: kw["gc"] = rng.choice([0.0, 0.4, 0.6, 0.9])
            if rng.random() < 0.15: kw["q_p95"] = rng.choice([1.0, 60.0, 300.0])
            if rng.random() < 0.15: kw["mem"] = rng.choice([0.1, 0.95])
            if rng.random() < 0.1: kw["trace_ok"] = rng.random() < 0.5
            if rng.random() < 0.1: kw["det_ok"] = rng.random() < 0.5
            if rng.random() < 0.1: kw["causal_ok"] = rng.random() < 0.5
            if rng.random() < 0.1:
                kw["byz"] = True
                kw["byz_count"] = rng.choice([1, 3, 4])
            steps.append({"dt": rng.choice([0.5, 1.0, 5.0, 20.0, 70.0, 200.0]), "signals": sig_dict(**kw),
                          "human_ack": rng.random() < 0.2})
        sc.append({"name": f"random_{n}", **run_scenario(steps)})
    return {"schema": SCHEMA, "scenarios": sc}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in (("hypervector", hypervector_vectors()), ("degradation", degradation_vectors())):
        (OUT / f"{name}.json").write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        print("wrote", name)
    d = json.loads((OUT / "degradation.json").read_text())
    seen = {t[1] for s in d["scenarios"] for t in s["transitions"]}
    print("levels reached:", sorted(seen))


if __name__ == "__main__":
    main()
