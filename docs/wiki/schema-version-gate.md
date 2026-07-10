# Schema-Version Gate

> Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W2 (ccos-1)
> Gate implementation: plugins/coordinator/bin/lib/schema.js § validateRecord

The coordinator uses a schema-version gate to detect cross-repo contract drift at
validation time.  The gate is **opt-in** (schemas and records without the relevant
fields pass through unchanged) and operates on **major-version differences only**
(semver semantics: breaking changes bump the major; minor/patch bumps are
backward-compatible and do not gate).

## Wire format

**Schema file** (`schemas/<name>.schema.json`) carries two keying fields:

```json
{
  "$id": "https://coordinator.local/schemas/handoff.schema.json",
  "x-schema-version": "1.0.0",
  ...
}
```

**Record** (frontmatter object or emitted JSON) carries:

```yaml
schema_version: "1.0.0"
```

The gate compares `record.schema_version` (semver string) against the schema
file's `x-schema-version` (semver string).  Both fields are optional — absent on
either side means the gate does not fire (no-op, fully backward-compatible).

## Semantics

### warn-on-newer-read (default, `mode: 'read'`)

A **consumer** reading a record whose `schema_version` major is **higher** than
the validator's vendored `x-schema-version` major receives a **non-fatal warning**:

- `result.ok` stays `true` — validation proceeds; the record is not rejected.
- `result.warnings` contains a `{ field: 'schema_version', error, hint }` entry.
- The consumer is notified that it is behind and should be widened before the next
  major producer bump.

This is the default behaviour (omitting `options` or passing `{ mode: 'read' }`).

### refuse-on-newer-write (`mode: 'write'`)

A **producer** validating a record for emission against a schema whose
`x-schema-version` major is **lower** than the record's `schema_version` major
receives a **hard failure**:

- `result.ok` is `false`; shape and cross-field validation is skipped.
- `result.errors` contains a `{ field: 'schema_version', error, hint }` entry.
- The producer must upgrade its vendored schema before writing records at the newer
  version.

### Calling the gate

```js
const { validateRecord } = require('./bin/lib/schema.js');

// Consumer (read path) — warn on newer, never block:
const result = validateRecord(record, schema);                   // mode defaults to 'read'
const result = validateRecord(record, schema, { mode: 'read' }); // explicit

if (result.warnings.length > 0) {
  // schema_version warning: log and continue (non-fatal)
}

// Producer (write path) — refuse if record is ahead of schema:
const result = validateRecord(record, schema, { mode: 'write' });
if (!result.ok) {
  // version gate fired — upgrade the vendored schema before writing
}
```

The `warnings` array is always present in the return value (empty when no gate
fires), so callers that do not yet check it are unaffected.

## Two-axis version scheme (record-class split)

The coordinator uses **two independent version axes** that govern disjoint record
classes and do not collide:

| Axis | Governs | Bump trigger | Source of truth |
|------|---------|--------------|-----------------|
| `CONTRACT_VERSION` (D3) | 14 cockpit-contract emission entities (`*-summary` projections consumed by cockpit) | zod change in `cockpit-contract/src/` | `cockpit-contract/DECISIONS.md` D3 |
| `x-schema-version` (this doc) | 26 on-disk coordinator records (`schemas/<name>.schema.json`) | hand-authored JSON Schema change | each `schemas/<name>.schema.json` |

`CONTRACT_VERSION` governs the cockpit emission entities; D2 (zod is the source for
cockpit entities) is scoped to that class and is intact.  `x-schema-version` governs
each on-disk record schema independently — bumped when the hand-authored JSON Schema
for that record type is updated.

Do not conflate the two axes.  A bump to `schemas/handoff.schema.json` bumps that
schema's own `x-schema-version` and does NOT change `CONTRACT_VERSION`.  The bump
triggers only apply to their own record class.

### Additive-bump holding/non-holding split (`CONTRACT_VERSION` axis only)

**Scoping note (read first):** the split below applies **only to the `CONTRACT_VERSION`
axis** — the cockpit-emission / cockpit consumer path (row in the table above).  It does
**not** float to `x-schema-version` / arbitrary on-disk record schemas: on that axis,
consumer structural tolerance for additive changes is unverified, so every bump there
still follows the reader-first / dual-gate discipline in full (§ below), with no
non-holding carve-out.

> A **top-level-array-additive** bump is non-holding IFF every registered consumer of that contract structurally ignores unknown top-level arrays — a capability each consumer must DECLARE, not one producers may assume. Absent a declared-tolerant consumer set, the bump reverts to bilateral-sequencing.
>
> Declared tolerance is **two-dimensional**: (1) STRUCTURAL — the consumer ignores/replayably-quarantines unknown top-level arrays rather than full-validating; AND (2) VERSION-ENVELOPE — the bump must land within the consumer's accepted `schema_version` range. The additive bump must therefore ship as a MINOR/patch widen (never rolled into a MAJOR increment — a major bump trips every consumer), and must stay at/above each consumer's minor-floor. A producer that couples an additive-array widen to a major bump, or emits below a consumer's floor, reverts to bilateral-sequencing for that consumer.
>
> A **nested-field-additive** bump — a new field on an existing entity object — breaks `.strict()` consumers (row quarantined). It is **holding / bilateral-sequencing-required** (widen consumers first) UNTIL consumers adopt entity-level unknown-field tolerance. NOT free-emit.
>
> Binding fleet envelope (as-of 2026-07-07): **major 2, minor ≥ 2.3.0** — binding because of rag's floor alone (cockpit imposes no floor).

