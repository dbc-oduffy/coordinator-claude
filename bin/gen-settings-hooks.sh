#!/usr/bin/env bash
# gen-settings-hooks.sh — generate settings.json hooks block from coordinator hooks.json
#
# Purpose: reads coordinator/hooks/hooks.json, emits a settings.json 'hooks' block where:
#   - ONLY type=='command' entries WITH ${CLAUDE_PLUGIN_ROOT} in their command string are emitted
#   - type=='mcp_tool' entries are SKIPPED (in-process coordinator_core ops, not settings.json rails)
#   - type=='command' entries WITHOUT ${CLAUDE_PLUGIN_ROOT} are SKIPPED (no bake needed, not plugin hooks)
#   - every ${CLAUDE_PLUGIN_ROOT} is rewritten to the registry-resolved ABSOLUTE coordinator path
#   - non-generated hooks already in settings.json (identity: path NOT under coordinator/hooks/) are PRESERVED
#
# Identity key: a hook group is "generated" iff at least one of its command hooks has a resolved
#   path starting with <coordinator_root>/hooks/. All other groups are preserved verbatim.
#
# Requirements: deterministic, idempotent (byte-identical output on re-run); --out param; fail-loud.
#
# Spec backlink: docs/plans/2026-07-04-doe-maximalist-execution-plugin-dir.md § M1
# Mechanism: coordinator/docs/wiki/external-plugin-live-resolution.md § Hook-delivery — SOLVED via settings.json

# ---- bash >=4 guard (must parse on bash 3.2) ----
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "ERROR: gen-settings-hooks.sh requires bash >= 4." >&2
  echo "Remediation: brew install bash  (then relaunch your shell or prefix with /opt/homebrew/bin/bash)" >&2
  exit 1
fi

set -euo pipefail

# ---- source shared settings-hook identity key (single source of truth) ----
_GEN_SETTINGS_HOOKS_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/settings-hook-identity.sh
source "${_GEN_SETTINGS_HOOKS_SELF_DIR}/../lib/settings-hook-identity.sh"

# ---- helpers ----
die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat >&2 <<'EOF'
Usage: gen-settings-hooks.sh [OPTIONS]

Options:
  --out <path>              Output path (default: ~/.claude/settings.json)
  --hooks-json <path>       Override hooks.json path (for tests)
  --coordinator-root <path> Override coordinator root (for tests; bypasses registry resolution)
  -h, --help                Show this help

Environment:
  REPO_DOE_CLAUDE           Fallback if machine-local get repos.doe_claude fails
EOF
}

# ---- arg parse ----
OUT_PATH=""
HOOKS_JSON_OVERRIDE=""
COORDINATOR_ROOT_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)              OUT_PATH="$2";              shift 2 ;;
    --hooks-json)       HOOKS_JSON_OVERRIDE="$2";   shift 2 ;;
    --coordinator-root) COORDINATOR_ROOT_OVERRIDE="${2%/}"; shift 2 ;; # Review: trailing-slash normalisation (F3)
    -h|--help)          usage; exit 0 ;;
    *) die "Unknown argument: $1\nRun with --help for usage." ;;
  esac
done

OUT_PATH="${OUT_PATH:-${HOME}/.claude/settings.json}"

# ---- jq check (fail-loud, not silent-degrade) ----
if ! command -v jq >/dev/null 2>&1; then
  die "jq is required but not installed.
Remediation:
  macOS:  brew install jq
  Ubuntu: sudo apt-get install jq
  Other:  https://jqlang.github.io/jq/download/"
fi

# ---- resolve coordinator root ----
if [[ -n "${COORDINATOR_ROOT_OVERRIDE}" ]]; then
  COORDINATOR_ROOT="${COORDINATOR_ROOT_OVERRIDE}"
else
  DOE_CLAUDE=""
  # Registry resolution order: machine-local get -> $REPO_DOE_CLAUDE -> fail-loud
  if command -v machine-local >/dev/null 2>&1; then
    DOE_CLAUDE="$(machine-local get repos.doe_claude 2>/dev/null || true)"
  fi
  if [[ -z "${DOE_CLAUDE}" ]]; then
    DOE_CLAUDE="${REPO_DOE_CLAUDE:-}"
  fi
  if [[ -z "${DOE_CLAUDE}" ]]; then
    die "Cannot resolve repos.doe_claude (DoE-claude repo root).
Remediation:
  Option 1 — register with machine-local:
    machine-local set repos.doe_claude /path/to/DoE-claude
  Option 2 — set env var:
    export REPO_DOE_CLAUDE=/path/to/DoE-claude
  Then re-run: gen-settings-hooks.sh"
  fi
  DOE_CLAUDE="${DOE_CLAUDE%/}" # Review: normalise trailing slash so double-slash can't propagate into hook paths (F3)
  COORDINATOR_ROOT="${DOE_CLAUDE}/coordinator"
fi

