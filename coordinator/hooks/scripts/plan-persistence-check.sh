#!/usr/bin/env bash
# PostToolUse hook: fires after ExitPlanMode.
#
# Purpose: Reads the approved plan from tool_response.plan, copies it to
# docs/plans/<YYYY-MM-DD>-<slug>.md in the project repo, stages it with
# git add (NEVER commits — committing from a hook child process bypasses all
# PreToolUse commit-safety matchers). Emits additionalContext pre-filling the
# exact scoped commit command and the subagent-review-artifact reminder.
#
# Spec backlink: docs/plans/2026-06-18-plan-persistence-hook-automation.md
#
# Portability: bash 3.2 / BSD-coreutils clean (DR-148).
# No sed -i, no date -d, no grep -P, no realpath, no mapfile/readarray, no ${var^^}.
#
# Activation predicate (graceful cross-repo no-op):
#   - tool_name must be ExitPlanMode
#   - tool_response.plan must be non-empty
#   - repo root must be discoverable (CLAUDE_PROJECT_DIR or git rev-parse)
#   - EITHER docs/plans/ OR docs/README.md must exist at the root
#   (Never auto-creates docs/plans/ in an arbitrary repo.)
#
# Slug-collision policy:
#   - Byte-identical → idempotent no-op (no write, no re-stage, no dup README entry)
#   - Content differs → emit collision additionalContext, do NOT overwrite, exit 0

set -uo pipefail

# --- Pick best python binary ---
PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)

# --- Safe stdin read (timeout guard prevents hang) ---
if command -v timeout >/dev/null 2>&1; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# --- Parse tool_name and tool_response fields (jq -> python -> sed fallback) ---
if command -v jq >/dev/null 2>&1; then
  TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
  PLAN_CONTENT=$(printf '%s' "$INPUT" | jq -r '.tool_response.plan // empty' 2>/dev/null || true)
  IS_AGENT=$(printf '%s' "$INPUT" | jq -r '.tool_response.isAgent // false' 2>/dev/null || true)
  CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
elif [[ -n "$PY" ]]; then
  # $INPUT is a captured variable (not a stream), so each `printf | python` re-pipes
  # the full payload — safe to read four times. Do NOT refactor $INPUT into a stream.
  TOOL_NAME=$(printf '%s' "$INPUT" | "$PY" -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_name","")))' 2>/dev/null || true)
  PLAN_CONTENT=$(printf '%s' "$INPUT" | "$PY" -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_response",{}).get("plan","") or ""))' 2>/dev/null || true)
  IS_AGENT=$(printf '%s' "$INPUT" | "$PY" -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("tool_response",{}).get("isAgent",False)).lower())' 2>/dev/null || true)
  CWD=$(printf '%s' "$INPUT" | "$PY" -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
sys.stdout.write(str(d.get("cwd","")))' 2>/dev/null || true)
else
  TOOL_NAME=$(printf '%s' "$INPUT" | sed -n 's/.*"tool_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  # Cannot reliably extract multiline plan via sed — leave empty so hook no-ops
  PLAN_CONTENT=""
  IS_AGENT="false"
  CWD=""
fi

# --- Guard: only act on ExitPlanMode ---
[[ "$TOOL_NAME" != "ExitPlanMode" ]] && exit 0

# --- Guard: skip subagent plan-mode ---
# A subagent's internal ExitPlanMode is not a PM-approved plan; canonicalizing it
# would pollute the repo's docs/plans/ with transient subagent scratch.
[[ "$IS_AGENT" == "true" ]] && exit 0

# --- Guard: plan must be non-empty ---
[[ -z "$PLAN_CONTENT" ]] && exit 0

# --- Resolve repo root ---
# Priority: CLAUDE_PROJECT_DIR (explicit) → git -C cwd → git from PWD
REPO_ROOT=""
if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]] && [[ -d "${CLAUDE_PROJECT_DIR:-}" ]]; then
  # Verify it's actually a git repo
  REPO_ROOT=$(git -C "$CLAUDE_PROJECT_DIR" rev-parse --show-toplevel 2>/dev/null || true)
fi
if [[ -z "$REPO_ROOT" ]] && [[ -n "$CWD" ]] && [[ -d "$CWD" ]]; then
  REPO_ROOT=$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null || true)
