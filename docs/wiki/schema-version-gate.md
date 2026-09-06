# Schema-Version Gate

> Spec backlink: docs/plans/2026-06-27-ccos-1-dual-context-validator.md § W2 (ccos-1)
> Gate implementation: claude-klabauter `coordinator_core/frontmatter/schema_validate.py` — `validate_frontmatter()` (write/refuse-on-newer path) and `validate()` (read/warn-on-newer path); `schema.js` was deleted in claude-klabauter `480ad8f8`

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

```python
from coordinator_core.frontmatter.schema_validate import validate, validate_frontmatter

# Consumer (read path) — warn on newer, never block:
result = validate(schema_name, fields)  # dict-returning; never raises SchemaVersionError

if result['ok'] is False:
    ...  # shape/cross-field errors only — a schema_version mismatch alone never fails this call

# Producer (write path) — refuse if record is ahead of schema:
try:
    errors = validate_frontmatter(fm_dict, schema_path)
except SchemaVersionError:
    ...  # version gate fired — upgrade the vendored schema before writing
```

`validate()` never raises on a `schema_version` mismatch alone (it is dict-returning,
`{"ok": bool, "errors"?: [...]}`); `validate_frontmatter()` raises `SchemaVersionError`
on a major-version mismatch. Callers that only need the read-path behaviour call
`validate()`; callers on the write path call `validate_frontmatter()` and catch
`SchemaVersionError`.

### The read/write asymmetry generalizes — a version-skew fail-closed abort must carve out read-only queries

The read-mode-warns / write-mode-refuses split above is a specific instance of a universal
rule for **any** version-skew or liveness fail-closed gate, not just this schema gate. An
"abort on stale/skewed service" gate (an R8-style liveness abort) is correct for **mutating**
ops but over-broad for **read-only queries**: a stale service answers a read-only lineage or
query op correctly against the same on-disk data, so a blanket abort forces manual workarounds
every skew window for no correctness gain.

**Rule:** add a per-invocation opt-in **read-only degrade** (warn + proceed) rather than
blanket-removing the gate — and keep the **single liveness source** (proceed to the real RPC,
never a local re-implementation of the liveness check). Mirror this doc's default: read path
degrades, write path fails closed. [universal]

### Scoping a read-side tolerance to a FUNCTION strands every other reader that calls a different one

The read/write asymmetry above is the right principle. The recurring way it is implemented wrong:
the tolerance gets attached to *one function* rather than to the *role*, and every other reader
reaching the same check through a different entry point silently keeps the strict behaviour.

**Concrete precedent (greppable).** After the C10 baton-`kind` narrow stranded sibling records,
Claude-klabauter `d2b28ac9` added D1 pre-rename alias tolerance so legacy batons stay claimable. It
applied `_tolerate_handoff_kind_aliases` as a post-process inside `validate_frontmatter()` and
deliberately excluded `_dispatch_validate()`, on the correct stated principle that *"alias tolerance
is a reader contract, not a writer one."* It also shipped a parity test driving both arms over the
full cross-product of canonical values, aliases, and garbage.

It was still incomplete, and the parity test could not see why. `lint-frontmatter` — the `d2`
directive in `baton-assemble`, and a pure reader — reaches the enum check by a **third** path:
`schema_validate.main` → `_run_single_file_check` → `validate_frontmatter_obj()` →
`_dispatch_validate()`. It inherited the writer-side strictness it was never meant to have, so the
claim gate was fixed while the lint gate was not: legacy batons claimed, and a
`baton-assemble apply` transaction naming one as predecessor still rolled back at `d2` and
compensated. Reported by example-cockpit-repo-em, a day after the claim-path fix landed.

**Rules:**
- **Classify the CALL SITE by role, then enumerate every call site of that role** — do not scope a
  tolerance to whichever function the reported failure happened to traverse. The bug report names
  one path; the role names all of them.
- **A linter is a reader.** It validates a record already on disk, authored days or weeks earlier;
  it cannot distinguish "just written" from "pre-existing," and treating it as a writer re-imposes a
  migration deadline on a corpus the writer contract was never about.
- **A two-arm parity test proves the two arms agree, not that there are only two arms.** When a
  tolerance is deliberately asymmetric, the test that actually protects it enumerates *entry
  points* — `grep` for every caller of the strict function — rather than driving the two known ones.
- **Diagnostic tell for this shape:** a reject whose hint lacks the enrichment the tolerance commit
  added. If the fix improved the error message on the path it touched, an un-enriched message is
  positive evidence you are on an untouched path — cheaper than tracing the call graph.

## Two-axis version scheme (record-class split)

The coordinator uses **two independent version axes** that govern disjoint record
classes and do not collide:

| Axis | Governs | Bump trigger | Source of truth |
|------|---------|--------------|-----------------|
| `CONTRACT_VERSION` (D3) | 14 cockpit-contract emission entities (`*-summary` projections consumed by cockpit) | zod change in `cockpit-contract/src/` | `cockpit-contract/DECISIONS.md` D3 |
| `x-schema-version` (this doc) | 26 on-disk coordinator records (`schemas/<name>.schema.json`) | hand-authored JSON Schema change | each `schemas/<name>.schema.json` |

`CONTRACT_VERSION` governs the cockpit emission entities; D2 (zod is the source for
Cockpit entities) is scoped to that class and is intact.  `x-schema-version` governs
each on-disk record schema independently — bumped when the hand-authored JSON Schema
for that record type is updated.

