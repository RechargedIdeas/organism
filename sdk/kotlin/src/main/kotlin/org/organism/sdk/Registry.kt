package org.organism.sdk

/*
 * Module registry and lifecycle ladder (K1). Port of the reference `registry.py` (`RegistryClient`) and its ladder.
 * Differences from the reference are listed on each function. The reference raises exceptions where this port returns
 * a rejection with a code; the conformance vectors record those cases as rejections.
 */

/** Lifecycle states (reference `LifecycleState`). */
enum class LifecycleState {
    PROPOSED, SANDBOXED, SHADOW_VALIDATED, EXPLORATION, DEVELOPMENT, DELIBERATION,
    SELF_TERMINATING, SUCCEEDED, DEGRADED, DEPRECATED, RETIRED,
}

/** The promotion ladder and the rank used by capability queries. */
object Ladder {
    /** Linear promotion order (reference `_PROMOTE_ORDER`). Only these states can be promoted. */
    val PROMOTE_ORDER: List<LifecycleState> = listOf(
        LifecycleState.PROPOSED,
        LifecycleState.SANDBOXED,
        LifecycleState.SHADOW_VALIDATED,
        LifecycleState.EXPLORATION,
        LifecycleState.DELIBERATION,
        LifecycleState.DEPRECATED,
        LifecycleState.RETIRED,
    )

    /**
     * Rank used by queries (reference `_rank`). DEVELOPMENT ranks as EXPLORATION. The other extended states
     * (SELF_TERMINATING, SUCCEEDED, DEGRADED) rank below every ladder state.
     */
    fun rank(state: LifecycleState): Int = when (state) {
        LifecycleState.DEVELOPMENT -> PROMOTE_ORDER.indexOf(LifecycleState.EXPLORATION)
        LifecycleState.SELF_TERMINATING, LifecycleState.SUCCEEDED, LifecycleState.DEGRADED -> -1
        else -> PROMOTE_ORDER.indexOf(state)
    }

    /** True when a promotion from [from] to [to] is exactly one step up the ladder. */
    fun isNextStep(from: LifecycleState, to: LifecycleState): Boolean {
        val f = PROMOTE_ORDER.indexOf(from)
        val t = PROMOTE_ORDER.indexOf(to)
        return f >= 0 && t == f + 1
    }
}

/** Handle returned by a capability query. */
data class ModuleHandle(
    val moduleId: String,
    val version: String,
    val role: ModuleRole,
    val tier: ReliabilityTier,
    val state: LifecycleState,
)

/** Query filter (reference `CapabilityFilter`). Empty means no restriction. */
data class CapabilityFilter(
    val roles: Set<ModuleRole> = emptySet(),
    val minReliability: ReliabilityTier? = null,
    val minLifecycleState: LifecycleState? = null,
)

/** Outcome of [ModuleRegistry.register]. A rejected contract is not stored. */
data class RegisterResult(
    val moduleId: String,
    val accepted: Boolean,
    val initialState: LifecycleState?,
    val issues: List<ValidationIssue>,
)

/** Outcome of [ModuleRegistry.promote]. [code] is the first issue's code, or null when accepted. */
data class PromoteResult(val accepted: Boolean, val issues: List<ValidationIssue>) {
    val code: String? get() = issues.firstOrNull()?.code
}

/**
 * In-process registry. Holds contracts and their lifecycle state.
 *
 * Deliberate differences from the reference, each one a finding for the gap list:
 * - [promote] checks the approver when [approvers] is set, and the shadow evidence for gated states (K6). Without
 *   [approvers] the approver is not checked, as in the reference without a trust store. The reference's
 *   `test_bypass_validation` has no counterpart here; the evidence check is never skipped.
 * - An unknown module id is a `not_found` rejection, not a KeyError.
 * - Registering an id that already exists replaces the entry, as the reference does. No warning is raised.
 * - [register] does not check an author signature. The reference does with a trust store; the Kotlin port has no
 *   registration signing yet.
 *
 * Every public method is synchronized, as the reference is (it holds a lock), so the registry can be shared between
 * threads on Android and on the desktop.
 */