if [[ ! -d "${COORDINATOR_ROOT}" ]]; then
  die "Coordinator root does not exist: ${COORDINATOR_ROOT}
Remediation: ensure the DoE-claude repo is cloned and has a coordinator/ subdirectory.
  Expected: ${COORDINATOR_ROOT}"
fi

# ---- locate hooks.json ----
if [[ -n "${HOOKS_JSON_OVERRIDE}" ]]; then
  HOOKS_JSON="${HOOKS_JSON_OVERRIDE}"
else
  HOOKS_JSON="${COORDINATOR_ROOT}/hooks/hooks.json"
fi

[[ -f "${HOOKS_JSON}" ]] || die "hooks.json not found: ${HOOKS_JSON}"

# ---- GENERATED_HOOKS_DIR: the prefix that identifies generated hook commands ----
GENERATED_HOOKS_DIR="${COORDINATOR_ROOT}/hooks"

# ---- read current settings.json (default to empty object if absent) ----
CURRENT_SETTINGS="{}"
if [[ -f "${OUT_PATH}" ]]; then
  CURRENT_SETTINGS="$(cat "${OUT_PATH}")"
fi

# ---- stray-check: hand hook under generated-hooks-dir that WON'T be re-emitted → fail-loud ----
# A command hook whose path is under <coordinator>/hooks/ but is NOT in the generator's will-emit
# set would be silently OVERWRITTEN on regeneration: group_is_generated classifies any group
# containing a coordinator/hooks/ command as "generated", so its entire group gets replaced.
# (The prior dead-code check guarded "preserved groups with gen-dir commands" — mutually exclusive
#  by definition of group_is_generated; this replacement detects the real data-loss footgun.)
# Detect before any write and fail-loud with remediation.
STRAY_CHECK_JQ_PROGRAM="$(
  settings_hook_identity_cmd_path_def
  cat <<'JQ_EOF'

# NOTE: intra-file duplicate of is_cpr_command/rewrite_cpr — fold if a third copy appears (C2 follow-up)
def is_cpr_command:
  .type == "command" and (.command | contains("${CLAUDE_PLUGIN_ROOT}"));

def rewrite_cpr:
  split("${CLAUDE_PLUGIN_ROOT}") | join($coordinator_root);

# Build the set of commands this generator WILL emit (after ${CLAUDE_PLUGIN_ROOT} rewrite).
[$hooks_json.hooks | to_entries[] |
  .value[] |
  .hooks[] |
  select(is_cpr_command) |
  .command | rewrite_cpr
] as $will_emit |

# Find any existing hook whose cmd_path is under the gen dir but is NOT in the will-emit set.
# Such hooks would be silently overwritten on the next regeneration.
(.hooks // {}) | to_entries[] |
.key as $ev |
.value[] |
.hooks[] |
select(.type == "command") |
select(.command | cmd_path | startswith($gen_dir + "/")) |
.command as $cmd |
select(($will_emit | map(. == $cmd) | any) | not) |
"event=\($ev) command=\($cmd)"
JQ_EOF
)"
STRAY_CHECK="$(
  jq -r \
    --arg gen_dir "${GENERATED_HOOKS_DIR}" \
    --arg coordinator_root "${COORDINATOR_ROOT}" \
    --argjson hooks_json "$(cat "${HOOKS_JSON}")" \
    "${STRAY_CHECK_JQ_PROGRAM}" \
    <<< "${CURRENT_SETTINGS}" 2>/dev/null || true
)"

if [[ -n "${STRAY_CHECK}" ]]; then
  printf 'ERROR: Hand-authored hook detected under the generator-owned coordinator/hooks/ dir.\n' >&2
  printf '       This hook is not in hooks.json and would be silently OVERWRITTEN on regeneration:\n' >&2
  printf '         %s\n' "${STRAY_CHECK}" >&2
  printf '\n' >&2
  printf 'Remediation: This hook lives under the generator-owned %s/ dir.\n' "${GENERATED_HOOKS_DIR}" >&2
  printf '             Move it elsewhere (e.g. <settings-home>/bin/ or ~/.claude/bin/ during\n' >&2
  printf '             the compat window) and update the command path,\n' >&2
  printf '             or add it to hooks.json so the generator manages it.\n' >&2
  exit 1
fi

# ---- jq program (written to temp file for clean heredoc) ----
JQ_TMPFILE="$(mktemp /tmp/gen-settings-hooks-jq.XXXXXX)"
# Unpredictable temp in the same dir as OUT_PATH so mv stays atomic (same filesystem).
# Edge case: if OUT_PATH has no directory component, ${OUT_PATH%/*} == OUT_PATH; fall back to ".".
_out_dir="${OUT_PATH%/*}"
[ "$_out_dir" = "$OUT_PATH" ] && _out_dir="."
TMP_OUT="$(mktemp "${_out_dir}/.gen-settings-hooks.XXXXXX")"
cleanup() { rm -f "${JQ_TMPFILE}" "${TMP_OUT}"; }
trap cleanup EXIT