This re-scopes the "producer holds merge-to-main and production emit" rule (§ Outage-gate
implication below): that hold now applies to **major bumps AND `nested-field-additive`**
bumps.  It does **not** apply to a `top-level-array-additive` bump against a declared-tolerant
consumer set — that bump is non-holding per the predicate above and may ship without
waiting on bilateral consumer re-vendor.

## Established cross-repo cutover patterns

**Do not re-derive** these; reference them.

### Reader-first ordering

Always widen the **consumer** before bumping the **producer**.

> Sources: `state/improvement-queue/2026-06-27-reader-first-ordering-for-contract-bump.yaml`,
> `state/improvement-queue/2026-06-23-contract-version-cutover-must-widen-the.yaml`.

The correct sequence for a major-version bump:

1. Author the new schema version (bump `x-schema-version` major in the schema file).
2. Update the **consumer** to accept both the old and the new version — widen the
   reader before any producer change ships to main.
3. Merge the consumer change.
4. Author the producer change (bump `schema_version` in the records / emit template).
5. Merge the producer change.

A write-first (producer-first) flip makes the consumer crash or quarantine records
on the first record it reads after the bump.  Reader-first is the safe order.

### Dual-gate requirement

A **producer-side drift gate is necessary but not sufficient** for a cross-repo
schema cutover.

> Source: `state/lessons.md` — search "producer-side drift gate is necessary-but-not-sufficient".

A producer gate (e.g. the refuse-on-newer-write path above) detects that the vendored
schema file is stale.  It does **not** detect a consumer-side ingest failure.  A
breaking field-add can still quarantine rows silently if the consumer's ingest code
does not have its own `schema_version` assertion.

Rule: every cross-repo schema cutover needs **both**:
- a producer drift gate (this validator, `mode: 'write'`), AND
- a consumer-side ingest-time `schema_version` fail-loud assertion (e.g. cockpit's
  `checkSchemaVersion`, major-only — see `example-cockpit-repo/docs/decisions/2026-07-07-cockpit-live-remote-per-repo-observation-model.md`).

A producer-only gate gives false confidence.  The dual-gate principle holds regardless
of which specific consumer-side assertion is in play: a producer gate alone never
substitutes for a consumer-side ingest-time check, and vice versa — this is orthogonal
to whether that consumer assertion hard-throws on any newer version or only on a major
mismatch (see § Outage-gate implication below for the current major-only behaviour).

### Outage-gate implication (cross-plan dependency for ccos-8)

A consumer's ingest-time `schema_version` assertion (e.g. cockpit's
`checkSchemaVersion` — see `example-cockpit-repo/docs/decisions/2026-07-07-cockpit-live-remote-per-repo-observation-model.md`)
gates on **MAJOR mismatch or malformed version only**: same-major bumps are accepted
at **any minor** (cockpit has no minor floor) — a higher minor warns and ignores
unknown arrays; a lower minor warns and proceeds.  Cockpit does **not** hard-throw on
every newer-than-vendored version; only a major mismatch or a malformed
`schema_version` throws.

This still makes a producer's **major bump, or a `nested-field-additive` bump,**
outage-gating (per the holding/non-holding split above — a `top-level-array-additive`
bump against a declared-tolerant consumer set is exempt from this hold):

- The producer commits the bump on its work branch.
- The producer **holds merge-to-main and production emit** until the consumer
  confirms re-vendor.
- The bump sequence follows reader-first ordering strictly (§ above).

**The first cross-repo consumer of `x-schema-version` triggers D13-style bilateral
widen-reader-first sequencing** (see `cockpit-contract/DECISIONS.md` D13).  This is a
cross-plan dependency for **ccos-8** (the cockpit ingest gate), which will be the
first consumer of `x-schema-version` on the on-disk record path.  ccos-8 authors
must coordinate the version-gate rollout with the coordinator side under reader-first
ordering and treat a MAJOR-bump or `nested-field-additive` producer change as
outage-gating from day one.

### A version bump requires a complete downstream-reader sweep — round-trip through the reader, not just the test

Reader-first ordering (§ above) governs the *sequence* of a cutover; this governs its *completeness*. A `SCHEMA_VERSION` / manifest-version / contract-version bump warrants an **exhaustive sweep of every downstream reader and every hardcoded version literal** — not only the tests the change happened to touch. Two recurring holes:

