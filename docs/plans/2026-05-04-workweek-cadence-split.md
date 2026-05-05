# Workweek Cadence — Split `/workday-complete`, Add Weekly Bookends

**Date:** 2026-05-04
**Status:** Execution complete — pending verification (executor completed 2026-05-04)
**Author:** EM (Claude)
**Reviewer:** Patrik (APPROVED_WITH_NOTES, 2026-05-04) — all findings resolved below

## Motivation

`/workday-complete` is now 306 lines doing double duty: daily housekeeping (commit-clean, branch consolidation, archive audit) AND release-grade ceremony (full `/update-docs` sweep, Codex review gate, shellcheck sweep, plugin validation, improvement queue triage). On a setup with multi-day workstreams, the heavy half rarely fires at the right cadence — workdays don't end on workstream boundaries, so the heavy ceremony either gets skipped or pulled forward inappropriately.

Two fixes, one shape:

1. **Lighten `/workday-complete`** to branch-only daily wrap.
2. **Add `/workweek-start` and `/workweek-complete`** as PM-invoked weekly bookends, gated by staleness.
3. **Add `tasks/week-changelog.md`** so the weekly EM has a structured trail and doesn't reconstruct the week from `git log`.

## Trigger Doctrine

`/workweek-complete` is **PM-invoked**. There is no auto-fire. But `/workday-complete` and `/workday-start` SURFACE staleness so the PM knows when it's overdue.

**Staleness signal (both must trigger to nudge):**
- ≥ 5 calendar days since last `/workweek-complete` (read from `tasks/week-changelog.md` header), AND
- ≥ 15 commits since the last weekly-reset SHA, measured as `git rev-list --count <reset-sha>..HEAD` where `<reset-sha>` is the `Prior week released: ... (commit <sha>, ...)` value in the changelog header. Branch-relative counts are wrong on this setup — `work/{machine}/{YYYY-MM-DD}` branches reset daily.

If the file doesn't exist, treat as "never run" — first nudge fires after the thresholds elapse from repo init.

`/workweek-start` is also PM-invoked. Same staleness logic surfaces it as the recommended next ceremony when overdue.

## Handoffs and the Changelog

Handoffs are the atom; the changelog is the weekly index over them. The week-changelog does not duplicate handoff content — it points to the handoffs that already exist and surfaces the few fields a weekly reader needs without opening each one.

This frames the workweek-cadence work as a *thin index layer over handoff/pickup*, the existing backbone of session continuity. `/workday-complete` synthesizes the daily block from today's handoffs and `/daily-review` summary, not from fresh agent prose. `/workweek-complete` reads the changelog as an index and follows the pointers into handoffs for deep evidence. `/pickup` gets enhanced to read recent changelog blocks for ambient context across other workstreams (gated on handoff age — see below).

Concretely:
- Daily-block `Decisions:` and `Blockers:` are extracted from today's handoffs, not re-authored
- Daily-block `Handoffs:` field lists today's handoff filenames as pointers
- `/pickup` gains a "while you were away" surface: when the named handoff is from a *prior* day (i.e., not a same-day baton pass), scan the changelog for blocks dated since the handoff and emit a one-liner per other workstream that shipped or moved. Same-day handoffs skip this surface — straight baton pass, no context drift.

## File Layout: `tasks/week-changelog/`

**Per-machine daily files**, not a single shared file. Concurrent `/workday-complete` invocations from different machines on the same calendar day would otherwise produce overlapping `## YYYY-MM-DD` blocks that git can't cleanly merge. Per-machine files merge trivially because no shared file is touched.

```
tasks/week-changelog/
  HEADER.md                          # week metadata (set by /workweek-complete, read by all)
  YYYY-MM-DD-{hostname}.md           # daily block, one per machine per day
  YYYY-MM-DD-{hostname}.md
  ...
```

`/workweek-start` and `/workweek-complete` glob the directory in date-then-hostname order to read the week's record. `/workweek-complete` archives the entire directory contents to `archive/week-changelogs/YYYY-MM-DD/` on reset.

**Format — `HEADER.md` (set by `/workweek-complete`, updated by `/workweek-start`):**
```markdown
# Week Changelog

**Week starting:** YYYY-MM-DD
**Prior week released:** vX.Y.Z (commit abc1234, YYYY-MM-DD)
**Last /workweek-start:** YYYY-MM-DD  (cleared by /workweek-complete on reset)
**Priorities (from /workweek-start):**
- [ ] Priority 1
- [ ] Priority 2
- [ ] Priority 3
```

The `Last /workweek-start` line disambiguates `/workweek-start` re-runs: if it's set and no `/workweek-complete` has occurred since, `/workweek-start` updates priorities in place; otherwise it does a full reset.

