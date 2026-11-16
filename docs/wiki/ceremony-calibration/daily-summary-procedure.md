---
name: daily-summary-procedure
status: active
---


# Daily Summary Procedure

Reference wiki for `/workday-complete` Step 6b-7, holding the heavy-weight artifacts the command body walks through inline.

> Reference wiki for `/workday-complete` Step 6b-7. Heavy-weight artifacts extracted here to keep the
> command body under 200 lines.
>

---

## Weekly Reviewer — Sonnet Observer, No Persona Routing

The strategic review runs once a week in `/workweek-complete` Step 7b, as an **unnamed Sonnet
worker** (`general-purpose`, `model: "sonnet"`). It is the one agent the daily/weekly doc path
keeps: its alignment notes and architectural-risk flags need model judgment. There is no
domain→persona routing: personas (the Game Dev Reviewer / the Front-End Reviewer / the Data Science Reviewer / the Staff Engineer) are Opus-only, and the daily
ceremony dispatches no agent.

**Role: observer, not judge.** The worker leaves a **paper trail for the Staff Engineer** — alignment notes,
debt candidates, architectural-risk *flags*. It renders no final architectural verdict. The Opus
The Staff Engineer arch pass (`/workweek-complete` Step 8) consumes the debt-backlog rows tagged
`weekly-arch-review` and the `## Strategic Review` section of `WEEK-SUMMARY.md`, and adjudicates.
Domain matters only for *vocabulary* — a UE-heavy week's observer should speak UE. No commit-count
floor: the observer runs every week, however few commits.

---

## Daily Summary Script Contract

Script first, no model call, no analyst dispatch (`docs/decisions/DR-1649-bookkeeping-is-script-first-under-a-1m-bar.md`).
The project-rag `plans-completed --project-root . [--since <when>] [--until <when>]` door lists the plans whose
`status` flipped to a terminal value in a commit inside the window (default: the 24h ending now),
sorted by sizing (XXL first, `?` last), each with the sha that recovers a plan distill has deleted;
the EM appends them below the script's summary. Bounded previews: a reader of a plan takes at most
~10k chars of it, and never fans out over the corpus. The strategic observer stays weekly (Step 7b).

`coordinator/scripts/daily-doc-rollup.py` writes the daily summary and the completion-log
clusters; no agent runs. Both subcommands print a JSON report `{written, skipped, elapsed_s}` and
exit 0 on success, 1 on git failure.

**`summary --repo <root> --day YYYY-MM-DD [--machine <slug>] [--backfilled] [--force]`** writes
`archive/daily-summaries/<day>-<machine>.md` (per-machine naming, mirroring
`state/week-changelog/<date>-<machine>.md`); an existing summary is not overwritten without
`--force`. Machine: `--machine`, else `$COORDINATOR_MACHINE`, else the machine resolver.

- **Frontmatter** is the Rollup Frontmatter Standard below. `commits` and `covered_tip_sha` come
  from `git log --no-merges` over the day window; `covered_tip_sha` is the newest commit in that
  window, `none` when the window is empty. Never hand-type it.
- **Work Completed** is residue-first (§ Source Discipline): one line per that day's
  `archive/completed/` entry (title, nature, its SHAs), then the commits no entry claims, grouped
  by subject prefix with short SHAs. A mechanical assertion that every day entry appears in the
  output fails the run (exit 1) when one is missing.
- **Systems Affected** is `git diff --numstat` grouped by top-level directory.
- The script writes no `## Architectural Decisions` section: that is judgment prose, and the
  weekly observer reads the week's diffs for it.

**`clusters --repo <root> --day YYYY-MM-DD`** adds a `narrative:` field on the lead (earliest)
entry of each `chain:` value with two or more `archive/completed/` entries that day whose lead
carries none: members and SHAs in date order, at most 300 words, never a new entry file. A lead
entry already carrying `narrative:` is skipped, so a rerun is a no-op.

