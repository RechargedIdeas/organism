"""SubstrateContract dataclasses + validation — A3.1 + Amendment 3.1 (R-6)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Literal

from organism_sdk.errors import RegistrationRejected


class Severity(str, Enum):
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    code: str
    field_path: str
    message: str
    params: dict[str, str] = field(default_factory=dict)


# ---- Enums mirroring proto (string labels for authoring) ----

class ModuleRole(str, Enum):
    PERCEPTION = "PERCEPTION"
    PREDICTION = "PREDICTION"
    SENTINEL = "SENTINEL"
    SOLVER = "SOLVER"
    VERIFIER = "VERIFIER"
    GOVERNANCE = "GOVERNANCE"
    FEATURE_EXTRACTOR = "FEATURE_EXTRACTOR"
    MEMORY = "MEMORY"
    ACTUATOR = "ACTUATOR"
    FRONTEND = "FRONTEND"


class ReliabilityTier(str, Enum):
    T0_DETERMINISTIC = "T0_DETERMINISTIC"
    T1_CALIBRATED_NONLEARNED = "T1_CALIBRATED_NONLEARNED"
    T2_LEARNED_CALIBRATED = "T2_LEARNED_CALIBRATED"
    T3_LEARNED_UNCALIBRATED = "T3_LEARNED_UNCALIBRATED"


class MaxSafetyTier(str, Enum):
    RESEARCH = "RESEARCH"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Modality(str, Enum):
    DENSE_VECTOR = "DENSE_VECTOR"
    TEMPORAL_STREAM = "TEMPORAL_STREAM"
    SPIKE_TRAIN = "SPIKE_TRAIN"
    SYMBOL_GRAPH = "SYMBOL_GRAPH"
    WAVELET_COEFFS = "WAVELET_COEFFS"
    PHYSICAL_SENSOR = "PHYSICAL_SENSOR"
    HYPERVECTOR = "HYPERVECTOR"
    TABULAR = "TABULAR"
    TEXT = "TEXT"
    IMAGE = "IMAGE"


class DataType(str, Enum):
    FP32 = "FP32"
    FP16 = "FP16"
    INT8 = "INT8"
    BINARY = "BINARY"
    BOOL = "BOOL"
    INT64 = "INT64"


class OutputForm(str, Enum):
    HYPERVECTOR = "HYPERVECTOR"
    SPIKE_TRAIN = "SPIKE_TRAIN"
    ENERGY_GRADIENT = "ENERGY_GRADIENT"
    SYMBOLIC_TRIPLE = "SYMBOLIC_TRIPLE"
    PROBABILITY_INTERVAL = "PROBABILITY_INTERVAL"
    SCALAR = "SCALAR"
    ASSIGNMENT_CERTIFICATE = "ASSIGNMENT_CERTIFICATE"
    FEATURE_VECTOR = "FEATURE_VECTOR"
    JUSTIFICATION_TOKEN = "JUSTIFICATION_TOKEN"


class UncertaintyKind(str, Enum):
    NONE = "NONE"
    CONFORMAL_INTERVAL = "CONFORMAL_INTERVAL"
    ENSEMBLE_SPREAD = "ENSEMBLE_SPREAD"
    ENERGY_LANDSCAPE = "ENERGY_LANDSCAPE"
    SYMBOLIC_PROOF = "SYMBOLIC_PROOF"


class Determinism(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    SEEDED = "SEEDED"
    STOCHASTIC = "STOCHASTIC"


class EscalationKind(str, Enum):
    NONE = "NONE"
    PROBE_FAILURES = "PROBE_FAILURES"
    DURATION = "DURATION"
    PROBE_OR_DURATION = "PROBE_OR_DURATION"


class JustificationKind(str, Enum):
    NONE = "NONE"
    CAUSAL_CERT = "CAUSAL_CERT"
    KERNEL_BOUND = "KERNEL_BOUND"
    RULE_TRACE = "RULE_TRACE"
    ENERGY_CERT = "ENERGY_CERT"
    SYMBOLIC_PROOF = "SYMBOLIC_PROOF"


class RecoveryKind(str, Enum):
    RESTART = "RESTART"
    RESTORE_SNAPSHOT = "RESTORE_SNAPSHOT"
    DEMOTE = "DEMOTE"
    HOT_SWAP = "HOT_SWAP"
    MANUAL = "MANUAL"


class DegradationKind(str, Enum):
    SILENT_ACCURACY_LOSS = "SILENT_ACCURACY_LOSS"
    SPIKE_SILENCE = "SPIKE_SILENCE"
    ENERGY_DIVERGENCE = "ENERGY_DIVERGENCE"
    SYMBOL_GROUNDING_FAILURE = "SYMBOL_GROUNDING_FAILURE"
    CALIBRATION_DRIFT = "CALIBRATION_DRIFT"
    TIMEOUT = "TIMEOUT"
    CRASH = "CRASH"


class BudgetClass(str, Enum):
    LEAN = "LEAN"
    STANDARD = "STANDARD"
    HEAVY = "HEAVY"
    RESEARCH = "RESEARCH"


class HardwareRequirement(str, Enum):
    NONE = "NONE"
    NEUROMORPHIC = "NEUROMORPHIC"
    EVENT_CAMERA = "EVENT_CAMERA"
    PHYSICAL_SUBSTRATE = "PHYSICAL_SUBSTRATE"
    TPU_NPU = "TPU_NPU"


# ---- Nested contract types ----

@dataclass(frozen=True)
class Shape:
    dims: tuple[int, ...]
    dtype: DataType


@dataclass(frozen=True)
class SamplingRequirement:
    rate_hz: float
    window_len: int
    requires_sync: bool = False


@dataclass(frozen=True)
class Identity:
    module_id: str
    version: str
    author: str
    license: str
    role: ModuleRole
    artifact_digest: bytes
    signatures_b64: tuple[bytes, ...] = ()


@dataclass(frozen=True)
class PerceptionSignature:
    modalities: tuple[Modality, ...]
    shapes: dict[str, Shape] = field(default_factory=dict)
    sampling: dict[str, SamplingRequirement] = field(default_factory=dict)
    required_modalities: tuple[Modality, ...] = ()  # R-7


@dataclass(frozen=True)
class EmissionSignature:
    output_form: OutputForm
    shape: Shape
    uncertainty: UncertaintyKind
    determinism: Determinism
    requires_justification_for: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResourceVector:
    cpu_cores: float = 1.0
    gpu_fraction: float = 0.0
    memory_mb: float = 256.0
    network_mbps: float = 0.0
    energy_watts: float = 5.0


@dataclass(frozen=True)
class MetabolicProfile:
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    energy_per_inference_j: float
    memory_footprint_mb: float
    memory_peak_mb: float
    requires_gradient_training: bool = False
    requires_gpu: bool = False
    requires_special_hardware: HardwareRequirement = HardwareRequirement.NONE
    max_concurrent_invocations: int = 1
    metabolic_budget_class: BudgetClass = BudgetClass.LEAN
    declared_share: ResourceVector = field(default_factory=ResourceVector)


@dataclass(frozen=True)
class HealthHttp:
    url: str
    expected_status: str = "200"
    timeout_ms: int = 500


@dataclass(frozen=True)
class HealthRpc:
    method_fqn: str
    timeout_ms: int = 2000


@dataclass(frozen=True)
class HealthStream:
    topic: str
    expected_period_ms: int
    stall_timeout_ms: int


HealthProbeKind = HealthHttp | HealthRpc | HealthStream


@dataclass(frozen=True)
class HealthProbe:
    kind: HealthProbeKind

    def timeout_ms(self) -> int:
        k = self.kind
        if isinstance(k, HealthHttp):
            return k.timeout_ms
        if isinstance(k, HealthRpc):
            return k.timeout_ms
        return k.stall_timeout_ms

    def effective_cadence_ms(self, probe_interval_ms: int) -> int:
        k = self.kind
        if isinstance(k, HealthStream):
            return k.expected_period_ms
        return probe_interval_ms


@dataclass(frozen=True)
class HealthEscalationPolicy:
    """A4.1 defaults with R-1: escalate_on_probe_unreachable=False."""

    kind: EscalationKind = EscalationKind.PROBE_OR_DURATION
    consecutive_probe_failures: int = 3
    degraded_duration_ms: int = 15_000
    escalate_on_probe_timeout: bool = True
    escalate_on_probe_unreachable: bool = False  # R-1 / Amendment 4.1
    probe_interval_ms: int = 5_000


@dataclass(frozen=True)
class FailureMode:
    name: str
    observable_signal: str
    expected_degradation: DegradationKind
    detection_latency_budget_ms: float
    detection_kind: str = "heartbeat"  # simplified authoring tag


@dataclass(frozen=True)
class RecoveryProcedure:
    kind: RecoveryKind = RecoveryKind.RESTART
    max_attempts: int = 3
    backoff_ms_initial: int = 100
    backoff_multiplier: float = 2.0
    backoff_ms_max: int = 5000
    preconditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class FailureSignature:
    """Full FailureSignature including escalation (R-6 / Amendment 3.1)."""

    modes: tuple[FailureMode, ...]
    probe: HealthProbe
    recovery: RecoveryProcedure
    escalation: HealthEscalationPolicy

    def probe_timeout_ms(self) -> int:
        return self.probe.timeout_ms()

    def effective_probe_cadence_ms(self) -> int:
        return self.probe.effective_cadence_ms(self.escalation.probe_interval_ms)

    def validate(self) -> list[ValidationIssue]:
        """Enforces A4.3 / REG-8, REG-9, REG-10."""
        issues: list[ValidationIssue] = []
        esc = self.escalation
        timeout = self.probe_timeout_ms()
        cadence = self.effective_probe_cadence_ms()

        # REG-8
        if esc.escalate_on_probe_timeout and timeout >= esc.degraded_duration_ms:
            issues.append(
                ValidationIssue(
                    Severity.ERROR,
                    "escalation_policy_inconsistent",
                    "failure.escalation",
                    "escalate_on_probe_timeout requires probe timeout < degraded_duration_ms",
                )
            )
        # REG-9
        if esc.degraded_duration_ms < 3 * cadence:
            issues.append(
                ValidationIssue(
                    Severity.ERROR,
                    "escalation_policy_inconsistent",
                    "failure.escalation",
                    "degraded_duration_ms must be >= 3 * probe cadence",
                )
            )
        # REG-10
        if timeout >= cadence:
            issues.append(
                ValidationIssue(
                    Severity.ERROR,
                    "health_probe_inconsistent",
                    "failure.probe",
                    "probe timeout must be < probe cadence",
                )
            )
        return issues


@dataclass(frozen=True)
class SafetyDeclaration:
    reliability_tier: ReliabilityTier
    may_actuate: bool
    requires_causal_certificate: bool = False
    requires_cross_check: bool = False
    cross_check_eligible_roles: tuple[ModuleRole, ...] = ()
    max_safety_tier: MaxSafetyTier = MaxSafetyTier.HIGH


@dataclass(frozen=True)
class CapabilityScopes:
    read_roles: tuple[str, ...] = ()
    write_roles: tuple[str, ...] = ()
    read_tags: tuple[str, ...] = ()
    write_tags: tuple[str, ...] = ()
    can_emit_control_affecting: bool = False
    allowed_channels: tuple[str, ...] = ()
    can_override_trace_sink: bool = False
    can_override_trace_sink_exploration: bool = False
    exploration_trace_sink_id: str = ""


@dataclass(frozen=True)
class Channel:
    channel_id: str
    producer_module: str
    consumer_modules: tuple[str, ...]
    payload_modality: Modality
    payload_shape: Shape
    delivery: str = "AT_LEAST_ONCE"
    logged_for_trace: bool = True


@dataclass(frozen=True)
class JustificationSpec:
    kind: JustificationKind
    format: str = ""
    required_fields: tuple[str, ...] = ()
    checkable_by: tuple[ModuleRole, ...] = ()


@dataclass(frozen=True)
class PromotionCriteria:
    shadow_invocations_min: int = 0
    max_incumbent_error_delta: float = 0.0
    required_gates: tuple[str, ...] = ()
    approver_role: ModuleRole = ModuleRole.GOVERNANCE
    causal_review_required: bool = False


@dataclass(frozen=True)
class Lifecycle:
    hot_swap_supported: bool = False
    rollback_artifact_digest: bytes = b""
    shadow_validation_required: bool = False
    promotion: PromotionCriteria = field(default_factory=PromotionCriteria)
    disallowed_runtimes: tuple[str, ...] = ()
    # IMP-9 (v0.2): apoptosis gate; T0 must keep False
    self_termination_permitted: bool = False
    replaceable: bool = False
    max_idle_time_s: float | None = None


@dataclass(frozen=True)
class SubstrateContract:
    identity: Identity
    perception: PerceptionSignature
    emission: EmissionSignature
    metabolic: MetabolicProfile
    failure: FailureSignature
    safety: SafetyDeclaration
    lifecycle: Lifecycle
    capabilities: CapabilityScopes
    channels: tuple[Channel, ...] = ()
    justification: JustificationSpec = field(
        default_factory=lambda: JustificationSpec(kind=JustificationKind.NONE)
    )

    def validate(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        issues.extend(self.failure.validate())

        # Basic identity
        if not self.identity.module_id:
            issues.append(
                ValidationIssue(Severity.ERROR, "identity_missing", "identity.module_id", "module_id required")
            )
        if not self.identity.version:
            issues.append(
                ValidationIssue(Severity.ERROR, "identity_missing", "identity.version", "version required")
            )

        # R-8 / REG-7 exploration sink
        if self.capabilities.can_override_trace_sink_exploration:
            if self.safety.reliability_tier not in (
                ReliabilityTier.T0_DETERMINISTIC,
                ReliabilityTier.T1_CALIBRATED_NONLEARNED,
                ReliabilityTier.T2_LEARNED_CALIBRATED,
            ):
                issues.append(
                    ValidationIssue(
                        Severity.ERROR,
                        "capability_tier_incompatible",
                        "capabilities.can_override_trace_sink_exploration",
                        "exploration sink override requires T0/T1/T2",
                    )
                )
            if not self.capabilities.exploration_trace_sink_id:
                issues.append(
                    ValidationIssue(
                        Severity.ERROR,
                        "exploration_sink_missing",
                        "capabilities.exploration_trace_sink_id",
                        "exploration_trace_sink_id required when override enabled",
                    )
                )

        # can_override_trace_sink: T0/T1 only
        if self.capabilities.can_override_trace_sink and self.safety.reliability_tier not in (
            ReliabilityTier.T0_DETERMINISTIC,
            ReliabilityTier.T1_CALIBRATED_NONLEARNED,
        ):
            issues.append(
                ValidationIssue(
                    Severity.ERROR,
                    "capability_tier_incompatible",
                    "capabilities.can_override_trace_sink",
                    "trace_sink_override requires T0/T1",
                )
            )

        # required_modalities ⊆ modalities
        mods = set(self.perception.modalities)
        for m in self.perception.required_modalities:
            if m not in mods:
                issues.append(
                    ValidationIssue(
                        Severity.ERROR,
                        "required_modality_undeclared",
                        "perception.required_modalities",
                        f"required modality {m} not in modalities",
                    )
                )

        # T0 + may_actuate without cross-check is OK; T2/T3 with may_actuate needs care
        if (
            self.safety.may_actuate
            and self.safety.reliability_tier
            in (ReliabilityTier.T2_LEARNED_CALIBRATED, ReliabilityTier.T3_LEARNED_UNCALIBRATED)
            and not self.safety.requires_cross_check
        ):
            issues.append(
                ValidationIssue(
                    Severity.WARNING,
                    "actuation_without_cross_check",
                    "safety.requires_cross_check",
                    "learned actuating modules should require cross-check",
                )
            )

        # Justification kind consistency
        if (
            self.justification.kind != JustificationKind.NONE
            and not self.emission.requires_justification_for
        ):
            issues.append(
                ValidationIssue(
                    Severity.WARNING,
                    "justification_unused",
                    "emission.requires_justification_for",
                    "justification.kind != NONE but no action classes require tokens",
                )
            )

        return issues

    def require_valid(self) -> None:
        issues = self.validate()
        errors = [i for i in issues if i.severity == Severity.ERROR]
        if errors:
            raise RegistrationRejected(errors)

    def to_proto(self) -> Any:
        """Best-effort conversion to generated SubstrateContract protobuf."""
        from organism_sdk._proto_path import ensure_proto_path

        ensure_proto_path()
        from organism.v1 import common_pb2, contract_pb2

        role_map = {
            ModuleRole.PERCEPTION: common_pb2.ROLE_PERCEPTION,
            ModuleRole.PREDICTION: common_pb2.ROLE_PREDICTION,
            ModuleRole.SENTINEL: common_pb2.ROLE_SENTINEL,
            ModuleRole.SOLVER: common_pb2.ROLE_SOLVER,
            ModuleRole.VERIFIER: common_pb2.ROLE_VERIFIER,
            ModuleRole.GOVERNANCE: common_pb2.ROLE_GOVERNANCE,
            ModuleRole.FEATURE_EXTRACTOR: common_pb2.ROLE_FEATURE_EXTRACTOR,
            ModuleRole.MEMORY: common_pb2.ROLE_MEMORY,
            ModuleRole.ACTUATOR: common_pb2.ROLE_ACTUATOR,
            ModuleRole.FRONTEND: common_pb2.ROLE_FRONTEND,
        }
        tier_map = {
            ReliabilityTier.T0_DETERMINISTIC: common_pb2.TIER_T0_DETERMINISTIC,
            ReliabilityTier.T1_CALIBRATED_NONLEARNED: common_pb2.TIER_T1_CALIBRATED_NONLEARNED,
            ReliabilityTier.T2_LEARNED_CALIBRATED: common_pb2.TIER_T2_LEARNED_CALIBRATED,
            ReliabilityTier.T3_LEARNED_UNCALIBRATED: common_pb2.TIER_T3_LEARNED_UNCALIBRATED,
        }
        modality_map = {
            Modality.DENSE_VECTOR: contract_pb2.MODALITY_DENSE_VECTOR,
            Modality.TEMPORAL_STREAM: contract_pb2.MODALITY_TEMPORAL_STREAM,
            Modality.SPIKE_TRAIN: contract_pb2.MODALITY_SPIKE_TRAIN,
            Modality.SYMBOL_GRAPH: contract_pb2.MODALITY_SYMBOL_GRAPH,
            Modality.WAVELET_COEFFS: contract_pb2.MODALITY_WAVELET_COEFFS,
            Modality.PHYSICAL_SENSOR: contract_pb2.MODALITY_PHYSICAL_SENSOR,
            Modality.HYPERVECTOR: contract_pb2.MODALITY_HYPERVECTOR,
            Modality.TABULAR: contract_pb2.MODALITY_TABULAR,
            Modality.TEXT: contract_pb2.MODALITY_TEXT,
            Modality.IMAGE: contract_pb2.MODALITY_IMAGE,
        }
        dtype_map = {
            DataType.FP32: contract_pb2.DTYPE_FP32,
            DataType.FP16: contract_pb2.DTYPE_FP16,
            DataType.INT8: contract_pb2.DTYPE_INT8,
            DataType.BINARY: contract_pb2.DTYPE_BINARY,
            DataType.BOOL: contract_pb2.DTYPE_BOOL,
            DataType.INT64: contract_pb2.DTYPE_INT64,
        }
        output_map = {
            OutputForm.HYPERVECTOR: contract_pb2.OUTPUT_HYPERVECTOR,
            OutputForm.SPIKE_TRAIN: contract_pb2.OUTPUT_SPIKE_TRAIN,
            OutputForm.ENERGY_GRADIENT: contract_pb2.OUTPUT_ENERGY_GRADIENT,
            OutputForm.SYMBOLIC_TRIPLE: contract_pb2.OUTPUT_SYMBOLIC_TRIPLE,
            OutputForm.PROBABILITY_INTERVAL: contract_pb2.OUTPUT_PROBABILITY_INTERVAL,
            OutputForm.SCALAR: contract_pb2.OUTPUT_SCALAR,
            OutputForm.ASSIGNMENT_CERTIFICATE: contract_pb2.OUTPUT_ASSIGNMENT_CERTIFICATE,
            OutputForm.FEATURE_VECTOR: contract_pb2.OUTPUT_FEATURE_VECTOR,
            OutputForm.JUSTIFICATION_TOKEN: contract_pb2.OUTPUT_JUSTIFICATION_TOKEN,
        }
        unc_map = {
            UncertaintyKind.NONE: contract_pb2.UNCERTAINTY_NONE,
            UncertaintyKind.CONFORMAL_INTERVAL: contract_pb2.UNCERTAINTY_CONFORMAL_INTERVAL,
            UncertaintyKind.ENSEMBLE_SPREAD: contract_pb2.UNCERTAINTY_ENSEMBLE_SPREAD,
            UncertaintyKind.ENERGY_LANDSCAPE: contract_pb2.UNCERTAINTY_ENERGY_LANDSCAPE,
            UncertaintyKind.SYMBOLIC_PROOF: contract_pb2.UNCERTAINTY_SYMBOLIC_PROOF,
        }
        det_map = {
            Determinism.DETERMINISTIC: contract_pb2.DETERMINISM_DETERMINISTIC,
            Determinism.SEEDED: contract_pb2.DETERMINISM_SEEDED,
            Determinism.STOCHASTIC: contract_pb2.DETERMINISM_STOCHASTIC,
        }
        esc_map = {
            EscalationKind.NONE: contract_pb2.ESCALATION_NONE,
            EscalationKind.PROBE_FAILURES: contract_pb2.ESCALATION_PROBE_FAILURES,
            EscalationKind.DURATION: contract_pb2.ESCALATION_DURATION,
            EscalationKind.PROBE_OR_DURATION: contract_pb2.ESCALATION_PROBE_OR_DURATION,
        }
        just_map = {
            JustificationKind.NONE: contract_pb2.JUSTIFICATION_NONE,
            JustificationKind.CAUSAL_CERT: contract_pb2.JUSTIFICATION_CAUSAL_CERT,
            JustificationKind.KERNEL_BOUND: contract_pb2.JUSTIFICATION_KERNEL_BOUND,
            JustificationKind.RULE_TRACE: contract_pb2.JUSTIFICATION_RULE_TRACE,
            JustificationKind.ENERGY_CERT: contract_pb2.JUSTIFICATION_ENERGY_CERT,
            JustificationKind.SYMBOLIC_PROOF: contract_pb2.JUSTIFICATION_SYMBOLIC_PROOF,
        }
        safety_map = {
            MaxSafetyTier.RESEARCH: common_pb2.SAFETY_RESEARCH,
            MaxSafetyTier.LOW: common_pb2.SAFETY_LOW,
            MaxSafetyTier.MEDIUM: common_pb2.SAFETY_MEDIUM,
            MaxSafetyTier.HIGH: common_pb2.SAFETY_HIGH,
            MaxSafetyTier.CRITICAL: common_pb2.SAFETY_CRITICAL,
        }

        c = contract_pb2.SubstrateContract()
        c.identity.module_id = self.identity.module_id
        c.identity.version = self.identity.version
        c.identity.author = self.identity.author
        c.identity.license = self.identity.license
        c.identity.role = role_map[self.identity.role]
        c.identity.artifact_digest = self.identity.artifact_digest
        c.identity.signatures_b64.extend(self.identity.signatures_b64)

        for m in self.perception.modalities:
            c.perception.modalities.append(modality_map[m])
        for m in self.perception.required_modalities:
            c.perception.required_modalities.append(modality_map[m])

        c.emission.output_form = output_map[self.emission.output_form]
        c.emission.shape.dims.extend(self.emission.shape.dims)
        c.emission.shape.dtype = dtype_map[self.emission.shape.dtype]
        c.emission.uncertainty = unc_map[self.emission.uncertainty]
        c.emission.determinism = det_map[self.emission.determinism]
        c.emission.requires_justification_for.extend(self.emission.requires_justification_for)

        c.metabolic.latency_p50_ms = self.metabolic.latency_p50_ms
        c.metabolic.latency_p95_ms = self.metabolic.latency_p95_ms
        c.metabolic.latency_p99_ms = self.metabolic.latency_p99_ms
        c.metabolic.energy_per_inference_j = self.metabolic.energy_per_inference_j
        c.metabolic.memory_footprint_mb = self.metabolic.memory_footprint_mb
        c.metabolic.memory_peak_mb = self.metabolic.memory_peak_mb
        c.metabolic.requires_gradient_training = self.metabolic.requires_gradient_training
        c.metabolic.requires_gpu = self.metabolic.requires_gpu
        c.metabolic.max_concurrent_invocations = self.metabolic.max_concurrent_invocations

        # Probe
        if isinstance(self.failure.probe.kind, HealthHttp):
            c.failure.probe.http.url = self.failure.probe.kind.url
            c.failure.probe.http.expected_status = self.failure.probe.kind.expected_status
            c.failure.probe.http.timeout_ms = self.failure.probe.kind.timeout_ms
        elif isinstance(self.failure.probe.kind, HealthRpc):
            c.failure.probe.rpc.method_fqn = self.failure.probe.kind.method_fqn
            c.failure.probe.rpc.timeout_ms = self.failure.probe.kind.timeout_ms
        else:
            c.failure.probe.stream.topic = self.failure.probe.kind.topic
            c.failure.probe.stream.expected_period_ms = self.failure.probe.kind.expected_period_ms
            c.failure.probe.stream.stall_timeout_ms = self.failure.probe.kind.stall_timeout_ms

        c.failure.escalation.kind = esc_map[self.failure.escalation.kind]
        c.failure.escalation.consecutive_probe_failures = self.failure.escalation.consecutive_probe_failures
        c.failure.escalation.degraded_duration_ms = self.failure.escalation.degraded_duration_ms
        c.failure.escalation.escalate_on_probe_timeout = self.failure.escalation.escalate_on_probe_timeout
        c.failure.escalation.escalate_on_probe_unreachable = (
            self.failure.escalation.escalate_on_probe_unreachable
        )
        c.failure.escalation.probe_interval_ms = self.failure.escalation.probe_interval_ms

        c.safety.reliability_tier = tier_map[self.safety.reliability_tier]
        c.safety.may_actuate = self.safety.may_actuate
        c.safety.requires_causal_certificate = self.safety.requires_causal_certificate
        c.safety.requires_cross_check = self.safety.requires_cross_check
        c.safety.max_safety_tier = safety_map[self.safety.max_safety_tier]

        c.capabilities.read_roles.extend(self.capabilities.read_roles)
        c.capabilities.write_roles.extend(self.capabilities.write_roles)
        c.capabilities.read_tags.extend(self.capabilities.read_tags)
        c.capabilities.write_tags.extend(self.capabilities.write_tags)
        c.capabilities.can_emit_control_affecting = self.capabilities.can_emit_control_affecting
        c.capabilities.can_override_trace_sink = self.capabilities.can_override_trace_sink
        c.capabilities.can_override_trace_sink_exploration = (
            self.capabilities.can_override_trace_sink_exploration
        )
        c.capabilities.exploration_trace_sink_id = self.capabilities.exploration_trace_sink_id

        c.justification.kind = just_map[self.justification.kind]
        c.justification.format = self.justification.format
        c.justification.required_fields.extend(self.justification.required_fields)

        c.lifecycle.hot_swap_supported = self.lifecycle.hot_swap_supported
        c.lifecycle.shadow_validation_required = self.lifecycle.shadow_validation_required
        return c
