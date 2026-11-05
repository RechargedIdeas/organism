## [Unreleased] - v1.11 MoA layer (in progress)

### Added
- **Work agent decisions adopted** (2026-11-04): W-D1a, the executor is Claude Code in non-interactive print mode, the one CLI in the argv template. W-D2, rules first, with no hosted LLM yet. W-D5 and S1, the approver holds the signing key and the agent verifies only. See `docs/SUPERAGENT_COMPARISON.md`, section 6.
- **Work agent design record and pure domain** (v1.12, W0 and W1): `docs/v1.12/WORK_AGENT.md` records the decisions and the
  principles. `organism_sdk.work` holds the domain types, the admission gate (`admit`), the Ticket stage table
  (`stage_of`) and the versioned Policy (`policy_version`). The domain modules do no I/O. Gate `work:domain`. The comparison
  with dsh-superagent and the build-out plan are in `docs/SUPERAGENT_COMPARISON.md`.
- **Work agent store** (v1.12, W2): `organism_sdk.work.store` (`WorkStore`) keeps the work agent's state in SQLite WAL mode. A round of intake (its Triggers, the Source cursor and its effects) is one transaction, and a Trigger is stored once by id. Receipts are queued once and settled as sent or dropped. The effects queue retries with backoff from 5 s to 300 s and can be paused. Opening a store takes an OS writer lock, so a second writer is refused at once with `StoreInUse`, and a crash releases the lock. Effects run at least once, so handlers must be idempotent. Only `store.py` does I/O; `codec.py` is pure. Gates `work:store` and `work:restart`, where a process killed mid-round or mid-effect is restarted and its replay is checked.
- **GitHub source, read only** (v1.12, W3): `organism_sdk.work.sources.github` reads one repository's notifications and the comments they name, through `gh api` with argv only, and turns new comments into Triggers. It never writes to GitHub. A failed item keeps its own error, and the cursor holds before it until it recovers. Gate `work:github_fake`, against a fake `gh`, with no network.
- **Eval and shadow promotion** (v1.12, W4): `organism_sdk.work.decide` decides each Trigger once per Policy version, from the gate's admission and a deterministic `RuleAssessor` whose rules match by pattern (200 characters at most). An inferred candidate is accepted only in auto mode, for a graduated rule. Otherwise a candidate that matched a rule is recorded as a would-accept. `promote.graduate` marks a rule auto only after 20 verdicts on its would-accepts, at least 90% agreeing. A Trigger older than an hour is ignored, so a new Policy version cannot start work on old requests. The store moves to schema 2. Gates `work:admission`, `work:shadow_promote` and `work:eval`. No model is consulted; the LLM assessor is not built (W-D2).
- **GitHub reply channel** (v1.12, W6): `organism_sdk.work.channels` queues replies per Ticket, sent in order. Each reply carries a hidden receipt marker, and the channel checks the thread for it before posting, so a crash between the post and the store does not post twice. Only HTTP 410 means the thread is gone, and that reply is dropped. Replies are off: no command enables the handler yet. Gate `work:channel_idempotent`.
- **Operator surface** (v1.12, W7): `organism work` (`status`, `tickets`, `attention`, `pause`, `resume`, `stop`, `retry`, `evaluate`) reads the store beside the writer and changes it under the writer lock. `organism serve` answers `GET /work/status`. The `needs_you` desktop panel lists what needs a person, with the healthy state in one line. Gates `work:operator`, `work:serve_status` and `work:needs_you_panel`.
- **Thread ownership routing** (v1.12, W8): `organism_sdk.work.routing.route` sends a human message to the open Ticket that owns its Thread, and refuses a Thread owned by two open Tickets. Nothing calls it yet. Hand-back, release and pull-request following are not built. Gate `work:followups`.
- **Signed Policy adoption** (v1.12, W9): `organism_sdk.work.governance.adopt` makes a Policy the one in force only when an approver in the TrustStore signed it, and queues a notice for each open Ticket it touches. It never cancels a Ticket. The instruction artifacts and the "default updated" flag are not built. Gate `work:policy_version`.
- **Environment panel and secret store** (`organism_sdk.envstore`): secret variables live in the OS credential store (Windows Credential Manager) or, elsewhere, in a per-user file readable by its owner only, never in the repository. The `Environment` desktop panel adds, edits, removes and reveals them. A value shows as a mask until an explicit reveal, which ends after 10 seconds. `serve` and the desktop app apply the store at start, and a sandboxed child never receives a stored name. Errors and logs name a variable, never its value. Gate `env:store_and_panel`.
- **MoA layer** (`organism_sdk.moa`): experts with capability descriptors that register as
  `SubstrateContract`s, a capability scorer with a shadow precision gate, VSA-backed
  aggregation with clean-up recovery, tiers T0 to T4 with recovery hysteresis, and a per-query pipeline.
