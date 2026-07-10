#!/usr/bin/env bash
# edit-live-hook.sh — stage/validate/atomic-swap helper for editing a LIVE PreToolUse
# Bash-matcher hook without ever exposing a syntactically-broken intermediate to the
# harness's per-tool-call `exec`.
#
# Purpose: the Claude Code harness execs each hook fresh from disk on every matching
# tool call — there is no cached/compiled hook process. A multi-`Edit` sequence
# directly against a hook file that is currently registered under a Bash-inclusive
# PreToolUse matcher leaves every intermediate edit state briefly the *live
# enforcement code* for every concurrent agent's Bash tool calls, not just the
# editor's own session. If any intermediate is syntactically broken, the very next
# Bash call from ANY concurrent session fails at the PreToolUse gate. This helper
# implements the safe pattern: copy the live hook to a scratch path, let the operator
# or agent edit the scratch copy freely (as many `Edit` calls as needed — none of them
# touch the live path), then validate the FINAL scratch state with `bash -n` and land
# it via a single atomic same-filesystem `mv` — there is no window where the live path
# is a partially-written file.
#
# See: coordinator/docs/wiki/concurrent-em-hazards.md § H33 for the incident this
# helper was built to prevent (2026-07-09, block-illegal-filename.sh heredoc-fix
# took down 4 concurrent agents' Bash tool fleet-wide).
#
# DO NOT multi-`Edit` a live Bash-matcher hook path directly, even "just to fix one
# line" — there is no such thing as an atomic single-line Edit at the harness level;
# the file is briefly absent/truncated during the write, and a fresh `exec` racing
# that window sees a broken or empty script. Always stage-edit-validate-swap.
#
# Usage:
#   edit-live-hook.sh stage <hook-path>
#       Copies <hook-path> to a scratch file next to it (same directory, so the
#       eventual `mv` is same-filesystem/atomic) and prints the scratch path.
#       Also runs the Bash-matcher detection check (see below) and WARNs — but
#       does not block — if the target isn't actually a live Bash-matcher hook,
#       since staging is harmless there too and the operator may want the same
#       discipline for any hook file.
#
#   edit-live-hook.sh commit <hook-path> <scratch-path>
#       Validates <scratch-path> with `bash -n`. On success, atomically `mv`s
#       <scratch-path> over <hook-path> (same-filesystem rename) and reports
#       success. On syntax failure, refuses to swap, leaves both files in place,
#       and exits non-zero — the live hook is never touched.
#
# Two-subcommand shape (not a single `edit-live-hook.sh <hook-path>` one-shot)
# because staging and committing happen in different tool calls with editing in
# between — the agent/operator needs the scratch path back before it can edit it.
#
# Exit codes: 0 success; 1 usage/argument error; 2 `bash -n` validation failure
# on commit (the swap did NOT happen).

set -euo pipefail

# ---------------------------------------------------------------------------
# Bash >=4 guard -- MUST be above all bash-4 syntax; parses safely on bash 3.2.
# ---------------------------------------------------------------------------
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  {
    printf 'edit-live-hook.sh: requires bash >=4 (found %s).\n' "${BASH_VERSION:-unknown}"
    printf '  macOS: brew install bash  (restart terminal; /opt/homebrew/bin/bash is bash 5)\n'
    printf '  Reference: coordinator/docs/wiki/cross-platform-shell-portability.md\n'
  } >&2
  exit 1
fi

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat >&2 <<EOF
Usage:
  ${SCRIPT_NAME} stage <hook-path>
  ${SCRIPT_NAME} commit <hook-path> <scratch-path>

See top-of-file header for the full stage/edit/validate/atomic-swap pattern
and the H33 hazard it prevents (docs/wiki/concurrent-em-hazards.md § H33).
EOF
}

# is_live_bash_matcher_hook <hook-path>
# Detection helper (offer, not a gate): greps hooks.json to check whether the
# named hook's basename appears inside a PreToolUse block whose matcher string
# contains "Bash". Returns 0 (true) if so, 1 otherwise. Never blocks the
# operator — `stage` only WARNs when this returns false-negative-shaped, since
# a hook not currently wired as a Bash-matcher is safe to edit directly, but
# the same discipline is still offered for consistency.
is_live_bash_matcher_hook() {
  local hook_path="$1"
  local hook_base
  hook_base="$(basename "$hook_path")"

  local hooks_json=""
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -f "${script_dir}/../hooks/hooks.json" ]]; then
    hooks_json="${script_dir}/../hooks/hooks.json"
  elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" && -f "${CLAUDE_PLUGIN_ROOT}/hooks/hooks.json" ]]; then
    hooks_json="${CLAUDE_PLUGIN_ROOT}/hooks/hooks.json"
  else
    return 1
  fi

  # Look for a PreToolUse entry whose matcher contains Bash and whose hook
  # command block references this hook's basename. This does a structured
  # JSON parse (python3 json.load + walk over hooks.PreToolUse entries) per
  # PreToolUse entry, not a text-proximity grep -- correctly handles multiple
  # separate {"matcher": "Bash", ...} array entries in hooks.json.
  # Review: code-reviewer -- comment previously described this as a "proximity
  # grep" but the implementation is a real JSON structural walk.
  python3 - "$hooks_json" "$hook_base" <<'PYEOF' 2>/dev/null
