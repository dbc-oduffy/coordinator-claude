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
| Any executor dispatched, OR >50 LOC code change, OR shared schema/seam touched | **Sonnet** (review-code Branch A.2 single reviewer) |
| Chain-end (started with `/pickup`, ending without `/handoff`/`/spinoff`) AND chain diff is non-trivial | **Sonnet** on chain diff (default) |
| Chain-end AND any of: chain diff >500 LOC, touches public API / schema / security-adjacent code, ≥3 segments in chain, novel external API integration | **Sonnet + the Staff Engineer** (EM-judged escalation) |

**Precedence rule:** chain-end rows (4, 5) override session-end rows (1, 2, 3) when both apply — the chain diff is the integration-risk artifact.

**Anchored-ranges note:** the numeric thresholds (50 LOC, 500 LOC, ≥3 segments) are worked examples for EM calibration, not gates that auto-dispatch or auto-skip. The executor-dispatch trigger in row 3 is mechanical; the diff-size dimension in rows 4–5 is judgment.

## Anti-ceremony-bias tripwire

> "If you're considering Sonnet-only because escalation feels like ceremony rather than because the diff is genuinely shallow — escalate. The Staff Engineer is one dispatch away; the cost of redundant review is one Opus call. The cost of unreviewed integration risk shipping to main is hours of debugging."

**Doctrine-table defaults are defaults, not negotiation starting points.** Each row in the diff-shape table above specifies a *default review scale*. The EM has waive authority for genuinely shallow diffs — a one-line rename, a mechanical typo fix — but "I already did plan-time review" and "the workstream felt small" are not waive grounds; they are the rationalization shapes the anti-ceremony bias takes. Plan-time review and post-implementation review catch different defect classes (see § Why post-implementation review is not redundant with plan-time review below). The table row that matches the session shape is the starting point; the EM must articulate a diff-shape reason to waive below it, not a coverage-completeness reason.

## Why post-implementation review is not redundant with plan-time review

EM judgment on row 3+ keeps waive authority for genuinely shallow diffs (a one-line rename caught by an executor, a mechanical typo fix, a single-file refactor with obvious shape). The diff-shape table's defaults stand; this section names four recurring rationalization patterns that look like judgment but are actually shape-mismatched substitutions, so future EMs can pattern-match against them.

**1. Plan-time review and post-implementation review catch different defect classes.** They are complementary, not substitutional.

- Plan-time (prior-art-checker + the Staff Engineer on the plan): catches architectural shape, prior-art conflicts, substrate verification — *what we're about to do*.
- Post-implementation Sonnet on the diff: catches what executors actually did vs. what the plan said — substitution misses, integration-seam mismatches between workstreams, scope creep, executor cleverness where mechanical was wanted.

If a waive rationale boils down to "the plan was already reviewed," that's the substitution error: the plan is reviewed; the diff is not.

