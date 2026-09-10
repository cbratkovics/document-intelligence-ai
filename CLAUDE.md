# Document Intelligence RAG System

Document search and evidence-grounded question answering over a local corpus.
Application code lives in `src/`; `app/` is experimental and not wired in
(except the optional cross-encoder). Positioning: implementation quality and
defensible evidence, not infrastructure lists.

## Commands

- `pip install -r requirements-dev.txt` (core + tooling; no provider keys needed)
- `make test` / `pytest tests -q`
- `make lint` (black, isort, flake8, mypy on `src`, bandit)
- `make eval` / `python -m eval.run_eval --embedding none|hash`
- `uvicorn src.api.main:app --host 127.0.0.1 --port 8000` then `/ui`, `/docs`
- `make docker-smoke`

## Architecture

`docs/ARCHITECTURE.md` is the single maintained architecture/evidence document.
Pipeline: upload -> extract (page spans) -> chunk (offsets) -> SQLite manifest ->
optional embeddings -> Chroma (cosine) -> commit -> BM25 rebuilt from manifest.
Query: scope validation -> BM25 + vector candidates (both scoped) -> RRF by chunk
id -> hydrate (ready docs, current version) -> optional rerank -> top-k ->
budgeted context -> generation -> citation validation.

## Invariants to preserve

- Manifest is authoritative; only `ready` documents at their current version are searchable.
- Ingestion is staged with rollback; no "processed" response before every index write succeeds.
- Empty document scope means nothing, never the whole corpus; unknown documents are rejected.
- Score fields stay separate (distance, similarity, lexical, fusion, rerank); no `confidence`.
- Failed reranking or generation is reported as a status, never faked with default scores.
- Nothing imports provider SDKs, opens Redis, or downloads models at import or startup.
- Single process, single corpus; do not claim multi-worker or multi-tenant support.

## Evidence rules

- Tests must fail under the old behavior they guard; provider calls use doubles.
- `hash` embeddings prove plumbing only; do not present them as retrieval quality.
- Evaluation artifacts carry provenance; do not commit a "latest" report or quote
  numbers from the tiny sample corpus as general performance.
- README claims must map to tests, evaluation runs, or be labeled optional/unverified.

## Boundaries

- Do not push, deploy, or change remote settings from here.
- Do not make paid provider calls without explicit authorization.
- Never store credentials in this file or in the repository.
