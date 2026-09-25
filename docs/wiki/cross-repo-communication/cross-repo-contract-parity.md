---
title: Cross-Repo Contract-Field Parity
status: active
kind: doctrine-wiki
created: 2026-06-09
provenance: project-rag EM memo 2026-05-28, promoted at instance #2 ahead of anticipated Unity-addon instance #3
---

# Cross-Repo Contract-Field Parity

## TL;DR

When a **producer** in one repo and a **consumer** in another repo must agree on the identity or ownership of a contract value (a metadata field, an embedding model identity, a vendored constant), apply this shape:

1. **Consumer publishes only its own surface** — a citable, versioned constant naming what *it* reads. Never enumerates known producers.
2. **Producer asserts against the consumer's published surface** before dropping, renaming, or diverging — mechanical check, not a grep round-trip.
3. **Drift guard lives producer-side.** Divergence is a build/test failure in the producer, not the consumer. The consumer stays addon-agnostic.

The shape is engine-agnostic and plugin-architecture-shaped — it applies to any coordinator-plugin ecosystem with a producer/consumer repo split.

## When this applies

- Two separate repos must agree on the identity of a contract value (field name, model identity, schema version, enum value).
- One repo is structurally a **consumer** (host, library, central plugin) and the other is a **producer** (addon, extension, peer-implementing-the-contract).
- The cost of silent divergence is high: data goes to the wrong vector space, a field gets renamed out from under live readers, a schema drifts and only crashes at runtime.

If both repos are *peers* publishing equivalent surfaces (sibling skills, parallel reviewers), use [`sibling-surface-parity-testing`](./sibling-surface-parity-testing.md) instead — that doctrine governs symmetric pairs. This wiki governs the *asymmetric* producer/consumer case.

## The two conventions

### Convention A — Canonical field ownership + consumer-published consumed-fields contract

The consumer publishes the closed set of fields it reads as a citable, versioned constant. The producer checks that constant before dropping or renaming a field.

**Consumer-side (what the central/host publishes):**

```python
# In a module the producer can import:
HOST_CONSUMED_FIELDS: frozenset[str] = frozenset({
    "field_a",
    "field_b",
    # ... every field the consumer actually reads, with per-field file:line provenance
    # recorded in a sibling doc.
})
```

The constant is the consumer's **READ surface**. It is intentionally distinct from any **VALIDATION surface** the consumer enforces at write time — the two contracts serve different purposes and must not be collapsed into one registry.

**Producer-side (what the addon/extension asserts):**

```python
# In the producer's test suite:
def test_field_drop_safe():
    assert field_to_drop not in HOST_CONSUMED_FIELDS, (
        f"{field_to_drop!r} is in the consumer's consumed-fields contract — "
        "coordinate with the consumer before removing it."
    )
```

**Critical polarity rule.** The consumer enumerates its **own** read surface. It does NOT enumerate known producers, host-side parity tests, or per-addon assertions. That direction reintroduces the "central repo must know about every consumer" coupling this convention exists to retire. The producer is the party that knows whether *it* stamps a given field, and the producer asserts against the consumer's static surface — never the other way round.

#### Schema-validated-channel carve-out

When the consumer reads producer output **through a closed (`additionalProperties: false`), versioned (`schema_version` const) JSON Schema that it validates against**, the schema IS the consumer's published read surface — a parallel Python `frozenset` is redundant and would introduce a dual-registry drift hazard, collapsing the READ and VALIDATION surfaces this wiki's own anti-patterns section forbids merging (see § Anti-patterns, last bullet). The schema is a *stricter* surface than a frozenset: it is citable (`$id`), versioned (`schema_version`, bump-on-shape-change), closed (enumerates the exact admitted field set), and mechanically enforced at the channel boundary by conformance tests. A frozenset is advisory; the schema is validated.

**Carve-out conditions (both must hold):**
1. The consumer validates producer output against the schema (not merely reads it).
2. The schema is closed (`additionalProperties: false`) and versioned (`schema_version` const).

**What "sufficient contract-of-record" means here.** A consumer that cherry-picks a subset of fields and does NOT validate the full schema still owes a `frozenset` naming its actual read subset — the schema over-states what it reads. The carve-out's precise claim is that the closed versioned schema is a sufficient DROP/RENAME coordination surface: any field drop on a closed schema forces a `schema_version` bump, which is a louder drop-detection signal than a `frozenset` assert.

