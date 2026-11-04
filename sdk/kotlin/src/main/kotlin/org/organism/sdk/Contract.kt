package org.organism.sdk

/*
 * Substrate contract (K1). Port of the validation rules in the Python reference `contract.py` (`SubstrateContract.validate`,
 * `FailureSignature.validate`). Names match the reference so that `conformance/vectors/contract.json` can be replayed.
 *
 * Not ported yet (K1 follow-up, tracked in docs/KOTLIN_PARITY_PLAN.md): perception shapes and sampling, emission shape and
 * dtype, the hardware requirement, failure modes and recovery backoff, read/write roles and tags, channels, justification
 * format and required fields. Validation does not read any of them, so the vectors do not cover them.
 */

/** Severity of a validation finding (reference `Severity`). */
enum class Severity { WARNING, ERROR }

/**
 * One finding from [SubstrateContract.validate]. Conformance compares severity, code and field path, in order.
 * [message] is for people and is not part of the contract.
 */
data class ValidationIssue(val severity: Severity, val code: String, val fieldPath: String, val message: String = "")

/** Module roles (reference `ModuleRole`). */
enum class ModuleRole { PERCEPTION, PREDICTION, SENTINEL, SOLVER, VERIFIER, GOVERNANCE, FEATURE_EXTRACTOR, MEMORY, ACTUATOR, FRONTEND }

/** Reliability tiers, best first. The ordinal is the comparison order used by capability queries. */
enum class ReliabilityTier { T0_DETERMINISTIC, T1_CALIBRATED_NONLEARNED, T2_LEARNED_CALIBRATED, T3_LEARNED_UNCALIBRATED }

/** Highest safety tier a module may serve (reference `MaxSafetyTier`). */
enum class MaxSafetyTier { RESEARCH, LOW, MEDIUM, HIGH, CRITICAL }

/** Input modalities (reference `Modality`). */
enum class Modality { DENSE_VECTOR, TEMPORAL_STREAM, SPIKE_TRAIN, SYMBOL_GRAPH, WAVELET_COEFFS, PHYSICAL_SENSOR, HYPERVECTOR, TABULAR, TEXT, IMAGE }

/**
 * Output forms (reference `OutputForm`). There is no text or token-stream form yet: a language model cannot declare
 * its output today. That is a gap for Lightspeed (see docs/AI_MODEL_GAPS.md).
 */
enum class OutputForm { HYPERVECTOR, SPIKE_TRAIN, ENERGY_GRADIENT, SYMBOLIC_TRIPLE, PROBABILITY_INTERVAL, SCALAR, ASSIGNMENT_CERTIFICATE, FEATURE_VECTOR, JUSTIFICATION_TOKEN }

/** Uncertainty kinds (reference `UncertaintyKind`). */
enum class UncertaintyKind { NONE, CONFORMAL_INTERVAL, ENSEMBLE_SPREAD, ENERGY_LANDSCAPE, SYMBOLIC_PROOF }

/** Determinism of an output (reference `Determinism`). */
enum class Determinism { DETERMINISTIC, SEEDED, STOCHASTIC }

/** Escalation kinds (reference `EscalationKind`). */
enum class EscalationKind { NONE, PROBE_FAILURES, DURATION, PROBE_OR_DURATION }

/** Recovery kinds (reference `RecoveryKind`). */
enum class RecoveryKind { RESTART, RESTORE_SNAPSHOT, DEMOTE, HOT_SWAP, MANUAL }

/** Justification kinds (reference `JustificationKind`). */
enum class JustificationKind { NONE, CAUSAL_CERT, KERNEL_BOUND, RULE_TRACE, ENERGY_CERT, SYMBOLIC_PROOF }

private val EXPLORATION_OVERRIDE_TIERS = setOf(ReliabilityTier.T0_DETERMINISTIC, ReliabilityTier.T1_CALIBRATED_NONLEARNED, ReliabilityTier.T2_LEARNED_CALIBRATED)
private val TRACE_OVERRIDE_TIERS = setOf(ReliabilityTier.T0_DETERMINISTIC, ReliabilityTier.T1_CALIBRATED_NONLEARNED)

private fun issue(severity: Severity, code: String, fieldPath: String, message: String) =
    ValidationIssue(severity, code, fieldPath, message)

data class Identity(
    val moduleId: String,
    val version: String,
    val role: ModuleRole,
    val author: String = "",
    val license: String = "",
)

data class PerceptionSignature(
    val modalities: List<Modality>,
    val requiredModalities: List<Modality> = emptyList(),
)

data class EmissionSignature(
    val outputForm: OutputForm,
    val uncertainty: UncertaintyKind = UncertaintyKind.NONE,
    val determinism: Determinism = Determinism.DETERMINISTIC,
    val requiresJustificationFor: List<String> = emptyList(),
)

/** Declared cost of one inference. Declared values, not measurements: a device measurement replaces them (see docs). */
data class MetabolicProfile(
    val latencyP50Ms: Double,
    val latencyP95Ms: Double,
    val latencyP99Ms: Double,
    val energyPerInferenceJ: Double,
    val memoryFootprintMb: Double,
    val memoryPeakMb: Double,
    val requiresGpu: Boolean = false,
    val requiresGradientTraining: Boolean = false,
    val maxConcurrentInvocations: Int = 1,
)

/** How a module is health-checked. [timeoutMs] is one probe's budget; [cadenceMs] is how often it runs. */
sealed interface HealthProbe {
    val timeoutMs: Int

    fun cadenceMs(probeIntervalMs: Int): Int = probeIntervalMs

    data class Http(val url: String, val expectedStatus: String = "200", override val timeoutMs: Int = 500) : HealthProbe

    data class Rpc(val methodFqn: String, override val timeoutMs: Int = 2000) : HealthProbe

