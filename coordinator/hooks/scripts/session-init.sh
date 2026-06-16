#!/bin/bash
# SessionStart hook: Initialize the coordinator session directory and write the
# .current-session-id sentinel so coordinator-safe-commit can resolve the
# session_id from a non-hook subprocess (the EM's interactive Bash).
#
# Primary mechanism update (2026-05-23): Claude Code (≥ ~2.1.150) now exports
# CLAUDE_CODE_SESSION_ID into every tool subprocess — the EM's interactive Bash
# AND dispatched subagents (which inherit the dispatching EM's id). The helpers'
# resolve_session_id prefers that env var; it is per-session and cannot be
# clobbered by a sibling session, so it is the authoritative source. The sentinel
# this hook writes is now a FALLBACK for older Claude Code (≤ 2.1.128 did not
# export the var). Keep writing it.
#
# Without env var AND without this hook, the helper has no path to the session_id:
#   - track-touched-files.sh creates session dirs only on the first Edit/Write,
#     so early-session helper invocations would fail.
#   - The PID-scan fallback is broken because cs_init records $$ (the hook
#     subprocess PID), which is dead by the time the helper runs.
#
# Concurrency note: the sentinel is "last writer wins". When two Claude Code
# sessions run in the same repo, the most recently started session owns the
# sentinel — which is why the env var (per-session, unclobberable) is preferred
# over it. On old Claude Code where only the sentinel exists, the helper's
# post-filter (touched.txt membership) still prevents foreign files from being
# staged even on sentinel collisions.
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

# --- Boot-time orphaned-git-lock sweep (best-effort, near-zero cost) ---
# Self-heal an orphaned `.git/index.lock` (etc.) left by a prior session's commit under
# concurrent-EM on Git-for-Windows, so this session doesn't hit "Unable to create
# '.../index.lock': File exists" on its first commit. The reaper removes ONLY aged + stable
# locks (never a fresh/in-flight one), and incurs no latency when no orphan exists.
# Spec: cross-repo/inbox/2026-05-30-index-lock-leak-concurrent-em.md; docs/wiki/concurrent-em-hazards.md § H21.
# Both helpers resolve the git dir from cwd, so pin cwd to the repo root (this hook's
# cwd is not guaranteed). Subshell keeps the cd local to each call.
_REAPER="$(dirname "${BASH_SOURCE[0]}")/../../bin/coordinator-reap-stale-locks"
[[ -x "$_REAPER" ]] && ( cd "$GIT_ROOT" && "$_REAPER" ) >/dev/null 2>&1 || true

# --- Idempotent git-config hardening (gc.autoDetach false) ---
# Ensures every coordinator-active repo has the production-reduction setting even if it was
# never formally onboarded — git's detached auto-maintenance is the orphaned-lock contributor.
# Idempotent and near-zero cost (a `git config --get`, plus one `--set` on first boot only).
_CFGGIT="$(dirname "${BASH_SOURCE[0]}")/../../bin/coordinator-configure-git"
[[ -x "$_CFGGIT" ]] && ( cd "$GIT_ROOT" && "$_CFGGIT" ) >/dev/null 2>&1 || true

# --- Idempotent post-commit auto-push hook install/repair ---
# The crash-insurance doctrine ("auto-push on every commit on work/* and feature/*") used to be
# install-time-only via /repo-setup § 3f.5. Repos that pre-date the doctrine, repos whose
# .git/hooks/ got wiped, and OSS users who clone without running /repo-setup all silently lost
# the safety net — commits succeed, no hook fires, work strands on local. This helper makes the
# install self-healing on every session boot, so the next opened session in any repo restores
# the hook. Idempotent and near-zero cost when already installed (one stat + one grep).
# Spec backlink: state/handoffs/2026-06-11_145955_auto-push-silent-failure-email-privacy.md.
_ENSURE_HOOK="$(dirname "${BASH_SOURCE[0]}")/../../bin/coordinator-ensure-post-commit-hook"
[[ -x "$_ENSURE_HOOK" ]] && ( cd "$GIT_ROOT" && "$_ENSURE_HOOK" ) >/dev/null 2>&1 || true

# --- Idempotent prepare-commit-msg Session-Id trailer hook install/repair ---
# Self-healing install of the prepare-commit-msg hook that appends Session-Id
# trailers — enables brightline gate --session-id filtering to scope commits
# to the current session on a shared-branch concurrent-EM work shape.
# Spec backlink: docs/plans/2026-06-15-brightline-session-scope-fix.md § C1, AC9.
_ENSURE_PCM_HOOK="$(dirname "${BASH_SOURCE[0]}")/../../bin/coordinator-ensure-prepare-commit-msg-hook"
[[ -x "$_ENSURE_PCM_HOOK" ]] && ( cd "$GIT_ROOT" && "$_ENSURE_PCM_HOOK" ) >/dev/null 2>&1 || true

