#!/usr/bin/env bash
# seed-skill-overrides.sh — install-health drop-in: seed bundled-skill skillOverrides.
#
# Why this exists:
#   The coordinator ships bundled skills (e.g. /plan, /review) whose command names
#   must be registered in Claude Code's settings.json as skillOverrides so the harness
#   can route them. Registering manually is error-prone; this drop-in ensures the seed
#   is applied idempotently on every install/re-install via install-health-run.sh.
#
# Deep-research override:
#   Post-merge (coordinator consolidation Wave C4), deep-research is ALWAYS bundled
#   inside the coordinator plugin. The old standalone detection (checking for
#   ~/.claude/plugins/deep-research/commands/web.md) can never return true — that path
#   no longer exists. The "deep-research": "off" skillOverride is now always seeded
#   unconditionally to suppress the Claude Code built-in /deep-research skill in favour
#   of /coordinator:research.
# Review: code-reviewer — F2: removed dead presence-detection; always pass --with-deep-research
#
# CHECK_ONLY mode:
#   When the CHECK_ONLY environment variable is non-empty (exported by
#   coordinator:install --check-only at Step 1b), passes --check-only to the helper
#   so no writes are performed — only a delta report is printed.
#
# Idempotent: safe to run repeatedly. The Python helper is idempotent internally
# (it writes only when the current settings differ from the target state).
#
# Spec backlink: parallel chunk in the install-health drop-in plan (2026-06-27);
# contract pinned to seed-skill-overrides.py helper interface.

set -euo pipefail

# ---------------------------------------------------------------------------
# Root resolution — prefer CLAUDE_PLUGIN_ROOT (set by skill/command invocations)
# over BASH_SOURCE derivation. This script lives at bin/install-health/, so the
# plugin root is two levels up from its own directory.
# ---------------------------------------------------------------------------
_plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
# shellcheck source=../../lib/coordinator-trusted-root-guard.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../lib" && pwd)/coordinator-trusted-root-guard.sh"
coordinator_trusted_root_guard --mode=fail-loud --root="$_plugin_root" --site="$0"

# ---------------------------------------------------------------------------
# Helper presence check — degrade gracefully if the helper is absent (e.g. a
# partial publish or a future refactor that moved it). Do NOT fail the whole
# orchestrator.
# ---------------------------------------------------------------------------
_helper="${_plugin_root}/bin/seed-skill-overrides.py"

if [[ ! -f "$_helper" ]]; then
  echo "[seed-skill-overrides] WARNING: helper not found at ${_helper}; skipping" >&2
  exit 0
fi

# ---------------------------------------------------------------------------
# Build arg list safely for bash 3.2 (no declare -A, no mapfile).
# The "${args[@]+"${args[@]}"}" form is POSIX and avoids "unbound variable"
# under set -u when the array is empty.
# ---------------------------------------------------------------------------
args=()

if [[ -n "${CHECK_ONLY:-}" ]]; then
  args+=(--check-only)
fi

# Deep-research is always bundled in coordinator post-C4 — always seed the override.
args+=(--with-deep-research)

# ---------------------------------------------------------------------------
# Invoke the helper. Surface its stdout directly (the helper prints a status
# line describing what it did or would do). Any non-zero exit propagates to
# the orchestrator, which marks this drop-in FAIL and continues the loop.
# ---------------------------------------------------------------------------
python3 "$_helper" "${args[@]+"${args[@]}"}"