Do not conflate the two axes.  A bump to `schemas/handoff.schema.json` bumps that
schema's own `x-schema-version` and does NOT change `CONTRACT_VERSION`.  The bump
triggers only apply to their own record class.

### Additive-bump holding/non-holding split

<!-- spec-backlink: docs/decisions/DR-097-sibling-notification-duty-on-terminal-events.md -->

**Scoping note (read first):** the `nested-field-additive` **holding** rule below applies
**only to the `CONTRACT_VERSION` axis** — the cockpit-emission / cockpit consumer path (row
in the table above). On `x-schema-version` / arbitrary on-disk record schemas, consumer
structural tolerance for a `nested-field-additive` change is unverified, so every such bump
there still follows the reader-first / dual-gate discipline in full (§ below), with no
non-holding carve-out. The `top-level-array-additive` **non-holding** carve-out, by contrast,
is **axis-agnostic**: it applies to `CONTRACT_VERSION` and to `x-schema-version` alike,
whenever the two-dimensional declared-tolerance predicate below is satisfied for the
specific consumer set of that specific contract or on-disk schema. A `CONTRACT_VERSION`
consumer's declared tolerance never carries over to an `x-schema-version` consumer, or vice
versa — the census is per governed record class, not per producer.

> A **top-level-array-additive** bump — on either axis — is non-holding IFF every registered consumer of that contract or on-disk schema structurally ignores unknown top-level arrays — a capability each consumer must DECLARE, not one producers may assume. Absent a declared-tolerant consumer set, the bump reverts to bilateral-sequencing.
>
> Declared tolerance is **two-dimensional**, on both axes: (1) STRUCTURAL — the consumer ignores/replayably-quarantines unknown top-level arrays rather than full-validating; AND (2) VERSION-ENVELOPE — the bump must land within the consumer's accepted `schema_version` (or `x-schema-version`) range. The additive bump must therefore ship as a MINOR/patch widen (never rolled into a MAJOR increment — a major bump trips every consumer), and must stay at/above each consumer's minor-floor. A producer that couples an additive-array widen to a major bump, or emits below a consumer's floor, reverts to bilateral-sequencing for that consumer, on whichever axis governs that record class.
>
> A **nested-field-additive** bump — a new field on an existing entity object — breaks `.strict()` consumers (row quarantined). On the `CONTRACT_VERSION` axis it is **holding / bilateral-sequencing-required** (widen consumers first) UNTIL consumers adopt entity-level unknown-field tolerance. NOT free-emit. On the `x-schema-version` axis it is unconditionally holding per the scoping note above — no declared-tolerance path exists for it there.
>
> Binding fleet envelope as of 2026-07-07 (`CONTRACT_VERSION` axis): **major 2, minor ≥ 2.3.0** — binding because of rag's floor alone (cockpit imposes no floor). No equivalent fleet-wide envelope has been ratified on the `x-schema-version` axis; each on-disk schema's consumer census stands alone until one is.

This re-scopes the "producer holds merge-to-main and production emit" rule (§ Outage-gate
implication below), on both axes: that hold applies to **major bumps AND
`nested-field-additive`** bumps (unconditionally on `x-schema-version`; until consumer
unknown-field tolerance lands on `CONTRACT_VERSION`). It does **not** apply to a
`top-level-array-additive` bump against a declared-tolerant consumer set on either axis —
that bump is non-holding per the predicate above and may ship without waiting on bilateral
consumer re-vendor.

### Bump-class extension key — making the CLASS machine-readable

