#!/usr/bin/env bash
# bin/check-example-orchestration-hub-doctor-sentinel.sh — read-only consumer of example-orchestration-hub's doctor sentinel.
#
# Purpose: surface example-orchestration-hub's `/example-orchestration-hub:doctor` health verdict during fleet
# /workday-start, mirroring how check-plugin-drift.sh nudges on drift.
# This is a READ-CONSUMER only — the sentinel is example-orchestration-hub-owned and written by
# `/example-orchestration-hub:doctor`; this script never writes it.
#
# Sentinel location: <EXAMPLE_ORCHESTRATION_HUB_ROOT>/state/doctor-last-run.json
# Sentinel schema (example-orchestration-hub-owned):
#   { "verdict": "GREEN|AMBER|RED", "red_probes": ["<probe id>", ...],
#     "hint": "<one-line remediation>", "ts": <epoch seconds> }
#
# Nudge-worthy states (mirrors the memo's ask):
#   - absent  — doctor never run on this machine (fresh install / bootstrap gap)
#   - stale   — sentinel older than COORDINATOR_EXAMPLE_ORCHESTRATION_HUB_DOCTOR_STALE_SEC (default 7d)
#   - RED/AMBER — last run found a broken/degraded probe; echo `hint`
#
# Output: zero or one line of the form
#   [health] example-orchestration-hub-doctor: <message>
# Exit 0 always (advisory, never gating) — matches check-plugin-drift.sh /
# scan-addon-health.sh convention of "probe never fails the ceremony".
#
# Spec backlink: cross-repo/inbox/2026-07-04-workday-start-example-orchestration-hub-doctor-sentinel.md
#
# Negative-spec:
#   - Does NOT write the sentinel — example-orchestration-hub's doctor owns that.
#   - Does NOT hardcode EXAMPLE_ORCHESTRATION_HUB_ROOT — resolves via coordinator_example_orchestration_hub_root()
#     (lib/coordinator-example-orchestration-hub-root.sh).
#   - Does NOT hard-error when EXAMPLE_ORCHESTRATION_HUB_ROOT or the sentinel is absent — degrades
#     to silent (EXAMPLE_ORCHESTRATION_HUB_ROOT unresolved: example-orchestration-hub not installed on this machine,
#     not nudge-worthy) or a soft "absent" nudge (EXAMPLE_ORCHESTRATION_HUB_ROOT resolved but no
#     sentinel yet: doctor never run).

set -uo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=../lib/coordinator-example-orchestration-hub-root.sh
source "${_SCRIPT_DIR}/../lib/coordinator-example-orchestration-hub-root.sh"

STALE_SEC="${COORDINATOR_EXAMPLE_ORCHESTRATION_HUB_DOCTOR_STALE_SEC:-604800}"  # 7 days

# Resolve EXAMPLE_ORCHESTRATION_HUB_ROOT. Unresolved is a silent skip, not a nudge — a machine
# with no example-orchestration-hub checkout registered simply isn't running the doctor, and that
# is a fleet-topology fact, not a health regression on this repo's ceremony.
EXAMPLE_ORCHESTRATION_HUB_ROOT_RESOLVED=$(coordinator_example_orchestration_hub_root 2>/dev/null) || exit 0
[[ -n "$EXAMPLE_ORCHESTRATION_HUB_ROOT_RESOLVED" ]] || exit 0

SENTINEL="${EXAMPLE_ORCHESTRATION_HUB_ROOT_RESOLVED}/state/doctor-last-run.json"

if [[ ! -f "$SENTINEL" ]]; then
  echo "[health] example-orchestration-hub-doctor: sentinel absent (doctor never run on this machine) — run /example-orchestration-hub:doctor to bootstrap."
  exit 0
fi

# shellcheck source=../lib/resolve-python.sh
source "${_SCRIPT_DIR}/../lib/resolve-python.sh" || {
  # No usable python resolver at all — degrade silently; this probe is advisory.
  exit 0
}
PY="${PYTHON_BIN:-}"
if [[ -z "$PY" ]]; then
  # No interpreter — can't parse JSON. Advisory-only, degrade silently.
  exit 0
fi
# Review: code-reviewer — Finding 3 (nit). resolve-python.sh documents PYTHON_ARGS as a
# required companion to PYTHON_BIN (Windows py launcher needs "-3" to avoid selecting a
# legacy Python 2 interpreter via PEP 514). resolve-python.sh unconditionally initializes
# PYTHON_ARGS=() on source, so it is always defined here.

parsed=$(cat "$SENTINEL" 2>/dev/null | "$PY" "${PYTHON_ARGS[@]}" -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('verdict', ''))
    print(d.get('hint', ''))
    print(','.join(d.get('red_probes', []) or []))
    print(d.get('ts', ''))
except Exception as e:
    sys.stderr.write('parse-error: ' + str(e) + '\n')
    sys.exit(1)
" 2>/dev/null) || {
  echo "[health] example-orchestration-hub-doctor: sentinel unreadable at ${SENTINEL} (malformed JSON?). Run /example-orchestration-hub:doctor."
  exit 0
}

verdict=$(echo "$parsed" | sed -n '1p')
hint=$(echo "$parsed" | sed -n '2p')
red_probes=$(echo "$parsed" | sed -n '3p')
ts=$(echo "$parsed" | sed -n '4p')

# Staleness: ts is epoch seconds (unlike scan-addon-health.sh's ISO ran_at).
# A missing/unparseable ts is treated as stale (best-effort, matches
# scan-addon-health.sh's ran_at-unparseable-is-stale convention).
NOW=$(date +%s)
stale=1
age_days="?"
if [[ "$ts" =~ ^[0-9]+$ ]]; then
  age_sec=$(( NOW - ts ))
  age_days=$(( age_sec / 86400 ))
  [[ "$age_sec" -le "$STALE_SEC" ]] && stale=0
fi

case "$verdict" in
  RED)
    probe_clause=""
    [[ -n "$red_probes" ]] && probe_clause=" (${red_probes})"
    hint_clause=""
    [[ -n "$hint" ]] && hint_clause=" — ${hint}."
    echo "[health] example-orchestration-hub-doctor: RED${probe_clause}${hint_clause} Run /example-orchestration-hub:doctor for details."
    ;;
  AMBER)
    hint_clause=""
    [[ -n "$hint" ]] && hint_clause=" — ${hint}."
    if [[ "$stale" -eq 1 && "$age_days" != "?" ]]; then
      echo "[health] example-orchestration-hub-doctor: AMBER (${age_days}d old)${hint_clause} Run /example-orchestration-hub:doctor to re-probe."
    else
      echo "[health] example-orchestration-hub-doctor: AMBER${hint_clause} Run /example-orchestration-hub:doctor to re-probe."
    fi
    ;;
  GREEN|"")
    if [[ "$stale" -eq 1 ]]; then
      if [[ "$age_days" == "?" ]]; then
        echo "[health] example-orchestration-hub-doctor: sentinel ts unparseable. Run /example-orchestration-hub:doctor."
      else
        echo "[health] example-orchestration-hub-doctor: stale (last run ${age_days}d ago). Run /example-orchestration-hub:doctor."
      fi
    fi
    ;;
  *)
    echo "[health] example-orchestration-hub-doctor: unknown verdict '${verdict}'. Run /example-orchestration-hub:doctor."
    ;;
esac

exit 0
