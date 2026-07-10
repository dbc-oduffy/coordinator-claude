---
name: workweek-start
description: Weekly strategic orient — surface last week's results, set this week's priorities, update HEADER.md
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
argument-hint: ""
---

# Workweek Start — Weekly Strategic Orient

PM-facing weekly bookend. Sets the week's context, surfaces carryover, and writes priorities into `state/week-changelog/HEADER.md`. The workstream-boundary ceremony for the week — and by definition also the day's first orient, so this command chains into `/workday-start` at the end (Step 7).

**Design contract:** handoffs are the atom; HEADER.md is the weekly index header. This command reads existing artifacts (changelog, tracker, handoffs) — it does not reconstruct or re-author them.

---

## Step 0: Bootstrap HEADER.md (first-run only)

If `state/week-changelog/HEADER.md` does not exist, create it with the seed template below before proceeding. This lets the command run on a fresh project without manual setup.

```markdown
# Week Changelog

<!-- Directory convention:
     state/week-changelog/ holds the current week's changelog state.
     HEADER.md (this file) is written by /workweek-complete on reset and by
     /workweek-start on re-run. It is the only shared file in this directory
     — all other files are per-machine daily blocks (YYYY-MM-DD-{hostname}.md)
     written by /workday-complete, which avoids concurrent-write conflicts.

     Priorities are NOT stored inline in HEADER.md — each /workweek-start
     writer owns its own fragment file, HEADER.priorities.<SID_SHORT>.md,
     to avoid a second collaborator's /workweek-start silently overwriting
     the first's priorities in the same week. Readers merge all fragments
     on read (see "Priorities (from /workweek-start)" below).

     On /workweek-complete, the full directory (daily files + fragments +
     old HEADER) is archived to archive/week-changelogs/<week-start>/ before
     HEADER is rewritten and fragments are cleared.
     check-weekly-staleness.sh reads this file to compute the staleness signal.
-->

**Week starting:** (run /workweek-start to initialise)
**Prior week released:** (run /workweek-complete to record)
**Last /workweek-start:** (none)
**Priorities (from /workweek-start):** see `HEADER.priorities.*.md` fragments — none yet; run /workweek-start to set priorities.
```

## Step 0.5: EM Environment Check

Before load-bearing work, confirm the EM is on the right model and effort:

- **Effort** — you cannot observe this yourself (it shows only in the CLI startup banner, never in your system prompt). Run the safety script and relay any banner it prints; silent output means clean (`medium` effort), so say nothing:
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
  bash "$_cc_root/bin/check-em-environment.sh"
  ```
- **Model** — your system prompt names your model. If it is not Opus, WARN the PM (`⚠ MODEL DRIFT — not Opus; toggle via /model`) and recommend switching before proceeding. (The script also reads the transcript model as a backstop.)

Step 5 will populate `Week starting:` and `Last /workweek-start:` with today's date and write the priorities the PM sets. `Prior week released:` stays as the placeholder until the first `/workweek-complete` runs.

If the file already exists, skip this step silently — do not overwrite an existing HEADER.

## Step 0.7: Refresh the exec-summary

Regenerate this repo's `docs/exec-summary.md` MANAGED sections (identity + progress) from disk so the
board reflects the new week — mirrors the weekly `HEADER.md` refresh. The two HAND sections (what makes
it special, near-term goals) are preserved verbatim:
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
bash "$_cc_root/bin/generate-exec-summary.sh"
```
Silent if the generator or the file is absent (`repo-setup` Phase 3d.5 creates it on onboarded repos).
Kill-switch for the staleness banner: `COORDINATOR_EXECSUMMARY_STATUS_OFF`.

## Step 1: Read Week-Changelog (prior week)

Glob `state/week-changelog/*.md` excluding `HEADER.md` and `HEADER.priorities.*.md` (the per-writer priorities fragments — not daily changelog files). Sort by filename (date-then-hostname order). Read each daily file.