**Coverage anchor (required):** `covered_tip_sha` is the completeness anchor a downstream backfill
scan reads to detect under-covered days. A summary MISSING this field on a day that has committed
work is treated as a GAP (fail-loud) by the scan — never as "unknown → pass".

**Anchor semantics — content-true tip, not actual tip:** `covered_tip_sha` MUST be the newest
commit the summary's content actually describes. The script's summary covers the whole day
window, so its anchor is the window tip; a hand-written partial summary anchors to the tip of the
range its prose covers, not the session-end tip. → See
`## Coverage Anchor Semantics and Phase A0 Backfill Deductions` below.

**Machine-defer convention (optional):** When a summary covers a day where work was actually
done on a different machine, add `defers_to: <machine-slug>` at line start in the summary
body (no `>` blockquote prefix — the backfill scan reads this field with a line-anchor grep):

```
defers_to: machine-a
```

This declares that `state/week-changelog/<date>-machine-a.md` covers this machine's work for
the day. **The backfill scan enforces the pointer:** if `state/week-changelog/<date>-<target>.md`
does not exist on disk, the scan emits `DANGLING-DEFER: <date> <this-machine> -> <target>` to
stderr and a `DANGLING-DEFER` TSV row to stdout — it never silently trusts a defer whose
changelog target is absent.

---

## Coverage Anchor Semantics and Phase A0 Backfill Deductions


### Anchor-semantics doctrine

`covered_tip_sha` MUST be the newest commit the summary's **content actually describes** (the
*content-true tip*), NEVER blindly the day's actual tip or the scan's `actual_tip` column value.
This is the whole ballgame: the backfill scan trusts the anchor, not the prose. A summary anchored
to a tip beyond its content silently certifies that uncovered work has been recorded — the gap
detector is defeated, not satisfied.

**Mechanical injection (Phase A0)** is safe only for a summary whose content already covers the
full day's commit range. For partial summaries (prose stops mid-day), anchor to the content-true
tip instead — this correctly re-flags the gap on the next scan — or route the date to a Phase A
content-assembly pass. That pass assembles from existing completion entries (authored truth,
not re-derivation) before a mechanically-correct anchor is set.

### Phase A0 content-completeness guard

Before mechanically injecting an anchor into a pre-existing summary, run a cheap heuristic to
check whether the prose is plausibly complete for the day's commit range (defense in depth):

- Count completion entries for the date: `query-completions --where created=<date>` (or
  `bin/query-records` equivalent).
- Count `## Work Completed` bullets in the summary file.
- **Large mismatch** (e.g. completion entries ≥ 2× Work-Completed bullets AND entries ≥ 3) →
  **CONTENT-GAP**: do NOT inject a masking anchor. Surface the date as requiring content-assembly
  (Phase A). Log the entry count and bullet count for auditability.
- **Commit-density signal** (complement to the completion-count heuristic): count commits dated
  to `<date>` reachable from the tip SHA (`git log <tip> --since="<date> 00:00:00"
  --until="<date> 23:59:59"`), then count distinct commit SHAs cited in the summary that resolve
  and are ancestors of the tip. **Cited count < 50% of range count (range ≥ 3)** → **CONTENT-GAP**
  (exit 30). A **morning-run/tail-wrap/spilled-past-midnight note** in the summary body is a
  corroborating near-certain gap signal when the range is large (≥ 10 commits; exit 30
  independently). The `# Daily Summary` H1 match is case-insensitive.

The injection script exits 30 on CONTENT-GAP; the Step 3.5 caller routes that date to the
content-assembly path, not the re-derivation path.

### Descendant-tip machine-row deduction

After branch consolidation, multiple machine branches (`work/machine-a/*`, `work/machine-b/*`) share
the same commit ancestry — `git log` on each branch-glob walks identical commits. The backfill scan
then emits duplicate gap rows (one per machine) for the same date.

