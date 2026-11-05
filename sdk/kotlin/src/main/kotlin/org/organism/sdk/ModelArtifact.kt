package org.organism.sdk

/*
 * ModelArtifact manifest (gap A8). Port of `organism_sdk/model_artifact.py`: what a model release states before it is
 * served. Digests are `sha256:` followed by 64 lower-case hex digits. Codes, order and field paths match the reference and
 * `conformance/vectors/model_artifact.json`.
 */

/** A model release manifest. [adapterLineage] lists adapter digests in the order applied, base first. */
data class ModelArtifact(
    val modelId: String,
    val version: String,
    val weightsDigest: String,
    val tokenizerDigest: String,
    val quantisation: String,
    val license: String,
    val gateReportDigest: String,
    val adapterLineage: List<String> = emptyList(),
    val dataProvenance: List<String> = emptyList(),
) {
    /** Same rules, same order as the reference `ModelArtifact.validate`. */
    fun validate(): List<ValidationIssue> {
        val issues = ArrayList<ValidationIssue>()

        fun missing(path: String) {
            issues += ValidationIssue(Severity.ERROR, "artifact_field_missing", path, "$path required")
        }

        fun invalidDigest(path: String) {
            issues += ValidationIssue(Severity.ERROR, "digest_invalid", path, "digest must be sha256: and 64 lower-case hex digits")
        }

        fun digest(path: String, value: String) {
            if (value.isEmpty()) missing(path) else if (!isDigest(value)) invalidDigest(path)
        }

        if (modelId.isEmpty()) missing("artifact.model_id")
        if (version.isEmpty()) missing("artifact.version")
        digest("artifact.weights_digest", weightsDigest)
        digest("artifact.tokenizer_digest", tokenizerDigest)
        if (quantisation.isEmpty()) missing("artifact.quantisation")
        val seen = HashSet<String>()
        adapterLineage.forEachIndexed { i, entry ->
            val path = "artifact.adapter_lineage[$i]"
            if (!isDigest(entry)) {
                invalidDigest(path)
            } else if (entry in seen) {
                issues += ValidationIssue(Severity.ERROR, "adapter_lineage_duplicate", path, "adapter appears twice in the lineage")
            }
            seen += entry
        }
        if (license.isEmpty()) missing("artifact.license")
        if (dataProvenance.isEmpty()) missing("artifact.data_provenance")
        dataProvenance.forEachIndexed { i, entry -> if (entry.isEmpty()) missing("artifact.data_provenance[$i]") }
        digest("artifact.gate_report_digest", gateReportDigest)
        return issues
    }

    /** True when no finding is error-level. */
    fun isReleasable(): Boolean = validate().none { it.severity == Severity.ERROR }

    companion object {
        private const val PREFIX = "sha256:"

        /** `sha256:` and exactly 64 lower-case hex digits. */
        fun isDigest(text: String): Boolean =
            text.length == PREFIX.length + 64 && text.startsWith(PREFIX) &&
                (PREFIX.length until text.length).all { text[it] in '0'..'9' || text[it] in 'a'..'f' }
    }
}