<!-- spec-backlink: docs/decisions/DR-097-sibling-notification-duty-on-terminal-events.md -->
<!-- spec-backlink: cross-repo/inbox/2026-07-26-claude-klabauter-em-dr083-bump-memo-extension-and-ahead-standdown-protocol.md (ask #2 part B) -->

**This key implements DR-097, it does not propose it.** `docs/decisions/DR-097-sibling-notification-duty-on-terminal-events.md`
§ Trigger (A) already ratifies both the requirement and the vocabulary: "The (A) notification
must state the bump's CLASS — `top-level-array-additive`, `nested-field-additive`,
`enum-value-additive`, or `major` — not merely that a bump occurred... a bare 'we bumped' notice
is insufficient and does not discharge the duty."

**Those four are the whole vocabulary — `narrowing` is not a class**, though this page uses the
word descriptively and it greps like one. A change that narrows the accepted set is `major`: the
additive terms all require that every document valid under the prior version still validates, and
a narrowing fails that by construction. No term fits → nearest fit on the SAFE side, with the
`x-bump-note` saying why none applied (`peer-set-entry.schema.json` is the worked case). Overstating
makes a sibling wait; understating lets them skip a hold they owed. Until this key existed, that CLASS lived only
in prose — a
`declaration.bump_class` free-text field on a `cross-repo-commitment.yaml` record, or a sentence
in a commit message. No machine read either. `claude-klabauter`'s
`coordinator_core/frontmatter/schema_drift_watch.py` can already see that a vendored schema's
bytes moved relative to its pin (it reports a DIRECTION — `we-are-ahead` / `we-are-behind` /
`both`) but had no way to see whether the move was COMPATIBLE or BREAKING.

**`x-bump-class`** closes that gap. It is an **additive, `x-`-prefixed sibling key to
`x-schema-version`**, living **inside the schema file itself** — not in
`schema-version-pins.json`. This placement is load-bearing, not a style choice:
`schema_drift_watch.py` discovers schemas by **globbing the schema files themselves**
(`directory.glob("*.schema.json")`) and parsing `x-schema-version` out of each one; it does not
read the pin file. A key placed in the pin file would be invisible to that consumer.

```json
{
  "x-schema-version": "2.1.0",
  "x-bump-class": "top-level-array-additive",
  "x-bump-note": "2.0.0 -> 2.1.0 added the optional top-level `carried_items` array (carry-forward counter + third-carry gate)."
}
```

**Closed vocabulary** (reused verbatim from § Additive-bump holding/non-holding split above —
do not invent new terms):

| Value | Meaning |
|---|---|
| `top-level-array-additive` | A new array field added at the document's top level (e.g. `handoff.schema.json`'s `carried_items`, `handoff-archived.schema.json`'s `disposed_successors`). |
| `nested-field-additive` | A new field added on an existing entity object — top-level scalar/object or nested inside an array item (e.g. `cross-repo-memo.schema.json`'s `to_repo`, `strategic-self-description.schema.json`'s `depends_on[].strength`). |
| `enum-value-additive` | One or more values added to an existing closed enum on an existing field — no field added, no field removed, no existing value's semantics changed (e.g. `sizing-object.schema.json`'s `detents[]` enum gaining `premise_unproven` and `premise_not_applicable`). **Note:** that widen did not land as a standalone, cleanly-classed bump — it was folded into a bundled 1.3.0→1.5.0 commit alongside the required-`premise` add, and the bundled bump's own recorded `x-bump-class` is `major`, because the most restrictive of the bundled changes' classes governs the whole commit. The standalone reference instance is `percolate-store.schema.json` 1.2.0→1.3.0 (`cd6d1b8325c0`): two values added across two enums, nothing else in the commit, recorded `x-bump-class` `enum-value-additive`. |
| `major` | A breaking change — a required field added, a field removed, or existing semantics changed (e.g. `review-findings.schema.json` 1.0.0→2.0.0 made `status` required, breaking the old bare-prose no-frontmatter shape). |

**A class alone never determines holding behaviour — the axis does too, and this key sits on
only one of the two.** `x-bump-class` is scoped to the `x-schema-version` axis (§ Two-axis
version scheme above) — the on-disk record-schema axis this whole document governs — not the
separate `CONTRACT_VERSION` axis (cockpit-emission entities). Per DR-097 § Reconciliation, the
two axes do **not** apply the same holding rule to the same class name:

