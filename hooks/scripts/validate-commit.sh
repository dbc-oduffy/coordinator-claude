#!/usr/bin/env bash
# PreToolUse hook: Validates git commit commands.
# Fires on ALL Bash tool invocations (PreToolUse matcher is tool-name-only).
# Exits immediately (<10ms) when command is not git commit.
#
# Checks:
#   1. .gitignore changes that add patterns matching curated data dirs (warn-only)
#   2. JSON validity in data/ and evaluation/ directories (warn-only)
#   3. ShellCheck on staged .sh files (warn-only)
#   4. Empty JSONL files in chunks/ (warn-only)
#   5. Scoped staging — foreign-file detection against session touch list
#      (warn-only in Phase 2; hard block when COORDINATOR_SCOPE_STRICT=1)
#   6. FULLY DECOMMISSIONED — branch-date enforcement removed 2026-05-07
#   7. CLAUDE.md char budget — soft warn at 38K chars; hard block at 40K
#      (override: COORDINATOR_OVERRIDE_CLAUDEMD_BUDGET=1)
#   8. Plan/handoff frontmatter mutation — commit subject must name the
#      mutation (warn-only; hard block when COORDINATOR_FRONTMATTER_STRICT=1)
#   9. Schema version bump tripwire — canonical-structure.yaml change without
#      coordinator-schema-version bump (warn-only; delegates to
#      bin/check-schema-version-bump.sh)
#  10. bin/sh polyglot shebang tripwire — coordinator/bin/ scripts must use
#      #!/bin/sh polyglot (not a named interpreter shebang) (warn-only; delegates to
#      bin/check-bin-sh-polyglot.sh)
#  11. Machine-path leak — settings.json absolute paths hard-block (deny);
#      working-repos.yaml current-home paths warn (delegates to
#      bin/check-machine-path-leak.sh)
#
# Input schema (PreToolUse for Bash):
#   { "tool_name": "Bash", "tool_input": { "command": "git commit -m ..." } }
#
# Sourceable interface: check_validate_commit "$command_string" "$session_id"
#   Prints deny JSON to stdout when blocked; prints nothing on allow.
#   Does NOT read stdin — caller is responsible for parsing input.
#   MUST be called via command-substitution: out=$(check_validate_commit ...); body uses exit, not return.

