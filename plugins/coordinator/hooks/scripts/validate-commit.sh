#!/bin/bash
# PreToolUse hook: Validates git commit commands.
# Fires on ALL Bash tool invocations (PreToolUse matcher is tool-name-only).
# Exits immediately (<10ms) when command is not git commit.
#
# Checks (all warnings, never blocking — exit 0 always):
#   1. .gitignore changes that add patterns matching curated data dirs
#   2. JSON validity in data/ and evaluation/ directories
#   3. Empty JSONL files in chunks/
#
# Input schema (PreToolUse for Bash):
#   { "tool_name": "Bash", "tool_input": { "command": "git commit -m ..." } }

# Safe stdin read — timeout prevents hang on Windows/Git Bash (see memory:
# feedback_no_userpromptsubmit_hooks.md for the full incident).
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

# Parse command — prefer jq, fall back to sed
if command -v jq &>/dev/null; then
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
else
  COMMAND=$(echo "$INPUT" | sed -n 's/.*"command"\s*:\s*"\([^"]*\)".*/\1/p' | head -1)
fi

# Fast exit: only process git commit commands
if ! echo "$COMMAND" | grep -qE '^git[[:space:]]+commit'; then
  exit 0
fi

# Get staged files
STAGED=$(git diff --cached --name-only 2>/dev/null)
if [[ -z "$STAGED" ]]; then
  exit 0
fi

WARNINGS=""

# --- Check 1: .gitignore changes matching curated data dirs ---
GITIGNORE_FILES=$(echo "$STAGED" | grep -E '\.gitignore$' || true)
if [[ -n "$GITIGNORE_FILES" ]]; then
  while IFS= read -r file; do
    if [[ -f "$file" ]]; then
      # Check for deny-all patterns on curated data directories
      for dir in chunks data evaluation training_data; do
        if git diff --cached "$file" 2>/dev/null | grep -qE "^\+.*${dir}(/|\*|$)"; then
          WARNINGS="${WARNINGS}\nGITIGNORE: $file adds pattern matching curated dir '${dir}/'. Per data protection policy, curated data must be tracked."
        fi
      done
    fi
  done <<< "$GITIGNORE_FILES"
fi

# --- Check 2: JSON validity in data/ and evaluation/ ---
JSON_FILES=$(echo "$STAGED" | grep -E '^(data|evaluation)/.*\.json$' || true)
if [[ -n "$JSON_FILES" ]]; then
  PYTHON_CMD=""
  for cmd in python python3 py; do
    if command -v "$cmd" &>/dev/null; then
      PYTHON_CMD="$cmd"
      break
    fi
  done

  if [[ -n "$PYTHON_CMD" ]]; then
    while IFS= read -r file; do
      if [[ -f "$file" ]]; then
        if ! "$PYTHON_CMD" -m json.tool "$file" > /dev/null 2>&1; then
          WARNINGS="${WARNINGS}\nJSON: $file is not valid JSON"
        fi
      fi
    done <<< "$JSON_FILES"
  fi
fi

# --- Check 3: ShellCheck on staged .sh files ---
# Pipe through tr -d '\r' to handle Windows CRLF — shellcheck treats \r as errors.
# Only report non-SC1017 (carriage return) issues to avoid noise on Windows.
SH_FILES=$(echo "$STAGED" | grep -E '\.sh$' || true)
if [[ -n "$SH_FILES" ]] && command -v shellcheck &>/dev/null; then
  while IFS= read -r file; do
    if [[ -f "$file" ]]; then
      SC_OUT=$(tr -d '\r' < "$file" | shellcheck -f gcc -s bash - 2>&1 | sed "s|-:|- $file:|g" || true)
      if [[ -n "$SC_OUT" ]]; then
        WARNINGS="${WARNINGS}\nSHELLCHECK: $file has issues:\n${SC_OUT}"
      fi
    fi
  done <<< "$SH_FILES"
fi

# --- Check 4: Empty JSONL files in chunks/ ---
JSONL_FILES=$(echo "$STAGED" | grep -E '^chunks/.*\.jsonl$' || true)
if [[ -n "$JSONL_FILES" ]]; then
  while IFS= read -r file; do
    if [[ -f "$file" && ! -s "$file" ]]; then
      WARNINGS="${WARNINGS}\nCHUNKS: $file is empty (0 bytes). Curated chunk files should not be empty."
    fi
  done <<< "$JSONL_FILES"
fi

# --- Check 5: Scoped staging — Bash-PreToolUse scope guard (warn-only in Phase 2) ---
# Fires only on `git commit` (already gated above). Compares staged files against
# the current session's scope (touched.txt union mtime-dirty, minus other sessions)
# per Phase 2 of scoped-safety-commits plan.
#
# Phase 2 behavior: warn-only. Foreign files are logged to scope-warnings.log and
# added to WARNINGS — commit is never blocked here (COORDINATOR_SCOPE_STRICT unset).
# Strict-mode blocking is dormant until Phase 5 predicate is met.

