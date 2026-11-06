# Encoder benchmark

This suite compares the candidate sentence encoders for the MoA intent router. It loads each model
on its own, measures it, puts a small trained head on top, and scores the head with stratified
cross-validation. Two controls run alongside: a majority-class baseline and the lexical router that
ships in `organism_sdk`.

It answers three questions: which encoder routes best, what each one costs on CPU (load time,
memory, latency, throughput), and what the lexical router scores on the same rows.

## Layout

| Path | What it is |
|---|---|
| `models.toml` | The model registry: name, Hugging Face repo, kind, query prefix |
| `models.lock.json` | The commit, license and per-file SHA-256 of every downloaded model. Committed |
| `models/` | Downloaded weights. Git-ignored |
| `fetch_models.py` | Downloads each model at its locked commit (`--update` re-resolves them) |
| `build_dataset.py` | Builds `data/intent_routing.json` from the MoA routing sets in `sdk/python/tests/data` |
| `data/intent_routing.json` | 117 labelled queries with their source file. Committed |
| `organism_bench/probe.py` | `LinearProbe`: multinomial logistic regression, fitted deterministically |
| `organism_bench/adapters.py` | One interface over the sentence, static and hash encoders |
| `organism_bench/metrics.py` | Accuracy, macro-F1, wrong-route rate, per-label recall, bootstrap interval |
| `organism_bench/measure.py` | Measures one encoder, and computes the two controls |
| `organism_bench/worker.py` | Benchmarks one model in its own process |
| `run_bench.py` | Runs every model one at a time and writes the results and the table |
| `results/` | Output of a run. Git-ignored |
| `baseline/` | The committed baseline: a copy of the summary from a full run |
| `tests/` | Unit tests. They use the hash encoder, so they need no weights |

## Run it

Use the venv interpreter from the repository root. On Linux, use `.venv/bin/python`. The venv needs
the benchmark dependencies (`torch`, `transformers`, `sentence-transformers`, `huggingface_hub`,
`model2vec`, `psutil`) and `organism_sdk` importable from `sdk/python`.

```bash
.venv/Scripts/python.exe bench/fetch_models.py
.venv/Scripts/python.exe bench/run_bench.py
```

`run_bench.py` writes `summary.json`, `summary.md`, `controls.json`, and one JSON and log file per
model to `bench/results/<UTC time>/`. To run a subset, pass `--models minilm-l6,gte-small`.

## What is measured

Per encoder:

- **dim, params**: embedding dimension and parameter count.
- **load_s, peak_rss_mb**: time to load, and the largest resident memory seen by the worker. The
  worker samples memory at three points, so a peak between samples is not caught.
- **latency_ms p50, p95, max**: one query at a time, after warm-up, over every row.
- **batch_rows_per_s**: throughput for the whole set in one call.
- **scores**: out-of-fold results, averaged over `--seeds` repetitions of stratified
  `--folds`-fold cross-validation. Each entry shows mean and standard deviation across seeds.
- **accuracy_ci95_seed0**: a bootstrap interval for accuracy on the first seed's predictions.

Metric definitions (`organism_bench/metrics.py`):

- **accuracy, macro-F1**: over the three labels `intent_classifier`, `extractor`, `unsure`.
- **wrong route**: the share of all rows sent to an expert other than the one the label names. An
  unsure row sent to any expert counts. This is the property the routing tests guard.
- **recall per label**: the share of rows with that label predicted as that label.

## The models

The probe is a `LinearProbe` on frozen, standardised embeddings. It has `dim × 3 + 3` parameters.
It is fitted by full-batch gradient descent from a zero start, so a fit is deterministic. Its step
size comes from the curvature bound, so the descent cannot diverge.

The controls need no encoder:

- **majority class**: predicts the most common label of the training folds.
- **lexical router**: `LexicalScorer` with the reference experts, as the router uses it.

## Baseline

`baseline/summary.md` is the committed table from a full run: all six encoders plus both controls,
with 5 folds and 3 seeds, on CPU with 4 threads. Every model runs in float32. `baseline/summary.json`
holds the same numbers in full, with the host, revision and licence of each model.

## Caveats

- **The dataset is small.** It has 117 rows, and every row has already been used to design a
  routing rule. The probe scores are estimates from cross-validation on those rows, and the
  bootstrap interval shows how wide they are. They are not a measure of generalisation to new
  queries.
- **The lexical router is optimistic.** Its rules were tuned on these rows, so its score is not a
  fair comparison. It is shown as a reference point only.
- **Probe scores depend on the data.** A different split or a larger set can change the ranking
  of the encoders. Compare encoders on the same rows, and read the intervals before ranking any two.
- **Weights are pinned, not vendored.** `models.lock.json` pins each model to a commit and records a
  hash per file. If a file's hash changes, `fetch_models.py` will not notice on its own. Check the
  hashes before trusting a re-download.

## Adding a model

1. Add a `[[model]]` entry to `models.toml`. Use `kind = "sentence"` for a transformer and
   `kind = "static"` for a Model2Vec table. Models that need `trust_remote_code` are not accepted,
   because that runs code from the hub at load time.
2. Run `.venv/Scripts/python.exe bench/fetch_models.py --only <name>`.
3. Run `.venv/Scripts/python.exe bench/run_bench.py --models <name>`.
