---
name: plan
description: Invoke on any planning trigger from the PM — "plan", "let's plan", "write a plan", "draft a plan", "break this down", "plan the implementation" — for decision-weight work (multi-file, abstraction, cross-system, agent scaffold, reversed prior). Triage lives inside the skill, not in EM pre-skill judgment; writing a plan to disk without invoking this skill is a doctrine violation.
version: 1.0.0
description-budget: 400
spec_backlink: docs/plans/2026-05-06-plan-super-skill.md
prerequisite:
  - agent:prior-art-checker
  - skill:coordinator:review
  - wiki:plugins/coordinator-claude/coordinator/docs/wiki/writing-plans.md
---

# coordinator:plan

<!-- Purpose: Decision-tree router for plan-writing workflows. Covers triage (should I plan?), substrate verification, body composition with the four PM doctrinal lenses, pre-dispatch handoff to coordinator:review, and mid-plan friction. Long-form doctrine lives in docs/wiki/writing-plans.md. -->

**Trigger:** EM is about to plan implementation work where the spec carries decision weight (multi-file, new abstraction, cross-system, scaffolds new agents/skills, reverses a prior decision) OR the PM has typed *"write a plan", "break this down", "plan the implementation"*.

**When NOT to use:** Trivial work (single-file fix, typo, link repoint, no abstraction) → just do it. Implementation-only ambiguity mid-coding → harness Plan tool inline. Architectural-tier (cross-system irreversible, multi-stakeholder) → surface to PM first. Spec vague or multi-subsystem → `coordinator:brainstorming` first. Skill-authoring (writing a SKILL.md) → `coordinator:writing-skills`. Plan already written and needs review → `coordinator:review`. Stuck pattern → see `docs/wiki/stuck-detection.md`.

---

## Branch A — Triage: should I plan, and at what altitude?

_Condition: EM has just received a planning trigger; first decision is whether a plan doc is the right artifact._

- _Trivial?_ (single-file change, no new abstraction, scope obvious from the ask)
  → Just do it. No plan doc. _See CLAUDE.md § Plan-First Workflow._
- _Implementation-only ambiguity?_ (multi-line edit where the EM is choosing between two equally valid shapes mid-typing)
  → Use the harness Plan tool inline. No plan doc.
- _Non-trivial (default for everything else)?_ (multi-file, new abstraction, cross-system, scaffolds an agent/skill, reverses prior teardown, touches shared schema)
  → Continue to **Branch B**.
- _Architectural-tier?_ (cross-system irreversible, multi-stakeholder, security/privacy boundary, naming-collision-with-product-policy)
  → Surface to PM: *"this looks architectural — propose `/staff-session`, want me to draft the staff-session brief?"* Wait for PM. _See CLAUDE.md § Challenging the PM and § Plan-First Workflow._

---

## Branch B — Pre-write substrate verification

_Condition: a plan doc is the right artifact; substrate must be verified BEFORE the plan body is drafted._

- _Five-dimension confidence checklist green?_ (no-duplicate / architecture-compatible / official-docs-read / reference-impl-seen / root-cause-known)
  → All five green → continue to Branch C. Any red → loop back to investigation Tier 1–3 or escalate to PM. _See CLAUDE.md § Pre-Dispatch Verification ¶ five-dimension confidence checklist._
- _File paths / framework names / helper APIs / test harness / cited counts verified against disk?_
  → Run the disk check inline (`ls`, `grep -c`, `head_limit:0` for enumerations). Any drift → fix the plan substrate before drafting body. _See CLAUDE.md § Pre-Dispatch Verification ¶ verify file paths and ¶ paginated grep._
- _Plan reverses a prior teardown / re-introduces a removed pattern?_
  → Run the negative-search procedure (grep `tasks/lessons.md` and wiki for the central nouns + prohibition vocabulary). _See `docs/wiki/writing-plans.md` § Negative-Search Before Drafting._
- _Native-code (C++/UE/Rust/etc.) plan?_
  → Add 2–3 in-tree `file:line` citations to the dispatch brief. _See CLAUDE.md § Pre-Dispatch Verification ¶ native-code plans._

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

---

## Exit — Handoff to `coordinator:review`

_Condition: plan body drafted, saved to `docs/plans/YYYY-MM-DD-<slug>.md`, ready for review._

→ Walk `coordinator:review` Branch A. That skill's Branch A.2 carries the auto-skip terminals (genuinely-trivial, PM-waived); this skill always exits there — seam exhaustiveness is provable from that skill's body.

**The full plan-writing pipeline is:** (1) substrate verification (Branch B above), (2) body composition with the four PM doctrinal lenses (Branch C above), (3) prior-art-checker via `coordinator:review` (skip only with an EM-justified rationale in the dispatch comment), (4) the Staff Engineer review, (5) review-integrator. Skipping `coordinator:plan` skips the pipeline; "I'll just write the plan and skip review" is the failure mode this skill exists to prevent.

<!-- Per docs/plans/2026-05-06-plan-super-skill.md F1 (PM lean b): coordinator:review Branch A.2 carries the auto-skip terminals. Renamed from "Branch D" to "Exit" per walk-through gap §2 — a one-row branch is shape-dishonest; this is a handoff, not a decision. -->

---

## Branch E — Mid-plan friction

_Condition: drafting is in progress and something is going sideways._

- _Repeating actions / oscillating between approaches / stalling?_
  → See `docs/wiki/stuck-detection.md` for the pattern catalog and recovery protocol.
- _Bug suspected mid-execution requiring root-cause investigation?_
  → See `docs/wiki/systematic-debugging.md` for the four-phase root-cause process.
