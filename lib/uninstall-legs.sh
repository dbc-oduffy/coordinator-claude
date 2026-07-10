#!/usr/bin/env bash
# coordinator/lib/uninstall-legs.sh — coordinator uninstall leg functions
#
# Purpose: sourceable library of individual uninstall "legs" — each leg
#   reverses one surface of the maximalist coordinator install (per
#   tasks/coordinator-uninstall/surface-map.md's authoritative table).
#   Legs are composed by the orchestrator (coordinator/bin/coordinator-uninstall.sh,
#   C7) but each is independently sourceable/callable for testing.
#
# Every leg resolves its filesystem/registry targets from environment
# overrides (${CLAUDE_HOME:-$HOME}, ${COORDINATOR_SETTINGS_HOME:-...},
# ${MACHINE_LOCAL_REGISTRY_DIR}) — NEVER a hardcoded real-user path. This is
# what lets the test suite sandbox every leg into a mktemp -d $HOME without
# risk to the real install.
#
# Spec backlink: docs/plans/2026-07-08-coordinator-uninstall.md § C3-C6
# Surface source of truth: tasks/coordinator-uninstall/surface-map.md
# Identity-key source of truth: coordinator/lib/settings-hook-identity.sh (C2)

# ---- bash >=4 guard (must parse on bash 3.2) ----
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "ERROR: uninstall-legs.sh requires bash >= 4." >&2
  echo "Remediation: brew install bash  (then relaunch your shell or prefix with /opt/homebrew/bin/bash)" >&2
  return 1 2>/dev/null || exit 1
fi

# ---- source shared settings-hook identity key (single source of truth) ----
_UNINSTALL_LEGS_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./settings-hook-identity.sh
source "${_UNINSTALL_LEGS_SELF_DIR}/settings-hook-identity.sh"

# _uninstall_require_home
#
# Review: code-reviewer F1 — shared $HOME/$CLAUDE_HOME-unset guard. Three
# legs (uninstall_strip_settings_hooks, uninstall_remove_substrate,
# uninstall_set_plugin_endstate) derived claude_home="${CLAUDE_HOME:-$HOME}"
# without this guard, so a stripped-env invocation (both empty) resolved
# claude_home to the empty string and destructive targets like
# "${claude_home}/.coordinator-claude-settings" silently became root-anchored
# absolute paths (e.g. "/.coordinator-claude-settings") for rm -rf / cp -R /
# settings.json overwrite. uninstall_remove_shim already carried this exact
# guard inline (keyed off $HOME only, since that leg's rc-file targets are
# always $HOME-relative); this helper generalizes it for legs that fall back
# to $HOME only when CLAUDE_HOME is also unset. Fails loud (non-zero, no
# mutation) rather than resolving to "/" and proceeding.
_uninstall_require_home() {
  local caller="$1"
  if [ -z "${CLAUDE_HOME:-}" ] && [ -z "${HOME:-}" ]; then
    echo "${caller}: both \$CLAUDE_HOME and \$HOME are unset/empty — cannot resolve destructive targets" >&2
    return 1
  fi
  return 0
}

# _uninstall_resolve_coordinator_root
#
# Resolves <coordinator_root> using the SAME seam the generator
# (gen-settings-hooks.sh) uses to bake ${CLAUDE_PLUGIN_ROOT} into settings.json
# at generation time, so the strip's identity-key prefix matches the paths
# actually baked into settings.json. Resolution order:
#   1. COORDINATOR_ROOT env var (explicit override — what the test harness
#      and any --coordinator-root CLI flag ultimately set)
#   2. machine-local registry `repos.doe_claude` (if the `machine-local`
#      resolver is on PATH) → <repo>/coordinator
#   3. REPO_DOE_CLAUDE env var → <repo>/coordinator
#   4. ${CLAUDE_HOME:-$HOME}/.doe-root pointer file → <repo>/coordinator
#
# Fails loud (prints to stdout: empty string, non-zero exit, diagnostic on
# stderr) if no resolution succeeds or the resolved dir does not exist on
# disk — callers MUST check the exit code and MUST NOT treat an empty
# resolution as "strip zero groups and exit 0" (the Staff Engineer F7).
_uninstall_resolve_coordinator_root() {
  local root=""

  if [ -n "${COORDINATOR_ROOT:-}" ]; then
    root="${COORDINATOR_ROOT%/}"
  fi

  if [ -z "$root" ] && command -v machine-local >/dev/null 2>&1; then
    local doe_claude
    doe_claude="$(machine-local get repos.doe_claude 2>/dev/null || true)"
    if [ -n "$doe_claude" ]; then
      root="${doe_claude%/}/coordinator"
    fi
  fi

  if [ -z "$root" ] && [ -n "${REPO_DOE_CLAUDE:-}" ]; then
    root="${REPO_DOE_CLAUDE%/}/coordinator"
  fi

  if [ -z "$root" ]; then
    local claude_home="${CLAUDE_HOME:-$HOME}"
    local doe_root_pointer="${claude_home}/.doe-root"
    if [ -f "$doe_root_pointer" ]; then
      local doe_claude
      doe_claude="$(cat "$doe_root_pointer" 2>/dev/null || true)"
      # Review: code-reviewer F2 — flag a multi-line/malformed pointer file
      # with a specific diagnostic before the generic [ -d ] check, rather
      # than letting a garbage concatenated path fall through to a
      # confusing "does not exist on disk" message.
      case "$doe_claude" in
        *$'\n'*)
          echo "uninstall-legs: ${doe_root_pointer} is malformed (multi-line) — expected a single path" >&2
          doe_claude=""
          ;;
      esac
      doe_claude="${doe_claude%/}"
      if [ -n "$doe_claude" ]; then
        root="${doe_claude}/coordinator"
      fi
    fi
  fi

  if [ -z "$root" ] || [ ! -d "$root" ]; then
    echo "uninstall-legs: cannot determine which hook paths are coordinator-owned — resolve coordinator root or pass --coordinator-root" >&2
    echo "  Tried: COORDINATOR_ROOT env, machine-local registry repos.doe_claude," >&2
    echo "         REPO_DOE_CLAUDE env, \${CLAUDE_HOME:-\$HOME}/.doe-root pointer." >&2
    [ -n "$root" ] && echo "  Resolved candidate does not exist on disk: ${root}" >&2
    return 1
  fi

  printf '%s' "$root"
}

