# Peer-Repo Polarity — UE Specialization vs. Common-Language Core

> **Doctrine source:** the peer `example-game-workbench-repo` repo's JetBrains gap-closure roadmap (2026-05-13), §0 and §12.1. Local working-tree readers know the path; published readers use the peer repo's release docs.
> **Coordinator-claude role:** routing doctrine + EM dispatch authority per §0 line 141–143. Capability ≠ fit.

## The polarity rule

After multi-rag-coexistence (PR-10/13/15, 2026-05-08) split engine-RAG production out of example-game-repo and into `project-rag-ue-addon`, the four-repo layout settled as:

| Repo | Owns | Polarity signal |
|---|---|---|
| `example-game-workbench-repo` | UE editor control (`example-game-repo-control` MCP, ~109 tools), `/example-game-repo:*` skills, benchmark suite, ACP integration | UE-runtime / editor-control |
| `project-rag` (core) | Language-agnostic indexing MCP host, `project_*` tools, embed sidecar, blended query, structural-index runtime | Producer-agnostic; common-language corpora live here |
| `project-rag-ue-addon` | UE-specific extraction + corpus publish, UHT exporter, Redpoint Clang specifier matchers, UE-semantic MCP surface (anything UObject-aware) | UE-specialization lives here |
| `coordinator-claude` | Routing doctrine, EM dispatch, review pipeline, agent abstention rationales | "Coordinator routing" / "EM dispatches" by definition |

