package org.organism.sdk

/*
 * Health and drain (K1b task 7, gap B6). Port of `health.py` (`HealthReport`) and the two calls that `registry.py` makes on
 * a module (`OrganismModule.health` and `OrganismModule.on_drain`, in `module.py`). The Python registry holds the module
 * object; this port holds [ModuleHooks]. Vectors: health.json.
 */

/** Health states (reference `HealthReport.status`: HEALTHY, DEGRADED or FAILED). */
enum class HealthStatus { HEALTHY, DEGRADED, FAILED }

/**
 * A module's health answer (reference `HealthReport`). The reference also carries active failures and probe results;
 * the vectors compare only the status and the score, so those are not ported yet.
 */
data class HealthReport(val moduleId: String, val status: HealthStatus, val score: Double = 1.0)

/**
 * The calls the registry makes on a module it holds. [health] is called on each query. [onDrain] is called once when the
 * module is deregistered, with the deadline in epoch milliseconds. A module with nothing to drain keeps the default.
 */
interface ModuleHooks {
    fun health(): HealthReport

    fun onDrain(deadlineMs: Long) {}
}
