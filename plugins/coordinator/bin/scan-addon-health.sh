#!/usr/bin/env bash
# scan-addon-health.sh — read addon-health sentinel files and emit operator notices.
#
# Convention: plugins (especially MCP-addon plugins like project-rag-ue-addon)
# write a sentinel after each /<plugin>:doctor run at
#   ~/.claude/plugins/<plugin>/data/doctor-last-run.json
# Schema (all fields required except red_probes which may be empty):
#   {
#     "ran_at":    "<ISO-8601 timestamp>",
#     "verdict":   "GREEN" | "AMBER" | "RED",
#     "red_probes": ["<probe-id>", ...],
#     "hint":      "<one-line operator action>",
#     "plugin":    "<plugin-name>"   # optional; derived from path if absent
#   }
#
# Modes:
#   --red-only                emit lines only for RED verdicts (session-start)
#   --red-and-stale           emit lines for RED + stale (>24h) + missing sentinels + plugins declaring a doctor with no sentinel (workday-start, default)
#   --check-sentinel-presence fresh-install bootstrap check (session-start, alongside --red-only):
#                               exit 0 + empty output  → no plugins installed, OR sentinels exist
#                               exit 0 + one-line msg  → plugins installed but no sentinel in any data/ dir
#                             Fires at most once per install life (sentinels appear after first doctor run).
#
# Output: zero or more lines, each of the form
#   [health] <plugin>: <message>
# Exit 0 always (advisory, never gating). Silent when nothing to report.
#
# Stale threshold: 24h (86400s). Override via COORDINATOR_HEALTH_STALE_SEC.

set -u

MODE="--red-and-stale"
if [[ "${1:-}" == "--red-only" ]]; then
  MODE="--red-only"
elif [[ "${1:-}" == "--red-and-stale" ]]; then
  MODE="--red-and-stale"
elif [[ "${1:-}" == "--check-sentinel-presence" ]]; then
  MODE="--check-sentinel-presence"
elif [[ -n "${1:-}" ]]; then
  echo "scan-addon-health.sh: unknown mode '$1' (expected --red-only, --red-and-stale, or --check-sentinel-presence)" >&2
  exit 2
fi

STALE_SEC="${COORDINATOR_HEALTH_STALE_SEC:-86400}"
PLUGINS_ROOT="${COORDINATOR_PLUGINS_ROOT:-$HOME/.claude/plugins}"

[[ -d "$PLUGINS_ROOT" ]] || exit 0