# uninstall_strip_settings_hooks
#
# Reverses surface #2 (settings.json generated hook block). Resolves
# <coordinator_root> the same way the generator does (see
# _uninstall_resolve_coordinator_root), fails loud if unresolvable rather
# than silently stripping zero groups and exiting 0 (the Staff Engineer F7 — the
# generator's rewrite_cpr bakes the resolved root into the emitted paths,
# so a strip run against a different resolved root under-strips silently
# otherwise). Delegates the actual inverse-strip to the shared identity-key
# helper (settings_hook_identity_inverse_strip, C2) — does NOT re-derive the
# identity key.
#
# Operates on ${CLAUDE_HOME:-$HOME}/settings.json (env-resolved). Per this
# test suite's pinned sandbox convention, CLAUDE_HOME is set to the
# `.claude`-suffixed dir directly (e.g. CLAUDE_HOME="$TMP/.claude"), i.e.
# CLAUDE_HOME already names the `.claude` dir itself, NOT its parent — do
# not append another literal `.claude` path segment here (that would be the
# seed-skill-overrides.py "recurring footgun" in reverse: doubling the
# suffix instead of omitting it).
# Writes atomically (temp file + mv into place). Preserves every non-generated
# hook group + all non-hook top-level keys (e.g. .enabledPlugins) untouched.
# Idempotent: re-run against an already-stripped settings.json is a no-op
# (zero groups match the generated-dir prefix, so nothing is removed).
#
# No-op (success, no error) if settings.json itself does not exist — an
# absent settings.json has nothing to strip.
uninstall_strip_settings_hooks() {
  # Review: code-reviewer F1 — guard $HOME/$CLAUDE_HOME-unset before deriving
  # destructive targets (see _uninstall_require_home header).
  _uninstall_require_home "uninstall_strip_settings_hooks" || return 1

  local claude_home="${CLAUDE_HOME:-$HOME}"
  local settings_json="${claude_home}/settings.json"

  if [ ! -f "$settings_json" ]; then
    echo "uninstall_strip_settings_hooks: no settings.json at ${settings_json} — nothing to strip (no-op)" >&2
    return 0
  fi

  local coordinator_root
  coordinator_root="$(_uninstall_resolve_coordinator_root)" || return 1

  local out_dir
  out_dir="$(dirname "$settings_json")"
  local tmp_out
  tmp_out="$(mktemp "${out_dir}/.settings.json.uninstall-strip.XXXXXX")" || {
    echo "uninstall_strip_settings_hooks: failed to create temp file in ${out_dir}" >&2
    return 1
  }

  if ! settings_hook_identity_inverse_strip "$settings_json" "$coordinator_root" "$tmp_out"; then
    echo "uninstall_strip_settings_hooks: inverse-strip failed for ${settings_json}" >&2
    rm -f "$tmp_out"
    return 1
  fi

  if [ ! -s "$tmp_out" ]; then
    echo "uninstall_strip_settings_hooks: inverse-strip produced empty output — refusing to overwrite ${settings_json}" >&2
    rm -f "$tmp_out"
    return 1
  fi

  mv "$tmp_out" "$settings_json"
}

# uninstall_remove_shim
#
# Reverses the launch-surface family — surfaces #4a/#4b/#4c + #10 (the Staff Engineer
# F0). All four sub-parts are env-resolved; none hardcode a real-user path.
#
#   (a) #4a — rm -f the owned shim file (gen-claude-doe-shim.sh:175-178).
#   (b) #4b — strip the sentinel-guarded generated block from the
#       $SHELL-detected interactive rc, using the SAME detection order as
#       install (gen-claude-doe-shim.sh:124-132): */zsh -> ~/.zshrc,
#       */bash -> ~/.bashrc, else -> ~/.zshrc. Override precedence mirrors
#       the generator: --rc (COORDINATOR_SHIM_RC_OVERRIDE, this leg's
#       equivalent of the generator's --rc flag) > COORDINATOR_SHIM_RC env
#       > $SHELL detection.
#   (c) #4c — remove the legacy "# --- coordinator maximalist launch ---"
#       block (+ its claude() fn) from ${CLAUDE_HOME:-$HOME}/.bashrc.
#       Fail-loud (non-zero exit, zero mutation) if the block was
#       hand-modified — compares the captured body against the exact
#       generated shape, never silently clobbers.
#   (d) #10 (the Staff Engineer F0) — rm -f the claude-doe wrapper cp'd by install.md
#       Step 3.5b. Carries the settings.json regen block (claude-doe:172-191)
#       so leaving it behind self-heals C3's strip on next launch. Applies
#       in BOTH end-states (revert-to-marketplace uses bare `claude`, not
#       the wrapper).
#
# In-file collision (b)+(c): on this machine class $SHELL is frequently bash,
# so #4b's generated sentinel block and #4c's legacy block can both live in
# the SAME ~/.bashrc. Both regions are stripped independently — order does
# not matter, each is identified by its own distinct marker pair.
#
# rc-file path resolution: rc paths (~/.zshrc, ~/.bashrc) are ALWAYS relative
# to $HOME (matching gen-claude-doe-shim.sh, which never consults
# CLAUDE_HOME for rc resolution) — CLAUDE_HOME only gates the shim file (a)
# and the wrapper (d) live under a home-relative default, never the rc
# files themselves. This mirrors the C1 test sandboxes, which set
# HOME="$TMP" and CLAUDE_HOME="$TMP/.claude" as distinct paths.
#
# Idempotent: absent shim file / absent sentinel block / absent legacy
# block / absent wrapper are all no-ops (success, not error).
uninstall_remove_shim() {
  # Review: code-reviewer F1 — was an inline copy of this exact guard;
  # refactored to call the shared helper so there's a single guard
  # definition (see _uninstall_require_home header).
  _uninstall_require_home "uninstall_remove_shim" || return 1
  local home="${HOME:-}"

  local claude_home="${CLAUDE_HOME:-$HOME}"

  local shim_sentinel_begin="# --- coordinator claude-doe shim [generated] ---"
  local shim_sentinel_end="# --- end coordinator claude-doe shim ---"
  local legacy_marker_begin="# --- coordinator maximalist launch ---"
  local legacy_marker_end="# --- end coordinator maximalist launch ---"

  local overall_rc=0

  # ---- (a) #4a: shell shim owned file ----
  local shim_file="${claude_home}/shell/claude-doe-shim.sh"
  if [ -f "$shim_file" ] || [ -L "$shim_file" ]; then
    rm -f "$shim_file" || {
      echo "uninstall_remove_shim: failed to remove shim file ${shim_file}" >&2
      overall_rc=1
    }
  fi

  # ---- resolve target rc for (b), same detection as install ----
  local target_rc
  if [ -n "${COORDINATOR_SHIM_RC_OVERRIDE:-}" ]; then
    target_rc="${COORDINATOR_SHIM_RC_OVERRIDE}"
  elif [ -n "${COORDINATOR_SHIM_RC:-}" ]; then
    target_rc="${COORDINATOR_SHIM_RC}"
  else
    case "${SHELL:-}" in
      */zsh)  target_rc="${home}/.zshrc" ;;
      */bash) target_rc="${home}/.bashrc" ;;
      *)      target_rc="${home}/.zshrc" ;;
    esac
  fi

  # ---- (b) #4b: strip generated sentinel block from the detected rc ----
  if [ -f "$target_rc" ] && grep -qF "$shim_sentinel_begin" "$target_rc"; then
    if ! _uninstall_strip_sentinel_block "$target_rc" "$shim_sentinel_begin" "$shim_sentinel_end"; then
      echo "uninstall_remove_shim: failed to strip generated shim block from ${target_rc}" >&2
      overall_rc=1
    fi
  fi

  # ---- (c) #4c: remove legacy block from ${CLAUDE_HOME:-$HOME}/.bashrc ----
  # NOTE: the legacy block was hand-authored during 2026-07-04 bringup
  # directly into ~/.bashrc (gen-claude-doe-shim.sh only detects it and
  # migration-notes — never rewrites), so it is keyed off $HOME, matching
  # the install-side detection and the C1 harness fixture, NOT claude_home.
  local legacy_bashrc="${home}/.bashrc"
  if [ -f "$legacy_bashrc" ] && grep -qF "$legacy_marker_begin" "$legacy_bashrc"; then
    local expected_claude_bin="${home}/X/DoE-claude/coordinator/bin/claude-doe"
    local expected_repo="${home}/X/DoE-claude"
    local expected_line
    expected_line="claude() { REPO_DOE_CLAUDE=\"${expected_repo}\" command bash \"${expected_claude_bin}\" \"\$@\"; }"

    local body
    body="$(awk -v b="$legacy_marker_begin" \
      '$0 == b {f=1; next} /^# --- end coordinator maximalist launch/ {f=0} f {print}' \
      "$legacy_bashrc")"
    local body_trimmed expected_trimmed
    body_trimmed="$(printf '%s' "$body" | awk 'NF')"
    expected_trimmed="$(printf '%s' "$expected_line" | awk 'NF')"

    if [ "$body_trimmed" != "$expected_trimmed" ]; then
      echo "uninstall_remove_shim: legacy block in ${legacy_bashrc} has been hand-modified — refusing to clobber." >&2
      echo "  Expected body: ${expected_trimmed}" >&2
      echo "  Found body:    ${body_trimmed}" >&2
      echo "  To reset: remove the block between \"${legacy_marker_begin}\" and its end marker from ${legacy_bashrc} and re-run." >&2
      return 1
    fi

    if ! _uninstall_strip_legacy_block "$legacy_bashrc" "$legacy_marker_begin"; then
      echo "uninstall_remove_shim: failed to strip legacy block from ${legacy_bashrc}" >&2
      overall_rc=1
    fi
  fi

  # ---- (d) #10 (the Staff Engineer F0): claude-doe wrapper ----
  # install.md Step 3.5b writes the wrapper at "${CLAUDE_HOME:-$HOME}/.local/bin/claude-doe".
  # In real (non-test) deployment CLAUDE_HOME is unset, so this is $HOME/.local/bin/claude-doe.
  # The C1 sandbox fixtures place the wrapper directly under HOME (harness.sh:127,
  # test-endstates.sh:83) while setting CLAUDE_HOME to a distinct "$HOME/.claude" value for
  # the settings/machine-local surfaces — so this leg resolves the wrapper off $HOME (not
  # CLAUDE_HOME) to match both the fixture and install.md's real-world CLAUDE_HOME-unset case.
  local wrapper="${home}/.local/bin/claude-doe"
  if [ -f "$wrapper" ] || [ -L "$wrapper" ]; then
    rm -f "$wrapper" || {
      echo "uninstall_remove_shim: failed to remove claude-doe wrapper ${wrapper}" >&2
      overall_rc=1
    }
  fi

  return "$overall_rc"
}

