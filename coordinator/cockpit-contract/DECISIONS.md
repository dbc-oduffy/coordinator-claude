# cockpit-contract — Decisions (tc-2)

Design decisions made authoring the work-state contract. tc-3 (emission) and tc-4
(connector) authors: read this for the *why* behind the field set, not just the shape.

Roadmap: `state/roadmap/work-cockpit-2026-06-21/`. Stub:
`state/handoffs/2026-06-21_210002_roadmap-work-cockpit-2026-06-21-tc-2.md`.

## D1 — Contract home: coordinator (R7), JSON Schema is canonical

Resolved upstream by **COORDINATOR-RESOLUTIONS.md § R7**, recorded here per AC.

The canonical work-state contract lives in **coordinator** at
`plugins/coordinator/cockpit-contract/`. The canonical
**cross-repo wire format is the emitted JSON Schema** under `schema/` — coordinator
emits it as a first-class surface. The `project-opticon` repo (tc-1) **generates its
TS/Zod from the JSON Schema; it does not host the schema.** All downstream stubs
import from this canonical location:

- **tc-1** (opticon skeleton) — generates TS types from `schema/*.json`.
- **tc-3** (emission, `~/.claude`) — validates `state/cockpit-emission.json` against the emitted JSON Schema.
- **tc-4** (connector) — imports the TS `Branch` / `CoordinatorRoot` types (or generates from schema).
- **tc-5** (store) — authors the relational DDL from the frozen C5-consumable field set.

This is **not** a re-openable pm-gate. A picking-up EM who reads "contract-home" as
contested is reading a superseded stub version.

## D2 — Zod is the authoring source of truth; TS types are inferred

The AC asks for "a complete TS type AND Zod schema" per entity. Rather than
hand-maintain two parallel definitions (which drift), **Zod schemas are the single
source of truth and TS types are derived via `z.infer`**. Every entity module
exports both the schema (`export const Branch = z.object(...)`) and the inferred
type (`export type Branch = z.infer<typeof Branch>`). This guarantees the validator
and the type can never disagree — the dispatch-safety property tc-2 exists to
protect.

## D3 — Zod v4 native `z.toJSONSchema()` (no `zod-to-json-schema` dep)

Zod v4 (4.4.x, pinned here) ships native JSON Schema emission. The stub suggested
`zod-to-json-schema or equivalent`; the native path is the equivalent and drops a
dependency. Emit targets `draft-2020-12`. `z.iso.datetime({offset:true})` →
`format: date-time`; `z.iso.date()` → `format: date`. `additionalProperties: false`
is emitted on every object (Zod strict-by-default), so unknown fields are rejected
at the wire boundary — a stronger field-completeness guarantee for tc-5.

**Version pinning:** `zod` is pinned to `~4.4.0` (patch-only), not `^4.0.0`. Zod v4
is young and `z.toJSONSchema` output / `z.iso.datetime` behaviour can shift across
minors; a contract package must not let a transitive minor bump silently change the
emitted JSON Schema. **A zod bump here is a contract change** — bump
`CONTRACT_VERSION` and re-run `pnpm run emit` when raising it. The committed
`pnpm-lock.yaml` pins the exact resolved version for reproducible installs.

## D9 — `.nullable()` means key-present-with-null, NOT key-absent (wire contract)

Every nullable field uses Zod `.nullable()`, never `.optional()`. The distinction is
load-bearing for tc-3/tc-4 emitters: **the key MUST be present in the emitted
payload, carrying `null` when uncomputed** (e.g. `ahead_by: null` before the REST
compare runs). Omitting the key entirely fails Zod validation, and the emitted JSON
Schema lists nullable fields in `required` (with `anyOf: [T, null]` types) — which
is correct for this contract: present-as-null gives tc-5 a value to insert in every
column, with no "absent vs null" ambiguity. The round-trip test asserts both
directions (present-as-null passes; key-omitted is rejected). tc-3/tc-4 authors:
emit `null`, do not drop the key.

## D10 — Emitted JSON Schema inlines shared sub-schemas (bundle `$defs` is a catalogue)

Zod v4's `z.toJSONSchema()` inlines nested schemas rather than emitting `$ref`
pointers, so `ProvenanceEnvelope` is duplicated verbatim inside every per-entity
schema. This is intentional for the per-entity `schema/<name>.schema.json` files —
each is **self-contained** and validates standalone. The bundle
`schema/cockpit-contract.schema.json` carries every entity (including
`provenance-envelope`) under `$defs`, but the entity entries there do NOT `$ref` the
shared `provenance-envelope` def — they inline it too. **Consumers validating wire
data must use the per-entity files; the bundle's `$defs` is a catalogue, not a
shared `$ref` target.** A future contract version that changes ProvenanceEnvelope
re-emits all files atomically (single `pnpm run emit`), so divergence cannot occur
within a committed version — but cross-version `$ref` reuse is not offered.

## D11 — `declared_by_machine` is a free string, not a machine enum (deliberate)

