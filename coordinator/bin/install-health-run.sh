#!/usr/bin/env bash
# install-health-run.sh — orchestrator for drop-in install-health scripts.
#
# Why this exists:
#   The /install command used to list every mechanical setup/health script as
#   its own inline bash block in commands/install.md. Adding a new one meant a
#   doc edit per script — an anti-pattern the PM called out (2026-06-16). This
#   orchestrator collapses that surface: it iterates bin/install-health/*.sh in
#   stable order and runs each one. Adding a new health script is a directory
#   drop, not a doc edit.
#
# Contract for scripts in bin/install-health/:
#   - Self-gate on OS (or any other precondition) at the top.
#   - Exit 0 silently when the gate fails — never error on a non-applicable
#     platform.
#   - Be idempotent: safe to run on every install / re-install.
#   - Source libs (e.g. lib/resolve-python.sh) via a CLAUDE_PLUGIN_ROOT-
#     respecting derivation.
#   - Scripts are invoked as `bash "<script>"`, so the execute bit is NOT
#     required for the orchestrator to run them (a dropped script runs even
#     without chmod +x — deliberate drop-in robustness). Setting +x is still
#     recommended for consistency with the rest of bin/ and for direct invocation.
#
# Orchestrator behavior:
#   - Iterate bin/install-health/*.sh in lexicographic order.
#   - Invoke each via `bash` (not source — keep failure isolation).
#   - On a non-zero exit, emit `[install-health] FAIL: <script> exit=<rc>` and
#     CONTINUE the loop. Partial install completeness beats total bail.
#   - Aggregate non-zero exits; the orchestrator's own exit code is non-zero iff
#     any sub-script failed.
#   - Silence on success: sub-scripts already no-op-silently on the wrong OS, so
#     a clean run produces no orchestrator chatter.
#
# Idempotent: safe to run repeatedly (delegates idempotency to sub-scripts).
#
# Run: bash "${CLAUDE_PLUGIN_ROOT}/bin/install-health-run.sh"

set -uo pipefail  # no -e: deliberate — the loop must continue past sub-script failures.

# Prefer CLAUDE_PLUGIN_ROOT (set by skill/command invocations) over BASH_SOURCE
# derivation. This script lives at bin/, so the plugin root is one level up.
_plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
_health_dir="${_plugin_root}/bin/install-health"

# Empty/absent dir is a valid state (no health scripts to run) — exit 0.
if [[ ! -d "$_health_dir" ]]; then
  exit 0
fi

_failures=0

# Lexicographic iteration. The nullglob guard makes the glob expand to nothing
# (rather than the literal pattern) when the dir is empty. The EXIT trap restores
# nullglob even if a future caller `source`s this script (the explicit restore at
# the end of the loop is the idiomatic path; the trap is the backstop).
trap 'shopt -u nullglob' EXIT
shopt -s nullglob
for _script in "$_health_dir"/*.sh; do
  rc=0
  bash "$_script" || rc=$?
  if [[ "$rc" -ne 0 ]]; then
    echo "[install-health] FAIL: $(basename "$_script") exit=${rc}" >&2
    _failures=$((_failures + 1))
  fi
done
shopt -u nullglob

if [[ "$_failures" -gt 0 ]]; then
  echo "[install-health] ${_failures} health script(s) failed; install is incomplete." >&2
  exit 1
fi

exit 0
