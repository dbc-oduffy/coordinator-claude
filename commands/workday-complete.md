---
name: workday-complete
description: End-of-day orchestration — validate, consolidate branches, daily review, append to week-changelog
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Skill"]
argument-hint: "[optional summary of the day]"
---

# Workday Complete — End-of-Day Orchestration

Lightweight daily wrap: validate, consolidate branches, run the strategic daily review, append to the week-changelog, and surface staleness signals. **Does NOT merge to main.** Heavy ceremony (docs sweep, ShellCheck, improvement-queue triage) is weekly — see `/workweek-complete`.

Daily is a branch wrap, not a release ceremony. Each step below is an explicit script under the coordinator `bin/` directory in the DoE repo; the prose names the contract, the script enforces it. All scripts are idempotent (re-running is a no-op when state is unchanged) and portable per `docs/wiki/cross-platform-shell-portability.md`.

`$ARGUMENTS` below refers to the user-supplied day-summary argument to the slash command (may be empty), per Claude Code conventions.

---

## Argument Parsing (Front Door)

<!-- Spec backlink: docs/plans/2026-07-07-workday-complete-local-day-and-targeted-wrap.md § C6 -->

Parse `--for-date <YYYY-MM-DD>` and `--only` out of `$ARGUMENTS` before any ceremony step executes. Without this front door, these flags would be forwarded verbatim to step9 as scope-summary prose (silently inert but noise-inducing). Run this block **first**, before Step 1.

```bash
# Front-door argument parsing — C6 (workday-complete-local-day-and-targeted-wrap)
_FOR_DATE=""       # YYYY-MM-DD when --for-date was supplied; empty otherwise
_ONLY_MODE=0       # 1 when --only was supplied alongside --for-date
_SCOPE_SUMMARY=""  # remaining prose after stripping --for-date / --only tokens

_ARGS_TMP="${ARGUMENTS:-}"

# Extract --for-date <YYYY-MM-DD>
case "$_ARGS_TMP" in
  *"--for-date "*)
    _FOR_DATE="$(printf '%s\n' "$_ARGS_TMP" | sed 's/.*--for-date[[:space:]]\{1,\}\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\).*/\1/')"
    _ARGS_TMP="$(printf '%s\n' "$_ARGS_TMP" | sed 's/--for-date[[:space:]]\{1,\}[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}[[:space:]]*//')"
    ;;
esac

# Extract --only (meaningful only alongside --for-date; accepted regardless to avoid parse noise)
case "$_ARGS_TMP" in
  *"--only"*)
    _ONLY_MODE=1
    _ARGS_TMP="$(printf '%s\n' "$_ARGS_TMP" | sed 's/--only[[:space:]]*//')"
    ;;
esac

# Remaining prose (after flag-strip and trim) is the scope summary forwarded to step9
_SCOPE_SUMMARY="$(printf '%s\n' "$_ARGS_TMP" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')"

# --only without --for-date produces a near-no-op ceremony with no diagnostic — fail loud
if [ "$_ONLY_MODE" = "1" ] && [ -z "$_FOR_DATE" ]; then
  echo "ERROR: --only requires --for-date <YYYY-MM-DD>; a targeted wrap needs a target date." >&2
  exit 1
fi
```

**Cross-machine restriction:** `--for-date` is restricted to the current machine. Passing `--machine <other>` alongside `--for-date` is not supported — the Phase B machinery does not call step9 for a non-current machine, so a cross-machine `--for-date` would silently produce a summary-only block (footgun). Fail loud immediately when both are present:

```bash
if [ -n "$_FOR_DATE" ]; then
  case "${ARGUMENTS:-}" in
    *"--machine "*)
      _cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
      _cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
      _cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
      _cc_trusted=0
      case "$_cc_root" in
        "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
      esac
      [ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
      case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
      [ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
      [ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
      [ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
      source "$_cc_root/lib/coordinator-daily-branch.sh"
      _CUR_MACHINE_FD="$(cs_compute_machine 2>/dev/null || hostname -s 2>/dev/null || echo unknown)"
      _ARG_MACHINE_FD="$(printf '%s\n' "${ARGUMENTS}" | sed 's/.*--machine[[:space:]]\{1,\}\([^[:space:]]*\).*/\1/')"
      if [ "$_ARG_MACHINE_FD" != "$_CUR_MACHINE_FD" ]; then
        echo "ERROR: cross-machine targeted wrap is not supported; run \`/workday-complete\` on \`${_ARG_MACHINE_FD}\` directly" >&2
        exit 1
      fi
      ;;
  esac
fi
```

**Routing summary:**

- **`--for-date <date>` (without `--only`):** the ceremony routes through Step 3.5 Phase B to wrap the specific date, then continues with the full today-ceremony (Steps 4, 6, 9 all run for today). The targeted date must appear in the backfill scan results for the current machine (`$CUR`); if absent (already wrapped, no commits, or beyond 14-day lookback), Phase B emits an informational message and skips it — this is not an error.

- **`--for-date <date> --only`:** wraps ONLY the targeted date via Phase B. Steps 4 (today-summary), 4.5 (completion-log clustering), 6 (archive audit), and the today-scoped Step 9 call are all skipped. The ceremony runs: Steps 1–3.5 (targeted wrap only) → Steps 5, 7.5, 8, 10, 11. This is the "wrap a missed day without opening an empty today" path.

- **Default (no `--for-date`):** unchanged today-keyed full ceremony. `$_SCOPE_SUMMARY` equals `$ARGUMENTS` (no flags to strip), `$_ONLY_MODE` stays `0`.

---

