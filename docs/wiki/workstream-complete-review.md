---
provenance:
  - archived_spec: archive/specs/2026-05-15-ubt-compile-gate-review-trail.md
    original_path: docs/plans/2026-05-15-ubt-compile-gate-review-trail.md
    last_verbose_sha: af9b63e49817131fa7c88c8dcb0513271a50012d
    distilled: 2026-05-15
---

# Workstream-Complete Review and Marker Trail

<!-- spec-backlink: archive/specs/2026-05/2026-05-08-session-end-review-and-marker-trail.md §T9 -->

`/workstream-complete` is the natural pause point for post-executor code review — the diff is fresh, the EM has context, and the cost of catching an integration bug now is one Sonnet call instead of a debugging session three weeks later. The marker trail at `state/review-trail/` records what has been reviewed so downstream weekly and daily ceremonies shed redundant load rather than re-reviewing work already covered.

## When this fires

**Trigger surfaces:**

- `/workstream-complete`'s review-scale decision (`jp-review-scale`, measured by `gates['review_scale']`) — fires whenever the workstream completes without a handoff and has non-trivial substance. This is the primary trigger surface: any session that dispatched executors, touched shared schema, or produced more than ~50 LOC of code change lands here.
- `/handoff` is **not** a trigger surface, by PM ruling — a handoff diff is in-flight by definition, which is the state least worth reviewing: findings against half-finished work are noise the successor re-adjudicates against whatever they finish. Handoff-authored work gets its review coverage here, at the terminus surface, once the diff has settled.

## Diff-shape decision table

EM judgment with anchored ranges — the numbers below are decision anchors, not hard thresholds. A 51-LOC change with a clean shape does not obligate escalation; a 49-LOC change touching a public schema seam does not release from review.

| Session shape | Default scale |
|---|---|
| Doc-only edits, lesson capture, no executor dispatched, no code touched | **None** |
| Single-file fix <50 LOC, no shared schema touched, no executor | **None** (but commit message names the change) |
| Any executor dispatched, OR >50 LOC code change, OR shared schema/seam touched | **`code-reviewer`** (Sonnet, locked — see `agents/code-reviewer.md`) |
| **Big-diff brightline** — any one of: ≥500 gross LOC (insertions+deletions), OR ≥5 commits, OR ≥4 distinct surfaces (e.g. bash + JSON + tests + doctrine). **Code-only — `.md`/`.yaml`/`.yml` excluded before counting** (see below); a hand-derived figure that includes them overshoots. File count is reported by the gate for context but is NOT a trigger; mass-renames touch many files at zero review-cost. | **Partitioned `code-reviewer` — mandatory, not chain-end-gated** (SKILL.md § Partitioning large surfaces) |
| Chain-end (started with `/pickup`, ending without `/handoff`/`/spinoff`) AND chain diff is non-trivial | **`code-reviewer`** on chain diff |
| Chain-end AND chain diff exceeds the big-diff brightline | **Partitioned `code-reviewer` dispatches**. Named reviewers are for plans/architecture — Sonnet `code-reviewer` is the ceiling at workstream-complete |

**Precedence rule:** the big-diff brightline (row 4) and chain-end rows (5, 6) override workstream-complete rows (1, 2, 3) when they apply — partitioning is the integration-risk control, not a chain-end privilege.

**Anchored-ranges note:** the small-side anchor (50 LOC at row 3) is a calibration anchor — shape can pull a 49-LOC change in or release a 51-LOC change out. **The big-side brightlines (≥500 gross LOC / ≥5 commits / ≥4 surfaces) are hard floors, not calibration anchors.** Above the brightline, single-reviewer is a doctrine violation regardless of how coherent the diff feels — `gates['review_scale']` carries the engine-measured `gross_loc`/`commit_count`/`surface_count` an EM reads before picking a row.

