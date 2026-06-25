#!/usr/bin/env bash
# dep_check.sh — Phase 0 dependency-chain gate for deep-research setup.sh.
#
# Purpose: implements the consent gate, dep probing, agent-mode detection, and
# visited-set helpers that setup.sh uses during Phase 0 (pre-preflight).
# All Phase 0 logic lives here, never inline in setup.sh.
#
# Spec backlink: docs/plans/2026-06-15-deep-research-install-chain-application-phase-b.md §7 C3
# Spec backlink: plugins/coordinator/docs/wiki/agent-install-contract.md §Dual-mode script UX
#
# Functions exported by this file:
#   _dr_phase_zero_should_run  — allowlist check; returns 0 (run) or 1 (skip)
#   _dr_run_mode_prompt        — agent-direct y/N prompt (a); exits 92 on agent-mode
#   _dr_dep_probe <dep-id>     — runs functional probe; echoes present/missing/present-but-broken
#   _dr_dep_probe_all          — NDJSON one line per dep with {id, severity, status, sibling_path, hint}
#   _dr_file_mtime_s           — portable file mtime in epoch seconds (BSD/GNU/date-r probe)
#   _dr_visited_set_crash_cleanup — Phase 0 entry crash-recovery reaper (>5 min TTL, age-only)
#   _dr_visited_set_init <session-id>   — creates visited-set file, stale-cleans >1h files
#   _dr_visited_set_check <session-id> <dep-id>  — 0 if already visited, 1 if not
#   _dr_visited_set_append <session-id> <dep-id> — atomic read-modify-write append
#   _dr_consent_gate           — emits banner, runs confirmation; exits 90/91/93 per §3.3
#
# Visited-set keyspace: ~/.claude/deep-research-claude/chain-walk-<session-id>.json
# (per agent-install-contract.md § Visited-set protocol; the Staff Engineer Finding 4 correction)
#
# Exit codes used by this file (canonical per §3.3):
#   90 — hard dep missing in non-TTY / non-interactive context, no flag pair
#   91 — double-confirm declined under TTY (user answered N to either prompt)
#   92 — agent-direct-invocation detected (--i-am-agent or agent-mode detection)
#   93 — override-flag-pair-incomplete (only one of the two flags provided)

# ---------------------------------------------------------------------------
# Guard: source vendored coordinator_prereq/manifest_reader.sh if not already loaded.
# ---------------------------------------------------------------------------
_DR_DEP_CHECK_LOADED="${_DR_DEP_CHECK_LOADED:-0}"
if [[ "$_DR_DEP_CHECK_LOADED" == "1" ]]; then
  return 0 2>/dev/null || true
fi
_DR_DEP_CHECK_LOADED=1

_dep_check_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=plugins/deep-research/scripts/lib/coordinator_prereq/manifest_reader.sh
source "$_dep_check_lib_dir/coordinator_prereq/manifest_reader.sh" 2>/dev/null || {
  echo "ERROR: dep_check.sh: cannot source coordinator_prereq/manifest_reader.sh from $_dep_check_lib_dir" >&2
  exit 1
}

