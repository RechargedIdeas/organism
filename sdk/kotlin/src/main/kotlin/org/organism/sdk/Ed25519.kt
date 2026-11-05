package org.organism.sdk

import java.math.BigInteger
import java.security.MessageDigest

/*
 * Ed25519 signature verification (gap A9), RFC 8032 section 5.1.7, in pure Kotlin on BigInteger.
 *
 * java.security has Ed25519 only from JDK 15 and this SDK targets JVM 11 (and Android), so the check is written out here.
 * Verify only: there is no signing and no key generation in this SDK. The arithmetic is not constant time, which is fine
 * because every input to a verification is public.
 *
 * The rules match the Python reference (`organism_sdk.signing.verify`, over OpenSSL) on every case in
 * `conformance/vectors/signature.json`:
 *  - a public key or signature of the wrong length is invalid, never an exception;
 *  - the public key and R must decode to a curve point, with y below 2^255 - 19;
 *  - S must be below the group order L (a signature with S + L is rejected: no malleability);
 *  - the check is cofactorless: [S]B == R + [k]A.
 */
object Ed25519 {
    const val PUBLIC_KEY_BYTES = 32
    const val SIGNATURE_BYTES = 64

    private val P = BigInteger.ONE.shiftLeft(255) - BigInteger.valueOf(19)
    private val L = BigInteger.ONE.shiftLeft(252) + BigInteger("27742317777372353535851937790883648493")
    private val D = BigInteger.valueOf(-121665).multiply(BigInteger.valueOf(121666).modInverse(P)).mod(P)
    private val D2 = D.shiftLeft(1).mod(P)
    private val SQRT_M1 = BigInteger.valueOf(2).modPow(P.subtract(BigInteger.ONE).shiftRight(2), P)

    /** A point in extended homogeneous coordinates (X, Y, Z, T) with x = X/Z, y = Y/Z and T = XY/Z. */
    private class Point(val x: BigInteger, val y: BigInteger, val z: BigInteger, val t: BigInteger)

    private val IDENTITY = Point(BigInteger.ZERO, BigInteger.ONE, BigInteger.ONE, BigInteger.ZERO)

    private val BASE: Point by lazy {
        // By = 4/5; the base point's x is the even root.
        val y = BigInteger.valueOf(4).multiply(BigInteger.valueOf(5).modInverse(P)).mod(P)
        val x = recoverX(y, 0)!!
        Point(x, y, BigInteger.ONE, x.multiply(y).mod(P))
    }

    /** True when [signature] is a valid Ed25519 signature of [message] under [publicKey]. Malformed input is false. */
    fun verify(publicKey: ByteArray, signature: ByteArray, message: ByteArray): Boolean {
        if (publicKey.size != PUBLIC_KEY_BYTES || signature.size != SIGNATURE_BYTES) return false
        val a = decodePoint(publicKey) ?: return false
        val rBytes = signature.copyOfRange(0, 32)
        val r = decodePoint(rBytes) ?: return false
        val s = littleEndian(signature.copyOfRange(32, 64))
        if (s >= L) return false
        val sha = MessageDigest.getInstance("SHA-512")
        sha.update(rBytes)
        sha.update(publicKey)
        sha.update(message)
        val k = littleEndian(sha.digest()).mod(L)
        return equal(multiply(s, BASE), add(r, multiply(k, a)))
    }

    private fun littleEndian(bytes: ByteArray): BigInteger {
        val be = ByteArray(bytes.size) { bytes[bytes.size - 1 - it] }
        return BigInteger(1, be)
    }

    private fun recoverX(y: BigInteger, sign: Int): BigInteger? {
        if (y >= P) return null
        val y2 = y.multiply(y).mod(P)
        val u = y2.subtract(BigInteger.ONE).mod(P)
        val v = D.multiply(y2).add(BigInteger.ONE).mod(P)
        val x2 = u.multiply(v.modInverse(P)).mod(P)
        if (x2.signum() == 0) return if (sign == 1) null else BigInteger.ZERO
        var x = x2.modPow(P.add(BigInteger.valueOf(3)).shiftRight(3), P)
        if (x.multiply(x).subtract(x2).mod(P).signum() != 0) x = x.multiply(SQRT_M1).mod(P)
        if (x.multiply(x).subtract(x2).mod(P).signum() != 0) return null
        if (x.testBit(0) != (sign == 1)) x = P.subtract(x)
        return x
    }

    private fun decodePoint(bytes: ByteArray): Point? {
        val raw = littleEndian(bytes)
        val sign = if (raw.testBit(255)) 1 else 0
        val y = raw.clearBit(255)
        val x = recoverX(y, sign) ?: return null
        return Point(x, y, BigInteger.ONE, x.multiply(y).mod(P))
    }

    private fun add(p: Point, q: Point): Point {
        val a = p.y.subtract(p.x).multiply(q.y.subtract(q.x)).mod(P)
        val b = p.y.add(p.x).multiply(q.y.add(q.x)).mod(P)
        val c = p.t.multiply(D2).multiply(q.t).mod(P)
        val d = p.z.shiftLeft(1).multiply(q.z).mod(P)
        val e = b.subtract(a)
        val f = d.subtract(c)
        val g = d.add(c)
        val h = b.add(a)
        return Point(e.multiply(f).mod(P), g.multiply(h).mod(P), f.multiply(g).mod(P), e.multiply(h).mod(P))
    }

    private fun multiply(scalar: BigInteger, point: Point): Point {
        var result = IDENTITY
        var addend = point
        for (i in 0 until scalar.bitLength()) {
            if (scalar.testBit(i)) result = add(result, addend)
            addend = add(addend, addend)
        }
        return result
    }

    private fun equal(p: Point, q: Point): Boolean =
        p.x.multiply(q.z).subtract(q.x.multiply(p.z)).mod(P).signum() == 0 &&
            p.y.multiply(q.z).subtract(q.y.multiply(p.z)).mod(P).signum() == 0
}