- **`nested-field-additive` on `x-schema-version` (this key's home axis) is holding
  unconditionally** — no declared-tolerance carve-out exists here, unlike on `CONTRACT_VERSION`
  where that carve-out is scoped (§ Additive-bump holding/non-holding split, scoping note).
  Every `nested-field-additive` value this key ever carries follows reader-first / dual-gate
  discipline in full.
- **`top-level-array-additive` is axis-agnostic** — non-holding on `x-schema-version` too, per
  DR-097, but only against a consumer set that has declared
  BOTH structural and version-envelope tolerance (the two-dimensional predicate in § Additive-bump
  holding/non-holding split); absent that declaration it reverts to bilateral-sequencing on this
  axis exactly as on the other.
- **`enum-value-additive` on `x-schema-version` is holding unconditionally — no
  declared-tolerance carve-out exists or may be earned for it, ever.** This is the same holding
  verdict as `nested-field-additive` but for a sharper reason: a consumer validating a record
  against a narrower vendored copy of the enum REJECTS that record outright. This is strictly
  worse than the unknown-*field* case — entity-level unknown-field tolerance is a coherent
  capability a consumer can implement and declare, but "accept an unenumerated enum value"
  defeats the entire purpose of a closed enum, so there is no tolerance a consumer could declare
  that would make an enum widen non-holding. `enum-value-additive` is explicitly fenced out of
  the `top-level-array-additive` non-holding carve-out above — that carve-out is the only
  non-holding path in this taxonomy and does not reach this class.

  The sharpest instance of this is a **symmetric-parity subcase**, live in this repo today: when
  an enum is mirrored in a sibling repo's artifact under a parity test — this schema's `detents`
  enum and `claude-klabauter`'s `coordinator_core.sizing_assemble.DETENT_ENUM`, guarded by
  `coordinator/tests/test_sizing_route_enum_schema_parity.py::test_detent_enum_parity` —
  bilateral sequencing is not merely advisable, it is mechanically enforced: either side widening
  alone turns this repo's own suite red.
- **`major` is holding on every axis, unconditionally** — no carve-out exists or is proposed for
  it anywhere in this document.

Do not read a bare `x-bump-class` value as sufficient on its own to decide whether a bump may
ship un-held — check the axis (always `x-schema-version` for a value living on this key) against
the table above, then check whether a declared-tolerance record exists for the specific
consumer+artifact+class triple before concluding non-holding applies.

**What it records — and what it deliberately does not.** `x-bump-class` describes the CLASS of
the schema's **most recent** version bump only, not a full changelog. It is optional and
**only present where a real, verified bump earned it** — a schema still at its seeded `1.0.0`
with no bump history carries no key rather than a fabricated class. Where a schema's most recent
version change was a pure routing/metadata edit (an `applies_to` glob relocation or a
description rewrite with **no property added, removed, or changed**), the key is likewise
omitted: none of the vocabulary terms describe a change with zero effect on record
validation, and forcing one would misrepresent the bump to a consumer deciding whether to hold.

**`x-bump-note`** is an optional companion key: a one-line human-readable note on WHAT changed,
kept separate from `x-bump-class` rather than overloading the class value with prose (a
consumer's guard should be able to switch on `x-bump-class` alone without parsing a sentence).
`x-bump-note` normally accompanies `x-bump-class`, but a **zero-shape-effect bump omits
`x-bump-class`** (per the paragraph above) while still owing a consumer an explanation of what
changed — that bump records its rationale in `x-bump-note` alone.

**A note standing without a class must contain the phrase `ZERO SHAPE EFFECT`.** The exception is
granted on an assertion, never on silence: forgetting the class on a bump that did change shape
still fails, because passing requires positively claiming no shape delta, and a false claim is a
reviewable lie rather than an omission nothing can see. Enforced by
`coordinator/tests/test_schema_version_pin.py::test_bump_note_without_class_declares_zero_shape_effect`.

**Vocabulary closure is enforced** by
`test_bump_class_vocabulary_is_closed` in the same file — any schema declaring `x-bump-class`
outside the four-value set above fails the fast tier.

**`x-bump-class` complements `cross-repo-commitment.schema.json`'s `declaration.bump_class` —
it does not duplicate it.** They answer different questions for different consumers and neither
makes the other redundant:

- `declaration.bump_class` (added by C11, itself a `nested-field-additive` bump on the
  commitment schema) is a per-**event** field on one `cross-repo-commitment.yaml` record — it
  answers "was consumer X notified about artifact Y's bump, and what tolerance did that
  notification declare?" It is free-text (`"type": "string"`, no enum), not machine-discoverable
  in bulk (a reader must scan the whole commitment corpus to find the most recent declaration
  for a given schema), and populated only when a notification actually fired.
- `x-bump-class` is a per-**schema** field co-located with `x-schema-version` inside the schema
  file itself — it answers "what class was this schema's own most recent shape change?",
  independent of whether or to whom a notification was sent, and is what
  `schema_drift_watch.py`'s glob-based discovery can actually see (§ above).

**One real gap the overlap surfaces:** `declaration.bump_class` has no enum and is not vocabulary-
enforced, unlike `x-bump-class` (`test_bump_class_vocabulary_is_closed`). A `declaration` record
SHOULD cite the same schema's `x-bump-class` value when one exists, but nothing currently
enforces that the two stay in sync — a future declaration citing a class the schema itself
doesn't carry (or a stale/different one) would go undetected. Tightening
`declaration.bump_class` to the same closed enum, or asserting cross-consistency where both
exist, is a candidate follow-up and is explicitly **not** implemented by this change.

### Pin-gate two-hash split — `shape_hash` gates, `content_hash` is advisory

<!-- spec-backlink: docs/plans/2026-07-31-pin-gate-shape-hash.md -->

`coordinator/schemas/schema-version-pins.json` pins each of the 58 versioned schemas with
**two** hash fields plus `x-schema-version`:

```json
{
  "archived-memo.schema.json": {
    "content_hash": "sha256:...",
    "shape_hash": "sha256:...",
    "x-schema-version": "1.4.0"
  }
}
```

**`shape_hash` is what `test_schema_version_pin.py::test_schema_shape_hash_matches_pin` gates
on.** It strips both pure-prose *annotations* — `description` and `$comment` (but not a property
literally named either one —
see § The trap the obvious implementation walks into, `docs/plans/2026-07-31-pin-gate-shape-hash.md`)
before hashing, so a prose-only edit to an annotation cannot move it. **`$comment` is included in
the strip set** because this corpus parks multi-paragraph cross-field-rule rationale in
`$comment` beside a two-line `if`/`then`; the JSON-Schema spec gives `$comment` no validation
effect, and on a schema `claude-klabauter` vendors byte-identically a spurious bump would charge
that sibling a re-vendor round trip for a typo fix. Everything this section says about a
description-only edit reads identically for a `$comment`-only one. **`content_hash` is
refreshed by the same regenerator on every run but is not itself gated** — the pin test asserts
`x-schema-version` and `shape_hash` only; `content_hash` is advisory, always-true, and carries no
pass/fail weight.

**A description-only edit moves `content_hash` alone, and that is not a bump.** It owes no
`x-bump-class` and no sibling notification under DR-097. This is not a new ruling — § Bump-class
extension key above already settled it for `x-bump-class`, for exactly the same reason:

> Where a schema's most recent version change was a pure routing/metadata edit (an `applies_to`
> glob relocation or a description rewrite with **no property added, removed, or changed**), the key
> is likewise omitted: none of the vocabulary terms describe a change with zero effect on
> record validation, and forcing one would misrepresent the bump to a consumer deciding whether
> to hold.

This plan extends that same settled conclusion to the pin gate's hash mechanics: a
description-only edit is not a bump there either, so it gets no `shape_hash` movement, no
`x-bump-class`, and no DR-097 notice.

**This is not "nothing happens" for a genuine description rewrite, though.** Because the
regenerator (`python3 coordinator/tests/test_schema_version_pin.py --regen`) refreshes
`content_hash` from the live schema on every run — including a clean-shape run — a `content_hash`
line moving in the pin file with **no** `shape_hash` movement is a precise, zero-cost,
human-readable "prose changed here, no shape delta" signal, visible in the pin-file diff at PR
review time. No new gate and no new warning channel were added to produce it; it falls out of
the regenerator refreshing both fields on every invocation (§ Anti-scope,
`docs/plans/2026-07-31-pin-gate-shape-hash.md`).

**Worked example:** `a7524193c` — a description-only re-vendor from `claude-klabauter` — tripped
two pins under the pre-split gate (which hashed `description` prose alongside shape) and had to
be cleared by editing `content_hash` by hand, with no mechanical evidence that the shape had
actually held still. That incident is what motivated this split: after it, the same re-vendor
would move only `content_hash` and leave the gate green.

**Regenerating the pins:** `python3 coordinator/tests/test_schema_version_pin.py --regen`.
Idempotent on a clean tree (a second run is a no-op, exit 0). It refuses to rewrite an existing
`shape_hash` under an unmoved `x-schema-version` unless the live shape actually still disagrees
with the pin — a real attempted shape overwrite, not idempotent re-seeding — in which case it
exits non-zero and requires `--force --reason '<why>'` to push through.

Not a bump-class extension: this split does **not** add a fourth member
(`doc-only`/similar) to the `x-bump-class` closed vocabulary in § Bump-class extension key above.
That vocabulary is scoped to bumps; a doc-only edit is not a bump, which is exactly why it needs
no class.

#### Cross-boundary semantic shape — the third axis

<!-- spec-backlink: docs/plans/2026-08-06-vendored-parity-equal-version-discriminator.md -->

Three independent axes now govern a vendored schema, and the vendored-parity duty gate
(`coordinator/tests/test_vendored_schema_version_parity.py`) reads a different one of them at
each decision point:

1. **`x-schema-version`** — the declared version string. Drives `HELD` /
   `CONSUMER_AHEAD_OF_MAIN` / `DECLARED_TOLERANCE` / `UNCOVERED_DRIFT` via `_classify_drift`
   (`coordinator/tests/test_vendored_schema_version_parity.py`, function `_classify_drift`),
   unchanged by this section.
2. **Semantic shape** (`_semantic_shape_hash`, `coordinator/tests/_schema_shape.py`, function
   `_semantic_shape_hash`) — the
   cross-boundary discriminator this section documents. It reuses `_shape_hash`'s own
   JSON-Schema-aware default-deny descent (`coordinator/tests/_schema_shape.py`, function
   `_shape_hash`, which already
   strips `description` and `$comment` at schema positions — see above) and additionally strips a
   NAMED root-level allowlist, `_AUTHORING_ANNOTATION_KEYWORDS = {"x-bump-class", "x-bump-note"}`
   (`coordinator/tests/_schema_shape.py`, module-level constant
   `_AUTHORING_ANNOTATION_KEYWORDS`). Never an `x-*` prefix glob.
3. **Prose / content** (`content_hash`) — advisory, ungated, unchanged from § above.

**Neither a `description`/`$comment` delta NOR an `x-bump-*` authoring-annotation delta is
drift.** The first is already-ratified doctrine — this same section, and
`docs/plans/2026-07-31-pin-gate-shape-hash.md` — and this section inherits it unchanged. The
second is new here and needs its own reason stated: `x-bump-class`/`x-bump-note` are DoE-side
metadata *about* a bump, not document shape — a validator behaves identically with or without
them, and claude-klabauter's vendored copies of `cross-repo-commitment.schema.json` and
`review-findings.schema.json` lack them today at equal versions with zero property/required/type
delta (table below).

**Why the strip is a named allowlist and not an `x-*` glob.** `x-` is the fleet's *extension*
namespace, not an inert-annotation prefix. The live root-level `x-*` inventory across
`coordinator/schemas/*.schema.json` is eight keys — `x-schema-name`, `x-schema-version`,
`x-bump-class`, `x-bump-note`, `x-generated-by`, `x-external-consumers`, `x-baton-class`,
`x-body-sections` — and `x-baton-class` (on `handoff.schema.json`) is a derived-field lookup
table claude-klabauter's `coordinator_core/contract/cockpit_schema/entities/summaries.py:156` reads **out
of the vendored copy**; its own docstring (:255-259) says a missing `x-baton-class.mapping`
entry nulls silently absent a parity gate. A glob would absorb exactly that key.

**This gate detects equal-version shape drift; it does NOT discharge or replace DR-097's
push-side notification duty.** Those are independent obligations answering different questions:
this section's gate tells you whether two vendored copies of a schema currently validate
identically; § Push-side duty on a vendored-schema bump (immediately below) governs whether a
bump owed an explicit notice to the sibling that vendors it. Passing this gate is not evidence
DR-097's duty was discharged, and discharging DR-097's duty does not exempt a schema from this
gate.

**A red-by-design gate gets suppressed within a week** — which is why the discriminator is
semantic shape and not byte or canonical comparison: byte and canonical both fire on three live
benign entries at HEAD today, measured against both repos' committed `HEAD`:

| schema | versions | `_shape_hash` | canonical | what actually differs |
|---|---|---|---|---|
| `cross-repo-commitment.schema.json` | 1.1.0 / 1.1.0 | **DIFFER** | DIFFER | DoE-only `x-bump-class`, `x-bump-note`. Zero property/required/type deltas. |
| `review-findings.schema.json` | 3.2.0 / 3.2.0 | **DIFFER** | DIFFER | DoE-only `x-bump-class`, `x-bump-note`. Zero property/required/type deltas. |
| `improvement-queue.schema.json` | 1.2.0 / 1.2.0 | SAME | DIFFER | `description` prose only. |
| `plan-tasks.schema.json` | 1.11.0 / 1.11.0 | SAME | SAME | Converged. Its drift window is the worked example for the section below: both copies read `1.10.0` while only claude-klabauter's declared `execution_mode`. **The gate covered it and was red** — `_shape_diff`'s AHEAD branch names the property and correctly says do NOT re-vendor. Nobody read it; claude-klabauter's own test is what surfaced it. This table is a snapshot and catches nothing on its own. |

### Push-side duty on a vendored-schema bump

<!-- spec-backlink: docs/decisions/DR-097-sibling-notification-duty-on-terminal-events.md -->

Everything above governs **pull-side** discipline: how a consumer's validator reacts once it
reads a record against a schema it may not have re-vendored yet. It does not, by itself, tell
DoE-claude to *tell* claude-klabauter a vendored schema bumped — that push-side duty is
`DR-097`. Read this doc first for whether/how a bump is holding or non-holding; DR-097 governs
whether the bump also owes an explicit notice to the sibling that vendors it. The two are
independent: a non-holding `top-level-array-additive` bump can still trigger DR-097's notice
duty, and a holding bump does not get a free pass on it either.

The parity guard that keeps the vendored set enumerated (12 schemas, not 14 — see DR-097) lives
at `coordinator/tests/test_vendored_schema_version_parity.py`; it is the mechanical
backstop that catches an unnotified bump on the next test run, not a substitute for sending the
notice at bump time.

## Established cross-repo cutover patterns

**Do not re-derive** these; reference them.

### Reader-first ordering

Always widen the **consumer** before bumping the **producer**.

> Sources: `state/improvement-queue/2026-06-27-reader-first-ordering-for-contract-bump.yaml`,
> `state/improvement-queue/2026-06-23-contract-version-cutover-must-widen-the.yaml`.

The correct sequence for a major-version bump:

1. Author the new schema version (bump `x-schema-version` major in the schema file).
2. Update the **consumer** to accept both the prior and bumped version — widen the
   reader before any producer change ships to main.
3. Merge the consumer change.
4. Author the producer change (bump `schema_version` in the records / emit template).
5. Merge the producer change.

A write-first (producer-first) flip makes the consumer crash or quarantine records
on the first record it reads after the bump.  Reader-first is the safe order.

### Dual-gate requirement

A **producer-side drift gate is necessary but not sufficient** for a cross-repo
schema cutover.

> Source: `state/lessons/` — search "producer-side drift gate is necessary-but-not-sufficient".

A producer gate (e.g. the refuse-on-newer-write path above) detects that the vendored
schema file is stale.  It does **not** detect a consumer-side ingest failure.  A
breaking field-add can still quarantine rows silently if the consumer's ingest code
does not have its own `schema_version` assertion.

Rule: every cross-repo schema cutover needs **both**:
- a producer drift gate (this validator, `mode: 'write'`), AND
- a consumer-side ingest-time `schema_version` fail-loud assertion (e.g. Cockpit's
  `checkSchemaVersion`, major-only — see `example-cockpit-repo/docs/decisions/2026-07-07-cockpit-live-remote-per-repo-observation-model.md`).

A producer-only gate gives false confidence.  The dual-gate principle holds regardless
of which specific consumer-side assertion is in play: a producer gate alone never
substitutes for a consumer-side ingest-time check, and vice versa — this is orthogonal
to whether that consumer assertion hard-throws on any newer version or only on a major
mismatch (see § Outage-gate implication below for the current major-only behaviour).

**Read the consumer's guard SOURCE before asserting a cross-repo outage.** A consumer's
version-gate behaviour must be read from its source, not a wiki summary. The current
major-only characterization below was confirmed by reading cockpit's `checkSchemaVersion`
(`ingest.ts:164-199`) directly — a protocol-wiki claim that it "hard-throws on any newer
`schema_version`" was **false** and produced a phantom-outage argument that overrode a
correct PM call. Reader-first holds are load-bearing for MAJOR bumps but coordination-only
for minor. Corollary: before declaring a sibling repo "un-scannable," verify it is actually
absent (check the registry path and the correct dir name) rather than inferring absence. [universal]

### Outage-gate implication (cross-plan dependency for ccos-8)

A consumer's ingest-time `schema_version` assertion (e.g. Cockpit's
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

### Narrowing an enum on a fleet-shared schema requires a sibling-record-corpus sweep before the narrow lands

The downstream-reader sweep above (§ A version bump requires a complete downstream-reader sweep) is about
*readers* — the code that parses a record. It is not the same claim as this one, which is about
*records* — the corpus of on-disk instances a fleet-shared schema already governs. **A reader that
accepts a value is not evidence that no sibling record still carries it.** Narrowing an enum on a
schema more than one repo emits into (`applies_to` reaches beyond this repo, or the schema is
vendored elsewhere) requires a **sibling-record-corpus sweep — enumerating every repo's live records
against the retiring values — before the narrow lands**, not only a reader-acceptance check.

**The generalized finding, which matters more than this one incident:** a fleet-wide oracle whose
consumer set is a hand-maintained list of repos silently shrinks below the fleet as repos are added,
and nothing fails when it falls behind the registry. A fleet oracle must **reconcile its consumer
set against the machine-local registry on every run**, and must **fail loud (non-zero exit) on an
unrecognised/off-enum value it finds**, rather than reporting a count and exiting 0 regardless. A
reporting tool that exits 0 on the exact condition it exists to detect is not a gate — it is a
dashboard wearing a gate's clothes.

**Reconcile against the registry — do not enumerate from it.** The obvious reading of the rule
above is "walk `repos.*`," and that substitutes one defect for another: the registry also carries
sandbox, fixture, and scratch keys (on the 2026-07-31 fleet, 15 keys including
`repos.zzztest-normcheck` → `/tmp/zzz` and `repos.example-game-repo-python-audit` → a UE `Saved/` dir), so a
walker built on it sweeps in exactly the non-repo class an explicit list exists to keep out.
`--list-receivers` is not the escape hatch either — it emits mirrors and aliases tagged
`is_receiver: False` and leaves filtering to the caller. The shape that satisfies the invariant
without inheriting the hole: keep the consumer set **explicit**, add a **second explicit set naming
every non-consumer registered key with a per-key reason**, and reconcile both against the live
registry each run — a key in neither set lands in an `unclassified` bucket and **gates**. A new
fleet repo then cannot sit quietly outside the oracle's view; it forces a classification, and no
heuristic about what "looks like" a real repo is ever needed.

**Fail loud against *which* vocabulary — an off-enum value is only off-enum relative to the schema
that governs that record.** "Reject unrecognised values" with no vocabulary attached is the trap
that reproduces this bug in the next oracle. Live and archived corpora are deliberately governed by
different schemas: `handoff-archived.schema.json` retains retired `kind` values on purpose (it was
*widened* in the same C10 commit that narrowed the live schema) precisely so archived records under
either vocabulary keep validating. An oracle that judges archived records against the live enum
fires on data that is exactly as it should be — claude-klabauter has zero live stranded records but 25
correctly-archived `spinoff-roadmap`, project-rag 37, example-market-data-repo 33. Rules: **live off-enum
gates; archived off-enum reports as a non-gating warning; an absent value is a valid bucket in both
populations and never gates** (~20 live records fleet-wide carry no `kind`). A gate that cries wolf
gets acknowledged by reflex, which leaves the fleet no better off than the pre-flight that never
fired at all — the same failure in a different coat.

**Concrete precedent (greppable):** the `baton-kind-vocabulary-one-axis-per-field` plan's C10 chunk
narrowed `coordinator/schemas/handoff.schema.json`'s live `kind` enum, retiring
`spinoff-goal`/`spinoff-roadmap`/`spinoff-roadmap-creator`. The plan HAD a gate for exactly this —
chunk C5, "Consumer-corpus pre-flight" (claude-klabauter
`coordinator_core/ops/fleet/consumer_corpus_preflight.py`) — and C5's own module docstring names
**DR-084** (an earlier producer-scoped-oracle failure) as the incident it was purpose-built to fix.
It failed anyway, on the same pattern, for three structural reasons: its `FLEET_REPO_KEYS` dict was
a hardcoded four repos, omitting 2 of the 3 repos actually stranded; it reported raw per-kind counts
without ever loading the schema, so it never exited non-zero on an off-enum value, only on an
unresolvable repo; and nothing invoked it — no hook, ceremony, or CI binding wired it into the
cutover. Result: 59 sibling records went unclaimable across example-cockpit-repo (25),
project-rag-ue-addon (21), and example-game-workbench-repo (13) — a purpose-built fix for DR-084's exact
failure mode recurred anyway, because the fix itself inherited DR-084's shape (hand-maintained
consumer list, no fail-loud). **A purpose-built gate is not proof against the failure it was built
to fix if it reintroduces the same hardcoded-consumer-set shape.**

