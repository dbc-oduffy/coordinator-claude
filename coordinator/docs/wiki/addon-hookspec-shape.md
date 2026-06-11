---
title: Addon hookspec shape — declarative-once, not query-per-call
created: 2026-05-16
status: active
spec_backlink: tasks/coordination/2026-05-16-cross-repo-hookspec-collision.md
relates_to:
  - docs/wiki/addon-protocol.md
  - docs/wiki/host-vs-addons.md
  - docs/wiki/chunker-registry.md
  - docs/wiki/capability-dispatch.md
distilled_from:
  - docs/plans/2026-05-16-multi-source-daemon-and-source-kwarg.md (C7, restructured)
  - docs/plans/2026-05-16-project-rag-read-side-mcp-and-engine-corpus-recovery-bugs.md (C6 deprecation path)
  - inter-team coordination 2026-05-16 (project-rag-ue-addon EM, project-rag EMs ×2)
---

<!-- Imported from X:/project-rag at SHA d376cb01 on 2026-05-19. Inherited substrate; canonical lineage now in Claude Central. Origin: project-rag/docs/... — see CLAUDE.local.md "Sibling repos" for layout. -->

<!-- RAG-bait: doctrine wiki for addon hookspec authoring. Read before proposing a new project_rag_register_* or project_rag_declare_* hookspec. -->

# Addon hookspec shape — declarative-once, not query-per-call

The pattern for authoring addon hookspecs in project-rag. Converged 2026-05-16 across three EMs (project-rag-ue-addon, multi-source-daemon plan author, read-side recovery plan author) after a real collision between two simultaneously-proposed hookspecs for the same concern.

**TL;DR:** addon hookspecs are **declarative registries**, not **per-call queries**. They return rich dataclasses (not `list[str]`). When a new concern looks adjacent to an existing hookspec, amend the existing contract before authoring a parallel one.

## The rule

> A hookspec is the right shape when it answers a question the addon can answer once at registration time. If the answer varies per call, the per-call surface is `current_*_context()` ContextVar plumbing, not a new hookspec.

Concrete test before authoring `project_rag_register_X` or `project_rag_declare_X`:

1. **Is the answer the same for the same addon across a session?** → declarative hookspec (`register_*`).
2. **Does the answer vary with per-call context (cwd, user, session)?** → ContextVar plumbing through an existing surface; NOT a new hookspec.
3. **Is the answer rich (multiple fields the host actually consumes)?** → return a dataclass façade in `core/addon_dataclasses.py`, not `list[str]`.
4. **Does an existing hookspec already cover this concern?** → amend its façade (add a field), don't author a parallel hookspec.

## What this rules out

| Shape | Verdict | Why |
|---|---|---|
| `register_corpus_provider() → list[CorpusBand]` | ✅ canonical | Declarative, rich façade, one hookspec for "addons declare what corpora they ship." |
| `declare_kind_sources(kind, engine_version) → list[str]` | ❌ rejected | Query-style. Caller passes context the host already has (`current_project_context()`); output strips information the host needs (authority pairs, default weight). Forces a second hookspec for the same concern. |
| `register_chunker() → AddonChunkerSpec` (with metadata fields added over time) | ✅ canonical precedent | Existing v6 hookspec. Multi-source-daemon's chunker-dispatch plan extends this with additive metadata fields — same pattern as adding `CorpusBand.kind`. No new hookspec needed for an adjacent concern. |
| `register_X() → list[str]` for any X | ❌ smell | If the host only needs a list of names, the concern is probably a config setting or a ContextVar surface, not a hookspec. If the host needs structured data, return the dataclass. |
| Two hookspecs covering the same concern at different abstraction levels | ❌ rejected | Future bug class: which is authoritative when both fire, divergent tests, double protocol-version-bump risk. Amend the existing contract. |

## How to amend an existing contract

When a new concern looks like it needs a new hookspec but an existing one is adjacent:

1. **Identify the existing contract.** Grep `core/addon_hookspecs.py` for the closest match.
2. **Add a field to the existing dataclass façade** (`core/addon_dataclasses.py`).
3. **Bump `ADDON_PROTOCOL_VERSION`** if the new field is non-optional, OR document as additive (no bump) if optional with a sensible default. The bump-or-not rule is in [[addon-protocol]].
4. **Update the hookspec docstring** to describe the new field.
5. **Update all known addon hookimpls** to populate the new field (or default it). The host iterates contributions at boot — silent stale impls are a footgun.

