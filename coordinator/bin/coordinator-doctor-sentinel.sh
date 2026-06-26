#!/usr/bin/env bash
# coordinator-doctor-sentinel.sh — fire the coordinator-doctor wiki's probes
# (P-1..P-9 plus P-10 claude-home smoke, P-11 templates/setup drift, and
# P-12 canonical document structure presence) and write a sentinel JSON that
# bin/scan-addon-health.sh consumes.
#
# Rationale: docs/wiki/coordinator-doctor.md defines runnable probes for the
# substrate downstream plugins depend on (machine-local registry,
# coordinator_whoami, mcpServers config, bin/ resolvers). The wiki explicitly
# rejects a /coordinator:doctor slash skill ("bloat for a non-interactive
# verification surface"). This script is the non-skill primitive that keeps
# the addon-health surface uniform — fires the probes on cadence (from
# /workday-start Step 1.10 --full) and writes ~/.claude/plugins/coordinator-claude/data/doctor-last-run.json
# so the existing scan-addon-health.sh picks up resolver drift the same way
# it picks up other plugin doctors' verdicts.
#
# Selection grammar (Chunk 4 — manifest-driven, scalpel-not-hammer):
#   bare / --triage        default; run only triage probes + emit RECOMMENDATION
#   --full                 run all probes + write sentinel (cadence / daily path)
#   --cluster NAME         run probes in cluster NAME; print verdict; do NOT write sentinel
#   --probe ID             run single probe by id; print verdict; do NOT write sentinel
#   --symptom TEXT         symptom match -> cluster(s) -> run those probes; do NOT write sentinel
#
# Spec backlink: archive/specs/2026-05-27-doctor-shape-doe-alignment.md § Chunk 4b.
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
#     their absence means /coordinator:install Phase 3 regressed)
#
# Exit code: always 0 (advisory) for --full. Subset modes exit 0 on success,
# non-zero on selector error.

set -u

# ---------------------------------------------------------------------------
# Arg parsing — selection grammar
# ---------------------------------------------------------------------------

MODE="triage"  # default: bare invocation = triage
_ARG=""

_usage_error() {
  echo "[coordinator-doctor] ERROR: $1" >&2
  echo "Usage: $0 [--triage|--full|--cluster NAME|--probe ID|--symptom TEXT]" >&2
  exit 2
}

if [[ $# -eq 0 ]]; then
  MODE="triage"
elif [[ $# -eq 1 ]]; then
  case "$1" in
    --triage) MODE="triage" ;;
    --full)   MODE="full"   ;;
    --cluster|--probe|--symptom)
      _usage_error "$1 requires an argument" ;;
    --*)
      _usage_error "unknown flag: $1" ;;
    *)
      _usage_error "unknown argument: $1" ;;
  esac
elif [[ $# -eq 2 ]]; then
  case "$1" in
    --cluster) MODE="cluster"; _ARG="$2" ;;
    --probe)   MODE="probe";   _ARG="$2" ;;
    --symptom) MODE="symptom"; _ARG="$2" ;;
    --triage|--full)
      _usage_error "too many arguments for $1" ;;
    *)
      _usage_error "unknown flag: $1" ;;
  esac