**Producer-side drift guard under the carve-out.** The conventional producer-side assertion (a test checking `field_to_drop not in HOST_CONSUMED_FIELDS`) is replaced by the schema conformance tests: a field drop or rename requires a `schema_version` bump AND causes conformance tests to fail mechanically. For a `source_is_live` producer (e.g. `coordinator-claude` over `~/.claude`, where the consumer cannot pin a release tag), the bump-memo obligation applies: a `schema_version` bump on the producer's closed schema IS the bump-memo trigger to the consuming EM, substituting for the freshness leg the consumer cannot run mechanically. The RAG-bait header at the producer's probe/schema edit sites is the wiki-prescribed edit-site reminder of this obligation (per § `source_is_live` SSOT degrades the producer's freshness leg, under Convention B — the same bump-memo pattern composes here).

*Carve-out ratified by the Director of Engineering (eng-director) review, whoami Apple Silicon inventory plan.*

#### Additive-field additivity has a consumer-shape boundary

Adding an OPTIONAL top-level field to a JSON Schema contract with `additionalProperties: false` is
additive-safe for **field-extracting readers** (they simply never look at the new key — no version bump
needed). It is **NOT safe** for a consumer that vendors its own copy of the schema and full-schema
validates producer output against that closed top-level `additionalProperties: false` — that consumer
REJECTS the new key regardless of any `schema_version` bump on the producer side (a bump only changes
*which* enum value the consumer's version check rejects on; it does not admit the new field). State this
boundary explicitly when claiming a schema addition is "additive" — it is additive for one consumer
shape and breaking for the other, not additive in general.

A clean, reusable companion shape for the migration itself: **optional-with-fallback field design** — add
the new preferred field as optional, and keep the old field as the fallback witness read only when the
new field is absent. This lets producer and consumer migrate independently without a hard cutover.


### Convention B — Vendored-constant cross-repo identity parity

When both repos must pin the same identity (embedding model + revision, schema version, protocol enum value), the SSOT lives in one repo and the other **vendors a copy**. Drift guard lives producer-side as a parity test.

**Consumer (SSOT) side:**

```python
# core/<module>.py
EMBED_MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
EMBED_MODEL_REVISION = "<full-40-char-model-revision-sha>"  # full 40-char SHA, mandatory
```

**Producer side:**

```python
# addon/embed_constants.py — vendored copy
EMBED_MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
EMBED_MODEL_REVISION = "<full-40-char-model-revision-sha>"

# addon/tests/test_embed_constant_parity.py
def test_embed_constant_parity():
    from host_module import EMBED_MODEL_NAME as HOST_NAME, EMBED_MODEL_REVISION as HOST_REV
    assert EMBED_MODEL_NAME == HOST_NAME
    assert EMBED_MODEL_REVISION == HOST_REV
```

**Full SHAs only.** Abbreviated prefixes (a 7-char SHA prefix) are weaker immutability — registries silently resolve them against the current tip of a tag, which can drift when upstream republishes weights. Existing abbreviated pins are migration items; new pins MUST use the full 40-char SHA.

**Why vendor instead of runtime-import?** Runtime cross-repo import recreates exactly the install-time coupling that "each repo is independently deployable" exists to prevent. Vendor-both-sides preserves self-containment; the parity test catches drift the moment either side updates without the other.

**Upgrade discipline.** When upgrading the constant in one repo, upgrade it in the other in the same change set. The producer-side parity test is the mechanical verification — it goes red the instant one side moves without the other.

**`source_is_live` SSOT degrades the producer's freshness leg — compensate with a bump-memo.** A producer-side parity test has two legs: *faithfulness* (the vendored bytes match a pinned SSOT SHA) and *freshness* (the pinned SHA is still the SSOT's tip). When the SSOT repo is **`source_is_live`** (no published/released version the producer can import or pin a tag against — e.g. `coordinator-claude` over `~/.claude`), the freshness leg degrades to **advisory**: the producer pins a *committed snapshot* and cannot mechanically detect that the SSOT has since changed. The faithfulness leg still holds. To close the resulting gap, the SSOT-side editor owes a **bump-memo** to the producer EM on any breaking change to a vendored file — the manual signal that substitutes for the freshness test the producer cannot run. Mark the obligation as RAG-bait at the vendored file's structural boundary (a header note naming the downstream vendor + the bump-memo rule) so the editor sees it at the edit site. This does **not** reintroduce the consumer-enumerates-producers anti-pattern: a passive editorial header is not a maintained drift-guard registry, and it carries no test dependency.


## Engine-agnostic design checklist

Neither convention should require engine-shaped naming or tooling. Before applying:

- [ ] Consumer's published surface enumerates **generic** field/identity names — no engine-specific vocabulary embedded in the contract.
- [ ] Producer's assertion is a pure import + comparison — no consumer-side hook, hookspec, or runtime registration.
- [ ] Drift-guard test lives in the **producer's** test suite — consumer stays test-free of per-producer assertions.
- [ ] Constants use the full identifying form (full SHA, full enum value) — no abbreviated prefixes that can resolve drift-silently.
- [ ] On change: both repos move in the same change set; parity test is the gate.

## Worked reference instances

### Instance 1 — `project-rag` chunk-metadata consumed-fields contract (Convention A)

- **Consumer:** `project-rag` host publishes `HOST_CONSUMED_ROW_METADATA_FIELDS: frozenset[str]` at `indexer/embed.py` enumerating the 29 chroma per-row metadata fields it reads at query/blend/rank/dedup/display time. Per-field `file:line` provenance recorded alongside.
- **Producer:** `project-rag-ue-addon` checks `HOST_CONSUMED_ROW_METADATA_FIELDS` before dropping or renaming a stamped field. Worked case: dropped `workspace` (not in consumed set) and retained `ue_version` as canonical, with an addon-side parity test asserting the two keys agreed during the transition window.
- **Full source:** `project-rag` repo, `docs/wiki/addon-protocol.md § Cross-repo parity conventions § Convention A` (resolve the repo root via `repos.project_rag`).

### Instance 2 — Embedding model identity parity (Convention B)

- **Consumer (SSOT):** `project-rag` carries `EMBED_MODEL_NAME` and `EMBED_MODEL_REVISION` at `core/embed.py`, full 40-char SHA.
- **Producer:** `project-rag-ue-addon` vendors its own copy of the same constants; `tests/test_embed_constant_parity.py` imports the live host value and asserts equality against the vendored copy. Convergence to the full 40-char SHA landed in the same change set on both repos.
- **Full source:** `project-rag` repo, `docs/wiki/addon-protocol.md § Cross-repo parity conventions § Convention B` (resolve the repo root via `repos.project_rag`).

### Instance 4 — Step Zero prereq lib vendored from `coordinator-claude` (Convention B, source_is_live)

- **Consumer (SSOT):** `coordinator-claude` carries `scripts/lib/{prereq_probe.sh, manifest_reader.sh, step_zero_emit.sh}` — a self-sourcing 3-file unit (`prereq_probe.sh` sources the other two). SSOT for the Step Zero install-prereq probe + NDJSON emitter contract.
- **Producer:** `project-rag-ue-addon` vendors all three BYTE-STABLE into `project_rag_ue_addon_scripts/lib/coordinator_prereq/` with DR-PARITY-001 vendor headers + Layer-1 parity tests, pinning the committed snapshot (not chasing live HEAD).
- **`source_is_live` wrinkle:** because `coordinator-claude` is `source_is_live`, the producer's parity *faithfulness* leg is pinned to the vendored SHA's blob but the *freshness* leg is advisory. Compensation: a breaking change to ANY of the three files warrants a **bump-memo to `project-rag-ue-addon-em`**. Recorded as a header note on each of the three SSOT files.
- **Generic-name self-source collision (follow-up memo):** the unit's three files share generic names (`prereq_probe.sh`, `manifest_reader.sh`, `step_zero_emit.sh`) and `prereq_probe.sh` self-sources the other two by name from its own dir. A consumer that vendors them **flat** alongside its own different-purpose `manifest_reader.sh` self-sources the WRONG file — source succeeds, but the expected symbol (`_co_find_python`) is undefined, surfacing downstream as a *misleading* `[WARN] python — No functional Python 3.11+ found`. **Vendoring contract: vendor the unit into a dedicated isolated subdir (e.g. `lib/coordinator_prereq/`), never flat next to same-named consumer libs.** Producer-side defense (the addon's shipped `coordinator_prereq/` subdir) is correct, but the SSOT also carries (a) a "vendor as a unit into an isolated subdir" header directive on `prereq_probe.sh` + `step_zero_emit.sh`, and (b) **detect-then-fail-loud post-source guards** in `prereq_probe.sh` that assert the expected symbol resolved — converting a silent mis-resolution into a self-diagnosing error. The structural guard (b) was chosen over renaming the generic files because `manifest_reader.sh` is a general-purpose lib with independent callers (`setup.sh`, `dep_check.sh`) — renaming it would misdescribe its role AND be a breaking change forcing immediate re-vendor.
- **Live-source consumers are a SECOND consumer class, and a vendor registry cannot see them.** A repo that resolves the SSOT files at runtime out of a coordinator clone — rather than vendoring a byte-stable copy — has no vendor header, no pinned SHA, and no parity test, so it appears nowhere in the vendor records this instance enumerates. `project-rag` is exactly that shape: it sourced `manifest_reader.sh` and `prereq_probe.sh` live through `resolve-coordinator-clone` from `install-project-rag-plugin.sh`. When the bash-kill campaign computed its owed-bump-memo list from vendor records, project-rag was *structurally unable to appear on it* and was not notified; both of its seams broke silently (one warn-and-skip, one hard prerequisite-gate failure). The two classes fail in opposite directions and that asymmetry is the whole point: a **vendored** consumer survives deletion of the SSOT (it holds its own copy) and needs the memo only to know its copy is now orphaned, whereas a **live-source** consumer breaks the moment the file is deleted and needs the memo *before* the delete lands. So enumerating owed bump-memos means enumerating BOTH — grep the fleet for live resolution of the file (`resolve-coordinator-clone` call sites and hardcoded `scripts/lib/` / `lib/` path fragments) in addition to reading the vendor records. Deleting a `source_is_live` SSOT file without that second sweep is how a consumer discovers the break by tripping over it days later, with no CI signal.
- **Known bump-memo recipients for this unit:** `project-rag-ue-addon-em` (vendored, isolated subdir), `deep-research-em` (vendored), and `project-rag-em` (**live-source**, added after the omission above).