One anchor in the shared flat `archive/daily-summaries/YYYY-MM-DD.md` closes **every machine row**
for that date. The deduction:

- **Machine that owns the descendant tip:** `recorded == actual` → covered.
- **Machines with an older tip:** the recorded (descendant) SHA is NOT an ancestor of their older
  tip → `merge-base --is-ancestor` is false → the scan treats the branch as diverged → **not a gap**.

Phase A0 therefore injects the **descendant tip** (the `actual_tip` value that is a descendant of
/ equal to all other machines' tips for that date), not any individual machine's tip. Do NOT
manufacture per-machine `YYYY-MM-DD-<machine>.md` duplicates for days covered by a legacy flat
summary — the flat file is canonical; the machine axis collapses post-consolidation.

---

## Weekly Strategic Observer Prompt Template

Dispatched once per `/workweek-complete` Step 7b, before Step 8, as an **unnamed Sonnet worker**
(`general-purpose`, `model: "sonnet"`) — **never a named persona**. The worker is an **observer
leaving a paper trail for the Staff Engineer**, not a judge. It flags candidates; the Opus the Staff Engineer arch pass
adjudicates.

---

**Weekly observer instructions:**

You are an unnamed Sonnet strategic observer for the weekly wrap. Read the week's work and project
strategic documents and leave a **paper trail** — alignment notes, debt candidates, and
architectural-risk *flags* for the Opus arch pass to adjudicate. **Render no final
architectural verdict** and do **not** claim a persona identity. **This is NOT a code review** — no
inline code fixes.

1. **Read** the week's `archive/daily-summaries/*.md` (each day's Architectural Decisions section
   first) and `git diff <week-start-baseline>..HEAD --stat` for architectural context; read the
   diff itself only for a flagged seam.

2. **Read project strategic documents** (check each, skip silently if missing):
   - `ROADMAP.md`, `docs/roadmap.md`, or `docs/ROADMAP.md`
   - `VISION.md` or `docs/vision.md`
   - `state/workstreams/` (query directly — the rendered `docs/project-tracker.md` view is retired)

3. **Assess** the week's work against the strategic direction. Focus on:
   - **Alignment:** Does the week's work advance the roadmap? Does anything conflict?
   - **Lock-in:** Do any decisions create accidental constraints that the roadmap/vision would
     want to avoid?
   - **Bridging opportunities:** Are there low-cost opportunities to make the week's code more ready
     for planned future capabilities?
   - **Debt patterns:** Is technical debt accumulating in a direction that should be documented?

   **A negative claim about a sibling repo is read there or not made.** "No fix has landed", "no
   guard shipped", "still unguarded" — absence in THIS repo's history is not absence. Resolve the
   sibling (`machine-local get repos.<key>`) and search it (`git -C <path> log --grep`), or write
   the finding without the negative. Nothing denies read access to a sibling checkout; an
   unchecked cross-repo negative sends a peer team chasing a bug they already closed.

4. **Write** findings as one section appended to
   `archive/week-changelogs/<week-start>/WEEK-SUMMARY.md` (exactly one `## Strategic Review`
   heading; no daily summary receives one):

   ```markdown
   ## Strategic Review (Sonnet weekly observer)

   > Observer read: [list which strategic docs were found and read]

   ### Alignment Assessment
   - [Where the week's work advances the roadmap]
   - [Where the week's work diverges or creates friction]

   ### Technical Debt Identified
   - [Debt item — what, why it matters, suggested future action]
   - ...

   ### Architectural-Risk Flags (for the Staff Engineer arch pass)
   - [Candidate concern — flagged, NOT adjudicated. State what to look at and why it might matter.]
   - ...

   ### Bridging Opportunities
   - [Things that could be done to better connect current state to vision]
   - ...
   ```

   If no strategic docs exist, note that and focus purely on architectural principles
   (SOLID, coupling, extensibility).

