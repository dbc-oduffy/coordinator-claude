#!/usr/bin/env bash
# backfill-initiative-fk.sh — idempotent batch-attach tool for the initiative FK.
#
# Spec backlink: docs/plans/2026-07-06-ceremony-as-pipeline-2-doe-land-d-slice.md § F4 (AC8)
#
# Purpose: reads (artifact-path, initiative-id) pairs from a TSV file (or stdin)
# and attaches the initiative FK to each artifact via coordinator-initiative attach.
# Designed to be run as a one-shot back-fill after initiatives are minted; safe
# to re-run on a partially-processed set.
#
# Input format: TSV with two tab-separated columns per line:
#   <artifact-path><TAB><initiative-id>
# Comment lines (# ...) and blank lines are ignored.
#
# Usage:
#   backfill-initiative-fk.sh [mapping.tsv]     # read from file
#   cat mapping.tsv | backfill-initiative-fk.sh  # read from stdin
#   backfill-initiative-fk.sh -                  # explicit stdin
#
# Idempotency:
#   Greps each artifact's frontmatter before calling coordinator-initiative attach.
#   If the artifact already carries the exact target initiative FK, the pair is
#   skipped with a "skipped (already attached)" message. A full re-run over an
#   already-processed mapping is a clean no-op with exit 0.
#
# Concurrency safety:
#   A lockfile (written to /tmp) structurally prevents two concurrent invocations.
#   Per concurrent-em-hazards §H1, concurrent frontmatter writers corrupt the tree.
#   If a lock is held, the second invocation exits non-zero with a warning naming
#   the holding PID.
#
# Fail-loud:
#   Exits non-zero and names the failing pair when coordinator-initiative attach
#   returns non-zero (e.g. unknown initiative-id, missing artifact).
#
# BSD-portable — bash ≥ 4 required (same guard as coordinator-initiative).
#
# Negative-spec: does NOT auto-create initiatives; run coordinator-initiative create first.
# Negative-spec: does NOT modify the mapping file in-place.
# Negative-spec: does NOT read from multiple mapping files in one invocation.
# Negative-spec: does NOT implement concurrency via flock(1) — macOS BSD does not ship flock;
#   uses a lockfile-PID guard instead, which is portable across macOS and Linux bash ≥ 4.
#
# Environment:
#   COORDINATOR_INITIATIVE_ROOT — if set, forwarded to coordinator-initiative (affects initiative
#   resolution; used in tests to redirect to a fixture directory instead of live central state).
#
# Known limitation — PID-reuse hazard (RAW-PID-LIVENESS tripwire):
#   The concurrency guard probes lock-holder liveness via kill -0 <pid>. PID values are reused
#   by the OS; after a crash the stored PID may belong to an unrelated process, causing a live
#   lock to appear stale (or vice-versa). There is no portable shell-only fix for PID reuse.
#   If the lock appears stuck, remove the lockfile manually: rm -f "${TMPDIR:-/tmp}/backfill-initiative-fk.lock".
#   Additionally, if the lock holder belongs to a different user, kill -0 may fail with EPERM,
#   causing a live lock to appear stale and be overwritten.

set -euo pipefail

# ── Portability guard ──────────────────────────────────────────────────────────
if (( ${BASH_VERSINFO[0]:-0} < 4 )); then
  printf 'backfill-initiative-fk: bash 4+ required (found %s).\n' "${BASH_VERSION:-unknown}" >&2
  printf '  Remediation: brew install bash (macOS) or apt install bash (Linux).\n' >&2
  exit 1
fi

# ── Path resolution ────────────────────────────────────────────────────────────
# Resolve coordinator-initiative relative to this script's own dir so that the
# tool works regardless of how it is invoked (no hardcoded /Users/example-operator paths).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COORDINATOR_INITIATIVE="${SCRIPT_DIR}/coordinator-initiative"

if [[ ! -x "$COORDINATOR_INITIATIVE" ]]; then
  printf 'backfill-initiative-fk: coordinator-initiative not found or not executable at %s\n' \
    "$COORDINATOR_INITIATIVE" >&2
  printf '  Ensure the coordinator plugin is fully installed.\n' >&2
  exit 1
fi

# ── Lockfile concurrency guard ─────────────────────────────────────────────────
# Uses a lockfile-PID pattern (POSIX sh, macOS BSD + Linux compatible).
# Per concurrent-em-hazards §H1: concurrent frontmatter writers corrupt the tree.
# coordinator-initiative attach is atomic per-artifact but the backfill session
# as a whole must be single-runner.
LOCKFILE="${TMPDIR:-/tmp}/backfill-initiative-fk.lock"