### Anticipated Instance 3 — Unity addon

When the Unity addon lands as a peer producer to the UE addon, both conventions apply unchanged: it imports `HOST_CONSUMED_ROW_METADATA_FIELDS` for Convention A, and vendors `EMBED_MODEL_*` with a producer-side parity test for Convention B. Promoting this doctrine at instance #2 (rather than waiting for instance #3 to force it) is the explicit reason this wiki exists — see provenance frontmatter.

## Plan-time prior-art trigger

When a plan introduces or modifies a producer/consumer contract field across separate repos — a new addon stamping metadata the host reads, a model/revision pin, a schema-version constant, a protocol enum — surface this wiki via `coordinator:plan` prior-art check. Specifically:

- New producer/consumer field added → Convention A applies; ensure the consumer's read surface is published as a citable constant before the producer ships.
- Identity constant pinned in two repos → Convention B applies; vendor both sides, producer-side parity test, full identifier.
- "Does the consumer read field X?" grep round-trip appears in the plan → that is the smell Convention A retires. Cite the consumed-fields constant instead.

## Anti-patterns

- **Consumer enumerates known producers.** Recreates the coupling. The consumer enumerates *its own read surface*; producers self-describe and assert.
- **Drift guard lives consumer-side.** A consumer-side test asserting each producer's vendored constant matches the SSOT means the consumer must know about every producer. Drift guard belongs in the producer's test suite, asserting against the SSOT.
- **Abbreviated SHAs / partial identifiers.** Silent registry resolution against moving tags. Always full identifier.
- **Runtime cross-repo import to "share" the constant.** Reintroduces install-time coupling. Vendor and test, don't import.
- **Collapsing READ surface and VALIDATION surface into one constant.** They serve different contracts. Document both; cross-reference; don't merge.

