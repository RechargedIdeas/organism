package org.organism.sdk

/**
 * Binary hypervector, bit-for-bit compatible with the Python reference (`organism_sdk.hypervector`).
 * DIM = 10,000 bits packed into 157 unsigned 64-bit words; bit i lives in word i / 64 at position i % 64.
 * The 48 unused top bits of the last word are always zero.
 */
class Hypervector(val words: LongArray) {
    init {
        if (words.size != WORD_COUNT) throw DimensionMismatch(WORD_COUNT, words.size)
    }

    /** XOR binding. XOR is an involution, so [unbind] is the same operation. */
    fun bind(other: Hypervector): Hypervector = Hypervector(LongArray(WORD_COUNT) { words[it] xor other.words[it] })

    fun unbind(role: Hypervector): Hypervector = bind(role)

    /** Circular shift: result bit i is source bit (i + k) mod DIM. */
    fun permute(k: Long): Hypervector {
        val shift = Math.floorMod(k, DIM.toLong()).toInt()
        if (shift == 0) return this
        val out = LongArray(WORD_COUNT)
        for (i in 0 until DIM) {
            if (bit((i + shift) % DIM)) out[i ushr 6] = out[i ushr 6] or (1L shl (i and 63))
        }
        return Hypervector(out)
    }

    /** 1 - Hamming distance / DIM. */
    fun similarity(other: Hypervector): Double {
        var dist = 0
        for (i in 0 until WORD_COUNT) dist += java.lang.Long.bitCount(words[i] xor other.words[i])
        return 1.0 - dist.toDouble() / DIM
    }

    fun bit(i: Int): Boolean = ((words[i ushr 6] ushr (i and 63)) and 1L) == 1L

    fun toHex(): List<String> = words.map { java.lang.Long.toHexString(it).padStart(16, '0') }

    override fun equals(other: Any?): Boolean = other is Hypervector && words.contentEquals(other.words)
    override fun hashCode(): Int = words.contentHashCode()

    companion object {
        const val DIM = 10_000
        const val WORD_COUNT = 157
        private const val UNUSED_BITS = WORD_COUNT * 64 - DIM
        private const val LAST_MASK = -1L ushr UNUSED_BITS

        fun zeros(): Hypervector = Hypervector(LongArray(WORD_COUNT))

        fun fromHex(hex: List<String>): Hypervector =
            Hypervector(LongArray(hex.size) { java.lang.Long.parseUnsignedLong(hex[it], 16) })

        /** Random hypervector; random streams differ from Python's by design (vectors carry explicit words). */
        fun random(random: java.util.Random): Hypervector {
            val w = LongArray(WORD_COUNT) { random.nextLong() }
            w[WORD_COUNT - 1] = w[WORD_COUNT - 1] and LAST_MASK
            return Hypervector(w)
        }

        /** Majority vote per bit; on an exact tie the bit is the parity (XOR) of the inputs' bits. Empty -> zeros. */
        fun bundle(hvs: List<Hypervector>): Hypervector {
            if (hvs.isEmpty()) return zeros()
            val n = hvs.size
            val out = LongArray(WORD_COUNT)
            for (wi in 0 until WORD_COUNT) {
                var word = 0L
                for (b in 0 until 64) {
                    var ones = 0
                    for (hv in hvs) ones += ((hv.words[wi] ushr b) and 1L).toInt()
                    val set = when {
                        ones * 2 > n -> true
                        ones * 2 == n -> ones % 2 == 1
                        else -> false
                    }
                    if (set) word = word or (1L shl b)
                }
                out[wi] = word
            }
            out[WORD_COUNT - 1] = out[WORD_COUNT - 1] and LAST_MASK
            return Hypervector(out)
        }
    }
}

class DimensionMismatch(val expected: Int, val actual: Int) :
    IllegalArgumentException("hypervector dimension mismatch: expected $expected, got $actual")
