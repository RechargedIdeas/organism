package org.organism.sdk

/**
 * Minimal JSON reader used for conformance vectors, op logs and manifests. Objects become [Map], arrays [List],
 * numbers [Double] (use [asInt] / [asLong] for integers), plus String, Boolean and null.
 */
object Json {
    fun parse(text: String): Any? {
        val p = Parser(text, exact = false)
        val v = p.value()
        p.ws()
        require(p.i == text.length) { "trailing data at ${p.i}" }
        return v
    }

    /**
     * Like [parse], but keeps what the canonical writer ([Canonical]) needs to see. Integer literals become [Long]
     * (or [java.math.BigInteger] beyond 64 bits), every other number is a [Double], and `NaN`, `Infinity` and
     * `-Infinity` are accepted as doubles, as Python's `json.loads` does, so the writer can reject them by code.
     */
    fun parseExact(text: String): Any? {
        val p = Parser(text, exact = true)
        val v = p.value()
        p.ws()
        require(p.i == text.length) { "trailing data at ${p.i}" }
        return v
    }

    private class Parser(val s: String, val exact: Boolean) {
        var i = 0

        fun ws() {
            while (i < s.length && s[i].isWhitespace()) i++
        }

        fun value(): Any? {
            ws()
            require(i < s.length) { "unexpected end" }
            val c = s[i]
            return when {
                c == '{' -> obj()
                c == '[' -> arr()
                c == '"' -> str()
                c == 't' -> lit("true", true)
                c == 'f' -> lit("false", false)
                c == 'n' -> lit("null", null)
                exact && c == 'N' -> lit("NaN", Double.NaN)
                exact && c == 'I' -> lit("Infinity", Double.POSITIVE_INFINITY)
                exact && s.startsWith("-Infinity", i) -> lit("-Infinity", Double.NEGATIVE_INFINITY)
                c == '-' || c.isDigit() -> num()
                else -> error("unexpected '$c' at $i")
            }
        }

        private fun lit(word: String, v: Any?): Any? {
            require(s.startsWith(word, i)) { "bad literal at $i" }
            i += word.length
            return v
        }

        private fun num(): Any {
            val st = i
            while (i < s.length && (s[i].isDigit() || s[i] == '+' || s[i] == '-' || s[i] == '.' || s[i] == 'e' || s[i] == 'E')) i++
            val text = s.substring(st, i)
            if (exact && text.none { it == '.' || it == 'e' || it == 'E' }) {
                val big = java.math.BigInteger(text)
                return if (big.bitLength() < 64) big.toLong() else big
            }
            return text.toDouble()
        }

        private fun str(): String {
            i++
            val sb = StringBuilder()
            while (true) {
                require(i < s.length) { "unterminated string" }
                val c = s[i++]
                if (c == '"') return sb.toString()
                if (c != '\\') {
                    sb.append(c)
                    continue
                }
                val e = s[i++]
                when (e) {
                    '"', '\\', '/' -> sb.append(e)
                    'b' -> sb.append('\b')
                    'f' -> sb.append('\u000C')
                    'n' -> sb.append('\n')
                    'r' -> sb.append('\r')
                    't' -> sb.append('\t')
                    'u' -> {
                        sb.append(s.substring(i, i + 4).toInt(16).toChar())
                        i += 4
                    }
                    else -> error("bad escape $e")
                }
            }
        }

        private fun arr(): List<Any?> {
            i++
            val out = ArrayList<Any?>()
            ws()
            if (s[i] == ']') {
                i++
                return out
            }
            while (true) {
                out.add(value())
                ws()
                val d = s[i++]
                if (d == ']') return out
                require(d == ',') { "expected , or ] at ${i - 1}" }
            }
        }

        private fun obj(): Map<String, Any?> {
            i++
            val out = LinkedHashMap<String, Any?>()
            ws()
            if (s[i] == '}') {
                i++
                return out
            }
            while (true) {
                ws()
                val k = str()
                ws()
                require(s[i++] == ':') { "expected : at ${i - 1}" }
                out[k] = value()
                ws()
                val d = s[i++]
                if (d == '}') return out
                require(d == ',') { "expected , or } at ${i - 1}" }
            }
        }
    }
}

@Suppress("UNCHECKED_CAST")
fun Any?.asMap(): Map<String, Any?> = this as Map<String, Any?>

@Suppress("UNCHECKED_CAST")
fun Any?.asList(): List<Any?> = this as List<Any?>

fun Any?.asDouble(): Double = (this as Number).toDouble()
fun Any?.asInt(): Int = (this as Number).toInt()
fun Any?.asLong(): Long = (this as Number).toLong()
