# Strategic Self-Description Standard

<!-- distilled: run 2026-07-19-synth; sources: cross-repo/archive/2026-07-12-example-cockpit-repo-em-strategic-self-description-repo-setup-lifecycle.md, cross-repo/archive/2026-07-12-example-cockpit-repo-em-superpowers-editorial-honesty.md, 2026-07-14-self-description-competitor-marking-deliverable.md -->

> **Spec backlink.** DoE's producer/schema leg of the fleet strategic self-description standard —
> `docs/plans/2026-07-11-strategic-self-description-standard.md` (Chunk C6). Schema:
> `coordinator/schemas/strategic-self-description.schema.json` (Chunk C1). Placement doctrine:
> `state-placement-law.md § Fleet Producer Contract → Artifact class — strategic self-description`
> (Chunk C2). Maintenance ceremony: `coordinator/skills/strategic-self-description-refresh/SKILL.md`
> (Chunk C4). **Provenance.** Actions the cockpit proposal (`2026-07-11-example-cockpit-repo-em-strategic-self-description-standard.md`);
> DoE owns the standard and built it from the abstract need each field serves, not cockpit's shipped
> field names — see the plan's Anti-scope.

## What this is

A repo's strategic self-description is its own authored declaration of what it strategically *is* —
mission, lifecycle phase, positioning, notable milestones, competitive stance, and a call-to-action —
living at `state/strategic/self-description.yaml`, one per repo. It is a **new artifact class under
the already-ratified Fleet Producer Contract**, not a new topology: per-repo emitted, harvested
read-side by consumers (cockpit's Strategic board first), never consolidated into a fleet-wide file.
See `state-placement-law.md § Fleet Producer Contract` for the placement doctrine this class extends.

## Schema reference

Canonical schema: `coordinator/schemas/strategic-self-description.schema.json`
(`x-schema-name: strategic-self-description`, `applies_to: state/strategic/self-description.yaml`).
Top-level required fields:

| Field | Shape | Notes |
|---|---|---|
| `repo_identity` | `{owner, repo, coordinator_root_path}` | Canonical join key — the SAME tuple the Fleet Producer Contract's emission join-key already uses (`emission-conformance-contract.md § Producer Contract`), not a competing single-field slug. |
| `lifecycle` | enum, see § Lifecycle enum below | DoE-canonical, richer than any one consumer's need. |
| `vision` | `{value, provenance}` | One-paragraph strategic statement. |
| `version_highlights` | array of `{label, date, bullets[], provenance}` | Ordered, most-relevant-first; may be empty. |
| `competitors` | array of `{name, relationship, note, provenance}` | `relationship` enum: `competitor \| complement \| prior-art \| superseded-by \| supersedes`. `note` is present-as-null when absent. |
| `call_to_action` | closed discriminated union, see § CTA below | Security boundary. |
| `hero_asset` | `string \| null` (URI) | Present-as-null when absent. |
| `maturity_axis`? | `string \| null`, OPTIONAL | Consumer-set-only (DEC-4) — DoE schema does not interpret its value. |
| `depends_on`? | array of repo-identity refs, OPTIONAL | Consumer-set-only (DEC-4) — blast-radius / retirement-impact queries. |

`additionalProperties: false` throughout — the schema is closed, not merely documented-closed.

## The three-value provenance model (DEC-2)

Every content-bearing field (`vision`, each `version_highlights[]` entry, each `competitors[]` entry)
carries a sibling `provenance` marker drawn from a **three-value enum**, never a binary:

- **`curated`** — a human authored or editorially ratified this value (e.g. at a
  `strategic-self-description-refresh` ceremony, or by hand-authoring the instance).
- **`generated`** — a machine (claude-klabauter) derived this value from an observable signal (commit history,
  release notes, example-market-data-repo deltas) and it has not yet been human-ratified.
- **`asserted`** — a human typed a bare factual claim with **no editorial judgment and no observable
  signal behind it** — the canonical case is a version label: someone typed `"v2.3"` and nothing
  computed or verified it, so it can silently drift out of truth with no signal to catch the drift.

`asserted` is a genuine third state, not a synonym for either neighbor. Collapsing to
`curated | generated` is the named anti-pattern (plan § Anti-scope) — an honesty-badge consumer must
be able to render three distinct visual/trust treatments, and squashing `asserted` into `curated`
overstates its reliability while squashing it into `generated` understates the human's role in typing
it.

<!-- Review: code-reviewer Finding 2 (nit) — the AC1 fixture named binary-provenance.json proves the
     enum is CLOSED (any value outside curated|generated|asserted is rejected) but cannot, by itself,
     distinguish a correctly-3-valued schema from an incorrectly-collapsed-to-2-valued one — a schema
     that had actually shipped `enum: ["curated", "generated"]` would reject that same fixture too.
     DEC-2's binary-collapse defense is STRUCTURAL, not fixture-provable in isolation: it is verified
     by reading `$defs.provenance.enum` in strategic-self-description.schema.json and confirming it
     literally lists 3 values, not by any single instance the schema rejects. -->



> **Disambiguation — this is NOT the RAG-embedding `curated` category.** `docs/wiki/addon-chunker-categories.md`
> already uses `curated` to mean "human-authored content intended for direct embedding in a
> user-facing knowledge base" (a chunker-ingest classification). The provenance-marker sense here is
> unrelated: it means *a human ratified this specific field's value at a ceremony or by direct
> authorship*, not that the field is a candidate for embedding. Same token, two independent
> vocabularies — do not conflate them when reading either wiki.

## Curated-vs-generated partition and the reconciliation seam

The standard splits authorship into two channels that never write the same file directly:

- **`state/strategic/self-description.yaml`** — the canonical, human-ratified artifact. Only a human
  ratify decision writes here (directly, by hand-authoring, or via the refresh skill's Step 4 write).
- **`state/strategic/self-description.draft.yaml`** — a per-repo sibling claude-klabauter may emit, carrying
  `provenance: generated` observable fields ONLY (e.g. `version_highlights` candidates, competitor
  signal candidates). Claude-Klabauter never writes the canonical file and never writes the human-curated
  `competitors[].relationship` judgment value, even inside the draft.

The reconciliation seam (proposal §5) is the `strategic-self-description-refresh` skill
(`coordinator/skills/strategic-self-description-refresh/SKILL.md`): draft-present-triggers-consume —
if a draft exists, the skill walks each `provenance: generated` field as a diff-against-canonical and
asks the human to ratify (write draft value, stays `generated`), override (human types a replacement,
becomes `curated` or `asserted`), or skip (canonical value untouched). Generation SEEDS curation; it
never auto-commits over human-ratified content — this is the **non-clobber invariant**. The skill is
nudged (not scheduled) from `/workweek-complete` (DEC-6): a discovery-surface mention that makes the
ceremony greppable and calendar-anchored, not a cron trigger — the human running the ceremony IS the
gate.

## Consumer-contract properties

Two properties every consumer of this artifact can rely on, enforced at the schema level:

- **Present-as-null, never omitted-key.** Nullable fields (`hero_asset`, `competitors[].note`) are
  `required` in the schema with a `["<type>", "null"]` union type — the key MUST be present in every
  conformant instance, with value `null` when there is no content. A consumer reading
  `instance.hero_asset` never has to distinguish "key missing" from "value absent"; both collapse to
  the single pattern-matchable case of `null`. This satisfies cockpit's D9 read contract.
  **The guarantee is carried by `required` plus the null union, and by nothing else.** An OPTIONAL
  field does not have it and cannot be given it by a sentence in its `description` — a validator
  reads neither. `competitors[].documents` is the standing case: optional by construction, so the
  1.4.0 bump could stay `nested-field-additive`, and so an omitted key, `null`, and `[]` are three
  legal spellings of one thing that a consumer coalesces (`entry.documents ?? []`). Measured
  2026-09-03 across the fleet's ten self-descriptions: of 57 competitor entries, 30 omit the key
  and 12 write it as null — the omitted form is the majority and is conformant. Moving an optional
  field into `required` to recover the guarantee is a `major` bump, holding on every axis; do not
  reach for it to make a description true. See
  `coordinator-tripwires/present-as-null-is-carried-by-required-never-by-a-description.md`.
- **Validate-or-degrade for `call_to_action` (DEC-5).** `call_to_action` is a closed `oneOf` over
  `kind`-discriminated branches (`url`, `claude-session`, `none` today), each pinning its own required
  payload shape with `additionalProperties: false` on both the branch and the envelope, and `kind`
  itself a closed enum. A consumer that validates an instance against this schema is handed either a
  fully-conformant payload for the given `kind` or a hard validation failure — never a schema-legal
  envelope wrapping a semantically malformed payload. This forecloses the validate-then-trust
  anti-pattern (a consumer trusting schema-validity alone and then acting on a malformed payload) and
  gives a consumer's validate-then-degrade posture a real schema decision to degrade on.
  <!-- Review: code-reviewer Finding 3 (P2) — plan chunk C1 named only `url` and `claude-session` as
       worked examples ("e.g." framing); `none` (label-only, no payload key) was added by the executor
       beyond those two, for a repo with genuinely no call-to-action (confirmed use case:
       state/strategic/self-description.yaml-shaped instances that predate a CTA decision). It does
       not weaken DEC-5's closed-union guarantee — a consumer switching on `kind` still gets a hard
       validation failure on any unrecognized value, and `none` degrades trivially (render the label,
       no action). Noted here for plan/executed-diff provenance traceability. -->
  The CTA is a security boundary (spawn-boundary command/argument-injection class) — DoE does not standardize any
  one consumer's execution mechanics (e.g. Cockpit's `shell:false` arg-vector posture is cockpit's own
  detail), only the shape that lets a consumer implement degrade-to-inert safely.

## Lifecycle enum — DoE-canonical, consumer-projected (DEC-3)

```
prototype -> vertical-slice -> alpha -> shipped -> live-ops -> sunset
```

This is DoE's **canonical, defined set** — the generic signal every repo emits into. It is
deliberately richer than any single consumer's need (e.g. Cockpit's own board only distinguishes
`shipped | pre-launch` today). Consumers **project/collapse** the canonical enum down into their own
layer rather than the standard shrinking to fit one consumer's binary — the mapping direction is
**generic superset → consumer subset**, and that direction is a documented contract property of this
standard, not an ad-hoc per-consumer decision. A consumer adding a new collapse mapping does not
require a DoE schema change; a consumer needing a *new lifecycle state* that doesn't collapse from the
canonical set is a signal the canonical enum itself may need to grow, and that growth is DoE's call.

