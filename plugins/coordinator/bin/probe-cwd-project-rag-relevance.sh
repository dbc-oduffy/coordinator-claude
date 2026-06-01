#!/usr/bin/env bash
# probe-cwd-project-rag-relevance.sh — Workstream-start gift-shape signal for project-RAG visibility.
#
# Purpose: Detect whether the current working directory has a project-RAG binding, assess MCP
# health, and apply a UE enrichment layer when a Unreal Engine project is detected. Emits
# zero or more human-readable lines to stdout. Exit 0 always — advisory, never gating.
#
# Spec backlink: docs/plans/2026-05-20-portable-code-substrate.md § Chunk 3
#
# Output format (zero or more lines):
#   [project-rag-relevance] <tag>: <message>
#
# AC-9 visibility matrix:
#   cwd type           | project-RAG bound? | MCP works? | Surface
#   Any, no binding    | no                 | n/a        | (silent)
#   Non-UE, bound      | yes                | yes        | healthy: ...
#   Non-UE, bound      | yes                | no         | broken: ...
#   UE, bound          | yes                | yes, corpus| healthy-ue: ... (2 lines)
#   UE, bound          | yes                | yes, nocrp | healthy-ue: ... + suggest-engine-corpus:
#   UE, bound          | yes                | no         | p0-broken-ue: (block-quoted)
#
# Testability: respect COORDINATOR_TEST_HOME for the ~ base path, allowing tests to mock
# all file reads without touching the real home directory.
#
# Usage: probe-cwd-project-rag-relevance.sh [--help]
# Exit 0 always.

set -u
set -o pipefail

# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--help" ]]; then
  cat <<'USAGE'
Usage: probe-cwd-project-rag-relevance.sh

Reads:
  - PWD (or git rev-parse --show-toplevel if inside git)
  - $HOME/.claude.json (mcpServers — look for "project-rag" key)
  - ~/.claude/machine-local/registry.local.toml (repos.project_rag for bound-source check; per-machine values)
  - ~/.claude/machine-local/registry.toml (fallback if registry.local.toml absent)
  - whoami output (project_kind probe, when project-rag tools registered)
  - presence of *.uproject file at PWD top level (canonical UE signal)
  - ~/.claude/plugins/coordinator-claude/data/mcp-registration-last-check.json (sentinel cache, optional)
  - ~/.claude/plugins/project-rag-ue-addon/data/doctor-last-run.json (engine-corpus heuristic)

Emits ZERO OR MORE lines following the AC-9 visibility matrix.
Exit 0 always.
USAGE
  exit 0
fi

# ---------------------------------------------------------------------------
# Resolve home base (COORDINATOR_TEST_HOME allows test mocking)
# ---------------------------------------------------------------------------
if [[ -n "${COORDINATOR_TEST_HOME:-}" ]]; then
  HOME_BASE="$COORDINATOR_TEST_HOME"
else
  HOME_BASE="$HOME"
fi

