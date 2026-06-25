#!/usr/bin/env bash
# manifest_reader.sh — stdlib-Python NDJSON emitter for agent-install-manifest.json.
#
# Purpose: reads docs/install/agent-install-manifest.json and emits one NDJSON line per
# direct_dep to stdout. Used by dep_check.sh and any future tooling that needs to consume
# coordinator-claude's dep chain without a pyyaml/yaml dependency.
#
# Downstream vendors (cross-repo): project-rag-ue-addon AND deep-research both vendor this
# file BYTE-STABLE as part of the prereq_probe.sh self-sourcing unit (prereq_probe.sh sources
# this for _co_find_python). coordinator-claude is source_is_live, so their producer-side
# parity test's FRESHNESS leg is advisory — a breaking change here warrants a bump-memo to
# BOTH project-rag-ue-addon-em AND deep-research-em.
# See docs/wiki/cross-repo-contract-parity.md § Convention B.
#
# Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §7 C3
#
# Reader-widen note: this reader accepts contract versions {1, 2, 3}. Coord ships its manifest
# at v3 as of the 2026-06-23 fleet-wide simultaneous-merge cutover (system_prerequisites array
# added; every consumer reader widened to {1,2,3} in the same synchronized merge wave, which
# closes the deployment-skew window without a reader-widen-first round-trip).
# knownAccepted range is the coordinator-canonical set; holodeck and other consumers mirror this shape.
#
# Contract:
#   - Stdlib-only: python -c "import json; ..." — no pyyaml, no third-party deps.
#     pyyaml is a project-rag transitive dep; it is NOT available at first-run time.
#   - Python resolver: tries python3 first, then python. Exits non-zero with a clean
#     "no Python found" message if neither is on PATH (per N-3: Python resolution must
#     run before manifest read, not inside it).
#   - Hard contract (per plan §5 constraint e): if the manifest is missing or JSON-
#     unparseable, exits non-zero with "manifest corrupt" — does NOT silently default to
#     "all deps OK".
#   - Output: one NDJSON line per direct_dep entry, fields:
#       {id, severity, sibling_dir_name, upstream_url,
#        functional_probe_kind, functional_probe_args}
#     functional_probe_args is a JSON object containing all probe-kind-specific fields
#     (path, expr, cmd) present in the manifest entry's functional_probe object.
#   - Does NOT emit: override_flags (top-level), consumer_install_args (per-dep, v2+)
#     — the chain-walker reads those directly from the upstream manifest at Steps 3 and 5.d.
#     Callers must not assume a complete dep record from this reader's output.
#
# Usage (standalone):
#   bash scripts/lib/manifest_reader.sh [--manifest <path>]
#
# Usage (sourced by dep_check.sh):
#   source scripts/lib/manifest_reader.sh
#   _co_manifest_read_ndjson   # emits NDJSON to stdout

# ---------------------------------------------------------------------------
# Python resolver — N-3: find Python before attempting manifest read.
# Negative-spec: DO NOT embed this inline in dep_check.sh or setup.sh;
# all Python resolution for manifest reading flows through this function.
#
# Functional probe: each candidate is actually EXECUTED to verify it is a
# working Python >= 3.11. This catches the Windows 11 WindowsApps Store stub
# (python3.exe App Execution alias) which passes `command -v` but exits 49
# with "Python was not found" when run — an existence-only probe would select
# the stub and then fail at every subsequent `"$PYTHON" -c` call.
#
# Candidate order:
#   1. python3
#   2. python
#   3. On Windows/MINGW/MSYS/CYGWIN: py launcher variants
#      (py -3.12, py -3, py) — resolved to the concrete executable path via
#      `py ... -c "import sys;print(sys.executable)"` so the returned value is
#      always a single token and callers can use it as `"$PYTHON" -c "..."`.
#
# Return value: echoes a single executable token (never a multi-word string).
# Returns 1 with a remediation message to stderr when no functional interpreter
# is found.
# ---------------------------------------------------------------------------
_co_find_python() {
  local _version_check='import sys; sys.exit(0 if sys.version_info[:2] >= (3,11) else 1)'

  # Helper: return 0 if candidate is a functional Python >= 3.11.
  _co_fp_probe() {
    local _cand="$1"
    command -v "$_cand" >/dev/null 2>&1 || return 1
    "$_cand" -c "$_version_check" >/dev/null 2>&1
  }

  if _co_fp_probe python3; then
    echo "python3"
    return 0
  fi

  if _co_fp_probe python; then
    echo "python"
    return 0
  fi

  # On Windows Git-Bash / MSYS2 / Cygwin, try the `py` launcher which survives
  # the Store stub problem and can dispatch a real CPython installation.
  # We resolve to the concrete executable path so the return value is always a
  # single token (callers do `"$PYTHON" -c "..."` with the value quoted as one
  # word; a multi-word value like "py -3.12" would be treated as a file name).
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*)
      if command -v py >/dev/null 2>&1; then
        for _py_ver in "-3.12" "-3.11" "-3" ""; do
          local _resolved
          if [[ -n "$_py_ver" ]]; then
            _resolved="$(py "$_py_ver" -c 'import sys;print(sys.executable)' 2>/dev/null)" || continue
          else
            _resolved="$(py -c 'import sys;print(sys.executable)' 2>/dev/null)" || continue
          fi
          if [[ -n "$_resolved" ]] && "$_resolved" -c "$_version_check" >/dev/null 2>&1; then
            echo "$_resolved"
            return 0
          fi
        done
      fi
      ;;
  esac

  # Review: code-reviewer F7 — error message is OS-aware: mentions py launcher on Windows
  _co_fp_os="$(uname -s 2>/dev/null || echo unknown)"
  case "$_co_fp_os" in
    MINGW*|MSYS*|CYGWIN*)
      echo "ERROR: no functional Python 3.11+ interpreter found on PATH (tried python3, python, py (launcher))." >&2
      ;;
    *)
      echo "ERROR: no functional Python 3.11+ interpreter found on PATH (tried python3, python)." >&2
      ;;
  esac
  echo "  Python 3.11+ is required to read the install manifest." >&2
  echo "  On Windows: if python3/python exist but are non-functional, disable the" >&2
  echo "    WindowsApps python/python3 App Execution aliases in:" >&2
  echo "    Settings > Apps > App execution aliases" >&2
  echo "    then install real Python 3.11+ from https://www.python.org/downloads/" >&2
  echo "  See: https://www.python.org/downloads/" >&2
  return 1
}