## Competitor marking — two altitudes, two axes (DEC-7)

`competitors[]` conflates two things a naive reading treats as one; this section pins both the
altitude the field operates at and the two orthogonal axes a single `relationship` value carries.

**Two-altitude model.** Per-repo competitor marking — the human-curated `competitors[]` array in
`state/strategic/self-description.yaml` — is **repo-owned source-of-truth**: this standard, and this
repo (DoE), own the shape and the ratification ceremony. An **org-wide or cross-company rollup** —
resolving a repo's raw competitor mark into a canonical cross-fleet competitor identity
(`competitor_uid`), deduplicating "Repo A calls it X, Repo B calls it Y" across the whole fleet — is a
different altitude entirely, and is **explicitly out of scope for a single repo's schema**. A device
running DoE's coordinator and a human PM pairing is not guaranteed to belong to a single company; the
per-repo artifact cannot assume org-wide context it may not have. That rollup altitude belongs to
Example-store-repo/cockpit (and, downstream, example-market-data-repo's `competitor_uid` resolution — see
`docs/competitive-intel-enablement-initiative.md § Fleet convention`). See DR-057 for the ratified
boundary this subsection encodes.

**Two orthogonal axes.** `relationship` conflates two questions a reader might assume are one:

- **Competitive stance** — is this other repo/product something we're competing against, alongside,
  or reaching toward? Values: `competitor`, `peer`, `aspirational-target`.