# _uninstall_strip_sentinel_block <file> <begin_marker> <end_marker>
#
# Removes the block delimited by <begin_marker>..<end_marker> (inclusive)
# from <file>, plus one immediately-preceding blank line if present (mirrors
# how gen-claude-doe-shim.sh appends the block: leading blank + 3 lines).
# Writes atomically (temp file in same dir + mv). No-op if the sentinel is
# absent (caller already checked, but this stays safe standalone).
_uninstall_strip_sentinel_block() {
  local file="$1" begin_marker="$2" end_marker="$3"
  local out_dir tmp
  out_dir="$(dirname "$file")"
  tmp="$(mktemp "${out_dir}/.$(basename "$file").uninstall-strip.XXXXXX")" || {
    echo "_uninstall_strip_sentinel_block: failed to create temp file in ${out_dir}" >&2
    return 1
  }

  awk -v b="$begin_marker" -v e="$end_marker" '
    $0 == b { skip=1; next }
    skip && $0 == e { skip=0; next }
    skip { next }
    { print }
  ' "$file" > "$tmp" || { rm -f "$tmp"; return 1; }

  # Collapse a run of >=2 trailing blank lines the strip may have left
  # where the block used to sit, down to at most one — cosmetic only.
  awk 'BEGIN{blank=0} { if ($0 ~ /^[[:space:]]*$/) { blank++; if (blank<=1) print; } else { blank=0; print } }' \
    "$tmp" > "${tmp}.collapsed" && mv "${tmp}.collapsed" "$tmp"

  mv "$tmp" "$file"
}

