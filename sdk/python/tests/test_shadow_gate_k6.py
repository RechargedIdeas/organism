"""K6 (gaps B1 and H1): promotion needs shadow evidence that meets the threshold; ShadowRunner scores live traffic."""
from __future__ import annotations

import hashlib
from typing import Any

import pytest
from deterministic_engine.engine import DeterministicEngine
from organism_sdk import signing
from organism_sdk.registry import (
    CapabilityFilter,
    LifecycleState,
    RegistryClient,
    ShadowThreshold,
    ShadowValidationRecord,
)
from organism_sdk.shadow_runner import MAX_LOSS, ShadowRunner, p95_nearest_rank
from organism_sdk.signing import TrustStore

DIGEST = hashlib.sha256(b"evidence-1").digest()


def _good(invocations: int = 200) -> ShadowValidationRecord:
    return ShadowValidationRecord(
        invocations=invocations,
        incumbent_error=0.25,
        candidate_error=0.125,
        p95_latency_ms=3.5,
        gates_passed=("sandbox", "contract"),
        evidence_digest=DIGEST,
    )


def _registry_with(initial: LifecycleState, **kwargs: Any) -> tuple[RegistryClient, str]:
    reg = RegistryClient(**kwargs)
    c = DeterministicEngine().declare_contract()
    reg.register(c, artifact_digest=c.identity.artifact_digest, author_signature=b"s", initial_state=initial)
    return reg, c.identity.module_id


def test_gated_promotion_is_refused_without_evidence() -> None:
    reg, mid = _registry_with("SANDBOXED")
    resp = reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", [], b"")
    assert not resp.accepted
    assert resp.validation_issues[0].code == "shadow_evidence_insufficient"
    assert reg.query(CapabilityFilter())[0].state == "SANDBOXED"


def test_ungated_promotion_needs_no_evidence() -> None:
    reg, mid = _registry_with("PROPOSED")
    assert reg.promote(mid, "PROPOSED", "SANDBOXED", [], b"").accepted


def test_evidence_that_meets_the_threshold_passes_each_gated_step() -> None:
    reg, mid = _registry_with("SANDBOXED")
    steps: tuple[tuple[LifecycleState, LifecycleState], ...] = (
        ("SANDBOXED", "SHADOW_VALIDATED"),
        ("SHADOW_VALIDATED", "EXPLORATION"),
        ("EXPLORATION", "DELIBERATION"),
    )
    for frm, to in steps:
        assert reg.promote(mid, frm, to, [_good()], b"").accepted, (frm, to)


def test_bypass_does_not_skip_the_evidence_check() -> None:
    reg, mid = _registry_with("SANDBOXED")
    resp = reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", [], b"", test_bypass_validation=True)
    assert not resp.accepted
    assert resp.validation_issues[0].code == "shadow_evidence_insufficient"


def test_too_few_invocations_are_refused() -> None:
    reg, mid = _registry_with("SANDBOXED")
    resp = reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", [_good(99)], b"")
    assert resp.validation_issues[0].code == "shadow_evidence_insufficient"


def test_candidate_worse_than_incumbent_is_refused() -> None:
    worse = ShadowValidationRecord(invocations=200, incumbent_error=0.125, candidate_error=0.25,
                                   p95_latency_ms=1.0, evidence_digest=DIGEST)
    reg, mid = _registry_with("SANDBOXED")
    resp = reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", [worse], b"")
    assert resp.validation_issues[0].code == "shadow_error_regression"


def test_record_without_digest_is_unattributed() -> None:
    no_digest = ShadowValidationRecord(invocations=200, incumbent_error=0.25, candidate_error=0.125,
                                       p95_latency_ms=1.0, evidence_digest=b"")
    reg, mid = _registry_with("SANDBOXED")
    resp = reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", [no_digest], b"")
    assert resp.validation_issues[0].code == "shadow_evidence_unattributed"


def test_threshold_is_a_parameter() -> None:
    reg, mid = _registry_with("SANDBOXED", shadow_threshold=ShadowThreshold(min_invocations=10))
    assert reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", [_good(10)], b"").accepted


def test_ladder_error_is_reported_before_the_evidence_check() -> None:
    reg, mid = _registry_with("PROPOSED")
    resp = reg.promote(mid, "PROPOSED", "EXPLORATION", [], b"")
    assert resp.validation_issues[0].code == "invalid_promotion"


def test_approver_signature_covers_the_evidence() -> None:
    author, approver = signing.generate_seed(), signing.generate_seed()
    store = TrustStore(authors=frozenset({signing.public_key_for(author)}),
                       approvers=frozenset({signing.public_key_for(approver)}))
    reg = RegistryClient(trust_store=store)
    c = DeterministicEngine().declare_contract()
    mid = c.identity.module_id
    reg.register(c, artifact_digest=c.identity.artifact_digest, author_signature=signing.sign(
        author, signing.registration_payload(mid, c.identity.version, c.identity.artifact_digest)),
        initial_state="SANDBOXED")
    evidence = [_good()]
    sig = signing.sign(approver, signing.promotion_payload(mid, "SANDBOXED", "SHADOW_VALIDATED", evidence))
    assert reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", evidence, sig).accepted

    tampered = [_good(201)]
    resp = reg.promote(mid, "SANDBOXED", "SHADOW_VALIDATED", tampered, sig)
    assert resp.validation_issues[0].code == "signature_invalid"


