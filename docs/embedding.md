# Embeddings

Vector search over retrieval chunks. Each chunk of a published book gets one
vector in a pgvector column, tagged with the embedding **model** (name,
provider, version, dimensions) that produced it and the **SHA-256 hash of the
chunk text** it was generated from. Vectors are consumed later by ANN search
(HNSW index, cosine) — this stage only *generates and tracks* them.

## Provider architecture

No single AI provider is hard-coded into the pipeline. The processor talks to
a thin `EmbeddingProvider` interface:

```python
class EmbeddingProvider(Protocol):
    name: str
    version: str
    dimensions: int
    def embed(self, texts) -> list[list[float]]: ...
```

Providers are looked up by name via `build_provider`:

- `dummy` — built-in, deterministic, dependency-free hashing backend (unit-normed
  signed char-n-gram counts). Vectors are reproducible and similar text scores
  higher cosine similarity; used by tests and offline dev.
- `pkg.module:ClassName` — any custom provider (e.g. an `openai`, `ollama` or
  `sentence-transformers` backend). The class receives no constructor arguments
  and must expose `name`, `version`, `dimensions` and `embed`.

Retry and rate-limit resilience live next to the interface:

- `embed_with_retry` — retries `RateLimitedError` / transient `EmbeddingError`
  with exponential backoff (`backoff_seconds * 2 ** attempt`) up to
  `max_retries`.
- `RateLimiter` — optional client-side throttle (`calls_per_minute`,
  sliding-window quota) so bursty batches respect provider limits.

## Configuration

Env / `.env` (prefix `KB_`, defaults shown):

| Setting | Default | Meaning |
| ------- | ------- | ------- |
| `KB_EMBEDDING_PROVIDER` | `dummy` | provider name or class path |
| `KB_EMBEDDING_MODEL` | `kb-dummy` | model name used to tag vectors |
| `KB_EMBEDDING_MODEL_VERSION` | `0.1.0` | bump → full re-embed under a new model |
| `KB_EMBEDDING_DIMENSIONS` | `768` | must match the pgvector column width |
| `KB_EMBEDDING_BATCH_SIZE` | `64` | texts per provider call |
| `KB_EMBEDDING_MAX_RETRIES` | `3` | retries on rate limit / transient error |
| `KB_EMBEDDING_BACKOFF_SECONDS` | `1.0` | exponential backoff base |
| `KB_EMBEDDING_CALLS_PER_MINUTE` | `0` | client-side quota (0 = unlimited) |

Note: the `embeddings.vector` column is fixed at 768 dimensions (that
is what the HNSW index is built on). A differently-dimensioned model needs a
schema migration first.

## Incremental semantics

```pwsh
knowledge-base embed run --sha256 8e3ba214de62   # one book
knowledge-base embed run --all --limit 10        # capped batch
knowledge-base embed run --all --provider "pkg.module:MyProvider" --model "my-model"
```

Per book, per run (transactional, all-or-nothing):

- **unchanged** chunk (`content_hash` matches) → the stored vector is kept,
  `reused_count` — never re-embedded;
- **changed** chunk → vector regenerated in place, `updated_count`;
- **new model/version** → a new `embedding_models` row and fresh vectors for
  every chunk (`embedded_count`); old vectors stay under the old model;
- **provider failure after retries**, missing chunks, or a dimension mismatch →
  the run fails with a `FAILED` `EMBED` job, and **no partial vectors** are
  written (pending rows are only applied after every batch succeeds).

Every `EMBED` run replaces the book's single `ProcessingJob(job_type=EMBED)`
record and writes a report under `data/processed/embed/<sha256>.txt`.

## Verification

```pwsh
docker exec islam24x7-db psql -U knowledge_base -d knowledge_base -tAc "
SELECT m.name, m.version, m.dimensions, count(e.id)
FROM embedding_models m LEFT JOIN embeddings e ON e.model_id = m.id
GROUP BY m.name, m.version, m.dimensions;"
```

Tests: `uv run pytest tests/test_embedding.py -q` (provider determinism and
similarity, content-hash reuse, idempotency, model versioning, retries/rate
limits, failure handling).