- **Lineage/genealogy** — what is this other repo/product's structural relationship to *this* repo's
  own history or design ancestry? Values: `complement`, `prior-art`, `superseded-by`, `supersedes`.

A `relationship` value is drawn from exactly one of these two axes, never both — the enum is a single
flat set of 7 values, but a reader (and any consumer projecting the field) must know which axis a
given value belongs to, because only one axis is stance-shaped and consumer-projectable.

**Cockpit projection — total mapping, 3-of-7 project.** The worked example for how a fleet consumer
(cockpit's `competitor-summary.category`) projects the DoE-canonical `relationship` enum lives here,
not in the schema — the schema stays generic per DEC-3's schema-generic / wiki-named split (see
Chunk C1 of the source plan). This is a **total** mapping: every one of the 7 `relationship` values has
a defined outcome, even where that outcome is "does not project."

| source `relationship` | cockpit `competitor-summary.category` |
|---|---|
| `competitor` | `competitor` |
| `peer` | `peer` |
| `aspirational-target` | `aspirational_target` |
| `complement` | NOT PROJECTED (filtered — lineage, self-description-only) |
| `prior-art` | NOT PROJECTED (filtered — lineage, self-description-only) |
| `superseded-by` | NOT PROJECTED (filtered — lineage, self-description-only) |
| `supersedes` | NOT PROJECTED (filtered — lineage, self-description-only) |

