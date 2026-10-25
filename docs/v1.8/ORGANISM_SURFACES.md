# Organism v1.8 surfaces

## Theme apply

`organism_sdk.generative.theme.theme_apply_payload(appearance)` builds a Desktop
payload with normalized palette and `shell_accent_qss`. Looks promote of
`theme`/`pack` attaches this under `result["theme"]`.

## Rollback deregister

`EvolutionRuntime.deregister_promoted` / `after_rollback` map bundle →
`gen_{bundle_id|skill_id}` ModuleRegistry entry and drain it.

## Multi-Organism

`OrganismStore.active_id` / `set_active` / `switch` / `list_summaries` with
`_active.json` persistence.

## Bundle format `organism_bundle_v1`

Zip entries: `manifest.json`, `organism_profile.json`, `skills.json`,
`appearance.json`, `assets/index.json`, `assets/<id>.body`.

## v1.8.1 polish

- Desktop bundle path edit/feedback round-trip.
- `MainWindow.update_organism_badge` / `shell_organism_badge`.
- Generative soak: evolve → promote → rollback must leave no hot-registered
  generative modules beyond the pre-soak registry baseline.
