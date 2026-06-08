---
title: Reviewer-Routed Workers
system: reviewer-routed-workers
status: distilled
distilled_from:
  - archive/specs/2026-04-29-reviewer-routed-workers.md
distilled_at: 2026-05-06
distilled_run: 2026-05-06-13h00
---

# Reviewer-Routed Workers

## Overview

**Reviewer-routed workers** add mechanical leverage to the agent hierarchy without inflating persona count. Reviewers (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer) name workers in a `## Worker Dispatch Recommendations` block; the review-integrator preserves the block verbatim; the EM dispatches in a follow-up. This avoided the alternative draft (3 new Opus personas + 10-12 workers + classifier rewrite ≈ 15-18 new dispatch surfaces).

**Roster doctrine (canonical):** Personas are for distinct **judgment** styles. Workers are for **mechanical leverage** with structured output. Threat-modeling and test-pyramid are absorbable as lenses, not new personas.

## Architecture

### Phase 1 workers (shipped)

| Worker | Tools | Named by | Job |
|--------|-------|----------|-----|
| `test-evidence-parser` | Bash, Read | the Staff Engineer, the Game Dev Reviewer | Classify failures: real / flake / env / timeout / known-skip |
| `security-audit-worker` | Read, Grep, Glob, restricted Bash (semgrep, bandit, gitleaks, trufflehog) | the Staff Engineer | Path traversal, validation traps, injection, secrets in source |
| `dep-cve-auditor` | Bash, Read | the Staff Engineer / EM (periodic + on-demand) | npm/pip-audit normalize |
| `doc-link-checker` | Bash, Read, WebFetch | EM (opportunistic from `/update-docs`); plan-author (default on path-move plans, subject to the substrate precondition § doc-link-checker Substrate Precondition) | Markdown link validation; sleep 1s, cap 100 external URLs |

### Worker spec requirements

Each worker spec includes:

- Structured-output contract (markdown table preferred over JSON).
- DONE-after-write protocol.
- ≥3 specific failure modes enumerated with structured-output shape per case.
- 3-4 dispatch examples in frontmatter.

## Key Patterns

### Reviewer protocol — "name the worker, don't dispatch"

The Staff Engineer, the Game Dev Reviewer, and the Data Science Reviewer each get a `## Worker Dispatch Recommendations` section in their prompt. Reviewers do **not** dispatch directly — they surface a recommendation to the EM with a one-line rationale per worker. They recommend a worker only when its analysis would add evidence the findings don't already cover.

### Integrator preserves the block verbatim

The review-integrator preserves the `Worker Dispatch Recommendations` block verbatim and **does not act on it**. The EM reads it after integration and dispatches in a follow-up step.

### Delta-vs-baseline acceptance

Each replay's worker output must (a) surface an issue not in the original review, (b) confirm with stronger mechanical evidence, or (c) cleanly rule out a class of concern. Three failed replays → reconsider the worker before percolating.

### Boundary: security-audit-worker vs dep-cve-auditor

- `security-audit-worker` reads **code** (path traversal, injection, secrets in source).
- `dep-cve-auditor` reads **dependency manifests** (`package.json`, `requirements.txt`).

No overlap.

### Periodic dispatch via /workweek-complete (change-aware)

