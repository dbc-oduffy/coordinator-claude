---
title: Review integration doctrine
created: 2026-05-17
type: doctrine
related:
  - plugins/coordinator/docs/wiki/prior-art-checker.md
  - plugins/coordinator/docs/wiki/docs-checker-pre-review.md
---

# Review Integration Doctrine

How to receive and apply reviewer findings correctly — the failure modes that appear at integration time rather than review time.

## The integrator is a second checker, not a cheaper typist — so dispatching it is mandatory

The integrator's value is not that it is cheaper than an EM's headspace. It is **a fresh agent that re-checks each finding against HEAD before applying it.** A review is a snapshot; by the time it lands a finding may be wrong, stale (a concurrent executor moved the schema), or mis-scoped (§ Re-verify reviewer premises). The EM who types the change instead applies the reviewer's claim at face value, and any defect in it lands silently.

So the cost framing misleads — "one line, dispatching an agent is wasteful" discards exactly the verification the dispatch exists to provide. **Finding size is not a license to self-author**; the smaller a finding looks, the cheaper the pass and the easier the skip.

Mechanics: dispatch `coordinator:review-integrator` (mode `auto`), read the returned escalation list, spot-check the diff. The EM routes and verifies, never authors. → `coordinator/snippets/em-operating-doctrine.md` § How to Decide.

### A reviewer's own disposition is a recommendation, not a closure

The sibling failure is skipping the dispatch entirely: a slice returns `verdict: OK` with findings the reviewer already self-dispositioned — *"informational, no fix needed"* — and the EM reads that as closure. **Every finding folds, nits included; the sole exemption is believing the finding is wrong, said out loud and defended.** An `OK` slice with findings is still a slice with findings.

`verified-no-action` is the legitimate bucket for this outcome, but it is reachable **only through an integrator that independently re-read the target**. Its definition presumes a dispatch already happened, so it cannot bind an EM who never dispatches.

**Worse than hand-authoring, because it is invisible.** Hand-authoring leaves a diff. A skipped integrator leaves no sidecar disposition block, no `/distill` Phase-2.5 exclusion, no artifact — the slice simply looks clean. Every other corner-cut here leaves a trace; this one needs a named tell instead.

**Tells.** *"nothing to apply"*, *"no integrator warranted for this slice"*, *"the reviewer already dispositioned it."* Same family as `skills/pickup/SKILL.md`'s stealth-skip tells. Reported upward as a considered choice it reads as rigour, which is the defer/hedge reflex wearing rigour's clothes. Tripwire: `REVIEWER-SELF-DISPOSITION-IS-NOT-CLOSURE`.

Named from a live five-slice review, reported by a sibling plane's EM, where the skip produced the right answer by luck — the re-dispatched integrator returned `verified-no-action` with cited evidence, matching the EM's guess. A skipped step that happens to be right is the case doctrine must catch; the wrong-answer case reports itself.

## Integrator unavailable — the named exit

The mandatory dispatch assumes the integrator can be dispatched. When it dies on an API or quota
limit, the hand-edit guard (`block_em_hand_edit_pending_review_integration`) still states an
absolute, leaving an EM with a break-class finding choosing between a silent override and a
knowingly-shipped defect. Neither. Order of resort:

1. **Re-dispatch once.** Most deaths are transient; the second failure is the signal.
2. **Not break-class → leave it unapplied with a durable home** — queue, successor handoff, open
   baton — and say in the commit that findings are outstanding.
3. **Break-class → hand-apply, discharging the integrator's function yourself.** That function is
   the fresh re-check against disk, not the typing: read the cited file at `HEAD`, confirm the
   premise still holds, apply, run the tests covering that surface.

**Record the deviation in the commit message** — finding, sidecar, why the integrator was
unavailable, what you ran. Unrecorded, it is indistinguishable from the violation it bounds.

"Unavailable" means dispatch failure on infrastructure — never slow, inconvenient, or one-line
(§ Finding size is not a license to self-author).

## Re-verify reviewer premises against artifacts landing after review

Schemas, function signatures, and file layouts can change between when a reviewer writes their findings and when the integrator applies them. A reviewer that writes "confirm field X exists before shipping" may be referencing a schema that has since been updated by a concurrent executor. Integrating the finding blindly adds a redundant check or, worse, rewrites something that does not need rewriting anymore.

Integrator discipline: before accepting any finding that contains "TBD," "confirm later," "verify before applying," or a premise about a schema/path/API, read the current state of the referenced artifact. If the premise fails to hold, drop the finding (not the whole review — just that finding) and note the drop in the integrator's report.

This is structural at concurrent-EM cadence. On shared branches, an executor may have landed changes while the review was in flight. The reviewer's frame is a snapshot; the integrator works against HEAD.

**Sidecar `<file>.md § <section>` citations need a two-part verification before integrating.** Prior-art-checker, docs-checker, and plan-coverage-checker sidecars routinely cite a wiki by name and section (`<file>.md § <section>`). Before acting on such a citation, verify BOTH that (a) the cited path exists (check `archive/` for relocated wikis — spec backlinks outlive their cited spec) AND (b) the section's scope actually maps to the plan's deliverable. A citation can resolve to a real file and a real section that nonetheless addresses a different concern than the sidecar implies — integrating against it imports a mismatched constraint. Path-exists is necessary but not sufficient; section-scope-maps-to-deliverable is the second leg.

**Worked variant: post-review schema-pinning.** A the Staff Engineer finding directed a renamed CLI flag (`--foo` → `--bar`); the schema then landed with `additionalProperties: false` pinning the original JSON key. Applying the rename verbatim would have broken the schema constraint that landed after the review. The resolution: keep the JSON key canonical to the schema, localize the rename to the user-facing CLI flag and banner text. Pattern: any reviewer finding that prescribes a rename must be re-verified against schemas, fixtures, and external-API contracts that may have landed since the review — the rename's scope is bounded by what landed after, not by the reviewer's frame at the time.

## Adopt-with-receipts — document-the-tradeoff is a valid integrator outcome

A reviewer (the canonical case is the Staff Engineer) flagging a bounded UX or design cost does not always mandate a restructure. **"Document the tradeoff, don't restructure" is a legitimate integrator disposition for bounded costs** — and it is not the same as dismissing the finding. The adopt-with-receipts shape: (1) name the cost explicitly in the artifact, (2) name the larger restructure that would eliminate it, (3) record PM-acceptance of the bounded cost, (4) name the revisit trigger (the condition under which the cost stops being acceptable and the restructure becomes warranted).

