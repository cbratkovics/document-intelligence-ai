#!/usr/bin/env bash
# Verify a local checkout: imports, tests, and an offline evaluation run.
set -euo pipefail
cd "$(dirname "$0")/.."
export APP_ENV_FILE="${APP_ENV_FILE:-/nonexistent/.env}"
export ANONYMIZED_TELEMETRY=False
python -c "import src.api.main; print('import ok')"
python -m pytest tests -q
python -m eval.run_eval --embedding none --out eval/results/verify-lexical.json
echo "setup verified"
