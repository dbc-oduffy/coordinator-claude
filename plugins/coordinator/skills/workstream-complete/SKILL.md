---
name: workstream-complete
description: Wrap up finished work — capture lessons, update docs
allowed-tools: ["Read", "Write", "Edit", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Workstream Complete — Wrap Up Completed Work

Close out a finished vein of work: capture lessons and update documentation to reflect completion. No handoff — this is for work that's *done*, not being passed forward.

> **`/workstream-complete` and `/handoff` are mutually exclusive.** This caps a workstream; `/handoff` passes one on. In-flight work → STOP and invoke `/handoff` instead. Two workstreams (one done, one in-flight) → end each separately, naming which is which. → coordinator CLAUDE.md § Handoff Lineage.

## Instructions

Capture lessons and update plan/project documentation to reflect completion. If work is incomplete, use `/handoff` instead. Multiple agents may be running concurrently — this skill closes out ONE session without heavy repo-wide operations.

## Execution Shape — gates vs. todo-list

This skill is mirror-shaped to `/handoff`: a small set of sequential gates plus a TODO-LIST cluster of independent post-work cleanup steps. Treat them as such — do not ladder-walk the todo-list. Convention: `docs/wiki/skill-step-parallelization.md`.

**Sequential gates (real data-dependency edges — must be in this order):**

1. **Step 1 → Step 1.2 micro-chain** — classification reads the lesson Step 1 just wrote. Skip both together if no new lesson.
2. **Step 2.6 internal chain** (Steps 2.6.1 → 2.6.2 → 2.6.3 → 2.6.4 → 2.6.5 → 2.6.5a → 2.6.6 → 2.6.7) — the per-entry archive write is a real chain: AUTO-MIGRATE → chain-slug resolve → Sonnet nature-infer → session-id resolve → LoE block → write entry. Internal to Step 2.6 only.
3. **Step 2.9** (code review) — integrator-edited files must be staged in Step 3.
4. **Step 2.4 → Step 3 staging edge** — when a governing plan exists, Step 2.4's reconciled plan doc (the corrected `docs/plans/<feature>.md`) must be staged in Step 3 before commit. Step 2.4 is a micro-chain off Step 2 in the todo-list cluster (see below); its output is part of Step 3's fan-in union, identical in shape to the existing Step 2.9-integrator-edits → Step 3 staging edge.
5. **Step 3** (commit + verify remote) — fan-in of ALL preceding file edits (lessons, plan docs, archive entries, orientation cache, action-items, review-integrator outputs, reconciled plan doc); commit consumes the union via explicit-path staging.
6. **Step 3.5** (archive session claim) — consumes Step 3's pushed commit.
7. **Step 4** (final summary) — informational.

**Todo-list (execute in any order, batch parallel where two independently read/write different files — with the Step 2→2.4 micro-chain exception noted below):**

- **Step 1 (then 1.2) — run as an inseparable pair, one todo-list slot** — lessons capture + classification (`state/lessons.md`). The 1→1.2 edge is real; run them sequentially as a unit; the *pair* parallelizes with the other slots.
- **Step 2 (then 2.4) — run as a micro-chain, one todo-list slot** — plan documentation (`docs/plans/`, `tasks/<feature>/todo.md`, etc.), then plan-doc reconciliation. The 2→2.4 edge is real: Step 2.4 reconciles the plan doc Step 2 just updated. Run them sequentially as a unit; the *pair* parallelizes with the other slots. Skip Step 2.4 if no governing plan exists.
- **Step 2.5** — doc-alignment insurance (chunk/stub `**Status:**` fields)
- **Step 2.6** — archive uncaptured work (`archive/completed/YYYY-MM/`; internal chain 2.6.1→2.6.7 is real but isolated to this slot)
- **Step 2.7** — archive predecessor handoff (file move only — independent of all other slots)
- **Step 2.8** — refresh orientation documents (pinboard + tracker + action-items + docs README)
- **Step 2.95** — aftermath lens-checkers (big-workstream only; reads session context, writes only the Step 4 summary checklist) — parallel-safe with the 2.x cluster

These six slots touch disjoint surfaces. Among peer slots, none consumes another's output — where two slots operate on different paths, run them in the same response via parallel tool calls. **Step 3 is a fan-in:** it stages the union of all files touched by the cluster; peer ordering is irrelevant, only their position before Step 3 matters.

### Step 1: Capture Lessons

Read `state/lessons.md` (if it exists). If anything was learned this session that isn't already captured, add it — but apply the intake filter first.

**Create on first use:** If lessons exist to capture AND the file does not exist yet, create it with a `# Lessons — [Project Name]` header, a one-line purpose note, and the `<!-- EM-maintained; see CLAUDE.md § Self-Improvement Loop -->` comment, then append the entry. If no lessons to capture and the file doesn't exist, do not create it.

**Feature scope:** `<feature>` is derived from the current work context:
- If a feature-scoped plan exists at `tasks/<feature>/todo.md`, use that feature name
- If on a `feature/<name>` branch, use `<name>`
- Otherwise, use `state/lessons.md` (global)

**Qualifies:** user corrections, surprising API/tooling behavior, patterns that worked or failed, debugging insights. **Doesn't qualify:** one-off fixes, pipeline-run details, anything already in code/CLAUDE.md/MEMORY.md. Test: *"Will this save time in the next 4 weeks?"*

Format: bold title + 1-2 sentence rule, max 3 lines. Prefer merging with an existing entry. Skip if nothing new.

### Step 1.2: Lesson Classification

For each new lesson, ask: **"Would this apply to any project type using the coordinator pipeline?"** Autonomous self-classification; no review step.

- **Yes (universal):** (a) tag with `[universal]` on the bold title line; (b) append one-liner to `~/.claude/state/coordinator-improvement-queue.md`: `- YYYY-MM-DD | <source-repo> | state/lessons.md:<line> | <summary> | proposed target: <coordinator file>`. Skip if that `<source-file>:<line>` already exists.
- **No (project-specific):** no further action.
- **Nothing new in Step 1:** skip entirely.

### Step 2: Update Plan Documentation

Find and update relevant plan/task documentation to reflect what was completed:

1. **Find the plan docs — actively search, don't wait to recall.** Check in order: session context (opened docs), `tasks/<feature>/todo.md`, `tasks/plans/`, `docs/plans/`, `~/.claude/plans/`, `tasks/todo.md`/`tasks/plan.md`. If a plan exists for work this session touched, read and update it — sessions diving from handoffs often never explicitly opened the plan.
2. **Mark completed items:** Check off finished tasks, update status fields, add completion notes where appropriate.
3. **Add a review section** (if not already present) summarizing outcomes — what was built, key decisions, anything notable about the result.
4. **Update other pertinent docs:** If the work affected README files, architecture docs, or other project documentation that should reflect the new state, update those too. Use judgment — only touch docs that are clearly stale as a result of this session's work.

### Step 2.4: Reconcile Plan Doc Against Shipped Reality

> **Spec backlink:** `archive/specs/2026-05-26-session-end-deviation-reconciliation-gate.md` § Goal, D1–D5.

**Governing-plan predicate** — fires only when a governing plan/spec exists (`docs/plans/YYYY-MM-DD-<feature>.md`, RFC, enriched stub, or handoff-body-as-live-spec). Negative-spec: if no governing plan exists, skip entirely. Do NOT invent a plan to reconcile against. No ceremony tax on plan-less sessions. → `docs/wiki/ceremony-calibration.md`.

#### What to correct in place — ALLOWLIST sections

Plan documents contain sections that `/distill` crystallizes into wiki entries (the ALLOWLIST). When what shipped diverged from the plan's forecast, correct these sections **in the plan doc** before the Step 3 commit so distill synthesizes shipped reality, not the stale forecast:

- **Decisions Made** — if a decision record describes an approach that was modified or superseded during implementation, annotate the changed item: `SHIPPED: <what-shipped> (was: <plan-forecast>)`. For decisions that shipped unchanged, no annotation is needed.
- **API Contracts / Function Signatures** — if a function signature, interface shape, or protocol contract landed differently from the plan's specification, correct the relevant entry with the same annotation: `SHIPPED: <actual-signature> (was: <planned-signature>)`.
- **Acceptance Criteria oracle tables** — AC tables (columns: `ID | Criterion | Test | Binding-Class | Status`) are consumed by `check-acceptance-oracle.sh`. **In-place correction of an AC table is scoped to the Status/note columns only** (e.g. `Status → shipped-differently` with a note cell). Free-text mutation of the `Criterion` or `Test` cells would corrupt the structured oracle the parser expects. Substantive "what shipped vs forecast" delta routes to the `## Deviations` table (below) and to the Decisions Made section — NOT a free-text edit of Criterion/Test cells.

The `(was: <plan-forecast>)` annotation maps to distill's `[SUPERSEDED]` nugget class — superseded provenance only; what crystallizes is the shipped reality.

#### Append the `## Deviations` audit section

After correcting ALLOWLIST sections, append the following section to the plan doc (or extend it if already present from an earlier partial session):

```markdown
## Deviations

| deviation | reason | commit |
|-----------|--------|--------|
| <brief description of what diverged from the plan> | <why it diverged> | <commit sha or "pending"> |
```

One row per meaningful deviation. This section is **provenance-only** — it is not crystallized by `/distill` (it is dropped as `[EPHEMERAL]`). The essential deviation fact survives in the corrected ALLOWLIST sections' `(was: …)` annotations; the verbose reasons live here and in git history.

#### Soft-ordering note re Step 2.9

Step 2.9's spec-completion lens is a soft input to this step, not a hard predecessor — Step 2.4 reconciles what the EM knows from session context. If Step 2.9 surfaces additional drift, fold those findings before Step 3. Two write-back types: Step 2.4 performs *forecast→reality* corrections; Step 2.9's integrator path performs *defect-fix* write-backs. Both fan into Step 3's staging union.

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

`git log --oneline` for commits since session start. For each substantive commit (skip merges, doc-only, quick-saves), check if already represented in the tracker or `archive/completed/YYYY-MM/` (by SHA). Group related commits into one entry.

#### Step 2.6.2 — AUTO-MIGRATE legacy monolith (idempotent)

Before writing any per-entry file, check whether a legacy monolith file exists at `archive/completed/YYYY-MM.md` (i.e., directly at the root of `archive/completed/`, NOT under a `YYYY-MM/` subdirectory). If found AND `COORDINATOR_OVERRIDE_LEGACY_MONOLITH` is not set to `1`:

```bash
git mv archive/completed/YYYY-MM.md archive/completed/legacy/YYYY-MM.md
```

Create `archive/completed/legacy/` if it does not exist. The `git mv` is idempotent — subsequent runs find no monolith-at-root and skip silently. If `COORDINATOR_OVERRIDE_LEGACY_MONOLITH=1`, skip the `git mv` (the EM has already handled migration manually).

<!-- TRIPWIRE: NO monolithic append — archive/completed/YYYY-MM.md writes outside legacy/ are forbidden.
     Static-grep check: check-no-monolith-completion-append.sh (created in Chunk 10).
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

**Interactive override:** If `COMPLETION_NATURE` is set in the environment before invoking `/workstream-complete`, use that value as `nature:` directly and write `nature_inferred: false`. The env var bypasses the Sonnet dispatch entirely.

**Why AUTO-INFER not interactive-prompt:** workstream-complete fires in autonomous chains where no human is present; a skip-default would bias `--where nature=<x>` queries. See plan § Chunk 3 for full rationale.

#### Step 2.6.5 — Resolve `$em_sid` and derive `<sid6>`

**`$em_sid` sourcing (env-var-primary):**
1. If `$em_sid` is set in the environment, use it directly.
2. Else use `$CLAUDE_CODE_SESSION_ID` — the platform-injected session id (Claude Code ≥ ~2.1.150). Per-session and unclobberable by a sibling session, so it is authoritative.
3. Else read from `.git/coordinator-sessions/.current-session-id` (last-writer-wins sentinel — `session-init.sh` writes it on every SessionStart; only a fallback for old Claude Code, per `docs/wiki/claude-code-platform-gotchas.md`). If the sentinel read is ambiguous (flips between ids across reads), two sessions are live — do not trust it; the env var in step 2 is the answer.
4. Do NOT use `meta.json`-based lookup — it is circular (you need `$em_sid` to find the directory containing `meta.json`).

`<sid6>` = last 6 characters of the resolved `$em_sid`. If `$em_sid` cannot be resolved, generate a 6-char hex fallback from the current timestamp (`date +%s | tail -c 7 | head -c 6`).

The `<sid6>` suffix ensures uniqueness per session with no race condition.

#### Step 2.6.5a — Compute LoE block

> **Behavioral rule (tripwire):** Workstream-complete MUST invoke `coordinator-session-loe.sh` (or `aggregate-chain-loe.sh` for chain-terminal) to write per-session LoE into the completion entry. Skipping this step produces an incomplete entry that Phase 3 consumers and workweek-complete cannot query. No override mechanism; the `loe:` block is always written.

Determine whether this is a **single-session** or **chain-terminal** session using the same detection logic as Step 2.9 chain-end detection:
- **Single-session:** this session was NOT opened via `/pickup` (no predecessor handoff consumed).
- **Chain-terminal:** session was opened via `/pickup` AND is ending via `/workstream-complete` (not `/handoff` or `/spinoff`).

**Single-session path:**

```bash
loe_block=$(~/.claude/plugins/coordinator/bin/coordinator-session-loe.sh \
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
2. Walk `state/handoffs/archive/<YYYY-MM>/` for entries with `consumed_by: <this session_id>`.

Then invoke the chain aggregator:

```bash
loe_block=$(~/.claude/plugins/coordinator/bin/aggregate-chain-loe.sh \
  --terminal-handoff "<resolved-predecessor-path>" \
  --format yaml-frontmatter 2>/dev/null)
```

If the script is absent or returns non-zero, degrade the same way as the single-session path. The resolved `$loe_block` is embedded into the completion entry frontmatter in Step 2.6.6.

#### Step 2.6.6 — Write per-entry file

For each untracked completed work item (or one entry if work is cohesive), write:

```
archive/completed/YYYY-MM/YYYY-MM-DD-<chain-slug>-<sid6>.md
```

(chain null → `YYYY-MM-DD-adhoc-<sid6>.md`). Create the `YYYY-MM/` subdirectory if absent.

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

Frontmatter semantics: `nature_inferred` true on AUTO-INFER, false on `COMPLETION_NATURE` env override; `chain_terminal` true on `/pickup`→`/workstream-complete`; `authored_by` = `$em_sid` or null; `status: pending-release` always; `loe` from Step 2.6.5a (chain-terminal adds aggregate + chain-summary fields; `loe.tshirt: null` = script unavailable). `<sid6>` ensures uniqueness — no collision handling needed.

#### Step 2.6.7 — Judgment filter

Not every commit is a work item. Group related commits into a single archive entry. Skip trivial commits (typo fixes, formatting). If a session produced no substantive commits beyond doc/lesson housekeeping, no archive entry is needed — skip silently.

### Step 2.65: Cross-repo memo lifecycle sweep — flip resolved memos to `actioned`

When the session's work resolves a cross-repo memo in **this repo's** `cross-repo/inbox/`, flip `status: open → actioned` (with optional `decision:` line) so the inbox accurately reflects channel state.

**Detection — non-automatable; prompt the EM** (no reliable programmatic signal connects commits to memo resolution):

1. **Glob** `cross-repo/inbox/*.md` in the current repo. Parse YAML frontmatter; filter to `status: open` (or absent → treat as open).
2. **If zero matches:** skip this step silently.
3. **If ≥1 matches:** list each as a numbered line — `N. <basename> — <title or first heading> (from: <from>, topic: <topic>)`. Then ask once, plain prose: _"Any of these resolved this session? If yes, give me the numbers; I'll flip `status: actioned` and add a one-line `decision:` you dictate. (Type none if none.)"_
4. **For each named memo:** Edit the file in place — set `status: actioned` and append `decision: <PM-supplied line>` to the frontmatter. Then **sweep it out of the inbox**: `git mv cross-repo/inbox/<file> cross-repo/archive/<file>`. Create `cross-repo/archive/` if absent. Both the edit and the move fold into Step 3's commit.

**Out of scope here:** sender side; memos the session created or moved; memos in `cross-repo/archive/`. Do NOT touch any other repo's `cross-repo/`.

**Why here:** batching at session close is cheaper than inline at resolution time.

### Step 2.66: Sender-side — do NOT re-surface already-sent memos

If this session sent a `cross-repo-memo` or doctrine-seeded a sibling repo, **do NOT list it as "pending PM-relay" or "pending your action" in the Final Summary, `Flag to PM:`, or any follow-on `/handoff`.** The receiver's inbox is the canonical channel; sender-side status knowledge decays. Banned phrasings: *"PM-relays pending your action"*, *"Cross-repo memo X awaiting relay"*, *"doctrine-seed Y pending sibling-EM action."* → `docs/wiki/cross-repo-communication.md` § Don't re-nag the PM about already-sent memos.

### Step 2.7: Archive Predecessor Handoff (if applicable)

When this session was opened with `/pickup`, the consumed handoff still lives in `state/handoffs/` (mutation-only at pickup time). If this session is ending via `/workstream-complete` rather than `/handoff`, archive the predecessor now.

**Detection:** scan `state/handoffs/*.md`, read frontmatter `consumed_by:`. Resolve session id: `$CLAUDE_CODE_SESSION_ID` first; `.git/coordinator-sessions/.current-session-id` fallback. Zero matches → skip. One match → archive. Multiple matches → log to stderr and archive all.

**Action:** `git mv state/handoffs/<file> archive/handoffs/<file>`. Create `archive/handoffs/` if absent. On `git mv` failure (already moved by a concurrent `/handoff`), log to stderr and continue. The move folds into the Step 3 commit.

**No claim release call needed** — `cs_archive` at Step 3.5 carries the entire session directory (including `handoff-claims/`) into `.archive/`. **Skip entirely if** exiting via `/handoff` — the two paths are mutually exclusive.

### Step 2.75: Refresh Handoff Tracker

After Step 2.7, regenerate `state/handoff-tracker.md`:

```bash
node ~/.claude/plugins/coordinator/bin/render-handoff-tracker.js
```

Skip silently if the script is absent or fails. Stage `state/handoff-tracker.md` in Step 3's scoped commit.

### Step 2.8: Refresh Orientation Documents

Update the documents that future sessions read for orientation — closing the read-write loop with `/workstream-start` and `/workday-start`.

1. **Orientation cache** (`state/orientation_cache.md`): **Do not author the cache body. Do not patch sections. Do not re-derive content section-by-section.** The cache schema (`pipelines/workday-start-internals.md` § 5.5) is owned by ceremony writers (`/workday-start`, `/update-docs`). `/workstream-complete` is a **mid-session writer** with a single, narrowly-scoped capability: pinboard append.

   **Pinboard rule (the only cache mutation permitted here):** if this session surfaced something the next session start MUST see, and it would otherwise be lost (a transient surface gotcha; a critical blocker context; an environment-specific caveat that fooled this session and will fool the next), write exactly one line to `## Pinboard` via the routine:

   ```bash
   bash ~/.claude/plugins/coordinator/bin/regenerate-orientation-cache.sh \
       --invoker workstream-complete \
       --pinboard "YYYY-MM-DD <writer-slug>: <one-line note>"
   ```

   One-slot escape valve — a second write overwrites, not appends. Cleared at every ceremony regen. If you want to write more than one line, that's a wiki edit, handoff body, or lessons.md entry. If nothing pinboard-worthy, do nothing. If the cache file doesn't exist (`ls state/orientation_cache.md` before asserting), skip.

2. **Project tracker** (`docs/project-tracker.md`): If it exists and this session completed or progressed tracked items, update their status rows. Only touch rows this session affected — don't re-derive the whole tracker.

3. **Action items** (first match: `ACTION-ITEMS.md`, `docs/active/ACTION-ITEMS.md`, `docs/ACTION-ITEMS.md`): If one exists and this session resolved any listed items, check them off or remove them per the file's existing conventions.

4. **Documentation index** (`docs/README.md`): If it exists and this session created new guides, added research files, or completed plan documents, patch the relevant table. Only touch rows this session affected.

**Concurrency note:** Targeted patches only — safe with concurrent agents working on different items.

### Step 2.9: Code Review Consideration

Assess whether this session's diff warrants a code review pass before committing. EM makes the call using the table below — this step is judgment, not ceremony.

**Diff-shape table:**

| Session shape | Default scale |
|---|---|
| Doc-only edits, lesson capture, no executor dispatched, no code touched | **None** |
| Single-file fix <50 LOC, no shared schema touched, no executor | **None** (but commit message names the change) |
| Any executor dispatched, OR >50 LOC code change, OR shared schema/seam touched | **`code-reviewer`** (Sonnet, locked — see `agents/code-reviewer.md`) |
| **Big-diff brightline** (any one of: ≥500 gross LOC (insertions+deletions), OR ≥5 commits, OR ≥4 distinct surfaces — e.g. bash + JSON + tests + doctrine. File count is reported for context but is NOT a gate; mass-renames touch many files at zero review-cost.) | **Partitioned `code-reviewer` dispatches — mandatory, not chain-end-gated.** See § Partitioning large surfaces |
| Chain-end (started with `/pickup`, ending without `/handoff`/`/spinoff`) AND chain diff is non-trivial | **`code-reviewer`** on chain diff |
| Chain-end AND chain diff exceeds the big-diff brightline above | **Partitioned `code-reviewer` dispatches**. Named reviewers (the Staff Engineer, personas) are for plans and architecture, not code output. Sonnet `code-reviewer` is the ceiling at workstream-complete |

**Precedence rule:** the big-diff brightline (row 4) and chain-end rows (5, 6) override workstream-complete rows (1, 2, 3) when they apply — partitioning is the integration-risk control, not a chain-end privilege.

**Brightline gate — mechanical, before picking a row.** Run `bin/review-brightline-gate.sh [<range>]`; verdict `PARTITION-MANDATORY` overrides row choice. Single-reviewer above the brightline is a doctrine violation — wiki § Worked counterexample.

**Anchored-ranges note:** the small-side anchor (50 LOC) is calibration — shape can adjust. **Big-side brightlines (≥500 gross LOC / ≥5 commits / ≥4 surfaces) are hard floors.** (Recalibrated 2026-06-09 — files count dropped as a gate, commits added, surfaces bumped 3→4. Rationale: file count is blunt — mass-renames touch many files at zero review-cost — while commit count tracks independent logical slices, which is what slicing operates on; 3 surfaces fired on routine hook-fixes (shell+test+wiki), 4 demands genuine breadth.)

**Partitioning large surfaces across multiple `code-reviewer` dispatches (rows 4 and 6 — the two partition-mandatory rows):**
Fan out into parallel `code-reviewer` dispatches over coherent slices (by package boundary, concern, or directory cluster) — no lens-orthogonality manifest or synthesizer required. Mechanics:
1. Each `code-reviewer` prompt names its slice explicitly (paths or commit subset) and an "out of scope: the rest of the chain diff" line.
2. **Dispatch in parallel; integrators are 1:1 with reviewer slices — one `coordinator:review-integrator` per `code-reviewer` slice, dispatched in parallel, each scoped to the same slice paths as its source reviewer.** No collation into a single union-integrator. **Mechanism:** `bin/fan-out-integrator.sh` (input: TSV of `<slice-id>TAB<reviewer-sidecar-path>TAB<scope-files>`; output: N parallel `coordinator:review-integrator` dispatch blocks). Manual N-prompt construction is permitted only when the script is unavailable — collation is never permitted. The reasoning is structural: reviewers were partitioned because one Sonnet couldn't fit the whole surface; the same context-fit constraint binds the integrator. A union-integrator inherits N reviewers' findings against N disjoint file sets and the merged scope is exactly what the slicing avoided — see `docs/wiki/review-integration-doctrine.md` § Integrator dispatches are 1:1 with reviewer slices.
3. Trail write uses `--reviewer code-reviewer`; record partition shape in the wrap-up sentence.
4. Post-review the Staff Engineer-escalation criteria apply to the **combined** finding set. No upper bound on partition count — the constraint is per-reviewer context fit, which (per item 2) is also the constraint on per-integrator scope.

**No named-reviewer escalation from code review.** Code output review is Sonnet `code-reviewer` only — partition across slices as needed. Architectural findings from `code-reviewer` → `state/lessons.md` + surface to PM; do not escalate to a named reviewer within the code-review path.

The weekly `/workweek-complete` Step 7 merge-gate is a separate, independent ceremony — do not skip workstream-complete review and "surface to PM for workweek."

**Anti-ceremony-bias tripwire:** `code-reviewer` is the floor on row-3+ sessions, not a negotiable add-on. Drafting a "waive with rationale" sentence on a row-3+ session is the tell — run the review. EM keeps waive authority on genuinely shallow row-3 diffs; the test is diff shape, not row number. → `docs/wiki/workstream-complete-review.md` § Why post-implementation review is not redundant with plan-time review.

**Chain-end detection:**
- Resolve session-id: `$CLAUDE_CODE_SESSION_ID` env var first (platform-injected, unclobberable); `.git/coordinator-sessions/.current-session-id` sentinel fallback only when the env var is empty.
- Chain-end signal: session opened via `/pickup` AND ending without `/handoff` or `/spinoff` invocation this session.
- **Trail is the only valid code-output coverage signal.** Read records via `list-review-trail-records.sh` (live AND archived — live-only glob misses prior-week reviews). Plan-level the Staff Engineer reviews are NOT trail records; a "the Staff Engineer reviewed the plan" handoff note does NOT satisfy the chain-end `code-reviewer` floor. No trail record covering the sha-range = unreviewed.

**Diff scope:**
- Chain-end → `git log $(git merge-base origin/main HEAD)..HEAD`
- Mid-chain → `git log $LAST_REVIEW_SHA..HEAD` (`$LAST_REVIEW_SHA` = most-recent trail record via `list-review-trail-records.sh | tail -1` whose `sha_range` head passes `git merge-base --is-ancestor <sha> HEAD`; iterate oldest to newest; fall back to session-start SHA if none passes).

**Dispatch:** invoke `coordinator:review-code` Branch A.2 with the resolved diff scope.

**Spec cross-reference (loop closure) — include in dispatch brief when a spec exists:**
When work is governed by a spec/plan/stub, name the spec path in the `code-reviewer` dispatch brief and instruct it to apply the **Spec completion lens** (per `agents/code-reviewer.md` § Spec completion lens). Apply on row 3/4/5/6 sessions; omit on row 1/2. If multiple specs apply, name all of them; the reviewer treats the union as the completion oracle. When partitioning the diff (§ Partitioning large surfaces), name each reviewer's spec slice explicitly.

Negative-spec: if no spec governs this session, omit the spec section from the brief — do not invent one. No spec named ⇒ reviewer skips the lens entirely.

**Findings disposition — fix everything, including nitpicks.** Every severity (P0/P1/P2/nitpick/observation/'consider') folds in via `coordinator:review-integrator` before the marker-trail write. "Recorded below blocking threshold" in the wrap-up is the tell that this rule was skipped — re-open and fold. Only legitimate skip: real tradeoff → escalate to PM (coordinator CLAUDE.md § Reviewer findings — apply, don't ratify).

The trail's `--verdict` field records the reviewer's pre-fix verdict (`ok`/`warn`/`blocked`), not what shipped — downstream load-shedding consumes the verdict; the trail is not a fix-completion log.

**Marker write:** after review integration completes, invoke:
```bash
~/.claude/plugins/coordinator/bin/coordinator-write-review-trail.sh \
  --sha-range <A..B> --reviewer <code-reviewer|patrik|code-reviewer+patrik|waived|ubt-compile> \
  --scope <chain|session> --verdict <ok|warn|blocked|waived|pending> --diff-loc <N>
```

**Negative-spec:**
- Trivial sessions (Row 1, 2 of the table): skip the review entirely. No trail record written.
- PM-waived sessions: log waiver to trail with `--reviewer waived --verdict waived`. Greppable as `verdict=waived`.

**Staging discipline:** files edited by `coordinator:review-integrator` must be staged via explicit path in Step 3 — not `git add -A`.

**UBT pending-marker (UE plugin work only):** If `bin/check-ubt-build-fresh.sh` exists in the cwd, invoke it in `--mode pending`. Captures the build verdict as a deferred record; resolution happens at `/workday-complete` Step 0c. This step is a no-op for non-UE repos (script absent) — the `[ -x bin/<name>.sh ]` pattern is the canonical convention for conditional UE-specific steps in coordinator skill bodies; future UE conditionals (`clippy`, etc.) follow this shape.

```bash
[ -x bin/check-ubt-build-fresh.sh ] && \
  bin/check-ubt-build-fresh.sh --since "$(git merge-base origin/main HEAD 2>/dev/null || git rev-parse HEAD~1)" --mode pending
```

### Step 2.95: Aftermath Lens-Checkers (big-workstream sessions)

**Fires on big workstreams** — same trigger as Step 2.9 rows 3/4/5/6. Skip silently on row-1/row-2 trivial sessions.

Step 2.9 is the *line-level* lens; these are *cross-cutting*. Quick self-check (not a reviewer dispatch unless depth needed):

1. **Install-surface completeness** — wrote state outside source (`machine-local/`, installer scripts, sentinels, env)? Confirm clean-install reproduces it. → `docs/wiki/install-surface-completeness.md`.
2. **Contact-point / convention drift** — added a convention, tripwire, hook, or agent-facing surface? Every contact-point updated in this workstream. → CLAUDE.md § Adding a Convention.
3. **Doc + wiki alignment** — big changes age `docs/README.md`, wiki, atlas; repoint stale refs (don't duplicate).
4. **Lessons + queue capture** — pattern worth promoting? Per Step 1/1.2; universals to central queue.
5. **Security / secret-exposure** — touched auth, secrets, external APIs, new deps? Route to `security-audit-worker` / `dep-cve-auditor` (CLAUDE.md § Reviewer-Routed Workers; `docs/wiki/reviewer-routed-workers.md`) — don't self-assess.

**Output:** one-line-per-lens checklist in Step 4 summary (`clear` / `<finding + disposition>`). Tradeoff-free corrections fold in; real tradeoffs surface to PM. "All clear" must be affirmative, not silent.

### Step 3: Commit + Verify Remote

#### Step 3.0: Pre-terminate dirty-tree gate

**Pre-terminate dirty-tree gate (fail loud on unattributable files).** Before the workstream-complete commit, run `git status --porcelain` and classify every dirty path. **EOL phantoms are benign — never case (c):** a file where `git diff --quiet -- <path>` exits 0 is a Git-for-Windows stat-staleness artifact (`docs/wiki/concurrent-em-hazards.md` § H23) — leave it untouched; swept by `coordinator-renormalize-index` at session start. Classify each remaining path:

- **(a) This session authored it** → it belongs in this terminator's scoped commit (handled by the existing scope/commit step).
- **(b) A known concurrent session owns it** → leave it alone. "Known" means you can name the workstream/session — a sibling `scope:` block, an active handoff, or a `consumed_by:` field in handoff frontmatter naming another session's id.
- **(c) Unattributable** — a dirty file you did NOT author AND cannot tie to a named concurrent owner (the classic case: an abandoned partial revert or orphaned edit from a crashed session). **Do NOT silently leave these — they wedge the next session opener.** Fail loud and pick exactly one disposition, in this order of preference:
  1. **Commit** with provenance if the change is coherent and you can attribute it: `git add -- <path> && git commit -m "chore: adopt orphaned WT change <path> — unattributed at workstream-complete"`.
  2. **Stash-with-provenance** if it is incoherent or risky to commit: `git stash push -u -m "orphaned-WT <YYYY-MM-DD> workstream-complete: <path> — left by unknown session" -- <path>`. Name the stash so the next session can find and adjudicate it (per CLAUDE.md "Probe edits in `git stash push -u` / `pop`").
  3. **Explicit "leave it owned by X"** only when you can now name the owner — record a one-line note (in the handoff body / session summary) stating which session/workstream owns it, converting it from case (c) to case (b).

The forbidden outcome is terminating with case-(c) files still dirty and unnamed. Orphan `.tmp.<pid>.<nanos>` files = Edit-tool atomic-write crash (CLAUDE.md § Verifying Executor Output) — diff against target before deleting; do not stash blind.

1. **Stage only paths this session touched — never `git add -A`.** Name each path explicitly: `git add <path1> <path2> ...`. Typical set: `state/lessons.md`, `docs/plans/<feature>.md` (if Step 2.4 ran), `archive/completed/YYYY-MM/<entry>.md`, `docs/project-tracker.md`, action-items, `docs/README.md`, `state/handoff-tracker.md` (if Step 2.75 ran). Unfamiliar dirty files → Step 3.0 gate first; "leave alone" is only correct for case (b) named-owner files.
2. Commit with a lightweight message: `"workstream-complete quick-save"`. (The post-commit hook will auto-push on work/feature branches.)
3. If nothing to commit, check for unpushed commits: `git log "origin/$(~/.claude/plugins/coordinator/bin/coordinator-current-branch)..HEAD" 2>/dev/null`
4. **Verify remote is synced:** confirm no unpushed commits remain. If auto-push failed, push explicitly and warn the PM.
5. If on main (shouldn't happen, but safety): push explicitly — `git push origin main`
6. If push fails (auth, network, conflicts), **warn the PM explicitly** — this is a critical failure

### Step 3.5: Archive Session Claim

Archive this session's claim directory — required at both `/workstream-complete` and `/handoff` to avoid forcing the next concurrent EM into a 24h wait.

Run:
```bash
sid="${CLAUDE_CODE_SESSION_ID:-$(cat "$(git rev-parse --show-toplevel)/.git/coordinator-sessions/.current-session-id" 2>/dev/null)}" && \
  source ~/.claude/plugins/coordinator/lib/coordinator-session.sh 2>/dev/null && \
  cs_archive "$sid" 2>/dev/null || true
```

Idempotent. Failures are non-fatal (24h reaper is the safety net). Skip if session id can't be resolved or lib is unavailable. Prefer `$CLAUDE_CODE_SESSION_ID`; `.current-session-id` is last-writer-wins fallback only.

### Step 3.8: Acceptance-Oracle Gate (AUTHORITATIVE)

<!-- spec-backlink: docs/wiki/acceptance-oracle.md § Where checked — gate seam relocated from /merge-to-main 2026-06-02 -->

If this session executed an oracle-bearing plan (one that went through `coordinator:review` and carries a bindable `## Acceptance Criteria` table with `gate-bound` rows), this is the authoritative gate. **One workstream = one plan = one AC table in frame; the oracle is load-bearing here, not at merge.**

**Plan-path discovery (try in order):**
1. Frontmatter `plan:` field on the workstream's plan document.
2. Explicit `--plan <path>` flag in `$ARGUMENTS`.
3. If neither yields a path AND the session shape is plan-execution → skip-with-offer: _"No plan path found — acceptance oracle can be validated manually with `bash check-acceptance-oracle.sh <plan-path>`."_ Continue to Step 4.

**If `COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1` is set:**
Skip the gate. Log: _"Acceptance-oracle gate bypassed via COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1 — exceptional use only."_ Continue to Step 4.

**If plan path resolved AND plan contains a bindable `## Acceptance Criteria` table:**

```bash
bash check-acceptance-oracle.sh <plan-path>
```

- **Exit 0 (all gate-bound rows green or cited-resolved):** Log the verdict. _"Acceptance oracle: all gate-bound tests pass — workstream may complete."_ Continue to Step 4.
- **Non-zero exit (any gate-bound row red or unresolved):** Hard-block. Print: _"Workstream-complete blocked: acceptance oracle has red/unresolved gate-bound tests."_ + the script verdict. Remediation: fix tests and re-run, OR mark deviations via `## Deviations` + `Status → shipped-differently` with a `cited:` row, OR set `COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1` (exceptional — `cited:` rows are the routine accommodation). Stop. Downstream `/merge-to-main` trusts this seam.

**If plan path resolved but no bindable `## Acceptance Criteria` table** (old-form plan): skip-with-offer: _"Plan found but no bindable acceptance-criteria table — oracle gate skipped. Consider upgrading (`docs/wiki/writing-plans.md` § Acceptance Oracle)."_

**If no oracle-bearing plan was involved** (doctrine/sweep/memo-action without a reviewed plan): skip silently. Daily-rollups and non-plan workstreams have nothing to gate on.

**Why authoritative here, not at merge:** `/merge-to-main` aggregates workstreams + doctrine edits + sweeps — no single AC table governs that union. The oracle is load-bearing where one plan is in frame.

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

If `$ARGUMENTS` is provided, use it as context for what was accomplished this session.