elif [[ $# -ge 3 && "$1" == "--symptom" ]]; then
  # Allow multi-word symptom passed as separate shell args.
  MODE="symptom"
  shift
  _ARG="$*"
else
  _usage_error "too many arguments (pass --symptom TEXT for multi-word symptoms)"
fi

# ---------------------------------------------------------------------------
# Resolve the selector helper (sibling to this script)
# ---------------------------------------------------------------------------

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_SELECTOR="${_SCRIPT_DIR}/doctor-probe-select.py"

if [[ ! -f "$_SELECTOR" ]]; then
  echo "[coordinator-doctor] ERROR: doctor-probe-select.py not found at $_SELECTOR" >&2
  exit 2
fi

# Resolve a Python 3 interpreter via the shared lib (honors COORDINATOR_PYTHON
# env var and machine-local coordinator.python pin before falling through to
# OS-level resolution).
# shellcheck source=../lib/resolve-python.sh
source "${_SCRIPT_DIR}/../lib/resolve-python.sh" || {
  echo "[coordinator-doctor] ERROR: failed to source resolve-python.sh" >&2
  exit 2
}
PY="$PYTHON_BIN" # verify-no-console-flash: allow — variable alias assignment, not a spawn; actual invocations use resolve-python.sh PYTHON_ARGS idiom
if [[ -z "$PY" ]]; then
  # Without python we cannot run the selector or emit JSON safely.
  echo "[coordinator-doctor] ERROR: no Python interpreter found — cannot run selector or probes" >&2
  exit 2
fi

# Human-readable identity of the interpreter the whoami / envelope probes use.
# Editable installs (pip install -e) register only in ONE interpreter's
# site-packages, so a "not importable" RED is ambiguous unless the note names
# WHICH interpreter was tried — a genuine python3-vs-venv mismatch otherwise
# looks identical to a stale install-timing RED. Naming it makes P-5/P-6/P-6s
# self-diagnosing. (cross-repo memo 2026-06-20-coordinator-doctor-whoami-false-red.)
_PY_PATH="$(command -v "$PY" 2>/dev/null || echo "$PY")"
_PY_IDENT="$("$PY" --version 2>&1 | head -1) at $_PY_PATH"

# ---------------------------------------------------------------------------
# Compute ACTIVE_PROBES via the selector
# ---------------------------------------------------------------------------

_selector_args=()
case "$MODE" in
  triage)  _selector_args=(--triage) ;;
  full)    _selector_args=(--full)   ;;
  cluster) _selector_args=(--cluster "$_ARG") ;;
  probe)   _selector_args=(--probe   "$_ARG") ;;
  symptom) _selector_args=(--symptom "$_ARG") ;;
esac

# Capture selector stderr for fail-loud propagation.
_selector_stderr_tmp="$(mktemp)"
_selector_exit=0
# Guard against set -u empty-array expansion on bash < 4.4 using the
# conditional expansion idiom ${arr[@]:+"${arr[@]}"} (safe on all bash versions).
ACTIVE_PROBES_RAW="$("$PY" "$_SELECTOR" "${_selector_args[@]:+"${_selector_args[@]}"}" 2>"$_selector_stderr_tmp")" || _selector_exit=$?

if [[ "$_selector_exit" -ne 0 ]]; then
  _sel_err="$(cat "$_selector_stderr_tmp" 2>/dev/null || true)"
  rm -f "$_selector_stderr_tmp"
  echo "[coordinator-doctor] selector error: ${_sel_err}" >&2
  exit "$_selector_exit"
fi
rm -f "$_selector_stderr_tmp"

# Vacuous-match guard: assert non-empty (selector already exits 2 for no-match,
# but defend under set -u).
if [[ -z "$ACTIVE_PROBES_RAW" ]]; then
  echo "[coordinator-doctor] ERROR: selector returned empty probe set (vacuous-GREEN guard)" >&2
  exit 2
fi

# is_active "P-N" — returns 0 (true) if P-N is in ACTIVE_PROBES_RAW.
is_active() {
  local _id="$1"
  echo "$ACTIVE_PROBES_RAW" | grep -qxF "$_id"
}

# ---------------------------------------------------------------------------
# Environment / path resolution
# ---------------------------------------------------------------------------

# Honor CLAUDE_HOME for test sandboxes / CI; mirror claude-home resolver shape.
# Review: code-reviewer — B-F1: capture original before reassign so P-18 subprocess
# sees the HOME-substitute value, not the .claude-suffixed one we set below.
_ORIGINAL_CLAUDE_HOME="${CLAUDE_HOME:-}"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME}/.claude"
PLUGINS_ROOT="${COORDINATOR_PLUGINS_ROOT:-$CLAUDE_HOME/plugins}"
SENTINEL_DIR="$PLUGINS_ROOT/coordinator-claude/data"
SENTINEL_PATH="$SENTINEL_DIR/doctor-last-run.json"
BIN_DIR="$CLAUDE_HOME/bin"

mkdir -p "$SENTINEL_DIR"

red_probes=()
amber_probes=()
hint_lines=()

note_red()   { red_probes+=("$1");   hint_lines+=("$1: $2"); }
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

# ---------------------------------------------------------------------------
# Probe bodies — each guarded by is_active "P-N"
# Probe logic is preserved verbatim from the original sentinel;
# only the is_active guards are new (Chunk 4b surgery).
# ---------------------------------------------------------------------------

# --- P-1: ~/.claude/machine-local/ directory exists -------------------------
if is_active "P-1"; then
  if [[ ! -d "$CLAUDE_HOME/machine-local" ]]; then
    note_red "P-1" "machine-local/ absent — run /coordinator:install Phase 3"
  fi
fi

