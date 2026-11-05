package org.organism.sdk

import java.math.BigInteger

/*
 * Canonical JSON writer (gap C3). Port of `organism_sdk/canonical.py`; the rule is written in docs/INTEROP.md and pinned
 * by `conformance/vectors/canonical.json`.
 *
 * Objects have their keys sorted by Unicode code point (not by UTF-16 unit: they differ for characters above U+FFFF), no
 * whitespace, UTF-8 output, non-ASCII written as itself, and only the escapes listed in the reference. Numbers are
 * integers from -(2^53 - 1) to 2^53 - 1. Floats, NaN and infinities are rejected.
 */

/** The value has no canonical form. [code] is part of the contract. */
class CanonicalException(val code: String, message: String = "") : IllegalArgumentException(if (message.isEmpty()) code else "$code: $message")

object Canonical {
    const val FLOAT_NOT_ALLOWED = "float_not_allowed"
    const val NON_FINITE_NUMBER = "non_finite_number"
    const val INTEGER_OUT_OF_RANGE = "integer_out_of_range"
    const val NON_STRING_KEY = "non_string_key"
    const val INVALID_STRING = "invalid_string"
    const val UNSUPPORTED_TYPE = "unsupported_type"

    private const val MAX_SAFE_INTEGER = 9_007_199_254_740_991L
    private val MAX_SAFE = BigInteger.valueOf(MAX_SAFE_INTEGER)

    /** Canonical text of a value tree: Map with String keys, List, String, Boolean, null and integers (Byte, Short, Int, Long, BigInteger). */
    fun text(value: Any?): String {
        val out = StringBuilder()
        write(value, out)
        return out.toString()
    }

    /** UTF-8 bytes of [text]. */
    fun bytes(value: Any?): ByteArray = text(value).toByteArray(Charsets.UTF_8)

    private fun write(value: Any?, out: StringBuilder) {
        when (value) {
            null -> out.append("null")
            is Boolean -> out.append(if (value) "true" else "false")
            is Byte, is Short, is Int, is Long -> integer(BigInteger.valueOf((value as Number).toLong()), out)
            is BigInteger -> integer(value, out)
            is Double -> reject(value)
            is Float -> reject(value.toDouble())
            is String -> string(value, out)
            is List<*> -> {
                out.append('[')
                value.forEachIndexed { i, item ->
                    if (i > 0) out.append(',')
                    write(item, out)
                }
                out.append(']')
            }
            is Map<*, *> -> {
                for (k in value.keys) if (k !is String) throw CanonicalException(NON_STRING_KEY, k.toString())
                out.append('{')
                val keys = value.keys.map { it as String }.sortedWith(CODE_POINT_ORDER)
                keys.forEachIndexed { i, k ->
                    if (i > 0) out.append(',')
                    string(k, out)
                    out.append(':')
                    write(value[k], out)
                }
                out.append('}')
            }
            else -> throw CanonicalException(UNSUPPORTED_TYPE, value::class.java.simpleName)
        }
    }

    private fun integer(v: BigInteger, out: StringBuilder) {
        if (v.abs() > MAX_SAFE) throw CanonicalException(INTEGER_OUT_OF_RANGE, v.toString())
        out.append(v.toString())
    }

    private fun reject(d: Double): Nothing {
        if (d.isNaN() || d.isInfinite()) throw CanonicalException(NON_FINITE_NUMBER)
        throw CanonicalException(FLOAT_NOT_ALLOWED, d.toString())
    }

    private fun string(s: String, out: StringBuilder) {
        out.append('"')
        var i = 0
        while (i < s.length) {
            val c = s[i]
            if (Character.isHighSurrogate(c)) {
                if (i + 1 >= s.length || !Character.isLowSurrogate(s[i + 1])) throw CanonicalException(INVALID_STRING, "lone surrogate")
                out.append(c).append(s[i + 1])
                i += 2
                continue
            }
            if (Character.isLowSurrogate(c)) throw CanonicalException(INVALID_STRING, "lone surrogate")
            when {
                c == '"' -> out.append("\\\"")
                c == '\\' -> out.append("\\\\")
                c == '\b' -> out.append("\\b")
                c == '\u000C' -> out.append("\\f")
                c == '\n' -> out.append("\\n")
                c == '\r' -> out.append("\\r")
                c == '\t' -> out.append("\\t")
                c < ' ' -> out.append("\\u00").append(HEX[c.code shr 4]).append(HEX[c.code and 15])
                else -> out.append(c)
            }
            i++
        }
        out.append('"')
    }

    private const val HEX = "0123456789abcdef"

    /** Orders strings by code point, the order of their UTF-8 bytes. `String.compareTo` orders by UTF-16 unit and is not the same. */
    private val CODE_POINT_ORDER = Comparator<String> { a, b ->
        var i = 0
        var j = 0
        while (i < a.length && j < b.length) {
            val ca = a.codePointAt(i)
            val cb = b.codePointAt(j)
            if (ca != cb) return@Comparator ca.compareTo(cb)
            i += Character.charCount(ca)
            j += Character.charCount(cb)
        }
        (a.length - i).compareTo(b.length - j)
    }
}
