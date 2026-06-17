#!/usr/bin/env bash
# manifest_reader.sh — stdlib-Python NDJSON emitter for agent-install-manifest.json.
#
# Purpose: reads docs/install/agent-install-manifest.json and emits one NDJSON line per
# direct_dep to stdout. Used by dep_check.sh and any future tooling that needs to consume
# coordinator-claude's dep chain without a pyyaml/yaml dependency.
#
# Spec backlink: docs/plans/2026-06-15-coordinator-install-chain-application-phase-b.md §7 C3
#
# Reader-widen note (2026-05-23 cross-repo agreement): this reader accepts contract versions
# {1, 2}. Coord ships its manifest at v2; holodeck (coord's downstream chain-walker) already
# accepts {1, 2} per the coordinated reader-widen-first sequencing. Mirror the knownAccepted
# shape from holodeck/scripts/lib/manifest_reader.sh.
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
# ---------------------------------------------------------------------------
_co_find_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
  elif command -v python >/dev/null 2>&1; then
    echo "python"
  else
    echo "ERROR: no Python interpreter found on PATH (tried python3, python)." >&2
    echo "  Python 3.11+ is required to read the install manifest." >&2
    echo "  See: https://www.python.org/downloads/" >&2
    return 1
  fi
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
# Reader-widen: accept v1 and v2 during the coordinated 1->2 bump (v2 adds
# optional DirectDep.consumer_install_args; reader-widen-first sequencing per
# cross-repo agreement 2026-05-23-addon-reply-s4-consumer-install-args-coreview.md).
if version not in (1, 2):
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
