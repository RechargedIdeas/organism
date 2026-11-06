"""Thin SubstrateContract factory for reference modules (IMP-22).

Re-exports ``organism_sdk.contract_factory`` (OC-8). Prefer importing from
``organism_sdk.contract_factory`` in new code.
"""
from __future__ import annotations

from organism_sdk.contract_factory import digest_of, make_contract

__all__ = ["digest_of", "make_contract"]
