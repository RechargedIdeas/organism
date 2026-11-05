package org.organism.sdk

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals

/** Replays `shadow.json` produced by the Python reference (`shadow_runner.py`): ShadowRunner on scripted live traffic. */
class ShadowConformanceTest {
    private fun load(): Map<String, Any?> {
        val dir = System.getProperty("organism.conformance.dir") ?: error("organism.conformance.dir not set")
        return Json.parse(File(dir, "shadow.json").readText(Charsets.UTF_8)).asMap()
    }

    private fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }

    @Test
    fun runnerEvidenceMatchesReference() {
        val doc = load()
        assertEquals(ShadowRunner.MAX_LOSS, doc["max_loss"].asInt(), "max loss changed")
        val cases = doc["cases"].asList().map { it.asMap() }
        assertEquals(5, cases.size, "shadow case count changed: regenerate and review shadow.json")
        for (c in cases) {
            val name = c["name"] as String
            // Json.parse reads numbers as doubles; every value here is an integer well inside their exact range.
            val rows = c["rows"].asList().map { r -> r.asList().map { (it as Number).toLong() } }
            val ticks = ArrayDeque(c["ticks"].asList().map { (it as Number).toLong() })
            val runner = ShadowRunner<Int, String>(
                incumbent = { "inc:$it" },
                candidate = { i ->
                    if (rows[i][2] == 1L) throw RuntimeException("candidate failed") else "cand:$i"
                },
                loss = { req, out -> if (out.startsWith("inc")) rows[req][0].toInt() else rows[req][1].toInt() },
                clockNs = { ticks.removeFirst() },
                gatesPassed = listOf("shadow_runner"),
            )
            for (i in rows.indices) assertEquals("inc:$i", runner.onTraffic(i), "$name: served output")
            val rec = runner.record()
            val e = c["expected"].asMap()
            assertEquals(e["invocations"].asInt(), rec.invocations, "$name: invocations")
            assertEquals(e["incumbent_error"].asDouble(), rec.incumbentError, 0.0, "$name: incumbent error")
            assertEquals(e["candidate_error"].asDouble(), rec.candidateError, 0.0, "$name: candidate error")
            assertEquals(e["p95_latency_ms"].asDouble(), rec.p95LatencyMs, 0.0, "$name: p95")
            assertEquals(e["gates_passed"].asList().map { it as String }, rec.gatesPassed, "$name: gates")
            assertEquals(e["evidence_digest"] as String, hex(rec.evidenceDigest), "$name: evidence digest")
        }
    }

    @Test
    fun p95IsNearestRank() {
        assertEquals(19L, p95NearestRank((1L..20L).toList()))
        assertEquals(0L, p95NearestRank(emptyList()))
    }
}