**Format — daily file `YYYY-MM-DD-{hostname}.md` (appended by `/workday-complete`):**
```markdown
## YYYY-MM-DD — {hostname}

**Branch:** work/{hostname}/YYYY-MM-DD
**Commits:** N (range: abc1234..def5678)
**Scope:** <one-line summary, taken from $ARGUMENTS or derived from commit subjects>
**Plans touched:** docs/plans/2026-XX-XX-foo.md (status: in-progress|shipped|reverted)
**Handoffs:** tasks/handoffs/YYYY-MM-DD-foo.md, tasks/handoffs/YYYY-MM-DD-bar.md  (pointers; deep evidence stays in the handoff)
**Decisions:** <bullet list — extracted from today's handoffs and /daily-review summary, not re-authored>
**Blockers:** <extracted from handoffs, or "none">
**Validation:** validate=<exit-code> plugin-suite=<exit-code>  (auto-filled from gate exit codes — NOT LLM-authored)
**Links:** archive/daily-summaries/YYYY-MM-DD.md, archive/completed/YYYY-MM.md
```

Fixed sections, no free-form prose. `Validation:` is mechanically populated from the exit codes of `/validate` and the plugin suite — if either failed, `/workday-complete` never reaches the changelog-append step (gates are blocking), so non-zero values appear only when this doctrine is bypassed. Weekly EM scans the bullets, not the connective tissue.

## Migration: Step Routing

Current `/workday-complete` steps, classified:

| Step | Current command | New home | Reasoning |
|---|---|---|---|
| 1 | `/update-docs` (full) | **weekly** | Heavy multi-phase sweep. Dropped from daily entirely — `/handoff` already archives handoffs at their natural trigger and tracker is touched when the work touches it. A daily `--scope=today` variant would duplicate work done elsewhere. |
| 1.5 | `/validate` | **daily** | Must pass to push. Non-negotiable. |
| RAG staleness | nudge | **daily** | Cheap, informational. |
| 1.7 | improvement-queue triage | **weekly (action) + daily (depth nudge)** | Actual triage is weekly. Daily emits a one-line nudge `"Improvement queue: K entries (oldest YYYY-MM-DD) — consider /workweek-complete"` when depth ≥ 5, no triage action. Prevents the queue from sitting at 18-21 days when weekly stalls. Update `coordinator/CLAUDE.md` to match. |
| 2 | Branch consolidation | **daily** | Reduces branch sprawl. Cheap. |
| 3 | `/daily-review` | **daily** | The strategic daily artifact feeds the weekly. |
| 3.4 | Plugin validation suite | **daily** | Blocking gate — hook regressions caught early. |
| 3.5 | scc stats | **weekly** | Daily delta is noise; weekly trend is signal. |
| 3.6 | Archive audit | **daily** | Daily archive is dated daily. Stays. |
| 3.7 | ShellCheck sweep | **weekly** | Lint accumulates fine over a week. |
| 3.8 | Codex review gate | **weekly** | Release-grade second opinion. Pairs with merge-to-main. |
| 3.9 | Tier usage report | **daily** | By-definition daily aggregate. |
| 4 | Final summary | **daily** | Stays — but ALSO appends to week-changelog. |
| NEW | Week-changelog append | **daily** | New step. |
| NEW | Staleness nudge | **daily** | New step in summary. |

## Command Skeletons

### `/workday-complete` (rewritten, target ~150 lines)

1. `/validate` — blocking gate (capture exit code for changelog Validation field)
2. RAG staleness nudge (informational)
3. Branch consolidation (sync-main, merge sibling branches, rebase, force-with-lease push)
4. `/daily-review` — produces `archive/daily-summaries/YYYY-MM-DD.md`
5. Plugin validation suite — blocking gate (capture exit code for changelog Validation field)
6. Archive audit (`archive/completed/YYYY-MM.md` reconciliation)
7. Tier usage report
8. **NEW: Improvement-queue depth nudge (read-only)** — if `~/.claude/tasks/coordinator-improvement-queue.md` has ≥5 active entries, emit one-line nudge in summary; no triage action
9. **NEW: Append to `tasks/week-changelog/YYYY-MM-DD-{hostname}.md`** — synthesize the block from today's handoffs (`tasks/handoffs/YYYY-MM-DD-*.md`) + the `/daily-review` summary. Extract Decisions and Blockers from handoff content; do not re-author. Auto-fill Validation from steps 1/5 exit codes. Per-machine file = no concurrent-write conflicts.
10. **NEW: Weekly staleness check** — `git rev-list --count <weekly-reset-sha>..HEAD` against the SHA in `tasks/week-changelog/HEADER.md`; if ≥5 days AND ≥15 commits, surface: _"Weekly is stale: D days, N commits since last `/workweek-complete`. Run `/workweek-complete` when ready."_
11. Final summary

