"""Shadow runner on live traffic (K6, gap H1).

``moa/shadow.py`` scores a candidate on a labelled set. This module scores it on the requests the system actually
serves. The incumbent answers every request, and the candidate runs on the same request with its output scored and
never returned. The result is a ``ShadowValidationRecord``, which is the evidence the registry's promotion gate reads.

Losses are integers in thousandths (0 to 1000), so the record and its evidence digest hold no float text and the
Kotlin port (``ShadowRunner.kt``) reproduces them exactly. Vectors: ``conformance/vectors/shadow.json``.
"""
from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from organism_sdk.canonical import canonical_bytes
from organism_sdk.registry import ShadowValidationRecord

MAX_LOSS = 1000  # a loss is an integer in 0..MAX_LOSS (thousandths of the full error)


def _checked_loss(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_LOSS:
        raise ValueError(f"loss must be an integer in 0..{MAX_LOSS}, got {value!r}")
    return value


def p95_nearest_rank(values_us: list[int]) -> int:
    """The 95th percentile by the nearest-rank method: the value at rank ceil(0.95 n), in integer arithmetic."""
    if not values_us:
        return 0
    ordered = sorted(values_us)
    rank = (95 * len(ordered) + 99) // 100
    return ordered[rank - 1]


@dataclass
class ShadowRunner:
    """Serves live traffic with ``incumbent`` and scores ``candidate`` on the same requests.

    ``loss(request, output)`` gives the integer loss of one output for one request (0 is perfect, 1000 is the worst).
    ``clock_ns`` is read twice per request, around the candidate call. Tests and vectors inject it.
    """

    incumbent: Callable[[Any], Any]
    candidate: Callable[[Any], Any]
    loss: Callable[[Any, Any], int]
    clock_ns: Callable[[], int] = time.perf_counter_ns
    gates_passed: tuple[str, ...] = ()
    _rows: list[tuple[int, int, int, int]] = field(default_factory=list, init=False, repr=False)

    def on_traffic(self, request: Any) -> Any:
        """The live traffic callback. Returns the incumbent's output, the only one a caller sees.

        A candidate that raises is scored with the worst loss and counted as a failure. Its exception does not reach
        the caller, and an incumbent error still does, because the incumbent is what is being served.
        """
        served = self.incumbent(request)
        incumbent_loss = _checked_loss(self.loss(request, served))
        started = self.clock_ns()
        failed = 0
        try:
            candidate_out = self.candidate(request)
            candidate_loss = _checked_loss(self.loss(request, candidate_out))
        except Exception:  # noqa: BLE001 - a shadow failure is evidence, never a serving error
            failed = 1
            candidate_loss = MAX_LOSS
        latency_us = max(0, (self.clock_ns() - started) // 1000)
        self._rows.append((incumbent_loss, candidate_loss, failed, latency_us))
        return served

    @property
    def invocations(self) -> int:
        return len(self._rows)

    def record(self) -> ShadowValidationRecord:
        """The evidence so far. Errors are the mean loss as a fraction of MAX_LOSS. The digest covers every row."""
        n = len(self._rows)
        if n == 0:
            incumbent_error = candidate_error = p95_ms = 0.0
        else:
            incumbent_error = sum(r[0] for r in self._rows) / (MAX_LOSS * n)
            candidate_error = sum(r[1] for r in self._rows) / (MAX_LOSS * n)
            p95_ms = p95_nearest_rank([r[3] for r in self._rows]) / 1000
        digest = hashlib.sha256(
            canonical_bytes({"version": 1, "rows": [list(r) for r in self._rows]})
        ).digest()
        return ShadowValidationRecord(
            invocations=n,
            incumbent_error=incumbent_error,
            candidate_error=candidate_error,
            p95_latency_ms=p95_ms,
            gates_passed=tuple(self.gates_passed),
            evidence_digest=digest,
        )
