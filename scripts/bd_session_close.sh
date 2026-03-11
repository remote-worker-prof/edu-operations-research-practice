#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT_DIR"

"$ROOT_DIR/scripts/bd_policy_check.sh"
"$ROOT_DIR/scripts/bd_flush_safe.sh"

echo "Session-close preflight done."
echo "Next:"
echo "  git add -A"
echo "  git commit -m \"[eorp-<id>] ...\""
echo "  git push"
