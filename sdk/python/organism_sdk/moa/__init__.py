"""Mixture-of-experts layer on Organism (v1.11). Design record: docs/v1.11/MOA_LAYER.md."""

from organism_sdk.moa.aggregate import MAX_EXPERTS_PER_REQUEST, AggregationResult, aggregate
from organism_sdk.moa.experts import (
    BaseExpert,
    CapabilityDescriptor,
    Expert,
    ExpertOutput,
    register_experts,
)
from organism_sdk.moa.guardrails import (
    GroundednessGuard,
    GuardrailSpec,
    GuardVerdict,
    InjectionGuard,
)
from organism_sdk.moa.pipeline import ROUTE_BLOCKED, ROUTE_DETERMINISTIC, MoAPipeline, MoAResult
from organism_sdk.moa.reference import Extractor, IntentClassifier, reference_experts
from organism_sdk.moa.scorer import LexicalScorer, RouteDecision
from organism_sdk.moa.shadow import PRECISION_GATE, RoutingReport, evaluate, load_labeled
from organism_sdk.moa.tiers import MoATier, TierController, TierInputs, select_tier

__all__ = [
    "MAX_EXPERTS_PER_REQUEST",
    "PRECISION_GATE",
    "ROUTE_BLOCKED",
    "ROUTE_DETERMINISTIC",
    "AggregationResult",
    "BaseExpert",
    "CapabilityDescriptor",
    "Expert",
    "ExpertOutput",
    "Extractor",
    "GroundednessGuard",
    "GuardVerdict",
    "GuardrailSpec",
    "InjectionGuard",
    "IntentClassifier",
    "LexicalScorer",
    "MoAPipeline",
    "MoAResult",
    "MoATier",
    "RouteDecision",
    "RoutingReport",
    "TierController",
    "TierInputs",
    "aggregate",
    "evaluate",
    "load_labeled",
    "reference_experts",
    "register_experts",
    "select_tier",
]