    data class Stream(val topic: String, val expectedPeriodMs: Int, val stallTimeoutMs: Int) : HealthProbe {
        override val timeoutMs: Int get() = stallTimeoutMs

        override fun cadenceMs(probeIntervalMs: Int): Int = expectedPeriodMs
    }
}

data class EscalationPolicy(
    val kind: EscalationKind = EscalationKind.PROBE_OR_DURATION,
    val consecutiveProbeFailures: Int = 3,
    val degradedDurationMs: Int = 15_000,
    val escalateOnProbeTimeout: Boolean = true,
    val escalateOnProbeUnreachable: Boolean = false,
    val probeIntervalMs: Int = 5_000,
)

data class RecoveryProcedure(val kind: RecoveryKind = RecoveryKind.RESTART, val maxAttempts: Int = 3)

data class FailureSignature(
    val probe: HealthProbe,
    val escalation: EscalationPolicy = EscalationPolicy(),
    val recovery: RecoveryProcedure = RecoveryProcedure(),
) {
    /** Reference REG-8, REG-9 and REG-10. */
    fun validate(): List<ValidationIssue> {
        val issues = ArrayList<ValidationIssue>()
        val timeout = probe.timeoutMs
        val cadence = probe.cadenceMs(escalation.probeIntervalMs)
        if (escalation.escalateOnProbeTimeout && timeout >= escalation.degradedDurationMs) {
            issues += issue(Severity.ERROR, "escalation_policy_inconsistent", "failure.escalation",
                "escalate_on_probe_timeout requires probe timeout < degraded_duration_ms")
        }
        if (escalation.degradedDurationMs < 3 * cadence) {
            issues += issue(Severity.ERROR, "escalation_policy_inconsistent", "failure.escalation",
                "degraded_duration_ms must be >= 3 * probe cadence")
        }
        if (timeout >= cadence) {
            issues += issue(Severity.ERROR, "health_probe_inconsistent", "failure.probe",
                "probe timeout must be < probe cadence")
        }
        return issues
    }
}

data class SafetyDeclaration(
    val reliabilityTier: ReliabilityTier,
    val mayActuate: Boolean,
    val requiresCausalCertificate: Boolean = false,
    val requiresCrossCheck: Boolean = false,
    val maxSafetyTier: MaxSafetyTier = MaxSafetyTier.HIGH,
)

data class CapabilityScopes(
    val canOverrideTraceSink: Boolean = false,
    val canOverrideTraceSinkExploration: Boolean = false,
    val explorationTraceSinkId: String = "",
)

data class Lifecycle(
    val hotSwapSupported: Boolean = false,
    val shadowValidationRequired: Boolean = false,
    val selfTerminationPermitted: Boolean = false,
)

data class Justification(val kind: JustificationKind = JustificationKind.NONE)

/**
 * The contract every module declares. A module with an error-level finding cannot be registered.
 * Warnings do not block registration.
 */
data class SubstrateContract(
    val identity: Identity,
    val perception: PerceptionSignature,
    val emission: EmissionSignature,
    val metabolic: MetabolicProfile,
    val failure: FailureSignature,
    val safety: SafetyDeclaration,
    val capabilities: CapabilityScopes = CapabilityScopes(),
    val lifecycle: Lifecycle = Lifecycle(),
    val justification: Justification = Justification(),
) {
    /** Same rules, same order as the reference `SubstrateContract.validate`. */
    fun validate(): List<ValidationIssue> {
        val issues = ArrayList<ValidationIssue>()
        issues += failure.validate()

        if (identity.moduleId.isEmpty()) {
            issues += issue(Severity.ERROR, "identity_missing", "identity.module_id", "module_id required")
        }
        if (identity.version.isEmpty()) {
            issues += issue(Severity.ERROR, "identity_missing", "identity.version", "version required")
        }

        val tier = safety.reliabilityTier
        if (capabilities.canOverrideTraceSinkExploration) {
            if (tier !in EXPLORATION_OVERRIDE_TIERS) {
                issues += issue(Severity.ERROR, "capability_tier_incompatible",
                    "capabilities.can_override_trace_sink_exploration", "exploration sink override requires T0/T1/T2")
            }
            if (capabilities.explorationTraceSinkId.isEmpty()) {
                issues += issue(Severity.ERROR, "exploration_sink_missing", "capabilities.exploration_trace_sink_id",
                    "exploration_trace_sink_id required when override enabled")
            }
        }
        if (capabilities.canOverrideTraceSink && tier !in TRACE_OVERRIDE_TIERS) {
            issues += issue(Severity.ERROR, "capability_tier_incompatible", "capabilities.can_override_trace_sink",
                "trace_sink_override requires T0/T1")
        }

        for (m in perception.requiredModalities) {
            if (m !in perception.modalities) {
                issues += issue(Severity.ERROR, "required_modality_undeclared", "perception.required_modalities",
                    "required modality $m not in modalities")
            }
        }

        if (safety.mayActuate &&
            (tier == ReliabilityTier.T2_LEARNED_CALIBRATED || tier == ReliabilityTier.T3_LEARNED_UNCALIBRATED) &&
            !safety.requiresCrossCheck
        ) {
            issues += issue(Severity.WARNING, "actuation_without_cross_check", "safety.requires_cross_check",
                "learned actuating modules should require cross-check")
        }

        if (justification.kind != JustificationKind.NONE && emission.requiresJustificationFor.isEmpty()) {
            issues += issue(Severity.WARNING, "justification_unused", "emission.requires_justification_for",
                "justification.kind != NONE but no action classes require tokens")
        }
        return issues
    }

    /** True when no finding is error-level. */
    fun isRegistrable(): Boolean = validate().none { it.severity == Severity.ERROR }
}