# --- Boot-time EOL phantom-dirty index sweep (best-effort, idempotent, silent) ---
# Clear "phantom-dirty" entries where the index records a stale line-ending blob size while
# HEAD and the worktree already agree on normalized content — `git status` flags these ` M`
# forever and no `--refresh` / `core.checkStat minimal` clears them (the size differs). The
# sweep refreshes ONLY content-equal paths (ls-files-m minus real worktree-vs-index diffs), so
# it can never absorb a sibling's live edit or unstage their staged blob — safe on a shared
# tree. No-op (no index write) when the tree is clean, and defers if a live index.lock is present.
# This is the hook home for the cadence: every session start, every repo, instead of per-ceremony
# prose steps. ORDERING IS INTENTIONAL — the stale-lock reaper (above) runs FIRST so any orphan
# index.lock is cleared before this sweep's index.lock-present deferral check, and so the sweep
# does not pile a write onto a lock the reaper would have removed. The script self-skips (clean
# no-op) on bash < 4; this hook discards its output regardless via >/dev/null 2>&1 || true.
# Spec: docs/wiki/concurrent-em-hazards.md § H23.
_RENORM="$(dirname "${BASH_SOURCE[0]}")/../../bin/coordinator-renormalize-index"
[[ -x "$_RENORM" ]] && ( cd "$GIT_ROOT" && "$_RENORM" ) >/dev/null 2>&1 || true

# --- Source the lib and call cs_init for proper session-dir setup ---
LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
[[ ! -f "$LIB_PATH" ]] && LIB_PATH="${HOME}/.claude/plugins/coordinator/lib/coordinator-session.sh"

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
# This is what coordinator-safe-commit's Priority-3 resolution reads (the
# fallback below the CLAUDE_CODE_SESSION_ID env var, for old Claude Code).
echo "$SESSION_ID" > "${SESSIONS_DIR}/.current-session-id"