import json, sys
path, hook_base = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(path))
except Exception:
    sys.exit(1)
for event, entries in d.get("hooks", {}).items():
    if event != "PreToolUse":
        continue
    for entry in entries:
        matcher = entry.get("matcher", "")
        if "Bash" not in matcher:
            continue
        for h in entry.get("hooks", []):
            cmd = h.get("command", "")
            if hook_base in cmd:
                sys.exit(0)
sys.exit(1)
PYEOF
}

cmd_stage() {
  local hook_path="${1:?stage requires <hook-path>}"

  if [[ ! -f "$hook_path" ]]; then
    printf '%s: stage: no such file: %s\n' "$SCRIPT_NAME" "$hook_path" >&2
    exit 1
  fi

  local hook_dir
  hook_dir="$(cd "$(dirname "$hook_path")" && pwd)"
  local hook_base
  hook_base="$(basename "$hook_path")"
  local scratch_path
  scratch_path="${hook_dir}/.${hook_base}.edit-live-hook.$$.scratch"

  cp -p -- "$hook_path" "$scratch_path"

  if is_live_bash_matcher_hook "$hook_path"; then
    printf '%s: NOTE: %s is registered under a Bash-inclusive PreToolUse matcher.\n' "$SCRIPT_NAME" "$hook_base" >&2
    printf '  Editing the scratch copy below is safe -- it is NOT the live enforcement path.\n' >&2
    printf '  See docs/wiki/concurrent-em-hazards.md %s H33 before editing the live path directly.\n' '§' >&2
  fi

  printf 'Staged scratch copy: %s\n' "$scratch_path"
  printf 'Edit the scratch copy freely, then run:\n' >&2
  printf '  %s commit %s %s\n' "$SCRIPT_NAME" "$hook_path" "$scratch_path" >&2
}

cmd_commit() {
  local hook_path="${1:?commit requires <hook-path> <scratch-path>}"
  local scratch_path="${2:?commit requires <hook-path> <scratch-path>}"

  if [[ ! -f "$scratch_path" ]]; then
    printf '%s: commit: no such scratch file: %s\n' "$SCRIPT_NAME" "$scratch_path" >&2
    exit 1
  fi

  # DO NOT swap on a syntax-broken scratch file -- fail loud and leave the
  # live hook untouched. This is the entire point of the helper: a bad
  # intermediate must never become the live enforcement code.
  # Review: code-reviewer -- captured bash -n stderr into a variable via
  # command substitution instead of a predictable shared-/tmp path
  # (/tmp/edit-live-hook.$$.stderr), avoiding a symlink-race footgun class
  # that was inconsistent with this file's own same-directory scratch
  # discipline (see cmd_stage above).
  local syntax_err
  if ! syntax_err="$(bash -n "$scratch_path" 2>&1 >/dev/null)"; then
    printf '%s: commit: REFUSED -- scratch copy fails `bash -n` syntax check:\n' "$SCRIPT_NAME" >&2
    printf '%s\n' "$syntax_err" >&2
    printf '  Live hook %s was NOT modified. Fix %s and re-run commit.\n' "$hook_path" "$scratch_path" >&2
    exit 2
  fi

  local hook_dir scratch_dir
  hook_dir="$(cd "$(dirname "$hook_path")" && pwd)"
  scratch_dir="$(cd "$(dirname "$scratch_path")" && pwd)"
  if [[ "$hook_dir" != "$scratch_dir" ]]; then
    printf '%s: commit: WARNING -- scratch (%s) and live hook (%s) are on different\n' "$SCRIPT_NAME" "$scratch_dir" "$hook_dir" >&2
    printf '  directories; the swap below may not be an atomic rename on this filesystem.\n' >&2
  fi

  # Preserve the live file's mode (e.g. exec bit) across the swap.
  local live_mode
  live_mode="$(stat -f '%A' "$hook_path" 2>/dev/null || stat -c '%a' "$hook_path" 2>/dev/null || echo '')"
  if [[ -n "$live_mode" ]]; then
    chmod "$live_mode" "$scratch_path"
  fi

  mv -- "$scratch_path" "$hook_path"
  printf '%s: commit: OK -- %s swapped in atomically (syntax-valid).\n' "$SCRIPT_NAME" "$hook_path"
}

main() {
  if [[ $# -lt 1 ]]; then
    usage
    exit 1
  fi

  local subcommand="$1"
  shift

  case "$subcommand" in
    stage)
      cmd_stage "$@"
      ;;
    commit)
      cmd_commit "$@"
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
    *)
      printf '%s: unknown subcommand: %s\n' "$SCRIPT_NAME" "$subcommand" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