# Extract session_id from the hook input JSON already parsed at top of file.
if command -v jq &>/dev/null; then
  SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
else
  SESSION_ID=$(echo "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
fi

SCOPE_FOREIGN_FILES=""

if [[ -n "$SESSION_ID" ]]; then
  # Locate .git root for session dir resolution
  GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
  SESSION_DIR="${GIT_ROOT}/.git/coordinator-sessions/${SESSION_ID}"

  if [[ -d "$SESSION_DIR" ]]; then
    # Source the session library
    LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../../lib/coordinator-session.sh"
    if [[ ! -f "$LIB_PATH" ]]; then
      LIB_PATH="${HOME}/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh"
    fi

    if [[ -f "$LIB_PATH" ]]; then
      # shellcheck source=/dev/null
      source "$LIB_PATH"

      # Compute MY_SCOPE (stdout = scope paths; stderr = skip/orphan diagnostics)
      MY_SCOPE=$(cs_compute_scope "$SESSION_ID" 2>/dev/null || true)

      # Check each staged file against MY_SCOPE
      while IFS= read -r staged_file; do
        [[ -z "$staged_file" ]] && continue

        # Check if staged_file is in MY_SCOPE
        if ! echo "$MY_SCOPE" | grep -qxF "$staged_file" 2>/dev/null; then
          # Foreign file — determine if owned by another session or orphan
          OWNER_SESSION=""
          if [[ -d "${GIT_ROOT}/.git/coordinator-sessions" ]]; then
            for other_sdir in "${GIT_ROOT}/.git/coordinator-sessions"/*/; do
              [[ -d "$other_sdir" ]] || continue
              other_id=$(basename "$other_sdir")
              [[ "$other_id" == "$SESSION_ID" ]] && continue
              [[ "$other_id" == ".archive" ]] && continue
              if [[ -f "${other_sdir}/touched.txt" ]] && grep -qxF "$staged_file" "${other_sdir}/touched.txt" 2>/dev/null; then
                OWNER_SESSION="$other_id"
                break
              fi
            done
          fi

          if [[ -z "$OWNER_SESSION" ]]; then
            OWNER_LABEL="orphan"
          else
            OWNER_LABEL="session ${OWNER_SESSION}"
          fi

          # Log structured entry to scope-warnings.log
          WARN_LOG="${SESSION_DIR}/scope-warnings.log"
          WARN_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
          echo "${WARN_TS} | ${SESSION_ID} | foreign-staged | ${staged_file} | owner:${OWNER_LABEL} | pending-resolution" >> "$WARN_LOG" 2>/dev/null || true

          # Accumulate human-readable warning
          WARNINGS="${WARNINGS}\nSCOPE: ${staged_file} is staged but not in this session's touch list — likely owned by ${OWNER_LABEL}. Strict mode would block this commit."

          # Accumulate for strict-mode block below
          SCOPE_FOREIGN_FILES="${SCOPE_FOREIGN_FILES} ${staged_file}"
        fi
      done <<< "$STAGED"
    fi
  fi
fi

# Print warnings (non-blocking) and always allow commit
if [[ -n "$WARNINGS" ]]; then
  echo -e "=== Commit Validation Warnings ===${WARNINGS}\n===================================" >&2
fi

# NOTE: exit 2 may need to be exit 1 or stderr-message-based — verify Claude Code
# PreToolUse deny contract before setting COORDINATOR_SCOPE_STRICT=1 in Phase 5.

# Strict-mode block (Phase 5 — gated on COORDINATOR_SCOPE_STRICT=1)
if [[ "${COORDINATOR_SCOPE_STRICT:-0}" == "1" && -n "$SCOPE_FOREIGN_FILES" ]]; then
  echo "BLOCKED: commit contains files outside this session's scope:" >&2
  echo "$SCOPE_FOREIGN_FILES" >&2
  echo "" >&2
  echo "Override: set COORDINATOR_OVERRIDE_SCOPE=1 to commit anyway (logged to overrides.log)." >&2
  echo "Or use the scoped helper: ~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-safe-commit \"<subject>\"" >&2
  # If the override env var is set, log and allow:
  if [[ "${COORDINATOR_OVERRIDE_SCOPE:-0}" == "1" ]]; then
    echo "$(date -Iseconds) | $SESSION_ID | OVERRIDE | $SCOPE_FOREIGN_FILES" >> ".git/coordinator-sessions/$SESSION_ID/overrides.log" 2>/dev/null || true
    exit 0
  fi
  exit 2  # PreToolUse deny code — VERIFY this is the correct deny exit code per Claude Code's hook contract before flipping the env var.
fi

exit 0
