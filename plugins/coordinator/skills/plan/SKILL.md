---
name: plan
description: Invoke on any planning trigger from the PM — "plan", "let's plan", "write a plan", "draft a plan", "break this down", "plan the implementation" — for decision-weight work (multi-file, abstraction, cross-system, agent scaffold, reversed prior). Triage lives inside the skill, not in EM pre-skill judgment; writing a plan to disk without invoking this skill is a doctrine violation.
version: 1.0.0
description-budget: 400
spec_backlink: docs/plans/2026-05-06-plan-super-skill.md
prerequisite:
  - agent:prior-art-checker
  - skill:coordinator:review
  - wiki:plugins/coordinator/docs/wiki/writing-plans.md
---

# coordinator:plan

<!-- Purpose: Decision-tree router for plan-writing workflows. Covers triage (should I plan?), substrate verification, body composition with the four PM doctrinal lenses, pre-dispatch handoff to coordinator:review, and mid-plan friction. Long-form doctrine lives in docs/wiki/writing-plans.md. -->

**Trigger:** EM is about to plan implementation work where the spec carries decision weight (multi-file, new abstraction, cross-system, scaffolds new agents/skills, reverses a prior decision) OR the PM has typed *"write a plan", "break this down", "plan the implementation"*.

**When NOT to use:** Trivial work (single-file fix, typo, link repoint, no abstraction) → just do it. Implementation-only ambiguity mid-coding → harness Plan tool inline. Architectural-tier (cross-system irreversible, multi-stakeholder) → surface to PM first. Spec vague or multi-subsystem → `coordinator:brainstorming` first. Skill-authoring (writing a SKILL.md) → `plugin-dev:skill-development`. Plan already written and needs review → `coordinator:review`. Stuck pattern → see `docs/wiki/stuck-detection.md`.

---

## Branch A — Triage: should I plan, and at what altitude?

_Condition: EM has just received a planning trigger; first decision is whether a plan doc is the right artifact._

- _Trivial?_ (single-file change, no new abstraction, scope obvious from the ask)
  → Just do it. No plan doc. _See CLAUDE.md § Plan-First Workflow._
- _Implementation-only ambiguity?_ (multi-line edit where the EM is choosing between two equally valid shapes mid-typing)
  → Use the harness Plan tool inline. No plan doc.
- _PM has set a session axiom?_ (PM said *"we are going to do X"* / *"the next thing is Y"* / *"build Z this session"* — an explicit directive that names the work, not a question about the work)
  → Disposition default flips to **plan**, not brainstorm. The brainstorm-vs-plan triage is bypassed: the PM has already chosen scope; the EM's job is to plan the named work, not to re-litigate whether to scope it differently. Continue to **Branch B**. The architectural-tier check (final bullet) still fires — a PM axiom does not override an architectural surface-to-PM. _See CLAUDE.md § Challenging the PM ¶ EM owns implementation discretion; PM owns product authority._
- _Non-trivial (default for everything else)?_ (multi-file, new abstraction, cross-system, scaffolds an agent/skill, reverses prior teardown, touches shared schema)
  → Continue to **Branch B**.
- _Architectural-tier?_ (cross-system irreversible, multi-stakeholder, security/privacy boundary, naming-collision-with-product-policy)
  → Surface to PM: *"this looks architectural — propose `/staff-session`, want me to draft the staff-session brief?"* Wait for PM. _See CLAUDE.md § Challenging the PM and § Plan-First Workflow._

---

## Branch B — Pre-write substrate verification

_Condition: a plan doc is the right artifact; substrate must be verified BEFORE the plan body is drafted._

- _Seven-dimension confidence checklist green?_ (no-duplicate / no-fabrication / architecture-compatible / official-docs-read / reference-impl-seen / root-cause-known / fix-locus discrimination)
  → All seven green → continue to Branch C. Any red → loop back to investigation Tier 1–3 or escalate to PM. _See CLAUDE.md § Pre-Dispatch Verification ¶ seven-dimension confidence checklist._
- _Fix-locus discrimination — is this the right layer to fix the bug?_
  → **Green:** planner has identified the upper-layer registry/dispatch/extension site by `file:line` (one level above each proposed edit site) AND can name a concrete reason patching the upper layer is wrong (registry already gates this case; upper layer is closed contract; upper layer is hot-path with unrelated callers).
  → **Red:** planner cannot articulate why the upper layer is the wrong locus, OR the upper layer is a registry/dispatch/extension site that already has the gate type the patch would re-implement at the call site.
  → **Action on red:** loop back to investigation Tier 1–3 on the upper-layer mechanism (Tier 2 / project-RAG preferred when indexed; Tier 3 grep works on unindexed repos). If an upper-layer gate exists, reframe the plan around extending it, not patching the call site. _See `docs/wiki/writing-plans.md` § Fix-locus discrimination and CLAUDE.md § Reviewer rationale must discriminate (the analogous review-time discipline)._
