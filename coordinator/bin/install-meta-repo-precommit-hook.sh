#!/usr/bin/env bash
# Install the meta-repo pre-commit exec-bit drift gate.
#
# Idempotent. Conditional: only installs when cwd is the meta-repo
# (~/.claude itself, identified by canonicalized path compare). Consumer
# repos are exited cleanly with no install — the gate's helper is a no-op
# outside the meta-repo anyway, so installing there would be inert noise.
#
# If a pre-commit hook already exists with content other than this gate
# (custom hooks, Git LFS prefix, etc.), the installer appends the gate
# call after the existing block rather than clobbering it.
#
# Spec backlink: cross-repo/inbox/2026-06-08-exec-bit-drift-runtime-tripwire-tests.md

set -euo pipefail

canon() {
  [ -n "$1" ] || { echo ""; return; }
  (cd "$1" 2>/dev/null && pwd -P) || echo "$1"
}

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "install-meta-repo-precommit-hook: not in a git repo — skipping." >&2
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
HELPER_PATH="$HOME/.claude/plugins/coordinator/bin/coordinator-precommit-exec-bit-check"
GATE_MARKER="coordinator-precommit-exec-bit-check"

# Idempotency: already-installed (any shape that references the helper).
if [ -f "$HOOK_PATH" ] && grep -q "$GATE_MARKER" "$HOOK_PATH" 2>/dev/null; then
  echo "install-meta-repo-precommit-hook: gate already installed at $HOOK_PATH — no-op." >&2
  exit 0
fi

# Fresh-install path: write the canonical shim.
if [ ! -f "$HOOK_PATH" ]; then
  cat > "$HOOK_PATH" <<'HOOK'
#!/bin/bash
# Meta-repo exec-bit drift gate — fires before drift can land.
# Delegates to coordinator-precommit-exec-bit-check (no-op outside ~/.claude).
# Self-healing if helper is absent (plugin path changes, fresh clone).
_helper="$HOME/.claude/plugins/coordinator/bin/coordinator-precommit-exec-bit-check"
[ -x "$_helper" ] && exec "$_helper"
exit 0
HOOK
  chmod +x "$HOOK_PATH"
  echo "install-meta-repo-precommit-hook: installed $HOOK_PATH." >&2
  exit 0
fi

# Append path: existing hook lacks the gate marker. Append a backgrounded
# invocation so the existing hook's exit code remains authoritative.
cat >> "$HOOK_PATH" <<'APPEND'

# === Meta-repo exec-bit drift gate (appended by install-meta-repo-precommit-hook.sh) ===
_helper="$HOME/.claude/plugins/coordinator/bin/coordinator-precommit-exec-bit-check"
[ -x "$_helper" ] && "$_helper"
APPEND
echo "install-meta-repo-precommit-hook: appended gate to existing $HOOK_PATH." >&2
