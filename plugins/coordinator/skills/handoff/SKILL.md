---
name: handoff
description: "Involuntary mid-workstream save-state under context pressure. By definition a continuation, never a workstream ending — see Step 0."
allowed-tools: ["Read", "Write", "Bash", "Grep", "Glob"]
argument-hint: "[optional context]"
---

# Session Handoff — Save State for Next Session

Capture the current session state so future sessions (or other agents) can pick up seamlessly.

> **Handoff is involuntary by definition.** The only legitimate trigger is context pressure that forces the current session to stop mid-workstream before its next action can land. A handoff is a continuation-point, not a workstream-ending ceremony — if you find yourself reaching for `/handoff` because the work feels like a good place to pause, that framing IS the disqualifier. Workstreams end via `/workday-complete`, `/merge-to-main`, or commit-and-stop; never via handoff. The EM does not voluntarily invoke this skill at perceived stopping points.

> **Continuation vs. fork.** This skill writes a *continuation* handoff — work the current session was doing that someone (often you, next session) will resume. To carve off a *different* mid-session topic for someone else to pick up cold, use `/spinoff` instead — that produces `kind: spinoff`, `predecessor: none` handoffs, designed for fork rather than continuation.
>
> **Recovery flavor.** If you are writing this handoff to resume from a crash, kill, or other unclean termination of a prior session — not a clean stopping point — set `kind: recovery` in frontmatter. Point `predecessor:` at the crashed handoff or its last commit SHA when known; null is permitted when no recoverable predecessor exists. Recovery handoffs follow the standard continuation lifecycle (deployment_state, /pickup flow, archival); the tag exists so `/workday-start` surfaces them with a `(recovery)` marker and so the audit trail distinguishes crash-driven continuations from deliberate ones.
>
> **Recovery-flavor crash-rescue sweep (required when `kind: recovery`).** Before exiting the recovery handoff write, sweep ALL files in `state/handoffs/` for gate/state that the crash may have invalidated. The crash that motivated this recovery handoff likely also broke premises in concurrent or downstream handoffs: an `awaiting_gate: <X>` where X was the crashed work; an `in_flight` handoff whose source branch the crash left in an unknown state; a `ready_to_fire` next-step that assumed the crashed work had landed. For each affected sibling: edit the body inline with a one-line crash-invalidation note (`**Crash-invalidated <YYYY-MM-DD>:** <one-line>`) and flip `deployment_state` if needed (most commonly `ready_to_fire` → `awaiting_gate` with `gate_dependency: recovery from <this-handoff-slug>`). Authoring only the new rescue handoff while leaving stale siblings as live work strands the next session on a false premise. Skip the sweep only if the crashed work is a leaf with no concurrent or downstream handoffs — confirm by grep, not by recall. Specific grep targets: search `state/handoffs/*.md` and `docs/plans/*.md` for (a) the crashed handoff's filename slug, (b) the crashed session's branch name (`work/{machine}/{date}` shape), (c) the crashed workstream name from its frontmatter `workstream:` field, and (d) any `gate_dependency:` value naming the crashed work. Zero hits across all four = leaf, sweep may be skipped. Any hit = read that file before declaring the rescue handoff complete.

## Instructions

When invoked, create a handoff document in `state/handoffs/` (git-tracked). Each session writes its own file (unique timestamp), so multiple concurrent sessions never overwrite each other.

**Path convention:**
- **Active handoffs:** `state/handoffs/*.md` — current, available for `/workstream-start` pickup
- **Archived handoffs:** `archive/handoffs/*.md` — consumed, kept as paper trail
- Both are git-tracked. `tasks/` and `archive/` must NOT be in `.gitignore` — they contain session continuity data that travels with the repo. `.claude/` contains only platform settings and does not need to be tracked.

**Design note:** Multiple agents may be running concurrently. This skill preserves ONE agent's work without assuming exclusive repo access.

**CRITICAL: Write the handoff file FIRST, before commits or anything else.** Handoffs are typically invoked when the session is near compaction. If you do git operations first, you risk losing the conversation context that makes the handoff valuable. Get the knowledge out of your head and onto disk immediately.

## Execution Shape — gates vs. todo-list

This skill has a small set of sequential gates and a TODO-LIST cluster. Treat them as such — do not ladder-walk the todo-list under context pressure. Convention: `docs/wiki/skill-step-parallelization.md`.

**Sequential gates (real data-dependency edges — must be in this order):**

1. **Step 0** (trigger check) — gate must pass to continue.
2. **Step 1** (write handoff) — produces the `scope:` block that Step 3 reads.
3. **Step 2.10** (code review consideration) — integrator-edited files must be staged in Step 3.
4. **Step 3** (commit + verify remote) — consumes Step 1's `scope:` and any Step 2.10 integrator edits.
5. **Step 3.5** (archive session claim) — consumes Step 3's pushed commit.
6. **Step 4** (confirm) — informational summary after 3.5.

**Todo-list (no edges between *peer* todo-list steps — execute in any order, batch parallel where two independently read/write different files):**

- **Step 2** — lessons (`state/lessons.md`)
- **Step 2.5** — doc-alignment insurance (chunk/stub `**Status:**` fields)
- **Step 2.6** — plan documentation (`docs/plans/`, `tasks/<feature>/todo.md`)
- **Step 2.7** — archive uncaptured work (`archive/completed/`)
- **Step 2.8** — build/test awareness (a note appended to the handoff body's Current State — reads Step 1's output)
- **Step 2.9** — refresh orientation documents (pinboard + tracker + action-items)

