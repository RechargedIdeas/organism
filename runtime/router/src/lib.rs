//! Structural router (v1.0-F) — parity with Python M3 core path.
use organism_registry::{LifecycleState, ModuleHandle};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Level {
    L0,
    L1,
    L2,
    L3,
    L4,
}

impl Level {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::L0 => "L0",
            Self::L1 => "L1",
            Self::L2 => "L2",
            Self::L3 => "L3",
            Self::L4 => "L4",
        }
    }
}

#[derive(Clone, Debug)]
pub struct RouterTask {
    pub task_id: String,
    pub form: String,
    pub safety_tier: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Excluded {
    pub module_id: String,
    pub reason_code: String,
}

#[derive(Clone, Debug)]
pub struct DispatchPlan {
    pub disposition: String, // DISPATCH | HOLD
    pub plan_type: String,   // DispatchPlan | DegradedDispatchPlan
    pub primary: Option<ModuleHandle>,
    pub excluded: Vec<Excluded>,
    pub level: String,
}

fn form_to_roles(form: &str) -> Vec<&'static str> {
    match form {
        "temporal_prediction" => vec!["PREDICTION", "FRONTEND", "FEATURE_EXTRACTOR"],
        "pattern_recognition" => vec!["PERCEPTION", "PREDICTION"],
        "anomaly_detection" => vec!["SENTINEL", "PREDICTION"],
        "constrained_allocation" => vec!["SOLVER"],
        "causal_inference" | "verification" | "calibration" => vec!["VERIFIER", "GOVERNANCE"],
        "symbolic_reasoning" => vec!["VERIFIER", "GOVERNANCE", "MEMORY"],
        "signal_analysis" | "feature_extraction" => vec!["FRONTEND", "FEATURE_EXTRACTOR"],
        "retrieval" => vec!["MEMORY"],
        "generation" => vec!["PREDICTION", "PERCEPTION"],
        "control_actuation" => vec!["ACTUATOR", "GOVERNANCE", "VERIFIER"],
        _ => vec![],
    }
}

fn tier_ok(safety: &str, tier: &str, form: &str) -> bool {
    let allowed: HashSet<&str> = if form == "control_actuation" {
        ["T0_DETERMINISTIC", "T1_CALIBRATED_NONLEARNED"]
            .into_iter()
            .collect()
    } else {
        match safety {
            "critical" => ["T0_DETERMINISTIC", "T1_CALIBRATED_NONLEARNED"]
                .into_iter()
                .collect(),
            "high" => [
                "T0_DETERMINISTIC",
                "T1_CALIBRATED_NONLEARNED",
                "T2_LEARNED_CALIBRATED",
            ]
            .into_iter()
            .collect(),
            _ => [
                "T0_DETERMINISTIC",
                "T1_CALIBRATED_NONLEARNED",
                "T2_LEARNED_CALIBRATED",
                "T3_LEARNED_UNCALIBRATED",
            ]
            .into_iter()
            .collect(),
        }
    };
    allowed.contains(tier)
}

fn level_roles(level: &Level) -> (HashSet<&'static str>, &'static str) {
    match level {
        Level::L0 | Level::L1 => (
            [
                "PERCEPTION",
                "PREDICTION",
                "SENTINEL",
                "SOLVER",
                "VERIFIER",
                "GOVERNANCE",
                "FEATURE_EXTRACTOR",
                "MEMORY",
                "ACTUATOR",
                "FRONTEND",
            ]
            .into_iter()
            .collect(),
            if matches!(level, Level::L0 | Level::L1) {
                "DispatchPlan"
            } else {
                "DegradedDispatchPlan"
            },
        ),
        Level::L2 => (
            [
                "SOLVER",
                "VERIFIER",
                "GOVERNANCE",
                "FRONTEND",
                "FEATURE_EXTRACTOR",
                "MEMORY",
                "ACTUATOR",
            ]
            .into_iter()
            .collect(),
            "DegradedDispatchPlan",
        ),
        Level::L3 => (
            ["MEMORY", "GOVERNANCE"].into_iter().collect(),
            "DegradedDispatchPlan",
        ),
        Level::L4 => (["GOVERNANCE"].into_iter().collect(), "DegradedDispatchPlan"),
    }
}

fn tier_rank(tier: &str) -> u8 {
    match tier {
        "T0_DETERMINISTIC" => 0,
        "T1_CALIBRATED_NONLEARNED" => 1,
        "T2_LEARNED_CALIBRATED" => 2,
        "T3_LEARNED_UNCALIBRATED" => 3,
        _ => 9,
    }
}

pub struct Router {
    pub level: Level,
    pub health: HashMap<String, String>,
    pub available_hardware: HashSet<String>,
}

impl Router {
    pub fn new(level: Level) -> Self {
        let mut hw = HashSet::new();
        hw.insert("NONE".into());
        Self {
            level,
            health: HashMap::new(),
            available_hardware: hw,
        }
    }

