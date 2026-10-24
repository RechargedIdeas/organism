"""v0.4-M2 perf budget gates."""
from __future__ import annotations

from harness.scenarios.v04_perf import (
    DEGRADE_P95_MS,
    HORMONE_P95_MS,
    ROUTER_P50_MS,
    ROUTER_P95_MS,
    WS_BIND_P95_MS,
    WS_QUERY_P95_MS,
    WS_UNBIND_P95_MS,
    measure_degradation_confirm,
    measure_hormone,
    measure_router,
    measure_workspace,
)


def test_perf_router_budgets():
    p = measure_router()
    assert p.p50 <= ROUTER_P50_MS, f"router p50 {p.p50} > {ROUTER_P50_MS}"
    assert p.p95 <= ROUTER_P95_MS, f"router p95 {p.p95} > {ROUTER_P95_MS}"


def test_perf_workspace_budgets():
    m = measure_workspace()
    assert m["bind"].p95 <= WS_BIND_P95_MS
    assert m["query"].p95 <= WS_QUERY_P95_MS
    assert m["unbind"].p95 <= WS_UNBIND_P95_MS


def test_perf_hormone_publish_budget():
    p = measure_hormone()
    assert p.p95 <= HORMONE_P95_MS, f"hormone p95 {p.p95} > {HORMONE_P95_MS}"


def test_perf_degradation_confirm_budget():
    p = measure_degradation_confirm()
    assert p.p95 <= DEGRADE_P95_MS, f"degrade p95 {p.p95} > {DEGRADE_P95_MS}"
