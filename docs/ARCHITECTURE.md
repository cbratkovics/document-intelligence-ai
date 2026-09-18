# Architecture and evidence

This is the single maintained description of how the system works, which
invariants it keeps, and what evidence backs each claim. It replaces the
earlier architecture, enterprise-feature, performance, and optimization
documents, which described components that were never connected.

## Supported deployment boundary

One API process serves one corpus from one data directory. This is a local,
single-process design:

- The manifest (SQLite) is the authoritative record of documents, versions,
  chunks, and lifecycle status.
- The BM25 index lives in process memory and is rebuilt from the manifest
  after every committed change. A second process would not see the first
  process's changes until it restarted, so multi-worker serving (for example
  `uvicorn --workers 2`) is unsupported and not tested.
- The vector index is an embedded Chroma collection under `DATA_DIR/index`.

`STORAGE_MODE=ephemeral` is explicit: manifest and vectors live in memory and
reset on restart. A failure to open persistent storage is a startup error
reported by `/health` and `/ready`; it never silently falls back to memory.

## Components (`src/`)

| Module | Role |
|---|---|
| `core/config.py` | Settings; provider resolution (`auto`), limits, no side effects at import |
| `core/types.py` | Typed contracts: `DocumentRecord`, `ChunkRecord`, `SourceLocation`, `QueryScope`, `SearchHit` (separate score fields), `AnswerStatus`, `Citation` |
| `utils/document_loader.py` | Filename normalization, extension and content checks, UTF-8/UTF-16 decoding, PDF extraction with page spans, upload storage with server-generated names |
| `core/chunking.py` | Character chunker preserving `[char_start, char_end)` offsets, page ranges, Markdown sections; bounded chunk counts; guaranteed progress |
| `core/manifest.py` | SQLite schema and operations; corpus generation counter |
| `core/embeddings.py` | `openai`, `local` (sentence-transformers, offline unless allowed), `fastembed` (ONNX Runtime, offline unless allowed), `hash` (test-only), `none` |
| `core/vector_store.py` | Chroma wrapper: cosine space, embedding-identity metadata, scoped queries, paginated enumeration |
| `core/lexical.py` | BM25 scorer (k1=1.5, b=0.75, Lucene IDF, English stopwords removed) and scoped in-memory index |
| `rag/service.py` | Ingestion, replacement, deletion, consistency report |
| `rag/hybrid_search.py` | Reciprocal rank fusion by chunk id with explicit weights |
| `rag/reranker.py` | Heuristic, LLM, and cross-encoder reranking with failure status |
| `rag/retriever.py` | Scope validation, mode resolution, candidate generation, hydration, reranking, truncation |
| `rag/generator.py` | Context budgeting, grounded prompting, citation validation, streaming, summaries, LLM judge |
| `rag/cache.py` | Bounded exact-match answer cache keyed by scope, corpus generation, and configuration |
| `api/` | FastAPI app factory, routes, schemas, API-key dependency, rate limiter, health, static review UI |
| `monitoring/metrics.py` | Optional Prometheus metrics with route-template labels |

## Data lifecycle invariants

1. Document IDs are server generated (`uuid4`). The display filename is stored
   separately and never used as a path. Stored files are named
   `<doc_id>.v<version><ext>` and created with `O_EXCL` inside `DATA_DIR/uploads`.
2. A document is searchable only while its manifest status is `ready`.
   Retrieval hydrates every candidate from the manifest and drops any chunk
   whose document is not ready or whose version is not the current one, so a
   stale vector can never be served.
3. Ingestion is staged: file -> manifest row (`indexing`) -> chunks -> vectors
   (if configured, verified present after write) -> commit (`ready`) -> BM25
   rebuild -> corpus generation bump -> answer cache cleared. Any failure
   rolls back chunks, vectors, and the file. A new document that fails stays
   visible as `failed` with its error and is never searchable. Re-uploading
   its bytes retries under the same id.
4. Identical bytes are deduplicated by SHA-256 content hash: a second upload
   returns the existing record with `created=false`. Content identity is not
   ownership; there is one shared corpus.
5. Replacement (`POST /documents/{id}/replace`) indexes version n+1 while
   version n stays searchable; only after commit are the old chunks,
   vectors, and file removed. Replacing with identical bytes is a no-op.
