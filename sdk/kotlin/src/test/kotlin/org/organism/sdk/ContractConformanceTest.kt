package org.organism.sdk

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Replays `contract.json` and `lifecycle.json` produced by the Python reference (`conformance/generate.py`). */
class ContractConformanceTest {
    private fun load(name: String): Map<String, Any?> {
        val dir = System.getProperty("organism.conformance.dir") ?: error("organism.conformance.dir not set")
        return Json.parse(File(dir, "$name.json").readText(Charsets.UTF_8)).asMap()
    }

    private fun Map<String, Any?>.str(key: String): String = this[key] as String

    private fun Map<String, Any?>.bool(key: String): Boolean = this[key] as Boolean

    private fun Map<String, Any?>.int(key: String): Int = this[key].asInt()

    private fun Map<String, Any?>.dbl(key: String): Double = this[key].asDouble()

    private fun Map<String, Any?>.obj(key: String): Map<String, Any?> = this[key].asMap()

    private fun Map<String, Any?>.arr(key: String): List<Any?> = this[key].asList()

    private fun Map<String, Any?>.strs(key: String): List<String> = arr(key).map { it as String }

    private fun parseProbe(d: Map<String, Any?>): HealthProbe = when (d.str("type")) {
        "HTTP" -> HealthProbe.Http(d.str("url"), d.str("expected_status"), d.int("timeout_ms"))
        "RPC" -> HealthProbe.Rpc(d.str("method_fqn"), d.int("timeout_ms"))
        "STREAM" -> HealthProbe.Stream(d.str("topic"), d.int("expected_period_ms"), d.int("stall_timeout_ms"))
        else -> error("unknown probe type ${d.str("type")}")
    }

    private fun parseContract(d: Map<String, Any?>): SubstrateContract {
        val identity = d.obj("identity")
        val perception = d.obj("perception")
        val emission = d.obj("emission")
        val metabolic = d.obj("metabolic")
        val failure = d.obj("failure")
        val escalation = failure.obj("escalation")
        val recovery = failure.obj("recovery")
        val safety = d.obj("safety")
        val caps = d.obj("capabilities")
        val lifecycle = d.obj("lifecycle")
        return SubstrateContract(
            identity = Identity(identity.str("module_id"), identity.str("version"), ModuleRole.valueOf(identity.str("role"))),
            perception = PerceptionSignature(
                modalities = perception.strs("modalities").map { Modality.valueOf(it) },
                requiredModalities = perception.strs("required_modalities").map { Modality.valueOf(it) },
            ),
            emission = EmissionSignature(
                outputForm = OutputForm.valueOf(emission.str("output_form")),
                uncertainty = UncertaintyKind.valueOf(emission.str("uncertainty")),
                determinism = Determinism.valueOf(emission.str("determinism")),
                requiresJustificationFor = emission.strs("requires_justification_for"),
            ),
            metabolic = MetabolicProfile(
                latencyP50Ms = metabolic.dbl("latency_p50_ms"),
                latencyP95Ms = metabolic.dbl("latency_p95_ms"),
                latencyP99Ms = metabolic.dbl("latency_p99_ms"),
                energyPerInferenceJ = metabolic.dbl("energy_per_inference_j"),
                memoryFootprintMb = metabolic.dbl("memory_footprint_mb"),
                memoryPeakMb = metabolic.dbl("memory_peak_mb"),
                requiresGpu = metabolic.bool("requires_gpu"),
                requiresGradientTraining = metabolic.bool("requires_gradient_training"),
                maxConcurrentInvocations = metabolic.int("max_concurrent_invocations"),
            ),
            failure = FailureSignature(
                probe = parseProbe(failure.obj("probe")),
                escalation = EscalationPolicy(
                    kind = EscalationKind.valueOf(escalation.str("kind")),
                    consecutiveProbeFailures = escalation.int("consecutive_probe_failures"),
                    degradedDurationMs = escalation.int("degraded_duration_ms"),
                    escalateOnProbeTimeout = escalation.bool("escalate_on_probe_timeout"),
                    escalateOnProbeUnreachable = escalation.bool("escalate_on_probe_unreachable"),
                    probeIntervalMs = escalation.int("probe_interval_ms"),
                ),
                recovery = RecoveryProcedure(RecoveryKind.valueOf(recovery.str("kind")), recovery.int("max_attempts")),
            ),
            safety = SafetyDeclaration(
                reliabilityTier = ReliabilityTier.valueOf(safety.str("reliability_tier")),
                mayActuate = safety.bool("may_actuate"),
                requiresCausalCertificate = safety.bool("requires_causal_certificate"),
                requiresCrossCheck = safety.bool("requires_cross_check"),
                maxSafetyTier = MaxSafetyTier.valueOf(safety.str("max_safety_tier")),
            ),
            capabilities = CapabilityScopes(
                canOverrideTraceSink = caps.bool("can_override_trace_sink"),
                canOverrideTraceSinkExploration = caps.bool("can_override_trace_sink_exploration"),
                explorationTraceSinkId = caps.str("exploration_trace_sink_id"),
            ),
            lifecycle = Lifecycle(
                hotSwapSupported = lifecycle.bool("hot_swap_supported"),
                shadowValidationRequired = lifecycle.bool("shadow_validation_required"),
                selfTerminationPermitted = lifecycle.bool("self_termination_permitted"),
            ),
            justification = Justification(JustificationKind.valueOf(d.obj("justification").str("kind"))),
        )
    }

