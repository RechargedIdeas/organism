# Organism Desktop — Product Design (v1.5)

**Intent:** A first-party desktop **control plane** for Organism: compose substrates,
run pipelines, inspect physiology, explore bio-digital safely, and operate a
CPU-first runtime. Not a toy demo. **Not** a fork of Hybrid PySide6 Studio.

**Stack:** **PySide6 6.12** (primary). NiceGUI remains an optional documented
fallback if Qt cannot be installed; this release ships PySide6.

**Guarantee:** Runs on CPU-only hardware (`QT_QPA_PLATFORM=offscreen` for CI).

## Information architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Organism Desktop                              [CPU ●] v1.5 │
├──────────────┬──────────────────────────────────────────────┤
│ Home         │  Status / version / degrade / serve          │
│ Registry     │  Modules · contracts · health · may_actuate  │
│ Workspace    │  Bindings · read/write · hypervector viz     │
│ Pipelines    │  TaskDescriptor → decide → DispatchPlan      │
│ Physiology   │  L0–L4 · hormones · immune · autonomic       │
│ Metamodel    │  synthesize → sandbox → shadow → promote     │
│ Bio-Digital  │  slime / mycelium / HAL · EXPLORATION ONLY   │
│ Traces       │  Decision traces · snapshot replay           │
│ Ops          │  validate-config · soak · wet-lab policy     │
│ Docs         │  CPU Everywhere · Soak · API freeze          │
└──────────────┴──────────────────────────────────────────────┘
```

Navigation is a fixed left rail; content is a stacked panel. Panel ids are
stable and listed in `organism_desktop.nav.PANELS`.

## Layer mapping

| UI surface | Organism layer |
|---|---|
| Home / Status | `deploy.stack.MinimalStack.status`, `device.select_compute_backend`, degrade level |
| Substrate Registry | `RegistryClient` + module contracts / health |
| Workspace | `WorkspaceClient` bindings (capability-scoped write tags) |
| Router / Pipelines | `RouterTask` → `Router.decide` → `DispatchPlan` + routing traces |
| Physiology | `DegradationMachine`, `HormoneBus`, `ImmuneLayer`, `AutonomicController` |
| Metamodel | `MetamodelTracker` explore path (may_actuate until promote) |
| Bio-Digital | `bio_digital.*` HAL / slime / mycelium — **exploration-only** |
| Traces / Replay | `TraceEmitter.entries`, `DurableWorkspace` snapshot helpers |
| Ops | deploy config validate, soak runbook paths, `SafetyPolicy.deny_all` viewer |
| Docs | Embedded links to in-repo markdown |

## Safety model (non-negotiable)

1. Bio / wet-lab panels **never** enable `control_actuation` by default.
2. UI service layer **hard-refuses** actuation requests
   (`DesktopService.request_bio_actuation` → refused; never calls HAL actuate).
3. Every module row shows a **`may_actuate`** badge (green only if True).
4. Wet-lab panel shows `SafetyPolicy` as deny-by-default and never flips
   certification from the UI without an explicit certified policy object
   (Desktop ships read-only policy viewer + refuse path).
5. Metamodel promote is exploration-gated; UI labels stages clearly.

## Pipeline builder

1. User edits **TaskDescriptor** fields (form, safety_tier, deadline, flags).
2. Service builds `RouterTask` and calls `router.decide`.
3. Panel shows **DispatchPlan** (primary, fallbacks, exclusions, ranking_trace).
4. Optional: emit / list routing traces from the attached `TraceEmitter`.

## Packaging

```bash
pip install -e '.[desktop]'
organism-desktop          # or: python -m organism_desktop
```

Package root: `desktop/organism_desktop/`. Headless tests under `desktop/tests/`.