fi
if [[ -z "$REPO_ROOT" ]]; then
  REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
fi

# --- Guard: must be in a git repo ---
[[ -z "$REPO_ROOT" ]] && exit 0

# --- Guard: repo must have opted into the docs convention ---
# NEITHER docs/plans/ NOR docs/README.md exists → not our kind of repo
DOCS_PLANS_DIR="$REPO_ROOT/docs/plans"
DOCS_README="$REPO_ROOT/docs/README.md"

if [[ ! -d "$DOCS_PLANS_DIR" ]] && [[ ! -f "$DOCS_README" ]]; then
  exit 0
fi

# --- Derive slug from first H1 ---
# Strip the "# " prefix from the first "# Title" line, lowercase, replace
# non-alphanumeric runs with hyphens, trim leading/trailing hyphens.
# BSD-portable: no sed -i, no grep -P, no ${var^^}.
H1_LINE=$(printf '%s' "$PLAN_CONTENT" | grep -m 1 '^# ' | head -1)
if [[ -n "$H1_LINE" ]]; then
  # Strip leading "# "
  H1_TEXT="${H1_LINE#\# }"
  # Lowercase via tr (portable)
  H1_LOWER=$(printf '%s' "$H1_TEXT" | tr '[:upper:]' '[:lower:]')
  # Replace non-alphanumeric chars with hyphens
  H1_SLUG=$(printf '%s' "$H1_LOWER" | tr -cs 'a-z0-9' '-')
  # Trim trailing hyphens
  SLUG=$(printf '%s' "$H1_SLUG" | sed 's/-*$//')
  # Trim leading hyphens
  SLUG=$(printf '%s' "$SLUG" | sed 's/^-*//')
  # Truncate to 60 chars to keep filenames reasonable
  SLUG=$(printf '%s' "$SLUG" | cut -c1-60)
else
  # Timestamp fallback
  SLUG="plan-$(date -u +%H%M%S)"
fi

# --- Build target path ---
TODAY=$(date -u +%Y-%m-%d)
TARGET_NAME="${TODAY}-${SLUG}.md"
TARGET_PATH="$DOCS_PLANS_DIR/$TARGET_NAME"

# --- Ensure docs/plans/ exists (it does, per guard above — but just in case) ---
# We only reach here if docs/plans/ or docs/README.md exists. If docs/README.md
# exists but docs/plans/ doesn't, we need to create it to write the plan.
# The spec says NEVER auto-create in arbitrary repos, but a repo with docs/README.md
# is clearly opted in — create docs/plans/ if the README exists.
if [[ ! -d "$DOCS_PLANS_DIR" ]]; then
  mkdir -p "$DOCS_PLANS_DIR" 2>/dev/null || { exit 0; }
fi

# --- Slug-collision check ---
if [[ -f "$TARGET_PATH" ]]; then
  EXISTING=$(cat "$TARGET_PATH" 2>/dev/null || true)
  if [[ "$EXISTING" = "$PLAN_CONTENT" ]]; then
    # Byte-identical → idempotent no-op (no write, no re-stage). Emit a RAW
    # multi-line string and encode it exactly ONCE (same pattern as the main
    # write path below) — building a pre-encoded JSON string and re-encoding it
    # double-escapes the value.
    IDEMPOTENT_CTX="PLAN ALREADY PERSISTED (idempotent re-fire): docs/plans/$TARGET_NAME is byte-identical — no re-write or re-stage needed.

NEXT — commit if not already committed:
  git add -- docs/plans/$TARGET_NAME && git commit -m \"plan: $SLUG\" -- docs/plans/$TARGET_NAME

SUBAGENT REVIEW ARTIFACTS: If subagent reviews (the Staff Engineer, the Game Dev Reviewer, etc.) were part of this planning session, their outputs must be written to disk NOW. Agent outputs exist only in your context — if you do not write them, they are lost on compaction. Review artifacts are intermediate — write them straight to archive (not active folders). The plan document itself must incorporate ALL review findings unless the EM believes they are in error or require PM input."
    if command -v jq >/dev/null 2>&1; then
      jq -n --arg ctx "$IDEMPOTENT_CTX" \
        '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":$ctx}}'
    elif [[ -n "$PY" ]]; then
      "$PY" -c "
