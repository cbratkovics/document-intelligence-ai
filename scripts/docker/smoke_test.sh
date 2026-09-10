#!/usr/bin/env bash
# Start the image, ingest a sample document, run a search, and stop.
set -euo pipefail
IMAGE="${1:-doc-intel:ci}"
NAME="doc-intel-smoke-$$"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" -p 18000:8000 -e STORAGE_MODE=ephemeral "$IMAGE" >/dev/null
for _ in $(seq 1 30); do
  if curl -fsS http://localhost:18000/ready >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://localhost:18000/ready >/dev/null

UPLOAD=$(curl -fsS -F "file=@eval/sample_corpus/docs/refund-policy.md" http://localhost:18000/api/v1/documents/upload)
echo "$UPLOAD" | grep -q '"status":"ready"' || { echo "upload did not report ready: $UPLOAD"; exit 1; }

SEARCH=$(curl -fsS -H 'Content-Type: application/json' \
  -d '{"text":"refund within 30 days","mode":"lexical"}' http://localhost:18000/api/v1/search)
echo "$SEARCH" | grep -q '"mode_effective":"lexical"' || { echo "unexpected search response: $SEARCH"; exit 1; }
echo "$SEARCH" | grep -q 'refund-policy.md' || { echo "search did not return the document: $SEARCH"; exit 1; }
echo "container smoke test passed"
