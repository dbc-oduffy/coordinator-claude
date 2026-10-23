---
name: plan-delivery-audit
description: Triangulate plan claims against code and reviews.
version: 1.0.0
allowed-tools: ["Read", "Grep", "Glob", "Bash", "Agent"]
argument-hint: "[plan-glob — default: docs/plans/*.md]"
---

# Plan-Delivery Audit

Triangulate each plan's own `status:` claim against code-reality and review-trail coverage,
resolving every plan into exactly one of five buckets. Invoke after a crash/partition, a
shipped-work reconciliation, or whenever `status: implemented` needs independent verification.

## Phase 1 — Gather and filter (EM, ~2 min)

Glob the plan set (default `docs/plans/*.md`, or the caller-supplied glob) and exclude sidecars —
any filename containing `.prior-art-check`, `.coverage-check`, `.docs-check`, `.review-`, or
`.check.`. They inherit their parent plan's `status:` and pollute the candidate set if left in.

Rough-sort by frontmatter `status:`:
- `superseded` / `closed` / `abandoned` / `cancelled` → **ABANDONED**, no further oracle work.
- `draft` / `in-progress` / `reviewed` → **IN-FLIGHT**, no further oracle work.
- `implemented` / `shipped` → queue for Oracle 2 + 3.

## The three oracles

Read each independently; Oracle 1 is the hypothesis, Oracles 2 and 3 test it; never let Oracle 1 color how you read them.

**Oracle 1 — plan-claim.** The plan's own `status:`, per-AC status column, execution/`reviewed:`
notes. A claim, not a verdict.

**Oracle 2 — code-reality.** Two required sub-checks.

(a) *Cited-artifact existence* — for every file/path/symbol/schema-field the plan claims to have
created or changed, confirm it exists at HEAD in the claimed shape.
<!-- engine-gap: field=oracle2.artifact_claim_verification producer=unknown memo=engine-gap-markers-name-a-memo-that-was-never-filed.md -->
Dispatch shape: for ≥4 plans, one parallel read-only Sonnet scout per plan — reads the plan's
scope/chunks/AC prose, extracts concrete artifact claims, checks each, reports PRESENT / ABSENT /
UNVERIFIABLE. No file modification, commit, or push during Oracle 2. If a plan names no concrete
artifacts, Oracle 2(a) is unverifiable — treat the plan conservatively (see tie-breaks below).

> **Do not ask whether to dispatch** — invoking this skill IS the request for the dispatch this
> step names; it dissolves no gate this skill's own body names.

(b) *Project test suite* — not on the implicit-grant ceremony list; gate via (shape per
`${CLAUDE_PLUGIN_ROOT}/snippets/resolve-coordinator-bin.md`; PowerShell shown)
`& "$env:COORDINATOR_SETTINGS_HOME\bin\tier-u-grant-cli.exe" check`
the way `coordinator:validate` does. Granted: run the project's `fast_test_cmd` at HEAD once for
the batch; a failing suite falsifies even when artifacts check out. Ungranted: report
skipped-pending-grant; never substitute a hand-rolled command or treat an unrun suite as passing.

**Oracle 3 — review (archive-aware).** Trail records live at BOTH `state/review-trail/**/*.json`
AND `archive/review-trail/**/*.json` — `/workweek-complete` moves the current week's records into
`archive/review-trail/<week>/` on every reset, so a live-only glob under-counts. There is no
lister CLI. Glob both trees, union the results, and sort by **basename**, not full path —
week-subdirectory ordering inverts on a full-path sort.

For each returned record, call `coordinator_core.git_ancestry.is_covered(commit, start_sha,
end_sha)` — the single source of truth for the covered-by-range polarity — for each of the
plan's delivery commits against the record's `sha_range`. ≥1 record covering every delivery
commit = COVERED. No covering record = UNCOVERED only if delivery predates the
trail's freeze; after it, Oracle 3 is `UNAVAILABLE`.

**The corpus is frozen** (newest record `2026-08-26-211749`; no live writer). Reviews land in the
reviewer sidecar's `findings_ledger`, which this oracle cannot read, so a post-freeze plan returns
UNCOVERED reviewed or not. Read the sidecar before reporting a review missing. Delivery commits
unnamed in frontmatter or notes: identify them from the plan's ACs.

## Bucket decision tree

| Oracle 1 | Oracle 2 | Oracle 3 | Bucket |
|---|---|---|---|
| `implemented`/`shipped` | artifacts exist AND tests green | ≥1 record covers delivery commits | **DELIVERED+REVIEWED** |
| `implemented`/`shipped` | artifacts exist AND tests green | no record covers, delivery predates the freeze | **DELIVERED-UNREVIEWED** |
| `implemented`/`shipped` | artifacts exist AND tests green | `UNAVAILABLE` (post-freeze) | **REVIEW-UNKNOWN** |
| `implemented`/`shipped` | ≥1 artifact absent/wrong at HEAD, OR tests red, OR unverifiable | (any) | **PARTIAL** |
| `in-progress`/`draft`/`reviewed` | (any) | (any) | **IN-FLIGHT** |
| `superseded`/`closed`/`abandoned`/`cancelled` | (any) | (any) | **ABANDONED** |

Tie-breaks: `implemented` with nothing independently checkable (no artifact claims, no test
suite) → **PARTIAL**, not DELIVERED — self-assertion alone is not delivery. `draft` with
commit evidence of shipped work still resolves to **IN-FLIGHT** — flip the frontmatter rather
than reclassify here. **DELIVERED-UNREVIEWED** is a real state, not an error — recommend a
`code-reviewer` dispatch against the delivery diff, never backdoor a review claim.
**REVIEW-UNKNOWN** never enters that queue -- the oracle is blind, not negative. **ABANDONED**
with Oracle 2 evidence of shipped code should surface a `status: superseded` +
`superseded_by:` flip recommendation.

## Output

Markdown table, one row per plan — `Plan | Oracle 1 | Oracle 2 | Oracle 3 | Bucket` — followed by:
count per bucket, the DELIVERED-UNREVIEWED catch-up queue (with delivery commits), ABANDONED
frontmatter-flip recommendations, and a method-notes line for any plan with unverifiable
Oracle 2 or unresolved delivery commits.

Save to `state/audits/YYYY-MM-DD-<SID_SHORT>-plan-delivery-audit.md` (`SID_SHORT` = first 8
characters of `cs_resolve_session_id`, else an 8-char nonce; create `state/audits/` if absent).

## Dispatch sequencing

Phase 2: parallel Oracle-2(a) scouts; EM-side, Oracle 2(b) once and Oracle 3 per plan. Phase 3:
apply the decision tree, write the table, and surface DELIVERED-UNREVIEWED plans to the PM with a
`code-reviewer` recommendation — never dispatch it autonomously.
