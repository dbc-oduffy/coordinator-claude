#!/usr/bin/env bash
# coordinator/lib/settings-hook-identity.sh — shared settings.json generated-hook identity key
#
# Purpose: SINGLE source of truth for "is this hook group coordinator-generated?",
#   consumed by both the forward generator (gen-settings-hooks.sh) and the uninstall
#   inverse-strip leg (uninstall_strip_settings_hooks, coordinator/lib/uninstall-legs.sh).
#   Prior to this module the identity key (interpreter-prefix strip + generated-dir
#   prefix test) was duplicated inline in gen-settings-hooks.sh at two call sites
#   (the stray-check ~line 139-140 and the main jq program ~line 221-229); any future
#   uninstall-side re-derivation would have been a THIRD copy, guaranteed to drift.
#
# Identity key: a hook group is "generated" iff at least one of its command hooks has
#   a resolved command path — after stripping a leading interpreter prefix
#   (bash/node/python3/python) — that starts with "<coordinator_root>/hooks/".
#   All other groups are preserved verbatim. This mirrors gen-settings-hooks.sh's
#   `group_is_generated` jq def exactly; do not re-derive divergently.
#
# Spec backlink: docs/plans/2026-07-08-coordinator-uninstall.md § C2
# Prior art: docs/wiki/install-surface-completeness.md § Multi-site value parity
#   ("one canonical manifest, all call-sites consume it" — this module is that
#   canonical manifest for the settings-hook identity key specifically).
# Surface source of truth: tasks/coordinator-uninstall/surface-map.md § settings.json
#   inverse-strip contract.

# ---- bash >=4 guard (must parse on bash 3.2) ----
# This module is always sourced, never executed directly — the return/exit
# fallback below exists only for defense-in-depth.
# Review: code-reviewer — noting source-only status so a future maintainer
# doesn't re-derive the return-vs-exit ambiguity for an execution path that
# doesn't occur for this file.
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "ERROR: settings-hook-identity.sh requires bash >= 4." >&2
  echo "Remediation: brew install bash  (then relaunch your shell or prefix with /opt/homebrew/bin/bash)" >&2
  return 1 2>/dev/null || exit 1
fi

# settings_hook_identity_cmd_path_def
#
# Emits the jq `def cmd_path: ...;` snippet that strips a leading interpreter
# prefix (bash/node/python3/python) from a command string, producing the bare
# script path used for identity comparisons. Callers splice this into their
# own jq program (via `$(...)`  string interpolation) alongside
# settings_hook_identity_group_is_generated_def.
settings_hook_identity_cmd_path_def() {
  cat <<'JQ_DEF'
def cmd_path:
  ltrimstr("bash ") | ltrimstr("node ") | ltrimstr("python3 ") | ltrimstr("python ");
JQ_DEF
}

# settings_hook_identity_group_is_generated_def
#
# Emits the jq `def group_is_generated: ...;` snippet. Depends on cmd_path
# (see settings_hook_identity_cmd_path_def) being defined earlier in the same
# jq program, and on a `$generated_hooks_dir` jq --arg being bound by the
# caller (the caller's invocation must pass
# `--arg generated_hooks_dir "<coordinator_root>/hooks"`).
settings_hook_identity_group_is_generated_def() {
  cat <<'JQ_DEF'
def group_is_generated:
  .hooks | any(
    .type == "command" and
    (.command | cmd_path | startswith($generated_hooks_dir + "/"))
  );
JQ_DEF
}

# settings_hook_identity_jq_program
#
# Convenience: emits both defs concatenated, ready to prepend to a larger jq
# program string. Equivalent to calling the two functions above in sequence.
settings_hook_identity_jq_program() {
  settings_hook_identity_cmd_path_def
  settings_hook_identity_group_is_generated_def
}

# settings_hook_identity_inverse_strip <settings_json_path> <coordinator_root> <out_path>
#
# Given a settings.json and a resolved coordinator root, writes to <out_path>
# a copy of the settings.json with every generated hook group removed
# (identity: settings_hook_identity_group_is_generated_def) and every other
# group — including all non-hook top-level keys such as `.enabledPlugins` —
# preserved untouched. Atomic-safe only insofar as the caller treats
# <out_path> as a temp file and renames it into place; this function itself
# performs a single jq invocation and does not do the rename.
#
# Fails loud (non-zero exit, no output written) if jq is missing or the
# input is not valid JSON — callers must not swallow the exit code.
settings_hook_identity_inverse_strip() {
  local settings_json="$1"
  local coordinator_root="$2"
  local out_path="$3"

  [ -n "$settings_json" ] || { echo "settings_hook_identity_inverse_strip: missing <settings_json_path>" >&2; return 1; }
  [ -n "$coordinator_root" ] || { echo "settings_hook_identity_inverse_strip: missing <coordinator_root>" >&2; return 1; }
  [ -n "$out_path" ] || { echo "settings_hook_identity_inverse_strip: missing <out_path>" >&2; return 1; }

  if ! command -v jq >/dev/null 2>&1; then
    echo "settings_hook_identity_inverse_strip: jq is required but not installed." >&2
    return 1
  fi

  [ -f "$settings_json" ] || { echo "settings_hook_identity_inverse_strip: not found: $settings_json" >&2; return 1; }

  local generated_hooks_dir="${coordinator_root%/}/hooks"

  local jq_program
  jq_program="$(
    settings_hook_identity_jq_program
    cat <<'JQ_EOF'

# Preserved: groups where NO command hook has a path under coordinator/hooks/.
# All non-hooks top-level keys (e.g. .enabledPlugins) pass through untouched
# via the trailing `. + {hooks: ...}` merge below.
#
# Review: code-reviewer — this filter (map(select(.value | length > 0)))
# is applied here, immediately after from_entries's input map, whereas
# gen-settings-hooks.sh's own $preserved extraction defers the equivalent
# filter to its later $merged_hooks computation. Functionally equivalent
# (empty-array event keys are dropped either way) — the "mirrors
# gen-settings-hooks.sh exactly" claim above scopes to the group_is_generated/
# cmd_path defs, not to this surrounding pipeline shape, which legitimately
# diverges in filter-application point between the two call sites.
((.hooks // {}) | to_entries | map(
  .key as $event |
  (.value | map(select(group_is_generated | not))) |
  {key: $event, value: .}
) | map(select(.value | length > 0)) | from_entries) as $preserved |

. + {hooks: $preserved}
JQ_EOF
  )"

  jq --arg generated_hooks_dir "$generated_hooks_dir" \
     "$jq_program" \
     "$settings_json" > "$out_path"
}
