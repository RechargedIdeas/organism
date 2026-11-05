package org.organism.sdk

import java.security.MessageDigest

/*
 * Routing (K2, gaps D1 and D2). Port of the pure parts of the reference `router.py`: the eligibility mask with typed
 * exclusions, the policy digest, and the canonical bytes of a DispatchPlan and of a routing trace entry. The decision
 * procedure itself (hormone reading, autonomic parameters, cross-check search, trace emission) is not ported yet; the
 * Python Router is still the only one. Every function here is pure, so the vectors in `conformance/vectors/router.json`
 * can be replayed without a registry.
 */

/** Exclusion codes (reference `ExclusionCode`). The set is closed: [Excluded] refuses any other code. */
object ExclusionCodes {
    val ALL: List<String> = listOf(
        "role_mismatch",
        "level_ineligible",
        "tier_ineligible",
        "critical_forbids_learned",
        "l4_deterministic_only",
        "health_failed",
        "hardware_capability_missing",
        "interpretability_required",
    )
}

/** One module the router did not consider, with its typed reason (reference `Excluded`). */
data class Excluded(
    val moduleId: String,
    val reasonCode: String,
    val reasonParams: Map<String, String> = emptyMap(),
) {
    init {
        require(reasonCode in ExclusionCodes.ALL) { "unknown exclusion code: $reasonCode" }
    }
}

/**
 * A module as the eligibility mask sees it (reference `ModuleHandle`, with its hardware requirement). Role and tier are
 * the reference's string values (`SOLVER`, `T0_DETERMINISTIC`), so a vector can name them directly.
 */
data class RouteModule(
    val moduleId: String,
    val role: String,
    val tier: String,
    val hardware: String = "NONE",
)

/** Result of [Routing.eligibility]: modules that may be ranked, and an exclusion for each one that may not. Registry order. */
data class Eligibility(val eligible: List<RouteModule>, val excluded: List<Excluded>)

/**
 * The plan the router returns. Modules are named by id (the reference holds the handles); the canonical bytes depend
 * only on the ids. plan_id is not part of the canonical bytes.
 */
data class DispatchPlan(
    val planId: String,
    val taskId: String,
    val policyId: String,
    val policyDigest: ByteArray,
    val level: String,
    val planType: String,
    val primary: String?,
    val fallbacks: List<String>,
    val constraintsApplied: List<String>,
    val excluded: List<Excluded>,
    val rankingTrace: List<String>,
    val crossCheckRequired: Boolean,
    val crossCheckModule: String?,
    val justificationRequired: String,
    val disposition: String = "DISPATCH",
    val holdReason: String? = null,
    val candidateRoles: List<String> = emptyList(),
) {
    // ByteArray has identity equality; compare plans through their canonical bytes instead.
    override fun equals(other: Any?): Boolean = other is DispatchPlan && Routing.planBytes(this).contentEquals(Routing.planBytes(other))
    override fun hashCode(): Int = Routing.planBytes(this).contentHashCode()
}

/** Identity of one routing trace entry (reference `RoutingTraceEntry`, without the float rationale). */
data class RoutingTraceEntry(
    val taskId: String,
    val form: String,
    val planType: String,
    val primaryModuleId: String,
    val policyId: String?,
    val policyDigest: ByteArray?,
    val level: String?,
    val holdReason: String?,
    val excluded: List<String>,
)

object Routing {
    const val BOOTSTRAP_POLICY_ID = "organism.router.bootstrap"
    const val BOOTSTRAP_POLICY_VERSION = "0.1.0"

    /** Default form to roles (reference `DEFAULT_FORM_TO_ROLES`, C.3 step 1). */
    val DEFAULT_FORM_TO_ROLES: Map<String, List<String>> = linkedMapOf(
        "temporal_prediction" to listOf("PREDICTION", "FRONTEND", "FEATURE_EXTRACTOR"),
        "pattern_recognition" to listOf("PERCEPTION", "PREDICTION"),
        "anomaly_detection" to listOf("SENTINEL", "PREDICTION"),
        "constrained_allocation" to listOf("SOLVER"),
        "causal_inference" to listOf("VERIFIER", "GOVERNANCE"),
        "symbolic_reasoning" to listOf("VERIFIER", "GOVERNANCE", "MEMORY"),
        "signal_analysis" to listOf("FRONTEND", "FEATURE_EXTRACTOR"),
        "feature_extraction" to listOf("FEATURE_EXTRACTOR", "FRONTEND"),
        "retrieval" to listOf("MEMORY"),
        "generation" to listOf("PREDICTION", "PERCEPTION"),
        "calibration" to listOf("VERIFIER", "GOVERNANCE"),
        "verification" to listOf("VERIFIER", "GOVERNANCE"),
        "control_actuation" to listOf("ACTUATOR", "GOVERNANCE", "VERIFIER"),
    )

    private val LEARNED = setOf("T2_LEARNED_CALIBRATED", "T3_LEARNED_UNCALIBRATED")
    private val DETERMINISTIC_TIERS = setOf("T0_DETERMINISTIC", "T1_CALIBRATED_NONLEARNED")

    /** Safety tier to allowed module tiers (reference `TIER_ELIGIBILITY`, C.3 step 2). */
    private val TIER_ELIGIBILITY: Map<String, Set<String>> = mapOf(
        "critical" to DETERMINISTIC_TIERS,
        "high" to DETERMINISTIC_TIERS + "T2_LEARNED_CALIBRATED",
        "medium" to DETERMINISTIC_TIERS + LEARNED,
        "low" to DETERMINISTIC_TIERS + LEARNED,
        "research" to DETERMINISTIC_TIERS + LEARNED,
    )

