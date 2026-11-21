#!/usr/bin/env bash
# Run the full test suite (unit + end-to-end) locally (Linux / WSL / macOS).
set -euo pipefail
cd "$(dirname "$0")/.."
export JAVA_HOME="${JAVA_HOME:-$HOME/jdk17}"
PY="${PYTHON:-$HOME/hc-venv/bin/python}"
export PYTHONPATH="$PWD/src"
"$PY" -m pytest tests -v "$@"