- **Reference experts**: `intent_classifier` and `extractor`. Rule-based, CPU-only, deterministic.
- **Synthetic routing set** (`sdk/python/tests/data/moa_routing_synthetic.json`) and four `v111:moa_*` gates in `ci/gates.yaml`.
- **Design record**: `docs/v1.11/MOA_LAYER.md`. Records corrections to the upgrade plan.
- **Local CI pipeline** (`ci/`, run with `python ci/run.py`): tiers `precommit`, `fast`, `full` and `nightly`; preflight checks;
  parallel gates with a serial `exclusive` phase; per-gate timeouts that kill the process tree; a content-addressed result cache;
  lint and format ratchets for ruff, mypy and rustfmt; hygiene scans; a single-run lock; git hooks in `ci/hooks`; and a Windows
  nightly schedule script, `ci/schedule/windows_nightly.ps1`. Documented in `ci/README.md`.
- **Runner tests**: `tests/ci/` covers config, preflight, ratchets, hygiene, cache, executor, lock, environment and CLI.
- **Clippy gate** `rust:clippy` (fast tier): `cargo clippy --workspace --all-targets -- -D warnings`. The Rust workspace has zero clippy findings.
- **Signed registry actions** (`organism_sdk.signing`): Ed25519 signatures, a `TrustStore` with separate author and approver keys, and domain-tagged payloads. The registration payload binds the module id, version and artifact digest. The promotion payload binds the states and the shadow evidence. `RegistryClient(trust_store=...)` enforces the check. With no trust store, behaviour is unchanged.
- **MoA guardrails** (`organism_sdk.moa.guardrails`, Phase 5, rule-based): an input guard that blocks prompt-injection queries before routing, and an output guard that rejects an answer whose extracted entities do not occur in the query. Each guard declares its measured false-positive and false-negative rates. `MoAResult.guarded` records which guards fired.
- **Red-team suite** (`test_v111_moa_redteam.py`, gate `v111:moa_redteam`, non-blocking): variants that must be blocked, three known misses as strict xfails, and a seeded fuzz that checks invariants.
- **Scheduled CI on GitHub** (`.github/workflows/nightly.yml`): the nightly tier at 02:00 UTC, and an advisory job running `pip-audit` and `cargo audit`.
- **Tests**: version alignment across the packages and the Rust workspace; every name in the frozen Python API is exported; container and VM detection evidence; the `python -m organism_sdk` entry point.
- **Docs**: `docs/GAP_ANALYSIS.md` lists what the review fixed, what is open, and the decisions still needed.

### Changed
- `tests/ops/test_soak_ops.py`: the executable-bit check reads the git index mode (`100755`) on every platform. On Linux it also checks the file's mode bit.
- **Versions** are aligned to 1.10.0. `sdk/python/pyproject.toml` was 1.4.0 and the Rust workspace was 1.3.0.
- **Dependencies**: removed `pydantic`, `blake3` and `structlog` from the root project, and `pydantic` and `numpy` from the SDK package, because nothing imported them. The SDK package now declares `cryptography`, which signing uses.
- **Typing**: mypy excludes the generated protobuf code. The in-repo packages under `modules/` are typed `Any` at the import boundary. Public SDK helpers, test fixtures, and the test and harness helpers are annotated. The hand-written mypy ratchet goes from 527 to 59.
- **Logging**: 24 modules that caught exceptions silently now log them with the standard `logging` module.
- `EVOLVE_BUDGET_MS` (`organism_sdk/generative/budgets.py`): the evolve wall-clock budget is per platform, 2000 ms on Windows and 1000 ms elsewhere. Windows `spawn` start-up dominates the measured cost.
- **Rust clean-up**: `cargo fmt` applied to four files (formatting only), so the rustfmt baseline is zero. Clippy fixes in `organism-client` (index loops rewritten as iterators, same output) and `organism-workspace` (`is_empty` added beside `len`). Removed the unused `registered_at` field from `organism-registry`. `runtime/registry` no longer depends on `chrono`. The crate is still used by `runtime/workspace` and `organism-client`.

### Fixed
- **Routing false positive**: the bare verb `find` is no longer an extractor keyword. It sent generic queries such as
  "Find a good recipe for dinner" to the extractor, with held-out precision 0.78. Held-out set added (`moa_routing_heldout.json`).
- **Mirror-lag flake on Windows**: `test_mirror_lag_slo` waits 25 ms, not 8 ms. The Windows clock ticks about every 15.6 ms,
  so the 8 ms wait missed the delivery in 25 of 60 runs.
- **Preflight protobuf check**: it reported stale modules on every run because it looked for the generated files at the wrong
  path. It now matches the path protoc writes to.
