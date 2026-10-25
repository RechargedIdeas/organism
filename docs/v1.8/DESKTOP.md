# Organism Desktop v1.8 — Generative surfaces

**Naming:** Organism only.  
**Safety:** bio `may_actuate=False`; promote gates mandatory; CPU Everywhere; no Hybrid Studio.

## New in v1.8.0

1. **Looks → Desktop theme apply** — evolving a `theme` or `pack` updates shell accents
   (CPU badge, nav selection, brand subtitle) via offscreen-safe QSS from the
   Organism appearance palette. `MainWindow.apply_organism_theme`.
2. **Code promote rollback deregisters** — `rollback_organism_code` /
   `demote_organism_code` call `EvolutionRuntime.after_rollback`, which removes
   the hot-registered `GeneratedSkillModule` from `ModuleRegistry` and the
   dynamic catalog.
3. **Multi-Organism store** — create / switch `OrganismProfile` in the Evolution
   panel (`organism_profile_combo`, Create, Switch). Active id persisted under
   `organism_data/organisms/_active.json`.
4. **Export / import bundle** — single zip (`organism_bundle_v1`) with profile
   JSON, skill packs, appearance, and asset bodies. Import restores RESEARCH_TIER
   skills (`may_control=False`) until re-promoted.

## Panel object names

| Object name | Role |
|---|---|
| `organism_profile_combo` | Active Organism selector |
| `organism_create` / `organism_switch` | Multi-Organism actions |
| `organism_export_bundle` / `organism_import_bundle` | Bundle IO |

## Service APIs

- `apply_organism_theme()` → palette + QSS payload
- `list_organisms()` / `create_organism()` / `switch_organism(id)`
- `export_organism_bundle(dest?)` / `import_organism_bundle(path)`
- `rollback_organism_code()` → includes `deregistered` + `module_id`