# --check-sentinel-presence: bootstrap notice for fresh installs that have never run a doctor.
# Logic: count installed plugin dirs, then count existing sentinels. If plugins exist but no
# sentinel is present anywhere, emit a one-line bootstrap notice; otherwise stay silent.
if [[ "$MODE" == "--check-sentinel-presence" ]]; then
  shopt -s nullglob 2>/dev/null || true
  plugin_dirs=( "$PLUGINS_ROOT"/*/ )
  installed_count=${#plugin_dirs[@]}
  if [[ "$installed_count" -eq 0 ]]; then
    # No plugins installed — genuine empty state; nothing to nag about.
    exit 0
  fi
  # Count sentinels across all installed plugins.
  sentinel_count=0
  for sentinel in "$PLUGINS_ROOT"/*/data/doctor-last-run.json; do
    [[ -f "$sentinel" ]] && (( sentinel_count++ )) || true
  done
  if [[ "$sentinel_count" -eq 0 ]]; then
    echo "addon-health: no doctor sentinels found across ${installed_count} installed plugin(s) — run /coordinator:setup and your plugin doctors to bootstrap"
  fi
  exit 0
fi

# Resolve a Python 3 interpreter. Windows Git Bash typically ships `python` (a
# Python 3.x install) but no `python3`; Linux/macOS typically ship `python3`
# but may lack `python`. Honour an explicit override; otherwise prefer python3.
PY="${COORDINATOR_PYTHON:-}"
if [[ -z "$PY" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  elif command -v python >/dev/null 2>&1; then
    PY=python
  else
    # No interpreter — script can't parse sentinels at all. Emit a single
    # diagnostic in red-and-stale mode so the operator knows why health is
    # silent; stay silent in red-only mode (signal-not-noise).
    if [[ "$MODE" == "--red-and-stale" ]]; then
      echo "[health] coordinator: no python3/python on PATH — addon-health scanner cannot parse sentinels. Install Python 3 or set COORDINATOR_PYTHON."
    fi
    exit 0
  fi
fi

NOW=$(date +%s)

# Iterate sentinels. Glob may not match — guard with nullglob-equivalent.
shopt -s nullglob 2>/dev/null || true
for sentinel in "$PLUGINS_ROOT"/*/data/doctor-last-run.json; do
  [[ -f "$sentinel" ]] || continue

  # Derive plugin name from path: .../plugins/<plugin>/data/doctor-last-run.json
  plugin_dir="${sentinel%/data/doctor-last-run.json}"
  plugin="${plugin_dir##*/}"

  # Parse fields with python (portable JSON across platforms; jq not always present on Windows).
  # Read file in bash and pipe to python via stdin to dodge MSYS-Windows path translation
  # quirks (`/tmp/...` and `/c/...` style paths embedded in -c strings don't reach Windows python).
  parsed=$(cat "$sentinel" 2>/dev/null | "$PY" -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('ran_at', ''))
    print(d.get('verdict', ''))
    print(d.get('hint', ''))
    print(d.get('plugin', ''))
    print(','.join(d.get('red_probes', []) or []))
except Exception as e:
    sys.stderr.write('parse-error: ' + str(e) + '\n')
    sys.exit(1)
" 2>/dev/null) || {
    # Malformed sentinel — surface in red-and-stale mode only, since RED-only callers
    # want signal not noise.
    if [[ "$MODE" == "--red-and-stale" ]]; then
      echo "[health] ${plugin}: sentinel unreadable at ${sentinel} (malformed JSON?). Run /${plugin}:doctor."
    fi
    continue
  }

  ran_at=$(echo "$parsed" | sed -n '1p')
  verdict=$(echo "$parsed" | sed -n '2p')
  hint=$(echo "$parsed" | sed -n '3p')
  plugin_field=$(echo "$parsed" | sed -n '4p')
  red_probes=$(echo "$parsed" | sed -n '5p')

  # Prefer the in-file plugin name if present.
  [[ -n "$plugin_field" ]] && plugin="$plugin_field"

  # Compute staleness (best-effort; ran_at parse failure → treat as stale).
  ran_at_epoch=$(printf '%s' "$ran_at" | "$PY" -c "
from datetime import datetime
import sys
try:
    s = sys.stdin.read().strip().replace('Z', '+00:00')
    print(int(datetime.fromisoformat(s).timestamp()))
except Exception:
    sys.exit(1)
" 2>/dev/null) || ran_at_epoch=""

  if [[ -n "$ran_at_epoch" ]]; then
    age_sec=$(( NOW - ran_at_epoch ))
    age_days=$(( age_sec / 86400 ))
    stale=0
    [[ "$age_sec" -gt "$STALE_SEC" ]] && stale=1
  else
    age_days="?"
    stale=1
  fi

  # Decide whether to emit.
  case "$verdict" in
    RED)
      probe_clause=""
      [[ -n "$red_probes" ]] && probe_clause=" (${red_probes})"
      hint_clause=""
      [[ -n "$hint" ]] && hint_clause=" — ${hint}."
      echo "[health] ${plugin}: doctor RED${probe_clause}${hint_clause} Run /${plugin}:doctor for details."
      ;;
    GREEN|AMBER|"")
      if [[ "$MODE" == "--red-and-stale" && "$stale" -eq 1 ]]; then
        if [[ "$age_days" == "?" ]]; then
          echo "[health] ${plugin}: doctor sentinel ran_at unparseable. Run /${plugin}:doctor."
        else
          echo "[health] ${plugin}: doctor stale (last run ${age_days}d ago). Run /${plugin}:doctor."
        fi
      fi
      ;;
    *)
      # Unknown verdict — only surface in red-and-stale mode.
      if [[ "$MODE" == "--red-and-stale" ]]; then
        echo "[health] ${plugin}: doctor unknown verdict '${verdict}'. Run /${plugin}:doctor."
      fi
      ;;
  esac
done

# Second pass: per-plugin absent-sentinel detection (--red-and-stale only).
# Surfaces plugins that declare a doctor command but have never written a
# sentinel — the "doctor exists, never ran" failure mode that the main loop
# (which iterates existing sentinels) silently skips.
if [[ "$MODE" == "--red-and-stale" ]]; then
  shopt -s nullglob 2>/dev/null || true
  plugin_dirs=( "$PLUGINS_ROOT"/*/ )
  for plugin_dir in "${plugin_dirs[@]}"; do
    plugin="${plugin_dir%/}"
    plugin="${plugin##*/}"

    # Detect a doctor command across known shapes:
    #   <plugin>/commands/doctor.md
    #   <plugin>/plugin/commands/doctor.md      (project-rag-shape)
    #   <plugin>/**/commands/<plugin>:doctor.md (namespace-shaped)
    doctor_md=$(find "$plugin_dir" -maxdepth 4 -type f \( -name 'doctor.md' -o -name "${plugin}:doctor.md" \) -path '*/commands/*' 2>/dev/null | head -1)
    [[ -z "$doctor_md" ]] && continue

    # Doctor declared; check sentinel presence. If sentinel exists, the main
    # loop above already handled verdict/staleness — skip.
    if [[ ! -f "$PLUGINS_ROOT/$plugin/data/doctor-last-run.json" ]]; then
      echo "[health] ${plugin}: doctor has never run (sentinel absent). Run /${plugin}:doctor to bootstrap."
    fi
  done
fi

exit 0
