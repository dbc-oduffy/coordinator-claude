---
provenance:
  - archived_spec: archive/specs/2026-05-07-multi-rag-coexistence-three-repo-split.md
    original_path: docs/plans/2026-05-07-multi-rag-coexistence-three-repo-split.md
    last_verbose_sha: af38275ad09f8ba6d1ef3b988f9c652fe97fe9f6
    distilled: 2026-05-08
  - archived_spec: archive/specs/2026-05-09-migrate-rag-content-to-addon.md
    original_path: docs/plans/2026-05-09-migrate-rag-content-to-addon.md
    last_verbose_sha: 0bbfc5fef008f62972c2d4e23188756b650bd1d4
    distilled: 2026-05-16
  - source: tasks/audit-2026-05-14/SYNTHESIS.md
    note: Gate 1 readiness snapshot (2026-05-14 cross-repo audit)
    distilled: 2026-05-18
  - source: tasks/scratch/artifact-distillation/2026-05-19-pass-27/wiki-drafts/bug-blitz-and-multi-rag-updates.md
    note: Chunks port (2026-05-18) + project-rag plugin layout
    distilled: 2026-05-19
  - source: tasks/scratch/artifact-distillation/2026-05-19-pass-27/wiki-drafts/cross-repo-archaeology-patterns.md
    note: Archaeology campaign patterns (2026-05-18 holodeck-docs sweep)
    distilled: 2026-05-19
---

# Multi-RAG Platform Architecture

> Distilled from the staff-session plan (2026-05-07) + Amendments 1–2, five handoffs, and 26 pass-2 review artifacts.
> Decision records DR-MRAG-001 through DR-MRAG-014 correspond to A1–A14 (unanimous decisions from the staff session).

## Three-Repo Topology

The holodeck ecosystem is split into three repos with clean concern boundaries:

| Repo | Role | Ships |
|------|------|-------|
| **`project-rag-ue-addon`** (formerly `holodeck-corpus`) | Write path — scrapers, extractors, structural-index emitters, release pipeline | Pre-embedding chunks JSONL, never vectors |
| **`project-rag`** (existing) | Read path — multi-source MCP retrieval + serving. Sole embedder owner | Embedding + retrieval MCP server |
| **`claude-unreal-holodeck`** | Execute path — C++ UE plugin, holodeck-control TS server, holodeck-headless Mode B, install orchestration, umbrella Claude Code plugins | UE plugin + install orchestrator |

Data flow: `project-rag-ue-addon` → (chunks JSONL) → `project-rag` ← (MCP) ← `claude-unreal-holodeck`.
The BOM (`holodeck-bom.yaml`) at the core repo root is the cross-repo schema-version contract.

**Cross-repo sequencing rule (DR-MRAG-001):** UE-addon ships first → project-rag second → holodeck reshapes last. Consumer set expands only when the current primary consumer reports a clean bill of health.

**Merge gating (DR-2026-05-14-MRAG-015 — dual-gate):** All three repos stay branch-local until Gate 1 (functional parity with the pre-split monorepo) is satisfied and all three merge simultaneously. Gate 2 (JetBrains gap closure) runs concurrently on migration branches. "Shipped on `origin/main`" doctrine does NOT apply to Gate 1 work — functional parity with the pre-split monorepo is the success metric, explicitly tracked as a PM-sanctioned doctrine exception.

## Gate 1 Readiness Snapshot (2026-05-14 audit)

As of 2026-05-14 cross-repo audit (`tasks/audit-2026-05-14/SYNTHESIS.md`):

**claude-unreal-holodeck:** Structurally complete. Residual: empty `plugin/holodeck-docs/` shell + 3 `__pycache__/*.pyc` fossils; `CLAUDE.md` self-contradiction at lines 42/46 vs 73 (ue-docs-researcher retired vs mentioned); wiki + agents still referencing retired `ue-docs-researcher`/`holodeck-router`.

