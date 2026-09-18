# API reference

Base URL: `http://127.0.0.1:8000`. Interactive documentation is served at
`/docs` (Swagger UI) and `/redoc`; the schema is at `/openapi.json`. A small
review page is at `/ui`.

## Authentication

When the server is started with `API_KEY` set, every route under `/api/v1`
requires the header `X-API-Key: <key>`. Without `API_KEY` the server is in
local mode: no authentication, and `DELETE /api/v1/documents` (bulk delete)
returns 403. Health endpoints never require a key.

## Errors

Errors are JSON objects `{"error": "...", "code": "...", "request_id": "..."}`.
Status codes are preserved: 400 invalid input, 401 missing/invalid key, 403
operation unavailable, 404 unknown document, 409 mode or document not
available (or `corpus_full` when the document cap is reached and nothing can
be evicted), 413 upload too large, 422 schema validation (unknown fields are
rejected), 429 rate limited (with `Retry-After`), 500 internal or incomplete
operation, 502 generation provider failure, 503 service not started.

## Documents

### `POST /api/v1/documents/upload`

Multipart form: `file` (required; `.txt`, `.md`, `.rst`, `.pdf`), `metadata`
(optional flat JSON object of strings, numbers, booleans; reserved keys such
as `doc_id` are rejected). Returns after every index write has succeeded.

```json
{
  "document": {"doc_id": "…", "version": 1, "filename": "refund-policy.md", "status": "ready",
               "chunk_count": 4, "page_count": null, "content_hash": "…", "chunking_config": "chars:v2:size=1000:overlap=200",
               "embedding_identity": null, "metadata": {}, "error": null, "...": "..."},
  "created": true, "duplicate_of": null, "warnings": [], "timings_ms": {"extract": 1.2, "chunk": 0.4, "index_lexical": 2.1}
}
```

Uploading identical bytes again returns the existing document with
`created=false` and `duplicate_of` set. When `MAX_DOCUMENTS` is configured,
`evicted` lists the ids removed (oldest first) to make room.

### `POST /api/v1/documents/{doc_id}/replace`

Same form as upload. Indexes a new version; the previous version stays
searchable until the new one is committed.

### `GET /api/v1/documents`, `GET /api/v1/documents/{doc_id}`

List or fetch document records including `status`
(`indexing`, `ready`, `failed`), `version`, `chunk_count`, `error`.

### `GET /api/v1/documents/{doc_id}/chunks?offset=0&limit=50`

Ordered chunks with `location` (`char_start`, `char_end` into the normalized
extracted text; `page`/`page_end` for PDFs; `section` for Markdown headings).

### `DELETE /api/v1/documents/{doc_id}`

Removes chunks, vectors, the stored file, the manifest row, and cached
answers. Returns counts. A second call returns 404. If a required index
removal fails the response is 500 with code `deletion_incomplete` and the
document remains excluded from retrieval until a retry succeeds.

### `DELETE /api/v1/documents`

Removes everything. Requires a configured and matching API key.

### `POST /api/v1/documents/{doc_id}/summary?max_chars=500`

Summarizes from the document's own ordered chunks. `status` is `ok`,
`excerpts_only` (no generation provider), or `provider_error`; `coverage`
reports how much of the document fit the context budget.

## Retrieval

### `POST /api/v1/search`

```json
{"text": "refund window", "mode": "hybrid", "top_k": 5, "doc_ids": null, "alpha": 0.5, "use_reranker": false}
```

- `mode`: `lexical`, `vector`, `hybrid`. `hybrid` without an embedding
  provider runs lexical-only and reports `mode_effective: "lexical"` with a
  note; `vector` without a provider returns 409.
- `doc_ids`: restrict to these documents. `[]` matches nothing. Unknown ids
  return 404.
- `alpha`: dense weight in fusion (lexical weight is `1 - alpha`).
- `use_reranker`: apply the configured reranker to the full candidate pool.

Response: `results` (each with `chunk_id`, `doc_id`, `version`, `ordinal`,
`filename`, `text`, `location`, `metadata`, `scores` with separate
`vector_distance`, `vector_similarity`, `vector_rank`, `lexical_score`,
`lexical_rank`, `fusion_score`, `fusion_rank` (hybrid only, before
reranking), `rerank_score`, and `rank`), plus `mode_requested`,
`mode_effective`, `rerank_status` (`applied`/`disabled`/`unavailable`/`failed`),
`reranker`, `scope`, `corpus_generation`, `candidate_k` (candidates requested
per branch; a null branch rank means outside that top list), `timings_ms`,
`notes`.

## Question answering

### `POST /api/v1/query`

Same fields as search plus `generate` (default `true`). Response:

| Field | Meaning |
|---|---|
| `status` | `answered`, `unverified_citations`, `insufficient_evidence`, `excerpts_only`, `provider_error` |
| `answer` | Generated text with `[S1]`-style markers, or `null` |
| `citations` | Markers that resolve to context blocks: label, chunk id, document, filename, location, text |
| `unknown_citations` | Markers the model emitted that were not in context |
| `excerpts` | Supporting passages when no answer was generated |
| `sources` | All retrieved hits with scores |
| `context` | Budget, chars used, which chunk ids entered the prompt, `truncated` |
| `retrieval_diagnostics` | Descriptive statistics of the retrieved set (not confidence) |
| `generation` | `model`, `prompt_version`, `cached`, `error` |

### `POST /api/v1/query/stream`

`application/x-ndjson`, one JSON object per line, protocol version 1:

```
{"event":"meta","v":1,"request_id":"…","retrieval":{…},"context":{…},"model":"openai:gpt-4o-mini"}
{"event":"sources","sources":[…]}
{"event":"delta","text":"Refunds are issued ","provisional":true}
{"event":"done","status":"answered","answer":"…","citations":[…],"unknown_citations":[]}
```

Exactly one terminal event (`done` or `error`) is sent. `delta` text is
provisional; only `done` carries the citation-validated answer. Scope and
validation errors happen before the response starts and use normal HTTP
status codes.

### `POST /api/v1/evaluate/judge`

`{"question", "answer", "context"}` -> an LLM rating with disclosed model and
prompt version. `status` is `ok`, `parse_failed`, `provider_error`, or
`unavailable`. It is not independent ground truth.

## Health

- `GET /health`: liveness plus the effective `retrieval_mode`,
  `embedding_provider`, `embedding_model`, `reranker_mode`,
  `generation_provider`, `document_count` (ready documents),
  `seeded_doc_ids`, `seed_errors`, capabilities (storage mode, embedding
  identity, supported extensions, upload and document limits) and any
  startup error. Never requires a key and is never rate limited.
- `GET /ready`: 200 when storage is reachable and the indexes agree with the
  manifest; 503 otherwise.
- `GET /api/v1/system/stats`: counts and a consistency report.
- `GET /metrics`: Prometheus text format (route-template labels).