- **The literal test asserts the value; it never round-trips it through the actual reader.** A cutover that flips `agent_install_contract_version` 1→3 and widens the *contract test* to `{1, 2, 3}` can still leave a non-test reader — `manifest_reader.{sh,ps1}` pinned to `version != 1` / `-ne 1` — that rejects the repo's own v3 manifest with `exit 1`. It was invisible in-repo because the test only asserts the manifest *value*, never feeds that manifest back through the reader that consumes it. **Enumerate every reader (shell, PowerShell, Python, JSON-Schema `const`), not just the test constant**, and add at least one round-trip assertion that a freshly-emitted record parses through the real reader. (Source: 2026-06 project-rag; a sibling-repo memo caught the pinned reader the in-repo suite could not.)
- **Executor-green ran a subset — the full hardcoded-literal set is the oracle.** An executor that bumps `graph.db SCHEMA_VERSION` 13→14 and reports "82 tests pass" typically updated only the assertions *it* touched: one of four hardcoded `== 13` checks, missing `test_producer_runner.py`, a v13-migration test, an eval golden, and docstrings. An executor runs the tests it edited, not every hardcoded-literal reader in the tree. Grep the **old version literal** (`== 13`, `!= 1`, `_v13`, `version: 13`) across the whole repo and drive every hit to a decision before declaring green; where a `schema-migration-auditor` worker exists, dispatch it to enumerate the complete downstream-reader set mechanically.

The unifying rule: a version constant is a symbol read in many places; "green" means the full reader/literal set was swept and a real record round-tripped through each reader — not that the touched tests passed.

## Backward-compatibility invariant

Records and schemas **without** `schema_version` / `x-schema-version` behave exactly
as before this gate was introduced.  The gate is entirely opt-in:

```yaml
# No schema_version in record → gate is silent (no-op)
title: My handoff
created: 2026-06-27
```

Do NOT back-fill `x-schema-version` archaeology into historical schema files.  New
and migrated schemas declare a version going forward; no fabricated version history.

## Re-pinning a vendored schema that adds `$defs` can expand conformance scope — it is not a constant-swap

Bumping the pinned version of a *vendored* schema (`v1.0.0 → v1.1.0`) looks like a one-line constant swap, but a minor bump that adds first-class `$defs` can silently **widen what gets validated**. When new `$defs` carry `x-coordinator-applies_to` (or equivalent) globs — especially the first non-`.md` artifact globs (`*.json`, `*.yaml`) — any validator that derives its `--validate-all` scope from those globs pulls previously-unscoped directories into conformance on the next run. A re-pin that adds queue/outbox `$defs` can drag `state/review-trail/`, `state/bug-backlog/`, and similar into validation scope that never conformed before, turning a "pin bump" into a broad, surprise validation expansion (and a red run).

**Rule:** before re-pinning a vendored schema, diff the new version's `$defs` and any `applies_to`/glob metadata against the old — not just the version string. If new globs appear, enumerate the directories they newly pull into scope and decide deliberately (conform them, or exclude them) *in the same change*. Treat a schema re-pin that adds `$defs`/globs as a scope change, not a constant swap. (Source: 2026-06-26 project-rag, artifact-shape-contract v1.0.0→v1.1.0 re-pin.)

## Kept-YAML exceptions (ccos-1 migration)

Six schemas were intentionally **not** migrated to `.schema.json` during the ccos-1 wave and remain
as `.yaml` files indefinitely.  The dual-format loader supports `.yaml` schemas indefinitely, so
these are permanently valid — not technical debt.

| Schema file | Reason kept as YAML |
|---|---|
| `schemas/lesson-entry.yaml` | Uses `match_mode: inline-tag-per-entry` — validated by `validateLessonsFile`, not the frontmatter path.  JSON Schema frontmatter validation is irrelevant for inline-tagged lesson entries; migrating would add noise without benefit. |
| `schemas/review-trail.yaml` | Validates `.json` records, not markdown frontmatter.  The lint tool skips `.json` files, so this schema is exercised by a different code path (`validateRecord` on emitted JSON blobs).  Migrating to `.schema.json` would collide with the loader's file-extension heuristic for the JSON Schema path. |
| `schemas/bug-backlog.yaml` | **Node-validated.** Validated at write time by `bin/coordinator-queue-append` via `bin/schema-cli.js` (schema.js), which reads the YAML-dialect shape directly (not JSON Schema). The Python `schema_loader.py` that formerly handled this was retired in option (d), 2026-06-27. |
| `schemas/debt-backlog.yaml` | Node-validated (see bug-backlog). |
| `schemas/improvement-queue.yaml` | Node-validated (see bug-backlog). |
| `schemas/lessons-outbox.yaml` | Node-validated (see bug-backlog). |

> **Residual / follow-on:** the 4 queue schemas stay `.yaml` because `schema.js` / `schema-cli.js`
> support YAML-dialect shapes indefinitely (dual-format loader). The Python `schema_loader.py` was
> **retired** in the dual-yaml-parser option (d) workstream (2026-06-27); there is no Python parser
> left to port. The remaining follow-on is migrating these 6 `.yaml` schemas to `.schema.json` (full
> JSON Schema unification) — a discrete future workstream, not a ccos-1 residual.
> These were briefly migrated and reverted in-session when the break surfaced (queue-append failed
> the schema lookup); they are now stable `.yaml`.

All other schemas in `schemas/` that match markdown frontmatter paths were migrated to
`.schema.json` in the ccos-1 W4 wave (W4a–W4d).
