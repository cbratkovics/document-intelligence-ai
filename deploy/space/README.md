---
title: Document Intelligence Demo
emoji: "📄"
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Hybrid BM25 + MiniLM retrieval with cited passages. No LLM.
---

# Document Intelligence demo API

This Space runs the API behind the public demo of
[document-intelligence-ai](https://github.com/cbratkovics/document-intelligence-ai).
It is deployed automatically from that repository's `main` branch; do not
edit files here.

## What it does

- Hybrid retrieval over a small fictional corpus: BM25 fused with
  `sentence-transformers/all-MiniLM-L6-v2` embeddings (ONNX Runtime via
  fastembed) using reciprocal rank fusion. A heuristic term-overlap reranker
  is available on request.
- Every hit reports its BM25 rank, dense rank, fused rank and score
  separately, so a client can show how the two retrievers disagree.
- Retrieval only. `GENERATION_PROVIDER=none`: no language model is called
  and no provider SDK is installed in the image.

## Configuration

Runtime settings come from `demo.env` (committed, no secrets). The only
secret is `API_KEY`, set in the Space settings; every `/api/v1` route
requires it in the `X-API-Key` header. `/health` is open and reports the
effective modes and document count.

Limits: uploads of `.txt`, `.md`, `.rst`, `.pdf` up to 4 MB; at most 24
documents in the corpus with oldest-first eviction of uploads (the four
seeded samples are never evicted); per-client and global rate limits;
storage is ephemeral and resets whenever the Space restarts.

## Endpoints used by the demo frontend

`GET /health`, `POST /api/v1/search`, `POST /api/v1/documents/upload`,
`GET /api/v1/documents`, `GET /api/v1/documents/{id}/chunks`.
Full OpenAPI schema at `/docs`.
