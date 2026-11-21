#!/usr/bin/env bash
# Run the whole pipeline locally (Linux / WSL / macOS).
#   ./scripts/run_local.sh [batch_id] [extra args, e.g. --fail-once silver]
set -euo pipefail
cd "$(dirname "$0")/.."
BATCH_ID="${1:-B20260630}"; shift || true
export JAVA_HOME="${JAVA_HOME:-$HOME/jdk17}"
PY="${PYTHON:-$HOME/hc-venv/bin/python}"
export PYTHONPATH="$PWD/src"
"$PY" -m carevista.pipeline \
  --input-path "$PWD/data/source" \
  --batch-id "$BATCH_ID" \
  --lake-root "$PWD/lake" \
  --report-dir "$PWD/reports" "$@"