    @Test
    fun contractValidationMatchesReference() {
        val cases = load("contract").arr("cases").map { it.asMap() }
        assertEquals(24, cases.size, "contract case count changed: regenerate and review the vectors")
        for (case in cases) {
            val name = case.str("name")
            val contract = parseContract(case.obj("contract"))
            val issues = contract.validate()
            assertEquals(case.bool("registered"), issues.none { it.severity == Severity.ERROR }, "$name: registered")
            val expected = case.arr("issues").map {
                val m = it.asMap()
                Triple(Severity.valueOf(m.str("severity")), m.str("code"), m.str("field_path"))
            }
            assertEquals(expected, issues.map { Triple(it.severity, it.code, it.fieldPath) }, "$name: issues")
        }
    }

    @Test
    fun statesMatchReference() {
        val names = load("lifecycle").strs("states")
        assertEquals(names, LifecycleState.entries.map { it.name })
    }

    @Test
    fun transitionsMatchReference() {
        val doc = load("lifecycle")
        val contract = parseContract(doc.obj("contract"))
        val all = doc.arr("transitions") + doc.arr("lifecycle_mismatch")
        assertEquals(121 + 11, all.size)
        for (raw in all) {
            val t = raw.asMap()
            val registry = ModuleRegistry()
            assertTrue(registry.register(contract, LifecycleState.valueOf(t.str("initial"))).accepted)
            val result = registry.promote(
                "m.lc", LifecycleState.valueOf(t.str("from")), LifecycleState.valueOf(t.str("to")),
            )
            val label = "${t.str("initial")} ${t.str("from")} -> ${t.str("to")}"
            assertEquals(t.bool("accepted"), result.accepted, "$label: accepted")
            assertEquals(t["code"] as String?, result.code, "$label: code")
            assertEquals(t.str("state_after"), registry.state("m.lc")?.name, "$label: state after")
        }
    }

    @Test
    fun capabilityQueriesMatchReference() {
        val queries = load("lifecycle").obj("queries")
        val registry = ModuleRegistry()
        for (raw in queries.arr("modules")) {
            val m = raw.asMap()
            registry.register(parseContract(m.obj("contract")), LifecycleState.valueOf(m.str("state")))
        }
        val cases = queries.arr("cases")
        assertTrue(cases.size >= 8)
        for (raw in cases) {
            val c = raw.asMap()
            val f = c.obj("filter")
            val filter = CapabilityFilter(
                roles = (f["roles"] as List<*>?)?.map { ModuleRole.valueOf(it as String) }?.toSet() ?: emptySet(),
                minReliability = (f["min_reliability"] as String?)?.let { ReliabilityTier.valueOf(it) },
                minLifecycleState = (f["min_lifecycle_state"] as String?)?.let { LifecycleState.valueOf(it) },
            )
            val got = registry.query(filter).map { it.moduleId }.sorted()
            assertEquals(c.strs("expected_ids"), got, "filter $f")
        }
    }
}
