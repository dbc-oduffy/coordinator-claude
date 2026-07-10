#!/usr/bin/env bash
# coordinator/bin/coordinator-uninstall.sh — coordinator uninstall orchestrator
#
# Purpose: CLI entrypoint that sequences the uninstall legs
#   (coordinator/lib/uninstall-legs.sh, C3-C6) in dependency order to
#   reverse the maximalist coordinator install's out-of-repo surfaces
#   (tasks/coordinator-uninstall/surface-map.md). Two end-states:
#   full-remove (default) and revert-to-marketplace (--keep-marketplace).
#
# Fail-loud-on-ambiguity doctrine (prior-art Compatible #6): this
#   orchestrator's aggregation instantiates coordinator/CLAUDE.md §
#   Implementation Standards's "detect-then-fail-loud on ambiguity, never
#   detect-then-silently-pick" — already the discipline every leg follows;
#   noted here for traceability. Concretely: if any leg fails, the
#   orchestrator stops sequencing (does not continue past a fail-loud leg)
#   and reports which surface + remediation, rather than silently
#   continuing into a possibly-inconsistent end-state.
#
# Sequencing (dependency order): strip settings hooks (resolves
#   coordinator-root FIRST, since later legs' resolution and the strip's
#   own identity-key baking both depend on it being resolved consistently)
#   -> remove shim+wrapper -> remove substrate (.doe-root removal AFTER the
#   strip has resolved root, so an early .doe-root deletion can't strand
#   the strip's own root-resolution fallback chain) -> set plugin end-state
#   (last, since it flips the registry wiring / re-registers the flat tree
#   the OTHER legs no longer need to know about).
#
# --dry-run performs ZERO filesystem writes and ZERO registry-key clears —
#   not merely "prints the plan" (the Staff Engineer F2 / AC8). Implemented by NEVER
#   calling into the mutating leg functions at all when --dry-run is set;
#   the ordered plan is printed from a static description, not by invoking
#   each leg with some hypothetical "preview" flag the legs don't have.
#
# Idempotent: every leg is independently idempotent (see uninstall-legs.sh
#   headers); re-running this orchestrator with the same mode is a no-op.
#
# Spec backlink: docs/plans/2026-07-08-coordinator-uninstall.md § C7
# Surface source of truth: tasks/coordinator-uninstall/surface-map.md
# Leg source of truth: coordinator/lib/uninstall-legs.sh

set -uo pipefail

# ---- bash >=4 guard (must parse on bash 3.2, matching gen-settings-hooks.sh:20) ----
if [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "ERROR: coordinator-uninstall.sh requires bash >= 4." >&2
  echo "Remediation: brew install bash  (then relaunch your shell or prefix with /opt/homebrew/bin/bash)" >&2
  exit 1
fi

_SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_ROOT="$(cd "${_SELF_DIR}/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: coordinator-uninstall.sh [OPTIONS]

Reverses the maximalist coordinator install's out-of-repo surfaces
(settings.json generated hooks, shell shim/wrapper, machine-local registry
keys, whoami/venv, .doe-root pointer, ~/.claude/bin forwarders, plugin
wiring). All filesystem/registry targets are resolved from environment
overrides (CLAUDE_HOME, COORDINATOR_SETTINGS_HOME, MACHINE_LOCAL_REGISTRY_DIR)
— never a hardcoded real-user path.

Options:
  (none)                    Full-remove (default, PM-ratified): reverses
                             every surface, leaves no coordinator tree
                             resolvable (check-install-singularity.sh ->
                             "no coordinator tree resolved").
  --keep-marketplace         Revert-to-marketplace: re-registers the flat
                             ~/.claude/plugins/coordinator-claude tree and
                             clears live_path, instead of removing wiring
                             entirely. Machine-local dir and ~/.claude/bin
                             forwarders are preserved (other surfaces may
                             still depend on them post-revert); .doe-root is
                             REMOVED (it is a resolution-shadowing pointer
                             that would otherwise outrank the re-registered
                             flat tree and defeat the revert).
  --purge-operator-config    Also purge operator-config surface #9
                             (coordinator-identity.yaml, working-repos.yaml,
                             CLAUDE.local.md). Conservative preserve-by-
                             default; fails loud on a hand-edited file
                             unless combined with --force.
  --force                    Fail-safe override for --purge-operator-config
                             — required to remove a file that differs from
                             its fresh re-render (possibly hand-edited).
  --dry-run                  Print the ordered leg plan and perform ZERO
                             filesystem writes and ZERO registry-key clears.
                             Not merely "prints the plan" — every mutating
                             call is skipped entirely, not run in some
                             preview mode.
  -h, --help                  Show this help and exit 0.

Examples:
  coordinator-uninstall.sh                         # full-remove
  coordinator-uninstall.sh --keep-marketplace       # revert-to-marketplace
  coordinator-uninstall.sh --dry-run                # print plan, no writes
  coordinator-uninstall.sh --purge-operator-config --force
EOF
}

