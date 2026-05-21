#!/usr/bin/env bash
# coordinator-doctor-sentinel.sh — fire the coordinator-doctor wiki's probes
# (P-1..P-9 plus P-10 claude-home smoke and P-11 templates/setup drift) and
# write a sentinel JSON that bin/scan-addon-health.sh consumes.
#
# Rationale: docs/wiki/coordinator-doctor.md defines runnable probes for the
# substrate downstream plugins depend on (machine-local registry,
# coordinator_whoami, mcpServers config, bin/ resolvers). The wiki explicitly
# rejects a /coordinator:doctor slash skill ("bloat for a non-interactive
# verification surface"). This script is the non-skill primitive that keeps
# the addon-health surface uniform — fires the probes on cadence (from
# /workday-start Step 1.10) and writes ~/.claude/plugins/coordinator-claude/data/doctor-last-run.json
# so the existing scan-addon-health.sh picks up resolver drift the same way
# it picks up other plugin doctors' verdicts.
#
# Sentinel schema (mirrors what scan-addon-health.sh parses, plus an
# amber_probes field for machine-readable AMBER triage — scan-addon-health.sh
# ignores unknown fields, so this is additive-safe):
#   {
#     "ran_at":       "<ISO-8601 timestamp, UTC, Z-suffix>",
#     "verdict":      "GREEN" | "AMBER" | "RED",
#     "red_probes":   ["P-<n>", ...],   # probes with error-severity that failed
#     "amber_probes": ["P-<n>", ...],   # probes with degraded-severity that failed
#     "hint":         "<one-line operator action — joins all probe notes with ' | '>",
#     "plugin":       "coordinator-claude"
#   }
#
# Verdict rules:
#   - Any probe whose wiki-severity is `error` fails              -> RED
#   - No errors, but one or more `degraded` probes fail           -> AMBER
#   - All probes pass                                             -> GREEN
#   - Probes for OPTIONAL tools whose dependency is missing       -> AMBER
#     (e.g. P-9 verify-ue-overrides.sh is skipped silently when absent)
#   - Probes for REQUIRED INFRASTRUCTURE whose binary is missing  -> RED
#     (P-4 machine-local CLI, P-10 claude-home — they are not optional;
#     their absence means /coordinator:setup Phase 3 regressed)
#
# Exit code: always 0 (advisory). Sentinel is the channel; stdout is silent
# on success, brief on RED/AMBER for direct-invocation operator visibility.

set -u

# Honor CLAUDE_HOME for test sandboxes / CI; mirror claude-home resolver shape.
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
PLUGINS_ROOT="${COORDINATOR_PLUGINS_ROOT:-$CLAUDE_HOME/plugins}"
SENTINEL_DIR="$PLUGINS_ROOT/coordinator-claude/data"
SENTINEL_PATH="$SENTINEL_DIR/doctor-last-run.json"
BIN_DIR="$CLAUDE_HOME/bin"