These six touch disjoint surfaces *relative to each other* and none consumes another's output. All six share Step 1's handoff file as a prerequisite (Step 2.8 explicitly so — it appends to the body), which is captured by the sequential gate ordering: Step 1 always runs before any todo-list item. Where two todo-list peers are disk operations on different paths, run them in the same response via parallel tool calls. Step 2.10 has a soft preference to land *with* the todo-list cluster so its integrator edits stage with Step 3, but does not consume the 2.x cluster's output.

**Doctrine-load-bearing exception:** Step 1's "CRITICAL: write the handoff file FIRST" remains absolute — the handoff body is the irreversible artifact under context pressure, and every other step (including the todo-list cluster) is recoverable from disk on a successor session if compaction strikes. Order: Step 1 first (absolute). Then the todo-list cluster and Step 2.10 in any interleaving — disjoint surfaces, parallel-safe. Then Step 3 (fan-in of both), Step 3.5, Step 4.

## Step 0: Trigger check — is context pressure actually forcing this?

Before writing anything, run this binary gate. The PRIMARY question is whether the current session can still take its next action; if it can, you are not handing off, you are deferring — and that's a doctrine violation regardless of how "tidy" the current state looks.

### Trigger gate — at least one must be true → continue

- Auto-compaction is imminent or in progress and would lose load-bearing context before the next action can land.
- A Claude Code restart or MCP-bridge restart is unavoidable mid-workstream.
- A hard blocker (PM input, external system, after-hours wait) is preventing the next action *right now* — not a future step.
- The PM has explicitly invoked `/handoff` and named the workstream. **Literal trigger only** — "you can hand that off," "let's pass this to the next session," or "another session will finish it" are intent-descriptions, not invocations. The authorizing act is the PM typing `/handoff` (or the skill name) for *this* workstream, OR one of the first three context-pressure conditions above firing involuntarily. Do not promote an intent-shaped remark into a voluntary handoff — that is precisely the deferral-disguised-as-handoff the NO-tests below exist to catch.

If none of these hold, STOP. Take the next action in this session instead. "Plan reviewed," "looks like a good pause point," "feels tidy here" are not triggers — they are the trap.

### NO-tests — any one of these → STOP, do not write a handoff (even under context pressure, redirect to the right artifact)

- The workstream's next action is `/merge-to-main`, or the terminal PR is already merged with no follow-up commits expected.
- The work is described in your head as "shipped," "complete on branch ready for merge," or "ready for the merge gate." That phrasing IS the disqualifier — write a commit message, not a handoff.
- All in-flight chunks of the active plan have landed and the plan doc is marked complete.
- **Plan is reviewed/approved but the executor hasn't been dispatched yet in this session.** A reviewed plan is scaffolding, not a deliverable — the next action belongs in *this* session (dispatch the executor), not in a successor's. Framing the session as winding down at plan-approval inverts the doctrine: plans exist to produce executed code. If acceptance criteria are still empirically unverified and no executor has run, STOP — dispatch, don't hand off. Handoff is legitimate only after the executor has run and there is genuine in-progress executor/integrator/test work for a successor to resume.
- **You are also planning to invoke `/workstream-complete` for this same workstream.** `/handoff` and `/workstream-complete` are mutually exclusive — never combined. `/workstream-complete` caps a workstream that is *done*; `/handoff` passes an *in-flight* workstream to a successor. The same workstream cannot be both. If the work is finished, STOP and run `/workstream-complete` alone. If it is in-flight, run `/handoff` alone — `/workstream-complete` will not also run on this workstream. If you genuinely have two workstreams (one finished, one in-flight), end the finished one with `/workstream-complete` *separately*, naming it explicitly, then write the in-flight handoff here for the other one — never bundle the two surfaces in one closing motion.
- **The handoff frontmatter you would write has `deployment_state: shipped` AND `pickup_ready: false` (or any equivalent shipped+not-pickupable combination).** That combination is a contradiction in terms — shipped work has no successor to pick it up. It signals the EM reached for `/handoff` as a generic session-summary template when the right surface is `/workstream-complete` (review trail + queue triage + archival sweep) or `/workday-complete` (daily ceremony). The handoff pipeline (`/workday-start`, `/workday-complete`, session-init orphan sweep, primary-list filters) treats every file in `state/handoffs/` as in-flight work — a shipped handoff shows up where it does not belong and pollutes triage in concurrent sessions. STOP — write the artifact for finished work, not a handoff for it.

### YES-tests — only consulted if all NO-tests fail

- In-progress edits not yet at a stopping point, AND a successor session must resume them.
- A plan in flight with remaining unexecuted chunks (not chunks that just landed in this session).
- Open blockers requiring PM input that arrived after-hours.
- A Claude Code restart imminent AND work in flight that the post-restart session must resume.
- PR open with reviewer feedback expected or unaddressed (iteration round counts as in-progress).

### If a NO-test trips → STOP

The right artifact is one of:
- `/workday-complete` — end-of-day ceremony; Step 4 daily summary lands in `archive/daily-summaries/`, indexed by Step 9 in `state/week-changelog/`
- Commit-and-stop — for mid-day completion of a workstream that's already merged or PR-ready
- `/workstream-complete` — if lessons need capture but no successor brief is needed

### If at least one YES-test fires AND no NO-test trips → continue to Step 1

*Handoffs are mid-stream baton-passes, not end-of-session ceremony. Shipped ≠ handed-off.*

---

### Inverted antipattern — "I'll just append to the predecessor I picked up"

> Parenthetical to Step 0 — applies whenever the EM has picked up a handoff this session and is now deciding whether to write a successor. Read it as a standalone callout, not a sub-decision of the YES-path.

