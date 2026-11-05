package org.organism.sdk

import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Replays `canonical.json` and `signature.json` produced by the Python reference (`conformance/generate.py`). */
class CanonicalSignatureConformanceTest {
    private fun load(name: String): Map<String, Any?> {
        val dir = System.getProperty("organism.conformance.dir") ?: error("organism.conformance.dir not set")
        return Json.parse(File(dir, "$name.json").readText(Charsets.UTF_8)).asMap()
    }

    private fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }

    private fun unhex(s: String): ByteArray = ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }

    @Test
    fun canonicalWriterMatchesReference() {
        val cases = load("canonical")["cases"].asList().map { it.asMap() }
        assertEquals(35, cases.size, "canonical case count changed: regenerate and review the vectors")
        var accepted = 0
        var rejected = 0
        for (case in cases) {
            val name = case["name"] as String
            val value = Json.parseExact(case["input"] as String)
            val error = case["error"] as String?
            if (error != null) {
                val e = assertFailsWith<CanonicalException>(name) { Canonical.text(value) }
                assertEquals(error, e.code, "$name: code")
                rejected++
            } else {
                assertEquals(case["canonical"] as String, Canonical.text(value), "$name: text")
                assertEquals(case["hex"] as String, hex(Canonical.bytes(value)), "$name: bytes")
                accepted++
            }
        }
        assertTrue(accepted > 15 && rejected > 10)
    }

    @Test
    fun canonicalWriterRejectsWhatJsonCannotCarry() {
        assertEquals(Canonical.NON_STRING_KEY, assertFailsWith<CanonicalException> { Canonical.text(mapOf(1 to "a")) }.code)
        assertEquals(Canonical.UNSUPPORTED_TYPE, assertFailsWith<CanonicalException> { Canonical.text(Any()) }.code)
        assertEquals(Canonical.FLOAT_NOT_ALLOWED, assertFailsWith<CanonicalException> { Canonical.text(1.0f) }.code)
        assertEquals("[1,2]", Canonical.text(listOf(1, 2L)))
    }

    @Test
    fun ed25519MatchesReference() {
        val cases = load("signature")["cases"].asList().map { it.asMap() }
        assertEquals(17, cases.size, "signature case count changed: regenerate and review the vectors")
        for (case in cases) {
            val name = case["name"] as String
            val got = Ed25519.verify(unhex(case["public_key"] as String), unhex(case["signature"] as String), unhex(case["message"] as String))
            assertEquals(case["valid"] as Boolean, got, name)
        }
        assertTrue(cases.count { it["valid"] as Boolean } == 4)
    }

    @Test
    fun ed25519NeverThrowsOnGarbage() {
        assertFalse(Ed25519.verify(ByteArray(0), ByteArray(0), ByteArray(0)))
        assertFalse(Ed25519.verify(ByteArray(32) { 0xff.toByte() }, ByteArray(64) { 0xff.toByte() }, byteArrayOf(1)))
    }
}
