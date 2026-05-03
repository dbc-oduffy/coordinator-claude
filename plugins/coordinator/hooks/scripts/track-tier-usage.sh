#!/bin/bash
# PostToolUse hook: Count tool calls by investigation tier for the current session.
#
# Classifies each tool call into a context-loading tier per the tiered-context-loading
# doctrine (docs/wiki/tiered-context-loading.md) and increments per-session counters
# persisted to ~/.claude/projects/<project-slug>/tier-usage/<session_id>.json.
#
# Tier classification:
#   tier 1 — Read of wiki/atlas/decisions/tracker paths
#   tier 2 — mcp__*project-rag*__* call OR Bash invoking bin/query-records or bin/lint-frontmatter
#   tier 3 — Read of any other path; Grep; Glob
#   tier 4 — Agent dispatch (subagent_type captured; rationale_present detected)
#   (other tools ignored — silent exit 0)
#
# Path portability: Python builds storage paths via os.path.expanduser, not bash $HOME,
# to avoid the /c/Users/... vs C:\Users\... mismatch on Windows + Git Bash.
#
# Always exits 0 — advisory telemetry, never blocks tool execution.
#
# Input schema (PostToolUse):
#   {
#     "session_id": "<id>",
#     "tool_name": "<name>",
#     "tool_input": { ... },
#     "cwd": "<path>"
#   }

# --- Safe stdin read ---
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

[[ -z "$INPUT" ]] && exit 0

# ---------------------------------------------------------------------------
# Extract fields using pure bash string operations (no external commands).
# Pattern mirrors track-touched-files.sh for performance consistency.
# ---------------------------------------------------------------------------

# Extract tool_name
if [[ "$INPUT" != *'"tool_name"'* ]]; then
  exit 0
fi
_tmp="${INPUT#*\"tool_name\":\"}"
TOOL_NAME="${_tmp%%\"*}"

# Fast-exit: only classify relevant tools
case "${TOOL_NAME:-}" in
  Read|Grep|Glob|Bash|Agent) ;;         # classify these
  mcp__*) ;;                             # mcp calls may be tier 2
  *) exit 0 ;;
esac

# Extract session_id
if [[ "$INPUT" != *'"session_id"'* ]]; then
  exit 0
fi
_tmp="${INPUT#*\"session_id\":\"}"
SESSION_ID="${_tmp%%\"*}"
[[ -z "$SESSION_ID" ]] && exit 0

# Extract cwd (for project slug)
CWD=""
if [[ "$INPUT" == *'"cwd"'* ]]; then
  _tmp="${INPUT#*\"cwd\":\"}"
  CWD="${_tmp%%\"*}"
fi
[[ -z "$CWD" ]] && CWD="$(pwd 2>/dev/null || echo "unknown")"

# ---------------------------------------------------------------------------
# Build project slug from cwd — matches the canonical form in ~/.claude/projects/
# (e.g. `X--coordinator-claude`, `C--Users-oduffy--claude`).
#
# Normalize Windows/MSYS path variants before slug derivation, then collapse all
# path separators (`/`, `\`, `:`) into single dashes. Without normalization, the
# leading slash(es) of MSYS form (`/x/path`) or any UNC-ish form (`///path`)
# survive into the slug as bare leading dashes, producing slugs like
# `--coordinator-claude` instead of the canonical `X--coordinator-claude`. The
# orphan tier-usage dirs land in the project working tree at the mangled slug
# and pollute git status. (issue #23)
# ---------------------------------------------------------------------------

