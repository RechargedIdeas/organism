//! Degradation machine (v1.0-F) — parity with Python Artifact B core transitions.
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Level {
    L0,
    L1,
    L2,
    L3,
    L4,
}

impl Level {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::L0 => "L0",
            Self::L1 => "L1",
            Self::L2 => "L2",
            Self::L3 => "L3",
            Self::L4 => "L4",
        }
    }
}

const ALPHA: f64 = 0.10;
const DELTA_1: f64 = 0.05;
const DELTA_2: f64 = 0.15;
const THERMAL_L1: f64 = 0.20;
const THERMAL_L0: f64 = 0.50;
const GC_L3: f64 = 0.50;
const GC_L4: f64 = 0.85;
const MEM_L4: f64 = 0.90;
const Q_P95_L3: f64 = 50.0;
const Q_P95_L4: f64 = 250.0;
const BYZ_COUNT_L4: i32 = 3;

#[derive(Clone, Debug)]
pub struct HealthSignals {
    pub h_m: HashMap<String, String>,
    pub c_m: HashMap<String, f64>,
    pub thermal: f64,
    pub mem: f64,
    pub q_p95: f64,
    pub gc: f64,
    pub byz: bool,
    pub byz_count: i32,
    pub trace_ok: bool,
    pub det_ok: bool,
    pub causal_ok: bool,
    pub neural_modules: Vec<String>,
    pub leading_predictive: Vec<String>,
}

impl Default for HealthSignals {
    fn default() -> Self {
        Self {
            h_m: HashMap::new(),
            c_m: HashMap::new(),
            thermal: 1.0,
            mem: 0.0,
            q_p95: 1.0,
            gc: 0.0,
            byz: false,
            byz_count: 0,
            trace_ok: true,
            det_ok: true,
            causal_ok: true,
            neural_modules: vec!["learned_module_t2".into()],
            leading_predictive: vec!["learned_module_t2".into()],
        }
    }
}

#[derive(Clone, Debug)]
pub struct DegradationMachine {
    pub level: Level,
    pub signals: HealthSignals,
    pub now_s: f64,
    pub human_ack: bool,
    pub transitions: Vec<(Level, Level, String)>,
    cond_since: HashMap<String, Option<f64>>,
    t_down: HashMap<&'static str, f64>,
    t_up: HashMap<&'static str, f64>,
}

impl Default for DegradationMachine {
    fn default() -> Self {
        Self::fast()
    }
}

impl DegradationMachine {
    pub fn fast() -> Self {
        let mut t_down = HashMap::new();
        t_down.insert("L1", 0.4);
        t_down.insert("L2", 0.6);
        t_down.insert("L3", 0.8);
        t_down.insert("L4", 0.4);
        let mut t_up = HashMap::new();
        t_up.insert("L1", 2.0);
        t_up.insert("L2", 3.0);
        t_up.insert("L3", 4.0);
        t_up.insert("L4", 5.0);
        Self {
            level: Level::L0,
            signals: HealthSignals::default(),
            now_s: 0.0,
            human_ack: false,
            transitions: vec![],
            cond_since: HashMap::new(),
            t_down,
            t_up,
        }
    }

    pub fn advance(&mut self, dt: f64) -> Option<Level> {
        self.now_s += dt;
        self.tick()
    }

    fn confirmed(&mut self, key: &str, holding: bool, window: f64) -> bool {
        if !holding {
            self.cond_since.insert(key.to_string(), None);
            return false;
        }
        let since = self.cond_since.get(key).copied().flatten();
        match since {
            None => {
                self.cond_since.insert(key.to_string(), Some(self.now_s));
                window <= 0.0
            }
            Some(t0) => (self.now_s - t0) >= window,
        }
    }

    fn sustained(&mut self, key: &str, holding: bool, window: f64) -> bool {
        self.confirmed(&format!("up:{key}"), holding, window)
    }