This sits between "fold silently" (§ Apply tradeoff-free fixes silently) and "escalate as ASK." The finding is real and accepted; the resolution is to carry the cost with a documented escape hatch rather than pay the restructure now. The receipts (named cost + named alternative + PM-acceptance + revisit trigger) are what distinguish adopt-with-receipts from appetite-based "not now / follow-up" hedging — the four elements make the deferral architectural, not an excuse.

## Apply tradeoff-free fixes silently; surface tradeoffs to PM

Correctness fixes (wrong API name, missing import, factual error, precedence) fold into the artifact via the integrator without EM narration or PM escalation. These have no tradeoff; the finding is simply correct.

Tradeoffs (cost vs. value, scope expansion, architectural direction, visible behavior change) go to the PM before integrating. The integrator writes an escalation list; the EM presents it. The PM decides.

The failure mode this prevents: EM treating every review finding as a question requiring PM sign-off, which bogs down integration and inverts the relationship between mechanical correctness and product judgment.

## A reviewer recommendation is not authority to deviate from what shipped

Spec authority is the PM's, not a reviewer's. A mid-workstream edit that honors a reviewer *recommendation* against already-shipped code can be reverted by the PM — the reviewer exposed a consideration, but "what shipped" is the PM's ratified surface until the PM says otherwise. Treat a reviewer's "you should restructure X" against landed code as a finding to route (fold-silently only if tradeoff-free-correct; otherwise escalate as ASK per § Apply tradeoff-free fixes silently), never as standing license to rewrite the shipped shape.

**A `system-reminder` reporting a file the user or a linter just modified is ground-truth signal — stop additive cleanup and roll back to match.** When the harness injects a `<system-reminder>` noting that the user (or a formatter/linter running on save) has just changed a file mid-session, that is the strongest available signal of the *desired* shape — stronger than any in-flight reviewer recommendation. The correct response is to **stop additive cleanup on that surface and roll back partial sibling edits to match** the reported state, not to continue applying the reviewer's frame over the top of what the user just chose. The user's live edit outranks the reviewer's snapshot.

## Verify a code-reviewer's absence claims against disk before honoring a BLOCKED built on them

`coordinator:code-reviewer` runs with Bash confined to the sidecar-scaffold command — it cannot run `find`/`git`/`ls` to enumerate the tree. Its "no tests exist" / "file absent" findings are guesses at plausible paths, and false-positive the moment the real file has a different name. A doctor-elevation slice was once returned BLOCKED partly on "no unit tests found" when the covering test file existed and passed. Independently confirm any absence-based finding on disk before treating a BLOCKED verdict built on it as real; if the absence claim doesn't hold, dismiss-with-rationale in the integrator brief rather than propagating the BLOCKED. Same discriminator as `docs/wiki/scout-and-dispatch-discipline.md`'s confined-dispatch tell — a reviewer with no enumeration tool sincerely reports an absence it has no instrument to see.

## An observable-outcome acceptance criterion is never satisfied by a tested pure function alone

An AC phrased as an observable outcome — "the wire carries X," "the endpoint returns Y," "the report includes Z" — is satisfied only by a test that drives the real production entry point and would fail if the call site were deleted. A fully-tested projection/builder function with zero non-test callers is the tell: the pydantic carrier can be correct, the validation gate can be correct, and every unit test can be green, while the value it builds is never wired into the thing that ships. This recurs because tests that live in isolation from the pipeline are structurally blind to the gap, and "unit-green plus an import smoke-check" cannot distinguish "built" from "reachable." What catches it is chain-terminal review tracing the actual production construction site rather than reading the diff in isolation. When a chunk's `scope:` and its prose disagree about which file owns the wiring, the scope is wrong, not the prose — a well-scoped executor cannot deliver an AC whose call site its scope excludes. Wave-map check: any new value that must reach an external surface needs one chunk whose write-surface includes the production call site, and one test verified (not assumed) to fail on reverting the wiring.

## Ordering domain-expert-then-generalist review can delete a load-bearing assertion the correctness pass alone would have kept

Close ceremonies run the overengineering/proportionality pass before the correctness pass deliberately — reviewing a shape about to be condemned wastes the correctness reviewer's attention. But the ordering has a blind seam: a proportionality cut can remove an assertion that reads as doing no work in isolation while actually carrying the only call into the code under test, and the correctness pass never sees the pre-cut version to notice what the removed assertion was covering. Neither reviewer is wrong individually — proportionality cannot see which assertion carries coverage, correctness never saw the version before the cut. Only the dispatching EM stands in both passes; that seam is the EM's to watch, not either reviewer's.

## Chain-end review and plan-time review catch different defect classes

Plan-time review (the Staff Engineer on the stub, prior-art-checker on the plan) checks substrate and approach: are the paths real, is the schema correct, does this contradict prior doctrine, is the architecture coherent? These checks work against the plan artifact before any code is written.

Chain-end review (workstream-complete `code-reviewer` or `code-reviewer`+the Staff Engineer on the landed diff) catches a different class: boundary-relabeling bugs (where a function's name or contract shifted during implementation), integration-seam mismatches (where two independently-implemented chunks don't compose), and structural drift from the plan. These defects are invisible at plan time because they emerge from the gap between intent and implementation.

Running only plan-time review and skipping chain-end review is not "sufficient review" — it is review that structurally cannot see the defect class that most commonly survives execution.

→ `coordinator/skills/review/SKILL.md` § A.3 — Sequencing ("exceptions: merge-gate, workstream-complete slices") for the chain-end review procedure.

## Single-agent math and precedence findings need verification

A single reviewer flagging a logic error, arithmetic mistake, or operator-precedence bug requires verification before integration — do not apply single-agent math/precedence findings silently. The false-positive rate on single-agent findings of this class is high enough that acting on them without verification introduces regressions.

The confidence threshold is convergence: two or more independent agents flagging the same issue from different entry points. One agent with high-confidence framing is not the same as convergence.

→ § Convergence as Confidence (below)
→ § P0/P1 Verification Gate (below)

## Convergence as Confidence

When ≥2 independent agents flag the same issue from different entry points, treat as high-confidence and fix. Single-agent findings — especially math/logic/precedence — require verification first (threshold is independence + distinct entry points, not raw count). Reviewer divergence → read source, don't tiebreak.

## P0/P1 Verification Gate

P0/P1 claims from sweep agents have poor track records. Before acting, EM or a verifier reads the cited code and confirms against current source — not the agent's paraphrase. High-confidence framing inverts the hit rate.