## Step 1: Validate (blocking gate)

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
# Capture stdout AND the script's exit code SEPARATELY. `eval "$(script)"` discards
# the script's exit code — command substitution throws it away, so `$?` after the
# eval is the status of the assignment line (always 0), silently passing every
# Step-1 failure (build break, test failure, UBT-blocked, missing interpreter).
# Capture stdout first (real exit code in $?), THEN eval the assignment line.
_STEP1_OUT="$("$_cc_root/bin/workday-complete-step1-validate.sh")"
RC_STEP1=$?
eval "$_STEP1_OUT"
```

The script runs the UBT pending-record resolution (UE work only, presence-detected) then the configured fast-test command. Emits `RC_UBT=…` (informs the Step 1 branch decision below) and `RC_VALIDATE=…` (forwarded to Step 9 via env) on **stdout** (the single eval-safe assignment line); all human-readable detail is on **stderr**, which streams to the terminal uncaptured.

**Exit-code branch:**
- `0` — both gates ok or skipped. Proceed.
- `1` — UBT resolved blocked. Stop and fix the C++ compile error. Override with `COORDINATOR_OVERRIDE_UBT_GATE=1` only when the PM authorises (override path emits `RC_VALIDATE=ubt-overridden` so Step 9 can distinguish bypass from a real validation pass).
- `2` — fast-test build failure, a `127` command-not-found (missing interpreter/binary), or the resolver itself hitting a missing interpreter (`RC_VALIDATE=interp-missing`). Stop and fix — these are blocking environment/build failures, never a silent skip.
- `3` — fast-test test failures only. Fix what's quick, flag the rest, proceed.
- `4` — resolver lib missing (`RC_VALIDATE=lib-missing`, distinct from "no fast-test configured" which emits `RC_VALIDATE=skipped`). Configure `fast_test_cmd:` in `coordinator.local.md` or `$COORDINATOR_FAST_TEST_CMD`, or repair the install if the lib was deleted.

> This is the cadence-gate full-tier invocation — not a per-commit reflex; cap parallelism at ~50% cores. → `docs/wiki/test-design-discipline.md § Posture: Proportional Test-Running`.

---

## Step 1.5: Cruft Sweep Apply (Layer 1 mechanical floor)

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
bash "$_cc_root/bin/cruft-sweep.sh" --class all --apply --quiet \
  || echo "[workday-complete] WARN: cruft-sweep Step 1.5 exited non-zero (non-blocking) — check $(coordinator_state_root --central)/cruft-sweep-log.md" >&2
```

Non-blocking. Lock-protected (concurrent invocations no-op), idempotent. Doctrine: `docs/wiki/cruft-sweep-cadence.md` § Layer 1.

---

## Step 2: RAG Staleness Nudge (informational)

If `ToolSearch` finds any `mcp__project-rag__*` tool, run the staleness survey. Surface in the final summary only if verdict is `stale` or `very-stale`. Skip silently otherwise.

---

## Step 2.5: Pre-terminate Dirty-Tree Disposition

Auto-disposes orphaned housekeeping files via path-prefix classification. Three valid dispositions — Commit, Gitignore, Discard — never stash (PM ruling 2026-06-16, `cross-repo/inbox/2026-06-16-workday-complete-dirty-tree-autonomy.md`).

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
bash "$_cc_root/bin/workday-complete-step2_5-dirty-tree.sh"
RC_STEP2_5=$?
```

The script walks `git status --porcelain` and acts:
- **EOL phantoms / submodule pointers / `state/handoffs/`** → skip (concurrent-session territory).
- **Allow-listed housekeeping roots** (`cross-repo/inbox/`, `state/review-trail/`, `state/memos/`, `state/lessons-outbox/`, improvement/debt/bug-backlog dirs, `tasks/audits/`, `archive/`, plan pre-flight sidecars, etc.) → single batched explicit-path commit.
- **Transient patterns** (`logs/*`, `*.log`, `*.pid`, `.DS_Store`) → add to `.gitignore`, remove from index, commit gitignore.
- **`.tmp.<pid>.<nanos>` orphans** → list, do NOT auto-delete (per CLAUDE.md § Verifying Executor Output — diff against target first).
- **Source-tree edits without attribution** → list and exit 2 (PM surface).

**Exit-code branch:**
- `0` — all clear-wins handled, nothing ambiguous remains. Proceed.
- `1` — processing error (git failure, `.gitignore` write failure, commit failure). Stop; inspect stderr before retrying.
- `2` — clear-wins handled, but source-tree or ambiguous paths remain. Surface the script's stderr listing to the PM and ask: _"Adopt-commit (mine, forgot to attribute), discard (abandoned), or attribute to another session?"_ Wait for response before proceeding.

> The allow-list of housekeeping roots is **authoritative in the script** (`workday-complete-step2_5-dirty-tree.sh`); the bullets above are illustrative. To add a root, edit the script's allow-list AND the smoke test, then update the prose here.

**If in doubt — look harder.** Read the file, `git log -- <path>` for prior touches, grep for the workstream, check `state/handoffs/` and `archive/handoffs/` for a `scope:` block that names it. Bailing to "I cannot decide" is the failure mode.

**Auto-disposition is workday-complete-specific by design.** The dirty-tree gate is replicated across all three session terminators (workstream-complete, handoff, workday-complete), but the disposition diverges: workstream-complete and handoff terminate mid-session with a smaller, fresher tree where unattributable-to-this-session is a real signal worth surfacing. The daily wrap is different — it absorbs the day's housekeeping accumulation across all sessions. Do NOT propagate this allow-list to the other two terminators (memo OOS clause).

---

## Step 2.6: Completion-Entry Reconcile Sweep

Folds any post-summary `Session-Id:`-trailer commits into `pending-release` completion entries authored this session. This is the common-case closure: most sessions end the day via `/workday-complete`, and any follow-on commits that landed after `/workstream-complete` Step 2.6.6 was written get folded here even if `/workstream-complete` was never re-run. Advisory and non-blocking — mirrors the Step 1.5 cruft-sweep WARN shape.

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
{
  # Resolve session-id: env var → sentinel file (pinned fallback chain)
  _RECONCILE_SID="${CLAUDE_CODE_SESSION_ID:-}"
  if [ -z "$_RECONCILE_SID" ] && [ -f ".git/coordinator-sessions/.current-session-id" ]; then
    _RECONCILE_SID="$(cat .git/coordinator-sessions/.current-session-id)"
  fi

  if [ -z "$_RECONCILE_SID" ]; then
    echo "[workday-complete] WARN: reconcile sweep Step 2.6 skipped — session-id unresolvable (non-blocking)" >&2
  else
    _TODAY_YM=$(date +%Y-%m)
    # Pre-compute live session IDs once for the cross-machine liveness gate (Axis 2).
    # Source coordinator-session.sh fail-softly: on failure _LIVE_IDS stays empty,
    # which degrades gracefully — only own-session entries reconcile (original behaviour).
    # RAW-PID-LIVENESS: NEVER ps -p / kill -0 a stored pid — cs_live_session_ids is the
    # sanctioned liveness predicate. → docs/wiki/coordinator-tripwires.md § RAW-PID-LIVENESS
    _LIVE_IDS=""
    if source "$_cc_root/lib/coordinator-session.sh" 2>/dev/null; then
      _LIVE_IDS=$(cs_live_session_ids 2>/dev/null || true)
    fi

    # Enumerate this month's pending-release entries for the reconcile sweep
    _RECONCILE_N_ENTRIES=0
    _RECONCILE_N_COMMITS=0
    for _ENTRY in "archive/completed/${_TODAY_YM}/"*.md; do
      [ -f "$_ENTRY" ] || continue
      grep -q "^status: pending-release$" "$_ENTRY" 2>/dev/null || continue
      # Liveness gate (Axis 2): own-session entries always reconcile; cross-machine
      # entries reconcile only when their authoring session is NOT live.
      # A live cross-machine session is mid-edit — stand down to avoid stomp.
      # status: released is hard-skipped inside reconcile-completion-commits.sh.
      _ENTRY_AUTHOR=$(awk '
        /^---$/ { n++; if (n == 2) exit; next }
        n == 1 && /^authored_by:/ {
          sub(/^authored_by:[[:space:]]*/, "")
          sub(/[[:space:]]*#.*$/, "")   # strip trailing inline YAML comment (e.g. "# forensic tracing only")
          gsub(/^"|"$/, "")
          print; exit
        }
      ' "$_ENTRY" 2>/dev/null || true)
      # Malformed entry: missing or null authored_by — skip explicitly rather than
      # letting grep -qxF "" match the trailing empty line of _LIVE_IDS (false "live").
      { [ -z "$_ENTRY_AUTHOR" ] || [ "$_ENTRY_AUTHOR" = "null" ]; } && continue
      if [ "$_ENTRY_AUTHOR" != "$_RECONCILE_SID" ]; then
        # Cross-machine entry: skip if the authoring session is still live
        if printf '%s\n' "$_LIVE_IDS" | grep -qxF "$_ENTRY_AUTHOR" 2>/dev/null; then
          continue  # live — stand down
        fi
      fi
      # F1 fix: pass the entry's own authored_by as the session-id for cross-machine
      # dead entries so reconcile collects THAT peer's commits, not the wrapping
      # session's. Own-session entries keep _RECONCILE_SID (no change in behaviour).
      if [ "$_ENTRY_AUTHOR" = "$_RECONCILE_SID" ]; then
        _CALL_SID="$_RECONCILE_SID"
      else
        _CALL_SID="$_ENTRY_AUTHOR"
      fi
      _RESULT=$("$_cc_root/bin/reconcile-completion-commits.sh" \
        --append --session-id "$_CALL_SID" "$_ENTRY" 2>/dev/null) || {
        echo "[workday-complete] WARN: reconcile-completion-commits failed for $_ENTRY (non-blocking)" >&2
        continue
      }
      _APPENDED=$(printf '%s\n' "$_RESULT" | grep -o 'appended=[0-9]*' | cut -d= -f2)
      if [ "${_APPENDED:-0}" -gt 0 ]; then
        git add -- "$_ENTRY" 2>/dev/null || true
        _RECONCILE_N_ENTRIES=$((_RECONCILE_N_ENTRIES + 1))
        _RECONCILE_N_COMMITS=$((_RECONCILE_N_COMMITS + _APPENDED))
      fi
    done
    if [ "$_RECONCILE_N_ENTRIES" -gt 0 ]; then
      echo "Completion reconcile: ${_RECONCILE_N_ENTRIES} entr(ies) folded ${_RECONCILE_N_COMMITS} commit(s)"
    else
      echo "Completion reconcile: clean"
    fi
  fi
} || echo "[workday-complete] WARN: completion-entry reconcile sweep Step 2.6 exited non-zero (non-blocking)" >&2
```

Non-blocking. Entries amended and staged here are committed alongside the Step 9 changelog commit (the same pattern as Step 4.5 completion-log clustering — `git add -- <entry>` above pre-stages them; Step 9 sweeps staged paths into its scoped commit). Concurrent-EM safety: own-session entries always reconcile; cross-machine entries reconcile only when the authoring session is dead (verified via `cs_live_session_ids` — the sanctioned liveness predicate, never raw pid). `pending-release`-only guard is enforced inside `reconcile-completion-commits.sh` (hard-skips `status: released`). The one-liner (`Completion reconcile: N entr(ies) folded M commit(s) / clean`) feeds Step 11.

---

## Step 3: Branch Consolidation

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
bash "$_cc_root/bin/workday-complete-step3-consolidate.sh"
RC_STEP3=$?
```