- **Gate environment placeholders**: `env` values such as `PROTOC: "{protoc}"` reached the child process unexpanded, so `build.rs` received the literal text. The runner now fills them as it does commands. Cargo's build-script cache hid the bug until a formatting change to `build.rs` forced a rerun.
- **Workspace replay determinism**: bindings with equal similarity are ordered by binding id, so replay no longer depends on insertion order.
- **Desktop evolve budget gate** (`v17:desktop_organism`): its tests run on a temp data root through `DesktopService.create(data_root=...)`. The budget no longer depends on the replay log that earlier runs grew in the repo's `organism_data`. See `docs/GAP_ANALYSIS.md`, item O11.

### Known issues
- Evolve budgets were measured on Windows and WSL only: 2000 ms on Windows, 1000 ms elsewhere. See `docs/v1.11/MOA_LAYER.md`, section 8.
- Registry signatures are checked only when a `TrustStore` is passed. Internal callers still pass placeholder bytes, and where production keys live is not decided. See `docs/GAP_ANALYSIS.md`, item S1.
- Three guardrail misses are recorded as strict xfails in `test_v111_moa_redteam.py`. See `docs/v1.11/MOA_LAYER.md`, section 10.
- Routing recall gap: extraction queries built around "email address" route unsure. Adding the phrases lost precision (7/11), so the fix waits for a context rule. See `docs/v1.11/MOA_LAYER.md`, section 4.
- Rust workspace tests need `protoc`. The local pipeline resolves it from `PROTOC`, then `.venv`, then `PATH`.
### Test baseline
- `pytest -m 'not slow'` collects 591 tests (584 passed, 3 skipped, 4 xfailed). The `suite:fast` gate passes in the full tier on Windows and WSL.
- Full tier of the local pipeline on Windows (`77e110c`): 61 of 61 gates pass. 49 of them were served from the content-addressed cache.
- Full tier on WSL Ubuntu (`77e110c`): 61 of 61 gates pass. The first WSL run failed `lint:mypy` on a stale `.mypy_cache` left from before the protobuf modules were regenerated. Clearing the cache fixed it with no code change.
- At `edd2924`, the head of this unreleased work, the full tier passes on Windows (61 of 61) and on WSL (61 of 61).
- Fast tier (pre-push): 60 of 60 gates pass.

## [1.10.0] — 2026-10-25

### Added
- **Host portability profiles** — `bare_metal`, `vm`, `container_generic` (Docker is one optional backend, never required).
- **Host detection** — `organism_sdk.host.detect_host()`; `organism status` reports `host_kind` + `docker_required: false`.
- **Bare install** — `deploy/bare/install.sh` + hardened `deploy/systemd/organism.service`.
- **OCI Containerfile** — `deploy/container/Containerfile` (Docker-and-Podman friendly); Dockerfile marked example-only.
- **Native Organism Sandbox** — `organism_sdk.sandbox` ProcessJail (rlimits + optional Linux namespaces), self-sandbox, audit → `SandboxTraceEntry`.
- **CLI** — `organism sandbox status|run|self-check`.
- **Desktop Ops** — host/sandbox badges + Sandbox self-check.
- Docs: `docs/v1.10/BARE_METAL_AND_SANDBOX.md`; gates `v110:*`.
- CI: Docker/OCI jobs `continue-on-error` / separate optional workflow; main gates never need Docker.

### Changed
- README / STATUS / deploy README: **Docker optional; first-class bare metal**.
- Generative `SafeSandbox` composes with native jail (`run_under_organism_jail`).
- Package / SDK / Desktop / generative versions **1.10.0**.

### Safety
- Bio `may_actuate=False` unchanged; shell-escape fuzz refused; env key scrub in jail.
- CPU Everywhere; no GPU hard-dep; no Hybrid Studio.

### Deferred (hardware / external)
- Neuromorphic silicon, wet-lab GPIO, production WAN BFT+TPM, Hybrid Studio UI,
  hosted LLM provider account.

### Test baseline
- `pytest -m 'not slow'`: **377** passed · 2 deselected

## [1.9.0] — 2026-10-25

### Added
- **GitHub Actions CI** — `.github/workflows/ci.yml` (pytest not-slow, Desktop smoke, Rust, Docker).
- **v18/v19 gates** in `ci/gates.yaml`.
- **HostedLLMBackend** — OpenAI-compatible HTTP client; `ORGANISM_LLM_*` env-gated; never default-on.
- **Sandbox process jail** — AST gate + child process wall-clock timeout + RSS cap.
- **ImageBackend** protocol — `procedural_v1.9` default + hosted refuse-until-configured.
- **Generative CLI** — `evolve-skill|looks|code`, `promote-*`, `rollback-code`, `bundle-*`, `list-*`, `replay-draft`.
- **Physiology Desktop depth** — immune/autonomic/circadian/apoptosis/morphogenesis/Learned-ISE demos.
- **Ops multiprocess stub** button (labeled `not_production_bft`).
- **Draft Replay** tab on Organism Evolution panel.
- **Rust control_loop** minimal tick loop + unit tests (`may_actuate=false`).
- **PyInstaller** `desktop/organism-desktop.spec` + PACKAGING v1.9.
- Template library expanded to 10 (normalizer/ranker/smoother/gate).
- Docs: `docs/v1.9/AUDIT_CLOSURE.md`; AUDIT_v1.8 marked closed for software items.

