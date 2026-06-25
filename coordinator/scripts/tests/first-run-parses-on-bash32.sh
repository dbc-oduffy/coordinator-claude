#!/usr/bin/env bash
# scripts/tests/first-run-parses-on-bash32.sh — AC2 producer for first-run.sh.
#
# Purpose: verify that scripts/first-run.sh parses cleanly under stock macOS
# /bin/bash (bash 3.2). Uses /bin/bash explicitly — NOT bare `bash`, which
# may resolve to a Homebrew bash>=4 on the runner.
#
# Exit: 0 if parse is clean, non-zero with a message if not.
# Non-authoritative note: if /bin/bash on this runner happens to be >=4,
# the test still runs but prints a one-line advisory. The test is only
# authoritative when /bin/bash is the stock macOS 3.2 build.
#
# Spec backlink: docs/plans/2026-06-23-first-run-entrypoint-c1a-skeleton.md § AC2

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$SCRIPT_DIR/../first-run.sh"

# Confirm the target exists.
if [ ! -f "$TARGET" ]; then
  printf 'ERROR: target script not found: %s\n' "$TARGET" >&2
  exit 1
fi

# Resolve absolute path (portable: cd/pwd; no realpath needed).
TARGET="$(cd "$(dirname "$TARGET")" && pwd)/$(basename "$TARGET")"

# Check /bin/bash version — advisory only, not a gate.
BASH_BIN=/bin/bash
BASH_VER="$("$BASH_BIN" --version 2>&1 | head -1 || true)"
BASH_MAJOR="$("$BASH_BIN" -c 'printf "%s" "${BASH_VERSINFO[0]}"' 2>/dev/null || printf '0')"

# Review: F7 — clarify advisory: exit stays 0 (gate must not red on Linux CI where
# /bin/bash is 4+). The test is ONLY authoritative on stock macOS where /bin/bash == 3.2.
if [ "$BASH_MAJOR" -ge 4 ] 2>/dev/null; then
  printf '[advisory] /bin/bash on this runner is version %s (>= 4).\n' "$BASH_MAJOR"
  printf '  This test is NON-AUTHORITATIVE on this runner — a >=4 parser accepts all bash-4\n'
  printf '  syntax, so parse-clean here does NOT confirm 3.2 compatibility.\n'
  printf '  Authoritative result: run on stock macOS where /bin/bash is the 3.2 system shell.\n'
  printf '  See plan AC2 note: docs/plans/2026-06-23-new-machine-clone-lands-correctly.md § AC2\n'
fi

# Run parse check.
printf 'Running: %s -n %s\n' "$BASH_BIN" "$TARGET"
if "$BASH_BIN" -n "$TARGET" 2>&1; then
  printf 'PASS: first-run.sh parses cleanly under %s\n' "$BASH_VER"
  exit 0
else
  printf 'FAIL: first-run.sh has parse errors under %s\n' "$BASH_VER" >&2
  exit 1
fi