    pub fn decide(&self, task: &RouterTask, handles: &[ModuleHandle]) -> DispatchPlan {
        if task.task_id.is_empty() || task.form.is_empty() || task.safety_tier.is_empty() {
            return DispatchPlan {
                disposition: "HOLD".into(),
                plan_type: "DispatchPlan".into(),
                primary: None,
                excluded: vec![],
                level: self.level.as_str().into(),
            };
        }
        let roles = form_to_roles(&task.form);
        if roles.is_empty() {
            return DispatchPlan {
                disposition: "HOLD".into(),
                plan_type: "DispatchPlan".into(),
                primary: None,
                excluded: vec![Excluded {
                    module_id: "*".into(),
                    reason_code: "unknown_form".into(),
                }],
                level: self.level.as_str().into(),
            };
        }
        let (eligible_roles, plan_type) = level_roles(&self.level);
        let mut excluded = Vec::new();
        let mut candidates: Vec<ModuleHandle> = Vec::new();
        for h in handles {
            if h.state != LifecycleState::Deliberation {
                continue;
            }
            if !roles.iter().any(|r| *r == h.role) {
                excluded.push(Excluded {
                    module_id: h.module_id.clone(),
                    reason_code: "role_mismatch".into(),
                });
                continue;
            }
            if !eligible_roles.contains(h.role.as_str()) {
                excluded.push(Excluded {
                    module_id: h.module_id.clone(),
                    reason_code: "level_ineligible".into(),
                });
                continue;
            }
            if !tier_ok(&task.safety_tier, &h.tier, &task.form) {
                excluded.push(Excluded {
                    module_id: h.module_id.clone(),
                    reason_code: "tier_ineligible".into(),
                });
                continue;
            }
            if matches!(self.level, Level::L4) && h.module_id != "deterministic_engine" {
                excluded.push(Excluded {
                    module_id: h.module_id.clone(),
                    reason_code: "l4_deterministic_only".into(),
                });
                continue;
            }
            if self.health.get(&h.module_id).map(|s| s.as_str()) == Some("FAILED") {
                excluded.push(Excluded {
                    module_id: h.module_id.clone(),
                    reason_code: "health_failed".into(),
                });
                continue;
            }
            candidates.push(h.clone());
        }
        candidates.sort_by(|a, b| {
            let ha = self.health.get(&a.module_id).map(|s| s.as_str()).unwrap_or("HEALTHY");
            let hb = self.health.get(&b.module_id).map(|s| s.as_str()).unwrap_or("HEALTHY");
            let ra = if ha == "HEALTHY" { 0 } else { 1 };
            let rb = if hb == "HEALTHY" { 0 } else { 1 };
            ra.cmp(&rb)
                .then(tier_rank(&a.tier).cmp(&tier_rank(&b.tier)))
                .then(a.module_id.cmp(&b.module_id))
        });
        if candidates.is_empty() {
            return DispatchPlan {
                disposition: "HOLD".into(),
                plan_type: plan_type.into(),
                primary: None,
                excluded,
                level: self.level.as_str().into(),
            };
        }
        DispatchPlan {
            disposition: "DISPATCH".into(),
            plan_type: plan_type.into(),
            primary: Some(candidates[0].clone()),
            excluded,
            level: self.level.as_str().into(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use organism_registry::{ContractRecord, LifecycleState, Registry};

    #[test]
    fn decide_governance_on_control_actuation() {
        let reg = Registry::new();
        reg.register(
            ContractRecord {
                module_id: "deterministic_engine".into(),
                version: "0.1.0".into(),
                role: "GOVERNANCE".into(),
                tier: "T0_DETERMINISTIC".into(),
                artifact_digest: vec![1],
                may_actuate: true,
            },
            LifecycleState::Proposed,
        )
        .unwrap();
        for (f, t) in [
            (LifecycleState::Proposed, LifecycleState::Sandboxed),
            (LifecycleState::Sandboxed, LifecycleState::ShadowValidated),
            (LifecycleState::ShadowValidated, LifecycleState::Exploration),
            (LifecycleState::Exploration, LifecycleState::Deliberation),
        ] {
            reg.promote("deterministic_engine", f, t).unwrap();
        }
        let handles = reg.query(&organism_registry::CapabilityFilter {
            roles: vec![],
            min_lifecycle: Some(LifecycleState::Deliberation),
        });
        let router = Router::new(Level::L0);
        let plan = router.decide(
            &RouterTask {
                task_id: "t1".into(),
                form: "control_actuation".into(),
                safety_tier: "high".into(),
            },
            &handles,
        );
        assert_eq!(plan.disposition, "DISPATCH");
        assert_eq!(
            plan.primary.as_ref().unwrap().module_id,
            "deterministic_engine"
        );
    }

    #[test]
    fn l4_holds_non_governance() {
        let handles = vec![ModuleHandle {
            module_id: "learned".into(),
            version: "0.1.0".into(),
            role: "PREDICTION".into(),
            tier: "T2_LEARNED_CALIBRATED".into(),
            state: LifecycleState::Deliberation,
            contract_digest: [0u8; 32],
        }];
        let router = Router::new(Level::L4);
        let plan = router.decide(
            &RouterTask {
                task_id: "t".into(),
                form: "pattern_recognition".into(),
                safety_tier: "medium".into(),
            },
            &handles,
        );
        assert_eq!(plan.disposition, "HOLD");
    }
}