{
  cat << 'JQ_EOF'
# Purpose: merge new generated hooks from hooks.json into current settings.json.
#
# Filters applied:
#   - type=='command' AND command contains '${CLAUDE_PLUGIN_ROOT}' → emit (with path rewritten)
#   - type=='mcp_tool' → skip
#   - type=='command' without '${CLAUDE_PLUGIN_ROOT}' → skip (not a coordinator plugin hook)
#
# Identity: a group is "generated" iff any command starts with $generated_hooks_dir/
# Merge: preserved_groups + new_generated_groups per event, events sorted alphabetically.

# Rewrite ${CLAUDE_PLUGIN_ROOT} → coordinator_root (literal split/join, no regex)
def rewrite_cpr:
  split("${CLAUDE_PLUGIN_ROOT}") | join($coordinator_root);

# Is this a command hook with a bake-able CPR path?
# ASSUMPTION: ${CLAUDE_PLUGIN_ROOT} must be the leading path component after any interpreter
# prefix (bash/node/python3/python). A non-prefix position passes this check but fails the
# cmd_path startswith check on re-run, silently treating the hook as preserved and duplicating
# it. All hooks.json entries must place ${CLAUDE_PLUGIN_ROOT} immediately after the interpreter.
# Review: document non-prefix CPR idempotency hazard (F6)
# NOTE: intra-file duplicate of is_cpr_command/rewrite_cpr — fold if a third copy appears (C2 follow-up)
def is_cpr_command:
  .type == "command" and (.command | contains("${CLAUDE_PLUGIN_ROOT}"));
JQ_EOF

  # Strip interpreter prefix to get the bare script path for identity checks, and the
  # generated/preserved classifier — SOURCED FROM THE SHARED MODULE (single source of
  # truth shared with the uninstall inverse-strip leg; see
  # coordinator/lib/settings-hook-identity.sh).
  settings_hook_identity_jq_program

  cat << 'JQ_EOF'

# ---- build new_generated from hooks.json ----
# For each event, for each group: filter to CPR commands only, rewrite, skip empty groups.
($hooks_json.hooks | to_entries | map(
  .key as $event |
  (.value | map(
    . as $group |
    ($group.hooks | map(select(is_cpr_command)) |
      map(.command |= rewrite_cpr)
    ) as $filtered_hooks |
    if ($filtered_hooks | length) == 0 then empty
    else
      # Emit group: forward all group-level fields; explicitly strip _comment (not meaningful in settings.json).
      # Per-hook fields (timeout, async, asyncRewake, etc.) are preserved within each hook entry —
      # map(select|rewrite_cpr) only modifies .command, leaving all other per-hook keys intact.
      # Group-level fields beyond matcher are intentionally forwarded via del(._comment) + merge.
      # Review: corrected misleading comment; changed to forward-all-group-fields pattern (F5)
      ($group | del(._comment)) + {hooks: $filtered_hooks}
    end
  )) |
  if length == 0 then empty
  else {key: $event, value: .}
  end
) | from_entries) as $new_generated |

# ---- extract preserved groups from current settings.json ----
# Preserved: groups where NO command hook has a path under coordinator/hooks/
((.hooks // {}) | to_entries | map(
  .key as $event |
  (.value | map(select(group_is_generated | not))) |
  {key: $event, value: .}
) | from_entries) as $preserved |

# ---- build merged hooks block ----
# Event order: alphabetical sort for deterministic/idempotent output
(($preserved | keys) + ($new_generated | keys) | unique | sort) as $all_events |
($all_events | map(
  . as $event |
  (($preserved[$event] // []) + ($new_generated[$event] // [])) as $combined |
  {key: $event, value: $combined}
) | map(select(.value | length > 0)) | from_entries) as $merged_hooks |

# ---- assemble final settings.json ----
# Preserve all non-hooks fields; replace hooks key with merged block
. + {hooks: $merged_hooks}
JQ_EOF
} > "${JQ_TMPFILE}"

# ---- run jq merge ----
OUT_DIR="$(dirname "${OUT_PATH}")"
if [[ ! -d "${OUT_DIR}" ]]; then
  mkdir -p "${OUT_DIR}"
fi

jq \
  --arg coordinator_root "${COORDINATOR_ROOT}" \
  --arg generated_hooks_dir "${GENERATED_HOOKS_DIR}" \
  --argjson hooks_json "$(cat "${HOOKS_JSON}")" \
  -f "${JQ_TMPFILE}" \
  <<< "${CURRENT_SETTINGS}" > "${TMP_OUT}"

# ---- atomic write (no partial file on error) ----
mv "${TMP_OUT}" "${OUT_PATH}"

printf 'gen-settings-hooks: hooks block written to %s\n' "${OUT_PATH}" >&2
