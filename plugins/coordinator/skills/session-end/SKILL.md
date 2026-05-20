---
name: session-end
description: Wrap up finished work — capture lessons, update docs
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Session End — Wrap Up Completed Work

Close out a finished vein of work: capture lessons and update documentation to reflect completion. No handoff — this is for work that's *done*, not being passed forward.

> **`/session-end` and `/handoff` are mutually exclusive — never combined.** `/session-end` caps a workstream; `/handoff` passes one on. A session terminates via exactly one of them (or via `/workday-complete` / `/merge-to-main` / commit-and-stop). If the work is in-flight and needs a successor, STOP — invoke `/handoff` instead and do not run this skill. If you are tempted to run both ("end the session AND write a handoff"), the underlying state is two workstreams: end the finished one here, hand off the in-flight one separately with `/handoff`, framing which is which.

## Instructions

When invoked, capture lessons and update plan/project documentation to reflect completion status. If work is incomplete and needs to be picked up later, use `/handoff` instead — not in addition.

**Design note:** Multiple agents may be running concurrently. This skill closes out ONE agent's session without heavy repo-wide operations that could conflict with other agents.

### Step 1: Capture Lessons

Read `tasks/lessons.md` (if it exists). If anything was learned this session that isn't already captured, add it — but apply the intake filter first.

**Create on first use:** `tasks/lessons.md` is not scaffolded by `/project-onboarding` (it would be empty — no lessons exist on day 1). If lessons exist to capture AND the file does not exist yet, create it now using the template header:

```markdown
# Lessons — [Project Name]

Engineering patterns worth internalizing. Bold title + 1-2 sentence rule. Max 3 lines per entry.

<!-- This file is maintained by the EM. See CLAUDE.md § Self-Improvement Loop for conventions. -->
```

Then append the new entry. If there are no lessons to capture and the file doesn't exist, do not create it.

**Feature scope:** `<feature>` is derived from the current work context:
- If a feature-scoped plan exists at `tasks/<feature>/todo.md`, use that feature name
- If on a `feature/<name>` branch, use `<name>`
- Otherwise, use `tasks/lessons.md` (global)

**What qualifies:**
- Corrections from the user (preferences, workflow, conventions)
- Surprising API behavior or tooling gotchas
- Patterns that worked well or failed
- Debugging insights that would save future sessions time

**What doesn't qualify:** One-off bug fixes, details specific to a single script/pipeline run, or anything already encoded in the code, CLAUDE.md, or MEMORY.md. Before adding, ask: *"Will this save time in the next 4 weeks, or is it just documenting what happened?"*

Add new entries in the established format (bold title + 1-2 sentence rule, max 3 lines). Prefer merging with an existing entry over adding a new one. Skip if nothing new.

### Step 1.2: Lesson Classification

For each new lesson added in Step 1, ask the tier-1 question: **"If a different project type — UE / web / data / research — also used the coordinator pipeline, would this rule apply?"** This is autonomous self-classification; no separate review step is needed.

- **If yes (tier-1 / universal):** (a) tag the entry in `tasks/lessons.md` by appending `[universal]` on the same line as the bold title; (b) append a one-liner to the global queue at `~/.claude/tasks/coordinator-improvement-queue.md`:
  ```
  - YYYY-MM-DD | <source-repo> | <source-file>:<line> | <one-line summary> | proposed target: <coordinator file>
  ```
  Use the project repo name as `<source-repo>`, and `tasks/lessons.md:<line-number>` as `<source-file>:<line>`. If the same `<source-file>:<line>` already exists in the queue, skip — the queue is append-only and that pair is the dedup key.
- **If no (tier-2 / project-specific):** no action beyond the lesson already written.
- **If nothing new was added in Step 1:** skip this step entirely.

### Step 2: Update Plan Documentation

Find and update relevant plan/task documentation to reflect what was completed:

1. **Find the plan docs — actively search, don't wait to recall.** Check these locations in order:
   - Any plan document referenced or opened during this session (you have it in context)
   - `tasks/<feature>/todo.md` — feature-scoped plans for current work
   - `tasks/plans/` — session handoff plans and tactical trackers
   - `docs/plans/` — historical and reference plans
   - `~/.claude/plans/` — plans written in plan mode (may need copying to canonical location)
   - `tasks/todo.md`, `tasks/plan.md` — legacy flat locations
   If a plan exists for the work this session touched, read it and update it. Don't rely on having opened it earlier — sessions that start from handoffs or dive straight into code often never explicitly open the plan.
