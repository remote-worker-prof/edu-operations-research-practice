#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT_DIR"

REQUIRED_BD_VERSION="0.59.0"

if ! command -v bd >/dev/null 2>&1; then
  echo "Error: 'bd' is not installed or not in PATH."
  exit 1
fi

bd_version_raw="$(bd version | awk '{print $3}')"
if [[ -z "${bd_version_raw:-}" ]]; then
  echo "Error: unable to parse bd version."
  exit 1
fi

version_min="$(printf '%s\n%s\n' "$REQUIRED_BD_VERSION" "$bd_version_raw" | sort -V | head -n1)"
if [[ "$version_min" != "$REQUIRED_BD_VERSION" ]]; then
  echo "Error: bd version must be >= $REQUIRED_BD_VERSION (found: $bd_version_raw)."
  echo "Upgrade command:"
  echo "  curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash"
  exit 1
fi

if [[ -f ".beads/config.yaml" ]] && rg -n '^\s*sync-branch\s*:' ".beads/config.yaml" >/dev/null; then
  echo "Error: sync-branch is configured in .beads/config.yaml."
  echo "This repository uses flush-only workflow; remove 'sync-branch' key."
  exit 1
fi

sync_branch_db="$(bd config get sync.branch 2>/dev/null || true)"
if [[ "${sync_branch_db:-}" == *"not set"* ]]; then
  sync_branch_db=""
fi
if [[ -n "${sync_branch_db:-}" ]]; then
  echo "Error: sync.branch is configured in bd config: '$sync_branch_db'."
  echo "Run: bd config unset sync.branch"
  exit 1
fi

legacy_daemons="$(pgrep -af '[b]d daemon --start' || true)"
if [[ -n "${legacy_daemons:-}" ]]; then
  echo "Error: legacy bd daemon process is running."
  echo "Run: pkill -f 'bd daemon --start'"
  exit 1
fi

if [[ "${BD_POLICY_SKIP_DOCTOR:-0}" != "1" ]]; then
  doctor_json="$(bd doctor --json 2>/dev/null || true)"
  if [[ -z "${doctor_json:-}" ]]; then
    echo "Error: bd doctor did not return JSON output."
    exit 1
  fi

  error_checks="$(echo "$doctor_json" | jq -r '.checks[] | select(.status=="error") | .name' 2>/dev/null || true)"
  if [[ -n "${error_checks:-}" ]]; then
    echo "Error: bd doctor reported error-level checks:"
    echo "$error_checks" | sed 's/^/  - /'
    exit 1
  fi
fi

echo "bd policy check passed (bd $bd_version_raw)"