The script: syncs main, discovers same-machine sibling workstream branches (case-insensitive, includes span-form), merges them into current, reconciles with `origin/main` (guarded against ahead-only no-op), pushes with `--force-with-lease` (one fetch-rebase-retry on rejection), and deletes merged siblings. Feature branches excluded.

**Exit-code branch:**
- `0` — full success.
- `1` — startup error: `sync-main` aborted, OR detached HEAD (cannot determine current branch), OR current branch is `main`/`master` (the script refuses to push-force to main). Report and stop.
- `2` — merge conflict during sibling merge. Report and halt.
- `3` — reconcile conflict with origin/main.
- `4` — push rejected twice. Report to PM.
- `5` — `cs_compute_machine` lib unavailable. Report to PM; the coordinator lib path is broken.

**Args:** `--no-push` for PM-deferred push; `--dry-run` for inspection.

---

## Step 3.5: Backfill Skipped Days (default-on)

The daily window is a rolling ~24h (`YESTERDAY 23:59Z .. TODAY 23:59Z`). A day that ran sessions but never ran `/workday-complete` falls **permanently** between windows — its commits are before the next run's floor and no window ever picks them up. This step closes that gap automatically: it detects past days with commits but no daily summary, and backfills the summary + per-day changelog block deterministically from the on-disk dated substrate (handoffs, completion entries, review-trail records — all still present). No hand-reconstruction.

```bash
# Capture once, then partition by first field
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
_BACKFILL_SCAN="$(bash "${_cc_root}/bin/workday-complete-backfill-scan.sh" --lookback 14)"
_GAP_ROWS="$(printf '%s\n' "$_BACKFILL_SCAN" | grep -v '^DANGLING-DEFER' | grep -v '^$')"
_DANGLING_ROWS="$(printf '%s\n' "$_BACKFILL_SCAN" | grep '^DANGLING-DEFER')"
```

The scan emits two row shapes on stdout:
- **Normal gap rows** (fed into Phase A0 / Phase A / Phase B): `<date>\t<machine>\t<recorded_tip>\t<actual_tip>` — first field is a date.
- **Dangling-defer rows** (surfaced loud, never auto-backfilled): `DANGLING-DEFER\t<date>\t<machine>\t<missing-target>` — first field is the literal `DANGLING-DEFER`; indicates a summary that deferred work to a `state/week-changelog/<date>-<machine>.md` block that doesn't exist.

`grep -v '^DANGLING-DEFER'` partitions normal gap rows into `$_GAP_ROWS`; `grep '^DANGLING-DEFER'` captures the dangling set into `$_DANGLING_ROWS`. **If both partitions are empty, skip the rest of this step silently** (the healthy common case).

