---
segment_id: shared-corpus
route: shared
class: protected
order: 790
---

## Branch B — Pre-write substrate verification

_Condition: a plan doc is the right artifact; substrate must be verified BEFORE the body is drafted._

### B.0 — Problem-shape confirmation (the doubt-check)

_Runs first: verifying you understood the problem precedes verifying the file paths that solve it. This is the always-on floor catching the case where Branch A's `/shape` offer was declined or skipped._

- **Read `gates.substrate.problem_set`** (`present`/`path`) → cite the path; satisfied.

- _Concurrent-session pre-flight done?_ (BEFORE scouts or reviewer dispatch — not at Branch C)
  → **Read `gates.substrate.concurrent_preflight`** — one disk/git collision op: **(a)** today-dated-plan collision; **(b)** `source_memo:` collision. A hit is a PM-surface decision, not an automatic abort. _See `skills/pickup/SKILL.md` M3._
- _Scope-path staleness re-check — at B.0 AND again immediately before the Exit's write-time commit?_
  → The pre-flight catches a competing PLAN, not competing WORK. Run `git log --since='<session start>' --oneline -- <each scope path>` over the `scope:` list, plus a line-count/symbol re-read of every file the body cites by `file:line`. **Re-run at commit time, not only at B.0.**
  → **When the plan's premise is "a peer team might decline X", the cross-repo memo surfaces are part of scope** — re-read `state/cross-repo/inbox/` and `state/cross-repo/archive/` for the topic before committing.
  → **Cite a peer repo's SHA as `<repo>@<sha>`, never bare.** Read `gates.substrate.peer_sha_lint` (`bad_citations[]`); a hit is a prompt to inspect, not an automatic defect.
- _Seven-dimension confidence checklist green?_ (no-duplicate / no-fabrication / architecture-compatible / official-docs-read / reference-impl-seen / root-cause-known / fix-locus discrimination)
  → All seven green → Branch C. Any red → loop back to investigation Tier 1–3 or escalate to PM.