**project-rag:** NOT at parity. UE substrate leaks:
- `indexer/chunker_registry.py:419-425` — `bp_json` chunker with `domain=["unreal"]` still in core (symmetric migration pending)
- `indexer/_ue_macros_generated.py` — 2093-line UE 5.7.4 macro skiplist in core substrate (should be hookspec-injected from addon)
- `core/ue_ls/` — UE-branded directory (rename candidate: `core/ls_host/`)
- `mcp/preflight.py` — UE preflight body in core
- `core/structural_schema.py:7` — stale provenance pointer to deleted path
- `mcp/tools/live.py:105-119` — UE-specific clangd kind normalization in core

**project-rag-ue-addon:** 216-commit branch-local delta. Only `corpus-v4.0.3-ue5.7` released (pre-split). BP extraction moved but not yet runnable inside addon without holodeck dependency.

## Source Taxonomy — Two-Axis (domain, subtype)

The unified retrieval surface is keyed on two orthogonal axes (Amendment 1, A1-A14 staff session). The single `source` enum (`_VALID_SOURCES`) is retired; `_VALID_DOMAINS` + per-domain `_VALID_SUBTYPES` mapping replaces it.

| `domain` | Coverage |
|---------|---------|
| `project` | The user's own codebase indexed by project-rag |
| `engine` | UE engine — headers, shaders, CVars, build system, anything inside the engine install |
| `official_docs` | Authoritative external docs — UDN, Fab, Epic blog, marketplace |
| `other` | Vendored community content, tutorials, learning resources |

`subtype` is domain-scoped and open for extension via chunker registration:

| `domain` | `subtype` examples |
|---------|-----------------|
| `project` | `code` · `docs` · `tests` · `config` · `plan` · `decision` · `research` |
| `engine` | `cpp_header` · `shader` · `cvars` · `build_system` · `engine_plugin` |
| `official_docs` | `udn` · `fab` · `epic_blog` · `marketplace` |
| `other` | `community` · `vendored` · `tutorial` · `forum` |

**`(other, vendored)` semantic:** when the `other` domain is populated from a project-local folder, it lands in the project collection (not the shared engine collection) with `(other, vendored)` provenance.

**`project` domain subtypes** (Amendment 2 additions):

| Subtype | Covers | Recency-decay profile |
|---------|--------|----------------------|
| `code` | Source files | None |
| `docs` | Wiki, conventions, reference | Mild |
| `tests` | Test files | None |
| `config` | INI, YAML, build files | None |
| `plan` | Time-bound architectural intent (`docs/plans/`) | Mild — active ranks higher than archived |
| `decision` | Ratified decisions / DRs (`docs/decisions/`) | None — decisions are durable |
| `research` | Timestamped research outputs (`docs/research/`) | Steep — "what we found at time T," not "current convention" |

Recency-decay is applied **multiplicatively**: `final_score = rerank_score × recency_decay(published_at, now, half_life_days)`. Per-project BOM override via `recency_decay_overrides: {(domain, subtype): profile}`.

## Four Tool-Surface Primitives

The current seven `mcp__holodeck_docs__*` tools collapse to four (DR-MRAG-013):

| Tool | Args | Default `domain_weights` |
|------|------|--------------------------|
| `query` | `text, domain?, subtype?, path_prefix?, audience?, engine_version?, since_date?, mode?, workspace?, tags?, domain_weights?, limit?` | `{engine: 1.0, official_docs: 0.9, project: 0.8, other: 0.3}` |
| `lookup_symbol` | `name, domain=engine, subtype?` → `{symbol_id, file, line, column, kind}` | `{engine: 1.0, others: 0.0}` |
| `referencers` | `symbol_id, depth?` | N/A — graph |
| `expert_examples` | `topic, audience=reference_example, k=5` (topic-retrieval only; NOT error-resolution) | `{engine: 0.5, official_docs: 1.0, other: 0.4}` |

**`path_prefix` filter semantics:** `$contains` substring matching with leading-slash-anchored workaround. The `$contains` operator is evaluated at the application layer (not a native ChromaDB operator — native: `$eq`, `$ne`, `$in`, `$gt`/`$lt`, `$contains`).

