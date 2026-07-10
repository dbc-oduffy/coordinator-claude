#!/usr/bin/env bash
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
if command -v timeout >/dev/null 2>&1; then
  INPUT=$(timeout 2 cat 2>/dev/null || true)
else
  INPUT=$(cat)
fi

[[ -z "$INPUT" ]] && exit 0

# --- Extract session_id (prefer jq, fall back to bash string ops) ---
if command -v jq >/dev/null 2>&1; then
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

# --- Pointer self-heal: (re)project ~/.claude/.doe-root if absent but registry is set ---
# Lifecycle decoupling: coordinator source ships via git pull (source_is_live, --plugin-dir),
# so ~/.claude/.doe-root can be absent on a machine that ran git pull without re-running the
# installer. (Re)project from the registry idempotently here, BEFORE any coordinator lib is
# sourced via the pointer — so that migrated inline fallbacks (C3) never encounter a
# pointer-miss on a post-pull boot. gen-doe-root-pointer.sh is atomic, idempotent, and
# handles the "registry unset" case internally (exits non-zero, which we suppress).
# Non-maximalist installs (repos.doe_claude unset) exit non-zero silently; the hook
# always exits 0. Resolved via BASH_SOURCE — same resolution pattern as all helpers below.
# Spec backlink: docs/plans/2026-07-04-coordinator-maximalist-install-shape.md § C1 / AC12
_doe_ptr_file="${CLAUDE_HOME:-$HOME}/.claude/.doe-root"
if [ ! -f "$_doe_ptr_file" ]; then
  _doe_gen_ptr="$(dirname "${BASH_SOURCE[0]}")/../../bin/gen-doe-root-pointer.sh"
  if [ -f "$_doe_gen_ptr" ]; then
    bash "$_doe_gen_ptr" >/dev/null 2>&1 || true
  fi
fi
unset _doe_ptr_file _doe_gen_ptr

# --- Shim self-heal: reseed ~/.claude/bin/resolve-coordinator-clone from the template ---
# The bin-shim is the fixed cold entry point out-of-tree consumers (project-rag / ue-addon /
# example-game-repo) call to LOCATE the resolver lib. Under maximalist it MUST carry the .doe-root
# bootstrap tier; a machine installed before that tier landed (or that ran git pull without
# re-running the installer) has a stale shim that fails cold once the flat tree is gone. Reseed
# idempotently from the coordinator-owned template (byte-identical by design) whenever the
# installed copy is absent or differs — atomic tmp+mv so a concurrent consumer never reads a
# half-written shim. Same lifecycle-decoupling rationale as the pointer self-heal above.
# Spec backlink: docs/plans/2026-07-04-coordinator-maximalist-install-shape.md § C3-binshim (row #13)
_shim_tmpl="$(dirname "${BASH_SOURCE[0]}")/../../templates/bin/resolve-coordinator-clone"
_shim_dst="${CLAUDE_HOME:-$HOME}/.claude/bin/resolve-coordinator-clone"
if [ -f "$_shim_tmpl" ] && ! cmp -s "$_shim_tmpl" "$_shim_dst" 2>/dev/null; then
  mkdir -p "$(dirname "$_shim_dst")" 2>/dev/null || true
  if cp "$_shim_tmpl" "$_shim_dst.tmp.$$" 2>/dev/null && chmod +x "$_shim_dst.tmp.$$" 2>/dev/null; then
    mv -f "$_shim_dst.tmp.$$" "$_shim_dst" 2>/dev/null || rm -f "$_shim_dst.tmp.$$" 2>/dev/null || true
  else
    rm -f "$_shim_dst.tmp.$$" 2>/dev/null || true
  fi
fi
unset _shim_tmpl _shim_dst