**2. Mechanical executor self-acceptance gates are not review proxies.** Grep returns 0, pytest passes, `bash -n` clean — these are correctness floors, not the lens a reviewer brings. None of them exercise cross-file integration, schema-vs-consumer agreement (e.g. did the producer schema in segment 2 actually match the consumer probe in segment 4 — *both green individually* doesn't mean *consistent across the seam*), or scope-creep detection. Treating mechanical gates as a stand-in for review collapses two distinct safety properties into one.

**3. The anti-ceremony tripwire fires symmetrically.** The existing tripwire ("if Sonnet feels like ceremony rather than because the diff is genuinely shallow — escalate to the Staff Engineer") catches the *escalate-direction* hedge. The reverse direction — "if Sonnet-after-already-doing-plan-review feels like ceremony — skip" — is the same motion running backwards. Same shape, opposite sign. The tripwire applies in both directions: ceremony-feeling is the tell either way.

**4. "We've done a lot of review already" is the shape wrap-up pressure takes.** At `/session-end`, token-budget anxiety and session-fatigue create implicit "close out" pressure. Dressed up, that becomes "distributed coverage upstream was sufficient." Bare, it's: one more dispatch felt like one more thing. Naming this pattern explicitly is the durable fix — future EMs hitting the same pressure can recognize the shape.

**The pattern-match tell:** if the EM is drafting a "waiving with rationale" sentence on a row-3+ session, the rationale itself is the tell. Compose the sentence; read it back; if it leans on plan-time coverage, executor gates, distributed/heavy upstream review, or "we've already done a lot" — run the Sonnet review. It's one dispatch. The marker trail records `verdict=ok` in seconds and downstream load-shedding still benefits.

**Summary.** Plan-time review (writing-plans pre-flight) and post-impl review (session-end review) catch different defect classes — pre-flight finds substrate/path/framework mismatches, post-impl finds integration/test-coverage/edge-case gaps. Doctrine-table defaults are defaults, not negotiation starting points; don't drop session-end review because "pre-flight passed."

**Worked example.** A multi-executor session shipped a substantial workstream with plan-time prior-art-check (7 findings folded), plan-time the Staff Engineer review (8 findings folded), per-executor self-acceptance gates (all PASS), and a final-segment validation including an OOM smoke test. The EM waived session-end Sonnet on the rationale "distributed coverage upstream." The audited holes: a the Staff Engineer plan-time finding had been factually wrong (the executor caught it — meaning plan-review surface had a leak that *more downstream eyes*, not fewer, was the right response to); one executor segment swept up unrelated concurrent work whose commit message described only the headline change; the OOM smoke passed in 8s of a 600s budget without verifying it had actually exercised the install path vs. short-circuiting on cached state. None of these were catchable by plan-time review or by mechanical executor gates. They were exactly the class of finding a fresh Sonnet lens on the actual diff catches.

## Findings disposition — fix everything, including nitpicks

A reviewer verdict of `OK` with N "below blocking threshold" observations is not a license to commit and move on. Those observations *are* the review output. The diff is fresh, the EM has context, and folding them in now costs a fraction of what they cost three weeks later when someone is hunting the bug they hinted at.

**Rule:** all findings of any severity fold in via `coordinator:review-integrator` before the marker-trail write. P0 / P1 / P2 / nitpick / observation / note / "consider" — same treatment. The integrator escalates real disagreements; it does not silently skip on severity.

**The only legitimate skip path** is a real tradeoff that escalates to PM per `coordinator/CLAUDE.md` § Reviewer findings — apply, don't ratify: cost/value, scope/polish, architectural direction. "Recorded below blocking threshold" framing in an EM wrap-up sentence is the tell that this rule was skipped — re-open the diff, fold the findings, then write the marker.

**Verdict semantics under this rule.** The marker trail's `verdict` field records what the reviewer found on the *pre-fix* diff (`ok` / `warn` / `blocked`), not what shipped. The verdict is a downstream load-shedding signal; the trail is not a fix-completion log. A pre-fix `verdict=ok` with three observations all folded in is the expected shape, not a contradiction.

## Marker trail mechanics

Every completed session-end review writes a small JSON record to disk. The trail is the machine-readable substrate that lets downstream ceremonies compute coverage without re-reviewing already-reviewed work.

**Per-session record shape:**

```json
{
  "sha_range": "abc123..def456",
  "reviewer": "sonnet|patrik|sonnet+patrik|waived",
  "scope": "chain|session",
  "verdict": "ok|warn|blocked|waived",
  "diff_loc": 247,
  "session_id": "..."
}
```

<!-- Review: the Staff Engineer — reviewer field example previously showed "sonnet|patrik" (incomplete);
     updated to show all four valid enum values: sonnet|patrik|sonnet+patrik|waived,
     matching the --reviewer enum in coordinator-write-review-trail.sh. -->

Records land at `tasks/review-trail/YYYY-MM-DD-HHMMSS-{session-id-short}.json` (git-tracked, per-session, no concurrent-write risk — one file per session).

**Helper:** `coordinator-write-review-trail.sh` — named-arg interface:

```sh
coordinator-write-review-trail.sh \
  --sha-range abc123..def456 \
  --reviewer sonnet \
  --scope chain \
  --verdict ok \
  --diff-loc 247
```

Session-id resolution uses strict precedence: `CLAUDE_SESSION_ID` environment variable first; sentinel fallback (`.git/coordinator-sessions/.current-session-id`) only when the env var is empty. The helper fails loud (exit 2) on collision detection — if the target file already exists with different content, it exits non-zero and does not overwrite. If it already exists with byte-identical content, it exits 0 (idempotent no-op).

**Daily roll-up:** `/workday-complete` Step 9 reads today's `tasks/review-trail/*.json` and emits one `**Reviewed:**` line per record into the day's changelog block:

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

`/workweek-complete` Step 7 prelude reads the trail before dispatching `coordinator:parallel-code-review`. The prelude narrows the scope passed to the Staff Engineer reviewer; the three mechanical workers always run on the full week diff regardless.

**Prelude logic (Step 7, external to `parallel-code-review` skill body):**

```
1. Glob tasks/review-trail/*.json for the week's date range.
2. Compute union of reviewed sha_ranges → reviewed_set.
3. weekly_diff_shas = git log origin/main..HEAD --format=%H
4. unreviewed_set = weekly_diff_shas - reviewed_set
5. cross_segment_seams = files modified in ≥2 different reviewed segments
6. patrik_scope = unreviewed_set + cross_segment_seams
   mechanical_scope = full week diff (always)
7. Write tasks/review-trail/.weekly-reviewer-scopes.json:
     {"patrik": "<patrik_scope_sha_list>", "mechanical_workers": "full"}
   Pass this scope file in the brief to parallel-code-review.
   The synthesizer reads it and narrates:
     "the Staff Engineer scoped to gap+seams; mechanical workers full diff."
```

The `parallel-code-review` skill body itself is NOT modified. All scope-narrowing happens in Step 7's prelude, preserving the doctrine-guarded carve-out from `archive/specs/2026-05-06-parallel-code-review-weekly-gate.md`.

**`cross_segment_seams` defined precisely:** a *segment* is the sha-range of one trail record (one session-end review). Cross-segment seams are the set of file paths that appear in the diff of ≥2 distinct segments — computed by taking the union of files-touched per record and intersecting pairwise. The per-segment file-touch set is derived from `git diff --name-only <sha-range>`. These seams carry integration risk because multiple independent sessions touched them; they warrant fresh the Staff Engineer attention regardless of whether each individual session already passed review.

**Verdict subvariant:** when `patrik_scope` is empty AND no findings from any mechanical worker, the synthesizer may emit `OK (patrik trail-covered, mechanical clean)` — an informational subvariant of the standard `OK` verdict. The parallel dispatch still runs; no "skip" path exists. This variant signals that the trail successfully shed load without bypassing the safety gate.

**Why mechanical workers are never scoped down:** session-end reviews dispatch only `coordinator:review-code` Branch A.2 (the Staff Engineer or Sonnet). The three mechanical workers (security-audit-worker, dep-cve-auditor, test-evidence-parser) never run at session-end. "Trail-covered" therefore does not mean "all four lenses covered" — it means "the Staff Engineer lens covered." Narrowing mechanical workers based on the trail would silently elide their independence property.

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
`--reviewer` enum extended with `ubt-compile` (alongside `sonnet|patrik|sonnet+patrik|waived`).
`--scope chain` (existing value — UBT verdicts are chain-scoped, not per-diff-slice).

Spec backlink: `docs/plans/2026-05-15-ubt-compile-gate-review-trail.md` §Shape.

## Cross-references

- `coordinator:review-code` Branch A.2 — the dispatch surface for the actual Sonnet/the Staff Engineer review invoked from Step 2.8 and Step 2.10
- `coordinator:parallel-code-review` — the merge-gate carve-out doctrine that this trail integrates with (without modifying); Step 7's prelude is the external interface between the trail and this skill
- `docs/wiki/ceremony-calibration.md` § "Session-end-as-defer is hedging in disguise" — **complementary doctrine**: ceremony-calibration prevents using `/session-end` itself as a deferral mechanism; this guide prevents using "Sonnet-only" as deferral within `/session-end`. The two framings are paired: one catches session-level hedging, the other catches review-scale hedging. Future EMs should read both.
- `coordinator/CLAUDE.md` § Review Sequencing — top-level pointer that names this wiki as the authoritative doctrine source
- `archive/specs/2026-05-06-parallel-code-review-weekly-gate.md` — the original spec whose Non-goals required Step 7 scope-narrowing to be implemented externally (not inside the parallel-code-review skill body)
