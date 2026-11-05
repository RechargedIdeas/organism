package org.organism.sdk

/** Degradation levels, L0 (full) .. L4 (deterministic engine only). */
enum class Level { L0, L1, L2, L3, L4 }

/** Per-module health as the reference names it. */
object Health {
    const val HEALTHY = "HEALTHY"
    const val DEGRADED = "DEGRADED"
    const val FAILED = "FAILED"
}

/** Inputs to the degradation machine (reference: `HealthSignals`). Field names and defaults match Python. */
data class HealthSignals(
    val hM: Map<String, String> = emptyMap(),
    val cM: Map<String, Double> = emptyMap(),
    val thermal: Double = 1.0,
    val power: Double = 1.0,
    val mem: Double = 0.0,
    val qP95: Double = 1.0,
    val gc: Double = 0.0,
    val byz: Boolean = false,
    val byzCount: Int = 0,
    val traceOk: Boolean = true,
    val detOk: Boolean = true,
    val causalOk: Boolean = true,
    val neuralModules: List<String> = listOf("learned_module_t2"),
    val leadingPredictive: List<String> = listOf("learned_module_t2"),
)

data class Transition(val from: Level, val to: Level, val trigger: String)

/** Hysteresis table in seconds, per target level. */
data class Hysteresis(val down: Map<Level, Double>, val up: Map<Level, Double>) {
    companion object {
        val DEFAULT = Hysteresis(
            down = mapOf(Level.L1 to 5.0, Level.L2 to 30.0, Level.L3 to 60.0, Level.L4 to 10.0),
            up = mapOf(Level.L1 to 120.0, Level.L2 to 300.0, Level.L3 to 600.0, Level.L4 to 900.0),
        )
        val FAST = Hysteresis(
            down = mapOf(Level.L1 to 0.4, Level.L2 to 0.6, Level.L3 to 0.8, Level.L4 to 0.4),
            up = mapOf(Level.L1 to 2.0, Level.L2 to 3.0, Level.L3 to 4.0, Level.L4 to 5.0),
        )
    }
}

/**
 * Port of the reference `DegradationMachine` (virtual clock). Conditions must hold for the hysteresis window
 * before a transition fires; all timers of a rule are armed before the rule is evaluated (no short circuit).
 * Entering L4 recovery needs [humanAck].
 */
class DegradationMachine(private val hysteresis: Hysteresis = Hysteresis.DEFAULT) {
    var level: Level = Level.L0
        private set
    var signals: HealthSignals = HealthSignals()
    var nowS: Double = 0.0
        private set
    var lastTransitionAt: Double = 0.0
        private set
    var humanAck: Boolean = false
    val transitions: MutableList<Transition> = ArrayList()
    private val condSince = HashMap<String, Double?>()

    fun advance(dt: Double): Level? {
        nowS += dt
        return tick()
    }

    private fun confirmed(key: String, holding: Boolean, window: Double): Boolean {
        if (!holding) {
            condSince[key] = null
            return false
        }
        val since = condSince[key]
        if (since == null) {
            condSince[key] = nowS
            return window <= 0.0
        }
        return nowS - since >= window
    }

    private fun sustained(key: String, holding: Boolean, window: Double): Boolean = confirmed("up:$key", holding, window)

    private class Spec(val key: String, val holding: Boolean, val window: Double)

    private fun anyConfirmed(specs: List<Spec>): Boolean = specs.map { confirmed(it.key, it.holding, it.window) }.any { it }

    private fun allSustained(specs: List<Spec>): Boolean = specs.map { sustained(it.key, it.holding, it.window) }.all { it }