### Changed
- README / STATUS synced to **v1.9.0**; generative evolution doc header updated.
- Dockerfile sets generative defaults (`ORGANISM_LLM_ENABLED=0`, sandbox isolate).
- Hypervector Workspace preview adds sparkline.
- Package / SDK / Desktop / generative module versions **1.9.0**.

### Safety
- Bio `may_actuate=False` unchanged; generative promote caps at EXPLORATION.
- Hosted LLM/image never default-on; secrets stay in env/vault.
- NiceGUI status page remains out of scope.

### Deferred (hardware / external)
- Neuromorphic silicon, wet-lab GPIO, production WAN BFT+TPM, Hybrid Studio UI,
  hosted LLM provider account.

### Test baseline
- `pytest -m 'not slow'`: **356** passed · 2 deselected
- Rust `organism-control-loop`: 3 passed

## [1.8.1] — 2026-10-24

### Added
- **Bundle path feedback** — Evolution panel `organism_bundle_path` +
  `organism_bundle_feedback` show export/import path and ok/error status;
  import reads the path field (falls back to last export / newest zip).
- **Active Organism shell badge** — `shell_organism_badge` in the Desktop header;
  updates on create/switch/import/refresh/theme apply (`MainWindow.update_organism_badge`).
- **Generative soak** — N evolve → promote → rollback cycles with registry leak
  check (service + offscreen UI); theme evolve interleaved.
- Service tracks `_last_bundle_path` on export/import.

### Fixed
- Weak Desktop v1.8 panel assertion on `organism_profile_combo` (was always-true).

### Safety
- Bio `may_actuate=False` unchanged; promote gates remain mandatory.
- Naming remains **Organism** only. No Hybrid Studio; CPU Everywhere.
- NiceGUI status page not added (out of STATUS scope).

### Changed
- Package / SDK / Desktop / generative module versions **1.8.1**.

### Test baseline
Default suite: **334 passed**, 0 skipped, 2 slow deselected.

## [1.8.0] — 2026-10-24

### Added
- **Looks → Desktop theme apply** — Organism appearance palette drives shell
  accents (`MainWindow.apply_organism_theme`, offscreen-safe QSS).
- **Rollback deregisters GeneratedSkillModule** — code promote rollback/demote
  removes hot-registered modules from `ModuleRegistry` + dynamic catalog.
- **Multi-Organism store** — create/switch `OrganismProfile` in Desktop Evolution
  panel; active id persisted.
- **Export/import Organism bundle** — zip (`organism_bundle_v1`) with profile +
  skill packs + appearance + asset bodies; import keeps skills RESEARCH_TIER.
- SDK: `theme.py`, `bundle.py`; EvolutionRuntime `after_rollback`.
- Docs: `docs/v1.8/DESKTOP.md`, `docs/v1.8/ORGANISM_SURFACES.md`.

### Safety
- Bio `may_actuate=False` unchanged; generative hot-register never actuates.
- Promote gates remain mandatory; imported skills cannot control until promote.
- Naming remains **Organism** only. No Hybrid Studio; CPU Everywhere.

### Changed
- Package / SDK / Desktop / generative module versions **1.8.0**.

### Test baseline
Default suite: **329 passed**, 0 skipped, 2 slow deselected.

## [1.7.2] — 2026-10-24

### Added
- **EvolutionRuntime** — generative promote → `ModuleRegistry` hot-register with
  shadow gate (`SANDBOXED` → `SHADOW_VALIDATED` → `EXPLORATION`); dynamic
  catalog entries for promoted skill/code modules (`may_actuate=False`).
- **EvolutionTraceEntry** / `TraceEmitter.emit_evolution` — evolution events on
  draft / promote / demote / quarantine.
- **Hormone pulse** (optional) on promote — dopamine/oxytocin bump via
  `HormoneBus.write_telemetry_window`.
- **ImmuneLayer quarantine** — drafts that fail contracts are demoted under
  QUARANTINE/DEMOTE decisions.
- **Wall-clock budgets** — `evolve_ms` / `promote_ms` on `CodePipeline`;
  `EVOLVE_P95_MS` / `PROMOTE_P95_MS` / hot-register / quarantine budgets in
  `EvolutionRuntime.PipelineTiming`.
- Desktop e2e: evolve skill → improve from trace → promote → appear in catalog.

