//! In-memory workspace — M2 (no snapshot/ops-log yet; those are M5).
use chrono::{DateTime, Utc};
use organism_client::{Hypervector, OrganismError};
use parking_lot::RwLock;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use uuid::Uuid;

#[derive(Clone, Debug)]
pub struct BindingRecord {
    pub binding_id: Uuid,
    pub hypervector: Hypervector,
    pub role: Hypervector,
    pub filler: Hypervector,
    pub tags: Vec<String>,
    pub module_id: String,
    pub salience: f32,
    pub checksum: [u8; 32],
    pub created_at: DateTime<Utc>,
}

impl BindingRecord {
    pub fn new(
        role: Hypervector,
        filler: Hypervector,
        tags: Vec<String>,
        module_id: String,
    ) -> Self {
        let hypervector = role.bind(&filler);
        let binding_id = Uuid::now_v7();
        let mut rec = Self {
            binding_id,
            hypervector,
            role,
            filler,
            tags,
            module_id,
            salience: 1.0,
            checksum: [0u8; 32],
            created_at: Utc::now(),
        };
        rec.checksum = rec.compute_checksum();
        rec
    }

    fn compute_checksum(&self) -> [u8; 32] {
        let mut h = Sha256::new();
        h.update(self.hypervector.to_bytes_be());
        h.update(self.role.to_bytes_be());
        h.update(self.filler.to_bytes_be());
        h.update(self.binding_id.as_bytes());
        let dig = h.finalize();
        let mut out = [0u8; 32];
        out.copy_from_slice(&dig);
        out
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum WriteStatus {
    Accepted,
    Rejected,
}

#[derive(Clone, Debug)]
pub struct BindingWriteResult {
    pub binding_id: Uuid,
    pub status: WriteStatus,
    pub reason_code: Option<String>,
}

pub struct Workspace {
    inner: RwLock<Inner>,
    write_tags: HashSet<String>,
}

struct Inner {
    bindings: HashMap<Uuid, BindingRecord>,
    seq: u64,
}

impl Workspace {
    pub fn new(write_tags: impl IntoIterator<Item = String>) -> Self {
        Self {
            inner: RwLock::new(Inner {
                bindings: HashMap::new(),
                seq: 0,
            }),
            write_tags: write_tags.into_iter().collect(),
        }
    }

    pub fn open_unrestricted() -> Self {
        Self::new(["*".to_string()])
    }

    fn check_write(&self, tags: &[String]) -> Result<(), OrganismError> {
        if self.write_tags.is_empty() || self.write_tags.contains("*") {
            return Ok(());
        }
        if tags.iter().any(|t| self.write_tags.contains(t)) {
            return Ok(());
        }
        Err(OrganismError::CapabilityScopeMissing(format!(
            "write tags {:?} not in {:?}",
            tags, self.write_tags
        )))
    }

    pub fn write(&self, mut binding: BindingRecord) -> BindingWriteResult {
        if let Err(e) = self.check_write(&binding.tags) {
            return BindingWriteResult {
                binding_id: binding.binding_id,
                status: WriteStatus::Rejected,
                reason_code: Some(e.to_string()),
            };
        }
        // Exactness: force hv = role.bind(filler)
        binding.hypervector = binding.role.bind(&binding.filler);
        binding.checksum = binding.compute_checksum();
        let id = binding.binding_id;
        let mut g = self.inner.write();
        g.bindings.insert(id, binding);
        g.seq += 1;
        BindingWriteResult {
            binding_id: id,
            status: WriteStatus::Accepted,
            reason_code: None,
        }
    }

    pub fn bind_exact(
        &self,
        role: Hypervector,
        filler: Hypervector,
        tags: Vec<String>,
        module_id: String,
    ) -> Result<BindingRecord, OrganismError> {
        let rec = BindingRecord::new(role, filler, tags, module_id);
        let id = rec.binding_id;
        let res = self.write(rec);
        if res.status != WriteStatus::Accepted {
            return Err(OrganismError::CapabilityScopeMissing(
                res.reason_code.unwrap_or_default(),
            ));
        }
        Ok(self.read_by_binding_id(id).expect("just written"))
    }

    pub fn unbind(&self, binding_id: Uuid) -> Option<BindingRecord> {
        let mut g = self.inner.write();
        g.bindings.remove(&binding_id)
    }

    pub fn read_by_binding_id(&self, binding_id: Uuid) -> Option<BindingRecord> {
        self.inner.read().bindings.get(&binding_id).cloned()
    }

    pub fn read_similar(&self, hv: &Hypervector, k: usize) -> Vec<(BindingRecord, f64)> {
        let g = self.inner.read();
        let mut scored: Vec<_> = g
            .bindings
            .values()
            .map(|b| (b.clone(), b.hypervector.similarity(hv)))
            .collect();
        scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        scored.truncate(k);
        scored
    }

    pub fn len(&self) -> usize {
        self.inner.read().bindings.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::{rngs::StdRng, SeedableRng};

    #[test]
    fn bind_unbind_exactness() {
        let ws = Workspace::open_unrestricted();
        let mut rng = StdRng::seed_from_u64(99);
        let role = Hypervector::random(&mut rng);
        let filler = Hypervector::random(&mut rng);
        let bound = ws
            .bind_exact(
                role.clone(),
                filler.clone(),
                vec!["governance".into()],
                "deterministic_engine".into(),
            )
            .unwrap();
        assert_eq!(bound.hypervector, role.bind(&filler));
        assert_eq!(bound.hypervector.unbind(&role), filler);
        let prior = ws.unbind(bound.binding_id).unwrap();
        assert_eq!(prior.binding_id, bound.binding_id);
        assert!(ws.read_by_binding_id(bound.binding_id).is_none());
    }
}
