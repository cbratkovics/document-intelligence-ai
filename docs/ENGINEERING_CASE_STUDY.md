# Document Intelligence: Retrieval Architecture and Lifecycle Guarantees

This case study describes the system's document lifecycle, retrieval pipeline,
failure semantics, and reproducible verification path. `docs/ARCHITECTURE.md`
is the detailed component reference; this document connects those components to
the product constraints they enforce.

## Product purpose and constraints

The service searches and answers questions over a local document corpus. Users
can upload text, Markdown, reStructuredText, or text-layer PDFs, inspect the
resulting chunks, restrict a query to selected documents, and remove documents
from every application-controlled store.

The default path is deliberately credential-free. BM25 retrieval and evidence
excerpts work without model downloads or provider keys. Dense retrieval,
cross-encoder or LLM reranking, and generated answers are configuration-dependent
capabilities and are not exercised by the default offline evaluation.

The design prioritizes these invariants:

- only a ready document's current version is searchable;
- a failed write does not expose partially indexed content;
- an explicit empty scope returns no evidence rather than widening to the corpus;
- provider unavailability and provider errors remain distinguishable from an
  evidence-free result; and
- bounded inputs, candidate pools, context, and caches limit local resource use.

## Document ingestion, replacement, and deletion lifecycle

SQLite is the lifecycle authority for document identity, version, status,
chunks, and the corpus generation. The process-local BM25 index is derived from
ready manifest records. When configured, Chroma stores vectors with document
and version metadata.

### Ingestion

```text
bounded upload -> validate and extract -> chunk with source locations
  -> manifest status=indexing -> optional vector write and verification
  -> manifest status=ready -> rebuild BM25 -> bump corpus generation
  -> clear answer cache
```

The service stages mutations in that order. If a required stage fails, it
removes staged chunks, vectors, and the stored file. A new failed record remains
visible with `failed` status for diagnosis and retry, but retrieval cannot use
it. Identical bytes are deduplicated by content hash within the shared corpus.

### Replacement

Replacement builds version `n+1` while version `n` remains current. The
manifest switches versions only after required writes succeed, then old chunks,
vectors, and the stored file are removed. An identical replacement is a no-op.
This sequencing avoids a read gap and prevents an incomplete replacement from
becoming current.

### Deletion

Deletion first marks a document deleted, excluding it from retrieval, and then
removes vectors for every version, chunks, the stored file, and the manifest
row. If backing-store cleanup fails, the API reports `deletion_incomplete` and
leaves the document excluded; retrying deletion can finish cleanup. Successful
mutations rebuild BM25 and invalidate cached answers through a corpus-generation
change.

## Retrieval, scope enforcement, hydration, and answer generation

```text
query and optional document scope -> validate scope
  -> scoped BM25 and/or scoped vector candidates
  -> reciprocal-rank fusion by chunk id -> current-version hydration
  -> optional reranking -> top-k -> bounded evidence context
  -> optional generation -> citation-label validation -> explicit status
```

`None` means whole-corpus scope; an explicit empty list means search nothing.
Unknown and non-ready document IDs are rejected. Both lexical and vector
candidate generators apply scope before fusion. The retriever then loads chunks
from the manifest and discards candidates that are missing, out of scope,
non-ready, or not from the document's current version. This hydration step is a
second defense against stale index entries.

BM25 is always available. Requested hybrid retrieval falls back transparently
to lexical retrieval when no embedding provider is configured and reports the
effective mode. Vector-only retrieval instead returns a capability error.
Hybrid mode uses reciprocal-rank fusion because lexical scores and cosine
distance do not share a meaningful numeric scale.

Answer context is assembled in rank order under a character budget and labels
evidence `[S1]` through `[Sn]`. Generation is optional: without a provider the
API returns `excerpts_only`. With a provider, source labels are checked against
the context actually supplied. That check detects missing or invented labels;
it does not prove that every generated claim is entailed by its cited passage.

## Design decisions and trade-offs

| Decision | Benefit | Cost or boundary |
|---|---|---|
| SQLite manifest is authoritative | Durable lifecycle state with simple local operation | Not a horizontally scaled multi-writer design |
| BM25 is rebuilt after committed mutations | Sparse state follows current manifest state | Rebuild cost and process-local visibility |
| Vector metadata records cosine space and embedding identity | Incompatible non-empty indexes fail closed | Configuration changes require deliberate re-indexing |
| RRF combines ranks | Avoids comparing incompatible raw scores | Discards score magnitude |
| Every retrieval branch applies document scope | Prevents out-of-scope evidence from entering fusion | Narrow scopes may reduce recall |
| Manifest hydration follows candidate generation | Filters stale versions even when an index contains them | Adds storage reads to retrieval |
| Context uses a character budget | Predictable and observable truncation | Character counts only approximate tokens |
| Provider imports and model loads are lazy | Offline startup and tests stay deterministic | Optional integrations require separate environments |