# ---------------------------------------------------------------------------
# _dr_phase_zero_should_run
#
# Purpose: single greppable allowlist of read-only flags that skip Phase 0
# (the consent gate + dep chain walk) entirely. If any of these flags are
# present in the caller's parsed state variables, Phase 0 is skipped.
#
# The allowlist is intentionally a comment block so it is greppable from any
# context — doc readers, agents, and auditors can find it with:
#   grep -A10 'READ_ONLY_FLAG_ALLOWLIST' scripts/lib/dep_check.sh
#
# READ_ONLY_FLAG_ALLOWLIST (Phase 0 skip set — canonical per agent-install-contract.md):
#   --help          (script exits 0 with usage text, no side effects)
#   --version       (script exits 0 with version string, no side effects)
#   --phase-list    (script exits 0 with phase list, no side effects)
#   --last-status   (script exits 0 with install status JSON, no side effects)
#   --i-am-agent    (exits 92 before Phase 0; listed here for allowlist completeness)
#   --check         (DR-specific read-only extension per contract § Read-only flag carve-out)
# END_READ_ONLY_FLAG_ALLOWLIST
#
# Returns: 0 = Phase 0 should run; 1 = Phase 0 should be skipped.
# Callers: setup.sh _run_all_phases, and anywhere Phase 0 is guarded.
# ---------------------------------------------------------------------------
_dr_phase_zero_should_run() {
  # These variables must be set by setup.sh's argument parser before
  # this function is called. Defaults to false/empty if not set (safe to call
  # in testing without the full parser context).
  local _help="${HELP_FLAG:-false}"
  local _version="${VERSION_FLAG:-false}"
  local _phase_list="${PHASE_LIST:-false}"
  local _last_status="${LAST_STATUS:-false}"
  local _i_am_agent="${I_AM_AGENT:-false}"
  local _check="${CHECK_FLAG:-false}"

  # READ_ONLY_FLAG_ALLOWLIST check — any read-only flag → skip Phase 0.
  if [[ "$_help" == true || "$_version" == true || \
        "$_phase_list" == true || "$_last_status" == true || \
        "$_i_am_agent" == true || "$_check" == true ]]; then
    return 1  # skip Phase 0
  fi
  return 0  # run Phase 0
}

# ---------------------------------------------------------------------------
# _dr_run_mode_prompt
#
# Purpose: implements step (a) of the dual-mode UX PM directive:
#   "Are you running this script as an autonomous agent rather than via
#    /deep-research:setup? [y/N]"
#
# Behavior per §3.1(ii):
#   - --i-am-agent / DEEP_RESEARCH_RUN_MODE=agent → exits 92 immediately with
#     AGENT_MANIFEST_PATH on stderr (agent-direct-invocation detected).
#   - --i-am-human / DEEP_RESEARCH_RUN_MODE=human → returns 0 (proceed as human).
#   - --non-interactive / non-TTY → prompt is SKIPPED ENTIRELY (implicit human).
#     Avoids prompt text in CI logs per N-2.
#   - TTY without flags → print prompt, read reply; y → exit 92, N → return 0.
#
# Callers must check _dr_phase_zero_should_run first; this function is not
# called when Phase 0 is skipped.
#
# Variables consumed (set by setup.sh argument parser):
#   I_AM_AGENT, I_AM_HUMAN, DEEP_RESEARCH_RUN_MODE, NON_INTERACTIVE
# ---------------------------------------------------------------------------
_dr_run_mode_prompt() {
  local _run_mode="${DEEP_RESEARCH_RUN_MODE:-}"
  local _i_am_agent="${I_AM_AGENT:-false}"
  local _i_am_human="${I_AM_HUMAN:-false}"
  local _non_interactive="${NON_INTERACTIVE:-true}"

  # Agent-mode detection: explicit flag or env var.
  if [[ "$_i_am_agent" == true || "$_run_mode" == "agent" ]]; then
    local _manifest_rel="docs/install/AGENT.md"
    echo "AGENT_MANIFEST_PATH=${_manifest_rel}" >&2
    echo "[setup] Agent-direct invocation detected. Use /deep-research:setup instead." >&2
    echo "[setup] Agent install guide: ${_manifest_rel}" >&2
    exit 92
  fi

  # Human-mode: explicit flag or env var → skip prompt, proceed.
  if [[ "$_i_am_human" == true || "$_run_mode" == "human" ]]; then
    return 0
  fi

  # Non-interactive / non-TTY → prompt skipped entirely (implicit human, per N-2).
  if [[ "$_non_interactive" == true || ! -t 0 ]]; then
    return 0
  fi

  # Interactive TTY without flags → print the (a) prompt.
  printf "[setup] Are you running this script as an autonomous agent rather than via /deep-research:setup? [y/N] " >&2
  local _reply=""
  read -r _reply || _reply=""
  if [[ "$_reply" == "y" || "$_reply" == "Y" ]]; then
    local _manifest_rel="docs/install/AGENT.md"
    echo "" >&2
    echo "AGENT_MANIFEST_PATH=${_manifest_rel}" >&2
    echo "[setup] Agent-direct invocation confirmed. Use /deep-research:setup instead." >&2
    echo "[setup] Agent install guide: ${_manifest_rel}" >&2
    exit 92
  fi
  return 0
}

