#!/usr/bin/env bash
# coordinator-state-root.sh — canonical state-root seam resolver.
#
# Purpose: single entry point for resolving the coordinator state directory root.
# Encodes the ratified taxonomy from the stop-the-rot plan and the DoE plane
# routing from the doe-authoring-repo plan, so every state-writing script can
# call coordinator_state_root instead of open-coding a root variable.
#
# Spec backlinks:
#   docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C2 / AC2
#   docs/plans/2026-07-04-doe-authoring-repo-build-subject-matter-.md § W2.3
#
# Public API (source this file, then call):
#   coordinator_state_root [--central] [--subject <engine|doctrine>] [--artifact <path>]
#     Prints the resolved state root path to stdout.
#     Returns 0 on success, 1 on failure (stderr carries remediation message),
#     or 2 when --artifact resolves to cross-cutting (human routing required).
#
#   coordinator_state_root --print-map
#     Prints a single-line JSON object mapping the two central subjects to their
#     resolved state roots (no trailing newline):
#       {"schema":"coordinator-state-root-map/v1","subjects":{"doctrine":"<doe>/state","engine":"<example-orchestration-hub>/state"}}
#     Unresolvable subjects emit JSON null (not a hard error) plus one stderr WARN
#     line per unresolvable subject; always returns 0.
#     Exists so a caching cross-plane consumer (example-orchestration-hub daemon) reads the whole
#     central map in one spawn rather than calling this function per-write.
#     --print-map is standalone: cannot be combined with --subject or --artifact
#     (returns 1). --central alongside --print-map is harmless/ignored.
#
# Five routing rules:
#
#   Rule 1  --central --subject doctrine
#             → $(coordinator_doe_root)/state
#             Fail-loud (return 1) if coordinator_doe_root cannot resolve the
#             DoE-claude repo. Does NOT fall back to example-orchestration-hub.
#
#   Rule 2  --central --subject engine
#             → $(coordinator_example_orchestration_hub_root)/state
#
#   Rule 3  --central --artifact <path>
#             → call coordinator_artifact_subject <path>; map result:
#                 doctrine      → DoE state  (Rule 1)
#                 engine        → example-orchestration-hub state (Rule 2)
#                 cross-cutting → fail-loud: return 2, emit a one-line stderr
#                                 note; do NOT print a state path.
#             Preserves the classifier's exit-2 semantics for cross-cutting.
#
#   Rule 4  --central  (no --subject, no --artifact)  [BACKWARD-COMPAT DEFAULT]
#             → $(coordinator_example_orchestration_hub_root)/state
#             Every existing --central caller resolves to example-orchestration-hub, unchanged.
#
#   Rule 5  (no --central)  [BACKWARD-COMPAT DEFAULT]
#             → $(coordinator_example_orchestration_hub_root)/state  when cwd git root IS the meta-repo
#               $GIT_ROOT/state                  when cwd git root is a sibling repo
#             Fail-loud on unresolvable git root.
#
# Backward-compatibility guarantee:
#   Callers that pass only --central (no --subject / --artifact) continue to
#   resolve to the example-orchestration-hub state root exactly as before. The new flags are
#   additive; they do NOT change any existing caller's resolution path.
#
# Argument rules:
#   Flags may appear in any order.
#   --subject and --artifact are mutually exclusive; if both given, return 1.
#   An unknown flag returns 1 (stderr).
#
# Negative-spec:
#   - Does NOT write any state; it only resolves the path.
#   - Does NOT fall back silently when git root is missing (Rule 5).
#   - Does NOT fall back to example-orchestration-hub when doctrine DoE root fails (Rule 1).
#   - Does NOT auto-route cross-cutting artifacts (Rule 3).
#   - Does NOT define any file-scope state that would cause issues on re-sourcing.
#   - Does NOT use GNU-isms; bash ≥3.2 compatible.
#
# Cross-platform: bash ≥3.2+ compatible (no bash-4-only features used).
# Safe to source multiple times.

# NOTE: no set -e — sourced lib; errexit would propagate to caller. Use explicit
# exit-code checks. Mirrors coordinator-example-orchestration-hub-root.sh convention.
set -uo pipefail

