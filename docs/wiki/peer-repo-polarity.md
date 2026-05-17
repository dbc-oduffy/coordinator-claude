# Peer-Repo Polarity — UE Specialization vs. Common-Language Core

> **Doctrine source:** the peer `claude-unreal-holodeck` repo's JetBrains gap-closure roadmap (2026-05-13), §0 and §12.1. Local working-tree readers know the path; published readers use the peer repo's release docs.
> **Coordinator-claude role:** routing doctrine + EM dispatch authority per §0 line 141–143. Capability ≠ fit.

## The polarity rule

After multi-rag-coexistence (PR-10/13/15, 2026-05-08) split engine-RAG production out of holodeck and into `project-rag-ue-addon`, the four-repo layout settled as:

| Repo | Owns | Polarity signal |
|---|---|---|
| `claude-unreal-holodeck` | UE editor control (`holodeck-control` MCP, ~109 tools), `/holodeck:*` skills, benchmark suite, ACP integration | UE-runtime / editor-control |
| `project-rag` (core) | Language-agnostic indexing MCP host, `project_*` tools, embed sidecar, blended query, structural-index runtime | Producer-agnostic; common-language corpora live here |
| `project-rag-ue-addon` | UE-specific extraction + corpus publish, UHT exporter, Redpoint Clang specifier matchers, UE-semantic MCP surface (anything UObject-aware) | UE-specialization lives here |
| `coordinator-claude` | Routing doctrine, EM dispatch, review pipeline, agent abstention rationales | "Coordinator routing" / "EM dispatches" by definition |

**The rule** (codified in project-rag-core's `feedback_addon_vs_core_polarity` memory):

> **UE-specialization migrates OUT to addon; new common-language corpora (Python / TS / Rust) stay IN-TREE as core. Don't invert.**

Inverting this — putting UE-aware analysis into core, or putting language-agnostic infrastructure into the addon — re-introduces the polarity error PR-10/13/15 fixed.

## What this means for coordinator-claude routing

When a new MCP surface lands and needs to appear in the agent-routing table (authoritative copy lives in the peer `claude-unreal-holodeck` repo at `tasks/agent-routing-table.md`, read by the `holodeck-router` agent) or in a coordinator-routed agent's abstention rationale, the routing entry must answer two questions, not one:

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
- `tasks/agent-routing-table.md` in the peer `claude-unreal-holodeck` repo — authoritative routing-table file (NOT in coordinator-claude; coordinator-claude owns the doctrine, holodeck owns the table file)
- `docs/wiki/repo-registry.md` — peer-repo registry for prior-art lookups; complements but does not subsume this polarity rule
