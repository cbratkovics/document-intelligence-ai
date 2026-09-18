# Changelog

## Unreleased (0.3.0): public retrieval demo

- `fastembed` embedding provider (ONNX MiniLM, no torch); `init_models.py
  --fastembed`; `requirements-demo.txt`; `huggingface_hub<0.26` pinned for
  the sentence-transformers path.
- Hits carry `fusion_rank`; retrieval reports `candidate_k`; `/health`
  reports effective modes, document count and seeded ids.
- Public-demo controls: startup seeding, document cap with oldest-first
  eviction, per-client and global rate limits with forwarded-IP trust only
  behind a valid key.
- BM25 removes English stopwords from documents and queries.
- Ephemeral services drop their Chroma collection on close; manifest
  timestamps use microsecond precision.
- `deploy/space/` (Hugging Face Space image and configuration), the deploy
  workflow, and `frontend/` (Next.js evidence view on Vercel).
- README rewritten around the deployed demo; repository description and
  topics corrected.

## Unreleased (0.2.0)

Repair-and-polish pass focused on correctness, honesty, and reproducible
evidence. Breaking API changes are marked.

### Runtime and data lifecycle
- Services are created in the application lifespan and shared through
  `app.state`; importing the app performs no I/O.
- New SQLite manifest as the authoritative record of documents, versions,
  chunks, source locations, lifecycle status, and configuration identity.
- Staged ingestion with rollback; failed documents are visible as `failed`
  and never searchable; identical bytes are deduplicated; explicit
  replacement endpoint with version handling.
- Deletion enumerates from the manifest (no 100-chunk assumption), removes
  vectors, chunks, files, and cached answers, and reports incomplete
  deletions instead of claiming success.
- Chroma collection created with cosine space and embedding identity
  metadata; incompatible indexes are refused at startup.
- BM25 implemented in-repo with a Lucene-style IDF (the previous library
  produced non-positive scores on tiny corpora) and rebuilt from the manifest.
- LangChain removed from the runtime path; providers are called through the
  OpenAI SDK lazily and only when configured.

### Retrieval and generation
- Document scope enforced in both retrieval branches; empty scope returns
  nothing; unknown or non-ready documents are rejected.
- Reciprocal rank fusion keyed by chunk id with explicit weights; zero-weight
  branches contribute nothing.
- Reranking reports `applied`/`disabled`/`unavailable`/`failed`; LLM scores
  are parsed strictly with no default values.
- Grounded prompting with delimited evidence, citation validation, and
  distinct statuses for abstention, unverified citations, provider errors,
  and excerpt-only mode. `confidence` replaced by `retrieval_diagnostics`.
- Structured NDJSON streaming with exactly one terminal event.
- Summaries read ordered chunks from the manifest and report coverage.

### API (breaking)
- `/query` and `/search` request models reject unknown fields; `filters` and
  `stream` are gone, replaced by `doc_ids`, `mode`, `alpha`, `use_reranker`,
  `generate`.
- `/query/stream` returns `application/x-ndjson` events instead of raw text.
- `/evaluate` moved to `/evaluate/judge` with strict parsing.
- Optional `API_KEY` enforcement; `DELETE /documents` requires a configured key.
- New: `/documents/{id}/chunks`, `/documents/{id}/replace`, `/system/stats`, `/ui`.

### Evaluation
- Metrics rewritten with stated conventions; nDCG uses judgments and the
  full ideal set; duplicates cannot inflate recall; comparisons align by
  query id; zero-baseline relative change is undefined.
- Labeled sample corpus and a runner that writes a provenance-stamped artifact.

### Documentation and CI
- README, architecture document, API reference, and security policy
  rewritten around verified behavior; fabricated metrics, badges, and
  enterprise-feature documents removed.
- CI enforces lint, type checks, tests, offline evaluation runs, and a
  container smoke test without provider secrets.

## Earlier history

Entries before 0.2.0 (including a "1.0.0" release with coverage, latency, and
image-size figures) are preserved in Git history only. Those figures were not
reproducible from the repository and are not carried forward.
