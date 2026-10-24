"""Hypervector bind/unbind exactness (D.1 / A3.2)."""
from organism_sdk.hypervector import DIM, Hypervector


def test_dim():
    assert Hypervector.dim() == 10000
    assert DIM == 10000


def test_bind_unbind_exact():
    a = Hypervector.random()
    b = Hypervector.random()
    bound = a.bind(b)
    assert bound.unbind(a).to_bytes_be() == b.to_bytes_be()
    assert bound.unbind(b).to_bytes_be() == a.to_bytes_be()


def test_bytes_roundtrip():
    hv = Hypervector.random()
    raw = hv.to_bytes_be()
    assert len(raw) == 1250
    assert Hypervector.from_bytes_be(raw).to_bytes_be() == raw


def test_self_similarity():
    hv = Hypervector.random()
    assert hv.similarity(hv) == 1.0