## Why this matters — the 2026-05-16 convergence story

On 2026-05-16, two project-rag plans authored on the same day proposed adjacent hookspecs:

- **ue-addon's D-5 memo** ratified `project_rag_register_corpus_provider() → list[CorpusBand]` where `CorpusBand = {band_name, authority_pairs, default_weight}`. Declarative; rich.
- **multi-source-daemon plan's C7** proposed `project_rag_declare_kind_sources(kind, engine_version) → list[str]`. Query-style; bare.

Both were trying to solve "addon declares which corpora are implicitly available for a given session kind." The ue-addon EM flagged the collision; both EMs converged independently on "D-5 wins on merits":

1. **Already ratified cross-repo.** Naming + shape decision was made; C7 was the latecomer.
2. **Declarative > query for static metadata.** Engine corpus mappings rarely change per-call. Per-call dispatch is wasted work compared to iterate-registered-bands-once.
3. **Rich output > bare list.** `CorpusBand` carries `authority_pairs` and `default_weight` — what the reranker actually needs. `list[str]` strips them.
4. **Two hookspecs for the same concern = future bugs.** Divergent tests, double protocol-version-bumps, ambiguous-authority cases.
5. **Filtering by `kind` was the apparent gap.** Solution: one-line amendment to `CorpusBand` (add `kind: str | None`), not a second hookspec.

**Convergence-as-confidence:** two independent EMs reaching the same conclusion from different problem framings is the [[convergence-as-confidence]] pattern. Treat as high-confidence cross-repo signal.

**Empirical validation 2026-05-16 (post-the Staff Engineer review).** The chunker-dispatch plan `docs/plans/2026-05-16-targeted-chunker-dispatch-doctrine.md` made it through the Staff Engineer review (NEEDS-CHANGES minor, 11 findings + 7 OQ resolutions) with **zero findings against the hookspec-shape decision** (additive metadata on the existing `project_rag_register_chunker` hookspec rather than authoring a new one). OQ-2 ("does adding a load-bearing default-valued field warrant an `ADDON_PROTOCOL_VERSION` bump?") resolved NO BUMP — defaulted-additive remains the rule for new fields that change dispatch behavior only when an opt-in addon populates them. The pattern survived contact with adversarial review.

## Sibling rule — registry surfaces follow the same polarity

The declarative-vs-query rule for hookspecs has a sibling rule for the runtime registries those hookspecs feed (`indexer/chunker_registry.py:Registry`, `priming/extractor_registry.py:Registry`, etc.):

1. **Host-side gating, not driver-side.** Dispatch gates (language intersection, substrate-glob matching) live in `Registry.iter()`, not in the addon driver loop. Driver-side gating creates two implementations that drift; the registry is the single source of truth. Validated by OQ-1 in the chunker-dispatch plan (resolved HOST, the Staff Engineer concurred).
2. **Registry stays pure; driver synthesizes skip-reasons.** `Registry.iter()` yields only entries that pass every gate — it does not yield `(entry, skip_reason)` tuples or carry a skip-reason taxonomy. Drivers that need a skip-reason (for `_regen_summary.json` or similar) call a registry-exposed helper (`Registry.substrate_matches(entry, project_root) -> bool`) and synthesize the reason themselves. Symmetric with how the language-gate skip is already handled today (`log.debug` in the registry, driver-side summary in the addon).
3. **Sibling registries mirror `iter()` signatures.** `chunker_registry.py:Registry.iter` and `extractor_registry.py:Registry.iter` are held in lockstep by `tests/test_build_collection_chunker_order.py` (AC-19 parity test). When extending one's signature with a new kwarg, mirror onto the other — even signature-only-with-no-logic (accepted-for-parity, unused at the extractor layer) is correct. Scope-excluding the parity test is the wrong move; it erodes a working tripwire.

These three rules together encode the same polarity the hookspec rule encodes: **a few rich surfaces at the host, not many bare surfaces fragmented across addon drivers.**

## How to use this wiki

- **Plan-authoring time:** if your plan adds a new `project_rag_register_*` or `project_rag_declare_*` hookspec, run the four-step test above. Cite this wiki in the plan's negative-spec section if you considered and rejected a parallel hookspec.
- **Plan-review time:** if a plan proposes a new hookspec, grep `core/addon_hookspecs.py` for adjacent contracts. Surface the candidate-for-amendment as a finding.
- **Cross-repo coordination time:** if you spot a collision (same concern, two proposed hookspecs), invoke this wiki in the inter-team message. The convergence pattern is the resolution mechanism.