## Cross-repo hookspec compat fields can be range OR list — read the host validator before picking shape

*Source: project-rag-ue-addon. [universal]*

**Rule.** A cross-repo schema field like `requires_protocol_version` can be a *list-membership* contract (`host in addon_required`) or a *range* contract (`pv_min <= host <= pv_max`). Local parity tests can encode the WRONG semantics; the host's validator is the authoritative source. Before changing a cross-repo schema-shaped field, grep the *receiver's* validator — not just the local test.

*Case.* When host-EM asked to widen `requires_protocol_version` from `[19, 19]`, the addon EM assumed list-membership because the addon's own parity test (`test_addon_protocol_version_parity`) used `host in addon_required`. Widened to `[19, 20, 21]` to satisfy that membership check — host then rejected with "must be int or [int, int]" because the host validator at `core/addon_manifest.py:270-298` is a `[min, max]` range check. The local parity test was just wrong; fixed by widening to `[19, 21]` (correct range) AND correcting the parity test to range semantics. (case: project-rag-ue-addon)

**Discipline.** When local-test semantics disagree with the receiver's validator, the local test is the bug. Cross-repo schema fields must be verified at the *receiver's* assertion site — adjacent to Convention A's polarity rule (the consumer publishes its own surface; the producer asserts against it, not against a copy that may have drifted).

