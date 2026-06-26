# @coordinator/cockpit-contract

The **work-state data contract** (tc-2) — the pinned interface every work-observation
cockpit producer and consumer speaks. This is the load-bearing seam between the
producer half (`~/.claude` emission, tc-3) and the ingestion/query/display stack
(tc-4 connector, tc-5 store, tc-6 dashboard, tc-8 MCP).

**Canonical wire format:** the JSON Schema under [`schema/`](./schema/). Zod schemas
in [`src/`](./src/) are the authoring source of truth; TypeScript types are inferred
from them; the JSON Schema is emitted from Zod (R7 — `project-opticon` generates its
TS/Zod from the JSON Schema, it does not host it).

See [`DECISIONS.md`](./DECISIONS.md) for the field-set rationale.

## Entities

| Entity | Source | Notes |
| --- | --- | --- |
| `ProvenanceEnvelope` | (shared) | Required on every fact. `observed_at` + `derivation` load-bearing; `ref` is `{branch, sha}`. |
| `CoordinatorRoot` | GitHub census | Keyed `(repo, coordinator_root_path)`. `last_activity_at` from branch-tip `committedDate`, not `pushedAt`. |
| `Branch` | census + REST compare | Keyed `(repo, name, tip_sha)`. `merge_base_sha` guards rebase artifacts. |
| `Goal` | declared (tc-3) | Append-only event record; current = latest non-superseded per `(repo, root, period, period_value)`. |
| `RoutineSignal` | staleness scripts | Typed derived-signal, 6 named kinds. Light bitemporal: `observed_at` vs `computed_as_of`. |
| `DayRollup` / `WeekRollup` | completion log | Deterministic facts are SSOT; `narrative` is a regenerable view citing its watermark. |
| `HandoffSummary` | `state/handoffs/*.md` | `repo`/`coordinator_root_path` injected by connector/emitter. |
| `BacklogItemSummary` | debt/bug/improvement YAML | Tagged `type`; `severity` (bug), `risk` (debt) nullable. |
| `ReviewTrail` | `state/review-trail/*.json` | `repo` injected. |

## Usage

```bash
pnpm install        # links esbuild native binary + builds dist/ (prepare → tsc)
pnpm run build      # compile src → dist/ (what the exports map points at)
pnpm run emit       # regenerate schema/*.json from the Zod definitions
pnpm run test       # round-trip + nullability-contract + datetime-format assertions
pnpm run typecheck  # tsc --noEmit
```

**Consuming the contract.** Cross-repo (project-opticon), generate TS/Zod from the
emitted `schema/*.json` — that JSON Schema is the canonical wire format (R7). For a
same-repo or workspace-linked JS consumer that wants the runtime Zod validators
directly, import `@coordinator/cockpit-contract` (resolves to compiled `dist/`).
Nullable fields are **present-as-null, never absent** — see DECISIONS § D9.

`ENTITY_SCHEMAS` (in `src/index.ts`) is the registry driving emit and the
round-trip test — add an entity there and both pick it up; the test fails if an
entity lacks a fixture or a fixture has no entity.

## Owner-Namespace Seam

The `owner` field on `CoordinatorRoot` and `Branch` is a **closed enum**, not a free
string — unknown owners are rejected at parse time. Which orgs appear in that enum is
operator configuration, not a contract constant.

Two env vars control schema emission:

| Env var | Purpose | Default |
| --- | --- | --- |
| `COCKPIT_OWNER_NAMESPACES` | Comma-separated list of GitHub org/owner namespaces to include in the closed enum. | `dbc-oduffy,Example-Interactive,workstation` (real orgs — private working tree) |
| `COCKPIT_SCHEMA_OUT_DIR` | Directory to write the emitted `*.schema.json` files into. | `schema/` (committed, canonical) |

**Private emit (default):** `pnpm run emit` — uses real orgs, writes to committed
`schema/`. Run this when the owner set changes or any Zod schema changes.

**Example / OSS emit:** `pnpm run emit:example` — synthetic orgs (`example-org`,
`example-team`), writes to `schema-example/` (not committed). Use this to generate
a sanitised schema for documentation, OSS distribution, or consumer onboarding without
leaking real org identity.

**Verification:** `bash test/owner-emit-example.sh` asserts that the example emit
produces synthetic-only owners and leaves committed `schema/` byte-identical.

## Versioning

`CONTRACT_VERSION` in `src/index.ts`. Bump on any breaking field change to the
emitted schema. Downstream consumers (tc-1/tc-3/tc-4/tc-5) pin against the emitted
JSON Schema.
