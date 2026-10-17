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

- _Concurrent-session pre-flight done?_ (BEFORE scouts or reviewer dispatch, not at Branch C)
  → **Read `gates.substrate.concurrent_preflight`** — one disk/git collision op: **(a)** today-dated-plan collision; **(b)** `source_memo:` collision. A hit is a PM-surface decision, not an abort. _See `skills/pickup/SKILL.md` M3._
- _Scope-path staleness re-check — at B.0 AND again immediately before the Exit's write-time commit?_
  → The pre-flight catches a competing PLAN, not competing WORK. Run `git log --since='<session start>' --oneline -- <each scope path>` over the `scope:` list, plus a line-count/symbol re-read of every file cited by `file:line`. **Re-run at commit time, not only at B.0.**
  → **When the premise is "a peer team might decline X", cross-repo memo surfaces are scope** — re-read `state/cross-repo/inbox/` and `state/cross-repo/archive/` for the topic before committing.
  → **Cite a peer repo's SHA as `<repo>@<sha>`, never bare.** Read `gates.substrate.peer_sha_lint` (`bad_citations[]`); a hit is a prompt to inspect, not a defect.
- _Seven-dimension confidence checklist green?_ (no-duplicate / no-fabrication / architecture-compatible / official-docs-read / reference-impl-seen / root-cause-known / fix-locus discrimination)
  → All seven green → Branch C. Any red → loop back to investigation Tier 1–3 or escalate to PM.
- _Cited sizing-object's `estimate.tshirt` is L or XL (never on the `spec-dispatch` lane)?_
  → Read the atlas per `writing-plans.md` § Codebase Research; record `atlas_consult` (pages, each `last_attested`, finding). Advisory, never a loop-back.
- _Eighth dimension — unproven mechanism gate: does this plan rest on a mechanism not proven viable?_
  → **A TYPED LOOP-BACK-TO-DERISK, not a third exit:** RED loops back like the seven, to a `/spike` destination.
  → **Consume `premise_unproven` off the object** (M/L/XL/XXL); `true` is RED. **Detent absent** (S/XS, or an express-lane sizing): read the object's `premise` field. Only `executed` is GREEN. Treat bare `read` as RED (mechanism read but never run; `coordinator:spike` is the discharge); it clears only when `premise.spike_verdict` carries `viable` for this exact mechanism. `not-applicable`/`unrecorded` leaves the dimension to be evaluated fresh. **Never reach M by widening `_LARGE_TSHIRTS`.**
  → **GREEN:** proceed to Branch C (resumed from trampoline: cite the `viable` verdict record, `docs/research/spike-verdicts/`). **RED:** trampoline to `coordinator:spike`, not contingent chunks assuming the mechanism works.
  → **Trampoline mechanism** (the `plan⇄spike` back-edge; spike-side half: `coordinator/skills/spike/SKILL.md` § The `plan⇄spike` back-edge):
    - Fires HERE, before Branch C; the deferred intent lives in the verdict record's **`gated route`** field. Dispatch `coordinator:spike` carrying the `trampoline: true` signal this entry path supplies (never fabricate it elsewhere). On `viable`, re-enter Branch B with only the eighth dimension flipped.
    - **(d) `not-viable`.** Does NOT loop back into Branch B — it goes to `coordinator:shape` / PM for a mechanism reconsider.
- _Verified-scope collapse — does Branch B's own verification show the ask is materially smaller than what was sized?_
  → **A TYPED LOOP-BACK to `coordinator:sizing` (the `plan⇄sizing` back-edge), not a third exit.**
  → **Fires only when ALL hold:** (1) the seven-dimension checklist is all-green; (2) the eighth dimension is green; (3) the drafted `scope:` list is ≤2 files (count it), no new abstraction, an existing test surface already covers it, and no scope path crosses a repo root.
  → **Action:** invoke `coordinator:sizing` with `--probe-signal collapse` and the Branch B findings as `--scout-evidence`.
  → **Resume** per the returned route (as Branch A), at most once per pass. `shape` leaves `plan`; `roadmap`/`pm-decision`/`goal-setting` are unreachable: stop and re-read the evidence. No cycle guard.