    fun tick(): Level? {
        val s = signals
        val prev = level
        val td = hysteresis.down
        val tu = hysteresis.up

        fun neuralDegraded() = s.neuralModules.any { s.hM[it] == Health.DEGRADED }
        fun neuralFailed() = s.leadingPredictive.any { s.hM[it] == Health.FAILED }
        fun neuralHealthy() = s.neuralModules.all { (s.hM[it] ?: Health.HEALTHY) == Health.HEALTHY }
        fun neuralCalibOk(delta: Double) = s.neuralModules.all { (s.cM[it] ?: 1.0) >= 1.0 - ALPHA + delta }
        fun neuralCalibBad(delta: Double) = s.neuralModules.all { (s.cM[it] ?: 1.0) < 1.0 - ALPHA - delta }

        var next: Level? = null
        var trigger = ""

        when (prev) {
            Level.L0 -> {
                val down = anyConfirmed(
                    listOf(
                        Spec("l0_thermal", s.thermal < THERMAL_L1, td.getValue(Level.L1)),
                        Spec("l0_calib", neuralCalibBad(DELTA_1) && s.neuralModules.isNotEmpty(), td.getValue(Level.L1)),
                        Spec("l0_hm", neuralDegraded(), td.getValue(Level.L1)),
                    ),
                )
                if (s.detOk && s.traceOk && down) {
                    next = Level.L1
                    trigger = "module_degraded_or_thermal"
                }
            }
            Level.L1 -> {
                val down = anyConfirmed(
                    listOf(
                        Spec("l1_failed", neuralFailed(), td.getValue(Level.L2)),
                        Spec("l1_calib2", neuralCalibBad(DELTA_2), td.getValue(Level.L2)),
                        Spec("l1_causal", !s.causalOk, td.getValue(Level.L2)),
                    ),
                )
                val up = allSustained(
                    listOf(
                        Spec("l1_thermal", s.thermal > THERMAL_L0, tu.getValue(Level.L1)),
                        Spec("l1_calib", neuralCalibOk(0.0), tu.getValue(Level.L1)),
                        Spec("l1_hm", neuralHealthy(), tu.getValue(Level.L1)),
                    ),
                )
                if (s.detOk && s.traceOk && down) {
                    next = Level.L2
                    trigger = "module_failed"
                } else if (up) {
                    next = Level.L0
                    trigger = "recovery"
                }
            }
            Level.L2 -> {
                val pressure = (s.gc > GC_L3 || s.qP95 > Q_P95_L3) ||
                    s.leadingPredictive.all { (s.hM[it] == Health.FAILED) || ((s.cM[it] ?: 1.0) < 1.0 - ALPHA - DELTA_2) }
                val down = confirmed("l2_gc", pressure, td.getValue(Level.L3))
                val up = allSustained(
                    listOf(
                        Spec("l2_calib", s.neuralModules.any { (s.cM[it] ?: 0.0) >= 1 - ALPHA }, tu.getValue(Level.L2)),
                        Spec("l2_hm", neuralHealthy(), tu.getValue(Level.L2)),
                        Spec("l2_causal", s.causalOk, tu.getValue(Level.L2)),
                    ),
                )
                if (s.detOk && s.traceOk && down) {
                    next = Level.L3
                    trigger = "workspace_pressure"
                } else if (up) {
                    next = Level.L1
                    trigger = "recovery"
                }
            }
            Level.L3 -> {
                val down = anyConfirmed(
                    listOf(
                        Spec("l3_trace", !s.traceOk, td.getValue(Level.L4)),
                        Spec("l3_det", !s.detOk, td.getValue(Level.L4)),
                        Spec("l3_gc", s.gc > GC_L4 || s.mem > MEM_L4, td.getValue(Level.L4)),
                        Spec("l3_qp", s.qP95 > Q_P95_L4, td.getValue(Level.L4)),
                        Spec("l3_byz", s.byzCount >= BYZ_COUNT_L4, td.getValue(Level.L4)),
                    ),
                )
                val up = allSustained(
                    listOf(
                        Spec("l3_ok", s.traceOk && s.detOk, tu.getValue(Level.L3)),
                        Spec("l3_gc", s.gc < GC_L3 && s.qP95 < Q_P95_L3, tu.getValue(Level.L3)),
                        Spec("l3_byz", !s.byz, tu.getValue(Level.L3)),
                    ),
                )
                if (down) {
                    next = Level.L4
                    trigger = "trace_or_byzantine"
                } else if (up) {
                    next = Level.L2
                    trigger = "recovery"
                }
            }
            Level.L4 -> {
                val ready = allSustained(
                    listOf(
                        Spec("l4_ok", s.traceOk && s.detOk, tu.getValue(Level.L4)),
                        Spec("l4_gc", s.gc < GC_L3 && s.mem < MEM_L4, tu.getValue(Level.L4)),
                        Spec("l4_qp", s.qP95 < Q_P95_L3, tu.getValue(Level.L4)),
                        Spec("l4_byz", !s.byz, tu.getValue(Level.L4)),
                    ),
                )
                if (ready && humanAck) {
                    next = Level.L3
                    trigger = "human_ack_recovery"
                    humanAck = false
                }
            }
        }

        if (next != null && next != prev) {
            transitions.add(Transition(prev, next, trigger))
            level = next
            lastTransitionAt = nowS
            condSince.clear()
            return next
        }
        return null
    }

    companion object {
        const val ALPHA = 0.10
        const val DELTA_1 = 0.05
        const val DELTA_2 = 0.15
        const val THERMAL_L1 = 0.20
        const val THERMAL_L0 = 0.50
        const val GC_L3 = 0.50
        const val GC_L4 = 0.85
        const val MEM_L4 = 0.90
        const val Q_P95_L3 = 50.0
        const val Q_P95_L4 = 250.0
        const val BYZ_COUNT_L4 = 3
    }
}