# _uninstall_strip_legacy_block <file> <begin_marker>
#
# Removes the hand-authored legacy block from <file>. The legacy block's
# end marker varies across bringups (some carry an explicit
# "# --- end coordinator maximalist launch ---" line, some end at the
# claude() fn line with no explicit end sentinel) — strip through the first
# line starting with "# --- end coordinator maximalist launch" if present,
# otherwise through the claude() fn line itself (single-line body, matching
# the 2026-07-04 bringup shape captured in the surface map and C1 harness
# fixture). Writes atomically.
_uninstall_strip_legacy_block() {
  local file="$1" begin_marker="$2"
  local out_dir tmp
  out_dir="$(dirname "$file")"
  tmp="$(mktemp "${out_dir}/.$(basename "$file").uninstall-strip.XXXXXX")" || {
    echo "_uninstall_strip_legacy_block: failed to create temp file in ${out_dir}" >&2
    return 1
  }

  # State machine: 0 = outside block, 1 = inside block (before claude() fn
  # line seen), 2 = inside block, claude() fn line already consumed (only
  # relevant when the block also carries an explicit end-marker line
  # immediately after the fn — drop that trailing marker too).
  awk -v b="$begin_marker" '
    $0 == b { st=1; next }
    st==1 && /^# --- end coordinator maximalist launch/ { st=0; next }
    st==1 && /^claude\(\) \{/ { st=2; next }
    st==2 && /^# --- end coordinator maximalist launch/ { st=0; next }
    st==2 { st=0 }
    st==1 { next }
    { print }
  ' "$file" > "$tmp" || { rm -f "$tmp"; return 1; }

  awk 'BEGIN{blank=0} { if ($0 ~ /^[[:space:]]*$/) { blank++; if (blank<=1) print; } else { blank=0; print } }' \
    "$tmp" > "${tmp}.collapsed" && mv "${tmp}.collapsed" "$tmp"

  mv "$tmp" "$file"
}

# _uninstall_ml_set <key> <value>
#
# Clears (or sets) a machine-local registry key via the machine-local CLI,
# resolved WITHOUT relying on the CLI being on PATH or pre-installed (an
# uninstall may run against a sandbox, or after the ~/.claude/bin forwarders
# have already been removed by an earlier leg in the same run).
#
# Resolution is relative to THIS SCRIPT'S OWN LOCATION (coordinator/lib/),
# not the target coordinator root being uninstalled — the CLI belongs to
# the coordinator RUNNING the uninstall, which may differ from (or be
# entirely absent from, on a real full-remove) the target root that
# _uninstall_resolve_coordinator_root resolves. Using the target root here
# was the original bug: it worked only by coincidence when running-coordinator
# == target-coordinator, and broke both the sandboxed-target case (tests) and
# the real full-remove case (target root deleted mid-run). Resolution order:
#   1. this script's own sibling `../templates/bin/_machine_local.py`,
#      invoked directly via python3. Preferred over the `../bin/machine-local`
#      shim because the shim hardcodes "${CLAUDE_HOME:-$HOME}/.claude/bin/machine-local"
#      (Convention A: CLAUDE_HOME is a $HOME-substitute, .claude is appended)
#      — but this test suite (and uninstall-legs.sh's own internals, e.g.
#      uninstall_strip_settings_hooks) run under Convention B, where
#      CLAUDE_HOME is ALREADY `.claude`-suffixed. Under Convention B the shim
#      would double the suffix to `.claude/.claude` and fail to resolve.
#      _machine_local.py has no such hazard: it reads CLAUDE_HOME directly
#      (Convention B) and honors MACHINE_LOCAL_REGISTRY_DIR as rung-1.
#   2. this script's own sibling `../bin/machine-local` shim, invoked
#      directly, if _machine_local.py is absent — covers a real install
#      shape where templates/bin/ was pruned but bin/machine-local remains.
#   3. `machine-local` on PATH — last-resort fallback for a real,
#      non-sandboxed install with an already-installed CLI.
#
# In all cases MACHINE_LOCAL_REGISTRY_DIR / COORDINATOR_SETTINGS_HOME (set by
# callers to point at the sandbox/target registry) are honored via the
# invoked tool's OWN env-resolution chain — this helper does not re-derive
# them, it just locates the right binary to hand them to.
#
# `machine-local set <key> ""` clears a key by writing an empty-string value
# to registry.local.toml (per _machine_local.py cmd_set) — this is a value
# overwrite, NOT a key-delete; the key line persists with an empty value,
# which every registry reader (get/has) treats as "not a hit" (rung 4 of the
# resolution chain). This is the documented clear-a-key idiom for this
# registry, not a workaround.
#
# Fails loud (non-zero) if no resolution path succeeds, rather than
# silently no-op'ing a key-clear that the caller believes happened.
_uninstall_ml_set() {
  local key="$1" value="$2"

  # Resolve the machine-local CLI relative to THIS script's own location,
  # not the target coordinator root being uninstalled — the CLI belongs to
  # the coordinator RUNNING the uninstall (this very uninstall-legs.sh tree),
  # which may differ from (or be absent from, on a real full-remove) the
  # target root. uninstall-legs.sh lives in coordinator/lib/, so its sibling
  # templates/bin/_machine_local.py is the primary resolution path — invoked
  # directly via python3 so MACHINE_LOCAL_REGISTRY_DIR / COORDINATOR_SETTINGS_HOME
  # are honored via _machine_local.py's OWN env-resolution chain (rung-1 =
  # MACHINE_LOCAL_REGISTRY_DIR), independent of CLAUDE_HOME convention.
  # coordinator/bin/machine-local (Convention A: appends `.claude` to
  # CLAUDE_HOME itself) is deliberately NOT the primary path — this test
  # suite (and uninstall-legs.sh's own internals) run under Convention B
  # (CLAUDE_HOME already `.claude`-suffixed, see uninstall_strip_settings_hooks's
  # header comment), so calling the bin/machine-local shim there would double
  # the suffix to `.claude/.claude` and fail to resolve. It remains a
  # fallback for the real, non-sandboxed, PATH-based case below.
  local _self_dir
  _self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

  if [ -f "${_self_dir}/../templates/bin/_machine_local.py" ]; then
    python3 "${_self_dir}/../templates/bin/_machine_local.py" set "$key" "$value"
    return $?
  fi

  if [ -x "${_self_dir}/../bin/machine-local" ]; then
    "${_self_dir}/../bin/machine-local" set "$key" "$value"
    return $?
  fi

  if command -v machine-local >/dev/null 2>&1; then
    machine-local set "$key" "$value"
    return $?
  fi

  echo "_uninstall_ml_set: cannot resolve a machine-local CLI (no sibling bin/machine-local, no templates/bin/_machine_local.py, and no fallback on PATH) — cannot clear ${key}" >&2
  return 1
}

# uninstall_remove_substrate <mode>
#
# Reverses surfaces #3, #5, #6, #7, #8, #9 (settings-home-aware) —
# per docs/plans/2026-07-08-coordinator-uninstall.md § C5 and
# tasks/coordinator-uninstall/surface-map.md.
#
# <mode> is one of:
#   full-remove             — full teardown: settings-home tree + compat
#                              symlinks + .doe-root + ~/.claude/bin
#                              forwarders all removed (default if omitted).
#   revert-to-marketplace    — conservative: clear only the coordinator
#                              registry KEYS (leaves the machine-local dir,
#                              compat symlinks, whoami/venv, bin forwarders
#                              in place — other surfaces may still depend
#                              on them post-revert per the surface table's
#                              "Revert-to-marketplace delta" column).
#
# Settings-home / registry-dir resolution happens ONCE at the top and is
# reused for every removal target in this leg (the Staff Engineer F5 / prior-art
# Compatible #8) — never re-derive or repeat the literal at each site; this
# is exactly the seam the durable-substrate migration introduced
# (state/lessons/2026-07-06-hardcoded-durable-path-literals-are-the.yaml).
#
# Operator-config purge (#9) is gated behind a SEPARATE explicit opt-in
# (second positional arg "--purge-operator-config") — never implied by
# <mode> alone, matching AC9's conservative-preserve-by-default contract in
# BOTH end-states.
#
# Idempotent: every removal is a no-op (success) if its target is already
# absent. Fail-loud only on: (a) an unrecognized <mode>, (b) a machine-local
# key-clear that cannot resolve a CLI, (c) an operator-config purge that
# detects a hand-edited file without --force.
uninstall_remove_substrate() {
  # Review: code-reviewer F1 — guard $HOME/$CLAUDE_HOME-unset before deriving
  # destructive targets (see _uninstall_require_home header).
  _uninstall_require_home "uninstall_remove_substrate" || return 1

  local mode="${1:-full-remove}"
  shift || true
  local purge_operator_config=0
  local force_purge=0
  local arg
  for arg in "$@"; do
    case "$arg" in
      --purge-operator-config) purge_operator_config=1 ;;
      --force) force_purge=1 ;;
      *)
        echo "uninstall_remove_substrate: unrecognized flag '${arg}'" >&2
        return 1
        ;;
    esac
  done

  case "$mode" in
    full-remove|revert-to-marketplace) ;;
    *)
      echo "uninstall_remove_substrate: unrecognized mode '${mode}' (expected full-remove | revert-to-marketplace)" >&2
      return 1
      ;;
  esac

  # ---- resolve ONCE, reuse everywhere (the Staff Engineer F5) ----
  local claude_home="${CLAUDE_HOME:-$HOME}"
  local sh="${COORDINATOR_SETTINGS_HOME:-${claude_home}/.coordinator-claude-settings}"
  local ml_dir="${MACHINE_LOCAL_REGISTRY_DIR:-${sh}/machine-local}"

  local overall_rc=0

  # ---- #3: clear coordinator registry keys (both modes) ----
  # revert-to-marketplace clears the SAME coordinator keys (it keeps the
  # machine-local DIR, not the coordinator-owned key values inside it) —
  # per surface-map.md #3's "Revert-to-marketplace delta: Clear keys only;
  # keep machine-local dir".
  if [ -d "$ml_dir" ] || command -v machine-local >/dev/null 2>&1; then
    local key
    for key in \
      "plugin.mirrors.coordinator-claude.source_path" \
      "plugin.mirrors.coordinator-claude.live_path" \
      "plugin.mirrors.coordinator-claude.propagation_mode" \
      "coordinator.python" \
      "coordinator.whoami_src" \
      "repos.doe_claude"
    do
      if ! MACHINE_LOCAL_REGISTRY_DIR="$ml_dir" _uninstall_ml_set "$key" ""; then
        echo "uninstall_remove_substrate: failed to clear registry key ${key}" >&2
        overall_rc=1
      fi
    done
  else
    echo "uninstall_remove_substrate: no machine-local registry dir at ${ml_dir} and no CLI on PATH — nothing to clear (no-op)" >&2
  fi

  # ---- #5: whoami + venv (durable, settings-home) ----
  rm -rf "${sh}/coordinator-whoami" "${sh}/.coordinator-venv" || {
    echo "uninstall_remove_substrate: failed to remove ${sh}/coordinator-whoami or ${sh}/.coordinator-venv" >&2
    overall_rc=1
  }
  # Compat symlink at the old ~/.claude path.
  local whoami_compat="${claude_home}/coordinator-whoami"
  if [ -e "$whoami_compat" ] || [ -L "$whoami_compat" ]; then
    rm -f "$whoami_compat" || {
      echo "uninstall_remove_substrate: failed to remove compat symlink ${whoami_compat}" >&2
      overall_rc=1
    }
  fi
  # Legacy venv path — idempotent no-op if already gone (it already is, on
  # every settings-home-migrated machine; harmless to also try on one that
  # somehow still has it).
  # Review: code-reviewer F5 — unconditional in both modes (unlike #7/#8)
  # because this is a pre-migration legacy path with no revert-mode
  # dependents; not gated behind full-remove.
  rm -rf "${claude_home}/.coordinator-venv" || {
    echo "uninstall_remove_substrate: failed to remove legacy ${claude_home}/.coordinator-venv" >&2
    overall_rc=1
  }

  # ---- #6: .doe-root pointer (BOTH modes) ----
  # NOTE ordering: caller (C7 orchestrator) sequences this AFTER the
  # settings.json strip leg (C3) has resolved <coordinator_root> — this
  # leg does not itself depend on .doe-root for its own resolution
  # (registry-key clears and whoami/venv/bin targets are all env-resolved
  # above), so it is safe for THIS leg to remove it unconditionally once
  # invoked, in either mode.
  #
  # revert-to-marketplace ALSO removes .doe-root (not full-remove-only):
  # resolve-coordinator-clone.sh's pointer tier (reads .doe-root) OUTRANKS
  # the flat-marketplace-tree tier in BOTH --for-content and --for-git-ops
  # precedence chains (see resolve-coordinator-clone.sh's precedence
  # comment). Leaving .doe-root behind after a "revert" would mean the
  # resolver keeps returning the DoE clone via the pointer tier instead of
  # the flat tree — i.e. revert-to-marketplace would not actually revert.
  # A real marketplace install has no .doe-root. Per
  # docs/plans/2026-07-08-coordinator-uninstall.md surface-map row 6, the
  # revert-to-marketplace delta for this surface is "remove (marketplace
  # plugin doesn't need it)" — resolves plan Decision #2.
  rm -f "${claude_home}/.doe-root" || {
    echo "uninstall_remove_substrate: failed to remove ${claude_home}/.doe-root" >&2
    overall_rc=1
  }

  if [ "$mode" = "full-remove" ]; then
    # ---- #7: ~/.claude/bin/ coordinator-owned forwarders (individual rm, NEVER rm -rf) ----
    local bin_dir="${claude_home}/bin"
    local coord_bin_name
    for coord_bin_name in \
      machine-local _machine_local.py machine-local.cmd \
      claude-home _claude_home.py claude-home.cmd \
      resolve-coordinator-clone coordinator-settings-home platform-localize.sh
    do
      local target="${bin_dir}/${coord_bin_name}"
      if [ -f "$target" ] || [ -L "$target" ]; then
        rm -f "$target" || {
          echo "uninstall_remove_substrate: failed to remove ${target}" >&2
          overall_rc=1
        }
      fi
    done

    # ---- #8: coordinator-authored artifacts under settings-home (full-remove only) ----
    # BOUNDARY (blanket-with-provenance, agent-install-contract.md § Uninstall
    # boundary): removes ONLY coordinator-authored artifacts under
    # <settings-home>; MUST NOT rm -rf the $sh root or sweep any
    # <settings-home>/<repo-id>/ consumer durable-data subtree. Mirrors the
    # "individual rm, NEVER rm -rf" discipline already used on the #7
    # ~/.claude/bin forwarder leg above — this is that same discipline
    # applied to the settings-home root now that a consumer durable-data
    # plane (e.g. <settings-home>/example-cockpit-repo/store.db) can share it.
    #
    # The allowlist below is the COMPLETE coordinator-authored footprint
    # under $sh, derived by grepping every writer of $sh (NOT hand-transcribed
    # from a prior enumeration — an incomplete allowlist silently under-cleans
    # and leaves the rmdir below unable to fire, per the Director of Engineering review 2026-07-09):
    #   - coordinator-whoami/, .coordinator-venv/  — already removed at #5 above
    #   - machine-local/                            — install-substrate.sh _ml_dst
    #   - bin/                                      — install-substrate.sh _bin_dst
    #   - settings-manifest.md                      — install-substrate.sh _manifest_dst
    #   - state/handoffs                            — the install/orient baton
    #     rendezvous (agent-install-contract.md § The rendezvous); nothing else
    #     is ever written under <settings-home>/state/, so only the handoffs
    #     subpath (not the whole state/ dir) is on the allowlist.
    # `setup/` is DELIBERATELY EXCLUDED: migrate-substrate-to-settings-home.sh's
    # own header states "setup/ is intentionally NOT migrated: nothing reads
    # setup/ from settings-home at runtime" — the executing migration script's
    # runtime behavior outranks the (stale) machine-local-registry.md §11
    # Namespace table row that still lists setup/ under this namespace.
    #
    # DISCRIMINATOR is BINARY, not a "plausible <repo-id>?" heuristic: only the
    # named allowlist entries above are removed; every OTHER top-level entry
    # under $sh — including any consumer <settings-home>/<repo-id>/ durable
    # subtree — is preserved by default. detect-then-fail-loud is reserved for
    # its real job below: an allowlist artifact that fails to `rm`.
    if [ -d "$sh" ]; then
      rm -rf "${sh:?}/machine-local" "${sh:?}/bin" "${sh:?}/state/handoffs" || {
        echo "uninstall_remove_substrate: failed to remove coordinator-owned machine-local/bin/state-handoffs under ${sh}" >&2
        overall_rc=1
      }
      if [ -f "${sh}/settings-manifest.md" ] || [ -L "${sh}/settings-manifest.md" ]; then
        rm -f "${sh}/settings-manifest.md" || {
          echo "uninstall_remove_substrate: failed to remove ${sh}/settings-manifest.md" >&2
          overall_rc=1
        }
      fi
      # state/ itself is only ever a container for handoffs/ (no other
      # coordinator writer targets <settings-home>/state/) — drop it once
      # handoffs/ is gone, but only if it is now empty; never rm -rf it.
      rmdir "${sh}/state" 2>/dev/null || true
      # Remove $sh ITSELF only if it is now empty. If any consumer
      # <settings-home>/<repo-id>/ durable subtree remains, $sh is left in
      # place with the consumer data intact — MUST NOT rm -rf "$sh".
      rmdir "$sh" 2>/dev/null || true
    fi
    # Compat symlink for machine-local (settings-home dir above already
    # covers the real dir; this removes the OLD ~/.claude-side pointer).
    local ml_compat="${claude_home}/machine-local"
    if [ -e "$ml_compat" ] || [ -L "$ml_compat" ]; then
      rm -f "$ml_compat" || {
        echo "uninstall_remove_substrate: failed to remove compat symlink ${ml_compat}" >&2
        overall_rc=1
      }
    fi
  fi
  # revert-to-marketplace: deliberately KEEPS the settings-home machine-local
  # subtree and the ~/.claude/bin forwarders (#3/#7) — per surface-map.md's
  # "Revert-to-marketplace delta" column ("keep machine-local dir" / "keep
  # if marketplace plugin still resolves via them"). Only the registry KEY
  # VALUES were cleared above. .doe-root (#6) is now removed in BOTH modes
  # (see above) — it is a resolution-shadowing pointer, not passive config,
  # so it does not get the same "keep, other surfaces may depend on it"
  # treatment as the forwarders.

  # ---- #9: operator config (gated, both modes) ----
  if [ "$purge_operator_config" -eq 1 ]; then
    if ! _uninstall_purge_operator_config "$claude_home" "$force_purge"; then
      overall_rc=1
    fi
  fi

  return "$overall_rc"
}