class ModuleRegistry(
    private val approvers: List<ByteArray>? = null,
    private val threshold: ShadowThreshold = ShadowThreshold(),
) {
    private class Entry(val contract: SubstrateContract, var state: LifecycleState)

    private val entries = LinkedHashMap<String, Entry>()

    /**
     * Validates [contract] and stores it in [initial] state (default PROPOSED). Any state is allowed as the initial
     * state, as in the reference, so a hot registration can start in DELIBERATION.
     */
    @Synchronized
    fun register(contract: SubstrateContract, initial: LifecycleState = LifecycleState.PROPOSED): RegisterResult {
        val id = contract.identity.moduleId
        val issues = contract.validate()
        if (issues.any { it.severity == Severity.ERROR }) return RegisterResult(id, false, null, issues)
        entries[id] = Entry(contract, initial)
        return RegisterResult(id, true, initial, issues)
    }

    /** Current state, or null when the module is not registered. */
    @Synchronized
    fun state(moduleId: String): LifecycleState? = entries[moduleId]?.state

    /**
     * Moves [moduleId] from [from] to [to]. The module must be in [from] and [to] must be the next ladder step.
     * With [approvers] set, [approverSignature] must verify over the promotion payload (`signature_invalid` otherwise),
     * as the reference does with a trust store. A promotion into a [GATED_STATES] state also needs [shadow] evidence
     * that passes [threshold] (`shadow_evidence_insufficient`, `shadow_evidence_unattributed`,
     * `shadow_error_regression`). The checks run in that order. A rejection leaves the state unchanged.
     */
    @Synchronized
    fun promote(
        moduleId: String,
        from: LifecycleState,
        to: LifecycleState,
        shadow: List<ShadowValidationRecord> = emptyList(),
        approverSignature: ByteArray = ByteArray(0),
    ): PromoteResult {
        val entry = entries[moduleId] ?: return reject("not_found", "module_id", "unknown module")
        val trusted = approvers
        if (trusted != null) {
            val payload = Signing.promotionPayload(moduleId, from.name, to.name, shadow)
            if (trusted.none { Ed25519.verify(it, approverSignature, payload) }) {
                return reject("signature_invalid", "approver_signature", "no trusted approver key verifies this signature")
            }
        }
        if (entry.state != from) {
            return reject("lifecycle_mismatch", "from_state", "actual=${entry.state} expected=$from")
        }
        if (!Ladder.isNextStep(from, to)) {
            return reject("invalid_promotion", "to_state", "cannot promote $from -> $to")
        }
        if (to in GATED_STATES) {
            val issues = shadowGate(shadow, threshold)
            if (issues.isNotEmpty()) return PromoteResult(false, issues)
        }
        entry.state = to
        return PromoteResult(true, emptyList())
    }

    /** Removes [moduleId] and returns the state it had, or null when it was not registered. */
    @Synchronized
    fun deregister(moduleId: String): LifecycleState? = entries.remove(moduleId)?.state

    /** Registered module ids in registration order. */
    @Synchronized
    fun ids(): List<String> = entries.keys.toList()

    /** Modules that pass [filter], in registration order. */
    @Synchronized
    fun query(filter: CapabilityFilter = CapabilityFilter()): List<ModuleHandle> {
        val out = ArrayList<ModuleHandle>()
        for ((id, entry) in entries) {
            val identity = entry.contract.identity
            val tier = entry.contract.safety.reliabilityTier
            if (filter.roles.isNotEmpty() && identity.role !in filter.roles) continue
            val minTier = filter.minReliability
            if (minTier != null && tier.ordinal > minTier.ordinal) continue
            val minState = filter.minLifecycleState
            if (minState != null && Ladder.rank(entry.state) < Ladder.rank(minState)) continue
            out += ModuleHandle(id, identity.version, identity.role, tier, entry.state)
        }
        return out
    }

    private fun reject(code: String, fieldPath: String, message: String) =
        PromoteResult(false, listOf(ValidationIssue(Severity.ERROR, code, fieldPath, message)))
}