**Weight renormalization:** `resolve_weights(call_weights: dict, active_domains: set) -> dict` lives in the resolver and renormalizes over active domains before weighting. Prevents phantom-domain underweighting in project-only deployments.

## Reranker Architecture

**Graph-rerank-on-semantic** (not three-substrate fusion):

```
final_score = blended_semantic_score × graph_boost(symbol_id, query_intent)
```

- Semantic = primary retrieval substrate (shared CodeRankEmbed space)
- Graph-rerank = separate scoring stage over top-K semantic candidates using SCIP structural graph evidence
- `compute_graph_boost(symbol_id: str, query_intent: str, graph_evidence: dict) -> float`
- Bounds: `graph_boost ∈ [0.5, 2.0]`; clamp inside function, not at call sites
- Out-of-range emits `log.warning` (operator signal); does not raise

## Embedder Ownership and Chunk Schema

**Single embedder owner: project-rag side.** holodeck-corpus emits structured chunks (text + metadata + provenance) per `engine_chunk_batch.v2.json`. project-rag embeds locally during install Phase 2.5 (~5-10 min one-time per UE version). Local embed is the default — NOT pre-built vector download (avoids cross-repo embedder-revision pinning into the BOM).

**Chunk schema v2 additions (Amendment 2):**

| Field | Required? | Why |
|-------|-----------|-----|
| `engine_version` | Required-if-available | Prevents UE 5.7-vs-5.8 noise mixed in same corpus |
| `published_at` | Required-if-available | Enables recency decay per domain |
| `symbol_refs: [symbol_id]` | Optional | Connective tissue between docs and source |
| `kind: SymbolKind` | Optional | LSP-compatible symbol kind enum |
| `audience` | Required (with `unknown`) | `reference \| tutorial \| commentary \| reference_example \| unknown` |
| `is_generated` | Required (default `false`) | Prevents generated outputs from passing as authoritative |
| `derived_from: [chunk_id]` | Optional | Traceability chain for generated chunks |
| `tags: [string]` | Optional (default `[]`) | Free-form multi-valued per-project labels |
| `workspace: string` | Optional | Monorepo workspace name |
| `coverage_summary` | Required on every retrieval response | `{by_domain: {domain: count}, by_path_prefix: {prefix: count}}` |

## Install Orchestration

7-phase pipeline behind `/holodeck:setup` (DR-MRAG-006):

| Phase | Name | Notes |
|-------|------|-------|
| 1 | Preflight | Existing |
| 2 | Fetch holodeck-corpus chunks | NEW — download chunks JSONL → `~/.cache/holodeck-corpus/<rev>/` |
| 2.5 | Engine embed | NEW — project-rag's pinned embedder over Phase-2 chunks → `~/.cache/project-rag/engine-corpus/<UE-version>/` |
| 3 | Install/upgrade project-rag | NEW — delegates to project-rag's installer |
| 4 | Build TS server | Existing |
| 5 | Install plugins | Existing; runs `~/.claude.json` migrator |
| 6 | Doctor verification | Existing; gains BOM + freshness probes |

**Partial-resume contract:** If embed crashes mid-stream, recovery resumes from chunk N. Sentinel layout: single append-only manifest `<rev>.partial/embedded.jsonl`. Note: `<rev>.partial` is INCLUDED by the recovery path (unlike the general doctrine in `holodeck-doctrine.md §6` that excludes `*.partial` patterns from auto-discovery globs — intentional reversal documented inline in `holodeck_recover.{sh,ps1}` Phase-2.5).

## Cutover Protocol

**Single coordinated cut, eval-gated** (DR-MRAG-010). No overlap window. Gate criteria — multi-dimensional per query shape `{query, lookup_symbol, referencers, expert_examples}`:

1. **recall@10** within 5pp of baseline (per-shape)
2. **NDCG@10** within 3pp of baseline (per-shape; graded: 2=definitive, 1=useful-context, 0=irrelevant)
3. **top-1 stability** ≥ 80% per-shape
4. **p95 query latency** within 1.5× baseline per-shape