def test_payload_has_no_float_text_and_binds_the_evidence() -> None:
    base = signing.promotion_payload("m", "SANDBOXED", "SHADOW_VALIDATED", [_good()])
    assert b"." not in base.split(b"\n", 1)[1]  # canonical JSON after the domain line: integers only
    tweaked = ShadowValidationRecord(invocations=200, incumbent_error=0.25, candidate_error=0.126,
                                     p95_latency_ms=3.5, gates_passed=("sandbox", "contract"),
                                     evidence_digest=DIGEST)
    assert base != signing.promotion_payload("m", "SANDBOXED", "SHADOW_VALIDATED", [tweaked])


# ---- ShadowRunner (H1) -------------------------------------------------------------------------------------------


def _runner(rows: list[tuple[int, int, int, int]], ticks: list[int] | None = None) -> ShadowRunner:
    """rows: (incumbent loss, candidate loss, candidate fails, latency ns). The clock is scripted, two reads a row."""
    clock_ticks: list[int] = []
    t = 0
    for *_, lat in rows:
        clock_ticks += [t, t + lat]
        t += lat + 1000
    feed = iter(ticks if ticks is not None else clock_ticks)

    def incumbent(i: int) -> tuple[str, int]:
        return ("inc", i)

    def candidate(i: int) -> tuple[str, int]:
        if rows[i][2]:
            raise RuntimeError("candidate failed")
        return ("cand", i)

    def loss(request: int, output: tuple[str, int]) -> int:
        return rows[request][0] if output[0] == "inc" else rows[request][1]

    return ShadowRunner(incumbent=incumbent, candidate=candidate, loss=loss,
                        clock_ns=lambda: next(feed), gates_passed=("shadow_runner",))


def test_runner_serves_the_incumbent_and_scores_the_candidate() -> None:
    rows = [(400, 200, 0, 2_000_000), (500, 250, 0, 3_000_000), (300, 100, 0, 1_000_000), (600, 300, 0, 4_000_000)]
    runner = _runner(rows)
    outs = [runner.on_traffic(i) for i in range(4)]
    assert outs == [("inc", i) for i in range(4)]
    rec = runner.record()
    assert rec.invocations == 4
    assert rec.incumbent_error == pytest.approx((400 + 500 + 300 + 600) / (MAX_LOSS * 4))
    assert rec.candidate_error == pytest.approx((200 + 250 + 100 + 300) / (MAX_LOSS * 4))
    assert rec.p95_latency_ms == 4.0  # nearest rank over 1, 2, 3, 4 ms
    assert rec.gates_passed == ("shadow_runner",)


def test_candidate_exception_is_scored_as_worst_and_never_raised() -> None:
    rows = [(400, 200, 0, 1_000_000), (500, 0, 1, 1_000_000)]
    runner = _runner(rows)
    assert runner.on_traffic(0) == ("inc", 0)
    assert runner.on_traffic(1) == ("inc", 1)
    rec = runner.record()
    assert rec.candidate_error == pytest.approx((200 + MAX_LOSS) / (MAX_LOSS * 2))


def test_evidence_digest_is_deterministic_and_covers_every_row() -> None:
    rows = [(400, 200, 0, 1_000_000), (500, 250, 0, 2_000_000)]
    a = _runner(rows)
    b = _runner(rows)
    for i in range(2):
        a.on_traffic(i)
        b.on_traffic(i)
    assert a.record().evidence_digest == b.record().evidence_digest
    other = _runner([(400, 200, 0, 1_000_000), (500, 251, 0, 2_000_000)])
    other.on_traffic(0)
    other.on_traffic(1)
    assert other.record().evidence_digest != a.record().evidence_digest


def test_out_of_range_loss_is_refused() -> None:
    runner = ShadowRunner(incumbent=lambda r: r, candidate=lambda r: r, loss=lambda r, o: MAX_LOSS + 1,
                          clock_ns=lambda: 0)
    with pytest.raises(ValueError):
        runner.on_traffic("x")


def test_empty_runner_gives_zero_evidence() -> None:
    rec = ShadowRunner(incumbent=lambda r: r, candidate=lambda r: r, loss=lambda r, o: 0).record()
    assert (rec.invocations, rec.incumbent_error, rec.candidate_error, rec.p95_latency_ms) == (0, 0.0, 0.0, 0.0)


def test_p95_uses_nearest_rank() -> None:
    assert p95_nearest_rank(list(range(1, 21))) == 19
    assert p95_nearest_rank([]) == 0