_acquire_lock() {
  # Review: code-reviewer — F3: use noclobber (set -C) for atomic initial lock creation to
  # eliminate the TOCTOU window between existence-check and file-write on a non-existent lockfile.
  if ( set -C; printf '%s\n' "$$" > "$LOCKFILE" ) 2>/dev/null; then
    return 0  # Atomically acquired — lockfile created exclusively by this process.
  fi
  # Lockfile already exists — read and check whether the holder is still live.
  local held_pid
  held_pid=$(cat "$LOCKFILE" 2>/dev/null || true)
  # Review: code-reviewer — F4: RAW-PID-LIVENESS — kill -0 is subject to PID reuse and EPERM
  # hazards; see header "Known limitation" block. No portable shell-only fix.
  if [[ -n "$held_pid" ]] && kill -0 "$held_pid" 2>/dev/null; then
    printf 'backfill-initiative-fk: another instance is running (PID %s, lockfile %s).\n' \
      "$held_pid" "$LOCKFILE" >&2
    printf '  Wait for it to finish, or remove the lockfile if it crashed.\n' >&2
    exit 1
  fi
  # Stale lockfile from a crashed prior run — overwrite below.
  printf 'backfill-initiative-fk: removing stale lockfile (PID %s no longer running).\n' \
    "${held_pid:-unknown}" >&2
  printf '%s\n' "$$" > "$LOCKFILE"
}

_release_lock() {
  # Review: code-reviewer — F1: only remove the lockfile when this process owns it.
  # Without this guard, a second invocation that exits via exit 1 inside _acquire_lock
  # fires the EXIT trap and unconditionally deletes the legitimate first holder's lockfile,
  # allowing a third invocation to acquire the lock while the first is still running.
  local lock_pid
  lock_pid=$(cat "$LOCKFILE" 2>/dev/null || true)
  if [[ "$lock_pid" == "$$" ]]; then
    rm -f "$LOCKFILE"
  fi
}

trap '_release_lock' EXIT

_acquire_lock

# ── Input source ───────────────────────────────────────────────────────────────
# Optional positional arg: path to TSV file, or '-' for explicit stdin.
# Default (no arg): stdin.
INPUT_SRC="${1:--}"

# ── Processing loop ────────────────────────────────────────────────────────────
# Reads TSV lines, skips blanks and comments (#...), and for each pair either
# skips (already attached) or calls coordinator-initiative attach (fail-loud).

skipped=0
attached=0
errors=0

_process_pairs() {
  local line_no=0
  while IFS=$'\t' read -r artifact_path initiative_id || [[ -n "$artifact_path" ]]; do
    (( line_no++ )) || true

    # Strip leading/trailing whitespace from each field.
    artifact_path="${artifact_path#"${artifact_path%%[! ]*}"}"
    artifact_path="${artifact_path%"${artifact_path##*[! ]}"}"
    initiative_id="${initiative_id#"${initiative_id%%[! ]*}"}"
    initiative_id="${initiative_id%"${initiative_id##*[! ]}"}"
    # Review: code-reviewer — F9: trim extra TSV columns. IFS=$'\t' read assigns the remainder
    # of a line (including further tabs) to the last named field; a 3-column input would set
    # initiative_id="col2<TAB>col3", breaking the idempotency grep and attach call.
    initiative_id="${initiative_id%%$'\t'*}"

    # Skip blank lines and comment lines.
    [[ -z "$artifact_path" ]] && continue
    [[ "$artifact_path" == \#* ]] && continue

    if [[ -z "$initiative_id" ]]; then
      printf 'backfill-initiative-fk: line %d: missing initiative-id for artifact: %s\n' \
        "$line_no" "$artifact_path" >&2
      (( errors++ )) || true
      continue
    fi

    # ── Idempotency check ────────────────────────────────────────────────────
    # Grep the artifact frontmatter for the exact target FK before attaching.
    # If already set to the target id, skip cleanly.
    # Review: code-reviewer — F2: end-anchor the grep to prevent false-positive skips when
    # initiative_id is a prefix of the attached value (e.g. "abc" would match "abcdef").
    if grep -qE "^initiative: ${initiative_id}[[:space:]]*$" "$artifact_path" 2>/dev/null; then
      printf 'skipped (already attached): %s -> initiative: %s\n' \
        "$artifact_path" "$initiative_id"
      (( skipped++ )) || true
      continue
    fi

    # ── Attach ───────────────────────────────────────────────────────────────
    # Delegate to coordinator-initiative attach (atomic write, fail-loud on
    # unknown initiative-id or missing artifact).
    if ! "$COORDINATOR_INITIATIVE" attach "$artifact_path" "$initiative_id"; then
      printf 'backfill-initiative-fk: FAILED pair: %s -> %s\n' \
        "$artifact_path" "$initiative_id" >&2
      (( errors++ )) || true
      # Continue processing remaining pairs; collect all failures before exiting.
      continue
    fi

    (( attached++ )) || true
  done
}

if [[ "$INPUT_SRC" == "-" ]]; then
  _process_pairs
else
  if [[ ! -f "$INPUT_SRC" ]]; then
    printf 'backfill-initiative-fk: mapping file not found: %s\n' "$INPUT_SRC" >&2
    exit 1
  fi
  _process_pairs < "$INPUT_SRC"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
printf 'backfill-initiative-fk: done — attached=%d skipped=%d errors=%d\n' \
  "$attached" "$skipped" "$errors"

if [[ $errors -gt 0 ]]; then
  exit 1
fi

exit 0
