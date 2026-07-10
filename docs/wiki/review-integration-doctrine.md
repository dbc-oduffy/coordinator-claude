---
title: Review integration doctrine
created: 2026-05-17
type: doctrine
related:
  - plugins/coordinator/docs/wiki/receiving-code-review.md
  - plugins/coordinator/docs/wiki/reviewer-premise-challenge.md
  - plugins/coordinator/docs/wiki/prior-art-checker.md
  - plugins/coordinator/docs/wiki/docs-checker-pre-review.md
---

# Review Integration Doctrine

How to receive and apply reviewer findings correctly — the failure modes that appear at integration time rather than review time.

## The integrator is a second checker, not a cheaper typist — so dispatching it is mandatory

**Why this is the foundational rule:** the recurring violation is an EM reading a review, opening the cited files, and hand-authoring the changes the reviewer stated — skipping the integrator because the findings look small or obvious. This is forbidden regardless of finding size.

The review-integrator's primary value is *not* that it costs a fraction of an EM's headspace (though it does). Its primary value is that it is **a fresh agent that independently re-checks each finding against the current state of disk before applying it.** A review is a snapshot; by the time it lands, a finding may be wrong, stale (a concurrent executor moved the schema), or mis-scoped (the rename collides with a constraint that landed after the review — see § Re-verify reviewer premises and the post-review schema-pinning worked variant). The integrator catches these because it reads HEAD, not the reviewer's frame. When the EM types the changes directly, that second independent check never happens — the EM applies the reviewer's claim at face value, and any defect in the finding lands silently in the artifact.

So the cost framing actively *misleads*: an EM who believes the integrator is just a token-saver will rationalize "this finding is one line, dispatching a whole agent is wasteful — I'll just type it" and in doing so discards exactly the verification the dispatch exists to provide. **Finding size is not a license to self-author.** The smaller and more obvious a finding looks, the cheaper the integrator pass is — and the easier it is to skip the check that occasionally catches the obvious-looking finding that was actually stale.

Mechanics of the mandatory pass: EM dispatches `coordinator:review-integrator` (mode `auto`), reviews the returned escalation list, spot-checks the diff. Tradeoff-free fixes the integrator folds silently; real tradeoffs it escalates as ASK for the EM to carry to the PM (§ Apply tradeoff-free fixes silently). The EM's job is to *route and verify*, never to *author*. → `coordinator/CLAUDE.md § Review Sequencing` ("never hand-author the reviewer's stated changes yourself"); global `CLAUDE.md § Acting on review findings`.

## Re-verify reviewer premises against artifacts landing after review

Schemas, function signatures, and file layouts can change between when a reviewer writes their findings and when the integrator applies them. A reviewer that writes "confirm field X exists before shipping" may be referencing a schema that has since been updated by a concurrent executor. Integrating the finding blindly adds a redundant check or, worse, rewrites something that no longer needs rewriting.

Integrator discipline: before accepting any finding that contains "TBD," "confirm later," "verify before applying," or a premise about a schema/path/API, read the current state of the referenced artifact. If the premise no longer holds, drop the finding (not the whole review — just that finding) and note the drop in the integrator's report.

This is structural at concurrent-EM cadence. On shared branches, an executor may have landed changes while the review was in flight. The reviewer's frame is a snapshot; the integrator works against HEAD.

**Sidecar `<file>.md § <section>` citations need a two-part verification before integrating.** Prior-art-checker, docs-checker, and plan-coverage-checker sidecars routinely cite a wiki by name and section (`<file>.md § <section>`). Before acting on such a citation, verify BOTH that (a) the cited path exists (check `archive/` for relocated wikis — spec backlinks outlive their cited spec) AND (b) the section's scope actually maps to the plan's deliverable. A citation can resolve to a real file and a real section that nonetheless addresses a different concern than the sidecar implies — integrating against it imports a mismatched constraint. Path-exists is necessary but not sufficient; section-scope-maps-to-deliverable is the second leg. *Source: project-rag-ue-addon, 2026-06-14.*