# ---------------------------------------------------------------------------
# _co_resolve_manifest_path [repo-root]
#
# Purpose: layout-aware resolution of agent-install-manifest.json. The
# coordinator-claude install surface ships in two layouts and the manifest
# lands in a DIFFERENT place in each — so callers MUST NOT assume a single
# fixed REPO_ROOT-relative location (the 2026-06-17 holodeck-em failure: the
# walker resolved coordinator/docs/install/ but the publish flat-mirror put
# the manifest at repo-root docs/install/, one level higher):
#
#   Nested working-tree / mirror layout — manifest beside the coordinator/ tree:
#       <REPO_ROOT>/docs/install/agent-install-manifest.json
#       (REPO_ROOT == coordinator/, the parent of scripts/)
#   Flat publish-repo-root layout — manifest one level ABOVE coordinator/,
#   published there by the `coordinator-claude-toplevel-install` flat-mirror
#   target so the leaf bootstrap can find it at a predictable repo root:
#       <REPO_ROOT>/../docs/install/agent-install-manifest.json
#
# Probes both, returns the first that exists (absolute, normalized). Fails
# LOUD with remediation when neither exists — never emits an empty/unbound
# path. Callers under `set -u` MUST guard the call (assign "" on failure).
#
# Arguments:
#   $1 (optional) — repo root. Defaults to ${REPO_ROOT}, else derived from
#                   this lib's location (scripts/lib → two levels up).
# ---------------------------------------------------------------------------
_co_resolve_manifest_path() {
  local _repo_root="${1:-${REPO_ROOT:-}}"
  if [[ -z "$_repo_root" ]]; then
    _repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
  fi
  local _rel="docs/install/agent-install-manifest.json"
  local _nested="${_repo_root}/${_rel}"           # working-tree / mirror layout
  local _flat="${_repo_root}/../${_rel}"           # publish-repo-root flat-mirror layout
  local _hit=""
  if [[ -f "$_nested" ]]; then
    _hit="$_nested"
  elif [[ -f "$_flat" ]]; then
    _hit="$_flat"
  else
    echo "ERROR: install manifest not found in either layout location:" >&2
    echo "  nested (working-tree/mirror): $_nested" >&2
    echo "  flat   (publish-repo-root):   $_flat" >&2
    echo "  Remediation: re-publish BOTH install-surface targets from the meta-repo —" >&2
    echo "    bash setup/publish.sh coordinator-claude-toplevel-install   # repo-root docs/install/" >&2
    echo "    bash setup/publish.sh coordinator-claude                    # coordinator/ mirror" >&2
    echo "  (a manifest-only or mirror-only re-publish leaves the layouts inconsistent)." >&2
    return 1
  fi
  # Normalize to an absolute path.
  (cd "$(dirname "$_hit")" && printf '%s/%s\n' "$(pwd)" "$(basename "$_hit")")
}