**Strict-inclusive upper-bound pins turn an additive bump into a forced re-release — check for a host-only home first.** Under a strict-inclusive gate (`pv_min <= host <= pv_max`), an *additive* bump on a HOST-consumed field falls OUT of every consumer that pinned `[lo, current]`, forcing each to widen-and-re-release for zero benefit — additive is not free under a strict upper bound. Before bumping the shared protocol version for what is actually a host-only concern, ask whether the field can stay host-internal (a presentation-only façade field no consumer reads needs no shared bump at all). The full discriminator — shared-contract change (coordinate reader-first) vs. host-owned façade field (host-side-only) — lives in [`cross-repo-communication.md`](../cross-repo-communication.md) § Host-owned façade fields don't need the shared bump. (Source: project-rag.)

## Wire-field op-classification is an allowlist, not a consumer heuristic

*Source: the doctrine repo. [universal]*

When a **consumer** must decide which producer ops carry a producer-routed envelope field (a `_origin_worktree`, a scope tag, any state-scoped wire attribute), classify with an **allowlist of confirmed state-scoped ops** — never an `all-minus-X` denylist. The allowlist is safe under BOTH failure hypotheses:

- **Engine ignores unknown fields** — a forgotten new op simply omits the field (fail-safe).
- **Engine rejects unknown fields** — a forgotten scoped op fails loud-and-visible, surfacing the gap immediately.

A denylist is safe only under the first hypothesis; under the second it ships a silent break the moment a new op is added. Worse, a plan that assumes BOTH "send because ignored" and "omit because rejected" on the same op class is self-contradicted — pick one, and confirm the producer's ignore-vs-reject behavior before shipping rather than re-deriving it heuristically.

**Polarity: the classification is producer-owned.** The confirmed-scoped set is the producer's AC table (its `_OP_KEY_SCOPE` / `WORKTREE_SCOPED_OPS` surface — see § Resolved instance — op-keying table parity above). The consumer asserts a SUBSET relation against that surface; it does not invent its own scope map. This is the same polarity as Convention A — the consumer never enumerates producer internals, it consumes the producer's published classification.

## Anchor a landed contract block on the WRITER + convention, not the reader's scaffolded placeholder

*Source: the doctrine repo. [universal]*

When landing a cross-repo contract/schema block, anchor every field decision — casing, key names, types, identity-field qualification — on **the producer contract's own conventions plus the actual WRITER's emitted form**, NOT on the reader's local generator, panel, or fixture artifacts, even when the reader scaffolded ahead and those artifacts *look* authoritative. A consumer's disclaimed-as-non-contract types (a reader's TypeScript backlog-history panel, say) are context, never wire authority: the writer emits against whatever the contract declares, so the contract-plane owner just makes the better convention-consistent choice and the reader conforms.

**Empirical:** three initial contract-field decisions (camelCase key, bare repo id, `IsoDate` type) were driven by an cockpit reader's scaffolded placeholder types and were all wrong — the producer (the engine repo) emits against the contract, so the correct anchor was the producer convention + the writer's emitted shape. Read the reader's shape for context; never treat it as the wire authority. This composes with § Cross-repo hookspec compat fields — verify at the *receiver's* assertion site — both say: the authoritative shape lives at the emitting/validating end, not in a local copy that may have drifted.

## A shared-vocabulary contract change is atomic across ALL consumers — the validator/reader is a consumer too

*Source: the doctrine repo. [universal]*

When a shared contract's field **vocabulary** changes (e.g. an override block's keys `{mechanism, name}` → `{flag, env}`), every consumer must sync in the same atomic change set: the schema, the data instances, AND the validator/reader that hardcodes the field names. Calling a downstream reader "no change needed" is a trap — a validator that still keys on the old `.override.mechanism` silently fails a compliant manifest even though the schema and data both moved. Grep **every** consumer of the changed field before declaring scope; the validator/reader is a first-class consumer, not infrastructure exempt from the rename.