**Watch-out — repo-name near-collision reads as a clean result.** The plan recorded "rag 0" during
this cutover, meaning `project-rag` carried zero retired-vocabulary records — true, but the 21
stranded records were in `project-rag-ue-addon`, a distinct sibling repo one prose-shorthand away
from the one actually checked. A near-identical repo name is exactly the shape that reads as a clean
sweep result while the sweep silently missed its target. **Sibling repo identity in a fleet oracle
must be a registry key (`machine-local get repos.<key>`), never a prose shorthand** — "rag" is not a
repo.

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

**Rule:** before re-pinning a vendored schema, diff the target version's `$defs` and any `applies_to`/glob metadata against the pinned one — not just the version string. If new globs appear, enumerate the directories they newly pull into scope and decide deliberately (conform them, or exclude them) *in the same change*. Treat a schema re-pin that adds `$defs`/globs as a scope change, not a constant swap. (Source: project-rag, artifact-shape-contract v1.0.0→v1.1.0 re-pin.)

## Ref-flatness is not a contract guarantee — a consumer that extracts a bare `$def` breaks the day composition lands

A vendored schema whose every `$def` happens to be self-contained invites a consumer to resolve a
file to its `$def`, **extract that sub-schema, and validate against it standalone**. That works
only while the contract is *ref-flat* — no `$def` carrying a `#/$defs/<name>` reference into the
root. Ref-flatness is a property of the data at a given version, never a promise: nothing in the
contract declares it, so nothing stops a later version from composing shared sub-shapes by
reference.

