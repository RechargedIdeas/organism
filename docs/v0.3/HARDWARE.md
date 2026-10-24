# v0.3 — Hardware gates and research-tier substrates

## Neuromorphic (SNN)

- `snn_sentinel` declares `requires_special_hardware=NEUROMORPHIC`.
- Router `available_hardware` defaults to `{NONE}` on this box.
- Module **registers** and can **simulate** spike-rate wakes into the workspace.
- Module is **not dispatched** on production control paths unless `NEUROMORPHIC` is present in `available_hardware`.
- Spike wake is advisory (`affects_control=false`); router escalation is an explicit API (`escalate_from_sentinel`).

## Physical / molecular

Physical, molecular, and wetware substrates remain **research-tier documentation only**. They must not appear on the control or actuation path in v0.3.
