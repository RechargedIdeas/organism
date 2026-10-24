use thiserror::Error;

#[derive(Debug, Error)]
pub enum OrganismError {
    #[error("capability scope missing: {0}")]
    CapabilityScopeMissing(String),
    #[error("dimension mismatch: expected {expected}, got {actual}")]
    DimensionMismatch { expected: usize, actual: usize },
    #[error("justification missing for action class: {0}")]
    JustificationMissing(String),
    #[error("registry unavailable: {0}")]
    RegistryUnavailable(String),
    #[error("workspace backpressure: {0}")]
    WorkspaceBackpressure(String),
    #[error("replay mismatch at sequence {0}")]
    ReplayMismatch(u64),
    #[error("validation rejected: {0}")]
    ValidationRejected(String),
}
