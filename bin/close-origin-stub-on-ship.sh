#!/usr/bin/env bash
# close-origin-stub-on-ship.sh — close the origin spinoff/spinoff-roadmap stub
# whose work just shipped, joining on (roadmap_id, stub_id) from the governing
# plan / consumed handoff.
#
# Purpose: a `kind: spinoff-roadmap` (or `spinoff`) origin stub in
# state/handoffs/ is authored `deployment_state: ready_to_fire` and its work
# is often executed through a SEPARATE plan/baton — the origin stub's own
# frontmatter is never touched again, so after the work ships the origin stub
# is left ready_to_fire forever, wrongly advertising shipped work as a live
# pickup-able target. This helper closes that stub at /workstream-complete
# time by joining on the (roadmap_id, stub_id) pair the governing plan (or
# consumed handoff) already carries in its own frontmatter.
#
# Spec backlinks:
#   cross-repo/inbox/2026-07-08-example-cockpit-repo-em-spinoff-roadmap-lifecycle-never-closed.md
#   state/handoffs/2026-07-08_205600_roadmap-lvv-09.md (C9/lvv-09 — sibling cadence backstop)
#
# Negative-spec: this is the PROACTIVE close-on-ship path, run inline from
# /workstream-complete Step 2.7b. The cadence-sweep backstop (lvv-09) is a
# SEPARATE, deferred mechanism that walks non-terminal stubs on a cadence and
# rolls them up via deliverable-id derivation — do NOT implement roll-up
# logic here; this script only ever closes via the exact (roadmap_id,
# stub_id) join surfaced at ship time.
#
# Trust boundary (Review: code-reviewer Finding 2, P2): this helper trusts
# the governing plan's/handoff's self-asserted `roadmap_id`/`stub_id` as an
# honest, complete claim that the plan realized the stub's promised scope.
# It does NOT verify the plan actually completed the stub's acceptance
# criteria, and it has no mechanism to distinguish "this plan fully realized
# the stub" from "this plan merely carries the stub's id" (e.g. a multi-plan
# stub where only the first plan completes). The correctness-derivation
# backstop — deriving ship-state from resolving commits rather than trusting
# self-asserted ids — is the deferred C9/lvv-09 cadence sweep's job, not
# this script's. A premature close (multi-plan stub, first plan completing)
# is a bounded, self-correcting harm: a later re-pickup of the still-open
# work reopens the stub. That bounded risk is strictly preferable to the
# permanent false-`ready_to_fire` state this script exists to fix.
#
# Usage:
#   close-origin-stub-on-ship.sh [--plan <plan-path>] [--handoff <handoff-path>]
#
# At least one of --plan / --handoff must be given.
#
# Exit: always 0 except usage errors (exit 2) — a declined stamp, an
# ambiguous match, or a no-op join are all non-fatal, surfaced states, not
# script failures.

set -euo pipefail

# ---------------------------------------------------------------------------
# bash>=4 guard (DR-148) — must be reachable on bash 3.2 (plain comparison)
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
PLAN_PATH=""
HANDOFF_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan)
      if [[ -z "${2-}" ]]; then
        echo "close-origin-stub-on-ship.sh: --plan requires an argument" >&2
        exit 2
      fi
      PLAN_PATH="$2"
      shift 2
      ;;
    --handoff)
      if [[ -z "${2-}" ]]; then
        echo "close-origin-stub-on-ship.sh: --handoff requires an argument" >&2
        exit 2
      fi
      HANDOFF_PATH="$2"
      shift 2
      ;;
    *)
      echo "close-origin-stub-on-ship.sh: unknown argument: $1" >&2
      echo "usage: close-origin-stub-on-ship.sh [--plan <plan-path>] [--handoff <handoff-path>]" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$PLAN_PATH" && -z "$HANDOFF_PATH" ]]; then
  echo "close-origin-stub-on-ship.sh: usage: close-origin-stub-on-ship.sh [--plan <plan-path>] [--handoff <handoff-path>]" >&2
  echo "close-origin-stub-on-ship.sh: at least one of --plan / --handoff must be given" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# _extract_fm_field FILE FIELD — extract a top-level YAML frontmatter scalar
