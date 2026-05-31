---
provenance:
  - archived_spec: archive/specs/2026-05-15-ubt-compile-gate-review-trail.md
    original_path: docs/plans/2026-05-15-ubt-compile-gate-review-trail.md
    last_verbose_sha: af9b63e49817131fa7c88c8dcb0513271a50012d
    distilled: 2026-05-15
---

# Session-End Review and Marker Trail

<!-- spec-backlink: docs/plans/2026-05-08-session-end-review-and-marker-trail.md §T9 -->

`/session-end` is the natural pause point for post-executor code review — the diff is fresh, the EM has context, and the cost of catching an integration bug now is one Sonnet call instead of a debugging session three weeks later. The marker trail at `tasks/review-trail/` records what has been reviewed so downstream weekly and daily ceremonies shed redundant load rather than re-reviewing work already covered.

## When this fires

**Trigger surfaces:**

- `/session-end` **Step 2.8** — fires whenever the session ends without a handoff and has non-trivial substance. This is the primary trigger surface: any session that dispatched executors, touched shared schema, or produced more than ~50 LOC of code change lands here.
- `/handoff` **Step 2.10** — fires only when `/handoff` Step 0's YES-test gate has passed and the skill is actually writing a handoff. If Step 0's NO-test trips and the session is redirected to `/session-end` or commit-and-stop, the review consideration belongs to that downstream surface (Step 2.8 above), not here. This gate alignment prevents double-review when the no-successor gate redirects.

## Diff-shape decision table

EM judgment with anchored ranges — the numbers below are decision anchors, not hard thresholds. A 51-LOC change with a clean shape does not obligate escalation; a 49-LOC change touching a public schema seam does not release from review.

| Session shape | Default scale |
|---|---|
| Doc-only edits, lesson capture, no executor dispatched, no code touched | **None** |
| Single-file fix <50 LOC, no shared schema touched, no executor | **None** (but commit message names the change) |
| Any executor dispatched, OR >50 LOC code change, OR shared schema/seam touched | **`code-reviewer`** (Sonnet, locked — see `agents/code-reviewer.md`) |
| Chain-end (started with `/pickup`, ending without `/handoff`/`/spinoff`) AND chain diff is non-trivial | **`code-reviewer`** on chain diff |
| Chain-end AND chain diff too large for a single reviewer | **Partitioned `code-reviewer` dispatches** (see SKILL.md § Partitioning large surfaces). Named reviewers are for plans/architecture — Sonnet `code-reviewer` is the ceiling at session-end |

**Precedence rule:** chain-end rows (4, 5) override session-end rows (1, 2, 3) when both apply — the chain diff is the integration-risk artifact.

**Anchored-ranges note:** the numeric thresholds (50 LOC, 500 LOC, ≥3 segments) are worked examples for EM calibration, not gates that auto-dispatch or auto-skip. The executor-dispatch trigger in row 3 is mechanical; the diff-size dimension in rows 4–5 is judgment.

## No named-reviewer escalation from code review

Named reviewers (the Staff Engineer, personas) are for plans and architecture, not code output. Sonnet `code-reviewer` is the ceiling at session-end — for any diff size, partition across as many `code-reviewer` slices as needed, but do not escalate to a named reviewer.

If `code-reviewer` surfaces an architectural finding, capture it in `tasks/lessons.md` and surface to PM for a plan-shaped decision. The finding belongs in the planning stream, not the code-review stream.

