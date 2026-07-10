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

- `/workstream-complete` **Step 2.9** — fires whenever the workstream completes without a handoff and has non-trivial substance. This is the primary trigger surface: any session that dispatched executors, touched shared schema, or produced more than ~50 LOC of code change lands here.
- `/handoff` **Step 2.10** — fires only when `/handoff` Step 0's YES-test gate has passed and the skill is actually writing a handoff. If Step 0's NO-test trips and the session is redirected to `/workstream-complete` or commit-and-stop, the review consideration belongs to that downstream surface (Step 2.9 above), not here. This gate alignment prevents double-review when the no-successor gate redirects.

## Diff-shape decision table

EM judgment with anchored ranges — the numbers below are decision anchors, not hard thresholds. A 51-LOC change with a clean shape does not obligate escalation; a 49-LOC change touching a public schema seam does not release from review.

| Session shape | Default scale |
|---|---|
| Doc-only edits, lesson capture, no executor dispatched, no code touched | **None** |
| Single-file fix <50 LOC, no shared schema touched, no executor | **None** (but commit message names the change) |
| Any executor dispatched, OR >50 LOC code change, OR shared schema/seam touched | **`code-reviewer`** (Sonnet, locked — see `agents/code-reviewer.md`) |
| **Big-diff brightline** — any one of: ≥500 gross LOC (insertions+deletions), OR ≥5 commits, OR ≥4 distinct surfaces (e.g. bash + JSON + tests + doctrine). File count is reported by the gate for context but is NOT a trigger; mass-renames touch many files at zero review-cost. | **Partitioned `code-reviewer` — mandatory, not chain-end-gated** (SKILL.md § Partitioning large surfaces) |
| Chain-end (started with `/pickup`, ending without `/handoff`/`/spinoff`) AND chain diff is non-trivial | **`code-reviewer`** on chain diff |
| Chain-end AND chain diff exceeds the big-diff brightline | **Partitioned `code-reviewer` dispatches**. Named reviewers are for plans/architecture — Sonnet `code-reviewer` is the ceiling at workstream-complete |

**Precedence rule:** the big-diff brightline (row 4) and chain-end rows (5, 6) override workstream-complete rows (1, 2, 3) when they apply — partitioning is the integration-risk control, not a chain-end privilege.

**Anchored-ranges note:** the small-side anchor (50 LOC at row 3) is a calibration anchor — shape can pull a 49-LOC change in or release a 51-LOC change out. **The big-side brightlines (≥500 gross LOC / ≥5 commits / ≥4 surfaces) are hard floors, not calibration anchors.** Above the brightline, single-reviewer is a doctrine violation regardless of how coherent the diff feels — SKILL.md § Step 2.9 carries the mechanical gate command that EMs run before picking a row.

**Recalibration 2026-06-09.** The gate originally tripped on `files >= 8`. A runtime-tripwire workstream that authored 3 commits across 5 files (shell + test + wiki) tripped `surfaces >= 3` despite the diff being small and coherent, while an unscoped range that pulled in a sibling-session commit inflated `files` to 11 — both fired the gate where the spirit of the rule did not. Three changes: (a) dropped `files >= 8` — file count is a blunt proxy for review-cost (a mass-rename touches many files at zero cost; a 1-file 800-LOC change is genuinely large), (b) added `commits >= 5` — commit count tracks independent logical slices, which is the unit slicing actually operates on, (c) bumped `surfaces` from 3 to 4 — hook-fixes routinely span shell+test+wiki at zero genuine breadth. The 2026-06-08 worked counterexample below still trips under the new rule (loc=890, commits=7); the small-diff false-positive at the surface=3 floor no longer does.

**Worked counterexample (2026-06-08, claude meta-repo).** A workstream-complete session shipped 2156 insertions / 26 deletions (2182 gross LOC) across 21 files spanning bash + JSON + tests + doctrine, in 7+ commits. The EM read row 3 (`>50 LOC OR executor dispatched`), satisfied it, and dispatched a single `code-reviewer`. The PM caught it pre-completion. Under the current (post-recalibration) gate, LOC is 4.3× over the floor and commits trip clean — partition would have been mandatory. The mechanical gate in SKILL.md exists so this shape can never again be reasoned-around.

## No named-reviewer escalation from code review

Named reviewers (the Staff Engineer, personas) are for plans and architecture, not code output. Sonnet `code-reviewer` is the ceiling at workstream-complete — for any diff size, partition across as many `code-reviewer` slices as needed, but do not escalate to a named reviewer.

If `code-reviewer` surfaces an architectural finding, capture it in `state/lessons.md` and surface to PM for a plan-shaped decision. The finding belongs in the planning stream, not the code-review stream.

