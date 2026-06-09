---
title: Cross-Repo Contract-Field Parity
status: active
kind: doctrine-wiki
created: 2026-06-09
provenance: project-rag EM memo 2026-05-28 (cross-repo/inbox/2026-05-28-cross-repo-contract-parity-pattern-promotion.md), promoted at instance #2 ahead of anticipated Unity-addon instance #3
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

If both repos are *peers* publishing equivalent surfaces (sibling skills, parallel reviewers), use [`sibling-surface-parity-testing`](sibling-surface-parity-testing.md) instead — that doctrine governs symmetric pairs. This wiki governs the *asymmetric* producer/consumer case.

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

### Convention B — Vendored-constant cross-repo identity parity

When both repos must pin the same identity (embedding model + revision, schema version, protocol enum value), the SSOT lives in one repo and the other **vendors a copy**. Drift guard lives producer-side as a parity test.

**Consumer (SSOT) side:**

```python
# core/<module>.py
EMBED_MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
EMBED_MODEL_REVISION = "3c4b60807d71f79b43f3c4363786d9493691f8b1"  # full 40-char SHA, mandatory
```

**Producer side:**

```python
# addon/embed_constants.py — vendored copy
EMBED_MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
EMBED_MODEL_REVISION = "3c4b60807d71f79b43f3c4363786d9493691f8b1"

# addon/tests/test_embed_constant_parity.py
def test_embed_constant_parity():
    from host_module import EMBED_MODEL_NAME as HOST_NAME, EMBED_MODEL_REVISION as HOST_REV
    assert EMBED_MODEL_NAME == HOST_NAME
    assert EMBED_MODEL_REVISION == HOST_REV
```

**Full SHAs only.** Abbreviated prefixes (`"3c4b608"`) are weaker immutability — registries silently resolve them against the current tip of a tag, which can drift when upstream republishes weights. Existing abbreviated pins are migration items; new pins MUST use the full 40-char SHA.

**Why vendor instead of runtime-import?** Runtime cross-repo import recreates exactly the install-time coupling that "each repo is independently deployable" exists to prevent. Vendor-both-sides preserves self-containment; the parity test catches drift the moment either side updates without the other.

**Upgrade discipline.** When upgrading the constant in one repo, upgrade it in the other in the same change set. The producer-side parity test is the mechanical verification — it goes red the instant one side moves without the other.

## Engine-agnostic design checklist

Neither convention should require engine-shaped naming or tooling. Before applying:

- [ ] Consumer's published surface enumerates **generic** field/identity names — no engine-specific vocabulary embedded in the contract.
- [ ] Producer's assertion is a pure import + comparison — no consumer-side hook, hookspec, or runtime registration.
- [ ] Drift-guard test lives in the **producer's** test suite — consumer stays test-free of per-producer assertions.
- [ ] Constants use the full identifying form (full SHA, full enum value) — no abbreviated prefixes that can resolve drift-silently.
- [ ] On change: both repos move in the same change set; parity test is the gate.

## Worked reference instances

### Instance 1 — `project-rag` chunk-metadata consumed-fields contract (Convention A, 2026-05-28)

- **Consumer:** `project-rag` host publishes `HOST_CONSUMED_ROW_METADATA_FIELDS: frozenset[str]` at `indexer/embed.py` enumerating the 29 chroma per-row metadata fields it reads at query/blend/rank/dedup/display time. Per-field `file:line` provenance recorded alongside.
- **Producer:** `project-rag-ue-addon` checks `HOST_CONSUMED_ROW_METADATA_FIELDS` before dropping or renaming a stamped field. Worked case: dropped `workspace` (not in consumed set) and retained `ue_version` as canonical, with an addon-side parity test asserting the two keys agreed during the transition window.
- **Full source:** `X:/project-rag/docs/wiki/addon-protocol.md § Cross-repo parity conventions § Convention A`.

### Instance 2 — Embedding model identity parity (Convention B, 2026-05-28)

- **Consumer (SSOT):** `project-rag` carries `EMBED_MODEL_NAME` and `EMBED_MODEL_REVISION` at `core/embed.py`, full 40-char SHA.
- **Producer:** `project-rag-ue-addon` vendors its own copy of the same constants; `tests/test_embed_constant_parity.py` imports the live host value and asserts equality against the vendored copy. Convergence to the full 40-char SHA on 2026-05-28 landed in the same change set on both repos.
- **Full source:** `X:/project-rag/docs/wiki/addon-protocol.md § Cross-repo parity conventions § Convention B`.

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

## See also

- [`cross-repo-communication`](cross-repo-communication.md) — the broader cross-repo communication doctrine; this wiki is the contract-field instance of it.
- [`sibling-surface-parity-testing`](sibling-surface-parity-testing.md) — symmetric peer parity (sibling skills, parallel reviewers). This wiki covers asymmetric producer/consumer.
- [`cross-repo-contract-test-discipline`](cross-repo-contract-test-discipline.md) — discipline for contract tests that skip-vs-run. Convention A's producer-side assertion needs a CI lane that actually runs it.
- [`parity-audit-doctrine`](parity-audit-doctrine.md) — plugin-migration audit; complementary to this wiki but governs the move-event, not the steady-state contract.
- [`named-contracts-vs-incidental-flags`](named-contracts-vs-incidental-flags.md) — when to name a contract at all.
- Provenance: `X:/project-rag/docs/wiki/addon-protocol.md § Cross-repo parity conventions`, `X:/project-rag/docs/plans/2026-05-28-addon-protocol-parity-conventions.md`.
