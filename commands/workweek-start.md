---
name: workweek-start
description: "Weekly orient — review last week, set this week's priorities."
allowed-tools: ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]
argument-hint: ""
---

# Workweek Start — Weekly Strategic Orient

PM-facing weekly bookend. Sets the week's context, surfaces carryover, and writes priorities into `state/week-changelog/HEADER.md`. The workstream-boundary ceremony for the week — and by definition also the day's first orient, so this command chains into `/workday-start` at the end (Step 10).

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
     check-weekly-staleness.py reads this file to compute the staleness signal.
-->

**Week starting:** (run /workweek-start to initialise)
**Prior week released:** (run /workweek-complete to record)
**Last /workweek-start:** (none)
**Priorities (from /workweek-start):** see `HEADER.priorities.*.md` fragments — none yet; run /workweek-start to set priorities.
```

Step 8 populates `Week starting:` and `Last /workweek-start:` with today's date and writes the priorities the PM sets. `Prior week released:` stays as the placeholder until the first `/workweek-complete` runs.

If the file already exists, skip this step silently — do not overwrite an existing HEADER.

## Step 1: Assemble the Week-Cadence Brief

Run: `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/orient-assemble" brief --cadence week`

The op computes the cadence-invariant orient spine in one read-only pass — EM environment/effort
drift, addon/doctor health, inbound cross-repo memo surfacing, project-RAG staleness, handoff
triage (ready-to-fire, awaiting-gate, stale-executing-plan advisory), agent-worktree sweep,
health-probe drift, and branch-span assertion — the same computation `workstream-start` and
`workday-start` name for their own cadences. It also resolves the week-marker freshness check:
its `judgment_points[]` will include an entry keyed `j-week-marker-freshness` whenever
`state/week-changelog/HEADER.md` reads stale, with dispositions `reset_week` /
`update_in_place` — this is the decision Step 8 below acts on. Parse the returned decision
object:

- **`directives[]`** — each is an unconditional action; execute it as you reach it, rendering its
  `detail` into the relevant Weekly Digest output rather than re-deriving the finding by hand.
- **`judgment_points[]`** — genuine EM/PM calls the op cannot resolve (inbound cross-repo memo
  dispositions, non-benign worktree/auto-reconcile findings, and the week-marker
  reset-vs-update-in-place call). Present each to the PM before proceeding past it; never
  auto-pick a disposition.
- **`narration`** / **`next_move`** — surface verbatim as the lead of the Weekly Digest when
  non-empty.

Do not re-derive any check the op already computes — this surface only consumes its output. What
follows is the week-specific residue the op does not cover: the prior-week digest, tracker
staleness, scheduled rechecks, the positioning nudge, priority-setting and goal authoring, and
the HEADER.md reset-or-update mechanics.

## Step 2: Refresh the Exec-Summary

Regenerate this repo's `docs/exec-summary.md` MANAGED sections (identity + progress) from disk so
the board reflects the new week — mirrors the weekly `HEADER.md` refresh. The two HAND sections
(what makes it special, near-term goals) are preserved verbatim:
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/generate-exec-summary"`
Silent if the generator or the file is absent (`repo-setup` Phase 3d.5 creates it on onboarded repos).
Kill-switch for the staleness banner: `COORDINATOR_EXECSUMMARY_STATUS_OFF`.

## Step 3: Read Week-Changelog (prior week)

Glob `state/week-changelog/*.md` excluding `HEADER.md` and `HEADER.priorities.*.md` (the per-writer priorities fragments — not daily changelog files). Sort by filename (date-then-hostname order). Read each daily file.

