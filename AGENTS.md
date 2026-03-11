# Agent Instructions

This project uses **bd** (beads) for issue tracking.
Run `bd onboard` to get started.

## Safe Mode Policy

This repository uses beads in a **flush-only** workflow.

- Do **not** run raw `bd sync` in this repo.
- Required `bd` version: `>= 0.59.0`.
- Start session with `make bd-import`.
- Before commit/push run `make bd-session-close`.

## Quick Reference

```bash
bd ready                               # Find available work
bd show <id>                           # View issue details
bd update <id> --status in_progress    # Claim work
bd close <id>                          # Complete work
make bd-check                          # Policy and health checks
make bd-import                         # Safe start step
make bd-flush                          # Export to .beads/issues.jsonl
make bd-session-close                  # Pre-push safety sequence
```

## Landing the Plane (Session Completion)

**When ending a work session**, all steps below are mandatory.
Work is NOT complete until `git push` succeeds.

1. File issues for remaining work.
2. Run quality gates (if code changed).
3. Update issue status (close finished, update in-progress).
4. Push to remote:
   ```bash
   git pull --rebase
   make bd-import
   make bd-session-close
   git push
   git status  # MUST show up-to-date with origin
   ```
5. Clean up (stashes, stale branches).
6. Verify all intended changes are committed and pushed.
7. Hand off with context for next session.

## Critical Rules

- Work is NOT complete until `git push` succeeds.
- Never stop before pushing.
- Never say "ready to push when you are"; push directly.
- If push fails, resolve and retry until success.
- Never run raw `bd sync` in this repository.