### Safety
- Bio `may_actuate=False` unchanged; generative hot-register never actuates.
- Promote gates remain mandatory; unsafe promote → `PromoteRefused` /
  `ActuationRefused`.
- Naming remains **Organism** only. No Hybrid Studio; CPU Everywhere.

### Changed
- Package / SDK / Desktop / generative module versions **1.7.2**.

### Test baseline
Default suite: **319 passed**, 0 skipped, 2 slow deselected.

## [1.7.1] — 2026-10-24

### Added / Hardened
- **Generative code production**: richer template library; `GeneratorBackend`
  protocol; replayable drafts (`DraftReplayLog`); expanded AST forbid list;
  shadow scoring metrics; `rollback_last_promote`; concurrent-safe
  `ArtifactStore` (atomic writes + content-hash verify).
- **Asset pipeline**: multi-asset packs (avatar + theme + icon); content-hash
  integrity; Desktop preview bytes/text; reject oversized/malformed; theme
  contrast checks (≥ 3.0).
- **Skills**: pack versioning + history; dependency DAG with cycle refusal;
  `improve_from_trace` via evolution_log; promote requires shadow threshold.
- **Desktop Evolution panel**: pipeline stage progress, rollback button, asset
  preview, skill DAG view, Improve from trace, looks **pack** kind.
- **Gates**: `v17:generative` covers fuzz of unsafe code drafts (must refuse).
- Docs: production ops notes in `ORGANISM_GENERATIVE_EVOLUTION.md`.

### Safety
- Bio `may_actuate=False` unchanged; sandbox/promote refusals hardened.
- Naming remains **Organism** only (not Sophont).
- No Hybrid Studio; CPU Everywhere.

### Changed
- Package / SDK / Desktop / generative module versions **1.7.1**.

### Test baseline
Default suite: **313 passed**, 0 skipped, 2 slow deselected.

## [1.7.0] — 2026-10-24

### Added
- **Organism Generative Evolution** — production-grade pipelines so Organisms can
  self-evolve **code**, **looks (assets)**, and **skills** under promote gates.
- SDK `organism_sdk.generative`: `CodePipeline`, `SafeSandbox`, pluggable
  `TemplateDraftBackend` / `LLMStubBackend`, `AssetPipeline` + `AppearanceProfile`,
  `SkillDescriptor` / `SkillRegistry`, `OrganismProfile` / `OrganismStore`,
  versioned `ArtifactStore` + provenance.
- Module `generative_organism` (RESEARCH_TIER, `may_actuate=False`) + catalog entry.
- Desktop **Organism Evolution** panel (13th): Evolve Skills / Looks / Code
  Promotions / Evolution Log; service APIs wired through `DesktopService`.
- Docs: `docs/v1.7/ORGANISM_GENERATIVE_EVOLUTION.md`, `docs/v1.7/DESKTOP.md`.
- Tests: SDK generative suite + Desktop organism evolution / catalog / gate.

### Safety
- Code exec sandbox-only (no arbitrary shell / imports / `open`).
- Promote without full gate → `PromoteRefused` / Desktop `ActuationRefused`.
- Generative drafts cannot declare `may_actuate=True`.
- Bio actuation remains hard-refused; no Hybrid Studio; CPU Everywhere.
- Naming is **Organism** throughout (not Sophont).

### Changed
- Package / SDK / Desktop versions **1.7.0**.

### Test baseline
Default suite: **296 passed**, 0 skipped, 2 slow deselected.

# Changelog

## [1.6.1] — 2026-10-24

### Added
- **Hormone / physiology timeline** — Physiology table of virtual-clock
  `hormone_state` windows; emits `HormoneTraceEntry`; **Open Traces** jump.
- **Degradation drillbook UI** — scripted L0→L4 with confirm dialog + reset;
  `docs/ops/DEGRADATION_DRILLBOOK.md` safety notes.
- **Federation / oxytocin stub** — multi-node mirror lag + quorum exploration
  (explicitly not production WAN BFT+TPM).
- **Rust runtime status** — Ops read-only crate inventory + optional
  `cargo metadata` probe (no forced build on refresh).
- **Soak / fuzz from Desktop** — Ops triggers short harness runs; writes
  `desktop/artifacts/soak_*.json` / `fuzz_*.json` with progress + path.
- UX: tooltips, empty hormone/bio states, bio actuation messaging polish.
- Tests: hormone timeline, drillbook confirm, federation stub, rust/ops harness,
  physiology panel Qt interactions.

### Changed
- Package / SDK / Desktop versions **1.6.1**.
- Docs links include Degradation Drillbook + Desktop v1.6.1.

### Security / safety
- Bio actuation remains hard-refused (`ActuationRefused`).
- Drillbook refuses without `confirm=True`; virtual clock only.
- Federation stub labeled `not_production_bft` / `stub_only`.
- Rust probe is read-only.

