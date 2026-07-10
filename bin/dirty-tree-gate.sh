#!/usr/bin/env bash
# Purpose: Pre-terminate dirty-tree gate — classify every dirty working-tree path as
#          (a) session-authored (staged), (b) known concurrent owner, or (c) unattributable.
#          Exits 0 when all dirty paths are (a) or (b). Exits 3, listing case-(c) paths one
#          per line on stdout, when any unattributable file remains. EOL phantoms are filtered
#          before classification: a path where `git diff --quiet -- <path>` exits 0 (worktree
#          content equals index — a Git-for-Windows stat-staleness artifact) is benign, never (c).
#
# Usage:   dirty-tree-gate.sh --terminator <token>
#   --terminator <token>   Display-only label in human-facing messages (e.g. wsc|handoff|workday-complete).
#
# Classification rules applied in order; first match wins for each dirty path:
#   EOL phantom : `git diff --quiet -- <path>` exits 0 → worktree == index (stat-stale) → skip
#   (a) Staged  : status XY where X != ' ' and X != '?' → staged for this session's commit → skip
#   (b) Scope   : path appears in scope: block of any state/handoffs/*.md that carries consumed_by: → skip
#   (c) Residual: all others → print to stdout and exit 3
#
# The script does NOT auto-dispose case-(c) paths — disposition (commit / stash / name-owner)
# stays EM judgment in the calling skill's prose. Case (c) is NOT always an orphan — see
# docs/wiki/concurrent-em-hazards.md and the stderr trailer this script emits on exit 3 (below,
# where "REFUSING to auto-stash" is defined) for the full concurrent-EM-peer disposition ladder;
# that trailer is the single source of truth for this guidance — skills/workstream-complete/SKILL.md
# § "Concurrent-EM shared-branch disposition" and this header both cite it rather than
# re-narrating it independently.
# Review: code-reviewer (F6/P2) — this header, the stderr trailer, and SKILL.md previously
# each re-explained the same case-(c)-is-not-always-an-orphan guidance independently (drift
# risk: 3 copies to keep in sync). Consolidated so the stderr trailer is the runtime SOT.
#
# Exit codes:
#   0  all dirty paths attributable (phantom / staged-a / consumed-handoff-b)
#   2  usage error (missing --terminator, not a git repo)
#   3  one or more case-(c) unattributable paths remain (listed on stdout, one per line) —
#      the stderr trailer names the manual-fallback disposition; the script never recommends
#      auto-stash/auto-adopt for these paths
#
# Negative-spec: this script does NOT attempt to auto-attribute case-(c) paths to a concurrent
# peer session (that would require cross-machine claim visibility this repo does not have —
# `.git/coordinator-sessions/` is per-clone, not shared across the fleet). See the 2026-07-07
# example-cockpit-repo memo (cross-repo/inbox/2026-07-07-example-cockpit-repo-em-wsc-commit-dirty-tree-gate-shared-branch.md)
# for the incident that motivated this refusal-to-auto-dispose contract; broadening case-(b)
# attribution to close the gap at the classifier is tracked as a separate, unscoped follow-up.
#
# Spec: docs/plans/2026-06-30-session-terminator-mechanism-unification.md C2

set -uo pipefail

# --- Bash version guard (bash ≥ 4 required for declare -A) ---
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "dirty-tree-gate: requires bash >= 4 (found ${BASH_VERSION})" >&2
  echo "  install: brew install bash (macOS) or use system bash on Linux" >&2
  exit 2
fi

# --- Resolve plugin root (survives marketplace-install layout) ---
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  PLUGIN_ROOT="$CLAUDE_PLUGIN_ROOT"
else
  _doe_root="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)"
  if [ -z "$_doe_root" ] || [ ! -d "$_doe_root/coordinator" ]; then
    echo "ERROR: ~/.claude/.doe-root missing/invalid — re-run coordinator:install" >&2
    exit 1
  fi
  PLUGIN_ROOT="$_doe_root/coordinator"
fi

# Source state-root seam — routes per-repo state/ refs through coordinator_state_root
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4 / AC4
# shellcheck source=lib/coordinator-state-root.sh
source "${PLUGIN_ROOT}/lib/coordinator-state-root.sh"