# ---------------------------------------------------------------------------
# _dr_dep_probe <dep-id>
#
# Purpose: run the manifest's functional probe for a given dep id.
# Echoes one of: present / missing / present-but-broken
#
# Probe kinds (per §3.1 functional probe kinds):
#   sibling_dir_exists — sibling folder present (implicit, always runs first)
#   file_exists        — given file exists relative to sibling root
#   python_import      — given import expression succeeds via resolved Python
#   command_succeeds   — given shell command exits zero
#
# Arguments:
#   $1 — dep id (e.g. "coordinator-claude")
#
# Variables consumed:
#   REPO_ROOT — repository root (set by setup.sh)
# ---------------------------------------------------------------------------
_dr_dep_probe() {
  local _dep_id="$1"
  local _repo_root="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
  local _sibling_root
  _sibling_root="$(cd "$_repo_root/.." && pwd)"

  # Parse manifest to find this dep's entry.
  local _dep_json=""
  local _python
  _python="$(_co_find_python 2>/dev/null)" || {
    echo "missing"
    return 0
  }

  # _co_manifest_read_ndjson with no args relies on REPO_ROOT being pre-set by the
  # caller (setup.sh exports it). Standalone use without REPO_ROOT will fail to
  # locate the manifest.
  _dep_json="$(_co_manifest_read_ndjson 2>/dev/null | \
    "$_python" -c "
import json, sys
dep_id = sys.argv[1]
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
        if obj.get('id') == dep_id:
            print(json.dumps(obj))
            break
    except json.JSONDecodeError:
        pass
" "$_dep_id" 2>/dev/null)"

  if [[ -z "$_dep_json" ]]; then
    echo "missing"
    return 0
  fi

  # Extract fields from the dep JSON.
  local _sibling_dir _probe_kind
  _sibling_dir="$("$_python" -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('sibling_dir_name',''))" "$_dep_json" 2>/dev/null)"
  _probe_kind="$("$_python" -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('functional_probe_kind',''))" "$_dep_json" 2>/dev/null)"

  local _sibling_path="$_sibling_root/$_sibling_dir"

  # Step 1: implicit sibling_dir_exists probe (always runs first).
  # Nested-layout fallback: in the working meta-repo, coordinator-claude is not a sibling
  # repo at `../coordinator-claude/` but rather a subfolder at `../coordinator/` (both
  # deep-research and coordinator live under plugins/coordinator-claude/).
  # The sibling_dir_name contract field is shaped for the flat publish-repo layout
  # (X:\deep-research-claude and X:\coordinator-claude as siblings). In working-repo layout
  # we strip the "-claude" suffix and check the sub-folder convention.
  # Review: code-reviewer — P1 bug: nested-layout probe always returned "missing" because
  # ~/.claude/plugins/coordinator-claude/coordinator-claude doesn't exist; the actual path
  # is ~/.claude/plugins/coordinator-claude/coordinator.
  if [[ ! -d "$_sibling_path" ]]; then
    local _bare_name="${_sibling_dir%-claude}"
    if [[ -n "$_bare_name" && -d "$_sibling_root/$_bare_name" ]]; then
      # Nested-layout: use the "-claude"-stripped sub-folder path.
      _sibling_path="$_sibling_root/$_bare_name"
    else
      echo "missing"
      return 0
    fi
  fi

  # Step 2: functional probe.
  case "$_probe_kind" in
    sibling_dir_exists)
      # Sibling dir exists (already confirmed above).
      echo "present"
      ;;
    file_exists)
      local _rel_path
      _rel_path="$("$_python" -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('functional_probe_args',{}).get('path',''))" "$_dep_json" 2>/dev/null)"
      if [[ -f "$_sibling_path/$_rel_path" ]]; then
        echo "present"
      else
        echo "present-but-broken"
      fi
      ;;
    python_import)
      local _expr
      _expr="$("$_python" -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('functional_probe_args',{}).get('expr',''))" "$_dep_json" 2>/dev/null)"
      local _python_probe
      _python_probe="$(_co_find_python 2>/dev/null)" || { echo "present-but-broken"; return 0; }
      # Run from caller's cwd, NOT from sibling dir — the probe must match the
      # runtime's actual sys.path resolution (post-`pip install --system -e`).
      # cd-into-sibling would mask the partial-install state the consent gate
      # is supposed to detect (sibling files present but not pip-installed).
      # Parity with PS half: scripts/lib/dep_check.ps1 python_import branch.
      if "$_python_probe" -c "$_expr" >/dev/null 2>&1; then
        echo "present"
      else
        echo "present-but-broken"
      fi
      ;;
    command_succeeds)
      local _cmd
      _cmd="$("$_python" -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('functional_probe_args',{}).get('cmd',''))" "$_dep_json" 2>/dev/null)"
      if bash -c "$_cmd" >/dev/null 2>&1; then
        echo "present"
      else
        echo "present-but-broken"
      fi
      ;;
    *)
      # Unknown probe kind — treat sibling presence as sufficient.
      echo "present"
      ;;
  esac
}