**Phase A0 (mechanical anchor injection, before analyst fan-out):** many scan gaps are legacy summaries that predate the `covered_tip_sha:` anchor field — the summary exists and is complete, but the scan flags it as missing because the anchor is absent. Phase A0 injects the anchor mechanically for those dates, eliminating the need to dispatch any analyst.

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
_ROOT="$_cc_root"
_GIT_ROOT="$(git -C "$_ROOT" rev-parse --show-toplevel 2>/dev/null || echo "${HOME}/.claude")"
_TODAY="$(date +%Y-%m-%d)"
_A0_INJECTED_DATES=""
_A0_CONTENT_GAP_DATES=""
_A0_INJECTED_FILES=()  # Review: code-reviewer — F2: accumulate injected file paths for scoped git add
```

For each distinct date in `$_GAP_ROWS`:
1. **Collect the `actual_tip` values** from every machine row for that date (there may be one row per machine after consolidation produces duplicate per-machine rows sharing the same commit ancestry).
2. **Compute the descendant tip** across those actual_tips. The descendant tip is the `actual_tip` that is a descendant of (or equal to) every other tip for the same date — it is the furthest-forward commit across all machines that day, and injecting it as the anchor closes every machine row at once (see load-bearing deduction below). With a single machine row the descendant tip is that row's `actual_tip` directly. For multiple rows, find the candidate for which all others are ancestors:
   ```bash
   # Walk $_DATE_TIPS (newline-separated actual_tips for this date):
   _DESC_TIP=""
   while IFS= read -r _cand; do
     _ok=1
     while IFS= read -r _other; do
       [[ -z "$_other" ]] && continue  # Review: code-reviewer — F11: guard against empty string from trailing newline
       [ "$_cand" = "$_other" ] && continue
       git -C "$_GIT_ROOT" merge-base --is-ancestor "$_other" "$_cand" 2>/dev/null \
         || { _ok=0; break; }
     done <<< "$_DATE_TIPS"
     [ "$_ok" -eq 1 ] && { _DESC_TIP="$_cand"; break; }
   done <<< "$_DATE_TIPS"
   ```
   If no single tip is a descendant of all others (diverged branches — genuinely diverged work on the same date), log a warning and skip A0 for this date; it falls through to Phase A as a true-gap.
3. **Call the inject-anchor script** (pass the machine from the scan row so branch-ref enumeration is not needed; capture stdout for the injected file path):
   ```bash
   # Review: code-reviewer — F10: derive machine from the scan row that owns _DESC_TIP
   _DESC_MACHINE="$(printf '%s\n' "$_GAP_ROWS" | awk -F'\t' -v date="$_DATE" -v tip="$_DESC_TIP" '$1==date && $4==tip {print $2; exit}')"
   # Review: code-reviewer — F2: capture stdout (TARGET=<path>) for scoped git add
   _inject_out="$(bash "${_ROOT}/bin/workday-complete-backfill-inject-anchor.sh" \
     "$_GIT_ROOT" "$_DATE" "$_DESC_TIP" "$_TODAY" "$_DESC_MACHINE")"
   _A0_RC=$?
   _TARGET_FILE="$(printf '%s\n' "$_inject_out" | grep '^TARGET=' | cut -d= -f2-)"
   ```
4. **Route by exit code:**
   - `0` (anchor injected — also covers a STALE anchor bumped to the descendant tip): resolved mechanically — no agent needed. Accumulate date into `$_A0_INJECTED_DATES`; accumulate file path into `$_A0_INJECTED_FILES`: `[[ -n "$_TARGET_FILE" ]] && _A0_INJECTED_FILES+=("$_TARGET_FILE")`.
   - `10` (anchor already present AND fresh — recorded `covered_tip_sha` >= scan target): resolved mechanically — no agent needed. Accumulate date into `$_A0_INJECTED_DATES`. A *stale* anchor (recorded is a strict ancestor of the target) no longer masquerades as resolved here — it returns exit 0 (bumped) above and is staged like an injection.
   - `20` (no summary file exists — true content gap): let the date fall through to Phase A analyst fan-out unchanged.
   - `30` (CONTENT-GAP — summary exists but content-completeness guard fired, prose looks materially incomplete for the commit range): do NOT inject a masking anchor. Accumulate date into `$_A0_CONTENT_GAP_DATES` for the Phase A content-assembly analyst below.
   - **Any other exit code (unexpected internal error, e.g. unclosed frontmatter):** log `"WARN: inject-anchor returned unexpected exit ${_A0_RC} for ${_DATE}; routing to Phase A analyst as true-gap"` >&2 and let the date fall through to Phase A analyst unchanged. Never silently drop a date.  _(Review: code-reviewer — F7: explicit else branch prevents silent drop)_

**Why one anchor closes all machine rows (load-bearing deduction).** The scan flags a gap only when `covered_tip_sha` is a strict ancestor of a machine's actual_tip (newer unrecorded work exists). After injecting the descendant tip D: the owner machine gets `recorded == actual` (covered); any older-tip machine M has D as its recorded tip, but D is NOT an ancestor of M's older actual_tip — the `merge-base --is-ancestor` check fails — so M is treated as a diverged branch, not a gap. One anchor in the shared legacy `YYYY-MM-DD.md` closes every machine row for that date. Do NOT manufacture per-machine `YYYY-MM-DD-<machine>.md` duplicates for migrated days — the flat file is canonical.

If any `exit 0` injections occurred, commit them before proceeding:
```bash
# Review: code-reviewer — F2: stage only the files A0 injected, never the whole directory
if [[ "${#_A0_INJECTED_FILES[@]}" -gt 0 ]]; then
  git -C "$_GIT_ROOT" add -- "${_A0_INJECTED_FILES[@]}"
  git -C "$_GIT_ROOT" commit -m "chore(daily-summaries): backfill anchor migration"
