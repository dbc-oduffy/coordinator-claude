#!/usr/bin/env bash
# Install the OSS publish-repo pre-commit exec-bit drift gate and illegal-path gate.
#
# Usage: install-publish-repo-precommit-hook.sh <EXPECTED_REPO_ROOT>
#
#   EXPECTED_REPO_ROOT — the canonical path of the OSS coordinator-claude
#   publish repo root, as captured by install.sh at install time via:
#   $(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
#   Passed as a positional argument so this script never hardcodes a
#   machine-specific path.
#
# Idempotent. Conditional: only installs when the running git repo's canonical
# root matches EXPECTED_REPO_ROOT. Repos that are NOT the expected publish
# target exit cleanly with no install.
#
# Foreign-hook handling: if .git/hooks/pre-commit already exists with content
# other than the coordinator exec-bit shim, print a one-line offer-shape
# message and continue — do not block install.sh.
#
# Upgrade-path handling: if the exec-bit gate is already installed but the
# illegal-path gate is absent (hook written before D4), the paths check is
# appended to the existing hook without regenerating it.
#
# BSD-portable: no grep -P, no realpath, no sed -i, no find -printf.
#
# Spec backlinks:
#   docs/plans/2026-06-11-exec-bit-install-surface-completion.md § Chunk 5
#   docs/plans/2026-06-30-cross-platform-file-naming-helper.md § Wave D4

set -euo pipefail

canon() {
  # Review: reviewer — return empty string on cd failure so a failed canon never
  # matches a non-empty expected path (safe skip rather than masked edge case).
  [ -n "$1" ] || { echo ""; return; }
  (cd "$1" 2>/dev/null && pwd -P) || { echo ""; }
}

# ------------------------------------------------------------------
# Argument check
# ------------------------------------------------------------------
if [ $# -lt 1 ] || [ -z "$1" ]; then
  echo "install-publish-repo-precommit-hook: missing EXPECTED_REPO_ROOT argument — skipping." >&2
  exit 0
fi
EXPECTED_REPO_ROOT="$1"
CANONICAL_EXPECTED="$(canon "$EXPECTED_REPO_ROOT")"

# ------------------------------------------------------------------
# Git-repo guard
# ------------------------------------------------------------------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "install-publish-repo-precommit-hook: not in a git repo — skipping." >&2
  exit 0
}
[ -n "$REPO_ROOT" ] || {
  echo "install-publish-repo-precommit-hook: empty repo root — skipping." >&2
  exit 0
}

# ------------------------------------------------------------------
# Identity guard: only install inside the expected OSS publish repo.
# Canonicalized path compare — handles symlinks, /c/ vs C:\ Git-Bash.
# ------------------------------------------------------------------
if [ "$(canon "$REPO_ROOT")" != "$CANONICAL_EXPECTED" ]; then
  echo "install-publish-repo-precommit-hook: not the expected OSS repo ($REPO_ROOT) — skipping." >&2
  exit 0
fi

HOOK_PATH="$REPO_ROOT/.git/hooks/pre-commit"
# Marker string that the exec-bit shim body embeds.
GATE_MARKER="coordinator-oss-exec-bit-gate"
# D4: illegal-path backstop. Path resolved at hook-fire time from $_cur (the
# publish repo root), using the same coordinator/ prefix as the exec-bit test.
# Spec backlink: docs/plans/2026-06-30-cross-platform-file-naming-helper.md § Wave D4
PATHS_MARKER="check-no-illegal-paths"

# ------------------------------------------------------------------
# Idempotency: paths check present → both gates wired, fully installed.
# (Paths check is the newest addition; its marker's presence means exec-bit
# is also wired — the upgrade path and fresh-install always pair them.)
# ------------------------------------------------------------------
if [ -f "$HOOK_PATH" ] && grep -q "$PATHS_MARKER" "$HOOK_PATH" 2>/dev/null; then
  echo "install-publish-repo-precommit-hook: gates already installed at $HOOK_PATH — no-op." >&2
  exit 0
fi

# ------------------------------------------------------------------
# Upgrade path: exec-bit gate present but illegal-path gate absent
# (hook written before D4). Append the paths check only.
# ------------------------------------------------------------------
if [ -f "$HOOK_PATH" ] && grep -q "$GATE_MARKER" "$HOOK_PATH" 2>/dev/null; then
  cat >> "$HOOK_PATH" <<APPEND

