# Schema and Validation Contracts

<!-- distilled: run 2026-07-19-synth; sources: archive/specs/2026-05/2026-05-01-portable-ideas-from-obsidian-research.md, 2026-05-21-cross-repo-memo-discoverability.md, archive/specs/2026-06/2026-06-24-handoff-lifecycle-transition-helper.md, archive/specs/2026-06/2026-06-27-ccos-2-plan-session-linkage.review-the Staff Engineer.md, archive/specs/2026-06/2026-06-27-ccos-3-provenance-triple-work-item-record.md, archive/specs/2026-06/2026-06-28-roadmap-stub-numbering-dependency-order.review-staff-eng.md, archive/specs/2026-06/2026-06-27-ccos-2-plan-session-linkage.md, archive/specs/2026-06/2026-06-29-handoff-lineage-dag-fan-in-fan-out.the Director of Engineering-review.md, 2026-07-17-claude-klabauter-em-schema-ssot-flip-accepted-sequencing.md -->

> Purpose: how DoE-claude's tracked-record schemas (YAML frontmatter) are declared, validated, and evolved — and who is authoritative for which validator.

## Overview

Tracked records — handoffs, memos, queue work-items, roadmap stubs, and similar
`tasks/`-adjacent artifacts — carry YAML frontmatter that is validated against
plain-YAML schema declarations in `schemas/<type>.yaml`. Validation is enforced at
multiple points (PreToolUse hook, `/validate`, `/workday-complete`, CI, write-time
Python validator) but there is exactly **one production validator** for queue
records; other checkers are either non-production or historically no-op stubs.
This guide covers the schema format, the validator landscape, evolution rules for
adding fields, and open/decided points around nested and kind-gated fields.

## Key Decisions

<!-- src: plan02-027, plan02-028 -->
### Frontmatter-as-schema, plain YAML

Tracked records (`tasks/handoffs/`, `tasks/reviews/`, etc.) carry YAML frontmatter
schemas. A PreToolUse hook blocks malformed writes; `/validate`, `/workday-complete`,
and CI hard-fail on violations. Authored notes (free-form prose docs) are exempt —
the schema regime applies to structured tracked records only, not to every markdown
file in the repo.

Schema files live at `schemas/<type>.yaml` and declare required/optional/enum
fields plus type constraints (`string`, `iso-date`, `path`, `list`). There is no
JSON Schema layer — schemas are plain YAML read by a bespoke loader/validator, not
an off-the-shelf schema engine. Example (`handoff.yaml`): `title` (string),
`created` (iso-date), `status` (enum: `active`/`consumed`/`superseded`),
`predecessor` (string-or-null).

<!-- src: plan10-011 -->
### Memo status machine

Memo frontmatter enforces a status state machine: `open → reviewed →
action_taken → closed`, with `superseded` as a terminal state reachable from any
non-closed status. `status: action_taken` requires a `decision` field — the schema
encodes a cross-field dependency, not just per-field type/enum checks.

<!-- src: plan26-005, plan26-011 -->
### Additive-only schema evolution — optional block, encoded-string-list default

New schema fields land in the `optional` block, never `required` — adding a
required field would break every existing artifact that predates it (see
`canonical-artifact-shapes.md` § D1 Negative-Spec). This is the standing rule for
any schema extension, not just the `agent_sessions` case that established it.

When a new field needs list-of-record semantics but the parser's list-of-map
support is contested or fork-blocked, the resolved pattern is an
**encoded-string-list** (e.g. `id|status|created_at` pipe-joined strings) rather
than list-of-map. `agent_sessions` chose this shape because it validates against
the existing `schema.js` immediately, is fork-independent from concurrent
mid-flight rewrites, and has the simplest concurrency story (append-only string,
no nested-object merge conflicts). Treat this as the default answer to "how do I
add a repeated-record field to frontmatter" unless list-of-map support has since
landed cleanly.

<!-- src: plan26-015 -->
### Identity/fields/system layering is additive

The identity/fields/system split on work-item records is realized additively:
pre-existing top-level frontmatter keys are treated as the identity+fields layers,
and a new `system` block is added on top. This is lossless and reader-safe — it
requires no reshaping of legacy records (309 records at time of decision). When
adding a new structural layer to an existing schema, prefer bolting it on as a new
top-level block over reshaping what's already there.

<!-- src: plan29-005 -->
### Missing-required-field detection must fail loud, never silently coerce

`sprint` is NOT a required field on `kind: spinoff-roadmap`. When a field that
*could* be missing feeds into an ordering/comparison operation (e.g. numeric
sprint ordering), a missing value must be its own detected violation class — fail
loud — rather than being silently absorbed into a string-vs-number lexicographic
comparison that produces wrong-but-plausible output. The pattern: use a sentinel
(e.g. `NO_SPRINT`) for *detection only*, never feed the sentinel into ordering
logic. This generalizes beyond roadmap stubs: any optional field consumed by a
comparison/sort must have an explicit missing-value guard, not an implicit
fallback.

<!-- src: plan29-012 -->
### Kind-gating new relationship fields

