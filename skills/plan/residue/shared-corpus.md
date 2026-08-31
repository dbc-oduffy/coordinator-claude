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
  → **Read `gates.substrate.concurrent_preflight`** — one disk/git collision op: **(a)** today-dated-plan collision; **(b)** `source_memo:` collision. Two concurrent EMs independently planning the same work is the failure mode, caught before any scout or reviewer spends tokens. **Judgment residue:** a hit on either leg is a PM-surface decision, not an automatic abort. **Residual:** the `source_memo:` leg catches the plan-routed collision only; a commit-only or `inline` realization is caught instead by the memo claim-lock (while `in_progress`) and the archived `realized_by` claim-of-record. _See `skills/pickup/SKILL.md` M3._
- _Scope-path staleness re-check — at B.0 AND again immediately before the Exit's write-time commit?_
  → **The pre-flight above catches a competing PLAN, not competing WORK.** Its legs grep `docs/plans/` and `source_memo:`; neither looks at the paths this plan proposes to change, so a peer shipping the actual fix into the plan's own scope files passes it silently. Close that over the `scope:` list: `git log --since='<session start>' --oneline -- <each scope path>`, plus a line-count/symbol re-read of every file the body cites by `file:line`. A cited line number that has moved is the cheapest staleness signal available.
  → **Re-run at commit time, not only at B.0.** Composition on a large plan takes long enough for a peer to land the work mid-draft; a clean B.0 pass says nothing about the tree at commit time.
  → **When the plan's premise is "a peer team might decline X", the cross-repo memo surfaces are part of scope** — re-read `cross-repo/inbox/` and `cross-repo/archive/` for the topic before committing. An acceptance landing mid-draft inverts the stated blast radius rather than shrinking it: chunks written for the decline branch describe a shape the delivered thing deliberately lacks, and an executor handed them regresses working code. No pre-flight lens covers this — `prior-art-checker` reads wiki/lessons, `plan-coverage-checker` reads the plan's own oracle; neither reads the inbox.
  → **Cite a peer repo's SHA as `<repo>@<sha>`, never bare.** Read `gates.substrate.peer_sha_lint` (`bad_citations[]`) — it also flags in-repo local SHAs/session ids, so `bad_citations` runs near-100% false-positive on a single-repo plan; treat a hit as a prompt to inspect, not an automatic defect.
- _Seven-dimension confidence checklist green?_ (no-duplicate / no-fabrication / architecture-compatible / official-docs-read / reference-impl-seen / root-cause-known / fix-locus discrimination)
  → All seven green → Branch C. Any red → loop back to investigation Tier 1–3 or escalate to PM.
- _Eighth dimension — unproven mechanism gate: does this plan rest on a mechanism not proven viable?_
  → **A TYPED LOOP-BACK-TO-DERISK, not a third exit.** Branch B's two-valued exit invariant holds: this dimension is evaluated alongside the seven and, on RED, resolves to the SAME loop-back, specialized to a `/spike` destination rather than a generic Tier 1–3 re-investigation.
  → **Consume `premise_unproven` off the object** — the detent covers M/L/XL/XXL, so no band reaching this skill needs a hand read; `true` is RED. **Detent absent** (S/XS, or an express-lane sizing): read the object's `premise` field. Only `executed` is GREEN — its inline evidence citation is the proof. Treat bare `read` as RED (mechanism read but never run; `coordinator:spike` is the discharge); it clears only when `premise.spike_verdict` carries `viable` for this exact mechanism. `not-applicable`/`unrecorded` leaves the dimension to be evaluated fresh. **Never reach M by widening `_LARGE_TSHIRTS`** — it also gates the shape route, so widening reroutes M-sized `jtbd_unclear` asks from `plan` to `shape`.
  → **GREEN (no unproven mechanism):** the common case. Nothing to cite; proceed to Branch C.
  → **GREEN (resumed from trampoline):** a prior `/spike` returned `viable` for this exact mechanism — cite the verdict record (`docs/research/spike-verdicts/`). Re-enter Branch C.
  → **RED:** viability hinges on a mechanism (a dependency behaving a certain way, an API doing something undocumented-here, a technique nobody here has exercised) that has not been empirically demonstrated. **The tell:** the natural next move would be "draft the plan anyway and let Chunk N's contingent sub-chunks handle it if the mechanism doesn't pan out" — that contingent-chunking instinct is exactly the token waste this row intercepts, since a reviewer burns tokens on chunks that may be moot. **Action: trampoline to `coordinator:spike` instead of drafting contingent chunks.**
  → **Trampoline mechanism** (the `plan⇄spike` back-edge; its spike-side half lives in `coordinator/skills/spike/SKILL.md` § The `plan⇄spike` back-edge):
    - **(a) Timing.** Fires HERE, before Branch C begins. There is no in-flight draft to park — only a *deferred plan-authoring intent*, captured in the eventual verdict record's **`gated route`** field, never a plan-body stub or parked chunk list.
    - **(b) Dispatch.** Invoke `coordinator:spike` on the specific mechanism, carrying the DEC-4 structural `trampoline: true` signal, which the Branch B entry path supplies. That signal is what makes the trampoline EM-reachable without a PM round-trip; a bare `/spike` without it is always PM-gated — do not fabricate the signal outside this entry path.
    - **(c) Resume.** On a `viable` verdict (immediately or across a session boundary), **resume re-enters Branch B — NOT a fresh Branch A triage, NOT a full seven-dimension re-run.** Only the eighth dimension flips, evidenced by the cited verdict record; carry the other seven forward as they were. Continue into Branch C.
    - **(d) `not-viable`.** Does NOT loop back into Branch B at all — per the spike's own exit routing it goes to `coordinator:shape` / PM for a mechanism reconsider, since the plan as conceived cannot proceed.