BASELINE re-freezes only on breaking deltas: `ue_rag_material_rev` major bump, `embed_model_revision` model-architecture change, or `embedding_strategy_version` bump. Non-breaking carry-forward emits `warnings: ["baseline_carry_forward: <reason>"]`.

## Strategic Posture

**Local-first, language-extensible, OSS destination** (post-halcyon strategic posture):

- Architectural insurance: deterministic + cached + structured retrieval floor that doesn't need re-architecting when model-tier costs change
- project-rag is the EM's brief-construction surface; agentic dispatch is the executor's reasoning surface; native LSP is the live-validation surface — different layers of the same pipeline
- Floor-hardening is the priority axis: graph-rerank passes, freshness signals in envelopes, capability-tier propagation harden the floor; tools that compose existing tools rank lower (an agent can already do that via dispatch)
- Industry-retreat narratives (Sourcegraph Cody walkback from embeddings) don't transfer: those were enterprise-multi-tenant economics; this is single-user, few-dozen-corpora, local-first deployment

## Decision Records

| DR | Decision | Rationale summary |
|----|----------|------------------|
| DR-MRAG-001 | Three-repo topology: corpus → server → core (upstream-first) | Clean concern boundaries; maintenance burden reduction; cloud-RAG aspiration preserved |
| DR-MRAG-002 | Local embed default (NOT pre-built vector download) | Avoids cross-repo embedder-revision pinning in BOM; bandwidth wins (~200-400 MB chunks vs ~3-4 GB vectors) |
| DR-MRAG-003 | ENVELOPE_VERSION=2 with 7 verdicts; no LegacyToolResponse shim | Doctrine debt compounds; pay it once; C1 refactor is where hit-shape divergence becomes load-bearing |
| DR-MRAG-004 | Parallel structural_engine.sqlite3; symbol_id PK shape aligned | Clean ownership; ID-space safety wins over one fewer round-trip |
| DR-MRAG-005 | Separate Chroma collections per source, shared embedding | Layer C plugin source is the precedent; score comparability preserved via shared CodeRankEmbed space |
| DR-MRAG-006 | 7-phase install pipeline behind /holodeck:setup | Single Entry-Point Doctrine preserved; phases are idempotent and resumable |
| DR-MRAG-007 | Doctor: orchestrator in core, probes follow data | Single report from two probe sources; /project-rag:doctor is contributor-only |
| DR-MRAG-008 | C++ UE plugin ships zero RAG content | Clean cadence separation; BOM reconciles via ue_engine_version + ue_rag_material_rev |
| DR-MRAG-009 | HTTP-shared engine source (:8765); per-project stdio for project source | 426K vectors don't deserve per-project reload; sidecar inflight cap accounts for fan-in |
| DR-MRAG-010 | Single coordinated cut, multi-dimensional eval-gated | No overlap window; two known consumers accept breaking change; green eval → cut merges |
| DR-MRAG-011 | BOM in core repo; cross-repo schema-version contract | Core is the install orchestrator; separate manifest-only repo overhead not justified |
| DR-MRAG-012 | bounded_popen: audit Wave 1, vendoring inversion Wave 5 | Inversion before PR-15 is premature abstraction; Wave 1 produces handoff doc |
| DR-MRAG-013 | Four unified primitives (query/lookup_symbol/referencers/expert_examples) replacing seven tools | Routing brittle with seven; skill ue-docs-lookup keeps UE-domain vocabulary routing but invokes four primitives |
| DR-MRAG-014 | Rename: last, single coordinated cut | Pre-rename identity drift compounds maintenance; provisional names hold until substrate is green |

## Coupling exceptions — content that stays in holodeck despite addon authority shift

Two files were explicitly PM-locked to remain in holodeck during the 2026-05-13 content migration:

| File | Rationale | Decision ID |
|---|---|---|
| `plugin/game-dev/sid-knowledge.md` | Sid persona-knowledge coupling is intentional — Sid's context is session-loaded from this path. Moving to addon would break the game-dev plugin's agent wiring. | Decision F (PM-locked 2026-05-13) |
| `../../../project-rag-ue-addon/docs/reference/game-dev-paradigm-shift.md` | Onboarding-adjacent reference cited from CLAUDE.md and persona READMEs as first recommended reading. An addon-side copy at `corpus/cheatsheets/game-dev-paradigm-shift.md` exists for RAG ingestion — intentional duplication, not drift. | Decision F-bis (PM-ratified 2026-05-14) |

Do NOT re-litigate these decisions. They are PM-locked.

## Script classification post-migration

18 PIPELINE-CORE scripts (16 original + 2 straddlers identified at migration time) moved to
`project-rag-ue-addon/scripts/`. The following categories stay in holodeck:
- **V3-TRAINING-BUILDER** — training data pipeline scripts (SFT-specific, not content-agnostic)
- **CURATION-ONE-OFF** — historical curation scripts
- **HOLODECK-DEBUG** — debug utilities tied to holodeck runtime

**Decision #4b** (PM-ratified 2026-05-13): content-agnostic production pipeline lives in addon;
holodeck-specific training and curation scripts stay in holodeck.

**Reference:** `archive/specs/2026-05-09-migrate-rag-content-to-addon.md` §Decisions F/F-bis, §4b.

---

## Consumer-set evolution — chunk-envelope direct consumption (2026-05-09)