The weekly `/workweek-complete` Step 7 parallel-code-review is the merge-gate ceremony — **N code-semantics chunk reviewers (Sonnet `code-reviewer-weekly`, partitioned over the narrowed scope) + 3 mechanical workers (security-audit-worker, dep-cve-auditor, test-evidence-parser) → no-rewrite synthesizer**. The Staff Engineer is NOT in the gate — consistent with "named reviewers are for plans/architecture, not code output" above; he runs a separate advisory architecture pass at Step 7.5 (fed by the synthesizer's `arch_tier_candidates` + `convergent_findings` + the seam set), which surfaces spinoff candidates but never blocks merge. The gate runs at merge time regardless of session-end coverage — it is NOT a deferral path. Session-end review happens at session-end; the merge gate is a separate, independent ceremony.

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

**3. "`code-reviewer`-after-already-doing-plan-review feels like ceremony — skip" is the ceremony-bias shape that matters at session-end.** The *`code-reviewer`-skip* direction is the live tripwire — ceremony-feeling is the tell for skipping a review that should happen. There is no the Staff Engineer escalation path from code review to balance against; `code-reviewer` is both the floor and the ceiling.

**4. "We've done a lot of review already" is the shape wrap-up pressure takes.** At `/session-end`, token-budget anxiety and session-fatigue create implicit "close out" pressure. Dressed up, that becomes "distributed coverage upstream was sufficient." Bare, it's: one more dispatch felt like one more thing. Naming this pattern explicitly is the durable fix — future EMs hitting the same pressure can recognize the shape.

**5. "The handoff says the Staff Engineer reviewed it" — plan-vs-code conflation at chain-ends.** When reading a predecessor handoff, a "the Staff Engineer review → N findings folded" note refers to the *plan* the Staff Engineer reviewed before executors fired. Plan-level reviews do not appear in `tasks/review-trail/*.json`. The trail is the mechanical boundary: if no trail record exists for a sha-range, that range has no code-output coverage regardless of what handoff narrative says about plan-level reviews. This variant fires specifically at chain-ends, where the EM scans the chain's review history and sees "the Staff Engineer reviewed" without distinguishing plan-review from diff-review. The tell: the cited review refers to a `docs/plans/*.review-patrik.md` or a plan critique, not a `code-reviewer` dispatch. The Staff Engineer judging the plan before executors fired is *design intent* coverage; it says nothing about what the executors actually produced.

**The pattern-match tell:** if the EM is drafting a "waiving with rationale" sentence on a row-3+ session, the rationale itself is the tell. Compose the sentence; read it back; if it leans on plan-time coverage, executor gates, distributed/heavy upstream review, or "we've already done a lot" — run the `code-reviewer`. It's one dispatch. The marker trail records `verdict=ok` in seconds and downstream load-shedding still benefits.

**Summary.** Plan-time review (writing-plans pre-flight) and post-impl review (session-end `code-reviewer`) catch different defect classes — pre-flight finds substrate/path/framework mismatches, post-impl finds integration/test-coverage/edge-case gaps. Doctrine-table defaults are defaults, not negotiation starting points; don't drop session-end review because "pre-flight passed."

**Worked example.** A multi-executor session shipped a substantial workstream with plan-time prior-art-check (7 findings folded), plan-time the Staff Engineer review (8 findings folded), per-executor self-acceptance gates (all PASS), and a final-segment validation including an OOM smoke test. The EM waived session-end `code-reviewer` on the rationale "distributed coverage upstream." The audited holes: a the Staff Engineer plan-time finding had been factually wrong (the executor caught it — meaning plan-review surface had a leak that *more downstream eyes*, not fewer, was the right response to); one executor segment swept up unrelated concurrent work whose commit message described only the headline change; the OOM smoke passed in 8s of a 600s budget without verifying it had actually exercised the install path vs. short-circuiting on cached state. None of these were catchable by plan-time review or by mechanical executor gates. They were exactly the class of finding a fresh `code-reviewer` lens on the actual diff catches.

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

A reviewer's enumerated options (do A, or do B) are bounded by the reviewer's brief and framing — they are not an exhaustive map of the decision space. When neither named option is right, the EM may synthesize a third shape the reviewer didn't surface; doing so is *application* of the review, not contradiction of it. The reviewer's value was exposing the tension, not pre-enumerating every resolution. (This is the inverse of rote ratification — the EM neither rubber-stamps option A nor treats the A/B menu as closed.) Pairs with `coordinator/CLAUDE.md` § Reviewer findings — apply, don't ratify. Source: 2026-05-20 claude-unreal-holodeck.

## Marker trail mechanics

Every completed session-end review writes a small JSON record to disk. The trail is the machine-readable substrate that lets downstream ceremonies compute coverage without re-reviewing already-reviewed work.

**Per-session record shape:**

```json
{
  "sha_range": "abc123..def456",
  "reviewer": "code-reviewer|patrik|code-reviewer+patrik|waived|ubt-compile",
  "scope": "chain|session",
  "verdict": "ok|warn|blocked|waived|pending",
  "diff_loc": 247,
  "session_id": "..."
}
```

Records land at `tasks/review-trail/YYYY-MM-DD-HHMMSS-{session-id-short}.json` (git-tracked, per-session, no concurrent-write risk — one file per session).

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
`code-reviewer | patrik | code-reviewer+patrik | waived | ubt-compile`

Historical JSON records written before 2026-05-18 retain `reviewer: "sonnet"` as data. No back-compat read path is required — historical records are not consumed by the weekly prelude's sha-range logic. New writes must use the current enum.

The `code-reviewer` value refers specifically to a dispatch of `agents/code-reviewer.md` (Sonnet-locked, read-only). Do NOT substitute a generic Sonnet dispatch and label it `code-reviewer` — the agent file is the contract.

**Daily roll-up:** `/workday-complete` Step 9 reads today's review records via `list-review-trail-records.sh --date-prefix "${TODAY}"` (unions `tasks/review-trail/` and `archive/review-trail/**` — covers the morning-after-weekly-reset edge case) and emits one `**Reviewed:**` line per record into the day's changelog block:

```
**Reviewed:** sha_range=abc..def reviewer=sonnet verdict=ok diff_loc=247
```

If no review records exist for today AND today had non-trivial commits, Step 9 emits `**Reviewed:** none — flag for /workweek-complete Step 7`.

**Weekly archival:** `/workweek-complete` Step 13 moves `tasks/review-trail/*.json` to `archive/review-trail/<week-starting>/` as part of the same archival sweep that moves `tasks/week-changelog/`. Archival happens AFTER Step 7 has consumed the trail (Step 7 runs before Step 13).

**Handoff frontmatter mirror:** when a session-end review fires AND a handoff is also written for this session, the handoff receives a `reviewed_at_session_end:` frontmatter field for audit-trail durability with the content:

```yaml
reviewed_at_session_end: abc123..def456 sonnet 2026-05-08
```

This field is optional; handoffs without it are valid (field is only present when a review was performed in the same session that authored the handoff).

## Downstream load-shedding contract

`/workweek-complete` Step 7 prelude reads the trail before dispatching `coordinator:parallel-code-review`. The prelude narrows the **code-semantics** scope (now chunked across N `code-reviewer-weekly` instances — the Staff Engineer is no longer the gate reviewer); the three mechanical workers always run on the full week diff regardless.

**Prelude logic (Step 7, external to `parallel-code-review` skill body):**

```
1. Glob tasks/review-trail/*.json for the week's date range.
   (intentional: Step 7 runs before Step 13 archival in same invocation — live dir is complete at this point)
2. Compute union of reviewed sha_ranges → reviewed_set.
3. weekly_diff_shas = git log origin/main..HEAD --format=%H
4. unreviewed_set = weekly_diff_shas - reviewed_set
5. cross_segment_seams = files modified in ≥2 different reviewed segments
6. code_semantics_scope = unreviewed_set + cross_segment_seams
   mechanical_scope = full week diff (always)
7. Write tasks/review-trail/.weekly-reviewer-scopes.json:
     {"patrik": "<scope_sha_list>", "patrik_seam_files": "<seam_paths>", "mechanical_workers": "full"}
   (The JSON keys are still named `patrik`/`patrik_seam_files` for back-compat — the helper
   `workweek-trail-scope.sh` was not renamed. Post-restructure the `patrik` SHA set is the
   code-semantics CHUNKING input; `patrik_seam_files` additionally feeds the Staff Engineer's advisory
   Layer-2 pass at Step 7.5.)
   Pass this scope file in the brief to parallel-code-review.
   The synthesizer reads it and narrates:
     "code-semantics chunks scoped to gap+seams; mechanical workers full diff."
```

The `parallel-code-review` skill body IS modified for the N-chunk model (Strand 1), but the doctrine-guarded carve-out from `archive/specs/2026-05-06-parallel-code-review-weekly-gate.md` is preserved: scope-narrowing still happens in Step 7's prelude, and the frozen-diff / orthogonal-lens / no-rewrite-synthesizer conditions still hold (orthogonality now spans the 3 specialist lenses + code-semantics-as-a-class; the N chunks partition that class disjointly by file-scope).

**`cross_segment_seams` defined precisely:** a *segment* is the sha-range of one trail record (one session-end review). Cross-segment seams are the set of file paths that appear in the diff of ≥2 distinct segments — computed by taking the union of files-touched per record and intersecting pairwise. The per-segment file-touch set is derived from `git diff --name-only <sha-range>`. These seams carry integration risk because multiple independent sessions touched them; they feed BOTH the code-semantics chunk review (seam-first chunking gives them extra integration scrutiny) AND the Staff Engineer's advisory Layer-2 pass at Step 7.5, which reads the seam set as an integration-surface signal but does NOT gate merge.

**Verdict subvariant:** when the code-semantics scope is empty AND no findings from any mechanical worker, the synthesizer may emit `OK (code-semantics trail-covered, mechanical clean)` — an informational subvariant of the standard `OK` verdict. The parallel dispatch still runs; no "skip" path exists. This variant signals that the trail successfully shed load without bypassing the safety gate.

**Why mechanical workers are never scoped down:** session-end reviews dispatch only `coordinator:review-code` Branch A.2 (`code-reviewer`). The three mechanical workers (security-audit-worker, dep-cve-auditor, test-evidence-parser) never run at session-end. "Trail-covered" therefore does not mean "all lenses covered" — it means "code-semantics lens covered." Narrowing mechanical workers based on the trail would silently elide their independence property.

## Three-Surface Composition — Automated Build Verdicts (UBT pattern, 2026-05-15)

The review trail accommodates automated build-quality checks via a deferred three-surface
composition. The UBT compile gate is the first example; future automated linters (`clippy`,
`eslint`, `pytest-coverage`) follow the same shape.

### Motivation

Running a UBT build (~30s incremental, low-minutes cold) at session-end blocks quick-save
commits under the concurrent-EM cadence (`tasks/lessons.md:324` — "at most one UBT-dependent
executor in flight"). The three-surface pattern decouples intent-capture (cheap, session-end)
from build-execution (expensive, daily) from gate-enforcement (cheap, weekly).

### Three surfaces and their roles

| Surface | Role | Cost | Trigger |
|---|---|---|---|
| `/session-end` Step 2.9 | Write `verdict=pending` marker if chain-diff touches `control/plugin/**/Source/**/*.{cpp,h}` | Cheap (no build) | Per session |
| `/workday-complete` Step 0c | Resolve today's pending markers — run UBT, parse result, write new resolved record | ~30s incremental | Daily |
| `/workweek-complete` Step 4c | Refuse merge if any `verdict=pending` records have NO resolved sibling | Cheap (scan) | Weekly |

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
no change. See `docs/wiki/holodeck-doctrine.md §7.7` for the full convention.

### Verdict semantics extension

`--verdict` enum extended with `pending` (alongside `ok|warn|blocked|waived`).
`--reviewer` enum extended with `ubt-compile` (alongside `code-reviewer | patrik | code-reviewer+patrik | waived`).
`--scope chain` (existing value — UBT verdicts are chain-scoped, not per-diff-slice).

Spec backlink: `docs/plans/2026-05-15-ubt-compile-gate-review-trail.md` §Shape.

## Boundary-relabeling defect class — a cross-segment seam signal

Chain-end review empirically catches **boundary-relabeling** bugs — where a refactor renames a failure-reason enum, retypes an error code, or relabels a status taxonomy, and prior mid-stream reviews fail to spot the relabel because each reviewer saw only their slice of the diff. The relabeled boundary surfaces only when the full chain is read in one pass.

Pattern shape: a taxonomy / enum / failure-reason vocabulary is refactored, and downstream consumers that pattern-match on the old labels silently fall through to a default arm. Per-commit review confirms each individual rename is correct in isolation; chain-end review reads enough of the chain to notice the relabel happened at all.

**How this maps to the current doctrine:** when partitioning a chain diff into slices, assign one slice specifically to boundary/seam/taxonomy/enum surfaces when present — this is the highest-value partition, not the one to merge into a larger bucket. The defect class is cross-segment by nature; a slice that spans the chain's full vocabulary-change surface ensures at least one `code-reviewer` instance sees the relabel end-to-end. If `code-reviewer` flags a boundary/seam/taxonomy shift, capture it in `tasks/lessons.md` and surface to PM for a plan-shaped decision; do not escalate to a named reviewer within the code-review path.

## Director-altitude review unbundles conflated concerns — and can dissolve a held decision

*2026-05-18, project-rag.* A Director-altitude tiebreaker pass (the Director of Engineering lens — invoked to break a deadlock between two reviewers or to adjudicate a contested architectural call) does more than pick a winner: it frequently **unbundles concerns the prior reviewers had conflated**, and the act of unbundling can dissolve the held decision entirely rather than ratifying either side. Two reviewers arguing "approach A vs approach B" may both be answering the wrong question — the Director lens reframes, splits the bundled concern into its independent axes, and the original A-vs-B framing evaporates because each axis resolves differently.

**Implication for review sequencing:** a Director-altitude reframe is not a failure of the lower-tier reviewers — it is the lens working as intended. Do not treat a dissolved decision as wasted review; the reframe is the value. But do treat it as a signal that the artifact's framing (the plan's problem statement, the stub's decomposition) was carrying a conflation the EM should fix at the source, not just in this one review. Capture the reframe in `tasks/lessons.md` and re-examine whether the same conflation recurs elsewhere in the workstream. This is the architectural-finding disposition path (§ No named-reviewer escalation from code review): the reframe belongs in the planning stream.

## Review-findings folder ownership is by scope header, not timestamp

`tasks/review-findings/YYYYMMDDTHHMMSSZ/` folder names encode *when* a review was dispatched, not *which workstream* owns it. A pickup session that crashed after dispatching a parallel review (but before committing the integrator fixes) leaves a folder that looks like the current workstream's pending review — but may hold a mix of real artifacts (the Staff Engineer.md, security.md at full size) and placeholder stubs (tests.md = "hello") from a different session/chain.

**Rule:** at pickup, before treating any `review-findings/` folder as in-progress work for the current branch, grep the folder's inner `artifact scope:` header and compare its named HEAD SHA against `git rev-parse HEAD`. A mismatch means the review belongs to a different session — don't integrate its findings into the current diff.

## Review-Trail Coverage Audits Must Glob the Archive — Live-Dir Absence Is Not Review Absence

<!-- anchor: Archive-Aware Glob -->

**Review-trail coverage audits must read `archive/review-trail/**`, not just the live dir — `/workweek-complete` archives records weekly, so live-dir absence is not review absence.**

`tasks/review-trail/` only ever holds the current week; any coverage check reading only it systematically under-counts review for anything older. The **review oracle** is git range-membership — `git merge-base --is-ancestor C B && ! ...C A` — over BOTH live (`tasks/review-trail/*.json`) and archived (`archive/review-trail/**/*.json`) records.

*2026-05-27, claude-unreal-holodeck.* A plan-delivery audit's central alarm ("only 4 review-trail records, all this week → most shipped work unreviewed") was an archival artifact — the missing 05-24 record was in `archive/review-trail/2026-05-21/` (moved there by weekly-reset commit `db151655e`), and its `session_id` matched the shipped plan's completion-entry filename suffix. Both audited `implemented` plans were DELIVERED+REVIEWED; zero PARTIAL.

When auditing delivery-vs-review: glob both dirs. The three-oracle plan-delivery audit shape (plan-claim / code-reality-on-disk / review-coverage) + this archive-aware fix were routed to the DoE as a coordinator-universal skill/doctrine candidate via cross-repo memo (`~/.claude/cross-repo/inbox/2026-05-27-plan-delivery-audit-shape.md`).

**Canonical helper:** `list-review-trail-records.sh` — emits the union of live (`tasks/review-trail/*.json`) and archived (`archive/review-trail/**/*.json`) records, NUL-separated, sorted by basename. Absent dirs do not error. All review-trail consumers should route through this helper rather than separate glob calls. See also `docs/wiki/plan-delivery-audit.md` for the full three-oracle audit skill.

## Constant/Identity Bump Is a Multi-Writer Change

*Source: project-rag, 2026-05-28.*

A "one-line" pin or identity bump (version constant, schema revision, protocol constant) is structurally a multi-writer change: the constant is likely vendored in more than one location, and mocks or test fixtures encode its value as a literal. Treating it as a single-file trivial edit produces a commit that appears clean while sibling vendored copies and mocks silently remain at the old value.

**Rule.** Never waive the row-3 review floor on a constant/identity bump on the grounds that it is "just one line." Before committing: grep every vendored copy and mock of the constant, run the touched test surface, and confirm all N copies are updated in the same commit. The bump is complete only when `git grep <old_value>` returns zero hits in non-test-data files.

## Cross-references

- `coordinator:review-code` Branch A.2 — the dispatch surface for the actual `code-reviewer`/the Staff Engineer review invoked from Step 2.8 and Step 2.10
- `coordinator:parallel-code-review` — the merge-gate carve-out doctrine that this trail integrates with (without modifying); Step 7's prelude is the external interface between the trail and this skill
- `docs/wiki/ceremony-calibration.md` § "Session-end-as-defer is hedging in disguise" — **complementary doctrine**: ceremony-calibration prevents using `/session-end` itself as a deferral mechanism; this guide prevents using "`code-reviewer`-only" as deferral within `/session-end`. The two framings are paired: one catches session-level hedging, the other catches review-scale hedging. Future EMs should read both.
- `coordinator/CLAUDE.md` § Review Sequencing — top-level pointer that names this wiki as the authoritative doctrine source
- `archive/specs/2026-05-06-parallel-code-review-weekly-gate.md` — the original spec whose Non-goals required Step 7 scope-narrowing to be implemented externally (not inside the parallel-code-review skill body)
