#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT_DIR"

"$ROOT_DIR/scripts/bd_policy_check.sh"

before="$(mktemp)"
after="$(mktemp)"
trap 'rm -f "$before" "$after"' EXIT

git status --porcelain | awk '{print $2}' | sort -u > "$before"

bd export --output .beads/issues.jsonl >/dev/null

git status --porcelain | awk '{print $2}' | sort -u > "$after"

new_changes="$(comm -13 "$before" "$after" || true)"
if [[ -n "${new_changes:-}" ]]; then
  unsafe="$(echo "$new_changes" | rg -v '^\.beads/issues\.jsonl$' || true)"
  if [[ -n "${unsafe:-}" ]]; then
    echo "Error: bd flush introduced unexpected file changes:"
    echo "$unsafe" | sed 's/^/  - /'
    exit 1
  fi
fi

echo "bd flush completed: .beads/issues.jsonl updated."
