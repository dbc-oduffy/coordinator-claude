#!/usr/bin/env bash
# coordinator-ceremony-hook.sh <canonical-ceremony-name>
#
# Generic per-repo post-ceremony command hook. Any of the four cadence
# ceremonies (/workday-start, /workday-complete, /workweek-start,
# /workweek-complete) calls this shared helper at its terminal step so a
# consumer repo can register its own opt-in advisory command (e.g. "publish
# settled end-of-day state to an external store or dashboard") without a
# bespoke terminal step per
# ceremony. One shared helper, not four near-identical bodies — the
# parallel-surface footgun this design deliberately avoids.
#
# Spec backlink: docs/plans/2026-07-08-ceremony-post-command-hook-seam.md
#   § "The seam (contract pinned in C1)", § "Helper shape (C1)"
#
# Contract:
#   Arg 1 — canonical dashed ceremony name (workday-start | workday-complete |
#           workweek-start | workweek-complete). Dashes map to underscores and
#           `_post_command` is appended to derive the coordinator.local.md key
#           (e.g. workday-complete -> workday_complete_post_command).
#   Key lookup — cs_read_local_md_key <repo_root> <key> (public resolver from
#           coordinator-resolve-validation-cmd.sh, R1-promoted for this
#           cross-file consumer). Empty/absent key -> silent no-op, exit 0,
#           NO output (the overwhelming common case; zero ceremony noise for
#           repos that declare nothing).
#   Repo root — git rev-parse --show-toplevel, falling back to $PWD.
#   Execution — the resolved command runs in a subshell cd-ed to repo_root via
#           `bash -c "$cmd"` (child-shell sandbox — isolates child variable
#           mutations from this shell's namespace; does not restrict what the
#           configured command executes).
#   Redaction — the command is NEVER echoed raw. `_cs_redact_for_diag` redacts
#           it in the summary line and any WARN; `_cs_metachar_warn` fires a
#           light advisory tripwire on shell-metacharacter shapes. Same
#           discipline `cs_resolve_fast_test_cmd` already applies to
#           `fast_test_cmd:`.
#
# Output contract (stdout):
#   Exactly one line when a command was configured+run:
#     Post-<ceremony> hook: ran <redacted-cmd> (exit <rc>)
#   Empty stdout when no command was configured (opt-in no-op). Consumed by
#   the calling ceremony's final-summary step via the pinned call-site idiom:
#     _HOOK_OUT="$(bash "$_cc_root/bin/coordinator-ceremony-hook.sh" <name>)" \
#       || echo "[<ceremony>] WARN: ceremony-hook exited non-zero (non-blocking)" >&2
#     if [ -n "$_HOOK_OUT" ]; then printf '%s\n' "$_HOOK_OUT"; fi
#   All human-readable detail (the command's own stdout/stderr, WARN lines)
#   streams to stderr uncaptured — never mixed into the one-line stdout
#   contract above.
#
# Exit codes: ALWAYS 0. A non-zero command exit, a missing command, an
#   unknown ceremony arg, or a resolver-lib sourcing failure all WARN to
#   stderr and still exit 0 — the hook must NEVER fail or block the calling
#   ceremony (the single most important invariant of this design). This
#   promise holds independent of the call-site's own `|| echo WARN` guard —
#   that guard is a second, separate layer (belt-and-suspenders), not a
#   substitute for this script's own unconditional exit 0.
#
# Security posture: the command is sourced ONLY from committed repo config
# (coordinator.local.md) — the repo owner's own declared command, running
# with full agent-shell privileges. This is NOT a shared-branch-baton
# injection surface (coordinator.local.md is repo-owner-authored config, not
# an inbound artifact from an untrusted sender). Unlike fast_test_cmd, there
# is deliberately NO env-var override (COORDINATOR_*_POST_COMMAND) — a
# per-repo ceremony command has no legitimate env-var source and an override
# would be a subprocess-injectable surface.
#
# Negative-spec: do NOT add a COORDINATOR_*_POST_COMMAND env override, do NOT
# read the command from a memo/handoff/work-branch baton, and do NOT let a
# resolver-lib sourcing failure abort this script before it reaches its own
# `exit 0` — all three are explicit anti-scope items in the plan.

set -eu

# Require bash >= 4 (coordinator baseline — DR-148).
if (( BASH_VERSINFO[0] < 4 )); then
  echo "[coordinator-ceremony-hook] ERROR: bash >= 4 required (found ${BASH_VERSION}). On macOS: brew install bash" >&2
  exit 1
fi

PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_LIB="${PLUGIN_ROOT}/lib/coordinator-resolve-validation-cmd.sh"

# Guarded source — a sourcing failure (path drift, partial file) must NOT
# leave cs_read_local_md_key unbound and abort this script with "command not
# found" before it reaches its own exit 0. WARN and exit 0 instead.
# shellcheck source=/dev/null
source "$_LIB" 2>/dev/null \
  || { echo "[coordinator-ceremony-hook] WARN: resolver lib unavailable at ${_LIB} — skipping hook" >&2; exit 0; }

# Belt-and-suspenders: even a successful `source` could, in principle, load a
# stale/partial file missing the function. Confirm before calling — the
# helper's "always exits 0" promise must hold independent of any call-site
# guard.
declare -F cs_read_local_md_key >/dev/null 2>&1 || {
  echo "[coordinator-ceremony-hook] WARN: cs_read_local_md_key not defined after sourcing ${_LIB} — skipping hook" >&2
  exit 0
}

ceremony="${1:-}"

case "$ceremony" in
  workday-start|workday-complete|workweek-start|workweek-complete)
    ;;
  *)
    echo "[coordinator-ceremony-hook] WARN: unknown ceremony '${ceremony}' — expected one of workday-start, workday-complete, workweek-start, workweek-complete" >&2
    exit 0
    ;;
esac

key="$(printf '%s' "$ceremony" | tr '-' '_')_post_command"
repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

cmd="$(cs_read_local_md_key "$repo_root" "$key")"

# Opt-in: key absent or empty -> silent no-op, no output.
[[ -z "$cmd" ]] && exit 0

_cs_metachar_warn "$cmd" "ceremony-hook:$ceremony" "coordinator-ceremony-hook"
redacted="$(_cs_redact_for_diag "$cmd")"

echo "[coordinator-ceremony-hook] ${ceremony}: running: ${redacted}" >&2

set +e
( cd "$repo_root" && bash -c "$cmd" ) >&2
rc=$?
set -e

if [[ $rc -ne 0 ]]; then
  echo "[coordinator-ceremony-hook] WARN: ${ceremony} post-command exited ${rc} (non-fatal): ${redacted}" >&2
fi

echo "Post-${ceremony} hook: ran ${redacted} (exit ${rc})"
exit 0
