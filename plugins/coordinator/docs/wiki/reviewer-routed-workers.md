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

**Reviewer-routed workers** add mechanical leverage to the [agent hierarchy](agent-hierarchy.md) without inflating reviewer count. Reviewers (the Staff Engineer, the Game Dev Reviewer, the Data Science Reviewer) name workers in a `## Worker Dispatch Recommendations` block; the [review-integrator](reviewer-output-schema.md) preserves the block verbatim; the EM dispatches in a follow-up. This avoided the alternative draft (3 new Opus reviewer roles + 10-12 workers + classifier rewrite ≈ 15-18 new dispatch surfaces).

**Roster doctrine (canonical):** Reviewer roles are for distinct **judgment** styles. Workers are for **mechanical leverage** with structured output. Threat-modeling and test-pyramid are absorbable as lenses, not new reviewer roles.

## Architecture

### Phase 1 workers (shipped)

| Worker | Tools | Named by | Job |
|--------|-------|----------|-----|
| `test-evidence-parser` | Bash, Read | the Staff Engineer, the Game Dev Reviewer | Classify failures: real / flake / env / timeout / known-skip |
| `security-audit-worker` | Read, Grep, Glob, restricted Bash (semgrep, bandit, gitleaks, trufflehog) | the Staff Engineer | Path traversal, validation traps, injection, secrets in source |
| `dep-cve-auditor` | Bash, Read | the Staff Engineer / EM (periodic + on-demand) | npm/pip-audit normalize |
| `doc-link-checker` | Bash, Read, WebFetch | EM (opportunistic from `/update-docs`) | Markdown link validation; sleep 1s, cap 100 external URLs |

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

The [review-integrator](reviewer-output-schema.md) preserves the `Worker Dispatch Recommendations` block verbatim and **does not act on it**. The EM reads it after integration and dispatches in a follow-up step.

### Delta-vs-baseline acceptance

Each replay's worker output must (a) surface an issue not in the original review, (b) confirm with stronger mechanical evidence, or (c) cleanly rule out a class of concern. Three failed replays → reconsider the worker before percolating.

### Boundary: security-audit-worker vs dep-cve-auditor

- `security-audit-worker` reads **code** (path traversal, injection, secrets in source).
- `dep-cve-auditor` reads **dependency manifests** (`package.json`, `requirements.txt`).

No overlap.

### Periodic dispatch via recheck markers

`dep-cve-auditor` runs both periodically and Staff Engineer-named. First run drops `tasks/cve-recheck-due-YYYY-MM-DD.md` dated +7 days; `/workday-start` Step 1.6 globs `tasks/*-recheck-due-*.md` and surfaces expiring markers.

## Phase 2 (deferred): /merge-to-main 5-step gate

Five questions the merge gate asks before allowing a merge:

1. User-visible changes summarized?
2. Schema/version bumps flagged?
3. Install/setup scripts touched (sandbox)?
4. CHANGELOG updated where applicable?
5. Staff Engineer review of release artifact required if ANY of: public API additions, version bump, install/setup script touched, >50 commits since last tag, breaking-change CHANGELOG entries.

## Gotchas

- **Validate worker findings independently.** Unused workers are unvalidated risk — a worker that's never been replayed against a real review may not survive contact with non-trivial corpora.
- **Workers feed reviewers, not vice versa.** A worker dispatched without a reviewer asking for it loses its routing-intelligence framing and becomes raw mechanical output the EM has to interpret cold.

## Reference

- Related: [agent-hierarchy](agent-hierarchy.md), [reviewer-output-schema](reviewer-output-schema.md), [reviewer-premise-challenge](reviewer-premise-challenge.md)
- Source plan: `archive/specs/2026-04-29-reviewer-routed-workers.md`