The most common failure mode of this skill is **skipping it**: the picked-up predecessor (now `status: consumed`, `consumed_by: <this-session>`) is sitting right there, so the EM appends a `### <date> session — pickup, <progress>` block to its Progress / What Was Accomplished section and stops. **This is a doctrine violation, not a shortcut.** A consumed handoff is paper trail; the pickup index (`/workday-start`, `/pickup`, session-init orphan sweep) treats consumed handoffs as historical and will NOT surface them as live work — any progress stapled into the body is invisible to the next opener. The carry-forward / cascade machinery, the YES-test/NO-test gate, the chain-archival, the new frontmatter (`status: active`, `deployment_state: ready_to_fire`, `predecessor: <this consumed file>`) — all of that exists precisely because a successor file is the only surface the index can find. If you are about to edit a `status: consumed` handoff body to record what you just did, **STOP and run this skill from Step 1** — the YES/NO gate above still applies (a session that doesn't pass it stops via commit / `/workday-complete` / `/workstream-complete`, not via predecessor-append). Enforced at the tool layer by `hooks/scripts/block-consumed-handoff-edit.sh`; tripwire `CONSUMED-HANDOFF-FROZEN` in `docs/wiki/coordinator-tripwires.md`. Override `COORDINATOR_OVERRIDE_CONSUMED_HANDOFF_EDIT=1` is reserved for recovery-flavor crash-invalidation notes into sibling consumed handoffs (see this skill's recovery-flavor preamble) and one-off paper-trail corrections — never progress appends.

### Workflow

#### Step 1: Write the Handoff (IMMEDIATELY)

**Do this first. Do not run git commands, read files, or do anything else before writing the handoff.** You already have everything you need in your conversation context.

Generate a filename: `state/handoffs/{YYYY-MM-DD}_{HHMMSS}_{session-id}.md` where:
- `{YYYY-MM-DD}` is the current date
- `{HHMMSS}` is the current time in 24-hour format (e.g., 143052 for 2:30:52 PM)
- `{session-id}` is a short identifier (first 8 chars of session UUID if known, otherwise `manual`)

**Primary source: your conversation context.** You know what you worked on, what files you modified, what decisions were made. Use that — don't rely on git log to reconstruct your session.

Write the file with this structure:

```markdown
---
title: "<one-line title>"           # REQUIRED. Concise workstream name.
created: <YYYY-MM-DD>               # REQUIRED. Date this handoff was authored.
branch: <branch-name>               # REQUIRED. Active branch (git symbolic-ref HEAD).
status: active                      # REQUIRED. Enum: active | consumed | superseded.
predecessor: <filename-or-null>     # REQUIRED. Predecessor handoff filename, or null.
                                    # null = no predecessor (fresh workstream).
category: <roadmap|infra|bug|docs|research|refactor>
                                    # category ∈ {roadmap|infra|bug|docs|research|refactor};
                                    # summary ≤120 chars, one-line tl;dr
summary: "<one-line tl;dr>"        # ≤120 chars. Required on handoffs created ≥ 2026-05-29.
workstream: <workstream-slug>      # short slug, e.g., scoped-safety-commits
scope:                              # git pathspec syntax — files this workstream owns
  - path/to/file.md
  - dir/with/files/**
deployment_state: ready_to_fire     # REQUIRED. Default to ready_to_fire when:
                                    #   - Recommended next steps are concrete AND
                                    #   - No PM-gate is named in ## Blockers or Issues.
                                    # Use awaiting_gate when the work cannot proceed
                                    # without an external condition clearing — pair
                                    # with gate_dependency. Use in_flight when this
                                    # handoff is a status report for work the next
                                    # session resumes immediately.
gate_dependency: <one-line>         # REQUIRED iff deployment_state=awaiting_gate.
                                    # Subsystem-named, not file-pathed. Same durability
                                    # rule as Recommended Next Steps prose: name the
                                    # condition or subsystem, not the source paths.
pickup_ready: true                  # DEFAULT ON for all handoffs authored by this skill.
                                    # Positive signal: this handoff is explicitly
                                    # authorized for pickup. Absence triggers a
                                    # non-blocking warning at /pickup time (not a
                                    # block). Do NOT remove — stays as authorial-intent
                                    # record on consumed handoffs.
reviewed_at_workstream_complete: <sha-range> <reviewer> <YYYY-MM-DD>
                                    # OPTIONAL. Written by /workstream-complete (Step 2.8) or
                                    # /handoff (Step 2.X) after running coordinator:review-code
                                    # on this session's diff. Format: "<sha-range> <reviewer>
                                    # <YYYY-MM-DD>" — e.g. "abc123..def456 code-reviewer 2026-05-18".
                                    # reviewer is one of: code-reviewer | patrik | code-reviewer+patrik | waived.
                                    # Omit on spinoffs (kind: spinoff / spinoff-roadmap) — the
                                    # field applies to continuation handoffs only.
---

# Session Handoff — [DATE]

## What Was Accomplished

_Continuing from [previous handoff filename]: [what the prior session had completed and where it left off]. This session picked up at [entry point]._

- [Bullet list of completed work with file paths]

## Current State
- **Build status:** [compiles / unknown / broken + error]
- **Tests:** [all passing / N failing / not run]
- **Branch:** [branch name] — workstream-start uses this to find resumable branches
- **Remote synced:** [yes/no — check `git log origin/{branch}..HEAD`]
- **Uncommitted changes:** [yes/no — what]

## In-Progress Work
<!-- Durability: describe what is happening, not how to continue it. Path references here are OK — you're describing state, not prescribing steps. -->
- [What was being worked on when the session ended]
- [Current step in the plan, if following a plan doc]
- [Plan doc path if applicable]

## Key Decisions Made

> Capture 2-5 decisions per session where the *reasoning* would save future context reconstruction. Not every decision — only those where knowing "why" matters more than knowing "what".

### Decision: [Short title]
- **Observed:** [What prompted this — the situation or constraint you saw]
- **Considered:** [Alternatives weighed — include rejected approaches briefly]
- **Chose:** [What was decided and the core reasoning]

[Repeat for each key decision]

## Blockers or Issues
- [Anything that's stuck or needs human intervention]

## Recommended Next Steps
<!-- Durability: name subsystems and concepts, not file paths or line numbers. Each step = behavioral outcome (what to accomplish), not procedure (how to do it). Include an "Out of scope" line to prevent gold-plating. -->
1. [First thing the next session should do — behavioral outcome, verifiable]
2. [Second thing]
3. [Third thing]

**Out of scope for next session:** [explicitly name what the next session should NOT do or expand into]

## Carried Forward
<!-- Items from the predecessor handoff that this session did NOT resolve. These cascade
     down the chain until completed or explicitly dismissed by the PM. If none, omit this section. -->
- [ ] [Unresolved item from predecessor] _(carried from [predecessor filename])_
- [ ] [Another unresolved item] _(carried from [predecessor filename])_

## Files Modified This Session
- [file path] — [one-line description of change]

## Session Ledger

| Field | Value |
|-------|-------|
| agent_dispatches | <!-- from coordinator-session-loe.sh --> |
| opus_dispatches | <!-- from coordinator-session-loe.sh --> |
| em_tokens | <!-- from coordinator-session-loe.sh --> |
| tshirt | <!-- from coordinator-session-loe.sh --> |
| commits | <!-- git log --oneline since session start --> |
| session_id | <!-- $CLAUDE_CODE_SESSION_ID, sentinel fallback --> |
| created | <!-- ISO-8601 timestamp at handoff-write time --> |
```