The `engine_chunk_batch.v2.json` envelope (defined in `project-rag-ue-addon`, consumed by `project-rag`'s ingest path) currently has **zero direct consumers in this repo**. Holodeck reads UE knowledge through `mcp__project-rag__*` (see [Multi-MCP Workflow](../../CLAUDE.md)) — never by ingesting the JSONL artifact directly. PR-15 of the multi-RAG-coexistence split (shipped 2026-05-08) excised the surface (`mcp_server/`) that could otherwise have been a consumer.

**If that ever changes** — i.e., a holodeck-side runtime grows a need to consume chunks directly without a project-rag dependency — the holodeck EM at that time MUST:

1. **Surface to addon and project-rag BEFORE writing any consumer code.** Coordination memo at `X:/project-rag-ue-addon/archive/<date>-coordination-memo-from-claude-unreal-holodeck.md` (the symmetric reply path used for the 2026-05-09 cross-repo proposals).
2. **Re-verify field-tolerance and enum-closure assumptions** against whatever envelope schema version is then live. The currently-ratified `domain` × `subtype` shape is not a forever guarantee.
3. **Stand down if bidirectional-consumer ergonomics would force shape changes** that hurt the addon-as-producer / project-rag-as-consumer flow. That flow is the load-bearing path; a holodeck-as-second-consumer addition does not get to disturb it.

This commitment was recorded in response to project-rag's Ask #3 in the envelope schema extension proposal:
- Proposal + ratifications: `X:/project-rag-ue-addon/archive/2026-05-09-envelope-schema-extension-proposal.md`
- Holodeck-side ack: in-place at proposal §"Response — claude-unreal-holodeck (2026-05-09, FYI-only acknowledgement)"

## Post-multirag gap closure (2026-05-08)

After the multi-rag-coexistence Pass 2 shipped (19/19 PASS), a follow-up audit (`archive/specs/2026-05-08-post-multirag-gap-closure.md`) identified two P0 runtime breakages not caught by the Pass 2 test suite. Both were root-caused and fixed before the audit closed.

### P0 #1 — Layer C plugin-search EmbedClient retarget

**What broke:** Layer C plugin-search used a `mcp_server.retrieval` import path that referenced code inside the `mcp_server/` directory. PR-15 excised `mcp_server/` entirely as part of the multi-rag-coexistence split. After excision, the import path was dead — Layer C plugin-search would throw `ModuleNotFoundError` on first use.

**Fix:** EmbedClient retarget. The import path was updated to the post-split location. Gated as Wave 1.5 of the gap-closure plan to run before the deletion sweep.

**Lesson:** Repo-split audits must runtime-probe import paths, not just grep references. A grep for `mcp_server.retrieval` would have found zero results (the string was in a plugin-search file that wasn't scanned), but a runtime import test would have surfaced the dead reference immediately.

### P0 #2 — Bridge-service :8765/mcp silent breakage

**What broke:** The bridge service had a `:8765/mcp` HTTP endpoint that was surgically retained during the multi-rag-coexistence pass. After project-rag MCP took over the load, the `:8765/mcp` endpoint became dead infrastructure that could silently accept requests and fail to route them, producing confusing no-result behavior rather than a hard error.

**Fix:** Surgical removal (S2 in the gap-closure plan). The endpoint was deleted, forcing consumers to migrate to the project-rag MCP path.

**Lesson:** "Surgical retain" decisions during a large split should be audited in the gap-closure pass. A retained surface that becomes dead infrastructure is worse than a deleted surface — it fails silently rather than loudly.

---

### Pre-delete regression-net HARD GATE (S4.0 pattern)

Before the deletion sweep in the gap-closure plan, the prior-art-checker identified a missing regression gate. Step S4.0 was added as an explicit HARD GATE: the deletion sweep was blocked on regression-net-green.

**The pattern:**

> Before any deletion sweep that touches multi-consumer surfaces, land a regression-net test that exercises the load-bearing pathway at runtime. Deletion sweep is blocked on net-green.

**Why HARD GATE, not just "recommended":** A deletion sweep that passes unit tests but breaks runtime import paths produces P0 incidents. The gap-closure S4.0 addition was a direct consequence of the prior-art-checker flagging the absence of a runtime regression net before deletion — not an engineering judgment call, but a policy enforcement triggered by sidecar review.

**Generalizes to:** Any large-blast-radius cleanup, cross-repo extricability audits, holodeck excision steps (see `docs/wiki/holodeck-doctrine.md` §Pre-delete HARD GATE).

**Prior-art-check conflict it resolved:** The prior-art-checker flagged a conflict against `pre-delete-regression-net.md` in the coordinator wiki, which carries a REQUIRE verdict. S4.0 is the mitigation that resolved the conflict before the plan shipped.

**Source:** `archive/specs/2026-05-08-post-multirag-gap-closure.md` (S4.0); `docs/plans/2026-05-08-post-multirag-gap-closure.prior-art-check.md` (conflict identification).

## Chunks Port — Producer Outputs in Addon, Consumer Vector Store in Holodeck

Following the authority shift (2026-05-13) and W7-mech.0-PORT chunker migration (2026-05-14), the JSONL chunk outputs were ported to the addon 2026-05-18:

- **Addon `chunks/5.7/`:** 41 JSONLs (5 pre-existing + 36 ported, 566 MB); sha256-verified
- **Addon `eval/compass-gap-qa/`:** 2 baseline JSONLs (56 KB)
- **Holodeck `vector_store/`:** 1.6 GB merged sqlite, gitignored — consumer-side artifact, stays in holodeck; regenerated from addon GitHub Release

**Two v4.1.0 footguns dispositioned as hotfix v4.1.1:**
1. `symbols.module` NULL across 832,728 rows — `_extraction_meta` corrected in manifest
2. `_extraction_meta` over-advertised engine_editor+lyra layers that didn't ship in v4.0.3

**project-rag plugin layout (peer-repo-survey 2026-05-16):** Full Claude Code plugin: 3 agents, 10 commands (setup, doctor, index, reindex, audit, diff, show-index, watch, probe-readiness, bp-lint), skills (impact, subsystem, staleness-survey, project-rag-routing), hooks.json with SessionStart + PreToolUse. Install follows COLLAPSE topology (spec: archive/specs/2026-04-29-em-self-install-redesign.md). Pre-execution state assessment: `python -m scripts._setup_routing decide` → verdict JSON. project-rag-ue-addon plugin: setup.md + doctor.md only (no agents/skills/hooks — addon is purely a producer).

## Archaeology Campaign Patterns (2026-05-18)

The holodeck-docs archaeology campaign (2026-05-18, ref commit 259091c17) established patterns for systematic cross-repo extraction work. These patterns generalize to any future archaeology-style campaign:

### Scope bounds

- **Temporal anchor:** from repo inception commit to the point where the peer repo took over authority
- **Deliverable:** research catalog of known-unknowns (sidecars), NOT a port plan
- **Out-of-scope:** holodeck-control runtime (stays in holodeck regardless of archaeology findings)
- **Deleted code is in scope:** retrieve via `git show <SHA>:path` — scouts retrieve from history, not HEAD

### Methodology-vs-instance split (recursive)

The generic methodology lives in project-rag; the UE-specific instance lives in ue-addon. This split applies at **every abstraction level**, not just at the libclang level:

| Domain | project-rag (generic methodology) | ue-addon (UE-specific instance) |
|--------|------------------------------------|---------------------------------|
| Fine-tuning | Generic SFT+DPO harness | V3 Defiant on Gemma/Qwen, UE-content training corpus |
| Chunking | Generic chunker protocol | UE-specific chunkers (cpp, bp, docs) |
| Gating | Generic freshness/staleness gating | UE version-specific gates |
| Eval harness | Generic eval framework | UE-specific compass QA + bp_lint eval |
| Training data | Generic pipeline plumbing | UE-specific annotation and training corpus |

### Retention manifest — four survival shapes

When a deletion sweep follows an archaeology campaign, classify retained content into four shapes:

1. **HOLODECK-ACTIVE** — currently needed by holodeck runtime; blocking to delete (e.g., mcp_server/host_resilience/, holodeck_setup.{sh,ps1})
2. **ALREADY-HERE** — content that was never portably distinct from holodeck's own concerns
3. **NO-ADDON-ROLE** — content with no downstream consumer in any peer repo
4. **FORENSIC-LINEAGE** — deleted from HEAD but reachable via git history; deletion sweep is HEAD-only, history is untouched

### Three external signals before deletion sweep fires

Holodeck-side deletion sweeps are gated on three signals:
1. project-rag peer annotates which ALREADY-PRESENT items are MIS-CLASSIFIED and need emergency PORT
2. ue-addon B-7 fires conditional verification on shared content
3. PM explicitly authorizes the deletion sweep with the retention manifest as contract

**Do NOT delete anything based on archaeology findings alone.** All three gates must clear.

### Retention anchors (permanent)

- `archive/specs/2026-04-15-holodeck-project-rag-plugin.md` — triad-architecture origin anchor; cited by all three repos' CLAUDE.md "Repo triad" sections; NEVER delete
- Deleted mcp_server/ content (46 files at 04a6075d^) — reachable via git history (FORENSIC-LINEAGE); HEAD-only deletion sweep leaves this intact

### Cross-repo DR routing convention

Decision records live in the repo owning the subject matter. Other repos may have stubs. Canonical file: `docs/decisions/README.md` (created 259091c17) establishes this convention.

## Related Guides

- [`docs/wiki/holodeck-bom.md`](holodeck-bom.md) — BOM schema reference
- [`docs/wiki/holodeck-doctrine.md`](holodeck-doctrine.md) — Single Entry-Point Doctrine, process-per-tenant
- [`../../../project-rag/docs/wiki/project-rag-workflow.md`](../../../project-rag/docs/wiki/project-rag-workflow.md) — Tool usage patterns, Discovery/Navigation/Impact modes
- [`docs/wiki/schema-migration-auditing.md`](schema-migration-auditing.md) — Three-bucket schema migration pattern
- Research corpus: [`../../../project-rag-ue-addon/corpus/research/2026-05-07-multi-rag-coexistence/corpus-INDEX.md`](../../../project-rag-ue-addon/corpus/research/2026-05-07-multi-rag-coexistence/corpus-INDEX.md)