This extends Convention B's upgrade discipline ("both repos move in the same change set") to the intra-contract case: the atomic set is not just producer + consumer repos, it is every code path that names the field — including the enforcement surface. A mid-execution vocabulary amendment that updates the schema and instances but leaves the validator on the old keys is the recurring shape.

## An equality gate asserts agreement, never correctness — a vocabulary rule and a parity rule do not compose into coverage

*Source: the doctrine repo and the engine repo. [universal]*

**Rule.** Every parity gate in this wiki — Convention B's vendored-constant check, a byte-for-byte
drift check, a committed-vs-fresh-regen check — asserts two copies **agree**, never that the agreed
content is **right**. A rule governing the *content* (a naming convention, a layering rule about
what a public string may name) **stacks** with the parity rule; it does not compose into coverage.
A defect present in both copies sits where each side's gate is individually green.


**The corollary is sharper than the rule: a red parity gate names *which two things disagree*,
never *which one is wrong*.** In the same incident the doctrine repo's generated
`artifact-shape-contract.schema.json` had already been corrected while the `coordinator/schemas/`
sources it generates from had not, so `test_artifact_shape_contract_freshness` was **red at HEAD**.
It reads as "the generated file is stale" — and the reflex fix, rerun the generator and commit,
would have re-propagated the defect and turned the gate green. The correct fix was upstream.
Picking the wrong side of a parity failure is a silent regression the gate itself then certifies.

**Discipline.**

- **Fix content defects at the SSOT, never in a vendored copy** — a local rename is a divergence
  the drift check will correctly reject. Route it via `cross-repo-memo`, as the engine repo did.
- **On a parity failure, establish which side is authoritative before choosing a direction.** For a
  generated artifact the sources are authoritative; green is not the goal.
- **A sender's sweep covers only what the sender vendors.** the engine repo cited the one file it copies;
  the string had six live sites in the doctrine repo's SSOT. An example propagates by copy-paste across sibling
  schemas faster than any of them get re-read — sweep the whole SSOT, don't fix only the cited locus.
- **Historical records are out of scope** — review-trail diffs, recovery patches, and plan sidecars
  keep the old string deliberately.

No mechanism is proposed for the gap; two incidents do not justify one. This exists so a third
lands on a named pattern instead of being rediscovered.

**Case — an inbound drift memo needs the same authority check as a red gate.** A memo reporting
drift on your surface can be reporting the *sender's* own stale vendored pin rather than a defect
of yours — the memo-shaped version of the same question above. Before re-reading your own surface
for the reported defect, establish which side pinned what: if the sender's copy is the one that
went stale, the fix is on their pin, not on your surface.

**Case — a red parity gate names a version gap, never which side moved.** A vendored-schema
parity gate's message is conventionally phrased as though the sibling always lags ("re-vendor
into your tree, or hold the bump") — but the gate fires identically when the sibling has moved
AHEAD, having already spent a version number on genuinely different content. Reading only the
gate's message and bumping to the next number risks making one version string mean two different
property sets across two repos. Read both files before bumping, not just the gate's text:
sibling-behind means bump-and-ask; sibling-ahead means adopt the sibling's already-spent versions
first, then bump past the highest one actually in use.

## Cross-boundary validation splits by fixability-at-source — sender rejects, receiver absorbs-and-warns

*Source: the doctrine repo and the engine repo. [universal]*