Surface a brief prior-week digest:
- **Days covered:** count unique dates across daily files.
- **Implemented:** list plans with status `implemented` across all `Plans touched:` fields. (Plan terminal state = code complete on branch; on-main release tracked separately via completion log + handoff `deployment_state: shipped`.)
- **Blockers carried over:** any `Blockers:` fields that weren't cleared by end of week.
- **Priorities met vs. missed (merge-on-read):** glob `state/week-changelog/HEADER.priorities.*.md`, read every fragment found, and union their checklist items into one merged priorities list (each fragment is an independent writer's set — do not treat any single fragment as authoritative). For each merged item, indicate met (plan flipped to `implemented` or handoff closed) or missed. If no fragments exist, report "no priorities were set last week."

If no daily files exist, skip this step: _"No prior-week changelog found — this may be the first run."_

---

## Step 4: Read Tracker — Stalled Workstreams

If `docs/project-tracker.md` exists, read it. Identify workstreams whose referenced branches have had no commits in >7 days — for each branch referenced in the tracker, run `git log --oneline --since="7 days ago" -- <branch> | wc -l`.

Surface stalled workstreams (zero recent commits) as a bulleted list. This gives the PM a concrete picture of what needs attention vs. what's moving.

---

## Step 5: Surface Scheduled Rechecks

Glob `tasks/cookbook-recheck-due-*.md` and any analogous `tasks/*-recheck-due-*.md` files. For files whose date component falls within the coming 7 days, read the first few lines and surface the recheck item.

If none found, skip silently.

---

## Step 6: Competitive Positioning Nudge (absent-or-empty trigger)

Offer-shaped, not a block — fires only when the repo has no positioning data captured yet. Delegates
scaffolding entirely to `coordinator:strategic-self-description-refresh` (its own scaffold-if-absent
path runs `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/coordinator-doc-new" --type strategic-self-description`, schema-validated on write); this
step does not author or duplicate any scaffold logic itself. Trigger logic (including the decline-memory
cooldown) is shared with `/workweek-complete` Step 4j via a single extracted script — see
`check-competitor-positioning-nudge.py`, claude-klabauter-resident at `<claude-klabauter-root>/coordinator/bin/`
(invoked below via its settings-home forwarder, not `coordinator/bin/` in this repo).

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-competitor-positioning-nudge"`

**Trigger is absent-OR-empty ONLY.** If `competitors[]` is already populated, the script emits nothing —
never re-nudge a repo that already has positioning data captured, even if it looks thin or stale (that's
`/workweek-complete` Step 4i's freshness-nudge territory, not this one's). If the PM declines this
specific offer, record the decline so the nudge doesn't recur for the cooldown window:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/check-competitor-positioning-nudge" --record-decline`

---

## Step 7: PM Dialogue — Set Priorities, Author Weekly Goal Artifacts

Present the digest from Steps 1–6 (including any `judgment_points[]` from Step 1 the PM hasn't yet resolved), then ask:

> "Given last week's results and current state, what are 1–3 priorities for this week?"

**Wait for the PM's response.**

If a priority names a fresh, unsized ask (no existing `sizing-object`), point at the `sizing`
skill as the entry point rather than deriving a route here — a cross-reference, not a dependency.

Resolve `<SID_SHORT>` the same way `workweek-trail-scope.py` does: `CLAUDE_SESSION_ID` / `CLAUDE_CODE_SESSION_ID` / `cs_resolve_session_id`, first 8 chars. The current ISO-week (e.g. `2026-W29`) is computed automatically by the CLI below (override via its `--iso-week` flag only if needed).

For **each** PM priority, author one `period=week` goal `.yaml` artifact via the `--type goal` scaffolder, then fill the gap the scaffolder leaves open (it emits `period_value: "PLACEHOLDER"` and leaves `weekly_perceptible`/`goal_id`/`parent_goal_id` commented out — see `coordinator-doc-new`'s `_scaffold_goal`). SESSION-DISAMBIGUATE the output path with `<SID_SHORT>` so two concurrent same-week sessions authoring same-titled priorities never clobber one file:

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-start-goal-and-priorities" scaffold-goal --title "<priority title>" --sid-short "<SID_SHORT>"`
Prints the authored goal artifact's path to stdout — capture it as this priority's `_GOAL_OUT` for Step 8.

Confine authored prose to the `objective` field (the priority's title/text, one sentence) and each key result's `text` field — no `body:` field; the goal schema has none. Leave `parent_goal_id` commented/null unless the PM names a parent quarter/repo OKR to backlink. This runs automatically as part of the ceremony for each priority — it adds NO new manual PM action beyond answering the priorities question.

Then write the PM's answer verbatim (as a checklist) to this session's OWN priorities fragment, `state/week-changelog/HEADER.priorities.<SID_SHORT>.md` — never to a shared HEADER.md section (a second collaborator's `/workweek-start` the same week must not overwrite this session's priorities). **This fragment is now a rendered INDEX/pointer to the authored goal artifacts, not the canonical store** — each checklist line links to the goal `.yaml` path it produced, e.g.:

```markdown
- [ ] <priority 1 title> — state/goals/<date>-<slug>-<SID_SHORT>.yaml
- [ ] <priority 2 title> — state/goals/<date>-<slug>-<SID_SHORT>.yaml
```

Mirror to `docs/project-tracker.md` if it exists (append under a `## Week of YYYY-MM-DD` heading or update an existing one). The goal artifacts are canonical; the fragment is a rendered index; the tracker copy is for visibility.

<!-- Goal events are emitted exactly once from Step 8, covering both the reset and
     update-in-place branches. Do NOT add an emission block here. -->

### Goal-Coverage Sweep (propose-stubs)

<!-- sole ritual home for THIS sweep — a distinct sweep from the initiative-govern
     sweep at /workweek-complete Step 4; do not conflate the two. That sweep
     clusters unattached records (initiative == null); this one checks whether
     ACTIVE GOALS have any work advancing them at all. -->

After Step 7 authors this week's goal artifacts, run the read-only coverage
scan over all active goals (not just this week's) to surface any goal with
zero in-flight work advancing it, via `bin/goal-coverage-scan.py --format text`.

**Surface to PM:** for each zero-coverage goal the scan reports, prompt individually:
_"Goal `<goal title/id>` has no in-flight work — spin off a stub? (routes to `/spinoff` or `/roadmap-planning`)"_

**Propose-only, PM-gated.** `/spinoff` and `/roadmap-planning` are keyword-gated
primitives — this step does NOT auto-invoke either. Surface the candidate and
wait for the PM's literal invocation (per `## Challenging the PM` — paraphrase
is not authorization).

**If no zero-coverage goals:** note _"Goal-coverage sweep: N active goals, all have in-flight work."_ and continue.

**If no active goals exist:** skip silently (the scan reports "No active goals found" — nothing to surface).

---

## Step 8: Reset-or-Update Decision

This is the critical branch in the command. Step 1's brief already resolved WHICH branch applies
— consume its `j-week-marker-freshness` judgment point (dispositions `reset_week` /
`update_in_place`) rather than re-deriving it from HEADER.md's date fields. If the brief carried
no such judgment point, HEADER.md read fresh — treat as `update_in_place` with no reset needed
(still run the "In both cases" commit step below, since the PM may still have set priorities in
Step 7). Present the disposition to the PM before acting on it.

**`reset_week`** — a `/workweek-complete` has occurred since the last `/workweek-start`, meaning
we are starting a genuinely new week:

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
4. Write this session's priorities fragment, `state/week-changelog/HEADER.priorities.<SID_SHORT>.md` (per Step 7 — `<SID_SHORT>` resolved the same way). This fragment is now a rendered INDEX/pointer to the goal artifacts Step 7 authored, not the canonical store:
   ```markdown
   - [ ] <priority 1 title> — state/goals/<date>-<slug>-<SID_SHORT>.yaml
   - [ ] <priority 2 title> — state/goals/<date>-<slug>-<SID_SHORT>.yaml
   - [ ] <priority 3 title> — state/goals/<date>-<slug>-<SID_SHORT>.yaml
   ```

   After writing the fresh HEADER.md and the priorities fragment, for each priority's authored goal artifact (Step 7), emit a structured weekly goal event by running — the emission sources `--period-value`/`--text` FROM the authored artifact's `period_value`/`objective` fields rather than raw priority text, so the emitted event and the on-disk goal agree byte-for-byte:
   `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-start-goal-and-priorities" emit-goal-event --goal "<this priority's authored goal artifact path from Step 7>"`
   This runs automatically as part of the ceremony — it adds NO new manual PM action.

**`update_in_place`** — no `/workweek-complete` has occurred since the last `/workweek-start`; this is a mid-week re-run:

1. Write (or overwrite) THIS session's own priorities fragment, `state/week-changelog/HEADER.priorities.<SID_SHORT>.md`, with the new priorities from Step 7. Do NOT touch any other session's fragment — a re-run only ever overwrites the fragment matching this session's own `<SID_SHORT>`, never another collaborator's.
2. Update `Last /workweek-start:` to today's date in HEADER.md. HEADER.md's own `Priorities (from /workweek-start):` line stays a pointer to the fragments (no content change needed there).
3. Leave daily files untouched.
4. For each priority's authored goal artifact (Step 7), emit a structured weekly goal event (single-emission, A-F9), sourced from the artifact:
   `"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-start-goal-and-priorities" emit-goal-event --goal "<this priority's authored goal artifact path from Step 7>"`

**In both cases,** commit the HEADER.md change, this session's priorities fragment, AND this session's authored goal artifacts:
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-start-goal-and-priorities" commit-priorities --sid-short "<SID_SHORT>"`

If a full reset moved daily files, include them in the same commit:
`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-start-goal-and-priorities" commit-archive-reset --prior-week-start "<prior-week-start>"`

---

## Step 9: Project Post-Ceremony Command Hook

Run the generic per-repo post-ceremony command hook so a consumer repo's opt-in `workweek_start_post_command:` (declared in `coordinator.local.md`) runs advisory, non-blocking, before the chain into `/workday-start`. This MUST run here — before Step 10 — else it would run after the entire chained `/workday-start` ceremony instead of at `/workweek-start`'s own settle point.

`"${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/workweek-start-goal-and-priorities" ceremony-hook --ceremony workweek-start`

The hook is opt-in: if the repo has not declared `workweek_start_post_command:` in `coordinator.local.md`, `$_HOOK_OUT` is empty and this step emits nothing. A configured command's summary line (`Post-workweek-start hook: ran <redacted-cmd> (exit N)`) is captured in `$_HOOK_OUT` and echoed into this step's own output — carry it forward into the Output section below (see the trailing "**Post-ceremony hook:**" line, rendered only when non-empty).

---

## Step 10: Chain into /workday-start

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
**Handoff/health advisories:** [Step 1 directives[] renders, or "none"]
**Upcoming rechecks:** [list or "none"]
**This week's priorities:**
  - [ ] Priority 1
  - [ ] Priority 2
  - [ ] Priority 3
**HEADER.md:** [reset (archived prior week) / updated in place]
```

If Step 9's `$_HOOK_OUT` was non-empty, append it as a standalone trailing line after the summary above (before the chained `/workday-start` output):

```
**Post-ceremony hook:** [Step 9's $_HOOK_OUT line — e.g. "Post-workweek-start hook: ran <redacted-cmd> (exit N)"]
```

Omit this line entirely when `$_HOOK_OUT` was empty (the common opt-in no-op case).

---

### Relationship to Other Commands

- **`/workday-start`** — tactical daily orient. Different ceremony, but `/workweek-start` chains into it (Step 10) because the week's first session is also a workday.
- **`/workweek-complete`** — the weekly close; it resets HEADER.md and archives daily files as part of its Step 14. `/workweek-start` detects that reset (via Step 1's `j-week-marker-freshness` judgment point) and does a full re-init.
- **`/pickup`** — gains a "while you were away" surface from the week-changelog; reads HEADER.md to determine week bounds.