Only the 3 stance values project to a cockpit `competitor-summary` row; the 4 lineage values are
self-description-only and **never** surface as a competitor-summary row. Concretely: this repo's own
dogfood mark of `superpowers` as `prior-art` (see this standard's own `self-description.yaml`) does
**not** surface on any competitor-summary dashboard — it is lineage, not stance, and the filter is
correct behavior, not a gap. This is a ratified EM decision encoded here as the standard's read
contract, not an open fork left for each consumer to resolve independently — a consumer collapsing
`prior-art` into `competitor` (or any other stance bucket) would be non-conformant.

**Total is not onto.** Cockpit `category` carries a `first_party` member (DR-192) that no
`relationship` value projects to. That vacancy is the two-altitude model working: a repo marks its
stance toward *others*, never itself, and org-wide "this entity is ours" identity is out of scope
for a per-repo artifact (DR-057). Restoring symmetry by adding an own-product `relationship` value
re-imports the altitude this standard ejected. The cockpit enum may grow members this table cannot
source; totality forbids only the reverse — a `relationship` value with no outcome. Discharged
mechanically: `relationship-out-of-enum.json` fails any value outside the 7, so an 8th lands red.

**Design-as-offers on the PM-facing surface.** The mint and nudge prompts that ask a human to ratify a
`competitors[]` entry (the refresh ceremony's stance-vs-lineage question) apply the same
design-as-offers posture used for agent-facing tooling (→ global `~/.claude/CLAUDE.md § Implementation
Standards — Extensions`): lead with the better categorization ("did you mean *lineage* — prior-art?"),
not a validation nag. This is a third design-as-offers surface beyond that doctrine's originally-named
agent-facing examples — the PM answering a ratification prompt gets the same lead-with-the-alternative
treatment an agent gets mid-work.

## Lifecycle hooks — repo-setup and workweek-complete
<!-- src: memo03-010 -->

DoE owns two lifecycle touch-points for `state/strategic/self-description.yaml`, both PM-authorized
and both **advisory, not hard gates**:

- **`/repo-setup`** mints a **born-compliant skeleton** — a schema-conformant instance with
  placeholder/empty content — at repo creation time. This is not a hard gate: a repo can proceed
  without a human filling in the skeleton immediately. The gate tightens only at the curation
  ceremony (the `strategic-self-description-refresh` skill), not at mint time.
- **`/workweek-complete`** runs a **presence + staleness check** — does the file exist, and has it
  been ratified recently enough — and surfaces the result as an advisory nudge (discovery-surface
  mention), the same nudge posture DEC-6 already established for the refresh skill itself (see
  § Curated-vs-generated partition above). It does not block the weekly ceremony.

Both design deltas exist because the schema-freeze signal (Chunk C1 landing) gates when downstream
consumers can safely read the artifact — until C1 lands, minting a skeleton eagerly and treating
absence as a hard failure would fire before the schema is stable. The cockpit graduation path (moving
this from an cockpit-proposed convention to a DoE-owned standard with its own lifecycle hooks) is the
throughline connecting `/repo-setup` and `/workweek-complete` ownership back to the original cockpit
proposal referenced in this doc's Spec backlink.

## Competitor-note editorial honesty
<!-- src: memo03-011 -->

When authoring a `competitors[]` entry's `note` field for an entry with `relationship: prior-art` (or
any relationship implying a positioning claim), prefer a **provenance-honest framing over a
superiority claim**. The concrete worked case: this repo's own `superpowers` entry is marked
`prior-art` — a philosophy/design-disagreement stance, not a claim that this system is empirically
better. The named anti-pattern is asserting an unearned superiority ("we do X better") when no
adoption or outcome evidence backs it; the corrective framing names the asymmetry directly, e.g.
*"they have a large, established install base; we have no adoption evidence we're better."* This is
an editorial-honesty convention for the `note` field's prose, not a schema constraint — the schema
does not (and should not) validate note content, but any human or `generated`-provenance note-writer
should apply this framing when marking a competitor whose install base or track record exceeds this
repo's own.

## Nudge cadence
<!-- src: plan34-027 -->

The competitor-positioning nudge (§ Design-as-offers above) is not a standalone script — it lives in
`check-competitor-positioning-nudge.py`, which applies a **28-day cooldown** so a repo isn't
re-nudged every ceremony once a mark has been ratified.

## Specialist-leg seam pointers

This plan (and this wiki) covers DoE's producer/schema leg only. Three specialist legs consume the
schema on their own plans, each memo'd separately per the source plan's § Out of scope:

- **rag leg** — makes the artifact queryable: indexing shape, query surface, and provenance
  composition across the harvested per-repo instances. Not built here; rag plans its own leg after
  ratification.
- **claude-klabauter leg** — generates the observable fields this standard's `generated` provenance marker
  describes: version highlights from commit/release history, competitor deltas from
  example-market-data-repo signals, emitted to the per-repo `self-description.draft.yaml` sibling path
  (path + present-triggers-consume trigger confirmed with claude-klabauter,
  `cross-repo/archive/2026-07-11-claude-klabauter-em-strategic-self-description-draft-path-seam.md`; the
  draft's internal field shape is claude-klabauter's own follow-on shape-confirm against this schema, not
  pinned by this plan). Claude-Klabauter never writes the canonical file.
- **cockpit leg** — widens `StrategicViewDto` to carry per-field provenance badges and maps the
  generic artifact (including the lifecycle enum collapse, § Lifecycle enum above) into cockpit's own
  config/DTO layers. Cockpit's own follow-on work, tracked on cockpit's plans.

## Reliability for downstream competitive-identity consumers
<!-- distilled: run 2026-08-06-14h38; source nugget: c5-012 -->

This standard is the intended per-repo source for any consumer that needs a repo's competitive
identity (e.g. an org-rollup competitive dashboard). It is reliable for that purpose because three
properties already documented above compose: the `competitors[]` field is **minted** at
`/repo-setup` as part of the born-compliant skeleton (§ Lifecycle hooks), its staleness is
**nudged** at `/workweek-complete` with a 28-day decline-memory so the same repo is never re-nagged
once ratified recently (§ Execution notes — competitor-marking deliverable), and the 7-value
`relationship` enum's stance-vs-lineage split (§ Competitor marking — two altitudes, two axes)
gives a rollup consumer a total, unambiguous projection to draw from rather than a free-text field
it must interpret. The per-repo-owned / org-rollup-not-ours boundary (DR-057, § Competitor marking
above) is what keeps this repo's `competitors[]` array honest as a *source* rather than a
*rollup* — a fleet-wide competitive-identity consumer reads N per-repo instances rather than
expecting any one of them to already be cross-fleet-deduplicated.

## See also

- `state-placement-law.md § Fleet Producer Contract` — placement doctrine, Tier A/B degradation,
  time-calibration this artifact class inherits.
- `coordinator/schemas/strategic-self-description.schema.json` — canonical schema, fixtures for AC1.
- `coordinator/skills/strategic-self-description-refresh/SKILL.md` — the reconciliation ceremony.
- `docs/wiki/emission-conformance-contract.md § Producer Contract` — the `(owner, repo,
  coordinator_root_path)` join-key tuple `repo_identity` matches.
- `docs/wiki/addon-chunker-categories.md` — unrelated `curated` vocabulary (RAG-embedding category);
  see § Provenance disambiguation above.