# Source state-root seam and resolve per-repo state root + state-hosting repo root.
# L1 fix: git -C "$GIT_ROOT" mv on state/handoffs/ → git -C "$_STATE_REPO" mv, so
#   archival targets example-orchestration-hub when GIT_ROOT is the meta-repo; sibling repos unchanged.
# L9 fix: sweep-shipped-handoffs.sh runs with cd "$_STATE_REPO" for the same reason.
# Spec backlink: docs/plans/2026-07-03-stop-the-rot-example-orchestration-hub-state-home-placement.md § C4/AC4
_csr_lib_si="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-state-root.sh"
[[ -f "$_csr_lib_si" ]] && source "$_csr_lib_si" 2>/dev/null || true
_STATE_ROOT="$(coordinator_state_root 2>/dev/null)" || _STATE_ROOT="${GIT_ROOT}/state"
_STATE_REPO="$(dirname "$_STATE_ROOT")"

# state_common_dir — the STATE-hosting repo's `.git` common dir, passed to
# sweep-boot.sh (session.boot_sweep) so the native op can route handoff-family
# archival to the STATE worktree while orphan-sweep-notes.md + plans + memos
# stay on GIT_ROOT. Symmetric with _STATE_REPO (a worktree root); the common
# dir is what the op's main_worktree_root() derivation expects (memo item 2).
# Unified-state case (_STATE_REPO == GIT_ROOT): resolves to GIT_ROOT/.git,
# which is Path.resolve()-equal to GIT_ROOT's own common dir — the op's
# documented fallback collapses this to identical single-commit behavior, so
# no separate empty-string branch is needed here.
# Spec backlink: cross-repo/inbox/2026-07-07-gap6-gpgsign-landed-boot-sweep-two-repo-split.md item 2
_STATE_COMMON_DIR="$(git -C "$_STATE_REPO" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" \
  || _STATE_COMMON_DIR="$(git -C "$_STATE_REPO" rev-parse --git-common-dir 2>/dev/null)" \
  || _STATE_COMMON_DIR=""
