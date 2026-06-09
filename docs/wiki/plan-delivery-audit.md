---
kind: wiki
title: coordinator:plan-delivery-audit — Three-Oracle Pattern
status: active
created: 2026-05-28
provenance:
  - archived_spec: archive/specs/2026-05-28-archive-aware-review-oracle-and-audit-skill.md
    original_path: docs/plans/2026-05-28-archive-aware-review-oracle-and-audit-skill.md
    last_verbose_sha: n/a
    distilled: 2026-05-28
---

# coordinator:plan-delivery-audit — Three-Oracle Pattern

<!-- spec-backlink: docs/plans/2026-05-28-archive-aware-review-oracle-and-audit-skill.md -->

`coordinator:plan-delivery-audit` is a skill for answering "did we actually deliver what we think we delivered?" — triggered after a crash, a session gap, or any moment of "did we finish what we thought we finished?" Runs in-session; does not require a separate dispatch.

## The Three-Oracle Pattern

Each plan is classified by triangulating three independent oracles:

### Oracle 1 — Plan-Claim

Source: plan frontmatter + `## Acceptance Criteria` bindable table.

Reads what the plan **claimed** would be delivered: goals, ACs, stated implementation shape.

### Oracle 2 — Code-Reality

Source: `git merge-base <base-branch> HEAD..HEAD` range check against the plan's target files.

Reads what **actually landed** in the working tree: commits, file mutations, diffs.

### Oracle 3 — Review Coverage

Source: archive-aware review-trail glob — `state/review-trail/**` AND `archive/review-trail/**`.

Reads whether the delivered work **was reviewed** at workstream-complete. Must use both live and archived dirs (see § Archive-Aware Glob below).

## Five Classification Buckets

| Bucket | Meaning |
|--------|---------|
| DELIVERED+REVIEWED | Code-reality matches plan-claim AND review-trail record exists in sha-range |
| DELIVERED-UNREVIEWED | Code-reality matches plan-claim BUT no review-trail record in sha-range |
| PARTIAL | Code-reality partially matches plan-claim; some ACs green, some missing |
| IN-FLIGHT | Plan claims status=in-progress; code-reality shows partial commits |
| ABANDONED | Plan frontmatter shows deployed_state=abandoned OR no commits in sha-range |

## Archive-Aware Review-Trail Glob

All review-trail consumers must glob BOTH:
- `state/review-trail/**` — current week's records
- `archive/review-trail/**` — prior weeks' records (moved by `/workweek-complete` Step 13)

`/workweek-complete` Step 13 moves `state/review-trail/*.json` into `archive/review-trail/<week-starting>/` on every weekly reset. Live-only readers systematically under-count review for anything older than one week.

**The 2026-05-27 holodeck "most shipped work is unreviewed" alarm was a pure archival artifact.** The missing 05-24 record was in `archive/review-trail/2026-05-21/`; both audited plans were DELIVERED+REVIEWED, not PARTIAL.

**Canonical helper:** `bin/list-review-trail-records.sh` — emits the union of live + archived records, NUL-separated, sorted by basename. Absent dirs do not error.

## When to Invoke

- After any crash or context reset where session state is uncertain
- When `/pickup` handoff claims X was delivered but git tells a different story
- Before declaring a workstream "complete" at `/workstream-complete` or `/handoff`
- `/workweek-complete` deep-audit of the week's delivery record

## Decision Records

- **DR-135** — Archive-aware review-trail glob: all consumers must read state/review-trail/** AND archive/review-trail/**; canonical helper bin/list-review-trail-records.sh
- **DR-136** — coordinator:plan-delivery-audit skill with three-oracle pattern (plan-claim, code-reality, review-coverage) and five classification buckets