# --- P-2: registry.toml parses and declares schema = 1 ----------------------
if is_active "P-2"; then
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
fi

# --- P-3: at least one repos.* key in registry.local.toml -------------------
if is_active "P-3"; then
  if [[ -n "$ml_cmd" ]]; then
    if ! "$ml_cmd" keys 2>/dev/null | grep -q '^repos\.'; then
      note_amber "P-3" "no repos.* keys populated — run machine-local set repos.<name> <path>"
    fi
  fi
fi

# --- P-4: bin/machine-local CLI smoke (required infrastructure) -------------
if is_active "P-4"; then
  if [[ -n "$ml_cmd" ]]; then
    if ! "$ml_cmd" keys >/dev/null 2>&1; then
      note_red "P-4" "machine-local CLI failed — registry.toml unparseable; re-run /coordinator:install Phase 3 (on macOS, ~/.claude/bin is reached via the coordinator/bin forwarder, not PATH directly)"
    fi
  else
    note_red "P-4" "machine-local CLI not found on PATH — re-run /coordinator:install Phase 3 (on macOS, ~/.claude/bin is reached via the coordinator/bin forwarder, not PATH directly)"
  fi
fi

# --- P-5: coordinator_whoami importable -------------------------------------
# _whoami_importable: unconditional import check used by P-6 and P-6s as a
# prerequisite, independent of whether P-5 is in ACTIVE_PROBES. Cached so the
# import runs at most once even when P-6 and P-6s are both active.
_whoami_checked=0
_whoami_ok=0
_whoami_importable() {
  if [[ "$_whoami_checked" -eq 0 ]]; then
    _whoami_checked=1
    if "$PY" -c "import coordinator_whoami" >/dev/null 2>&1; then
      _whoami_ok=1
    fi
  fi
  return $(( 1 - _whoami_ok ))
}

if is_active "P-5"; then
  if ! _whoami_importable; then
    note_red "P-5" "coordinator_whoami not importable under $_PY_IDENT — pip install -e plugins/coordinator/whoami/ (editable installs are per-interpreter; install under THIS interpreter, or set COORDINATOR_PYTHON to the one that has it)"
  fi
fi

# --- P-6: live coordinator_whoami.project_rag envelope ----------------------
# Only fire if coordinator_whoami is importable; otherwise the failure is
# downstream of P-5. (Gate is the unconditional import check, not P-5 active-membership.)
if is_active "P-6"; then
  if _whoami_importable; then
    # Capture output separately so a non-zero exit from the producer is
    # distinguishable from a JSON-parse failure on the consumer side.
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
  else
    note_red "P-6" "coordinator_whoami not importable under $_PY_IDENT — cannot probe project_rag envelope (fix P-5 first)"
  fi
fi

# --- P-6s: live coordinator_whoami.session envelope (orientation-health probe) --
# Distinct from P-6 (plugin-binding health for project-rag adopter): P-6s probes
# the first-class session-identity spine that /workstream-start depends on.
# Only fire if coordinator_whoami is importable; otherwise the failure is
# downstream of P-5. (Gate is the unconditional import check, not P-5 active-membership.)
if is_active "P-6s"; then
  if _whoami_importable; then
    p6s_out="$("$PY" -m coordinator_whoami.session 2>/dev/null || true)"
    if [[ -z "$p6s_out" ]]; then
      note_red "P-6s" "coordinator_whoami.session produced no output — module crash or missing CLI"
    elif ! echo "$p6s_out" | "$PY" -c "
import json, sys
d = json.load(sys.stdin)
assert d.get('contract_version') == 1, 'contract_version != 1'
assert d.get('plugin_name') == 'coordinator-session', 'plugin_name != coordinator-session'
" >/dev/null 2>&1; then
      note_red "P-6s" "coordinator_whoami.session envelope invalid — expected contract_version=1, plugin_name=coordinator-session"
    fi
  else
    note_red "P-6s" "coordinator_whoami not importable under $_PY_IDENT — cannot probe session envelope (fix P-5 first)"
  fi
fi

# --- P-7: ~/.claude.json mcpServers present (config-presence only) ----------
if is_active "P-7"; then
  if ! DOCTOR_CFG="$CLAUDE_HOME.json" "$PY" -c "
import json, os, pathlib
p = pathlib.Path(os.environ['DOCTOR_CFG'])
if not p.exists(): raise SystemExit(1)
cfg = json.loads(p.read_text())
assert 'mcpServers' in cfg and len(cfg['mcpServers']) > 0
" >/dev/null 2>&1; then
    note_amber "P-7" "~/.claude.json mcpServers entry absent or empty — re-run plugin install"
  fi