import json,sys
ctx=sys.argv[1]
print(json.dumps({'hookSpecificOutput':{'hookEventName':'PostToolUse','additionalContext':ctx}}))
" "$IDEMPOTENT_CTX"
    else
      printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"Plan already persisted — idempotent re-fire."}}\n'
    fi
    exit 0
  else
    # Content differs → collision; do NOT overwrite
    COLLISION_MSG="COLLISION: $TARGET_PATH already exists with DIFFERENT content. Hook did NOT overwrite. Resolve the collision manually before committing."
    if command -v jq >/dev/null 2>&1; then
      jq -n --arg msg "$COLLISION_MSG" \
        '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":$msg}}'
    elif [[ -n "$PY" ]]; then
      "$PY" -c "
import json,sys
msg=sys.argv[1]
print(json.dumps({'hookSpecificOutput':{'hookEventName':'PostToolUse','additionalContext':msg}}))
" "$COLLISION_MSG"
    else
      printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"COLLISION: file already exists with different content."}}\n'
    fi
    exit 0
  fi
fi

# --- Write plan to target ---
printf '%s' "$PLAN_CONTENT" > "$TARGET_PATH" || exit 0

# --- Stage with explicit path (NEVER git add -A or git add .) ---
git -C "$REPO_ROOT" add -- "$TARGET_PATH" 2>/dev/null || true

# --- Idempotently insert a Plans-section line into docs/README.md ---
README_MODIFIED=0
if [[ -f "$DOCS_README" ]]; then
  README_LINE="- [\`$TARGET_NAME\`](docs/plans/$TARGET_NAME)"
  # Only insert if line is not already present
  if ! grep -qF "$TARGET_NAME" "$DOCS_README" 2>/dev/null; then
    # Append the line to the README (BSD-portable: no sed -i)
    printf '\n%s\n' "$README_LINE" >> "$DOCS_README" 2>/dev/null && README_MODIFIED=1
    git -C "$REPO_ROOT" add -- "$DOCS_README" 2>/dev/null || true
  fi
fi

# --- Emit additionalContext ---
# COMMIT_CMD includes docs/README.md ONLY when this invocation actually modified
# it — not merely when the file exists. An idempotent re-fire (entry already
# present) leaves README untouched, so the pre-filled commit must not name it.
if [[ "$README_MODIFIED" -eq 1 ]]; then
  COMMIT_CMD="git add -- docs/plans/$TARGET_NAME docs/README.md && git commit -m \"plan: $SLUG\" -- docs/plans/$TARGET_NAME docs/README.md"
else
  COMMIT_CMD="git add -- docs/plans/$TARGET_NAME && git commit -m \"plan: $SLUG\" -- docs/plans/$TARGET_NAME"
fi

ADDITIONAL_CTX="PLAN PERSISTED: docs/plans/$TARGET_NAME has been written and staged.

NEXT — commit now (exact command, copy-paste ready):
  $COMMIT_CMD

SUBAGENT REVIEW ARTIFACTS: If subagent reviews (the Staff Engineer, the Game Dev Reviewer, etc.) were part of this planning session, their outputs must be written to disk NOW. Agent outputs exist only in your context — if you do not write them, they are lost on compaction. Review artifacts are intermediate — write them straight to archive (not active folders). The plan document itself must incorporate ALL review findings unless the EM believes they are in error or require PM input. The goal is a polished plan document, not review clutter."

if command -v jq >/dev/null 2>&1; then
  jq -n --arg ctx "$ADDITIONAL_CTX" \
    '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":$ctx}}'
elif [[ -n "$PY" ]]; then
  "$PY" -c "
import json,sys
ctx=sys.argv[1]
print(json.dumps({'hookSpecificOutput':{'hookEventName':'PostToolUse','additionalContext':ctx}}))
" "$ADDITIONAL_CTX"
else
  # Last-resort: manually escape for JSON output (backslashes FIRST, then quotes,
  # then the newline placeholder — order matters or the escapes double-apply).
  ESC_CTX=$(printf '%s' "$ADDITIONAL_CTX" | tr '\n' '|' | sed 's/\\/\\\\/g; s/"/\\"/g; s/|/\\n/g')
  printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"%s"}}\n' "$ESC_CTX"
fi

exit 0