**Drops:** `/update-docs` (entirely, no `--scope=today` variant), improvement-queue triage action (depth nudge stays), scc, shellcheck, Codex review gate.

### `/workweek-start` (new, ~120 lines)

PM-facing strategic orient. Distinct from `/workday-start` (tactical).

1. **Read week-changelog** for the prior week (if any). Surface: shipped count, blocker carryover, priorities-met vs priorities-missed.
2. **Read tracker** (`docs/project-tracker.md`). Surface stalled workstreams (no commits in their referenced branches in >7 days).
3. **Orphan sweep** — handoffs older than 7 days in `tasks/handoffs/`, plans in `docs/plans/` with status: draft and no commits in >14 days.
4. **Surface scheduled rechecks** due in the coming week (existing pattern: `tasks/cookbook-recheck-due-*.md`, etc).
5. **PM dialogue** — ask: "Given [shipped] / [stalled] / [carryover], what are 1–3 priorities for this week?" Write the answer to `tasks/week-changelog/HEADER.md` (replacing prior priorities). Mirror to `docs/project-tracker.md` if it exists; HEADER.md is canonical.
6. **Reset-or-update decision** — read `Last /workweek-start:` and `Prior week released:` lines from HEADER.md. If a `/workweek-complete` has occurred since the last `/workweek-start` (i.e., HEADER.md was rewritten by the weekly), do a full reset: archive `tasks/week-changelog/*.md` (except HEADER.md) to `archive/week-changelogs/<prior-week-start>/`, then write the new HEADER.md. Otherwise (mid-week re-run): update priorities in place, refresh `Last /workweek-start:` to today, leave daily files alone.

### `/pickup` enhancement (existing skill — small additive change)

After reading the named handoff, check the handoff date:
- **Same day (handoff date == today):** straight baton pass — skip the changelog surface.
- **Prior day (handoff date < today):** glob `tasks/week-changelog/*.md` for daily files dated *since* the handoff (exclusive). For each, emit a one-line "while you were away" surface: `<date> <hostname>: <Scope>` plus shipped-plan pointers. Cap at ~10 lines total; if more, summarize as "(N more days — see `tasks/week-changelog/`)".

Implementation cost: ~20 lines added to `/pickup`. Reuses the same per-machine-file globbing pattern as `/workweek-complete`.

### `/workweek-complete` (new, ~250 lines — the heavy one)

PM-invoked, release-grade. Reads week-changelog as the ground truth — does NOT reconstruct.

1. **Read week-changelog** — this is the canonical record of what shipped. Surface to PM for confirmation: "Week covers D days, N commits, M shipped workstreams. Proceed?"
2. **`/validate` + plugin suite + build** — full validation, blocking
3. **`/update-docs`** — full multi-phase sweep
4. **Improvement-queue triage** (moved from daily) — with the ≥5 / ≥14d threshold check
5. **scc snapshot** — record in `tasks/code-stats-history.md` (or similar) for trend tracking
6. **ShellCheck sweep** — clean lint accumulated over the week
7. **Codex review gate** — second-opinion on the week's diff against main
8. **Tracker reconciliation** — mark shipped workstreams complete, update statuses
9. **Release notes** — drafted from week-changelog + `archive/completed/YYYY-MM.md` entries; written to `archive/release-notes/YYYY-MM-DD-vX.Y.Z.md`
10. **Version bump** — propose semver based on changelog content (PM confirms)
11. **`/merge-to-main`** — only after PM confirms release notes and version
12. **Archive consolidation** — invoke `coordinator:artifact-consolidation` on shipped plans/handoffs
13. **Health survey** — full run
14. **Reset week-changelog** — archive `tasks/week-changelog/*.md` (all daily files + old HEADER) to `archive/week-changelogs/<week-start>/`. Write fresh `tasks/week-changelog/HEADER.md` with the released version + reset SHA + cleared `Last /workweek-start:` line.
15. **Final summary** — what shipped, what's tracked for next week, links to release notes

## Resolutions to Open Questions (post-Patrik-review)

