# Engineering case study and portfolio guide

This document explains the engineering story behind the repository and gives
reviewers a short, reproducible path through its evidence. It is intentionally
specific about what the project proves, what it does not prove, and which next
steps would create the strongest additional career signal.

## Executive summary

The project is a local-first document intelligence service: users ingest a
small corpus, retrieve evidence with lexical, dense, or fused search, and ask
questions whose answers are tied to the exact chunks supplied to the model.
It remains useful with no API key—lexical retrieval and evidence excerpts work
offline—while optional providers add semantic retrieval and generation.

The central engineering problem is not simply calling an LLM. It is preserving
trust across mutable documents and partially available dependencies. An answer
must never cite a stale document version, a failed ingestion must not become
searchable, an empty scope must not broaden into the entire corpus, and a
provider failure must not be presented as low confidence or no evidence.

The implementation addresses that problem with an authoritative SQLite
manifest, staged lifecycle operations, independently scoped retrieval
branches, hydration against current manifest state, explicit outcome statuses,
and tests for failure paths. `docs/ARCHITECTURE.md` is the normative technical
description; this document focuses on the product and career narrative.

## The problem and constraints

### User need

A user reviewing policies or operational documents needs to:

1. know which files are actually indexed;
2. limit a question to selected documents;
3. inspect the passages behind a result;
4. distinguish “not found” from a provider outage;
5. replace or delete content without old versions leaking into results.

### Deliberate constraints

- **Useful without secrets.** CI and the default developer path cannot depend
  on paid APIs or model downloads.
- **Evidence before claims.** Feature claims map to tests or executable
  evaluation; the sample corpus is not represented as a production benchmark.
- **One process and one corpus.** The in-memory lexical index makes this an
  explicit deployment boundary rather than a hidden scaling claim.
- **Bounded work.** Uploads, extracted text, chunks, query length, candidate
  counts, context, and cache size have configured bounds.
- **No silent degradation.** Effective retrieval mode, unavailable reranking,
  generation errors, truncated context, and invalid citations are surfaced.

## System walkthrough

### Write path

```text
upload
  -> bounded read and file validation
  -> extraction with source locations
  -> offset-preserving chunks
  -> manifest status = indexing
  -> optional embeddings and vector writes
  -> manifest status = ready
  -> lexical-index rebuild and cache invalidation
```

If a required stage fails, the service rolls back the chunks, vectors, and
stored file. Replacement builds the next version while the current version
stays available, then switches the manifest only after the new version is
ready. Deletion excludes the record first and reports incomplete cleanup
honestly if a backing store cannot be updated.

### Read path

```text
question and document scope
  -> scope validation
  -> scoped BM25 and/or scoped vector candidates
  -> reciprocal-rank fusion by chunk identity
  -> hydration from ready, current manifest versions
  -> optional reranking
  -> bounded evidence context [S1..Sn]
  -> optional generation
  -> citation validation and explicit answer status
```

Hydrating candidates from the manifest is an important second line of defense:
even if an index contains stale data, it cannot be returned for a non-current
or non-ready document version.

## Key decisions and trade-offs

| Decision | Benefit | Cost / boundary |
|---|---|---|
| SQLite manifest is authoritative | Durable lifecycle state and simple local operation | Not a multi-writer, horizontally scaled design |
| In-memory BM25 is rebuilt after mutations | Straightforward consistency with the manifest | Rebuild cost and single-process deployment |
| Chroma collection declares cosine space and embedding identity | Score interpretation is explicit; incompatible vectors fail closed | Changing embedding configuration requires re-indexing |
| RRF combines ranks, not unlike raw scores | Avoids pretending BM25 and vector scores share a scale | Rank fusion discards magnitude information |
| Every retrieval branch applies document scope | Prevents out-of-scope evidence entering fusion | Filtering can reduce recall for very narrow scopes |
| Context assembly has a character budget | Predictable request size and explicit truncation | Character counts approximate, rather than exactly measure, tokens |
| Citation checking validates source labels | Detects invented or missing evidence references | Structural validity does not prove claim entailment |
| Offline mode returns excerpts | The core product and CI work without secrets | It does not demonstrate live answer quality |
| Provider imports and model loading are lazy | Startup is deterministic and offline-safe | Optional paths need separate environment validation |

