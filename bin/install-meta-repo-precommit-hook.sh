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
# Review: the Staff Engineer F5 — embed the STABLE FLAT literal path in the generated hook rather than
# the resolved (possibly cache-versioned) COORDINATOR_CONTENT_ROOT. The meta-repo install
# context guarantees a flat/source_is_live layout; a stable embed survives version bumps
# without the idempotency-guard (GATE_MARKER grep) silently trapping a rotted cache path.
HELPER_PATH="$HOME/.claude/plugins/coordinator/bin/coordinator-precommit-exec-bit-check"
GATE_MARKER="coordinator-precommit-exec-bit-check"

# D2: illegal-path backstop — stable flat path (same reasoning as HELPER_PATH above).
# Spec backlink: docs/plans/2026-06-30-cross-platform-file-naming-helper.md § Wave D2
PATHS_CHECK_PATH="$HOME/.claude/plugins/coordinator/bin/check-no-illegal-paths.sh"
PATHS_MARKER="check-no-illegal-paths"

# Idempotency: paths check already present → fully installed, no-op.
# (Paths check is the newest addition; its marker's presence means both checks are wired.)
if [ -f "$HOOK_PATH" ] && grep -q "$PATHS_MARKER" "$HOOK_PATH" 2>/dev/null; then
  echo "install-meta-repo-precommit-hook: gate already installed at $HOOK_PATH — no-op." >&2
  exit 0
fi

# Upgrade path: exec-bit check already present but no paths check → append paths check only.
# Handles hooks installed before D2 without re-generating the whole hook.
if [ -f "$HOOK_PATH" ] && grep -q "$GATE_MARKER" "$HOOK_PATH" 2>/dev/null; then
  # Atomic append: copy to temp, append, mv so a concurrent git-commit never reads a torn hook.
  cp "$HOOK_PATH" "$HOOK_PATH.tmp.$$"
  cat >> "$HOOK_PATH.tmp.$$" <<APPEND

# === Meta-repo illegal-path gate (appended by install-meta-repo-precommit-hook.sh) ===
# check-no-illegal-paths: catches human git-mv with NTFS-illegal chars the PreToolUse hook cannot see.
_paths_check="$PATHS_CHECK_PATH"
if command -v bash >/dev/null 2>&1 && [ -x "\$_paths_check" ]; then bash "\$_paths_check" || exit \$?; fi
APPEND
  mv -f "$HOOK_PATH.tmp.$$" "$HOOK_PATH"
  echo "install-meta-repo-precommit-hook: appended illegal-path gate to existing $HOOK_PATH." >&2
  exit 0
fi

# Fresh-install path: write the canonical shim with BOTH checks.
# Note: unquoted HOOK delimiter — $HELPER_PATH/$PATHS_CHECK_PATH expanded at install time
# to stable flat literals (meta-repo context guarantees flat/source_is_live layout).
# Self-healing: absent helpers are no-ops; the hook always exits 0 if helpers are missing.
if [ ! -f "$HOOK_PATH" ]; then
  # Atomic write: cat to temp then mv so a concurrent git-commit never reads a torn hook.
  cat > "$HOOK_PATH.tmp.$$" <<HOOK
#!/bin/sh
# Meta-repo pre-commit gates — fire before drift can land.
# 1. exec-bit drift gate (coordinator-precommit-exec-bit-check)
# 2. illegal-path gate (check-no-illegal-paths) — D2
# Both are self-healing if the helper is absent (plugin path changes, fresh clone).
# POSIX-sh + bash guard: GitHub Desktop's MinGit lacks bash; skip cleanly there.
command -v bash >/dev/null 2>&1 || exit 0

# Gate 1: exec-bit drift
_helper="$HELPER_PATH"
if [ -x "\$_helper" ]; then bash "\$_helper" || exit \$?; fi

# Gate 2: NTFS-illegal path check — catches human git mv with illegal chars
# check-no-illegal-paths
_paths_check="$PATHS_CHECK_PATH"
if [ -x "\$_paths_check" ]; then bash "\$_paths_check" || exit \$?; fi

exit 0
HOOK
  mv -f "$HOOK_PATH.tmp.$$" "$HOOK_PATH"
  chmod +x "$HOOK_PATH"
  echo "install-meta-repo-precommit-hook: installed $HOOK_PATH." >&2
  exit 0
fi

# Append path: existing non-coordinator hook lacks both markers.
# Append BOTH checks so the hook is fully wired in one pass.
# Atomic append: copy to temp, append, mv so a concurrent git-commit never reads a torn hook.
cp "$HOOK_PATH" "$HOOK_PATH.tmp.$$"
cat >> "$HOOK_PATH.tmp.$$" <<APPEND

# === Meta-repo exec-bit drift gate (appended by install-meta-repo-precommit-hook.sh) ===
_helper="$HELPER_PATH"
if command -v bash >/dev/null 2>&1 && [ -x "\$_helper" ]; then bash "\$_helper" || exit \$?; fi
# === Meta-repo illegal-path gate (appended by install-meta-repo-precommit-hook.sh) ===
# check-no-illegal-paths: catches human git mv with NTFS-illegal chars the PreToolUse hook cannot see.
_paths_check="$PATHS_CHECK_PATH"
if command -v bash >/dev/null 2>&1 && [ -x "\$_paths_check" ]; then bash "\$_paths_check" || exit \$?; fi
APPEND
mv -f "$HOOK_PATH.tmp.$$" "$HOOK_PATH"
echo "install-meta-repo-precommit-hook: appended gates to existing $HOOK_PATH." >&2
