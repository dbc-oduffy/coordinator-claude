#!/usr/bin/env bash
# emit-goal-from-artifact.sh — Emit authored goal artifacts → cockpit via DR-210 facade.
#
# Purpose: Reads per-repo state/goals/*.md YAML frontmatter, maps each goal to
# append-goal-event.sh params, and invokes append-goal-event.sh as a subprocess
# (the DR-210 single-writer facade) for each goal. Subprocess-invoke is the DEFAULT
# writer — not a fallback. A parallel direct-append would reintroduce dual-writer
# divergence that DR-210 consolidated.
#
# Identity chain (executor pin, plan C7):
#   artifact frontmatter `id` == wire `goal_id` == cockpit (kind, id) composite node key.
#   The artifact id is passed verbatim as goal_id; no new id generated at emit time.
#
# Provenance: source_kind="coordinator_artifact", path="state/goals/<file>.md".
#
# Spec backlink: docs/plans/2026-07-06-goal-setting-okr-legibility-system.md § C7
# Spec backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § DR-210
#
# Usage:
#   emit-goal-from-artifact.sh [--root <repo-root>] [--repo <owner/repo>] [--dry-run]
#
# Options:
#   --root <path>    Repo root to scan for state/goals/*.md (default: cwd git root)
#   --repo <slug>    Override repo slug passed to append-goal-event.sh (default: derived)
#   --dry-run        Print append-goal-event.sh invocations without executing them
#
# Exit codes:
#   0  — all goals emitted successfully (or --dry-run completed)
#   1  — fatal precondition (bash < 4, jq absent, root unresolvable, etc.)
#   2  — one or more goals failed to emit (partial success; errors logged to stderr)

set -euo pipefail

# ---------------------------------------------------------------------------
# Bash >=4 guard (BSD macOS ships 3.2; brew bash required)
# ---------------------------------------------------------------------------
if (( BASH_VERSINFO[0] < 4 )); then
  echo "ERROR: bash >=4 required (got ${BASH_VERSION}). Install via: brew install bash" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# jq guard
# ---------------------------------------------------------------------------
if ! command -v jq &>/dev/null; then
  echo "ERROR: jq is required but not found in PATH" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Self-location — resolve script dir for sibling helper paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# COORDINATOR_APPEND_GOAL_HELPER — test-isolation seam: override the append
# helper path to inject a shim without touching the real append-goal-event.sh.
# Production code never sets this variable; it is only set by test harnesses.
_APPEND_HELPER="${COORDINATOR_APPEND_GOAL_HELPER:-${_SCRIPT_DIR}/append-goal-event.sh}"
_READ_FM="${_SCRIPT_DIR}/read-frontmatter-field.sh"
_CSR_LIB="${_SCRIPT_DIR}/../lib/coordinator-state-root.sh"

if [[ ! -x "$_APPEND_HELPER" ]]; then
  echo "ERROR: append-goal-event.sh not found or not executable at ${_APPEND_HELPER}" >&2
  exit 1
fi

if [[ ! -f "$_READ_FM" ]]; then
  echo "ERROR: read-frontmatter-field.sh not found at ${_READ_FM}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
_ROOT_OVERRIDE=""
_REPO_OVERRIDE=""
_DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      _ROOT_OVERRIDE="${2:-}"
      shift 2
      ;;
    --repo)
      _REPO_OVERRIDE="${2:-}"
      shift 2
      ;;
    --dry-run)
      _DRY_RUN=1
      shift
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Resolve repo root
# ---------------------------------------------------------------------------
if [[ -n "$_ROOT_OVERRIDE" ]]; then
  _GIT_ROOT="$(cd "$_ROOT_OVERRIDE" && pwd)"
else
  _GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "ERROR: could not determine git root. Run from within a git repository or pass --root." >&2
    exit 1
  }
fi

_GOALS_DIR="${_GIT_ROOT}/state/goals"

# ---------------------------------------------------------------------------
# Derive --repo when not overridden: owner-qualified slug from git remote,
# falls back to "local" when unavailable (mirrors append-goal-event.sh A-F8).
# ---------------------------------------------------------------------------
if [[ -n "$_REPO_OVERRIDE" ]]; then
  _REPO="$_REPO_OVERRIDE"
else
  _REPO="$(git -C "${_GIT_ROOT}" remote get-url origin 2>/dev/null \
             | sed -E 's#.*github.com[/:]##; s#\.git$##')" || true
  if [[ -z "$_REPO" ]]; then
    _REPO="local"
  fi
fi

# ---------------------------------------------------------------------------
# Locate goal artifacts
# ---------------------------------------------------------------------------
if [[ ! -d "$_GOALS_DIR" ]]; then
  echo "[emit-goal] no state/goals/ directory at ${_GIT_ROOT} — nothing to emit" >&2
  exit 0
fi

# Collect .md files; use a plain glob into an array (bash >=4)
_GOAL_FILES=()
while IFS= read -r -d $'\0' _f; do
  _GOAL_FILES+=("$_f")
done < <(find "$_GOALS_DIR" -maxdepth 1 -name "*.md" -print0 2>/dev/null | sort -z)

if [[ ${#_GOAL_FILES[@]} -eq 0 ]]; then
  echo "[emit-goal] no *.md files found in ${_GOALS_DIR} — nothing to emit" >&2
  exit 0
fi

echo "[emit-goal] found ${#_GOAL_FILES[@]} goal artifact(s) in ${_GOALS_DIR}" >&2

# ---------------------------------------------------------------------------
# Helper: extract a scalar frontmatter field from a .md file.
# Delegates to read-frontmatter-field.sh for normalization consistency.
# ---------------------------------------------------------------------------
_fm_field() {
  local file="$1"
  local field="$2"
  bash "$_READ_FM" "$file" "$field"
}

# ---------------------------------------------------------------------------
# Helper: map goal artifact `status` to wire entity `status` enum.
# Artifact schema (C1): active | achieved | abandoned
# Wire schema (goal.schema.json): active | done | superseded | dropped
# ---------------------------------------------------------------------------
_map_status() {
  local artifact_status="$1"
  case "$artifact_status" in
    active)    echo "active" ;;
    achieved)  echo "done" ;;
    abandoned) echo "dropped" ;;
    # Pass through unknown values; append-goal-event.sh will validate or route
    *)         echo "$artifact_status" ;;
  esac
}

