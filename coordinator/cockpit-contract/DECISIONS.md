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

## D12 — Owner enum is seam-generated (closed enum, env override) for OSS portability (2026-06-25)

The `owner` field on `CoordinatorRoot` and `Branch` uses a **closed Zod enum**, not
`z.string()`. `z.string()` was explicitly rejected: it downgrades parse-time validation
and eliminates the boundary guarantee that unknown owners (misrouted data, typos, wrong
repo) are caught at the contract parse boundary rather than silently stored and only
discovered in tc-5 queries. The closed enum is the entire point.

The set of allowed values is operator / deployment configuration. Hard-baking real org
identities (`dbc-oduffy`, `Example-Interactive`) into the Zod literal made the emitted
JSON Schema unsuitable for OSS distribution without leaking real GitHub org identity.

**Resolution:** `OwnerNamespace` is now built at runtime by `resolveOwnerNamespaces()`
in `src/owner-namespaces.ts`, reading the env var `COCKPIT_OWNER_NAMESPACES` (comma-
separated) with a fail-loud guard on a present-but-all-blank value. Two operational
modes:

- **Private emit (default, env unset):** real orgs (`dbc-oduffy`, `Example-Interactive`,
  `workstation`). `pnpm run emit` writes to committed `schema/`.
- **Example emit (env set):** synthetic orgs (e.g. `example-org`, `example-team`).
  `pnpm run emit:example` writes to `schema-example/` (not committed). Intended for
  OSS distribution and consumer onboarding documentation.

**Also rejected:** a swap-at-publish approach (shipping one committed schema and
post-processing it during publish). Rejected because it would require a separate
publish pipeline step that could drift from the source of truth, and because the closed
enum must be correct in the emitted output — patching it after emit is fragile and
bypasses the Zod source-of-truth discipline (D2). The env-seam approach keeps a single
emit path; the only variable is which enum members it emits.

The `COCKPIT_SCHEMA_OUT_DIR` env var parallels the namespace seam: it redirects the
emit output directory so example / OSS emits never touch committed `schema/`. Default
(env unset) is byte-identical to the previous hardcoded `join(here, "..", "schema")`.

## Ask 6 — handoff enum partition (C4, 2026-06-26 — superseded RETIRED)

Three decisions shipped together as a single coherent enum + documentation edit.

