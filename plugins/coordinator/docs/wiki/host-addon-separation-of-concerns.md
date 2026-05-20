---
title: Host-addon separation of concerns — umbrella principle
created: 2026-05-19
status: active
spec_backlink: docs/plans/2026-05-19-host-side-engine-corpus-unreachable-fix.md §S-1c
relates_to:
  - docs/wiki/host-vs-addons.md
  - docs/wiki/corpus-band-protocol.md
  - docs/wiki/addon-protocol.md
  - docs/wiki/cross-corpus-class-addon-contract.md
  - docs/wiki/codebase-judgment/typed-surface-over-text-pattern.md
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

<!-- Spec backlink: docs/plans/2026-05-19-host-side-engine-corpus-unreachable-fix.md §S-1c (umbrella-principle wiki) -->

# Host-Addon Separation of Concerns

The umbrella design principle for host-addon protocol surface design in
project-rag.

> **Mechanics wiki.** This wiki states the principle and its tactics at
> plugin-architecture altitude. For the concrete field-by-field contract of the
> canonical CorpusBand instance, see
> [corpus-band-protocol.md](corpus-band-protocol.md).

---

## Principle

Host-addon protocol surfaces are designed so that addons can evolve their
internal implementation, layout, format, backing, and version cadence
**without requiring host-side changes or cross-repo coordination folds**.

Plugin-agnosticism is the goal. Separation of concerns at the protocol seam is
the mechanism.

---

## Why this matters (PM 2026-05-19)

project-rag is content-agnostic code RAG. The host's value is the runtime,
read-path, and retrieval stack — not knowledge of any particular addon's
internals. The host serves TypeScript, C++, Python, Markdown, and more as
first-class consumers. Zero content-specific privilege lives in the host.

Every cross-repo fold the host requires from an addon is a tax on the addon's
ability to evolve. An addon that needs to rename its corpus directory, upgrade
its sqlite schema, or add a new storage tier should be able to do that without
opening a PR in project-rag. Reciprocally, every reach-in the host makes into
addon internals couples future host work to addon coordination — both directions
pay the tax.

The cleanest state: host owns what's universal; addon owns what's
content-specific; the protocol is the contract; neither side reaches across.