When two repos validate the same cross-boundary artifact (a memo, a manifest, any
producer-emitted payload a consumer also checks), the two validators should not run the same
policy. **The sender-side validator rejects** — the sender can fix the defect before anything
ships, so a violation there is an authoring failure, gated hard. **The receiver-side validator
absorbs and warns** — by the time a malformed artifact reaches the receiver, the receiver cannot
fix the sender's defect, so rejecting outright means blocking the receiver's own pipeline on
someone else's bug; absorbing it while logging loudly keeps the receiver live and still surfaces
the problem. The discriminator is fixability-at-source, not severity: the identical defect class
gets the strict gate on the side that authored it and the lenient one on the side that only
consumes it.

This generalizes past the memo-cap field it was ratified on — any cross-boundary validation pair
should ask "which side can actually fix this" before choosing reject-vs-absorb, rather than
mirroring one policy on both ends of the seam.

## A shared key name crossing a repo seam must name its axis, not just its value

*Source: the doctrine repo. [universal]*

A key shared across a repo seam can pass every check a normal contract review runs — type
matches, required-ness matches, glob shape matches — and still be silently inert end to end,
because review never asked what the token *denotes*. Two repos froze a two-key sidecar contract
where both sides named a key `platform`, but each meant a different axis: one meant pipeline
modality (web/repo/structured/notebooklm), the other meant evidence venue (youtube/gdelt/rss/x).
Both facts are real, both readings are natural, and neither contract said which axis the key was
on — so it landed green on both sides. The producer emitted, the consumer's lander returned exit
0, and every landed record then died at the classification step: all four producer tokens
unmappable against the consumer's own vocabulary. Not one byte flowed correctly or incorrectly —
the seam was inert, and neither side's own test suite could have caught it, because each owned
only one half and each half was internally consistent on its own.

**Discipline.** State each cross-seam field's AXIS in the contract, not just its type and an
example value — "the venue the evidence came from, vocabulary owned by X" beats "non-blank
string, e.g. web." An enumerated vocabulary is the tell: if a field takes a closed set of tokens,
the contract must name whose set it is and where it's defined, or two repos will each supply
their own. Prefer a name that resists a second reading (`pipeline` over `platform` when the value
is a pipeline modality). Where producer and consumer vocabularies genuinely differ, have the
consumer supply its own token caller-side rather than reading the producer's. Treat this class as
unreachable by review alone — a passing contract review checks shape, never meaning — and schedule
one real end-to-end run across the seam before declaring the contract proven.

## A schema the fleet shares is authored in `coordinator/schemas/` and vendored outward — never originated in a consumer

*Source: the doctrine repo and the engine repo. [universal]*

**Rule.** A schema of record that more than one repo validates against is authored canonically in
the doctrine repo's `coordinator/schemas/`; consumers vendor the generated output (the engine repo into
`coordinator_core/frontmatter/schemas/`) and never hand-edit their copy. A shared schema
first authored inside a consumer makes that consumer the source of record for a contract it does
not own, which inverts every parity gate on this page: the drift check still passes, and the side
it certifies is the wrong one. This holds for a schema that does not exist yet as strongly as for
one already vendored — homing is decided before the first field, not retrofitted after.

**Corollary — a not-yet-existing schema still has a home, and asking where is cheap.** The
`spine.schema.json` case: the engine repo needed one, found it absent on both sides, and asked
where it must live rather than authoring it locally and letting the vendoring direction be
settled by whoever typed first. That is the correct move, and the answer is always this section.
Field shape is a separate conversation from homing; pinning the home does not commit either side
to a shape.

**Widening a schema's `applies_to` is a MINOR bump with a lockstep set.** No document valid before
becomes invalid, so it is additive — but every consumer that decides *which files ARE* records of
that class by its own hardcoded glob must widen in the same change set, or the newly-admitted
documents validate while staying invisible to that consumer. Those globs live on both sides of the
vendoring boundary (in the engine repo, `coordinator_core/ops/records_query.py`'s `_TYPE_TO_GLOB` and the
registry-sync golden), so re-vendoring the schema alone does not discharge the widen.

## A cross-plane contract whose only caller lives in the other repo has no test on either side

*Source: the doctrine repo and the engine repo. [universal]*

**Rule.** When a producer's contract has exactly one caller and that caller lives in a *different*
repo, neither side's own test suite can assert the join — asserting it means reaching into the
other repo's tree, which neither side's test runner does. Each half can be green in isolation
while the join between them has never run.

