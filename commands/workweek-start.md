---
name: workweek-start
description: "Weekly orient — review last week, set this week's priorities."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
argument-hint: ""
---

# Workweek Start — Weekly Strategic Orient

PM-facing weekly bookend. Sets the week's context, surfaces carryover, and writes priorities into
`state/week-changelog/HEADER.md`. The week's workstream-boundary ceremony — and the day's first
orient, so it chains into `/workday-start` at the end (Step 10).

Handoffs are the atom; HEADER.md is the weekly index header. This command reads existing
artifacts — it does not reconstruct or re-author them.

---

## Step 0: Bootstrap HEADER.md (first-run only)

If `state/week-changelog/HEADER.md` doesn't exist, create it with the template below, then
continue — no scaffold CLI covers this file yet.
<!-- engine-gap: field=week_changelog.header_bootstrap producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
If it already exists, skip silently — never overwrite an existing HEADER.

```markdown
# Week Changelog

**Week starting:** (run /workweek-start to initialise)
**Prior week released:** (run /workweek-complete to record)
**Last /workweek-start:** (none)
**Priorities (from /workweek-start):** see `HEADER.priorities.*.md` fragments — none yet; run /workweek-start to set priorities.
```

Directory conventions (fragment ownership, per-machine daily files, archive-on-complete): wiki.

Step 8 fills `Week starting:`, `Last /workweek-start:`, and priorities on the first real run.

---

## Step 1: Assemble the Week-Cadence Brief

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/orient-assemble" brief --cadence week`

Computes the cadence-invariant orient spine in one read-only pass (env/effort drift, addon/doctor
health, inbound cross-repo memo surfacing, project-RAG staleness, handoff triage, agent-worktree
sweep, health-probe drift, branch-span assertion) — the same spine `workstream-start` and
`workday-start` consume for their own cadences — plus the week-marker freshness check: its
`judgment_points[]` carries `j-week-marker-freshness` (dispositions `reset_week` /
`update_in_place`) whenever HEADER.md reads stale. Step 8 acts on that.

- **`directives[]`** — execute as you reach each one; render its `detail` into the Weekly Digest
  rather than re-deriving the finding by hand.
- **`judgment_points[]`** — genuine EM/PM calls the op cannot resolve (inbound memo dispositions,
  non-benign worktree/reconcile findings, the week-marker reset call). Present each to the PM
  before proceeding past it — never auto-pick a disposition.
- **`narration`** / **`next_move`** — surface verbatim as the digest's lead when non-empty.

Do not re-derive any check this op already computes. What follows is the week-specific residue it
doesn't cover: the exec-summary refresh, the positioning nudge, priority-setting and goal
authoring, and the HEADER.md reset-or-update mechanics.

---

## Step 2: Refresh the Exec-Summary

Regenerate `docs/exec-summary.md`'s MANAGED sections (identity + progress) from disk; the two HAND
sections (what makes it special, near-term goals) are preserved verbatim:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/generate-exec-summary"`

Silent if the generator or the file is absent (`repo-setup` Phase 3d.5 creates it on onboarded
repos). Kill-switch for the staleness banner: `COORDINATOR_EXECSUMMARY_STATUS_OFF`.

---

## Step 3: Prior-Week Digest — engine gap

Days covered, implemented plans, blockers carried over, and priorities met vs. missed are
engine-knowable but not yet emitted by any producer.
<!-- engine-gap: field=week_changelog.prior_week_digest producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
Until it lands, report: _"No engine-computed prior-week digest yet — see
`state/week-changelog/*.md` for the raw record."_ Do not hand-derive the digest by reading and
cross-referencing the daily files and priority fragments yourself.

---

## Step 4: Stalled Workstreams — engine gap

Which `state/workstreams/` workstreams have had no commits in >7 days is engine-knowable but
not yet emitted.
<!-- engine-gap: field=tracker.stalled_workstreams producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->
Report "no engine-computed staleness signal yet" rather than running `git log --since` per tracker
branch.

---

## Step 5: Scheduled Rechecks — engine gap

Upcoming `tasks/*-recheck-due-*.md` items due within 7 days are engine-knowable but not yet
emitted.
<!-- engine-gap: field=tasks.recheck_due_this_week producer=unknown memo=2026-08-14-doe-claude-em-three-cut-obligations-from-the-corpus-grind.md -->

---

## Step 6: Competitive Positioning Nudge

Offer-shaped, absent-OR-empty trigger only — fires when `competitors[]` is unpopulated, never
re-nudges once data exists (that's `/workweek-complete` Step 4i's freshness-nudge territory).
Delegates scaffolding to `coordinator:strategic-self-description-refresh`; this step never authors
the scaffold itself. Shared with `/workweek-complete` Step 4j via one extracted script.

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-competitor-positioning-nudge"`

If the PM declines, record it so the nudge doesn't recur for the cooldown window:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-competitor-positioning-nudge" --record-decline`

---

## Step 7: PM Dialogue — Set Priorities, Author Weekly Goal Artifacts

