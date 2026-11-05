package org.organism.sdk

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/** Replays `router.json` produced by the Python reference (`conformance/generate.py`): K2, gaps D1 and D2. */
class RouterConformanceTest {
    private fun load(): Map<String, Any?> {
        val dir = System.getProperty("organism.conformance.dir") ?: error("organism.conformance.dir not set")
        return Json.parse(File(dir, "router.json").readText(Charsets.UTF_8)).asMap()
    }

    private fun strs(v: Any?): List<String> = v.asList().map { it as String }

    private fun unhex(s: String): ByteArray = ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }

    private fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }

    @Test
    fun exclusionCodesAndDefaultPolicyMatchReference() {
        val doc = load()
        assertEquals(strs(doc["exclusion_codes"]), ExclusionCodes.ALL, "exclusion codes")
        val policy = doc["policy"].asMap()
        val formToRoles = policy["form_to_roles"].asMap().mapValues { strs(it.value) }
        assertEquals(formToRoles, Routing.DEFAULT_FORM_TO_ROLES, "default form to roles")
        assertEquals(Routing.BOOTSTRAP_POLICY_ID, policy["policy_id"] as String)
        assertEquals(Routing.BOOTSTRAP_POLICY_VERSION, policy["version"] as String)
        val digest = Routing.policyDigest(policy["policy_id"] as String, policy["version"] as String, formToRoles)
        assertEquals(policy["digest"] as String, hex(digest), "policy digest")
    }

    @Test
    fun exclusionsRefuseUnknownCodes() {
        assertFailsWith<IllegalArgumentException> { Excluded("m", "not_a_code") }
    }

    @Test
    fun eligibilityMasksMatchReference() {
        val doc = load()
        val formToRoles = doc["policy"].asMap()["form_to_roles"].asMap().mapValues { strs(it.value) }
        val cases = doc["eligibility"].asList().map { it.asMap() }
        assertEquals(8, cases.size, "eligibility case count changed: regenerate and review router.json")
        for (c in cases) {
            val name = c["name"] as String
            val form = c["form"] as String
            val modules = c["modules"].asList().map { it.asMap() }.map {
                RouteModule(it["module_id"] as String, it["role"] as String, it["tier"] as String, it["hardware"] as String)
            }
            val result = Routing.eligibility(
                modules = modules,
                roles = formToRoles[form] ?: emptyList(),
                form = form,
                safetyTier = c["safety_tier"] as String,
                level = c["level"] as String,
                requiresInterpretability = c["requires_interpretability"] as Boolean,
                health = c["health"].asMap().mapValues { it.value as String },
                availableHardware = strs(c["available_hardware"]).toSet(),
            )
            assertEquals(strs(c["eligible"]), result.eligible.map { it.moduleId }, "$name: eligible")
            val excluded = result.excluded.map {
                mapOf("module_id" to it.moduleId, "reason_code" to it.reasonCode, "reason_params" to it.reasonParams)
            }
            assertEquals(c["excluded"], excluded, "$name: excluded")
        }
    }

    @Test
    fun planBytesMatchReference() {
        val plans = load()["plans"].asList().map { it.asMap() }
        assertEquals(2, plans.size, "plan case count changed: regenerate and review router.json")
        for (raw in plans) {
            val name = raw["name"] as String
            val p = raw["plan"].asMap()
            val plan = DispatchPlan(
                planId = "not-part-of-the-bytes",
                taskId = p["task_id"] as String,
                policyId = p["policy_id"] as String,
                policyDigest = unhex(p["policy_digest"] as String),
                level = p["level"] as String,
                planType = p["plan_type"] as String,
                primary = p["primary"] as String?,
                fallbacks = strs(p["fallbacks"]),
                constraintsApplied = strs(p["constraints_applied"]),
                excluded = p["excluded"].asList().map { e ->
                    val m = e.asMap()
                    Excluded(m["module_id"] as String, m["reason_code"] as String,
                        m["reason_params"].asMap().mapValues { it.value as String })
                },
                rankingTrace = strs(p["ranking_trace"]),
                crossCheckRequired = p["cross_check_required"] as Boolean,
                crossCheckModule = p["cross_check_module"] as String?,
                justificationRequired = p["justification_required"] as String,
                disposition = p["disposition"] as String,
                holdReason = p["hold_reason"] as String?,
                candidateRoles = strs(p["candidate_roles"]),
            )
            assertEquals(raw["canonical"] as String, String(Routing.planBytes(plan), Charsets.UTF_8), "$name: plan bytes")
        }
    }

    @Test
    fun traceIdentityMatchesReference() {
        val traces = load()["traces"].asList().map { it.asMap() }
        assertEquals(2, traces.size, "trace case count changed: regenerate and review router.json")
        for (raw in traces) {
            val name = raw["name"] as String
            val e = raw["entry"].asMap()
            val entry = RoutingTraceEntry(
                taskId = e["task_id"] as String,
                form = e["form"] as String,
                planType = e["plan_type"] as String,
                primaryModuleId = e["primary_module_id"] as String,
                policyId = e["policy_id"] as String?,
                policyDigest = (e["policy_digest"] as String?)?.let { unhex(it) },
                level = e["level"] as String?,
                holdReason = e["hold_reason"] as String?,
                excluded = strs(e["excluded"]),
            )
            assertEquals(raw["canonical"] as String, String(Routing.traceBytes(entry), Charsets.UTF_8), "$name: trace bytes")
        }
    }
}
