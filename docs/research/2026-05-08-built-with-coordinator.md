---
title: "Built with coordinator-claude — evidence corpus"
date: 2026-05-08
type: evidence-corpus
---

# Built with coordinator-claude

This is one PM's experience over ~17 weeks (December 2025 → May 2026). It documents what was shipped or progressed under the coordinator-claude PM/EM workflow during a period in which the PM did not type a line of code himself. It is not a generalizable benchmark. It is one data point on what one setup, one PM, and one model produced in a defined window.

The projects below range from pure infrastructure (a local-first MCP indexing server in Python) to production game software (a UE 5.7 title on Steam in private alpha) to deployed web applications and analytics engines. The coordinator-claude workflow was used throughout — not as a code-completion tool, but as a full PM/EM operating layer: planning with named-reviewer review gates, executor dispatch for implementation, structured handoffs between sessions, and decision records tracking the architectural choices.

**Six projects, ~10,000 commits, 17 weeks, one PM who hasn't typed code since December 2025.**

---

## Headline projects

### `project-rag` — local-first project-indexing MCP server

Open-source ([dbc-oduffy/project-rag](https://github.com/dbc-oduffy/project-rag) — private at time of writing, OSS-targeted). ~91K Python LOC across 328 files, 700+ commits produced in approximately three weeks. This is the densest engineering velocity in the set.

Architecture: SQLite + ChromaDB + CodeRankEmbed pipeline. Exposes a live MCP server with 7+ tools. Sub-second queries against an 85K-asset corpus. Layer-1 SQL fast-paths benchmarked at 58×–408× vs. naive baseline. Includes a C++ structural index (clang-AST), CVar extraction, asset registry, semantic search, and an embed sidecar. Frozen schema; UE-augmented mode + standalone mode for TypeScript, Python, Rust, and generic project types. Distributed via private GitHub and consumed by the Unreal Engine stack below.

Coordinator-discipline footprint: 24 wiki pages, 5 handoff artifacts, eval-baseline JSON, and sweep results all committed to the repo. The architecture decision records, capability matrix documentation, and multi-session handoff chain are themselves evidence of how the workflow operates on a nontrivial infrastructure project.

### An Unreal Engine knowledge + control stack

Three-layer architecture built for AI-native Unreal Engine development:

- **Knowledge layer** — 426K-vector RAG built over the engine source, official Epic documentation, UE Python API, 4,200+ CVars, HLSL shaders, and the C# build system; 648K-symbol clang-AST structural index.
- **Control layer** — ~90 MCP tools covering 1,900+ actions across actor, blueprint, lighting, animation, Gameplay Ability System, Niagara VFX, sequence/cinematics, Enhanced Input, and networking.
- **Project-intelligence layer** — distributes `project-rag` (above) as the per-project asset and code indexing substrate.

Gated by a 789-question reproducible benchmark at 97.6% accuracy (99.8% factual / 94.9% code-quality / 90.2% Blueprint). Test surface: 1,088 Python tests + 1,159 TypeScript tests. Production-validated against the simulation game below — 85K assets, real shipping target. 4,980 commits across approximately three months; 25 active handoff artifacts and 81 wiki pages at time of writing.

No public-facing brand surfaced in this document.

### A UE 5.7 simulation game in private Steam alpha — proof-of-the-stack

85,619 assets, 326,062 reference edges, 2,581 commits in approximately three months. This project is the production validation target for the knowledge + control stack above — every MCP tool, every knowledge-layer query, every benchmark assertion was exercised against real gameplay systems in this codebase.

The coordinator-discipline footprint here is the densest in the set: 81 wiki pages, 6 decision records, 8 active handoffs, a dedicated archive directory, and a custom tooling directory — all alongside a real UE 5.7 project with custom engine plugins, Steam packaging configured for multiple SKUs, and a clang-LSP-ready build.

Steam-shipped (private alpha) is the load-bearing fact: this is not a prototype or a tech demo. The specific store listing, public-facing title, and operator brand are not surfaced here. This is the "real game on Steam" proof artifact: the single most credible signal in the set that AI-driven development produces shippable software at real production scale.

These three headline projects span from pure infrastructure (project-rag) through an AI tooling layer (the UE knowledge + control stack) to a production game title (the Steam alpha). Taken together they represent continuous cross-domain operation of the coordinator-claude workflow over approximately three months.

The coordinator-discipline footprint is visible across all three: handoff chains, wiki pages, decision records, and eval infrastructure are committed alongside the code. These artifacts are not just bureaucracy — they are the navigational substrate that lets a PM make sense of 4,000+ commits in a complex codebase without reading a diff.

---

## Minor projects

Smaller proof points, each built under the same coordinator-claude PM/EM workflow:

- **An e-commerce storefront** — production-deployed, in stealth. Firebase App Hosting + DataConnect backend.
- **A cloud-streamed games application backed by AWS GameLift Streams** — production-deployed, in stealth.
- **A sports analytics engine wrapped in a Firebase webapp** — built in 7 days flat. pnpm monorepo, prediction engine + serving layer, deployed against a live tournament calendar.
- **`experiments`** — the coordinator-claude project's own benchmark harness staging ground. Two full benchmark rigs scaffolded (handoff-vs-compaction, research-pipeline-benchmark) with v1 + v2 implementations and a persistent results database. Harnesses are built; most runs are pending dedicated budget. Naming the harness as evidence of "we can run our own evals when we have the budget" is fair; the numbers from unfinished runs are not quoted here.

---

## What this demonstrates — and what it does not

Six projects across five domains (infrastructure, AI tooling, game development, SaaS / e-commerce, data analytics) in 17 weeks. One product manager. No code typed by the PM. ~10,000 commits. That is the summary; the detail above is what makes it checkable.

This is not a claim that a different orchestration approach couldn't have produced these outputs. It is a claim about a specific setup — one PM, one model, this workflow — producing this much real software in this much time. The artifacts have shape: production deployments, Steam packaging, real benchmarks with verifiable numbers, multi-machine + concurrent-EM operations at scale, mature wiki + decision-record discipline. They are not a portfolio of toys, but they are also not a controlled comparison. They are evidence that this setup works for this PM, on these problems, at this point in time.

Your mileage will depend on your domain, codebase, and the discipline you bring to PM/EM separation. The coordinator-claude workflow is not frictionless — it asks for real architectural judgment and consistent PM altitude. What it removes is implementation latency; what it adds is structured review and continuity discipline. The work above is linked or described so readers can assess the shape of the output themselves.

---

## Sibling evidence

These three artifacts form the evidence corpus for coordinator-claude. They are peers — no one of them is primary:

- **[docs/research/2026-03-26-persona-experiment-results.md](2026-03-26-persona-experiment-results.md)** — controlled experiment with negative result: 400 paired observations, mechanically scored. Frames where named personas add signal (plan/architecture review) and where they don't (mechanical bug detection, where bare Sonnet agents do at least as well). The negative result is the credibility signal — it was published, not suppressed.
- **[docs/evolution/05-failure-modes.md](../evolution/05-failure-modes.md)** — qualitative evidence ledger. Operational scar tissue from real coordinator-claude sessions, organized by failure-mode taxonomy. False completion, silent scope expansion, test theater, review laundering, context amnesia, integration blindness — these are the failure modes the system was built around, described from observation rather than theory.
- **This file** — productivity-proof corpus: what was shipped and at what scale, with enough detail to evaluate the claim.