# Source dependencies from the same lib directory.
# BASH_SOURCE[0] is this file; dirname gives the lib dir containing siblings.
_CSR_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
# shellcheck source=lib/coordinator-example-orchestration-hub-root.sh
source "${_CSR_LIB_DIR}/coordinator-example-orchestration-hub-root.sh"
# shellcheck source=lib/coordinator-is-meta-repo.sh
source "${_CSR_LIB_DIR}/coordinator-is-meta-repo.sh"
# shellcheck source=lib/coordinator-doe-root.sh
source "${_CSR_LIB_DIR}/coordinator-doe-root.sh"
# shellcheck source=lib/coordinator-artifact-subject.sh
source "${_CSR_LIB_DIR}/coordinator-artifact-subject.sh"

# ---------------------------------------------------------------------------
# Public: coordinator_state_root [--central] [--subject <engine|doctrine>] [--artifact <path>]
# ---------------------------------------------------------------------------
# Prints the resolved state-root path to stdout (no trailing newline).
# Returns 0 on success; 1 on failure (see stderr); 2 on cross-cutting artifact.
coordinator_state_root() {
  local _csr_central=0
  local _csr_subject=""
  local _csr_artifact=""
  local _csr_print_map=0
  local _csr_example_orchestration_hub=""
  local _csr_doe=""
  local _csr_cas_out=""
  local _csr_cas_rc=0
  local _csr_git_root=""

  # Argument parsing: accept flags in any order.
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --central)
        _csr_central=1
        shift
        ;;
      --subject)
        if [[ $# -lt 2 || -z "${2:-}" ]]; then
          echo "coordinator_state_root: --subject requires an argument: engine or doctrine" >&2
          return 1
        fi
        _csr_subject="$2"
        shift 2
        ;;
      --artifact)
        if [[ $# -lt 2 || -z "${2:-}" ]]; then
          echo "coordinator_state_root: --artifact requires an argument: an artifact path" >&2
          return 1
        fi
        _csr_artifact="$2"
        shift 2
        ;;
      --print-map)
        _csr_print_map=1
        shift
        ;;
      *)
        echo "coordinator_state_root: unknown flag '$1'; valid flags: --central, --subject, --artifact, --print-map" >&2
        return 1
        ;;
    esac
  done

  # Mutual exclusivity: --subject and --artifact cannot both be given.
  if [[ -n "$_csr_subject" && -n "$_csr_artifact" ]]; then
    echo "coordinator_state_root: --subject and --artifact are mutually exclusive; specify at most one" >&2
    return 1
  fi

  # --print-map cannot be combined with --subject or --artifact.
  if [[ "$_csr_print_map" -eq 1 && ( -n "$_csr_subject" || -n "$_csr_artifact" ) ]]; then
    echo "coordinator_state_root: --print-map cannot be combined with --subject/--artifact" >&2
    return 1
  fi

  # --print-map mode: emit the central map as a single-line JSON object, always rc 0.
  # --central alongside --print-map is harmless/ignored (the map IS the central map).
  if [[ "$_csr_print_map" -eq 1 ]]; then
    local _csr_pm_doc_part _csr_pm_eng_part _csr_pm_root _csr_pm_p

    # Resolve doctrine root. On failure: emit null + one stderr WARN line, continue.
    if _csr_pm_root="$(coordinator_doe_root 2>/dev/null)"; then
      _csr_pm_p="${_csr_pm_root}/state"
      _csr_pm_p="${_csr_pm_p//\\/\\\\}"   # backslash → \\
      _csr_pm_p="${_csr_pm_p//\"/\\\"}"   # double-quote → \"
      _csr_pm_doc_part="\"${_csr_pm_p}\""
    else
      echo "coordinator_state_root --print-map: doctrine root unresolvable — WARN+skip semantics apply" >&2
      _csr_pm_doc_part="null"
    fi

    # Resolve engine root. On failure: emit null + one stderr WARN line, continue.
    if _csr_pm_root="$(coordinator_example_orchestration_hub_root 2>/dev/null)"; then
      _csr_pm_p="${_csr_pm_root}/state"
      _csr_pm_p="${_csr_pm_p//\\/\\\\}"   # backslash → \\
      _csr_pm_p="${_csr_pm_p//\"/\\\"}"   # double-quote → \"
      _csr_pm_eng_part="\"${_csr_pm_p}\""
    else
      echo "coordinator_state_root --print-map: engine root unresolvable — WARN+skip semantics apply" >&2
      _csr_pm_eng_part="null"
    fi

    printf '{"schema":"coordinator-state-root-map/v1","subjects":{"doctrine":%s,"engine":%s}}' \
      "$_csr_pm_doc_part" "$_csr_pm_eng_part"
    return 0
  fi

  # --central branch: typed routing with subject-aware rules.
  if [[ "$_csr_central" -eq 1 ]]; then

    # Rule 1 / Rule 2: explicit subject override.
    if [[ -n "$_csr_subject" ]]; then
      case "$_csr_subject" in
        doctrine)
          # Rule 1: doctrine subject → DoE state. Fail-loud; no fallback to example-orchestration-hub.
          _csr_doe="$(coordinator_doe_root)" || return 1
          printf '%s/state' "$_csr_doe"
          return 0
          ;;
        engine)
          # Rule 2: engine subject → example-orchestration-hub state.
          _csr_example_orchestration_hub="$(coordinator_example_orchestration_hub_root)" || return 1
          printf '%s/state' "$_csr_example_orchestration_hub"
          return 0
          ;;
        *)
          echo "coordinator_state_root: unknown --subject value '$_csr_subject'; expected 'engine' or 'doctrine'" >&2
          return 1
          ;;
      esac
    fi

    # Rule 3: artifact-subject classification routes to the appropriate plane.
    if [[ -n "$_csr_artifact" ]]; then
      _csr_cas_out="$(coordinator_artifact_subject "$_csr_artifact")" || _csr_cas_rc=$?

      case "$_csr_cas_out" in
        doctrine)
          # Classifier: doctrine → Rule 1 (DoE state). Fail-loud; no fallback.
          _csr_doe="$(coordinator_doe_root)" || return 1
          printf '%s/state' "$_csr_doe"
          return 0
          ;;
        engine)
          # Classifier: engine → Rule 2 (example-orchestration-hub state).
          _csr_example_orchestration_hub="$(coordinator_example_orchestration_hub_root)" || return 1
          printf '%s/state' "$_csr_example_orchestration_hub"
          return 0
          ;;
        cross-cutting)
          # Classifier: cross-cutting — fail-loud; preserve exit-2 semantics.
          # The classifier already emitted a remediation to stderr; add one-liner.
          echo "coordinator_state_root: '$_csr_artifact' is cross-cutting and cannot be auto-routed; human routing decision required" >&2
          return 2
          ;;
        *)
          # Unexpected output from classifier (usage error or empty).
          echo "coordinator_state_root: unexpected output '${_csr_cas_out}' from coordinator_artifact_subject (rc=${_csr_cas_rc})" >&2
          return 1
          ;;
      esac
    fi

    # Rule 4: --central with no --subject and no --artifact. BACKWARD-COMPAT DEFAULT.
    # Resolves to example-orchestration-hub — identical to the prior implementation.
    _csr_example_orchestration_hub="$(coordinator_example_orchestration_hub_root)" || return 1
    printf '%s/state' "$_csr_example_orchestration_hub"
    return 0
  fi

  # Rule 5: default branch (no --central). BACKWARD-COMPAT DEFAULT.
  # Resolve the git root of the current working directory.
  # FAIL LOUD when the git root is empty or unresolvable — never silently pick
  # either branch (detect-then-fail-loud per implementation standards).
  _csr_git_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    {
      echo "coordinator_state_root: git rev-parse --show-toplevel failed."
      echo "  Not inside a git repository, or git is unavailable."
      echo "  Remediation: run from within a git repository, or pass --central for"
      echo "  central state that is not repo-scoped."
    } >&2
    return 1
  }
  if [[ -z "$_csr_git_root" ]]; then
    {
      echo "coordinator_state_root: git rev-parse --show-toplevel returned empty."
      echo "  Not inside a git repository."
      echo "  Remediation: run from within a git repository, or pass --central for"
      echo "  central state that is not repo-scoped."
    } >&2
    return 1
  fi

  # Discriminate: is this the meta-repo or a sibling repo?
  # coordinator_is_meta_repo is CLAUDE_HOME-aware and canonicalized (cd/pwd -P).
  if coordinator_is_meta_repo "$_csr_git_root"; then
    # Meta-repo → central state is in example-orchestration-hub.
    _csr_example_orchestration_hub="$(coordinator_example_orchestration_hub_root)" || return 1
    printf '%s/state' "$_csr_example_orchestration_hub"
  else
    # Sibling repo → per-repo state stays in the repo itself.
    printf '%s/state' "$_csr_git_root"
  fi
}

# EOF exec-guard: invoke coordinator_state_root when executed directly (not sourced).
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then coordinator_state_root "$@"; fi