When composition lands, an extracted bare `$def` has no root to resolve against and raises
`PointerToNowhere` — **and that is a hard crash of the whole validation run, not a drift report on
one record.** The blast radius is the highest-traffic glob, not an obscure one: `artifact-shape-contract`
v3.0.0 composed `plan` → `grouping_approval_block`, and `plan` means `docs/plans/*.md`.

**Neither existing census detects the exposure**, because it is a property of *how the consumer's
validator is constructed*, not of what records it holds or which version it pins. A record census
returns the consumer clean; the vendored-validator-axis census sees the pinned copy but says
nothing about extract-vs-root-resolve; the consumer's own suite stays green until the pin flips.
So a consumer can be fully current on the notification list, hold zero affected records, and still
have its conformance gate go from working to crashing on the bump.

**Producer rule — call out ref-flatness loss by name in the bump note.** `x-bump-class: major` is
necessary but not sufficient: it says *something* breaks, not *which property the consumer
depended on*. The introduction of intra-`$defs` composition gets its own line in the bump note,
separately from enum narrowings and removed `$defs`. The line that discharges this is literally
"the schema is now composed by reference — a `$def` extracted standalone will no longer resolve."

**Consumer rule — re-root, never extract.** Build the validator by pairing the selected `$def`
with the root `$defs` at validator-construction time (or register the root document in a
`referencing` registry) rather than handing a bare sub-schema to the validator. The re-root is
verifiably inert against a ref-flat pin — identical ok/drift/unmatched counts — so it can land
*before* the bump rather than under crash pressure.