### Test baseline
Default suite: **280 passed**, 0 skipped, 2 slow deselected.


## [1.6.0] — 2026-10-24

### Added
- **Trace explorer** — filterable table (`kind` / `task_id` / `emitted_at` / seq);
  **Export JSON**; **Jump from last pipeline** (`traces_for_last_pipeline`).
- **Router / plan inspector** — structured summary, ranking_trace steps, excluded
  table in Pipelines; **Open result in Traces**.
- **Multi-profile deploy** — `deploy/config/default.yaml` (profile `default`,
  health port 8788); Ops profile combo + `switch_deploy_profile` with
  status_facts delta; allowed profiles include `default`.
- **Module catalog** panel — 10 substrates, **RESEARCH_TIER** badges
  (`snn_sentinel`, `physical_research`), one-click `register_catalog_module`.
- **Contracts / Assert** panel — `run_contract_checks` /
  `last_contract_results` over registered + bio modules.
- Packaging note: `desktop/docs/PACKAGING.md` (PyInstaller sketch);
  `docs/v1.6/DESKTOP.md`.
- Tests: trace explorer, plan inspector, multi-profile, catalog, contracts,
  panel Qt interactions; deploy default.yaml.

### Changed
- Package / SDK / Desktop versions **1.6.0**.
- Navigation: **12 panels** (Catalog + Contracts); shortcuts Ctrl+1–0 /
  Ctrl+Alt+N for panels 11+.
- `list_traces` adds `seq`, `kind`, `emitted_at`, optional `task_id` /
  `since_iso` filters.

### Security / safety
- Bio actuation remains hard-refused (`ActuationRefused`).
- RESEARCH_TIER catalog register refuses if contract declares `may_actuate=True`.
- Profile switch stays CPU-first (`prefer_gpu: false` on both profiles).

### Test baseline
Default suite: **269 passed**, 0 skipped, 2 slow deselected.

## [1.5.2] — 2026-10-24

### Added
- Shared **CLI ↔ Desktop status parity** (`organism_sdk.deploy.status_facts`):
  `common_status_facts` / `enrich_cli_status` / `PARITY_KEYS`; `organism status`
  JSON now includes `cpu_everywhere`, `organism_version`, `device_runtime`.
- `DesktopService.status_parity`, `soak_snapshot`, `refresh_bundle`.
- Home / Ops polish: live CPU Everywhere + deploy profile badges, soak snapshot
  + runbook path, CLI parity block on Home.
- Keyboard shortcuts: **Ctrl+R** refresh panel, **Ctrl+Shift+R** refresh-all,
  **Ctrl+1–0** jump panels; status-bar **toasts** for errors (non-silent).
- Tests: CLI/Desktop parity, e2e register→bind→decide→traces→L0→L1,
  desktop refresh soak (50× offscreen), CLI status enrichment.

### Changed
- Package / SDK / Desktop versions **1.5.2**.
- `--smoke` prints parity line and runs refresh-all once.

### Security / safety
- Bio actuation remains hard-refused (`ActuationRefused`); e2e asserts refuse
  after full flow. Wet-lab policy still deny-by-default.

### Test baseline
Default suite: **249 passed**, 0 skipped, 2 slow deselected.

## [1.5.1] — 2026-10-24

### Added
- Desktop panel deepenings: registry register/deregister, workspace bind/unbind,
  physiology L0→L1 safe demo, structured traces + emit demo, HAL twin refresh.
- `DesktopService.register_core_module` / `unbind_binding` / `simulate_l0_to_l1` /
  `emit_demo_traces` / `refresh_bio_twin`.
- Offscreen `--screenshot` → `desktop/screenshots/` (PNGs gitignored).
- Expanded `desktop/tests/` (panel Qt clicks, registry/workspace, physiology/traces).

### Changed
- Package / SDK / Desktop versions **1.5.1**.
- `BasePanel.refresh` documented as intentional no-op default; `set_json` helper.
- Bio HAL init uses `PHYSARUM_LIMITS` stub backend (fixes empty twin).

### Security / safety
- Bio module deregister via Desktop refused; actuation refuse tests strengthened.
- Physiology demo is virtual-clock only; never enables bio actuation.

### Test baseline
Default suite: **239 passed**, 0 skipped, 2 slow deselected.

## [1.5.0] — 2026-10-24

### Added
- **Organism Desktop** — first-party PySide6 control plane under `desktop/organism_desktop/`.
- Panels: Home, Registry, Workspace, Pipelines, Physiology, Metamodel, Bio-Digital,
  Traces, Ops, Docs (`docs/v1.5/DESKTOP.md`).
- `DesktopService` headless façade; bio actuation **hard-refused** (`ActuationRefused`).
- Console script `organism-desktop`; optional extra `[desktop]` (PySide6).
- Offscreen smoke (`--smoke` / `QT_QPA_PLATFORM=offscreen`); `desktop/tests/`.
- Design + plan: `docs/v1.5/`.