- _Verified-scope collapse — does Branch B's own verification show the ask is materially smaller than what was sized?_
  → **A TYPED LOOP-BACK to `coordinator:sizing` (the `plan⇄sizing` back-edge), not a third exit** — same shape as the eighth dimension above.
  → **Fires only when ALL hold** (a conjunction): (1) the seven-dimension checklist is all-green; (2) the eighth dimension is green; (3) verified scope is materially smaller than the ask implied — mechanically: the drafted `scope:` list is ≤2 files (count it), no new abstraction, an existing test surface already covers it, and no cross-repo contract (no scope path crosses a repo root — same check as the cross-repo-work row in Branch A).
  → **Action:** invoke `coordinator:sizing` with `--probe-signal collapse` and the Branch B findings as `--scout-evidence`.
  → **Resume — all six routes disposed:** **`plan`** → conform detent fires but resumes at **Branch C**, not Branch B (already all-green, this row's own precondition); full terminal. **`spec-dispatch`** → Branch C at S-lane weight; light terminal. **`dispatch`** → scope collapsed below plan-worthiness; abandon the pass and dispatch directly, clean by construction. **`shape`** → the re-size tripped the shape gate; leave `plan`, shape's exit chains back here. **`roadmap`/`pm-decision`** → **unreachable by construction:** the edge feeds `--probe-signal collapse`, which only moves the t-shirt down. One returning anyway means the probe signal was mis-fed — stop and re-read the Branch B evidence; a diagnosis, not a disposition.
  → **Termination.** Fires at most once per pass; no reachable outcome re-enters this row, and Branch A's trampoline adds no cycle — disjoint re-entry points. Do not add a cycle guard.
- _Fix-locus discrimination — is this the right layer to fix the bug?_
  → **Green:** the upper-layer registry/dispatch/extension site is identified by `file:line` (one level above each proposed edit site) AND you can name a concrete reason patching it is wrong (registry already gates this case; it is a closed contract; it is hot-path with unrelated callers).
  → **Red:** you cannot articulate why the upper layer is wrong, OR it is a registry/dispatch site already carrying the gate type the patch would re-implement at the call site.
  → **On red:** loop back to Tier 1–3 on the upper-layer mechanism (Tier 2 / project-RAG when indexed, Tier 3 grep otherwise). If an upper-layer gate exists, reframe around extending it.
- _File paths / framework names / helper APIs / test harness / cited counts verified against disk?_
  → Run the check inline (`ls`, `grep -c`, `head_limit:0` for enumerations). Any drift → fix substrate before drafting.
- _Plan changes existing code (replaces/edits/removes a symbol it assumes present)?_
  → **Grep the symbol-to-replace at plan-write time to confirm the fix-locus is still un-shipped.** A green `docs-checker` verifies the *external API claim*; it does not verify that the in-repo symbol still exists in the assumed shape — a concurrent session may already have shipped the fix, renamed it, or removed it. Absent or already-changed → re-investigate and amend substrate. This is fix-locus *liveness*, distinct from *discrimination* (which layer) above, and distinct from the path row before it: that confirms the FILE exists; this confirms the SYMBOL inside still has the shape you plan to replace.
- _Plan reverses a prior teardown / re-introduces a removed pattern?_
  → Run the negative-search procedure: grep `state/lessons/` and the wiki for the central nouns plus prohibition vocabulary.
- _Native-code (C++/UE/Rust) plan?_ → Add 2–3 in-tree `file:line` citations to the dispatch brief.
- _Plan renumbers or rekeys a published API (constants, error codes, route numbers, step indices)?_
  → The reverse-reference scan must grep ≥3 shapes per value: bare number, quoted (`'N'`/`"N"`), fmt-string (`{n}`/`%d`), and comment form (`# step N`). Bare-number grep misses string citations; string grep misses comment form. Cross-references rot silently when only the canonical declaration site is found.
- _Plan adds a new dispatch / handler / op / job to a surface with registered entries?_
  → Check for a table/registry pattern (`UE_REGISTER_*`, `register_action`, plugin auto-registration). If one exists the plan MUST use it; a parallel `else if`/`switch`/hand-rolled lookup re-introduces dispatch-fragility bugs.
- _Plan ports / mirrors / adapts a feature from a peer repo?_
  → Before authoring a parallel addon surface mirroring the peer's shape, check whether the host has its own registration seam / hookspec / extension point. **Default to host-registration over parallel-surface** — a parallel front-end duplicates routing, splits maintenance, and turns every host upgrade into a re-port. If a seam exists the plan MUST attach via it; a parallel surface requires a documented reason (seam closed, or fundamentally wrong shape for the port).

When drafting a plan body on either lane, cutting an item from the complete problem set is an
untrusted-gate obligation, never composition machinery the EM discharges alone: any item cut MUST
become a spine row with a closed disposition (spun off, backlogged, ruled out) and a real
disposition detail — never a silent drop, never a row the author approves themselves. The cut is
not authorized until the PM approves the grouping it lands in. Enforcement lives at write time,
in the row's own closure gate, not in a checker's after-the-fact report.

- _Spine rows and the prime exit criterion testable + time framed for agents, not humans?_
  → Each spine row and the prime exit criterion's falsifier leg is a binary pass/fail check. Agent-scoped time annotations are fine ("this dispatch runs ~90s"); reject human-sprint framing ("two-week effort", "Q3 milestone").

- _A "we'll add X later" / scope-trim / YAGNI argument is in the draft?_ → **Always surface to PM**, never EM-unilateral. YAGNI is a product call.
- _A "soon = now" deferral candidate?_ (an item deferred because the EM thinks it lower-priority than the headline work)
  → Either ship it in this plan or get explicit PM disposition — and disposition means **both** the case against shipping now (`case_against`) **and** a non-vacuous `disposition_detail`, plus a recommendation stating your confidence. No silent deferrals. _Full both-sides form: `${CLAUDE_PLUGIN_ROOT}/docs/wiki/writing-plans.md`._

- _Each chunk has an identified test surface?_ — a set-containment check: the named test paths must be a subset of that chunk's own scope paths (Tier T, below). Verifiable per chunk without leaving the file: read the chunk's `scope:`/file list and confirm every named test path is in it.
  → Name the test per chunk, or document why none. Where another chunk's test exercises this chunk's output, name which chunk authors the file; an implementation chunk does not author its own tests unless the brief says so. **The named surface MUST be Tier T — path-scoped to the files that chunk authors or touches.** Naming the repo's fast tier or full suite is malformed at plan-write time for the same reason it is at dispatch time: it defers the identical deny until after the plan is reviewed and ratified on a row that was never enforceable. Genuinely global or cadence-scoped verification (Tier F/U) is **EM-owned at the wave boundary or cadence gate** — never a chunk's test surface, never a plan deliverable. _Tier definitions: `coordinator/skills/validate/SKILL.md`; the EM-owned mechanism: `execute-plan/SKILL.md`._
- _Plan will hand off to an executor agent?_ (sub-conditions additive)
  - **Always:** apply the standard hard-constraints block (explicit file scope, no commits, no out-of-scope edits, no fallback escape hatches) — confirm via `gates.composition.hard_constraints_block` (`present`).
  - _Parallel executors with file-overlap risk?_ → **Read `gates.composition.chunk_overlap`** (`pairs[]`).
  - _Stub spawns sub-agents (orchestrator-shaped)?_ → Mark it read-only-planner; sub-task dispatch happens at EM level, never nested.
  - _Touches concurrency-shared state (shared appends across machines/sessions, shared index or lock)?_ → Prefer per-machine paths over atomic-merge logic.

- _A single chunk would hand ONE executor multiple independent deliverables?_ (N modules or disjoint files whose **write** targets do not overlap — check it as a pairwise intersection over each deliverable's own write-target file list; an empty intersection between any two is the fan-out signal)
  → **Decompose into N chunks at plan-write time — fan-out chunking is a plan-author obligation, not an execution-time afterthought.** Only two justifications keep them together: (a) genuine write-overlap — and even then it is a *sequence* of small dispatches, not one fat executor — or (b) an unpinnable shared interface. **A shared read-only source and a pinned import contract are NOT serialization reasons** — both are reads, and only WRITE-overlap gates parallelism; a plan collapsing N disjoint-write deliverables under "file-overlap" has mistaken read-overlap for write-overlap. Size each chunk to ~5–10 min on one coherent surface, 15 min hard ceiling. **`writes:` is REQUIRED on every non-deferred row** (`deferred: true` rows are exempt — harvest candidates, never dispatch candidates): it is the pairwise-intersection input above, written down instead of discarded. **`depends_on:` (array of `{chunk, gate_kind}`) is required wherever the author imposes a gate the file-write graph cannot compute** — never for write-overlap, which the wave-builder derives on its own; consult `plan-tasks.schema.json`'s `gate_kind` NEGATIVE SPEC before writing one, three of the six discriminator gate kinds are deliberately unwritable there. These arrays make wave-map derivation a pure function of the spine; `dispatch.emit` cannot fire on an undeclared one. _Late-correction surface: [`skills/execute-plan/SKILL.md`](../execute-plan/SKILL.md) Phase 1.6 wave-map authoring; the ledger schema lives only there._
- **Read `gates.composition.path_rename_or_move`** (`fires`/`paths[]`, any `git mv`, rename, relocation, or directory restructure — **the trigger is path movement, not `scope_mode`**).
  → **Schedule a post-execution `doc-link-checker` dispatch as the closeout chunk, subject to the precondition below.** Renames orphan inbound doc links (wiki cross-refs, README entries, spec backlinks, `@`-imports) the renaming executor never sees.
  → **Precondition, checkable inline:** grep the repo for inbound links to each moved path (`grep -rn "<old-path>" --include=*.md`), then diff that hit set against what `validate-references` already covers. Schedule the closeout chunk ONLY when the residual is non-empty — **relative inbound markdown links not already covered by `validate-references`** OR **public-URL inbound links**. **Skip, and note why, when** inbound links are private-repo absolute self-URLs (the worker gets 401/404 — no signal) or are already covered by `run-all-checks`. The `#anchor` check it uniquely adds only works post-merge by an authed human — note it for one-click post-merge sanity rather than reflex-dispatching the worker into abstention.
  → **When the gate fires and the plan hands the move to an executor**, the chunk brief MUST carry the rename procedure (point at `coordinator/agents/executor.md` § Moving or Renaming Files — plain `mv`, not `git mv`; report both path sets to the EM), and the chunk's `writes:` MUST enumerate BOTH sides of the move — old paths and new paths. `writes:` takes plain strings, no glob syntax (`coordinator/schemas/plan-tasks.schema.json:107-110`); a directory-shaped move has to be enumerated path-by-path, which is the accepted cost, not a defect to route around.

- _Cross-plan conflict scan run? (mandatory before dispatch)_
  → **Read `gates.composition.cross_plan_conflict`** (`hits[]`, each `{plan_path, overlapping_paths[]}`). Fold findings into `## Cross-plan coordination`: each sibling plan touched, what assumption it carries, and whether this plan amends / defers to / supersedes it. No hits → write the section anyway with `scanned — no overlapping file scope or seam citations`. A missing section is the failure mode.

- _Plan contains a chunk authoring a handoff, spinoff, or workstream-complete artifact?_ — grep the drafted chunk headings/bodies for authoring verbs against those three artifact names; any hit fires this row.
  → **Reject the chunk.** These are PM-gated session-continuity artifacts, not plan deliverables. "Chunk N: write a spinoff" launders the PM gate through plan approval — by execution time it reads as a checklist item and the spinoff's Step 0 gate never fires. Correct primitives instead: commit-and-stop or `/workday-complete` for a wrap-up chunk; PM-as-relay or `cross-repo-memo` for a cross-repo one. Genuine cross-EM coordination makes the chunk "surface cross-repo brief to PM".
- _Plan brief contains code blocks the executor will consume?_ — a fenced-block lint: every fenced block in the chunk body must carry a `TEMPLATE`/`VERBATIM` marker comment directly above it; grep the chunk for ` ``` ` and confirm each has one.
  → Mark every fenced block `TEMPLATE` (executor adapts paths/values) or `VERBATIM` (copies as-is), via a fenced comment above it. Unmarked pseudocode-shaped bash gets faithfully transcribed into broken shell.

→ **Do not ask the PM whether to proceed to whichever terminal the route selected.** Pausing to ask "want me to invoke review now?" or "want me to dispatch now?" is a doctrine violation — the answer is always yes for the selected terminal.

Plan review altitude is binary — there is no Sonnet-tier plan reviewer, and the `spec-dispatch`
lane skips review entirely. Its compensating control is not `/workstream-complete` or `/handoff`
but the light terminal's own mandatory scoped `code-reviewer` pass (§ `spec-dispatch` row),
binding on every exit.

The `plan`-route terminal runs a five-step pipeline (substrate verification, four-lens
composition, three pre-flights, named Opus reviewer, review-integrator); the `spec-dispatch`
lane's own pipeline shape is the S lane's only statement of what it runs in place of that:
**the light terminal is a deliberately shortened pipeline** — (1) and a reduced (2) still run;
(3)–(5) are replaced by its cross-plan-scan-then-dispatch sequence.

## Branch D — Executor BLOCKED on substrate drift

_Condition: a dispatched executor returns BLOCKED citing substrate differing from what the plan asserted (path moved, helper renamed, framework changed, contract field absent, schema column missing)._

- _Default: amend the plan or write a successor; do NOT silently expand executor scope to absorb the drift._
  → Substrate drift is plan-substrate failure, not executor failure. Re-invoke `coordinator:plan` to amend (small drift, same workstream) or compose a successor (larger drift or shape change). Re-run the pipeline on the amended body from substrate verification, not from "we already reviewed the parent" — **that invariant is shared; which chain discharges it is selected by the lane.** `plan`: prior-art-checker → named Opus persona → review-integrator. `spec-dispatch`: re-run **Branch B** over the drifted paths, amend the light body, re-fire the light terminal (cross-plan scan, then dispatch); its mandatory scoped `code-reviewer` pass over the re-dispatched diff still binds. **Do not hand the S lane the full lane's chain** — it never ran it, and importing it re-adds the gate the lane exists to remove. Silently expanding scope to make the BLOCKED go away bypasses the doctrinal lenses, the prior-art check, and the reviewer pass.
- _Product-risk findings during BLOCKED inspection?_
  → Even under `/autonomous`, surface them via `AskUserQuestion` before amending. Autonomous mode suppresses handoff nudges, not product judgment. A BLOCKED revealing a privacy implication, a permission-default change, or an external contract shift is exactly what the Ask-the-PM doctrine covers.

## Branch E — Mid-plan friction

_Condition: drafting is in progress and something is going sideways._

- _Repeating actions / oscillating / stalling?_ — three literal counts over the transcript, each independently checkable: same action **3+ times** with the same result; **4+ actions** alternating between two approaches; **3+ paragraphs** of analysis with no tool call.
  → Recognize the pattern, then stop, name it, and switch to a fundamentally different approach (report BLOCKED if none exists).
- _Bug suspected mid-execution needing root-cause work?_ → Invoke `coordinator:systematic-debugging`.
