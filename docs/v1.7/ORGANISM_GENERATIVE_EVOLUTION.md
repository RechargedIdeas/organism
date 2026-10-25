# Organism Generative Evolution (v1.7)

**Release:** v1.7.0  
**Goal:** Production-grade generative **code**, **asset (looks)**, and **skills** pipelines so Organisms can self-evolve under explicit promote gates.

## Principles

1. **Never silent control overwrite** — code/skills reach `may_control` only after PromoteGate (static → contract → sandbox → shadow ≥ 0.9 → promote).
2. **RESEARCH_TIER drafts** until promoted; demote returns exploration.
3. **Sandbox-only exec** — restricted AST; no `os`/`subprocess`/`open`; mirrors `ActuationRefused` on unsafe promote.
4. **CPU Everywhere** — template + LLM-stub backends are offline/deterministic; no GPU hard-dep.
5. **Bio `may_actuate=False`** unchanged; no Hybrid Studio import.
6. Terminology is **Organism** / `OrganismProfile` — never Sophont.

## Architecture

```
intent → draft (TemplateDraftBackend | LLMStubBackend)
      → static checks → contract validate
      → SafeSandbox.exec(main)
      → shadow score → promote | demote
```

| Layer | Path |
|---|---|
| SDK | `sdk/python/organism_sdk/generative/` |
| Module | `modules/generative` (`generative_organism`, RESEARCH_TIER) |
| Artifacts | `organism_data/artifacts/` (+ `assets/`, `organisms/`) |
| Desktop | Panel **Organism Evolution** — Evolve Skills / Looks / Code Promotions / Evolution Log |

### A. Generative code

- `CodePipeline.evolve` / `promote` / `demote`
- Versioned `ArtifactStore` + provenance JSON
- `PromoteRefused` if gate incomplete

### B. Generative assets (looks)

- Kinds: `avatar` · `skin` · `icon` · `theme`
- Procedural SVG / theme JSON → validate dims/safety → stage → apply `AppearanceProfile`
- Manifests under `organism_data/assets/*.manifest.json`

### C. Skills

- `SkillDescriptor` + `SkillRegistry.generate_skill` / `improve_skill` / `promote_skill`
- Hooks metamodel organs via `attach_from_metamodel`

### D. Organism identity

- `OrganismProfile`: id, skills[], appearance, code_revisions[], evolution_log
- `OrganismStore` persists JSON under `organism_data/organisms/`

## Desktop

Navigation adds **Organism Evolution** (13 panels). Service APIs:

- `organism_snapshot` · `evolve_organism_skill` · `promote_organism_skill`
- `evolve_organism_looks` · `evolve_organism_code` · `promote_organism_code` · `demote_organism_code`

## Safety checklist

- [x] Bio actuation hard-refused
- [x] Generative `may_actuate` forced False in contracts/drafts
- [x] Unsafe promote → `ActuationRefused`
- [x] No arbitrary shell in sandbox
- [x] No Sophont naming in types/UI/docs