# ---------------------------------------------------------------------------
# _co_manifest_read_ndjson — emit NDJSON, one line per direct_dep.
#
# Purpose: parse agent-install-manifest.json with stdlib json only and emit
# structured output for shell consumption. Exits non-zero on corrupt manifest.
#
# Arguments:
#   $1 (optional) — path to manifest file. Defaults to
#                   <repo-root>/docs/install/agent-install-manifest.json.
# ---------------------------------------------------------------------------
_co_manifest_read_ndjson() {
  local _manifest_path="${1:-}"
  local _python

  _python="$(_co_find_python)" || return 1

  # Default manifest location: layout-aware resolution (nested working-tree
  # vs flat publish-repo-root). The old lib-relative `../../docs/install/`
  # default was layout-blind and resolved a non-existent path under the publish
  # flat-mirror layout — see _co_resolve_manifest_path.
  if [[ -z "$_manifest_path" ]]; then
    _manifest_path="$(_co_resolve_manifest_path)" || return 1
  fi

  # Normalize to absolute path.
  # This guards CALLER-SUPPLIED paths ($1): the default-resolved path from
  # _co_resolve_manifest_path is already normalized + existence-checked, so for
  # that branch this block is a harmless re-normalization. F10: wrap with a
  # parent-dir existence check — in a caller without `set -e`, a `cd "$(dirname
  # ...)"` into a missing dir leaves `pwd` printing cwd, producing a misleading
  # path; the explicit check hard-fails with a clear message instead.
  local _manifest_dir
  _manifest_dir="$(dirname "$_manifest_path")"
  if [[ ! -d "$_manifest_dir" ]]; then
    echo "ERROR: manifest parent directory not found: $_manifest_dir" >&2
    echo "  Cannot normalize manifest path: $_manifest_path" >&2
    return 1
  fi
  _manifest_path="$(cd "$_manifest_dir" && pwd)/$(basename "$_manifest_path")"

  "$_python" -c "
import json, sys, os

manifest_path = sys.argv[1]

# Hard contract: corrupt manifest → non-zero exit, never silently OK.
if not os.path.isfile(manifest_path):
    print('ERROR: manifest not found: ' + manifest_path, file=sys.stderr)
    print('  manifest corrupt or missing — cannot proceed', file=sys.stderr)
    sys.exit(1)

try:
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
except json.JSONDecodeError as e:
    print('ERROR: manifest corrupt (JSON parse error): ' + str(e), file=sys.stderr)
    print('  file: ' + manifest_path, file=sys.stderr)
    sys.exit(1)
except OSError as e:
    print('ERROR: manifest unreadable: ' + str(e), file=sys.stderr)
    sys.exit(1)

# Minimal structural validation — runtime path is stdlib-only (no jsonschema).
required_top = ['agent_install_contract_version', 'repo_id', 'direct_deps']
for field in required_top:
    if field not in manifest:
        print('ERROR: manifest corrupt — missing required field: ' + field, file=sys.stderr)
        sys.exit(1)

version = manifest.get('agent_install_contract_version')
# Reader-widen: accept v1, v2, and v3 (v2 adds optional DirectDep.consumer_install_args;
# v3 adds optional system_prerequisites; per cross-repo agreement
# 2026-05-23-addon-reply-s4-consumer-install-args-coreview.md and
# docs/plans/2026-06-23-coordinator-root-system-prerequisites.md C6/C7).
# Coordinator manifest flipped to v3 in the 2026-06-23 fleet-wide simultaneous-merge cutover.
if version not in (1, 2, 3):
    print('ERROR: manifest corrupt — unrecognised contract version: ' + repr(version), file=sys.stderr)
    sys.exit(1)

direct_deps = manifest.get('direct_deps', [])
if not isinstance(direct_deps, list):
    print('ERROR: manifest corrupt — direct_deps must be an array', file=sys.stderr)
    sys.exit(1)

for dep in direct_deps:
    probe = dep.get('functional_probe', {})
    probe_kind = probe.get('kind', '')
    # Collect probe-kind-specific args (path, expr, cmd) into a sub-object.
    probe_args = {}
    for key in ('path', 'expr', 'cmd'):
        if key in probe:
            probe_args[key] = probe[key]
    out = {
        'id': dep.get('id', ''),
        'severity': dep.get('severity', ''),
        'sibling_dir_name': dep.get('sibling_dir_name', ''),
        'upstream_url': dep.get('upstream_url', ''),
        'functional_probe_kind': probe_kind,
        'functional_probe_args': probe_args,
    }
    print(json.dumps(out, ensure_ascii=True))
" "$_manifest_path"
}

# ---------------------------------------------------------------------------
# Standalone entrypoint — when executed directly (not sourced).
# ---------------------------------------------------------------------------
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  # Ensure Python is available before invoking ndjson reader
  if ! _co_find_python >/dev/null 2>&1; then
    echo "ERROR: manifest_reader requires Python 3. Install Python and retry." >&2
    exit 78  # EX_CONFIG
  fi
  _manifest_arg=""
  if [[ "${1:-}" == "--manifest" && -n "${2:-}" ]]; then
    _manifest_arg="$2"
  fi
  _co_manifest_read_ndjson "$_manifest_arg"
fi