# ---------------------------------------------------------------------------
# _dr_dep_probe_all
#
# Purpose: probe all direct_deps from the manifest and emit NDJSON.
# Output: one line per dep, fields: {id, severity, status, sibling_path, hint}
# Statuses: present / missing / present-but-broken
#
# Concurrency-safe: one line per dep (per §5 constraint f).
# ---------------------------------------------------------------------------
_dr_dep_probe_all() {
  local _repo_root="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
  local _sibling_root
  _sibling_root="$(cd "$_repo_root/.." && pwd)"
  local _python
  _python="$(_co_find_python 2>/dev/null)" || return 1

  while IFS= read -r _dep_line; do
    [[ -z "$_dep_line" ]] && continue
    local _id _severity _sibling_dir _upstream_url
    _id="$("$_python" -c "import json,sys; print(json.loads(sys.argv[1]).get('id',''))" "$_dep_line" 2>/dev/null)"
    _severity="$("$_python" -c "import json,sys; print(json.loads(sys.argv[1]).get('severity',''))" "$_dep_line" 2>/dev/null)"
    _sibling_dir="$("$_python" -c "import json,sys; print(json.loads(sys.argv[1]).get('sibling_dir_name',''))" "$_dep_line" 2>/dev/null)"
    _upstream_url="$("$_python" -c "import json,sys; print(json.loads(sys.argv[1]).get('upstream_url',''))" "$_dep_line" 2>/dev/null)"

    local _sibling_path="$_sibling_root/$_sibling_dir"
    # Nested-layout fallback: mirror the same strip-"-claude" logic as _dr_dep_probe
    # so the sibling_path field in NDJSON output reflects the actual resolved path.
    if [[ ! -d "$_sibling_path" ]]; then
      local _bare="${_sibling_dir%-claude}"
      if [[ -n "$_bare" && -d "$_sibling_root/$_bare" ]]; then
        _sibling_path="$_sibling_root/$_bare"
      fi
    fi
    local _status
    _status="$(_dr_dep_probe "$_id")"

    local _hint=""
    case "$_status" in
      missing)
        _hint="Clone from: $_upstream_url"
        ;;
      present-but-broken)
        _hint="Sibling present but functional probe failed. Re-install or check: $_sibling_path"
        ;;
      present)
        _hint=""
        ;;
    esac

    "$_python" -c "