**Populate the Session Ledger immediately after writing the handoff body** (still in Step 1, before Step 2). This is the per-session contribution slice that the chain-terminal aggregator (Chunk 5) will sum across the predecessor chain.

**Invocation:** `coordinator-session-loe.sh` does not emit a `--format markdown` mode. Use `--format json` and render the table fields manually:

```bash
# Resolve session ID — platform env var (per-session, unclobberable) first;
# sentinel (last-writer-wins) only as fallback for old Claude Code.
SID="${CLAUDE_CODE_SESSION_ID:-$(cat "$(git rev-parse --show-toplevel)/.git/coordinator-sessions/.current-session-id" 2>/dev/null || echo "unknown")}"

# Get LoE metrics
LOE=$(bash ~/.claude/plugins/coordinator/bin/coordinator-session-loe.sh \
      --session-id "$SID" --format json 2>/dev/null || echo '{"agent_dispatches":0,"opus_dispatches":0,"em_tokens":null,"tshirt":"XS"}')

# Extract fields (requires jq or inline bash parsing)
AD=$(echo "$LOE" | grep -o '"agent_dispatches": *[0-9]*' | grep -o '[0-9]*$')
OD=$(echo "$LOE" | grep -o '"opus_dispatches": *[0-9]*' | grep -o '[0-9]*$')
TOK=$(echo "$LOE" | grep -o '"em_tokens": *[^,}]*' | sed 's/.*: *//')
TS=$(echo "$LOE" | grep -o '"tshirt": *"[^"]*"' | grep -o '"[^"]*"$' | tr -d '"')

# Commits since session start (best-effort: last 20, space-separated short SHAs)
COMMITS=$(git log --oneline -20 --format="%h" 2>/dev/null | tr '\n' ' ' | sed 's/ $//')

# Timestamp
CREATED=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
```

Then replace the placeholder comment cells in the `## Session Ledger` block with the resolved values before writing the file to disk.

**Multi-ledger rule (re-pickup / recovery flavor):** If the handoff being written already contains a `## Session Ledger` block — because this is a recovery flavor or re-pickup of an existing handoff doc — DO NOT overwrite that block. Instead, append a second `## Session Ledger` block below the existing one. Multiple ledger blocks in one handoff file = multiple sessions touched the same workstream. The chain-aggregator (Chunk 5) and `bin/query-completions --type handoff-ledger` (Chunk 6) parse ALL `## Session Ledger` blocks in a file as separate synthetic records, using `session_id` as the deduplicator.

> **Design note — body, not frontmatter.** Session Ledger lives in the body, not in the YAML frontmatter. The frontmatter schema (`schemas/handoff.yaml`) already carries `reviewed_at_workstream_complete`; adding LoE there would bloat the schema and complicate `bin/query-records` frontmatter parsing. Body placement keeps the data accessible to the Chunk 6 query extension without schema changes.
>
> **Spec backlink:** `docs/plans/2026-05-19-completion-log-phase2-loe-and-handoff-ledger.md` § Chunk 4 (plan lines 162–188).

### Durability Rules for Next-Steps and In-Progress Sections

These four rules apply specifically to `## Recommended Next Steps` and `## In-Progress Work`. They do **not** apply to `## Current State` or `## Files Modified This Session` — those sections legitimately carry procedural detail and file paths because they are *describing what is*, not *prescribing what to do*.

