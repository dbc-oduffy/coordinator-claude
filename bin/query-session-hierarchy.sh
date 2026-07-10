#!/usr/bin/env bash
# query-session-hierarchy.sh — Reverse-query interface over the per-machine session/workstream
# hierarchy projection shards (state/session-hierarchy.<machine>.json).
#
# Purpose: Given a workstream slug, returns the session_ids that belong to it ("which sessions
# are in workstream X"). Given a session_id, returns its workstream, branch, parent_session_id,
# and session_type. Operates over the UNION of all per-machine shards — answers span every
# machine's derived projection, not just the local one.
#
# Spec backlink: docs/plans/2026-06-27-ccos-5-session-workstream-hierarchy-record.md § C3
#
# Shard format (pinned): each state/session-hierarchy.<machine>.json is a JSON ARRAY of record
# objects conforming to schemas/session-hierarchy.schema.json. Fields: session_id, session_type
# (session|workstream|blitz), workstream, branch, parent_session_id (nullable), linked_handoffs,
# system. The query surface is the UNION across all matching shard globs.
#
# Negative-spec: does NOT parse handoff YAML; does NOT write any state; is NOT the derive script
# (that is derive-session-hierarchy.sh, chunk C2). Read-only; safe to run concurrently.
#
# Dependencies: jq (required; checked at startup), bash >=4 + BSD coreutils (DR-148).

set -euo pipefail

# ---------------------------------------------------------------------------
# Bash >=4 guard (macOS stock /bin/bash is 3.2; coordinator:install provides brew bash)
# Must be reachable on bash 3.2 — simple arithmetic guard, no bash-4 syntax used above it.
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >=4 required (got ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Resolve repo root: walk up from SCRIPT_DIR until we find a .git dir, or use git directly.
_resolve_repo_root() {
  local dir
  dir="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)" && echo "$dir" && return 0
  echo "ERROR: could not resolve repository root from ${SCRIPT_DIR}" >&2
  return 1
}

REPO_ROOT="$(_resolve_repo_root)"

# Review: code-reviewer — F5: QUERY_SHARD_DIR override for test isolation;
# mirrors CLAUDE_HOME override in derive-session-hierarchy.sh. Default is
# the real state/ dir; tests set this to a fixture dir to avoid real-data leakage.
QUERY_SHARD_DIR="${QUERY_SHARD_DIR:-${REPO_ROOT}/state}"

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
_usage() {
  cat <<'EOF'
query-session-hierarchy.sh — Query the session/workstream hierarchy projection.

Reads the union of all state/session-hierarchy.<machine>.json shards.
If no shards exist yet, run derive-session-hierarchy.sh first.

USAGE
  query-session-hierarchy.sh --workstream <slug>
      Print all session_ids belonging to workstream <slug>, one per line.

  query-session-hierarchy.sh --session <session_id>
      Print a JSON object with workstream, branch, parent_session_id, and
      session_type for the given session_id.

  query-session-hierarchy.sh [--help | -h]
      Show this message.

EXAMPLES
  query-session-hierarchy.sh --workstream example-workstream
  query-session-hierarchy.sh --session d964cd5a-f3db-4d10-b906-9b63701ec4a4

NOTES
  - Shard location: state/session-hierarchy.<machine>.json (per-machine)
  - Query surface: UNION across all shards (all machines)
  - Requires: jq
  - Output for --workstream: one session_id per line (empty output = no sessions found)
  - Output for --session: JSON object, or error + exit 1 if not found

SPEC
  docs/plans/2026-06-27-ccos-5-session-workstream-hierarchy-record.md § C3
EOF
}

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------
if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: jq not found — required for query-session-hierarchy.sh" >&2
  echo "Install via: brew install jq  (macOS)  or  apt-get install jq  (Debian/Ubuntu)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
MODE=""
ARG_VALUE=""

case "${1:-}" in
  --help | -h | "")
    _usage
    exit 0
    ;;
  --workstream)
    MODE="workstream"
    ARG_VALUE="${2:-}"
    if [[ -z "$ARG_VALUE" ]]; then
      echo "ERROR: --workstream requires a slug argument" >&2
      _usage >&2
      exit 2
    fi
    ;;
  --session)
    MODE="session"
    ARG_VALUE="${2:-}"
    if [[ -z "$ARG_VALUE" ]]; then
      echo "ERROR: --session requires a session_id argument" >&2
      _usage >&2
      exit 2
    fi
    ;;
  *)
    echo "ERROR: unknown argument: ${1}" >&2
    _usage >&2
    exit 2
    ;;
esac

# ---------------------------------------------------------------------------
# Glob shard files (nullglob prevents literal glob on zero matches)
# ---------------------------------------------------------------------------
shopt -s nullglob
shard_files=( "${QUERY_SHARD_DIR}/session-hierarchy."*.json )
shopt -u nullglob

if [[ ${#shard_files[@]} -eq 0 ]]; then
  echo "ERROR: no session-hierarchy shards found — run derive-session-hierarchy.sh first" >&2
  echo "  Expected: ${QUERY_SHARD_DIR}/session-hierarchy.<machine>.json" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------
case "$MODE" in
  workstream)
    # Print one session_id per line for every record whose workstream matches the slug.
    # jq reads each shard file in sequence; each is a JSON array — iterate .[] and filter.
    # Review: code-reviewer — F1: exclude the synthetic workstream container node
    # (session_type=="workstream") so callers receive only member session_ids (UUIDs),
    # not the "workstream:<slug>" container id that downstream consumers (ccos-7/8)
    # would reject as a non-UUID.
    jq -r --arg slug "$ARG_VALUE" \
      '.[] | select(.workstream == $slug and .session_type != "workstream") | .session_id' \
      "${shard_files[@]}"
    ;;

  session)
    # Print a compact JSON object for the matching session_id.
    # -c outputs each match on one line; head -n1 stops after the first match
    # (session_ids are unique across machines per shard contract, but the union
    # may pass the same record through multiple shard files during a transition —
    # take first match only).
    RESULT="$(jq -c --arg sid "$ARG_VALUE" \
      '.[] | select(.session_id == $sid) | {session_id, session_type, workstream, branch, parent_session_id}' \
      "${shard_files[@]}" | head -n 1)"

    if [[ -z "$RESULT" ]]; then
      echo "ERROR: session_id not found in any shard: ${ARG_VALUE}" >&2
      echo "  Searched ${#shard_files[@]} shard(s): ${shard_files[*]}" >&2
      exit 1
    fi
    printf '%s\n' "$RESULT"
    ;;
esac
