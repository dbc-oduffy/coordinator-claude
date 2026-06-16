#!/usr/bin/env bash
# Daily probe: scan all tracked shebanged files for index mode 100644 drift.
#
# Detect-only — does NOT auto-fix. The pre-commit hook
# (coordinator-precommit-exec-bit-check) auto-fixes at commit time, so steady-
# state drift here means files that drifted out-of-band: --no-verify commits,
# external pushes, or hook-bypass paths. Daily surfacing keeps those visible.
#
# Wired into: /workday-start Step 1.10.7, runs read-only and reports to PM.
#
# Spec backlink: state/handoffs/2026-06-15_114014_exec-bit-drift-recurring-on-windows-git-bash.md AC
#
# Exit codes:
#   0 — no drift
#   1 — drift detected (path list printed to stderr)
#   2 — probe infra failure (test missing, node missing)

set -euo pipefail

# Review F2 (2026-06-15): bash 4+ required for `mapfile -t` below. DR-148
# mandates fail-loud guard with brew remediation. Plain arithmetic so bash 3.2
# can parse before executing.
if (( BASH_VERSINFO[0] < 4 )); then
  echo "check-all-shebanged-exec-bits: requires bash >= 4 (brew install bash on macOS)" >&2
  exit 2
fi

META_REPO="$HOME/.claude"
EXEC_BIT_TEST="$META_REPO/plugins/coordinator/tests/plugin-ecosystem/exec-bit.test.js"

if ! command -v node >/dev/null 2>&1; then
  echo "check-all-shebanged-exec-bits: node not available — probe skipped." >&2
  exit 2
fi

if [ ! -f "$EXEC_BIT_TEST" ]; then
  echo "check-all-shebanged-exec-bits: test file missing at $EXEC_BIT_TEST — probe skipped." >&2
  exit 2
fi

TEST_OUT="$(node --test "$EXEC_BIT_TEST" 2>&1)" || TEST_FAILED=1
if [ "${TEST_FAILED:-0}" != "1" ]; then
  exit 0
fi

# Format dependency (review F3, F5): regex bound to literal assertion-message
# format at plugins/coordinator/tests/plugin-ecosystem/
# exec-bit.test.js around line 289-291. Mirror of the extraction in
# coordinator-precommit-exec-bit-check; both must update together if the test
# format changes.
mapfile -t DRIFT_PATHS < <(printf '%s\n' "$TEST_OUT" | grep -oE 'update-index --chmod=\+x "[^"]+"' | sed -E 's/.*"([^"]+)"/\1/' | sort -u)

if [ ${#DRIFT_PATHS[@]} -eq 0 ]; then
  echo "check-all-shebanged-exec-bits: test failed but no drift paths surfaced (test infra issue)." >&2
  echo "$TEST_OUT" >&2
  exit 2
fi

echo "exec-bit drift detected on ${#DRIFT_PATHS[@]} file(s) (probe-only — not auto-fixed):" >&2
for p in "${DRIFT_PATHS[@]}"; do
  echo "  $p" >&2
done
echo "" >&2
echo "Fix: cd ~/.claude && git update-index --chmod=+x <path>... && git commit -m 'fix: exec-bit drift' -- <path>..." >&2
echo "Or trigger the pre-commit auto-fix by staging any change and committing — the hook will fix all drift in one pass." >&2
exit 1