**Worked variant: post-review schema-pinning.** A the Staff Engineer finding directed a renamed CLI flag (`--foo` → `--bar`); the schema then landed with `additionalProperties: false` pinning the original JSON key. Applying the rename verbatim would have broken the schema constraint that landed after the review. The resolution: keep the JSON key canonical to the schema, localize the rename to the user-facing CLI flag and banner text. Pattern: any reviewer finding that prescribes a rename must be re-verified against schemas, fixtures, and external-API contracts that may have landed since the review — the rename's scope is bounded by what landed after, not by the reviewer's frame at the time. (Source: 2026-05-28 apply-packet-cluster-4.)

## Adopt-with-receipts — document-the-tradeoff is a valid integrator outcome

A reviewer (the canonical case is the Staff Engineer) flagging a bounded UX or design cost does not always mandate a restructure. **"Document the tradeoff, don't restructure" is a legitimate integrator disposition for bounded costs** — and it is not the same as dismissing the finding. The adopt-with-receipts shape: (1) name the cost explicitly in the artifact, (2) name the larger restructure that would eliminate it, (3) record PM-acceptance of the bounded cost, (4) name the revisit trigger (the condition under which the cost stops being acceptable and the restructure becomes warranted).

This sits between "fold silently" (§ Apply tradeoff-free fixes silently) and "escalate as ASK." The finding is real and accepted; the resolution is to carry the cost with a documented escape hatch rather than pay the restructure now. The receipts (named cost + named alternative + PM-acceptance + revisit trigger) are what distinguish adopt-with-receipts from the appetite-based "not now / follow-up" hedging that `coordinator/CLAUDE.md § Implementation Standards` bans — the four elements make the deferral architectural, not an excuse.

*Source: example-league-data-repo, 2026-06-08 (the Staff Engineer bounded-UX-cost pattern).*

## Apply tradeoff-free fixes silently; surface tradeoffs to PM

→ coordinator/CLAUDE.md § Reviewer findings — apply, don't ratify

Correctness fixes (wrong API name, missing import, factual error, precedence) fold into the artifact via the integrator without EM narration or PM escalation. These have no tradeoff; the finding is simply correct.

Tradeoffs (cost vs. value, scope expansion, architectural direction, visible behavior change) go to the PM before integrating. The integrator writes an escalation list; the EM presents it. The PM decides.

The failure mode this prevents: EM treating every review finding as a question requiring PM sign-off, which bogs down integration and inverts the relationship between mechanical correctness and product judgment.

## A reviewer recommendation is not authority to deviate from what shipped

Spec authority is the PM's, not a reviewer's. A mid-workstream edit that honors a reviewer *recommendation* against already-shipped code can be reverted by the PM — the reviewer exposed a consideration, but "what shipped" is the PM's ratified surface until the PM says otherwise. Treat a reviewer's "you should restructure X" against landed code as a finding to route (fold-silently only if tradeoff-free-correct; otherwise escalate as ASK per § Apply tradeoff-free fixes silently), never as standing license to rewrite the shipped shape.

**A `system-reminder` reporting a file the user or a linter just modified is ground-truth signal — stop additive cleanup and roll back to match.** When the harness injects a `<system-reminder>` noting that the user (or a formatter/linter running on save) has just changed a file mid-session, that is the strongest available signal of the *desired* shape — stronger than any in-flight reviewer recommendation. The correct response is to **stop additive cleanup on that surface and roll back partial sibling edits to match** the reported state, not to continue applying the reviewer's frame over the top of what the user just chose. The user's live edit outranks the reviewer's snapshot.

## Chain-end review and plan-time review catch different defect classes

Plan-time review (the Staff Engineer on the stub, prior-art-checker on the plan) checks substrate and approach: are the paths real, is the schema correct, does this contradict prior doctrine, is the architecture coherent? These checks work against the plan artifact before any code is written.

Chain-end review (workstream-complete `code-reviewer` or `code-reviewer`+the Staff Engineer on the landed diff) catches a different class: boundary-relabeling bugs (where a function's name or contract shifted during implementation), integration-seam mismatches (where two independently-implemented chunks don't compose), and structural drift from the plan. These defects are invisible at plan time because they emerge from the gap between intent and implementation.

Running only plan-time review and skipping chain-end review is not "sufficient review" — it is review that structurally cannot see the defect class that most commonly survives execution.

→ coordinator/CLAUDE.md § Workstream-complete / weekly marker trail (under Review Sequencing) for the chain-end review procedure.

