# Organism Generative Evolution (v1.7 / v1.7.2)

**Release:** v1.7.2  
**Goal:** Production-grade generative **code**, **asset (looks)**, and **skills** pipelines so Organisms can self-evolve under explicit promote gates.

## Principles

1. **Never silent control overwrite** — code/skills reach `may_control` only after PromoteGate (static → contract → sandbox → shadow ≥ 0.9 → promote).
2. **RESEARCH_TIER drafts** until promoted; demote / **rollback last promote** returns exploration.
3. **Sandbox-only exec** — restricted AST (expanded forbid list); no `os`/`subprocess`/`open`/`eval`/`getattr`; mirrors `ActuationRefused` on unsafe promote.
4. **CPU Everywhere** — template library + LLM-stub backends are offline/deterministic; no GPU hard-dep. `GeneratorBackend` protocol is pluggable.
5. **Bio `may_actuate=False`** unchanged; no Hybrid Studio import.
6. Terminology is **Organism** / `OrganismProfile` — never Sophont.

## Architecture

```
intent → draft (TemplateDraftBackend | LLMStubBackend | custom GeneratorBackend)
      → static checks → contract validate
      → SafeSandbox.exec(main)
      → shadow metrics → promote | demote | rollback
```

| Layer | Path |
|---|---|
| SDK | `sdk/python/organism_sdk/generative/` |
| Module | `modules/generative` (`generative_organism`, RESEARCH_TIER) |
| Artifacts | `organism_data/artifacts/` (+ `assets/`, `organisms/`, `packs/`) |
| Desktop | Panel **Organism Evolution** — Evolve Skills / Looks / Code Promotions / Evolution Log |

### A. Generative code (v1.7.1 production)

- Richer **template library** (`adder`, `scorer`, `navigator`, `filter`, `aggregator`, `classifier`)
- Pluggable **`GeneratorBackend`** protocol (+ `DraftBackend` ABC)
- **Replayable drafts** via `DraftReplayLog` / `CodePipeline.replay_draft`
- Expanded **AST forbid list** (imports, eval/exec, async, class, lambda, network, pickle, …)
- **Shadow metrics** breakdown (`ShadowMetrics`)
- **`rollback_last_promote`** restores prior control revision
- Concurrent-safe **`ArtifactStore`** (RLock + atomic replace + content-hash verify)

### B. Generative assets (looks)

- Kinds: `avatar` · `skin` · `icon` · `theme`
- **Multi-asset packs** (`evolve_pack`: avatar SVG + theme JSON + icon)
- **Content-hash integrity** on stage/store; Desktop **preview bytes/text**
- Reject **oversized** (>256KB) / **malformed** SVG/JSON; **theme contrast** floor (≥ 3.0)
- Manifests under `organism_data/assets/*.manifest.json`

### C. Skills

- `SkillDescriptor` versioning + `version_history`
- **Dependency DAG** (`depends_on`, `dependency_dag()`, cycle refusal)
- **`improve_from_trace`** uses Organism `evolution_log`
- **Promote requires shadow threshold** (`min_shadow_for_promote`)

### D. Organism identity

- `OrganismProfile`: id, skills[], appearance, code_revisions[], evolution_log
- `OrganismStore` persists JSON under `organism_data/organisms/`


### E. Runtime integration (v1.7.2)

- `EvolutionRuntime.hot_register_promoted` — ModuleRegistry shadow gate + dynamic catalog
- `EvolutionTraceEntry` via `TraceEmitter.emit_evolution`
- Optional `HormoneBus` dopamine/oxytocin pulse on promote
- `ImmuneLayer` quarantine demotes generative drafts that fail contracts
- Wall-clock budgets: `EVOLVE_P95_MS` (250) · `PROMOTE_P95_MS` (100) · hot-register / quarantine

Desktop service returns `runtime` / `timings` / `within_budgets` on evolve/promote.

## Desktop (v1.7.1 / v1.7.2)

Navigation keeps **Organism Evolution** (13 panels). New UI:

- Pipeline **stage progress** bar + checklist
- **Rollback last promote** button
- **Asset preview** pane (SVG/JSON text)
- **Skill DAG** view + **Improve from trace**
- Looks kind includes **pack**

Service APIs:

- `organism_snapshot` · `evolve_organism_skill` · `promote_organism_skill`
- `improve_organism_skill_from_trace` · `organism_skill_dag`
- `evolve_organism_looks` · `evolve_organism_looks_pack` · `organism_asset_preview`
- `evolve_organism_code` · `promote_organism_code` · `demote_organism_code`
- `rollback_organism_code` · `code_stage_progress` · `list_code_bundles`

## Production ops notes

1. **Artifact root** — default `organism_data/artifacts/`. Back up `provenance/index.json` with code/assets/skills trees; content-hash verify via `ArtifactStore.verify(id)`.
2. **Replay** — `draft_replay.json` records every draft; re-run identical source with `replay_draft` for incident review / bisect.
3. **Promote / rollback** — only one live promote stack tip; `rollback_last_promote` demotes tip to `ROLLBACK` without deleting provenance.
4. **Shadow floor** — default `min_shadow=0.9`. Skill promote uses registry `min_shadow_for_promote` (default 0.9). Raise in locked-down deploys.
5. **Fuzz gate** — `v17:generative` CI runs unsafe-draft fuzz; all payloads must `REJECTED` and refuse promote.
6. **Concurrency** — `ArtifactStore.put` is process-local RLock + atomic `os.replace`; do not share one store across processes without an external lock.
7. **CPU Everywhere** — no GPU required; swap `LLMStubBackend` for a hosted provider behind `GeneratorBackend` without changing gates.
8. **Bio** — generative path never sets `may_actuate=True`; Desktop still hard-refuses wet-lab actuation.

## Safety checklist

- [x] Bio actuation hard-refused
- [x] Generative `may_actuate` forced False in contracts/drafts
- [x] Unsafe promote → `ActuationRefused` / `PromoteRefused`
- [x] No arbitrary shell in sandbox
- [x] Fuzz unsafe drafts refuse
- [x] No Sophont naming in types/UI/docs