    private val TEN_ROLES = setOf(
        "PERCEPTION", "PREDICTION", "SENTINEL", "SOLVER", "VERIFIER",
        "GOVERNANCE", "FEATURE_EXTRACTOR", "MEMORY", "ACTUATOR", "FRONTEND",
    )

    /** Roles each level admits (reference `LEVEL_ELIGIBILITY`, the role part). */
    private val LEVEL_ROLES: Map<String, Set<String>> = mapOf(
        "L0" to TEN_ROLES,
        "L1" to TEN_ROLES,
        "L2" to setOf("SOLVER", "VERIFIER", "GOVERNANCE", "FRONTEND", "FEATURE_EXTRACTOR", "MEMORY", "ACTUATOR"),
        "L3" to setOf("MEMORY", "GOVERNANCE"),
        "L4" to setOf("GOVERNANCE"),
    )

    /**
     * The eligibility mask for one task (reference `eligibility`). The checks run in the reference's order and the
     * first one a module fails gives its exclusion code, so each module has at most one exclusion. An unknown level
     * throws, as the reference's table lookup does.
     */
    fun eligibility(
        modules: List<RouteModule>,
        roles: List<String>,
        form: String,
        safetyTier: String,
        level: String,
        requiresInterpretability: Boolean,
        health: Map<String, String>,
        availableHardware: Set<String>,
    ): Eligibility {
        val eligibleRoles = LEVEL_ROLES.getValue(level)
        var allowedTiers = TIER_ELIGIBILITY[safetyTier] ?: emptySet()
        // Correction 1.1: control_actuation at any safety tier prefers the deterministic tiers.
        if (form == "control_actuation") allowedTiers = DETERMINISTIC_TIERS
        val eligible = ArrayList<RouteModule>()
        val excluded = ArrayList<Excluded>()
        for (m in modules) {
            val hw = m.hardware.ifEmpty { "NONE" }
            when {
                m.role !in roles -> excluded += Excluded(m.moduleId, "role_mismatch", mapOf("role" to m.role))
                m.role !in eligibleRoles -> excluded += Excluded(m.moduleId, "level_ineligible", mapOf("level" to level))
                m.tier !in allowedTiers -> excluded += Excluded(m.moduleId, "tier_ineligible", mapOf("tier" to m.tier))
                safetyTier == "critical" && m.tier in LEARNED ->
                    excluded += Excluded(m.moduleId, "critical_forbids_learned")
                level == "L4" && m.moduleId != "deterministic_engine" ->
                    excluded += Excluded(m.moduleId, "l4_deterministic_only")
                (health[m.moduleId] ?: "HEALTHY") == "FAILED" -> excluded += Excluded(m.moduleId, "health_failed")
                hw != "NONE" && hw !in availableHardware -> excluded += Excluded(
                    m.moduleId,
                    "hardware_capability_missing",
                    mapOf("required" to hw, "available" to availableHardware.sorted().joinToString(",")),
                )
                requiresInterpretability && m.tier in LEARNED ->
                    excluded += Excluded(m.moduleId, "interpretability_required")
                else -> eligible += m
            }
        }
        return Eligibility(eligible, excluded)
    }

    /** SHA-256 of the canonical JSON of the policy content (reference `compute_policy_digest`, gap D2). */
    fun policyDigest(policyId: String, version: String, formToRoles: Map<String, List<String>>): ByteArray {
        val body = mapOf("policy_id" to policyId, "version" to version, "form_to_roles" to formToRoles)
        return MessageDigest.getInstance("SHA-256").digest(Canonical.bytes(body))
    }

    /** Canonical JSON of a plan (reference `DispatchPlan.to_canonical_bytes`). plan_id is left out. */
    fun planBytes(plan: DispatchPlan): ByteArray = Canonical.bytes(
        mapOf(
            "task_id" to plan.taskId,
            "policy_id" to plan.policyId,
            "policy_digest" to hex(plan.policyDigest),
            "level" to plan.level,
            "plan_type" to plan.planType,
            "primary" to plan.primary,
            "fallbacks" to plan.fallbacks,
            "constraints_applied" to plan.constraintsApplied,
            "excluded" to plan.excluded.map {
                mapOf("module_id" to it.moduleId, "reason_code" to it.reasonCode, "reason_params" to it.reasonParams)
            },
            "ranking_trace" to plan.rankingTrace,
            "cross_check_required" to plan.crossCheckRequired,
            "cross_check_module" to plan.crossCheckModule,
            "justification_required" to plan.justificationRequired,
            "disposition" to plan.disposition,
            "hold_reason" to plan.holdReason,
            "candidate_roles" to plan.candidateRoles,
        ),
    )

    /** Canonical JSON of a routing trace entry's identity (reference `canonical_routing_entry`). */
    fun traceBytes(entry: RoutingTraceEntry): ByteArray = Canonical.bytes(
        mapOf(
            "task_id" to entry.taskId,
            "form" to entry.form,
            "plan_type" to entry.planType,
            "primary_module_id" to entry.primaryModuleId,
            "policy_id" to entry.policyId,
            "policy_digest" to entry.policyDigest?.let { hex(it) },
            "level" to entry.level,
            "hold_reason" to entry.holdReason,
            "excluded" to entry.excluded,
        ),
    )

    private fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }
}