- _File paths / framework names / helper APIs / test harness / cited counts verified against disk?_
  → Run the disk check inline (`ls`, `grep -c`, `head_limit:0` for enumerations). Any drift → fix the plan substrate before drafting body. _See CLAUDE.md § Pre-Dispatch Verification ¶ verify file paths and ¶ paginated grep._
- _Plan reverses a prior teardown / re-introduces a removed pattern?_
  → Run the negative-search procedure (grep `tasks/lessons.md` and wiki for the central nouns + prohibition vocabulary). _See `docs/wiki/writing-plans.md` § Negative-Search Before Drafting._
- _Native-code (C++/UE/Rust/etc.) plan?_
  → Add 2–3 in-tree `file:line` citations to the dispatch brief. _See CLAUDE.md § Pre-Dispatch Verification ¶ native-code plans._
- _Plan renumbers or rekeys a published API (constants, error codes, route numbers, step indices)?_
  → Reverse-reference scan must grep ≥3 pattern shapes for each renumbered value: bare number, quoted string (`'N'` / `"N"`), fmt-string form (`{n}` / `%d`), and comment form (`# step N`, `// route N`). Bare-number grep misses string-form citations; string-form grep misses comment-form. Internal cross-references rot silently when only the canonical declaration site is found.
- _Plan adds a new dispatch / handler / op / job to a surface that already has registered entries?_
  → Check whether a table/registry pattern exists (e.g. `UE_REGISTER_*`, `register_action`, plugin-style auto-registration). If yes, the plan MUST use the registered surface; adding a parallel `else if` / `switch` / hand-rolled lookup is a recurring footgun that re-introduces dispatch-fragility bugs. Project-level wikis carry the concrete instances (see `docs/wiki/writing-plans.md` for project-specific examples).
- _Plan ports / mirrors / adapts a feature from a peer repo (cross-repo port, plugin addon, downstream re-implementation)?_
  → Before authoring a parallel addon surface that mirrors the peer's shape, check whether the host has its own registration seam / hookspec / extension point that the ported feature could attach to. Default to host-registration over parallel-surface — a parallel addon front-end duplicates routing, splits maintenance, and turns every host upgrade into a re-port. Grep the host's plugin/extension/hookspec/registry directory for an existing seam; if one exists, the plan MUST attach via that seam. Authoring a parallel surface requires a documented reason (host seam is closed, fundamentally wrong shape for the port, etc.). _See `docs/wiki/writing-plans.md` for the cross-repo port checklist._

---

## Branch C — Compose the plan body

_Condition: substrate verified; ready to draft body. The four PM doctrinal lenses bind here — this branch is where the wrong shape gets baked in._

**Lenses applied in rows 2–5 below:** time (agent-scoped only) / refactor>patch / PM-owned YAGNI / soon=now.

- _Scope mode declared?_ (prototype | production-patch | feature | architecture | spike)
  → Pick one before drafting tasks. Mode shapes review depth and the evidence bar. _See `docs/wiki/writing-plans.md` § Scope Mode._
- _Acceptance criteria testable + time framed for agents, not humans?_
  → Each AC is a binary pass/fail check. Time annotations OK when agent-scoped ("this dispatch runs ~90s"); reject human-sprint framing ("two-week effort", "Q3 milestone"). _See CLAUDE.md § Plan-First Workflow ¶ don't-import-human-effort-timelines (project-level) and § Operating Assumptions (global `~/.claude/CLAUDE.md`)._
- _Refactor-or-patch decision: which is correct here?_
  → Default to refactor when AI is the implementer and the patch is in a patch-accumulating area. If a reviewer would propose a refactor, propose it now. _See CLAUDE.md § Core Principles ('Do the right thing, not the easy thing')._
- _A "we'll add X later" / scope-trim / YAGNI argument is part of the draft?_
  → **Always surface to PM** — never EM-unilateral. YAGNI is a product call. _See CLAUDE.md § Challenging the PM ¶ ask the PM when._
