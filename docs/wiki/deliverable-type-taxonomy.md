---
title: "Deliverable-Type Taxonomy — kind-discriminated frontmatter schemas for ephemeral .md artifacts"
kind: wiki
audience: coordinator-em
created: 2026-06-23
system: frontmatter-validation
---

# Deliverable-Type Taxonomy

<!-- Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C1 -->
<!-- Negative-spec: the old path keyed validation on *directory glob only* (all docs/plans/*.md → plan.yaml).
     The new path keys on frontmatter `kind:` first, glob fallback second. These are distinct mechanisms
     with distinct jobs — do NOT conflate them. kind: drives VALIDATION selection; applies_to drives ENUMERATION. -->

Each coordinator artifact family that lives under `docs/plans/` but is not a plan gets its own
content-shaped schema. Validation is discriminated by `kind:` (frontmatter), not by path alone.
`applies_to` in each schema is the enumeration surface walked by `query-records --type <type>`.

---

## Design split: kind vs applies_to

| Mechanism | Purpose | Consumer |
|---|---|---|
| `kinds:` list in schema | Validation selection — `matchSchema()` routes `kind:` to the right schema | Hook (`validate-frontmatter-schema.js`) |
| `applies_to` glob in schema | Enumeration — `query-records` walks the glob to find records of that type | `bin/query-records.js` |

`kind:` drives validation; `applies_to` drives enumeration. A schema needs both: `kinds:` so the hook routes correctly, `applies_to` so `query-records --type` can enumerate files on disk.

---

## Artifact type registry

| Schema name | `kinds:` values (canonical first) | `applies_to` glob | Required fields | Optional fields |
|---|---|---|---|---|
| `review-sidecar` | `staff-eng-review`, `eng-director-review`, `staff-ux-review`, `staff-game-dev-review`, `staff-data-sci-review`, `senior-front-end-review`, `code-review` *(role-based canonical)* + `plan-review`, `review`, `review-sidecar`, `the Staff Engineer-review`, `substrate-adjudication`, `plan-rereview` *(legacy resolvers)* | `docs/plans/*-review.md` | `plan` | `reviewer`, `verdict`, `created`, `author`, `title`, `status`, `findings_count`, `diff_sha`, `mode`, `predecessor_review`, `prior_art_check`, `scope` |
| `prior-art-check` | `prior-art-check` | `docs/plans/*.prior-art-check.md` | `plan` | `author`, `created`, `status`, `conflicts`, `compatible`, `silent`, `title` |
| `plan-coverage-check` | `plan-coverage-check`, `coverage-check` | `docs/plans/*coverage-check.md` | `plan` | `author`, `created`, `status`, `verdict`, `title` |
| `docs-check-sidecar` | `docs-check-sidecar`, `docs-check` | `docs/plans/*docs-check.md` | `artifact` | `checker`, `claims_checked`, `verified`, `unverified`, `incorrect`, `auto_fixed`, `verification_source`, `created`, `status`, `title` |
| `integration-summary` | `integration-summary` | `docs/plans/*.integration-summary.md` | `plan` | `integrator`, `reviewer`, `created`, `status`, `title` |
| `problem-set` | `problem-set` | `docs/problems/*.md` | `title`, `status` | `date`, `ratified_by`, `ratified_date`, `kind` |
| `archived-memo` | `archived-memo` | `cross-repo/archive/*.md` | `from`, `to`, `status` | `title`, `created`, `kind`, `related_plan`, `related_review` |

---

## Role-based canonical vocabulary (review-sidecar)

New review sidecars emit a role-keyed `kind:` going forward. Person-named legacy values remain as resolvers (no data migration).

| Canonical `kind:` | Role | Persona (this repo) | Notes |
|---|---|---|---|
| `staff-eng-review` | Staff Engineer | the Staff Engineer | Preferred over legacy `the Staff Engineer-review` |
| `eng-director-review` | Engineering Director | the Director of Engineering | Preferred over legacy `review` / `plan-review` |
| `staff-ux-review` | Staff UX | the UX Reviewer | — |
| `staff-game-dev-review` | Staff Game Dev | the Game Dev Reviewer | — |
| `staff-data-sci-review` | Staff Data Scientist | the Data Science Reviewer | — |
| `senior-front-end-review` | Senior Front-End | the Front-End Reviewer | — |
| `code-review` | Sonnet code reviewer | `code-reviewer` agent | Already role-named; kept as-is |

Legacy `kind:` values (`plan-review`, `review`, `review-sidecar`, `the Staff Engineer-review`, `substrate-adjudication`, `plan-rereview`) remain in `review-sidecar.yaml`'s `kinds:` list and resolve correctly. No on-disk rewrite required (Decision 2).

**OSS distribution note:** person-named kinds do not survive depersonalization. Role-keyed vocabulary is the only form that travels across the publish boundary. → `CLAUDE.local.md § OSS distribution`.

---

## Required-field discipline

Required blocks are the back-compat intersection: only fields universally present across that family on disk. Content-rich fields are `optional` (still queryable via `query-records` when present). This avoids recreating fight-the-hook against the new schemas. Hard content-shape enforcement for new writes is a producer concern (C5 agent prompts), not a schema-required concern.

No `status` enum on any sidecar schema — legacy values like `reviewed` and `implemented` vary and are off the plan-schema enum. `status` is plain `string`.

---

## Schema files

```
plugins/coordinator/schemas/
  review-sidecar.yaml
  prior-art-check.yaml
  plan-coverage-check.yaml
  docs-check-sidecar.yaml
  integration-summary.yaml
  problem-set.yaml        (parity — authored separately, C1b)
  archived-memo.yaml      (parity — authored separately, C1b)
```

Loader: `bin/lib/schema.js` `loadSchemas()`. Registry source-of-truth: schema `applies_to` globs (C4 collapses the prior two-registry duplication).
