#!/usr/bin/env bash
# Surface a "central learn-lessons run due (by VOLUME)" nudge when [universal]
# entries accrued since the last COMPLETE central run exceed a threshold.
#
# Companion to the date-based lesson-triage-recheck marker: a fixed cadence
# over-runs in quiet weeks and under-runs in busy ones (when the sibling
# lessons.md boot-surface floor balloons). This bounds the floor ADAPTIVELY —
# busy periods cross the threshold sooner. Read-only; surfaces, never dispatches.
#
# Cutoff = last central run that wrote a COMPLETE sentinel (Phase 8). An
# in-progress/aborted run (no sentinel) is correctly ignored.
#
# Output: a single `CENTRAL_RUN_DUE` line on stdout when over threshold; an
# informational under-threshold / no-baseline line on stderr otherwise. Exit 0
# always (it is a nudge, not a gate). Optional arg overrides the threshold.
# errexit intentionally omitted — this is a nudge, not a gate: it must exit 0 and
# never terminate /workday-start on an internal error (pipefail still guards pipes).
# Source the state-root seam -- must precede coordinator_state_root calls (added by repoint-central-state-refs.sh C3)
_CSR_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" 2>/dev/null && pwd)"
# shellcheck source=lib/coordinator-state-root.sh
source "${_CSR_LIB_DIR}/coordinator-state-root.sh"

set -uo pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME}/.claude"
# learn-lessons-config is empty-by-default (learn-lessons-config-update.sh inert); stale-read accepted no-op — migrate config to DoE when class becomes active
CONFIG="$(coordinator_state_root --central)/learn-lessons-config.md"

# Resolve coordinator content root via the portable resolver (CLAUDE_PLUGIN_ROOT →
# COORDINATOR_ROOT → registry clone → versioned cache → flat layout).
_rcc_resolver="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lib/resolve-coordinator-clone.sh"
if [[ -f "$_rcc_resolver" ]]; then
    # shellcheck source=../lib/resolve-coordinator-clone.sh
    source "$_rcc_resolver" 2>/dev/null || true
fi
if [[ -z "${COORDINATOR_CONTENT_ROOT:-}" ]]; then
    COORDINATOR_CONTENT_ROOT="$CLAUDE_HOME/plugins/coordinator-claude/coordinator"
fi

# Discovery roots are PER-MACHINE, derived from the machine-local [repos] registry by this helper
# (NOT the old BEGIN/END learn-lessons-roots sentinel in $CONFIG, which is retired). $CONFIG is read
# below only for the central_volume_threshold knob.
ROOTS_HELPER="$COORDINATOR_CONTENT_ROOT/bin/learn-lessons-roots.sh"
EXTRACT="$COORDINATOR_CONTENT_ROOT/bin/extract-lessons.py"
# Python 3 interpreter: python3 on macOS/Linux, python on Windows git-bash.
PYTHON="$(command -v python3 || command -v python || true)"

# Threshold: arg > config (central_volume_threshold: N) > default 150.
THRESHOLD="${1:-}"
if [ -z "$THRESHOLD" ] && [ -f "$CONFIG" ]; then
  THRESHOLD=$(grep -oE 'central_volume_threshold:[[:space:]]*[0-9]+' "$CONFIG" 2>/dev/null \
              | grep -oE '[0-9]+' | head -1)
fi
[ -z "$THRESHOLD" ] && THRESHOLD=150
[[ "$THRESHOLD" =~ ^[0-9]+$ ]] || { echo "central-run-due: invalid threshold '$THRESHOLD' — skipping" >&2; exit 0; }

[ -f "$CONFIG" ] || { echo "central-run-due: no config at $CONFIG — skipping" >&2; exit 0; }
[ -f "$EXTRACT" ] || { echo "central-run-due: extractor missing at $EXTRACT — skipping" >&2; exit 0; }
[ -n "$PYTHON" ] || { echo "central-run-due: no python interpreter found — skipping" >&2; exit 0; }

# Last COMPLETE central run (dirs sort lexically == chronologically for YYYY-MM-DD).
cutoff=""
for d in "$CLAUDE_HOME"/tasks/learn-lessons-20*/; do
  [ -f "${d}COMPLETE" ] && cutoff=$(basename "$d" | sed 's#learn-lessons-##')
done
if [ -z "$cutoff" ]; then
  echo "central-run-due: no COMPLETE central-run sentinel found — skipping volume check" >&2
  exit 0
fi
# A non-date suffix dir (e.g. learn-lessons-2026-05-27-retry) sorts after the dated one
# and would feed a non-date string to --since; validate before trusting it as a cutoff.
[[ "$cutoff" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || {
  echo "central-run-due: unrecognised cutoff '$cutoff' — skipping" >&2; exit 0; }

# Guard: if ROOTS_HELPER is absent or not executable, emit a diagnostic and exit rather
# than silently producing zero roots (which would always report 0 universals accrued).
[ -x "$ROOTS_HELPER" ] || { echo "central-run-due: roots helper not executable at $ROOTS_HELPER — skipping" >&2; exit 0; }

# Sum [universal] entries dated >= cutoff across reachable roots, excluding the
# central target itself (~/.claude is the promotion DESTINATION, not a source).
total=0
detail=""
while IFS= read -r root; do
  [ -z "$root" ] && continue
  # Normalise backslashes + case before comparing so a Windows-native CLAUDE_HOME
  # (c:\users\...\.claude) still self-excludes, not just the git-bash /c/... form.
  root_norm="$(printf '%s' "${root//\\//}" | tr '[:upper:]' '[:lower:]')"
  home_norm="$(printf '%s' "${CLAUDE_HOME//\\//}" | tr '[:upper:]' '[:lower:]')"
  case "$root_norm" in
    "$home_norm"|*/.claude) continue ;;  # self-exclude (~/.claude is the promotion destination)
  esac
  lessons="$root/state/lessons.md"
  [ -f "$lessons" ] || continue   # unreachable on this machine — skip silently
  out=$("$PYTHON" "$EXTRACT" extract "$lessons" --shortname vol --since "$cutoff" --require-tag universal 2>/dev/null) || continue # verify-no-console-flash: allow — on-demand cross-repo check, not session-hot-path
  n=$(printf '%s\n' "$out" | grep -oE '# record_count:[[:space:]]*[0-9]+' | grep -oE '[0-9]+' | head -1)
  if [ -z "$n" ]; then
    [ -n "$out" ] && echo "central-run-due: no record_count in extractor output for $root — counting 0" >&2
    n=0
  fi
  total=$((total + n))
  [ "$n" -gt 0 ] && detail="${detail:+$detail }$(basename "$root"):$n"
done < <( "$ROOTS_HELPER" 2>/dev/null )

if [ "$total" -ge "$THRESHOLD" ]; then
  echo "CENTRAL_RUN_DUE volume: $total [universal] entries accrued since last central run ($cutoff) >= threshold $THRESHOLD.${detail:+ Breakdown: $detail}. Consider /learn-lessons central."
else
  echo "central-run-due: $total/$THRESHOLD universals since $cutoff — below threshold" >&2
fi
exit 0
