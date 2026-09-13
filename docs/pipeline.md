# End-to-end ingestion pipeline

`knowledge-base pipeline run` drives a source file through every processing
stage in order and records per-stage outcomes, a verdict, and a report file.

## The plan

Each registered source runs this fixed plan:

```
inspect → extract → ocr → metadata → publish(gate) → structure → normalize
→ chunk → index → embed
```

The `publish` step is a gate, not a job: it needs either an already-materialised
`Book` for the source, or approval of the metadata candidates. With
`--auto-review`, high-confidence candidates are auto-approved and the book is
published. Without it the pipeline halts at the gate with `WAITING` until a
human approves candidates (see `docs/metadata.md`) and re-runs.

Each stage is idempotent and restartable:

- Stages already recorded as `SUCCEEDED` are skipped unless `--force` is set.
- `--from STAGE` / `--until STAGE` resume or cap the plan; `--continue-on-error`
  keeps going past a failed stage.
- OCR only reads the pages flagged by extraction, so text PDFs need no engine;
  the embed stage runs only when an embedding provider is available.

`stage_status()` exposes the plan plus where each stage currently stands, which
is what `pipeline status` prints.

## Usage

```pwsh
# ingest a raw book and run the whole plan (auto-approve + publish)
$env:KB_DATABASE_URL="postgresql+psycopg://knowledge_base:islam24x7_dev@localhost:5434/knowledge_base"
knowledge-base pipeline run --source "Books/sample.pdf" --auto-review
knowledge-base pipeline run --sha256 8e3ba214de62 --auto-review
knowledge-base pipeline run --all --limit 2 --auto-review --embed-provider kb-dummy

# resume from the structure stage, forcing its re-run
knowledge-base pipeline run --sha256 8e3ba214de62 --from structure --force --auto-review

# stop before chunking, then inspect where a source stands
knowledge-base pipeline run --sha256 8e3ba214de62 --until normalize --auto-review
knowledge-base pipeline status 8e3ba214de62 --json
```

`pipeline run` takes one of `--sha256 <prefix>`, `--source <path>` (ingests the
file first), or `--all [--limit N]`. Embedding knobs mirror the settings
(`--embed-provider`, `--embed-model`, `--embed-model-version`,
`--embed-dimensions`, `--embed-batch-size`); OCR knobs are
`--ocr-engine`, `--ocr-dpi`, `--ocr-languages`. `--json` prints the per-stage
outcomes as JSON.

Exit codes: `0` success, `1` a stage failed, `3` the run stopped `WAITING` at
the publish gate.

## Outcomes & reports

Each run returns a `PipelineResult`: the `overall` verdict
(`SUCCEEDED` | `WAITING` | `FAILED`) and one `StageOutcome` per stage with
status, detail, count, error, and elapsed time. A human-readable report is
written to `data/processed/pipeline/<sha256>.txt`:

```
Pipeline for 8e3ba214de62 (source a1b2c3d4)
Book: 57b91e3f2d41
Overall: SUCCEEDED

SUCCEEDED inspect  [96]  text_pdf
SUCCEEDED chunk    [31]  chunks=31 tokens=12040
SUCCEEDED embed    [31]  embedded=31 updated=0 reused=0
```

## Hits & gates

- A stage that never ran is `not_run`; the publish gate is `succeeded` when a
  `Book` exists, otherwise `waiting`.
- Failure of one stage stops the plan at that point (unless
  `--continue-on-error`), and the whole run reports `FAILED`.
- `run_pipeline_all` and `run_pipeline_from_file` are the library entry points
  for batch runs and ingest-then-run.