- _Cited sizing-object's `estimate.tshirt` is L or XL (never true on the `spec-dispatch` lane)?_
  → Read the atlas per `writing-plans.md` § Codebase Research; record `atlas_consult` (pages + each page's `last_attested`, finding). Advisory, never a loop-back; an uncovered surface is a `finding`, not a blocker.
- _Eighth dimension — unproven mechanism gate: does this plan rest on a mechanism not proven viable?_
  → **A TYPED LOOP-BACK-TO-DERISK, not a third exit:** on RED it resolves to the same loop-back as the seven, specialized to a `/spike` destination.
  → **Consume `premise_unproven` off the object** (M/L/XL/XXL); `true` is RED. **Detent absent** (S/XS, or an express-lane sizing): read the object's `premise` field. Only `executed` is GREEN. Treat bare `read` as RED (mechanism read but never run; `coordinator:spike` is the discharge); it clears only when `premise.spike_verdict` carries `viable` for this exact mechanism. `not-applicable`/`unrecorded` leaves the dimension to be evaluated fresh. **Never reach M by widening `_LARGE_TSHIRTS`.**
  → **GREEN (no unproven mechanism):** proceed to Branch C. **GREEN (resumed from trampoline):** cite the `viable` verdict record (`docs/research/spike-verdicts/`); re-enter Branch C.
  → **RED:** viability hinges on a mechanism not yet empirically demonstrated. **Action:** trampoline to `coordinator:spike` instead of drafting contingent chunks that assume it works.
  → **Trampoline mechanism** (the `plan⇄spike` back-edge; its spike-side half lives in `coordinator/skills/spike/SKILL.md` § The `plan⇄spike` back-edge):
    - **(a) Timing.** Fires HERE, before Branch C begins; the deferred plan-authoring intent is captured in the verdict record's **`gated route`** field, never a plan-body stub or parked chunk list.
    - **(b) Dispatch.** Invoke `coordinator:spike` on the specific mechanism, carrying the DEC-4 structural `trampoline: true` signal, which the Branch B entry path supplies; a bare `/spike` without it is always PM-gated — do not fabricate the signal outside this entry path.
    - **(c) Resume.** On a `viable` verdict, **resume re-enters Branch B — NOT a fresh Branch A triage, NOT a full seven-dimension re-run.** Only the eighth dimension flips; carry the other seven forward. Continue into Branch C.
    - **(d) `not-viable`.** Does NOT loop back into Branch B — it goes to `coordinator:shape` / PM for a mechanism reconsider.
- _Verified-scope collapse — does Branch B's own verification show the ask is materially smaller than what was sized?_
  → **A TYPED LOOP-BACK to `coordinator:sizing` (the `plan⇄sizing` back-edge), not a third exit.**
  → **Fires only when ALL hold:** (1) the seven-dimension checklist is all-green; (2) the eighth dimension is green; (3) the drafted `scope:` list is ≤2 files (count it), no new abstraction, an existing test surface already covers it, and no cross-repo contract (no scope path crosses a repo root).
  → **Action:** invoke `coordinator:sizing` with `--probe-signal collapse` and the Branch B findings as `--scout-evidence`.
  → **Resume — all seven routes disposed:** **`plan`** → resumes at **Branch C**, not Branch B; full terminal. **`spec-dispatch`** → Branch C at S-lane weight; light terminal. **`dispatch`** → abandon the pass and dispatch directly. **`shape`** → leave `plan`, shape's exit chains back here. **`roadmap`/`pm-decision`/`goal-setting`** → **unreachable by construction** (the probe signal only moves the t-shirt down); one returning anyway means the probe signal was mis-fed — stop and re-read the Branch B evidence.
  → **Termination.** Fires at most once per pass; do not add a cycle guard.
- _Fix-locus discrimination — is this the right layer to fix the bug?_
  → **Green:** the upper-layer registry/dispatch/extension site is identified by `file:line` (one level above each proposed edit site) AND you can name a concrete reason patching it is wrong (registry already gates this case; it is a closed contract; it is hot-path with unrelated callers).
  → **Red:** you cannot articulate why the upper layer is wrong, OR it is a registry/dispatch site already carrying the gate type the patch would re-implement at the call site.
  → **On red:** loop back to Tier 1–3 on the upper-layer mechanism; if an upper-layer gate exists, reframe around extending it.
- _File paths / framework names / helper APIs / test harness / cited counts verified against disk?_
  → Run the check inline (`ls`, `grep -c`, `head_limit:0` for enumerations). Any drift → fix substrate before drafting.
- _Plan's mechanism rests on a single external-tool BEHAVIORAL fact (not a signature)?_
  → **Route it through a `docs-checker`/citation pass even when it looks self-evident to the author** Cite the confirming source in the plan body.
- _Plan changes existing code (replaces/edits/removes a symbol it assumes present)?_
  → **Grep the symbol-to-replace at plan-write time to confirm the fix-locus is still un-shipped.** Absent or already-changed → re-investigate and amend substrate. This is fix-locus *liveness*, distinct from *discrimination* (which layer) above and from the path row before it (that confirms the FILE exists).
- _Plan scopes an edit to a function the production path may not call?_
  → **STEP-0 caller-grep.** `git grep '<F>('` (or the language equivalent) to confirm the production path reaches the proposed edit locus before scoping a chunk to it.
- _Plan adds a transitional default (`X=None`) meaning to cut param `X` later, at a call site invoked positionally?_
  → **Verify the call shape (positional vs keyword) before scoping the cut — not after.** Grep each call site (`git grep '<callee>('`) for its literal arg list. **On a positional hit:** the chunk that removes `X` MUST also pin a keyword-rebind of the surviving trailing arg(s) at that call site, in the same edit.
- _Plan reverses a prior teardown / re-introduces a removed pattern?_
  → Run the negative-search procedure: grep `state/lessons/` and the wiki for the central nouns plus prohibition vocabulary.
- _Native-code (C++/UE/Rust) plan?_ → Add 2–3 in-tree `file:line` citations to the dispatch brief.
- _Plan renumbers or rekeys a published API (constants, error codes, route numbers, step indices)?_
  → The reverse-reference scan must grep ≥3 shapes per value: bare number, quoted (`'N'`/`"N"`), fmt-string (`{n}`/`%d`), and comment form (`# step N`).
- _Plan adds a new dispatch / handler / op / job to a surface with registered entries?_
  → Check for a table/registry pattern (`UE_REGISTER_*`, `register_action`, plugin auto-registration). If one exists the plan MUST use it.
- _Plan ports / mirrors / adapts a feature from a peer repo?_
  → Check whether the host has its own registration seam / hookspec / extension point. **Default to host-registration over parallel-surface**; if a seam exists the plan MUST attach via it; a parallel surface requires a documented reason.

When drafting a plan body on either lane, cutting an item from the complete problem set is an
untrusted-gate obligation, never composition machinery the EM discharges alone: any item cut MUST
become a spine row with a closed disposition (spun off, backlogged, ruled out) and a real
disposition detail — never a silent drop, never a row the author approves themselves. The cut is
not authorized until the PM approves the grouping it lands in. A distill-routed item
(ADR, lineage, docs chunk) is not a cut and needs no grouping approval, but it keeps a tracking
hook — a non-empty `## Distill pass` referenced from the closing handoff or the
`/workstream-complete` step, which hands its items to `/distill`.

- _Spine rows and the prime exit criterion testable + time framed for agents, not humans?_
  → Each spine row and the prime exit criterion's falsifier leg is a binary pass/fail check. Reject human-sprint framing ("two-week effort", "Q3 milestone").

- _A "we'll add X later" / scope-trim / YAGNI argument is in the draft?_ → **Always surface to PM**, never EM-unilateral. YAGNI is a product call.
- _A "soon = now" deferral candidate?_ (an item deferred because the EM thinks it lower-priority than the headline work)
  → Either ship it in this plan or get explicit PM disposition — and disposition means **both** the case against shipping now (`case_against`) **and** a non-vacuous `disposition_detail`, plus a recommendation stating your confidence. No silent deferrals. _Full both-sides form: `coordinator/docs/wiki/planning/writing-plans.md`._

- _Each chunk has an identified test surface?_ — a set-containment check: the named test paths must be a subset of that chunk's own scope paths (Tier T, below).
  → Name the test per chunk, or document why none. Where another chunk's test exercises this chunk's output, name which chunk authors the file; an implementation chunk does not author its own tests unless the brief says so. **The named surface MUST be Tier T — path-scoped to the files that chunk authors or touches.** Naming the repo's fast tier or full suite is malformed at plan-write time. Genuinely global or cadence-scoped verification (Tier F/U) is **EM-owned at the wave boundary or cadence gate** — never a chunk's test surface, never a plan deliverable. _Tier definitions: `coordinator/skills/validate/SKILL.md`; the EM-owned mechanism: `execute-plan/SKILL.md`._
- _Plan will hand off to an executor agent?_ (sub-conditions additive)
  - **Always:** apply the standard hard-constraints block (explicit file scope, no commits, no out-of-scope edits, no fallback escape hatches) — confirm via `gates.composition.hard_constraints_block` (`present`).
  - _Parallel executors with file-overlap risk?_ → **Read `gates.composition.chunk_overlap`** (`pairs[]`).
  - _Stub spawns sub-agents (orchestrator-shaped)?_ → Mark it read-only-planner; sub-task dispatch happens at EM level, never nested.
  - _Touches concurrency-shared state (shared appends across machines/sessions, shared index or lock)?_ → Prefer per-machine paths over atomic-merge logic.

- _A single chunk would hand ONE executor multiple independent deliverables?_ (N modules or disjoint files whose **write** targets do not overlap — check it as a pairwise intersection over each deliverable's own write-target file list; an empty intersection between any two is the fan-out signal)
  → **Decompose into N chunks at plan-write time — fan-out chunking is a plan-author obligation, not an execution-time afterthought.** Only two justifications keep them together: (a) genuine write-overlap — even then a *sequence* of small dispatches, not one fat executor — or (b) an unpinnable shared interface. **A shared read-only source and a pinned import contract are NOT serialization reasons** — both are `reads_at_head:`, and only WRITE-overlap gates parallelism. Size each chunk to ~5-10 min, 15 min ceiling. **`writes:` is REQUIRED on every non-deferred row** (`deferred: true` rows are exempt). **`depends_on:` (array of `{chunk, gate_kind}`) is required wherever the author imposes a gate the write graph cannot compute** — never for write-overlap, which the wave-builder derives on its own; consult `plan-tasks.schema.json`'s `gate_kind` NEGATIVE SPEC first, three of six kinds are unwritable there. `dispatch.emit` cannot fire on an undeclared array. _Late-correction: [`skills/execute-plan/SKILL.md`](../execute-plan/SKILL.md) Phase 1.6; the ledger schema lives only there._
- **Read `gates.composition.path_rename_or_move`** (`fires`/`paths[]`, any `git mv`, rename, relocation, or directory restructure — **the trigger is path movement, not `scope_mode`**).
  → **Schedule a post-execution `doc-link-checker` dispatch as the closeout chunk, subject to the precondition below.**
  → **Precondition, checkable inline:** grep the repo for inbound links to each moved path (`grep -rn "<old-path>" --include=*.md`), then diff against what `validate-references` already covers. Schedule the closeout chunk ONLY when the residual is non-empty. **Skip, and note why, when** inbound links are private-repo absolute self-URLs or already covered by `run-all-checks`.
  → **When the gate fires and the plan hands the move to an executor**, the chunk brief MUST carry the rename procedure (`coordinator/agents/executor.md` § Moving or Renaming Files — plain `mv`, not `git mv`; report both path sets to the EM), and the chunk's `writes:` MUST enumerate BOTH sides — old paths and new. `writes:` takes plain strings, no glob syntax (`coordinator/schemas/plan-tasks.schema.json:107-110`); a directory-shaped move is enumerated path-by-path.

- A row that creates or modifies a module directory's barrel file (e.g. `index.ts`) declares that
  barrel path in its own `writes:` — a re-exporting entry point is a write like any other, and
  `premise-check`/`plan-coverage-checker` flag its silent omission the same way they flag any
  undeclared write.

- _Cross-plan conflict scan run? (mandatory before dispatch)_
  → **Read `gates.composition.cross_plan_conflict`** (`hits[]`, each `{plan_path, overlapping_paths[]}`). The scan must cover plugin-nested plan dirs (`plugins/*/*/docs/plans/*.md`), not just `docs/plans/*.md` — a single-owner declaration can live under a plugin-nested path, and `owns_plans:`/`install_surface_index:` frontmatter can declare a hotspot file single-owner with no body prose a path grep would catch; check both before claiming a file unowned. Fold findings into `## Cross-plan coordination`: each sibling plan touched, what assumption it carries, and whether this plan amends / defers to / supersedes it. No hits → write the section anyway with `scanned — no overlapping file scope, seam citations, or ownership-frontmatter claims`.

- _Plan contains a chunk authoring a handoff, spinoff, or workstream-complete artifact?_ — grep the drafted chunk headings/bodies for authoring verbs against those three artifact names; any hit fires this row.
  → **Reject the chunk.** These are PM-gated session-continuity artifacts, not plan deliverables; "Chunk N: write a spinoff" launders the PM gate through plan approval. Correct primitives instead: commit-and-stop or `/workday-complete` for a wrap-up chunk; PM-as-relay or `cross-repo-memo` for a cross-repo one.
- _Plan brief contains code blocks the executor will consume?_ — a fenced-block lint: every fenced block in the chunk body must carry a `TEMPLATE` (executor adapts paths/values) or `VERBATIM` (copies as-is) marker comment directly above it. Unmarked pseudocode-shaped bash gets faithfully transcribed into broken shell.

→ **Do not ask the PM whether to proceed to whichever terminal the route selected.** Asking "want me to invoke review now?" is a doctrine violation — the answer is always yes.

Plan review altitude is graded by lane: a named Opus persona on the `plan` route, a Sonnet
`plan-reviewer` lens ahead of it on the accepted-XL lane, and on the `spec-dispatch` lane a
single pre-dispatch `plan-reviewer` pass and no Opus review. The lane's compensating control is
the light terminal's own mandatory scoped `code-reviewer` pass (§ `spec-dispatch` row), binding
on every exit; the pre-dispatch pass reviews the plan body and does not replace `code-reviewer`'s
post-hoc review of the executor's diff.

The `plan`-route terminal runs a pipeline of substrate verification, four-lens composition, (accepted-XL only)
`plan-reviewer`, three pre-flights, and a named Opus reviewer who applies and verifies its own findings.
**The light terminal is a deliberately shortened pipeline** — (1) and a reduced (2) still run;
(3)–(5) are replaced by its cross-plan-scan-then-dispatch sequence.

## Branch D — Executor BLOCKED on substrate drift

_Condition: a dispatched executor returns BLOCKED citing substrate differing from what the plan asserted (path moved, helper renamed, framework changed, contract field absent, schema column missing)._

- _Default: amend the plan or write a successor; do NOT silently expand executor scope to absorb the drift._
  → Re-invoke `coordinator:plan` to amend (small drift, same workstream) or compose a successor (larger drift or shape change). Re-run the pipeline on the amended body from substrate verification — **that invariant is shared; which chain discharges it is selected by the lane.** `plan`: prior-art-checker → named Opus persona, who applies its own findings and verifies via `review-findings-ledger verify`. `spec-dispatch`: re-run **Branch B** over the drifted paths, amend the light body, re-fire the light terminal (cross-plan scan, pre-dispatch `plan-reviewer` pass, then dispatch); its mandatory scoped `code-reviewer` pass over the re-dispatched diff still binds. **Do not hand the S lane the full lane's chain** — the pre-dispatch `plan-reviewer` pass is one pass inside the light terminal, not that chain; it does not gate on a persona verdict and adds no re-run obligation of its own.
- _Product-risk findings during BLOCKED inspection?_
  → Even under `/autonomous`, surface them via `AskUserQuestion` before amending (a privacy implication, a permission-default change, an external contract shift).

## Branch E — Mid-plan friction

_Condition: drafting is in progress and something is going sideways._

- _Repeating actions / oscillating / stalling?_ — three literal counts over the transcript, each independently checkable: same action **3+ times** with the same result; **4+ actions** alternating between two approaches; **3+ paragraphs** of analysis with no tool call.
  → Recognize the pattern, then stop, name it, and switch to a fundamentally different approach (report BLOCKED if none exists).
- _Bug suspected mid-execution needing root-cause work?_ → Invoke `coordinator:systematic-debugging`.
