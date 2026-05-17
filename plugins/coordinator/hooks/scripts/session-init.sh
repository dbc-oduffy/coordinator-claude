#!/bin/bash
# SessionStart hook: Initialize the coordinator session directory and write the
# .current-session-id sentinel so coordinator-safe-commit can resolve the
# session_id from a non-hook subprocess (the EM's interactive Bash).
#
# Without this hook, the helper has no path to the session_id:
#   - CLAUDE_SESSION_ID is not exported to the EM's subprocess (Claude Code only
#     puts session_id in hook input JSON).
#   - track-touched-files.sh creates session dirs only on the first Edit/Write,
#     so early-session helper invocations would fail.
#   - The PID-scan fallback is broken because cs_init records $$ (the hook
#     subprocess PID), which is dead by the time the helper runs.
#
# Concurrency note: the sentinel is "last writer wins". When two Claude Code
# sessions run in the same repo, the most recently started session owns the
# sentinel. Other sessions must use CLAUDE_SESSION_ID explicitly. This is
# acceptable — the sentinel is a convenience for the common single-session case;
# the helper's post-filter (touched.txt membership requirement) prevents foreign
# files from being staged even on sentinel collisions.
#
# Input schema (SessionStart):
#   { "session_id": "<id>", "source": "startup|compact|clear", ... }
#
# Always exits 0 — never blocks session start.

# --- Safe stdin read with timeout (mirror existing hook pattern) ---
if command -v timeout &>/dev/null; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

[[ -z "$INPUT" ]] && exit 0

# --- Extract session_id (prefer jq, fall back to bash string ops) ---
if command -v jq &>/dev/null; then
  SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
else
  if [[ "$INPUT" != *'"session_id"'* ]]; then
    exit 0
  fi
  _tmp="${INPUT#*\"session_id\":\"}"
  SESSION_ID="${_tmp%%\"*}"
fi

[[ -z "$SESSION_ID" ]] && exit 0

# --- Locate git root (skip if not in a repo) ---
GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -z "$GIT_ROOT" ]] && exit 0

SESSIONS_DIR="${GIT_ROOT}/.git/coordinator-sessions"
mkdir -p "$SESSIONS_DIR" 2>/dev/null || exit 0

# --- Source the lib and call cs_init for proper session-dir setup ---
LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
[[ ! -f "$LIB_PATH" ]] && LIB_PATH="${HOME}/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh"

if [[ -f "$LIB_PATH" ]]; then
  # shellcheck source=/dev/null
  source "$LIB_PATH"
  cs_init "$SESSION_ID" 2>/dev/null || true
else
  # Lib missing — minimal session-dir bootstrap (mirror track-touched-files.sh)
  SESSION_DIR="${SESSIONS_DIR}/${SESSION_ID}"
  mkdir -p "$SESSION_DIR" 2>/dev/null || exit 0
  touch "${SESSION_DIR}/touched.txt"
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "${SESSION_DIR}/started_at"
  git rev-parse HEAD 2>/dev/null > "${SESSION_DIR}/head_at_start" || echo "unknown" > "${SESSION_DIR}/head_at_start"
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  printf '{"session_id":"%s","branch":"%s","pid":"%s","last_activity":"%s","goal":""}\n' \
    "$SESSION_ID" "$BRANCH" "$$" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" > "${SESSION_DIR}/meta.json"
fi

# --- Write the .current-session-id sentinel ---
# This is what coordinator-safe-commit's Priority-2 resolution reads.
echo "$SESSION_ID" > "${SESSIONS_DIR}/.current-session-id"