2. **Mark completed items:** Check off finished tasks, update status fields, add completion notes where appropriate.
3. **Add a review section** (if not already present) summarizing outcomes — what was built, key decisions, anything notable about the result.
4. **Update other pertinent docs:** If the work affected README files, architecture docs, or other project documentation that should reflect the new state, update those too. Use judgment — only touch docs that are clearly stale as a result of this session's work.

### Step 2.5: Doc-Alignment Insurance

End of session is the last chance to ensure status fields match reality. This catches work that completed but whose status wasn't updated — common after compaction or rapid context shifts.

1. **Check active chunk/stub docs:** If this session worked on chunk stubs (files with `**Status:**` fields in `docs/active/`, `docs/plans/`, or similar), verify their status reflects what actually happened:
   - If the work is complete but status says "in progress" → update to complete
   - If the work is blocked but status says "in progress" → update to blocked with reason
   - If the status is already correct, skip
2. **Check execution tracker:** If a tactical execution tracker exists (e.g., `docs/plans/consolidated-execution-tracker.md`), verify that chunks worked on this session have accurate status entries
3. **Lightweight pass only.** Read what's in your conversation context — don't re-read every file in the project. If you have no memory of working on tracked chunks, skip this step entirely.

### Step 2.6: Archive Uncaptured Work

Sweep the session's commits for completed work that isn't already in the project tracker (`docs/project-tracker.md`) or the per-entry completion archive under `archive/completed/`. This catches bug fixes, ad-hoc requests, and quick tasks that bypassed the spec pipeline.

**Skip if** no `archive/` directory exists and no `docs/project-tracker.md` exists — the project hasn't adopted unified tracking yet.

#### Step 2.6.1 — Scan session commits

`git log --oneline` for commits since the session started (or since the last `/session-end`/`/update-docs`). For each substantive commit (skip merge commits, doc-only commits, quick-saves), check if the work is already represented in either the tracker or an existing per-entry file under `archive/completed/YYYY-MM/`. Check by commit SHA — if the hash already appears in any file under that directory, skip that entry. The archive records *what shipped*, not every keystroke; group related commits into a single entry.

#### Step 2.6.2 — AUTO-MIGRATE legacy monolith (idempotent)

Before writing any per-entry file, check whether a legacy monolith file exists at `archive/completed/YYYY-MM.md` (i.e., directly at the root of `archive/completed/`, NOT under a `YYYY-MM/` subdirectory). If found AND `COORDINATOR_OVERRIDE_LEGACY_MONOLITH` is not set to `1`:

```bash
git mv archive/completed/YYYY-MM.md archive/completed/legacy/YYYY-MM.md
```

Create `archive/completed/legacy/` if it does not exist. The `git mv` is idempotent — subsequent runs find no monolith-at-root and skip silently. If `COORDINATOR_OVERRIDE_LEGACY_MONOLITH=1`, skip the `git mv` (the EM has already handled migration manually).

<!-- TRIPWIRE: NO monolithic append — archive/completed/YYYY-MM.md writes outside legacy/ are forbidden.
     Static-grep check: bin/check-no-monolith-completion-append.sh (created in Chunk 10).
     Registered in docs/wiki/coordinator-tripwires.md.
     Override: COORDINATOR_OVERRIDE_LEGACY_MONOLITH=1 skips git mv (manual migration path). -->

#### Step 2.6.3 — Determine chain slug

(a) If a plan was touched this session (any file under `docs/plans/` or `tasks/*/todo.md`), chain = that plan's filename stem (e.g., `2026-05-19-completion-log-phase1`).
(b) Else if a handoff was picked up this session, chain = the handoff's filename stem.
(c) Else if a workstream slug appears in any handoff frontmatter consumed this session, chain = that slug.
(d) Else chain = `null` (omit from filename; write as `archive/completed/YYYY-MM/YYYY-MM-DD-adhoc-<sid6>.md`).

#### Step 2.6.4 — AUTO-INFER nature via Sonnet dispatch