1. **No file paths or line numbers in next-steps prose.** They go stale within hours — a renamed file or merged diff makes the step wrong before the next session even opens it. Reference subsystems, components, and concepts instead. _Exception:_ when the path IS the artifact (e.g., "the plan at `docs/plans/X.md`"), that's an identifier, not a procedural step — fine to include.

2. **Behavioral, not procedural.** Describe *what* the next session needs to accomplish, not *how* to accomplish it. The "how" goes stale; the "what" is durable. Bad: "run `npm test` and fix the three failures in `src/auth/token.ts:142`." Good: "get the auth token tests green — they are failing against the new expiry contract."

3. **Each next step is independently verifiable.** The picker should be able to confirm "done" without reading this handoff again. If a step can't be verified on its own, break it down or add an acceptance signal.

4. **Explicit out-of-scope line.** Every `## Recommended Next Steps` section should end with an "Out of scope for next session" line naming what the next session should NOT expand into. This prevents a fresh-eyed picker from gold-plating or drifting.

**Anti-amnesia chain:** The `_Continuing from..._` preamble in `## What Was Accomplished` creates a chain — any single handoff is a self-contained orientation point, not just an incremental update. **The predecessor is whatever handoff this session was opened with — period.** Identify it from a positive opening signal:

1. **Session was started with `/pickup <handoff>`** — the file passed to `/pickup` is the predecessor. This is the canonical signal. If `/pickup` was used, you already know the answer.
2. **The PM explicitly named a handoff at session start** — e.g., "continue from yesterday's auth handoff." (Combining two predecessors into one handoff requires explicit PM direction at session start — the EM does not collapse the chain on its own.)
3. **Neither?** Then this handoff has **no predecessor**. Omit the `Continuing from` preamble entirely and write a standalone handoff.

**"Most recent file in `state/handoffs/`" is a facile signal — do not use it.** Concurrent sessions across machines routinely produce adjacent handoffs that have nothing to do with each other. Adjacency is not ancestry. Picking the most recent timestamp corrupts the audit trail and incorrectly archives active work belonging to other workstreams. If you didn't open this session with a specific handoff, you have no predecessor.

**Cascading unresolved items (only when there IS a predecessor):** When this session genuinely continues a predecessor, check its `## Recommended Next Steps` and `## Carried Forward` sections for items this session did NOT complete. Any unresolved items **must** be carried forward into the new handoff's `## Carried Forward` section — they don't disappear just because a session ended. Each carried item retains its origin annotation (e.g., `_(carried from 2026-03-20_100000_abc123.md)_`) so the full lineage is visible. Items leave the cascade only when: (1) completed by a session (moved to `## What Was Accomplished`), or (2) explicitly dismissed by the PM. A session cannot silently drop a carried item.

**Chain archival (only the explicit predecessor):** Because the cascade ensures all unresolved obligations flow into the new handoff, the **explicit** predecessor can be safely archived after a continuation. Move *only* that predecessor to `archive/handoffs/` (create the directory if needed). Do not sweep other adjacent handoffs in `state/handoffs/` — they belong to other workstreams or other sessions and are not yours to archive.

> **Negative-spec — no consumed markers written here.** Moving the predecessor to `archive/handoffs/` is a file move, not a marker operation. The `<!-- consumed: YYYY-MM-DD -->` marker is `/pickup`'s exclusive responsibility (`coordinator/commands/pickup.md:130`). This step never writes that marker — to any file, in any circumstance.

**Park-with-links on supersession (superseded workstream, not a continuation).** When a workstream is *superseded* rather than continued — a newer plan, spinoff, or roadmap stub now owns the work the old handoff described, and the old handoff should NOT be picked up — do not leave it sitting `active`/`ready_to_fire` in `state/handoffs/`. A superseded handoff left in the active queue strands the next session on a dead workstream. Park it with three links, all in one commit:

1. **Relocate out of the active queue — relocation is the load-bearing guard.** `git mv state/handoffs/<superseded-file> archive/handoffs/<superseded-file>`. Set frontmatter `status: superseded` (a legal enum value per CLAUDE.md § Handoff Lineage and `schemas/handoff.yaml`) AND `deployment_state: abandoned` — superseded work is not `ready_to_fire` and was not its own ship, so `abandoned` keeps it out of every primary list (`/workday-start`, `bin/query-records`, the `session-init` orphan sweep) regardless of which `status` value a given reader honors. The relocation to `archive/handoffs/` is the load-bearing guarantee that the active-queue filters never see it; `status: superseded` is secondary metadata. Do this for the shipped-but-superseded case too — `deployment_state: abandoned` applies whenever the workstream's ownership moved elsewhere, shipped or not. **Do NOT set a `superseded_by:` frontmatter field** — the handoff schema (`schemas/handoff.yaml`) declares no such field and `bin/lib/schema.js CROSS_FIELD_RULES.handoff` enforces no `status: superseded requires superseded_by` rule (that rule exists only for `cross-repo-memo`). Provenance lives in the body links (step 2), which are schema-free and correct. If symmetry with `plan.yaml`/`decision.yaml` is wanted, a `superseded_by:` handoff field is a SEPARATE schema change (handoff.yaml optional block + a schema.js cross-field rule) and must not be smuggled in via this plan — it is an improvement-queue candidate.
2. **Bidirectional canonical link (schema-free body prose).** In the superseded handoff body, add a one-line `**Superseded by:** <successor-path-or-roadmap-stub-id>`. In the successor (handoff, plan, or stub body), add `**Supersedes:** <superseded-handoff-path>`. The pair makes the provenance trail navigable from either end. This body-prose link pair — NOT any frontmatter field — is the canonical supersession-provenance mechanism for handoffs.
3. **README / index provenance.** If the repo carries a handoff index or `docs/README.md` row referencing the superseded workstream, repoint it at the successor (per CLAUDE.md "Stale doc references: repoint when covered").

