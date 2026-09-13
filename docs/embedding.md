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

## Vector (semantic) search

`knowledge_base.search.similar` embeds a query with the *same* provider used
at index time and returns the nearest stored chunk vectors by cosine distance,
ranked by similarity score (`1 - cosine distance`). The query embedding must
use the same model family as the stored vectors; results are scoped to one
`embedding_models` row (name, or name + version — omit the version for the
latest registered).

```pwsh
knowledge-base similar "importance of patience"                       # top 20
knowledge-base similar "sabr and perseverance" --min-score 0.3        # threshold
knowledge-base similar "sabr and perseverance" --category tafsir
knowledge-base similar "hadith narrators" --book 8e3ba214de62 --language ar
knowledge-base similar "fasting" --source-type pdf --author "ibn"
knowledge-base similar "patience" --limit 5 --json                    # machine-readable
```

Every `VectorHit` keeps full provenance so vector search never loses
traceability: chunk id + content id, book id/title, chapter id/title, section
id/title, page number, source-file id + full SHA-256, source type (format),
language, and the matched text.

Filters (all optional, combinable): `category` (category code), `book`
(source SHA-256 prefix), `language` (`ar`/`ur`/`en`), `source_type` (file
format), `author` (substring), and `min_score` (drop hits below a similarity
threshold). Results default to all embedded chunks of the model; a model or
provider mismatch raises a dimension error rather than returning junk.

Tests: `uv run pytest tests/test_vector_search.py -q` (relevance ranking,
provenance integrity, model/version scoping, every filter, empty queries).

## Hybrid search (keyword + semantic)

`knowledge_base.search.hybrid_search` runs **both** retrievers for every
query and fuses them into one result set:

```
query → keyword candidates (search_documents tsvector)
         + semantic candidates (embeddings cosine)
       → normalized weighted score per chunk   (ranking)
       → deduplication by chunk                (fusion)
       → source-rich HybridHit results
```

- **Configurable weighting** — `weight_fts` / `weight_vector` (both default
  0.5). Set one to 0 to disable a path: `weight_vector=0` for keyword-only,
  `weight_fts=0` for semantic-only.
- **Never semantic-only by design** — when the embedding provider is
  unavailable the keyword path still runs (keyboard-only fallback); keyword
  retrieval never depends on embeddings.
- **Ranking** — keyword ranks are normalised by the pool maximum, so both
  contributions live in the same `[0,1]` space: score = `w_fts·norm_rank +
  w_vec·similarity`. Each hit reports its raw `fts_score`, `vector_score`,
  weights, and the `retrievers` that found it.
- **Semantic recall** — passages that share little vocabulary (e.g. a query
  about "importance of patience" surfacing a passage on *sabr, perseverance,
  self-control, forgiveness*) are recovered by the semantic path even though
  keyword matching cannot see them, while exact keyword matches still rank
  via the keyword path.
- **Provenance** — every `HybridHit` carries book/chapter/section/page,
  source SHA-256 + file id + format, language, content id and chunk id, and
  the original text.

```pwsh
knowledge-base hybrid "importance of patience"                 # fused top 20
knowledge-base hybrid "prayer" --weight-vector 0               # keyword-only
knowledge-base hybrid "fasting" --weight-fts 0.3 --weight-vector 0.7
knowledge-base hybrid "sabr" --category fiqh --language en --json
```

Tests: `uv run pytest tests/test_hybrid.py -q` (Islamic evaluation queries:
semantic recall without exact keywords, keyword-only degradation, weighting,
deduplication of fused hits, provenance integrity).