# --- Parse arguments ---
TERMINATOR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --terminator)
      if [[ $# -lt 2 || -z "$2" ]]; then
        echo "dirty-tree-gate: --terminator requires a non-empty value" >&2
        exit 2
      fi
      TERMINATOR="$2"
      shift 2
      ;;
    *)
      echo "dirty-tree-gate: unknown argument: $1" >&2
      echo "usage: dirty-tree-gate.sh --terminator <token>" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$TERMINATOR" ]]; then
  echo "dirty-tree-gate: --terminator <token> is required" >&2
  echo "usage: dirty-tree-gate.sh --terminator <token>" >&2
  exit 2
fi

# --- Resolve git repo root ---
REPO_ROOT=""
if ! REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "dirty-tree-gate ($TERMINATOR): must be run inside a git repository" >&2
  exit 2
fi

# --- Build case-(b) known-scope path set ---
# A path is known-concurrent-owner (b) when it appears in the scope: block of
# any state/handoffs/*.md that carries a consumed_by: field, meaning another
# session has claimed that handoff and owns its scope.
declare -A KNOWN_SCOPE  # path → 1 (O(1) membership test)

HANDOFFS_DIR="$(coordinator_state_root)/handoffs"
if [[ -d "$HANDOFFS_DIR" ]]; then
  for hf in "$HANDOFFS_DIR"/*.md; do
    # Glob with no matches expands to the literal string — skip non-files.
    [[ -f "$hf" ]] || continue
    # Only consume handoffs that have consumed_by: set (another session is active on it).
    if grep -q "^consumed_by:" "$hf" 2>/dev/null; then
      # Extract scope: paths from YAML frontmatter (  - <path> lines until next top-level key).
      # Byte-identical to the awk idiom in extract-scope-paths.sh (C4) and the inline skill blocks.
      while IFS= read -r sp; do
        [[ -n "$sp" ]] && KNOWN_SCOPE["$sp"]=1
      # Review: code-reviewer A-F1 — added found && /^---/{exit} before /^[a-z]/ guard so
      # extraction terminates at the closing --- when scope: is the last frontmatter field.
      done < <(awk '/^scope:/{found=1; next} found && /^  - /{print substr($0, 5)} found && /^---/{exit} found && /^[a-z]/{exit}' "$hf" 2>/dev/null)
    fi
  done
fi

# --- Classify dirty paths ---
UNATTRIBUTABLE=()

# git status --porcelain output format: "XY path" or "XY orig -> dest" (rename/copy).
# X = staged status vs HEAD; Y = worktree status vs index.
while IFS= read -r line; do
  [[ -z "$line" ]] && continue

  xy="${line:0:2}"
  path="${line:3}"

  # Handle rename/copy format: "orig -> dest" — we care about the destination.
  if [[ "$path" == *" -> "* ]]; then
    path="${path##* -> }"
  fi

  # (a) Staged: X status char is not ' ' or '?' → this session staged it for its scoped commit.
  x_char="${xy:0:1}"
  if [[ "$x_char" != ' ' && "$x_char" != '?' ]]; then
    continue  # case (a) — belongs to this session's pending commit
  fi

  # EOL phantom filter (tracked unstaged only — untracked files are never phantoms):
  # `git diff --quiet -- <path>` compares worktree vs index. Exit 0 → content identical →
  # this is a Git-for-Windows stat-staleness artifact (concurrent-em-hazards.md § H23) → skip.
  if [[ "$x_char" == ' ' ]]; then
    if git -C "$REPO_ROOT" diff --quiet -- "$path" 2>/dev/null; then
      continue  # EOL phantom — worktree equals index, benign stat artifact
    fi
  fi

  # (b) Known concurrent owner: path in scope of a consumed handoff → skip.
  if [[ -n "${KNOWN_SCOPE[$path]+_}" ]]; then
    continue  # case (b) — another session's handoff owns this path
  fi

  # (c) Unattributable — cannot name the owner.
  UNATTRIBUTABLE+=("$path")

done < <(git -C "$REPO_ROOT" status --porcelain 2>/dev/null)

# --- Report and exit ---
if [[ ${#UNATTRIBUTABLE[@]} -eq 0 ]]; then
  exit 0
fi

echo "dirty-tree-gate ($TERMINATOR): ${#UNATTRIBUTABLE[@]} unattributable file(s) — disposition required (commit / stash / name-owner):" >&2
for p in "${UNATTRIBUTABLE[@]}"; do
  echo "$p"
done
echo "" >&2
echo "REFUSING to auto-stash or auto-adopt these paths — this gate cannot tell 'orphaned WT change from a crashed session' apart from 'live peer session's in-flight file on a shared branch' (the two look identical to git status). On a concurrent-EM branch this is routine, not exceptional." >&2
echo "" >&2
echo "MANUAL FALLBACK — resolve by hand before re-running:" >&2
echo "  1. Inspect each path above: is it yours (forgot to stage), a live peer's (git log -1 --format=%an -- <path>; is another EM session active on this branch right now?), or a genuine orphan (no active peer, stale/crashed session)?" >&2
echo "  2. Peer file (live concurrent-EM session)   -> leave it untouched. Do NOT stash, do NOT commit it. Complete via explicit-path commit of ONLY your own session's files (git add -- <your-paths> && git commit -m ... -- <your-paths>), skipping this gate's blanket pass for this run." >&2
echo "  3. Your own file (forgot to stage)          -> git add -- <path>, then re-run this gate." >&2
echo "  4. Genuine orphan (crashed/abandoned session) -> commit-with-provenance, or stash-with-provenance (git stash push -u -m '...' -- <path>), or name the owner explicitly — see skills/workstream-complete/SKILL.md Step 3.0." >&2
exit 3