# --- Orphan consumed-handoff sweep (spec backlink: tasks/split-pickup-archival/plan.md § Edit 7) ---
#
# Under the split-pickup-archival lifecycle, /pickup mutates frontmatter only
# (status: consumed, deployment_state: in_flight, consumed_by: <sid>). Archival
# to archive/handoffs/ happens at the terminal event: /handoff chain-archival or
# /session-end Step 2.7. A handoff in tasks/handoffs/ with status: consumed is
# therefore an orphan — the picking-up session died before its terminal event.
#
# Recovery: for each such file, check if the consuming session is still alive. If
# the session is dead (no .git/coordinator-sessions/<sid>/ dir, or its PID is dead),
# and consumed_at is not in the future (sanity check), flip deployment_state from
# in_flight to abandoned (closure-on-archive — otherwise archived records look
# active forever to any query over archive/handoffs/) and git mv the file to
# archive/handoffs/. No PM ping, no WARNING line — silent recovery.
#
# This handles: cross-machine pickup-then-end-elsewhere, mid-workstream Claude Code
# restart, crash-without-/session-end. Recovery latency drops from "7 days" (reaper)
# to "next session boot."
#
# Why query-records, not grep: per coordinator CLAUDE.md "Tripwire call-shape
# coverage" rule, raw grep misses quoted/whitespace variants. query-records uses
# the schema parser.

