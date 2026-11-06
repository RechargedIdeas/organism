"""Installable reference substrate modules (OC-8).

Import individual modules as top-level packages (``reservoir``, ``hdc_module``,
…); this meta-package documents which substrates ship in the wheel and exposes
``contract_factory``.
"""
from __future__ import annotations

from organism_sdk.contract_factory import digest_of, make_contract

REFERENCE_MODULES: tuple[str, ...] = (
    "deterministic_engine",
    "learned_module",
    "reservoir",
    "hdc_module",
    "kernel_module",
    "energy_hopfield",
    "spectral",
    "snn_sentinel",
    "neurosymbolic",
)

__all__ = ["REFERENCE_MODULES", "digest_of", "make_contract"]
