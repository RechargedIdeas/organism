"""One interface over every encoder the benchmark can load.

Each adapter exposes `dim`, `params` and `encode(texts) -> float32 array of shape (n, dim)`. The
heavy libraries are imported inside the constructors, so importing this module stays cheap and the
tests can use the hash encoder without downloading anything.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from organism_bench.specs import ModelSpec


class Encoder(Protocol):
    dim: int
    params: int

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


class SentenceEncoder:
    """A transformer encoder loaded through sentence-transformers, on CPU, L2-normalised."""

    def __init__(self, spec: ModelSpec) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        # float32 for every model. Some checkpoints ship in bfloat16, which is much slower on CPU.
        self._model = SentenceTransformer(
            str(spec.path), device="cpu", model_kwargs={"dtype": torch.float32}
        )
        self._prefix = spec.query_prefix
        self.dim = int(self._model.get_embedding_dimension() or 0)
        self.params = int(sum(p.numel() for p in self._model.parameters()))

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode(
            [self._prefix + text for text in texts],
            batch_size=32,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


class StaticEncoder:
    """A Model2Vec static embedding table: token vectors averaged, no transformer forward pass."""

    def __init__(self, spec: ModelSpec) -> None:
        from model2vec import StaticModel

        self._model = StaticModel.from_pretrained(str(spec.path))
        self.dim = int(self._model.dim)
        self.params = int(np.prod(self._model.embedding.shape))
        self._prefix = spec.query_prefix

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode([self._prefix + text for text in texts])
        return np.asarray(vectors, dtype=np.float32)


class HashEncoder:
    """Signed token hashing into a fixed number of buckets. Deterministic and dependency-free.

    It is the control for the test suite and the smoke run. It is not a candidate for the router.
    """

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim
        self.params = 0

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in re.findall(r"[a-z0-9@.]+", text.lower()):
                digest = int.from_bytes(
                    hashlib.blake2b(token.encode(), digest_size=8).digest(), "little"
                )
                sign = 1.0 if (digest >> 63) & 1 == 0 else -1.0
                out[row, digest % self.dim] += sign
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return np.asarray(out / np.maximum(norms, 1e-9), dtype=np.float32)


def load_encoder(spec: ModelSpec) -> Encoder:
    if spec.kind == "sentence":
        return SentenceEncoder(spec)
    if spec.kind == "static":
        return StaticEncoder(spec)
    if spec.kind == "hash":
        return HashEncoder()
    raise ValueError(f"unknown encoder kind {spec.kind!r} for {spec.name}")
