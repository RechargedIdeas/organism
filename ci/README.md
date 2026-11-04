# Local CI pipeline

The pipeline runs on this machine. The `pipeline` job in `.github/workflows/ci.yml` runs
the full tier on Linux for pushes and pull requests to `main`, so the gates apply even
in clones without hooks. The local pipeline is the place where every
gate in [gates.yaml](gates.yaml) actually runs, with preflight checks, caching, lint
ratchets, and hooks.

```bash
python ci/run.py run --tier fast        # what pre-push runs
python ci/run.py run --tier precommit   # what pre-commit runs (about 1 second)
python ci/run.py status                 # the last run, in full
```

On Windows use `.venv\Scripts\python ci\run.py ...`. The runner re-executes itself under
`.venv` when PyYAML is missing from the interpreter you start it with.

## Tiers

| Tier | Runs | Typical time | When |
|---|---|---|---|
| `precommit` | staged-file hygiene, ruff ratchet | about 1 s | every commit (hook) |
| `fast` | preflight, tree hygiene, lint and format ratchets, every blocking gate tagged `fast` | a few minutes; unchanged gates are skipped (`CACHED`), timing gates always run | every push (hook) |
| `full` | `fast` plus gates tagged `full` (desktop smoke) | fast plus a few minutes | before merging |
| `nightly` | `full` plus the opt-in slow suites (`ORGANISM_WALL_CLOCK_FULL`, `ORGANISM_SOAK_FULL`) | 30 minutes or more | scheduled |

A gate runs in its own tier and every tier above it.

A gate whose inputs are unchanged shows `CACHED` and is not run again. Gates that measure time
(`cacheable: false`) always run, so an unchanged `fast` run still takes a couple of minutes. Ctrl-C
stops every gate process the run started, and the run does not return until they are gone. Run
directories older than the newest 20 are pruned at the start of each run.

## What a run does

1. **Lock.** One run at a time. A stale lock (its process is gone) is taken over.
2. **Preflight.** Checks the runner Python, the venv Python and its modules, git, free
   disk, that the run directory is writable, that protobuf modules are current (and
   regenerates them when stale), `protoc`, `cargo`, `rustfmt`/`clippy`, and that pytest
   collects every test without an import error. A FAIL stops the run before any gate
   starts, with the command that fixes it.
3. **Gates.** Parallel up to `jobs`. Gates marked `exclusive` run alone afterwards, so
   machine load cannot push a wall-clock budget over its limit.
4. **Report.** `ci/runs/<stamp>-<tier>-<pid>/report.json` holds everything. The console
   shows only what needs attention. `ci/runs/latest.json` always points at the last run.

Exit codes: `0` pass, `1` a blocking gate failed, `2` preflight failed, `3` internal
error, `4` configuration error, `5` another run holds the lock, `130` interrupted.

## Gate statuses

| Status | Meaning | Fails the run? |
|---|---|---|
| `PASS` | Ran and passed | no |
| `CACHED` | Passed earlier on identical inputs (same files, command, environment, toolchain) | no |
| `FLAKY` | Failed, then passed on a retry. Always shown, never hidden as `PASS`. | no |
| `FAIL` | Exit code non-zero | yes, if blocking |
| `ERROR` | Timed out, or could not start | yes, if blocking |
| `SKIP` | A required tool is missing, or fail-fast stopped it | yes, if blocking (unless `--allow-skips`) |

A non-blocking gate (`blocking: false`) is reported as advisory and never fails the run.

## Lint and format ratchets

`lint:ruff`, `lint:mypy`, and `rust:fmt` compare current findings with a baseline in
[baselines/](baselines/). A run fails only when a finding is new, or when a file gains
more findings than the baseline recorded. Fixing findings passes and reports the
improvement. The baseline never rises by accident. To lower it after fixing issues:

```bash
python ci/run.py baseline ruff     # or mypy, rustfmt
```

Review the diff in `ci/baselines/` before committing it.

## Hooks