import json, sys
print(json.dumps({
    'id': sys.argv[1],
    'severity': sys.argv[2],
    'status': sys.argv[3],
    'sibling_path': sys.argv[4],
    'hint': sys.argv[5],
}))
" "$_id" "$_severity" "$_status" "$_sibling_path" "$_hint"
  # _co_manifest_read_ndjson with no args relies on REPO_ROOT being pre-set by the
  # caller (setup.sh exports it). Standalone use without REPO_ROOT will fail to
  # locate the manifest.
  done < <(_co_manifest_read_ndjson 2>/dev/null)
}

# ---------------------------------------------------------------------------
# _dr_file_mtime_s
#
# Portable file-mtime helper.  GNU coreutils `date -r FILE` reads file mtime;
# BSD/macOS `date -r SECONDS` interprets the arg as an epoch — so the GNU form
# silently degrades to mtime=0 on macOS (every file then reads as "all stale",
# bypassing every threshold check).  Probe `stat` flavors first, fall back to
# `date -r` only when no `stat` is available.
# Each probe output is validated as numeric before use; non-numeric output
# (e.g. BSD stat returning empty on error) falls through to the next probe.
# ---------------------------------------------------------------------------
_dr_file_mtime_s() {
  local _f="$1"
  local _v
  _v=$(stat -f %m "$_f" 2>/dev/null) && [[ "$_v" =~ ^[0-9]+$ ]] && printf '%s\n' "$_v" && return 0  # BSD / macOS
  _v=$(stat -c %Y "$_f" 2>/dev/null) && [[ "$_v" =~ ^[0-9]+$ ]] && printf '%s\n' "$_v" && return 0  # GNU coreutils
  _v=$(date -r "$_f" +%s 2>/dev/null) && [[ "$_v" =~ ^[0-9]+$ ]] && printf '%s\n' "$_v" && return 0  # last resort (GNU date only)
  echo 0
}

# ---------------------------------------------------------------------------
# _dr_visited_set_crash_cleanup
#
# Purpose: Phase 0 entry crash-recovery reaper for orphan visited-set files.
#
# A crashed install (SIGKILL, power loss, Ctrl-C) leaves a chain-walk-*.json
# file on disk whose session-id is no longer active.  The session-start janitor
# (_dr_visited_set_init) uses a 1h TTL, so a retry within that window silently
# treats the stale file as an in-progress session and skips dep installation.
# This pass uses a 5-minute TTL instead, targeting exactly that crash-retry window.
#
# Visited-set keyspace: ~/.claude/deep-research-claude/
# (per agent-install-contract.md § Visited-set protocol; the Staff Engineer Finding 4 correction)
#
# Complementary surfaces:
#   _dr_visited_set_init  — session-start janitor, 1h TTL (DO NOT MODIFY)
#   Initialize-DrVisitedSetCrashCleanup — PowerShell parity (dep_check.ps1)
# ---------------------------------------------------------------------------
_dr_visited_set_crash_cleanup() {
  local _dr_dir="$HOME/.claude/deep-research-claude"
  [[ -d "$_dr_dir" ]] || return 0  # nothing to clean

  local _now
  _now="$(date +%s)"
  local _stale_threshold=300  # 5 minutes in seconds

  for _candidate in "$_dr_dir"/chain-walk-*.json; do
    [[ -f "$_candidate" ]] || continue
    local _mtime
    _mtime="$(_dr_file_mtime_s "$_candidate")"
    local _age=$(( _now - _mtime ))
    if [[ "$_age" -gt "$_stale_threshold" ]]; then
      rm -f "$_candidate"
    fi
  done
}

