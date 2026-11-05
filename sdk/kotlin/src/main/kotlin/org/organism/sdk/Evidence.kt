package org.organism.sdk

/*
 * Calibration and measured-metabolics evidence (K1b task 7, gaps A5 and A6). Port of `evidence.py`. The gates compare
 * doubles with the same operations as the reference, so the same record gives the same issues in both SDKs. Vectors:
 * evidence.json. Values are measured on a device here only as data; no GPU or NPU device was used to produce them.
 */

/** Tiers that claim calibration (reference `CALIBRATED_TIERS`). T3 says it is uncalibrated, so it makes no claim. */
val CALIBRATED_TIERS: Set<ReliabilityTier> = setOf(
    ReliabilityTier.T1_CALIBRATED_NONLEARNED,
    ReliabilityTier.T2_LEARNED_CALIBRATED,
)

/** Calibration measured on held-out data. Every rate is a fraction in 0..1 (reference `CalibrationRecord`). */
data class CalibrationRecord(
    val ece: Double,
    val targetCoverage: Double,
    val empiricalCoverage: Double,
    val samples: Int,
    val evidenceDigest: ByteArray = ByteArray(0),
)

/** What calibration evidence must show. The defaults are placeholders for the owner to set (reference `CalibrationThreshold`). */
data class CalibrationThreshold(
    val maxEce: Double = 0.05,
    val maxCoverageGap: Double = 0.05,
    val minSamples: Int = 200,
)

/**
 * The first issue that stops a gated promotion, or an empty list when the evidence passes. Pure. Codes:
 * `calibration_evidence_invalid`, `calibration_evidence_insufficient`, `calibration_evidence_unattributed`,
 * `calibration_ece_exceeded`, `calibration_coverage_short`.
 */
fun calibrationGate(record: CalibrationRecord, threshold: CalibrationThreshold): List<ValidationIssue> {
    fun fail(code: String, fieldPath: String, message: String) =
        listOf(ValidationIssue(Severity.ERROR, code, fieldPath, message))

    for ((name, value) in listOf(
        "ece" to record.ece,
        "target_coverage" to record.targetCoverage,
        "empirical_coverage" to record.empiricalCoverage,
    )) {
        if (!(value >= 0.0 && value <= 1.0)) { // NaN fails this comparison too
            return fail("calibration_evidence_invalid", "calibration.$name", "$name must be in 0..1")
        }
    }
    if (record.samples < threshold.minSamples) {
        return fail("calibration_evidence_insufficient", "calibration.samples",
            "samples=${record.samples} required=${threshold.minSamples}")
    }
    if (record.evidenceDigest.isEmpty()) {
        return fail("calibration_evidence_unattributed", "calibration.evidence_digest", "no evidence digest")
    }
    if (record.ece > threshold.maxEce) {
        return fail("calibration_ece_exceeded", "calibration.ece", "ece=${record.ece} max=${threshold.maxEce}")
    }
    if (record.targetCoverage - record.empiricalCoverage > threshold.maxCoverageGap) {
        return fail("calibration_coverage_short", "calibration.empirical_coverage",
            "target=${record.targetCoverage} empirical=${record.empiricalCoverage}")
    }
    return emptyList()
}

/** What a module cost when it ran on a device. Units are those of [MetabolicProfile] (reference `MeasuredMetabolics`). */
data class MeasuredMetabolics(
    val deviceClass: String,
    val latencyP95Ms: Double,
    val energyPerInferenceJ: Double,
    val memoryPeakMb: Double,
    val samples: Int,
    val evidenceDigest: ByteArray = ByteArray(0),
)

/** A measured value may exceed the declared one by [factor] before it counts as under-declared (reference `MetabolicTolerance`). */
data class MetabolicTolerance(val factor: Double = 1.25, val minSamples: Int = 100)

/**
 * The issues that stop a gated promotion because the measurement does not fit the declared cost. Pure. Codes:
 * `measurement_invalid` (the first bad value), `measurement_insufficient`, `measurement_unattributed`, and
 * `metabolic_underdeclared` for each field whose measured value exceeds the declared value times the factor, in field order.
 */
fun metabolicGate(
    declared: MetabolicProfile,
    measured: MeasuredMetabolics,
    tolerance: MetabolicTolerance,
): List<ValidationIssue> {
    for ((name, value) in listOf(
        "latency_p95_ms" to measured.latencyP95Ms,
        "energy_per_inference_j" to measured.energyPerInferenceJ,
        "memory_peak_mb" to measured.memoryPeakMb,
    )) {
        if (!(value >= 0.0 && value < Double.POSITIVE_INFINITY)) {
            return listOf(ValidationIssue(Severity.ERROR, "measurement_invalid", "measured.$name", "$name must be finite and >= 0"))
        }
    }
    if (measured.samples < tolerance.minSamples) {
        return listOf(ValidationIssue(Severity.ERROR, "measurement_insufficient", "measured.samples",
            "samples=${measured.samples} required=${tolerance.minSamples}"))
    }
    if (measured.evidenceDigest.isEmpty()) {
        return listOf(ValidationIssue(Severity.ERROR, "measurement_unattributed", "measured.evidence_digest", "no evidence digest"))
    }
    val pairs = listOf(
        Triple("latency_p95_ms", measured.latencyP95Ms, declared.latencyP95Ms),
        Triple("energy_per_inference_j", measured.energyPerInferenceJ, declared.energyPerInferenceJ),
        Triple("memory_peak_mb", measured.memoryPeakMb, declared.memoryPeakMb),
    )
    return pairs
        .filter { (_, measuredValue, declaredValue) -> measuredValue > declaredValue * tolerance.factor }
        .map { (name, measuredValue, declaredValue) ->
            ValidationIssue(Severity.ERROR, "metabolic_underdeclared", "measured.$name",
                "measured $measuredValue exceeds declared $declaredValue x ${tolerance.factor}")
        }
}