# 1. Strip duplicate leading slashes (e.g. `///path` → `/path`).
while [[ "$CWD" == //* ]]; do
  CWD="${CWD#/}"
done

# 2. Lift MSYS form (`/x/...`) to Windows form (`X:/...`) so the drive letter
#    survives slug derivation.
if [[ "$CWD" =~ ^/([a-zA-Z])/(.*)$ ]]; then
  _drive="${BASH_REMATCH[1]}"
  CWD="${_drive^^}:/${BASH_REMATCH[2]}"
fi

# 3. Drop any trailing separator so the slug doesn't end in a dash.
CWD="${CWD%/}"
CWD="${CWD%\\}"

# 4. Collapse `/`, `\`, `:`, `.` to dashes (matches Claude Code's own
#    project-dir slug — `.claude` becomes `-claude`, so `C:\Users\oduffy\.claude`
#    yields `C--Users-oduffy--claude` matching `~/.claude/projects/`); strip a
#    single leading dash if any survived (defensive — unrooted relative paths
#    or fallback `pwd` output).
PROJECT_SLUG=$(echo "$CWD" | sed 's|[/\\:.]|-|g' | sed 's|^-||')
[[ -z "$PROJECT_SLUG" ]] && PROJECT_SLUG="unknown"

# ---------------------------------------------------------------------------
# Tier classification logic.
# ---------------------------------------------------------------------------
TIER=""
SUBAGENT_TYPE=""
RATIONALE_PRESENT="false"

# Tier 2: mcp__*project-rag*__* calls
if [[ "$TOOL_NAME" == mcp__*project-rag*__* || "$TOOL_NAME" == mcp__*project_rag*__* ]]; then
  TIER="tier2"
fi

# Classify by tool name (TIER not yet set)
if [[ -z "$TIER" ]]; then
  case "${TOOL_NAME}" in

    Read)
      # Extract file_path from tool_input
      FILE_PATH=""
      if [[ "$INPUT" == *'"file_path"'* ]]; then
        _tmp="${INPUT#*\"file_path\":\"}"
        FILE_PATH="${_tmp%%\"*}"
      fi
      # Tier 1 surfaces: wiki/, architecture-atlas/, decisions/, project-tracker.md,
      # orientation_cache.md, lessons.md
      if [[ "$FILE_PATH" == */docs/wiki/* || \
            "$FILE_PATH" == */tasks/architecture-atlas/* || \
            "$FILE_PATH" == */docs/decisions/* || \
            "$FILE_PATH" == */docs/project-tracker.md || \
            "$FILE_PATH" == *orientation_cache.md || \
            "$FILE_PATH" == *lessons.md ]]; then
        TIER="tier1"
      else
        TIER="tier3"
      fi
      ;;

    Grep|Glob)
      TIER="tier3"
      ;;

    Bash)
      # Tier 2 if the command invokes bin/query-records or bin/lint-frontmatter
      CMD=""
      if [[ "$INPUT" == *'"command"'* ]]; then
        _tmp="${INPUT#*\"command\":\"}"
        CMD="${_tmp%%\"*}"
      fi
      if [[ "$CMD" == *bin/query-records* || "$CMD" == *bin/lint-frontmatter* ]]; then
        TIER="tier2"
      else
        # Other Bash calls — not classified
        exit 0
      fi
      ;;

    Agent)
      TIER="tier4"
      # Extract subagent_type from tool_input
      if [[ "$INPUT" == *'"subagent_type"'* ]]; then
        _tmp="${INPUT#*\"subagent_type\":\"}"
        SUBAGENT_TYPE="${_tmp%%\"*}"
      fi
      # Detect rationale preamble — heuristic substring match against the full INPUT JSON.
      # Review: patrik R2 finding 5 — document the approximation rather than tighten with jq.
      #
      # Known edges:
      #   False positive: if any tool_input field other than the prompt contains "tier 1-3 attempted"
      #     (unlikely in practice — the phrase is only meaningful in a dispatch preamble).
      #   False negative: if the phrase is JSON-escaped in an unusual way that breaks the substring.
      #
      # Deliberate choice: scanning the entire INPUT is cheap (no jq subprocess, no parse latency).
      # Tightening to `jq -r '.tool_input.prompt'` would add a jq call to every Agent dispatch —
      # not worth the cost for a heuristic telemetry counter. Revisit if false rates become a
      # calibration problem.
      PROMPT_LOWER=$(echo "$INPUT" | tr '[:upper:]' '[:lower:]' 2>/dev/null || echo "")
      if [[ "$PROMPT_LOWER" == *"tier 1-3 attempted"* ]]; then
        RATIONALE_PRESENT="true"
      fi
      ;;

    *)
      # Unclassified mcp__ or other tool — no tier
      exit 0
      ;;
  esac
fi

[[ -z "$TIER" ]] && exit 0

# ---------------------------------------------------------------------------
# Persist counter to ~/.claude/projects/<slug>/tier-usage/<session_id>.json
#
# Pass values to Python via env vars rather than bash string interpolation to
# avoid the /c/Users/... vs C:\Users\... path mismatch on Windows + Git Bash.
# Python builds the storage path with os.path.expanduser, which resolves to
# the correct native path on both POSIX and Windows.
# ---------------------------------------------------------------------------
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "unknown")

if command -v python3 &>/dev/null; then
  TIER_SLUG="$PROJECT_SLUG" \
  TIER_SESSION="$SESSION_ID" \
  TIER_NAME="$TIER" \
  TIER_NOW="$NOW" \
  TIER_SUBAGENT="$SUBAGENT_TYPE" \
  TIER_RATIONALE="$RATIONALE_PRESENT" \
  python3 - <<'PYEOF' 2>/dev/null || exit 0
import json, os

project_slug      = os.environ.get("TIER_SLUG", "unknown")
session_id        = os.environ.get("TIER_SESSION", "unknown")
tier              = os.environ.get("TIER_NAME", "")
now               = os.environ.get("TIER_NOW", "unknown")
subagent_type     = os.environ.get("TIER_SUBAGENT", "")
rationale_present = os.environ.get("TIER_RATIONALE", "false") == "true"

# Build path via Python's own home resolution (works on Windows + POSIX)
tier_dir  = os.path.join(os.path.expanduser("~"), ".claude", "projects", project_slug, "tier-usage")
tier_file = os.path.join(tier_dir, session_id + ".json")

os.makedirs(tier_dir, exist_ok=True)

# Load existing or create fresh
if os.path.exists(tier_file):
    try:
        with open(tier_file, "r") as f:
            data = json.load(f)
    except Exception:
        data = {}
else:
    data = {}

# Ensure shape
data.setdefault("session_id", session_id)
data.setdefault("started_at", now)
data.setdefault("counts", {"tier1": 0, "tier2": 0, "tier3": 0, "tier4": 0})
for k in ("tier1", "tier2", "tier3", "tier4"):
    data["counts"].setdefault(k, 0)
data.setdefault("tier4_dispatches", [])

# Increment
if tier in data["counts"]:
    data["counts"][tier] += 1

# Record tier-4 dispatch detail
if tier == "tier4":
    data["tier4_dispatches"].append({
        "ts": now,
        "subagent_type": subagent_type,
        "rationale_present": rationale_present
    })

# Write back
with open(tier_file, "w") as f:
    json.dump(data, f, indent=2)
PYEOF
else
  # python3 unavailable — skip silently (telemetry is best-effort)
  exit 0
fi

exit 0