**The rule** (codified in project-rag-core's `feedback_addon_vs_core_polarity` memory):

> **UE-specialization migrates OUT to addon; new common-language corpora (Python / TS / Rust) stay IN-TREE as core. Don't invert.**

Inverting this — putting UE-aware analysis into core, or putting language-agnostic infrastructure into the addon — re-introduces the polarity error PR-10/13/15 fixed.

### Addon ↔ example-game-repo — sibling mutual dependency, NOT host/consumer

The `project-rag-ue-addon` ↔ `example-game-workbench-repo` relationship is **bidirectional and mutual**, not host/consumer. Both directions are load-bearing:

- **example-game-repo needs the addon corpus.** Without UE-grounded retrieval (UObject specifiers, UHT-derived headers, editor API surface), example-game-repo agents working in UE C++ / Blueprint hallucinate API shapes. Grounding without hallucination is the addon's deliverable to example-game-repo.
- **The addon needs example-game-repo control.** Without an agent surface that can *act* on the editor (spawn actors, edit Blueprints, run PIE), the addon's knowledge is toothless — querying "what is `UCharacterMovementComponent::MaxWalkSpeed`?" with no mechanism to apply the answer is a half-loop. Knowledge without acting is toothless; acting without knowledge is dangerous.

This differs from the host/consumer polarity that governs `project-rag` (host) → `example-game-repo` / `example-sim-repo` / `example-repo` / `example-stats-repo` (consumers): there, the dependency is **one-directional** (consumers depend on the host; the host never depends on them — see DR-152 host-consumer dependency-direction invariant). The addon↔example-game-repo pair is a separate polarity shape — sibling mutual dep — and surfaces in both repos' READMEs must frame it that way, not as one repo publishing to the other.

A reader reaching for "who depends on whom?" between addon and example-game-repo should find the sibling-mutual-dep framing, not infer host/consumer by analogy with the other consumers. (Source: 2026-06-04 ue-addon README disambiguation — incoming readers were misreading the addon as a publisher-to-example-game-repo rather than a peer.)

## Triad polarity — knowledge / mechanics / host axes

The 2-rail "UE-specialization OUT to addon" rule sits inside a richer 3-axis triad. Primary axis is **mechanics-vs-knowledge**; secondary axis is **engine-wide vs project-specific**; the host repo carries neither half but provides the runtime substrate both halves plug into.

| Repo | Axis position | What it owns |
|---|---|---|
| `project-rag-ue-addon` | **Knowledge** half (engine-wide) | UE corpus production, UHT/libclang extraction, structural-index schema, UE-semantic MCP tools |
| `example-game-workbench-repo` | **Mechanics** half (project-specific) | Editor control, headless authoring, 3D-gen sidecars, in-editor actuation |
| `project-rag` | **Host** (content-agnostic) | Indexing runtime, MCP host, embed sidecar, addon protocol, blended query |
| `coordinator-claude` | **Routing doctrine + EM dispatch** | Polarity rules, agent abstention rationales, review pipeline |

The shorthand that captures the mechanics/knowledge split, originally from the 2026-05-13 UE-authority-shift memo:

> **Knowledge without ability to act is toothless; acting without knowledge is dangerous.**

This is the structural reason example-game-repo and ue-addon are *siblings with mutual dependency*, not host-and-consumer. The 22 chunkers + structural-extraction pipeline + schema-vendoring source were ported from example-game-repo to ue-addon on 2026-05-14 (W7-mech.0-PORT) precisely to realign these axes; that port is what makes the polarity rule above tractable. Canonical doctrine in peer repos: `docs/wiki/triad-roles-doctrine.md`.

## Repo capsules — what each owns (post-carve-out)

When routing or abstaining, the polarity question reduces to: which of these capsules is the request asking about? Read these once; they are the source of truth that downstream README prose must match.

**`project-rag` (host).** Local-first, content-agnostic code-RAG MCP server. Three-layer retrieval: raw (file/symbol lookup), structural graph (SQLite v12, deterministic), semantic (ChromaDB + FastAPI embed sidecar on port 43841 with GPU isolation, 300s idle-offload, 1800s self-exit). Install has two legs (capability + orient-and-index); setup seeds spinoff batons for coordinator `/pickup`. **Never** UE-specific by construction.

**`project-rag-ue-addon` (knowledge / engine-wide).** UE engine-corpus producer + MCP-tool author plugged into the host via the addon protocol. Production: scrapes UDN (Playwright), chunks (22 `chunk_*.py` producers), indexes (libclang + UHT F-L1 .NET 8 exporter). Ships as versioned GitHub Release bundles, canonical tag `corpus-v<corpus_version>-ue<UE_MAJOR>.<UE_MINOR>` (e.g. `corpus-v0.1.0-ue5.7`): JSONL chunk set + SQLite structural index (`schema_version=4`, `MIN_SUPPORTED_SCHEMA=3`) + `manifest.json` + `.sha256` sidecar. Canonical publisher: `publish-engine-corpus.sh` — never raw `gh release upload` (bypasses `gate_structural_index.py`). Registers 17 MCP tools into the host: 10 D-wave diagnostic + 7 `project_engine_*` query. Corpus and schema versions deliberately decoupled from UE version.

**`example-game-workbench-repo` (mechanics / project-specific).** UE editor control (`example-game-repo-control` MCP, ~109 tools), headless-mode authoring in `example-game-repo-headless`, 3D-gen sidecars, `/example-game-repo:*` skills, benchmark suite, ACP integration. Owns the dogfood project (example-sim-repo asset/edge counts), **not** the engine-knowledge benchmark — that belongs to ue-addon.

**`coordinator-claude` (routing).** Routing doctrine, EM dispatch authority, review pipeline, agent abstention rationales. Owns the *rules*; the agent-routing-table file itself lives in the peer example-game-repo repo.

## Install chain — example-game-repo is the leaf

Canonical install order (upstream-first, walked by the agentic install spine):

```
coordinator-claude  →  project-rag  →  project-rag-ue-addon  →  example-game-workbench-repo
```

**example-game-repo is the leaf.** It consumes project-rag (`mcp__project-rag__project_semantic_search` with `source="unreal"`) for engine queries, and downloads the structural-index corpus from `project-rag-ue-addon` GitHub Releases (e.g. `corpus-v4.0.3-ue5.7`). `coordinator-claude` is a *soft-dep* in nominal terms but effectively required in practice (chain-install, machine-local registry, review personae).

Practical implication for routing: a request that starts in example-game-repo and reaches for engine knowledge crosses **two** polarity boundaries (example-game-repo → host → addon). Abstention rationales should name the boundary being crossed, not just the "right tool" — otherwise the next reviewer re-derives the chain from scratch.

## OSS-publish polarity per repo

The trio is **not** uniformly OSS-bound. Polarity matrix:

| Repo | OSS posture | Implication |
|---|---|---|
| `project-rag` | OSS-bound, **content-agnostic** | Public README must read as a content-agnostic indexing host; UE-specific phrasing is a doctrine error |
| `project-rag-ue-addon` | Internal **developer-facing** | OK to be UE-explicit; assume reader is a developer working on the addon, not an end-user installing it cold |
| `example-game-workbench-repo` | Internal **invite-only** | Smallest audience; README can assume full trio context; **do not** mirror its framing into the OSS-bound repos |

This matrix is *load-bearing* for README authoring. The 2026-06-02 trust-surface plan made it explicit precisely because surgical edits to a public README kept re-inverting polarity when the author was thinking from the internal-repo POV. Inversions are *structural*, not stylistic — a README that reads OK in isolation but presents the wrong audience contract is still a polarity violation.

## Three-layer fiction — README discipline post-carve-out

A specific failure mode the trust-surface audit caught: example-game-repo's README historically attributed **all three layers** (knowledge, control, project-intelligence) to itself. Post-carve-out, this is fiction:

- **Knowledge layer** (426K-vector RAG, 636K-symbol structural index, 789-question benchmark, 97.6% accuracy) belongs to `project-rag-ue-addon`.
- **Control layer** (107 MCP tools in `example-game-repo-control`, headless authoring, 3D-gen sidecars) is example-game-repo's actual scope.
- **Project-intelligence layer** belongs to the `project-rag` host.

example-sim-repo asset/edge counts ARE example-game-repo's dogfood, and benchmark stats ARE knowledge-layer — keep them straight. Fixing this is a **structural rewrite**, not a surgical edit; polarity inversions don't repair with line-level patching because the surrounding prose still scaffolds the wrong mental model.

Generalize the rule: if a repo's README claims authorship of a capability the trio capsules above assign to a sibling, that's a three-layer-fiction defect — rewrite, don't patch.

## Sibling-naming scrub — what each repo's public README may NOT mention

Per the OSS-publish polarity matrix, the content-agnostic host (`project-rag`) **must not** publicly name its UE-specific siblings. Concrete must-scrub items found in the 2026-06-04 audit:

- `project-rag` README must NOT publicly name `project-rag-ue-addon` or `example-game-repo-control` (regardless of HTML-comment tags like `ue-augmented`).
- A `project-rag` README reference to a wiki page named `standalone-vs-ue-augmented.md` is itself a polarity leak — the filename leaks the addon's existence to OSS readers.
- Acceptable framing: *"engine- or domain-specific functionality attaches via the addon protocol."* Generic, content-agnostic, doesn't name a sibling.

Symmetrically: internal-audience repos (ue-addon, example-game-repo) can be explicit about siblings — their READMEs are not OSS surfaces.

## Trust-surface artifact set (trio repos)

Trust-surface artifacts are standardized across the trio (example-game-repo, project-rag, project-rag-ue-addon), modeled on `coordinator-claude`'s shape: **polarity-aware, humans-first, fact-accurate.**

The canonical artifact set:

- `README.md` — written to the OSS-publish polarity matrix above
- `CONTRIBUTING.md`
- `SECURITY.md`
- `PRIVACY.md`
- `COMMERCIAL.md`
- `CODE_OF_CONDUCT.md`
- `AGENTS.md` — standardized agent-facing entry-point naming across the trio

"Polarity-aware" is the load-bearing adjective: the artifact set is *the same files*, but the prose inside each is written to that repo's polarity row in the matrix. A SECURITY.md for `project-rag` (OSS-bound, content-agnostic) reads differently from a SECURITY.md for `example-game-workbench-repo` (invite-only), and that difference is *correct*, not a drift defect.

## What this means for coordinator-claude routing

When a new MCP surface lands and needs to appear in the agent-routing table (authoritative copy lives in the peer `example-game-workbench-repo` repo at `tasks/agent-routing-table.md`, read by the `example-game-repo-router` agent) or in a coordinator-routed agent's abstention rationale, the routing entry must answer two questions, not one:

1. **Which agent has the capability?** (mechanical — match the tool name to the agent's `tools:` frontmatter and signal vocabulary.)
2. **Is the capability a fit for this agent's polarity?** (load-bearing — a tool that calls `mcp__project-rag__*` from the addon namespace is *UE-semantic*; routing it through a producer-agnostic agent crosses the polarity line.)

A routing entry that only answers (1) is mechanical and wrong. A routing entry that answers both is doctrine-aligned.

## Abstention-rationale template

When a coordinator-routed agent abstains from a UE-semantic request because the better fit lives in a peer agent (or vice versa), the abstention rationale should mirror the polarity language explicitly:

> ABSTAIN: This request is UE-semantic (touches UObject / specifier / `WITH_EDITOR` / cooked-vs-editor semantics). Per peer-repo polarity (see `docs/wiki/peer-repo-polarity.md`), route through `<addon-namespaced tool>` rather than the producer-agnostic core surface. Suggested next: `<agent>` with goal `<concrete-goal>`.

Or, for the inverse case:

> ABSTAIN: This request is common-language indexing (`<lang>` corpus, no UE-specific semantics). Per peer-repo polarity, route through `mcp__project-rag__*` core tools, not the UE-addon surface. Suggested next: `<agent>` with goal `<concrete-goal>`.

Greppable signal words for abstention triggers: `UObject`, `UCLASS`, `UFUNCTION`, `UPROPERTY`, `WITH_EDITOR`, `cooked`, `AssetRegistry`, `UHT`, `specifier`, `.uproject`, `BlueprintCallable`. If a request mentions any and the candidate agent's `mcp__project-rag__*` tool list is core-only, abstain to the addon.

## The polarity audit (F-L4 reconciliation, W5–W6)

`project-rag-core`'s F-L4 integration host owns the polarity-audit authority at the W5 seam review: any tool registered against the integration host that is UE-semantic gets pushed back to the addon. Coordinator-claude's role at W5–W6 is downstream — once F-L4 ships, the agent-routing table and per-agent abstention rationales should reflect F-L4's polarity verdicts, not coordinator-side guesses.

If coordinator-claude routing claims something is producer-agnostic but F-L4 audits it as UE-semantic, **F-L4 wins** — that's the seam contract from §12.1.

## Cross-references

- Source roadmap §0 — full four-repo polarity statement and historical context (multi-rag-coexistence)
- Source roadmap §12.1 — "polarity error is doctrine-violating, not stylistic" (project-rag-core EM addendum)
- `tasks/agent-routing-table.md` in the peer `example-game-workbench-repo` repo — authoritative routing-table file (NOT in coordinator-claude; coordinator-claude owns the doctrine, example-game-repo owns the table file)
- `docs/wiki/repo-registry.md` — peer-repo registry for prior-art lookups; complements but does not subsume this polarity rule
- `docs/wiki/peer-port-discipline.md` — the adoption/comparison sibling: what to re-verify when an artifact crosses a repo boundary (this wiki owns the *ownership* axis; that one owns the *adoption* axis)