# --path-format=absolute (git >=2.31) prints an absolute path directly; older
# git prints a path relative to cwd (usually just ".git") — normalize that
# fallback case to absolute so the op receives a stable, cwd-independent path.
if [[ -n "$_STATE_COMMON_DIR" && "$_STATE_COMMON_DIR" != /* ]]; then
  _STATE_COMMON_DIR="$(cd "$_STATE_REPO" && cd "$_STATE_COMMON_DIR" 2>/dev/null && pwd)" || _STATE_COMMON_DIR=""
fi
# Breadcrumb only — does NOT change behavior/branching. On a genuine two-repo
# (example-orchestration-hub meta-repo) layout, an unexpected empty _STATE_COMMON_DIR would
# silently sweep shipped handoffs against GIT_ROOT instead of the STATE repo
# with no diagnostic; this makes that mis-configuration debuggable. Written
# inline (not via $_cc_degrade_log, which is not defined until later in this
# file) to the same sentinel path _cc_degrade_log resolves to below.
# Review: the Staff Engineer — nitpick applied (2026-07-08).
if [[ -z "$_STATE_COMMON_DIR" && "$_STATE_REPO" != "$GIT_ROOT" ]]; then
  {
    mkdir -p "${GIT_ROOT}/.git/coordinator-sessions" 2>/dev/null
    echo "WARN: state_common_dir empty on split layout — shipped-handoff sweep will target GIT_ROOT" \
      >> "${GIT_ROOT}/.git/coordinator-sessions/sessionstart-degrade.log"
  } 2>/dev/null || true
fi

SESSIONS_DIR="${GIT_ROOT}/.git/coordinator-sessions"
mkdir -p "$SESSIONS_DIR" 2>/dev/null || exit 0

# --- Async hook failure read-back (spec: docs/plans/2026-06-30-async-hook-failure-surfacing.md § Wiring) ---
# Surface any load-bearing async hook failures recorded by async producers since last boot,
# then atomically clear them so they don't re-nag on the following session.
# This is the ONLY correct read-back point: session-init.sh is a SYNC hook (async:false),
# so its stdout reliably reaches the operator; async hooks cannot be read from.
# Wrapped in a compound-command+|| true so no failure here can violate the always-exit-0 contract.
# BASH_SOURCE-relative primary (mirrors existing lib resolution pattern); CLAUDE_PLUGIN_ROOT/HOME fallback.
{
  _ahs_helper="$(dirname "${BASH_SOURCE[0]}")/../../lib/async-hook-status.sh"
  # Review: code-reviewer Slice-B F5 — CLAUDE_PLUGIN_ROOT is set by bootstrap-substrate.sh during
  # --setup-only install (first marketplace-install boot); CLAUDE_HOME fallback covers meta-repo
  # dev installs where bootstrap-substrate.sh has already run. Fallback fires when BASH_SOURCE
  # resolution above produced a path that does not yet exist on this machine.
  if [[ ! -f "$_ahs_helper" ]]; then
    # Guard fires ONLY on this CLAUDE_PLUGIN_ROOT-derived fallback reassignment,
    # never on the BASH_SOURCE-relative primary above (which legitimately
    # contains a `/..` sibling-hop and would false-reject under the shared
    # guard's traversal check) — promoted to coordinator_trusted_root_guard,
    # Variant B / fail-open (advisory hook, must never hard-exit).
    # Spec backlink: docs/plans/2026-07-09-resolver-unification-v3split-01.md § C5
    _ahs_helper="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}/lib/async-hook-status.sh"
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
    if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
      coordinator_trusted_root_guard --mode=fail-open --root="$_ahs_helper" --site="$0" || _ahs_helper=''
    else
      _ahs_helper=''
    fi
  fi
  if [[ -f "$_ahs_helper" ]]; then
    # shellcheck source=/dev/null
    source "$_ahs_helper"
    command -v ahs_surface_and_clear >/dev/null 2>&1 && ahs_surface_and_clear
  else
    echo "async-hook-status helper not found — failure surfacing skipped" >&2
  fi
} || true

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

# Resolve coordinator root once for library fallback lookups (soft-degrade: _cc_root=""
# on .doe-root miss — hook always exits 0, never hard-fails on missing libs).
# Guard promoted to the shared coordinator_trusted_root_guard function —
# Variant B / fail-open, since this is an advisory SessionStart hook that must
# never hard-exit the hook chain. See coordinator/lib/coordinator-trusted-root-guard.sh.
# Spec backlink: docs/plans/2026-07-09-resolver-unification-v3split-01.md § C5
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-trusted-root-guard.sh" 2>/dev/null || true
if command -v coordinator_trusted_root_guard >/dev/null 2>&1; then
  coordinator_trusted_root_guard --mode=fail-open --root="$_cc_root" --site="$0" || _cc_root=''
else
  _cc_root=''
fi
[ -d "$_cc_root" ] || _cc_root=""

# --- Source the lib and call cs_init for proper session-dir setup ---
LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-session.sh"
[[ ! -f "$LIB_PATH" && -n "$_cc_root" ]] && LIB_PATH="${_cc_root}/lib/coordinator-session.sh"

if [[ -f "$LIB_PATH" ]]; then
  # shellcheck source=/dev/null
  source "$LIB_PATH"
  cs_init "$SESSION_ID" 2>/dev/null || true
else
  # Lib missing — minimal session-dir bootstrap (mirror track-touched-files.sh)
  SESSION_DIR="${SESSIONS_DIR}/${SESSION_ID}"
  mkdir -p "$SESSION_DIR" 2>/dev/null || exit 0
  touch "${SESSION_DIR}/touched.txt"
  [[ ! -f "${SESSION_DIR}/started_at" ]] && date -u +"%Y-%m-%dT%H:%M:%SZ" > "${SESSION_DIR}/started_at"
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

# --- Periodic stale-session reaper (delegated to reap-sessions.sh) ---
#
# cs_reap_stale archives sessions that are >24h inactive AND have a dead PID;
# cs_reap_agents bounds the .agents/ back-pointer index the same way. Without a
# caller these never ran, so session dirs accumulated unbounded — hundreds on a
# long-lived machine — and every cs_live_session_ids scan (safe-commit foreign-
# path check, agent-id union) degraded to tens of seconds.
#
# Stale-session cleanup is now delegated to reap-sessions.sh, which routes
# through the coordinator_core session.reap op on the native path (strangle_route_mutation)
# or the cs_reap_* trio on the legacy path. The 12h .last-reap cadence gate is now
# internal to the op / the wrapper's legacy path — session-init no longer owns
# REAP_MARKER / REAP_INTERVAL / _reap_now / _reap_last. Best-effort: reap-sessions.sh
# always exits 0, so this block never blocks session start.
#
# Spec backlink: docs/plans/2026-07-06-session-init-op-absorption-repoint.md § C2 / KD-5
#
# _cc_degrade_log: untracked diagnostic sink for cc_invoke stderr from the two
# best-effort cc_invoke-invoking calls below (reap-sessions, sweep-terminal-plans).
# Both calls previously suppressed stderr entirely (2>/dev/null), so a timeout or
# op-partial-failure degraded silently with no trace. Redirecting to this log
# surfaces degradation for post-hoc diagnosis without adding terminal noise on the
# normal (fast, silent) SessionStart path — nothing is written here unless one of
# the two calls actually emits stderr. Append-mode (>>) below is deliberate — the
# log accumulates across boots until manually inspected/cleared, not reset per-boot;
# the size cap immediately below bounds that accumulation.
# Review: code-reviewer — F1: bound unbounded append-only growth with a size cap;
# F6: document the append-mode (>>) choice explicitly.
_cc_degrade_log="${GIT_ROOT}/.git/coordinator-sessions/sessionstart-degrade.log"
mkdir -p "$(dirname "$_cc_degrade_log")" 2>/dev/null || true
[ -f "$_cc_degrade_log" ] && [ "$(wc -c < "$_cc_degrade_log" 2>/dev/null || echo 0)" -gt 524288 ] && : > "$_cc_degrade_log"
_reap_script="$(dirname "${BASH_SOURCE[0]}")/../../bin/reap-sessions.sh"
if [[ -f "$_reap_script" ]]; then
  # CC_INVOKE_TIMEOUT_SECS=3: cap per cc_invoke call at 3s (default is 10s).
  # Worst-case cc_invoke budget: 3×3=9s; additional subprocess startup adds ~0.5–1s
  # per script (bash init, plugin-root resolution, _sf_seam_present probe). Monitor
  # if SessionStart smoke ceiling is regularly breached.
  # Review: code-reviewer — nit: original 9s estimate excluded subprocess-launch overhead
  CC_INVOKE_TIMEOUT_SECS=3 bash "$_reap_script" "$GIT_ROOT" 2>>"$_cc_degrade_log" || true
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

# Resolve coordinator content root for query-records.js — use the shared resolver
# so fleet/cached installs work without ~/.claude/plugins being present.
# Sourced (no args): sets COORDINATOR_CONTENT_ROOT in this scope (empty if unresolved).
# Spec backlink: docs/plans/2026-06-23-coordinator-install-surface-dogfood-hardening.md § C2b
_RCC_LIB="$(dirname "${BASH_SOURCE[0]}")/../../lib/resolve-coordinator-clone.sh"
# shellcheck source=/dev/null
[[ -f "$_RCC_LIB" ]] && source "$_RCC_LIB"

# BASH_SOURCE-relative primary → resolver-based secondary → last-ditch flat fallback
QR="$(dirname "${BASH_SOURCE[0]}")/../../bin/query-records.js"
if [[ ! -f "$QR" ]]; then
  QR="${COORDINATOR_CONTENT_ROOT:-${HOME}/.claude/plugins/coordinator-claude/coordinator}/bin/query-records.js"
fi
if [ -z "$INIT_SKIP_SWEEP" ] && [ -d "${_STATE_ROOT}/handoffs" ] && [ -f "$QR" ] && command -v node >/dev/null 2>&1; then
  # Find all consumed handoffs still in state/handoffs/
  consumed_paths=$(node "$QR" --type handoff --where "status=consumed" --format paths --root "$GIT_ROOT" 2>/dev/null || true)
  if [ -n "$consumed_paths" ]; then
    archive_dir="${_STATE_REPO}/archive/handoffs"
    mkdir -p "$archive_dir" 2>/dev/null || true
    # Source stamp lib once before the loop (C2b — orphan-sweep call site).
    # Spec: archive/completed/2026-06/2026-06-15-shipped-in-archive-stamping-a62b94.md § C2b.
    # Review: F10 — resolve lib relative to this hook before falling back to ~/.claude
    # shellcheck source=../../lib/coordinator-archive-stamp.sh
    STAMP_LIB_PATH="$(dirname "${BASH_SOURCE[0]}")/../../lib/coordinator-archive-stamp.sh"
    [[ ! -f "$STAMP_LIB_PATH" && -n "$_cc_root" ]] && STAMP_LIB_PATH="${_cc_root}/lib/coordinator-archive-stamp.sh"
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
      # Delegates to the canonical liveness predicate _cs_session_live from
      # lib/coordinator-session.sh (see the lib source block above). That function uses a
      # 30-minute last_activity window — the documented single source of truth for
      # session liveness across the claim layer, the reaper, and this sweep.
      #
      # The old inline predicate used ALIVE_WINDOW_MINUTES=10 and fell back to a
      # kill -0 PID check. Both are now removed:
      #   - 10m was too short: a live session idle >10 min between tool calls (e.g.
      #     waiting on a backgrounded task) was falsely marked abandoned and its
      #     in-flight handoff clobbered (real incident: 2026-06-24, ~13.5 min idle).
      #   - kill -0 against the recorded pid is structurally useless: meta.json's pid
      #     is $$ of the cs_init hook subshell, dead within seconds of session open.
      #
      # cwd discipline: _cs_session_live calls _cs_session_dir → _cs_sessions_dir →
      # _cs_git_root (git rev-parse --show-toplevel), which is cwd-relative. A
      # SessionStart hook's cwd is arbitrary — pin it to $GIT_ROOT via subshell so
      # the internal resolution always targets the right repo.
      #
      # NEGATIVE-SPEC: last_activity does NOT refresh while a live session merely
      # WAITS on a backgrounded task or user input — a session idle >30 min between
      # tool calls can still be falsely swept. The consumed_at recency floor below
      # and the conservative lib-unavailable fallback narrow this window. The 24h
      # cs_reap_stale reaper is the ultimate backstop for any residual false-negatives
      # (false-negatives = keeping a file in state/ too long, not clobbering live work).
      session_alive=false
      if command -v _cs_session_live >/dev/null 2>&1; then
        ( cd "$GIT_ROOT" && _cs_session_live "$consumed_sid" ) && session_alive=true || session_alive=false
      else
        # lib unavailable → bias to life; never eagerly abandon without the canonical check
        session_alive=true
      fi

      # Sanity: skip if session is still alive
      [ "$session_alive" = "true" ] && continue

      # consumed_at recency floor (belt against false-abandon of just-claimed handoffs).
      #
      # A just-consumed handoff's session is almost certainly live and simply hasn't
      # heartbeated yet. If consumed_at is within the last 30 minutes, skip archival
      # even if _cs_session_live returned false (the heartbeat may not have fired yet,
      # or the session dir may not yet exist on this machine). The 24h cs_reap_stale
      # reaper is the backstop for any handoff this floor shields that is genuinely orphaned.
      consumed_at_raw=$(awk '/^---$/{n++; next} n==1' "$fpath" 2>/dev/null | grep -m1 '^consumed_at:' | sed 's/consumed_at:[[:space:]]*//' | tr -d '"' | tr -d "'" | xargs || true)
      if [ -n "$consumed_at_raw" ]; then
        _cat_now=$(date +%s 2>/dev/null || echo 0)
        # ISO-8601 → epoch: try GNU date, BSD date (macOS), python fallback via spawn-hidden.sh
        _cat_epoch=$(date -u -d "$consumed_at_raw" +%s 2>/dev/null) \
          || _cat_epoch=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$consumed_at_raw" +%s 2>/dev/null) \
          || _cat_epoch=0
        if [ "$_cat_epoch" -eq 0 ]; then
          # Python fallback — env-var pattern avoids shell-interpolation injection (mirrors
          # the existing last_activity ISO parse above, uses same spawn-hidden.sh wrapper).
          # popup-safe-env-suppressed
          _spawn_hidden="$(dirname "${BASH_SOURCE[0]}")/../../lib/spawn-hidden.sh"
          if command -v python3 >/dev/null 2>&1 && [ -f "$_spawn_hidden" ]; then
            _cat_epoch=$(CS_ISO_TS="${consumed_at_raw%Z}" bash "$_spawn_hidden" --stdin-mode=safe python3 -c "import os,datetime; print(int(datetime.datetime.fromisoformat(os.environ['CS_ISO_TS']).replace(tzinfo=datetime.timezone.utc).timestamp()))" 2>/dev/null || echo 0)
          elif command -v python >/dev/null 2>&1 && [ -f "$_spawn_hidden" ]; then
            _cat_epoch=$(CS_ISO_TS="${consumed_at_raw%Z}" bash "$_spawn_hidden" --stdin-mode=safe python -c "import os,datetime; print(int(datetime.datetime.fromisoformat(os.environ['CS_ISO_TS']).replace(tzinfo=datetime.timezone.utc).timestamp()))" 2>/dev/null || echo 0)
          fi
        fi
        # Treat unparseable/absent epoch as "old" (0) — does NOT block sweeping genuinely old orphans.
        # Only skip when epoch is fresh (>0 and within 30 min).
        if [ "$_cat_epoch" -gt 0 ] && [ "$(( _cat_now - _cat_epoch ))" -lt "$(( 30 * 60 ))" ]; then
          continue  # just consumed — session almost certainly live, heartbeat hasn't fired yet
        fi
      fi

      # has-other-live-children guard: skip archival if this handoff is still named
      # as predecessor/additional_predecessors/forked_from by another live handoff.
      # Fail-closed: the wrapper itself exits 0 on any internal error (do-not-archive).
      # Best-effort: if the wrapper is missing, fall through to old archival behavior.
      # Spec backlink: docs/plans/2026-06-29-handoff-lineage-dag-fan-in-fan-out.md § C4a
      _hlc_script="$(dirname "${BASH_SOURCE[0]}")/../../bin/handoff-has-live-children.sh"
      if [[ -f "$_hlc_script" ]]; then
        # Guard archival-caller contract (handoff-has-live-children.sh:10-18): ONLY exit 1
        # means safe-to-archive. exit 0 = has-live-children; exit 2 = indeterminate/internal
        # error — BOTH fail-closed (defer archival). Under command-type coordinator_core,
        # version skew is impossible (fresh process, current source each call); exit 3 is
        # retired with the UDS transport (DR-215).
        # A bare `if bash ...; then continue; fi` deferred only on exit 0, letting exit 2
        # fall through to git-mv — a fail-OPEN bug that could archive a live merge-parent
        # during a guard error (orphaning children). Capture the code and
        # defer on anything ≠ 1, matching coordinator-handoff-archive.sh:251-259.
        _hlc_rc=0
        bash "$_hlc_script" "$fpath" >/dev/null 2>&1 || _hlc_rc=$?
        if [[ "$_hlc_rc" -ne 1 ]]; then
          # exit 0/2 (or any non-1) = do-not-archive → defer
          continue
        fi
        # exit 1 = safe-to-archive → proceed with archival below
      fi

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
      command -v stamp_shipped_in >/dev/null 2>&1 && stamp_shipped_in "$fpath" || true

      # Quietly archive (git mv stages both the rename and the in-place sed edit above).
      # L1 fix: use _STATE_REPO (not GIT_ROOT) so archival lands in the correct repo
      # (example-orchestration-hub when GIT_ROOT is the meta-repo; GIT_ROOT itself for sibling repos).
      fname=$(basename "$fpath")
      git -C "$_STATE_REPO" mv "state/handoffs/${fname}" "archive/handoffs/${fname}" 2>/dev/null || true
      # Ensure the content modification at the new path is staged
      # (git mv stages the rename; modified content may need an explicit add)
      git -C "$_STATE_REPO" add "archive/handoffs/${fname}" 2>/dev/null || true

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

    # Commit any moved files (only if git has staged changes from the mv above).
    # Plain-git explicit commit — do NOT use coordinator-safe-commit here (SC-DR-008, lessons.md:207)
    # L1 fix: split into two scoped commits because state/handoffs + archive/handoffs now live in
    # _STATE_REPO (which is example-orchestration-hub when GIT_ROOT is the meta-repo) while tasks/orphan-sweep-notes.md
    # always lives in GIT_ROOT. When _STATE_REPO == GIT_ROOT (sibling repo), both commits target the
    # same repo — git ignores a commit with nothing staged, so the split is always safe.
    # gpgsign=false is DELIBERATE: TTY-less SessionStart hook, passphrase key would hang.
    if ! git -C "$_STATE_REPO" diff --cached --quiet -- state/handoffs/ archive/handoffs/ 2>/dev/null; then
      git -c commit.gpgsign=false -C "$_STATE_REPO" commit \
        -m "session-init: archived orphaned handoff(s)" \
        -- state/handoffs/ archive/handoffs/ 2>/dev/null || true
    fi
    if ! git -C "$GIT_ROOT" diff --cached --quiet -- tasks/orphan-sweep-notes.md 2>/dev/null; then
      git -c commit.gpgsign=false -C "$GIT_ROOT" commit \
        -m "session-init: archived orphaned handoff(s) [sweep-notes]" \
        -- tasks/orphan-sweep-notes.md 2>/dev/null || true
    fi
  fi
fi

# --- Boot sweep: actioned-memo + terminal-plan + shipped-handoff (spec backlinks:
#       state/handoffs/2026-06-22_232810_unified-terminal-artifact-archival-sweep.md
#       cross-repo/inbox/2026-07-07-gap6-gpgsign-landed-boot-sweep-two-repo-split.md) ---
#
# These three archival classes (actioned memos in cross-repo/inbox/, terminal plans
# in docs/plans/, shipped handoffs in state/handoffs/) are routed through the
# session.boot_sweep strangler wrapper (sweep-boot.sh) instead of three separate
# inline bash blocks. This retires the legacy meta-repo 4-sweep bash fallback that
# used to live here (each class re-implemented its own cc_invoke/legacy branching
# inline) — sweep-boot.sh already encodes the same three-state routing in one
# reusable wrapper (landed C2/0578ef6, cutover wired here). Consumed-handoff sweep
# (above) is NOT part of this call — sweep-boot.sh has no lib-level equivalent for
# it (documented seam limitation, AC9) and stays as session-init's own inline block.
#
# state_common_dir: _STATE_COMMON_DIR (computed above) is forwarded so the native
# op can route handoff-family archival (shipped handoffs) to the STATE worktree
# while plans + memos stay on GIT_ROOT, per the two-repo-split param contract.
# Unified-state repos (sibling checkouts) pass a value that resolves identically
# to GIT_ROOT's own common dir — op-side fallback collapses to prior behavior.
#
# Commit ownership:
#   Native path: session.boot_sweep self-commits all archival classes internally —
#     the diff --cached guard below is then a no-op (nothing left staged).
#   Legacy path (State 1, seam absent): sweep-boot.sh's _legacy_sweep_boot calls the
#     same sub-sweeps (cs_sweep_actioned_memos, sweep-terminal-plans.sh,
#     sweep-shipped-handoffs.sh) that used to be invoked inline here — they stage
#     but do not self-commit, so the commit below covers that path. Two scoped
#     commits (STATE-repo handoffs, then GIT_ROOT plans/memos) mirror the same
#     split used by the orphan-consumed-handoff sweep above.
#
# INIT_SKIP_SWEEP (computed in the branch guard above) is honored as an outer
# guard here — sweep-boot.sh does not self-skip (parity with sweep-terminal-plans.sh).
if [ -z "$INIT_SKIP_SWEEP" ]; then
  _sweep_boot_script="$(dirname "${BASH_SOURCE[0]}")/../../bin/sweep-boot.sh"
  if [[ -f "$_sweep_boot_script" ]]; then
    # CC_INVOKE_TIMEOUT_SECS=3: same per-call cap as reap-sessions/terminal-plan
    # sweeps above; the native path makes a single session.boot_sweep call.
    CC_INVOKE_TIMEOUT_SECS=3 bash "$_sweep_boot_script" "$GIT_ROOT" "$_STATE_COMMON_DIR" \
      >/dev/null 2>>"$_cc_degrade_log" || true

    # Legacy-path fallback commit — a no-op on the native path (op self-commits,
    # nothing left staged). Scoped exactly as the pre-cutover inline commits were.
    if ! git -C "$_STATE_REPO" diff --cached --quiet -- state/handoffs/ archive/handoffs/ 2>/dev/null; then
      # gpgsign=false: same TTY-less SessionStart-hook rationale as the orphan-handoff-sweep
      # commit above — a passphrase-protected signing key would hang the hook.
      git -c commit.gpgsign=false -C "$_STATE_REPO" commit \
        -m "session-init: archived shipped handoff(s)" \
        -- state/handoffs/ archive/handoffs/ 2>/dev/null || true
    fi
    if ! git -C "$GIT_ROOT" diff --cached --quiet -- cross-repo/inbox/ cross-repo/archive/ docs/plans/ archive/specs/ 2>/dev/null; then
      # Per-class granularity in the message (restored, Review: the Staff Engineer minor 2026-07-08):
      # the combined fallback commit used to say only "actioned memo(s)/terminal
      # plan(s)" regardless of which class(es) actually moved, losing per-class
      # count for git-log archaeology. Detect each class independently and name
      # only the one(s) that staged something; legacy path only (native path's
      # self-commit messages are example-orchestration-hub-owned, untouched).
      _si_moved_classes=()
      git -C "$GIT_ROOT" diff --cached --quiet -- cross-repo/inbox/ cross-repo/archive/ 2>/dev/null \
        || _si_moved_classes+=("memo(s)")
      git -C "$GIT_ROOT" diff --cached --quiet -- docs/plans/ archive/specs/ 2>/dev/null \
        || _si_moved_classes+=("terminal plan(s)")
      _si_moved_msg=$(IFS=/; echo "${_si_moved_classes[*]}")
      # gpgsign=false: same TTY-less SessionStart-hook rationale as above.
      git -c commit.gpgsign=false -C "$GIT_ROOT" commit \
        -m "session-init: auto-sweep ${_si_moved_msg:-actioned memo(s)/terminal plan(s)} (session-init)" \
        -- cross-repo/inbox/ cross-repo/archive/ docs/plans/ archive/specs/ 2>/dev/null || true
      unset _si_moved_classes _si_moved_msg
    fi
  fi
fi

exit 0
