package org.organism.sdk

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/** Replays the language-neutral vectors produced by the Python reference (`conformance/generate.py`). */
class ConformanceTest {
    private fun load(name: String): Map<String, Any?> {
        val dir = System.getProperty("organism.conformance.dir") ?: error("organism.conformance.dir not set")
        return Json.parse(File(dir, "$name.json").readText(Charsets.UTF_8)).asMap()
    }

    private fun hv(v: Any?) = Hypervector.fromHex(v.asList().map { it as String })

    @Test
    fun hypervectorMatchesReference() {
        val doc = load("hypervector")
        assertEquals(Hypervector.DIM, doc["dim"].asInt())
        assertEquals(Hypervector.WORD_COUNT, doc["word_count"].asInt())
        var n = 0
        for (c in doc["cases"].asList().map { it.asMap() }) {
            when (val op = c["op"] as String) {
                "bind" -> assertEquals(hv(c["out"]), hv(c["a"]).bind(hv(c["b"])), "bind")
                "permute" -> assertEquals(hv(c["out"]), hv(c["a"]).permute(c["k"].asLong()), "permute k=${c["k"]}")
                "similarity" -> assertEquals(c["out"].asDouble(), hv(c["a"]).similarity(hv(c["b"])), 0.0, "similarity")
                "bundle" -> assertEquals(hv(c["out"]), Hypervector.bundle(c["in"].asList().map { hv(it) }), "bundle n=${c["in"].asList().size}")
                else -> error("unknown op $op")
            }
            n++
        }
        assertEquals(20, n)
    }

    private fun signals(d: Map<String, Any?>) = HealthSignals(
        hM = d["h_m"].asMap().mapValues { it.value as String },
        cM = d["c_m"].asMap().mapValues { it.value.asDouble() },
        thermal = d["thermal"].asDouble(),
        power = d["power"].asDouble(),
        mem = d["mem"].asDouble(),
        qP95 = d["q_p95"].asDouble(),
        gc = d["gc"].asDouble(),
        byz = d["byz"] as Boolean,
        byzCount = d["byz_count"].asInt(),
        traceOk = d["trace_ok"] as Boolean,
        detOk = d["det_ok"] as Boolean,
        causalOk = d["causal_ok"] as Boolean,
        neuralModules = d["neural_modules"].asList().map { it as String },
        leadingPredictive = d["leading_predictive"].asList().map { it as String },
    )

    @Test
    fun degradationMatchesReference() {
        val scenarios = load("degradation")["scenarios"].asList().map { it.asMap() }
        assertTrue(scenarios.size >= 20)
        val reached = HashSet<String>()
        for (sc in scenarios) {
            val m = DegradationMachine()
            val steps = sc["steps"].asList().map { it.asMap() }
            val levels = sc["levels"].asList().map { it as String }
            steps.forEachIndexed { i, st ->
                m.signals = signals(st["signals"].asMap())
                m.humanAck = st["human_ack"] == true
                m.advance(st["dt"].asDouble())
                assertEquals(levels[i], m.level.name, "${sc["name"]} step $i")
            }
            val expected = sc["transitions"].asList().map { t -> t.asList().map { it as String } }
            assertEquals(expected, m.transitions.map { listOf(it.from.name, it.to.name, it.trigger) }, "${sc["name"]} transitions")
            assertEquals(sc["final_human_ack"] as Boolean, m.humanAck, "${sc["name"]} final ack")
            m.transitions.forEach { reached.add(it.to.name) }
        }
        assertEquals(setOf("L0", "L1", "L2", "L3", "L4"), reached)
    }
}