1. **Staleness thresholds:** 5 days AND 15 commits, measured from the last weekly-reset SHA via `git rev-list --count`. Branch-relative count was wrong — daily branches reset, so the count would never accumulate (Patrik finding #1, AUTO-FIX applied).
2. **Daily `/update-docs`:** dropped entirely. No `--scope=today` variant. `/handoff` already archives at natural trigger; tracker is touched when work touches it. (Patrik finding #2.)
3. **Version bumps:** informal. Track "released X commits since last release" + a date-named release-notes file. Formal semver/tag policy is out of scope for this change — revisit if it's needed.
4. **Concurrent-EM safety:** **per-machine daily files** under `tasks/week-changelog/`, not a single shared file. Eliminates the merge-conflict class entirely (Patrik finding #0, the major one). HEADER.md is the only shared file and is touched only by the two weekly commands, not by daily.
5. **Priorities location:** `tasks/week-changelog/HEADER.md` canonical, mirrored to `docs/project-tracker.md` if it exists.

## Patrik Findings Summary

| # | Finding | Resolution |
|---|---|---|
| 0 | Concurrent append unsafe (major) | Per-machine daily files — no shared write target |
| 1 | Commit-count baseline wrong | AUTO-FIX applied — measured from weekly-reset SHA |
| 2 | Drop daily `/update-docs` entirely | Accepted — no `--scope=today` variant |
| 3 | Schema: add `Branch:`, auto-fill `Validation:` | Accepted — `Validation:` populated from gate exit codes, not LLM-authored |
| 4 | Improvement-queue triage doctrine drift | Accepted — daily depth nudge (read-only) + weekly triage; update `coordinator/CLAUDE.md` |
| 5 | `/workweek-start` re-run trigger ambiguous | Accepted — added `Last /workweek-start:` line to HEADER.md |

## Implementation Plan

**Estimate:** one focused afternoon, dispatched not typed.

1. ~~Plan review — PM approval~~ — done
2. ~~Patrik review~~ — done, APPROVED_WITH_NOTES, all findings resolved
3. **Implement:**
   - Scaffold `tasks/week-changelog/` (HEADER.md template + initial empty state)
   - Author `bin/check-weekly-staleness.sh` (consumed by daily nudge + both weekly commands)
   - Rewrite `/workday-complete` (drop heavy steps; add changelog append, depth nudge, staleness check)
   - Author `/workweek-start`
   - Author `/workweek-complete`
   - Update `coordinator/CLAUDE.md` doctrine section on cadence + improvement-queue triage rule
   - Optional wiki guide: `docs/wiki/workday-workweek-cadence.md`
4. **Spot-check** — verify `/daily-review` summary output is structured enough for daily-block field extraction (Patrik gap-flag); if not, either constrain `/daily-review` output or relax the auto-extract requirement
5. **Test** — dry-run on the current branch; verify changelog directory format is parseable and weekly commands can act on it without git-archaeology
6. **Patrik review** of rewritten command files
7. **Percolate** — same files exist in `plugins/coordinator-claude/` (this repo) and need to flow to publish repo on next release

**Files touched (estimate):**
- 3 commands (`workweek-start.md`, `workweek-complete.md`, rewritten `workday-complete.md`)
- 1 small enhancement to `/pickup` (existing skill — "while you were away" surface, gated on handoff age)
- 1 new bin script (`bin/check-weekly-staleness.sh`)
- 1 new tasks directory convention (`tasks/week-changelog/HEADER.md` template + initial empty state)
- 1 doctrine update (`coordinator/CLAUDE.md` — cadence section + improvement-queue triage rule + "handoffs are the atom, changelog is the index")
- 1 optional wiki guide (`docs/wiki/workday-workweek-cadence.md`)
- Test additions if `tests/plugins/` covers command structure

## Risks

- **Bifurcation risk.** Two daily ceremonies that don't compose cleanly will cause one to be skipped. Mitigation: daily must remain genuinely lightweight (~150 lines, <5min runtime), weekly must read changelog without reconstruction.
- **Week-changelog stale-write.** If `/workweek-complete` doesn't reset cleanly, next week's daily files append into prior week's directory. Mitigation: HEADER.md `Week starting:` is authoritative; daily reads it; if today >`Week starting:` + 14d, daily emits a hard warning ("HEADER.md is stale — was `/workweek-complete` skipped?") and refuses to append until resolved.
- **Concurrent EMs from different machines.** Resolved by per-machine daily files (Patrik finding #0). HEADER.md is touched only by weekly commands, which are PM-invoked and serial.
- **PM forgets weekly.** Without auto-fire, `/workweek-complete` may go unrun for weeks. Mitigation: daily nudge intensifies past thresholds (mild at 5d/15c, visible at 10d/30c, full warning at 14d/50c — same shape as debt-triage doctrine).

## Recommendation

Build it. The current `/workday-complete` is doing too much, and multi-day workstreams need a release cadence that doesn't tie to calendar days. The week-changelog is the load-bearing innovation — it converts "weekly EM does archaeology" into "weekly EM consumes a structured ledger."

Cleared to implement.
