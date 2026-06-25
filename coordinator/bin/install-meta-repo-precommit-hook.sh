#!/usr/bin/env bash
# Install the meta-repo pre-commit exec-bit drift gate.
#
# Idempotent. Conditional: only installs when the resolved repo root is the
# meta-repo (~/.claude itself, identified by canonicalized path compare). Pass
# "$HOME/.claude" as the first arg to make the install cwd-independent; absent the
# arg the root is derived from cwd. Consumer repos are exited cleanly with no
# install — the gate's helper is a no-op outside the meta-repo anyway, so
# installing there would be inert noise.
#
# If a pre-commit hook already exists with content other than this gate
# (custom hooks, Git LFS prefix, etc.), the installer appends the gate
# call after the existing block rather than clobbering it.
#
# Spec backlink: cross-repo/inbox/2026-06-08-exec-bit-drift-runtime-tripwire-tests.md

set -euo pipefail

canon() {
  # Return empty string on cd failure (parity with install-publish-repo-precommit-hook.sh)
  # so a failed canon never matches a non-empty expected path — a non-existent target
  # is a guaranteed skip, never a false identity match against $HOME/.claude.
  [ -n "$1" ] || { echo ""; return; }
  (cd "$1" 2>/dev/null && pwd -P) || { echo ""; }
}

# Resolve coordinator content root via the portable resolver (CLAUDE_PLUGIN_ROOT →
# COORDINATOR_ROOT → registry clone → versioned cache → flat layout).
_rcc_resolver="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lib/resolve-coordinator-clone.sh"
if [[ -f "$_rcc_resolver" ]]; then
    # shellcheck source=../lib/resolve-coordinator-clone.sh
    source "$_rcc_resolver" 2>/dev/null || true
fi
if [[ -z "${COORDINATOR_CONTENT_ROOT:-}" ]]; then
    COORDINATOR_CONTENT_ROOT="${HOME}/.claude/plugins/coordinator-claude/coordinator"
fi

# Optional positional arg: an explicit target directory to resolve the repo root
# from (parity with install-publish-repo-precommit-hook.sh's EXPECTED_REPO_ROOT).
# Without it the script derives the root from cwd — which silently no-ops when the
# caller's cwd is not the meta-repo (the 2026-06-24 gap: /coordinator:install and
# /repo-setup invoke this with cwd = the operator's environment or a consumer
# project, so the meta-repo gate was never installed; only a pickup whose cwd
# happened to be ~/.claude installed it). Passing "$HOME/.claude" makes the install
# cwd-independent. Backward compatible: absent arg = old cwd-derived behavior.
_target="${1:-.}"
# `git -C "$_target"` RESOLVES the repo root from the (caller-supplied or cwd) target —
# it is an override, not a cwd-relative read. A caller passing an arbitrary path can only
# steer which .git is resolved; the canon() identity guard below (REPO_ROOT == $HOME/.claude)
# is the load-bearing safety control that rejects any non-meta-repo target. Do not refactor
# the guard away on the assumption the resolution strategy alone constrains the install.
REPO_ROOT="$(git -C "$_target" rev-parse --show-toplevel 2>/dev/null)" || {
  echo "install-meta-repo-precommit-hook: $_target not in a git repo — skipping." >&2
  exit 0
}
[ -n "$REPO_ROOT" ] || {
  echo "install-meta-repo-precommit-hook: empty repo root — skipping." >&2
  exit 0
}

META_REPO="$HOME/.claude"
if [ "$(canon "$REPO_ROOT")" != "$(canon "$META_REPO")" ]; then
  echo "install-meta-repo-precommit-hook: not the meta-repo ($REPO_ROOT) — skipping." >&2
  exit 0
fi

HOOK_PATH="$REPO_ROOT/.git/hooks/pre-commit"
# Review: patrik F5 — embed the STABLE FLAT literal path in the generated hook rather than
# the resolved (possibly cache-versioned) COORDINATOR_CONTENT_ROOT. The meta-repo install
# context guarantees a flat/source_is_live layout; a stable embed survives version bumps
# without the idempotency-guard (GATE_MARKER grep) silently trapping a rotted cache path.
HELPER_PATH="$HOME/.claude/plugins/coordinator/bin/coordinator-precommit-exec-bit-check"
GATE_MARKER="coordinator-precommit-exec-bit-check"

# Idempotency: already-installed (any shape that references the helper).
if [ -f "$HOOK_PATH" ] && grep -q "$GATE_MARKER" "$HOOK_PATH" 2>/dev/null; then
  echo "install-meta-repo-precommit-hook: gate already installed at $HOOK_PATH — no-op." >&2
  exit 0
fi

# Fresh-install path: write the canonical shim.
# Note: unquoted HOOK delimiter — $HELPER_PATH is expanded at install time to the
# stable flat literal set above (meta-repo context guarantees flat/source_is_live layout).
# Self-healing comment is preserved: helper absence is a no-op via exit 0.
if [ ! -f "$HOOK_PATH" ]; then
  cat > "$HOOK_PATH" <<HOOK
#!/bin/bash
# Meta-repo exec-bit drift gate — fires before drift can land.
# Delegates to coordinator-precommit-exec-bit-check (no-op outside ~/.claude).
# Self-healing if helper is absent (plugin path changes, fresh clone).
_helper="$HELPER_PATH"
[ -x "\$_helper" ] && exec "\$_helper"
exit 0
HOOK
  chmod +x "$HOOK_PATH"
  echo "install-meta-repo-precommit-hook: installed $HOOK_PATH." >&2
  exit 0
fi

# Append path: existing hook lacks the gate marker. Append a backgrounded
# invocation so the existing hook's exit code remains authoritative.
cat >> "$HOOK_PATH" <<APPEND

# === Meta-repo exec-bit drift gate (appended by install-meta-repo-precommit-hook.sh) ===
_helper="$HELPER_PATH"
[ -x "\$_helper" ] && "\$_helper"
APPEND
echo "install-meta-repo-precommit-hook: appended gate to existing $HOOK_PATH." >&2
