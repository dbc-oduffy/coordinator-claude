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
3. **Step 2.9** (code review) — integrator-edited files must be staged in Step 3. On chain-end sessions, Step 2.9's chain-end coverage gate (`review-coverage-gate.sh`) is a predecessor to Step 3: the gate must emit `VERDICT=COVERED` (or an explicit `COORDINATOR_OVERRIDE_COVERAGE_GATE=1` waiver) before Step 3 may proceed.
4. **Step 2.4 → Step 3 staging edge** — when a governing plan exists, Step 2.4's reconciled plan doc (the corrected `docs/plans/<feature>.md`) must be staged in Step 3 before commit. Step 2.4 is a micro-chain off Step 2 in the todo-list cluster (see below); its output is part of Step 3's fan-in union, identical in shape to the existing Step 2.9-integrator-edits → Step 3 staging edge.
5. **Step 3** (commit + verify remote) — fan-in of ALL preceding file edits (lessons, plan docs, archive entries, orientation cache, action-items, review-integrator outputs, reconciled plan doc, **Step 2.67 deletions named in commit body**); commit consumes the union via explicit-path staging. Step 3 step 1.5 (structural gate) runs between stage and commit; step 2 commits FROM the validated file via `git commit -F "$msg_file" -- "${WSC_PATHS[@]}"` (explicit pathspec — never a bare `git commit -F`, which would absorb a sibling's staged files on the shared index).
6. **Step 3.5** (archive session claim) — consumes Step 3's pushed commit.
7. **Step 4** (final summary) — informational. Fan-in of todo-list outputs: lessons (Step 1/1.2), plan update (Step 2/2.4), archive entry (Step 2.6), handoff archive (Step 2.7), orientation refresh (Step 2.8), code review disposition (Step 2.9/2.9b), cross-cutting check (Step 2.95), and **completeness-checklist advisory WARN (Step 2.96)** — the Step 2.96 one-liner (`Completeness checklist: N items unverified — WARN emitted` / `all verified / not applicable`) is a required input to the Step 4 summary.
   <!-- Review: code-reviewer — F10: added Step 2.96 to the Step 4 gate summary line so the completeness-checklist advisory feeds the final summary explicitly -->

**Todo-list (execute in any order, batch parallel where two independently read/write different files — with the Step 2→2.4 micro-chain exception noted below):**

- **Step 1 (then 1.2) — run as an inseparable pair, one todo-list slot** — lessons capture + classification (`state/lessons.md`). The 1→1.2 edge is real; run them sequentially as a unit; the *pair* parallelizes with the other slots.
- **Step 2 (then 2.4) — run as a micro-chain, one todo-list slot** — plan documentation (`docs/plans/`, `tasks/<feature>/todo.md`, etc.), then plan-doc reconciliation. The 2→2.4 edge is real: Step 2.4 reconciles the plan doc Step 2 just updated. Run them sequentially as a unit; the *pair* parallelizes with the other slots. Skip Step 2.4 if no governing plan exists.
- **Step 2.6** — archive uncaptured work (`archive/completed/YYYY-MM/`; internal chain 2.6.1→2.6.7 is real but isolated to this slot)
- **Step 2.7** — archive predecessor handoff (file move only — independent of all other slots)
- **Step 2.8** — refresh orientation documents (pinboard + tracker + action-items + docs README)
- **Step 2.9b** — dispatch-shape observation (read-only; never blocks; surface any offer into Step 4 summary) — parallel-safe with the 2.x cluster
- **Step 2.95** — cross-cutting check (big-workstream only; one-line `clear` / `<finding>` in Step 4 summary) — parallel-safe with the 2.x cluster
- **Step 2.96** — completeness-checklist advisory WARN (opt-in: fires only when consumed baton carries `completeness_checklist:` frontmatter; silent no-op on ordinary sessions) — parallel-safe with the 2.x cluster

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

- **Yes (universal):** (a) tag with `[universal]` on the bold title line; (b) write a structured central improvement-queue entry via the CLI — `from_repo` is auto-derived from the invoking repo's git root (registered repos use the machine-local shortname; unregistered repos fall back to the basename): <!-- Review: code-reviewer — F8: from_repo derivation clarified -->
  ```
  coordinator-queue-append --schema improvement-queue --queue-scope central \
    --title "<summary>" \
    --body "<the rule / context; cite evidence: state/lessons.md:<line> and proposed target: <coordinator file>" \
    --surface "state/lessons.md:<line>" \
    --proposed-action "<coordinator file>" \
    --change-kind <skill-edit|hook-edit|wiki-append|wiki-new|agent-prompt-edit> \
    --status open
  # Review: code-reviewer — F2: pick the most accurate --change-kind for the lesson.
  # Valid values: skill-edit, hook-edit, wiki-append, wiki-new, agent-prompt-edit.
  ```
  The CLI writes directly to `~/.claude/state/improvement-queue/<date>-<slug>.yaml` when `--queue-scope central` is set (dedup is not enforced by the CLI — skip the write if the same `state/lessons.md:<line>` evidence already appears in an existing entry under `~/.claude/state/improvement-queue/`). `from_repo` is auto-derived from the invoking repo's git root (registered repos use the machine-local shortname; unregistered repos fall back to the basename). <!-- Review: code-reviewer — F8: from_repo derivation restated accurately -->
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
- **Acceptance Criteria oracle tables** — AC tables (columns: `ID | Criterion | Test | Binding-Class | Status`) are consumed by `check-acceptance-oracle.sh`. **In-place correction of an AC table is scoped to the Status/note columns only** (e.g. `Status → shipped-differently` with a note cell). Free-text mutation of the `Criterion` or `Test` cells would corrupt the structured oracle the parser expects. Substantive "what shipped vs forecast" delta routes to the Decisions Made section's `(was: <plan-forecast>)` annotation — NOT a free-text edit of Criterion/Test cells.

The `(was: <plan-forecast>)` annotation maps to distill's `[SUPERSEDED]` nugget class — superseded provenance only; what crystallizes is the shipped reality.

#### No audit table append

The `(was: <plan-forecast>)` ALLOWLIST corrections above are the canonical "what shipped vs forecast" surface — distill Phase 1 reads them and tags `[SUPERSEDED]`. The `## Deviations` audit table was retired 2026-06-15: historical archived plans may carry one (distill's `[EPHEMERAL]` exemption still handles them), but Step 2.4 no longer writes new ones. Reasoning lives in the corrected ALLOWLIST entries and in git history. → `docs/wiki/plan-deviation-reconciliation.md`.

#### Soft-ordering note re Step 2.9

Step 2.9's spec-completion lens is a soft input to this step, not a hard predecessor — Step 2.4 reconciles what the EM knows from session context. If Step 2.9 surfaces additional drift, fold those findings before Step 3. Two write-back types: Step 2.4 performs *forecast→reality* corrections; Step 2.9's integrator path performs *defect-fix* write-backs. Both fan into Step 3's staging union.

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

<ONE paragraph (≤8 sentences): what shipped + why it matters. NOT a synthesis log — reviewer chain belongs in the plan, deviations belong in the plan's ALLOWLIST (was: ...) corrections, AC results belong in the plan's AC table. The completion entry is the queryable index, not the synthesis archive.>
```

**Banned prose-body sections in completion entries:** `## Reviewer chain`, `## Deviations from plan`, `## Acceptance criteria` (redundant with plan), `## Universal lessons captured` (covered by Step 1.2 central-queue append). Prose body is ONE paragraph; structural sections belong in the plan, not here. The prose body has no mechanical consumer (`bin/query-records` consumes frontmatter only) — its sole purpose is one-paragraph human-readable context for the archive index.

Frontmatter semantics: `nature_inferred` true on AUTO-INFER, false on `COMPLETION_NATURE` env override; `chain_terminal` true on `/pickup`→`/workstream-complete`; `authored_by` = `$em_sid` or null; `status: pending-release` always; `loe` from Step 2.6.5a (chain-terminal adds aggregate + chain-summary fields; `loe.tshirt: null` = script unavailable). `<sid6>` ensures uniqueness — no collision handling needed.

#### Step 2.6.7 — Judgment filter

Not every commit is a work item. Group related commits into a single archive entry. Skip trivial commits (typo fixes, formatting). If a session produced no substantive commits beyond doc/lesson housekeeping, no archive entry is needed — skip silently.

### Step 2.65: Cross-repo memo lifecycle sweep — flip resolved memos to `actioned`

When the session's work resolves a cross-repo memo in **this repo's** `cross-repo/inbox/`, flip `status: open → actioned` (with optional `decision:` line) so the inbox accurately reflects channel state.

**Detection — non-automatable; prompt the EM** (no reliable programmatic signal connects commits to memo resolution):

1. **Glob** `cross-repo/inbox/*.md` in the current repo. Parse YAML frontmatter; filter to `status: open` (or absent → treat as open).
2. **If zero matches:** skip this step silently.
3. **If ≥1 matches:** list each as a numbered line — `N. <basename> — <title or first heading> (from: <from>, topic: <topic>)`. Then ask once, plain prose: _"Any of these resolved this session? If yes, give me the numbers; I'll flip `status: actioned` and add a one-line `decision:` you dictate. (Type none if none.)"_
4. **For each named memo:** Edit the file in place — set `status: actioned` and append `decision: <PM-supplied line>` to the frontmatter. The flip (judgment: which memos this session resolved) is non-automatable and stays here.
5. **Sweep the inbox via the shared function** — do NOT hand-roll per-memo `git mv`. After the flips, run the same sweep session-init uses so the just-flipped memos (and any actioned stragglers) move to `cross-repo/archive/` (flat) with the skip/idempotency/claim-safety guards in one place:
   ```bash
   source "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_HOME:-${HOME}}/.claude/plugins/coordinator-claude/coordinator}/lib/coordinator-session.sh"
   cs_sweep_actioned_memos "$(git rev-parse --show-toplevel)" >/dev/null
   cs_sweep_terminal_plans "$(git rev-parse --show-toplevel)" >/dev/null
   ```
   Both functions stage their moves (neither commits); they fold into Step 3's commit alongside the in-place edits. `cs_sweep_terminal_plans` archives terminal (implemented/superseded/abandoned) plans from `docs/plans/` to `archive/specs/YYYY-MM/` using the same enumerate/skip/git-mv shape as the memo sweep. Skip this step's prompt if the glob in (1) found zero open memos — the staged moves are still picked up because the functions re-enumerate independently.

**Belt-and-suspenders, not load-bearing:** this step is now an *immediate* sweep (cheaper than waiting for the next session-init). Even if it is skipped entirely — a bare `/pickup` that actions a memo and never reaches `/workstream-complete` — the next `session-init.sh` boot auto-sweeps the actioned memo via the same `cs_sweep_actioned_memos`. The in-place `status: actioned` commit is therefore always safe to leave in the inbox; archival is guaranteed downstream.

**Do-now violation check (belt-and-suspenders).** While the inbox is globbed, also scan for the deferral anti-pattern: an `ask` memo the session **accepted in word but didn't land** — `decision: accepted` with no real `realized_by` (missing, or a prose value the schema would reject), or an `open`/`in_progress` memo whose `decision_note` reads *"will land before <release/gate>."* That is a do-now ask deferred (→ `docs/wiki/cross-repo-communication.md` § Do-now applies to memos). A *"land before X happens"* ask is do-now: landing on `origin/main` is the work-gate (do-now); synchronized go-live is the PM-owned release-gate, not a reason to leave the fix undone. **Do the work now** and stamp a real `realized_by: <SHA>`, or — if genuinely blocked — Decline-with-rationale / Surface-to-PM. Never close the session on an accepted-but-unlanded memo.

**Out of scope here:** sender side; memos the session created or moved; memos in `cross-repo/archive/`. Do NOT touch any other repo's `cross-repo/`.

**Why here:** batching at session close is cheaper than inline at resolution time.

### Step 2.66: Sender-side — do NOT re-surface already-sent memos

If this session sent a `cross-repo-memo` or doctrine-seeded a sibling repo, **do NOT list it as "pending PM-relay" or "pending your action" in the Final Summary, `Flag to PM:`, or any follow-on `/handoff`.** The receiver's inbox is the canonical channel; sender-side status knowledge decays. Banned phrasings: *"PM-relays pending your action"*, *"Cross-repo memo X awaiting relay"*, *"doctrine-seed Y pending sibling-EM action."* → `docs/wiki/cross-repo-communication.md` § Don't re-nag the PM about already-sent memos.

### Step 2.67: Self-clean session-authored transient artifacts

<!-- Spec backlink: docs/plans/2026-06-15-workstream-complete-self-clean.md -->

The EM has freshest context on what's trash vs. potentially-useful for the work this session shipped — that judgment decays once the session ends. Enumerate-and-defer-to-`/distill` is a doctrine violation: `/distill` is record-keeping (extracting the shape of shipped/decided work into wiki), NOT a disposal route. **Default = delete.** The session commit IS the recovery substrate; forensics via `git log -- <paths>` and `git show <sha>^:<path>` recover any item later judged useful. This is Layer 3 of the cruft-sweep cadence — front-line judgment at the workstream terminator. → `docs/wiki/cruft-sweep-cadence.md` § Three-layer design.

**Session-authored predicate (operational test — pin before enumerating):** A file is "session-authored" iff it appears in `git status --porcelain` AND one of:
- (a) `git log --diff-filter=A --since="$SESSION_START_TIME" -- <path>` shows this session created it, OR
- (b) the path is untracked AND its mtime is after `$SESSION_START_TIME` AND it is NOT classifiable as Step 3.0 case (b) ("known concurrent session owns it" — sibling `scope:` block, active handoff, or `consumed_by:` in handoff frontmatter naming another session id).

Resolve `$SESSION_START_TIME` as: the mtime of `.git/coordinator-sessions/<sid>/` claim dir, OR — if absent — the timestamp of this session's first commit on the active branch. Files that fail BOTH (a) and (b) are NOT session-authored and fall through to Step 3.0's case (a)/(b)/(c) classifier with no change in semantics.

**Procedure (hard step, default delete):**

1. Enumerate files passing the session-authored predicate under `tasks/` and adjacent scratch surfaces: sender-side `cross-repo-memo` reference copies, working notes the EM authored mid-flow, draft snippets that didn't ship, intermediate scratch under `tasks/<feature>/` that isn't the feature plan / todo / completion-log entry.
2. For each, choose `git rm` OR justify-keep with a one-line reason. Default is delete. Examples of valid justify-keep reasons: *"PM may need this for next-turn follow-on"* (the 2026-06-14 lessons.md note: don't strip scratch the PM hasn't had a turn to action), *"still load-bearing for active sibling workstream"*, *"cited verbatim from active plan"*.
3. Stage the deletions into Step 3's scoped commit. The commit body MUST carry the structured blocks below; the structural gate in Step 3 step 1.5 validates them before the commit lands.

   **Commit-body block format (machine-parsed by `bin/check-workstream-complete-deletion-blocks.sh`):**
   - `Deleted (Step 2.67):` block — one path per line, **no leading whitespace**, no trailing reason. Format: `<path>\n`.
   - `Kept (Step 2.67):` block — one entry per line, format `<path> — <reason>` (em-dash U+2014 with single space on each side as the separator). Path first, no leading whitespace.
   - Block-end is the NEXT `^[A-Z][a-z]+ \(Step 2\.67\):` header OR the literal footer line `--- end Step 2.67 blocks ---`. **Blank lines INSIDE a block are permitted** (paragraph grouping); they do NOT terminate the block.
   - Always emit the `--- end Step 2.67 blocks ---` footer after the last Step 2.67 block, so the gate's block-end detection is unambiguous.

   The named-path discipline is what makes `git log -- <path>` and `git show <sha>^:<path>` recovery work.

**Seam with Step 3.0 (dirty-tree gate):** Step 2.67 runs BEFORE Step 3.0. It operates ONLY on files passing the session-authored predicate above. Files Step 2.67 keeps (justify-keep) stage as case (a) at Step 3.0 — they commit normally. Files Step 2.67 declines because they fail the predicate fall through to Step 3.0's case (a)/(b)/(c) classifier unchanged. Step 2.67 NEVER touches files Step 3.0 would classify case (b) ("known concurrent session owns it") or case (c) ("unattributable"); the disjoint-scope discipline is what keeps the two steps from fighting each other.

**Keep-list (NEVER self-cleaned at this step):**
- `docs/plans/*.md` — plan files are high-value distillation input (current plans carry `(was: <plan-forecast>)` ALLOWLIST annotations; legacy plans may carry `## Deviations` logs).
- `tasks/<feature>/todo.md`, `tasks/<feature>/plan.md` — feature-scoped plan files are load-bearing per CLAUDE.md § Task Management.
- `archive/completed/**` — completion-log entries written this session (Step 2.6.6).
- `state/**` allowlist surfaces (orientation_cache, handoffs/, handoff-tracker, lessons.md, week-changelog/, review-trail/, memos/, ledgers, queues).
- `archive/handoffs/**` — predecessor handoff archived in Step 2.7.
- `cross-repo/inbox/**`, `cross-repo/archive/**` — lifecycle owned by Step 2.65, not Step 2.67.
- Any file a known concurrent session owns (Step 3.0 case (b)).

**Banned Final Summary phrasings** (the enumeration-without-deletion shape):
- *"Transient artifacts (`/distill` will sweep): …"*
- *"Other working files predating this session"* (without disposition)
- *"Will be cleaned up later"* / *"safe to delete in a future pass"*
- Any *(transient|scratch|working|temporary|trash|tmp|residual|leftover)…(sweep|distill|future|later|next|cleanup|clean.up|downstream|pruned|pruning)* pattern (broadened to catch paraphrase evasion — also enforced as a tripwire registry entry).

If the EM finds itself drafting one of those phrasings, the failure mode is THIS step — return here, delete or justify-keep, then write the summary. The Final Summary names what was deleted, not what will be swept.

### Step 2.7: Archive Predecessor Handoff (if applicable)

When this session was opened with `/pickup`, the consumed handoff still lives in `state/handoffs/` (mutation-only at pickup time). If this session is ending via `/workstream-complete` rather than `/handoff`, archive the predecessor now.

**Detection:** scan `state/handoffs/*.md`, read frontmatter `consumed_by:`. Resolve session id: `$CLAUDE_CODE_SESSION_ID` first; `.git/coordinator-sessions/.current-session-id` fallback. Zero matches → skip. One match → archive. Multiple matches → log to stderr and archive all.

**Action:** Before moving, stamp `shipped_in:` into the handoff frontmatter — the SHA must be captured while the file is still in `state/handoffs/` and the workstream's commit context is fresh:

```bash
source "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_HOME:-${HOME}}/.claude/plugins/coordinator-claude/coordinator}/lib/coordinator-archive-stamp.sh"
stamp_shipped_in "state/handoffs/<file>" --allow-branch-tip-fallback
```

The `--allow-branch-tip-fallback` flag is correct here: this is a ceremony-complete path where the workstream actually finished, so the branch tip is a plausible signal for the completed workstream. If stamping finds no SHA, it exits 0 and skips silently — the `git mv` still proceeds.

**Shared-branch tip caveat.** On a shared concurrent-EM branch (`work/{machine}/{date}`), the branch tip at this moment may be a SIBLING EM's HEAD commit — not this session's last commit — because auto-push from a concurrent session may have landed between this session's last commit and this ceremony step. Before trusting the stamped `shipped_in` SHA, verify it belongs to this session: `git show --format='%s%n%(trailers:key=Session-Id)' --no-patch <sha>` must surface a `Session-Id:` trailer matching `$CLAUDE_CODE_SESSION_ID`. If the trailer is absent (legacy commit) or mismatches, walk `git log` backwards from HEAD until you find a commit with a matching trailer — that SHA is the correct `shipped_in` value. If no matching commit is found in the last 20 commits, record `shipped_in` as `null` and note the ambiguity in Step 4. [source: queue-triage-2026-06-21 chunk-5, queue line 143]

Then move into the handoff's **month-subfolder** (matching the `archive/specs/YYYY-MM/` convention) — derive `YYYY-MM` from the handoff filename's date prefix:

```bash
bn="$(basename "<file>")"; ym="${bn:0:7}"   # filenames start YYYY-MM-DD..; first 7 chars = YYYY-MM
mkdir -p "archive/handoffs/$ym"
git mv "state/handoffs/$bn" "archive/handoffs/$ym/$bn"
```

(If the filename has no `YYYY-MM` date prefix — e.g. a no-date install baton — fall back to flat `archive/handoffs/$bn`.) Create the month dir if absent. On `git mv` failure (already moved by a concurrent `/handoff`), log to stderr and continue. The move folds into the Step 3 commit.

**No claim release call needed** — handoff claims are basename-only (`.git/coordinator-sessions/handoff-claims/<basename>/`, NOT under `<sid>/`, since 2026-06-17 — see DR-110 § Correction), so `cs_archive` does NOT carry them; they are reaped by `cs_reap_stale_claims` (dead-PID only, session-init gated, ~12h cadence) or taken over inline on the next pickup of the same baton. **Skip entirely if** exiting via `/handoff` — the two paths are mutually exclusive.

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

**Brightline gate — mechanical, before picking a row.** Run

```
~/.claude/plugins/coordinator/bin/review-brightline-gate.sh --session-id "${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-$(cat .git/coordinator-sessions/.current-session-id 2>/dev/null)}}"
```

The `--session-id` flag scopes the gate's diff to commits authored by THIS session (matched by `Session-Id:` git trailer injected by `prepare-commit-msg`); without it, the gate computes over the whole shared-branch diff and fires `PARTITION-MANDATORY` on concurrent EMs' already-reviewed work — the 2026-06-15 multi-EM-brightline-noise failure (`docs/wiki/workstream-complete-review.md` § Session-scoped diff via `--session-id`). Verdict `PARTITION-MANDATORY` overrides row choice. Single-reviewer above the brightline is a doctrine violation — wiki § Worked counterexample. **AC6 semantics:** if `--session-id` filters to zero matching commits (legacy commits without trailers, or session-id mismatch), the gate emits `filtered_to=0 VERDICT=single-reviewer-ok` with a stderr note — fail-loud-non-blocking, EM verifies scope manually. Silent fallback to whole-branch is deliberately NOT provided.

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
- Resolve session-id: `$CLAUDE_SESSION_ID` (explicit override) first; then `$CLAUDE_CODE_SESSION_ID` (platform-injected, unclobberable); then `.git/coordinator-sessions/.current-session-id` sentinel (last-writer-wins fallback) — identical resolution order to `bin/coordinator-write-review-trail.sh:182-199`.
- Chain-end signal: session opened via `/pickup` AND ending without `/handoff` or `/spinoff` invocation this session.

**Coverage gate (chain-end path — mechanical, required):**

Run `review-coverage-gate.sh` over the full chain, scoped to the closing workstream's files when known. Derive scope from the governing plan or handoff `scope:` field. If no scope paths are known, run UNSCOPED — never pass an empty pathspec.

<!-- TEMPLATE: set SCOPE_ARGS below from the governing plan or handoff scope: field before running -->
<!-- VERBATIM — run this block exactly as written; adapt SCOPE_ARGS for your workstream scope -->
```bash
REPO=$(git rev-parse --show-toplevel)
GATE="$REPO/plugins/coordinator/bin/review-coverage-gate.sh"

# Review: F9 — use SCOPE_ARGS variable; angle-bracket placeholder would be read as a redirect if unsubstituted
SCOPE_ARGS=""  # set to: --scope-paths path1 path2 ... when scope known from plan/handoff; empty = unscoped (safe fallback)

VERDICT_LINE=$(bash "$GATE" $SCOPE_ARGS)
echo "$VERDICT_LINE"
if echo "$VERDICT_LINE" | grep -q 'VERDICT=UNCOVERED'; then
  # Review: F3 — uncovered commits already surfaced on stderr from the first call above; no re-run needed
  # Review: F2 — COORDINATOR_OVERRIDE_COVERAGE_GATE=1 allows PM-authorized bypass
  if [ "${COORDINATOR_OVERRIDE_COVERAGE_GATE:-0}" = "1" ]; then
    echo "WARNING: COORDINATOR_OVERRIDE_COVERAGE_GATE=1 — coverage gate bypassed by PM override." >&2
  else
    echo "HALT: coverage gate UNCOVERED — dispatch coordinator:review-code on the listed commits, then re-run the gate." >&2
    echo "Override (PM-authorized only): set COORDINATOR_OVERRIDE_COVERAGE_GATE=1 to bypass." >&2
    # The uncovered commits MUST go under coordinator:review-code before asserting merge-ready.
    # After review integration completes and the trail record is written, re-run the gate.
    # The gate must show VERDICT=COVERED before proceeding to Step 3.
    exit 1
  fi
fi
```
<!-- /VERBATIM -->

Output line shape: `range=… chain_commits=N covered=M uncovered=K VERDICT={COVERED|UNCOVERED}`. On `UNCOVERED`, per-commit `uncovered: <sha> <subject>` lines appear on stderr. The gate exits 0 on both verdicts — parse the VERDICT token, do NOT rely on exit code.

**On UNCOVERED:** the listed commits MUST be dispatched to `coordinator:review-code` before this session asserts merge-ready. After review integration completes and the trail record is written, re-run the gate — it must show `VERDICT=COVERED` before proceeding.

**The mechanical gate is the only valid coverage signal.** A workstream is unreviewed until the gate emits `VERDICT=COVERED` — no prose note, handoff frontmatter, or plan-review annotation substitutes for the gate.

**Coverage-completeness risk:** `--scope-paths` narrowing is a coverage-completeness risk if the handoff scope is underspecified — commits that touched the workstream's real surface but fall outside the declared pathspec are excluded from `chain_set` and silently pass. The unscoped `/merge-to-main` gate is the intended backstop. An empty or missing scope falls back to UNSCOPED whole-chain.

**Diff scope (mid-chain path):**
- Chain-end → default range `$(git merge-base origin/main HEAD)..HEAD` (the gate's built-in default)
- Mid-chain → `git log $LAST_REVIEW_SHA..HEAD` (`$LAST_REVIEW_SHA` = most-recent trail record via `list-review-trail-records.sh | tail -1` whose `sha_range` head passes `git merge-base --is-ancestor <sha> HEAD`; iterate oldest to newest; fall back to session-start SHA if none passes)

**Dispatch:** invoke `coordinator:review-code` Branch A.2 with the resolved diff scope.

**Doc-fragile domain lens (parallel sibling — UE, Unity, fast-moving SDK APIs):**

Sonnet executors confidently hallucinate API signatures in domains where training data lags reality (canonical example: Unreal Engine 5.6/5.7 — class renames, deprecated specifiers, header reshuffles). The fix-where-it-lands-cheapest position is a post-execution docs verification pass, not a "research as you go" mandate on every dispatch.

Gate (BOTH must hold):
1. `coordinator.local.md` declares a doc-fragile domain via `project_subtypes`. Current table:

   | `project_subtypes` contains | Fragile filetypes (diff must touch ≥1) |
   |---|---|
   | `unreal` | `*.cpp`, `*.h`, `*.hpp`, `*.uproject`, `*.uplugin`, `*.Build.cs`, `*.Target.cs` |
   | `unity` | `*.cs`, `*.asmdef`, `Packages/manifest.json` |
   | `godot` | `*.gd`, `*.tscn`, `*.tres` |

   Extensible — add rows when a new doc-fragile domain surfaces. Absent declaration ⇒ skip silently (no false positives on generic C++/C# projects where training data is fine).

2. The diff scope (resolved above — chain-end or mid-chain) actually touches ≥1 of the gated filetypes for the declared subtype. `git diff --name-only <A>..<B>` filtered through the table. Zero matches ⇒ skip silently (bash-only sessions in a UE repo don't trigger).

Dispatch shape: `coordinator:docs-checker` agent (Sonnet, read-write), **in parallel with** the `code-reviewer` dispatch above — orthogonal lenses on a frozen diff, the same exemption carved out in coordinator CLAUDE.md § Review Sequencing for merge-gate code review. No synthesizer; findings feed `coordinator:review-integrator` alongside code-reviewer findings (one integrator pass over the union, since file overlap is non-disjoint by construction — both lenses scan the same diff).

Brief inlines: (a) the resolved sha-range, (b) the filetype filter from the table above, (c) post-execution context note — "you are verifying executor-shipped code, not pre-screening a plan; findings route through review-integrator, not back to a plan author".

Trail field: `--reviewer` becomes `code-reviewer+docs-checker` when both ran. Schema-compatible (the field is free-text by convention; `+` is the existing combiner — see existing `code-reviewer+patrik` value in the writer script).

Negative-spec: row 1/2 sessions (no code touched) skip docs-checker the same way they skip code-reviewer — the gate's filetype precondition handles this automatically.

**Spec cross-reference (loop closure) — include in dispatch brief when a spec exists:**
When work is governed by a spec/plan/stub, name the spec path in the `code-reviewer` dispatch brief and instruct it to apply the **Spec completion lens** (per `agents/code-reviewer.md` § Spec completion lens). Apply on row 3/4/5/6 sessions; omit on row 1/2. If multiple specs apply, name all of them; the reviewer treats the union as the completion oracle. When partitioning the diff (§ Partitioning large surfaces), name each reviewer's spec slice explicitly.

Negative-spec: if no spec governs this session, omit the spec section from the brief — do not invent one. No spec named ⇒ reviewer skips the lens entirely.

**Findings disposition — fix everything, including nitpicks.** Every severity (P0/P1/P2/nitpick/observation/'consider') folds in via `coordinator:review-integrator` before the marker-trail write. "Recorded below blocking threshold" in the wrap-up is the tell that this rule was skipped — re-open and fold. Only legitimate skip: real tradeoff → escalate to PM (coordinator CLAUDE.md § Reviewer findings — apply, don't ratify).

The trail's `--verdict` field records the reviewer's pre-fix verdict (`ok`/`warn`/`blocked`), not what shipped — downstream load-shedding consumes the verdict; the trail is not a fix-completion log.

**quota-exhausted dispatch detection — scan completed Agent dispatches' return bodies before writing any verdict-ok trail record.**

The doctrine root is `docs/wiki/tool-output-flakiness-protocol.md § API quota exhaustion looks like a clean "completed" return with error-text body`. Pattern set + corroboration rule (inlined here so the rule is greppable from the skill itself, per the dual-altitude convention with `snippets/quota-self-detect-preamble.md`):

| Pattern (case-INsensitive) | Alone-sufficient? |
|---|---|
| `resets [0-9][0-9]?:[0-9][0-9]` | Yes — time-signature is structurally unique to the quota-apology shape. |
| `session limit` | No — requires body length < 1024 bytes. |
| `rate limit` | No — requires body length < 1024 bytes. |
| `quota` | No — requires body length < 1024 bytes. |

**Also recognize the `QUOTA-EXHAUSTED-DISPATCH:` envelope** as a definite quota event (the agent self-detected and substituted — see `snippets/quota-self-detect-preamble.md`). No corroboration needed; the envelope IS the corroboration.

**On match:** treat the dispatch as failed-needing-re-dispatch. Do NOT write a verdict-ok trail record. Either (a) wait for quota reset and re-dispatch with the original brief, or (b) escalate to PM with the partial-coverage situation. The EM decides retry vs escalate based on retry budget. → `docs/wiki/tool-output-flakiness-protocol.md § API quota exhaustion`.

<!-- quota-scan precondition: the quota-exhausted dispatch detection above must pass before invoking this trail-write. -->
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

### Step 2.9b: Dispatch-Shape Observation (read-only, never blocks)

<!-- spec-backlink: archive/specs/2026-06/2026-06-22-invariant-verification-observers.md § C3 -->

**Peer read-only slot — parallel-safe with the 2.x cluster.** Runs alongside Step 2.95 and the other 2.x slots. Does NOT gate the commit (Step 3) or any other step. Read-only: consumes the plan's Dispatch Ledger and the session's dispatched-agents.txt; writes nothing.

**When to run:** any session where a governing plan with a `## Dispatch Ledger` exists (the plan slug or path is known from session context). Skip silently if no plan governs this session or the plan has no Dispatch Ledger.

**Invocation:**

```bash
bash ~/.claude/plugins/coordinator/bin/classify-dispatch-shape.sh \
  --plan-file <path/to/docs/plans/YYYY-MM-DD-<slug>.md>
```

Or by slug if the plan lives under `docs/plans/`:

```bash
bash ~/.claude/plugins/coordinator/bin/classify-dispatch-shape.sh <plan-slug>
```

**What it checks:** counts parallel-permitted gate-groups in the Dispatch Ledger (`runs: parallel`, `gate-kind ∈ {none, output-consumption-content, contract-change}`, excluding `inline (EM)` rows — F1) and compares against distinct EXECUTOR-CLASS agentIds in the session's `dispatched-agents.txt` (reviewers/scouts excluded — F3). If N > 1 parallel-permitted chunks were declared but only 1 executor agent is attributable, it emits a question-framed offer to stderr.

**Output disposition:** any offer text from stderr surfaces in the **Step 4 summary** (one-line mention: `Dispatch-shape: <paste or summarize offer>` / `Dispatch-shape: clear`). If nothing was emitted, write `Dispatch-shape: clear`. This is the only output required — no action is mandatory; the offer is advisory.

**Fidelity limit (stated in the tool's offer text):** records do not carry a plan slug; attribution is scoped to the em_sid session. Multi-plan sessions may mix agents from other plans. The classifier detects the gross serial-grind antipattern; fine-grained interleaving is not distinguishable. Pilot-then-expand and inline-EM shapes may also present as 1 agent — the offer asks a question rather than pronouncing a verdict.

### Step 2.95: Cross-cutting check (big-workstream sessions)

**Fires on big workstreams** — same trigger as Step 2.9 rows 3/4/5/6. Skip silently on row-1/row-2 trivial sessions.

One question: *anything cross-cutting that the line-level review at Step 2.9 wouldn't have surfaced?* Quick self-check against session memory — examples: install surface reproducing on a clean machine (→ `docs/wiki/install-surface-completeness.md`), a new convention's contact-points all updated (→ CLAUDE.md § Adding a Convention), security/secret surface clean (route to `security-audit-worker` / `dep-cve-auditor` for depth — don't self-assess), doc/wiki stale refs repointed, lessons captured (Step 1/1.2 covers; universals to central queue). Tradeoff-free corrections fold in; real tradeoffs surface to PM.

**Output:** one line in Step 4 summary — `clear` or `<finding + disposition>`. The five sub-areas have independent load-bearing gates elsewhere; this is the cross-cutting safety net, not a re-run.

**Sub-check: machine-local regeneratability (install-surface-completeness).** Run as a peer sub-check alongside the install-surface examples above. Offer-shaped — exit 0 always; findings to stderr only:

```bash
bash ~/.claude/plugins/coordinator/bin/check-machine-local-regeneratability.sh
```

A `session-accumulated-must-survive-crash` key with no tracked baseline declaration in `registry.toml` IS an install-surface defect (fresh-machine clone loses the value). The script emits a remediation offer on stderr when the condition is detected; it is silent on a clean registry. See `docs/wiki/machine-local-registry.md § 13` for the regeneratability classification table and `docs/wiki/install-surface-completeness.md § Bootstrap gap` for the broader context.

### Step 2.96: Completeness-Checklist Advisory WARN (refuses-silent-done)

<!-- spec-backlink: docs/plans/2026-06-24-install-baton-completeness-claude-code-validation.md § C7 -->
<!-- enforcement model: docs/wiki/install-surface-completeness.md § Post-Consumer Gates Must Be Advisory WARN, Not Hard-Fail -->

**Opt-in — fires only when all three conditions hold:**

1. This session was opened via `/pickup` (a handoff was consumed, i.e. `consumed_by:` was stamped at Step 5 of the pickup skill).
2. The consumed handoff carries a `completeness_checklist:` frontmatter field (literal token — install/onboarding batons only; ordinary continuation handoffs are silent no-ops here).
3. At least one checklist item remains unverified (open Tasks-API task from the pickup step, or not explicitly waived by the EM).

**If any condition does not hold → skip silently. No warning, no ceremony tax.**

**If all three hold:**

1. **Locate the consumed handoff.** Resolve via `state/handoffs/` entries with `consumed_by:` matching this session id (same resolution used in Step 2.7). If already archived by Step 2.7, read from `archive/handoffs/`.

2. **Read the `completeness_checklist:` field.** It is a `list-of-string` (YAML sequence); each item obeys the grammar `<class>: <assertion text> [probe: <shell-command>]` where `<class>` ∈ `{live, restart-gated}`.

3. **Cross-reference with open Tasks-API todos** from the pickup step (those created by `/pickup` under the `completeness_checklist` instantiation). Open tasks are per-conversation reminders; this step is the actual close-out check.

4. **Count unverified items.** An item is considered verified if:
   - Its corresponding Tasks-API task is marked done, OR
   - The EM has explicitly waived it with a one-line rationale (inline during the session).

   **Cross-conversation note:** In a cross-conversation session (pickup Tasks not visible — e.g. session was resumed after compaction or in a new conversation), every uncompleted checklist item is treated as **unverified** unless a durable waiver exists in the handoff body or a commit message. Tasks-API state is per-conversation; it does not survive cross-conversation pickup. Do not assume an item is verified because no open Task is visible — absence of a Task record is NOT proof of completion.
   <!-- Review: code-reviewer — F7: added cross-conversation clause for cases where Tasks are not visible -->


5. **Emit the WARN** (to the session output, NOT as a hard-fail or process exit):

   ```
   WARN [completeness-checklist]: N completeness item(s) unverified on consumed baton <handoff-basename>.
   Validate or explicitly waive each before this counts as shipped.

   Unverified items:
     - <class>: <assertion text>
     ...

   Reference: docs/wiki/install-surface-completeness.md § Running-in-Claude-Code
   To waive: note each item explicitly ("waiving: <item> — <rationale>") and re-run /workstream-complete,
   or mark the corresponding Tasks-API task done after verifying.
   ```

**This step is ADVISORY per § Post-Consumer Gates Must Be Advisory WARN, Not Hard-Fail (`docs/wiki/install-surface-completeness.md`).** It does NOT block the commit, does NOT hard-fail workstream-complete, and does NOT gate Step 3. The WARN is the "refuses silent done" surface — an honest signal that the checklist was not fully cleared. The EM may proceed past it with an explicit waiver or acknowledgement. Silent-proceed without the WARN being emitted is the failure mode this step prevents.

**Execution shape:** this step is a peer slot in the todo-list cluster (parallel-safe with Steps 2.6, 2.7, 2.8, 2.9, 2.9b, 2.95 — it reads the consumed handoff file and open Tasks; it does NOT write any files). Its output feeds the **Step 4 Final Summary** as a one-liner: `Completeness checklist: N items unverified — WARN emitted` or `Completeness checklist: all verified / not applicable`.

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

1. **Stage only paths this session touched — never `git add -A`.** Capture the explicit session path set ONCE into a shell array and reuse it for both `git add` and `git commit` — this ensures the same set drives both operations and a sibling EM's already-staged files on the shared index are never absorbed (2026-06-24: a workstream-complete commit absorbed 6 files a concurrent session had staged when `git commit -F` was invoked without a pathspec). Step 2.67 git-rm deletions MUST be listed in `WSC_PATHS` too, so the pathspec commit includes them.

   ```bash
   # Capture the explicit session path set ONCE — reuse for BOTH stage and commit so a
   # sibling EM's already-staged files on the shared index are never absorbed (2026-06-24:
   # a workstream-complete commit absorbed 6 files a concurrent session had staged).
   # Step 2.67 git-rm deletions MUST be listed here too, so the pathspec commit includes them.
   WSC_PATHS=( state/lessons.md "docs/plans/<feature>.md" "archive/completed/YYYY-MM/<entry>.md" )  # explicit, this session only
   git add -- "${WSC_PATHS[@]}"
   ```

   Typical set: `state/lessons.md`, `docs/plans/<feature>.md` (if Step 2.4 ran), `archive/completed/YYYY-MM/<entry>.md`, `docs/project-tracker.md`, action-items, `docs/README.md`, `state/handoff-tracker.md` (if Step 2.75 ran), **`git rm` of any Step 2.67 deletions** (each `git rm` both removes the file and stages the deletion atomically — no separate `git add` needed; still list the path in `WSC_PATHS` so the commit pathspec covers it). Unfamiliar dirty files → Step 3.0 gate first; "leave alone" is only correct for case (b) named-owner files.

<!-- mandatory-commit-shape -->
**Mandatory commit shape (concurrent-EM safe).** Plain explicit-path git is the default per SC-DR-008; the helper is reserved for sweep ceremonies + the executor's branch-pin path. Use ONE of:

```bash
# Default — explicit-path commit (SC-DR-008 baseline):
git add -- <paths> && git commit -m "<subject>" -- <paths>

# OR, for handoff-scoped sessions, the helper (defaults to em-only as of 2026-06-15):
coordinator-safe-commit --scope-from <handoff> "<subject>"
```

Plain-git is listed first deliberately — the helper is the carve-out, not the primary path. **Never `git add -A` / `git add .` / `git add --all`** — the `block-blanket-git-add.sh` PreToolUse hook enforces this; see `docs/wiki/coordinator-tripwires.md § BLOCK-BLANKET-GIT-ADD` and `docs/wiki/scoped-safety-commits.md § SC-DR-014`.

   For any Step 2.67 deletions or justify-keeps, format the commit body with `Deleted (Step 2.67):` and `Kept (Step 2.67):` blocks (one path per line, em-dash separator on Kept entries, `--- end Step 2.67 blocks ---` footer — see Step 2.67 step 3) so `git log -- <path>` recovery works mechanically.

1.5. **Validate Step 2.67 commit-body blocks against staged reality, then commit FROM the validated file.** Compose the commit message body with `Deleted (Step 2.67):` and `Kept (Step 2.67):` blocks per the format pinned in Step 2.67 step 3. Write it to a PID-scoped scratch file under `.git/`:

   ```bash
   msg_file=$(mktemp "$(git rev-parse --git-dir)/COMMIT_EDITMSG.workstream-complete.XXXXXX")
   cat > "$msg_file" <<'EOF'
   <workstream subject — e.g. "workstream-complete: <feature-name>" or "feat(<surface>): <summary>">

   <prose body summarizing what shipped>

   Deleted (Step 2.67):
   <one path per line; omit the entire block if nothing deleted>

   Kept (Step 2.67):
   <path> — <one-line reason; omit the entire block if nothing kept>
   --- end Step 2.67 blocks ---
   EOF

   bash ~/.claude/plugins/coordinator/bin/check-workstream-complete-deletion-blocks.sh "$msg_file"
   ```

   - **Exit 0** → proceed to step 2.
   - **Exit 1** → claim mismatch; the gate names the offending paths. Fix the commit body OR re-stage, then re-run. Do NOT proceed to commit.
   - **Exit 2/3** → script invocation/environment error; check usage and that you're in a git repo.

   If the session had no Step 2.67 deletions or keeps to record (e.g. a doc-only session), the structured blocks may be omitted — the gate then has nothing to validate and is effectively a no-op. The PID-scoped file is still the canonical artifact passed to `git commit -F`.

1.6. **Pre-commit scope-verify.** Run `git diff --cached --name-only` and confirm the staged set matches `WSC_PATHS`. If OTHER files appear, that signals a concurrent sibling session staged something before this commit — note the observation but do not abort. The explicit `-- "${WSC_PATHS[@]}"` pathspec in step 2 will keep those sibling-staged files out of this commit automatically.

2. **Commit FROM the validated file with an explicit pathspec** — `git commit -F "$msg_file" -- "${WSC_PATHS[@]}"`. A bare `git commit -F` with no pathspec commits the whole index, absorbing any sibling session's staged files on the shared branch — the explicit `-- "${WSC_PATHS[@]}"` is what prevents that. **`git commit -m "..."` is also forbidden for this commit** (it would let a divergent message land that the gate never saw). After the commit lands, `rm -f "$msg_file"`. The post-commit hook will auto-push on work/feature branches.
3. If nothing to commit, check for unpushed commits: `git log "origin/$(~/.claude/plugins/coordinator/bin/coordinator-current-branch)..HEAD" 2>/dev/null`
4. **Verify remote is synced:** confirm no unpushed commits remain. If auto-push failed, push explicitly and warn the PM.
5. If on main (shouldn't happen, but safety): push explicitly — `git push origin main`
6. If push fails (auth, network, conflicts), **warn the PM explicitly** — this is a critical failure

### Step 3.5: Archive Session Claim

Archive this session's claim directory — required at both `/workstream-complete` and `/handoff` to avoid forcing the next concurrent EM into a 24h wait.

Run:
```bash
sid="${CLAUDE_CODE_SESSION_ID:-$(cat "$(git rev-parse --show-toplevel)/.git/coordinator-sessions/.current-session-id" 2>/dev/null)}" && \
  source "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_HOME:-${HOME}}/.claude/plugins/coordinator-claude/coordinator}/lib/coordinator-session.sh" 2>/dev/null && \
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
- **Non-zero exit (any gate-bound row red or unresolved):** Hard-block. Print: _"Workstream-complete blocked: acceptance oracle has red/unresolved gate-bound tests."_ + the script verdict. Remediation: fix tests and re-run, OR add a `cited:` row in the plan's Acceptance Criteria table with `Status → shipped-differently` and a rationale, OR set `COORDINATOR_OVERRIDE_ACCEPTANCE_GATE=1` (exceptional — `cited:` rows are the routine accommodation). Stop. Downstream `/merge-to-main` trusts this seam.

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

**Classify flags by severity before listing.** A break-class defect (broken / would-break / fails / leaks / silently-bypasses) is **fix-by-default** — fix it (or dispatch / propose a plan) and report the *fix*, not a passive `Flag to PM:` choice. Only direction-class items (product / prioritization / genuine tradeoff) belong under Flag-to-PM. → global `CLAUDE.md § Flag Severity`; `docs/wiki/flag-severity-triage.md`.

**Flag to PM:** Explicitly note the push so they can verify nothing breaks for other consumers.

If `$ARGUMENTS` is provided, use it as context for what was accomplished this session.