The stub illustrated `declared_by_machine` as `"machine-c" | "machine-a"`. It is
implemented as `z.string()` ON PURPOSE: the machine-slug set is NOT stable — on
2026-06-22 the Mac's daily-branch slug drifted `machine-c` → `machine-b` mid-stream
(`cs_compute_machine` output changed). An enum would reject the new slug and require
a contract bump for every machine rename. A free string is the correct shape for an
unstable, low-cardinality identifier; tc-5 stores it as TEXT.

## D4 — Three read-from-disk summary entities are first-class, not deferred

The frozen C5-consumable field set (stub § Specification) lists **HandoffSummary**,
**BacklogItemSummary**, and **ReviewTrail** alongside the six core entities. The AC
forbids deferring any field in that set, so these are authored as full Zod
entities now (`src/entities/summaries.ts`), not left for tc-5 to invent. A field
gap here would force a re-run of tc-3 AND tc-4 — the exact failure tc-2 prevents.

- `repo` + `coordinator_root_path` are **injected by the connector/emitter** — the
  on-disk frontmatter/JSON does not record which repo it was read from.
- `BacklogItemSummary` is a single tagged shape (`type: debt|bug|improvement`) with
  `severity` (bug-only) and `risk` (debt-only) nullable — simpler for a single
  relational table than three near-identical entities.
- `BugSeverity` includes **P3** (observed on-disk) beyond the corpus-noted P0–P2.

**Extensions beyond the stub's frozen field list** (added for tc-5 keying/queries —
flagged so integration does not treat them as errors):
- `coordinator_root_path` on `BacklogItemSummary` and `ReviewTrail` — the backlog
  YAML and review-trail JSON carry `from_repo`/`repo` but no root-path; injected by
  the connector/emitter to match the `(repo, coordinator_root_path)` keying every
  other entity uses, so a monorepo's backlogs don't collapse to one key.
- `reviewed_at` (ISO-8601 UTC) on `ReviewTrail` — the review-trail JSON body has no
  canonical date field (verified across `state/review-trail/*.json`); the date is in
  the filename. Injected from the filename so tc-5 can run `WHERE reviewed_at
  BETWEEN ...` — `provenance.observed_at` is the observation time, not the review
  date, and is not a substitute.

## D5 — Provenance is required on every entity, `ref` is structured

Per the Data Science Reviewer P1-D2/P2 and the stub: `ProvenanceEnvelope` is a non-optional field on
every entity; `observed_at` and `derivation` are non-nullable. `ref` is a
`{branch, sha}` **object**, not a flat `"work/...@sha"` string — tc-5 splits it into
`ref_branch` + `ref_sha` columns for `WHERE ref_sha = ...` provenance queries; a
lossy flat string defeats that.

## D6 — Nullability conventions

- **Computed-later branch facts** (`ahead_by`, `behind_by`, `merge_base_sha`) are
  `nullable` — the REST compare call may not have run at census time.
- **Parsed hints** (`machine_hint`, `date_hint`) are `nullable` — non-`work/{machine}/{date}` branches don't parse.
- **`narrative`** (rollups) is `nullable` but **present** (not optional): a rollup
  always has the slot; `null` means "not yet generated." `deterministic_facts` is
  never nullable — it is the SSOT; narrative is a regenerable view (the Data Science Reviewer P1-D4).

## D7 — `period_value` encoding (Goal, rollups)

`Goal.period_value` and rollup `period` are strings encoding the grain:
- `day` → ISO date `YYYY-MM-DD`
- `week` → ISO week `YYYY-Www` (e.g. `2026-W25`)
- `repo` (Goal only) → the literal `"ongoing"`

Kept as a string (not a union of branded types) so the relational store indexes one
column per grain; the grain field disambiguates. tc-3/tc-5 must agree on ISO-week
formatting (`YYYY-Www`, zero-padded week).

## D8 — Toolchain: pnpm + tsx + vitest, esbuild build allowlisted

Matches the fifa-stats stack family (R1) — Vitest for tests. `tsx` runs the emit
script without a build step. pnpm 11 requires build-script allowlisting in
`pnpm-workspace.yaml` (`allowBuilds: { esbuild: true }`) — esbuild (transitive via
tsx/vitest) links a platform-native binary in postinstall; without the allowlist a
clean `pnpm install` leaves it unbuilt and `tsx` fails at runtime. This is the
clean-install-completeness fix, committed so a fresh checkout's `pnpm install` works.

**Build / consumption:** the package `exports` map points at compiled `dist/`
(`tsc -p tsconfig.build.json`, run via the `prepare` lifecycle script on install),
NOT at raw `.ts` — a `.ts` `exports` target throws "Unknown file extension" under
Node's ESM loader for any consumer not running through tsx. Cross-repo, the canonical
consumption path is still the emitted **JSON Schema** (R7): project-opticon generates
its own TS/Zod from `schema/*.json`. The compiled `dist/` exists for same-repo /
workspace-linked JS consumers who want the runtime Zod validators directly; `dist/`
is gitignored and rebuilt on install.

## Out of scope (enforced — see stub § Anti-scope)

No emission (tc-3), connector (tc-4), store DDL (tc-5), dashboard (tc-6), or
project-rag addon (tc-5/tc-8) code lives in this package. Contract only.