Present the digest from Steps 1–6 (including any `judgment_points[]` the PM hasn't yet resolved),
then ask:

> "Given last week's results and current state, what are 1–3 priorities for this week?"

**Wait for the PM's response.** A fresh, unsized priority routes to the `sizing` skill rather than
being derived here.

Resolve `<SID_SHORT>` as `workweek-trail-scope.py` does: `CLAUDE_SESSION_ID` /
`CLAUDE_CODE_SESSION_ID` / `cs_resolve_session_id`, first 8 chars.

For **each** priority, author one `period=week` goal artifact:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-start-goal-and-priorities" scaffold-goal --title "<priority title>" --sid-short "<SID_SHORT>"`

Prints the goal artifact's path — capture as `_GOAL_OUT` for Step 8. Confine authored prose to
`objective` and each key result's `text`; leave `parent_goal_id` null unless the PM names a parent
OKR to backlink.

Write the PM's answer verbatim, as a checklist, to THIS session's own
`state/week-changelog/HEADER.priorities.<SID_SHORT>.md` — never a shared HEADER.md section (a
concurrent collaborator's own `/workweek-start` must not overwrite it). Each line links to the
goal artifact it produced:

```markdown
- [ ] <priority title> — state/goals/<date>-<slug>-<SID_SHORT>.yaml
```

### Goal-Coverage Sweep

After authoring this week's goals, run the read-only coverage scan over all active goals via
`bin/goal-coverage-scan.py --format text`. For each zero-coverage goal, prompt individually:
_"Goal `<title>` has no in-flight work — spin off a stub? (routes to `/spinoff` or
`/roadmap-planning`)"_ — propose-only, wait for the PM's literal invocation. No zero-coverage
goals: note the count and continue. No active goals: skip silently.

---

## Step 8: Reset-or-Update Decision

Consume Step 1's `j-week-marker-freshness` judgment point rather than re-deriving it from
HEADER.md's dates. No such point: HEADER.md read fresh, treat as `update_in_place`. Present the
disposition to the PM before acting on it.

**`reset_week`** — a `/workweek-complete` occurred since the last `/workweek-start`:

1. Read `Week starting:` from HEADER.md for the archive path.
2. Move all daily files and priorities fragments to `archive/week-changelogs/<prior-week-start>/`.
   Do NOT move HEADER.md.
3. Write a fresh HEADER.md (Step 0 template, today's date, prior `Prior week released:` value
   carried over).
4. Write this session's priorities fragment (Step 7 format).
5. For each priority's goal artifact, emit the weekly goal event — sourced FROM the artifact's
   `period_value`/`objective` fields so the emitted event and the on-disk goal agree byte-for-byte:
   `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-start-goal-and-priorities" emit-goal-event --goal "<goal artifact path>"`

**`update_in_place`** — no `/workweek-complete` since the last `/workweek-start` (a mid-week
re-run):

1. Write (or overwrite) THIS session's own priorities fragment only — never another session's.
2. Update `Last /workweek-start:` in HEADER.md; leave its `Priorities:` pointer line as-is.
3. Leave daily files untouched.
4. Emit the weekly goal event per priority, same command as above.

**In both cases,** commit HEADER.md, this session's priorities fragment, and this session's goal
artifacts:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-start-goal-and-priorities" commit-priorities --sid-short "<SID_SHORT>"`

A full reset also commits the archived daily files:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-start-goal-and-priorities" commit-archive-reset --prior-week-start "<prior-week-start>"`

---

## Step 9: Project Post-Ceremony Command Hook

Run the opt-in per-repo hook (declared via `workweek_start_post_command:` in
`coordinator.local.md`) here — before Step 10, so it settles at `/workweek-start`'s own close
rather than after the chained `/workday-start`.

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-start-goal-and-priorities" ceremony-hook --ceremony workweek-start`

Empty `$_HOOK_OUT` when unconfigured — nothing renders. A configured command's summary line
renders in the Output section below.

---

## Step 10: Chain into /workday-start

A new week's first session is also a new workday. Invoke `Skill(coordinator:workday-start)`
unconditionally — it short-circuits itself if already run today.

After the chained `/workday-start` returns, emit the combined summary below.

---

## Output

```
## Workweek Start

**Prior week:** [D days, N shipped, K blockers carried over — or "no prior record"]
**Stalled workstreams:** [list or "none"]
**Handoff/health advisories:** [Step 1 directives[] renders, or "none"]
**Upcoming rechecks:** [list or "none"]
**This week's priorities:**
  - [ ] Priority 1
  - [ ] Priority 2
  - [ ] Priority 3
**HEADER.md:** [reset (archived prior week) / updated in place]
```

If Step 9's `$_HOOK_OUT` was non-empty, append it as a trailing line before the chained
`/workday-start` output:

```
**Post-ceremony hook:** [Step 9's $_HOOK_OUT line]
```

Omit entirely when `$_HOOK_OUT` was empty.

---

### Relationship to Other Commands

- **`/workday-start`** — tactical daily orient; `/workweek-start` chains into it (Step 10).
- **`/workweek-complete`** — the weekly close; resets HEADER.md and archives daily files.
  `/workweek-start` detects that reset via Step 1's `j-week-marker-freshness` judgment point.
- **`/pickup`** — reads HEADER.md to determine week bounds for its "while you were away" surface.