# ---------------------------------------------------------------------------
# Resolve Python interpreter (same pattern as scan-addon-health.sh)
# ---------------------------------------------------------------------------
PY="${COORDINATOR_PYTHON:-}"
if [[ -z "$PY" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  elif command -v python >/dev/null 2>&1; then
    PY=python
  else
    # No interpreter — cannot parse JSON or TOML; emit nothing (advisory, not gating).
    exit 0
  fi
fi

# ---------------------------------------------------------------------------
# Debug helper (only fires when COORDINATOR_DEBUG=1)
# ---------------------------------------------------------------------------
_debug() {
  if [[ "${COORDINATOR_DEBUG:-0}" == "1" ]]; then
    echo "[debug] probe-cwd-project-rag-relevance: $*" >&2
  fi
}

# ---------------------------------------------------------------------------
# Step 1: Determine effective CWD (git top-level preferred)
# COORDINATOR_TEST_PWD allows tests to override the directory scanned for .uproject,
# bypassing git top-level detection which is pinned to the real filesystem CWD.
# ---------------------------------------------------------------------------
if [[ -n "${COORDINATOR_TEST_PWD:-}" ]]; then
  EFFECTIVE_CWD="$COORDINATOR_TEST_PWD"
else
  EFFECTIVE_CWD="${PWD}"
  if command -v git >/dev/null 2>&1; then
    _git_top=$(git rev-parse --show-toplevel 2>/dev/null) && EFFECTIVE_CWD="$_git_top" || true
  fi
fi
_debug "effective_cwd=$EFFECTIVE_CWD"

# ---------------------------------------------------------------------------
# Step 2: Is project-RAG bound?
# "Project-RAG bound" means: mcpServers has a "project-rag" key OR
# registry.toml repos.project_rag is set and non-empty.
# ---------------------------------------------------------------------------
CLAUDE_JSON="$HOME_BASE/.claude.json"
REGISTRY_LOCAL_TOML="$HOME_BASE/.claude/machine-local/registry.local.toml"
REGISTRY_TOML="$HOME_BASE/.claude/machine-local/registry.toml"

_rag_bound=0

# Check ~/.claude.json for mcpServers["project-rag"]
if [[ -f "$CLAUDE_JSON" ]]; then
  _has_rag=$(cat "$CLAUDE_JSON" 2>/dev/null | "$PY" -c "
import json, sys
try:
    d = json.load(sys.stdin)
    servers = d.get('mcpServers', {})
    print('1' if 'project-rag' in servers else '0')
except Exception:
    print('0')
" 2>/dev/null) || _has_rag=0
  [[ "$_has_rag" == "1" ]] && _rag_bound=1
fi

# Check registry.local.toml (per-machine values) then registry.toml for repos.project_rag
_registry_file=""
if [[ -f "$REGISTRY_LOCAL_TOML" ]]; then
  _registry_file="$REGISTRY_LOCAL_TOML"
elif [[ -f "$REGISTRY_TOML" ]]; then
  _registry_file="$REGISTRY_TOML"
fi
if [[ "$_rag_bound" -eq 0 && -n "$_registry_file" ]]; then
  _reg_val=$(cat "$_registry_file" 2>/dev/null | "$PY" -c "
import sys
content = sys.stdin.read()
# Simple TOML parse: find [repos] section, then look for project_rag = 'something'
# Use tomllib (3.11+) if available, otherwise fall back to manual grep-style parse.
try:
    import tomllib
    d = tomllib.loads(content)
    val = d.get('repos', {}).get('project_rag', '')
    print(val.strip() if val else '')
except (ImportError, AttributeError):
    # tomllib not available (Python < 3.11) — simple line-scan fallback
    in_repos = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == '[repos]':
            in_repos = True
        elif stripped.startswith('[') and stripped != '[repos]':
            in_repos = False
        elif in_repos and stripped.split('=', 1)[0].strip() == 'project_rag':
            # Extract value: project_rag = 'value' or project_rag = \"value\"
            parts = stripped.split('=', 1)
            if len(parts) == 2:
                val = parts[1].strip().strip('\"').strip(\"'\")
                print(val)
                sys.exit(0)
    print('')
except Exception:
    print('')
" 2>/dev/null) || _reg_val=""
  [[ -n "$_reg_val" ]] && _rag_bound=1
fi

_debug "rag_bound=$_rag_bound"

# If not bound, emit nothing — silent per AC-9
if [[ "$_rag_bound" -eq 0 ]]; then
  exit 0
fi

# ---------------------------------------------------------------------------
# Step 3: Is UE project?
# Belt-and-suspenders UE detection:
#   (a) .uproject present at EFFECTIVE_CWD top level — definitively UE
#   (b) whoami project_kind == "ue" — also UE
# ---------------------------------------------------------------------------
_is_ue=0
_uproject_signal=0
_whoami_signal=0

# (a) .uproject file at top level
shopt -s nullglob 2>/dev/null || true
_uproject_files=( "$EFFECTIVE_CWD"/*.uproject )
if [[ "${#_uproject_files[@]}" -gt 0 ]]; then
  _is_ue=1
  _uproject_signal=1
  _debug ".uproject found at $EFFECTIVE_CWD — UE confirmed"
fi

# (b) whoami project_kind probe
_whoami_pk=$(
  "$PY" -c "
import json
try:
    m = __import__('coordinator_whoami.project_rag', fromlist=[''])
    d = json.loads(m.get_whoami_json())
    print(d.get('project_kind', ''))
except Exception:
    print('')
" 2>/dev/null
) || _whoami_pk=""

if [[ "$_whoami_pk" == "ue" ]]; then
  _whoami_signal=1
  if [[ "$_is_ue" -eq 0 ]]; then
    _is_ue=1
    _debug "whoami project_kind=ue (no .uproject on disk)"
  fi
fi

# Belt-and-suspenders: if .uproject present but whoami disagrees, log to debug
if [[ "$_uproject_signal" -eq 1 && "$_whoami_signal" -eq 0 && -n "$_whoami_pk" && "$_whoami_pk" != "ue" ]]; then
  _debug ".uproject present but whoami project_kind='$_whoami_pk' — treating as UE"
fi

_debug "is_ue=$_is_ue"

# ---------------------------------------------------------------------------
# Step 4: MCP health check
# Read mcp-registration-last-check.json; conservative default = healthy.
# If project-rag appears in red_servers → broken.
# ---------------------------------------------------------------------------
MCP_SENTINEL="$HOME_BASE/.claude/plugins/coordinator-claude/data/mcp-registration-last-check.json"
_mcp_healthy=1

if [[ -f "$MCP_SENTINEL" ]]; then
  _rag_in_red=$(cat "$MCP_SENTINEL" 2>/dev/null | "$PY" -c "
import json, sys
try:
    d = json.load(sys.stdin)
    red = d.get('red_servers', []) or []
    print('1' if 'project-rag' in red else '0')
except Exception:
    print('0')
" 2>/dev/null) || _rag_in_red=0
  [[ "$_rag_in_red" == "1" ]] && _mcp_healthy=0
fi

_debug "mcp_healthy=$_mcp_healthy"

# ---------------------------------------------------------------------------
# Step 5: Engine-corpus heuristic (UE enrichment layer only)
# Reads project-rag-ue-addon/data/doctor-last-run.json.
# MISSING/STALE if:
#   (a) sentinel absent, OR
#   (b) verdict RED with red_probes matching /engine.?corpus/i, OR
#   (c) verdict AMBER with same match
# PRESENT otherwise.
# ---------------------------------------------------------------------------
_engine_corpus_ok=0

if [[ "$_is_ue" -eq 1 ]]; then
  UE_ADDON_SENTINEL="$HOME_BASE/.claude/plugins/project-rag-ue-addon/data/doctor-last-run.json"

  if [[ ! -f "$UE_ADDON_SENTINEL" ]]; then
    _engine_corpus_ok=0
    _debug "UE addon sentinel absent → engine corpus MISSING"
  else
    _corpus_check=$(cat "$UE_ADDON_SENTINEL" 2>/dev/null | "$PY" -c "
import json, sys, re
try:
    d = json.load(sys.stdin)
    verdict = d.get('verdict', '').upper()
    red_probes = d.get('red_probes', []) or []
    probe_str = ','.join(str(p) for p in red_probes)
    engine_match = bool(re.search(r'engine.?corpus', probe_str, re.IGNORECASE))
    if verdict in ('RED', 'AMBER') and engine_match:
        print('missing')
    else:
        print('present')
except Exception:
    print('missing')
" 2>/dev/null) || _corpus_check="missing"

    if [[ "$_corpus_check" == "present" ]]; then
      _engine_corpus_ok=1
    fi
    _debug "engine_corpus_check=$_corpus_check"
  fi
fi

# ---------------------------------------------------------------------------
# Step 6: Emit based on AC-9 visibility matrix
# ---------------------------------------------------------------------------

if [[ "$_is_ue" -eq 0 ]]; then
  # Non-UE path
  if [[ "$_mcp_healthy" -eq 1 ]]; then
    echo "[project-rag-relevance] healthy: project-rag MCP up for this cwd."
  else
    echo "[project-rag-relevance] broken: project-rag MCP not responding for this cwd. Run /project-rag:doctor to restore."
  fi
else
  # UE path
  if [[ "$_mcp_healthy" -eq 0 ]]; then
    # p0-broken-ue: block-quoted, listed first
    echo "[project-rag-relevance] p0-broken-ue: > Going alone on a UE codebase: project-rag MCP is the knowledge tool for this terrain."
    echo "[project-rag-relevance] p0-broken-ue: > Restore it first — /project-rag:doctor. Without it you're grepping a 100K-file engine source by hand."
  else
    # healthy-ue: 2 lines per contract
    echo "[project-rag-relevance] healthy-ue: project-rag MCP up — subsystems, blueprint graph, referencers, C++ symbols ready."
    echo "                                     Query the index; engine source is 100K files."
    if [[ "$_engine_corpus_ok" -eq 0 ]]; then
      echo "[project-rag-relevance] suggest-engine-corpus: Engine corpus not loaded. Run /project-rag-ue-addon:doctor to bootstrap."
    fi
  fi
fi

exit 0