**`recovery` kept in `HandoffKind`** — the structured-handoff spinoff verdict landed
**`recovery == kind`** (not flavor), confirmed at `schemas/handoff.yaml:81` and
unblocked by commit `96d877a4`. The parent plan (D3 row) originally recommended
moving `recovery` to a `flavor` field; the landed spinoff verdict diverged to `kind`,
so `recovery` stays in the `HandoffKind` enum. Do not re-litigate this: the verdict
was a deliberate domain decision, not an oversight. The `kind:` absent → `session-handoff`
normalization contract (NORMALISATION CONTRACT in `HandoffKind`'s docstring) is
unchanged.

**`superseded` RETIRED from `HandoffStatus` (handoff-only) — 2026-06-26.** The Ask-6
removal was originally dropped because the stated premise ("never observed, no doctrine
dependency") proved false. The retirement was then executed in the correct sequence:
doctrine writers (CLAUDE.md, spinoff-handoffs.md, skills/handoff/SKILL.md,
schemas/handoff.yaml) and the one live archived `superseded` handoff record were
migrated FIRST; the contract was narrowed after. `HandoffStatus` is now
`["active", "consumed"]`. Supersession of a handoff is expressed via
`deployment_state: abandoned` + the existing `predecessor`/`supersedes:` lineage fields.

**Legacy/external tolerance — coerce-at-ingest.** Readers tolerate a legacy or external
handoff carrying `status: superseded`. The cockpit emitter coerces `superseded` →
`consumed` at ingest, before the strict Zod validator sees the record. Any other
string-but-unrecognized handoff status that passes the per-record jq `select` (which
excludes only missing/null fields) but is NOT coerced triggers a **whole-emit abort**
at `validate_main_record` — not a per-record exclusion. Only the one retired
`superseded` token is coerced; everything else still hard-aborts the emit.

Ref plan: `docs/plans/2026-06-26-retire-superseded-handoff-status.md` § C4.

**stage↔`deployment_state` partition** — `status` (`active | consumed`) and
`deployment_state` (`awaiting_gate | ready_to_fire | in_flight | shipped | abandoned`)
are **orthogonal axes**, not redundant. `status` is a two-stage gate: "is this
handoff still in play?" `deployment_state` is the delivery lifecycle progression of
the associated workstream. A `consumed` handoff can carry `deployment_state: in_flight`
(picked up, not yet shipped); an `active` handoff can carry `deployment_state:
ready_to_fire` (staged, awaiting pickup). Consumers MUST NOT substitute one axis for
the other when keying queries. This partition is documented in the `HandoffStatus`
JSDoc in `src/entities/summaries.ts` and referenced from `DeploymentState`.

## D13 — 1.0→2.0 breaking bump shipped with bilateral consumer-migration gate (C11)

The 1.0→2.0 bump is **intentionally breaking** (strict-mode `additionalProperties:false` +
all additive fields land in `required` with `anyOf:[T,null]` per D9 — making any additive
field-add a contract break; `1.1.0-first` is not available under this contract). The prior
1.0 bump shipped without a consumer signal gate (DSR-2026-06-23-4, status: open). This bump
MUST close that debt entry.

The gate is **bilateral**:

- **Producer side (this repo):** emitter fails loud on semver mismatch; `sync-cockpit-contract.sh`
  wired as a mandatory consumer-staleness signal (not merely invocable).
- **Consumer side — by consumer:**
  - **project-opticon:** already ships `assertSchemaVersion` (`ingest.ts:71-93`, major-aware
    `compareSemver` at lines 43-52) — a host 2.0 flip before opticon re-vendors causes a
    **TOTAL COCKPIT-OUTAGE** (every ingest aborts). Gate is therefore outage-gating, not advisory.
    Sequence: opticon widens reader to accept 2.0 shapes AND re-vendors FIRST; then host flips
    `CONTRACT_VERSION = "2.0.0"`. The 2026-06-26 bilateral confirmation: opticon landed a
    dual-read reader/store (`assertSchemaVersion` auto-flipped 1.0.0→2.0.0 on re-vendor;
    still-1.0 host emission warns-proceeds with no quarantine) — AC11 outage window closed.
  - **example-repo:** `assertSchemaVersion` unverified at review time; consumer memo must ask
    geneva to verify and add if absent.
- **Sequencing rule:** widen-reader-first is mandatory for opticon. Do NOT flip the host
  `CONTRACT_VERSION` before the consumer memo is dispatched and PM-relayed.

DSR-2026-06-23-4 is `git mv`'d to `archive/debt-backlog/` with `status: closed` only after
the C11 consumer memo is dispatched.

## D14 — Fleet board-scope: PRIVATE repos excluded from `coordinator_roots[]` (2026-06-26)

`CoordinatorRoot.visibility ∈ {PRIVATE, INTERNAL, PUBLIC}` is already on the schema.
Whether private repos appear on the all-staff board is a direction-class PM call (the Director of Engineering P1 §
"consumer-leak — fleet visibility"). **PM decision 2026-06-26 (re-confirmed):**

- **PUBLIC** and **INTERNAL** roots are board-eligible.
- **PRIVATE** roots are **excluded** from `coordinator_roots[]` in every emitted fleet snapshot.
- C9c bakes the visibility filter; acceptance asserts PRIVATE exclusion.

This is not a schema-level filter (the entity carries `visibility`) — it is an **emitter-level
gate**: C9c's fleet-discovery loop skips any root with `visibility == "PRIVATE"` when building
the array. Rationale: the all-staff cockpit is the rendering target; emitting private repo
names to that surface leaks org structure.

## D15 — `CrossRepoMemoSummary.title` is board-public (authors warned)

`CrossRepoMemoSummary` is metadata-only: no memo bodies, no AC prose. The `title` field is
free prose and ships verbatim to the all-staff board with no redaction. Real memo titles can
encode sensitive coordination details (embargos, unannounced moves). PM decision: **accept
title as board-public with a documented author norm** — authors are warned at write time that
memo titles are observable by the full fleet board audience.

The entity docstring in `src/entities/cross-repo-memo-summary.ts` MUST carry this norm
verbatim: "metadata only — no AC prose, no memo bodies, AND memo titles are board-public
(authors warned)." No length cap or sensitivity-flag seam was added in 2.0; a future revision
may introduce a `sensitive: bool` field without a schema bump if the author-norm proves
insufficient.

## Out of scope (enforced — see stub § Anti-scope)

No emission (tc-3), connector (tc-4), store DDL (tc-5), dashboard (tc-6), or
project-rag addon (tc-5/tc-8) code lives in this package. Contract only.