check_validate_commit() {
  local cmd="${1//$'\r'/}"        # CR-strip — Windows jq.exe CRLF class (parent commit 496271681)
  local session_id="$2"
  set +u +o pipefail              # D6: this script was authored/shipped WITHOUT set flags; the dispatcher
                                  # runs `set -uo pipefail` and the out=$(check_validate_commit ...) command-
                                  # substitution subshell would INHERIT it, changing this script's runtime
                                  # contract (e.g. ${PYTHON_ARGS[@]} on an unset array is a set-u abort trap;
                                  # pipefail flips masked pipeline exit codes). Neutralize here — isolated to
                                  # the subshell, does NOT leak to the dispatcher main shell or sibling checks.

  # Compatibility aliases — body references $COMMAND and $SESSION_ID unchanged.
  local COMMAND="$cmd"
  local SESSION_ID="$session_id"

  # Local declarations — prevents namespace collision when sourced alongside sibling checks.
  local _contains_git_commit _normalized _token
  local file staged_file dir
  local STAGED WARNINGS
  local GITIGNORE_FILES JSON_FILES SH_FILES JSONL_FILES SC_OUT
  local LIB_PATH SCOPE_FOREIGN_FILES
  local GIT_ROOT SESSION_DIR MY_SCOPE
  local OWNER_SESSION OWNER_LABEL WARN_LOG WARN_TS other_sdir other_id
  local CLAUDEMD_FILES CLAUDEMD_HARD_VIOLATION CLAUDEMD_SOFT_NAMES
  local CLAUDEMD_SOFT_LIMIT CLAUDEMD_HARD_LIMIT _cf _csize
  local REASON ESC_REASON GIT_ROOT_LOG OVERRIDE_LOG
  local FRONTMATTER_FILES FRONTMATTER_MUTATIONS DIFF SENSITIVE
  local SUBJECT SUBJECT_LC SUBJECT_OK token
  local _RCC_LIB_VC COORDINATOR_CONTENT_ROOT
  local BUMP_CHECK_SCRIPT BUMP_OUT BUMP_EXIT
  local SHEBANG_CHECK_SCRIPT SHEBANG_OUT SHEBANG_EXIT
  local MACHINE_PATH_LEAK_SCRIPT
  local SETTINGS_STAGED WORKING_REPOS_STAGED _sf _wf
  local LEAK_STDERR_TMP LEAK_STDOUT LEAK_EXIT LEAK_STDERR WARN_EXCERPT
  local PYTHON_BIN
  local -a PYTHON_ARGS
  local _cc_root

  # Fast exit: only process git commit commands.
  # Fast path: command starts with "git commit" (most common case, <1ms).
  # Slow path: tokenize on shell separators (;, &&, ||) and test each
  # subcommand's leading word pair — catches chained forms like:
  #   git status && git commit -m "..."
  #   cd foo && git commit -m "..."
  # Each token is stripped of leading whitespace before testing so that
  # "git commit" must appear as the first two words of a subcommand, not
  # anywhere inside a quoted string or a longer word (e.g. git commits).
  _contains_git_commit=0
  if echo "$COMMAND" | grep -qE '^git[[:space:]]+commit([[:space:]]|$)'; then
    _contains_git_commit=1
  else
    # Split on &&, ||, ; — replace each with a newline, then test each line.
    _normalized=$(printf '%s' "$COMMAND" | sed 's/&&/\n/g; s/||/\n/g; s/;/\n/g')
    while IFS= read -r _token; do
      # Strip leading whitespace from token
      _token="${_token#"${_token%%[! ]*}"}"
      if echo "$_token" | grep -qE '^git[[:space:]]+commit([[:space:]]|$)'; then
        _contains_git_commit=1
        break
      fi
    done <<< "$_normalized"
  fi
  if [[ "$_contains_git_commit" -eq 0 ]]; then
    exit 0
  fi

  # Get staged files
  STAGED=$(git diff --cached --name-only 2>/dev/null)
  if [[ -z "$STAGED" ]]; then
    exit 0
  fi

  WARNINGS=""

  # Resolve coordinator root once for library fallback lookups (soft-degrade: _cc_root=""
  # on .doe-root miss — hook always exits 0, never hard-fails on missing libs).
  _cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
  # shellcheck source=/dev/null
  source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
  if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
    coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0" || _cc_root=''
  else
    _cc_root=''
  fi
  [ -d "$_cc_root" ] || _cc_root=""

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
    # Resolve via shared lib so Windows uses pythonw.exe (no console flash).
    LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/resolve-python.sh"
    [[ ! -f "$LIB_PATH" && -n "$_cc_root" ]] && LIB_PATH="${_cc_root}/lib/resolve-python.sh"
    # shellcheck source=/dev/null
    [[ -f "$LIB_PATH" ]] && source "$LIB_PATH"

    if [[ -n "$PYTHON_BIN" ]]; then
      while IFS= read -r file; do
        if [[ -f "$file" ]]; then
          if ! "$PYTHON_BIN" "${PYTHON_ARGS[@]}" -m json.tool "$file" > /dev/null 2>&1; then
            WARNINGS="${WARNINGS}\nJSON: $file is not valid JSON"
          fi
        fi
      done <<< "$JSON_FILES"
    fi
  fi

  # --- Check 3: ShellCheck on staged .sh files ---
  # Pipe through tr -d '\r' to handle Windows CRLF — shellcheck treats \r as errors.
  # Strip CRLF before piping to shellcheck — prevents SC1017 (carriage-return) noise on Windows.
  SH_FILES=$(echo "$STAGED" | grep -E '\.sh$' || true)
  if [[ -n "$SH_FILES" ]] && command -v shellcheck &>/dev/null; then
    while IFS= read -r file; do
      if [[ -f "$file" ]]; then
        SC_OUT=$(git show ":${file}" 2>/dev/null | tr -d '\r' | shellcheck -f gcc -s bash - 2>&1 | sed "s|-:|${file}:|g" || true)
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
  #
  # SESSION_ID is provided as $2 (function argument) — no stdin re-parse needed.

  SCOPE_FOREIGN_FILES=""

  if [[ -n "$SESSION_ID" ]]; then
    # Locate .git root for session dir resolution
    GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
    SESSION_DIR="${GIT_ROOT}/.git/coordinator-sessions/${SESSION_ID}"

    if [[ -d "$SESSION_DIR" ]]; then
      # Source the session library
      LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../../lib/coordinator-session.sh"
      if [[ ! -f "$LIB_PATH" && -n "$_cc_root" ]]; then
        LIB_PATH="${_cc_root}/lib/coordinator-session.sh"
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
                [[ "$other_id" == ".agents" ]] && continue
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

  # --- Check 7: CLAUDE.md char budget ---
  # Claude Code shows a perf warning when any auto-loaded CLAUDE.md exceeds 40K chars.
  # Soft threshold (38K, warn) and hard threshold (40K, block) on staged CLAUDE.md files.
  # Override: COORDINATOR_OVERRIDE_CLAUDEMD_BUDGET=1 (emergency only; logged).
  CLAUDEMD_FILES=$(echo "$STAGED" | grep -E '(^|/)CLAUDE\.md$' || true)
  CLAUDEMD_HARD_VIOLATION=""
  CLAUDEMD_SOFT_NAMES=""
  CLAUDEMD_SOFT_LIMIT=38000
  CLAUDEMD_HARD_LIMIT=40000

  if [[ -n "$CLAUDEMD_FILES" ]]; then
    while IFS= read -r _cf; do
      [[ -z "$_cf" ]] && continue
      # Use the staged blob (what would actually land), not the worktree file.
      _csize=$(git show ":${_cf}" 2>/dev/null | LC_ALL=C.UTF-8 wc -m | tr -d ' ')
      [[ -z "$_csize" || "$_csize" -eq 0 ]] && continue
      if [[ "$_csize" -gt "$CLAUDEMD_HARD_LIMIT" ]]; then
        CLAUDEMD_HARD_VIOLATION="${CLAUDEMD_HARD_VIOLATION}"$'\n'"  ${_cf} = ${_csize} chars (limit ${CLAUDEMD_HARD_LIMIT})"
      elif [[ "$_csize" -gt "$CLAUDEMD_SOFT_LIMIT" ]]; then
        CLAUDEMD_SOFT_NAMES="${CLAUDEMD_SOFT_NAMES}"$'\n'"  ${_cf} = ${_csize} chars (soft ${CLAUDEMD_SOFT_LIMIT}; hard ${CLAUDEMD_HARD_LIMIT})"
      fi
    done <<< "$CLAUDEMD_FILES"
  fi

  if [[ -n "$CLAUDEMD_SOFT_NAMES" ]]; then
    WARNINGS="${WARNINGS}\nCLAUDEMD-BUDGET (soft):${CLAUDEMD_SOFT_NAMES}\n  → Approaching 40K perf warning. Demote a section to docs/wiki/ before the next addition."
  fi

  # Hard violation: emit JSON deny on stdout, print warnings to stderr, exit 0.
  if [[ -n "$CLAUDEMD_HARD_VIOLATION" && "${COORDINATOR_OVERRIDE_CLAUDEMD_BUDGET:-0}" != "1" ]]; then
    if [[ -n "$WARNINGS" ]]; then
      # $WARNINGS is the %b ARGUMENT (never the format string — no injection risk).
      # %b is intentional: WARNINGS is assembled with literal "\n" separators that must
      # expand to newlines here. Content is internally-built (ShellCheck output + our own
      # strings); a stray "\c"/"\x.." in that content would be %b-interpreted, but the
      # inputs don't carry those. Applies to all four warning-banner emits in this file.
      printf '=== Commit Validation Warnings ===%b\n===================================\n' "$WARNINGS" >&2
    fi
    REASON="BLOCKED: staged CLAUDE.md exceeds 40K char limit (Claude Code perf warning threshold):${CLAUDEMD_HARD_VIOLATION}"$'\n\n'
    REASON+="Trim before committing: demote a section to docs/wiki/ and replace with a pointer."$'\n'
    REASON+="Emergency override (logged): COORDINATOR_OVERRIDE_CLAUDEMD_BUDGET=1"

    if command -v jq &>/dev/null; then
      jq -nc --arg reason "$REASON" '{
        hookSpecificOutput: {
          hookEventName: "PreToolUse",
          permissionDecision: "deny",
          permissionDecisionReason: $reason
        }
      }'
    else
      ESC_REASON=${REASON//\\/\\\\}
      ESC_REASON=${ESC_REASON//\"/\\\"}
      ESC_REASON=${ESC_REASON//$'\n'/\\n}
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$ESC_REASON"
    fi
    exit 0
  fi

  if [[ -n "$CLAUDEMD_HARD_VIOLATION" && "${COORDINATOR_OVERRIDE_CLAUDEMD_BUDGET:-0}" == "1" ]]; then
    GIT_ROOT_LOG=$(git rev-parse --show-toplevel 2>/dev/null || true)
    OVERRIDE_LOG="${GIT_ROOT_LOG:-.}/.git/coordinator-sessions/${SESSION_ID:-no-session}/overrides.log"
    mkdir -p "$(dirname "$OVERRIDE_LOG")" 2>/dev/null || true
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | ${SESSION_ID:-no-session} | OVERRIDE-CLAUDEMD-BUDGET |$(printf '%b\n' "$CLAUDEMD_HARD_VIOLATION" | tr '\n' ' ')" >> "$OVERRIDE_LOG" 2>/dev/null || true
    WARNINGS="${WARNINGS}\nCLAUDEMD-BUDGET (override):${CLAUDEMD_HARD_VIOLATION}"
  fi

  # NOTE: warn-only output is flushed ONCE at the end of the script (see the final
  # flush before `exit 0`), so checks that accumulate into WARNINGS *after* this
  # point (Check 8 frontmatter, Check 9 schema-bump) are surfaced too. Each
  # early-exit hard/strict block below prints WARNINGS itself before emitting deny.

  # Strict-mode block (Phase 5 — gated on COORDINATOR_SCOPE_STRICT=1).
  #
  # Deny contract verified 2026-04-27 against canonical docs at
  # https://code.claude.com/docs/en/hooks. Uses the modern JSON output form
  # (hookSpecificOutput.permissionDecision = "deny") rather than exit 2 + stderr.
  # Both are valid; JSON is preferred because permissionDecisionReason is
  # purpose-built to surface the message verbatim to the EM Claude session.
  # See coordinator/docs/preooluse-deny-contract.md for verification details.
  if [[ "${COORDINATOR_SCOPE_STRICT:-0}" == "1" && -n "$SCOPE_FOREIGN_FILES" ]]; then
    # Early-exit path: print accumulated warnings before allowing/denying.
    if [[ -n "$WARNINGS" ]]; then
      printf '=== Commit Validation Warnings ===%b\n===================================\n' "$WARNINGS" >&2
    fi
    # If the override env var is set, log and allow:
    if [[ "${COORDINATOR_OVERRIDE_SCOPE:-0}" == "1" ]]; then
      echo "$(date -Iseconds) | $SESSION_ID | OVERRIDE | $SCOPE_FOREIGN_FILES" >> ".git/coordinator-sessions/$SESSION_ID/overrides.log" 2>/dev/null || true
      exit 0
    fi

    # Build the deny reason — surfaced to the EM via permissionDecisionReason
    REASON="BLOCKED: commit contains files outside this session's scope:${SCOPE_FOREIGN_FILES}"$'\n\n'
    REASON+="Override: set COORDINATOR_OVERRIDE_SCOPE=1 to commit anyway (logged to overrides.log)."$'\n'
    REASON+="Stage explicit paths: git add -- <paths>, then git commit -m \"<subject>\" -- <paths>."$'\n'
    REASON+="The helper is reserved for sweep ceremonies (/workstream-start, /workday-complete, /update-docs, relay-protocol, distillation — all --blanket) and agents/executor.md (--expected-branch per SC-DR-006). See docs/wiki/scoped-safety-commits.md SC-DR-008."

    # Emit the JSON deny form on stdout (only parsed on exit 0).
    # jq is preferred for proper escaping; fall back to printf-based JSON if absent.
    if command -v jq &>/dev/null; then
      jq -nc --arg reason "$REASON" '{
        hookSpecificOutput: {
          hookEventName: "PreToolUse",
          permissionDecision: "deny",
          permissionDecisionReason: $reason
        }
      }'
    else
      # Minimal JSON-string escaping (newline, quote, backslash). Adequate for
      # our reason content which contains only ASCII + newlines + quotes.
      ESC_REASON=${REASON//\\/\\\\}
      ESC_REASON=${ESC_REASON//\"/\\\"}
      ESC_REASON=${ESC_REASON//$'\n'/\\n}
      printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$ESC_REASON"
    fi

    exit 0
  fi

  # --- Check 6: FULLY DECOMMISSIONED ---
  # Branch discipline at commit time was Check 6 in this file. It was temporarily
  # consolidated into block-off-daily-branch.sh (`commit` arm) by the Staff Engineer F11.
  # That commit arm has now been deleted entirely (2026-05-07, per PM call) —
  # the hook no longer enforces branch-date at commit time at all.
  # See docs/plans/2026-05-07-daily-branch-doctrine-rethink.md Phase 2.
  # This hook handles commit-content validation only (Checks 1-5 above).

  # --- Check 8: Plan/handoff frontmatter mutation needs commit-subject discipline ---
  # When a staged file is under tasks/plans/, state/handoffs/, or docs/plans/ AND
  # the diff modifies frontmatter (lines between the first two `---` delimiters,
  # specifically `status:` / `deployment_state:` / `consumed_by:` / `shipped_in:` keys),
  # the commit subject MUST name at least one of:
  #   - the frontmatter key that changed (e.g., "deployment_state:", "status:")
  #   - one of the lifecycle verbs: pickup, handoff, consume, ship, abandon, supersede
  # Otherwise warn (or block under COORDINATOR_FRONTMATTER_STRICT=1).
  #
  # Doctrine: coordinator/CLAUDE.md:206-209 — deployment_state and status enums are
  # load-bearing for /workstream-start, /workday-start, query-driven surfacing. A
  # frontmatter mutation without a subject-line audit trail makes
  # `git log -- state/handoffs/<file>` opaque.

  # L6 fix: seam-aware handoffs path prefix — routes through coordinator_state_root
  # so the pattern stays valid after state migrates from meta-repo to example-orchestration-hub.
  # Source coordinator-state-root.sh (guarded); restore set +u +o pipefail immediately
  # after, since coordinator-state-root.sh enables set -uo pipefail at source time and
  # this function's contract (line 39) neutralises those flags for its duration.
  # Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § L6/C4
  local _vc_handoffs_prefix="state/handoffs"
  local _vc_csr_lib
  _vc_csr_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)/lib/coordinator-state-root.sh"
  if [[ -f "$_vc_csr_lib" ]]; then
    # shellcheck source=../../lib/coordinator-state-root.sh
    source "$_vc_csr_lib" 2>/dev/null || true
    set +u +o pipefail  # restore — coordinator-state-root.sh enables set -uo pipefail
    local _vc_git_root _vc_st_root
    _vc_git_root=$(git rev-parse --show-toplevel 2>/dev/null || true)
    _vc_st_root=$(coordinator_state_root 2>/dev/null || true)
    if [[ -n "$_vc_st_root" && -n "$_vc_git_root" && "$_vc_st_root" == "${_vc_git_root}/"* ]]; then
      # State root is within this git root — compute repo-relative prefix.
      _vc_handoffs_prefix="${_vc_st_root#${_vc_git_root}/}/handoffs"
    fi
    # If state root is outside git root (meta-repo → example-orchestration-hub after migration): keep
    # fallback "state/handoffs". Staged paths from an external repo can never appear
    # in git diff --cached of this repo, so the pattern correctly matches nothing.
  fi
  FRONTMATTER_FILES=$(echo "$STAGED" | grep -E "^(tasks/plans|${_vc_handoffs_prefix}|docs/plans)/.*\\.md\$" || true)
  FRONTMATTER_MUTATIONS=""

  if [[ -n "$FRONTMATTER_FILES" ]]; then
    while IFS= read -r file; do
      [[ -z "$file" ]] && continue
      [[ ! -f "$file" ]] && continue

      # Check whether the staged diff touches frontmatter lines (between first two `---`).
      # Use `git diff --cached -U0` to get exact added/removed lines.
      DIFF=$(git diff --cached -U0 -- "$file" 2>/dev/null || true)
      [[ -z "$DIFF" ]] && continue

      # Look for added/removed lines matching frontmatter-sensitive keys.
      # Match lines starting with +/- (but not +++/---) followed by a key.
      # NOTE: this pattern matches any diff line with these keys, not just lines
      # inside the YAML frontmatter block. False positives possible if the body
      # contains instructional YAML snippets (e.g., a docs/plans/ file showing
      # `deployment_state: ready_to_fire` as an example). Path filter + warn-only
      # nature makes this acceptable; tighten if false positives observed.
      SENSITIVE=$(echo "$DIFF" | grep -E '^[+-](status|deployment_state|consumed_by|shipped_in|predecessor|kind):' | grep -v -E '^(\+\+\+|---)' || true)
      if [[ -n "$SENSITIVE" ]]; then
        FRONTMATTER_MUTATIONS="${FRONTMATTER_MUTATIONS} ${file}"
      fi
    done <<< "$FRONTMATTER_FILES"
  fi

  if [[ -n "$FRONTMATTER_MUTATIONS" ]]; then
    # Extract commit subject from the command. The commit message is in the -m argument.
    # Tokens like: git commit -m "subject" or git commit -m 'subject' or here-doc.
    # Parse from the full COMMAND variable (already extracted at top of script).
    SUBJECT=$(echo "$COMMAND" | sed -n "s/.*-m[[:space:]]*[\"']\\([^\"']*\\)[\"'].*/\\1/p" | head -1)
    # Fallback: heredoc-style commits embed newlines; collapse and retry extraction.
    if [[ -z "$SUBJECT" ]]; then
      SUBJECT=$(echo "$COMMAND" | tr -s '\n' ' ' | sed -n "s/.*-m[[:space:]]*[\"']\\([^\"']*\\)[\"'].*/\\1/p" | head -1)
    fi
    # If sed didn't match (here-doc or unusual quoting), leave SUBJECT empty — fail open with warning.

    SUBJECT_LC=$(echo "$SUBJECT" | tr '[:upper:]' '[:lower:]')
    # Accept if subject names a frontmatter key OR a lifecycle verb.
    SUBJECT_OK=0
    for token in "status:" "deployment_state:" "consumed_by:" "shipped_in:" "predecessor:" "kind:" \
                 "pickup" "handoff" "consume" "ship" "abandon" "supersede"; do
      if echo "$SUBJECT_LC" | grep -qF "$token"; then
        SUBJECT_OK=1
        break
      fi
    done

    if [[ "$SUBJECT_OK" -eq 0 ]]; then
      WARNINGS="${WARNINGS}\nFRONTMATTER-MUTATION: staged files modify load-bearing frontmatter (status/deployment_state/consumed_by/shipped_in/predecessor/kind) without naming the mutation in the commit subject:${FRONTMATTER_MUTATIONS}\n  → Commit subject should include the changed key (e.g., 'deployment_state:') OR a lifecycle verb (pickup/handoff/consume/ship/abandon/supersede). Without this, git log -- <file> loses the audit trail. See coordinator/CLAUDE.md § Handoff Lineage. (heredoc commit subjects may not parse — confirm your subject names the mutation if you used a heredoc form)"

      # Strict-mode block (gated on COORDINATOR_FRONTMATTER_STRICT=1).
      if [[ "${COORDINATOR_FRONTMATTER_STRICT:-0}" == "1" && "${COORDINATOR_OVERRIDE_FRONTMATTER:-0}" != "1" ]]; then
        # Early-exit path: print accumulated warnings before emitting deny.
        if [[ -n "$WARNINGS" ]]; then
          printf '=== Commit Validation Warnings ===%b\n===================================\n' "$WARNINGS" >&2
        fi
        REASON="BLOCKED: commit modifies load-bearing frontmatter without subject-line audit trail.\n\nFiles:${FRONTMATTER_MUTATIONS}\n\nFix: amend commit subject to name the changed key (e.g., 'handoff: flip deployment_state to ready_to_fire') or a lifecycle verb.\n\nOverride: COORDINATOR_OVERRIDE_FRONTMATTER=1 (logged)."
        if command -v jq &>/dev/null; then
          jq -nc --arg reason "$REASON" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason}}'
        else
          ESC_REASON=${REASON//\\/\\\\}; ESC_REASON=${ESC_REASON//\"/\\\"}; ESC_REASON=${ESC_REASON//$'\n'/\\n}
          printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$ESC_REASON"
        fi
        exit 0
      fi

      # Override logging — mirrors CLAUDEMD_BUDGET override-log shape (L260-266).
      if [[ "${COORDINATOR_FRONTMATTER_STRICT:-0}" == "1" && "${COORDINATOR_OVERRIDE_FRONTMATTER:-0}" == "1" ]]; then
        GIT_ROOT_LOG=$(git rev-parse --show-toplevel 2>/dev/null || true)
        OVERRIDE_LOG="${GIT_ROOT_LOG:-.}/.git/coordinator-sessions/${SESSION_ID:-no-session}/overrides.log"
        mkdir -p "$(dirname "$OVERRIDE_LOG")" 2>/dev/null || true
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | ${SESSION_ID:-no-session} | OVERRIDE-FRONTMATTER-MUTATION |${FRONTMATTER_MUTATIONS}" >> "$OVERRIDE_LOG" 2>/dev/null || true
        WARNINGS="${WARNINGS}\nFRONTMATTER-MUTATION (override):${FRONTMATTER_MUTATIONS}"
      fi
    fi
  fi

  # Resolve coordinator content root once for checks 9–11 (bin script delegation).
  # Sourced (no args): sets COORDINATOR_CONTENT_ROOT in this scope (empty if unresolved).
  # Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md § C2b
  _RCC_LIB_VC="$(dirname "${BASH_SOURCE[0]}")/../../lib/resolve-coordinator-clone.sh"
  # shellcheck source=/dev/null
  [[ -f "$_RCC_LIB_VC" ]] && source "$_RCC_LIB_VC"

  # --- Check 9: Schema version bump tripwire ---
  # canonical-structure.yaml must not change without a corresponding bump to
  # coordinator-schema-version. Delegates to bin/check-schema-version-bump.sh
  # (warn-only — does not block unrelated commits).
  #
  # Rationale: a structural schema change without a version bump causes consumer
  # repos' currency stamps to silently remain "current" even though they were
  # onboarded against a different schema — exactly the class of silent drift that
  # the currency system was built to detect.
  #
  # Doctrine: lib/coordinator-currency.sh § coordinator_currency_probe;
  # docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1.

  BUMP_CHECK_SCRIPT="$(dirname "${BASH_SOURCE[0]}")/../../bin/check-schema-version-bump.sh"
  if [[ ! -f "$BUMP_CHECK_SCRIPT" ]]; then
    BUMP_CHECK_SCRIPT="${COORDINATOR_CONTENT_ROOT:-${HOME}/.claude/plugins/coordinator-claude/coordinator}/bin/check-schema-version-bump.sh"
  fi

  if [[ -f "$BUMP_CHECK_SCRIPT" ]]; then
    BUMP_OUT="$("$BASH" "$BUMP_CHECK_SCRIPT" --staged 2>/dev/null)"
    BUMP_EXIT=$?
    if [[ $BUMP_EXIT -eq 1 ]]; then
      WARNINGS="${WARNINGS}\nSCHEMA-BUMP-TRIPWIRE:\n${BUMP_OUT}"
    fi
    # BUMP_EXIT 2 = script error (not a git repo, etc.) — silently skip
  fi

  # --- Check 10: bin/sh polyglot shebang tripwire ---
  # coordinator/bin/ scripts must use a #!/bin/sh polyglot shebang, not a named
  # interpreter shebang (#!/usr/bin/env python, #!/usr/bin/env python3, etc.).
  # Delegates to bin/check-bin-sh-polyglot.sh --staged (warn-only).
  #
  # Doctrine: docs/wiki/cross-platform-shell-portability.md § sh/python trampoline.
  # Greppable token: BIN-SH-POLYGLOT-TRIPWIRE.

  SHEBANG_CHECK_SCRIPT="$(dirname "${BASH_SOURCE[0]}")/../../bin/check-bin-sh-polyglot.sh"
  if [[ ! -f "$SHEBANG_CHECK_SCRIPT" ]]; then
    SHEBANG_CHECK_SCRIPT="${COORDINATOR_CONTENT_ROOT:-${HOME}/.claude/plugins/coordinator-claude/coordinator}/bin/check-bin-sh-polyglot.sh"
  fi

  if [[ -f "$SHEBANG_CHECK_SCRIPT" ]]; then
    SHEBANG_OUT="$("$BASH" "$SHEBANG_CHECK_SCRIPT" --staged 2>/dev/null)"
    SHEBANG_EXIT=$?
    if [[ $SHEBANG_EXIT -eq 1 ]]; then
      WARNINGS="${WARNINGS}\nBIN-SH-POLYGLOT-TRIPWIRE:\n${SHEBANG_OUT}"
    fi
    # SHEBANG_EXIT 0 = OK; 1 = violation (warned above); any other non-zero =
    # infrastructure error (script not in a git repo, etc.) — silently skip,
    # mirroring Check 9's BUMP_EXIT 2 treatment.
  fi

  # --- Check 11: Machine-path leak guard ---
  # settings.json staged in this commit → HARD BLOCK if a machine-specific absolute
  # path leaf value is found (any /Users/<n>/, /home/<n>/, C:\Users\, X:\, E:\).
  # working-repos.yaml staged in this commit → SOFT WARN if a current-machine
  # $HOME-rooted path leaf value is found (foreign-machine catalog paths are fine).
  # Delegates to bin/check-machine-path-leak.sh.
  # Doctrine: docs/plans/2026-06-23-machine-path-leak-guard.md
  # Greppable token: MACHINE-PATH-LEAK-TRIPWIRE

  MACHINE_PATH_LEAK_SCRIPT="$(dirname "${BASH_SOURCE[0]}")/../../bin/check-machine-path-leak.sh"
  if [[ ! -f "$MACHINE_PATH_LEAK_SCRIPT" ]]; then
    MACHINE_PATH_LEAK_SCRIPT="${COORDINATOR_CONTENT_ROOT:-${HOME}/.claude/plugins/coordinator-claude/coordinator}/bin/check-machine-path-leak.sh"
  fi

  if [[ -f "$MACHINE_PATH_LEAK_SCRIPT" ]]; then
    # Identify which of the two sentinel files are in this commit's staged set.
    # Review: reviewer — P2 Finding 7: use ${STAGED:-} so nounset cannot trip if STAGED is somehow unset.
    SETTINGS_STAGED=$(echo "${STAGED:-}" | grep -E '(^|/)settings\.json$' || true)
    WORKING_REPOS_STAGED=$(echo "${STAGED:-}" | grep -E '(^|/)working-repos\.yaml$' || true)

    # --- settings.json: HARD BLOCK sink ---
    if [[ -n "$SETTINGS_STAGED" ]]; then
      while IFS= read -r _sf; do
        [[ -z "$_sf" ]] && continue
        LEAK_STDERR_TMP="$(mktemp 2>/dev/null || echo "/tmp/_machine_leak_err_$$")"
        LEAK_STDOUT=$("$BASH" "$MACHINE_PATH_LEAK_SCRIPT" "$_sf" 2>"$LEAK_STDERR_TMP")
        LEAK_EXIT=$?
        LEAK_STDERR=$(cat "$LEAK_STDERR_TMP" 2>/dev/null || true)
        rm -f "$LEAK_STDERR_TMP"

        if [[ $LEAK_EXIT -eq 1 ]]; then
          # Hard violation — print accumulated warnings then emit deny JSON.
          if [[ -n "$WARNINGS" ]]; then
            printf '=== Commit Validation Warnings ===%b\n===================================\n' "$WARNINGS" >&2
          fi
          REASON="BLOCKED: ${_sf} contains machine-specific absolute path(s) that must not be committed."$'\n\n'
          REASON+="${LEAK_STDERR}"$'\n\n'
          REASON+="Machine-specific paths must live in gitignored settings.local.json or machine-local registry, not in tracked settings.json."$'\n'
          REASON+="See docs/plans/2026-06-23-machine-path-leak-guard.md"

          if command -v jq &>/dev/null; then
            jq -nc --arg reason "$REASON" '{
              hookSpecificOutput: {
                hookEventName: "PreToolUse",
                permissionDecision: "deny",
                permissionDecisionReason: $reason
              }
            }'
          else
            ESC_REASON=${REASON//\\/\\\\}
            ESC_REASON=${ESC_REASON//\"/\\\"}
            ESC_REASON=${ESC_REASON//$'\n'/\\n}
            printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$ESC_REASON"
          fi
          exit 0
        fi
        # LEAK_EXIT 0 = OK; LEAK_EXIT 2 = infrastructure error — skip silently.
      done <<< "$SETTINGS_STAGED"
    fi

    # --- working-repos.yaml: SOFT WARN sink ---
    if [[ -n "$WORKING_REPOS_STAGED" ]]; then
      while IFS= read -r _wf; do
        [[ -z "$_wf" ]] && continue
        LEAK_STDERR_TMP="$(mktemp 2>/dev/null || echo "/tmp/_machine_leak_err_$$")"
        "$BASH" "$MACHINE_PATH_LEAK_SCRIPT" "$_wf" 2>"$LEAK_STDERR_TMP" || true
        LEAK_STDERR=$(cat "$LEAK_STDERR_TMP" 2>/dev/null || true)
        rm -f "$LEAK_STDERR_TMP"

        # The guard emits "WARN:" lines to stderr for soft violations.
        if echo "$LEAK_STDERR" | grep -q "^WARN:"; then
          WARN_EXCERPT=$(echo "$LEAK_STDERR" | grep "^WARN:" | head -5)
          WARNINGS="${WARNINGS}\nMACHINE-PATH-LEAK-TRIPWIRE (working-repos.yaml): ${_wf} contains current-machine home-rooted path(s) — consider moving to machine-local registry:\n${WARN_EXCERPT}"
        fi
      done <<< "$WORKING_REPOS_STAGED"
    fi
  fi

  # --- Single warn-only flush ---
  # Every warn-only check (1-11) appends to WARNINGS above. This is the single sink
  # that surfaces them; the early-exit hard/strict blocks each printed WARNINGS
  # themselves before denying. Flushing here (not before Checks 8/9) is what fixes
  # the previously-dropped frontmatter + schema-bump warnings.
  if [[ -n "$WARNINGS" ]]; then
    printf '=== Commit Validation Warnings ===%b\n===================================\n' "$WARNINGS" >&2
  fi

  exit 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  # Safe stdin read — timeout prevents hang on Windows/Git Bash (see memory:
  # feedback_no_userpromptsubmit_hooks.md for the full incident).
  if command -v timeout &>/dev/null; then
    INPUT=$(timeout 2 cat 2>/dev/null || true)
  else
    INPUT=$(cat)
  fi

  # Parse command — prefer jq, fall back to sed
  if command -v jq &>/dev/null; then
    _COMMAND_PARSED=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
  else
    _COMMAND_PARSED=$(echo "$INPUT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi

  # Parse session_id — prefer jq, fall back to sed
  if command -v jq &>/dev/null; then
    _SESSION_PARSED=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
  else
    _SESSION_PARSED=$(echo "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
  fi

  check_validate_commit "$_COMMAND_PARSED" "$_SESSION_PARSED"
  exit 0  # not reached — check_validate_commit always exits internally
fi