## Competency-to-evidence map

Use this table as a reviewer index, not as a substitute for reading the code.

| Competency | Concrete evidence | What to discuss |
|---|---|---|
| API design | `src/api/endpoints.py`, `src/api/schemas.py`, `tests/test_api.py` | Strict requests, outcome statuses, upload bounds, NDJSON contract |
| Data modeling and consistency | `src/core/manifest.py`, `src/rag/service.py`, `tests/test_lifecycle.py` | Source of truth, staged commits, replacement, retryable deletion |
| Information retrieval | `src/core/lexical.py`, `src/rag/hybrid_search.py`, `src/rag/retriever.py` | BM25 semantics, cosine distance, RRF, filtering and hydration |
| LLM reliability | `src/rag/generator.py`, `tests/test_retrieval_generation.py` | Context budgeting, abstention, citations, streaming cleanup |
| Evaluation | `eval/retrieval_metrics.py`, `eval/run_eval.py`, `tests/test_eval_metrics.py` | Metric conventions, judgments, provenance, scenario checks |
| Security and privacy | `src/api/deps.py`, `src/utils/document_loader.py`, `.github/workflows/ci.yml` | Auth boundary, file validation, secret/dependency scanning |
| Operability | `src/api/health.py`, `src/monitoring/metrics.py`, `docker/` | Readiness, route-template metrics, persistent container smoke test |
| Engineering communication | `README.md`, `docs/ARCHITECTURE.md`, this case study | Claims backed by evidence; limitations and trade-offs are explicit |

## Five-minute reviewer demo

This path requires Python 3.11 but no credentials or model downloads.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
APP_ENV_FILE=/nonexistent/.env uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

In a second shell:

```bash
# Confirm startup and effective provider modes.
curl -s http://127.0.0.1:8000/health | python -m json.tool

# Ingest a known document.
curl -s -F file=@eval/sample_corpus/docs/refund-policy.md \
  http://127.0.0.1:8000/api/v1/documents/upload | python -m json.tool

# Show transparent lexical fallback and inspect ranked evidence.
curl -s -H 'Content-Type: application/json' \
  -d '{"text":"How long do refunds take?","mode":"hybrid"}' \
  http://127.0.0.1:8000/api/v1/search | python -m json.tool

# Run the reproducible retrieval evaluation.
python -m eval.run_eval --embedding none --out /tmp/doc-intel-eval.json
python -m json.tool /tmp/doc-intel-eval.json | head -80
```

Then show one lifecycle test and one generation-contract test rather than
scrolling through the entire suite:

```bash
pytest tests/test_lifecycle.py -q
pytest tests/test_retrieval_generation.py -q
```

## Interview discussion guide

### A concise project narrative

> I built a local-first RAG service around a trust problem: retrieval and
> generation must stay consistent while documents change and providers fail.
> I made SQLite the lifecycle authority, staged index mutations, scoped both
> retrieval branches, revalidated candidates against current state, and made
> degradation explicit in the API. I also created an offline evaluation path
> so the important behavior is reproducible without credentials.

### Questions this project can answer well

**Why not use vector search alone?** Lexical search is deterministic, cheap,
and strong for exact identifiers and policy terms. Dense retrieval is useful
for paraphrases. RRF combines rankings without treating their raw scores as
commensurate, and the response retains each score for inspection.

**How do you prevent stale answers after replacement?** The old version stays
current during indexing. The manifest switches only after required writes
succeed; old artifacts are then removed. Retrieval also hydrates candidates
against ready/current manifest state, and the cache key includes the corpus
generation.