(Source: project-rag, `bin/validate-artifacts.py` on the v1.12.0→v3.0.0 pin flip;
fixed in `dbdbb0c14`. Post-fix the bump was a substantial net win there — drift 316→68, coverage
2686→3152 artifacts — which is exactly why the consumer defect must not be allowed to look like a
contract regression.)

## Frontmatter YAML-parsing gotchas — emitters must emit block-style, nullable fields need explicit type

The gate implementation (claude-klabauter's `coordinator_core/frontmatter/schema_validate.py`, cited at the
top of this doc) uses a **minimal** YAML parser (`parse_yaml`) for the frontmatter/record path. Two shapes
it does NOT handle the way a full YAML library would — both are emitter-side authoring constraints, not
validator bugs:

- **Flow-style mappings parse as raw strings, not objects.** `schema_validate.py`'s `parse_yaml` reads a
  flow-style mapping (`divergence: {diverged: false}`) as the literal string `"{diverged: false}"`,
  so an object-typed schema field emitted flow-style fails validation with `expected object, got
  string`. **Emitters must emit block-style YAML for object fields:**

  ```yaml
  divergence:
    diverged: false
  ```

  (coordinator-doc-new's flight-recorder emitter hit exactly this and had to switch `divergence` to
  block style to validate.)

- **A scaffold-null-then-written-later field needs type `['string','null']`, not bare `'string'`.**
  A field scaffolded as `null` and populated on a later write (e.g. `started_at`/`finished_at`) fails
  validation at the null-placeholder stage unless its schema type admits null. Declare it
  `['string','null']`. (Source: coordinator-doc-new flight-recorder emitter.)

