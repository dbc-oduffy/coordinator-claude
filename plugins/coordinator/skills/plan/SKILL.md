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

**When NOT to use:** Trivial work (single-file fix, typo, link repoint, no abstraction) → just do it. Implementation-only ambiguity mid-coding → harness Plan tool inline. Architectural-tier (cross-system irreversible, multi-stakeholder) → surface to PM first. PM in exploration mode or problem-shape not yet converged → `coordinator:shape` first (see Branch A). Spec vague or multi-subsystem → `coordinator:brainstorming` first. Skill-authoring (writing a SKILL.md) → `plugin-dev:skill-development`. Plan already written and needs review → `coordinator:review`. Stuck pattern → see `docs/wiki/stuck-detection.md`.

---

## Branch A — Triage: should I plan, and at what altitude?

_Condition: EM has just received a planning trigger; first decision is whether a plan doc is the right artifact._

- _Trivial?_ (single-file change, no new abstraction, scope obvious from the ask)
  → Just do it. No plan doc. _See CLAUDE.md § Plan-First Workflow._
- _Implementation-only ambiguity?_ (multi-line edit where the EM is choosing between two equally valid shapes mid-typing)
  → Use the harness Plan tool inline. No plan doc.
- _PM has set a session axiom?_ (PM said *"we are going to do X"* / *"the next thing is Y"* / *"build Z this session"* — an explicit directive that names the work, not a question about the work)
  → Disposition default flips to **plan**, not brainstorm. The brainstorm-vs-plan triage is bypassed: the PM has already chosen scope; the EM's job is to plan the named work, not to re-litigate whether to scope it differently. Continue to **Branch B**. The architectural-tier check (final bullet) still fires — a PM axiom does not override an architectural surface-to-PM. _See CLAUDE.md § Challenging the PM ¶ EM owns implementation discretion; PM owns product authority._
- _PM in exploration mode, OR problem-shape not yet converged, OR the EM detects it is guessing at the problem?_ (open-ended framing — *"what do you think?"*, *"I'm not sure about X"*, a problem named without a deliverable; or the EM cannot confidently restate the problem the PM is solving)
  → Propose `coordinator:shape` **before** committing to plan — converge on the problem (the PRD half) first; its exit gate chains back here. This is the seam where premature convergence happens, and the EM-side complement to the global First Officer Engagement-Modes doctrine (which is personal and does not ship). **Precedence:** a PM session axiom and the architectural-tier check both take precedence — `/shape` is the exploration/unconverged-problem branch, NOT an override of a PM directive to plan named work. Discriminating test vs. brainstorming: *if the PM HAS a problem and wants confirmation you understood it (vs. not knowing what to build at all) → `coordinator:shape`, not `coordinator:brainstorming`.*
- _Cross-repo work, even when a handoff says "ready to execute" / "investigation complete, straight execution" / "XS"?_ (the work touches ≥2 sibling repos, OR it ships a cross-repo contract / hookspec / shared fixture, OR it requires sibling-EM coordination via memo)
  → **Invoke `coordinator:plan` anyway — do NOT execute directly off the handoff's t-shirt.** Handoff t-shirt sizing from inside an investigation is systematically too low for cross-repo plans: investigation reveals the *structural* problem ("here's what's wrong, here's the fix shape"), but planning reveals the *implementation blast radius* (N repos, M reviewers, contract fixtures, framing-inversion checks). The two scopes are different. The 2026-05-21 unreal-toml-concern handoff is the empirical case — tagged tshirt: XS ("investigation complete, straight execution"), actual scope was 3 repos / 4-reviewer pipeline / Decision-#0 framing inversion caught at review / a real bug discovered in peer-repo reference impl / ~2000 LOC. The handoff scope is "decide what to build"; the plan scope is "decide how it ships across N repos with M reviewers." T-shirt promotes from inside the plan body, not from inside the handoff. Continue to **Branch B**.
- _Non-trivial (default for everything else)?_ (multi-file, new abstraction, cross-system, scaffolds an agent/skill, reverses prior teardown, touches shared schema)
  → Continue to **Branch B**.
- _Architectural-tier?_ (cross-system irreversible, multi-stakeholder, security/privacy boundary, naming-collision-with-product-policy)
  → Surface to PM: *"this looks architectural — propose `/staff-session`, want me to draft the staff-session brief?"* Wait for PM. _See CLAUDE.md § Challenging the PM and § Plan-First Workflow._