- _Fix-locus discrimination — is this the right layer to fix the bug?_
  → **Green:** the upper-layer registry/dispatch/extension site is identified by `file:line` (one level above each proposed edit site) AND you can name a concrete reason patching it is wrong.
  → **Red:** you cannot articulate why the upper layer is wrong, OR it already carries the gate type the patch would re-implement. Loop back to Tier 1–3 on the upper-layer mechanism; reframe around extending its gate.
- _File paths / framework names / helper APIs / test harness / cited counts verified against disk?_ → Run the check inline (`ls`, `grep -c`, `head_limit:0`). Any drift → fix substrate before drafting.
- _Plan's mechanism rests on a single external-tool BEHAVIORAL fact (not a signature)?_ → **Route it through a `docs-checker`/citation pass even when it looks self-evident**; cite the confirming source in the plan body.
- _Plan changes existing code (replaces/edits/removes a symbol it assumes present)?_ → **Grep the symbol-to-replace at plan-write time to confirm the fix-locus is still un-shipped**; absent or already-changed → re-investigate and amend substrate.
- _Plan scopes an edit to a function the production path may not call?_ → **STEP-0 caller-grep.** `git grep '<F>('` to confirm the production path reaches the edit locus before scoping a chunk to it.
- _Plan adds a transitional default (`X=None`) meaning to cut param `X` later, at a call site invoked positionally?_ → **Verify positional vs keyword** with `git grep '<callee>('` before scoping the cut. **On a positional hit:** the chunk that removes `X` MUST also pin a keyword-rebind of the surviving trailing arg(s) at that call site, in the same edit.
- _Plan reverses a prior teardown / re-introduces a removed pattern?_ → Negative-search: grep `state/lessons/` and the wiki for the central nouns plus prohibition vocabulary.
- _Native-code (C++/UE/Rust) plan?_ → Add 2–3 in-tree `file:line` citations to the dispatch brief, and declare `row_build_gate` frontmatter (`[{when: {change_kind, surface_glob}, command}]`) so each compiled row's executor builds before returning DONE.
- _Plan renumbers or rekeys a published API (constants, error codes, route numbers, step indices)?_ → The reverse-reference scan greps ≥3 shapes per value: bare number, quoted (`'N'`/`"N"`), fmt-string (`{n}`/`%d`), comment form (`# step N`).
- _Plan adds a new dispatch / handler / op / job to a surface with registered entries?_ → If a table/registry pattern exists (`UE_REGISTER_*`, `register_action`, plugin auto-registration), the plan MUST use it.
- _Plan ports / mirrors / adapts a feature from a peer repo?_ → If the host has its own registration seam / hookspec / extension point, **default to host-registration over parallel-surface**; a parallel surface requires a documented reason.

When drafting a plan body on either lane, cutting an item from the complete problem set is an
untrusted-gate obligation: any item cut MUST become a spine row with a closed disposition (spun
off, backlogged, ruled out) and a real disposition detail — never a silent drop, never a row the
author approves themselves. The cut is not authorized until the PM approves the grouping it lands
in. A distill-routed item (ADR, lineage, docs chunk) is not a cut and needs no grouping approval,
but keeps its `## Distill pass` tracking hook (Branch A).

- _Spine rows and the prime exit criterion testable + time framed for agents, not humans?_
  → Each is a binary pass/fail check. Reject human-sprint framing ("two-week effort", "Q3 milestone").

- _A "we'll add X later" / scope-trim / YAGNI argument is in the draft?_ → **Always surface to PM**, never EM-unilateral. YAGNI is a product call.
- _A "soon = now" deferral candidate?_ (an item deferred because the EM thinks it lower-priority than the headline work)
  → Ship it in this plan or get explicit PM disposition: **both** the case against shipping now (`case_against`) **and** a non-vacuous `disposition_detail`, plus a recommendation stating your confidence. No silent deferrals. _Form: `coordinator/docs/wiki/planning/writing-plans.md`._