5. **Debt backlog entries:** For any finding that warrants tracking, write a per-entry YAML file
   via `coordinator-queue-append --schema debt-backlog`. Do NOT append to a markdown file.
   Required fields:
   - **`title`** — one-line noun-phrase summary of the finding
   - **`body`** — multi-line prose: what was observed, the structural gap, context (`body: |` block scalar)
   - **`source`** — `workweek-complete/step7b/sonnet-observer/{date}`
   - **`risk`** — consequence of leaving the debt unaddressed
   - **`proposed_action`** — what the EM or a future executor should do about it
   - **`status`** — `open`
   - **`created`** — today's date (YYYY-MM-DD)
   - **`tags: [weekly-arch-review]`** — for any architectural-risk flag, so the Staff Engineer arch pass
     (`/workweek-complete` Step 8) picks it up.

   This produces `state/debt-backlog/<date>-<slug>.yaml`. See `docs/wiki/schema-and-validation-contracts/debt-backlog-schema.md`
   for the full field reference and an example entry.

---

## Health Ledger Entry Schema

After the summary script completes, update `state/health-ledger.md`:

1. If it doesn't exist, create it with this shape (two audit clocks above a per-system table —
   the schema established by the weekly-gate/arch-survey restructure; do **not**
   conflate the clocks):

   ```markdown
   # Health Ledger

   **Last full audit:** (none — run /architecture-survey)
   **Last targeted audit:** <date or none>
   **Next rotation target:** <system>

   | System | Grade | Last Audited | Notes |
   |--------|-------|-------------|-------|
   ```

2. If a system was touched by today's commits but has no row yet, add it with grade `?` (unaudited).

3. Do **NOT** update grades or the two audit clocks from the daily wrap. `Last full audit` is written
   only by a PM-invoked `/architecture-survey`; `Last targeted audit` only by `/architecture-audit`.
   The weekly Sonnet observer renders no grades — it flags candidates as debt-backlog YAML entries
   (`state/debt-backlog/<date>-<slug>.yaml`) with `tags: [weekly-arch-review]` for the
   the Staff Engineer arch pass to adjudicate. Grade changes are an audit output, never a daily-wrap side effect.

---

## Debt Backlog Entry Format (Weekly Observer)

Entries added by the weekly strategic observer are per-entry YAML files produced by
`coordinator-queue-append --schema debt-backlog`. The filename is the canonical identity handle:

```
state/debt-backlog/<YYYY-MM-DD>-<slug>.yaml
```

The pre-tc-2 DSR-{YYYY-MM-DD}-{N} ID prefix and markdown table row format are retired.
See `docs/wiki/schema-and-validation-contracts/debt-backlog-schema.md` for the full field reference and a complete example entry.
Historical DSR-prefixed references in entry bodies (e.g. in `evidence:` prose) are tolerated;
the `id:` field itself is dropped (filename is the identity key).

---

## Source Discipline — Residue First, Never `git log`

The primary source for a daily summary or a weekly digest is the residue `/workstream-complete`
leaves: completion entries under `archive/completed/`, plus lessons, handoffs, and the
review-trail. **`git log` is fallback detail for a thinly-named unit, not the spine.** Weekly
agents run *after* the dailies and read them rather than re-deriving from commits.

A completion entry is a unit of work the session that did it declared complete — already
theme-shaped, carrying a title, `nature`, t-shirt LoE, its own commit list, and a narrative body.
Commit-first grouping asks an analyst to reconstruct all of that from scratch, and it is both
costlier and lossy.

Measured on the 2026-07-28 → 2026-08-05 backfill: roughly 350 commits/day against
roughly 10 completion entries/day, and commit-first analysts missed **30% of declared work units
(23 of 75)** — concentrated on exactly the high-commit days where the loss is least visible. A
residue-first second pass closed it to 75/75. Dailies feed release notes, so a dropped entry
becomes a dropped release-note line.

