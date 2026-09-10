# Sample evaluation corpus

Sample data. Six short original documents about a fictional retailer,
"Northwind Outfitters", written for this repository so the evaluation is
reproducible without external datasets or licensing questions. The corpus is
deliberately tiny: it exercises the retrieval pipeline and metric code, and it
is *not* a benchmark from which to claim retrieval quality.

Files:

- `docs/` - the documents (`.md` and `.txt`). Stable evaluation IDs are the
  filenames; server-generated document IDs are mapped back to filenames by
  the runner.
- `queries.json` - queries with `id`, `text`, an optional `scope` (list of
  filenames), optional `support` snippets that a supporting passage should
  contain, and a `kind` tag (exact_id, paraphrase, multi_doc, duplicate_text,
  negation_date, unanswerable, scoped).
- `qrels.json` - graded document-level relevance judgments per query
  (2 = directly answers, 1 = partially relevant, absent = not relevant),
  written by hand from the documents and independent of any retriever output.
- `deletion.json` - a deletion/replacement scenario checked by the runner.

Relevance is judged at the document level. Chunk-level retrieval is mapped to
documents by first occurrence, so overlapping chunks of one document count
once. If chunking changes, the judgments remain valid because they are
document-level.

Design notes about specific cases:

- `remote-work-policy.txt` and `expense-policy.txt` contain an identical
  "Equipment" paragraph (duplicate text in two sources).
- `remote-work-policy.txt` states the old 2021 stipend (400 dollars) and the
  current one (250 dollars) so that a date-sensitive question has one right
  answer inside the same document.
- `security-incident-procedure.md` contains an embedded instruction that must
  be treated as evidence, not obeyed.