# Resolve a Python 3 interpreter the same way scan-addon-health.sh does.
PY="${COORDINATOR_PYTHON:-}"
if [[ -z "$PY" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  elif command -v python >/dev/null 2>&1; then
    PY=python
  else
    # Without python we cannot emit JSON safely. Stay silent on stdout and
    # exit 0; scan-addon-health.sh's own python-missing diagnostic will fire.
    exit 0
  fi
fi

mkdir -p "$SENTINEL_DIR"

red_probes=()
amber_probes=()
hint_lines=()

note_red() { red_probes+=("$1"); hint_lines+=("$1: $2"); }
note_amber() { amber_probes+=("$1"); hint_lines+=("$1: $2"); }

# Resolve machine-local CLI once (P-3 and P-4 both use it).
ml_cmd=""
if [[ -x "$BIN_DIR/machine-local" ]]; then
  ml_cmd="$BIN_DIR/machine-local"
elif command -v machine-local >/dev/null 2>&1; then
  ml_cmd="machine-local"
fi

# Resolve claude-home CLI once (P-10).
ch_cmd=""
if [[ -x "$BIN_DIR/claude-home" ]]; then
  ch_cmd="$BIN_DIR/claude-home"
elif command -v claude-home >/dev/null 2>&1; then
  ch_cmd="claude-home"
fi

# --- P-1: ~/.claude/machine-local/ directory exists -------------------------
if [[ ! -d "$CLAUDE_HOME/machine-local" ]]; then
  note_red "P-1" "machine-local/ absent — run /coordinator:setup Phase 3"
fi

# --- P-2: registry.toml parses and declares schema = 1 ----------------------
if [[ -f "$CLAUDE_HOME/machine-local/registry.toml" ]]; then
  if ! DOCTOR_REG="$CLAUDE_HOME/machine-local/registry.toml" "$PY" -c "
import os, pathlib
try:
    import tomllib
except ImportError:
    import sys; sys.exit(2)  # py < 3.11 — inconclusive, treat as amber upstream
d = tomllib.loads(pathlib.Path(os.environ['DOCTOR_REG']).read_text())
assert d.get('schema') == 1, 'schema mismatch'
" 2>/dev/null; then
    rc=$?
    if [[ "$rc" -eq 2 ]]; then
      note_amber "P-2" "Python < 3.11 lacks tomllib — cannot validate registry.toml"
    else
      note_red "P-2" "registry.toml unparseable or wrong schema"
    fi
  fi
else
  # Already covered by P-1 if dir is absent; only surface here if dir exists.
  if [[ -d "$CLAUDE_HOME/machine-local" ]]; then
    note_red "P-2" "registry.toml missing from machine-local/"
  fi
fi

# --- P-3: at least one repos.* key in registry.local.toml -------------------
if [[ -n "$ml_cmd" ]]; then
  if ! "$ml_cmd" keys 2>/dev/null | grep -q '^repos\.'; then
    note_amber "P-3" "no repos.* keys populated — run machine-local set repos.<name> <path>"
  fi
fi

# --- P-4: bin/machine-local CLI smoke (required infrastructure) -------------
if [[ -n "$ml_cmd" ]]; then
  if ! "$ml_cmd" keys >/dev/null 2>&1; then
    note_red "P-4" "machine-local CLI failed — verify ~/.claude/bin/ on PATH and registry.toml parses"
  fi
else
  note_red "P-4" "machine-local CLI not found on PATH — re-run /coordinator:setup Phase 3"
fi

# --- P-5: coordinator_whoami importable -------------------------------------
_p5_ok=0
if ! "$PY" -c "import coordinator_whoami" >/dev/null 2>&1; then
  note_red "P-5" "coordinator_whoami not importable — pip install -e plugins/coordinator/whoami/"
else
  _p5_ok=1
fi

# --- P-6: live coordinator_whoami.project_rag envelope ----------------------
# Only fire if P-5 passed; otherwise the failure is downstream of P-5.
if [[ "$_p5_ok" -eq 1 ]]; then
  # Capture output separately so a non-zero exit from the producer is
  # distinguishable from a JSON-parse failure on the consumer side.
  # CLI defaults to JSON; --json is unrecognized. Suppress stderr (carries
  # non-fatal warnings like marker_dir reconciliation hints) and parse stdout.
  p6_out="$("$PY" -m coordinator_whoami.project_rag 2>/dev/null || true)"
  if [[ -z "$p6_out" ]]; then
    note_red "P-6" "coordinator_whoami.project_rag produced no output — module crash or missing CLI"
  elif ! echo "$p6_out" | "$PY" -c "
import json, sys
d = json.load(sys.stdin)
assert d.get('contract_version') == 1, 'contract_version != 1'
" >/dev/null 2>&1; then
    note_red "P-6" "coordinator_whoami.project_rag envelope invalid — check registry keys + contract docs"
  fi
fi

# --- P-7: ~/.claude.json mcpServers present (config-presence only) ----------
if ! DOCTOR_CFG="$CLAUDE_HOME.json" "$PY" -c "
import json, os, pathlib
p = pathlib.Path(os.environ['DOCTOR_CFG'])
if not p.exists(): raise SystemExit(1)
cfg = json.loads(p.read_text())
assert 'mcpServers' in cfg and len(cfg['mcpServers']) > 0
" >/dev/null 2>&1; then
  note_amber "P-7" "~/.claude.json mcpServers entry absent or empty — re-run plugin install"
fi

# --- P-8: at least one doctor-last-run.json across installed plugins --------
# Note: by the time this runs, *our own* sentinel has not been written yet
# (we're about to write it). We count existing sibling sentinels; if zero,
# this is a cold-start condition — the sentinel we're about to write satisfies
# P-8 on the next run regardless of whether any sibling exists.
sentinel_count=0
shopt -s nullglob 2>/dev/null || true
for s in "$PLUGINS_ROOT"/*/data/doctor-last-run.json; do
  [[ -f "$s" ]] && sentinel_count=$(( sentinel_count + 1 ))
done
if [[ "$sentinel_count" -eq 0 ]]; then
  note_amber "P-8" "no prior plugin sentinels found — this sentinel will satisfy P-8 on the next run"
fi

# --- P-9: UE override verifier (OPTIONAL tool — silent skip if absent) ------
if [[ -x "$BIN_DIR/verify-ue-overrides.sh" ]]; then
  if ! "$BIN_DIR/verify-ue-overrides.sh" >/dev/null 2>&1; then
    note_amber "P-9" "verify-ue-overrides.sh emitted remediation — check repos.claude_unreal_holodeck"
  fi
fi

# --- P-10: claude-home resolver smoke (REQUIRED infrastructure) -------------
# Wiki defines P-4 for machine-local CLI but no symmetric probe for the
# claude-home path resolver. Added 2026-05-21 to close the resolver-family
# coverage gap. Absence is RED (not AMBER): claude-home is required
# infrastructure laid down by /coordinator:setup Phase 3 — if it's missing,
# Phase 3 regressed and downstream plugins will fail. This is the same
# severity rule as P-4.
if [[ -n "$ch_cmd" ]]; then
  ch_out="$("$ch_cmd" plugins 2>/dev/null || true)"
  if [[ -z "$ch_out" || ! -d "$ch_out" ]]; then
    note_red "P-10" "claude-home plugins did not resolve to a directory — resolver drift"
  fi
else
  note_red "P-10" "claude-home resolver not found — re-run /coordinator:setup Phase 3"
fi

# --- P-11: coordinator templates/setup drift detection ----------------------
# OPTIONAL tool: if verify-templates-setup-sync.sh is not present (fresh
# install before the script was shipped, or non-coordinator-claude install
# tree), silently skip. Non-zero exit -> drift detected -> AMBER (operator
# customization is legitimate; bugfixes in the template just won't reach
# this operator until manually re-synced). See coordinator-doctor.md § P-11.
_p11_script="$PLUGINS_ROOT/coordinator-claude/coordinator/bin/verify-templates-setup-sync.sh"
if [[ -x "$_p11_script" ]]; then
  if ! bash "$_p11_script" >/dev/null 2>&1; then
    note_amber "P-11" "templates/setup drift detected — run verify-templates-setup-sync.sh (no flags) to inspect; --fix to copy live → template"
  fi
fi

# --- Verdict synthesis ------------------------------------------------------
if [[ "${#red_probes[@]}" -gt 0 ]]; then
  verdict="RED"
elif [[ "${#amber_probes[@]}" -gt 0 ]]; then
  verdict="AMBER"
else
  verdict="GREEN"
fi

if [[ "$verdict" == "GREEN" ]]; then
  hint="All coordinator-doctor probes (P-1..P-11) passed."
else
  # Join hint lines with " | " for single-line sentinel hint field.
  hint=""
  for line in "${hint_lines[@]}"; do
    if [[ -z "$hint" ]]; then hint="$line"; else hint="$hint | $line"; fi
  done
fi

ran_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Write sentinel via python for safe JSON quoting. Verify write succeeded —
# silent write failure (disk full, permissions) would leave a stale sentinel
# the scanner happily reports as fresh.
if ! RED_PROBES_CSV="$(IFS=,; echo "${red_probes[*]:-}")" \
     AMBER_PROBES_CSV="$(IFS=,; echo "${amber_probes[*]:-}")" \
     RAN_AT="$ran_at" \
     VERDICT="$verdict" \
     HINT="$hint" \
     SENTINEL_PATH="$SENTINEL_PATH" \
     "$PY" -c "
import json, os
red = [p for p in os.environ['RED_PROBES_CSV'].split(',') if p]
amber = [p for p in os.environ['AMBER_PROBES_CSV'].split(',') if p]
payload = {
    'ran_at':       os.environ['RAN_AT'],
    'verdict':      os.environ['VERDICT'],
    'red_probes':   red,
    'amber_probes': amber,
    'hint':         os.environ['HINT'],
    'plugin':       'coordinator-claude',
}
with open(os.environ['SENTINEL_PATH'], 'w', encoding='utf-8') as f:
    json.dump(payload, f, indent=2)
    f.write('\n')
" 2>/dev/null; then
  echo "[coordinator-doctor] WARN: failed to write sentinel at $SENTINEL_PATH — check disk space and permissions" >&2
  exit 0
fi

# Brief stdout for direct-invocation operators (scan-addon-health.sh reads the
# file, not stdout). Silent on GREEN to keep workday-start chatter low.
if [[ "$verdict" != "GREEN" ]]; then
  echo "[coordinator-doctor] $verdict ($SENTINEL_PATH)"
  echo "  $hint"
fi

exit 0
