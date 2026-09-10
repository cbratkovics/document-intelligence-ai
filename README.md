# Document Intelligence RAG System

Document search and evidence-grounded question answering over a local corpus.

[![CI](https://github.com/cbratkovics/document-intelligence-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/cbratkovics/document-intelligence-ai/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Upload text, Markdown, reStructuredText, or PDF files; inspect how they were
chunked; search them with BM25, dense vectors, or a fusion of both; ask a
question scoped to selected documents; see exactly which passages supported
the answer; and delete documents with every index kept consistent. The
offline path (no API keys, no model downloads) is fully functional and is what
the test suite and CI exercise.

## Quick start (no keys required)

```bash
git clone https://github.com/cbratkovics/document-intelligence-ai.git
cd document-intelligence-ai
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ui for the review page or
http://127.0.0.1:8000/docs for the OpenAPI console. Data is stored under
`./data` (a SQLite manifest, uploaded files, and the vector index) and
survives restarts.

### Guided walkthrough

The commands below use the labeled sample corpus in `eval/sample_corpus`
(six short original documents about a fictional retailer).

```bash
# 1. Ingest two documents. The response is returned only after all index writes succeed.
curl -s -F file=@eval/sample_corpus/docs/refund-policy.md  localhost:8000/api/v1/documents/upload | python -m json.tool
curl -s -F file=@eval/sample_corpus/docs/shipping-policy.md localhost:8000/api/v1/documents/upload | python -m json.tool

# 2. Inspect status and chunks (offsets, headings, and page numbers for PDFs).
curl -s localhost:8000/api/v1/documents | python -m json.tool
curl -s "localhost:8000/api/v1/documents/<doc_id>/chunks?limit=3" | python -m json.tool

# 3. Search. Without an embedding provider, "hybrid" runs lexical-only and says so
#    ("mode_effective": "lexical").
curl -s -H 'Content-Type: application/json' -d '{"text":"how long do refunds take","mode":"hybrid"}' \
  localhost:8000/api/v1/search | python -m json.tool

# 4. Ask a scoped question. Without a generation provider the status is
#    "excerpts_only" and the supporting passages are returned verbatim.
curl -s -H 'Content-Type: application/json' \
  -d '{"text":"How long do refunds take?","doc_ids":["<doc_id>"]}' localhost:8000/api/v1/query | python -m json.tool

# 5. Ask something the corpus cannot answer: status "insufficient_evidence" when nothing is retrieved,
#    or the model abstains when a provider is configured.
curl -s -H 'Content-Type: application/json' -d '{"text":"What is the parental leave allowance?","doc_ids":[]}' \
  localhost:8000/api/v1/query | python -m json.tool

# 6. Delete a document; chunks, vectors, the stored file, and cached answers go with it.
curl -s -X DELETE localhost:8000/api/v1/documents/<doc_id> | python -m json.tool
```

### Enabling generation and dense retrieval

Set `OPENAI_API_KEY` (this makes paid API calls) and install the provider
client:

```bash
pip install -r requirements-ml.txt
export OPENAI_API_KEY=sk-...
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

With a key, `auto` provider resolution enables OpenAI embeddings for
`vector`/`hybrid` retrieval and OpenAI chat completions for answers. Answers
are checked so that every `[S1]`-style citation resolves to a passage that was
actually in the model's context; anything else is reported as
`unverified_citations`, never silently accepted.

For a local embedding model or the transformer cross-encoder reranker,
prepare the model files first (network required once), then select the mode:

```bash
python scripts/setup/init_models.py --embedding --reranker
export EMBEDDING_PROVIDER=local RERANKER_MODE=cross_encoder
```

The application never downloads models at import, startup, or request time.

## What is in the box

| Capability | Status | Evidence |
|---|---|---|
| Ingestion of `.txt`, `.md`, `.rst`, `.pdf` with validation (size while reading, encoding, PDF magic bytes, encrypted and text-less PDFs rejected) | Tested | `tests/test_extraction.py`, `tests/test_api.py` |
| Offset-preserving chunking with page ranges (PDF) and Markdown section headings | Tested | `tests/test_chunking.py` |
| Authoritative SQLite manifest; staged ingestion with rollback; idempotent re-upload; versioned replacement | Tested | `tests/test_lifecycle.py` |
| BM25 lexical retrieval (in-repo scorer, Lucene IDF) | Tested and evaluated | `tests/test_indexes.py`, `eval/run_eval.py --embedding none` |
| Dense retrieval in an explicitly cosine Chroma collection with embedding-identity checks | Tested (deterministic test embeddings); optional with OpenAI or local models | `tests/test_indexes.py`, `tests/test_lifecycle.py` |
| Hybrid retrieval by reciprocal rank fusion with explicit weights and chunk identity | Tested | `tests/test_indexes.py`, `tests/test_retrieval_generation.py` |
| Per-request document scope enforced in both branches; empty scope returns nothing | Tested | `tests/test_retrieval_generation.py` |
| Reranking modes: heuristic, LLM scoring (strict parsing), cross-encoder adapter | heuristic and LLM tested with doubles; cross-encoder optional, not exercised in CI | `src/rag/reranker.py` |
| Grounded answers with citation validation, abstention, provider-error and excerpt-only statuses | Tested with provider doubles; live generation requires a key | `tests/test_retrieval_generation.py` |
| Structured NDJSON streaming with one terminal event and cancellation cleanup | Tested with doubles | `tests/test_retrieval_generation.py`, `tests/test_api.py` |
| Deletion of all versions, vectors, files, and cached answers; honest failure when a store is unavailable | Tested (including >100 chunks and restart) | `tests/test_lifecycle.py` |
| Optional API key on all `/api/v1` routes; bulk delete requires a configured key | Tested | `tests/test_api.py` |
| Prometheus metrics with route-template labels | Tested | `tests/test_api.py` |
| Retrieval evaluation with hand-checked metric conventions and a provenance-stamped artifact | Tested and run in CI | `tests/test_eval_metrics.py`, `eval/` |
| Experimental components under `app/` (semantic cache, chunking strategies, embedding factory, Celery tasks) | Not wired into the API | `app/README.md` |

## Architecture

```
upload -> validate + extract (pypdf / UTF-8) -> chunk (offsets, pages, sections)
       -> manifest (SQLite, status=indexing) -> embeddings (optional) -> Chroma (cosine)
       -> commit (status=ready) -> BM25 rebuilt from manifest -> answer cache cleared

query  -> scope check (unknown/non-ready docs rejected) -> BM25 + vector candidates (scoped)
       -> RRF fusion by chunk id -> hydrate from manifest (ready docs, current version only)
       -> optional rerank of the full pool -> top-k -> context budget with labels [S1..Sn]
       -> generation (optional) -> citation validation -> status + sources
```

One process serves one corpus. The manifest is the source of truth; the BM25
index is rebuilt from it after every committed change, and vectors carry the
document id and version so stale entries are never served. Multi-process
deployment is not supported: sparse state is process-local by design. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the data lifecycle
invariants, score semantics, and the evidence behind each claim.

`src/` is the application. `app/` holds earlier experimental components that
are kept for reference and are not imported by the API, except for the
transformer cross-encoder, which `RERANKER_MODE=cross_encoder` loads lazily.

## Configuration

Copy `.env.example` to `.env`. Key settings:

| Variable | Default | Effect |
|---|---|---|
| `STORAGE_MODE` | `persistent` | `ephemeral` keeps everything in memory and resets on restart |
| `DATA_DIR` | `./data` | Manifest, uploads, and vector index location |
| `API_KEY` | unset | When set, every `/api/v1` route requires `X-API-Key`; bulk delete always requires it |
| `EMBEDDING_PROVIDER` | `auto` | `none`, `openai`, `local`, or `hash` (test-only, non-semantic) |
| `GENERATION_PROVIDER` | `auto` | `none` or `openai` |
| `RERANKER_MODE` | `none` | `heuristic`, `llm`, or `cross_encoder` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 1000 / 200 | Characters; changing them changes the recorded chunking configuration |
| `MAX_UPLOAD_SIZE` | 10 MiB | Enforced while the upload is read |

Without `API_KEY` the server runs in local mode with no authentication.
Bind it to localhost, or set a key before exposing it.

## Evaluation

```bash
python -m eval.run_eval --embedding none    # lexical only; runs in CI
python -m eval.run_eval --embedding hash    # dense/hybrid plumbing with non-semantic embeddings
python -m eval.run_eval --embedding openai  # paid; real dense retrieval
```

Each run ingests the sample corpus into a disposable index, runs every
requested mode with identical queries, evaluates against hand-written
document-level judgments, runs scope, replacement, and deletion scenario
checks, and writes a JSON artifact to `eval/results/` containing the commit,
source and corpus hashes, configuration, per-query ranks, and metric
denominators. The corpus is tiny and illustrative; it proves the pipeline and
the metric code, not general retrieval quality. Metric conventions are stated
in `eval/retrieval_metrics.py`.

## Development

```bash
pip install -r requirements-dev.txt
make lint      # black, isort, flake8, mypy, bandit
make test      # pytest
make eval      # offline evaluation run
make docker-smoke   # build the image and ingest/search inside a container
```

CI runs lint, type checks, the test suite, both offline evaluation runs, and
the container smoke test without any provider secrets.

## Limitations

- Single process, single corpus. No multi-tenant isolation; the API key is
  one shared credential.
- PDF support is text-layer only. Scanned PDFs are rejected rather than OCR'd.
  DOCX and HTML are not supported.
- Citation validation is structural: it proves a cited passage was in
  context, not that the passage entails the claim.
- The evidence delimiting in prompts reduces prompt-injection risk but does
  not eliminate it.
- Deletion removes application-controlled data only. Provider-side logs or
  external backups are outside its control.
- Prometheus metrics are exposed at `/metrics`; no dashboards are included.

## License

MIT. See [LICENSE](LICENSE).
