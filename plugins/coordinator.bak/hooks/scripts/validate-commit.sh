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

# Print warnings (non-blocking) and always allow commit
if [[ -n "$WARNINGS" ]]; then
  echo -e "=== Commit Validation Warnings ===${WARNINGS}\n===================================" >&2
fi

exit 0
