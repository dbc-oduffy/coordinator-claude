#!/usr/bin/env bash
# draft-plan-aging.sh — mechanized draft-plan staleness/liveness detector
#
# Faithful clone of handoff-gate-aging.sh's structure (same _date_to_epoch
# BSD/GNU fallback, same _read_fm_field awk frontmatter reader, same
# single-file-or-directory scan, same 0/1/2 exit contract), adapted to the
# draft-plan liveness predicate. A stale, orphaned draft plan must not sit
# silently in docs/plans/ forever — this script is the detector; the caller
# (workday-start/workweek-start) drives the surfacing + decision prompt.
#
# Predicate — a draft plan is STALE iff ALL hold:
#   1. status: draft (frontmatter) — cheap short-circuit.
#   2. now - created: >= 14 days.
#   3. Liveness discriminator — NO recent real-work commit AND NO active baton:
#      3a. Resolve scope: frontmatter paths, prefix-normalized (strip a
#          leading "plugins/coordinator-claude/" so both the published-repo
#          convention and this repo's bare convention resolve against this
#          tree).
#      3b. No commit within the aging window on a normalized scope path
#          whose subject is NOT on the mechanical denylist (pickup:,
#          reclaim(docs), session-init, frontmatter mutation). A no-scope
#          plan fails 3b definitionally (toward surfacing) — no plan-doc-level
#          git-log fallback.
#      3c. No non-consumed handoff in state/handoffs/*.md references the
#          plan's on-disk path in its body. An active baton suppresses STALE.
#          (No prefix-variant matching here: plans live at repo-root
#          docs/plans/<name>.md and are never published under
#          plugins/coordinator-claude/, so the plan's own on-disk path is
#          never prefix-ambiguous — unlike 3a's scope-path normalization,
#          which matches paths *cited inside* the plan. Review: code-reviewer
#          Slice-1 F1/F2 — simplified to the single match the code performs.)
#
# Checker-sidecar exclusion: docs/plans/ also holds report artifacts emitted
# by prior-art-checker / reviewer / docs-checker / plan-coverage-checker
# (*.prior-art-check.md, *.review.md, *.docs-check.md, *.plan-coverage-check.md).
# These carry status:/created: frontmatter of their own but are NOT plans —
# both the directory scan and single-file mode exclude/short-circuit them.
#
# Usage:
#   draft-plan-aging.sh <plan-path>              # single-file check
#   draft-plan-aging.sh <directory>               # scan *.md files (one level)
#
# Output: one line per stale draft plan (path + reason), to stdout.
# Exit codes:
#   0 — no stale draft plans found
#   1 — one or more stale draft plans found (fail loud)
#   2 — internal error (missing path, bad frontmatter, unparseable date,
#       git-log failure, or unresolvable handoff-read failure)
#
# Spec backlink: docs/plans/2026-07-09-continuity-artifact-staleness-parity.md § Design Fix #2, § Chunks C1
# Doctrine anchor: project CLAUDE.md § Architecture ("Both trees are named
#   coordinator-claude; they are NOT the same tree" — the DoE-vs-published
#   prefix trap that motivates condition 3a's normalization).
# Portability (DR-148): bash >= 4 + BSD coreutils; date -d/-j fallback chain, no GNU-only flags.

set -euo pipefail

if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "draft-plan-aging.sh: requires bash >= 4 (current: ${BASH_VERSION})" >&2
  echo "  Install via Homebrew: brew install bash" >&2
  exit 2
fi

AGING_THRESHOLD_DAYS=14

# Checker-sidecar suffix denylist (report artifacts, not plans — see header
# comment). Kept as a small array so it's greppable and extensible.
SIDECAR_SUFFIXES=(".prior-art-check.md" ".review.md" ".docs-check.md" ".plan-coverage-check.md")

# ---------------------------------------------------------------------------
# Returns 0 (true) if the given path's basename ends in a checker-sidecar
# suffix from SIDECAR_SUFFIXES — i.e. it's a report artifact, not a plan.
# ---------------------------------------------------------------------------
_is_sidecar_file() {
  local file="$1" base suffix
  base="$(basename -- "$file")"
  for suffix in "${SIDECAR_SUFFIXES[@]}"; do
    case "$base" in
      *"$suffix") return 0 ;;
    esac
  done
  return 1
}

TARGET="${1-}"
if [[ -z "$TARGET" ]]; then
  echo "draft-plan-aging.sh: missing argument: <plan-path-or-directory>" >&2
  exit 2