```bash
python ci/run.py hooks install     # sets core.hooksPath to ci/hooks (local to this clone)
python ci/run.py hooks status
python ci/run.py hooks uninstall
```

`pre-commit` runs the `precommit` tier. `pre-push` runs the `fast` tier. Either can be
bypassed for one operation with `--no-verify`. Do that rarely: the run is the record
that the change works.

## Scheduled nightly runs (Windows)

`ci/schedule/windows_nightly.ps1` registers a daily Task Scheduler job that runs the
`nightly` tier. It does not register anything until you run it:

```powershell
powershell -ExecutionPolicy Bypass -File ci\schedule\windows_nightly.ps1 -At 02:00
powershell -ExecutionPolicy Bypass -File ci\schedule\windows_nightly.ps1 -Remove
```

On Linux, the equivalent is a cron line: `0 2 * * * cd /path/to/Organism && python3 ci/run.py run --tier nightly`.

GitHub runs the same nightly tier at 02:00 UTC from `.github/workflows/nightly.yml`, and that workflow also runs an advisory dependency audit (`pip-audit` and `cargo audit`). The audit reports but never fails the run. Use `workflow_dispatch` to start either job by hand.

## Configuration

- [gates.yaml](gates.yaml): the gates. Every field is documented at the top of the file.
  Unknown keys are rejected, so a typo such as `blockign: false` fails loudly.
- [pipeline.toml](pipeline.toml): defaults, the environment every gate inherits,
  preflight requirements, hygiene rules, lint paths, and protobuf settings.

To add a gate, add an entry to `gates.yaml` and run `python ci/run.py list --tier <tier>`
to confirm it is picked up. Use `{python}` for the venv interpreter; never hard-code
`.venv/bin` or `.venv\Scripts`.

## Caching and logs

- The cache lives in `ci/cache/` (one file per gate, holding its last eight passing keys, so a
  terminal run and a git hook run do not evict each other). A key covers the gate id, the
  resolved command and environment, the Python, protoc, and cargo versions, and the bytes
  of the gate's inputs. Only passing results are stored. Gates marked `cacheable: false`
  (timing budgets, full suites) never use the cache.
- Logs for each gate are in `ci/runs/<run>/logs/`.
- `python ci/run.py prune --keep 20` removes old run directories.
- `ci/runs/`, `ci/cache/`, and the lock file are gitignored.

## Hygiene

The `hygiene:*` gates block these from being committed: paths under `chat_archive/` or
`organism-chats/`, `*.trace`, `.env`, `*.pem`, `*.key`, unresolved merge-conflict markers,
secret-shaped tokens (AWS keys, private-key headers, GitHub and Slack tokens), and files
over 5 MiB. Detector source and the CI test fixtures are exempt from the secret scan.
The list lives in `[hygiene]` in [pipeline.toml](pipeline.toml).

## Troubleshooting

- **`venv.modules` FAIL.** Run the install hint it prints. Use `.venv`, not the system Python.
- **`proto.generated` WARN then PASS.** Protobuf modules were stale and were regenerated. Nothing to do.
- **A gate shows `SKIP` with `missing: cargo` or `missing: protoc`.** Rust is not on this
  machine's path. Install rustup, or set `PROTOC` to a protoc binary. `protoc` is also
  available as the `protoc-wheel-0` package in `.venv`.
- **`busy: another pipeline run is active`.** Wait, or confirm no run is active and delete
  `ci/runs/.lock`. The runner also detects and clears a lock whose process has exited.
- **A gate is `ERROR` with `timed out`.** The gate exceeded its `timeout_s`. Raise it in
  `gates.yaml`, or pass `--timeout-scale 2` once to see whether the gate is simply slow.
- **Re-run a single gate.** `python ci/run.py run --only <gate-id> --no-cache`.

## Tests

The pipeline's own behaviour is tested in [tests/ci/](../tests/ci/):

```bash
python -m pytest -q tests/ci
```

They run as part of the fast suite. They use short real child processes, not mocks, for
timeouts, retries, and cache behaviour.