This is distinct from chain-archival (above): chain-archival moves the *explicit predecessor of a continuation*; park-with-links handles a *superseded* workstream that has no continuation in this session but whose ownership moved elsewhere. Supersession is a PM-or-roadmap event, not an EM unilateral call on adjacent handoffs — do not park another session's handoff as "superseded" without the explicit successor link (per CLAUDE.md "Don't archive other handoffs as 'superseded' unilaterally").

#### Step 1.5: Refresh Handoff Tracker

After chain-archival above, regenerate `state/handoff-tracker.md` so the durable tracker reflects the current queue state before the commit lands.

```bash
node ~/.claude/plugins/coordinator/bin/render-handoff-tracker.js
```

If the script is absent or exits non-zero, skip silently. The generated file is staged with the handoff's scoped commit at Step 3 — no separate commit.

#### Step 2: Capture Lessons

Follow `/workstream-complete` Step 1 (Capture Lessons) — same intake filter, same format requirements, same merge-over-add rules. Skip if compaction is imminent — the handoff file is the priority.

#### Step 2.5: Doc-Alignment Insurance

Follow `/workstream-complete` Step 2.5 (Doc-Alignment Insurance) — verify status fields match reality for any chunk/stub docs and execution trackers worked on this session. Lightweight pass only — read what's in conversation context, don't re-read every file.

#### Step 2.6: Update Plan Documentation

Follow `/workstream-complete` Step 2 (Update Plan Documentation) — including the active search across all plan locations (`tasks/<feature>/`, `tasks/plans/`, `docs/plans/`, `~/.claude/plans/`). Mark completed items, update status fields, add completion notes. Don't skip this because you don't recall opening a plan — search for one. Skip only if no plan docs exist for this session's work area.

#### Step 2.7: Archive Uncaptured Work

Follow `/workstream-complete` Step 2.6 (Archive Uncaptured Work) — sweep session commits for completed work not yet in the project tracker or completion archive. Skip if the project hasn't adopted unified tracking (`archive/` and `docs/project-tracker.md` don't exist).

#### Step 2.8: Build/Test Awareness

If the project uses a compiled language with a running IDE or editor (e.g., Unreal Engine, Unity, Xcode):
- **Do NOT run builds or test suites during handoff** — they conflict with running editors and concurrent agents
- Instead, note in the handoff's "Current State" section whether changes need a rebuild, and what tests should be run next session

#### Step 2.9: Refresh Orientation Documents

Update the documents that future sessions read for orientation — closing the read-write loop with `/workstream-start` and `/workday-start`. **Skip if compaction is imminent** — the handoff file is the priority; orientation docs are best-effort.

1. **Orientation cache** (`state/orientation_cache.md`): **Do not author the cache body. Do not patch sections.** `/handoff` is a **mid-session writer** with a single, narrowly-scoped capability: pinboard append (one line, overwrite-or-omit). The cache schema (`pipelines/workday-start-internals.md` § 5.5) is owned by ceremony writers (`/workday-start`, `/update-docs`).

   **Pinboard rule:** if the picker-upper of this handoff MUST see a piece of context that won't be obvious from the handoff body or from a fresh ceremony regen (a transient surface gotcha; a known-trap environment caveat; an in-flight investigation that hasn't crystallised into the handoff body yet), write one line via:

   ```bash
   bash ~/.claude/plugins/coordinator/bin/regenerate-orientation-cache.sh \
       --invoker handoff \
       --pinboard "YYYY-MM-DD <writer-slug>: <one-line note>"
   ```

   Otherwise do nothing — the handoff body is where pickup-state lives, not the cache. The pinboard is cleared at the next ceremony regen. Skip if cache doesn't exist.

2. **Project tracker** (`docs/project-tracker.md`): If it exists and this session completed or progressed tracked items, update their status rows.

3. **Action items** (first match: `ACTION-ITEMS.md`, `docs/active/ACTION-ITEMS.md`, `docs/ACTION-ITEMS.md`): If one exists and this session resolved any listed items, check them off.

**Same guidance as `/workstream-complete` Step 2.7** — targeted patches to what this session touched, not regeneration. Concurrency-safe.

#### Step 2.10: Code Review Consideration

Follow `/workstream-complete` Step 2.9 (Code Review Consideration) — same diff-shape table, same precedence rule, same anti-ceremony-bias and symmetric anti-ceremony tripwires, same dispatch via `coordinator:review-code` Branch A.2, same trail-marker write via `coordinator-write-review-trail.sh`.

**Gate alignment:** This step fires ONLY when `/handoff` Step 0's YES-test gate has passed and the skill is actually writing a handoff. If Step 0's NO-test trips and the session is redirected to `/workstream-complete` or commit-and-stop, the review consideration belongs to that downstream surface, not here. Do not double-review.

**Additional handoff-specific behavior:** when this step writes a trail record, ALSO mirror the marker into the handoff frontmatter as:
```
reviewed_at_workstream_complete: <sha-range> <reviewer> <YYYY-MM-DD>
```
Use the same `<sha-range>`, `<reviewer>`, and date as the trail record (per the optional schema field added in `schemas/handoff.yaml`). Add this field to the frontmatter block written in Step 1.

**Edge case (PM-flagged):** when `/handoff` is written because the EM is bailing on a workstream they don't want to finish, the successor benefits from a `code-reviewer` pass on what landed. Treat the bailing case the same as any other non-trivial handoff — the diff-shape table determines the scale.