## Single-agent math and precedence findings need verification

A single reviewer flagging a logic error, arithmetic mistake, or operator-precedence bug requires verification before integration — do not apply single-agent math/precedence findings silently. The false-positive rate on single-agent findings of this class is high enough that acting on them without verification introduces regressions.

The confidence threshold is convergence: two or more independent agents flagging the same issue from different entry points. One agent with high-confidence framing is not the same as convergence.

→ coordinator/CLAUDE.md § Convergence as Confidence  
→ coordinator/CLAUDE.md § P0/P1 Verification Gate

## Pre-flight sidecars do not require integration before the first reviewer

The sequential-review HARD RULE ("integrate Reviewer 1 before Reviewer 2") applies to **named persona reviewers** — the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering. It does NOT apply between a Sonnet pre-flight (docs-checker, prior-art-checker, external-pattern-checker) and the first named reviewer.

The reasoning is structural, not a convenience exception. The named reviewer is exactly the agent whose Opus-tier architectural judgment we want shaping direction-of-correction on prior-art Conflicts. Front-loading EM disposition before the reviewer sees the plan inverts the leverage: it forces the EM to make architectural calls the reviewer was dispatched to make, and it freezes prior art into "plan must yield" rather than asking which surface is the more current artifact. The post-reviewer integrator pass is where prior-art-side edits land — across the plan, the wiki, or both — per the reviewer's recommendation and the EM's direction call.

What this means in practice:

- **docs-checker** AUTO-FIX corrections land inline per its own contract (`docs/wiki/docs-checker-pre-review.md`). No integrator pass between docs-checker and the reviewer; the sidecar travels with the artifact for the reviewer's awareness.
- **prior-art-checker** sidecar travels unintegrated. The reviewer sees `Conflicts` / `Compatible-but-relevant` / `Silent` buckets and recommends a direction-of-correction per Conflict. EM pre-disposition in the dispatch brief is optional, reserved for cases where the direction is mechanically obvious (e.g., a Conflict against load-bearing doctrine that's already settled). When the EM does pre-dispose and the reviewer disagrees, the integrator escalates as ASK — never silently applies either direction. → `agents/review-integrator.md § Prior-Art Conflict Resolution`.
- **external-pattern-checker** sidecar folds into the reviewer's dispatch prompt as ad-hoc context (per its own consumption contract), not as an integration step.

What still requires integration between artifacts: every pass between two named persona reviewers. If the Staff Engineer runs first and recommends changes, the integrator lands them before the Game Dev Reviewer sees the artifact. That's the rule the HARD RULE was written to enforce, and it's unaffected.

→ coordinator/CLAUDE.md § Review Sequencing (pre-flight carve-out bullet)  
→ `docs/wiki/prior-art-checker.md § Bidirectional resolution`  
→ `agents/review-integrator.md § Prior-Art Conflict Resolution`

## Re-run mechanical pre-flights after material plan amendments

Pre-flights (path scout, prior-art-checker, docs-checker) are point-in-time. A material plan amendment — adding a new component, changing a schema decision, reordering chunks — creates a new claim surface that the original pre-flight did not cover. Stale pre-flight findings at integration cause the integrator to accept or reject findings against a plan that no longer matches what was reviewed.

The rule: after any material amendment, re-run the relevant pre-flights before dispatching the next reviewer. "Material" means any change that alters paths, APIs, schema fields, or architectural approach. Prose clarifications and wording changes do not require re-run.

→ coordinator/CLAUDE.md § Plan-First Workflow → Pre-Dispatch Verification ("Re-run mechanical pre-flights after material plan amendments")  
→ `docs/wiki/prior-art-checker.md` for prior-art-checker procedure  
→ `docs/wiki/docs-checker-pre-review.md` for docs-checker procedure

## Reviewer self-persists; EM reads the returned path — no transcription

`coordinator:code-reviewer` self-persists by default. There is no inline-return mode and no `-selfpersist`
variant — there is one reviewer, and it always writes its findings to disk. Spec backlink:
`cross-repo/inbox/2026-07-01-reviewer-selfpersist-confinement-redirect.md`.

**How it works.** The reviewer scaffolds its own sidecar in `state/review-trail/findings/` via
`coordinator-doc-new --type review-findings` (the Bash allowlist permits this one command), edits the
`<!-- FINDINGS -->` sentinel with its findings, and returns only a pointer+verdict line:

```
DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>
```

No EM pre-scaffold. No `cs_write_review_claim` call. No claim-marker ceremony. No EM transcription.
The EM reads the returned path and passes it to `coordinator:review-integrator`.

**Personas (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer, the Front-End Reviewer, the UX Reviewer, the Director of Engineering)** are dual-use (advisory OR sidecar-review).
When dispatched for a review that feeds an integrator, the invoking skill appends the
`snippets/findings-self-persist-sentinel.md` protocol to the brief — the persona then scaffolds its
own sidecar in `state/review-trail/findings/` and returns the pointer line. No pre-scaffold by the EM;
no claim marker. Same zero-ceremony pattern as `code-reviewer`.

**If a reviewer returns inline despite this contract**, it is a dispatch failure — re-dispatch
`coordinator:code-reviewer`. Do NOT transcribe inline output manually; the transcription path is
what the self-persist contract exists to eliminate.

→ `agents/code-reviewer.md` — the one self-persisting reviewer

### Runtime-only findings need an explicit pass-through channel — disk-observing writers cannot reconstruct runtime facts

A reviewer finding of the shape *"record runtime-only X distinctly"* (a value observed only at execution time — a live error string, a timing-dependent state, an actual emitted token, an environment-resolved path) has no on-disk source for the integrator to read. The `review-integrator` is a disk-observing writer: it reads the cited code and the sidecar, then edits the artifact. It physically cannot reconstruct a runtime fact that exists only in the reviewer's execution context — if that fact is not handed across explicitly, it is lost in the integration pass.

**Rule:** when a reviewer surfaces a runtime-observed fact that must survive into the artifact, the EM captures the verbatim runtime value into the persisted sidecar (same persistence-layer discipline as inline reviewer output, above) so the integrator has an on-disk source. Do not assume the integrator will re-derive it — it observes disk, not the reviewer's runtime. The companion wiring (an explicit runtime-fact pass-through field in the integrator dispatch brief) lands in `agents/review-integrator.md` and `coordinator:review` Branch B. *Source: example-game-workbench-repo, 2026-06-18.*

## Brightline PARTITION-MANDATORY over-counts memo/doc-only commits — partition the CODE surface

The `≥5-commits` brightline (`review-brightline-gate.sh`, → `workstream-complete-review.md § Diff-shape decision table`) fires on raw commit count, but the partition decision is about **reviewable code surface**, not commit count. When the brightline trips, check how many of those commits actually *touch code*: if the reviewable surface is one coherent code slice — several of the commits being memo/doc/lesson-only — then a **single `code-reviewer` is correct**, and the right move is to `git show --stat` the code commits, confirm the coherent slice, and **record the disposition** ("gate over-counted N non-code commits; reviewable surface is one slice") rather than spawning empty partition reviewers over doc commits with nothing to review.

**`--session-id` scoping fixes cross-EM noise but NOT the doc-vs-code mix within one session.** The session-scope flag (→ `workstream-complete-review.md § Session-scoped diff via --session-id`) removes *other* EMs' commits from the count; it does nothing about *your own* session's memo + doc + lesson commits inflating the code-commit count past the brightline. That mix is disposed of by the code-surface check above, at disposition time, not by the gate.

## Integrator dispatches are 1:1 with reviewer slices

When a code review is partitioned across N parallel `code-reviewer` slices (per `skills/workstream-complete/SKILL.md` § Partitioning large surfaces), the integrator pass is partitioned the same way: **one `coordinator:review-integrator` per slice, dispatched in parallel, each scoped to the same slice paths as its source reviewer.** Not a single integrator over the union of N findings against N disjoint file sets.

**Why structural.** Reviewers are sliced because one Sonnet can't fit the whole surface in context. The same context-fit constraint binds the integrator — it reads the cited code, locates each finding's site, applies the fix, and adds annotations; the work is bounded by the union of (findings × cited paths), exactly the dimension the slicing controlled for. A union-integrator inherits N reviewers' merged scope and re-creates the overflow the slicing was designed to avoid. The dispatch-decomposition discipline that governs executor waves (`docs/wiki/dispatching-parallel-agents.md`) applies here for the same reason — small-remit-and-many beats large-remit-and-one when the surface was already partitioned upstream.

**Why not unification.** "One integrator over the union" looks like it preserves a coherent view of the diff, but the reviewers already partitioned that view — by package, concern, or directory cluster — into slices with no file overlap. Re-unifying at the integrator stage does not restore lost coherence (none was lost; slices were chosen to be disjoint); it just re-imports the context-pressure failure mode. If two slices DO overlap on a file (rare, by construction), the EM resolves that at the partition step, not by collapsing the integrator pass.

**Mechanics.**

1. Each `coordinator:code-reviewer` dispatch scaffolds its own per-slice sidecar in `state/review-trail/findings/` and writes its findings there. No EM pre-scaffold; no claim marker. The reviewer returns a pointer+verdict line: `DONE: <sidecar-path> | verdict: <OK|WARN|BLOCKED> | findings: <N>`. The EM reads the returned path. The sidecar must exist on disk before the integrator is dispatched (the reviewer's self-persist guarantees this on a clean return). The self-persist flow is an explicit step in `skills/workstream-complete/SKILL.md` § Partitioning (step 2), and the integrator's hard-stop is in `agents/review-integrator.md` § Intake precondition — hard stop.
2. EM dispatches N integrators in parallel, each pointing at one slice's sidecar + the same slice's artifact paths.
3. Each integrator writes its own disposition block to its own sidecar (§ Sidecar Disposition Annotation) and its own completion report.
4. EM reads the N reports in aggregate, applies the standard tradeoff-vs-correctness routing (`coordinator/CLAUDE.md` § Reviewer findings — apply, don't ratify), and stages the union of integrator-edited files in the workstream-complete commit (`skills/workstream-complete/SKILL.md` Step 3 staging discipline already handles fan-in).

**Tripwire.** A single `coordinator:review-integrator` dispatch handed N reviewers' findings against N disjoint slice paths is a doctrine violation — the integrator agent prompt rejects this shape as a broken intake (`agents/review-integrator.md` § Intake precondition, "One reviewer slice per integrator dispatch"). The recovery is to re-dispatch 1:1.

**Scope.** This rule binds workstream-complete partitioned reviews. The weekly merge-gate (`coordinator:parallel-code-review`) uses a different downstream — a no-rewrite synthesizer, not the integrator — so the 1:1 rule does not apply there; the synthesizer's input is multi-slice by design and never edits files.

## Cross-session review convergence routes through the integrator, not SUPERSEDED prose

## Narrative-Shape Review — Frame-Drift Lens Separate from Code-Review

Narrative-shape review is a separate lens from code-review — frame-drift ships clean diffs. Code-review operates at the level of individual hunks; it cannot catch when the entire framing of a document (entry-point prose, stated purpose, scope claim) drifts from the intended narrative. Author an entry-point prose check at producer time as part of the producer skill. Apply: for any document with a stated purpose (skill, wiki, plan), add a "narrative-shape check" step in the producer: does the opening paragraph still match what the document actually does?

**Cross-session review outputs flow through the review-integrator on a single canonical artifact — "SUPERSEDED" prose is not review provenance.**
**Why:** When concurrent EM sessions independently produce review outputs against parallel artifacts, marking the loser SUPERSEDED with a "findings carry forward" assertion is structurally unverifiable — Session B's enrichment may never have seen Session A's reviewer pass.
**How to apply:** at convergence time, the EM that supersedes MUST dispatch the review-integrator with the loser's findings as input and the winner artifact as target — same as a normal integrator pass. Review provenance is not transitive across artifact splits; an asserted carry-forward is just prose. Pairs with `coordinator/CLAUDE.md` § Cross-session reviews converge on one canonical artifact.

*Source: example-game-repo `state/lessons.md` (example-game-repo-L121, central-promoted 2026-05-28).*

## review-integrator commits by default — align the brief with the agent's behavior

**The `review-integrator` agent commits on completion as part of its executor-class script (Co-Authored-By attribution and all); "No commits — EM will commit after spot-check" in the dispatch brief is overridden by that hardwired behavior.** A /plan→/review pipeline returned with both the plan and a prior-art sidecar committed despite the brief explicitly forbidding commits; the integrator also picked up a previously-untracked sidecar at the same SHA, which was arguably the right call for the audit trail. The violation was constraint-shape, not work-shape. Discipline: phrase the brief around the expected commit shape (paths, subject, what should be staged together) rather than "do not commit" — or escalate to a different agent type that does not auto-commit. Briefs that fight the agent's hardwired completion behavior produce a constraint-shape violation every time. (case: example-game-repo 2026-06-09)

<!-- DoE resolved: 2026-06-15 — review-integrator agent prompt § Commit Discipline now carries an explicit brief-overrides-defaults precedence rule -->

## A write-tool reviewer may self-integrate against a read-only brief — diff the artifact before trusting findings

A reviewer whose agent-type carries `Edit`/`Write` (the canonical case is `coordinator:staff-eng` / the Staff Engineer, but any persona reviewer qualifies) can **ignore an explicit read-only dispatch and integrate its own findings into the artifact** — leaving an internally-inconsistent draft where some findings are applied, some are only described, and the two disagree. The read-only instruction in the brief is prose; the write tools are real, and under perceived helpfulness pressure the tools win.

**Rule:** on every reviewer return whose agent-type carries write tools, `git diff` the reviewed artifact *before* trusting the returned findings. If the reviewer edited the artifact, treat those edits as **integrator-grade, not authoritative** — verify each against current disk exactly as the review-integrator would, do not adopt them blind. The returned "findings" list may not match what was actually written. Structural fixes (either direction closes the gap): a hard no-edit guard in the reviewer's own prompt, or stripping write tools from the tool surface for read-only review dispatches. Until one lands, the diff-before-trust check is the EM's floor.

## Integrator-modifies-sidecar — promote to baseline-prompt rule, not per-dispatch reminder

The `review-integrator` modifying the sidecar it was told to read-from has recurred 4× in a single observation window (2026-05-27 cluster). Per-dispatch "DO NOT modify the sidecar" briefs are empirically unreliable — the same constraint-shape failure recurs across distinct EMs and distinct artifacts.

**Rule:** the sidecar-immutability constraint belongs in the integrator's baseline agent prompt (`agents/review-integrator.md`), not in every dispatch brief. Brief-level reminders are reasonable belt-and-braces, but they are not the primary enforcement surface — the agent-prompt is.

This is the same shape as the executor-writes-to-archive/ recurrence: when a constraint fails 3+ times across independent dispatches, the fix is to make the constraint load-bearing in the agent's own prompt, not to keep refining the dispatch brief. EM-side: when surfacing a recurring constraint failure to PM, propose the agent-prompt edit, not a brief-template revision.

A hook-level tripwire (e.g. `block-write-to-sidecar-during-integration`) is the next escalation if the baseline-prompt rule still fails.

Source: 2026-05-27 learn-lessons pass-2 cluster decomposition (b2g-034).

## Opus coherent-voice prose work — amendment pass to restore load-bearing specifics

**After an Opus "humans-first" or coherent-voice prose rewrite, budget an amendment pass to restore load-bearing specifics that over-genericization removed.**

Opus prose work that targets narrative coherence (making documents read as a unified voice, removing jargon, smoothing transitions) has a systematic failure mode: the model treats domain-specific numeric thresholds, named edge-case distinctions, empirical caveats, and "negative-spec" blocks as friction and smooths over them in the name of clarity. The resulting prose is more readable but loses specifics that were load-bearing — a downstream executor reading the smoothed version derives the wrong implementation detail, a scanner misses an exemption that was carved out, or a tripwire loses its concrete trigger condition.

Apply: after any Opus coherent-voice pass (a persona review whose mandate includes "humans-first prose" or "readable narrative"), run a diff of the output against the input and recover:
1. Named numeric thresholds that became verbal qualifiers ("at most five" → "a small number").
2. Negative-spec blocks ("NOT `git add -A` — use explicit paths") that softened to affirmative suggestions ("prefer explicit paths").
3. Empirical citations or "concrete failure" examples that were removed as repetitive.

The amendment pass is EM-side, not a re-dispatch to the Opus reviewer — the reviewer did its job correctly; the EM's job is to audit the specificity delta and restore load-bearing content the generic voice dropped. *Source: 2026-06-02 central-improvement-queue #50.*
