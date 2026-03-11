#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT_DIR"

BD_POLICY_SKIP_DOCTOR=1 "$ROOT_DIR/scripts/bd_policy_check.sh"

if bd list --limit 1 >/dev/null 2>&1; then
  echo "bd import: database is healthy, no import required."
  exit 0
fi

if [[ -f ".beads/issues.jsonl" ]]; then
  echo "bd import: bootstrapping local DB from .beads/issues.jsonl..."
  if bd init --prefix eorp --from-jsonl --skip-hooks --quiet >/dev/null 2>&1; then
    echo "bd import: bootstrap completed."
    exit 0
  fi
fi

echo "Error: beads database is not ready and bootstrap failed."
echo "Run recovery command:"
echo "  make bd-recover-from-jsonl"
exit 1