## What this doesn't change

- **The host/addon polarity** ([[host-vs-addons]]) — content-agnostic host, domain-specific addons. Unchanged.
- **The discovery mechanism** ([[addon-protocol]] §Discovery) — entry-point-based addon loading. Unchanged.
- **The thin-wrapper graceful-fail seam** ([[thin-wrapper-graceful-fail]]) — addons can be absent without breaking the host. Unchanged.
- **Existing hookspecs.** This wiki is a forward doctrine; do not retroactively rewrite shipped hookspecs unless they re-collide.

## Negative spec

- Do NOT author `project_rag_declare_*` hookspecs as query-style surfaces. If a new declarative hookspec is genuinely needed, name it `project_rag_register_*` to match existing convention.
- Do NOT return `list[str]` from a hookspec when the host consumes structured data. The host is the consumer; bare lists strip its leverage.
- Do NOT add a second hookspec when the first can be amended. The cost of the bump-vs-additive call in [[addon-protocol]] is paid once; the cost of two parallel hookspecs is paid forever.
- Do NOT skip the cross-repo grep when proposing a hookspec for an addon-flavoured concern. Adjacent contracts in sibling repos (`X:/project-rag-ue-addon/...`, `X:/claude-unreal-holodeck/...`) must be checked per [[cross-repo-authority-shift-protocol]].

## Examples

**Good:** chunker-dispatch plan extends `project_rag_register_chunker` with additive metadata fields — same shape as `CorpusBand.kind` amendment. One hookspec, richer dataclass, no protocol-version bump.

**Good:** new producer hookspec `project_rag_register_producer` (Wave 1, 2026-05-14) reused the pre-existing `AddonProducerSpec` façade — additive hookspec, no new façade, no bump (per tc-6 precedent).

**Good:** `Registry.iter(detected_languages=..., project_root=...)` (`indexer/chunker_registry.py`, WS-A 2026-05-09 + targeted-dispatch-doctrine 2026-05-16) — host-side runtime gate, pure (yields entries only), with a separate `substrate_matches()` helper for driver-side skip-reason synthesis. Sibling-rule canonical instance.

**Rejected:** `declare_kind_sources(kind, engine_version) → list[str]` — query-style, bare list, would have created a second corpus-provider surface.

**Rejected (hypothetical):** authoring a new `project_rag_query_chunker_for_file(path)` hookspec for per-file chunker selection. That's per-call context — belongs in ContextVar plumbing through the existing chunker registry, not a new hookspec.

## v8 hookspec catalog additions (2026-05-17, E-NAMED-BANDS)

### `project_rag_register_doctor_probe() → list[FailureCatalogRow]`

Registration hookspec for addon-side failure-catalog contribution. Parallel-call (no firstresult) — host collects all rows from all registered addons at boot and merges them with host-shipped rows (from `docs/wiki/failure-catalog.json`) into a unified catalog sealed for the process lifetime.

**Why a new hookspec and not an amendment to `register_corpus_provider`?**
The concern is orthogonal: `register_corpus_provider` returns `CorpusBand` objects that gate routing and blend behavior. Doctor-probe rows are failure-catalog entries that drive hint text and doctor output — a separate concern with a separate lifecycle (format-at-diagnosis time vs. gate-at-query-time). The four-step test: (1) static at registration time ✅; (2) does not vary per-call ✅; (3) rich dataclass (`FailureCatalogRow`) ✅; (4) no existing hookspec covers this concern ✅. New hookspec is warranted.

**`FailureCatalogRow` fields:** `id`, `failure_mode`, `doctor_probe`, `setup_remediation_template`, `runtime_verdict`, `hint_template`, `contributor`. Every row's `id` must be globally unique across host + all addons; `(failure_mode, runtime_verdict)` pair must also be unique. Boot raises `AddonCatalogIdCollision` / `AddonCatalogModeCollision` / `AddonCatalogInvalidVerdict` on violations.

**Why `FailureCatalogRow` and not `AddonFailureCatalogRow`?**
The type is shared between host (contributing host rows) and addons (contributing addon rows via this hookspec). A strict `Addon*` prefix would imply addon-only scope. The allowlist in `tests/addons/test_facade_discipline.py` carries an explicit exception for this type with rationale.

Spec backlink: `docs/plans/2026-05-17-engine-rag-named-bands.md §1.2, §1.3`.