6. Deletion marks the document `deleted` first (so retrieval excludes it
   immediately), then removes vectors for every version, chunks, the file,
   and the manifest row, then rebuilds BM25 and clears the cache. If vector
   removal fails the request returns 500 with `deletion_incomplete`, the
   document remains excluded from retrieval, and a retry finishes the job.
   A repeated delete of a removed document returns 404.
7. The vector collection records the embedding identity and cosine space in
   its metadata. Opening a non-empty index with a different identity raises
   at startup (`/health` shows the error, `/ready` returns 503) instead of
   mixing incompatible vectors.
8. The chunking configuration id (`chars:v2:size=..:overlap=..`) is recorded
   per document so a configuration change is visible and can prompt a
   deliberate re-index.

## Retrieval and score semantics

- `lexical`: BM25 over every ready chunk. Scope filters candidates before
  ranking; corpus statistics are corpus-wide (single-corpus isolation model).
  A short English stopword list is removed from documents and queries, so a
  question made only of function words yields no lexical hits instead of
  feeding noise into fusion (`tests/test_indexes.py`).
- `vector`: cosine distance from Chroma; `vector_similarity = 1 - distance`
  is valid only because the collection is created with `hnsw:space=cosine`.
- `hybrid`: RRF with `score = sum(weight / (rrf_k + rank))`, `rrf_k=60`,
  `vector_weight = alpha`, `lexical_weight = 1 - alpha`. A zero-weight branch
  contributes no candidates. Identity is the chunk id, so duplicate text in
  two documents yields two hits. Ties break on chunk id.
- Candidate pool: `top_k * candidate_multiplier` per branch (bounded), fused,
  hydrated, reranked in full if requested, then truncated to `top_k`.
- `rerank_status` is `applied`, `disabled` (not requested), `unavailable`
  (requested but `RERANKER_MODE=none` or provider missing), or `failed`
  (original order kept, error reported). Failed LLM scores are never
  replaced with defaults.
- Every hit carries `vector_distance`, `vector_similarity`, `vector_rank`,
  `lexical_score`, `lexical_rank`, `fusion_score`, `fusion_rank` (position
  after fusion, before any reranking; hybrid only), `rerank_score` and the
  final `rank` separately. The response reports `candidate_k`, the number of
  candidates requested from each branch, so a missing branch rank can be read
  as "outside the top `candidate_k`". None of these is calibrated relevance
  or answer confidence.
- Requested `hybrid` without an embedding provider runs lexical-only and
  reports `mode_effective=lexical` with a note; requested `vector` returns 409.

## Answer generation

- Context is assembled in rank order under a character budget that accounts
  for the system prompt and question. A passage that does not fit is
  excerpted (never silently dropped as the only candidate) and the response
  records `context.truncated` plus which chunk ids entered the context.
- Evidence is rendered inside `<evidence>` / `<text>` delimiters with labels
  `[S1]..[Sn]`; the system prompt instructs the model to ignore instructions
  inside evidence and to reply `INSUFFICIENT_EVIDENCE` when unsupported.
- Statuses: `answered` (all citations resolve), `unverified_citations`
  (missing or unknown labels; answer returned but flagged),
  `insufficient_evidence`, `excerpts_only` (no provider or `generate=false`),
  `provider_error` (kept distinct from "no evidence").
- `retrieval_diagnostics` are descriptive statistics of the retrieved set and
  replace the old `confidence` field, which was an average of retrieval
  scores.
- The answer cache is exact-match and keyed by question, scope, corpus
  generation, mode, top_k, alpha, reranker, embedding identity, prompt
  version, model, and generation settings; responses report `cached=true`.
- Streaming (`/query/stream`) emits NDJSON events `meta`, `sources`, `delta`
  (provisional), and exactly one `done` or `error`. Validation errors occur
  before the response starts. Client disconnects close the provider stream.
- Summaries read the document's own chunks in order under the context budget
  and report coverage; they never use similarity search.
- The `/evaluate/judge` endpoint is an LLM rating with disclosed model and
  prompt version; parse failures are reported as `parse_failed`, not scored.

## Public-demo controls

All optional and off by default (`tests/test_demo_controls.py`):

- `DEMO_SEED_DIR`: files ingested in the lifespan handler after the services
  start. Their ids are protected from eviction and reported by `/health`.
  Failures are reported in `/health.seed_errors`, never raised.