# === OSS publish-repo illegal-path gate (appended by install-publish-repo-precommit-hook.sh) ===
# check-no-illegal-paths: catches commits with NTFS-illegal filenames.
# Self-healing: absent helper exits 0 silently.
_paths_check="\$_cur/coordinator/bin/check-no-illegal-paths.sh"
if command -v bash >/dev/null 2>&1 && [ -x "\$_paths_check" ]; then bash "\$_paths_check" || exit \$?; fi
APPEND
  echo "install-publish-repo-precommit-hook: appended illegal-path gate to existing $HOOK_PATH." >&2
  exit 0
fi

# ------------------------------------------------------------------
# Foreign-hook handling: existing hook, not the coordinator shim.
# Offer-shape: print and continue — do not block install.
# ------------------------------------------------------------------
if [ -f "$HOOK_PATH" ]; then
  echo "install-publish-repo-precommit-hook: an existing pre-commit hook is in place; the coordinator guards were NOT installed — install manually by running: bash coordinator/bin/install-publish-repo-precommit-hook.sh \"\$(pwd)\"" >&2
  exit 0
fi

# ------------------------------------------------------------------
# Fresh-install path: write the canonical OSS shim.
#
# The shim is self-contained: it bakes in the canonical OSS repo root at
# install time, re-discovers the repo root at hook-fire time, and compares.
# If the comparison fails (submodule, different checkout) it exits 0 silently.
# This avoids relying on the meta-repo coordinator-precommit-exec-bit-check
# identity guard, which checks for $HOME/.claude instead of the OSS root.
#
# The GATE_MARKER string ("coordinator-oss-exec-bit-gate") is embedded in the
# comment on the first line of the shim so that the idempotency grep above
# can detect a previously-installed shim.
# ------------------------------------------------------------------
cat > "$HOOK_PATH" <<HOOK
#!/bin/sh
# coordinator-oss-exec-bit-gate — OSS publish-repo pre-commit gates.
# 1. exec-bit drift gate (coordinator-oss-exec-bit-gate)
# 2. illegal-path gate (check-no-illegal-paths) — D4
# Identity-scoped to this repo (canonical path baked in at install time).
# Exits 0 silently when run outside the expected repo.
# Both checks are self-healing: absent helpers exit 0 silently.
#
# Spec backlinks:
#   docs/plans/2026-06-11-exec-bit-install-surface-completion.md § Chunk 5
#   docs/plans/2026-06-30-cross-platform-file-naming-helper.md § Wave D4
# POSIX-sh + bash guard — GitHub Desktop's MinGit lacks bash; skip cleanly there.
command -v bash >/dev/null 2>&1 || exit 0
OSS_REPO_ROOT="${CANONICAL_EXPECTED}"
_canon() {
  # Review: reviewer — return empty string on cd failure so a failed _canon never
  # matches a non-empty expected path (safe skip rather than masked edge case).
  [ -n "\$1" ] || { echo ""; return; }
  (cd "\$1" 2>/dev/null && pwd -P) || { echo ""; }
}
_cur="\$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -n "\$_cur" ] || exit 0
if [ "\$(_canon "\$_cur")" != "\$(_canon "\$OSS_REPO_ROOT")" ]; then
  exit 0
fi
if [ "\${COORDINATOR_OVERRIDE_PRECOMMIT_EXEC_BIT:-}" = "1" ]; then
  echo "pre-commit: exec-bit check skipped (COORDINATOR_OVERRIDE_PRECOMMIT_EXEC_BIT=1)." >&2
  exit 0
fi
if ! command -v node >/dev/null 2>&1; then
  exit 0
fi
EXEC_BIT_TEST="\$_cur/coordinator/tests/plugin-ecosystem/exec-bit.test.js"
if [ ! -f "\$EXEC_BIT_TEST" ]; then
  exit 0
fi
if ! node --test "\$EXEC_BIT_TEST" >&2 2>&1; then # verify-no-console-flash: allow — pre-commit hook, runs on explicit git commit only
  # Review: reviewer — >&2 first redirects stdout to stderr, then 2>&1 merges
  # remaining stderr to the same fd; the prior order 2>&1 >&2 was wrong: it
  # duplicated stderr to current stdout (tty) before redirecting stdout to stderr.
  echo "" >&2
  echo "pre-commit: exec-bit drift detected (above). Fix and re-commit." >&2
  echo "Override (PM-authorized only): COORDINATOR_OVERRIDE_PRECOMMIT_EXEC_BIT=1 git commit ..." >&2
  exit 1
fi

# Gate 2: NTFS-illegal path check — catches commits with illegal filenames.
# check-no-illegal-paths
_paths_check="\$_cur/coordinator/bin/check-no-illegal-paths.sh"
if [ -x "\$_paths_check" ]; then bash "\$_paths_check" || exit \$?; fi
HOOK
chmod +x "$HOOK_PATH"
echo "install-publish-repo-precommit-hook: installed $HOOK_PATH." >&2
