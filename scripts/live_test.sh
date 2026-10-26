#!/usr/bin/env bash
set -euo pipefail

if [[ "${AZURE_SUBSCRIPTIONS:-}" == "" ]]; then
  echo "AZURE_SUBSCRIPTIONS must contain one or more subscription UUIDs" >&2
  exit 1
fi

python - <<'PY'
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit(f"Expected Python 3.12, found {sys.version.split()[0]}")
import function_app
assert function_app.app is not None
print("Function package import: OK")
PY

if [[ "${AZURE_SMOKE_LIVE:-0}" != "1" ]]; then
  echo "Local package/config check passed. Set AZURE_SMOKE_LIVE=1 for read-only Azure discovery."
  exit 0
fi

python scripts/azure_smoke_test.py