fi

# --- P-8: at least one doctor-last-run.json across installed plugins --------
# Note: by the time this runs, *our own* sentinel has not been written yet
# (we're about to write it). We count existing sibling sentinels; if zero,
# this is a cold-start condition — the sentinel we're about to write satisfies
# P-8 on the next run regardless of whether any sibling exists.
if is_active "P-8"; then
  sentinel_count=0
  shopt -s nullglob 2>/dev/null || true
  for s in "$PLUGINS_ROOT"/*/data/doctor-last-run.json; do
    [[ -f "$s" ]] && sentinel_count=$(( sentinel_count + 1 ))
  done
  if [[ "$sentinel_count" -eq 0 ]]; then
    note_amber "P-8" "no prior plugin sentinels found — this sentinel will satisfy P-8 on the next run"
  fi
fi

# --- P-9: UE override verifier (OPTIONAL tool — silent skip if absent) ------
if is_active "P-9"; then
  if [[ -x "$BIN_DIR/verify-ue-overrides.sh" ]]; then
    if ! "$BIN_DIR/verify-ue-overrides.sh" >/dev/null 2>&1; then
      note_amber "P-9" "verify-ue-overrides.sh emitted remediation — check repos.claude_unreal_holodeck"
    fi
  fi
fi

# --- P-10: claude-home resolver smoke (REQUIRED infrastructure) -------------
# Wiki defines P-4 for machine-local CLI but no symmetric probe for the
# claude-home path resolver. Added 2026-05-21 to close the resolver-family
# coverage gap. Absence is RED (not AMBER): claude-home is required
# infrastructure laid down by /coordinator:install Phase 3 — if it's missing,
# Phase 3 regressed and downstream plugins will fail. This is the same
# severity rule as P-4.
if is_active "P-10"; then
  if [[ -n "$ch_cmd" ]]; then
    ch_out="$("$ch_cmd" plugins 2>/dev/null || true)"
    if [[ -z "$ch_out" || ! -d "$ch_out" ]]; then
      note_red "P-10" "claude-home plugins did not resolve to a directory — resolver drift"
    fi
  else
    note_red "P-10" "claude-home resolver not found — re-run /coordinator:install Phase 3 (on macOS, ~/.claude/bin is reached via the coordinator/bin forwarder, not PATH directly)"
  fi
fi

# --- P-11: coordinator templates/setup drift detection ----------------------
# OPTIONAL tool: if verify-templates-setup-sync.sh is not present (fresh
# install before the script was shipped, or non-coordinator-claude install
# tree), silently skip. Non-zero exit -> drift detected -> AMBER (operator
# customization is legitimate; bugfixes in the template just won't reach
# this operator until manually re-synced). See coordinator-doctor.md § P-11.
if is_active "P-11"; then
  _p11_script="$PLUGINS_ROOT/coordinator-claude/coordinator/bin/verify-templates-setup-sync.sh"
  if [[ -x "$_p11_script" ]]; then
    if ! bash "$_p11_script" >/dev/null 2>&1; then
      note_amber "P-11" "templates/setup drift detected — run verify-templates-setup-sync.sh (no flags) to inspect; --fix to copy live → template"
    fi
  fi
fi

# --- P-12: canonical document structure present (eager dirs + READMEs intact)
# spec-backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 6
# Resolve scaffold relative to THIS script's directory (siblings in bin/) so the probe
# fires regardless of COORDINATOR_PLUGINS_ROOT (which may be a test-env override that
# points to a scratch directory without a real coordinator install).
# OPTIONAL: if scaffold-canonical-structure.sh is not present (pre-Chunk-2 install),
# silently skip. severity: degraded — missing cross-repo/ breaks memo discoverability
# but does not halt coordinator function like P-1/P-4/P-10 do.
if is_active "P-12"; then
  _p12_sentinel_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  _p12_scaffold="${_p12_sentinel_dir}/scaffold-canonical-structure.sh"
  if [[ -x "$_p12_scaffold" ]]; then
    _p12_dry_out="$(bash "$_p12_scaffold" --root "$CLAUDE_HOME" --dry-run 2>/dev/null || true)"
    # --dry-run prints "would create" for missing items; "skip (exists)" for present ones.
    # A fully healthy install produces ONLY "skip (exists)" lines (plus the header lines).
    if echo "$_p12_dry_out" | grep -q "would create"; then
      note_amber "P-12" "canonical structure incomplete at $CLAUDE_HOME — run scaffold-canonical-structure.sh --root $CLAUDE_HOME to restore; or re-run /coordinator:install"
    fi
  fi
fi

# --- P-13: onboarding currency (per-repo coordinator-currency.yaml stamp) ---
# spec-backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1
# CHEAP probe — file read + one shell comparison; no subprocess spawn required.
# severity: degraded — stale/unstamped repo does not halt coordinator function
# but means the agent's scaffolding may be out of date with the current schema.
# inconclusive → AMBER (per doctor-probe-design.md § inconclusive Is a First-Class Probe Status).
# source_is_live → silent skip (expected-unstamped; see probe script).
if is_active "P-13"; then
  _p13_script="${_SCRIPT_DIR}/probe-onboarding-currency.sh"
  if [[ -x "$_p13_script" ]]; then
    _p13_out="$(CLAUDE_HOME="$CLAUDE_HOME" \
                COORDINATOR_CURRENCY_PLUGIN_ROOT="${PLUGINS_ROOT}/coordinator-claude/coordinator" \
                bash "$_p13_script" 2>/dev/null || true)"
    case "$_p13_out" in
      current)
        : # healthy — no action
        ;;
      source_is_live)
        : # expected-unstamped — silent skip, not AMBER
        ;;
      unstamped*)
        note_amber "P-13" "repo predates onboarding currency feature — run /repo-setup to stamp"
        ;;
      drift*)
        note_amber "P-13" "onboarding stamp is stale: ${_p13_out} — re-run /repo-setup to refresh"
        ;;
      inconclusive*)
        note_amber "P-13" "onboarding currency check inconclusive: ${_p13_out}"
        ;;
      "")
        # Probe script produced no output — treat as inconclusive rather than
        # false-pass (per doctor-probe-design.md § vacuous-pass guard).
        note_amber "P-13" "onboarding currency probe produced no output — check probe-onboarding-currency.sh"
        ;;
      *)
        note_amber "P-13" "onboarding currency probe returned unexpected status: ${_p13_out}"
        ;;
    esac
  fi
  # If probe script is missing: silently skip (pre-ship install; not an error).
fi

# --- P-15: system-prerequisite gate (SSOT: scripts/lib/prereq_probe.sh) --------------
# spec-backlink: docs/plans/2026-06-23-clone-auth-semi-hard-step-zero.md § C4
# Reuses _co_prereq_probe_all (the install Step Zero SSOT) — no duplicated probe logic.
# Only hard-severity failures (git, python, gh, node) drive RED; advisory-tier absences
# (uv, pwsh, ue, longpaths, git_lfs) are silently skipped (GREEN) per doctor-probe-design.md
# § "AMBER on Optional Absence Is Bad Form".
# Sourcing discipline: COORDINATOR_PREREQ_PROBE_LIB_DIR is set explicitly so the lib-dir
# resolution inside prereq_probe.sh does not depend on BASH_SOURCE (which is unreliable
# under `bash -c` dispatch). The sentinel's own _SCRIPT_DIR is always resolved above.
if is_active "P-15"; then
  # Honor COORDINATOR_PREREQ_PROBE_LIB_DIR as an override (used by tests to inject
  # a fake prereq_probe.sh without touching the real SSOT lib).
  if [[ -n "${COORDINATOR_PREREQ_PROBE_LIB_DIR:-}" ]]; then
    _p15_lib_dir="$COORDINATOR_PREREQ_PROBE_LIB_DIR"
  else
    _p15_lib_dir="${_SCRIPT_DIR}/../scripts/lib"
  fi
  if [[ -f "$_p15_lib_dir/prereq_probe.sh" ]]; then
    # Source the SSOT prereq lib. Export COORDINATOR_PREREQ_PROBE_LIB_DIR so its
    # internal sibling-sources (manifest_reader.sh, step_zero_emit.sh) resolve correctly.
    # Review: code-reviewer — F5-A: combined split export+assignment into single line
    #   to ensure the exported value is the resolved absolute path, not the original.
    export COORDINATOR_PREREQ_PROBE_LIB_DIR="$(cd "$_p15_lib_dir" && pwd)"
    # shellcheck source=../scripts/lib/prereq_probe.sh
    if source "$_p15_lib_dir/prereq_probe.sh" 2>/dev/null; then
      # Capture all 10 NDJSON rows from the aggregator.
      _p15_ndjson="$(_co_prereq_probe_all 2>/dev/null || true)"
      if [[ -z "$_p15_ndjson" ]]; then
        note_red "P-15" "prereq_probe_all emitted no output — check scripts/lib/prereq_probe.sh"
      else
        # Parse: only hard-severity rows with status=fail drive RED.
        # Advisory-tier (warn/inconclusive on advisory/semi-hard) → skip silently.
        _p15_hard_fails=""
        while IFS= read -r _p15_row; do
          [[ -z "$_p15_row" ]] && continue
          # Extract name, status, severity using portable sed (no grep -P).
          _p15_name="$(printf '%s' "$_p15_row"   | sed 's/.*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' 2>/dev/null || true)"
          _p15_status="$(printf '%s' "$_p15_row" | sed 's/.*"status"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' 2>/dev/null || true)"
          _p15_sev="$(printf '%s' "$_p15_row"    | sed 's/.*"severity"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' 2>/dev/null || true)"
          # Review: code-reviewer — F4-A: guard against unextractable/corrupt rows;
          #   skip rather than mis-counting an empty name/status/severity.
          [[ -z "$_p15_name" || -z "$_p15_status" || -z "$_p15_sev" ]] && continue
          # Only hard-severity fail rows count as RED.
          if [[ "$_p15_status" == "fail" && "$_p15_sev" == "hard" ]]; then
            if [[ -z "$_p15_hard_fails" ]]; then
              _p15_hard_fails="$_p15_name"
            else
              _p15_hard_fails="$_p15_hard_fails, $_p15_name"
            fi
          fi
          # semi-hard + warn (clone_auth with no-auth) → GREEN at doctor level.
          # advisory warn (uv, pwsh, ue, longpaths, git_lfs) → GREEN at doctor level.
          # inconclusive → GREEN at doctor level (cannot determine, do not block).
        done <<< "$_p15_ndjson"
        if [[ -n "$_p15_hard_fails" ]]; then
          note_red "P-15" "hard system-prerequisite(s) absent: $_p15_hard_fails — install via coordinator:install or see remediation"
        fi
        # Advisory-only result or all pass → no note; probe contributes GREEN.
      fi
    else
      # prereq_probe.sh failed to source — inconclusive; treat as amber (not red).
      note_amber "P-15" "could not source prereq_probe.sh from $_p15_lib_dir — inconclusive; re-run /coordinator:install"
    fi
  fi
  # If prereq_probe.sh is absent (pre-ship install), silently skip.
fi

# --- P-17: macOS bash login-shell orphan check (SSOT: scripts/lib/prereq_probe.sh) ---
# spec-backlink: coordinator-doctor.md § P-17
# Delegates to _co_probe_shell_login_env from prereq_probe.sh — same SSOT the install
# Step Zero gate uses. Non-macOS machines and non-bash login shells pass immediately.
# fail   → RED (error): bash login shell has orphaned ~/.local/bin; claude won't resolve.
# inconclusive → skip: cannot probe the login shell (advisory; do not block).
# pass   → no action (GREEN).
# Sourcing discipline: COORDINATOR_PREREQ_PROBE_LIB_DIR is honored so tests can inject
# a fake prereq_probe.sh. The idempotency guard in prereq_probe.sh makes re-sourcing
# cheap when P-15 already ran in the same sentinel invocation.
if is_active "P-17"; then
  if [[ -n "${COORDINATOR_PREREQ_PROBE_LIB_DIR:-}" ]]; then
    _p17_lib_dir="$COORDINATOR_PREREQ_PROBE_LIB_DIR"
  else
    _p17_lib_dir="${_SCRIPT_DIR}/../scripts/lib"
  fi
  if [[ -f "$_p17_lib_dir/prereq_probe.sh" ]]; then
    export COORDINATOR_PREREQ_PROBE_LIB_DIR="$(cd "$_p17_lib_dir" && pwd)"
    # shellcheck source=../scripts/lib/prereq_probe.sh
    if source "$_p17_lib_dir/prereq_probe.sh" 2>/dev/null; then
      _p17_row="$(_co_probe_shell_login_env 2>/dev/null || true)"
      if [[ -z "$_p17_row" ]]; then
        note_amber "P-17" "shell_login_env probe emitted no output — check scripts/lib/prereq_probe.sh"
      else
        _p17_status="$(printf '%s' "$_p17_row" | sed 's/.*"status"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' 2>/dev/null || true)"
        _p17_detail="$(printf '%s' "$_p17_row" | sed 's/.*"detail"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' 2>/dev/null || true)"
        case "$_p17_status" in
          fail)
            note_red "P-17" "bash login-shell orphan: ${_p17_detail:-orphaned ~/.local/bin or claude not found}"
            ;;
          inconclusive)
            : # Cannot probe the login shell — advisory skip; do not block.
            ;;
          pass|*)
            : # pass, non-applicable (non-macOS/non-bash), or unextractable status — conservative GREEN
            ;;
        esac
      fi
    else
      # prereq_probe.sh failed to source — inconclusive; treat as amber.
      note_amber "P-17" "could not source prereq_probe.sh from $_p17_lib_dir — inconclusive; re-run /coordinator:install"
    fi
  fi
  # prereq_probe.sh absent (pre-ship install) → silently skip.
fi

# --- P-14: bare-name resolution of ~/.claude/bin resolvers (macOS regression net) ---
# spec-backlink: docs/plans/2026-06-18-machine-local-bare-invocation-macos.md § C3
# P-4/P-10 resolve ml_cmd/ch_cmd ABSOLUTE-path-first, so they pass even when bare-name
# resolution is broken (the macOS ~/.claude/bin-not-on-PATH bug). This probe asserts the
# bare names resolve on PATH (via the coordinator/bin forwarders), catching that regression.
if is_active "P-14"; then
  _bare_missing=""
  command -v machine-local >/dev/null 2>&1 || _bare_missing="machine-local"
  # builds "machine-local, claude-home" or just the single missing name
  # Review: code-reviewer slice1-F5 — clarifying comment on concatenation idiom
  command -v claude-home  >/dev/null 2>&1 || _bare_missing="${_bare_missing:+$_bare_missing, }claude-home"
  if [[ -n "$_bare_missing" ]]; then
    note_red "P-14" "bare-name resolver(s) not on PATH: $_bare_missing — coordinator/bin forwarder missing; re-run /coordinator:install (Phase 3)"
  fi
fi

# P-18 — install singularity: exactly one coordinator install tree at ~/.claude,
# consistent marketplace registration, no doubled .claude/.claude venv pin. A split
# install silently loads a stale coordinator copy (the 2026-06-26 three-tree failure).
# The check exempts a single explicit COORDINATOR_CLONE/ROOT dev-loop override.
if is_active "P-18"; then
  _p18_check="${_SCRIPT_DIR}/../lib/check-install-singularity.sh"
  if [[ -x "$_p18_check" ]]; then
    # Review: code-reviewer — B-F1: pass _ORIGINAL_CLAUDE_HOME (HOME-substitute) so
    # check-install-singularity.sh applies its own §4a convention, not our .claude-suffixed local.
    # Review: code-reviewer — B-F3: amber on absent script so corruption doesn't silently GREEN.
    if ! _p18_out="$(CLAUDE_HOME="${_ORIGINAL_CLAUDE_HOME}" "$_p18_check" 2>&1)"; then
      note_red "P-18" "install singularity check failed: ${_p18_out%%$'\n'*} — reconcile to a single ~/.claude install; re-run /coordinator:install"
    fi
  else
    note_amber "P-18" "singularity check script absent/not-executable at $_p18_check — plugin may be corrupted; reinstall coordinator"
  fi
fi

# ---------------------------------------------------------------------------
# Verdict synthesis (shared by all modes)
# ---------------------------------------------------------------------------

if [[ "${#red_probes[@]}" -gt 0 ]]; then
  verdict="RED"
elif [[ "${#amber_probes[@]}" -gt 0 ]]; then
  verdict="AMBER"
else
  verdict="GREEN"
fi

if [[ "$verdict" == "GREEN" ]]; then
  hint="All coordinator-doctor probes passed."
else
  # Join hint lines with " | " for single-line sentinel hint field.
  hint=""
  for line in "${hint_lines[@]}"; do
    if [[ -z "$hint" ]]; then hint="$line"; else hint="$hint | $line"; fi
  done
fi

# ---------------------------------------------------------------------------
# Mode-specific output / write behavior
# ---------------------------------------------------------------------------

if [[ "$MODE" == "full" ]]; then
  # --- Machine info (informational — NOT a probe; --full only) ---------------
  # Surface host OS / GPU / Python / uv inventory in the doctor record so the
  # doctor is a visible "what host am I on" surface (PM request 2026-05-27).
  # Diagnostic only — never RED/AMBER (there is no "wrong" GPU). Gated on P-5
  # (package importable); empty object if the package or CLI is unavailable.
  # Human one-liner: `python -m coordinator_whoami.machine --human`.
  machine_json="{}"
  if _whoami_importable; then
    _machine_out="$("$PY" -m coordinator_whoami.machine 2>/dev/null || true)"
    [[ -n "$_machine_out" ]] && machine_json="$_machine_out"
  fi

  ran_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  # Write sentinel (--full ONLY — subset modes MUST NOT overwrite the daily
  # sentinel; a partial-subset verdict would corrupt the ambient health signal
  # scan-addon-health.sh reads). Gate is MODE == full.
  if ! RED_PROBES_CSV="$(IFS=,; echo "${red_probes[*]:-}")" \
       AMBER_PROBES_CSV="$(IFS=,; echo "${amber_probes[*]:-}")" \
       RAN_AT="$ran_at" \
       VERDICT="$verdict" \
       HINT="$hint" \
       MACHINE_JSON="$machine_json" \
       SENTINEL_PATH="$SENTINEL_PATH" \
       "$PY" -c "
import json, os
red = [p for p in os.environ['RED_PROBES_CSV'].split(',') if p]
amber = [p for p in os.environ['AMBER_PROBES_CSV'].split(',') if p]
try:
    machine = json.loads(os.environ.get('MACHINE_JSON') or '{}')
except (ValueError, TypeError):
    machine = {}
payload = {
    'ran_at':       os.environ['RAN_AT'],
    'verdict':      os.environ['VERDICT'],
    'red_probes':   red,
    'amber_probes': amber,
    'hint':         os.environ['HINT'],
    'machine':      machine,
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

else
  # --- Subset mode (triage / cluster / probe / symptom) ---
  # Print structured read to stdout; do NOT write sentinel.

  echo "[coordinator-doctor] MODE=$MODE verdict=$verdict"

  if [[ "${#red_probes[@]}" -gt 0 || "${#amber_probes[@]}" -gt 0 ]]; then
    _all_failing="${red_probes[*]:-} ${amber_probes[*]:-}"
    echo "  Failing: $(echo "$_all_failing" | xargs)"
    echo "  Hint: $hint"
  else
    echo "  All selected probes passed."
  fi

  if [[ "$MODE" == "triage" ]]; then
    # Emit RECOMMENDATION: name the cluster(s) of failing triage probes and
    # suggest --cluster <name> or --full. Do NOT auto-run the cluster.
    if [[ "${#red_probes[@]}" -gt 0 || "${#amber_probes[@]}" -gt 0 ]]; then
      _failing_ids=()
      [[ "${#red_probes[@]}" -gt 0 ]] && _failing_ids+=("${red_probes[@]}")
      [[ "${#amber_probes[@]}" -gt 0 ]] && _failing_ids+=("${amber_probes[@]}")

      # Resolve cluster for each failing probe id via the selector's --id-to-cluster
      # mode. Strip \r so the dedup compare is robust against Windows CRLF output.
      _rec_clusters=()
      _MANIFEST="${DOCTOR_PROBES_MANIFEST:-${_SCRIPT_DIR}/doctor-probes.toml}"
      for _fid in "${_failing_ids[@]}"; do
        _c="$(DOCTOR_PROBES_MANIFEST="$_MANIFEST" "$PY" "$_SELECTOR" --id-to-cluster "$_fid" 2>/dev/null | tr -d '\r' || true)"
        if [[ -n "$_c" ]]; then
          # Append cluster only if not already in recommendation list.
          _already=0
          for _ec in "${_rec_clusters[@]+"${_rec_clusters[@]}"}"; do
            [[ "$_ec" == "$_c" ]] && _already=1 && break
          done
          [[ "$_already" -eq 0 ]] && _rec_clusters+=("$_c")
        fi
      done

      echo ""
      echo "  RECOMMENDATION: triage found failing probes."
      for _rc in "${_rec_clusters[@]+"${_rec_clusters[@]}"}"; do
        echo "    Run: $0 --cluster $_rc"
      done
      echo "    Or run: $0 --full  (to run all probes and write the health sentinel)"
    else
      echo ""
      echo "  RECOMMENDATION: triage probes all passed. Run '$0 --full' for complete health check."
    fi
  fi

  # Subset modes always exit 0 (a successful probe run; the verdict is in stdout).
  exit 0
fi
