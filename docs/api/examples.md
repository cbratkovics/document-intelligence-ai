# Examples

## Python (requests)

```python
import json
import requests

BASE = "http://127.0.0.1:8000/api/v1"
HEADERS = {}  # {"X-API-Key": "..."} when API_KEY is configured

with open("eval/sample_corpus/docs/refund-policy.md", "rb") as handle:
    uploaded = requests.post(f"{BASE}/documents/upload", files={"file": handle}, headers=HEADERS).json()
doc_id = uploaded["document"]["doc_id"]

hits = requests.post(f"{BASE}/search", json={"text": "refund window", "mode": "lexical"}, headers=HEADERS).json()
for hit in hits["results"]:
    print(hit["rank"], hit["filename"], hit["scores"]["lexical_score"], hit["text"][:60])

answer = requests.post(f"{BASE}/query", json={"text": "How long do refunds take?", "doc_ids": [doc_id]}, headers=HEADERS).json()
print(answer["status"], answer["answer"] or [e["text"][:80] for e in answer["excerpts"]])

with requests.post(f"{BASE}/query/stream", json={"text": "How long do refunds take?"}, headers=HEADERS, stream=True) as response:
    for line in response.iter_lines():
        event = json.loads(line)
        if event["event"] == "delta":
            print(event["text"], end="", flush=True)
        elif event["event"] in ("done", "error"):
            print("\n", event["status"])

requests.delete(f"{BASE}/documents/{doc_id}", headers=HEADERS)
```

## curl

```bash
curl -s -F file=@eval/sample_corpus/docs/shipping-policy.md localhost:8000/api/v1/documents/upload
curl -s -H 'Content-Type: application/json' -d '{"text":"expedited delivery cost","mode":"hybrid","top_k":3}' localhost:8000/api/v1/search
curl -s -H 'Content-Type: application/json' -d '{"text":"What does expedited delivery cost?","generate":false}' localhost:8000/api/v1/query
curl -s -N -H 'Content-Type: application/json' -d '{"text":"What does expedited delivery cost?"}' localhost:8000/api/v1/query/stream
```

## Reading the response

- Trust `status` before `answer`: `unverified_citations` means the model
  answered but at least one citation did not resolve.
- `retrieval.mode_effective` is what ran; `retrieval.rerank_status` says
  whether reranking happened.
- `context.blocks` lists the chunk ids that were in the prompt; `sources`
  lists everything retrieved. Only cited blocks support the answer.