# _uninstall_purge_operator_config <claude_home> <force>
#
# Reverses surface #9 — ~/.claude/{coordinator-identity.yaml,
# working-repos.yaml, CLAUDE.local.md} — ONLY when explicitly invoked via
# --purge-operator-config (never implied by mode alone, per AC9). Hand-edit
# detection: re-render each file's known-fixed shape and byte-compare
# against what's on disk; ANY diff is treated as possibly-hand-edited
# (fail-safe option (b) — the Staff Engineer: endorsed without reservation) and
# refuses to remove it unless <force> is 1.
#
#   coordinator-identity.yaml — fixed template (install.md Phase 2 Step 3):
#     re-render using the operator_name already recorded in the file itself
#     (there is nothing else to source it from at uninstall time), byte-
#     compare against disk. A mismatch means the file was hand-edited AFTER
#     being written (not merely that operator_name differs from some other
#     source — we have no other source of truth to differ against).
#   working-repos.yaml — NOT re-derivable at uninstall time (its content
#     comes from repo-discovery, run once at install time; re-running
#     discovery now would almost certainly differ from what was captured
#     then, which is not "hand-edited", just "time has passed"). Per AC9's
#     fail-safe framing this leg treats working-repos.yaml the same as
#     CLAUDE.local.md: it does not attempt a byte-exact re-render (there is
#     no fixed template to re-render against), so it is purged only when
#     <force>=1, treating "cannot prove it's unmodified" as "assume it may
#     be hand-relevant" — i.e. the SAME fail-safe posture as (b), applied to
#     a file with no static template to check against.
#   CLAUDE.local.md — template-rendered (CLAUDE.local.md.tmpl); re-render
#     with the CURRENT PM_NAME (from coordinator-identity.yaml) and CURRENT
#     WORKING_REPOS block (read verbatim from the on-disk working-repos.yaml
#     use is not exact since the template consumes a different WORKING_REPOS
#     shape than the persisted YAML — so, per AC9 fail-safe option (b), ANY
#     diff from a fresh render (or an unresolvable render) is treated as
#     possibly-hand-edited).
_uninstall_purge_operator_config() {
  local claude_home="$1" force="$2"
  local identity_file="${claude_home}/coordinator-identity.yaml"
  local working_repos_file="${claude_home}/working-repos.yaml"
  local claude_local_file="${claude_home}/CLAUDE.local.md"
  local overall_rc=0

  # ---- coordinator-identity.yaml: re-render + byte-compare ----
  if [ -f "$identity_file" ]; then
    local operator_name
    operator_name="$(awk -F': ' '/^operator_name:/ { $1=""; sub(/^ /,""); print; exit }' "$identity_file")"
    local expected
    expected="$(cat <<EOF
# ~/.claude/coordinator-identity.yaml — operator-local, NEVER a publish target
version: 1
operator_name: ${operator_name}
EOF
)"
    local actual
    actual="$(cat "$identity_file")"
    if [ "$force" -eq 1 ] || [ "$expected" = "$actual" ]; then
      rm -f "$identity_file" || { echo "_uninstall_purge_operator_config: failed to remove ${identity_file}" >&2; overall_rc=1; }
    else
      echo "_uninstall_purge_operator_config: ${identity_file} differs from a fresh re-render — possibly hand-edited. Refusing to remove without --force." >&2
      overall_rc=1
    fi
  fi

  # ---- working-repos.yaml: no static template to re-render against; ----
  # ---- fail-safe requires --force (see function header). ----
  if [ -f "$working_repos_file" ]; then
    if [ "$force" -eq 1 ]; then
      rm -f "$working_repos_file" || { echo "_uninstall_purge_operator_config: failed to remove ${working_repos_file}" >&2; overall_rc=1; }
    else
      echo "_uninstall_purge_operator_config: ${working_repos_file} has no fixed template to re-render against — possibly hand-edited. Refusing to remove without --force." >&2
      overall_rc=1
    fi
  fi

  # ---- CLAUDE.local.md: template-rendered; any diff from fresh render (or ----
  # ---- unresolvable render) => possibly hand-edited => --force required. ----
  if [ -f "$claude_local_file" ]; then
    local coordinator_root
    coordinator_root="$(_uninstall_resolve_coordinator_root 2>/dev/null)" || coordinator_root=""
    local render_tmpl="${coordinator_root}/templates/CLAUDE.local.md.tmpl"
    local render_bin="${coordinator_root}/bin/render-template.sh"

    if [ "$force" -eq 1 ]; then
      rm -f "$claude_local_file" || { echo "_uninstall_purge_operator_config: failed to remove ${claude_local_file}" >&2; overall_rc=1; }
    elif [ -n "$coordinator_root" ] && [ -f "$render_tmpl" ] && [ -f "$render_bin" ]; then
      local operator_name
      operator_name="$(awk -F': ' '/^operator_name:/ { $1=""; sub(/^ /,""); print; exit }' "$identity_file" 2>/dev/null)"
      local working_repos_block
      working_repos_block="$(cat "$working_repos_file" 2>/dev/null || true)"

      local rendered_tmp
      rendered_tmp="$(mktemp)" || { echo "_uninstall_purge_operator_config: mktemp failed" >&2; return 1; }
      if bash "$render_bin" "$render_tmpl" -o "$rendered_tmp" \
           PM_NAME="${operator_name}" WORKING_REPOS="${working_repos_block}" 2>/dev/null \
         && diff -q "$rendered_tmp" "$claude_local_file" >/dev/null 2>&1; then
        rm -f "$claude_local_file" || { echo "_uninstall_purge_operator_config: failed to remove ${claude_local_file}" >&2; overall_rc=1; }
      else
        echo "_uninstall_purge_operator_config: ${claude_local_file} differs from a fresh template re-render (or re-render failed) — possibly hand-edited. Refusing to remove without --force." >&2
        overall_rc=1
      fi
      rm -f "$rendered_tmp"
    else
      echo "_uninstall_purge_operator_config: cannot resolve coordinator root/template to re-render ${claude_local_file} — possibly hand-edited. Refusing to remove without --force." >&2
      overall_rc=1
    fi
  fi

  return "$overall_rc"
}