When adding a new frontmatter relationship field (e.g. `forked_from`,
`additional_predecessors`), two separate decisions are required: (a) add the
field(s) as schema properties, and (b) explicitly decide whether the field is
kind-gated (permitted only on certain `kind:` values) or universal. Don't let
kind-gating happen by omission — mirror the existing `supersedes` /
graph-primitive kind-gate pattern when the field is conceptually spinoff-only or
similarly scoped.

<!-- src: memo08-009 -->
### Schema SSOT ownership split (DR-047 sub-decision)

Per DR-047's contract-vs-engine boundary, ownership of schema *tooling* (not the
schema *contract*) has been split by ratified sequencing: claude-klabauter takes over (A)
becoming the `.schema.json` emitter — retiring the DoE-vendored, drift-checked
copy — and (B) retiring `schema-cli.js` in favor of native enum-introspection.
DoE retains the contract/governance layer (the schema files themselves and the
rules in this guide). The cutover is sequenced behind DoE's 8-schema
landing-commit and spans all four shell-out call sites: `queue_append
--describe/--validate`, `queue_promote`, `plan_tasks_mutate`, `schema_validate.py`.
**DoE's deletion signal is an explicit cutover-clear memo from claude-klabauter** — do not
delete the vendored emitter or `schema-cli.js` preemptively.

## Validator Landscape

<!-- src: plan26-025 -->
### Only one production validator for queue records

`lint-frontmatter.py` explicitly skips `*.yaml`/`*.json` files. `schema.js` is
**out of the production path** for queue records entirely. The sole production
validator for queue records is `schema_loader.validate()` (Python), invoked at
write-time via `coordinator-queue-append`. When reasoning about "will this write
be validated," trace through `coordinator-queue-append` → `schema_loader.py`, not
through `schema.js` or `lint-frontmatter.py`.

<!-- src: plan26-024 -->
### schema_loader.validate() is shallow, not recursive

`schema_loader.validate()` checks top-level `required` + `enum` constraints only —
it does **not** descend into nested blocks (e.g. a nested `system` block).
Nested-field validation is currently producer-side, living in
`coordinator-queue-append` rather than in the shared validator. This is a named
architectural deferral, not an oversight — don't assume adding a nested block to a
schema gets you nested validation for free; the producer must validate it
explicitly.

<!-- src: plan26-023 -->
### schema.js list-of-map gap

`schema.js`'s YAML parser already handles block list-of-maps structurally
(parsing logic present). The only missing piece to fully support list-of-map
frontmatter fields is `validateField` type support — roughly 15 lines. As of the
source review, a concurrent mid-flight rewrite blocked landing this, which is why
the encoded-string-list pattern (above) was chosen as the interim default instead
of waiting on list-of-map support.

<!-- src: plan23-028 -->
### Permissive-stub validators are an intentional interim state

Not every "validation" call site is wired to a real schema. The handoff-lifecycle
transition helper's Node CLI validates frontmatter against a (future) handoff
schema before writing, but at the time it shipped, that validation was left as a
no-op/permissive stub carrying a `TODO(ask2)` marker, pending a separate
schema-building effort. **Do not assume every call site that says "validates
frontmatter" is enforcing anything** — check whether the referenced schema exists
and whether the validator is wired live or stubbed permissive.

## Gotchas

- **`schema.js` ≠ production validator for queue records.** Editing or testing
  against `schema.js` does not exercise what actually gates writes; use
  `schema_loader.validate()` / `coordinator-queue-append` for anything queue-record
  related.
- **Nested blocks are not auto-validated.** Adding a `system:`-style nested block
  to a schema does not get required/enum checking unless the producer
  (`coordinator-queue-append` or equivalent) validates it explicitly.
- **A "validates frontmatter" claim in an older plan may describe a stub.** Check
  for `TODO(ask2)`-style markers or confirm the referenced schema file actually
  exists before trusting a validation claim.
- **New fields are additive by default.** Landing a field as `required` on an
  existing schema is a breaking change to every prior artifact unless you've
  audited and migrated them — default to `optional`.
- **Missing-optional-field bugs hide in comparisons, not lookups.** A `None`/absent
  optional field usually passes structural validation fine; the danger is
  downstream code that sorts, compares, or arithmetically combines it without a
  missing-value guard.

## Reference

| Concern | Owner / Location |
|---|---|
| Schema contract (schema file authorship, field semantics) | DoE (this repo) |
| `.schema.json` emitter | claude-klabauter (post DR-047 sub-decision, memo08-009) |
| `schema-cli.js` | Retiring → claude-klabauter native enum-introspection (memo08-009) |
| Production validator for queue records | `schema_loader.validate()` (Python), via `coordinator-queue-append` |
| `schema.js` | Non-production for queue records; list-of-map `validateField` support still missing |
| `lint-frontmatter.py` | Skips `*.yaml`/`*.json` — not a schema validator |
| Handoff schema (Node CLI transition helper) | Historically permissive stub, `TODO(ask2)` — verify current wiring before relying on it |