QR="${HOME}/.claude/plugins/coordinator-claude/coordinator/bin/query-records.js"
if [ -d "${GIT_ROOT}/tasks/handoffs" ] && [ -f "$QR" ] && command -v node &>/dev/null; then
  # Find all consumed handoffs still in tasks/handoffs/
  consumed_paths=$(node "$QR" --type handoff --where "status=consumed" --format paths --root "$GIT_ROOT" 2>/dev/null || true)
  if [ -n "$consumed_paths" ]; then
    archive_dir="${GIT_ROOT}/archive/handoffs"
    mkdir -p "$archive_dir" 2>/dev/null || true

    while IFS= read -r fpath; do
      [ -z "$fpath" ] && continue

      # Extract consumed_by session id from frontmatter.
      # query-records.js has no --field flag, so we read the YAML line directly.
      # The frontmatter is bounded by --- delimiters; consumed_by is a single
      # scalar string written by /pickup, so a one-line grep is sufficient.
      consumed_sid=$(awk '/^---$/{n++; next} n==1' "$fpath" 2>/dev/null | grep -m1 '^consumed_by:' | sed 's/consumed_by:[[:space:]]*//' | tr -d '"' | tr -d "'" | xargs || true)
      [ -z "$consumed_sid" ] && continue

      # Check if the consuming session is alive.
      #
      # Sentinel-pulse mitigation (spec backlink:
      #   docs/plans/2026-05-17-ws2-channel-a-narrow-activation.md § Chunk 7):
      #
      # The PID recorded in meta.json is $$ of the cs_init hook subshell — dead
      # within seconds of session boot. kill -0 therefore always returns non-zero
      # for any session older than its launch instant; session_alive=true via PID
      # is structurally unreachable (the Staff Engineer review: lib/coordinator-session.sh:189).
      #
      # Fix: check last_activity recency first. session-heartbeat.sh writes
      # last_activity on every PreToolUse:Bash (throttled to 60s). If a session
      # is actively running a Bash command (e.g. a multi-minute extraction), its
      # last_activity will be recent. Treat any session with last_activity within
      # the last ALIVE_WINDOW_MINUTES minutes as live — skip archival.
      #
      # ALIVE_WINDOW_MINUTES=10: long enough to cover normal extraction/build runs
      # (UE source extract passes run 5-8 min); short enough to recover real
      # crashes promptly (a crash leaves last_activity frozen; after 10 min it
      # will be swept by the next session-init boot).
      sid_dir="${GIT_ROOT}/.git/coordinator-sessions/${consumed_sid}"
      session_alive=false
      ALIVE_WINDOW_MINUTES=10
      ALIVE_WINDOW_SECONDS=$(( ALIVE_WINDOW_MINUTES * 60 ))
      if [ -d "$sid_dir" ]; then
        # Primary liveness: last_activity recency (sentinel-pulse, Path B).
        # Read last_activity from meta.json via sed (avoids jq dependency on this path).
        sid_last_activity=$(sed -n 's/.*"last_activity"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
          "${sid_dir}/meta.json" 2>/dev/null | head -1 || true)
        if [ -n "$sid_last_activity" ]; then
          now_epoch=$(date +%s 2>/dev/null || echo 0)
          # ISO-8601 -> epoch: try GNU date, BSD date, python fallback
          last_epoch=$(date -u -d "$sid_last_activity" +%s 2>/dev/null) \
            || last_epoch=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$sid_last_activity" +%s 2>/dev/null) \
            || last_epoch=0
          if [ "$last_epoch" -eq 0 ]; then
            # Python fallback (Windows/portable)
            if command -v python3 &>/dev/null; then
              last_epoch=$(python3 -c "import datetime,sys; ts='${sid_last_activity%Z}'; print(int(datetime.datetime.fromisoformat(ts).replace(tzinfo=datetime.timezone.utc).timestamp()))" 2>/dev/null || echo 0)
            elif command -v python &>/dev/null; then
              last_epoch=$(python -c "import datetime,sys; ts='${sid_last_activity%Z}'; print(int(datetime.datetime.fromisoformat(ts).replace(tzinfo=datetime.timezone.utc).timestamp()))" 2>/dev/null || echo 0)
            fi
          fi
          inactive_for=$(( now_epoch - last_epoch ))
          if [ "$inactive_for" -lt "$ALIVE_WINDOW_SECONDS" ]; then
            session_alive=true  # recent last_activity — session is alive
          fi
        fi

        # Secondary liveness: PID check (kept as defense-in-depth for the rare
        # case where heartbeats did not fire — e.g. a session that only ran
        # Write/Edit tools and session-heartbeat.sh was not in hooks.json yet).
        if [ "$session_alive" != "true" ]; then
          sid_pid=$(sed -n 's/.*"pid"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
            "${sid_dir}/meta.json" 2>/dev/null | head -1 || true)
          if [ -n "$sid_pid" ] && kill -0 "$sid_pid" 2>/dev/null; then
            session_alive=true
          fi
        fi
      fi

      # Sanity: skip if session is still alive
      [ "$session_alive" = "true" ] && continue

      # Flip deployment_state: in_flight → abandoned before archival.
      # The consuming session died without /handoff or /session-end, so by
      # definition this handoff did not complete its workstream — leaving it
      # in_flight forever makes archived records look active to any query.
      # `abandoned` is the honest terminal: we don't know if work shipped on
      # the branch, only that closure ceremony never ran. If work did ship,
      # the commit log is authoritative; deployment_state is process-state.
      if grep -q '^deployment_state:[[:space:]]*in_flight' "$fpath" 2>/dev/null; then
        # In-place sed; portable form (works on both GNU sed and BSD sed via tmpfile)
        tmp_ds="${fpath}.ds.tmp.$$"
        sed 's/^deployment_state:[[:space:]]*in_flight.*/deployment_state: abandoned/' "$fpath" > "$tmp_ds" && mv "$tmp_ds" "$fpath"
      fi

      # Quietly archive (git mv stages both the rename and the in-place sed edit above)
      fname=$(basename "$fpath")
      git -C "$GIT_ROOT" mv "tasks/handoffs/${fname}" "archive/handoffs/${fname}" 2>/dev/null || true
      # Ensure the content modification at the new path is staged
      # (git mv stages the rename; modified content may need an explicit add)
      git -C "$GIT_ROOT" add "archive/handoffs/${fname}" 2>/dev/null || true
    done <<< "$consumed_paths"

    # Commit any moved files (only if git has staged changes from the mv above)
    # Plain-git explicit commit — do NOT use coordinator-safe-commit here (SC-DR-008, lessons.md:207)
    # The staged paths are exactly the git mv operations above; no additional staging needed.
    if git -C "$GIT_ROOT" diff --cached --quiet 2>/dev/null; then
      : # nothing staged — no commit needed
    else
      git -c commit.gpgsign=false -C "$GIT_ROOT" commit -m "session-init: archived orphaned handoff(s)" 2>/dev/null || true
    fi
  fi
fi

exit 0