    pub fn tick(&mut self) -> Option<Level> {
        let prev = self.level;
        let s = self.signals.clone();
        let td = self.t_down.clone();
        let tu = self.t_up.clone();

        let neural_degraded = s
            .neural_modules
            .iter()
            .any(|m| s.h_m.get(m).map(|x| x.as_str()) == Some("DEGRADED"));
        let neural_failed = s
            .leading_predictive
            .iter()
            .any(|m| s.h_m.get(m).map(|x| x.as_str()) == Some("FAILED"));
        let neural_healthy = s
            .neural_modules
            .iter()
            .all(|m| s.h_m.get(m).map(|x| x.as_str()).unwrap_or("HEALTHY") == "HEALTHY");
        let neural_calib_bad = |delta: f64| {
            !s.neural_modules.is_empty()
                && s.neural_modules
                    .iter()
                    .all(|m| *s.c_m.get(m).unwrap_or(&1.0) < 1.0 - ALPHA - delta)
        };
        let neural_calib_ok = s
            .neural_modules
            .iter()
            .all(|m| *s.c_m.get(m).unwrap_or(&1.0) >= 1.0 - ALPHA);

        let mut new: Option<Level> = None;
        let mut trigger = String::new();

        match self.level {
            Level::L0 => {
                let a = self.confirmed("l0_thermal", s.thermal < THERMAL_L1, td["L1"]);
                let b = self.confirmed("l0_calib", neural_calib_bad(DELTA_1), td["L1"]);
                let c = self.confirmed("l0_hm", neural_degraded, td["L1"]);
                let down = a || b || c;
                if s.det_ok && s.trace_ok && down {
                    new = Some(Level::L1);
                    trigger = "module_degraded_or_thermal".into();
                }
            }
            Level::L1 => {
                let down = self.confirmed("l1_failed", neural_failed, td["L2"])
                    || self.confirmed("l1_calib2", neural_calib_bad(DELTA_2), td["L2"])
                    || self.confirmed("l1_causal", !s.causal_ok, td["L2"]);
                let up = self.sustained("l1_thermal", s.thermal > THERMAL_L0, tu["L1"])
                    && self.sustained("l1_calib", neural_calib_ok, tu["L1"])
                    && self.sustained("l1_hm", neural_healthy, tu["L1"]);
                if s.det_ok && s.trace_ok && down {
                    new = Some(Level::L2);
                    trigger = "module_failed".into();
                } else if up {
                    new = Some(Level::L0);
                    trigger = "recovery".into();
                }
            }
            Level::L2 => {
                let pressure = s.gc > GC_L3
                    || s.q_p95 > Q_P95_L3
                    || s.leading_predictive.iter().all(|m| {
                        s.h_m.get(m).map(|x| x.as_str()) == Some("FAILED")
                            || *s.c_m.get(m).unwrap_or(&1.0) < 1.0 - ALPHA - DELTA_2
                    });
                let down = self.confirmed("l2_gc", pressure, td["L3"]);
                let up = self.sustained(
                    "l2_calib",
                    s.neural_modules
                        .iter()
                        .any(|m| *s.c_m.get(m).unwrap_or(&0.0) >= 1.0 - ALPHA),
                    tu["L2"],
                ) && self.sustained("l2_hm", neural_healthy, tu["L2"])
                    && self.sustained("l2_causal", s.causal_ok, tu["L2"]);
                if s.det_ok && s.trace_ok && down {
                    new = Some(Level::L3);
                    trigger = "workspace_pressure".into();
                } else if up {
                    new = Some(Level::L1);
                    trigger = "recovery".into();
                }
            }
            Level::L3 => {
                let d1 = self.confirmed("l3_trace", !s.trace_ok, td["L4"]);
                let d2 = self.confirmed("l3_det", !s.det_ok, td["L4"]);
                let d3 = self.confirmed("l3_gc", s.gc > GC_L4 || s.mem > MEM_L4, td["L4"]);
                let d4 = self.confirmed("l3_qp", s.q_p95 > Q_P95_L4, td["L4"]);
                let d5 = self.confirmed("l3_byz", s.byz_count >= BYZ_COUNT_L4, td["L4"]);
                let down = d1 || d2 || d3 || d4 || d5;
                let up = self.sustained("l3_ok", s.trace_ok && s.det_ok, tu["L3"])
                    && self.sustained("l3_gc", s.gc < GC_L3 && s.q_p95 < Q_P95_L3, tu["L3"])
                    && self.sustained("l3_byz", !s.byz, tu["L3"]);
                if down {
                    new = Some(Level::L4);
                    trigger = "trace_or_byzantine".into();
                } else if up {
                    new = Some(Level::L2);
                    trigger = "recovery".into();
                }
            }
            Level::L4 => {
                let up = self.sustained("l4_ok", s.trace_ok && s.det_ok, tu["L4"])
                    && self.sustained("l4_gc", s.gc < GC_L3 && s.mem < MEM_L4, tu["L4"])
                    && self.sustained("l4_qp", s.q_p95 < Q_P95_L3, tu["L4"])
                    && self.sustained("l4_byz", !s.byz, tu["L4"])
                    && self.human_ack;
                if up {
                    new = Some(Level::L3);
                    trigger = "human_ack_recovery".into();
                    self.human_ack = false;
                }
            }
        }

        if let Some(n) = new {
            if n != prev {
                self.transitions.push((prev, n, trigger));
                self.level = n;
                self.cond_since.clear();
                return Some(n);
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn l0_to_l1_on_thermal() {
        let mut m = DegradationMachine::fast();
        m.signals.thermal = 0.1;
        // arm timer
        assert!(m.advance(0.1).is_none());
        // hold past t_down L1 = 0.4
        assert_eq!(m.advance(0.4), Some(Level::L1));
        assert_eq!(m.level, Level::L1);
    }

    #[test]
    fn byzantine_to_l4() {
        let mut m = DegradationMachine::fast();
        m.level = Level::L3;
        m.signals.byz_count = 3;
        m.signals.byz = true;
        assert!(m.advance(0.1).is_none()); // arm
        assert_eq!(m.advance(0.4), Some(Level::L4));
    }
}