- _Each chunk has an identified test surface?_ — a set-containment check: the named test paths must be a subset of that chunk's own scope paths (Tier T, below).
  → Name the test per chunk, or document why none; where another chunk's test exercises this chunk's output, name which chunk authors the file. **The named surface MUST be Tier T — path-scoped to the files that chunk authors or touches.** Naming the repo's fast tier or full suite is malformed. Global or cadence-scoped verification (Tier F/U) is **EM-owned at the wave boundary or cadence gate** — never a chunk's test surface, never a plan deliverable. _Tiers: `coordinator/skills/validate/SKILL.md`; EM-owned mechanism: `execute-plan/SKILL.md`._
- _Plan will hand off to an executor agent?_ (sub-conditions additive)
  - **Always:** apply the standard hard-constraints block (explicit file scope, no commits, no out-of-scope edits, no fallback escape hatches) — confirm via `gates.composition.hard_constraints_block` (`present`).
  - _Parallel executors with file-overlap risk?_ → **Read `gates.composition.chunk_overlap`** (`pairs[]`).
  - _Stub spawns sub-agents?_ → Mark it read-only-planner; sub-task dispatch happens at EM level, never nested.
  - _Touches concurrency-shared state?_ → Prefer per-machine paths to atomic-merge logic.

- _A single chunk would hand ONE executor multiple independent deliverables?_ (N modules or disjoint files whose **write** targets do not overlap — check it as a pairwise intersection over each deliverable's own write-target file list; an empty intersection between any two is the fan-out signal)
  → **Decompose into N chunks at plan-write time.** Only three justifications keep them together: (a) genuine write-overlap — even then a *sequence* of small dispatches; (b) an unpinnable shared interface; or (c) N files taking the SAME deterministic transform: one row or script, never N (`A-SAME-RULE-TRANSFORM-OVER-N-FILES-IS-ONE-ROW`). **A shared read-only source and a pinned import contract are NOT serialization reasons** — both are `reads_at_head:`; only WRITE-overlap gates parallelism. Size each chunk to ~5-10 min, 15 min ceiling. **`writes:` is REQUIRED on every non-deferred row** (`deferred: true` rows are exempt). **`depends_on:` (array of `{chunk, gate_kind}`) is required wherever the author imposes a gate the write graph cannot compute** — never for write-overlap; consult `plan-tasks.schema.json`'s `gate_kind` NEGATIVE SPEC first, three of six kinds are unwritable there. `dispatch.emit` cannot fire on an undeclared array. _Ledger schema: [`skills/execute-plan/SKILL.md`](../execute-plan/SKILL.md) Phase 1.6._
- **Read `gates.composition.path_rename_or_move`** (`fires`/`paths[]`, any `git mv`, rename, relocation, or directory restructure — **the trigger is path movement, not `scope_mode`**).
  → **Schedule a post-execution `doc-link-checker` dispatch as the closeout chunk**, only when you grep the repo for inbound links to each moved path (`grep -rn "<old-path>" --include=*.md`), diff against what `validate-references` covers, and the residual is non-empty; note why when skipped. When an executor does the move, the brief carries the rename procedure (`coordinator/agents/executor.md` § Moving or Renaming Files, plain `mv`) and `writes:` lists BOTH old and new paths as plain strings (no globs).

- A row that creates or modifies a module directory's barrel file (e.g. `index.ts`) declares that
  barrel path in its own `writes:`; `premise-check`/`plan-coverage-checker` flag its silent omission.

- _Cross-plan conflict scan run? (mandatory before dispatch)_
  → **Read `gates.composition.cross_plan_conflict`** (`hits[]`, each `{plan_path, overlapping_paths[]}`). The scan covers plugin-nested plan dirs (`plugins/*/*/docs/plans/*.md`) and `owns_plans:`/`install_surface_index:` frontmatter (single-owner claims with no body prose); check both before claiming a file unowned. Fold findings into `## Cross-plan coordination`: each sibling plan touched, what assumption it carries, and whether this plan amends / defers to / supersedes it. No hits → write the section anyway with `scanned — no overlapping file scope, seam citations, or ownership-frontmatter claims`.

- _Plan contains a chunk authoring a handoff, spinoff, or workstream-complete artifact?_ — grep the drafted chunk headings/bodies for authoring verbs against those three artifact names; any hit fires this row.
  → **Reject the chunk:** PM-gated session-continuity artifacts are not plan deliverables; "Chunk N: write a spinoff" launders the PM gate through plan approval. Use commit-and-stop or `/workday-complete` for wrap-up; PM-as-relay or `cross-repo-memo` cross-repo.
- _Plan brief contains code blocks the executor will consume?_ — a fenced-block lint: every fenced block in the chunk body must carry a `TEMPLATE` (executor adapts paths/values) or `VERBATIM` (copies as-is) marker comment directly above it. Unmarked pseudocode-shaped bash gets faithfully transcribed into broken shell.

→ **Do not ask the PM whether to proceed to whichever terminal the route selected.** Asking "want me to invoke review now?" is a doctrine violation — the answer is always yes.

Plan review altitude is graded by lane (named Opus persona on `plan`; Sonnet `plan-reviewer` first on accepted-XL; one pre-dispatch `plan-reviewer` pass on `spec-dispatch`, whose mandatory scoped `code-reviewer` pass still binds and which does not replace `code-reviewer`'s post-hoc review of the executor's diff). Detail: `coordinator/docs/wiki/planning/writing-plans.md` § Plan skill residue.

The `plan`-route terminal runs a pipeline of substrate verification, four-lens composition, (accepted-XL only) `plan-reviewer`, three pre-flights, and a named Opus reviewer who applies and verifies its own findings.

**The light terminal is a shortened pipeline** — (1) and a reduced (2) still run; (3)–(5) are replaced by its cross-plan-scan-then-dispatch sequence.

## Branch D — Executor BLOCKED on substrate drift

_Condition: a dispatched executor returns BLOCKED citing substrate differing from what the plan asserted (path moved, helper renamed, framework changed, contract field absent, schema column missing)._

- _Default: amend the plan or write a successor; do NOT silently expand executor scope to absorb the drift._
  → Re-invoke `coordinator:plan` to amend (small drift) or compose a successor (larger drift or shape change). Re-run the pipeline on the amended body from substrate verification; that invariant is shared; which chain discharges it is selected by the lane. `plan`: prior-art-checker → named Opus persona, who applies its own findings and verifies via `review-findings-ledger verify`. `spec-dispatch`: re-run **Branch B** over the drifted paths, amend the light body, re-fire the light terminal (cross-plan scan, pre-dispatch `plan-reviewer` pass, then dispatch); its scoped `code-reviewer` pass over the re-dispatched diff still binds. **Do not hand the S lane the full lane's chain**; the pre-dispatch `plan-reviewer` pass is one pass, not that chain; it does not gate on a persona verdict and adds no re-run obligation.
- _Product-risk findings during BLOCKED inspection (privacy, permission-default change, external contract shift)?_
  → Even under `/autonomous`, surface them via `AskUserQuestion` before amending.

## Branch E — Mid-plan friction

_Condition: drafting is in progress and something is going sideways._

- _Repeating actions / oscillating / stalling?_ — three literal counts over the transcript, each independently checkable: same action **3+ times** with the same result; **4+ actions** alternating between two approaches; **3+ paragraphs** of analysis with no tool call.
  → Stop, name the pattern, and switch to a fundamentally different approach (report BLOCKED if none exists).
- _Bug suspected mid-execution needing root-cause work?_ → Invoke `coordinator:systematic-debugging`.