MODE="full-remove"
PURGE_OPERATOR_CONFIG=0
FORCE=0
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --keep-marketplace)
      MODE="revert-to-marketplace"
      ;;
    --purge-operator-config)
      PURGE_OPERATOR_CONFIG=1
      ;;
    --force)
      FORCE=1
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "coordinator-uninstall.sh: unrecognized option '$1'" >&2
      echo "Run with -h/--help for usage." >&2
      exit 1
      ;;
  esac
  shift
done

# ---- print the ordered plan (always, both dry-run and real) ----
echo "coordinator-uninstall: mode=${MODE} purge-operator-config=${PURGE_OPERATOR_CONFIG} force=${FORCE} dry-run=${DRY_RUN}"
echo "coordinator-uninstall: ordered plan:"
echo "  1. strip settings.json generated hooks (resolves coordinator-root)"
echo "  2. remove shell shim + wrapper (#4a/#4b/#4c/#10)"
echo "  3. remove substrate (registry keys, whoami/venv, .doe-root, ~/.claude/bin forwarders, settings-home tree)"
if [ "$PURGE_OPERATOR_CONFIG" -eq 1 ]; then
  echo "     (+ purge operator config, force=${FORCE})"
fi
echo "  4. set plugin end-state (${MODE})"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "coordinator-uninstall: --dry-run — performing ZERO filesystem writes and ZERO registry-key clears."
  exit 0
fi

# ---- source legs (only for a real run — dry-run must not even load a ----
# ---- mutating call path, though sourcing itself defines functions only ----
# ---- and does not mutate; kept after the dry-run exit for clarity/least- ----
# ---- surprise: no leg function is ever invoked on the dry-run path). ----
# shellcheck source=../lib/uninstall-legs.sh
source "${_ROOT}/lib/uninstall-legs.sh"

fail_loud() {
  local surface="$1" remediation="$2"
  echo "coordinator-uninstall: FAILED at surface: ${surface}" >&2
  echo "  Remediation: ${remediation}" >&2
  echo "coordinator-uninstall: stopping — not continuing past a fail-loud leg (fail-loud-on-ambiguity doctrine)." >&2
  exit 1
}

# ---- 1. strip settings.json generated hooks (resolves coordinator-root FIRST) ----
if ! uninstall_strip_settings_hooks; then
  fail_loud "settings.json generated hooks (surface #2)" \
    "Resolve coordinator root explicitly (COORDINATOR_ROOT env, machine-local repos.doe_claude, REPO_DOE_CLAUDE env, or \${CLAUDE_HOME:-\$HOME}/.doe-root pointer) and re-run."
fi

# ---- 2. remove shim + wrapper (#4a/#4b/#4c/#10) ----
if ! uninstall_remove_shim; then
  fail_loud "shell shim / wrapper (surfaces #4a/#4b/#4c/#10)" \
    "Check stderr above for a hand-modified legacy ~/.bashrc block or a removal failure; resolve manually then re-run (this leg is idempotent — re-running after a manual fix is safe)."
fi

# ---- 3. remove substrate (.doe-root removal AFTER strip has resolved root) ----
_SUBSTRATE_ARGS=()
if [ "$PURGE_OPERATOR_CONFIG" -eq 1 ]; then
  _SUBSTRATE_ARGS+=(--purge-operator-config)
  if [ "$FORCE" -eq 1 ]; then
    _SUBSTRATE_ARGS+=(--force)
  fi
fi
if ! uninstall_remove_substrate "$MODE" "${_SUBSTRATE_ARGS[@]}"; then
  fail_loud "substrate (registry keys / whoami / venv / .doe-root / ~/.claude/bin forwarders / settings-home tree, surfaces #3/#5/#6/#7/#8/#9)" \
    "Check stderr above for the specific removal/registry-clear failure. If it names a hand-edited operator-config file, re-run with --purge-operator-config --force to override, or omit --purge-operator-config to preserve it."
fi

# ---- 4. set plugin end-state (last — flips registry wiring / re-registers flat tree) ----
if ! uninstall_set_plugin_endstate "$MODE"; then
  fail_loud "plugin end-state (surface #1)" \
    "Check stderr above — likely an unresolvable coordinator root (for revert-to-marketplace re-registration) or a platform-localize.sh failure (CHECK 5 tri-file agreement not guaranteed). Resolve and re-run (idempotent)."
fi

echo "coordinator-uninstall: complete (mode=${MODE})."
exit 0