# ---------------------------------------------------------------------------
# _dr_visited_set_init <session-id>
#
# Purpose: create ~/.claude/deep-research-claude/chain-walk-<session-id>.json
# visited-set file. Stale-cleans any existing chain-walk-*.json files older
# than 1 hour.
#
# Keyspace: ~/.claude/deep-research-claude/ per contract § Visited-set protocol.
# Schema: {"session_id": "<uuid>", "started_at": "<ISO8601>", "visited": []}
# ---------------------------------------------------------------------------
_dr_visited_set_init() {
  local _session_id="$1"
  local _dr_dir="$HOME/.claude/deep-research-claude"
  mkdir -p "$_dr_dir"

  # Stale-cleanup: delete chain-walk-*.json files older than 1 hour.
  local _now
  _now="$(date +%s)"
  for _stale_file in "$_dr_dir"/chain-walk-*.json; do
    [[ -f "$_stale_file" ]] || continue
    local _mtime
    _mtime="$(_dr_file_mtime_s "$_stale_file")"
    local _age=$(( _now - _mtime ))
    if [[ "$_age" -gt 3600 ]]; then
      rm -f "$_stale_file"
    fi
  done

  local _visited_file="$_dr_dir/chain-walk-${_session_id}.json"
  local _python
  _python="$(_co_find_python)" || return 1

  local _started_at
  _started_at="$("$_python" -c "import datetime; print(datetime.datetime.utcnow().isoformat() + 'Z')" 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"

  "$_python" -c "
import json, sys
data = {
    'session_id': sys.argv[1],
    'started_at': sys.argv[2],
    'visited': [],
}
with open(sys.argv[3], 'w', encoding='utf-8') as f:
    json.dump(data, f)
" "$_session_id" "$_started_at" "$_visited_file"
}

# ---------------------------------------------------------------------------
# _dr_visited_set_check <session-id> <dep-id>
#
# Purpose: check whether a dep-id is already in the visited set.
# Returns: 0 if already visited (skip), 1 if not visited (proceed).
#
# Atomic read semantics: reads the file in a single Python invocation.
# ---------------------------------------------------------------------------
_dr_visited_set_check() {
  local _session_id="$1"
  local _dep_id="$2"
  local _visited_file="$HOME/.claude/deep-research-claude/chain-walk-${_session_id}.json"
  local _python
  _python="$(_co_find_python)" || return 1

  if [[ ! -f "$_visited_file" ]]; then
    return 1  # file doesn't exist → not visited
  fi

  "$_python" -c "
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as f:
    data = json.load(f)
visited = data.get('visited', [])
dep_id = sys.argv[2]
sys.exit(0 if dep_id in visited else 1)
" "$_visited_file" "$_dep_id"
}