Surface a brief prior-week digest:
- **Days covered:** count unique dates across daily files.
- **Implemented:** list plans with status `implemented` across all `Plans touched:` fields. (Plan terminal state = code complete on branch; on-main release tracked separately via completion log + handoff `deployment_state: shipped`.)
- **Blockers carried over:** any `Blockers:` fields that weren't cleared by end of week.
- **Priorities met vs. missed (merge-on-read):** glob `state/week-changelog/HEADER.priorities.*.md`, read every fragment found, and union their checklist items into one merged priorities list (each fragment is an independent writer's set — do not treat any single fragment as authoritative). For each merged item, indicate met (plan flipped to `implemented` or handoff closed) or missed. If no fragments exist, report "no priorities were set last week."

If no daily files exist, skip this step: _"No prior-week changelog found — this may be the first run."_

---

## Step 2: Read Tracker — Stalled Workstreams

If `docs/project-tracker.md` exists, read it. Identify workstreams whose referenced branches have had no commits in >7 days:

```bash
# For each branch referenced in the tracker:
git log --oneline --since="7 days ago" -- <branch> 2>/dev/null | wc -l
```

Surface stalled workstreams (zero recent commits) as a bulleted list. This gives the PM a concrete picture of what needs attention vs. what's moving.

---

## Step 3: Orphan Sweep

Scan for aging artefacts that may need pruning or deferral:

1. **Stale handoffs:** query, don't grep:
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
   "$_cc_root/bin/query-records.sh" --type handoff --where "status=active" --older-than 7d --format markdown-list
   ```
   Lists ready_to_fire and awaiting_gate handoffs older than 7 days.
2. **Draft plans without recent commits — mechanized:** run the aging detector against `docs/plans/` (same script wired into `/workday-start`, docs/wiki/coordinator-tripwires.md § DRAFT-PLAN-AGING):
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
   bash "$_cc_root/bin/draft-plan-aging.sh" docs/plans
   ```
   - **Exit `1`** (stale draft plans found, one line each): surface the flagged plans under a "Stale draft plans" subsection with a decision prompt — _"{N} draft plans older than 14d with no recent real-work commits and no owning baton — execute / archive / close-DR?"_ List the flagged paths.
   - **Exit `0`** (nothing stale): skip silently.
   - **Exit `2`** (internal error): surface the stderr diagnostic verbatim under "Stale draft plans"; do not silently drop the malformed record.

Surface as a brief list for PM awareness. No archival action — this command is read-and-surface only.

---

## Step 4: Surface Scheduled Rechecks

Glob `tasks/cookbook-recheck-due-*.md` and any analogous `tasks/*-recheck-due-*.md` files. For files whose date component falls within the coming 7 days, read the first few lines and surface the recheck item.

If none found, skip silently.

---

## Step 5: PM Dialogue — Set Priorities

Present the digest from Steps 1–4, then ask:

> "Given last week's results and current state, what are 1–3 priorities for this week?"

**Wait for the PM's response.** Write the answer verbatim (as a checklist) to this session's OWN priorities fragment, `state/week-changelog/HEADER.priorities.<SID_SHORT>.md` — never to a shared HEADER.md section (a second collaborator's `/workweek-start` the same week must not overwrite this session's priorities). Resolve `<SID_SHORT>` the same way `workweek-trail-scope.sh` does: `CLAUDE_SESSION_ID` / `CLAUDE_CODE_SESSION_ID` / `cs_resolve_session_id`, first 8 chars. Mirror to `docs/project-tracker.md` if it exists (append under a `## Week of YYYY-MM-DD` heading or update an existing one). The fragment is canonical; the tracker copy is for visibility.

<!-- Review: A-F9 — goal-event emission removed from Step 5 to prevent double-emit.
     Goal events are emitted exactly once from Step 6, covering both the reset and
     update-in-place branches. Do NOT add an emission block here. -->

---

## Step 6: Reset-or-Update Decision

This is the critical branch in the command. Read `state/week-changelog/HEADER.md`:

```
**Last /workweek-start:** YYYY-MM-DD  (or "(none)")
**Prior week released:** vX.Y.Z (commit abc1234, YYYY-MM-DD)
```

**Decision logic:**

If `Last /workweek-start:` is `(none)` OR `Prior week released:` commit is newer than the `Last /workweek-start:` date — a `/workweek-complete` has occurred since the last `/workweek-start`, meaning we are starting a genuinely new week:

→ **Full reset:**
1. Read `Week starting:` from HEADER.md to get the prior week's start date for the archive path.
2. Create `archive/week-changelogs/<prior-week-start>/` and move all daily files (`state/week-changelog/YYYY-MM-DD-*.md`) there, along with any existing `state/week-changelog/HEADER.priorities.*.md` fragments from the prior week (they're now historical — the new week starts with a clean fragment set). Do NOT move HEADER.md.
3. Write a fresh HEADER.md:
   ```markdown
   # Week Changelog

   **Week starting:** YYYY-MM-DD  (today's date)
   **Prior week released:** <version> (commit <sha>, <date>)  (from the prior HEADER)
   **Last /workweek-start:** YYYY-MM-DD  (today's date)
   **Priorities (from /workweek-start):** see `HEADER.priorities.*.md` fragments
   ```
4. Write this session's priorities fragment, `state/week-changelog/HEADER.priorities.<SID_SHORT>.md` (per Step 5 — `<SID_SHORT>` resolved the same way):
   ```markdown
   - [ ] <priority 1 from PM>
   - [ ] <priority 2 from PM>
   - [ ] <priority 3 from PM>
   ```

   After writing the fresh HEADER.md and the priorities fragment, for each priority checkbox, emit a structured weekly goal event by running:
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
   # Review: A-F13 — absolute path required; /workweek-start runs from arbitrary cwd
   # Review: A-F9 — single-emission point: emitted here (reset path) and in update-in-place path
   bash "$_cc_root/bin/append-goal-event.sh" --period week --period-value <current-ISO-week, e.g. 2026-W26> --text "<the bold priority title>"
   ```
   This runs automatically as part of the ceremony — it adds NO new manual PM action.

If `Last /workweek-start:` is set AND no `/workweek-complete` has occurred since (i.e., `Prior week released:` commit predates `Last /workweek-start:`) — this is a mid-week re-run:

→ **Update in place:**
1. Write (or overwrite) THIS session's own priorities fragment, `state/week-changelog/HEADER.priorities.<SID_SHORT>.md`, with the new priorities from Step 5. Do NOT touch any other session's fragment — a re-run only ever overwrites the fragment matching this session's own `<SID_SHORT>`, never another collaborator's.
2. Update `Last /workweek-start:` to today's date in HEADER.md. HEADER.md's own `Priorities (from /workweek-start):` line stays a pointer to the fragments (no content change needed there).
3. Leave daily files untouched.
4. For each priority checkbox, emit a structured weekly goal event (single-emission, A-F9):
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
   # Review: A-F13 — absolute path required; /workweek-start runs from arbitrary cwd
   bash "$_cc_root/bin/append-goal-event.sh" --period week --period-value <current-ISO-week, e.g. 2026-W26> --text "<the bold priority title>"
   ```

**In both cases,** commit the HEADER.md change and this session's priorities fragment:
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
# Stage only THIS session's own fragment — never a sibling collaborator's fragment file.
git add -- state/week-changelog/HEADER.md "state/week-changelog/HEADER.priorities.<SID_SHORT>.md"
git commit -m "chore(workweek-start): set week priorities $(date +%Y-%m-%d)"
git push origin $("$_cc_root/bin/coordinator-current-branch")
```

If a full reset moved daily files, include them in the same commit:
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
git add -- state/week-changelog/ archive/week-changelogs/<prior-week-start>/
git commit -m "chore(workweek-start): archive prior week, reset changelog $(date +%Y-%m-%d)"
git push origin $("$_cc_root/bin/coordinator-current-branch")
```

---

## Step 6.5: Project Post-Ceremony Command Hook

Run the generic per-repo post-ceremony command hook so a consumer repo's opt-in `workweek_start_post_command:` (declared in `coordinator.local.md`) runs advisory, non-blocking, before the chain into `/workday-start`. This MUST run here — before Step 7 — else it would run after the entire chained `/workday-start` ceremony instead of at `/workweek-start`'s own settle point.

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
# Review: code-reviewer (F1) — guard is defensive-only against the helper-script-absent
# (install-drift) case; the helper itself is contracted always-exit-0, so this `||` fires
# only if `bash <path>` itself can't find/exec the script (e.g. exit 127).
_HOOK_OUT="$(bash "$_cc_root/bin/coordinator-ceremony-hook.sh" workweek-start)" \
  || echo "[workweek-start] WARN: ceremony-hook exited non-zero (non-blocking)" >&2
if [ -n "$_HOOK_OUT" ]; then printf '%s\n' "$_HOOK_OUT"; fi
```

The hook is opt-in: if the repo has not declared `workweek_start_post_command:` in `coordinator.local.md`, `$_HOOK_OUT` is empty and this step emits nothing. A configured command's summary line (`Post-workweek-start hook: ran <redacted-cmd> (exit N)`) is captured in `$_HOOK_OUT` and echoed into this step's own output — carry it forward into the Output section below (see the trailing "**Post-ceremony hook:**" line, rendered only when non-empty).

---

## Step 7: Chain into /workday-start

A new workweek's first session is also a new workday — the daily orient (session reaper, branch reconcile, handoff triage, staleness surfacing, orientation cache refresh) still has to happen. Invoke it now via `Skill(coordinator:workday-start)` so the PM gets a single chained briefing rather than having to re-invoke manually.

If `/workday-start` has already run today (check `state/.workday-start-marker` or equivalent freshness signal it maintains), the skill itself will short-circuit — no special handling needed here. Just invoke unconditionally.

After the chained `/workday-start` returns, emit the combined Workweek Start + Workday Start summary below.

---

## Output

After completing all steps, emit a brief summary:

```
## Workweek Start

**Prior week:** [D days, N shipped, K blockers carried over — or "no prior record"]
**Stalled workstreams:** [list or "none"]
**Stale handoffs:** [list or "none"]
**Upcoming rechecks:** [list or "none"]
**This week's priorities:**
  - [ ] Priority 1
  - [ ] Priority 2
  - [ ] Priority 3
**HEADER.md:** [reset (archived prior week) / updated in place]
```

If Step 6.5's `$_HOOK_OUT` was non-empty, append it as a standalone trailing line after the summary above (before the chained `/workday-start` output):

```
**Post-ceremony hook:** [Step 6.5's $_HOOK_OUT line — e.g. "Post-workweek-start hook: ran <redacted-cmd> (exit N)"]
```

Omit this line entirely when `$_HOOK_OUT` was empty (the common opt-in no-op case).

---

### Relationship to Other Commands

- **`/workday-start`** — tactical daily orient. Different ceremony, but `/workweek-start` chains into it (Step 7) because the week's first session is also a workday.
- **`/workweek-complete`** — the weekly close; it resets HEADER.md and archives daily files as part of its Step 14. `/workweek-start` detects that reset and does a full re-init.
- **`/pickup`** — gains a "while you were away" surface from the week-changelog; reads HEADER.md to determine week bounds.