## Kept-YAML exceptions (ccos-1 migration)

Six schemas were intentionally **not** migrated to `.schema.json` during the ccos-1 wave and remain
as `.yaml` files indefinitely.  The dual-format loader supports `.yaml` schemas indefinitely, so
these are permanently valid — not technical debt.

| Schema file | Reason kept as YAML |
|---|---|
| `schemas/lesson-entry.yaml` | Uses `match_mode: inline-tag-per-entry` — validated by `validateLessonsFile`, not the frontmatter path.  JSON Schema frontmatter validation is irrelevant for inline-tagged lesson entries; migrating would add noise without benefit. |
| `schemas/review-trail.yaml` | Validates `.json` records, not markdown frontmatter.  The lint tool skips `.json` files, so this schema is exercised by a different code path (`validate_frontmatter()` on emitted JSON blobs).  Migrating to `.schema.json` would collide with the loader's file-extension heuristic for the JSON Schema path. |
| `schemas/bug-backlog.yaml` | **Validated via the native schema seam.** Validated at write time by `bin/coordinator-queue-append.py` via `coordinator_core/frontmatter/schema_cli.py`'s `describe()`/`validate()` (the byte-identical parity successor to the deleted `schema-cli.js`, claude-klabauter `480ad8f8`), which reads the YAML-dialect shape directly (not JSON Schema); `schema_loader.py` does not cover this schema — see option (d). |
| `schemas/debt-backlog.yaml` | Native-seam-validated (see bug-backlog). |
| `schemas/improvement-queue.yaml` | Native-seam-validated (see bug-backlog). |
| `schemas/lessons-outbox.yaml` | Native-seam-validated (see bug-backlog). |

> **Residual / follow-on:** the 4 queue schemas stay `.yaml` because `schema_cli.py` (via
> `schema_validate.describe()`/`validate()`) supports YAML-dialect shapes indefinitely
> (dual-format loader). The separate `schema_loader.py` was **retired** in the dual-yaml-parser
> option (d) workstream; there is no other Python parser left to port. The remaining follow-on is
> migrating these 6 `.yaml` schemas to `.schema.json` (full JSON Schema unification) — a discrete
> future workstream, not a ccos-1 residual. These were briefly migrated and reverted in-session
> when the break surfaced (queue-append failed the schema lookup); they are now stable `.yaml`.

All other schemas in `schemas/` that match markdown frontmatter paths were migrated to
`.schema.json` in the ccos-1 W4 wave (W4a–W4d).