## Pre-flight sidecars do not require integration before the first reviewer

The sequential-review HARD RULE ("integrate Reviewer 1 before Reviewer 2") applies to **named persona reviewers** — the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering. It does NOT apply between a Sonnet pre-flight (docs-checker, prior-art-checker, external-pattern-checker) and the first named reviewer.

The reasoning is structural, not a convenience exception. The named reviewer is exactly the agent whose Opus-tier architectural judgment we want shaping direction-of-correction on prior-art Conflicts. Front-loading EM disposition before the reviewer sees the plan inverts the leverage: it forces the EM to make architectural calls the reviewer was dispatched to make, and it freezes prior art into "plan must yield" rather than asking which surface is the more current artifact. The post-reviewer integrator pass is where prior-art-side edits land — across the plan, the wiki, or both — per the reviewer's recommendation and the EM's direction call.

What this means in practice:

- **docs-checker** AUTO-FIX corrections land inline per its own contract (`docs/wiki/docs-checker-pre-review.md`). No integrator pass between docs-checker and the reviewer; the sidecar travels with the artifact for the reviewer's awareness.
- **prior-art-checker** sidecar travels unintegrated. The reviewer sees `Conflicts` / `Compatible-but-relevant` / `Silent` buckets and recommends a direction-of-correction per Conflict. EM pre-disposition in the dispatch brief is optional, reserved for cases where the direction is mechanically obvious (e.g., a Conflict against load-bearing doctrine that's already settled). When the EM does pre-dispose and the reviewer disagrees, the integrator escalates as ASK — never silently applies either direction. → `agents/review-integrator.md § Prior-Art Conflict Resolution`.
- **external-pattern-checker** sidecar folds into the reviewer's dispatch prompt as ad-hoc context (per its own consumption contract), not as an integration step.

What still requires integration between artifacts: every pass between two named persona reviewers. If the Staff Engineer runs first and recommends changes, the integrator lands them before the Game Dev Reviewer sees the artifact. That's the rule the HARD RULE was written to enforce, and it's unaffected.

→ `coordinator/skills/review/SKILL.md` § A.3 — Sequencing ("Two Sonnet pre-flights gate before an Opus reviewer") for the pre-flight carve-out  
→ `docs/wiki/prior-art-checker.md § Bidirectional resolution`  
→ `agents/review-integrator.md § Prior-Art Conflict Resolution`

## Re-run mechanical pre-flights after material plan amendments

Pre-flights (path scout, prior-art-checker, docs-checker) are point-in-time. A material plan amendment — adding a new component, changing a schema decision, reordering chunks — creates a new claim surface that the original pre-flight did not cover. Stale pre-flight findings at integration cause the integrator to accept or reject findings against a plan that has since diverged from what was reviewed.

The rule: after any material amendment, re-run the relevant pre-flights before dispatching the next reviewer. "Material" means any change that alters paths, APIs, schema fields, or architectural approach. Prose clarifications and wording changes do not require re-run.

→ `coordinator/docs/wiki/pre-dispatch-verification.md` ("Re-run mechanical pre-flights after material plan amendments")  
→ `docs/wiki/prior-art-checker.md` for prior-art-checker procedure  
→ `docs/wiki/docs-checker-pre-review.md` for docs-checker procedure

## Reviewer self-persists; EM reads the returned path — no transcription

`coordinator:code-reviewer` self-persists by default. There is no inline-return mode and no `-selfpersist`
variant — there is one reviewer, and it always writes its findings to disk.

**How it works.** The reviewer writes to its pre-provisioned sidecar —
`state/subagent-share/<session>/<provision_key>.md` — pre-provisioned by the dispatching EM in the
common case (the engine repo's `provision_report` engine creates it at spawn), or self-scaffolded into that
same home via `coordinator-doc-new --type review-findings` (the Bash allowlist permits this one
command) only when no path arrived pre-provisioned. Either way, the reviewer edits the
`<!-- FINDINGS -->` sentinel with its findings and returns only a pointer+verdict line:

```
DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N> | executed: <yes|no>
```

No EM pre-scaffold. No `cs_write_review_claim` call. No claim-marker ceremony. No EM transcription.
The EM reads the returned path and passes it to `coordinator:review-integrator`.

**Personas (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering)** are dual-use (advisory OR sidecar-review).
When dispatched for a review that feeds an integrator, the invoking skill injects the
pre-provisioned `state/subagent-share/<session>/<provision_key>.md` path into the dispatch brief —
the engine repo's `provision_report` engine has already created the sidecar at spawn — and the persona
writes its findings into that path and returns the pointer line. No sentinel-append self-scaffold,
no EM pre-scaffold, no claim marker. Same zero-ceremony pattern as `code-reviewer`. The
review-integrator intake fails loud (BLOCKED) if the returned sidecar is a trivial/unfilled
scaffold — the intake fill-guard, not a per-dispatch-site check.

**If a reviewer returns inline despite this contract**, it is a dispatch failure — re-dispatch
`coordinator:code-reviewer`. Do NOT transcribe inline output manually; the transcription path is
what the self-persist contract exists to eliminate.

**Invariant — the sidecar-write belongs to the review-PRODUCING agent, not the consumer, and this
covers ad-hoc reviewers too.** Any agent that produces review findings — the named reviewers
(`code-reviewer`, personas) AND an ad-hoc reviewer an EM spins up outside them (most commonly a
`Verify`/review phase authored *inside a background Workflow* as a bare `agent(prompt, {schema})`
call) — MUST write its findings to its `state/subagent-share/<session>/<provision_key>.md` sidecar and return ONLY a pointer
(path + verdict + count). **Inline findings are never a valid handoff format to a downstream
consumer.** The EM's job is to pass the pointer to `review-integrator`, never to relay findings inline;
the integrator's intake hard-stop (`agents/review-integrator.md` § Intake precondition — hard stop)
BLOCKS on inline input unconditionally and does not soft-proceed. The trap is structural, not an EM
slip: a Workflow `schema:` return IS an inline-return mechanism — correct for an *executor* stage
(structured data the EM consumes), wrong for a *review* stage (findings that must land on disk). The
workflow-authoring carve-out that closes the pit lives in `workflow-orchestration.md` § Notes on the
shape (review/verify stages dispatch `agentType: 'coordinator:code-reviewer'`, or instruct a bare
`agent()` to self-persist and return the path — never a findings array).

**Empirical scale.** A 36-slice partitioned close dispatched nine review-integrators with findings rendered inline into the prompt; five hard-stopped on exactly this intake precondition, two of them sitting on real defects (one a sixth un-updated mirror of an enum). The refusal was correct and the dispatch was wrong — an integrator handed prose cannot tell a reviewer's verdict from its dispatcher's paraphrase, which is the whole reason the sidecar exists. The tell is an integrator returning `applied=[]` with a long note where a short one belongs: read the note, do not re-dispatch.

→ `agents/code-reviewer.md` — the one self-persisting reviewer
→ `workflow-orchestration.md` § Notes on the shape — the workflow review-stage carve-out

### Runtime-only findings need an explicit pass-through channel — disk-observing writers cannot reconstruct runtime facts

A reviewer finding of the shape *"record runtime-only X distinctly"* (a value observed only at execution time — a live error string, a timing-dependent state, an actual emitted token, an environment-resolved path) has no on-disk source for the integrator to read. The `review-integrator` is a disk-observing writer: it reads the cited code and the sidecar, then edits the artifact. It physically cannot reconstruct a runtime fact that exists only in the reviewer's execution context — if that fact is not handed across explicitly, it is lost in the integration pass.

**Rule:** when a reviewer surfaces a runtime-observed fact that must survive into the artifact, the EM captures the verbatim runtime value into the persisted sidecar (same persistence-layer discipline as inline reviewer output, above) so the integrator has an on-disk source. Do not assume the integrator will re-derive it — it observes disk, not the reviewer's runtime. The companion wiring (an explicit runtime-fact pass-through field in the integrator dispatch brief) lands in `agents/review-integrator.md` and `coordinator:review` Branch B.

## Brightline PARTITION-MANDATORY over-counts memo/doc-only commits — partition the CODE surface

The `≥5-commits` brightline (a diff-shape gate deciding whether a review must be partitioned) fires on raw commit count, but the partition decision is about **reviewable code surface**, not commit count. When the brightline trips, check how many of those commits actually *touch code*: if the reviewable surface is one coherent code slice — several of the commits being memo/doc/lesson-only — then a **single `code-reviewer` is correct**, and the right move is to `git show --stat` the code commits, confirm the coherent slice, and **record the disposition** ("gate over-counted N non-code commits; reviewable surface is one slice") rather than spawning empty partition reviewers over doc commits with nothing to review.

**`--session-id` scoping fixes cross-EM noise but NOT the doc-vs-code mix within one session.** The session-scope flag removes *other* EMs' commits from the count; it does nothing about *your own* session's memo + doc + lesson commits inflating the code-commit count past the brightline. That mix is disposed of by the code-surface check above, at disposition time, not by the gate.

## Integrator dispatches are 1:1 with reviewer slices

When a code review is partitioned across N parallel `code-reviewer` slices (per `skills/workstream-complete/SKILL.md` § Partitioning large surfaces), the integrator pass is partitioned the same way: **one `coordinator:review-integrator` per slice, dispatched in parallel, each scoped to the same slice paths as its source reviewer.** Not a single integrator over the union of N findings against N disjoint file sets.

**Why structural.** Reviewers are sliced because one Sonnet can't fit the whole surface in context. The same context-fit constraint binds the integrator — it reads the cited code, locates each finding's site, applies the fix, and adds annotations; the work is bounded by the union of (findings × cited paths), exactly the dimension the slicing controlled for. A union-integrator inherits N reviewers' merged scope and re-creates the overflow the slicing was designed to avoid. The dispatch-decomposition discipline that governs executor waves (`docs/wiki/dispatching-parallel-agents.md`) applies here for the same reason — small-remit-and-many beats large-remit-and-one when the surface was already partitioned upstream.

**Why not unification.** "One integrator over the union" looks like it preserves a coherent view of the diff, but the reviewers already partitioned that view — by package, concern, or directory cluster — into slices with no file overlap. Re-unifying at the integrator stage does not restore lost coherence (none was lost; slices were chosen to be disjoint); it just re-imports the context-pressure failure mode. If two slices DO overlap on a file (rare, by construction), the EM resolves that at the partition step, not by collapsing the integrator pass.

**Mechanics.**

1. Each `coordinator:code-reviewer` dispatch writes its findings to its own per-slice sidecar at `state/subagent-share/<session>/<provision_key>.md` — pre-provisioned by the dispatching EM in the common case, self-scaffolded into that same home otherwise. No EM pre-scaffold in the common case; no claim marker either way. The reviewer returns a pointer+verdict line: `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N> | executed: <yes|no>`. The EM reads the returned path. The sidecar must exist on disk before the integrator is dispatched (the reviewer's self-persist guarantees this on a clean return). The self-persist flow is an explicit step in `skills/workstream-complete/SKILL.md` § Partitioning (step 2), and the integrator's hard-stop is in `agents/review-integrator.md` § Intake precondition — hard stop.
2. EM dispatches N integrators in parallel, each pointing at one slice's sidecar + the same slice's artifact paths.
3. Each integrator writes its own disposition block to its own sidecar (§ Sidecar Disposition Annotation) and its own completion report.
4. EM reads the N reports in aggregate, applies the standard tradeoff-vs-correctness routing (§ Apply tradeoff-free fixes silently; surface tradeoffs to PM, above), and stages the union of integrator-edited files in the workstream-complete commit (`skills/workstream-complete/SKILL.md` Step 3 staging discipline already handles fan-in).

**Tripwire.** A single `coordinator:review-integrator` dispatch handed N reviewers' findings against N disjoint slice paths is a doctrine violation — the integrator agent prompt rejects this shape as a broken intake (`agents/review-integrator.md` § Intake precondition, "One reviewer slice per integrator dispatch"). The recovery is to re-dispatch 1:1.

**Scope.** This rule binds workstream-complete partitioned reviews. The weekly merge-gate (`coordinator:parallel-code-review`) uses a different downstream — a no-rewrite synthesizer, not the integrator — so the 1:1 rule does not apply there; the synthesizer's input is multi-slice by design and never edits files.

## Cross-session review convergence routes through the integrator, not SUPERSEDED prose

**Cross-session review outputs flow through the review-integrator on a single canonical artifact — "SUPERSEDED" prose is not review provenance.**
**Why:** When concurrent EM sessions independently produce review outputs against parallel artifacts, marking the loser SUPERSEDED with a "findings carry forward" assertion is structurally unverifiable — Session B's enrichment may never have seen Session A's reviewer pass.
**How to apply:** at convergence time, the EM that supersedes MUST dispatch the review-integrator with the loser's findings as input and the winner artifact as target — same as a normal integrator pass. Review provenance is not transitive across artifact splits; an asserted carry-forward is just prose. Cross-session reviews converge on one canonical artifact — this rule is what makes that convergence enforceable rather than aspirational.

## Narrative-Shape Review — Frame-Drift Lens Separate from Code-Review

Narrative-shape review is a separate lens from code-review — frame-drift ships clean diffs. Code-review operates at the level of individual hunks; it cannot catch when the entire framing of a document (entry-point prose, stated purpose, scope claim) drifts from the intended narrative. Author an entry-point prose check at producer time as part of the producer skill. Apply: for any document with a stated purpose (skill, wiki, plan), add a "narrative-shape check" step in the producer: does the opening paragraph still match what the document actually does?

## review-integrator does not commit — full stop

**The `review-integrator` agent never creates git commits, in any category — doctrine files, integrated plans, or anything else.** The agent's § Commit Discipline is a single non-committing rule with no doctrine/plan exception, mirroring the executor's "subagents apply, EM commits" model. A brief needs no phrasing around expected commit shape to be honored — "write and report back" is the agent's only behavior, so there is nothing for brief-shape to fight.

## A write-tool reviewer may self-integrate against a read-only brief — diff the artifact before trusting findings

A reviewer whose agent-type carries `Edit`/`Write` (the canonical case is `coordinator:staff-eng` / the Staff Engineer, but any persona reviewer qualifies) can **ignore an explicit read-only dispatch and integrate its own findings into the artifact** — leaving an internally-inconsistent draft where some findings are applied, some are only described, and the two disagree. The read-only instruction in the brief is prose; the write tools are real, and under perceived helpfulness pressure the tools win.

**Rule:** on every reviewer return whose agent-type carries write tools, `git diff` the reviewed artifact *before* trusting the returned findings. If the reviewer edited the artifact, treat those edits as **integrator-grade, not authoritative** — verify each against current disk exactly as the review-integrator would, do not adopt them blind. The returned "findings" list may not match what was actually written. Structural fixes (either direction closes the gap): a hard no-edit guard in the reviewer's own prompt, or stripping write tools from the tool surface for read-only review dispatches. Until one lands, the diff-before-trust check is the EM's floor.

## Integrator-modifies-sidecar — promote to baseline-prompt rule, not per-dispatch reminder

The `review-integrator` modifying the sidecar it was told to read-from has recurred 4× in a single observation window. Per-dispatch "DO NOT modify the sidecar" briefs are empirically unreliable — the same constraint-shape failure recurs across distinct EMs and distinct artifacts.

**Rule:** the sidecar-immutability constraint belongs in the integrator's baseline agent prompt (`agents/review-integrator.md`), not in every dispatch brief. Brief-level reminders are reasonable belt-and-braces, but they are not the primary enforcement surface — the agent-prompt is.

This is the same shape as the executor-writes-to-archive/ recurrence: when a constraint fails 3+ times across independent dispatches, the fix is to make the constraint load-bearing in the agent's own prompt, not to keep refining the dispatch brief. EM-side: when surfacing a recurring constraint failure to PM, propose the agent-prompt edit, not a brief-template revision.

A hook-level tripwire (e.g. `block-write-to-sidecar-during-integration`) is the next escalation if the baseline-prompt rule still fails.

## Opus coherent-voice prose work — amendment pass to restore load-bearing specifics

**After an Opus "humans-first" or coherent-voice prose rewrite, budget an amendment pass to restore load-bearing specifics that over-genericization removed.**

Opus prose work that targets narrative coherence (making documents read as a unified voice, removing jargon, smoothing transitions) has a systematic failure mode: the model treats domain-specific numeric thresholds, named edge-case distinctions, empirical caveats, and "negative-spec" blocks as friction and smooths over them in the name of clarity. The resulting prose is more readable but loses specifics that were load-bearing — a downstream executor reading the smoothed version derives the wrong implementation detail, a scanner misses an exemption that was carved out, or a tripwire loses its concrete trigger condition.

Apply: after any Opus coherent-voice pass (a persona review whose mandate includes "humans-first prose" or "readable narrative"), run a diff of the output against the input and recover:
1. Named numeric thresholds that became verbal qualifiers ("at most five" → "a small number").
2. Negative-spec blocks ("NOT `git add -A` — use explicit paths") that softened to affirmative suggestions ("prefer explicit paths").
3. Empirical citations or "concrete failure" examples that were removed as repetitive.

The amendment pass is EM-side, not a re-dispatch to the Opus reviewer — the reviewer did its job correctly; the EM's job is to audit the specificity delta and restore load-bearing content the generic voice dropped.

## Why sequential-with-fix-gates beats parallel+aggregate

The coordinator review pipeline's sequential-with-mandatory-fix-gates shape (domain-expert
reviewer reviews first → **all** findings from that pass are applied, not triaged, before the
next reviewer sees the artifact → generalist reviewer(s) review the now-clean artifact) is a
genuinely novel pattern, not merely "parallel review with extra steps": it optimizes for
**compounding insight** — each reviewer builds on a progressively cleaner artifact, rather than
everyone independently reviewing the same messy draft and requiring a separate aggregation step
to reconcile overlapping or contradictory findings. Parallel+aggregate trades reviewer
independence for reconciliation cost; sequential-with-fix-gates trades a longer pipeline for a
monotonically improving artifact at each stage.

**Parallel+aggregate is the tempting default — resist it for domain-expert-then-generalist
review.** It looks cheaper (dispatch N reviewers at once, merge results) but it loses the
compounding-insight property: a generalist reviewing a messy draft in parallel with the domain
expert will re-raise issues the domain expert would have already caught and fixed, and true
reconciliation of conflicting findings becomes a manual, ad-hoc step instead of a designed
pipeline stage.

**A synthesis/adjudication pass, where run, is what turns "N reviewers each said something"
into "here is what the reviewers collectively found, and where they diverge."** Without this
layer, disagreement between personas is silently dropped or requires the consuming EM to
manually reconcile N separate review documents — read every persona's output, consolidate the
findings, and flag agreement/disagreement across personas explicitly rather than leaving it
implicit in the raw output.

## review-integrator.md § Intake precondition — EM remedies

Relocated from the agent body's intake hard-stop paragraph (C2 of
the integrator-payload trim) — the pinned two-sentence hard
stop itself stays in the agent body verbatim; this is the EM-facing remedy mechanics that don't
need to occupy every integrator dispatch's context.

When the integrator BLOCKS with "intake broken: no sidecar on disk," the EM has two remedies:
re-dispatch the reviewer (`provision_report` auto-provisions a sidecar at spawn:
`state/subagent-share/<session>/<provision_key-or-label-nonce>.md`), or, defect-recovery only,
`Write` the reviewer's verbatim output into that sidecar then re-dispatch the integrator with the
path. Never hand-scaffold via `coordinator-doc-new` for this recovery — that command is reserved
for the reviewer's own self-scaffold path, not an EM substitute for a missing reviewer sidecar.

## review-integrator.md § Shared-Tree Stash Discipline

Relocated from the agent body (the integrator-payload trim)
— the agent body keeps the rule and the guard citations (`block_subagent_stash_creation.py:134`,
`block_stash_destruction.py:139`), this is the incident rationale.

A shared-tree incident showed a subagent's own `git stash push` capturing every concurrent
session's uncommitted work, not just its own, with no reliable undo path available to it. The
create-side command is now denied outright for every subagent rather than left to scoped
discipline — there is no pathspec-scoped form that gets through, by design, because the incident
showed scoped discipline alone was insufficient.

## review-integrator.md § How to write the block

Relocated from the agent body (the integrator-payload trim)
— the agent body keeps the shape reference (heading, fenced YAML with the six buckets, optional
Rationale subsection, the sixth-bucket-renders-only-when-used rule); this is the full worked
example.

````markdown
---

## Integrator Dispositions

```yaml
schema_version: 1
applied: [F1, F2, F3, F7, F10]
escalated-disagree: [F4]
escalated-ask: [F6, F9]
escalated-p0: []
deferred: [F8]
verified-no-action: [F5]
```

### Rationale

- **F1 (applied):** stale `surface` claim on `2026-08-01-plan/C3` corrected against HEAD before applying.
- **F4 (escalated-disagree):** reviewer's fix would re-introduce the precedence bug in `docs/wiki/<x>.md` — current code is intentional.
- **F5 (verified-no-action):** reviewer couldn't re-derive the count under its own tooling — re-derived by a second method, exactly right; nothing to change.
- **F8 (deferred):** real bug, needs a 4-file refactor; captured as `state/debt-backlog/<date>-<slug>.yaml`.
````

## Analysis-before-build with EM adjudication — case study

Pre-execution analysis — reviewing a recipe or plan step's `gives_pause` flags with EM
adjudication *before* building — has empirically earned its keep. On one migration workstream,
recipe analysis surfaced three scope corrections that would otherwise have shipped wrong:

- Deferred a step whose dependency hadn't actually resolved yet, even though the recipe listed it
  as ready.
- NO-OP'd a step that, on inspection, wasn't needed at all — its precondition failed to hold.
- Gated a later step to run only after an earlier one had actually produced the artifact it
  depended on, instead of running them in the recipe's stated order.

None of these corrections were visible from the recipe text alone — each required an adjudicator
to ask "does this step's stated precondition actually hold right now?" **`gives_pause` flags are
not self-resolving** — a recipe or plan step can carry a flag that reads as boilerplate caution,
and still hide a real scope correction behind that framing. Treat every such flag as requiring an
explicit adjudication decision (defer / no-op / gate / proceed), not a pass-through — the standing
lesson is to keep the same adjudication discipline for every remaining recipe's `gives_pause`
flag, not just the ones that happened to surface problems first.

## review-integrator.md § AUTO-FIX vs ASK Routing — why the un-calibrated row is the normal case

A reviewer writing to the injected `review-findings-body-contract` — `code-reviewer`, the pairing
`/workstream-complete` prescribes — emits neither a fix classification nor a confidence, that
contract specifying Severity, Location, Evidence, Issue, and Suggested fix and nothing else. The
calibrated rows are therefore the exception across most of the live dispatch population, and the
un-calibrated rows are the whole table for those dispatches.

The failure this ordering prevents is coercion: an integrator reading "confidence < 5 → drop"
against a finding with no `confidence` field at all, treating absence as zero, and silently
dropping a P1. Absence is not zero. Severity carries the routing the missing fields would have
carried, and an un-calibrated-by-contract P0/P1 still runs the P0/P1 Verification Gate before
applying anything — the Gate's inputs are the finding's citations, not a confidence number, so it
runs fine un-calibrated. The Gate was never inapplicable to this class; only its calibration
precondition was, and that precondition was never what the Gate actually needed. A
calibration-capable reviewer that omitted the fields still escalates unchanged — that is a
distinct, worse case (the calibration was owed and missing), not the normal one this section
describes.

## review-integrator.md § What a Dispatch Brief Cannot Relax

A dispatch brief sets scope, targets, and emphasis. It does not lower a routing floor. The floors
are the routing table (un-calibrated rows included), the always-ASK rule for
math/algebra/precedence and symbolic-reasoning findings, sidecar immutability, and the commit
prohibition.

Why the floors resist ordinary EM phrasing: a brief saying *"apply tradeoff-free fixes silently —
that is the default and needs no permission"* is a true statement of the general default and still
does not reach these cases, because the dispatching EM has usually not read the integrator's own
body. That is the point of dispatching. An EM who has not read the floor cannot knowingly waive it,
so an integrator resolving the collision silently toward the brief removes a default the EM never
learned they were overriding.

Hence the collision is itself a finding owed upward: hold the floor, then quote the conflicting
sentence verbatim under `### Brief Conflicts` in the completion report, naming the floor it would
have relaxed and what you did instead.

## review-integrator.md § Pattern findings, instance-vs-class, and complexity threshold

**Pattern vs spot.** A pattern-shaped finding names a recurring shape rather than one location
("early-return without OutResult population"); its tells are generalizing language ("this pattern",
"always", "any X that Y"), a category of code rather than a specific site, or an implied consistent
policy. Grep for siblings, fix all of them, report the footprint. A spot-shaped finding ("line 42
has the wrong constant") applies only there. When in doubt, do the grep.

**Instance vs class** governs the file you are already touching, where pattern findings govern
other files. A finding can cite one instance of a broader inconsistency — import style, naming,
error-handling shape — without the reviewer having surveyed every occurrence, and fixing only the
cited instance can create a *new*, narrower inconsistency: one of four imports restyled leaves the
file mixed. Default to resolving the class within the touched file, on the finding's axis only.
Widening past that file is the EM's call, noted in `Reasoning` rather than acted on. Instance-only
is sometimes correct — a file legitimately mixed for a stated reason, or a whole-file fix that
exceeds scope — but say so in `Reasoning` rather than applying the narrow fix silently. Self-check:
*is the touched file now internally consistent on this axis?*

**Complexity threshold.** New files or abstractions, changes across 3+ interacting files (import
chains, shared state), or architectural restructuring (moving modules, changing interfaces) are
pipeline work, not inline work. Note the conversion in the completion report, capture a
`debt-backlog` entry via `coordinator-queue-append` when `state/debt-backlog/` exists (one YAML per
entry) or hand the entry to the EM in the report when it does not, and continue with the remaining
findings.

## review-integrator.md § Escalation blocks and the circuit breaker

An escalation block carries four lines: the finding summary, the integrator's position, the
reviewer's position, and a recommendation. Three or more escalations in one pass is itself a
signal — flag it as a possible calibration mismatch between reviewer and integrator, so the EM can
choose between overriding individually and recalibrating the pairing.

The anti-dodge rule is what keeps ASK from becoming a disposal route: "needs PM input" alone is a
dodge. A genuine ASK names the specific tradeoff, two or more concrete options, which the
integrator would pick if forced, and why the choice exceeds its discretion. A finding that cannot
fill all four is not an ASK — it is Applied if the integrator can decide, or escalate-disagree if
it can decide and disagrees.

## review-integrator.md § Prior-art conflict directions

A dispatch citing a `prior-art-checker` sidecar with Conflicts carries a direction-of-correction
per conflict, and `update-prior-art` is a first-class outcome rather than a fallback. No direction
named → escalate ASK rather than guessing.

- `update-plan` — amend the plan to fold the prior art in, annotated with reviewer plus prior-art
  quote citation.
- `update-prior-art` — edit the cited wiki/registry/lessons file per the EM's correction, annotated
  with plan citation plus reviewer reasoning.
- `both` — land both amendments in one pass, cross-citing each annotation.
- `override-and-document` — one line in the plan's "Considered alternatives" carrying the prior-art
  quote and the override rationale; the prior-art file is not edited.
- `PM-input-needed` — no edit; surface the conflict, the candidate directions, and a recommendation.

On the two hand-editing directions the integrator holds read-write access to wikis, lessons, and
registry/improvement-queue files. Matching the EM's correction in scope and substance wins the tie
against Reconcile-Before-You-Add: needing more than the stated update to stay consistent escalates
ASK rather than expanding silently. A global-wiki target with a bundled copy at
`plugins/*/docs/wiki/<name>.md` trips the wiki-mirror guard, which is advisory — the write already
landed when the flag appears, so it is neither undone nor retried differently; escalate ASK with
the hook output and let the EM decide whether to redirect to the mirrored path or accept the
dev-side copy.

## review-integrator.md § REJECTED verdict — why findings are suspended wholesale

`verdict: REJECTED` means the reviewer found a premise-level problem that findings cannot fix. The
suspension is wholesale — no AUTO-FIX, no ASK, no sibling sweeps — because applying findings under
a rejected premise patches the wrong design, and doing so partially is worse than not at all: it
produces an artifact that looks reviewed.

The override protocol exists so that proceeding anyway leaves a durable trace. Only explicit PM
agreement, recorded verbatim before any finding is applied, and landed in the EM's coordination
notes or task log rather than chat alone. Paraphrase is insufficient — the whole value of the
premise-challenge is that overriding it costs something visible.

## review-integrator.md § Identity — why the integrator is unconditional on verdict

The agent body keeps the rule (`OK` does not skip integration; never gate on `WARN`/`BLOCKED`) and
the tripwire citation. This is the argument.

Confirmation and verification emit the same token. A reviewer that actually re-derived a claim and a
reviewer that skimmed and agreed both return `OK`, so an integrator that only runs on
`WARN`/`BLOCKED` gives the cheapest-to-produce verdict the least scrutiny — precisely inverted. An
`OK` dispatch is therefore normal traffic, not a dispatch error to be reported back, and it costs
the integrator one empty triage table. Full tell:
`coordinator/docs/wiki/coordinator-tripwires/an-ok-is-not-evidence-anyone-checked.md`.

## review-integrator.md § AUTO-FIX vs ASK Routing — why always-ASK outranks the table

The agent body keeps the rule (math/algebra/precedence and any symbolic-reasoning finding is ALWAYS
ASK, at any confidence, severity or fix class, including a calibrated `AUTO-FIX` at confidence 10
and a P0/P1 that passes the Verification Gate) and the ordering (apply it before any table row).
This is why the ordering is load-bearing.

A symbolic-reasoning finding also matches a severity row. An integrator reading the routing table as
a severity lookup therefore reaches "P0/P1, calibrated AUTO-FIX → verify and apply" and applies the
algebra silently, without ever noticing that a separate rule governed it. The always-ASK rule is
stated above the table, not inside it, so that a row-first read cannot miss it.

The Verification Gate does not close the gap. The Gate confirms that the finding's cited evidence
matches current source — "the evidence block matches the source" confirms the quote, never the
algebra. A reviewer that mis-derived a precedence result will quote the source correctly and still
be wrong, and the Gate passes.

## review-integrator.md § ASK Options Carry Their Source

The agent body keeps the rule (every option names its source; only a reviewer-sourced option is
choosable downstream; never author a fix or narrow a reviewer's stated option set) and the
plan-blitz tripwire citation. This is the mechanism and the argument.

**Attribution errs both ways, and both ways break settleability.** An option the integrator composed
and left under a reviewer's name launders the integrator's own judgment as the reviewer's — the EM
or planner downstream reads a reviewer recommendation that no reviewer made. A reviewer's option
left unattributed is not merely uncredited: it is *dropped*, because the downstream gate can only
settle an escalation by choosing a reviewer-sourced option, so an escalation whose only options read
as the integrator's arrives unsettleable. An option the integrator composed is still the
integrator's, still unchoosable, and still never a reason to apply an ASK itself.

**Escalation destination.** An escalated ASK does not necessarily stop at the EM. `plan-blitz.mjs`
conditionally re-invokes the planner — its revising branch — once a plan's integration escalates at
least one ASK, and hands that planner a catalogue built from the reviewer-attributed options the
escalation states. That planner reads the structured escalations and nothing else, so a finding the
integrator neither applied nor escalated reaches no one at all. This changes only WHERE an escalated
ASK is read next; it never widens what the integrator may apply. See
`coordinator/docs/wiki/coordinator-tripwires/the-revising-planner-also-edits-the-plan-body.md`.

## review-integrator.md § Trail-File Ownership — what a returning writer would owe

The agent body keeps the operative rule: the integrator writes no trail file, nothing does,
`state/review-trail/*.json` is frozen, its UNCOVERED never means "unreviewed", and the record is the
`review_receipt:` block a reviewer stamps into its own sidecar
(`A-SUSPENDED-OP-IS-NOT-A-MECHANISM-TO-WAIT-OUT`).

Retained here because the shape matters if a writer ever returns, and because a reader finding the
frozen file might otherwise reconstruct the wrong ownership rule: one file per
`(session_id, sha_range)`, never an append to another session's file, and escalate rather than guess
when the pair cannot be determined. That is not a live obligation on any integrator today. Reading
it as one is the failure this note exists to prevent — the suspension is not a queue to wait out.

## review-integrator.md § Apply Everything — an annotation without the edit beside it

The agent body keeps the rule: an annotation standing alone beside unchanged operative text is an
UNAPPLIED finding, dispositioned `escalated-ask` and returned in the structured escalation with the
reviewer's fix attributed as its one option — never `applied`, never `deferred`, never closed by the
annotation (`A-SINGLE-REVIEWER-OPTION-IS-A-RECOMMENDATION-NOT-A-DEAD-END`).

Why it is worth a rule of its own: the annotation quotes the reviewer's fix, so the artifact reads as
though the finding was considered and handled, while the operative text it sits beside is byte-identical
to before. Nothing downstream distinguishes that from an applied fix except re-reading the diff. A plan
reaching the readiness gate carrying one of these is pulled, which is the cost the rule prevents —
the finding looked closed for as long as nobody looked, and then cost a whole gate cycle.

## review-integrator.md § Apply Everything — annotating a plan spine row

The agent body keeps the rules: apply spine-row findings with `Edit` like anything else, never reach
for the retired `plan-tasks-stamp`, and escalate ASK on a finding proposing an edit to
`disposition`/`disposition_ref`/`disposition_detail` (engine-reserved, owned by `resolve`) or to
`pm_approved`/`deferred` (authorization and scope semantics).

Why no CLI path is the right answer rather than a gap to fill: a spine row is markdown inside a
fenced YAML block in a plan the integrator is already editing. A mechanically-mappable finding
tempts an integrator toward a stamping CLI, and `plan-tasks-stamp` was retired precisely because a
second writer into the spine produced rows whose `disposition` no longer agreed with the engine's.
A retired path is not one to reconstruct because a finding looks mechanically mappable.

## review-integrator.md § Detector Widened — why attribution defaults to the detector

The agent body keeps the rule: a fix touching detection logic (lint, guard, matcher, validator,
schema check) changes what that detector matches, so when the suite goes red after such a fix the
default attribution is the detector, not the newly-flagged site; read the flagged content rather
than only the assertion, and name the attribution and its reason in the report
(`DETECTOR-WIDENED-ATTRIBUTE-BEFORE-ESCALATING`).

The asymmetry is what justifies a default rather than a case-by-case judgment. A widened detector
firing on a site that was always wrong and never matched is the expected, healthy outcome of the
fix; a widened detector firing on a correct site is a defect in the widening. Both present
identically as a red assertion, and the cheap read — escalate the flagged site — is wrong in the
second case and wasteful in the first, because the flagged site's own author is not the one who
changed anything. Attributing to the detector first puts the question where the change was.

## review-integrator.md § Terminal Stamp — why column zero and why a list

The agent body keeps the rule: `integrated_from` as a top-level frontmatter key at column zero in
the integrator's OWN run-report sidecar, never the reviewer findings sidecar, valued as a list of
reviewer-sidecar stems in receipt order, skipped entirely when nothing was integrated, plus the
pre-completion self-check and the `guard-kira-verdict-routed.py` consequence.

Two mechanisms, both silent on failure. The run-report scaffold's `divergence:` pair is itself
indented, so a key appended at the end of the frontmatter lands nested under it; the record then
fails `additionalProperties: false` and the stamp is discarded without an error anyone reads. And
`guard-kira-verdict-routed.py` joins on this key alone — an unstamped run-report reads at session
close as a dispatch that never happened, which hard-stops the EM at the gate rather than at the
integrator. The list shape matters for the same reason: a scalar satisfies "the key is present"
while carrying only one of N sidecars, and the guard's join then silently covers a subset.

Re-deriving the list from the triage table is the tempting shortcut and is wrong: the triage table
holds the findings that were triaged, not the sidecars that were received, so a sidecar that
stopped at an intake precondition or contributed no rows disappears from it.

## review-integrator.md § Sidecar Disposition Annotation — hand-authored shape

Hand-authoring is licensed by exactly one condition: an `agent_type` refusal from
`append-integrator-dispositions`. It stays mandatory, stays self-checked, and goes in the report.
The worked example is above, under § How to write the block. The shape it must match:

1. A `---` divider.
2. The literal `## Integrator Dispositions` heading.
3. A fenced `yaml` block carrying `schema_version: 1` plus the six buckets.
4. An optional `### Rationale` subsection — one bullet per finding that needs one, never a row per
   finding.

Five buckets always render, `[]` included. `verified-no-action` renders only when non-empty, and
last — `DISPOSITION-BUCKET-SIXTH-RENDERS-ONLY-WHEN-USED`, whose contact points include
the engine repo's `coordinator_core/ops/append_integrator_dispositions.py` `BUCKET_ORDER`. Matching the
CLI's byte-for-byte output is the whole point of the shape spec: a hand-authored block that renders
a sixth empty bucket, or orders them differently, diverges from every block the CLI wrote.

## review-integrator.md § Escalation Protocol — the one-option carve-out

The four anti-dodge fields and the three-escalation circuit breaker are above, under § Escalation
blocks and the circuit breaker. One clause needs its own note, because it looks like a hole in the
floor and is not.

Field (2) normally demands two or more concrete options. Where the reviewer wrote exactly one named
fix and the integrator composed nothing, that single reviewer-sourced option satisfies it. The floor
exists to stop an integrator inventing an option or laundering its own as a reviewer's — it was
never meant to suppress the one option a reviewer actually wrote, and reading it that way turns a
settleable recommendation into a dropped finding. Downstream, a one-option escalation is settled as
a recommendation, not a dead end: `A-SINGLE-REVIEWER-OPTION-IS-A-RECOMMENDATION-NOT-A-DEAD-END`.
