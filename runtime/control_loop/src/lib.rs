//! organism-control-loop — minimal tick-loop parity with Python deploy serve.
//!
//! Software control path only. No bio actuation. RESEARCH helpers stay out of
//! this crate. This is an honest minimal runtime tick (not a full Python port).

use std::time::{Duration, Instant};

/// Snapshot of one control-loop tick (mirrors deploy health/status shape lightly).
#[derive(Clone, Debug, PartialEq)]
pub struct TickSnapshot {
    pub tick: u64,
    pub level: String,
    pub healthy: bool,
    pub elapsed_ms: u128,
    pub may_actuate: bool,
}

impl TickSnapshot {
    pub fn as_status_line(&self) -> String {
        format!(
            "tick={} level={} healthy={} elapsed_ms={} may_actuate={}",
            self.tick, self.level, self.healthy, self.elapsed_ms, self.may_actuate
        )
    }
}

/// Minimal Organism control loop — advances virtual ticks with a wall budget.
pub struct ControlLoop {
    tick: u64,
    level: String,
    started: Instant,
}

impl Default for ControlLoop {
    fn default() -> Self {
        Self::new()
    }
}

impl ControlLoop {
    pub fn new() -> Self {
        Self {
            tick: 0,
            level: "L0".to_string(),
            started: Instant::now(),
        }
    }

    pub fn set_level(&mut self, level: impl Into<String>) {
        self.level = level.into();
    }

    pub fn level(&self) -> &str {
        &self.level
    }

    /// Advance one tick. Always reports `may_actuate=false`.
    pub fn tick_once(&mut self) -> TickSnapshot {
        self.tick = self.tick.saturating_add(1);
        TickSnapshot {
            tick: self.tick,
            level: self.level.clone(),
            healthy: self.level != "L4",
            elapsed_ms: self.started.elapsed().as_millis(),
            may_actuate: false,
        }
    }

    /// Run until `max_ticks` or `budget` wall time, whichever first.
    pub fn run(&mut self, max_ticks: u64, budget: Duration) -> Vec<TickSnapshot> {
        let deadline = Instant::now() + budget;
        let mut out = Vec::with_capacity(max_ticks as usize);
        for _ in 0..max_ticks {
            if Instant::now() >= deadline {
                break;
            }
            out.push(self.tick_once());
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tick_never_actuates() {
        let mut loop_ = ControlLoop::new();
        let snap = loop_.tick_once();
        assert_eq!(snap.tick, 1);
        assert!(!snap.may_actuate);
        assert!(snap.healthy);
        assert!(snap.as_status_line().contains("may_actuate=false"));
    }

    #[test]
    fn run_respects_budget_and_ticks() {
        let mut loop_ = ControlLoop::new();
        let snaps = loop_.run(10, Duration::from_secs(1));
        assert_eq!(snaps.len(), 10);
        assert_eq!(snaps.last().unwrap().tick, 10);
        assert!(snaps.iter().all(|s| !s.may_actuate));
    }

    #[test]
    fn l4_marked_unhealthy() {
        let mut loop_ = ControlLoop::new();
        loop_.set_level("L4");
        let snap = loop_.tick_once();
        assert!(!snap.healthy);
    }
}
