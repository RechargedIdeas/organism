//! In-memory Substrate Registry — M2 register/query/promote.
use chrono::{DateTime, Utc};
use organism_client::OrganismError;
use parking_lot::RwLock;
use sha2::{Digest, Sha256};
use std::collections::HashMap;

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum LifecycleState {
    Proposed,
    Sandboxed,
    ShadowValidated,
    Exploration,
    Deliberation,
    Deprecated,
    Retired,
}

impl LifecycleState {
    fn rank(&self) -> u8 {
        match self {
            Self::Proposed => 0,
            Self::Sandboxed => 1,
            Self::ShadowValidated => 2,
            Self::Exploration => 3,
            Self::Deliberation => 4,
            Self::Deprecated => 5,
            Self::Retired => 6,
        }
    }

    pub fn can_promote_to(&self, to: &Self) -> bool {
        to.rank() == self.rank() + 1
    }
}

#[derive(Clone, Debug)]
pub struct ContractRecord {
    pub module_id: String,
    pub version: String,
    pub role: String,
    pub tier: String,
    pub artifact_digest: Vec<u8>,
    pub may_actuate: bool,
}

#[derive(Clone, Debug)]
pub struct ModuleHandle {
    pub module_id: String,
    pub version: String,
    pub role: String,
    pub tier: String,
    pub state: LifecycleState,
    pub contract_digest: [u8; 32],
}

#[derive(Clone, Debug)]
struct Entry {
    contract: ContractRecord,
    state: LifecycleState,
    contract_digest: [u8; 32],
    registered_at: DateTime<Utc>,
}

#[derive(Clone, Debug)]
pub struct CapabilityFilter {
    pub roles: Vec<String>,
    pub min_lifecycle: Option<LifecycleState>,
}

pub struct Registry {
    inner: RwLock<HashMap<String, Entry>>,
}

impl Registry {
    pub fn new() -> Self {
        Self {
            inner: RwLock::new(HashMap::new()),
        }
    }

    pub fn register(
        &self,
        contract: ContractRecord,
        initial: LifecycleState,
    ) -> Result<ModuleHandle, OrganismError> {
        if contract.module_id.is_empty() || contract.version.is_empty() {
            return Err(OrganismError::ValidationRejected(
                "identity_missing".into(),
            ));
        }
        let mut h = Sha256::new();
        h.update(contract.module_id.as_bytes());
        h.update(&contract.artifact_digest);
        let dig = h.finalize();
        let mut contract_digest = [0u8; 32];
        contract_digest.copy_from_slice(&dig);
        let handle = ModuleHandle {
            module_id: contract.module_id.clone(),
            version: contract.version.clone(),
            role: contract.role.clone(),
            tier: contract.tier.clone(),
            state: initial.clone(),
            contract_digest,
        };
        let mut g = self.inner.write();
        g.insert(
            contract.module_id.clone(),
            Entry {
                contract,
                state: initial,
                contract_digest,
                registered_at: Utc::now(),
            },
        );
        Ok(handle)
    }

    pub fn promote(
        &self,
        module_id: &str,
        from: LifecycleState,
        to: LifecycleState,
    ) -> Result<(), OrganismError> {
        let mut g = self.inner.write();
        let e = g
            .get_mut(module_id)
            .ok_or_else(|| OrganismError::RegistryUnavailable(module_id.into()))?;
        if e.state != from {
            return Err(OrganismError::ValidationRejected(format!(
                "lifecycle_mismatch actual={:?} expected={:?}",
                e.state, from
            )));
        }
        if !from.can_promote_to(&to) {
            return Err(OrganismError::ValidationRejected(format!(
                "invalid_promotion {:?} -> {:?}",
                from, to
            )));
        }
        e.state = to;
        Ok(())
    }

    pub fn query(&self, filter: &CapabilityFilter) -> Vec<ModuleHandle> {
        let g = self.inner.read();
        g.values()
            .filter(|e| {
                if !filter.roles.is_empty() && !filter.roles.iter().any(|r| r == &e.contract.role) {
                    return false;
                }
                if let Some(min) = &filter.min_lifecycle {
                    if e.state.rank() < min.rank() {
                        return false;
                    }
                }
                true
            })
            .map(|e| ModuleHandle {
                module_id: e.contract.module_id.clone(),
                version: e.contract.version.clone(),
                role: e.contract.role.clone(),
                tier: e.contract.tier.clone(),
                state: e.state.clone(),
                contract_digest: e.contract_digest,
            })
            .collect()
    }

    pub fn get_contract(&self, module_id: &str) -> Option<ContractRecord> {
        self.inner.read().get(module_id).map(|e| e.contract.clone())
    }
}

impl Default for Registry {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn register_query_promote_roundtrip() {
        let reg = Registry::new();
        let h = reg
            .register(
                ContractRecord {
                    module_id: "deterministic_engine".into(),
                    version: "0.1.0".into(),
                    role: "GOVERNANCE".into(),
                    tier: "T0".into(),
                    artifact_digest: vec![1, 2, 3],
                    may_actuate: true,
                },
                LifecycleState::Proposed,
            )
            .unwrap();
        assert_eq!(h.state, LifecycleState::Proposed);

        let steps = [
            (LifecycleState::Proposed, LifecycleState::Sandboxed),
            (LifecycleState::Sandboxed, LifecycleState::ShadowValidated),
            (LifecycleState::ShadowValidated, LifecycleState::Exploration),
            (LifecycleState::Exploration, LifecycleState::Deliberation),
        ];
        for (f, t) in steps {
            reg.promote("deterministic_engine", f, t).unwrap();
        }
        let found = reg.query(&CapabilityFilter {
            roles: vec!["GOVERNANCE".into()],
            min_lifecycle: Some(LifecycleState::Deliberation),
        });
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].state, LifecycleState::Deliberation);
    }
}
