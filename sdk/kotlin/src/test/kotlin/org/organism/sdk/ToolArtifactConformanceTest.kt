package org.organism.sdk

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Replays `tool.json` (gap A2) and `model_artifact.json` (gap A8) produced by the Python reference. */
class ToolArtifactConformanceTest {
    private fun load(name: String): Map<String, Any?> {
        val dir = System.getProperty("organism.conformance.dir") ?: error("organism.conformance.dir not set")
        return Json.parse(File(dir, "$name.json").readText(Charsets.UTF_8)).asMap()
    }

    private fun Map<String, Any?>.str(key: String): String = this[key] as String

    private fun Map<String, Any?>.strs(key: String): List<String> = this[key].asList().map { it as String }

    private fun triples(raw: Any?): List<Triple<Severity, String, String>> = raw.asList().map {
        val m = it.asMap()
        Triple(Severity.valueOf(m.str("severity")), m.str("code"), m.str("field_path"))
    }

    private fun found(issues: List<ValidationIssue>) = issues.map { Triple(it.severity, it.code, it.fieldPath) }

    @Test
    fun toolContractMatchesReference() {
        val cases = load("tool")["cases"].asList().map { it.asMap() }
        assertEquals(24, cases.size, "tool case count changed: regenerate and review the vectors")
        for (case in cases) {
            val name = case.str("name")
            val t = case["tool"].asMap()
            val tool = ToolContract(
                name = t.str("name"),
                schemaJson = t.str("schema"),
                riskTier = MaxSafetyTier.valueOf(t.str("risk_tier")),
                confirmation = ToolConfirmation.valueOf(t.str("confirmation")),
                network = ToolNetwork.valueOf(t.str("network")),
                confinement = ToolConfinement.valueOf(t.str("confinement")),
            )
            assertEquals(triples(case["issues"]), found(tool.validate()), "$name: issues")
            assertEquals(case["registered"] as Boolean, tool.isRegistrable(), "$name: registered")
        }
    }

    @Test
    fun modelArtifactMatchesReference() {
        val cases = load("model_artifact")["cases"].asList().map { it.asMap() }
        assertEquals(22, cases.size, "model_artifact case count changed: regenerate and review the vectors")
        for (case in cases) {
            val name = case.str("name")
            val a = case["artifact"].asMap()
            val artifact = ModelArtifact(
                modelId = a.str("model_id"),
                version = a.str("version"),
                weightsDigest = a.str("weights_digest"),
                tokenizerDigest = a.str("tokenizer_digest"),
                quantisation = a.str("quantisation"),
                license = a.str("license"),
                gateReportDigest = a.str("gate_report_digest"),
                adapterLineage = a.strs("adapter_lineage"),
                dataProvenance = a.strs("data_provenance"),
            )
            assertEquals(triples(case["issues"]), found(artifact.validate()), "$name: issues")
            assertEquals(case["releasable"] as Boolean, artifact.isReleasable(), "$name: releasable")
        }
    }

    @Test
    fun digestFormat() {
        assertTrue(ModelArtifact.isDigest("sha256:" + "0123456789abcdef".repeat(4)))
        assertFalse(ModelArtifact.isDigest("sha256:" + "0123456789ABCDEF".repeat(4)))
        assertFalse(ModelArtifact.isDigest("sha256:"))
    }
}