# field's value, stripping surrounding quotes. Portable (awk-only, no GNU
# sed/grep -P). Prints empty string if the field is absent or the file has
# no frontmatter.
# Review: code-reviewer Finding 5 (nit) — trailing-comment stripping
# (`field: value  # comment`) is skipped for quoted values, since a quoted
# scalar cannot legitimately carry an inline comment; see Finding 1 fix above.
# ---------------------------------------------------------------------------
_extract_fm_field() {
  local file="$1" field="$2"
  [[ -f "$file" ]] || return 0
  awk -v field="$field" '
    NR==1 && /^---[[:space:]]*$/ { infm=1; next }
    infm && /^---[[:space:]]*$/ { exit }
    infm {
      pat = "^" field ":[[:space:]]*"
      if ($0 ~ pat) {
        val = $0
        sub(pat, "", val)
        sub(/[[:space:]]+$/, "", val)
        # Review: code-reviewer Finding 1 (P1) — comment-strip must run AFTER
        # quote-strip, and only apply to unquoted values: a quoted YAML
        # scalar cannot carry an inline comment, so stripping "#..." before
        # checking quotes truncated quoted values containing "#" (e.g.
        # stub_id: "idx-01#c3" silently became "idx-01").
        is_quoted = (val ~ /^"/ || val ~ /^'"'"'/)
        sub(/^"/, "", val); sub(/"$/, "", val)
        sub(/^'"'"'/, "", val); sub(/'"'"'$/, "", val)
        if (!is_quoted) {
          sub(/[[:space:]]*#.*$/, "", val)   # strip trailing comment (unquoted values only)
        }
        print val
        exit
      }
    }
  ' "$file" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Step 1 — collect (roadmap_id, stub_id) pairs from provided sources.
# ---------------------------------------------------------------------------
declare -a PAIRS=()

for src in "$PLAN_PATH" "$HANDOFF_PATH"; do
  [[ -z "$src" ]] && continue
  [[ -f "$src" ]] || continue
  rid="$(_extract_fm_field "$src" "roadmap_id")"
  sid="$(_extract_fm_field "$src" "stub_id")"
  if [[ -n "$rid" && -n "$sid" ]]; then
    PAIRS+=("${rid}"$'\t'"${sid}")
  fi
done

if [[ "${#PAIRS[@]}" -eq 0 ]]; then
  echo "close-origin-stub-on-ship: no (roadmap_id,stub_id) in inputs — no-op"
  exit 0
fi

# De-duplicate pairs (a plan and a handoff could legitimately carry the same pair).
declare -a UNIQUE_PAIRS=()
for pair in "${PAIRS[@]}"; do
  dup=0
  for seen in "${UNIQUE_PAIRS[@]+"${UNIQUE_PAIRS[@]}"}"; do
    [[ "$pair" == "$seen" ]] && { dup=1; break; }
  done
  [[ "$dup" -eq 0 ]] && UNIQUE_PAIRS+=("$pair")
done

# ---------------------------------------------------------------------------
# Steps 2-5 — for each pair, scan state/handoffs/*.md for a non-terminal
# origin stub matching (kind, roadmap_id, stub_id).
# ---------------------------------------------------------------------------
for pair in "${UNIQUE_PAIRS[@]}"; do
  rid="${pair%%$'\t'*}"
  sid="${pair#*$'\t'}"

  declare -a MATCHES=()

  for stub in state/handoffs/*.md; do
    [[ -f "$stub" ]] || continue

    stub_kind="$(_extract_fm_field "$stub" "kind")"
    case "$stub_kind" in
      spinoff|spinoff-roadmap) ;;
      *) continue ;;
    esac

    stub_rid="$(_extract_fm_field "$stub" "roadmap_id")"
    [[ "$stub_rid" == "$rid" ]] || continue

    stub_sid="$(_extract_fm_field "$stub" "stub_id")"
    [[ "$stub_sid" == "$sid" ]] || continue

    stub_state="$(_extract_fm_field "$stub" "deployment_state")"
    case "$stub_state" in
      ready_to_fire|awaiting_gate) ;;
      *) continue ;;   # excludes in_flight/shipped/abandoned — non-terminal ONLY
    esac

    MATCHES+=("$stub")
  done

  match_count="${#MATCHES[@]}"

  if [[ "$match_count" -eq 0 ]]; then
    echo "close-origin-stub-on-ship: no non-terminal origin stub for (${rid},${sid}) — nothing to close"
    continue
  fi

  if [[ "$match_count" -gt 1 ]]; then
    echo "close-origin-stub-on-ship: WARNING ambiguous — ${match_count} stubs match (${rid},${sid}); refusing to stamp any" >&2
    continue
  fi

  stub_path="${MATCHES[0]}"

  if bash "${SCRIPT_DIR}/coordinator-handoff-archive.sh" "$stub_path" --stamp-only; then
    echo "close-origin-stub-on-ship: closed origin stub ${stub_path} (stub_id ${sid}) — deployment_state: shipped"
  else
    echo "close-origin-stub-on-ship: WARNING coordinator-handoff-archive.sh --stamp-only reported an issue for ${stub_path} (stub_id ${sid})" >&2
  fi
done

exit 0