## Implementation and verification map

| Concern | Implementation | Verification |
|---|---|---|
| Lifecycle authority and staged mutations | `src/core/manifest.py`, `src/rag/service.py` | `tests/test_lifecycle.py` |
| Scoped lexical retrieval | `src/core/lexical.py`, `src/rag/retriever.py` | `tests/test_indexes.py`, `tests/test_retrieval_generation.py` |
| Dense retrieval and fusion | `src/core/vector_store.py`, `src/rag/hybrid_search.py` | deterministic embedding doubles in `tests/test_indexes.py` |
| Current-version hydration and reranking | `src/rag/retriever.py`, `src/rag/reranker.py` | `tests/test_retrieval_generation.py` |
| Context, statuses, citations, and streaming | `src/rag/generator.py`, `src/api/endpoints.py` | `tests/test_retrieval_generation.py`, `tests/test_api.py` |
| Request and response contracts | `src/api/schemas.py`, `src/api/endpoints.py` | `tests/test_api.py` |
| Offline retrieval metrics and scenarios | `eval/retrieval_metrics.py`, `eval/run_eval.py` | `tests/test_eval_metrics.py`, sample-corpus evaluation |
| Publication content policy | `scripts/check_publication.py` | `tests/test_publication.py`, CI publication check |

Failure-path tests cover staged-ingestion rollback, replacement failures,
retryable deletion, stale candidates, empty and invalid scopes, unavailable or
failed rerankers, generation errors, invalid citations, and stream cleanup.
Provider doubles verify contracts without claiming live-provider validation.

## Reproducible local walkthrough

This path uses Python 3.11 and requires no credentials or model downloads.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
APP_ENV_FILE=/nonexistent/.env uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

In a second shell:

```bash
curl -s http://127.0.0.1:8000/health | python -m json.tool

curl -s -F file=@eval/sample_corpus/docs/refund-policy.md \
  http://127.0.0.1:8000/api/v1/documents/upload | python -m json.tool

curl -s -H 'Content-Type: application/json' \
  -d '{"text":"How long do refunds take?","mode":"hybrid"}' \
  http://127.0.0.1:8000/api/v1/search | python -m json.tool

python -m eval.run_eval --embedding none --out /tmp/doc-intel-eval.json
python -m json.tool /tmp/doc-intel-eval.json | head -80
```

The search response should report `mode_effective=lexical` when embeddings are
not configured. The evaluation output is temporary and records configuration,
source and corpus hashes, query rankings, metrics, and lifecycle scenario
results. Run the lifecycle and generation contracts separately with:

```bash
pytest tests/test_lifecycle.py -q
pytest tests/test_retrieval_generation.py -q
```

## Evaluation procedure and measurement scope

`python -m eval.run_eval --embedding none` ingests the small fictional sample
corpus into disposable storage, evaluates document rankings against checked-in
judgments, and runs scope, replacement, and deletion scenarios. The metric
implementation defines precision, recall, reciprocal rank, and nDCG conventions
explicitly. Hash embeddings can verify dense and hybrid plumbing but are not
semantic quality evidence.

The corpus and judgments are regression fixtures, not a representative quality
benchmark. They do not establish production accuracy, latency, throughput,
cost, live-provider behavior, or answer groundedness. A representative
evaluation would require domain queries, slice analysis, human relevance and
entailment labels, and separately reported operational measurements.

## Operational boundaries and technical roadmap

Current operation is one process serving one corpus. BM25 is in memory, so
multi-worker serving is unsupported; authentication is one optional shared API
key, not tenant isolation. PDF ingestion requires a text layer. Citation checks
validate labels rather than factual entailment. Provider-side retention and
external backups are outside application-controlled deletion.

Technical follow-up work should preserve these boundaries until each change is
implemented and verified:

1. Expand representative retrieval judgments and add human-reviewed
   groundedness and unanswerable-query evaluation.
2. For multi-process operation, move sparse retrieval to shared durable storage
   and use idempotent jobs or an outbox for index mutations and reconciliation.
3. Add concurrency tests for upload, replacement, query, and deletion races
   before asserting distributed lifecycle guarantees.
4. Add claim-to-source entailment evaluation and document trust policies rather
   than treating structural citations as factual verification.
5. Add OCR or new formats only with extraction-quality statuses, provenance,
   difficult fixtures, and observable failure handling.

## Technical FAQ

**Why retain lexical retrieval?** It is deterministic, credential-free, and
effective for exact identifiers and policy terms. Dense retrieval is optional
and useful for semantic similarity; hybrid mode combines their ranks.

**Why can stale vectors not become answers?** Scope is applied during candidate
generation and candidates are hydrated against ready, current manifest state.
Replacement and deletion sequencing provide additional lifecycle protection.

**What fails first beyond the supported deployment boundary?** Process-local
BM25 state is not coordinated between workers. Shared sparse storage and a
reconciled mutation protocol are prerequisites for horizontal serving.