`dep-cve-auditor` runs both periodically and the Staff Engineer-named. The periodic cadence is owned by `/workweek-complete` Step 4h — change-aware: it dispatches the auditor only when a tracked dependency manifest (`package.json`, `requirements.txt`, `pyproject.toml`, `Cargo.toml`, `go.mod`, or their lock files) actually changed in the last 7 days. Repos with no dep surface (e.g. the `~/.claude` meta-repo's scripts-only `package.json`) skip silently every week. The worker does not schedule its own re-runs and does not drop recheck-marker files — the marker mechanism was retired 2026-06-08 because for low-no-op-cost surfaces it produced ceremony with no signal.

## Phase 2 (deferred): /merge-to-main 5-step gate

Five questions the merge gate asks before allowing a merge:

1. User-visible changes summarized?
2. Schema/version bumps flagged?
3. Install/setup scripts touched (sandbox)?
4. CHANGELOG updated where applicable?
5. The Staff Engineer review of release artifact required if ANY of: public API additions, version bump, install/setup script touched, >50 commits since last tag, breaking-change CHANGELOG entries.

## Gotchas

- **Validate worker findings independently.** Unused workers are unvalidated risk — a worker that's never been replayed against a real review may not survive contact with non-trivial corpora.
- **Workers feed reviewers, not vice versa.** A worker dispatched without a reviewer asking for it loses its routing-intelligence framing and becomes raw mechanical output the EM has to interpret cold.

## `doc-link-checker` Substrate Precondition — Skip on Private-Repo Absolute Self-URLs

**`doc-link-checker` adds no signal on a private repo where docs cite absolute self-URLs — don't reflex-dispatch it.**

The "route reviewer-workers as routine" default has a substrate precondition. For `doc-link-checker`, dispatch only when the diff adds **RELATIVE markdown links** OR links to **PUBLIC URLs**. Private-repo absolute self-links → skip, note why, defer the anchor check to a one-click post-merge sanity.

*2026-05-24, claude-unreal-holodeck.* the Staff Engineer routed `doc-link-checker` post-implementation (the routine reviewer-worker default). But: (a) external HEAD requests to `github.com/dbc-oduffy/...` URLs return 401/404 (private repo, no auth in the worker), and (b) the hotwire links were absolute GitHub blob URLs, not relative markdown links, so the relative-link-resolution leg didn't apply — and `validate-references` (in `run-all-checks`) already covers relative links. The one valuable check (does the `#anchor` resolve against the rendered heading) only works post-merge by an authed human clicking it.

Refines coordinator CLAUDE.md § Reviewer-Routed Workers (distributed-abstention applies to the EM's dispatch decision too — don't dispatch a worker into a substrate where it must abstain).

## Specialist workers as routine post-implementation lens

**Specialist worker lenses catch what generalist reviewer lenses miss — route security-audit/dep-cve/doc-link/test-evidence post-implementation as a routine pass, not only on the Staff Engineer recommendation.**
**Why:** Two the Staff Engineer architectural review passes on one plan caught 16 findings but missed a bare `-e .` editable-install anchor in a recovery script. The security-audit-worker caught it next pass because the security lens forces the question "what if the runtime invocation is hostile?" the Staff Engineer's correctness-of-design and the specialist's correctness-of-deployment are different lenses.
**How to apply:** after each post-implementation review, dispatch the specialist roster (security-audit-worker, dep-cve-auditor, doc-link-checker, test-evidence-parser) as a bundle, not just on explicit the Staff Engineer recommendation. The costs are mechanical; the catches are structural.

*Source: holodeck `state/lessons.md` (holodeck-L153, central-promoted 2026-05-28).*

## Reviewer-Recommended Workers Are Real Deliverables — Track and Gate

*Source: claude-central, 2026-05-28. Empirical: skipping security-audit-worker led EM to standardize on `eval` when `bash -c` was correct; PM caught the gap.*

The `## Worker Dispatch Recommendations` block in a reviewer's output is the **output of the review** — not a suggestion list. The doctrine says "EM dispatches in follow-up," but the empirical skip rate is high. A skipped worker recommendation is a skipped review lens; the finding it would have surfaced ships instead.

**Rule.** After every review, before writing the marker-trail record, verify that every named worker in the `## Worker Dispatch Recommendations` block has been dispatched and its output integrated. Treat an undispatched recommendation the same as an unaddressed P1 finding. Sessions that end with pending worker recommendations should note them in `state/lessons.md` for the next pickup.

*Note: a workstream-complete checklist gate was proposed (skills/workstream-complete Step 2.9 "reviewer-recommended workers dispatched: y/n"). Pending authoring at that site.*

## Reviewer Correctly Suppressing a Worker Is Not Worker Validation — Exercise Every New Worker in Phase 1

**A well-calibrated reviewer declining to name a worker on a small/clear diff is the suppress-if-redundant rule working — not a protocol failure, and not evidence the worker is sound.** The two facts are independent: the reviewer's restraint validates the *routing layer*; it says nothing about whether the *worker itself* produces correct, useful output. Percolating a worker spec that has never actually run is a hidden risk no amount of correct reviewer suppression retires.

This sharpens the § Gotchas bullet "Validate worker findings independently — unused workers are unvalidated risk" and the § Delta-vs-baseline acceptance criterion: those say *don't ship an unreplayed worker*; this names *when the gap hides*. The gap hides precisely when the reviewer is well-calibrated, because a good Opus reviewer correctly suppresses the worker on exactly the small/clear diffs you'd otherwise have used to smoke-test it — so "no reviewer triggered it" reads as "validated by absence of complaint" when it is the opposite.

**Rule.** When introducing a new reviewer-routed worker, exercise it on a representative target as part of Phase 1 validation **even if no reviewer named it on the diffs you happened to run.** The delta-vs-baseline criterion (surface a new issue / confirm with stronger evidence / cleanly rule out a class) applies to the *worker*, not only to the routing protocol. Do not treat correct reviewer suppression as a substitute for an independent worker exercise.

**Why.** *2026-04-29 reviewer-routed-workers Phase 1:* the `test-evidence-parser` worker, run independently against a representative target, surfaced 13 failures that the Staff Engineer's focused (correctly-scoped) review never named — the Staff Engineer's suppression was right for the diff, and the worker still found real signal the review lens missed. Suppression-correct and worker-valuable were both true at once.

## Reference

- Related: [reviewer-premise-challenge](reviewer-premise-challenge.md)
- Source plan: `archive/specs/2026-04-29-reviewer-routed-workers.md`