The weekly `/workweek-complete` Step 7 parallel-code-review is the merge-gate ceremony — **N code-semantics chunk reviewers (Sonnet `code-reviewer-weekly`, partitioned over the narrowed scope) + 3 mechanical workers (security-audit-worker, dep-cve-auditor, test-evidence-parser) → no-rewrite synthesizer**. The Staff Engineer is NOT in the gate — consistent with "named reviewers are for plans/architecture, not code output" above; he runs a separate advisory architecture pass at Step 7.5 (fed by the synthesizer's `arch_tier_candidates` + `convergent_findings` + the seam set), which surfaces spinoff candidates but never blocks merge. The gate runs at merge time regardless of workstream-complete coverage — it is NOT a deferral path. Workstream-complete review happens at workstream completion; the merge gate is a separate, independent ceremony.

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

*2026-05-18, self.* For code that runs against the operator's live environment — doctor probes, installers, MCP wiring, CLIs that mutate user state — plan-review and post-implementation code-review are *not* sufficient. Dogfooding (running the code end-to-end against a real environment, per `dogfooding-doctrine.md`) catches a distinct class of defects:

- Plan-review catches design errors.
- Post-impl code-review catches integration errors.
- **Dogfood catches reality errors** — assumptions about the operator's machine state that no static review can verify (interpreter resolution, registry layout, network timing, file-system permissions).

Three cycles on the same artifact (plan-review + code-review + dogfood) routinely surface progressively different defect classes on operator-environment code. Dogfood should be treated as a **required review surface** for any code in this class, not an optional last step. Operator-environment code includes: `doctor` skills, install/setup scripts, MCP server bootstrap, CLI commands that mutate user state outside the working tree.

Companion: `dogfooding-doctrine.md` carries the binary-outcome rule and the smoke-driven fix-through loop.

## Findings disposition — fix everything, including nitpicks

A reviewer verdict of `OK` with N "below blocking threshold" observations is not a license to commit and move on. Those observations *are* the review output. The diff is fresh, the EM has context, and folding them in now costs a fraction of what they cost three weeks later when someone is hunting the bug they hinted at.

**Rule:** all findings of any severity fold in via `coordinator:review-integrator` before the marker-trail write. P0 / P1 / P2 / nitpick / observation / note / "consider" — same treatment. The integrator escalates real disagreements; it does not silently skip on severity.

**The only legitimate skip path** is a real tradeoff that escalates to PM per `coordinator/CLAUDE.md` § Reviewer findings — apply, don't ratify: cost/value, scope/polish, architectural direction. "Recorded below blocking threshold" framing in an EM wrap-up sentence is the tell that this rule was skipped — re-open the diff, fold the findings, then write the marker.

**Verdict semantics under this rule.** The marker trail's `verdict` field records what the reviewer found on the *pre-fix* diff (`ok` / `warn` / `blocked`), not what shipped. The verdict is a downstream load-shedding signal; the trail is not a fix-completion log. A pre-fix `verdict=ok` with three observations all folded in is the expected shape, not a contradiction.

## Reviewer option-sets are bounded by the brief — the EM may synthesize a third shape

A reviewer's enumerated options (do A, or do B) are bounded by the reviewer's brief and framing — they are not an exhaustive map of the decision space. When neither named option is right, the EM may synthesize a third shape the reviewer didn't surface; doing so is *application* of the review, not contradiction of it. The reviewer's value was exposing the tension, not pre-enumerating every resolution. (This is the inverse of rote ratification — the EM neither rubber-stamps option A nor treats the A/B menu as closed.) Pairs with `coordinator/CLAUDE.md` § Reviewer findings — apply, don't ratify. Source: 2026-05-20 example-game-workbench-repo.

## Re-check for overlapping peer spinoffs at workstream-complete — pickup-time reconcile is point-in-time

A routed-plan / handoff reconcile done at `/pickup` is **point-in-time**: it correctly reflects the handoff/spinoff landscape at the moment the session started, but a concurrent peer session can fork a handoff for the *same scope* while you plan, review, and execute. The pickup-time "no overlapping handoff exists" finding does not stay true.

**Rule:** at `/workstream-complete`, re-run the overlap check against `state/handoffs/` — do not trust the pickup-time reconcile as still-current. The empirical instance (project-rag): a pickup-time reconcile correctly found no host-work handoff for a scope (none existed yet); ~25 min later, while the EM planned and reviewed, a peer recovery session created one for the *same* scope and a third folded that scope into a spinoff — so at workstream-complete there were **three** overlapping handoffs. No code was duplicated (the shared file was confirmed untouched before commit), but the EM had authored a duplicate handoff that a workstream-complete re-check would have caught. This is the handoff-lineage analog of the § Multi-session shared-branch union-coverage hazard: concurrent peers on a shared branch mutate the landscape *during* your session, so the terminal ceremony owns the re-verification, not the entry ceremony.

## Marker trail mechanics

Every completed workstream-complete review writes a small JSON record to disk. The trail is the machine-readable substrate that lets downstream ceremonies compute coverage without re-reviewing already-reviewed work.

**Per-session record shape:**

```json
{
  "sha_range": "abc123..def456",
  "reviewer": "code-reviewer|the Staff Engineer|code-reviewer+the Staff Engineer|waived|ubt-compile",
  "scope": "chain|session",
  "verdict": "ok|warn|blocked|waived|pending",
  "diff_loc": 247,
  "session_id": "..."
}
```

Records land at `state/review-trail/YYYY-MM-DD-HHMMSS-{session-id-short}.json` (git-tracked, per-session, no concurrent-write risk — one file per session).

**Helper:** `coordinator-write-review-trail.sh` — named-arg interface:

```sh
coordinator-write-review-trail.sh \
  --sha-range abc123..def456 \
  --reviewer code-reviewer \
  --scope chain \
  --verdict ok \
  --diff-loc 247
```

Session-id resolution uses strict precedence: `CLAUDE_SESSION_ID` (explicit override) first; then `CLAUDE_CODE_SESSION_ID` (platform-injected, per-session, unclobberable — Claude Code ≥ ~2.1.150); then the `.git/coordinator-sessions/.current-session-id` sentinel (last-writer-wins, fallback for old Claude Code). The helper fails loud (exit 2) on collision detection — if the target file already exists with different content, it exits non-zero and does not overwrite. If it already exists with byte-identical content, it exits 0 (idempotent no-op).

**Reviewer enum current values (as of 2026-05-18 migration):**
`code-reviewer | the Staff Engineer | code-reviewer+the Staff Engineer | waived | ubt-compile`

Historical JSON records written before 2026-05-18 retain `reviewer: "sonnet"` as data. No back-compat read path is required — historical records are not consumed by the weekly prelude's sha-range logic. New writes must use the current enum.

The `code-reviewer` value refers specifically to a dispatch of `agents/code-reviewer.md` (Sonnet-locked, read-only). Do NOT substitute a generic Sonnet dispatch and label it `code-reviewer` — the agent file is the contract.

**Daily roll-up:** `/workday-complete` Step 9 reads today's review records via `list-review-trail-records.sh --date-prefix "${TODAY}"` (unions `state/review-trail/` and `archive/review-trail/**` — covers the morning-after-weekly-reset edge case) and emits one `**Reviewed:**` line per record into the day's changelog block:

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

`/workweek-complete` Step 7 prelude reads the trail before dispatching `coordinator:parallel-code-review`. The prelude narrows the **code-semantics** scope (now chunked across N `code-reviewer-weekly` instances — the Staff Engineer is no longer the gate reviewer); the three mechanical workers always run on the full week diff regardless.

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
     {"patrik": "<scope_sha_list>", "patrik_seam_files": "<seam_paths>", "mechanical_workers": "full"}
   (The JSON keys are still named `the Staff Engineer`/`patrik_seam_files` for back-compat — the helper
   `workweek-trail-scope.sh` was not renamed. Post-restructure the `the Staff Engineer` SHA set is the
   code-semantics CHUNKING input; `patrik_seam_files` additionally feeds the Staff Engineer's advisory
   Layer-2 pass at Step 7.5.)
   Pass this scope file in the brief to parallel-code-review.
   The synthesizer reads it and narrates:
     "code-semantics chunks scoped to gap+seams; mechanical workers full diff."
```

The `parallel-code-review` skill body IS modified for the N-chunk model (Strand 1), but the doctrine-guarded carve-out from `archive/specs/2026-05-06-parallel-code-review-weekly-gate.md` is preserved: scope-narrowing still happens in Step 7's prelude, and the frozen-diff / orthogonal-lens / no-rewrite-synthesizer conditions still hold (orthogonality now spans the 3 specialist lenses + code-semantics-as-a-class; the N chunks partition that class disjointly by file-scope).

**`cross_segment_seams` defined precisely:** a *segment* is the sha-range of one trail record (one workstream-complete review). Cross-segment seams are the set of file paths that appear in the diff of ≥2 distinct segments — computed by taking the union of files-touched per record and intersecting pairwise. The per-segment file-touch set is derived from `git diff --name-only <sha-range>`. These seams carry integration risk because multiple independent sessions touched them; they feed BOTH the code-semantics chunk review (seam-first chunking gives them extra integration scrutiny) AND the Staff Engineer's advisory Layer-2 pass at Step 7.5, which reads the seam set as an integration-surface signal but does NOT gate merge.

**Verdict subvariant:** when the code-semantics scope is empty AND no findings from any mechanical worker, the synthesizer may emit `OK (code-semantics trail-covered, mechanical clean)` — an informational subvariant of the standard `OK` verdict. The parallel dispatch still runs; no "skip" path exists. This variant signals that the trail successfully shed load without bypassing the safety gate.

**Why mechanical workers are never scoped down:** workstream-complete reviews dispatch only `coordinator:review-code` Branch A.2 (`code-reviewer`). The three mechanical workers (security-audit-worker, dep-cve-auditor, test-evidence-parser) never run at workstream-complete. "Trail-covered" therefore does not mean "all lenses covered" — it means "code-semantics lens covered." Narrowing mechanical workers based on the trail would silently elide their independence property.

## workweek-trail-scope.sh — detect-then-fail-loud on segment-shape, not silent-pick on string proxy

The `workweek-trail-scope.sh` prelude computes `cross_segment_seams` by intersecting per-segment file-touch sets across review-trail records. The original implementation used a string-shape proxy to decide whether a record was a "segment" — silently coercing ambiguous record shapes into a default arm.

**The detect-then-silently-pick footgun (per `coordinator/CLAUDE.md` § Implementation Standards) applies here:** if a trail record's shape does not unambiguously identify it as a per-session segment (e.g. multi-line JSON variant, future schema migration, partial write), the prelude MUST fail loud rather than silently classify it. Silent classification produces a `code_semantics_scope` that omits real seam files, and the weekly gate runs with a too-narrow lens.

**Rule:** segment detection in `workweek-trail-scope.sh` (and any future trail-shape consumer) fails on unrecognized record shape with a remediation message, not a default arm. The cost of a noisy false-positive is a Step 7 prelude that asks the EM to upgrade the trail-reader; the cost of a silent false-negative is a missed integration-seam at merge time.

Companion: `coordinator/CLAUDE.md` § Implementation Standards, "Detect-then-silently-pick is a footgun." Source: 2026-06-01 weekly-gate the Staff Engineer arch review (b3g-077).

## review-coverage-gate.sh — chain-end mechanical coverage gate (2026-06-23)

<!-- spec-backlink: docs/plans/2026-06-23-chain-end-review-coverage-gate.md § Design -->

`bin/review-coverage-gate.sh` is the chain-end mechanical gate that verifies every commit in a workstream's chain diff is covered by at least one `code-reviewer` trail record. It runs at `/workstream-complete` Step 2.9 (scoped to the closing workstream) and at `/merge-to-main` as an unconditional pre-merge step.

### Mechanics

1. **Chain set:** `git rev-list --no-merges <merge-base origin/main HEAD..HEAD> [-- <scope-paths>]`. Merge commits are excluded via `--no-merges` (they carry no authored diff that requires review — this is an explicit design decision, not emergent behavior).
2. **Reviewed set:** reads ALL trail records (live + archived) via `bin/list-review-trail-records.sh` (archive-aware — records move to `archive/review-trail/<week>/` after `/workweek-complete` Step 13; the gate must read both dirs). For each `scope_kind=diff` record with a valid `sha_range`, the shared `lib/review-coverage-core.sh` computes `git rev-list <sha_range>` and unions → `reviewed_set`. Records with `scope_kind ∈ {plan, integration}` are skipped silently (no real sha-range).
3. **Verdict filter (shared core):** the shared core excludes `verdict=pending` from `reviewed_set`. A `pending` record means the review has not completed — counting it as coverage lets the gate pass on unreviewed commits. `verdict=waived` counts as covered (explicit PM waiver = a coverage decision). Verdicts `{ok, warn, blocked, waived}` all count.
4. **Uncovered set:** `chain_set − reviewed_set`.
5. **Output:** `range=… chain_commits=N covered=M uncovered=K VERDICT={COVERED|UNCOVERED}` on stdout. On `UNCOVERED`, one `uncovered: <sha> <subject>` line per gap on stderr. Exit 0 in both cases (verdict-line shape, same as `review-brightline-gate.sh`) — the calling skill parses `VERDICT=UNCOVERED` and halts.

**Shared lib:** the coverage computation (SAFE_RANGE validator, per-record `git rev-list` union loop, JSON-OR-JSONL dual-shape parse) lives in `lib/review-coverage-core.sh`, consumed by BOTH this gate and `lib/workweek-trail-scope.sh`. The drift vector between the two gates is closed permanently: a naïve re-implementation would silently drop JSONL integrator-envelope records from `reviewed_set`, producing false UNCOVERED verdicts — sharing the core prevents this.

### The `A..B` per-commit footgun — net-new doctrine

**Endpoint-string comparison is the trap; per-commit `git rev-list` is correct.**

`git rev-list A..B` covers the half-open interval `(A, B]` — it lists commits reachable from `B` but NOT from `A`. This means `A` itself is NOT in the output. A trail record with `sha_range=A..B` does NOT cover commit `A`.

**Incident shape (project-rag-ue-addon, 2026-06-22):** record `76619a87f..df44968f9` covered C3→C5 + fixes. Because `A` (= `76619a87f` = C2's own tip) was excluded, C1 (`37798a455`) and C2 (`76619a87f`) — the 521-LOC correctness-critical core — were unreviewed. The trail *looked* like it covered the work.

**Why per-commit is correct:** `review-coverage-core.sh` computes `git rev-list <sha_range>` per record and unions the resulting SHA sets. Commit `A` is covered only if some *other* record's range includes it as a right endpoint (e.g. a prior record `X..A` where `A` IS in `git rev-list X..A`). This is not a special case — it is the natural behavior of per-commit union coverage. The bug in the incident was the absence of any such prior record, which a per-commit gate surfaces immediately and an endpoint-string comparison silently misses.

**Negative-spec:** do NOT "fix" the recorded `sha_range` format to be endpoint-inclusive (e.g. by changing `A..B` to `A^..B` in the writer). The weekly gate and cockpit-tc-3 `ReviewTrail` reader both consume the existing format — changing it would break both consumers. The per-commit consumption in `review-coverage-core.sh` handles the `A..B` boundary correctly by construction.

### Multi-session shared-branch union-coverage hazard

On a `work/<machine>/<date>` branch shared by concurrent EM sessions, a feature spanning multiple sessions produces multiple trail records — one per session. **Per-session trail ranges are NOT additive-by-assumption.** Session boundaries create gap-SHAs (session 1's terminal SHA is the left endpoint of session 2's record, but the terminal SHA itself is NOT covered by session 2's record per the `A..B` boundary above).

**Rule:** the chain-terminal session owns the union-coverage check. At `/workstream-complete` Step 2.9, `review-coverage-gate.sh` reads the `reviewed_set` as the UNION of ALL sessions' trail records (never session-filtered). If gaps exist at session boundaries, the terminal session is responsible for either:
- Verifying that a prior session's record covered the gap SHA as a right endpoint, OR
- Dispatching an additional `code-reviewer` pass on the uncovered commits before asserting merge-ready.

**Asymmetry note:** `review-brightline-gate.sh` narrows to `--session-id` (avoids false PARTITION-MANDATORY on peer commits already reviewed). The coverage gate does the reverse — it widens `reviewed_set` to credit ALL sessions' reviews. This asymmetry is architectural, not accidental.

### Verdict filter — resolves latent weekly-gate gap

`lib/workweek-trail-scope.sh` previously applied no verdict filter when computing `reviewed_set` for the weekly gate's load-shedding prelude. A `verdict=pending` record (e.g. a UBT compile marker written before the build resolves) counted as coverage, potentially narrowing `unreviewed_set` too aggressively.

**This gap is fixed.** The shared `lib/review-coverage-core.sh` extracted in this workstream applies the verdict filter in one place; BOTH the new chain-end gate AND `workweek-trail-scope.sh`'s re-pointed consumption inherit correct pending-exclusion. The fix is fail-safe: excluding a pending record moves its commits FROM covered INTO unreviewed → weekly gate reviews MORE, never less. **Document as resolved, not a follow-up.**

### `--scope-paths` narrowing risk and the unscoped `/merge-to-main` backstop

The gate accepts `--scope-paths <pathspec>...` so Step 2.9 can scope the chain set to the closing workstream's files (from the governing plan / handoff `scope:`), via `git rev-list --no-merges <range> -- <paths>`. The `reviewed_set` is never path-filtered — a commit reviewed by any session's trail record is covered regardless of path.

**Risk:** if `--scope-paths` is drawn from a stale or incomplete handoff `scope:`, commits that touched the workstream's real surface but fall outside the declared pathspec are excluded from `chain_set` and never checked — the scoped gate passes while leaving authored code unreviewed.

**Backstop:** the `/merge-to-main` unconditional pre-merge gate runs `review-coverage-gate.sh` UNSCOPED over `origin/main..HEAD`. This makes the `/merge-to-main` gate load-bearing for the whole design — the scoped chain-end gate is allowed to be permissive precisely because the unscoped merge gate is the floor. An empty or missing `--scope-paths` falls back to UNSCOPED whole-chain (detect-then-fail-loud, NOT silently scoped to nothing).

### `--on-record-error skip|fail` resilience policy

The chain-end gate scans the FULL archive (potentially hundreds of historical records from weeks or months of work). Historical trail dirs can contain:
- Files that parse as neither JSON nor JSONL (concatenated objects, sidecars sharing the trail dir)
- Records whose `sha_range` references an unresolvable git ref (literal `..WORKING` placeholder, GC'd SHA, rebased commit)

Both make `git rev-list` or the parser hard-exit, which would abort the whole gate on one ancient archived record — an unusable gate.

**Policy:** `lib/review-coverage-core.sh` accepts `--on-record-error skip|fail`. The lib default is `fail`. Each consumer passes the flag EXPLICITLY — removing the flag from either consumer would change its behavior back to `fail`.

- **`skip` (chain-end gate's explicit default):** `review-coverage-gate.sh` passes `--on-record-error skip` explicitly. Warn-and-continue on an unprocessable record. Fail-safe: an unparseable/unresolvable record credits NO commits → those commits surface as MORE review (the uncovered direction), never less. Skips are announced per-file on stderr, never silent.
- **`fail` (weekly gate's explicit default):** `lib/workweek-trail-scope.sh` passes `--on-record-error fail` explicitly (or omits the flag, inheriting the lib default). Detect-then-fail-loud, consistent with `workweek-trail-scope.sh`'s documented doctrine. The weekly gate scans only the narrow current-week live dir (Step 7 runs before Step 13 archival in the same invocation), so a malformed record there is a fresh defect that should halt and be fixed.

The asymmetric behavior is deliberate — the same core, correctly configured for each consumer's scan scope and failure semantics. If you remove `--on-record-error skip` from the coverage gate invocation, it silently changes to `fail` behavior.

## Three-Surface Composition — Automated Build Verdicts (UBT pattern, 2026-05-15)

The review trail accommodates automated build-quality checks via a deferred three-surface
composition. The UBT compile gate is the first example; future automated linters (`clippy`,
`eslint`, `pytest-coverage`) follow the same shape.

### Motivation

Running a UBT build (~30s incremental, low-minutes cold) at workstream-complete blocks quick-save
commits under the concurrent-EM cadence (`state/lessons.md:324` — "at most one UBT-dependent
executor in flight"). The three-surface pattern decouples intent-capture (cheap, workstream-complete)
from build-execution (expensive, daily) from gate-enforcement (cheap, weekly).

### Three surfaces and their roles

| Surface | Role | Cost | Trigger |
|---|---|---|---|
| `/workstream-complete` Step 2.9 | Write `verdict=pending` marker if chain-diff touches `control/plugin/**/Source/**/*.{cpp,h}` | Cheap (no build) | Per session |
| `/workday-complete` Step 0c | Resolve today's pending markers — run UBT, parse result, write new resolved record | ~30s incremental | Daily |
| `/workweek-complete` Step 4c | Refuse merge if any `verdict=pending` records have NO resolved sibling | Cheap (scan) | Weekly |

Full-tier run here is the cadence-gate firing of the posture (full suite at cadence only, N=0 bar unchanged): → `docs/wiki/test-design-discipline.md § Posture: Proportional Test-Running`.

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
Each adds exactly one closed-enum value to `coordinator-write-review-trail.sh`'s `--reviewer`
enum. Pattern established by Chunk 0 of the UBT plan (DR-UBT-001).

### Detection signature — file-path, not workstream name

The pending-marker trigger detects diff files matching `control/plugin/**/Source/**/*.{cpp,h}`
(including `Tests/` subdirectories — TC-6 demonstrated test-side include-rot is a real failure
class). Workstream name / commit-message prefix matching is explicitly rejected: it would fire
pointlessly on TS-only stubs and miss future workstreams that drop the `tc-` prefix.

### Presence-detection gate

Coordinator skill bodies invoke the gate via `[ -x bin/check-ubt-build-fresh.sh ] &&
bin/check-ubt-build-fresh.sh [args]`. Absent script → graceful no-op so non-UE repos see
no change. See `docs/wiki/example-game-repo-doctrine.md §7.7` for the full convention.

### Verdict semantics extension

`--verdict` enum extended with `pending` (alongside `ok|warn|blocked|waived`).
`--reviewer` enum extended with `ubt-compile` (alongside `code-reviewer | the Staff Engineer | code-reviewer+the Staff Engineer | waived`).
`--scope chain` (existing value — UBT verdicts are chain-scoped, not per-diff-slice).

Spec backlink: `docs/plans/2026-05-15-ubt-compile-gate-review-trail.md` §Shape.

## Boundary-relabeling defect class — a cross-segment seam signal

Chain-end review empirically catches **boundary-relabeling** bugs — where a refactor renames a failure-reason enum, retypes an error code, or relabels a status taxonomy, and prior mid-stream reviews fail to spot the relabel because each reviewer saw only their slice of the diff. The relabeled boundary surfaces only when the full chain is read in one pass.

Pattern shape: a taxonomy / enum / failure-reason vocabulary is refactored, and downstream consumers that pattern-match on the old labels silently fall through to a default arm. Per-commit review confirms each individual rename is correct in isolation; chain-end review reads enough of the chain to notice the relabel happened at all.

**How this maps to the current doctrine:** when partitioning a chain diff into slices, assign one slice specifically to boundary/seam/taxonomy/enum surfaces when present — this is the highest-value partition, not the one to merge into a larger bucket. The defect class is cross-segment by nature; a slice that spans the chain's full vocabulary-change surface ensures at least one `code-reviewer` instance sees the relabel end-to-end. If `code-reviewer` flags a boundary/seam/taxonomy shift, capture it in `state/lessons.md` and surface to PM for a plan-shaped decision; do not escalate to a named reviewer within the code-review path.

## Director-altitude review unbundles conflated concerns — and can dissolve a held decision

*2026-05-18, project-rag.* A Director-altitude tiebreaker pass (the Director of Engineering lens — invoked to break a deadlock between two reviewers or to adjudicate a contested architectural call) does more than pick a winner: it frequently **unbundles concerns the prior reviewers had conflated**, and the act of unbundling can dissolve the held decision entirely rather than ratifying either side. Two reviewers arguing "approach A vs approach B" may both be answering the wrong question — the Director lens reframes, splits the bundled concern into its independent axes, and the original A-vs-B framing evaporates because each axis resolves differently.

**Implication for review sequencing:** a Director-altitude reframe is not a failure of the lower-tier reviewers — it is the lens working as intended. Do not treat a dissolved decision as wasted review; the reframe is the value. But do treat it as a signal that the artifact's framing (the plan's problem statement, the stub's decomposition) was carrying a conflation the EM should fix at the source, not just in this one review. Capture the reframe in `state/lessons.md` and re-examine whether the same conflation recurs elsewhere in the workstream. This is the architectural-finding disposition path (§ No named-reviewer escalation from code review): the reframe belongs in the planning stream.

## Review-findings folder ownership is by scope header, not timestamp

`state/review-findings/YYYYMMDDTHHMMSSZ/` folder names encode *when* a review was dispatched, not *which workstream* owns it. A pickup session that crashed after dispatching a parallel review (but before committing the integrator fixes) leaves a folder that looks like the current workstream's pending review — but may hold a mix of real artifacts (the Staff Engineer.md, security.md at full size) and placeholder stubs (tests.md = "hello") from a different session/chain.

**Rule:** at pickup, before treating any `review-findings/` folder as in-progress work for the current branch, grep the folder's inner `artifact scope:` header and compare its named HEAD SHA against `git rev-parse HEAD`. A mismatch means the review belongs to a different session — don't integrate its findings into the current diff.

## Review-Trail Coverage Audits Must Glob the Archive — Live-Dir Absence Is Not Review Absence

<!-- anchor: Archive-Aware Glob -->

**Review-trail coverage audits must read `archive/review-trail/**`, not just the live dir — `/workweek-complete` archives records weekly, so live-dir absence is not review absence.**

`state/review-trail/` only ever holds the current week; any coverage check reading only it systematically under-counts review for anything older. The **review oracle** is git range-membership — `git merge-base --is-ancestor C B && ! ...C A` — over BOTH live (`state/review-trail/*.json`) and archived (`archive/review-trail/**/*.json`) records.

*2026-05-27, example-game-workbench-repo.* A plan-delivery audit's central alarm ("only 4 review-trail records, all this week → most shipped work unreviewed") was an archival artifact — the missing 05-24 record was in `archive/review-trail/2026-05-21/` (moved there by weekly-reset commit `db151655e`), and its `session_id` matched the shipped plan's completion-entry filename suffix. Both audited `implemented` plans were DELIVERED+REVIEWED; zero PARTIAL.

When auditing delivery-vs-review: glob both dirs. The three-oracle plan-delivery audit shape (plan-claim / code-reality-on-disk / review-coverage) + this archive-aware fix were routed to the DoE as a coordinator-universal skill/doctrine candidate via cross-repo memo (`~/.claude/cross-repo/inbox/2026-05-27-plan-delivery-audit-shape.md`).

**Canonical helper:** `list-review-trail-records.sh` — emits the union of live (`state/review-trail/*.json`) and archived (`archive/review-trail/**/*.json`) records, NUL-separated, sorted by basename. Absent dirs do not error. All review-trail consumers should route through this helper rather than separate glob calls. See also `docs/wiki/plan-delivery-audit.md` for the full three-oracle audit skill.

## Constant/Identity Bump Is a Multi-Writer Change

*Source: project-rag, 2026-05-28.*

A "one-line" pin or identity bump (version constant, schema revision, protocol constant) is structurally a multi-writer change: the constant is likely vendored in more than one location, and mocks or test fixtures encode its value as a literal. Treating it as a single-file trivial edit produces a commit that appears clean while sibling vendored copies and mocks silently remain at the old value.

**Rule.** Never waive the row-3 review floor on a constant/identity bump on the grounds that it is "just one line." Before committing: grep every vendored copy and mock of the constant, run the touched test surface, and confirm all N copies are updated in the same commit. The bump is complete only when `git grep <old_value>` returns zero hits in non-test-data files.

## Session-scoped diff via `--session-id` — fixes the brightline gate on shared-branch concurrent EM work

*2026-06-15, claude-central + project-rag.* On a `work/<machine>/<date>` branch shared by 3-4 concurrent EM sessions, `~/.claude/plugins/coordinator/bin/review-brightline-gate.sh` was firing `PARTITION-MANDATORY` on the whole branch since split — most of which was other EMs' already-reviewed work. The gate's input range was branch-scoped (`merge-base origin/main..HEAD`), but its job is session-scoped: only THIS session's commits should be assessed for partitioning. The branch-scoped reading reduced the gate to noise EMs routed around (manual review-trail intersection, waive-with-rationale, partition someone else's work).

**Fix shape:** `prepare-commit-msg` hook injects `Session-Id: <id>` git trailer on every commit (resolution-order: `CLAUDE_SESSION_ID` → `CLAUDE_CODE_SESSION_ID` → `.git/coordinator-sessions/.current-session-id` sentinel, identical to `bin/coordinator-write-review-trail.sh:182-199`). `review-brightline-gate.sh` gains `--session-id <id>` flag that filters the range via `git log --grep='^Session-Id: <id>$'` and recomputes loc/commits/surfaces/files over the filtered SHAs.

**Canonical invocation at `/workstream-complete` Step 2.9:**

```bash
~/.claude/plugins/coordinator/bin/review-brightline-gate.sh --session-id "${CLAUDE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-$(cat .git/coordinator-sessions/.current-session-id 2>/dev/null)}}"
```

**Zero-match semantics — fail-loud-non-blocking, NOT silent fallback.** When `--session-id` filters to zero matching commits (legacy commits without trailers, or session-id mismatch), the gate emits `range=<r> loc=0 commits=0 surfaces=0 files=0 filtered_to=0 VERDICT=single-reviewer-ok` and a stderr note `note: session-id matched 0 commits in range — gate vacuous, EM verify scope manually`. The vacuous pass is the calibrated shape — hard-fail would block every workstream-complete in the first session post-ship (no commits carry trailers yet) and re-create the route-around failure mode this fix exists to prevent. Silent fallback to whole-branch is deliberately NOT provided: it would re-introduce the multi-EM noise.

**EM action on zero-match:** run `~/.claude/plugins/coordinator/bin/review-brightline-gate.sh` without `--session-id` to see the full branch scope; if the whole-branch output is also minimal (doc-only, short session), proceed; if it is large, determine whether trailers are missing from your commits (`git log --pretty='%B' <range> | grep '^Session-Id:' | wc -l`) and whether `coordinator-ensure-prepare-commit-msg-hook` was installed before those commits landed. The first session after the install-surface ships sees this case once by construction — install the hook (`bash ~/.claude/plugins/coordinator/bin/coordinator-ensure-prepare-commit-msg-hook`) and subsequent commits in the session will carry the trailer; the next workstream-complete sees session-scope automatically.

**Output field order is pinned** (consumers grep for `VERDICT=`, `loc=`, etc.): `range=<r> loc=<l> commits=<c> surfaces=<s> files=<f> filtered_to=<N> VERDICT=<v>`. The `filtered_to=<N>` field appears only when `--session-id` is passed.

**Install surface:** `coordinator-ensure-prepare-commit-msg-hook` is installed by `repo-setup` § 3f.5.5 and self-healed by `session-init.sh` every session boot — same two-wire install pattern as the post-commit auto-push hook. Plan: `docs/plans/2026-06-15-brightline-session-scope-fix.md`.

## Cross-references

- `coordinator/docs/wiki/resolves-commit-trailer.md` — sibling git-native
  commit-trailer convention (`Resolves: <artifact-id>`) modeled on this
  page's `Session-Id:` trailer, including the same zero-match
  vacuous-pass semantics (§ Session-scoped diff above); consumed by
  `coordinator/bin/rollup-derive.sh` for artifact-to-commit roll-up.

## partitioned reviewers require partitioned integrators

Partitioned reviewers require partitioned integrators. When a review event is fanned out to N parallel reviewers (each reviewing a different diff chunk), one integrator over the union is wrong — it will miss findings that require per-chunk context. Dispatch N parallel integrators (one per reviewer/chunk) and fold results EM-side. Apply: whenever N > 1 parallel reviewers are dispatched, plan for N parallel integrators.

## partial-shipped execute-plan is a handoff not workstream-complete

A partial-shipped execute-plan (where one or more chunks landed in `BLOCKED-ON-EXTERNAL` state) is a handoff, not a workstream-complete. `BLOCKED-*` state means the work is in-flight, not done. Apply: before invoking `/workstream-complete`, verify ALL AC rows are realized and NO chunk is in BLOCKED state; if any are BLOCKED, write a handoff instead.

- `coordinator:review-code` Branch A.2 — the dispatch surface for the actual `code-reviewer`/the Staff Engineer review invoked from Step 2.9 and Step 2.10
- `coordinator:parallel-code-review` — the merge-gate carve-out doctrine that this trail integrates with (without modifying); Step 7's prelude is the external interface between the trail and this skill
- `docs/wiki/ceremony-calibration.md` § "Workstream-complete-as-defer is hedging in disguise" — **complementary doctrine**: ceremony-calibration prevents using `/workstream-complete` itself as a deferral mechanism; this guide prevents using "`code-reviewer`-only" as deferral within `/workstream-complete`. The two framings are paired: one catches session-level hedging, the other catches review-scale hedging. Future EMs should read both.
- `coordinator/CLAUDE.md` § Review Sequencing — top-level pointer that names this wiki as the authoritative doctrine source
- `archive/specs/2026-05-06-parallel-code-review-weekly-gate.md` — the original spec whose Non-goals required Step 7 scope-narrowing to be implemented externally (not inside the parallel-code-review skill body)