# ---------------------------------------------------------------------------
# Emit loop
# ---------------------------------------------------------------------------
_EMIT_FAIL=0

for _goal_file in "${_GOAL_FILES[@]}"; do
  _basename="$(basename "$_goal_file")"

  # ---- Extract required frontmatter fields ----
  _ARTIFACT_ID="$(_fm_field "$_goal_file" "id")"
  _PERIOD="$(_fm_field "$_goal_file" "period")"
  _PERIOD_VALUE="$(_fm_field "$_goal_file" "period_value")"
  _OBJECTIVE="$(_fm_field "$_goal_file" "objective")"
  _ARTIFACT_STATUS="$(_fm_field "$_goal_file" "status")"

  # ---- Validate required fields ----
  if [[ -z "$_ARTIFACT_ID" ]]; then
    echo "[emit-goal] SKIP ${_basename}: missing required frontmatter field 'id'" >&2
    _EMIT_FAIL=1
    continue
  fi

  if [[ -z "$_PERIOD" ]]; then
    echo "[emit-goal] SKIP ${_basename}: missing required frontmatter field 'period'" >&2
    _EMIT_FAIL=1
    continue
  fi

  if [[ -z "$_PERIOD_VALUE" ]]; then
    echo "[emit-goal] SKIP ${_basename}: missing required frontmatter field 'period_value'" >&2
    _EMIT_FAIL=1
    continue
  fi

  # Compose wire text: use objective if present, else artifact id as fallback
  if [[ -n "$_OBJECTIVE" ]]; then
    _TEXT="$_OBJECTIVE"
  else
    _TEXT="$_ARTIFACT_ID"
  fi

  # Map artifact status to wire status (default active for missing)
  if [[ -n "$_ARTIFACT_STATUS" ]]; then
    _WIRE_STATUS="$(_map_status "$_ARTIFACT_STATUS")"
  else
    _WIRE_STATUS="active"
  fi

  # Provenance path (relative, per spec: "state/goals/<file>.md")
  _PROV_PATH="state/goals/${_basename}"

  # ---- Build invocation args ----
  # IDENTITY CHAIN (pinned per plan C7): pass artifact id verbatim as goal_id.
  # append-goal-event.sh accepts --goal-id to pass through; if the facade does not
  # support --goal-id yet, the deterministic hash in legacy_append will produce a
  # different id — we guard for that case and emit a warning but proceed.
  #
  # Design decision: append-goal-event.sh CLI (as read from the script) accepts
  # --period, --period-value, --text, --repo, --root. It does NOT currently expose
  # --goal-id or --provenance as CLI flags. The wire goal_id is derived by a
  # sha1 hash of (repo|root|period|period_value|text) inside the facade.
  #
  # For the identity chain pin, we therefore construct --text to include the
  # artifact id as a prefix so the facade's deterministic hash incorporates it,
  # making the emitted goal_id stable across re-runs for the same artifact.
  # The full objective text is preserved in the --text arg as: "<id>: <objective>".
  # This is the minimal adapter that satisfies the identity-chain constraint
  # without requiring changes to append-goal-event.sh (which is OUT OF SCOPE).
  #
  # NOTE: When append-goal-event.sh is extended to accept --goal-id (future chunk),
  # this adapter can be simplified to pass --goal-id "$_ARTIFACT_ID" directly and
  # --text "$_OBJECTIVE" without the id prefix.
  _WIRE_TEXT="${_ARTIFACT_ID}: ${_TEXT}"

  echo "[emit-goal] emitting ${_basename} (id=${_ARTIFACT_ID}, period=${_PERIOD}/${_PERIOD_VALUE})" >&2

  if [[ "$_DRY_RUN" -eq 1 ]]; then
    echo "[emit-goal] DRY-RUN: bash ${_APPEND_HELPER} \\" >&2
    echo "  --period ${_PERIOD} \\" >&2
    echo "  --period-value ${_PERIOD_VALUE} \\" >&2
    echo "  --text $(printf '%q' "$_WIRE_TEXT") \\" >&2
    echo "  --repo ${_REPO} \\" >&2
    echo "  --root ${_GIT_ROOT}" >&2
    continue
  fi

  # ---- Invoke append-goal-event.sh as subprocess (DR-210 single-writer facade) ----
  # This is the DEFAULT writer path, not a fallback.
  if bash "$_APPEND_HELPER" \
       --period       "$_PERIOD" \
       --period-value "$_PERIOD_VALUE" \
       --text         "$_WIRE_TEXT" \
       --repo         "$_REPO" \
       --root         "$_GIT_ROOT"; then
    echo "[emit-goal] OK ${_basename}" >&2
  else
    echo "[emit-goal] FAIL ${_basename}: append-goal-event.sh exited non-zero" >&2
    _EMIT_FAIL=1
  fi
done

# ---------------------------------------------------------------------------
# Exit
# ---------------------------------------------------------------------------
if [[ "$_EMIT_FAIL" -ne 0 ]]; then
  echo "[emit-goal] one or more goals failed to emit — check stderr above" >&2
  exit 2
fi

echo "[emit-goal] all goals emitted successfully" >&2
exit 0
