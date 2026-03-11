#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT_DIR"

if [[ ! -f ".beads/issues.jsonl" ]]; then
  echo "Error: .beads/issues.jsonl not found."
  exit 1
fi

echo "Recovering beads database from .beads/issues.jsonl..."
bd init --force --prefix eorp --from-jsonl --skip-hooks --quiet

echo "Recovery completed."