**Staging discipline:** any files edited by `coordinator:review-integrator` during this step must be staged via explicit path in Step 3, not absorbed by a post-integration `git add -A`.

#### Step 2.95: Pre-terminate dirty-tree gate

**Pre-terminate dirty-tree gate (fail loud on unattributable files).** Before the handoff commit, run `git status --porcelain` and classify every dirty (modified / untracked / partially-staged) path. **EOL phantoms are benign — never case (c):** a dirty file that is content-equal to the index (`git diff --quiet -- <path>` exits 0 — worktree vs. index, no HEAD; this is the membership test the sweep itself uses) is a Git-for-Windows EOL stat-staleness artifact (`docs/wiki/concurrent-em-hazards.md` § H23), not an orphaned edit — leave it untouched; it is swept automatically by `coordinator-renormalize-index` at every session open (`session-init.sh`), so no per-ceremony step is needed. Classify each remaining path:

- **(a) This session authored it** → it belongs in this terminator's scoped commit (handled by the existing scope/commit step).
- **(b) A known concurrent session owns it** → leave it alone (existing rule). "Known" means you can name the workstream/session — a sibling `scope:` block, an active handoff, or a session claim under `.git/coordinator-sessions/` accounts for it. The machine-checkable form of "a session claim accounts for it" is a handoff-frontmatter `consumed_by:` field naming another session's id (sourced from `.git/coordinator-sessions/.current-session-id` per `schemas/handoff.yaml`) — grep for that to tie the prose signal to a field an executor can actually check.
- **(c) Unattributable** — a dirty file you did NOT author AND cannot tie to a named concurrent owner (the classic case: an abandoned partial revert or orphaned edit from a crashed session). **Do NOT silently leave these — they wedge the next session opener.** Fail loud and pick exactly one disposition, in this order of preference:
  1. **Commit** with provenance if the change is coherent and you can attribute it: `git add -- <path> && git commit -m "chore: adopt orphaned WT change <path> — unattributed at handoff"`.
  2. **Stash-with-provenance** if it is incoherent or risky to commit: `git stash push -u -m "orphaned-WT <YYYY-MM-DD> handoff: <path> — left by unknown session" -- <path>`. Name the stash so the next session can find and adjudicate it (per CLAUDE.md "Probe edits in `git stash push -u` / `pop`").
  3. **Explicit "leave it owned by X"** only when you can now name the owner — record a one-line note (in the handoff body / session summary) stating which session/workstream owns it, converting it from case (c) to case (b).

The forbidden outcome is terminating with case-(c) files still dirty and unnamed. Orphan `.tmp.<pid>.<nanos>` files are a special case (Edit-tool atomic-write crash, per CLAUDE.md § Verifying Executor Output) — diff against target before deleting; do not stash them blind.

**Note — this dirty-tree gate is replicated across all three session terminators (workstream-complete, handoff, workday-complete) because the failure is identical across them.** Three surfaces, same gate, inline-not-snippet: the three blocks legitimately vary by `<terminating action>` / `<terminator>` token (workstream-complete commit vs. handoff commit vs. workday-complete merge/rebase). Snippet-sync is for byte-identical text that must not drift; near-identical-with-intentional-variation is the correct shape here. This is the instance-#3 ceremony moment the `ceremony-calibration.md` rule names — three terminator surfaces in one plan IS the threshold, and the conscious choice is inline-over-snippet because parameterizing the per-surface variation into a single snippet would make that variation invisible. Trigger for revisiting: a fourth terminator surface appears, OR the three blocks converge to byte-identical.

#### Step 3: Commit + Verify Remote

**Pre-flight: verify shipped claims.** For each commit referenced in this handoff's `## What Was Accomplished` as completed/shipped, run `check-shipped-on-main.sh <sha>`. If any commit is NOT on `origin/main`:

1. Append a `## Not Yet On Main` section to the handoff body listing each unmerged commit with `{sha} — {subject}`.
2. Replace any "shipped" / "landed" / "in production" wording in `## What Was Accomplished` with "complete on branch, not yet merged."
3. Do not block the handoff — write the truth and continue.

**Now** that the handoff is written, commit everything and verify remote sync.

**Workstream scope is declared in the handoff `scope:` block** (written above this step). With concurrent EMs active on the same branch, `git add -A` would sweep up another session's staged/modified files and silently re-attribute them — the `scope:` block is the workstream-anchored authority on which paths belong to this commit. If `git status` shows unfamiliar unstaged files you didn't touch, leave them alone — but first run the Step 2.95 dirty-tree gate; "leave alone" is correct ONLY for case (b) named-owner files.

1. Commit using explicit-path plain git — read the `scope:` block from the handoff frontmatter and stage only those paths (lessons.md:43, lessons.md:207, SC-DR-008; no fallback to staging-all):
   ```bash
   HANDOFF=<handoff-doc-path>
   # Extract scope paths from YAML frontmatter (  - <path> lines between scope: and next key)
   SCOPE=$(awk '/^scope:/{found=1; next} found && /^  - /{print substr($0, 5)} found && /^[a-z]/{exit}' "$HANDOFF")
   if [ -z "$SCOPE" ]; then
     echo "FAIL: handoff frontmatter scope: block missing or empty — cannot enumerate paths" >&2
     exit 1
   fi
   git add -- $SCOPE && git commit -m "handoff quick-save: <workstream>" -- $SCOPE
   ```
   where `<workstream>` is the slug from the handoff doc's `workstream:` frontmatter field (e.g., `handoff quick-save: scoped-safety-commits`). The `scope:` block lists git pathspec entries — keeping concurrent sessions isolated. The pathspec format follows standard git pathspec syntax (e.g., `path/to/file.md`, `dir/with/files/**`). **If `scope:` is missing or empty: FAIL and exit non-zero — no fallback.**