Nature is classified automatically — no interactive prompt. Dispatch a small Sonnet sub-call (~1 KB output) with:
- Touched paths (from `git diff --name-only` for this session's commits)
- Commit messages (from `git log --oneline` for this session)
- Workstream kind (plan-driven | handoff-pickup | spinoff | ad-hoc)
- Chain slug (resolved in Step 2.6.3)

Sonnet classifies to one of `[roadmap | bugfix | tech-debt | infra]` and returns a `nature:` value + one-sentence rationale. Tag the entry `nature_inferred: true`.

**Interactive override:** If `COMPLETION_NATURE` is set in the environment before invoking `/session-end`, use that value as `nature:` directly and write `nature_inferred: false`. The env var bypasses the Sonnet dispatch entirely.

**Why AUTO-INFER not interactive-prompt:** session-end fires in autonomous execution chains where no human EM is present to answer. A default-skip mechanism would systematically produce un-tagged entries in autonomous sessions and tagged ones in interactive sessions — a sampling bias that corrupts `--where nature=<x>` queries that Phase 3 consumers depend on. See plan § Chunk 3 for full rationale.

#### Step 2.6.5 — Resolve `$em_sid` and derive `<sid6>`

**`$em_sid` sourcing (env-var-primary):**
1. If `$em_sid` is set in the environment, use it directly.
2. Else read from `.git/coordinator-sessions/.current-session-id` (the platform sentinel — `session-init.sh:77` writes the current `session_id` there on every SessionStart, per `docs/wiki/claude-code-platform-gotchas.md:47`).
3. Do NOT use `meta.json`-based lookup — it is circular (you need `$em_sid` to find the directory containing `meta.json`).

`<sid6>` = last 6 characters of the resolved `$em_sid`. If `$em_sid` cannot be resolved, generate a 6-char hex fallback from the current timestamp (`date +%s | tail -c 7 | head -c 6`).

The `<sid6>` suffix makes the filename deterministically unique per EM session — no existence-check race condition. Two concurrent session-ends in the same chain on the same day produce two distinct files, not a collision.

#### Step 2.6.5a — Compute LoE block

> **Behavioral rule (tripwire):** Session-end MUST invoke `coordinator-session-loe.sh` (or `aggregate-chain-loe.sh` for chain-terminal) to write per-session LoE into the completion entry. Skipping this step produces an incomplete entry that Phase 3 consumers and workweek-complete cannot query. No override mechanism; the `loe:` block is always written.

Determine whether this is a **single-session** or **chain-terminal** session using the same detection logic as Step 2.9 chain-end detection:
- **Single-session:** this session was NOT opened via `/pickup` (no predecessor handoff consumed).
- **Chain-terminal:** session was opened via `/pickup` AND is ending via `/session-end` (not `/handoff` or `/spinoff`).

**Single-session path:**

```bash
loe_block=$(~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-session-loe.sh \
  --format yaml-frontmatter 2>/dev/null)
```

If the script is absent or returns non-zero, degrade gracefully: set `loe_block` to:
```yaml
loe:
  agent_dispatches: null
  opus_dispatches: null
  em_tokens: null
  tshirt: null
```

**Chain-terminal path:**

Resolve the consumed predecessor handoff path (the handoff archived by Step 2.7 this session). Resolution order:
1. Check session state for the handoff path that was consumed at `/pickup` time.
2. Walk `tasks/handoffs/archive/<YYYY-MM>/` for entries with `consumed_by: <this session_id>`.

Then invoke the chain aggregator:

```bash
loe_block=$(~/.claude/plugins/coordinator-claude/coordinator/bin/aggregate-chain-loe.sh \
  --terminal-handoff "<resolved-predecessor-path>" \
  --format yaml-frontmatter 2>/dev/null)
```

The chain aggregator walks the `predecessor:` chain backward from the consumed handoff, reads `## Session Ledger` blocks from each handoff (including archived predecessors at `tasks/handoffs/archive/**/`), sums LoE across all sessions, and recomputes t-shirt size against the shared threshold table. If the script is absent or returns non-zero, degrade the same way as the single-session path.

The resolved `$loe_block` is embedded into the completion entry frontmatter in Step 2.6.6.

#### Step 2.6.6 — Write per-entry file

For each untracked completed work item (or one entry covering the session's full scope if work is cohesive), write a single Markdown file at:

```
archive/completed/YYYY-MM/YYYY-MM-DD-<chain-slug>-<sid6>.md
```

(where `YYYY-MM-DD` is today's date; if chain is null, use `YYYY-MM-DD-adhoc-<sid6>.md`).

Create the `archive/completed/YYYY-MM/` directory if it does not exist.

File shape:

```markdown
---
title: "<Concise past-tense one-line description>"
created: YYYY-MM-DD
nature: <roadmap|bugfix|tech-debt|infra>
nature_inferred: <true|false>
chain: <chain-slug or null>
commits:
  - <sha1>
  - <sha2>
status: pending-release
chain_terminal: <true|false>
authored_by: <em_sid or null>
loe:
  agent_dispatches: <N or null>
  opus_dispatches: <N or null>
  em_tokens: <N or null>
  tshirt: <XS|S|M|L|XL|null>
# chain-terminal only — omit for single-session entries:
# chain_sessions: <N>
# chain_span_days: <N>
# chain_starting_handoff: <path>
---

<One paragraph prose summary: what shipped, key decisions, anything notable.>
```

Frontmatter field semantics:
- `nature_inferred: true` when AUTO-INFER Sonnet path was used; `false` when `COMPLETION_NATURE` env var was set.
- `chain_terminal: true` when this session is chain-terminal (opened via `/pickup`, ending via `/session-end`); `false` for single-session work. Phase 1 defaulted this to `true`; Phase 2 sets it correctly per detection.
- `authored_by:` is `$em_sid` if resolvable; omit field (or write `null`) if not.
- `status: pending-release` is the initial state for all completion log entries.
- `loe:` block is populated from Step 2.6.5a. For chain-terminal sessions, the block contains aggregate values across the full predecessor chain plus the additional chain-summary fields (`chain_sessions`, `chain_span_days`, `chain_starting_handoff`) that `aggregate-chain-loe.sh` emits. For single-session entries, only the four base fields are present.
- `loe.tshirt` null means LoE computation was unavailable (script absent or errored) — entry is still valid, just unranked.

**No separate collision handling needed.** The `<sid6>` suffix makes the filename unique by construction (Step 2.6.5).

#### Step 2.6.7 — Judgment filter

Not every commit is a work item. Group related commits into a single archive entry. Skip trivial commits (typo fixes, formatting). If a session produced no substantive commits beyond doc/lesson housekeeping, no archive entry is needed — skip silently.

### Step 2.7: Archive Predecessor Handoff (if applicable)

When this session was opened with `/pickup`, the consumed handoff still lives in `tasks/handoffs/` (mutation-only at pickup time). If this session is ending via `/session-end` rather than `/handoff`, archive the predecessor now.

**Detection:** scan `tasks/handoffs/*.md`. For each file, read its frontmatter `consumed_by:` field.

- Resolve this session's id: `$CLAUDE_SESSION_ID` env var first; sentinel fallback at `.git/coordinator-sessions/.current-session-id` only when env var is empty.
- Zero matches → skip silently.
- One match → archive it (see Action below).
- More than one match → log to stderr and archive all. (A session that legitimately consumed multiple predecessors is rare but not invalid — no fail-loud.)

**Action:** `git mv tasks/handoffs/<file> archive/handoffs/<file>`. Create `archive/handoffs/` if it does not exist. On `git mv` failure (file already moved by a concurrent `/handoff` chain-archival), log to stderr and continue — idempotent treatment of already-moved files.

The move folds into the existing session-end commit at Step 3 — no separate commit for this step.

**No claim release call needed here.** `cs_archive` at Step 3.5 carries the entire session directory (including `handoff-claims/`) into `.archive/`. The claim is released structurally.

**Skip entirely if** this session is exiting via `/handoff` — `/handoff` chain-archival owns that path. `/session-end` and `/handoff` are mutually exclusive session-exit paths.

### Step 2.8: Refresh Orientation Documents

Update the documents that future sessions read for orientation — closing the read-write loop with `/session-start` and `/workday-start`.

1. **Orientation cache** (`tasks/orientation_cache.md`): **Do not author the cache body. Do not patch sections. Do not re-derive content section-by-section.** The cache schema (`pipelines/workday-start-internals.md` § 5.5) is owned by ceremony writers (`/workday-start`, `/update-docs`). `/session-end` is a **mid-session writer** with a single, narrowly-scoped capability: pinboard append.

   **Pinboard rule (the only cache mutation permitted here):** if this session surfaced something the next session boot MUST see, and it would otherwise be lost (a transient surface gotcha; a critical blocker context; an environment-specific caveat that fooled this session and will fool the next), write exactly one line to `## Pinboard` via the routine:

   ```bash
   bash plugins/coordinator-claude/coordinator/bin/regenerate-orientation-cache.sh \
       --invoker session-end \
       --pinboard "YYYY-MM-DD <writer-slug>: <one-line note>"
   ```

   The pinboard is a one-slot escape valve. A second mid-session write overwrites; it does not append. The pinboard is cleared at every ceremony regen (`/workday-start`, `/update-docs`). If you find yourself wanting to write more than one line, that's not a cache edit — it's a wiki edit, a handoff body, or a lessons.md entry. Escalate to PM.

   If you have nothing pinboard-worthy, **do nothing.** Counters, workstreams, branch state, doc-freshness, "recent work" prose — none of this is a mid-session concern. The ceremony writers regenerate all of it from disk on the next boot.

   If the cache file doesn't exist, skip — the project hasn't run `/workday-start` yet. **Do not claim the cache is absent based on intuition** — `ls tasks/orientation_cache.md` before asserting absence.

2. **Project tracker** (`docs/project-tracker.md`): If it exists and this session completed or progressed tracked items, update their status rows. Only touch rows this session affected — don't re-derive the whole tracker.

3. **Action items** (first match: `ACTION-ITEMS.md`, `docs/active/ACTION-ITEMS.md`, `docs/ACTION-ITEMS.md`): If one exists and this session resolved any listed items, check them off or remove them per the file's existing conventions.

4. **Documentation index** (`docs/README.md`): If it exists and this session created new guides, added research files, or completed plan documents, patch the relevant table. Only touch rows this session affected.

**Concurrency note:** These are targeted patches to specific rows/sections based on this session's work — safe with concurrent agents, as long as agents work on different items (which they should by design).

### Step 2.9: Code Review Consideration

Assess whether this session's diff warrants a code review pass before committing. EM makes the call using the table below — this step is judgment, not ceremony.

**Diff-shape table:**

| Session shape | Default scale |
|---|---|
| Doc-only edits, lesson capture, no executor dispatched, no code touched | **None** |
| Single-file fix <50 LOC, no shared schema touched, no executor | **None** (but commit message names the change) |
| Any executor dispatched, OR >50 LOC code change, OR shared schema/seam touched | **`code-reviewer`** (Sonnet, locked — see `agents/code-reviewer.md`) |
| Chain-end (started with `/pickup`, ending without `/handoff`/`/spinoff`) AND chain diff is non-trivial | **`code-reviewer`** on chain diff (default) |
| Chain-end AND any of: chain diff >500 LOC, touches public API / schema / security-adjacent code, ≥3 segments in chain, novel external API integration | **`code-reviewer` on the chain diff** (partition into multiple parallel dispatches when surface is too large for one reviewer — see § Partitioning large surfaces), with EM-judged Patrik escalation *post-code-reviewer* on signal — see § Post-code-reviewer Patrik-escalation criteria |

**Precedence rule:** chain-end rows (4, 5) override session-end rows (1, 2, 3) when both apply — the chain diff is the integration-risk artifact.

**Anchored-ranges note:** the numeric anchors (50 LOC, 500 LOC, ≥3 segments) are decision anchors, not hard thresholds. An EM seeing a 51-LOC change with a clean shape should not feel obliged to escalate; an EM seeing a 49-LOC change touching a public schema seam should not feel released from review.

**Partitioning large surfaces across multiple `code-reviewer` dispatches (row 5):**
One Sonnet reviewer over a chain diff that spans a new package + cross-repo edits + a shared-schema change will skim — the surface exceeds what a single dispatch can carry with depth. When the row-5 diff is genuinely too big for one reviewer, the EM SHOULD fan out into multiple parallel `code-reviewer` dispatches, each over a coherent slice. Partitioning shapes (pick what matches the diff):
- **By repo / package boundary** — one dispatch per repo touched, or per top-level package in a multi-package diff.
- **By concern** — one dispatch on the new code (correctness, structure, naming, tests), a second on the cross-repo edits / schema migration (compatibility, call-site coverage, version-aware logic), a third on external API integration (auth, error handling, retry, secret handling) if novel.
- **By directory cluster** when neither of the above is clean — `src/foo/**`, `src/bar/**`, `tests/**` as separate slices, with the EM owning the union.

This is **diff partitioning under capacity limits**, not the workweek parallel-orthogonal-lenses pattern — every dispatch is the same agent (`code-reviewer`) with a narrower scope. It does NOT require the lens-orthogonality manifest or the no-rewrite synthesizer from `coordinator:parallel-code-review`; it shares only the frozen-diff property from § Review Sequencing's parallel carve-out. Mechanics:
1. EM declares partition in the dispatch brief — each `code-reviewer` prompt names its slice explicitly (paths or commit subset) and an "out of scope: the rest of the chain diff" line so reviewers don't drift.
2. Dispatch in parallel (one message, multiple `Agent` tool uses).
3. Findings land separately; EM dispatches `coordinator:review-integrator` per slice OR collates findings and dispatches one integrator over the union — EM's call based on overlap.
4. Trail write at end uses `--reviewer code-reviewer` (single value); record the partition shape in the wrap-up sentence, not the trail field.
5. Post-`code-reviewer` Patrik-escalation criteria below apply to the **combined** finding set (sum across slices), not each slice independently.

If you find yourself partitioning into more than ~4 slices, the diff is workweek-territory — surface to PM as a candidate `/workweek-complete`-style parallel review, don't fan out a sixth `code-reviewer`.

**Post-code-reviewer Patrik-escalation criteria (row 5 chain-end):**
Default after `code-reviewer` returns is *no Patrik*. Escalate iff the report shows one or more of:
- A high-volume finding count (rough anchor: ≥5 substantive findings, not nits).
- Any finding flagged as architectural, strategic, cross-system, or boundary/seam/taxonomy-shaped — i.e. not a tactical fix the integrator can fold mechanically.
- The reviewer itself recommends a deeper second pass, OR EM reads the report and is genuinely uncertain whether a flagged issue is tactical or structural.

Tactical-only or clean `code-reviewer` → fold via integrator, write the trail, ship. The weekly `/workweek-complete` Step 7 parallel-code-review remains the structural backstop for chain-end work that reaches main without Patrik at session-end.

**Anti-ceremony-bias tripwire (`code-reviewer`-skip direction — still load-bearing):**
> "If you're considering skipping `code-reviewer` because the diff feels small or 'we already reviewed the plan' — run it. Plan-time and post-implementation review catch different defect classes; the marker trail records `verdict=ok` in seconds when there's nothing to find. `code-reviewer` is the floor on row-3+ sessions, not a negotiable add-on."

**Symmetric anti-ceremony tripwire (row 3+ — `code-reviewer` floor):**
> "Plan-time review and post-implementation review catch different defect classes — complementary, not substitutional. Mechanical executor gates (grep/pytest/`bash -n`) are correctness floors, not review lenses. 'We've done a lot of review already' is the shape wrap-up pressure takes at session-end. If you're drafting a waiving-with-rationale sentence on a row-3+ session to skip `code-reviewer`, the rationale is the tell. EM keeps waive authority on genuinely shallow row-3 diffs; the test is the diff shape, not the row number. (Post-`code-reviewer` Patrik escalation is a separate question — governed by the actual report per § Post-code-reviewer Patrik-escalation criteria, not by ceremony intuition.) See `docs/wiki/session-end-review.md` § why-post-implementation-review-is-not-redundant for the worked example."

**Chain-end detection:**
- Resolve session-id: `CLAUDE_SESSION_ID` env var first; sentinel fallback at `.git/coordinator-sessions/.current-session-id` only when env var is empty.
- Chain-end signal: session opened via `/pickup` AND ending without `/handoff` or `/spinoff` invocation this session.
- **Additional Patrik-escalation signal:** if `/handoff` Step 0's NO-test gate previously fired and routed the session to `/session-end`, the session is shipped/complete — weight that into the post-`code-reviewer` escalation decision alongside the report's findings.

**Diff scope:**
- Chain-end → `git log $(git merge-base origin/main HEAD)..HEAD`
- Mid-chain → `git log $LAST_REVIEW_SHA..HEAD` (where `$LAST_REVIEW_SHA` is the `sha_range` head from the most recent trail record, or session-start SHA if no prior review exists)

**Dispatch:** invoke `coordinator:review-code` Branch A.2 with the resolved diff scope.

**Spec cross-reference (loop closure) — include in dispatch brief when a spec exists:**
When this session (or the chain, for chain-end) implemented work governed by a spec, plan, or stub — `docs/plans/YYYY-MM-DD-<feature>.md`, an RFC, an enriched stub spec, or a handoff body that functions as a live spec — name the spec path in the `code-reviewer` dispatch brief and instruct it to apply the **Spec completion lens** (per `agents/code-reviewer.md` § Spec completion lens). The reviewer reads the spec before the diff and reports on scope completeness, shape adherence, substrate drift, acceptance-criteria coverage, and hedge-shaped deferrals.

This is loop closure, not redundancy: EM dispatch-time scope vetting and TDD cover what the author thought to verify; the reviewer's spec lens is the independent pass that catches silently-dropped deliverables, scope creep marketed as "while I was there", and acceptance criteria where the tests drifted to test the easy thing. Apply on row 3, 4, 5 sessions whenever a spec exists; omit on row 1, 2 (no spec involved by definition). If multiple specs apply (chain of stubs, plan + amendment), name all of them; the reviewer will treat the union as the completion oracle. If partitioning the diff across multiple `code-reviewer` dispatches (per § Partitioning large surfaces), name the spec slice each reviewer is responsible for — overlap is fine, gaps are findings the EM will own.

Negative-spec: if no spec governs this session (small organic fix, opportunistic refactor, doc-touch session), omit the spec section from the brief — do not invent a spec to satisfy the rule, and do not point at a stale spec. The reviewer's agent prompt is clear that no spec named ⇒ skip the lens entirely.

**Findings disposition — fix everything, including nitpicks:**
> "If a finding is worth surfacing, it is worth fixing now. The diff is fresh, the EM has context, and the cost to fix at session-end is a fraction of what it costs three weeks later in a debugging session. A reviewer verdict of `OK` with three 'below blocking threshold' observations is NOT a license to commit and move on — those observations are the review output, and they get fixed in this session before commit. This applies symmetrically across severities: P0/P1/P2/nitpick/observation/note/'consider' — all fold in via `coordinator:review-integrator` before the marker-trail write. The only legitimate skip path is a real tradeoff (cost/value, scope/polish, architectural direction) that escalates to PM per § Reviewer findings — apply, don't ratify in `coordinator/CLAUDE.md`. 'Recorded below blocking threshold' in the EM's wrap-up sentence is the tell that this rule was skipped. Re-open the diff, fold the findings, then write the marker."

After integration, the trail's `--verdict` field still records the reviewer's original verdict (`ok` / `warn` / `blocked`) — verdict tracks what the reviewer found on the pre-fix diff, not what shipped. Downstream load-shedding consumes the verdict; the trail is not a fix-completion log.

**Marker write:** after review integration completes, invoke:
```bash
~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-write-review-trail.sh \
  --sha-range <A..B> --reviewer <code-reviewer|patrik|code-reviewer+patrik|waived|ubt-compile> \
  --scope <chain|session> --verdict <ok|warn|blocked|waived|pending> --diff-loc <N>
```

**Negative-spec:**
- Trivial sessions (Row 1, 2 of the table): skip the review entirely. No trail record written.
- PM-waived sessions: log waiver to trail with `--reviewer waived --verdict waived`. Greppable as `verdict=waived`.

**Staging discipline:**
> "Any files edited by `coordinator:review-integrator` during this step must be staged via explicit path in Step 3, not absorbed by a post-integration `git add -A`. This preserves the existing concurrent-EM safety property of Step 3."

**UBT pending-marker (UE plugin work only):** If `bin/check-ubt-build-fresh.sh` exists in the cwd, invoke it in `--mode pending`. Captures the build verdict as a deferred record; resolution happens at `/workday-complete` Step 0c. This step is a no-op for non-UE repos (script absent) — the `[ -x bin/<name>.sh ]` pattern is the canonical convention for conditional UE-specific steps in coordinator skill bodies; future UE conditionals (`clippy`, etc.) follow this shape.

```bash
[ -x bin/check-ubt-build-fresh.sh ] && \
  bin/check-ubt-build-fresh.sh --since "$(git merge-base origin/main HEAD 2>/dev/null || git rev-parse HEAD~1)" --mode pending
```

### Step 3: Commit + Verify Remote

1. **Stage only paths this session touched — never `git add -A`.** With concurrent EMs active on the same branch, `git add -A` sweeps up another session's staged/modified files and silently re-attributes them. Instead:
   - Make a mental (or explicit) list of the files you edited during Steps 1/2/2.5/2.6/2.7 (typically a small set: `tasks/lessons.md`, `archive/completed/YYYY-MM/<entry>.md`, `archive/completed/legacy/YYYY-MM.md` if AUTO-MIGRATE ran, `docs/project-tracker.md`, action-items file, `docs/README.md`).
   - `git add <path1> <path2> ...` — name each path explicitly.
   - If you also edited files earlier in the session that are still unstaged, stage those by path too — but only ones you know you authored this session.
   - If `git status` shows unfamiliar unstaged files you didn't touch, **leave them alone** — they belong to a concurrent session.
2. Commit with a lightweight message: `"session-end quick-save"`. (The post-commit hook will auto-push on work/feature branches.)
3. If nothing to commit, check for unpushed commits: `git log "origin/$(~/.claude/plugins/coordinator-claude/coordinator/bin/coordinator-current-branch)..HEAD" 2>/dev/null`
4. **Verify remote is synced:** confirm no unpushed commits remain. If auto-push failed, push explicitly and warn the PM.
5. If on main (shouldn't happen, but safety): push explicitly — `git push origin main`
6. If push fails (auth, network, conflicts), **warn the PM explicitly** — this is a critical failure

### Step 3.5: Archive Session Claim

Now that the final commit has landed and pushed, archive this session's claim directory so concurrent sessions don't see stale claims accumulating until the 24h reaper fires. `/session-end` is one of two session-exit pathways (the other being `/handoff`); both must clean up claims, otherwise sessions that wind down via `/session-end` leak claims that force the next concurrent EM into a 24h wait, `COORDINATOR_OVERRIDE_SCOPE=1`, or hand-archival.

Run:
```bash
sid=$(cat "$(git rev-parse --show-toplevel)/.git/coordinator-sessions/.current-session-id" 2>/dev/null) && \
  source ~/.claude/plugins/coordinator-claude/coordinator/lib/coordinator-session.sh 2>/dev/null && \
  cs_archive "$sid" 2>/dev/null || true
```

Idempotent — already-archived sessions return 0 silently (verified: a session archived by `/handoff` and re-archived here is a no-op). Failures are non-fatal (the 24h reaper is the safety net). Skip silently if the sentinel is missing or the lib is unavailable.

**Note on session_id source:** The sentinel is "last writer wins" across concurrent sessions. If `CLAUDE_SESSION_ID` is exported in your environment, prefer it over the sentinel — that's the session that actually owns this exit.

### Step 4: Final Summary

Present a brief end-of-session summary:
```
## Session Complete

**Work done:** [1-2 sentence summary]
**Lessons captured:** [N new / none]
**Work archived:** [N items written to archive/completed/YYYY-MM/<filename>.md / none needed / project not using unified tracking]
**Docs updated:** [list of updated files]
**Orientation refreshed:** [orientation cache patched / tracker updated / action items checked off / nothing to update / no orientation docs exist]
**Pushed to remote:** [yes — branch name / no — reason]
```

**Flag to PM:** Explicitly note the push so they can verify nothing breaks for other consumers.

**Reminder:** Run `/update-docs` periodically for repo-wide documentation maintenance — it doesn't need to happen every session.

If `$ARGUMENTS` is provided, use it as context for what was accomplished this session.