**What does citation validation guarantee?** It guarantees that every cited
label maps to evidence actually placed in model context. It does not establish
that a claim is entailed by that evidence; entailment verification is a
documented follow-up opportunity.

**What would break first at scale?** The process-local BM25 index and rebuilds
make horizontal scaling inappropriate. The next design would use a shared
sparse index plus transactional/outbox-driven index updates, with corpus and
tenant isolation designed into storage and authorization.

**How do you know retrieval is good?** The checked-in judgments and metric
implementation make a small, reproducible regression suite. They validate
metric and pipeline behavior, not general quality. A real deployment needs a
larger representative query set, slice analysis, latency/cost tracking, and
human review of answer groundedness.

## Defensible resume language

Tailor these bullets to the role and only add measured numbers from a real,
reproducible run. Do not invent scale, latency, accuracy, or users.

- Built a FastAPI document-intelligence service with BM25/vector retrieval,
  reciprocal-rank fusion, optional reranking, and citation-checked generation.
- Designed staged ingestion, versioned replacement, and retryable deletion
  around an authoritative SQLite manifest to prevent stale or partial index
  state from becoming searchable.
- Created credential-free retrieval evaluations with explicit metric
  conventions, provenance-stamped artifacts, and regression tests for scope,
  replacement, and deletion behavior.
- Implemented bounded context assembly and structured NDJSON streaming with
  explicit abstention, degradation, citation-validation, and cancellation
  semantics.
- Added typed API contracts, health/readiness checks, Prometheus metrics,
  container smoke testing, static analysis, and security scanning in CI.

### Role-specific emphasis

- **Applied AI / ML engineer:** lead with retrieval evaluation, hybrid search,
  context construction, provider abstraction, and groundedness limitations.
- **Backend engineer:** lead with lifecycle invariants, failure recovery,
  streaming contracts, persistent state, input bounds, and API tests.
- **Platform / MLOps engineer:** lead with offline determinism, configuration
  identity, readiness behavior, metrics, Docker validation, and CI gates.

## Prioritized roadmap for stronger career signal

The ordering favors demonstrable engineering depth over adding more framework
names.

### 1. Evaluation depth (highest leverage)

- Expand judgments with realistic, adversarial, and unanswerable queries.
- Report retrieval slices by document type, query type, and scope size.
- Add answer-level groundedness review with a human-labeled calibration set.
- Record latency, token use, and provider cost separately from quality.

**Why it matters:** this turns a correct pipeline demonstration into credible
evidence of iterative ML-system improvement.

### 2. Multi-process indexing architecture

- Move sparse retrieval to shared durable infrastructure.
- Introduce an outbox/job model for idempotent index mutations.
- Add concurrency tests for upload, replacement, query, and deletion races.
- Define recovery and reconciliation procedures before claiming scale.

**Why it matters:** this demonstrates distributed-systems reasoning without
pretending the current local design is already distributed.

### 3. Stronger groundedness and security

- Add claim-to-source entailment checks evaluated against labeled examples.
- Test prompt-injection corpora and document-level trust policies.
- Add tenant-aware authorization only together with storage/index isolation.

**Why it matters:** reliability and security are more differentiating than
another retrieval provider adapter.

### 4. Broader ingestion with observable quality

- Add OCR or DOCX behind explicit capability and quality statuses.
- Preserve page/layout provenance and test difficult fixtures.
- Measure extraction failures rather than silently accepting empty content.

**Why it matters:** ingestion quality often bounds downstream RAG quality and
creates a concrete end-to-end applied AI story.

## Claims to avoid

The repository does **not** currently establish production scale,
multi-tenancy, OCR support, semantic quality from hash embeddings, live model
quality, or claim-level factual correctness. Avoid “enterprise-ready,” “high
accuracy,” and performance claims unless a future reproducible artifact
defines the workload, environment, baseline, and measurement method.

That restraint is part of the portfolio signal: the project distinguishes
implemented behavior, tested behavior, optional capability, and future work.