The summary script reads the day's completion entries first and covers every one, then asserts
coverage mechanically: each entry for the span must be traceable in the output, else exit 1. A
hand-written or agent-written summary (backfill content-assembly) follows the same rule: cover
every entry, then verify mechanically — sub-agents report success either way.

---

## Failure Mode Table

| Situation | Action |
|---|---|
| No commits since baseline | The script writes a minimal summary with `covered_tip_sha: none` |
| `daily-doc-rollup.py summary` exits 1 | EM writes a minimal work summary from the day's `archive/completed/` entries |
| `daily-doc-rollup.py clusters` exits 1 | Skip the clustering; the entries stay unclustered, report one line |
| Weekly observer dispatch fails | Skip it, note "strategic review skipped" in `WEEK-SUMMARY.md` |
| No strategic docs exist | Observer focuses on pure architectural principles instead of roadmap alignment |
| No debt entries to write | Skip the write; `coordinator-queue-append` creates the entry file; `state/debt-backlog/` directory must exist |

---

## Skip Condition

The only valid skip: **zero new commits today AND no agent-driven changes outside commits.**
Anything else — one commit, one file — write the daily summary. The weekly observer has no
skip condition on commit count.

---

## `archive/daily-summaries/` Read-Only Intake — Dispositions

Named as read-only intake in `PIPELINE.md` § Phase 0 step 1 and `update-docs.md`'s `tasks/` vs
`state/` paragraph. Three dispositions: (1) cadence-trigger extension is
control-plane-engine work, out of this corpus's scope; (2) no harvest debt — debt is computed
over `archive/specs/`, not this directory; (3) no new link-heal no-rewrite class — stays in
AC19's ordinary rewritable `archive/` scope. Left open: the never-delete asymmetry —
`state/week-changelog/` is on `artifact-pruning.md`'s Never-delete list, this directory is not.

---

## Rollup Frontmatter Standard

Every daily summary and every archived week carries frontmatter in one shape, so a reader like
Cockpit parses facts without scraping prose. The keys mirror the cockpit contract's `day-rollup` /
`week-rollup` entities (`grain`, `period`, `repo`, `deterministic_facts.commits`).

- **Day** — `archive/daily-summaries/YYYY-MM-DD[-<machine>].md`, keys exactly as below, in that
  order. Unknown value → `null`, never omitted. Keys outside the standard are kept under a nested
  `legacy:` map, never at top level. `covered_tip_sha` stays line-anchored so the backfill scan
  still reads it.

  ```yaml
  ---
  rollup_schema: 1
  grain: day
  period: YYYY-MM-DD
  repo: <owner>/<repo>
  machine: <machine-slug or null>
  commits: <int or null>
  covered_tip_sha: <40-char SHA, "none", or null>
  covered_machine: <machine-slug or null>
  backfilled: false
  ---
  ```

- **Week** — every `archive/week-changelogs/<week-start>/` holds exactly one `WEEK-SUMMARY.md`
  (never `WEEK-DIGEST.md`, `week-changelog.md`, or a dated variant) opening with:

  ```yaml
  ---
  rollup_schema: 1
  grain: week
  period: YYYY-Www          # ISO week of week_start
  week_start: YYYY-MM-DD
  week_end: YYYY-MM-DD
  repo: <owner>/<repo>
  commits: <sum of the week's daily `commits`, or null>
  days: [YYYY-MM-DD, ...]   # days with any record
  backfilled: <bool>
  narrative: authored | null   # null = generated day index, no written weekly narrative
  ---
  ```

- The body under the frontmatter is prose and free-form beyond the H1
  (`# Daily Summary — YYYY-MM-DD` / `# Week Summary — <start> .. <end>`).

## Field rules

- **Reconstruct past work from ceremony residue first, then git log.** `archive/completed/` under-reports; mise-delivered work often has no entry.
