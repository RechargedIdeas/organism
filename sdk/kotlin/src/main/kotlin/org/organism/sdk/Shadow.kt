package org.organism.sdk

import java.security.MessageDigest

/*
 * Shadow evidence and the promotion gate (K6, gaps B1 and H1). Port of `registry.py` (`shadow_gate`, `ShadowThreshold`,
 * `GATED_STATES`) and `shadow_runner.py` (`ShadowRunner`). The runner scores a candidate on live traffic: the incumbent
 * answers, and the candidate's output is scored and never returned. Losses are integers in 0..1000, so the evidence and
 * its digest hold no float text. Vectors: shadow.json, and the evidence cases in lifecycle.json.
 */

/** Evidence from shadow runs (reference `ShadowValidationRecord`). Errors are fractions in 0..1. */
data class ShadowValidationRecord(
    val invocations: Int,
    val incumbentError: Double,
    val candidateError: Double,
    val p95LatencyMs: Double,
    val gatesPassed: List<String> = emptyList(),
    val evidenceDigest: ByteArray = ByteArray(0),
)

/** What shadow evidence must show before a gated promotion (reference `ShadowThreshold`). */
data class ShadowThreshold(val minInvocations: Int = 100, val maxErrorRatio: Double = 1.0)

/** States a module may enter only with evidence over the threshold (reference `GATED_STATES`, gap B1). */
val GATED_STATES: Set<LifecycleState> = setOf(
    LifecycleState.SHADOW_VALIDATED,
    LifecycleState.EXPLORATION,
    LifecycleState.DELIBERATION,
)

/**
 * The issues that stop a gated promotion, or an empty list when the evidence passes. Pure. Codes:
 * `shadow_evidence_insufficient`, `shadow_evidence_unattributed`, `shadow_error_regression`.
 */
fun shadowGate(records: List<ShadowValidationRecord>, threshold: ShadowThreshold): List<ValidationIssue> {
    fun issue(code: String, message: String) =
        listOf(ValidationIssue(Severity.ERROR, code, "shadow_records", message))
    if (records.isEmpty()) return issue("shadow_evidence_insufficient", "no shadow records")
    val total = records.sumOf { it.invocations }
    if (total < threshold.minInvocations) {
        return issue("shadow_evidence_insufficient", "invocations=$total required=${threshold.minInvocations}")
    }
    if (records.any { it.evidenceDigest.isEmpty() }) {
        return issue("shadow_evidence_unattributed", "a record has no evidence digest")
    }
    // Explicit loops in the reference's order: the same floating-point additions in both SDKs.
    var incumbent = 0.0
    var candidate = 0.0
    for (r in records) {
        incumbent += r.incumbentError * r.invocations
        candidate += r.candidateError * r.invocations
    }
    if (candidate > threshold.maxErrorRatio * incumbent) {
        return issue("shadow_error_regression", "candidate error exceeds the incumbent")
    }
    return emptyList()
}

/**
 * Serves live traffic with [incumbent] and scores [candidate] on the same requests (reference `ShadowRunner`).
 * [loss] gives an integer in 0..[MAX_LOSS] for one output and request. [clockNs] is read twice per request, around the
 * candidate call. A candidate that throws is scored as the worst loss and its exception does not reach the caller.
 */
class ShadowRunner<Req, Out>(
    private val incumbent: (Req) -> Out,
    private val candidate: (Req) -> Out,
    private val loss: (Req, Out) -> Int,
    private val clockNs: () -> Long = System::nanoTime,
    private val gatesPassed: List<String> = emptyList(),
) {
    /** One row per request: incumbent loss, candidate loss, candidate failed (0 or 1), candidate latency in microseconds. */
    private val rows = ArrayList<LongArray>()

    /** The live traffic callback. Returns the incumbent's output, the only one a caller sees. */
    fun onTraffic(request: Req): Out {
        val served = incumbent(request)
        val incumbentLoss = checkedLoss(loss(request, served))
        val started = clockNs()
        var failed = 0L
        var candidateLoss: Long
        try {
            candidateLoss = checkedLoss(loss(request, candidate(request))).toLong()
        } catch (e: Exception) {
            failed = 1L
            candidateLoss = MAX_LOSS.toLong()
        }
        val latencyUs = maxOf(0L, (clockNs() - started) / 1000L)
        rows += longArrayOf(incumbentLoss.toLong(), candidateLoss, failed, latencyUs)
        return served
    }

    /** The evidence so far. Errors are the mean loss as a fraction of [MAX_LOSS]; the digest covers every row. */
    fun record(): ShadowValidationRecord {
        val n = rows.size
        if (n == 0) return ShadowValidationRecord(0, 0.0, 0.0, 0.0, gatesPassed, digest())
        val incumbentSum = rows.sumOf { it[0] }
        val candidateSum = rows.sumOf { it[1] }
        val p95Us = p95NearestRank(rows.map { it[3] })
        return ShadowValidationRecord(
            invocations = n,
            incumbentError = incumbentSum.toDouble() / (MAX_LOSS.toDouble() * n),
            candidateError = candidateSum.toDouble() / (MAX_LOSS.toDouble() * n),
            p95LatencyMs = p95Us.toDouble() / 1000.0,
            gatesPassed = gatesPassed,
            evidenceDigest = digest(),
        )
    }

    private fun digest(): ByteArray {
        val body = mapOf("version" to 1, "rows" to rows.map { it.toList() })
        return MessageDigest.getInstance("SHA-256").digest(Canonical.bytes(body))
    }

    private fun checkedLoss(value: Int): Int {
        require(value in 0..MAX_LOSS) { "loss must be an integer in 0..$MAX_LOSS, got $value" }
        return value
    }

    companion object {
        const val MAX_LOSS = 1000
    }
}

/** 95th percentile by the nearest-rank method, in integer arithmetic: the value at rank ceil(0.95 n). */
fun p95NearestRank(valuesUs: List<Long>): Long {
    if (valuesUs.isEmpty()) return 0L
    val ordered = valuesUs.sorted()
    val rank = (95 * ordered.size + 99) / 100
    return ordered[rank - 1]
}