**Hand-derived figures overshoot:** a hand-derived gross figure will exceed the floors (one close: 990/6 by hand vs the gate's 225/4) and read as under-measurement. The verdict string discloses none of this; asked of claude-klabauter.

**Why the gate keys on `commits` and `surfaces`, not raw file count.** File count is a blunt proxy for review-cost — a mass-rename touches many files at zero cost, while a 1-file 800-LOC change is genuinely large. `commits >= 5` tracks independent logical slices, the unit slicing actually operates on. `surfaces >= 4` (rather than 3) avoids tripping on hook-fixes, which routinely span shell+test+wiki at zero genuine breadth. The worked counterexample below still trips under this shape (loc=890, commits=7); a small, coherent diff that merely touches several file types does not.

**Worked counterexample (claude meta-repo).** A workstream-complete session shipped 2156 insertions / 26 deletions (2182 gross LOC) across 21 files spanning bash + JSON + tests + doctrine, in 7+ commits. The EM read row 3 (`>50 LOC OR executor dispatched`), satisfied it, and dispatched a single `code-reviewer`. The PM caught it pre-completion. Under the current (post-recalibration) gate, LOC is 4.3× over the floor and commits trip clean — partition would have been mandatory. The mechanical gate in SKILL.md exists so this shape can never again be reasoned-around.

## A partition verdict is answered by slicing, never by narrowing

*From `cross-repo/inbox/2026-08-04-project-rag-em-mise-phase6-review-does-not-scale-with-baton-count.md`.* Two rules, both learned the expensive way. Greppable token: `SLICE_NEVER_NARROW`.

**1. `/mise-en-place` Phase 6 and `/workstream-complete` § Review are not interchangeable.** Phase 6 reviews **the run's own diff**; this ceremony reviews **the chain diff** — that work plus its ancestry. Both are owed, and neither discharges the other. The trap is specific and sharp: a `/mise` run ends with a *mandated* review, so the EM arrives at close having just satisfied a review obligation, which reads as satisfying *the* review obligation. In the reporting run, the Phase-6 review over a 5027-LOC session diff returned **zero** findings; the chain-scoped partitioned review over the same work plus ancestry returned **eight**, across three of four slices — test surface, non-workstate code, and specs/decision records. Not a weaker version of the right review; a different, smaller one. Both skill bodies now carry a one-sentence pointer at the other.

**2. Never answer a partition-mandatory verdict by reducing scope.** On a shared `work/*` branch the foreign-session guard legitimately refuses a trail record spanning peer commits (§ `sha_range` in SKILL.md). The documented answer is per-slice records over one's own commits (`<sha>~1..<sha>` — `~1`, never `^`: cmd.exe eats a literal `^` in argv on Windows). The failure mode is using that legitimate refusal to *narrow the reviewed diff* instead — which conveniently also shrinks what gets reviewed. **The guard constrains what may be recorded, not how much must be reviewed.** If a guard blocks a contiguous range, slice it. And where a partition legitimately excludes ceremony bookkeeping — in the reporting chain, 227 files / 31043 insertions of review-trail JSON, subagent sidecars, and memo/handoff frontmatter — **the exclusion and its LOC must be stated**, because a silent narrowing reads as coverage. Same class as the § Bookkeeping-commit partition rule below, applied at review-scope time rather than at coverage-verdict time.

**Why `/mise` bites hardest here:** it is a no-stopping autonomous run, Phase 6 is the last checkpoint before the EM relinquishes control, and the EM reaching it has just watched twenty-odd items go green under per-item verifiers. Everything about that moment argues "this is done." A floor phrased as "at minimum one reviewer" becomes a ceiling the instant it is met — hence the tier-vs-count wording now in PIPELINE.md § Phase 6.

## The review-owed close trampoline

*Self — a PM catch on a workstream that capped with `PARTITION-MANDATORY reviewers_required=4` and zero reviewers run.* Greppable token: `REVIEW-OWED-CLOSE-TRAMPOLINES`.

**The rule.** When this ceremony names a review scale the session cannot run *and* integrate in remaining context, it does not cap. It stops, and `/handoff` passes the whole ceremony to a successor whose remit is *run the owed review, then cap*. That is the only reason `/workstream-complete` ever ends without capping, and the only sanctioned exit under context pressure. **The gate is context, nothing else** — with context to spare, the review belongs in this session, and reaching for the trampoline to avoid a tedious four-reviewer dispatch is the ordinary deferral trap wearing a ceremony costume.

**Before this fix, `/handoff` and `/workstream-complete` each refused the same case and pointed at the other — re-closing either side alone restores that trap.**

**`verdict: pending` is not the escape hatch.** It belongs to a review that is open and will close, never one nobody will run; consumers checking for a record rather than a verdict read it as coverage. `reviewer: waived` paired with a non-`waived` verdict is worse than either field alone — one says no reviewer is coming, the other says one is.

**Tells, all meaning stop and take the trampoline:** a sentence forming that says the next session can review this; a range narrowed to one commit because the honest range was refused; "mandatory" reasoned about as advisory; a trail record composed before any reviewer was dispatched.

Enforcement today is these two skill bodies — prose, i.e. the operator remembering. The engine-side refusal, and the fact that a review owed by one session and paid by another cannot record trail coverage at all, are asked of `claude-klabauter`.

## No named-reviewer escalation from code review

Named reviewers (the Staff Engineer, personas) are for plans and architecture, not code output. Sonnet `code-reviewer` is the ceiling at workstream-complete — for any diff size, partition across as many `code-reviewer` slices as needed, but do not escalate to a named reviewer.

If `code-reviewer` surfaces an architectural finding, capture it in `state/lessons/` and surface to PM for a plan-shaped decision. The finding belongs in the planning stream, not the code-review stream.

The weekly `/workweek-complete` Step 7 parallel-code-review is the merge-gate ceremony — **N code-semantics chunk reviewers (Sonnet `code-reviewer-weekly`, partitioned over the narrowed scope) + 3 mechanical workers (security-audit-worker, dep-cve-auditor, test-evidence-parser) → no-rewrite synthesizer**. The Staff Engineer is NOT in the gate — consistent with "named reviewers are for plans/architecture, not code output" above; they run a separate advisory architecture pass at Step 7.5 (fed by the synthesizer's `arch_tier_candidates` + `convergent_findings` + the seam set), which surfaces spinoff candidates but never blocks merge. The gate runs at merge time regardless of workstream-complete coverage — it is NOT a deferral path. Workstream-complete review happens at workstream completion; the merge gate is a separate, independent ceremony.

## Anti-ceremony-bias tripwire (code-reviewer-skip direction)

> "If you're considering skipping `code-reviewer` because the diff feels small or 'we already reviewed the plan' — run `code-reviewer`. Plan-time and post-implementation review catch different defect classes; the marker trail records `verdict=ok` in seconds when there's nothing to find. `code-reviewer` is the floor on row-3+ sessions, not a negotiable add-on."

**Doctrine-table defaults are defaults, not negotiation starting points** — for `code-reviewer`. The EM has waive authority for genuinely shallow diffs (one-line rename, mechanical typo fix), but "I already did plan-time review" and "the workstream felt small" are not waive grounds for *`code-reviewer`*; they are the rationalization shapes the anti-ceremony bias takes. Plan-time and post-implementation review catch different defect classes (§ Why post-implementation review is not redundant). The Staff Engineer-escalation above `code-reviewer` is a separate question governed by `code-reviewer`'s actual output, not by ceremony intuition — see § Post-code-reviewer the Staff Engineer-escalation criteria.

## Why post-implementation review is not redundant with plan-time review

EM judgment on row 3+ keeps waive authority for genuinely shallow diffs (a one-line rename caught by an executor, a mechanical typo fix, a single-file refactor with obvious shape). The diff-shape table's defaults stand; this section names four recurring rationalization patterns that look like judgment but are actually shape-mismatched substitutions, so future EMs can pattern-match against them.

**1. Plan-time review and post-implementation review catch different defect classes.** They are complementary, not substitutional.

- Plan-time (prior-art-checker + the Staff Engineer on the plan): catches architectural shape, prior-art conflicts, substrate verification — *what we're about to do*.
- Post-implementation `code-reviewer` on the diff: catches what executors actually did vs. what the plan said — substitution misses, integration-seam mismatches between workstreams, scope creep, executor cleverness where mechanical was wanted.

If a waive rationale boils down to "the plan was already reviewed," that's the substitution error: the plan is reviewed; the diff is not.

**2. Mechanical executor self-acceptance gates are not review proxies.** Grep returns 0, pytest passes, `bash -n` clean — these are correctness floors, not the lens a reviewer brings. None of them exercise cross-file integration, schema-vs-consumer agreement (e.g. did the producer schema in segment 2 actually match the consumer probe in segment 4 — *both green individually* doesn't mean *consistent across the seam*), or scope-creep detection. Treating mechanical gates as a stand-in for review collapses two distinct safety properties into one.

**3. "`code-reviewer`-after-already-doing-plan-review feels like ceremony — skip" is the ceremony-bias shape that matters at workstream-complete.** The *`code-reviewer`-skip* direction is the live tripwire — ceremony-feeling is the tell for skipping a review that should happen. There is no the Staff Engineer escalation path from code review to balance against; `code-reviewer` is both the floor and the ceiling.

**4. "We've done a lot of review already" is the shape wrap-up pressure takes.** At `/workstream-complete`, token-budget anxiety and session-fatigue create implicit "close out" pressure. Dressed up, that becomes "distributed coverage upstream was sufficient." Bare, it's: one more dispatch felt like one more thing. Naming this pattern explicitly is the durable fix — future EMs hitting the same pressure can recognize the shape.

**5. "The handoff says the Staff Engineer reviewed it" — plan-vs-code conflation at chain-ends.** When reading a predecessor handoff, a "the Staff Engineer review → N findings folded" note refers to the *plan* the Staff Engineer reviewed before executors fired. Plan-level reviews do not appear in `state/review-trail/*.json`. The trail is the mechanical boundary: if no trail record exists for a sha-range, that range has no code-output coverage regardless of what handoff narrative says about plan-level reviews. This variant fires specifically at chain-ends, where the EM scans the chain's review history and sees "the Staff Engineer reviewed" without distinguishing plan-review from diff-review. The tell: the cited review refers to a `docs/plans/*.review-the Staff Engineer.md` or a plan critique, not a `code-reviewer` dispatch. The Staff Engineer judging the plan before executors fired is *design intent* coverage; it says nothing about what the executors actually produced.

**The pattern-match tell:** if the EM is drafting a "waiving with rationale" sentence on a row-3+ session, the rationale itself is the tell. Compose the sentence; read it back; if it leans on plan-time coverage, executor gates, distributed/heavy upstream review, or "we've already done a lot" — run the `code-reviewer`. It's one dispatch. The marker trail records `verdict=ok` in seconds and downstream load-shedding still benefits.

**Summary.** Plan-time review (coordinator:plan pre-flight) and post-impl review (workstream-complete `code-reviewer`) catch different defect classes — pre-flight finds substrate/path/framework mismatches, post-impl finds integration/test-coverage/edge-case gaps. Doctrine-table defaults are defaults, not negotiation starting points; don't drop workstream-complete review because "pre-flight passed."

**Worked example.** A multi-executor session shipped a substantial workstream with plan-time prior-art-check (7 findings folded), plan-time the Staff Engineer review (8 findings folded), per-executor self-acceptance gates (all PASS), and a final-segment validation including an OOM smoke test. The EM waived workstream-complete `code-reviewer` on the rationale "distributed coverage upstream." The audited holes: a the Staff Engineer plan-time finding had been factually wrong (the executor caught it — meaning plan-review surface had a leak that *more downstream eyes*, not fewer, was the right response to); one executor segment swept up unrelated concurrent work whose commit message described only the headline change; the OOM smoke passed in 8s of a 600s budget without verifying it had actually exercised the install path vs. short-circuiting on cached state. None of these were catchable by plan-time review or by mechanical executor gates. They were exactly the class of finding a fresh `code-reviewer` lens on the actual diff catches.

## Dogfood as a structurally distinct review surface

*Self.* For code that runs against the operator's live environment — doctor probes, installers, MCP wiring, CLIs that mutate user state — plan-review and post-implementation code-review are *not* sufficient. Dogfooding (running the code end-to-end against a real environment, per `dogfooding-doctrine.md`) catches a distinct class of defects:

- Plan-review catches design errors.
- Post-impl code-review catches integration errors.
- **Dogfood catches reality errors** — assumptions about the operator's machine state that no static review can verify (interpreter resolution, registry layout, network timing, file-system permissions).

Three cycles on the same artifact (plan-review + code-review + dogfood) routinely surface progressively different defect classes on operator-environment code. Dogfood should be treated as a **required review surface** for any code in this class, not an optional last step. Operator-environment code includes: `doctor` skills, install/setup scripts, MCP server bootstrap, CLI commands that mutate user state outside the working tree.

Companion: `dogfooding-doctrine.md` carries the binary-outcome rule and the smoke-driven fix-through loop.

## Findings disposition — fix everything, including nitpicks

A reviewer verdict of `OK` with N "below blocking threshold" observations is not a license to commit and move on. Those observations *are* the review output. The diff is fresh, the EM has context, and folding them in now costs a fraction of what they cost three weeks later when someone is hunting the bug they hinted at.

**Rule:** all findings of any severity fold in via `coordinator:review-integrator` before the marker-trail write. P0 / P1 / P2 / nitpick / observation / note / "consider" — same treatment. The integrator escalates real disagreements; it does not silently skip on severity.

**The only legitimate skip path** is a real tradeoff that escalates to PM per `global-doctrine/CLAUDE.md` § Flag Severity, "Reviewer findings — apply, don't ratify": cost/value, scope/polish, architectural direction. "Recorded below blocking threshold" framing in an EM wrap-up sentence is the tell that this rule was skipped — re-open the diff, fold the findings, then write the marker.

**Verdict semantics under this rule.** The marker trail's `verdict` field records what the reviewer found on the *pre-fix* diff (`ok` / `warn` / `blocked`), not what shipped. The verdict is a downstream load-shedding signal; the trail is not a fix-completion log. A pre-fix `verdict=ok` with three observations all folded in is the expected shape, not a contradiction.

## Reviewer option-sets are bounded by the brief — the EM may synthesize a third shape

A reviewer's enumerated options (do A, or do B) are bounded by the reviewer's brief and framing — they are not an exhaustive map of the decision space. When neither named option is right, the EM may synthesize a third shape the reviewer didn't surface; doing so is *application* of the review, not contradiction of it. The reviewer's value was exposing the tension, not pre-enumerating every resolution. (This is the inverse of rote ratification — the EM neither rubber-stamps option A nor treats the A/B menu as closed.) Pairs with `global-doctrine/CLAUDE.md` § Flag Severity, "Reviewer findings — apply, don't ratify". Source: example-game-workbench-repo.

## Re-check for overlapping peer spinoffs at workstream-complete — pickup-time reconcile is point-in-time

A routed-plan / handoff reconcile done at `/pickup` is **point-in-time**: it correctly reflects the handoff/spinoff landscape at the moment the session started, but a concurrent peer session can fork a handoff for the *same scope* while you plan, review, and execute. The pickup-time "no overlapping handoff exists" finding does not stay true.

**Rule:** at `/workstream-complete`, re-run the overlap check against `state/handoffs/` — do not trust the pickup-time reconcile as still-current. The empirical instance (project-rag): a pickup-time reconcile correctly found no host-work handoff for a scope (none existed yet); ~25 min later, while the EM planned and reviewed, a peer recovery session created one for the *same* scope and a third folded that scope into a spinoff — so at workstream-complete there were **three** overlapping handoffs. No code was duplicated (the shared file was confirmed untouched before commit), but the EM had authored a duplicate handoff that a workstream-complete re-check would have caught. This is the handoff-lineage analog of the § Multi-session shared-branch union-coverage hazard: concurrent peers on a shared branch mutate the landscape *during* your session, so the terminal ceremony owns the re-verification, not the entry ceremony.

## Marker trail mechanics

Every completed workstream-complete review writes a small JSON record to disk. The trail is the machine-readable substrate that lets downstream ceremonies compute coverage without re-reviewing already-reviewed work.

**Per-session record shape:**

```json
{
  "sha_range": "abc123..def456",
  "reviewer": "code-reviewer|staff-eng|code-reviewer+staff-eng|em-verified|waived|ubt-compile|wsc-auto-adjudication",
  "scope": "chain|session|workstream-close-auto",
  "verdict": "ok|warn|blocked|waived|pending",
  "diff_loc": 247,
  "session_id": "..."
}
```

> **RETIRED — read this section as archaeology, never as instruction.** `review_trail.write`
> and `coordinator-write-review-trail.py` are a kill-ledger K-060 gravestone (DR-372/DR-374) with
> `Returns-when: Not applicable` — the replacement DR-372 built is the `review_receipt:` block a
> dispatched reviewer stamps into its own sidecar, which `gates.review_receipt` reads and
> `jp-review-receipt-block-stamp` gates the terminal stamp on. Dispatching the reviewer IS
> recording the review; nobody writes a trail record. The op id is still dialable because draining
> it from its five registration surfaces is unfinished follow-on work, so calling it returns a
> refusal naming the dead surface — that refusal is not a verdict about your close. Everything
> below describes the retired mechanism and is kept for readers tracing why a `state/review-trail/`
> file exists. Tripwire: `A-SUSPENDED-OP-IS-NOT-A-MECHANISM-TO-WAIT-OUT`.

Records land at `state/review-trail/YYYY-MM-DD-HHMMSS-{session-id-short}.json` (git-tracked, per-session, no concurrent-write risk — one file per session).

**Helper (historical — retired, see banner above):** `coordinator-write-review-trail.py` was a
pure-Python shape-(b) trampoline over the native `review_trail.write` op — named-arg interface:

```text
RETIRED — DO NOT RUN. Kept as a shape record, not an invocation. The op behind this
refuses (-32006, K-060 gravestone); running it records nothing and tells you nothing
about your close. The live mechanism is the reviewer's own sidecar receipt.

    python coordinator-write-review-trail.py \
      --sha-range abc123..def456 \
      --reviewer code-reviewer \
      --scope chain \
      --verdict ok \
      --diff-loc 247 \
      --reviewer-evidence state/subagent-share/<session>/coordinatorcode-reviewer-<id>.md
```

`--reviewer-evidence` correlates the `--reviewer` claim with an artifact showing the review ran.
Delegate values (`code-reviewer`, `code-reviewer+staff-eng`, `staff-eng`, `ubt-compile`) take an
existing sidecar path under `state/subagent-share/` or `state/plan-sidecars/`, or a dispatch id
matching column 1 of this session's own `dispatched-agents.txt`. `em-verified`/`waived` take ≥20
characters of justification instead. Exempt: `wsc-auto-adjudication`, and a delegate reviewer at
`--verdict pending`. The value gates the write and is not persisted into the record.

Session-id resolution uses strict precedence, env-only: `CLAUDE_SESSION_ID` (explicit override) first; then `CLAUDE_CODE_SESSION_ID` (platform-injected, per-session, unclobberable — Claude Code ≥ ~2.1.150) — resolved server-side by the native op (`coordinator_core/ops/session_context.py:resolve_current_session_id`, claude-klabauter). An unresolvable session id is reported as unresolved rather than papered over. The write is additive-create/last-write-wins: same timestamp + session-id-short → same filename → the new write overwrites atomically (no collision-fail).

**Reviewer enum current values (post the persona-to-role-slug migration; source of
truth: `_VALID_REVIEWERS` in claude-klabauter's `coordinator_core/ops/review_trail_write.py`):**
`code-reviewer | staff-eng | code-reviewer+staff-eng | em-verified | waived | ubt-compile | wsc-auto-adjudication`

`em-verified` names a review the EM performed directly — distinct from `waived`, which asserts
none happened. Consumers weighting trust by `reviewer` read it as weaker than a delegate reviewer,
stronger than a waiver.

Historical JSON records written before 2026-05-18 retain `reviewer: "sonnet"` as data. No back-compat read path is required — historical records are not consumed by the weekly prelude's sha-range logic. New writes must use the current enum.

The `code-reviewer` value refers specifically to a dispatch of `agents/code-reviewer.md` (Sonnet-locked, read-only). Do NOT substitute a generic Sonnet dispatch and label it `code-reviewer` — the agent file is the contract.

**Daily roll-up (historical — this mechanism is retired, see banner above):** `/workday-complete`
Step 9 used to read the day's review records by walking `state/review-trail/` and
`archive/review-trail/**` (unioned — this covered the morning-after-weekly-reset edge case) and
emit one `**Reviewed:**` line per record into the day's changelog block. No trail record has been
written since the writer's retirement, so this step now has nothing to read:

```
**Reviewed:** sha_range=abc..def reviewer=sonnet verdict=ok diff_loc=247
```

If no review records exist for today AND today had non-trivial commits, Step 9 emits `**Reviewed:** none — flag for /workweek-complete Step 7`.

**Weekly archival:** `/workweek-complete` Step 13 moves `state/review-trail/*.json` to `archive/review-trail/<week-starting>/` as part of the same archival sweep that moves `state/week-changelog/`. Archival happens AFTER Step 7 has consumed the trail (Step 7 runs before Step 13).

**Handoff frontmatter mirror:** when a workstream-complete review fires AND a handoff is also written for this session, the handoff receives a `reviewed_at_workstream_complete:` frontmatter field for audit-trail durability with the content:

```yaml
reviewed_at_workstream_complete: abc123..def456 sonnet 2026-05-08
```

This field is optional; handoffs without it are valid (field is only present when a review was performed in the same session that authored the handoff).

## Downstream load-shedding contract

`/workweek-complete` Step 7 prelude reads the trail before dispatching `coordinator:parallel-code-review`. The prelude narrows the **code-semantics** scope, chunked across N `code-reviewer-weekly` instances; the three mechanical workers always run on the full week diff regardless.

**Prelude logic (Step 7, external to `parallel-code-review` skill body):**

```
1. Glob state/review-trail/*.json for the week's date range.
   (intentional: Step 7 runs before Step 13 archival in same invocation — live dir is complete at this point)
2. Compute union of reviewed sha_ranges → reviewed_set.
3. weekly_diff_shas = git log origin/main..HEAD --format=%H
4. unreviewed_set = weekly_diff_shas - reviewed_set
5. cross_segment_seams = files modified in ≥2 different reviewed segments
6. code_semantics_scope = unreviewed_set + cross_segment_seams
   mechanical_scope = full week diff (always)
7. Write state/review-trail/.weekly-reviewer-scopes.json:
     {"staff_eng": "<scope_sha_list>", "staff_eng_seam_files": "<seam_paths>", "mechanical_workers": "full"}
   (The JSON keys are role slugs, not persona names — renamed producer-side 2026-08-04
   (claude-klabauter `a78271b1a`) with no back-compat shim. The `staff_eng` SHA set is the
   code-semantics CHUNKING input; `staff_eng_seam_files` additionally feeds the Staff Engineer's advisory
   Layer-2 pass at Step 7.5.)
   Pass this scope file in the brief to parallel-code-review.
   The synthesizer reads it and narrates:
     "code-semantics chunks scoped to gap+seams; mechanical workers full diff."
```

The `parallel-code-review` skill body IS modified for the N-chunk model (Strand 1), but the doctrine-guarded carve-out from `archive/specs/2026-05-06-parallel-code-review-weekly-gate.md` is preserved: scope-narrowing still happens in Step 7's prelude, and the frozen-diff / orthogonal-lens / no-rewrite-synthesizer conditions still hold (orthogonality now spans the 3 specialist lenses + code-semantics-as-a-class; the N chunks partition that class disjointly by file-scope).

**`cross_segment_seams` defined precisely:** a *segment* is the sha-range of one trail record (one workstream-complete review). Cross-segment seams are the set of file paths that appear in the diff of ≥2 distinct segments — computed by taking the union of files-touched per record and intersecting pairwise. The per-segment file-touch set is derived from `git diff --name-only <sha-range>`. These seams carry integration risk because multiple independent sessions touched them; they feed BOTH the code-semantics chunk review (seam-first chunking gives them extra integration scrutiny) AND the Staff Engineer's advisory Layer-2 pass at Step 7.5, which reads the seam set as an integration-surface signal but does NOT gate merge.

**Verdict subvariant:** when the code-semantics scope is empty AND no findings from any mechanical worker, the synthesizer may emit `OK (code-semantics trail-covered, mechanical clean)` — an informational subvariant of the standard `OK` verdict. The parallel dispatch still runs; no "skip" path exists. This variant signals that the trail successfully shed load without bypassing the safety gate.

**Why mechanical workers are never scoped down:** workstream-complete reviews dispatch only `coordinator:review-code` Branch A.2 (`code-reviewer`). The three mechanical workers (security-audit-worker, dep-cve-auditor, test-evidence-parser) never run at workstream-complete. "Trail-covered" therefore does not mean "all lenses covered" — it means "code-semantics lens covered." Narrowing mechanical workers based on the trail would silently elide their independence property.

## workweek-trail-scope.py — detect-then-fail-loud on segment-shape, not silent-pick on string proxy

The `workweek-trail-scope.py` prelude computes `cross_segment_seams` by intersecting per-segment file-touch sets across review-trail records. The original implementation used a string-shape proxy to decide whether a record was a "segment" — silently coercing ambiguous record shapes into a default arm.

**The detect-then-silently-pick footgun (see `coordinator/snippets/deletion-list-hygiene.md` for a related instance of the same footgun) applies here:** if a trail record's shape does not unambiguously identify it as a per-session segment (e.g. multi-line JSON variant, future schema migration, partial write), the prelude MUST fail loud rather than silently classify it. Silent classification produces a `code_semantics_scope` that omits real seam files, and the weekly gate runs with a too-narrow lens.

**Rule:** segment detection in `workweek-trail-scope.py` (and any future trail-shape consumer) fails on unrecognized record shape with a remediation message, not a default arm. The cost of a noisy false-positive is a Step 7 prelude that asks the EM to upgrade the trail-reader; the cost of a silent false-negative is a missed integration-seam at merge time.

Companion: "Detect-then-silently-pick is a footgun." Source: weekly-gate the Staff Engineer arch review (b3g-077).

## review-coverage-gate.py — chain-end mechanical coverage gate (RETIRED) <!-- guard-allow: directive-ids-are-engine-current — K-001/K-005 retired this gate; the section is a design record and every directive id in it is quoted as it stood, per its own banner below -->

<!-- spec-backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § Design -->

**RETIRED — absence is the operative fact, not an oversight.** `coordinator/bin/review-coverage-gate.py`
does not exist in claude-klabauter; the DoE-side `review-coverage-gate` forwarder exits 127.
Neither `/workstream-complete`'s `d-run-chain-coverage-gate` directive nor `/merging-to-main`'s
pre-merge step has a mechanical review-coverage gate to invoke — do not cite either as gated on
this mechanism, and do not restore it on the grounds it "looks like it should still work."
Provenance: claude-klabauter `state/kill-ledger.md` K-001, K-005. The rest of this section is a
historical design record (mechanics, footguns, verdict semantics), kept for a reader tracing an
old trail record's shape — none of it describes invocable behavior.

`bin/review-coverage-gate.py` was the chain-end mechanical gate that verified every commit in a workstream's chain diff was covered by at least one `code-reviewer` trail record. It ran at `/workstream-complete`'s `d-run-chain-coverage-gate` directive (scoped to the closing workstream) and at `/merging-to-main` as an unconditional pre-merge step.

### Mechanics

1. **Chain set:** `git rev-list --no-merges <merge-base origin/main HEAD..HEAD> [-- <scope-paths>]`. Merge commits are excluded via `--no-merges` (they carry no authored diff that requires review — this is an explicit design decision, not emergent behavior).
2. **Reviewed set:** reads ALL trail records (live + archived) via `bin/list-review-trail-records.py` (archive-aware — records move to `archive/review-trail/<week>/` after `/workweek-complete` Step 13; the gate must read both dirs). For each `scope_kind=diff` record with a valid `sha_range`, the shared `lib/review-coverage-core.py` computes `git rev-list <sha_range>` and unions → `reviewed_set`. Records with `scope_kind ∈ {plan, integration}` are skipped silently (no real sha-range).
3. **Verdict filter (shared core):** the shared core excludes `verdict=pending` from `reviewed_set`. A `pending` record means the review has not completed — counting it as coverage lets the gate pass on unreviewed commits. `verdict=waived` counts as covered (explicit PM waiver = a coverage decision). Verdicts `{ok, warn, blocked, waived}` all count.
4. **Uncovered set:** `chain_set − reviewed_set`.
5. **Output:** `range=… chain_commits=N covered=M uncovered=K VERDICT={COVERED|UNCOVERED}` on stdout. On `UNCOVERED`, one `uncovered: <sha> <subject>` line per gap on stderr. Exit 0 in both cases (verdict-line shape, same as `review-brightline-gate.py`) — the calling skill parses `VERDICT=UNCOVERED` and halts.

**`UNCOVERED` is currently a census, not a signal — do not halt on it, and do not
dispatch a reviewer off it.** `reviewed_set` is built from a corpus nothing writes to: `review_trail.write` is retired with no live writer, and reviews land in the
reviewer sidecar's `## Integrator Dispositions` receipt (DR-372 § 3) that this gate
cannot read. Every chain touching recent commits therefore returns a confident
`UNCOVERED` **whether or not it was reviewed**, so the verdict supports no reading in
either direction. Establish coverage from the sidecars under
`state/subagent-share/<session>/` instead, and record on the artifact what you found
and that the gate's verdict was uninformative.

**If you applied the findings yourself, there is no `## Integrator Dispositions`
block and that fallback is dead too** — the block is written by a dispatched
`review-integrator`, and the close skill permits an EM to apply findings directly.
`gates.review_receipt` reports this as "no integrator receipt (review ran, findings
not recorded as applied)", which reads as an annotation and is in fact the notice
that your fallback is gone. Then the evidence is the reviewer sidecars plus the
commits that cite them: **name every commit individually** — which reviewer covered
it, or which reviewed commit it applies the findings of, or that it is ceremony
bookkeeping. Never wave a set through as a class; "bookkeeping" is the word that
lets a genuinely unreviewed commit ride along.

**Write the substitute down every time.** The always-`UNCOVERED` gate is safe only
because nobody can act on it, and that is exactly what makes it invisible — the
failure is not a wrong verdict but every session privately inventing the same
workaround and none of them recording it. Dispatching a `code-reviewer` because
the gate said `UNCOVERED` spends review capacity re-deriving a verdict that already
exists — the same failure `plan-delivery-audit`'s Oracle 3 committed before
`d575c16a5`. Tripwire: `A-RETIRED-PRODUCER-LEAVES-ITS-READERS-ANSWERING`.

**Shared lib:** the coverage computation (SAFE_RANGE validator, per-record `git rev-list` union loop, JSON-OR-JSONL dual-shape parse) lives in `lib/review-coverage-core.py`, consumed by BOTH this gate and `lib/workweek-trail-scope.py`. The drift vector between the two gates is closed permanently: a naïve re-implementation would silently drop JSONL integrator-envelope records from `reviewed_set`, producing false UNCOVERED verdicts — sharing the core prevents this.

### Ceremony-bookkeeping commits do not hold the verdict — code, not paperwork

Review coverage is a question about code, not about the ceremony's own bookkeeping. A commit whose every touched path lies under `state/`, `archive/`, or `tasks/` — a completion entry, a review-trail record, a `shipped_in` stamp, a boot-sweep note, a pickup claim — has nothing in it a reviewer could meaningfully open.

**Where the partition happens — the verdict split, not chain-set derivation.** Bookkeeping commits stay in the chain set and are still counted in `chain_commits`. The partition is applied to the *uncovered* list at verdict time (`coordinator_core/coverage.py`, `run_coverage_gate`): uncovered commits are split into a code partition and a bookkeeping partition, and `VERDICT=COVERED` iff the **code** partition is empty. Do not read this section as saying the chain set shrinks — it does not, and a fix aimed at `_derive_dag_chain_set` would be aimed at the wrong place.

**Consequence for the counts.** Because the frozen verdict line `chain_commits=N covered=M uncovered=K` must keep its arithmetic (`covered + uncovered == chain_commits`), a bookkeeping commit is counted as *covered* in `M`. That is a deliberate, mild over-claim in the count, and it is the reason the accompanying note is not optional: the gate emits a note naming every excluded SHA. `CoverageResult.bookkeeping_shas` carries them structurally. **`coverage.gate`'s JSON-RPC op and the `state/coverage/gate-result.json` disk artifact are RETIRED** (kill-ledger K-001/K-005; claude-klabauter carries no `coordinator/bin/review-coverage-gate.py`) — there is no mechanical floor producing either artifact. See `docs/wiki/coordinator-tripwires/anti-literal-tripwires-fire-on-docstring-examples-apply-noqa-marker-during-tripwire-chunk.md` § CHAIN-END-COVERAGE-GATE for the retirement record and the substitute (establish coverage from reviewer sidecars under `state/subagent-share/<session>/`, not from a gate verdict). Read `M` as "not awaiting review," not as "opened by a reviewer."

**Mixed commits classify as code, always.** A commit touching both a bookkeeping path and anything else is code — the exclusion tests "every touched path is bookkeeping," not "any touched path is bookkeeping," so it fails closed by construction and cannot become a hole a real source change hides in.

**Why this was needed.** Every workstream that ran `/workstream-complete` acquired a permanent 2-3 commit uncovered tail, because the ceremony writes its own commits and those necessarily postdate the trail record that would cover them — the gate could therefore never return COVERED for any closed workstream. Observed live on 2026-07-26: a chain whose two uncovered commits were a `pickup-assemble apply:` handoff claim and a `session.boot_sweep:` orphan note.

**Bookkeeping is reported, not vanished.** The gate still names the excluded commits in its output — the exclusion changes what the verdict keys on, never what the operator can see.

**This does not make COVERED easier to reach as a goal.** The point is that the verdict means something: a gate that always says COVERED is worse than one that always says UNCOVERED, because the first is trusted. Excluding bookkeeping narrows the gate to the class of commit where an UNCOVERED verdict is actually informative.

### Chain-ancestry-waiver records (`state/review-trail/chain-ancestry-waivers/`) — reader is `claude-klabauter`-resident

**These records exist in DoE-claude but their reader does not.** `record_chain_ancestry_waiver`
(write side) and `chain_ancestry_waived_shas` (read side) both live in `claude-klabauter`'s
`coordinator_core/chain_ancestry_waivers.py` — DoE-claude has no local copy of either, by design
(§ Place in the fleet, `coordinator/CLAUDE.md`). A reviewer working from this repo alone cannot
open that source; treat any claim about the reader's parsing behavior as attributed, not
independently re-derivable here.

**2026-08-06 provenance for the `source_handoff` field specifically.** 15-then-28 waiver records
carried a machine-absolute `source_handoff` path, tripping the absolute-path-literal gate. Rewritten
repo-relative on the strength of a read of `chain_ancestry_waived_shas` at that date: it matches a
waiver on directory/`chain_id` and filename/`sha` only and never parses `source_handoff`, so the
rewrite is semantics-preserving. See commit `c3a437888` (the rewrite) and the cross-repo memo
`state/memo-outbox/sent/chain-ancestry-waiver-absolute-path.md` (root-cause ask: the write site,
`coordinator_core/chain_ancestry_waivers.py:206` via `coordinator_core/ops/coverage_gate.py:432`,
persists `from_handoff` verbatim and should normalize at the source instead of per-consumer). A
future review of these records should re-derive this from `claude-klabauter` directly rather than
citing this note as still-current — it is a snapshot of one verification, not a standing guarantee.

### The `A..B` per-commit footgun — net-new doctrine

**Endpoint-string comparison is the trap; per-commit `git rev-list` is correct.**

`git rev-list A..B` covers the half-open interval `(A, B]` — it lists commits reachable from `B` but NOT from `A`. This means `A` itself is NOT in the output. A trail record with `sha_range=A..B` does NOT cover commit `A`.

**Incident shape (project-rag-ue-addon):** record `76619a87f..df44968f9` covered C3→C5 + fixes. Because `A` (= `76619a87f` = C2's own tip) was excluded, C1 (`37798a455`) and C2 (`76619a87f`) — the 521-LOC correctness-critical core — were unreviewed. The trail *looked* like it covered the work.

**Why per-commit is correct:** `review-coverage-core.py` computes `git rev-list <sha_range>` per record and unions the resulting SHA sets. Commit `A` is covered only if some *other* record's range includes it as a right endpoint (e.g. a prior record `X..A` where `A` IS in `git rev-list X..A`). This is not a special case — it is the natural behavior of per-commit union coverage. The bug in the incident was the absence of any such prior record, which a per-commit gate surfaces immediately and an endpoint-string comparison silently misses.

**Negative-spec:** do NOT "fix" the recorded `sha_range` format to be endpoint-inclusive (e.g. by changing `A..B` to `A^..B` in the writer). The weekly gate and cockpit-tc-3 `ReviewTrail` reader both consume the existing format — changing it would break both consumers. The per-commit consumption in `review-coverage-core.py` handles the `A..B` boundary correctly by construction.

### Multi-session shared-branch union-coverage hazard

On a `work/<machine>/<date>` branch shared by concurrent EM sessions, a feature spanning multiple sessions produces multiple trail records — one per session. **Per-session trail ranges are NOT additive-by-assumption.** Session boundaries create gap-SHAs (session 1's terminal SHA is the left endpoint of session 2's record, but the terminal SHA itself is NOT covered by session 2's record per the `A..B` boundary above).

**Rule:** the chain-terminal session owns the union-coverage check. At `/workstream-complete`'s `d-run-chain-coverage-gate` directive, `review-coverage-gate.py` reads the `reviewed_set` as the UNION of ALL sessions' trail records (never session-filtered). If gaps exist at session boundaries, the terminal session is responsible for either:
- Verifying that a prior session's record covered the gap SHA as a right endpoint, OR
- Dispatching an additional `code-reviewer` pass on the uncovered commits before asserting merge-ready.

**Asymmetry note:** `review-brightline-gate.py` narrows to `--session-id` (avoids false PARTITION-MANDATORY on peer commits already reviewed). The coverage gate does the reverse — it widens `reviewed_set` to credit ALL sessions' reviews. This asymmetry is architectural, not accidental.

**Terminus narrowing coexists with session narrowing — two modes, not a replacement.** The `--session-id` narrowing above answers "does THIS session's own diff need partitioning" — correct mid-chain, where the chain hasn't closed yet and asking about the whole chain would double-count peer sessions' already-reviewed commits. It undercounts at a chain terminus, where the question changes to "does the WHOLE closing chain, across every session that contributed to it, carry enough reviewers." `/workstream-complete`'s `d-run-chain-coverage-gate` directive answers that second question with a distinct, additive mode — the two-oracle chain+plan detector — rather than by further tuning `--session-id`: session mode stays authoritative mid-chain (`/handoff`, and `/workstream-complete` when `WSC_DISPOSITION != chain-terminal`); chain+plan mode fires only at `WSC_DISPOSITION=chain-terminal`. See § Two-oracle chain+plan contract below for the full field/tier reference.

### Verdict filter — weekly-gate coverage must exclude pending verdicts

Computing `reviewed_set` for the weekly gate's load-shedding prelude must exclude `verdict=pending` records (e.g. a UBT compile marker written before the build resolves) — a pending record is not coverage, and counting it narrows `unreviewed_set` too aggressively.

The shared `lib/review-coverage-core.py` applies the verdict filter in one place; BOTH the chain-end gate AND `workweek-trail-scope.py`'s consumption inherit correct pending-exclusion from it. The filter is fail-safe: excluding a pending record moves its commits FROM covered INTO unreviewed → weekly gate reviews MORE, never less.

### `--scope-paths` narrowing risk and the unscoped `/merging-to-main` backstop

The gate accepts `--scope-paths <pathspec>...` so Step 2.9 can scope the chain set to the closing workstream's files (from the governing plan / handoff `scope:`). **`scope_paths` is honoured in BOTH flat mode and DAG mode** — flat mode narrows at derivation time (`git rev-list --no-merges <range> -- <paths>`); DAG mode narrows as a post-filter: `run_coverage_gate` (`coordinator_core/coverage.py`) first derives the full chain set via `_derive_dag_chain_set`, then, only `if scope_paths:`, calls `_filter_shas_by_scope_paths(dag_result.shas, scope_paths, cwd)` to narrow it — git's own pathspec matcher applied over the already-derived SHA set, not folded into derivation itself. The `reviewed_set` is never path-filtered in either mode — a commit reviewed by any session's trail record is covered regardless of path.

**Risk:** if `--scope-paths` is drawn from a stale or incomplete handoff `scope:`, commits that touched the workstream's real surface but fall outside the declared pathspec are excluded from `chain_set` and never checked — the scoped gate passes while leaving authored code unreviewed.

**DAG-mode filter failure is fail-closed to INDETERMINATE, never silently unfiltered or silently empty.** `_filter_shas_by_scope_paths` returns `(None, note)` on a git error during the pathspec match; `run_coverage_gate` treats `filtered is None` as fail-closed and returns `CoverageResult(verdict="INDETERMINATE", exit_code=2, ...)` rather than falling back to the unfiltered chain set (would silently defeat scoping) or an empty one (would silently drop the whole chain) — both of those fallbacks are exploit-shaped, per the function's own docstring.

**Backstop:** the `/merging-to-main` unconditional pre-merge gate runs `review-coverage-gate.py` UNSCOPED over `origin/main..HEAD`. This makes the `/merging-to-main` gate load-bearing for the whole design — the scoped chain-end gate is allowed to be permissive precisely because the unscoped merge gate is the floor. An empty or missing `--scope-paths` falls back to UNSCOPED whole-chain (detect-then-fail-loud, NOT silently scoped to nothing).

### `Deliverable-Id:` trailer — workstream-membership attribution in DAG mode

<!-- spec-backlink: coordinator/docs/wiki/resolves-commit-trailer.md § Sibling precedent — Deliverable-Id: trailer -->

`_derive_dag_chain_set` (`coordinator_core/coverage.py`) Step 3 computes each node's commit segment. For a node whose handoff carries a `deliverable_id`, the segment is the union of (a) commits carrying a matching `Deliverable-Id:` trailer (`git log --grep=^Deliverable-Id: <id>$`) and (b) commits already matched by the node's `Session-Id:` that carry **no** `Deliverable-Id:` trailer at all — the legacy-history fallback. Nodes without a `deliverable_id` keep the plain `Session-Id:`-only segment, byte-identical to prior behaviour.

**Forward-only.** Leg (b) is what keeps every commit made before this trailer shipped — and every commit from a workstream that never adopts `deliverable_id` — attributed exactly as it was under the old Session-Id-only rule. This closes the gate to *new* false positives; it does not retroactively re-derive or clear old chains' verdicts. Do not read a passing verdict on an old chain as having been re-checked under the new rule — it wasn't.

**Attribution follows the work, not the typist.** A commit stamped with a matching `Deliverable-Id:` attributes to that workstream even when a different session's `Session-Id:` is on the same commit — this is the fix, not an edge case of it. It exists because Session-Id-only attribution conflated "who ran `git commit`" with "what the commit was for": a session that spun off a baton and also shipped unrelated work donated all of it to the spinoff's coverage obligation. Reported independently by project-rag and example-cockpit-repo.

Full trailer-family writeup (vs. `Resolves:` and `Session-Id:`): `coordinator/docs/wiki/resolves-commit-trailer.md` § Sibling precedent — `Deliverable-Id:` trailer.

### `--on-record-error skip|fail` resilience policy

The chain-end gate scans the FULL archive (potentially hundreds of historical records from weeks or months of work). Historical trail dirs can contain:
- Files that parse as neither JSON nor JSONL (concatenated objects, sidecars sharing the trail dir)
- Records whose `sha_range` references an unresolvable git ref (literal `..WORKING` placeholder, GC'd SHA, rebased commit)

Both make `git rev-list` or the parser hard-exit, which would abort the whole gate on one ancient archived record — an unusable gate.

**Policy:** `lib/review-coverage-core.py` accepts `--on-record-error skip|fail`. The lib default is `fail`. Each consumer passes the flag EXPLICITLY — removing the flag from either consumer would change its behavior back to `fail`.

- **`skip` (chain-end gate's explicit default):** `review-coverage-gate.py` passes `--on-record-error skip` explicitly. Warn-and-continue on an unprocessable record. Fail-safe: an unparseable/unresolvable record credits NO commits → those commits surface as MORE review (the uncovered direction), never less. Skips are announced per-file on stderr, never silent.
- **`fail` (weekly gate's explicit default):** `lib/workweek-trail-scope.py` passes `--on-record-error fail` explicitly (or omits the flag, inheriting the lib default). Detect-then-fail-loud, consistent with `workweek-trail-scope.py`'s documented doctrine. The weekly gate scans only the narrow current-week live dir (Step 7 runs before Step 13 archival in the same invocation), so a malformed record there is a fresh defect that should halt and be fixed.

The asymmetric behavior is deliberate — the same core, correctly configured for each consumer's scan scope and failure semantics. If you remove `--on-record-error skip` from the coverage gate invocation, it silently changes to `fail` behavior.

### The gate is an oracle, not a lock

Both `review-coverage-gate.py` and the two-oracle brightline gate (§ Two-oracle chain+plan contract below) compute a mechanically-trustworthy verdict, but neither one enforces it. Verified across both repos: `coordinator_core/ops/ceremony/tail_ops.py:698` states the ceremony continues on either verdict — "never a hard gate"; `coordinator_core/ops/ceremony/receipt_schema.py:30` does not gate the receipt on coverage; in `coordinator_core/workstream_complete/__init__.py` the commit directive `d-tail` carries no dependency edge on the coverage gate directive; `wsc-close` does not consult coverage at all, and `wsc-tail` has no coverage flag on its trampoline. The runner's `exit 1` is consumed by no op, hook, or write guard — consistent with § Mechanics step 5 above, which already documents that the gate exits 0 in both COVERED and UNCOVERED cases and that it is the calling skill's `VERDICT=UNCOVERED` parse that halts.

**What this means in practice:** the verdict is a computed, trustworthy signal; the halt is prose addressed to the EM, whose compliance is the whole enforcement mechanism. Whether that should change — whether the gate should become an actual hard stop — is an open PM decision, not something this doctrine resolves; this section records the current mechanism honestly, not a recommendation either way.

## Three-Surface Composition — Automated Build Verdicts (UBT pattern)

The review trail accommodates automated build-quality checks via a deferred three-surface
composition. The UBT compile gate is the first example; future automated linters (`clippy`,
`eslint`, `pytest-coverage`) follow the same shape.

### Motivation

Running a UBT build (~30s incremental, low-minutes cold) at workstream-complete blocks quick-save
commits under the concurrent-EM cadence (`state/lessons/:324` — "at most one UBT-dependent
executor in flight"). The three-surface pattern decouples intent-capture (cheap, workstream-complete)
from build-execution (expensive, daily) from gate-enforcement (cheap, weekly).

### Three surfaces and their roles

| Surface | Role | Cost | Trigger |
|---|---|---|---|
<!-- guard-allow: directive-ids-are-engine-current the row documents a RETIRED leg; naming a live id here would assert a wiring that no longer exists -->
| ~~`/workstream-complete`'s `d-run-ubt-pending-check` directive~~ **RETIRED** | Wrote a `verdict=pending` marker if the chain-diff touched `control/plugin/**/Source/**/*.{cpp,h}` | — | **Nothing writes the marker today** |
| `/workday-complete` Step 0c | Resolve today's pending markers — run UBT, parse result, write new resolved record | ~30s incremental | Daily |
| `/workweek-complete` Step 4c | Refuse merge if any `verdict=pending` records have NO resolved sibling | Cheap (scan) | Weekly |

### Cost profile

<!-- guard-allow: directive-ids-are-engine-current same retired leg as the table row above -->
**The writer leg is gone, so this chain currently starts at its second link.** `d-run-ubt-pending-check` was removed from `/workstream-complete` along with its CLI: the directive named `scan_unresolved_ubt_records.py` as its `cli` and no such script ever existed on disk, so the gate could not fire and reported success anyway — the worked example in `coordinator-tripwires/phantom-cli-guard-seam.md`. The op it fronted (`review_trail.scan_unresolved_ubt`) still exists and is still callable; what no longer happens automatically is the per-session marker write. Read the two rows below as a resolver and a merge gate over a marker set nothing is currently populating, and see `state/bug-backlog/2026-09-01-ubt-pending-chain-lost-its-writer-leg.yaml`.

The asymmetry the table records still holds for the pattern: the writer leg was "Cheap (no build)" — a marker write, not a test tier. The full-tier run this pattern exists to gate happens at `/workday-complete` Step 0c, one of the three ceremonies holding an implicit Tier-U grant; `/workstream-complete` holds none and stays test-free → `docs/wiki/test-design-discipline.md § The Three Implicit-Grant Ceremonies`.

### Two-record model (never-overwrite)

Pending and resolved are distinct files. The pending marker is NEVER mutated after creation.
Resolution writes a NEW `<base>.ubt-compile.resolved.json` alongside the pending file.
`/workweek-complete` Step 4c scans for pending-without-resolved-sibling pairs (not raw
`verdict=pending`), so a resolved pending record is not a merge blocker.

**Filename shape:** `YYYY-MM-DD-<nanosecond-timestamp>-<sha-fragment>.ubt-compile.pending.json`
and `<same-base>.ubt-compile.resolved.json`. Nanosecond precision eliminates concurrent-session
write collisions by construction.

### Automated-check reviewer naming convention

Automated-check reviewers are mechanism-named (`ubt-compile`, not `automated-check`). This
prevents enum ambiguity when `clippy`, `eslint`, or `pytest-coverage` each add one entry.
Each adds exactly one closed-enum value to the native `review_trail.write` op's `reviewer`
enum (`coordinator_core/ops/review_trail_write.py:_VALID_REVIEWERS`, claude-klabauter).
Pattern established by Chunk 0 of the UBT plan (DR-UBT-001).

### Detection signature — file-path, not workstream name

The pending-marker trigger detects diff files matching `control/plugin/**/Source/**/*.{cpp,h}`
(including `Tests/` subdirectories — TC-6 demonstrated test-side include-rot is a real failure
class). Workstream name / commit-message prefix matching is explicitly rejected: it would fire
pointlessly on TS-only stubs and miss future workstreams that drop the `tc-` prefix.

### Presence-detection gate

Coordinator skill bodies invoke the gate via a presence-check (`[ -x <path> ] && <path>
[args]`) against the UE build-freshness script. Absent script → graceful no-op so non-UE
repos see no change. See `docs/wiki/example-game-repo-doctrine.md §7.7` for the full convention.

### Verdict semantics extension

<!-- Review: code-reviewer — historical snapshot of the enum at the time `ubt-compile` was
     added; the persona spellings below (`the Staff Engineer`, `code-reviewer+the Staff Engineer`) are the pre-2026-08-04
     names and are retired on the wire today (see § Marker trail mechanics above for the current
     enum). Left as-is because it documents what the enum looked like at the moment of this past
     extension, not current guidance. -->
`--verdict` enum extended with `pending` (alongside `ok|warn|blocked|waived`).
`--reviewer` enum extended with `ubt-compile` (alongside `code-reviewer | the Staff Engineer | code-reviewer+the Staff Engineer | waived`).
`--scope chain` (existing value — UBT verdicts are chain-scoped, not per-diff-slice).

Spec backlink: `docs/plans/2026-05-15-ubt-compile-gate-review-trail.md` §Shape.

## Boundary-relabeling defect class — a cross-segment seam signal

Chain-end review empirically catches **boundary-relabeling** bugs — where a refactor renames a failure-reason enum, retypes an error code, or relabels a status taxonomy, and prior mid-stream reviews fail to spot the relabel because each reviewer saw only their slice of the diff. The relabeled boundary surfaces only when the full chain is read in one pass.

Pattern shape: a taxonomy / enum / failure-reason vocabulary is refactored, and downstream consumers that pattern-match on the old labels silently fall through to a default arm. Per-commit review confirms each individual rename is correct in isolation; chain-end review reads enough of the chain to notice the relabel happened at all.

**How this maps to the current doctrine:** when partitioning a chain diff into slices, assign one slice specifically to boundary/seam/taxonomy/enum surfaces when present — this is the highest-value partition, not the one to merge into a larger bucket. The defect class is cross-segment by nature; a slice that spans the chain's full vocabulary-change surface ensures at least one `code-reviewer` instance sees the relabel end-to-end. If `code-reviewer` flags a boundary/seam/taxonomy shift, capture it in `state/lessons/` and surface to PM for a plan-shaped decision; do not escalate to a named reviewer within the code-review path.

## Director-altitude review unbundles conflated concerns — and can dissolve a held decision

*Project-rag.* A Director-altitude tiebreaker pass (the Director of Engineering lens — invoked to break a deadlock between two reviewers or to adjudicate a contested architectural call) does more than pick a winner: it frequently **unbundles concerns the prior reviewers had conflated**, and the act of unbundling can dissolve the held decision entirely rather than ratifying either side. Two reviewers arguing "approach A vs approach B" may both be answering the wrong question — the Director lens reframes, splits the bundled concern into its independent axes, and the original A-vs-B framing evaporates because each axis resolves differently.

**Implication for review sequencing:** a Director-altitude reframe is not a failure of the lower-tier reviewers — it is the lens working as intended. Do not treat a dissolved decision as wasted review; the reframe is the value. But do treat it as a signal that the artifact's framing (the plan's problem statement, the stub's decomposition) was carrying a conflation the EM should fix at the source, not just in this one review. Capture the reframe in `state/lessons/` and re-examine whether the same conflation recurs elsewhere in the workstream. This is the architectural-finding disposition path (§ No named-reviewer escalation from code review): the reframe belongs in the planning stream.

## Review-findings folder ownership is by scope header, not timestamp

`state/review-findings/YYYYMMDDTHHMMSSZ/` folder names encode *when* a review was dispatched, not *which workstream* owns it. A pickup session that crashed after dispatching a parallel review (but before committing the integrator fixes) leaves a folder that looks like the current workstream's pending review — but may hold a mix of real artifacts (the Staff Engineer.md, security.md at full size) and placeholder stubs (tests.md = "hello") from a different session/chain.

**Rule:** at pickup, before treating any `review-findings/` folder as in-progress work for the current branch, grep the folder's inner `artifact scope:` header and compare its named HEAD SHA against `git rev-parse HEAD`. A mismatch means the review belongs to a different session — don't integrate its findings into the current diff.

## Review-Trail Coverage Audits Must Glob the Archive — Live-Dir Absence Is Not Review Absence

<!-- anchor: Archive-Aware Glob -->

**Review-trail coverage audits must read `archive/review-trail/**`, not just the live dir — `/workweek-complete` archives records weekly, so live-dir absence is not review absence.**

`state/review-trail/` only ever holds the current week; any coverage check reading only it systematically under-counts review for anything older. The **review oracle** is git range-membership — `git merge-base --is-ancestor C B && ! ...C A` — over BOTH live (`state/review-trail/*.json`) and archived (`archive/review-trail/**/*.json`) records.

*Claude-unreal-example-game-repo.* A plan-delivery audit's central alarm ("only 4 review-trail records, all this week → most shipped work unreviewed") was an archival artifact — the missing 05-24 record was in `archive/review-trail/2026-05-21/` (moved there by weekly-reset commit `db151655e`), and its `session_id` matched the shipped plan's completion-entry filename suffix. Both audited `implemented` plans were DELIVERED+REVIEWED; zero PARTIAL.

When auditing delivery-vs-review: glob both dirs. The three-oracle plan-delivery audit shape (plan-claim / code-reality-on-disk / review-coverage) + this archive-aware fix were routed to the DoE as a coordinator-universal skill/doctrine candidate via cross-repo memo (`~/.claude/cross-repo/inbox/2026-05-27-plan-delivery-audit-shape.md`).

**No lister CLI exists.** The per-commit review-trail writer/lister family is retired with no
launcher of any kind, replaced by a binary review receipt. Every consumer walks both trees
directly instead: union `state/review-trail/*.json` and `archive/review-trail/**/*.json`, sorted
by basename (not full path). The records this walk finds are complete only up to the retirement
point — nothing writes a new trail record after it, so this walk answers nothing about recent
commits' review coverage. See also `docs/wiki/plan-delivery-audit.md` for the full three-oracle
audit skill.

## Constant/Identity Bump Is a Multi-Writer Change

*Source: project-rag.*

A "one-line" pin or identity bump (version constant, schema revision, protocol constant) is structurally a multi-writer change: the constant is likely vendored in more than one location, and mocks or test fixtures encode its value as a literal. Treating it as a single-file trivial edit produces a commit that appears clean while sibling vendored copies and mocks silently remain at the old value.

**Rule.** Never waive the row-3 review floor on a constant/identity bump on the grounds that it is "just one line." Before committing: grep every vendored copy and mock of the constant, run the touched test surface, and confirm all N copies are updated in the same commit. The bump is complete only when `git grep <old_value>` returns zero hits in non-test-data files.

## Session-scoped diff via `--session-id` — fixes the brightline gate on shared-branch concurrent EM work

*Claude-central + project-rag.* On a `work/<machine>/<date>` branch shared by 3-4 concurrent EM sessions, `review-brightline-gate.py` (migrated to claude-klabauter's `coordinator/bin/`, commit b644d5a9) was firing `PARTITION-MANDATORY` on the whole branch since split — most of which was other EMs' already-reviewed work. The gate's input range was branch-scoped (`merge-base origin/main..HEAD`), but its job is session-scoped: only THIS session's commits should be assessed for partitioning. The branch-scoped reading reduced the gate to noise EMs routed around (manual review-trail intersection, waive-with-rationale, partition someone else's work).

**Fix shape:** `prepare-commit-msg` hook injects `Session-Id: <id>` git trailer on every commit (resolution-order, env-only: `CLAUDE_SESSION_ID` → `CLAUDE_CODE_SESSION_ID`, identical to `coordinator-write-review-trail.py:182-199` (retired from `.sh`; migrated to claude-klabauter's `coordinator/bin/`, commit b644d5a9)). `review-brightline-gate.py` gains `--session-id <id>` flag that filters the range via `git log --grep='^Session-Id: <id>$'` and recomputes loc/commits/surfaces/files over the filtered SHAs.

**Canonical invocation at `/workstream-complete`'s `d-run-review-brightline-gate` directive** —
`review-brightline-gate --session-id "$WSC_SID"`, resolved per the precedence ladder in
`coordinator/snippets/resolve-coordinator-bin.md` (Shape W on a PowerShell host, Shape A/B on
POSIX).

`$WSC_SID` is the session id `/workstream-complete`'s `gates.session_shape` gate resolves once via `wsc-session-disposition` (the same env-only `CLAUDE_SESSION_ID` → `CLAUDE_CODE_SESSION_ID` chain, done once by that op rather than re-derived per caller). An unresolvable session id fails loud — `wsc-session-disposition resolve` exits 4 with a CC-7-shaped error envelope (`evidence.session_id_source: "unresolved"`) — rather than falling back. A caller outside that skill that has no `$WSC_SID` in scope must resolve a session id itself before invoking the gate — the forwarder does not currently self-resolve one when `--session-id` is omitted or empty; that is a known gap, not a documented fallback.

**Zero-match semantics — fail-loud-non-blocking, NOT silent fallback.** When `--session-id` filters to zero matching commits (legacy commits without trailers, or session-id mismatch), the gate emits `range=<r> loc=0 commits=0 surfaces=0 files=0 filtered_to=0 VERDICT=single-reviewer-ok` and a stderr note `note: session-id matched 0 commits in range — gate vacuous, EM verify scope manually`. The vacuous pass is the calibrated shape — hard-fail would block every workstream-complete in the first session post-ship (no commits carry trailers yet) and re-create the route-around failure mode this fix exists to prevent. Silent fallback to whole-branch is deliberately NOT provided: it would re-introduce the multi-EM noise.

**EM action on zero-match:** run `review-brightline-gate` (resolved per `coordinator/snippets/resolve-coordinator-bin.md`, Shape W on PowerShell) without `--session-id` to see the full branch scope; if the whole-branch output is also minimal (doc-only, short session), proceed; if it is large, determine whether trailers are missing from your commits (`git log --pretty='%B' <range> | grep '^Session-Id:' | wc -l`) and whether `coordinator-ensure-prepare-commit-msg-hook` was installed before those commits landed. The first session after the install-surface ships sees this case once by construction — install the hook via `coordinator-ensure-prepare-commit-msg-hook` (resolved per `coordinator/snippets/resolve-coordinator-bin.md`, same rung-0/POSIX split) and subsequent commits in the session will carry the trailer; the next workstream-complete sees session-scope automatically.

**Output field order is pinned** (consumers grep for `VERDICT=`, `loc=`, etc.): `range=<r> loc=<l> commits=<c> surfaces=<s> files=<f> filtered_to=<N> VERDICT=<v>`. The `filtered_to=<N>` field appears only when `--session-id` is passed.

**Install surface:** `coordinator-ensure-prepare-commit-msg-hook` is installed by `repo-setup` § 3f.5.5 and self-healed every session boot via the session-init op — same two-wire install pattern as the post-commit auto-push hook. Plan: `docs/plans/2026-06-15-brightline-session-scope-fix.md`.

## Two-oracle chain+plan contract — terminus-only reviewer-quantity narrowing (RETIRED) <!-- guard-allow: directive-ids-are-engine-current — K-007 removed the two-oracle brightline gate; section kept as the design record its successors are measured against -->

**RETIRED — absence is the operative fact.** claude-klabauter `state/kill-ledger.md` K-007 removed the
chain-terminal two-oracle brightline gate. Nothing computes a terminus reviewer-quantity verdict;
the brightline stays mandatory on `gates['review_scale']`'s measurement alone. What follows is the
design record, not invocable behaviour.

*Reviewer-quantity chain+plan two-oracle detector plan.* The session-scoped `--session-id` gate (§ Session-scoped diff above) answers a mid-chain question — does THIS session's own diff need partitioning. It structurally cannot answer the chain-terminal question — does the WHOLE closing chain, aggregated across every contributing session, carry enough reviewers for its actual size and risk. The gate lives at claude-klabauter (`coordinator_core/ops/review_brightline_gate.py`) and is invoked in a NEW mode, additive to the existing `--session-id` mode:

`review-brightline-gate --from-handoff <closing-handoff-path> [<git-range>]`, resolved per
`coordinator/snippets/resolve-coordinator-bin.md`.

which emits one stdout line:

```
BRIGHTLINE reviewers_required=<int> reviewers_suggested=<int> reviewers_low=<int> plan_oracle=<int> chain_oracle=<int> session_oracle=<int> tier=<none|A|B> verdict=<single-reviewer-ok|PARTITION-MANDATORY> basis="..."
```

(The `--from-handoff` invocations above and below are the POSIX-host form; a PowerShell host
uses rung 0 / Shape W — see `coordinator/snippets/resolve-coordinator-bin.md`.)

**Two-oracle composition.** `reviewers_required = max(plan_oracle, chain_oracle, session_oracle)` — the governing plan's own declared reviewer count, a chain-derived estimate walking the closing handoff's predecessor DAG, and the pre-existing session-scoped brightline signal are each computed independently and the maximum wins. No single oracle is trusted alone: a plan can under-declare, a chain walk can miss an unwalked predecessor, and the session-scoped signal by itself undercounts at a terminus (the asymmetry note above). Taking the max is the fail-safe direction — the same "excluding moves commits toward MORE review, never less" posture the coverage gate uses (§ `--on-record-error skip|fail`).

**Tiered disagreement guard — not a uniform hard stop.** When the oracles disagree, severity is classified into a tier, and only one tier halts:
- **Tier `A`** (declared-but-unwalked-repo — the plan names a repo the chain walk never actually visited): **HARD stop.** Override is gated on the `/autonomous` sentinel being present AND a recorded reviewer whose findings artifact names the unwalked repo — both conditions, not either.
- **Tier `B`** (a magnitude disagreement between oracles that doesn't rise to the declared-but-unwalked case) and **`none`** (oracles agree): **communicate loudly, do not halt.** The runner surfaces the three oracle numbers + `basis` and requires a recorded EM reviewer-count decision, cross-checked against findings artifacts already under `state/subagent-share/<session-id>/` (the DR-091 provisioned home) — but does not block progress to Step 3.

**Enforcement wrapper — `wsc-coverage-gate-runner brightline-gate`.** `/workstream-complete`'s `d-run-chain-plan-brightline-gate` directive does not call `review-brightline-gate --from-handoff` directly; it calls the claude-klabauter enforcer subcommand that wraps it and owns the halt-or-communicate policy above:

`wsc-coverage-gate-runner brightline-gate --from-handoff "$WSC_CONSUMED_HANDOFF"`, resolved per
`coordinator/snippets/resolve-coordinator-bin.md`.

This mirrors the existing `wsc-coverage-gate-runner coverage-gate --from-handoff` DAG-mode invocation (§ `review-coverage-gate.py` above) — same binary, same settings-home resolution, sibling subcommand for reviewer-quantity instead of coverage.

**Terminus-only — the `--session-id` mode is UNCHANGED.** This is additive, not a replacement. Nothing about the existing `--session-id "$WSC_SID"` mid-chain invocation changes; `/workstream-complete` at any disposition other than `chain-terminal` keeps using it exactly as documented in § Session-scoped diff above.

**Contract for G3 review-pipeline agents.** `reviewers_required` is the field to key on for row-selection / partitioning decisions downstream — not `verdict` alone, and not any single oracle field in isolation. `plan_oracle`, `chain_oracle`, and `session_oracle` are diagnostic breakdown, useful for explaining a disagreement, not for re-deriving the required count (that's `reviewers_required`, already the max). `tier` communicates severity of any oracle disagreement; only `tier=A` is a hard-stop signal, `B`/`none` are communicate-and-record signals.

## The reviewer is confined to Read/Grep/Glob — "review the diff" must mean a frozen file, not a live git command

<!-- Spec backlink: cross-repo/inbox/2026-07-23-example-cockpit-repo-em-mise-en-place-run-friction-five-observations.md § 3 -->

`code-reviewer`'s Bash is allowlist-confined to `coordinator-doc-new --type review-findings` by the engine-side guard `coordinator_core.bash_guards.block_reviewer_bash_outside_allowlist` (claude-klabauter) — fail-closed, no escape-hatch env var. That is deliberate: it's what keeps the reviewer's own footprint auditable (§ `agents/code-reviewer.md`'s Bash-confinement note). The consequence that doctrine had not fully reckoned with: **the reviewer cannot run `git show`, `git diff`, or `git log`.** It has no way to ask git what changed.

Every non-weekly gate that dispatches it — `/workstream-complete`'s `d-freeze-and-dispatch-review-partition-integrator` directive, `coordinator:review-code` Branch A.2, `/mise-en-place` Phase 6 steps 2 and 5 — says "review the diff" in its own framing while actually passing the reviewer a list of paths or a commit range. A confined reviewer handed a path does the only thing it can: it opens that path and reads its current on-disk contents. That is not the diff. It is the file.

**Three fidelity losses follow from that substitution, and they compound at exactly the checkpoints doctrine treats as strictest:**

1. **Deletions are invisible.** Code removed by the change under review is, by definition, not present on disk for the reviewer to read. A reviewer that dropped error handling, silently narrowed a validation, or deleted a test cannot be caught by a reviewer reading only what remains.
2. **No before/after.** Reading current file contents gives no way to distinguish which lines are new (the thing under review) from which lines were already there. Every line in the file reads as equally "the diff."
3. **No attribution — the sharpest of the three.** On a shared `work/*` branch with concurrent EM sessions (the routine case here, not an edge case — see § Multi-session shared-branch union-coverage hazard above), a peer session's edits landed in the same working tree the reviewer opens. A reviewer reading current file contents cannot tell its own session's work from a concurrent peer's. This degrades precisely the checkpoints doctrine treats as the strictest: the `/mise-en-place` re-review gate and any chain-end review are both explicitly designed around "read enough of the accumulated change to catch what per-slice review missed" — and that design assumption fails silently when the artifact being read is the tree, not the change.

**The canonical fix, and why it's frozen-at-dispatch rather than "give the reviewer git":** the dispatching EM materializes a frozen diff — `git diff <range> > state/review-trail/diffs/<slice-id>.diff` — before dispatch, and injects that path into the brief as the primary artifact; the working tree remains available as context only. Partitioned dispatches get one frozen diff per slice, delivered alongside (not instead of) the existing path list. Frozen-at-dispatch is the load-bearing property, not an implementation detail: a diff written to disk at dispatch time cannot drift under concurrent commits the way a live git query or a working-tree read can, so the review target is stable for exactly as long as the review takes, however long that is. This is also why it's the *right* shape rather than a workaround: it preserves the reviewer's read-only posture completely (no guard change, no new Bash surface to audit), and it gives a *stronger* guarantee than live git access would — live `git diff` at read time is still vulnerable to a peer's commit landing mid-review, where a frozen file is not.

**Tripwire for future EMs:** if you are dispatching `code-reviewer` and your brief contains no path under `state/review-trail/diffs/`, the reviewer is not reviewing a diff — it is reading files. Check the brief before dispatch, not after the findings come back thin.

**Reciprocal note — the weekly gate carries no exception in this section.** `coordinator/skills/parallel-code-review/SKILL.md`'s Snapshot step and `coordinator/agents/code-reviewer-weekly.md:62` (that agent doesn't even carry Bash) freeze the weekly gate's diff correctly. All six call sites — the weekly gate included — invoke `coordinator/bin/freeze-review-diff.py` (`--range`, required and never defaulted, plus `--slice-id` and optional `--paths`) rather than carrying a raw `git diff` payload, writing `state/review-trail/diffs/<slice-id>.diff` + a sibling `.head.sha`.

One asymmetry survives, and it must not be harmonised away: the weekly gate's range is `origin/main...HEAD`, because a frozen merge-boundary diff is its actual contract — the whole week's shipped delta, every time. Every other surface must instead pass a **scope-appropriate range** — session-scoped at `/workstream-complete` and `/handoff` (`--session-id`) — and must never default to `origin/main...HEAD` on a shared `work/*` branch, where that range would sweep concurrent sessions' already-reviewed commits into the review (the multi-EM-brightline-noise failure this section's `--session-id` fix above exists to prevent). `freeze-review-diff.py` refuses to default `--range` precisely so this stays an explicit caller decision rather than a silently-reused constant.

**Why this took until now to surface.** The degradation was invisible to every mechanical gate in this file — no test asserts on what a reviewer *read*, only on whether it ran and what verdict it returned. It surfaced because a `code-reviewer` instance, dispatched by a example-cockpit-repo EM, disclosed its own tool-surface limit in its findings sidecar rather than quietly reviewing whatever it could see and reporting a clean verdict. That EM routed the disclosure as a cross-repo field report instead of treating it as noise. Agents naming their own confinement in their output — rather than papering over the gap — is exactly the behavior this system depends on to catch what no mechanical gate is watching for; it is worth explicitly preserving as a norm, not filed away as an incidental finding.

## The wsc_commit tail is a fragile multi-step engine op — verify its effects after firing

`/workstream-complete`'s commit tail is executed by claude-klabauter's `ceremony.wsc_commit` engine op (invoked via `cc_invoke` from the SKILL's D-5 step), not by inline EM bash. One call does scaffold + fill + stage + commit + push + claim-release, and `wsc_resolve` stamps the consumed handoff — a long, non-atomic sequence whose mid-tail failures are NOT cleanly idempotent-recoverable (a timeout after commit-before-fill leaves a half-baked artifact on `origin`). Several empirically-observed failure modes share one remedy: the EM verifies the tail's *effects on disk* after it returns, rather than trusting the op's exit code.

**Rule — after `wsc_commit` returns, verify four effects before treating the workstream as closed:**

1. **Completion entry is filled, not a bare scaffold** *(doe-L99)*. `wsc_commit` applies `f_slots` to in-memory `ctx` nodes but did not (historically) write the step-2.6.6c prose / `nature` / `commits` into the scaffolded `archive/completed` entry FILE — it committed a bare scaffold (`nature:infra` default, placeholder prose, `commits:[]`). Read the committed entry; if it is a scaffold, the fill residues must land via an explicit EM `Edit` (or the op fixed to fill from `f_slots` + `resolved_state`).
2. **`review_trail` param was present when `b_adjudication` was passed** *(doe-L98)*. Whenever `b_adjudication` is passed, `wsc_commit` REQUIRES a top-level `review_trail:{sha_range,reviewer,scope,verdict,diff_loc}` dict (read at `wsc_commit.py:1591`, separate from `b_adjudication`) — else `coordinator-write-review-trail.py` (claude-klabauter `coordinator/bin/`, migrated from DoE-claude commit b644d5a9) raises a `failed_critical` and the op exits 1. The D-5 jq payload in `skills/workstream-complete/SKILL.md` must carry `review_trail`, not just `b_adjudication`.
3. **No actioned-memo inbox path was passed in `wsc_paths`** *(doe-L67)*. `sweep-actioned-memos.py` (migrated to claude-klabauter's `coordinator/bin/`, commit b644d5a9; over the native `fleet.archive_actioned_memos` op) moves actioned memos inbox→archive during the archival phase BEFORE the stage step git-adds `wsc_paths`; passing a memo-inbox path in `wsc_paths` makes the stage fail with `pathspec did not match` (commit+push then skip). Pass only non-memo session artifacts — the sweep owns actioned-memo staging.
4. **YOUR consumed handoff actually shipped** *(doe-L154)*. `wsc_resolve` can populate `resolved_state.consumed_handoff` with a foreign-repo / phantom handoff path (and `resolved_state.sid` null), so Step 2.7's stamp-only targets the wrong handoff and leaves your real consumed handoff frozen at `consumed`/`claimed`/`in_flight`. After `wsc_commit`, grep `state/handoffs/` for your session id against BOTH vocabularies (`grep -rlE "(claimed_by|consumed_by): <sid>" state/handoffs/` — DR-084 renamed `consumed_by` to `claimed_by`; the write path hasn't cut over but the on-disk corpus is mixed, so dual-read) and confirm that handoff is `deployment_state:shipped`; if not, ship it manually via `archive-stamp-cli`'s `stamp-shipped-in` + `ship-handoff` verbs.

**cc_invoke timeout floor** *(doe-L92)*: the `cc_invoke` default `CC_INVOKE_TIMEOUT_SECS=10` is too short for the commit+push tail — it can time out mid-tail, leaving a partial commit (e.g. an unfilled completion entry committed before fill). Set `CC_INVOKE_TIMEOUT_SECS=180` for the `wsc_commit` invoke (or raise the op-specific default). A timeout mid-tail is not cleanly idempotent-recoverable if it committed a half-baked artifact.

These are claude-klabauter-owned engine bugs / robustness gaps (each routed via cross-repo memo to claude-klabauter). The durable EM-facing discipline is the post-commit effect-verification above: the exit code says the op ran, not that the four effects landed correctly.

## `wsc-session-disposition` Detector C false-positive — shared-directory scope overlap is not chain-terminal proof

<!-- spec-backlink: 2026-08-06-14h38 nugget c7-050, source 2026-07-25-adhoc-7cb841.md -->

`wsc-session-disposition` resolves `WSC_DISPOSITION` (§ Two-oracle chain+plan contract above — `chain-terminal` gates the terminus-only oracle mode) via multiple internal detectors. Detector C infers chain-terminal status from scope overlap: if the closing session's declared scope shares a directory with a prior session's baton/handoff scope, Detector C treats that as evidence the closing session is the terminal link in the same chain.

**The false-positive.** Sharing a directory is not the same claim as being the same chain. Two independent sessions can legitimately both touch files under one shared directory without either being downstream of the other — Detector C conflated "scope overlaps" with "is chain-terminal for this baton," and on the observed instance it would have re-stamped a peer session's already-shipped baton as if it belonged to the closing session's own chain, corrupting that baton's shipped/consumed provenance.

**Why this matters beyond the one instance:** a mis-fired `chain-terminal` disposition routes the closing session into the terminus-only two-oracle brightline mode (§ Two-oracle chain+plan contract) and into the chain-end union-coverage walk (§ Multi-session shared-branch union-coverage hazard) over the WRONG chain — the gate would compute reviewer-quantity and coverage against ancestry that isn't actually this session's, while a genuinely-unrelated peer baton gets its shipped state clobbered.

**Rule of thumb for detector authors:** directory/path overlap is a *candidate* signal for chain membership, never sufficient proof on its own — chain identity needs an actual ancestry edge (a consumed-handoff link, a `Deliverable-Id:`/`Session-Id:` trailer match, or an explicit predecessor pointer), not co-located scope. Treat shared-directory overlap the same way § `Deliverable-Id:` trailer treats attribution: follow the work, not the location it happened to touch.

## /workstream-start red predicate — standing structural test, not a one-time grep

<!-- spec-backlink: 2026-08-06-14h38 nugget c7-035, source 2026-07-25-test-red-fingerprint-and-delta-c05980.md -->

`/workstream-start` item 6 implements the red predicate that `bug-blitz.md` claimed already existed — the check that classifies a failing test as "genuinely red" (worth investigating) vs. an expected/known-red fixture. A prior one-time grep was supposed to keep the `/workstream-start` implementation and the `bug-blitz.md` claim in sync; a one-time check has no mechanism to detect future drift between the two.

**Fix:** a standing structural test replaces the one-time grep. The test asserts the red-predicate implementation actually exists where `bug-blitz.md` says it does, so drift between doctrine claim and implementation is caught at test time, not discovered later by an EM trusting a stale doc.

## Cross-references

- `coordinator/docs/wiki/resolves-commit-trailer.md` — sibling git-native
  commit-trailer convention (`Resolves: <artifact-id>`) modeled on this
  page's `Session-Id:` trailer, including the same zero-match
  vacuous-pass semantics (§ Session-scoped diff above); consumed by
  claude-klabauter's `coordinator/bin/rollup-derive.py` (migrated from
  DoE-claude, commit b644d5a9) for artifact-to-commit roll-up.

## partitioned reviewers require partitioned integrators

Partitioned reviewers require partitioned integrators. When a review event is fanned out to N parallel reviewers (each reviewing a different diff chunk), one integrator over the union is wrong — it will miss findings that require per-chunk context. Dispatch N parallel integrators (one per reviewer/chunk) and fold results EM-side. Apply: whenever N > 1 parallel reviewers are dispatched, plan for N parallel integrators.

## partial-shipped execute-plan is a handoff not workstream-complete

A partial-shipped execute-plan (where one or more chunks landed in `BLOCKED-ON-EXTERNAL` state) is a handoff, not a workstream-complete. `BLOCKED-*` state means the work is in-flight, not done. Apply: before invoking `/workstream-complete`, verify ALL AC rows are realized and NO chunk is in BLOCKED state; if any are BLOCKED, write a handoff instead.

- `coordinator:review-code` Branch A.2 — the dispatch surface for the actual `code-reviewer`/the Staff Engineer review invoked from `d-freeze-and-dispatch-review-partition-integrator`
- `coordinator:parallel-code-review` — the merge-gate carve-out doctrine that this trail integrates with (without modifying); Step 7's prelude is the external interface between the trail and this skill
- `docs/wiki/ceremony-calibration.md` § "Workstream-complete-as-defer is hedging in disguise" — **complementary doctrine**: ceremony-calibration prevents using `/workstream-complete` itself as a deferral mechanism; this guide prevents using "`code-reviewer`-only" as deferral within `/workstream-complete`. The two framings are paired: one catches session-level hedging, the other catches review-scale hedging. Future EMs should read both.
- `coordinator/skills/review/SKILL.md` § A.3 — Sequencing — the top-level sequential-review rule this wiki elaborates
- `archive/specs/2026-05-06-parallel-code-review-weekly-gate.md` — the original spec whose Non-goals required Step 7 scope-narrowing to be implemented externally (not inside the parallel-code-review skill body)