- `MAX_DOCUMENTS`: before a new document is staged, the oldest unprotected
  documents (by `created_at`, microsecond precision) are deleted through the
  normal deletion path until one more fits. Uploads report `evicted`. When
  only protected documents remain the upload fails with 409 `corpus_full`.
- `RATE_LIMIT_PER_MINUTE` and `RATE_LIMIT_GLOBAL_PER_MINUTE`: sliding
  60-second windows enforced by middleware on `/api` paths, returning 429
  with `Retry-After`. The per-client key is the socket address, or the value
  of `CLIENT_IP_HEADER` when the request carries a valid API key.
- `/health` states the effective retrieval mode, embedding model, reranker,
  generation provider, ready document count and seeded ids so a client can
  label itself truthfully.
- Ephemeral services drop their Chroma collection on close; the embedded
  ephemeral client is process-global and would otherwise leak state across
  service instances in one process.

## Public demo deployment

`deploy/space/` holds the Hugging Face Space image and `demo.env`, the
runtime configuration: ephemeral storage, `EMBEDDING_PROVIDER=fastembed`
(MiniLM through ONNX Runtime, model downloaded at image build time and
offline afterwards), `GENERATION_PROVIDER=none`, heuristic reranker on
request, seeded samples from `data/samples/`, 4 MiB uploads, a 24-document
cap and rate limits. No provider SDK is installed in the image.
`tests/test_demo_safety.py` loads `demo.env` with a fake `OPENAI_API_KEY`
present and proves the stack starts, seeds, and answers hybrid queries with
every socket blocked and `openai` unimportable.

`frontend/` is the Next.js page deployed on Vercel. Its route handlers hold
the API key, expose only health, search, upload, document list and document
chunks, forward the visitor address as `X-Client-IP`, and scope every request
to the seeded documents plus the ids the browser uploaded. The Space is
deployed by `.github/workflows/deploy-space.yml` after CI succeeds on `main`.

## Access control and limits

- `API_KEY` unset: local mode, no authentication, bulk delete disabled (403).
- `API_KEY` set (16+ characters): every `/api/v1` route requires a matching
  `X-API-Key` (constant-time comparison); health endpoints stay open.
- Upload size is enforced while reading; filenames, metadata (flat scalars,
  reserved keys rejected), extracted text, PDF page count, chunk count,
  query length, and `top_k` are bounded by settings.
- CORS is off unless `CORS_ORIGINS` is set; credentials are never combined
  with a wildcard origin.
- Unknown request fields (for example the old `filters` and `stream`) are
  rejected with 422.

## Observability

Prometheus metrics (`/metrics`) use route templates, never document ids.
Per-stage timings for extraction, chunking, embedding, indexing, lexical and
vector search, and reranking are returned in responses (`timings_ms`). No
dashboards, uptime figures, or throughput numbers are published.

## Evaluation

`eval/retrieval_metrics.py` states its conventions (precision denominator k,
recall over judged relevant, nDCG gain `2^rel-1` with the ideal computed from
the full judged set, unanswerable queries reported separately, comparisons
paired by query id, undefined relative change from a zero baseline).
`eval/run_eval.py` ingests the sample corpus into a disposable index, runs
each mode, checks scope/replacement/deletion scenarios, and writes an
artifact with commit, dirty flag, source and corpus hashes, configuration,
per-query ranks, and denominators. `hash` embeddings prove plumbing only.

## Experimental code (`app/`)

`app/` predates the current pipeline and is not imported by the API, with one
exception: `RERANKER_MODE=cross_encoder` lazily loads
`app/reranking/cross_encoder.py`. See `app/README.md` for per-module status.

## Known gaps

- No OCR, DOCX, or HTML ingestion.
- Structural citation validation only; no entailment check.
- No multi-process or multi-tenant support.
- The transformer cross-encoder, sentence-transformers embeddings and the
  real fastembed model are not exercised in CI (they need prepared model
  files); fastembed plumbing is tested through a double.
- sentence-transformers 2.2.x needs `huggingface_hub<0.26`; the pin is in
  `requirements-ml.txt`. Its cache is `SENTENCE_TRANSFORMERS_HOME`, not
  `HF_HOME`.