# ---------------------------------------------------------------------------
# _dr_visited_set_append <session-id> <dep-id>
#
# Purpose: atomically append dep-id to the visited set (read-modify-write).
# Uses a single Python invocation to avoid TOCTOU races.
# ---------------------------------------------------------------------------
_dr_visited_set_append() {
  local _session_id="$1"
  local _dep_id="$2"
  local _visited_file="$HOME/.claude/deep-research-claude/chain-walk-${_session_id}.json"
  local _python
  _python="$(_co_find_python)" || return 1

  "$_python" -c "
import json, sys, os, tempfile

visited_file = sys.argv[1]
dep_id = sys.argv[2]

if not os.path.isfile(visited_file):
    print('ERROR: visited-set file not found: ' + visited_file, file=sys.stderr)
    sys.exit(1)

with open(visited_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

visited = data.get('visited', [])
if dep_id not in visited:
    visited.append(dep_id)
    data['visited'] = visited

# Atomic write via temp file + rename.
dir_ = os.path.dirname(visited_file)
with tempfile.NamedTemporaryFile('w', dir=dir_, delete=False, suffix='.tmp',
                                  encoding='utf-8') as tmp:
    json.dump(data, tmp)
    tmp_path = tmp.name
os.replace(tmp_path, visited_file)
" "$_visited_file" "$_dep_id"
}

# ---------------------------------------------------------------------------
# Override-flag convention — cross-repo localization (ratified 2026-05-09)
#
# Convention: --skip-dep-check + --accept-<repo-risk>-risk
#
# Each repo in the multi-RAG-coexistence split names its own risk class;
# cross-repo greppability is preserved via the --accept-[a-z-]+-risk regex.
#
# deep-research-claude risk class: vestigial-path (single soft dep on coordinator-claude).
# The flag fires only when coordinator-claude is declared as a soft dep but absent AND
# the user opts out of the default warn-and-continue behaviour by explicitly requesting
# override. When an operator passes this flag, they accept that setup proceeds without
# the coordinator-claude dep check, treating the soft dep as waived.
#
# Flag pair for deep-research-claude:
#   --skip-dep-check + --accept-missing-deps-risk
# (predecessor §7.2 PM-ratified vestigial-path naming)
#
# Authoritative DR: plugins/coordinator/docs/wiki/agent-install-contract.md
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _dr_consent_gate
#
# Purpose: emit the verbatim dep_consent_banner.txt with missing-dep list
# filled in, then enforce the confirmation protocol per §3.3 gate-behavior.
#
# Gate behavior (canonical):
#   TTY, no flag pair           → banner → confirm 1 → confirm 2 → proceed; exit 91 on N
#   Non-TTY, no flag pair       → banner → exit 90
#   TTY, both flags             → banner once → one-line acknowledgment → proceed
#   Non-TTY, both flags         → banner to stderr → proceed
#   Either, only one flag       → exit 93
#
# Variables consumed (set by setup.sh argument parser):
#   SKIP_DEP_CHECK, ACCEPT_MISSING_DEPS_RISK, NON_INTERACTIVE
#
# Note: the variable name is ACCEPT_MISSING_DEPS_RISK (matching setup.sh:196,210).
# Review: code-reviewer — P1 bug: was ACCEPT_HALLUCINATION_RISK (stale name from an
# earlier spec draft); setup.sh exports ACCEPT_MISSING_DEPS_RISK so the gate would
# always see false → exit 93 even when both override flags were supplied.
# ---------------------------------------------------------------------------
_dr_consent_gate() {
  local _skip_dep_check="${SKIP_DEP_CHECK:-false}"
  local _accept_risk="${ACCEPT_MISSING_DEPS_RISK:-false}"
  local _non_interactive="${NON_INTERACTIVE:-true}"

  # Incomplete flag pair → exit 93 unconditionally (before dep probe, independent of dep state).
  # §3.3: "Either, only one of two flags → exit 93 (override-flag-pair-incomplete)"
  if [[ "$_skip_dep_check" == true && "$_accept_risk" != true ]]; then
    echo "ERROR: --skip-dep-check requires --accept-missing-deps-risk (exit 93: override-flag-pair-incomplete)" >&2
    echo "  Pass both flags together: --skip-dep-check --accept-missing-deps-risk" >&2
    exit 93
  elif [[ "$_skip_dep_check" != true && "$_accept_risk" == true ]]; then
    echo "ERROR: --accept-missing-deps-risk requires --skip-dep-check (exit 93: override-flag-pair-incomplete)" >&2
    echo "  Pass both flags together: --skip-dep-check --accept-missing-deps-risk" >&2
    exit 93
  fi

  # Note: DR currently declares no `hard` deps (one soft only).
  # The banner-render and confirm flow below (lines ~565+) is structurally unreachable
  # for v1/v2 schema in this repo, but kept intact for parity with the
  # holodeck/project-rag template and forward-compat if DR ever promotes a dep to hard.
  # Review: code-reviewer — P2: dead code identified; comment added to make the intent
  # explicit; code retained for schema-parity and forward-compatibility.

  # Collect missing hard deps for banner substitution.
  # DR has only one soft dep (coordinator-claude); hard deps are structurally absent.
  # The banner path is traversed anyway for schema uniformity.
  local _missing_hard=()
  while IFS= read -r _probe_line; do
    [[ -z "$_probe_line" ]] && continue
    local _python
    _python="$(_co_find_python 2>/dev/null)" || continue
    local _severity _status _id
    _severity="$("$_python" -c "import json,sys; print(json.loads(sys.argv[1]).get('severity',''))" "$_probe_line" 2>/dev/null)"
    _status="$("$_python" -c "import json,sys; print(json.loads(sys.argv[1]).get('status',''))" "$_probe_line" 2>/dev/null)"
    _id="$("$_python" -c "import json,sys; print(json.loads(sys.argv[1]).get('id',''))" "$_probe_line" 2>/dev/null)"
    if [[ "$_severity" == "hard" && ( "$_status" == "missing" || "$_status" == "present-but-broken" ) ]]; then
      _missing_hard+=("$_id [$_status]")
    fi
  done < <(_dr_dep_probe_all 2>/dev/null)

  # No hard deps missing → no consent needed.
  if [[ ${#_missing_hard[@]} -eq 0 ]]; then
    return 0
  fi

  # Build the banner with missing-dep list substituted.
  local _banner_path
  _banner_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/dep_consent_banner.txt"
  local _banner_body=""
  if [[ -f "$_banner_path" ]]; then
    _banner_body="$(cat "$_banner_path")"
  else
    # Fallback: inline minimal banner if file is missing.
    _banner_body="================================================================
WARNING — UNSAFE INSTALL REQUESTED
Missing hard deps; see scripts/lib/dep_consent_banner.txt
================================================================"
  fi

  # Substitute <list of missing hard deps, one per line> placeholder.
  local _dep_list=""
  for _entry in "${_missing_hard[@]}"; do
    _dep_list="${_dep_list}  ${_entry}"$'\n'
  done
  # Strip trailing newline from dep list.
  _dep_list="${_dep_list%$'\n'}"
  local _banner_rendered
  _banner_rendered="${_banner_body//'  <list of missing hard deps, one per line>'/$_dep_list}"

  # Both flags provided — banner once, one-line acknowledgment, proceed.
  if [[ "$_skip_dep_check" == true && "$_accept_risk" == true ]]; then
    if [[ "$_non_interactive" == true || ! -t 2 ]]; then
      echo "$_banner_rendered" >&2
    else
      echo "$_banner_rendered" >&2
      echo "[setup] Override flags accepted: --skip-dep-check --accept-missing-deps-risk. Proceeding." >&2
    fi
    return 0
  fi

  # No flag pair. Emit banner to stderr.
  echo "$_banner_rendered" >&2

  # Non-TTY without flag pair → exit 90.
  if [[ "$_non_interactive" == true || ! -t 0 ]]; then
    echo "" >&2
    echo "ERROR: Hard dependencies missing in non-interactive context (exit 90)." >&2
    echo "  Run interactively, or pass --skip-dep-check --accept-missing-deps-risk to override." >&2
    exit 90
  fi

  # TTY without flag pair → double-confirm protocol.
  echo "" >&2
  printf "Do you accept the risk of proceeding without the required dependencies? [y/N] " >&2
  local _reply1=""
  read -r _reply1 || _reply1=""
  if [[ "$_reply1" != "y" && "$_reply1" != "Y" ]]; then
    echo "[setup] Aborted: first confirmation declined (exit 91)." >&2
    exit 91
  fi

  printf "Specifically, do you accept that running without required deps may produce contract-violation outcomes? [y/N] " >&2
  local _reply2=""
  read -r _reply2 || _reply2=""
  if [[ "$_reply2" != "y" && "$_reply2" != "Y" ]]; then
    echo "[setup] Aborted: second confirmation declined (exit 91)." >&2
    exit 91
  fi

  echo "[setup] Both confirmations received. Proceeding with unsafe install." >&2
  return 0
}