---

## Branch B — Pre-write substrate verification

_Condition: a plan doc is the right artifact; substrate must be verified BEFORE the plan body is drafted._

### B.0 — Problem-shape confirmation (the doubt-check)

_Runs first — problem-shape is the highest substrate; verifying you understood the problem precedes verifying the file paths that solve it. This is the always-on floor that catches the case where Branch A's `/shape` offer was declined or skipped (the "just roll with it" case)._

- **A ratified problem-set exists** (a prior `/shape` ran, or `docs/problems/<slug>.md` is cited in plan frontmatter via `problem_set:`) → cite it; the doubt-check is satisfied; proceed to substrate verification.
- **No ratified problem-set, and `scope_mode` is `feature` / `architecture` / `spike`** → produce the forced-articulation block before drafting tasks (and surface its material items to the PM): **(1)** restate the problem(s) in the PM's vocabulary, falsifiably; **(2)** name your single biggest uncertainty per the un-gaming clauses below; **(3)** flag any intent you inferred that the PM did not state.
- **No ratified problem-set, but `scope_mode` is `production-patch` / audit (obvious one-line problem)** → the doubt-check is a single restating sentence, not the full triad. Proportional to scope — matches the coverage nudge's silence for these scope_modes, and honours P5 (`AC7`: no gate fires heavily on trivial work).

**Un-gaming clauses for step (2)** — a yes/no "I have the shape ✓" is a banned response (EM confidence is coupled with helpfulness and self-reports green every time):
1. The least-certain item must be **the scope boundary whose wrong guess would cost the most rework** ("name the boundary that, if guessed wrong, invalidates the most of the plan") — NOT "name something you're unsure about."
2. State the **probability-weighted consequence** ("if I'm wrong about X, chunks C2–C4 are rework") — a trivial selection self-evidently fails this test.
3. The surfaced uncertainty must be a **PM-altitude question** (product intent, scope boundary, success criteria). Tactical/EM-decided uncertainties (naming, test framework, commit shape, file structure) are **disqualified as off-altitude** — not merely low-stakes — regardless of how unsure you are, per global `~/.claude/CLAUDE.md § PM Altitude`. Resolving them is your job; surfacing them is noise.

_Discriminating test vs. brainstorming, if the doubt-check reveals the problem itself is unconverged:_ *if the PM HAS a problem and wants confirmation you understood it (vs. not knowing what to build at all) → `coordinator:shape`, not `coordinator:brainstorming`.*

**Known boundary:** this floor protects the plan path only. Work mis-triaged as "trivial → just do it" at Branch A bypasses both `/shape` and the doubt-check by construction — there is no floor on the just-do-it path. The mitigation is EM alertness to exploration signals at the Branch A routing row, not a second doubt-check (which would over-ceremony the trivial path, violating P5). Named here as a known boundary, not a silent one.

- _Seven-dimension confidence checklist green?_ (no-duplicate / no-fabrication / architecture-compatible / official-docs-read / reference-impl-seen / root-cause-known / fix-locus discrimination)
  → All seven green → continue to Branch C. Any red → loop back to investigation Tier 1–3 or escalate to PM. _See CLAUDE.md § Pre-Dispatch Verification ¶ seven-dimension confidence checklist._