**No-UE-special-case rule.** This principle's primary prior-art instance is
the no-UE-special-case rule in
[cross-corpus-class-addon-contract.md §1](cross-corpus-class-addon-contract.md):
"The substrate does NOT privilege any binding. There is no `if engine_kind ==
'unreal':` branch in host dispatch." Structural enforcement of content-agnostic
dispatch is the principle in practice at the corpus-class layer. The no-UE-
special-case rule and this broader separation-of-concerns principle operate at
different altitudes but are mutually reinforcing; both deserve cross-links from
any new host-addon seam doc.

---

## Tactics

These are concrete patterns that implement the principle. This section grows as
new patterns are discovered; each tactic names a canonical instance so future
planners can grep the instance before re-deriving the reasoning.

### Tactic 1 — Opaque-resource resolvers

When the host needs an addon-owned resource that the addon may relocate, rename,
reshape, or version independently (file path, handle, config value), the
protocol surface accepts a **callable resolver** (`Callable[[], T] | None`)
rather than a raw value.

The host invokes the resolver lazily and treats the return value as opaque. This
design makes the "host MUST NOT derive siblings" contract **type-enforced**
rather than doc-enforced: the host only ever sees the returned value, never the
surrounding directory. Doc-enforced contracts decay under refactor; type-enforced
ones don't.

**Prior-art judgment grounding this tactic:**
[codebase-judgment/typed-surface-over-text-pattern.md](codebase-judgment/typed-surface-over-text-pattern.md)
— the callable-resolver shape IS the typed-surface-over-text-pattern judgment
applied to host-addon boundaries. When a plan proposes encoding an
interoperability contract as a "the host walks adjacent files by convention"
pattern, the correct primitive is a resolver field.

**Canonical instance:** `CorpusBand.structural_index_resolver` (this plan,
S-1a, 2026-05-19). Before S-1a, the host attempted to derive the structural
index path from `corpus_root` via an undocumented layout assumption. S-1a
replaced that derivation with an opaque callable; the UE addon now declares the
path explicitly via its own `_make_ue_band()` builder, and the host simply
invokes `band.structural_index_resolver()`. See
[corpus-band-protocol.md §structural_index_resolver](corpus-band-protocol.md)
for the full field contract.

**Future candidate:** `corpus_root_resolver` for Chroma resolution. Today
`corpus_root` is a raw `Path` with a documented host-walkable sub-path
convention. Future work may migrate Chroma to a parallel callable resolver for
full symmetry. See plan Followups in the spec backlink.

**Counter-example:** `corpus_root` today is intentionally value-shaped. The
chroma sub-path convention (engine-kinded: `.../engine-vector-store/<ver>/chroma/`;
universal: `.../corpus-vector-store/<ver>/chroma/`) IS the protocol's documented
surface — the v10 `collection_name`-opacity precedent established this
deliberately. The host walks the sub-tree by specification, not by accident.
This is intentional coupling, not a resolver gap. See Tactic 1 counter-example
reasoning in [corpus-band-protocol.md §corpus_root](corpus-band-protocol.md).

---

### Tactic 2 — Closed protocol surfaces

Addons interact with the host exclusively via hookspecs and protocol dataclasses.
No addon reaches into host module internals; no host module imports addon modules
directly except via the registered hookspec implementations.

**Canonical instance:** `core/addon_hookspecs.py` — every addon contribution
flows through one of the declared hookspec methods. The host iterates
contributions at boot and at each call boundary; no host tool imports
`project_rag_ue_addon` directly.

This boundary is enforced by the pluggy registry: addons that are not installed
are simply absent from the aggregation result, and the host degrades gracefully
(see [thin-wrapper-graceful-fail.md](thin-wrapper-graceful-fail.md)).

---

### Tactic 3 — Additive-only protocol evolution

Protocol versions bump on breaking changes only. New fields default to `None`;
new hookspec methods get no-op default implementations. Addons compiled against
an older protocol version continue to work without coordination.

**Canonical instance:** `ADDON_PROTOCOL_VERSION` discipline in
`core/addon_protocol.py`. Fields like `default_weight`, `required_env`, and
`chunk_filter` were all added as additive-defaulted without version bumps.

The formal boundary analysis for what counts as "additive" is documented in
`addon-protocol.md` as Z-AMEND-1. The carve-out-2 case — "a new defaulted field
that introduces an opt-in dispatch path unreachable without the new field" —
applies to `CorpusBand.structural_index_resolver` (S-1a did not bump the
protocol version). See
[corpus-band-protocol.md §Z-AMEND-1 carve-out 2](corpus-band-protocol.md)
for the qualifying conditions.

---

### Tactic 4 — Addon-declared failure modes

When an addon contributes domain-specific failure shapes, it declares its own
catalog rows rather than asking the host to enumerate the failure. The host
validates contributions for collision and verdict-palette membership; the host
does not encode addon-specific failure semantics.

**Canonical instance:** the `project_rag_register_doctor_probe` hookspec, which
accepts `FailureCatalogRow` entries with prefixed IDs (e.g., `A-F-N` from the
UE addon). The host's failure catalog (`docs/wiki/failure-catalog.json`) is the
canonical palette; addons extend it at registration time, not by editing
host-side JSON directly.

This tactic keeps addon-specific failure message text, hint routing, and
remediation scripts in the addon repo where they belong. When the UE addon wants
to add a new doctor probe or update failure text for an engine-specific error,
it ships an addon release — no host coordination required.

---

### Tactic 5 — *(future patterns land here as they're discovered)*

When a new protocol seam reveals a stable tactic not covered above, add it here.
The decision rule below provides the test for whether a new tactic is warranted.

---

## When this principle DOES NOT apply

Some host-addon coupling is structural and intentional. These are protocol
*participation* surfaces, not reach-ins to fix.

**Envelope verdict palette membership.** Addons that contribute doctor probes
read `core.envelope._VALID_ENVELOPE_VERDICTS` because the host's verdict palette
IS the closed-world surface addons contribute against. An addon using an
unrecognized verdict string would silently corrupt the envelope contract; reading
the palette is correct and expected. This is deliberate coupling — the host
intentionally owns the verdict surface.

**`CorpusBand` as a shared protocol type.** Addons import and instantiate
`CorpusBand` from `core.addon_protocol` because dataclasses are the shared
protocol type. This is the protocol dataclass pattern: both sides own the
dataclass (host defines it; addon instantiates it). The import is a
protocol-participation act, not a reach-in to host internals.

**Hookspec method signatures.** Addons implement hookspec methods whose
signatures are defined in `core/addon_hookspecs.py`. Implementing a hookspec
requires matching the signature — this coupling is intentional and load-bearing.
Signature changes require a protocol version bump precisely because they are
structural coupling.

The distinguishing test: does removing the coupling require the host to lose
information it genuinely needs to operate? If yes, the coupling is structural.
If no, it's a reach-in that the principle applies to.

---

## Decision rule for protocol-surface design

When introducing a new field, method, or seam on a protocol dataclass or
hookspec, apply this decision rule:

> **"Could the addon want to change this in a year without telling the host?"**

- **Yes** → use a resolver / callable / hookspec shape. The addon's
  implementation is volatile; the protocol surface should be stable.
- **No** (the host genuinely consumes it structurally per a documented contract)
  → raw value with documented semantics. The coupling is intentional.
- **Unclear** → default to the addon-evolvable (resolver/callable) shape.
  Loosening later (converting a resolver back to a raw value) is cheaper than
  tightening (converting a raw value to a resolver after dependents have built
  on the raw-value assumption).

This rule is the operationalized form of the Principle above. Run it at
protocol-authoring time — the Z-AMEND-1 boundary analysis in `addon-protocol.md`
is the formal complement for cases near the bump/no-bump boundary.

---

## For prior-art-checker

Plans introducing host-addon protocol surfaces — new `CorpusBand` fields, new
hookspecs, new shared dataclasses, new seams — **must cite this wiki** and apply
the decision rule above before proposing a specific field shape. The prior-art
check question is: "is the proposed shape a raw value where a resolver should
be, or vice versa?"

The canonical instance table (Tactics 1–4 above) provides the grounding for
each pattern. If a proposed shape matches a tactic's canonical instance,
cross-cite the instance rather than re-deriving the reasoning.

---

## Related docs

- [host-vs-addons.md](host-vs-addons.md) — host/addon polarity rule; what lives
  in the host vs. what lives in addons; Wave-2 transition status.
- [corpus-band-protocol.md](corpus-band-protocol.md) — canonical instance of
  the opaque-resource resolver tactic (Tactic 1); field-by-field `CorpusBand`
  contract.
- [addon-protocol.md](addon-protocol.md) — formal versioned contract; hookspec
  table; Z-AMEND-1 boundary analysis; `ADDON_PROTOCOL_VERSION` bump history.
- [cross-corpus-class-addon-contract.md](cross-corpus-class-addon-contract.md)
  — §1: no-UE-special-case rule; binding protocol for multi-class addons.
- [codebase-judgment/typed-surface-over-text-pattern.md](codebase-judgment/typed-surface-over-text-pattern.md)
  — the convergent judgment (3 independent plans) grounding Tactic 1's
  typed-surface-over-text-pattern design.