### Changed
- Package / SDK versions **1.5.0**.
- pytest `testpaths` / `pythonpath` include `desktop`.

### Security / safety
- Bio / wet-lab panels never enable `control_actuation`; `may_actuate` badges shown.
- Wet-lab policy viewer remains deny-by-default; UI cannot certify actuation.

### Test baseline
Default suite: **223 passed**, 0 skipped, 2 slow deselected.

All notable changes to Organism are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow SemVer for the **frozen** surface in `docs/API_FREEZE_v1.0.md` (additive integrations in 1.x).

## [1.4.0] — 2026-10-24

### Added
- **Single-device CPU-only deploy** — `deploy/config/cpu_only.yaml`, Dockerfile,
  systemd unit, entrypoint; CLI `organism` / `python -m organism_sdk`
  (`validate-config`, `status`, `serve`) with `/health` + `/status`.
- **Soak / target-box runbook** — `docs/ops/SOAK_RUNBOOK.md`,
  `scripts/soak_target.sh`, soak reconstructibility helper + env overrides.
- **Torch optional accelerator clarity** — `ORGANISM_TORCH=0` force-CPU;
  `accelerator_selection_summary()`; CUDA only when opted in + present;
  mocked device tests with **no default-suite skips**.
- **Wet-lab HAL stub + SafetyPolicy** — `bio_digital.wetlab`; actuation denied
  until certified policy **and** `ORGANISM_WETLAB_GPIO=1`; sim loop; clamps;
  `docs/ops/WETLAB_SAFETY_POLICY.md`.
- Gates: `v14:deploy`, `v14:soak_ops`, `v14:wetlab`.
- Plan: `docs/v1.4/PLAN.md`.

### Changed
- Package / SDK / bio module versions **1.4.0**.
- `docs/CPU_EVERYWHERE.md` documents optional torch install path.

### Security / safety
- Wet-lab default `SafetyPolicy.deny_all`; bio modules remain `may_actuate=False`.
- Real GPIO open refused without env+policy; missing device → `device_missing`.

### Test baseline
Default suite: **209 passed**, 0 skipped, 2 slow deselected.

## [1.3.0] — 2026-10-24

### Added
- **CPU Everywhere** product guarantee — every RESEARCH_SIM / GPU-labelled workload
  runs on `CPU_GENERAL` when accelerators are absent (`docs/CPU_EVERYWHERE.md`).
- `organism_sdk.device` — `RuntimeId`, `select_compute_backend`, `resolve_requires_gpu`,
  `CPU_HOSTABLE_HARDWARE`; never hard-fails on missing GPU/CUDA/torch.
- Bio wave twin **NumPy** backend (`numpy_cpu`) — same diffusion math as torch path.
- Blocking CI gate **`cpu:everywhere`**.
- `neuromorphic_cpu_backend()` on `neuro_sim`.

### Changed
- Package / SDK / bio module versions **1.3.0**.
- Default wave twin backend is `numpy_cpu` (not HAL stub).
- `ORGANISM_BIO_GPU_TWIN=1` without torch/CUDA runs NumPy wave (no pytest skip).

### Removed
- Torch-missing **skip** in default GPU twin tests (converted to CPU assertions).

### Security / safety
- Bio modules remain `may_actuate=False`.
- Twin / telemetry still `affects_control=False`.

### Test baseline
Default suite: **223 passed**, 0 skipped, 2 slow deselected.

## [1.2.0] — 2026-10-24

### Added
- **Live Hybrid import** — `bio_digital.vendor_loader` loads real HAL / slime_mold / mycelium when `BIO_DIGITAL_HYBRID_ROOT` (or default checkout) is present; stub fallback otherwise.
- **Telemetry bridge** — NodeStatus / EnvironmentState / metrics → `HealthReport.probes` + optional hormone stress; workspace mirror `affects_control=False`.
- **Hypervisor drill** — Active/Standby drain→promote; kill ACTIVE mid-flight; CI gate `v12:hypervisor_drill`.
- **Optional GPU twin** — torch wave sim behind RESEARCH_SIM + `ORGANISM_BIO_GPU_TWIN`; CPU HAL twin default; skip-clean without torch.
- `HealthReport.probes` additive field (API freeze additive).

### Changed
- Package / SDK versions **1.2.0**.
- Bio species module versions **1.2.0**.

### Security / safety
- Bio modules remain `may_actuate=False`; hypervisor events never control path.
- Twin / telemetry feeds mark `affects_control=False`.

### Test baseline
Default suite: **167 passed**, 1 skipped (torch), 2 slow deselected.

## [1.1.0] — 2026-10-24

