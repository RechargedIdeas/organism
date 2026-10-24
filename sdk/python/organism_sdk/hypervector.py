"""Binary Hypervector — A3.2 / D.1. DIM=10000 packed as [u64;157] (10048 bits, top 48 unused)."""
from __future__ import annotations

import secrets
import struct
from dataclasses import dataclass
from typing import Iterable, Sequence

from organism_sdk.errors import DimensionMismatch

DIM = 10_000
WORD_COUNT = 157  # 157 * 64 = 10048 >= 10000
BYTES_LEN = 1250  # 10000 bits / 8


@dataclass(frozen=True)
class Hypervector:
    """Binary hypervector packed big-endian as 157 uint64 words."""

    words: tuple[int, ...]  # length WORD_COUNT

    def __post_init__(self) -> None:
        if len(self.words) != WORD_COUNT:
            raise DimensionMismatch(WORD_COUNT, len(self.words))

    @staticmethod
    def dim() -> int:
        return DIM

    @classmethod
    def zeros(cls) -> Hypervector:
        return cls(tuple(0 for _ in range(WORD_COUNT)))

    @classmethod
    def random(cls, *, rng: secrets.SystemRandom | None = None) -> Hypervector:
        r = rng or secrets.SystemRandom()
        words = [r.getrandbits(64) for _ in range(WORD_COUNT)]
        # Clear unused top 48 bits of last word (bits 10000..10047)
        unused = WORD_COUNT * 64 - DIM
        if unused:
            mask = (1 << (64 - unused)) - 1
            words[-1] &= mask
        return cls(tuple(words))

    @classmethod
    def from_bytes_be(cls, data: bytes | bytearray) -> Hypervector:
        if len(data) != BYTES_LEN:
            raise DimensionMismatch(BYTES_LEN, len(data))
        # Pad to 157*8 = 1256 bytes for struct unpack
        padded = bytes(data) + b"\x00" * (WORD_COUNT * 8 - BYTES_LEN)
        words = struct.unpack("<" + "Q" * WORD_COUNT, padded)
        return cls(tuple(words))

    def to_bytes_be(self) -> bytes:
        packed = struct.pack("<" + "Q" * WORD_COUNT, *self.words)
        return packed[:BYTES_LEN]

    def bind(self, other: Hypervector) -> Hypervector:
        """XOR binding."""
        return Hypervector(tuple(a ^ b for a, b in zip(self.words, other.words)))

    def unbind(self, role: Hypervector) -> Hypervector:
        return self.bind(role)  # XOR is involution

    def permute(self, k: int) -> Hypervector:
        """Circular bit shift left by k positions within DIM bits."""
        k = k % DIM
        if k == 0:
            return self
        bits = self._to_bitlist()
        bits = bits[k:] + bits[:k]
        return Hypervector._from_bitlist(bits)

    def similarity(self, other: Hypervector) -> float:
        """1 - Hamming/D over DIM bits."""
        dist = 0
        for a, b in zip(self.words, other.words):
            dist += (a ^ b).bit_count()
        # Last word may have unused bits already zeroed
        return 1.0 - (dist / DIM)

    @staticmethod
    def bundle(hvs: Sequence[Hypervector]) -> Hypervector:
        """Majority vote with parity tie-break (even → 0)."""
        if not hvs:
            return Hypervector.zeros()
        n = len(hvs)
        out = [0] * WORD_COUNT
        for wi in range(WORD_COUNT):
            for bit in range(64):
                ones = sum(((hv.words[wi] >> bit) & 1) for hv in hvs)
                if ones * 2 > n:
                    out[wi] |= 1 << bit
                elif ones * 2 == n:
                    # parity tie-break: use XOR of all bits at position
                    parity = 0
                    for hv in hvs:
                        parity ^= (hv.words[wi] >> bit) & 1
                    if parity:
                        out[wi] |= 1 << bit
        unused = WORD_COUNT * 64 - DIM
        if unused:
            mask = (1 << (64 - unused)) - 1
            out[-1] &= mask
        return Hypervector(tuple(out))

    def _to_bitlist(self) -> list[int]:
        bits: list[int] = []
        for wi, w in enumerate(self.words):
            limit = 64
            if wi == WORD_COUNT - 1:
                limit = 64 - (WORD_COUNT * 64 - DIM)
            for bit in range(limit):
                bits.append((w >> bit) & 1)
        return bits

    @classmethod
    def _from_bitlist(cls, bits: list[int]) -> Hypervector:
        if len(bits) != DIM:
            raise DimensionMismatch(DIM, len(bits))
        words = [0] * WORD_COUNT
        for i, b in enumerate(bits):
            if b:
                words[i // 64] |= 1 << (i % 64)
        return cls(tuple(words))