**Case.** A cross-plane contract (a plan-status ladder) shipped green on both planes and had never
actually run. The engine gated on a kwarg whose documented sole caller was the doctrine repo's skill — and that
skill never passed it. The engine's own tests passed: the gate behaves correctly for every input its
suite exercises, including the default it falls back to when the kwarg is absent. The doctrine repo's own tests
passed: the skill does everything its own suite checks. Neither suite exercises the seam, because
the seam is "does the doctrine repo's skill actually pass the engine's kwarg," and that assertion has no home on
either side. This survived a full plan review and a delivery memo exchange between the two repos —
both processes checked their own half against its own spec, and the spec on each side was
satisfied.

**Discipline.**
- When a plan proposes a producer/consumer split across repos, name the consumer callsite in the
  *same memo* that asks for the producer change — not as a follow-up, in the memo that requests
  the producer surface at all. A producer built without its caller named has nowhere for the join
  to be asserted from either side.
- State explicitly who asserts the join. If the answer is "nobody, each side tests its own half,"
  that is the gap this section names, not a resolved design.
- Prefer a default-ON flag over a default-off one for a cross-plane kwarg: a caller that never
  passes it should get the SAFE behavior loudly, not the unsafe behavior silently. A gate that
  silently no-ops when its only caller omits the kwarg is exactly the shape that let a one-producer/
  one-consumer contract ship unexercised.
- A one-producer/one-consumer split across repos is a standing candidate for a joint integration
  test that runs against both repos' current code — not each side's own suite — precisely because
  no other mechanism can assert the join.

## A doc that names a key, glob, or path must name the LAYER it belongs to — the failure mode is a confident reader, not an error

*Source: example-market-data-repo. [universal]*

Two documents in two repos can each correctly describe a shared name — a natural key, a glob
constant, a join field — from its own layer, and each be right, while neither names which layer it
is describing. Read together they look like a contradiction; each reads as a refutation of the
other, when in fact both facts are true at different points in the pipeline. One repo's doc named
the natural key for a shared row "at ingest" as a three-field composite; a sibling repo's doc,
reading a downstream delta module, said the join key was a single field, flatly, with no layer
qualifier. Trusting the second doc's framing over the code led to a near-miss: a proposal to clear
a table as "cheap insurance" against a duplicate-row risk that the actual store schema (checked
directly) showed did not exist — and the proposed "insurance" would have destroyed real tombstone
state the reconcile mechanism already handled correctly.

The same class recurs in the opposite direction just as easily: two files in the same repo can both
reference a named constant that no longer exists anywhere in the tree, because the transport layer
it named was retired and nothing updated the callers' comments — leading a reader to regenerate and
ship artifacts through a path that was never actually consulted downstream, mistaking "verified the
fix" for "delivered the fix."

**Discipline.** When a doc states a key, glob, or path, name the pipeline layer it applies to
("at ingest," "at the delta/join step," "as read by the live producer invocation") — not just the
value. A doc that omits the layer is not wrong, but it reads as universal, and a second doc making
an equally true claim about a different layer will read as contradicting it. Before treating two
docs' claims as opposed, check the code at both layers rather than picking a side from the prose
alone — this composes with § An equality gate asserts agreement, never correctness above: a
plausible-sounding doc disagreement is a "which layer" question to verify, not a fact to reason
from directly.

## See also

- [`cross-repo-communication`](../cross-repo-communication.md) — the broader cross-repo communication doctrine; this wiki is the contract-field instance of it.
- [`sibling-surface-parity-testing`](./sibling-surface-parity-testing.md) — symmetric peer parity (sibling skills, parallel reviewers). This wiki covers asymmetric producer/consumer.
- [`cross-repo-contract-test-discipline`](./cross-repo-contract-test-discipline.md) — discipline for contract tests that skip-vs-run. Convention A's producer-side assertion needs a CI lane that actually runs it.
- [`parity-audit-doctrine`](../reviewer-pipeline/parity-audit-doctrine.md) — plugin-migration audit; complementary to this wiki but governs the move-event, not the steady-state contract.
- [`named-contracts-vs-incidental-flags`](../doctrine-authoring/named-contracts-vs-incidental-flags.md) — when to name a contract at all.