# uninstall_set_plugin_endstate <mode>
#
# Reverses surface #1 (plugin-source wiring) — per
# docs/plans/2026-07-08-coordinator-uninstall.md § C6 and
# tasks/coordinator-uninstall/surface-map.md #1. Ends the install singularity-
# clean in either end-state (AC7):
#
#   full-remove             — clears the mirror wiring keys
#                              (plugin.mirrors.coordinator-claude.*) so no
#                              coordinator tree resolves via the registry.
#                              Anti-scope: does NOT delete <DoE>/coordinator
#                              source — that is a separate, PM-gated decision
#                              (handoff anti-scope; plan Anti-scope section).
#   revert-to-marketplace    — re-registers the flat
#                              ${CLAUDE_HOME:-$HOME}/.claude/plugins/coordinator-claude
#                              plugin AND clears live_path (else
#                              check-install-singularity.sh CHECK 4 sees BOTH
#                              the flat tree and live_path and fails as a
#                              split — surface-map.md's "Revert-to-marketplace
#                              delta" column for surface #1).
#
# CHECK 5 tri-file contract (the Staff Engineer F3): once live_path is absent, ALL THREE
# present settings files (settings.json, settings.local.json,
# known_marketplaces.json — check-install-singularity.sh:471-532) must AGREE
# on the flat coordinator-claude path, or CHECK 5 fails the revert as a
# split. This leg satisfies that postcondition the SAME way install.md does
# for this same branch (install.md:1088, "Two-surface model" note at
# install.md:1225): it invokes platform-localize.sh, which scans
# ${CLAUDE_HOME:-$HOME}/.claude/plugins/ for directories carrying a
# .claude-plugin/ manifest and regenerates BOTH settings.local.json's
# extraKnownMarketplaces AND known_marketplaces.json from that single scan —
# so the two derived files agree by construction. settings.json itself is
# left untouched by this leg (the harness/real-world settings.json never
# carries an extraKnownMarketplaces.coordinator-claude entry under the
# maximalist shape being reversed here — the flat marketplace registration
# lives only in the derived files), matching CHECK 5's "absent -> concordant"
# guard (check-install-singularity.sh:472-476).
#
# Env-resolves every path: ${CLAUDE_HOME:-$HOME}, resolved coordinator root
# (via _uninstall_resolve_coordinator_root, same seam as C3/C5) for the
# source of the re-registered plugin payload, and
# ${MACHINE_LOCAL_REGISTRY_DIR:-<settings-home>/machine-local} for the
# registry-key clears (shared with C5's _uninstall_ml_set, same resolution
# order — never a re-hardcoded literal, the Staff Engineer F5).
#
# Idempotent: re-run is a no-op — clearing an already-empty key is a no-op
# key-set; re-copying an already-present flat plugin tree is skipped when the
# destination already exists; re-running platform-localize.sh is idempotent
# by its own design ("compares before writing — no disk churn if already
# correct", platform-localize.sh:20).
uninstall_set_plugin_endstate() {
  # Review: code-reviewer F1 — guard $HOME/$CLAUDE_HOME-unset before deriving
  # destructive targets (see _uninstall_require_home header).
  _uninstall_require_home "uninstall_set_plugin_endstate" || return 1

  local mode="${1:-full-remove}"

  case "$mode" in
    full-remove|revert-to-marketplace) ;;
    *)
      echo "uninstall_set_plugin_endstate: unrecognized mode '${mode}' (expected full-remove | revert-to-marketplace)" >&2
      return 1
      ;;
  esac

  local claude_home="${CLAUDE_HOME:-$HOME}"
  local sh="${COORDINATOR_SETTINGS_HOME:-${claude_home}/.coordinator-claude-settings}"
  local ml_dir="${MACHINE_LOCAL_REGISTRY_DIR:-${sh}/machine-local}"

  local overall_rc=0

  # ---- revert-to-marketplace ONLY: clear the mirror wiring keys ----
  # (source_path stays; the leg only clears live_path + propagation_mode,
  # matching the surface table: full-remove clears wiring but leaves
  # <DoE>/coordinator SOURCE intact — clearing source_path too would be
  # indistinguishable from deleting the source registration, which is out
  # of scope).
  #
  # full-remove is deliberately EXCLUDED here: uninstall_remove_substrate
  # (the prior leg, surface #3) already clears these same two keys AND then
  # rm -rf's the entire settings-home tree (surface #8), including
  # ${ml_dir}. Re-clearing here after that rm -rf would re-create the
  # tree via _machine_local.py's auto-create-on-write behavior (bug found
  # via test-endstates.sh full-remove assertion: settings-home tree gone —
  # still present), silently undoing the just-completed full-remove.
  # revert-to-marketplace's prior leg clears the keys but does NOT rm -rf
  # the settings-home tree (it keeps the machine-local dir — surface-map.md
  # #3's "Revert-to-marketplace delta: Clear keys only; keep machine-local
  # dir") — so re-clearing here is genuinely idempotent, not resurrective.
  if [ "$mode" = "revert-to-marketplace" ] && { [ -d "$ml_dir" ] || command -v machine-local >/dev/null 2>&1; }; then
    local key
    for key in \
      "plugin.mirrors.coordinator-claude.live_path" \
      "plugin.mirrors.coordinator-claude.propagation_mode"
    do
      if ! MACHINE_LOCAL_REGISTRY_DIR="$ml_dir" _uninstall_ml_set "$key" ""; then
        echo "uninstall_set_plugin_endstate: failed to clear registry key ${key}" >&2
        overall_rc=1
      fi
    done
  elif [ "$mode" = "revert-to-marketplace" ]; then
    echo "uninstall_set_plugin_endstate: no machine-local registry dir at ${ml_dir} and no CLI on PATH — nothing to clear (no-op)" >&2
  fi

  if [ "$mode" = "full-remove" ]; then
    # full-remove: wiring cleared above is sufficient — no flat tree to
    # create, no further action. End-state: no coordinator tree resolves
    # (check-install-singularity.sh CHECK 4 -> _tree_count == 0).
    return "$overall_rc"
  fi

  # ---- revert-to-marketplace: re-register the flat plugin tree ----
  local flat_plugin_dir="${claude_home}/plugins/coordinator-claude"

  if [ ! -d "$flat_plugin_dir" ]; then
    local coordinator_root
    coordinator_root="$(_uninstall_resolve_coordinator_root 2>/dev/null)" || coordinator_root=""

    if [ -z "$coordinator_root" ]; then
      echo "uninstall_set_plugin_endstate: cannot resolve coordinator root — cannot re-register the flat marketplace plugin at ${flat_plugin_dir}" >&2
      overall_rc=1
    elif [ ! -d "${coordinator_root}/.claude-plugin" ]; then
      echo "uninstall_set_plugin_endstate: resolved coordinator root ${coordinator_root} has no .claude-plugin/ manifest — cannot re-register the flat marketplace plugin" >&2
      overall_rc=1
    else
      mkdir -p "$(dirname "$flat_plugin_dir")" || {
        echo "uninstall_set_plugin_endstate: failed to create ${claude_home}/plugins" >&2
        overall_rc=1
      }
      if ! cp -R "$coordinator_root" "$flat_plugin_dir"; then
        echo "uninstall_set_plugin_endstate: failed to copy ${coordinator_root} -> ${flat_plugin_dir}" >&2
        overall_rc=1
      fi
    fi
  fi

  # ---- satisfy CHECK 5's tri-file agreement postcondition ----
  # Same mechanism install.md uses to satisfy this same branch forward
  # (install.md:1088, § Two-surface model at install.md:1225): invoke
  # platform-localize.sh so settings.local.json + known_marketplaces.json
  # are (re)derived from a single directory scan and therefore agree.
  local localize_script="${sh}/bin/platform-localize.sh"
  if [ ! -f "$localize_script" ]; then
    local coordinator_root2
    coordinator_root2="$(_uninstall_resolve_coordinator_root 2>/dev/null)" || coordinator_root2=""
    if [ -n "$coordinator_root2" ] && [ -f "${coordinator_root2}/templates/bin/platform-localize.sh" ]; then
      localize_script="${coordinator_root2}/templates/bin/platform-localize.sh"
    fi
  fi

  if [ -f "$localize_script" ]; then
    # platform-localize.sh derives its OWN working CLAUDE_HOME as
    # "${CLAUDE_HOME:-$HOME}/.claude" (Convention A, appends the suffix
    # itself). This leg's ${claude_home} is ALREADY .claude-suffixed (per
    # this test suite's sandbox convention — see uninstall_strip_settings_hooks's
    # header comment), so CLAUDE_HOME must be left UNSET for this
    # subprocess and HOME set to the un-suffixed parent instead — passing
    # claude_home through as CLAUDE_HOME here would double the suffix to
    # .claude/.claude (the same footgun the header comments elsewhere in
    # this file warn against).
    if ! env -u CLAUDE_HOME HOME="${claude_home%/.claude}" bash "$localize_script"; then
      echo "uninstall_set_plugin_endstate: platform-localize.sh failed — settings.local.json / known_marketplaces.json may not agree with the flat plugin tree (CHECK 5 may fail)" >&2
      overall_rc=1
    fi
  else
    echo "uninstall_set_plugin_endstate: cannot resolve platform-localize.sh (checked ${sh}/bin and coordinator root templates/bin) — cannot regenerate settings.local.json / known_marketplaces.json; CHECK 5 tri-file agreement is NOT guaranteed" >&2
    overall_rc=1
  fi

  return "$overall_rc"
}