fi
```

**Re-run the scan and recompute `$_GAP_ROWS`** after A0 so the cap and Phase A operate only on what remains:
```bash
_BACKFILL_SCAN="$(bash "${_ROOT}/bin/workday-complete-backfill-scan.sh" --lookback 14)"
_GAP_ROWS="$(printf '%s\n' "$_BACKFILL_SCAN" | grep -v '^DANGLING-DEFER' | grep -v '^$')"
```

**Cap:** if `$_GAP_ROWS` (post-A0) contains **> 10** rows, do NOT auto-fan the whole wave — surface the list to the PM (`Backfill scan found N skipped days going back to <oldest>; backfill all, or a bounded subset?`) and wait. A 10+-day gap is a signal worth a human glance, not a silent 10-agent burst. The cap counts only TRUE gaps remaining after A0; format-migration rows resolved mechanically by A0 do NOT count. (Dangling-defer rows do NOT count toward the cap — they are surfaced separately in the report and never auto-backfilled.)

**Phase A (parallel):** dispatch one Sonnet analyst (`general-purpose`, `run_in_background: true`) per row — independent `(date, machine)` pairs, fan out and await all. Each analyst is parameterized to its date and machine — same prompt as Step 4b (`docs/wiki/daily-summary-procedure.md` § Sonnet Analyst Prompt Template) but:
   - baseline/tip = the row's `<recorded_tip>..<actual_tip>` (that machine's unrecorded commit span), not `<baseline>..HEAD`.
   - completions source = `query-completions --where "created=<date>"`.
   - writes `archive/daily-summaries/<date>-<machine>.md` with `backfilled: true` in frontmatter and a one-line `> _Backfilled on <today> — ceremony was not run on <date>._` note under the H1.

   **CONTENT-GAP dates** (those accumulated in `$_A0_CONTENT_GAP_DATES` via exit 30 above) fan to a **content-assembly** analyst instead of the standard derivation analyst. The content-assembly analyst assembles the summary from existing completion entries (`query-completions --where "created=<date>"`), handoffs, and review-trail records — it does NOT re-derive from `git diff`. The distinction matters: content-assembly synthesizes authored truth (what the operator actually recorded at the time), not a post-hoc commit-graph reconstruction that may conflict with or duplicate pre-existing prose in the partial summary.

**Phase B (oldest-first, serial):** resolve the current (wrapping) machine once up front:
   ```bash
   _cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
   _cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
   _cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
   _cc_trusted=0
   case "$_cc_root" in
     "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
   esac
   [ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
   case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
   [ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
   [ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
   [ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
   source "$_cc_root/lib/coordinator-daily-branch.sh"
   CUR="$(cs_compute_machine)"
   ```
   Then for each `(date, machine)` row, gate on machine identity before calling step9:

   **`--only` filter (front-door targeted wrap):** when `$_ONLY_MODE=1`, process **only** the row where `<date> == $_FOR_DATE`; skip all other rows silently. Their backfill is deferred to the next normal `/workday-complete` run. When `$_ONLY_MODE=0` (default), all current-machine rows are processed.

   **Front-door targeted date validation:** when `$_FOR_DATE` is set, after the Phase B loop completes, if `$_FOR_DATE` was not found among the processed rows (not present in `$_GAP_ROWS` for `$CUR`), emit: `"INFO: --for-date ${_FOR_DATE} not detected as a gap for ${CUR} (already wrapped, no commits, or beyond 14-day lookback); nothing to do."` — this is not an error.

   - **If `<machine>` == `$CUR`:** run `step9 --for-date <date>` oldest-first so the changelog reads chronologically:
     ```bash
     _cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
     _cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
     _cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
     _cc_trusted=0
     case "$_cc_root" in
       "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
     esac
     [ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
     case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
     [ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
     [ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
     [ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
     # C6: skip this row when --only is set and it doesn't match the user-targeted date
     [ "$_ONLY_MODE" = "1" ] && [ "<date>" != "${_FOR_DATE:-}" ] && continue
     # C6: extract per-machine BASE..TIP span from scan row (C3 emits <date>\t<machine>\t<BASE>\t<TIP>)
     _B_BASE="$(printf '%s\n' "$_GAP_ROWS" | awk -F'\t' -v d="<date>" -v m="$CUR" '$1==d && $2==m {print $3; exit}')"
     _B_TIP="$(printf '%s\n' "$_GAP_ROWS" | awk -F'\t' -v d="<date>" -v m="$CUR" '$1==d && $2==m {print $4; exit}')"
     # Build --commit-span flag when scan provided a well-formed span (C3 guarantee); omit on legacy rows
     _B_SPAN_FLAG=""
     [ -n "$_B_BASE" ] && [ -n "$_B_TIP" ] && _B_SPAN_FLAG="--commit-span ${_B_BASE}..${_B_TIP}"
     # Pass scope summary only for the explicitly front-door-targeted date; auto-detected rows
     # carry no user-supplied prose, so step9 omits the **Scope:** line entirely (C4 omit-by-default;
     # there is NO completion-title derivation — the block simply has no Scope line without an explicit arg)
     _B_SCOPE_ARG=""
     if [ "<date>" = "${_FOR_DATE:-__no_target__}" ] && [ -n "${_SCOPE_SUMMARY:-}" ]; then
       _B_SCOPE_ARG="$_SCOPE_SUMMARY"
     fi
     bash "${_cc_root}/bin/workday-complete-step9-append-changelog.sh" \
       --for-date <date> \
       ${_B_SPAN_FLAG:+${_B_SPAN_FLAG}} \
       ${_B_SCOPE_ARG:+"$_B_SCOPE_ARG"}
     ```
     `--for-date` overrides `TODAY` so the whole block (commit window, `<date>-<machine>.md` filename, summary link, review-trail `--date-prefix`) keys to that day. `--commit-span <BASE>..<TIP>` (C3) keys `Commits:`/`Plans touched:` to the machine-scoped span from the scan row rather than the derived date window, preventing over-count on anchor-divergent machines. Both `--commit-span` git-log queries (commit list and plans-touched) run `--first-parent --no-merges`, so a span that crosses a cross-machine merge scopes to the wrapping machine's own first-parent lineage — commits pulled in through the merged branch's second parent are excluded, not counted. It commits + pushes the per-day changelog file alongside the backfilled summary.
   - **If `<machine>` ≠ `$CUR`:** do NOT call step9. Phase A already wrote that machine's per-machine summary `<date>-<machine>.md` (the durable artifact); its changelog block stays absent until that machine itself runs `/workday-complete` — this is the accepted state per the cross-machine note below.

**Do NOT run the strategic observer (Step 4c) for backfilled days** — debt/risk rows are a *today* signal; re-deriving them for a past day risks stale or duplicate DSR rows. Backfill produces the durable artifacts (summary + changelog), not the live triage surface.

**Cross-machine note:** backfill writes one per-machine changelog block (the machine running it); if multiple machines worked a date and none wrapped, other machines' blocks stay absent — accepted, the summary is the durable artifact.

Report:
- `Phase A0: mechanically migrated N dates (anchor injected): <date list>.` (omit if none)
- `Phase A0: CONTENT-GAP N dates (content-assembly analyst dispatched): <date list>.` (omit if none)
- `Backfilled N skipped days (current machine): <date list>.`
- `Cross-machine gaps (summary backfilled, changelog block awaits that machine's wrap): <machine>@<date>, ...` (omit if none)
- `⚠ Dangling defers (summary deferred to an absent changelog block — investigate): <deferring-machine>@<date> -> <missing-target>, ...` (omit if `$_DANGLING_ROWS` is empty)

Then proceed to Step 4 for *today*.

> Spec / convergence: `cross-repo/archive/2026-06-23-workday-complete-skipped-day-backfill.md` (example-cockpit-repo-em independently root-caused the same gap). Phase A0 anchor-injection: `cross-repo/inbox/2026-07-02-backfill-scan-legacy-anchor-migration.md` (example-game-repo-em) and `cross-repo/inbox/2026-07-02-workday-backfill-covered-tip.md` (cockpit-em, reconciled tension — descendant-tip vs content-true-tip). Scan: `bin/workday-complete-backfill-scan.sh`. Inject: `bin/workday-complete-backfill-inject-anchor.sh`. Override: `step9 --for-date`.

---

## Step 4: Strategic Daily Review

Produce `archive/daily-summaries/YYYY-MM-DD-<machine>.md` (per-machine naming — mirrors `state/week-changelog/YYYY-MM-DD-<machine>.md`). Heavy-weight templates, the failure-mode table, health-ledger schema, and debt-backlog DSR-ID format live in `docs/wiki/daily-summary-procedure.md` — walk that wiki for detail; do not re-author it inline.

**Skip when `--only` is set** (`$_ONLY_MODE=1`): a targeted past-date wrap does not produce a today-summary. Skip this entire step (4a–4f) and proceed directly to Step 4.5.

**Skip condition:** zero new commits AND no agent-driven changes outside commits → write a one-line summary noting "no work today" and skip 4b–4f.

### Step 4a: Inventory Generation

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
mkdir -p tasks/daily-review-scratch
bash "${CLAUDE_PLUGIN_ROOT}/bin/standup.sh" > tasks/daily-review-scratch/inventory.md
TODAY=$(date +%Y-%m-%d)
"$_cc_root/bin/query-completions.sh" --where "created=$TODAY" --format json \
  > tasks/daily-review-scratch/completions-today.json
```

`completions-today.json` is the primary source for the **Work Completed** section. `git log` scanning is deprecated except as a fallback for pre-completion-log sessions (when the JSON is empty).

### Step 4b: Analyst Dispatch (Sonnet, background)

Dispatch a Sonnet analyst (`model: "sonnet"`, `run_in_background: true`). It reads `inventory.md` + `completions-today.json` + `git diff <baseline>..HEAD`, then writes `archive/daily-summaries/YYYY-MM-DD-<machine>.md` with Work Completed / Systems Affected / Architectural Decisions sections.

Full prompt template: `docs/wiki/daily-summary-procedure.md` § Sonnet Analyst Prompt Template.

Dispatch 4b and 4c in parallel — proceed immediately to Step 4c without waiting.

### Step 4c: Strategic Observer Dispatch (Sonnet, non-persona, parallel with 4b)

Dispatch an **unnamed Sonnet worker** (`general-purpose`, `model: "sonnet"`, `run_in_background: true`) — NOT a named persona. Personas (the Staff Engineer / the Game Dev Reviewer / the Data Science Reviewer / the Front-End Reviewer) are Opus-only and reserved for `/workweek-complete` Step 7.5, the merge gate, and explicit architectural decisions.

The observer leaves a paper trail for future-the Staff Engineer — alignment notes, debt candidates, architectural-risk flags. It renders **no final architectural verdict**; weekly Opus the Staff Engineer adjudicates. Writes flagged items as debt-backlog YAML entries via `coordinator-queue-append --schema debt-backlog` (producing `state/debt-backlog/<date>-<slug>.yaml`), using `tags: [weekly-arch-review]` for architectural risk candidates.

**Sidecar output:** the observer writes `## Strategic Review (Sonnet daily observer)` to a **sidecar file** at `archive/daily-summaries/YYYY-MM-DD-<machine>.observer.md` (NOT appended directly to the main summary). Step 4d stitches this into the main file once both agents complete.

> **Parallel-pattern caveat:** 4b and 4c read the same inputs (`tasks/daily-review-scratch/inventory.md`, `completions-today.json`, `git diff <baseline>..HEAD`) — the observer derives its findings from those inputs, NOT from 4b's prose. If a future Step 4c revision needs to cross-reference 4b's "Architectural Decisions" section or any other analyst-authored prose, this parallel/sidecar pattern breaks and must revert to serial dispatch (4b completes first, then 4c reads the main summary and appends directly).

Full prompt template: `docs/wiki/daily-summary-procedure.md` § Daily Strategic Observer Prompt Template.

### Step 4d: Stitch Observer Sidecar into Daily Summary

Wait for both Step 4b and Step 4c to complete. Then concatenate the observer sidecar into the main daily summary and remove the sidecar:

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
source "$_cc_root/lib/coordinator-daily-branch.sh"
MACHINE="$(cs_compute_machine)"
OBSERVER_SIDECAR="archive/daily-summaries/${TODAY}-${MACHINE}.observer.md"
DAILY_SUMMARY="archive/daily-summaries/${TODAY}-${MACHINE}.md"
cat "$OBSERVER_SIDECAR" >> "$DAILY_SUMMARY"
rm "$OBSERVER_SIDECAR"
```

This produces the single canonical daily summary with the `## Strategic Review (Sonnet daily observer)` section intact. The sidecar is a transient artifact — it exists only between Step 4c completing and this stitch, entirely within the workday-complete loop.

### Step 4e: Health Ledger Update

1. Read `state/health-ledger.md`. If missing, create from schema in `docs/wiki/daily-summary-procedure.md` § Health Ledger Entry Schema.
2. Add rows (grade `?`, unaudited) for any system touched today with no row yet.
3. Do **NOT** touch audit clocks (`Last full audit`, `Last targeted audit`) or any grade — those are written only by `/architecture-survey` (full) and `/architecture-audit` (targeted).

### Step 4f: Clean Scratch

```bash
rm -rf tasks/daily-review-scratch
```

The daily summary artifact is committed by Step 9 alongside the changelog row — not here.

---

## Step 4.5: Completion-Log Clustering Pass

<!-- Spec backlink: archive/specs/2026-05/2026-05-19-completion-log-phase1-foundational-loop.md § Chunk 4 (plan archived; sidecar at docs/plans/2026-05-19-completion-log-phase1-foundational-loop.plan-coverage-check.md retained) -->

**Skip when `--only` is set** (`$_ONLY_MODE=1`): this step writes uncommitted `narrative:` edits to today's completion entries; with Step 9 skipped under `--only`, those edits would accumulate as dirty-tree state. Skip this step and proceed to Step 5.

Groups today's completion entries by `chain:` field and synthesizes a machine-readable `narrative:` for each multi-entry chain. Single-entry chains skip. Enables `/workweek-complete` editorial bucketing to read `narrative:` rather than re-derive.

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
TODAY=$(date +%Y-%m-%d)
"$_cc_root/bin/query-completions.sh" --where "created=$TODAY" --format json > /tmp/completions-cluster-$TODAY.json
```

Parse the JSON, group by `chain:`. For each group with ≥2 entries:

1. **Lead entry:** lexicographically first file path in the chain.
2. **Idempotency:** if the lead entry already has `narrative:` AND the body text below the closing `---` of every entry is byte-identical to when it was written → skip this chain.
3. **Dispatch a Sonnet `general-purpose` worker** with this inline prompt:

   > You are synthesizing the contribution narrative for a completion-log chain.
   >
   > Chain entries (JSON): `<paste chain entries JSON>`
   >
   > Write ONE paragraph (3–6 sentences) summarizing the chain's combined contribution. Rules: preserve commit SHAs verbatim; no editorial bucketing (Features/Fixes/etc — that's `/workweek-complete`'s job); describe what was built/fixed/changed and why it matters; ≤300 words.
   >
   > Reply with ONLY the paragraph text. No preamble.

4. **Write the result** — `Edit` the lead entry's frontmatter to insert `narrative: |` as a block scalar.
5. **Mark non-lead entries** — insert `narrative_in: <path-to-lead-entry>` into each non-lead's frontmatter (skip if already present).

No commit here. Step 9 stages and commits the entry files alongside the changelog row.

---

## Step 5: Plugin Validation Suite (blocking gate)

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
node --test "$_cc_root/tests/plugin-ecosystem/run.js"
RC_PLUGIN_SUITE=$?
```

- **Hook-behavior failures:** blocking — stop and fix.
- **Non-hook failures:** report in summary, flag for morning, do not block git steps.

`RC_PLUGIN_SUITE` populates the changelog `Validation:` field in Step 9.

---

## Step 6: Completed Archive Audit

**Skip when `--only` is set** (`$_ONLY_MODE=1`): archive audit is today-scoped; not applicable when running a targeted past-date wrap only. Skip this step and proceed to Step 7.5.

1. `git log --oneline --since="$TODAY 00:00" --until="$TODAY 23:59"` — today's commits.
2. `query-completions --where "created=$TODAY" --format json` — today's per-entry completion records.
3. Reconcile: add missing entries via per-entry write (per `skills/workstream-complete/SKILL.md` Step 2.6 schema), fix inaccurate ones, skip trivial commits.
4. If `docs/project-tracker.md` exists, verify completed workstreams have updated status.
5. Report: _"Archive audit: N verified, M added, K corrected."_

---

<!-- Step 7 intentionally removed (tier-usage telemetry rip-out, 2026-05-18). Do not reuse this number. -->

## Step 7.5: Bug-Backlog Prune (best-effort, non-blocking)

Archive closed bug-backlog entries via `fleet.prune_closed_bugs`. Predicate: `status: closed` only — `wontfix` and `deferred` entries are retained. The fleet op owns the `git-mv` and self-commit; this step does not stage or commit.

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
bash "$_cc_root/bin/prune-closed-bugs.sh" \
  || echo "[workday-complete] WARN: prune-closed-bugs Step 7.5 exited non-zero (non-blocking)" >&2
```

Non-blocking. Best-effort — errors are logged to stderr and the step never hard-gates subsequent steps. The script always exits 0; the `||` guard catches unexpected exit codes from early failures (e.g., sourcing). Wiring: `/workday-complete` only (daily cadence) — not wired into `/pickup` (too high-frequency for daily-cadence bug prune). Spec: `docs/plans/2026-07-06-dr215-fleet-ops-ceremony-wiring.md § KD-4 / AC6`.

---

## Step 8: Improvement-Queue Depth Nudge (read-only)

Count open YAML entries in the central improvement queue directory (`$(coordinator_state_root --central)/improvement-queue/`, example-orchestration-hub-resident — see `docs/wiki/state-placement-law.md`):

```bash
_IQ_COUNT=$(ls "$(coordinator_state_root --central)/improvement-queue/"*.yaml 2>/dev/null | wc -l | tr -d ' ')
```

<!-- Review: code-reviewer slice-C F4 — the old single-file markdown queue was swept by tc-2; replaced with count against the YAML dir -->

- **≥ 5 entries:** emit in final summary: _"Coordinator-improvement queue: K entries — consider `/workweek-complete` to triage."_
- **Otherwise:** skip silently.

No triage at daily cadence — triage is weekly.

---

## Step 9: Append to Week-Changelog

**Skip when `--only` is set** (`$_ONLY_MODE=1`): the today-scoped changelog block is not written when running a targeted past-date wrap only (the targeted block was already written via Step 3.5 Phase B). `RC_STEP9` is set to `0` (no-op) in this case.

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
if [ "${_ONLY_MODE:-0}" = "0" ]; then
  RC_VALIDATE="${RC_VALIDATE:-skipped}" \
  RC_PLUGIN_SUITE="${RC_PLUGIN_SUITE:-n/a}" \
  bash "$_cc_root/bin/workday-complete-step9-append-changelog.sh" "$_SCOPE_SUMMARY"
  RC_STEP9=$?
else
  echo "[workday-complete] --only set — skipping today-scoped Step 9 (targeted wrap already committed via Step 3.5 Phase B)" >&2
  RC_STEP9=0
fi
```

The script:
- Checks `state/week-changelog/HEADER.md` staleness; emits a WARN and skips (non-blocking — caller proceeds to Step 10) if `Week starting:` is >14 days past today.
- Synthesises a per-machine block from today's handoffs (`state/handoffs/YYYY-MM-DD-*.md`), the daily summary, and review-trail records (via `bin/list-review-trail-records.sh --date-prefix "$TODAY"`).
- Extracts `Decisions:` and `Blockers:` from handoff bodies (does not re-author).
- Auto-fills `Validation:` from the env vars above.
- Emits one `**Reviewed:**` line per record; falls back to `**Reviewed:** none — flag for /workweek-complete Step 7` only when today had non-trivial commits and no records exist; omits the field entirely when all today's commits are trivial.

The bold-label set emitted by this step is the **canonical week-changelog daily label set** — see
`docs/wiki/canonical-artifact-shapes.md § week-changelog daily — canonical label set` for the
authoritative per-label definitions, including the `Scope:` expressiveness guardrail and the
`Validation:` enum reference.
- Idempotent: re-running on the same day with unchanged inputs is a no-op (no new commit, no push).
- Commits `$CHANGELOG_FILE` + `archive/daily-summaries/${TODAY}-${MACHINE}.md` together and pushes.

**Exit-code branch:**
- `0` — block written, committed, pushed.
- `1` — write or commit error.
- `2` — push rejected (caller decides retry).
- `3` — HEADER staleness skip (informational).

**Args:** `--dry-run`, `--no-push`.

---

## Step 10: Weekly Staleness Check

```bash
_cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
_cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
_cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
_cc_trusted=0
case "$_cc_root" in
  "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
esac
[ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
[ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
[ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
[ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
"$_cc_root/bin/check-weekly-staleness.sh"
```

- **STALE:** _"Weekly is stale: D days, N commits since last `/workweek-complete`. Run it when ready."_
- **MILD:** _"Weekly cadence: mild staleness. Consider `/workweek-complete` soon."_
- **FRESH / UNKNOWN:** skip silently.

---

## Step 10.5: Project Post-Ceremony Command Hook

**Skip when `--only` is set** (`$_ONLY_MODE=1`): the hook publishes *today's* settled end-of-day state; a targeted past-date backfill is not a live wrap. Skip this entire step and proceed to Step 11.

Runs a consumer repo's opt-in `workday_complete_post_command:` (declared in `coordinator.local.md`) via the shared, generic per-repo post-ceremony hook. Advisory/non-blocking — never gates the ceremony. Spec: `docs/plans/2026-07-08-ceremony-post-command-hook-seam.md` § "Per-ceremony wiring (C2–C5)".

```bash
if [ "${_ONLY_MODE:-0}" = "0" ]; then
  _cc_root="${CLAUDE_PLUGIN_ROOT:-$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null)/coordinator}"
  _cc_doe="$(cat "${CLAUDE_HOME:-$HOME}/.claude/.doe-root" 2>/dev/null || true)"
  _cc_doe="${_cc_doe%/}"   # trailing-slash normalization: prevents //* false-reject on stale/hand-edited .doe-root
  _cc_trusted=0
  case "$_cc_root" in
    "${CLAUDE_HOME:-$HOME}/.claude/"*) _cc_trusted=1 ;;
  esac
  [ -n "$_cc_doe" ] && case "$_cc_root" in "$_cc_doe"/*) _cc_trusted=1 ;; esac
  case "$_cc_root" in *"/.."*) _cc_trusted=0 ;; esac   # load-bearing traversal check; dotdot-prefixed name (e.g. ..cache) is accepted false-reject edge
  [ "${COORDINATOR_PLUGIN_ROOT_TRUSTED:-}" = 1 ] && _cc_trusted=1   # sanctioned --plugin-dir spike opt-out
  [ "$_cc_trusted" = 1 ] || { echo "ERROR: coordinator root '$_cc_root' outside trusted prefix — refusing to source; re-run coordinator:install (or set COORDINATOR_PLUGIN_ROOT_TRUSTED=1 for a sanctioned --plugin-dir spike)" >&2; exit 1; }
  [ -d "$_cc_root" ] || { echo "ERROR: coordinator root unresolved — ~/.claude/.doe-root missing/invalid; re-run coordinator:install" >&2; exit 1; }
  # Review: code-reviewer (F1) — guard is defensive-only against the helper-script-absent
  # (install-drift) case; the helper itself is contracted always-exit-0, so this `||` fires
  # only if `bash <path>` itself can't find/exec the script (e.g. exit 127).
  _HOOK_OUT="$(bash "$_cc_root/bin/coordinator-ceremony-hook.sh" workday-complete)" \
    || echo "[workday-complete] WARN: ceremony-hook exited non-zero (non-blocking)" >&2
  if [ -n "$_HOOK_OUT" ]; then printf '%s\n' "$_HOOK_OUT"; fi
else
  echo "[workday-complete] --only set — skipping post-ceremony command hook" >&2
fi
```

---

## Step 11: Final Summary

```
## Workday Complete

**Validation:** [step1 exit code]
**Branches consolidated:** [step3 summary]
**Branch state:** [branch name], rebased on main, pushed
**Daily review:** [archive/daily-summaries/YYYY-MM-DD-<machine>.md]
**Completion reconcile:** [step2.6 summary: N entr(ies) folded M commit(s) / clean / skipped]
**Plugin validation:** [step5 N pass / N fail]
**Archive audit:** [step6 summary]
**Week-changelog:** [step9 summary]
**Weekly staleness:** [STALE / MILD / FRESH]
**Post-ceremony hook:** [step10.5 $_HOOK_OUT line — omit entirely when $_HOOK_OUT was empty/unset]
**NOT merged to main** — use `/merge-to-main` when ready
```

If `$_SCOPE_SUMMARY` is non-empty (prose remaining after stripping `--for-date`/`--only` flags from `$ARGUMENTS`), prepend: _"Day summary: {scope summary}"_. If `$_FOR_DATE` was set, also prepend: _"Targeted wrap: <date> (backfilled via Step 3.5 Phase B)"_. When neither flag was supplied, `$_SCOPE_SUMMARY` equals `$ARGUMENTS` — unchanged behavior.

---

### What This Does NOT Do

- **Merge to main** — `/merge-to-main` runs the test suite first.
- **`/update-docs`** — weekly only.
- **Triage the improvement queue** — depth nudge only; triage is weekly.
- **ShellCheck or scc stats** — `/workweek-complete`.
- **Delete the work branch** — stays alive for morning.
- **Delete handoffs** — `/pickup` archives, `/distill` deletes from archive (guarded). Spec: `docs/plans/2026-05-08-roadmap-skill-and-handoff-lifecycle.md` § Phase 4.
- **Propagate dirty-tree auto-disposition to other terminators** — Step 2.5's allow-list logic is workday-complete-specific; `/workstream-complete` and `/handoff` keep their stricter surface where unattributable IS a real signal worth surfacing.

### Concurrent Session Safety

Per-machine files under `state/week-changelog/` eliminate concurrent-write conflicts. HEADER.md is touched only by the two weekly commands. Health files are global — workday-complete is the single daily writer.

### Relationship to Other Commands

- **`/merge-to-main`** — supervised merge; morning.
- **`archive/daily-summaries/YYYY-MM-DD-<machine>.md`** — produced by Step 4; feeds Step 9.
- **`/workweek-complete`** — weekly release: docs sweep, ShellCheck, triage, version bump, merge.
- **`/workweek-start`** — PM-facing weekly orient; sets priorities in HEADER.md.
