package org.organism.sdk

/*
 * Signed promotion payload (K6, gap B1). Port of `signing.promotion_payload`. Every payload starts with a domain line,
 * so a registration signature cannot be replayed as a promotion. The body is canonical JSON (`Canonical.kt`) with
 * integer evidence: error rates as parts per million, latency as microseconds, both rounded half to even (Math.rint,
 * the same rounding as Python's round()). The bytes therefore agree in both SDKs. Vectors: lifecycle.json.
 */
object Signing {
    private const val PROMOTE_DOMAIN = "organism.registry.promote.v1\n"

    /** Bytes an approver signs to move [moduleId] from [fromState] to [toState] with [shadow] as the evidence. */
    fun promotionPayload(
        moduleId: String,
        fromState: String,
        toState: String,
        shadow: List<ShadowValidationRecord>,
    ): ByteArray {
        val body = mapOf(
            "module_id" to moduleId,
            "from_state" to fromState,
            "to_state" to toState,
            "shadow" to shadow.map { shadowJson(it) },
        )
        return PROMOTE_DOMAIN.toByteArray(Charsets.UTF_8) + Canonical.bytes(body)
    }

    private fun shadowJson(r: ShadowValidationRecord): Map<String, Any?> = mapOf(
        "invocations" to r.invocations,
        "incumbent_error_ppm" to scaled(r.incumbentError, 1_000_000.0),
        "candidate_error_ppm" to scaled(r.candidateError, 1_000_000.0),
        "p95_latency_us" to scaled(r.p95LatencyMs, 1_000.0),
        "gates_passed" to r.gatesPassed,
        "evidence_digest" to r.evidenceDigest.joinToString("") { "%02x".format(it) },
    )

    private fun scaled(value: Double, scale: Double): Long {
        val product = value * scale
        require(product.isFinite()) { "shadow evidence must be finite" }
        return Math.rint(product).toLong()
    }
}