2. **Pushing:** The post-commit hook handles pushing to branch automatically.
   Do NOT manually push. Just commit — the hook does the rest.
   If on main (shouldn't happen, but safety): do NOT push. Commits on main
   stay local until merged via PR.
3. **Verify remote is synced:** confirm no unpushed commits remain (`git log "origin/$(~/.claude/plugins/coordinator/bin/coordinator-current-branch)..HEAD"`). If auto-push failed, push explicitly and warn the PM.

#### Step 3.5: Archive Session Claim

Now that the final commit has landed and pushed, archive this session's claim directory so concurrent sessions don't see stale claims accumulating until the 24h reaper fires. Session claims are consumed by the helper's `--blanket` sweep ceremonies (workstream-start, workday-complete, update-docs, relay-protocol, distillation) and the `--expected-branch` gate in `agents/executor.md` — those are the post-SC-DR-008 paths that still touch the claims directory. Without archival, dead-PID claims accumulate and force concurrent sweep ceremonies to either wait 24h, set `COORDINATOR_OVERRIDE_SCOPE=1` (which masks the gap), or manually `cs_archive` each defunct session by hand.

Run:
```bash
sid="${CLAUDE_CODE_SESSION_ID:-$(cat "$(git rev-parse --show-toplevel)/.git/coordinator-sessions/.current-session-id" 2>/dev/null)}" && \
  source ~/.claude/plugins/coordinator/lib/coordinator-session.sh 2>/dev/null && \
  cs_archive "$sid" 2>/dev/null || true
```

Idempotent — already-archived sessions return 0 silently. Failures are non-fatal (the 24h reaper is the safety net). Skip silently if the session id can't be resolved or the lib is unavailable.

**Note on session_id source:** Prefer the platform env var `$CLAUDE_CODE_SESSION_ID` (Claude Code ≥ ~2.1.150) — it is per-session and cannot be clobbered by a sibling session, so it is the session that actually owns this handoff. The `.current-session-id` sentinel is "last writer wins" across concurrent sessions and is only a fallback for older Claude Code. An ambiguous sentinel read (it flips between two ids across reads) means two sessions are live — do **not** act on it; use the env var.

#### Step 4: Confirm

Remind the user:
- "Handoff saved to `state/handoffs/`. Pick up with `/pickup` (relay-race resumption) or `/workstream-start` (general orientation)."
- "Run `/update-docs` if you want repo-wide documentation maintenance (directory sync, handoff archiving to `archive/handoffs/`)."

**Verify `.gitignore`:** Quickly check that `tasks/` is NOT gitignored. If it is, warn the user — handoffs in a gitignored directory will be invisible to other sessions and lost on clone.

### Notes

- **A Claude Code restart is a session boundary, not a step within a session.** If your workflow needs an MCP-bridge restart, a runtime artifact rebuild, or a `/reload-plugins` between code-edit and verification, run `/handoff` BEFORE the restart, not after. Splitting code+build from runtime-verify across two sessions is cleaner than trying to span the restart — context is lost in the gap, and the post-restart session that picks up has no context unless a handoff exists. Symptom that you should have handed off: you find yourself saying "let me just wait through this restart and then verify" — stop, hand off, the next session verifies.
- Each session writes a NEW file with a unique timestamp — never overwrite other sessions' handoffs
- Keep it concise — aim for under 50 lines. The next session will also have MEMORY.md and project context.
- Focus on state that MEMORY.md doesn't capture: in-progress work, blockers, uncommitted changes
- If the user provides arguments (e.g., `/handoff focus on auth refactor`), incorporate that context
- **Cross-repo communication is not a handoff use-case.** Telling another repo's EM something routes through the PM as relay (copy-paste in chat, or use `cross-repo-memo --to <receiver-em> --topic <slug>` for structured briefs). See `docs/wiki/cross-repo-communication.md`.
- **Cleanup:** During `/handoff`, archive the predecessor after carrying forward its unresolved items. General handoff archiving (48-hour sweep) is handled by `/update-docs` — no broader sweep here.
- **Active vs archived:** Active handoffs live in `state/handoffs/` (available for pickup). Archived handoffs live in `archive/handoffs/` (paper trail). Both are git-tracked.
- **User context:** If `$ARGUMENTS` is provided (e.g., `/handoff focus on auth refactor`), incorporate that context into the handoff's "In-Progress Work" and "Recommended Next Steps" sections.

### Crash-Rescue Checklist

When writing a recovery handoff after a crash or unclean termination:

**Sweep all live handoffs for gate/state invalidation.** Do not only author the new rescue handoff. For each existing handoff in `state/handoffs/` with `deployment_state` in `{ready_to_fire, in_flight, awaiting_gate}`, re-verify the gate predicate and stated substrate against current HEAD. Update frontmatter or add a comment block for any entry whose gate has cleared, whose substrate has changed, or whose stated in-progress state is now inconsistent with the branch.

**Enumerate dirty/untracked files AND `git reflog` across all sibling repos under the same machine.** Cross-repo concurrent crashes leave fragments in N repos; stopping at the most-recent handoff misses N-1 crash sites. For each sibling repo in `~/.claude/state/repo-registry.md` that shares `stack_tags` or was in-flight this session, run `git status` and `git reflog --since="2 hours ago"` to surface uncommitted fragments.