fi
if [[ ! -e "$TARGET" ]]; then
  echo "draft-plan-aging.sh: path not found: ${TARGET}" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Portable date-to-epoch (mirrors check-atlas-watch-drift.sh / aggregate-chain-loe.sh
# convention: GNU `date -d` tried first, BSD `date -j -f` fallback).
# ---------------------------------------------------------------------------
_date_to_epoch() {
  local d="$1" e=""
  if date --version >/dev/null 2>&1; then
    e=$(date -d "$d" +%s 2>/dev/null || echo "")
  else
    e=$(date -j -f "%Y-%m-%d" "$d" +%s 2>/dev/null || echo "")
  fi
  printf '%s' "$e"
}

TODAY_EPOCH=$(date +%s)

# ---------------------------------------------------------------------------
# Read a top-level frontmatter scalar field from a plan file.
# Mirrors the awk `/^---$/{n++; next} n==1 && /^field:/` convention used
# throughout commands/workday-start.md and commands/workday-complete.md.
# Strips surrounding double-quotes.
# ---------------------------------------------------------------------------
_read_fm_field() {
  local file="$1" field="$2"
  awk -v f="^${field}:" '
    /^---$/ { n++; next }
    n==1 && $0 ~ f {
      sub(f "[[:space:]]*", "")
      gsub(/^"|"$/, "")
      print
      exit
    }
  ' "$file" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Extract the scope: path list from a plan's frontmatter, one path per line.
# Same awk idiom as extract-scope-paths.sh (handoff-side seam), inlined here
# so this script stays a self-contained clone with no cross-script dependency.
# Prints nothing (not an error) when the scope: block is absent or empty —
# callers must treat "no scope" as its own condition (§ no-scope-block case),
# not as a parse failure.
# ---------------------------------------------------------------------------
_read_scope_paths() {
  local file="$1"
  awk '/^scope:/{found=1; next} found && /^  - /{print substr($0, 5)} found && /^---/{exit} found && /^[a-z]/{exit}' "$file" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Strip a leading "plugins/coordinator-claude/" prefix so both the
# published-repo convention and this repo's bare convention resolve against
# this tree (condition 3a — the DoE-vs-published trap).
# ---------------------------------------------------------------------------
_normalize_prefix() {
  local p="$1"
  printf '%s' "${p#plugins/coordinator-claude/}"
}

# ---------------------------------------------------------------------------
# Condition 3b: does ANY normalized scope path have a real-work commit
# (non-mechanical subject) within the aging window? Prints "1" if yes (real
# recent work found -> NOT stale contribution), "0" if no. On a git-log
# invocation failure (distinct from a valid empty result), returns 2 and
# emits a verbatim stderr diagnostic — caller must map that to exit 2.
# ---------------------------------------------------------------------------
_has_recent_real_work_commit() {
  local file="$1"
  local -a scope_paths=()
  local raw_path norm_path

  while IFS= read -r raw_path; do
    [[ -z "$raw_path" ]] && continue
    norm_path="$(_normalize_prefix "$raw_path")"
    scope_paths+=("$norm_path")
  done < <(_read_scope_paths "$file")

  if [[ "${#scope_paths[@]}" -eq 0 ]]; then
    # No-scope-block case: no scope path to prove a real-work commit against.
    # Condition 3b is definitionally TRUE (no real-work commit) — fails
    # toward surfacing. Do NOT fall back to a plan-doc-level git-log check.
    printf '0'
    return 0
  fi

  local log_output
  if ! log_output="$(git log --since="${AGING_THRESHOLD_DAYS} days ago" --format=%s -- "${scope_paths[@]}" 2>&1)"; then
    echo "draft-plan-aging.sh: ${file}: git log failed on scope paths (${scope_paths[*]}): ${log_output}" >&2
    printf '2'
    return 0
  fi

  if [[ -z "$log_output" ]]; then
    # Valid empty result: no commits in window at all — not an error, not real work.
    printf '0'
    return 0
  fi

  local subject
  while IFS= read -r subject; do
    [[ -z "$subject" ]] && continue
    local lc_subject
    lc_subject="$(printf '%s' "$subject" | tr '[:upper:]' '[:lower:]')"
    # Review: code-reviewer Slice-1 F5 — "pickup:"/"reclaim(docs)"/"session-init"
    # are always commit-subject prefixes in this repo's convention, so anchor
    # them to prefix match. "frontmatter mutation" appears as a SUFFIX
    # ("pickup: X — frontmatter mutation") and must stay an unanchored
    # substring or it breaks the F0 guarantee.
    if [[ "$lc_subject" != "pickup:"* && "$lc_subject" != "reclaim(docs)"* && "$lc_subject" != "session-init"* && "$lc_subject" != *"frontmatter mutation"* ]]; then
      printf '1'
      return 0
    fi
  done <<< "$log_output"

  # Every in-window commit was mechanical.
  printf '0'
  return 0
}

# ---------------------------------------------------------------------------
# Condition 3c: does any non-'consumed' handoff in state/handoffs/*.md
# reference this plan (on-disk path, or its plugins/coordinator-claude/...
# or bare coordinator/... prefix variants) in its body? Prints "1" if an
# active baton is found (suppresses STALE), "0" otherwise. On a
# state/handoffs/ read failure, returns 2 with a verbatim stderr diagnostic.
# ---------------------------------------------------------------------------
_has_active_baton() {
  local file="$1"
  local handoffs_dir="state/handoffs"

  if [[ ! -d "$handoffs_dir" ]]; then
    # No handoffs directory at all: nothing can reference the plan.
    printf '0'
    return 0
  fi

  local -a handoff_files=()
  while IFS= read -r -d '' f; do
    handoff_files+=("$f")
  done < <(find "$handoffs_dir" -maxdepth 1 -name '*.md' -print0 2>/dev/null) || {
    echo "draft-plan-aging.sh: ${file}: failed to read ${handoffs_dir}" >&2
    printf '2'
    return 0
  }

  # Match target: the plan's own on-disk path. No prefix-variant construction
  # here (see condition-3c comment in the header) — the plan's own path is
  # never prefix-ambiguous under this repo's convention.
  local plan_path="$file"

  local hf status
  for hf in "${handoff_files[@]}"; do
    status="$(_read_fm_field "$hf" "status")"
    [[ "$status" == "consumed" ]] && continue

    if grep -qF -- "$plan_path" "$hf" 2>/dev/null; then
      printf '1'
      return 0
    fi
  done

  printf '0'
  return 0
}

# ---------------------------------------------------------------------------
# Evaluate the draft-plan staleness predicate for one plan file.
# Prints "STALE: ..." to stdout when all conditions hold; prints nothing
# when any condition fails. Returns 2 for internal errors (parse error,
# git-log failure, handoff-read failure) — caller distinguishes via return
# code, matching the skeleton's _check_one contract.
# ---------------------------------------------------------------------------
_check_one() {
  local file="$1"
  local status created

  status="$(_read_fm_field "$file" "status")"
  # Condition 1: status must be draft — cheap short-circuit.
  [[ "$status" == "draft" ]] || return 0

  created="$(_read_fm_field "$file" "created")"
  if [[ -z "$created" ]]; then
    echo "draft-plan-aging.sh: ${file}: draft plan missing 'created:' field — cannot evaluate aging" >&2
    return 2
  fi

  local created_epoch
  created_epoch="$(_date_to_epoch "$created")"
  if [[ -z "$created_epoch" ]]; then
    echo "draft-plan-aging.sh: ${file}: unparseable created date '${created}'" >&2
    return 2
  fi

  local age_days=$(( (TODAY_EPOCH - created_epoch) / 86400 ))
  # Condition 2: age >= 14 days.
  (( age_days >= AGING_THRESHOLD_DAYS )) || return 0

  # Condition 3b: recent real-work commit check.
  local has_recent_work
  has_recent_work="$(_has_recent_real_work_commit "$file")"
  if [[ "$has_recent_work" == "2" ]]; then
    return 2
  fi
  if [[ "$has_recent_work" == "1" ]]; then
    # Recent real-work commit found -> not stale.
    return 0
  fi

  # Condition 3c: active baton check.
  local has_baton
  has_baton="$(_has_active_baton "$file")"
  if [[ "$has_baton" == "2" ]]; then
    return 2
  fi
  if [[ "$has_baton" == "1" ]]; then
    # Active baton found -> not stale.
    return 0
  fi

  echo "STALE: ${file} (created ${age_days}d ago, no real-work commit, no owning baton)"
  return 0
}

# ---------------------------------------------------------------------------
# Collect target files: single file, or one-level *.md scan of a directory.
# ---------------------------------------------------------------------------
FILES=()
if [[ -d "$TARGET" ]]; then
  while IFS= read -r -d '' f; do
    _is_sidecar_file "$f" && continue
    FILES+=("$f")
  done < <(find "$TARGET" -maxdepth 1 -name '*.md' -print0 2>/dev/null)
else
  if _is_sidecar_file "$TARGET"; then
    # Single-file mode on a checker sidecar: not a plan, never stale.
    exit 0
  fi
  FILES=("$TARGET")
fi

STALE_COUNT=0
PARSE_ERROR=0
for f in "${FILES[@]}"; do
  out="$(_check_one "$f")" || PARSE_ERROR=1
  if [[ -n "$out" ]]; then
    echo "$out"
    STALE_COUNT=$((STALE_COUNT + 1))
  fi
done

# Review: code-reviewer Slice-1 F3 — when a scan mixes a parse error (file A)
# with genuine staleness (file B), STALE_COUNT>0 wins and this falls through
# to exit 1, masking the parse-error's exit-2 signal (the diagnostic is still
# printed to stderr). This precedence is inherited verbatim from
# handoff-gate-aging.sh and is intentional-inherited, not an oversight —
# fixing it here alone would break clone-fidelity and leave the parent script
# with the same gap; the correct fix touches both scripts as a follow-up.
if [[ "$PARSE_ERROR" -eq 1 && "$STALE_COUNT" -eq 0 ]]; then
  exit 2
fi
if [[ "$STALE_COUNT" -gt 0 ]]; then
  exit 1
fi
exit 0