- _Fix-locus discrimination — is this the right layer to fix the bug?_
  → **Green:** planner has identified the upper-layer registry/dispatch/extension site by `file:line` (one level above each proposed edit site) AND can name a concrete reason patching the upper layer is wrong (registry already gates this case; upper layer is closed contract; upper layer is hot-path with unrelated callers).
  → **Red:** planner cannot articulate why the upper layer is the wrong locus, OR the upper layer is a registry/dispatch/extension site that already has the gate type the patch would re-implement at the call site.
  → **Action on red:** loop back to investigation Tier 1–3 on the upper-layer mechanism (Tier 2 / project-RAG preferred when indexed; Tier 3 grep works on unindexed repos). If an upper-layer gate exists, reframe the plan around extending it, not patching the call site. _See `docs/wiki/writing-plans.md` for the planning-time discipline (Fix-locus discrimination). CLAUDE.md § Pre-Dispatch Verification carries the analogous review-time discipline (¶ Reviewer rationale must discriminate)._
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
- _Plan will go through `coordinator:review`?_ (the gate predicate — any plan of non-trivial scope)
  → Use the bindable-table form for `## Acceptance Criteria`: `ID | Criterion (prose) | Test (typed-prefix) | Binding-Class | Status`. Pre-review, `Test` cells are `pending realization`; the reviewer reads prose criteria as a design lens. Post-review, each gate-bound row is realized as a named failing test using the typed-prefix scheme (`pytest:`, `grep:`, `cited:`, etc.). At done-time, the green-gate enforces these rows at `coordinator:merging-to-main` Step 0a. _See `docs/wiki/writing-plans.md` § Acceptance Oracle (outer-loop) for the full two-altitude flow and typed-prefix scheme._
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
  → **Reject the chunk.** Handoffs (`/handoff`), spinoffs (`/spinoff`), and session-end captures (`/session-end`) are PM-gated session-continuity artifacts, not plan deliverables. A plan that pre-authorizes "Chunk N: write a spinoff to <topic>" launders the PM gate through plan approval — by execution time, the EM treats it as a checklist item and the spinoff's Step 0 gate never fires. Two failure shapes this row prevents: (a) the plan's terminal chunk is "author handoff" used as a wrap-up ceremony when commit-and-stop or `/workday-complete` is the right artifact; (b) the plan's terminal chunk is "author spinoff to <other-EM>" used as cross-repo messaging when the actual primitive is PM-as-relay (copy-paste in chat, or use `cross-repo-memo --to <receiver-em> --topic <slug>` for structured briefs). If the plan genuinely needs cross-EM coordination, the chunk is "surface cross-repo brief to PM" with the brief composed inline or sent via `cross-repo-memo`. _See `docs/wiki/cross-repo-communication.md`._
- _Plan brief contains code blocks (shell, Python, config) the executor will consume?_
  → Mark every fenced block either `TEMPLATE` (illustrative — executor adapts paths/values) or `VERBATIM` (executor copies as-is). Convention: place a fenced comment above the block, e.g. `<!-- TEMPLATE: adapt paths -->` or `<!-- VERBATIM -->`. Unmarked pseudocode-shaped bash gets faithfully transcribed into broken shell — the convention is the fix.

---

## Exit — Auto-Invoke `coordinator:review`

_Condition: plan body drafted, saved to `docs/plans/YYYY-MM-DD-<slug>.md`, ready for review._

→ **Invoke `coordinator:review` immediately. Do not ask the PM whether to proceed to review — plan→review is the pipeline, not a checkpoint.** If the plan was worth formally writing, it is worth formally reviewing; the gating on review-or-not happens inside `coordinator:review` Branch A (Branch A.2 carries the auto-skip terminals for genuinely-trivial / PM-waived). Pausing to ask "want me to invoke review now?" is a doctrine violation — the answer is always yes, and the auto-skip path lives downstream.

**Reviewer altitude is binary: named Opus persona, or no review.** Plan review is an Opus-persona judgment task (the Staff Engineer / the Game Dev Reviewer / the Director of Engineering / the Data Science Reviewer / the Front-End Reviewer / the UX Reviewer). There is no Sonnet-tier plan reviewer, and `code-reviewer` is not one — it is the Sonnet **diff** reviewer (its own scope is "weak tests, dead code, unclear naming, correctness/security issues" on a frozen diff). Reaching for `code-reviewer` because "the Staff Engineer feels heavy for this plan" is the failure mode this row prevents. The correct fork is: plan merits review → named persona; plan does not merit review → skip review, implement, let `code-reviewer` catch issues on the diff at `/session-end` or `/handoff`. Sonnet-on-plan-body is not on the menu.

**The full plan-writing pipeline is:** (1) substrate verification (Branch B above), (2) body composition with the four PM doctrinal lenses (Branch C above), (3) `docs-checker` / `prior-art-checker` / **`plan-coverage-checker`** pre-flights via `coordinator:review`, (4) named reviewer (Opus persona), (5) review-integrator. Skipping `coordinator:plan` skips the pipeline; "I'll just write the plan and skip review", "let me ask first before invoking review", and "I'll send this to `code-reviewer` instead of the Staff Engineer" are the three failure modes this skill exists to prevent.

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