- _A "soon = now" deferral candidate?_ (an item the draft would defer because the EM thinks it's lower priority than the headline work)
  → Either ship it in this plan or get explicit PM disposition. No silent deferrals. _See CLAUDE.md § Plan-First Workflow ¶ implement-and-iterate (project-level) and § Operating Assumptions (global `~/.claude/CLAUDE.md`)._
- _Each chunk has an identified test surface?_
  → For each chunk, name the test (or explicitly document why no test). _See `docs/wiki/test-design-discipline.md` and `docs/wiki/writing-plans.md` § Bite-Sized Task Granularity._
- _Plan will hand off to an executor agent?_ (sub-conditions are additive — apply baseline always, plus any modifiers that apply)
  - **Always — every executor-bound stub:** Apply the standard hard-constraints block (explicit file scope, no commits, no out-of-scope edits, no fallback escape hatches). _See `docs/wiki/writing-plans.md` § Hard Constraints (a) — Explicit file-scope, (e) — No fallback escape hatches._
  - _Additionally, plan uses parallel executors with file overlap risk?_ → Run file-overlap analysis listing each file each executor will touch. _See `docs/wiki/writing-plans.md` § Hard Constraints (g) — File-overlap analysis._
  - _Additionally, plan stub spawns sub-agents (orchestrator-shaped)?_ → Mark stub as read-only-planner; sub-task dispatch happens at EM level, not nested. _See `docs/wiki/writing-plans.md` § Hard Constraints (b) — Read-only orchestrators._
  - _Additionally, plan touches concurrency-shared state (shared file appends across N machines/sessions, shared index, shared lock)?_ → Prefer per-machine paths over atomic-merge logic. _See `docs/wiki/writing-plans.md` § Hard Constraints (f) — Concurrency-safe file design._
- _Plan mutates a shared symbol (state enum, gameplay tag, public field, exported function signature)?_
  → Add a reverse-reference scan subsection to the plan listing every consumer. _See `docs/wiki/writing-plans.md` § Shared-State Pre-Flight Gate._
- _Cross-plan conflict scan run? (mandatory before dispatch)_
  → Grep `docs/plans/*.md` for each chunk-scope file path AND for each new abstraction / registry entry / hookspec / schema field the plan introduces. Fold findings into a `## Cross-plan coordination` section: enumerate each sibling plan touched, what assumption it carries, and whether this plan amends / defers to / supersedes it. No conflicts → write the section anyway with `scanned — no overlapping file scope or seam citations`. Missing section is the failure mode this row exists to prevent. _See `docs/wiki/writing-plans.md` § (c) Cross-plan reconciliation — Cross-plan conflict scan procedure._
- _Plan amends an assumption that another live plan also depends on?_ (the current plan revises a path / contract / constant / sequencing decision that one or more sibling plans in `docs/plans/` reference — by `**Depends on:**` header, shared-symbol citation, or explicit cross-reference)
  → **Edit the body of every affected sibling plan in this same change** — do not let sibling plans silently drift. Procedure: (1) grep `docs/plans/` for references to the amended assumption (path, constant, contract name); (2) for each hit, open the sibling plan and edit the body inline so the assumption matches the new shape; (3) add a one-line amendment note at the top of each edited sibling: `**Amended <YYYY-MM-DD> by <this-plan-slug>:** <one-line change>`; (4) commit the amending plan and all edited siblings together. Silent drift is the failure mode this row exists to prevent — a sibling plan that still cites the old shape will be dispatched against stale substrate. _See `docs/wiki/writing-plans.md` § (c) Cross-plan reconciliation is a separate pass._
- _Plan scaffolds a new autonomous skill / agent / command?_
  → Apply the skill-scaffold checklist before drafting the body: (1) destructive-action prohibition block (see `docs/wiki/coordinator-tripwires.md` — Destructive-action prohibition in autonomous-dispatch prompts) for any write-capable autonomous skill; (2) explicit out-of-scope list; (3) spinoff-schema awareness if the skill can author handoffs (kind / predecessor / deployment_state fields per `docs/wiki/spinoff-handoffs.md`); (4) recheck-marker semantics if the skill has a cadence (recheck-due files per `coordinator:learn-lessons` mode `recheck`); (5) discovery-surface integration (where does this skill announce itself — `/session-start` mention, `/workday-start` surfacing, hook integration?). Empirical: bug-blitz the Staff Engineer R1 caught 5 majors on a skill scaffolded without this pass; the checklist exists because the failure mode is recurring. _See CLAUDE.md § Adding a Convention to the Coordinator System for the contact-point enumeration shape._
- _Plan contains a chunk that authors a handoff, spinoff, or session-end artifact?_
  → **Reject the chunk.** Handoffs (`/handoff`), spinoffs (`/spinoff`), and session-end captures (`/session-end`) are PM-gated session-continuity artifacts, not plan deliverables. A plan that pre-authorizes "Chunk N: write a spinoff to <topic>" launders the PM gate through plan approval — by execution time, the EM treats it as a checklist item and the spinoff's Step 0 gate never fires. Two failure shapes this row prevents: (a) the plan's terminal chunk is "author handoff" used as a wrap-up ceremony when commit-and-stop or `/workday-complete` is the right artifact; (b) the plan's terminal chunk is "author spinoff to <other-EM>" used as cross-repo messaging when the actual primitive is PM-as-relay (copy-paste in chat, or write to `archive/cross-repo/<topic>.md` and hand the PM the link). If the plan genuinely needs cross-EM coordination, the chunk is "surface cross-repo brief to PM" with the brief written inline or to `archive/cross-repo/`. _See `docs/wiki/cross-repo-communication.md`._
- _Plan brief contains code blocks (shell, Python, config) the executor will consume?_
  → Mark every fenced block either `TEMPLATE` (illustrative — executor adapts paths/values) or `VERBATIM` (executor copies as-is). Convention: place a fenced comment above the block, e.g. `<!-- TEMPLATE: adapt paths -->` or `<!-- VERBATIM -->`. Unmarked pseudocode-shaped bash gets faithfully transcribed into broken shell — the convention is the fix.

---

## Exit — Auto-Invoke `coordinator:review`

_Condition: plan body drafted, saved to `docs/plans/YYYY-MM-DD-<slug>.md`, ready for review._

→ **Invoke `coordinator:review` immediately. Do not ask the PM whether to proceed to review — plan→review is the pipeline, not a checkpoint.** If the plan was worth formally writing, it is worth formally reviewing; the gating on review-or-not happens inside `coordinator:review` Branch A (Branch A.2 carries the auto-skip terminals for genuinely-trivial / PM-waived). Pausing to ask "want me to invoke review now?" is a doctrine violation — the answer is always yes, and the auto-skip path lives downstream.

**The full plan-writing pipeline is:** (1) substrate verification (Branch B above), (2) body composition with the four PM doctrinal lenses (Branch C above), (3) `docs-checker` / `prior-art-checker` / **`plan-coverage-checker`** pre-flights via `coordinator:review`, (4) named reviewer, (5) review-integrator. Skipping `coordinator:plan` skips the pipeline; "I'll just write the plan and skip review" — and "let me ask first before invoking review" — are the two failure modes this skill exists to prevent.

<!-- Per docs/plans/2026-05-06-plan-super-skill.md F1 (PM lean b): coordinator:review Branch A.2 carries the auto-skip terminals. Renamed from "Branch D" to "Exit" per walk-through gap §2 — a one-row branch is shape-dishonest; this is a handoff, not a decision. -->

---

## Branch D — Executor BLOCKED on substrate drift

_Condition: a dispatched executor returns BLOCKED citing substrate that differs from what the plan asserted (path moved, helper renamed, framework changed, contract field absent, schema column missing)._

- _Default action: amend the plan or write a successor plan; do NOT silently expand executor scope to absorb the drift._
  → Substrate drift is plan-substrate failure, not executor failure. Re-invoke `coordinator:plan` to amend (small drift, same workstream) or compose a successor (larger drift or shape change). Re-run the prior-art-checker → the Staff Engineer → review-integrator chain on the amended body — the pipeline runs again from substrate verification, not from "we already reviewed the parent." Silently expanding the executor's scope to make the BLOCKED finding go away is a doctrine violation: it bypasses the doctrinal lenses, the prior-art check, and the reviewer pass that the original plan went through.
- _Product-risk findings during BLOCKED inspection?_
  → Even under `/autonomous`, surface product-risk findings via `AskUserQuestion` before amending. The autonomous mode suppresses handoff nudges, not product judgment. A BLOCKED that reveals (e.g.) a privacy implication, a permission default change, or an external contract shift is exactly the case the "Ask the PM" doctrine covers — autonomous mode does not waive it.

---

## Branch E — Mid-plan friction

_Condition: drafting is in progress and something is going sideways._

- _Repeating actions / oscillating between approaches / stalling?_
  → See `docs/wiki/stuck-detection.md` for the pattern catalog and recovery protocol.
- _Bug suspected mid-execution requiring root-cause investigation?_
  → See `docs/wiki/systematic-debugging.md` for the four-phase root-cause process.