### Added
- **Bio-Digital Hybrid Cluster integration** — mapping doc `docs/integrations/BIO_DIGITAL_HYBRID_CLUSTER.md`.
- RESEARCH_TIER modules: `bio_digital.slime_mold` (*Physarum*), `bio_digital.mycelium` (*Pleurotus*).
- HAL facade (`RESEARCH_SIM`), bus adapter (declared Channels + VSA workspace results), twin bridge (`bio_twin` → workspace / optional hormone feed), hypervisor `DrainPolicy` + hot-swap/apoptosis map.
- Vendor note `modules/bio_digital/VENDOR.md` (no GUI copy; optional `BIO_DIGITAL_HYBRID_ROOT`).
- Invariant tests: exploration-only, contract validate, twin→workspace, no control dispatch.

### Changed
- Package / SDK versions **1.1.0**; Cargo workspace **1.1.0**.

### Security / safety
- Bio-digital modules: `may_actuate=False`, hard-refuse `control_actuation`, `MaxSafetyTier.RESEARCH`, `HardwareRequirement.PHYSICAL_SUBSTRATE`.

### Test baseline
Default suite: **150 passed** (2 slow deselected).

## [1.0.0] — 2026-10-24

### Added
- **Software Organism complete** — Phases A–H per `docs/v1.0/PLAN.md`.
- Substrate ecology modules: `kernel_module`, `hdc_module`, `reservoir`, `energy_hopfield`, `spectral`, `neurosymbolic`.
- Full RL-DCA `train_online_loop`; learned ISE **promote + revoke**; live tiny NAS search.
- Multi-**process** cluster with oxytocin quorum (≥3), BFT-ish (f=1, N=4), clock skew injection.
- `ORGANISM_NEURO_SIM=1` neuromorphic RESEARCH_SIM; `physical_research` exploration-only module.
- Rust `organism-router` + `organism-degradation` parity with Python core paths.
- API freeze `docs/API_FREEZE_v1.0.md`; hardening guide `docs/v1.0/HARDENING.md`.

### Changed
- Package / crate / SDK versions aligned to **1.0.0**.
- README + STATUS declare software Organism **COMPLETE**.

### Out of scope (true external deps)
Real neuromorphic silicon, wet-lab/molecular physical substrates, production WAN BFT / TPM attestation.

### Test baseline
Default suite grows substantially beyond v0.4.0 (see STATUS.md).

## [0.4.0] — 2026-10-24

### Added
- **API freeze** — `docs/API_FREEZE_v1.0.md` (stable Python SDK + `organism.v1` proto; experimental biology / multi-node / SNN called out).
- **v0.4 hardening (M0–M3)**
  - Soak harness (`harness/scenarios/v04_soak.py`) with GC pressure and reconstructible traces; full soak via `ORGANISM_SOAK_FULL=1`.
  - Perf budgets (`docs/v0.4/PERF.md`) + blocking `perf:router` / `perf:workspace` / `perf:hormone` / `perf:degradation` gates.
  - Security fuzz: malformed contracts, unjustified control actuation, Byzantine → L4, capability-scope violations, immune quarantine forgery.
- **v0.3 E.8 lifts (M0–M4)** — learned ISE + RL-DCA (shadow), metamodel synthesizer (exploration), in-process multi-node + oxytocin, SNN sentinel (HW-gated).
- **v0.2 biological organs** — HormoneBus, ISE, Immune, Autonomic/apoptosis, circadian, morphogenesis; full J–O fault matrix.
- **v0.1 M1–M7** — proto, Python SDK, deterministic_engine, registry, workspace, router, learned_module, snapshots, degradation, two-module bootstrap + CI.

### Changed
- Package / crate / SDK versions aligned to **0.4.0**.
- README status refreshed to v0.4.0-ready.

### Security
- Immune forgery rejection without FULL / affects_control / immune_layer.
- Justification required for untrusted `control_actuation`.
- Capability-scoped workspace write/read enforcement under fuzz.

### Out of scope (unchanged)
Real neuromorphic silicon, full BFT cluster, live NAS, molecular/physical substrates on the control path.

### Test baseline
Default suite: **115 passed** (2 slow deselected).

## [0.3.0] — 2026-10-24

Internal milestone line (learned ISE, metamodel, multi-node sim, SNN sentinel). Superseded by 0.4.0 packaging.

## [0.2.0] — 2026-10-24

Biological extension (HormoneBus through morphogenesis + J–O matrix). Superseded by 0.4.0 packaging.

## [0.1.0] — 2026-10-24

Initial closed-corpus implementation (Batch 1 + M1–M7).

[0.4.0]: https://github.com/RechargedIdeas/organism/releases/tag/v0.4.0

[1.1.0]: https://github.com/RechargedIdeas/organism/releases/tag/v1.1.0

[1.0.0]: https://github.com/RechargedIdeas/organism/releases/tag/v1.0.0
