#!/usr/bin/env bash
# Start the CareVista results dashboard on http://localhost:8000
#
#   ./scripts/start_frontend.sh               # serve the last exported results
#   ./scripts/start_frontend.sh --refresh     # pull the latest results from AWS first
#   PORT=8080 ./scripts/start_frontend.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8000}"
PY=$(command -v python3 || command -v python)

if [ "${1:-}" = "--refresh" ]; then
  echo "Exporting the latest results from AWS..."
  "$PY" "$ROOT/deploy/aws/export_results.py"
fi
[ -f "$ROOT/frontend/data/results.json" ] || echo "warning: frontend/data/results.json not found; run with --refresh (needs AWS login)" >&2

echo "CareVista dashboard: http://localhost:$PORT   (Ctrl+C to stop)"
exec "$PY" -m http.server "$PORT" --bind 127.0.0.1 --directory "$ROOT/frontend"
