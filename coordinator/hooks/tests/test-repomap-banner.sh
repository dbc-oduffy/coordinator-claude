#!/usr/bin/env bash
# Test suite for the repomap staleness banner in project-orientation.sh.
#
# The banner is emitted on EVERY session path (above the cache early-exits).
# Stale-only: silent when fresh (<24h), one line when stale (24-168h), louder
# when very-stale (>=168h). Tracks .claude/repomap.md. Kill-switch:
# COORDINATOR_REPOMAP_STATUS_OFF (sentinel to stderr, no stdout banner).
#
# Isolation: each scenario runs the hook with cwd = a fresh non-git TMPDIR, so
# `git rev-parse --show-toplevel` returns empty and ${REPO_ROOT:-.} resolves to
# that fixture dir. Fixture mtimes are set via python3 os.utime (absolute epoch)
# — never `touch -d 'N hours ago'`, which has no relative form on BSD/macOS (DR-148).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/../scripts/project-orientation.sh"
PASS=0
FAIL=0

# Clean up fixture dirs on exit (each mkroot appends to CLEANUP_DIRS).
CLEANUP_DIRS=()
trap 'rm -rf "${CLEANUP_DIRS[@]}"' EXIT

# mkroot <age_hours|"none"> -> prints a fresh fixture project-root dir.
# "none" omits the repomap entirely; otherwise writes .claude/repomap.md with an
# mtime age_hours in the past.
mkroot() {
  local age="$1" root
  root=$(mktemp -d)
  CLEANUP_DIRS+=("$root")
  if [ "$age" != "none" ]; then
    mkdir -p "$root/.claude"
    printf '# repo map fixture\n' > "$root/.claude/repomap.md"
    local target
    target=$(( $(date +%s) - age * 3600 ))
    python3 -c "import os,sys; t=int(sys.argv[2]); os.utime(sys.argv[1],(t,t))" \
      "$root/.claude/repomap.md" "$target"
  fi
  printf '%s' "$root"
}

# run_stdout <root> [extra-env...] -> hook stdout (stderr discarded)
run_stdout() {
  local root="$1"; shift
  ( cd "$root" && env "$@" bash "$HOOK" --lightweight 2>/dev/null || true )
}
# run_stderr <root> [extra-env...] -> hook stderr (stdout discarded)
run_stderr() {
  local root="$1"; shift
  ( cd "$root" && { env "$@" bash "$HOOK" --lightweight >/dev/null; } 2>&1 || true )
}

expect() { # <desc> <expected> <actual>
  if [[ "$2" == "$3" ]]; then PASS=$((PASS + 1)); else
    FAIL=$((FAIL + 1)); echo "FAIL: $1 (expected '$2', got '$3')"; fi
}
# Literal substring membership (grep -F) — patterns are fixed strings, not regex.
has() { printf '%s' "$1" | grep -qF "$2" && echo yes || echo no; }

# --- Scenario 1: no repomap -> banner silent ---------------------------------
R=$(mkroot none)
OUT=$(run_stdout "$R")
expect "missing repomap: no stale banner" no "$(has "$OUT" 'Repo map stale')"
expect "missing repomap: no very-stale banner" no "$(has "$OUT" 'VERY STALE')"

# --- Scenario 2: fresh (<24h) -> silent --------------------------------------
R=$(mkroot 2)
OUT=$(run_stdout "$R")
expect "fresh repomap: no stale banner" no "$(has "$OUT" 'Repo map stale')"
expect "fresh repomap: no very-stale banner" no "$(has "$OUT" 'VERY STALE')"

# --- Scenario 3: stale (25h) -> one stale line -------------------------------
R=$(mkroot 25)
OUT=$(run_stdout "$R")
expect "25h: stale line on stdout" yes "$(has "$OUT" 'Repo map stale:')"
expect "25h: not flagged very-stale" no "$(has "$OUT" 'VERY STALE')"

# --- Scenario 4: very-stale (200h) -> very-stale line ------------------------
R=$(mkroot 200)
OUT=$(run_stdout "$R")
expect "200h: VERY STALE on stdout" yes "$(has "$OUT" 'VERY STALE')"

# --- Scenario 5: kill-switch -> stderr sentinel, no stdout banner ------------
R=$(mkroot 200)
OUT=$(run_stdout "$R" COORDINATOR_REPOMAP_STATUS_OFF=1)
ERR=$(run_stderr "$R" COORDINATOR_REPOMAP_STATUS_OFF=1)
expect "kill-switch: no banner on stdout" no "$(has "$OUT" 'VERY STALE')"
expect "kill-switch: sentinel on stderr" yes "$(has "$ERR" 'disabled via COORDINATOR_REPOMAP_STATUS_OFF')"

# --- Scenario 6 (AC3b): cache PRESENT + stale -> banner still fires -----------
# Note: the fixture is a non-git dir, so the hook's `git cat-file` on the cache
# HEAD fails and the cache exits via its "HEAD unverifiable" branch. That's fine
# for AC3b — the contract is "banner fires above the cache exit regardless of
# which cache branch handles the exit", which this verifies.
R=$(mkroot 25)
mkdir -p "$R/state"
cat > "$R/state/orientation_cache.md" <<'EOF'
---
git_head_at_generation: deadbeef
---
# cache
EOF
OUT=$(run_stdout "$R")
expect "cache-present + stale: banner still fires" yes "$(has "$OUT" 'Repo map stale')"

# --- Scenario 7: full startup (NO --lightweight), cache absent + stale ---------
# Exercises the full-mode path: banner fires AND the cache-absent pointers section
# emits the "Repo Map:" read-pointer.
R=$(mkroot 25)
OUT=$( cd "$R" && bash "$HOOK" 2>/dev/null || true )
expect "full-startup: banner fires" yes "$(has "$OUT" 'Repo map stale:')"
expect "full-startup: read-pointer appears" yes "$(has "$OUT" 'Repo Map: .claude/repomap.md')"

echo "----"
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