# --- Stop-watcher stale PID-lock sweep (best-effort, silent) ---
# C2d: sweep any stop-watcher.pid files left by crashed sessions. A lock file
# whose PID is no longer alive is an orphan — remove it so the next Stop event
# can acquire the lock and start a fresh watcher without being blocked by a
# ghost entry.  Live PIDs (sibling session's active watcher) are left alone.
# Spec backlink: docs/plans/2026-06-15-runtime-tripwire-idle-em-layered-fix.md § C2d.
for _sw_pid_file in "${SESSIONS_DIR}"/*/stop-watcher.pid; do
  [ -f "$_sw_pid_file" ] || continue
  _sw_pid=$(cat "$_sw_pid_file" 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$_sw_pid" ] && { rm -f "$_sw_pid_file" 2>/dev/null || true; continue; }
  kill -0 "$_sw_pid" 2>/dev/null || rm -f "$_sw_pid_file" 2>/dev/null || true
done
unset _sw_pid_file _sw_pid

# --- Periodic stale-session reaper (gated: at most once per 12h) ---
#
# cs_reap_stale archives sessions that are >24h inactive AND have a dead PID;
# cs_reap_agents bounds the .agents/ back-pointer index the same way. Without a
# caller these never ran, so session dirs accumulated unbounded — hundreds on a
# long-lived machine — and every cs_live_session_ids scan (safe-commit foreign-
# path check, agent-id union) degraded to tens of seconds.
#
# The reaper itself is an O(n) scan with a subprocess or two per dir, so we do
# NOT pay it on every boot: a marker file (.last-reap) gates it to roughly once
# per 12h. Most boots are a single stat of the marker; once per window we run the
# scan. Post-sweep the dir count stays small, so the gated run is cheap. The
# current session is never reaped (its last_activity is fresh). Best-effort —
# wrapped so it can never block or fail session start.
#
# Concurrent session-init firings within the same 12h window produce benign
# double-runs: the second mv fails ENOENT (file already archived), cs_archive
# returns 1, and cs_reap_stale silently skips the entry. No data loss, no
# double-archive. Review: code-reviewer — confirmed idempotent.
if command -v cs_reap_stale &>/dev/null; then
  REAP_MARKER="${SESSIONS_DIR}/.last-reap"
  REAP_INTERVAL=$(( 12 * 3600 ))
  _reap_now=$(date +%s 2>/dev/null || echo 0)
  _reap_last=0
  if [[ -f "$REAP_MARKER" ]]; then
    # Review: code-reviewer — fallback 0 is intentional: unknown mtime → treat
    # as epoch-0, so the gap always exceeds REAP_INTERVAL and the reaper fires.
    # "trigger reap" default, not "skip reap".
    _reap_last=$(stat -c %Y "$REAP_MARKER" 2>/dev/null || stat -f %m "$REAP_MARKER" 2>/dev/null || echo 0)
  fi
  if [[ "$_reap_now" -gt 0 && $(( _reap_now - _reap_last )) -ge "$REAP_INTERVAL" ]]; then
    cs_reap_stale  >/dev/null 2>&1 || true
    cs_reap_agents >/dev/null 2>&1 || true
    : > "$REAP_MARKER" 2>/dev/null || true
  fi
fi

# --- Orphan consumed-handoff sweep (spec backlink: tasks/split-pickup-archival/plan.md § Edit 7) ---
#
# Under the split-pickup-archival lifecycle, /pickup mutates frontmatter only
# (status: consumed, deployment_state: in_flight, consumed_by: <sid>). Archival
# to archive/handoffs/ happens at the terminal event: /handoff chain-archival or
# /workstream-complete Step 2.7. A handoff in state/handoffs/ with status: consumed is
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
# restart, crash-without-/workstream-complete. Recovery latency drops from "7 days" (reaper)
# to "next session start."
#
# Why query-records, not grep: per coordinator CLAUDE.md "Tripwire call-shape
# coverage" rule, raw grep misses quoted/whitespace variants. query-records uses
# the schema parser.

# --- Branch guard: never write or commit on main/master or detached HEAD ---
#
# This block performs git mv + git commit. If HEAD is main (common right after
# /merge-to-main) the cleanup would land on main, violating the read-only-main
# doctrine and causing sync-main.sh to abort on the next workday-start. Skip
# the orphan sweep when HEAD is not on a work branch — the next session that
# boots on a work/* (or named long-lived) branch will pick up the orphans.
#
# Empirical motivation: 2026-05-20, /workday-start aborted with "local main is
# 1 commit ahead of origin/main" pointing at a session-init archival commit.
INIT_BRANCH=$(git -C "$GIT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
case "$INIT_BRANCH" in
  main|master|HEAD|"")
    INIT_SKIP_SWEEP=1
    ;;
  archive/*)
    # archive/* branches are terminal/dead-work by naming convention; committing
    # archival entries there is noise. Skip the sweep — the next session on a
    # live work branch picks up any orphans.
    INIT_SKIP_SWEEP=1
    ;;
  *)
    INIT_SKIP_SWEEP=
    ;;
esac

QR="${HOME}/.claude/plugins/coordinator/bin/query-records.js"
if [ -z "$INIT_SKIP_SWEEP" ] && [ -d "${GIT_ROOT}/state/handoffs" ] && [ -f "$QR" ] && command -v node &>/dev/null; then
  # Find all consumed handoffs still in state/handoffs/
  consumed_paths=$(node "$QR" --type handoff --where "status=consumed" --format paths --root "$GIT_ROOT" 2>/dev/null || true)
  if [ -n "$consumed_paths" ]; then
    archive_dir="${GIT_ROOT}/archive/handoffs"
    mkdir -p "$archive_dir" 2>/dev/null || true
    # Source stamp lib once before the loop (C2b — orphan-sweep call site).
    # Spec: docs/plans/2026-06-15-shipped-in-archive-stamping.md § C2b.
    # Review: F10 — resolve lib relative to this hook before falling back to ~/.claude
    # shellcheck source=../../lib/coordinator-archive-stamp.sh
    STAMP_LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-archive-stamp.sh"
    [[ ! -f "$STAMP_LIB_PATH" ]] && STAMP_LIB_PATH="${HOME}/.claude/plugins/coordinator/lib/coordinator-archive-stamp.sh"
    [[ -f "$STAMP_LIB_PATH" ]] && source "$STAMP_LIB_PATH"

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
      # within seconds of session open. kill -0 therefore always returns non-zero
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
            # Python fallback (Windows/portable) — use env-var pattern to avoid
            # shell-interpolation injection via sid_last_activity value.
            # Review: code-reviewer — mirrors lib's env-var pattern.
            if command -v python3 &>/dev/null; then
              last_epoch=$(CS_ISO_TS="${sid_last_activity%Z}" bash "$(dirname "${BASH_SOURCE[0]}")/../../lib/spawn-hidden.sh" --stdin-mode=safe python3 -c "import os,datetime; print(int(datetime.datetime.fromisoformat(os.environ['CS_ISO_TS']).replace(tzinfo=datetime.timezone.utc).timestamp()))" 2>/dev/null || echo 0)
            elif command -v python &>/dev/null; then
              last_epoch=$(CS_ISO_TS="${sid_last_activity%Z}" bash "$(dirname "${BASH_SOURCE[0]}")/../../lib/spawn-hidden.sh" --stdin-mode=safe python -c "import os,datetime; print(int(datetime.datetime.fromisoformat(os.environ['CS_ISO_TS']).replace(tzinfo=datetime.timezone.utc).timestamp()))" 2>/dev/null || echo 0)
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
      # The consuming session died without /handoff or /workstream-complete, so by
      # definition this handoff did not complete its workstream — leaving it
      # in_flight forever makes archived records look active to any query.
      # `abandoned` is the honest terminal: we don't know if work shipped on
      # the branch, only that closure ceremony never ran. If work did ship,
      # the commit log is authoritative; deployment_state is process-state.
      if grep -q '^deployment_state:[[:space:]]*in_flight' "$fpath" 2>/dev/null; then
        # In-place sed; portable form (works on both GNU sed and BSD sed via tmpfile)
        tmp_ds="${fpath}.ds.tmp.$$"
        sed 's/^deployment_state:[[:space:]]*in_flight.*/deployment_state: abandoned/' "$fpath" > "$tmp_ds" && mv "$tmp_ds" "$fpath" || rm -f "$tmp_ds"
      fi

      # Stamp shipped_in: before archival — no branch-tip fallback (the Staff Engineer F1).
      # The orphan case: we don't know if work shipped on the branch; the branch
      # tip is overwhelmingly a sibling workstream's commit. If scope-paths yield
      # no commit, shipped_in: is left absent — misattribution is worse than omission.
      # DO NOT pass --allow-branch-tip-fallback here.
      # Review: F11 — guard against stamp_shipped_in not being defined (lib source may have failed)
      command -v stamp_shipped_in &>/dev/null && stamp_shipped_in "$fpath" || true

      # Quietly archive (git mv stages both the rename and the in-place sed edit above)
      fname=$(basename "$fpath")
      git -C "$GIT_ROOT" mv "state/handoffs/${fname}" "archive/handoffs/${fname}" 2>/dev/null || true
      # Ensure the content modification at the new path is staged
      # (git mv stages the rename; modified content may need an explicit add)
      git -C "$GIT_ROOT" add "archive/handoffs/${fname}" 2>/dev/null || true

      # Per-archive WARN marker — workday-start Step 0.8 consumes this list to
      # surface stale-executing plans whose driving handoff was archived without
      # ceremony. The marker is append-only; workday-start rotates it after read.
      # Spec backlink: state/coordinator-improvement-queue.md (2026-05-16, session-init
      # orphan-sweep workstream-end ceremony).
      marker_dir="${GIT_ROOT}/tasks"
      mkdir -p "$marker_dir" 2>/dev/null || true
      marker_file="${marker_dir}/orphan-sweep-notes.md"
      if [ ! -f "$marker_file" ]; then
        printf '# Orphan sweep notes\n\nArchive events from session-init.sh. /workday-start Step 0.8 reads and rotates.\n\n' > "$marker_file"
      fi
      printf -- '- %s | archived %s (consumed_by=%s, deployment_state flipped to abandoned)\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$fname" "$consumed_sid" >> "$marker_file"
      git -C "$GIT_ROOT" add "tasks/orphan-sweep-notes.md" 2>/dev/null || true
    done <<< "$consumed_paths"

    # Commit any moved files (only if git has staged changes from the mv above)
    # Plain-git explicit commit — do NOT use coordinator-safe-commit here (SC-DR-008, lessons.md:207)
    # The staged paths are exactly the git mv operations above; no additional staging needed.
    if git -C "$GIT_ROOT" diff --cached --quiet 2>/dev/null; then
      : # nothing staged — no commit needed
    else
      # gpgsign=false is DELIBERATE here (not a block-no-verify violation): this is a
      # best-effort orphan-archival commit from a TTY-less SessionStart hook. A
      # passphrase-protected signing key would hang the hook with no prompt to answer,
      # so signing is disabled for this internal housekeeping commit only. block-no-verify
      # guards EM-issued Bash commits, not hook-internal subprocess commits.
      git -c commit.gpgsign=false -C "$GIT_ROOT" commit -m "session-init: archived orphaned handoff(s)" -- state/handoffs/ archive/handoffs/ tasks/orphan-sweep-notes.md 2>/dev/null || true
    fi
  fi
fi

exit 0
