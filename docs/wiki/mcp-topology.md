# MCP Topology

> A typed, standalone declarative view over coordinator's first-party MCP servers — the architecture-level answer to MCP tool proliferation.
>
> Spec backlink: `docs/plans/2026-06-27-ccos-9-mcp-topology-schema.md`
> Declaration file: `plugins/coordinator/mcp-topology.yaml`

---

## 1. The Model

`mcp-topology.yaml` declares every MCP server the coordinator plugin ships or depends on. Its purpose is to give the EM a single place to read the load posture of the full tool surface — before any session starts, and without interrogating the harness.

Each entry in `servers:` is typed on **two independent axes**, plus an opt-out unit field:

| Axis / Field | Field | Values / Semantics |
|------|-------|--------|
| **Boundary** | `configKey` | The `.mcp.json` server key — the SDK-visible boundary. Each entry is independently addressable at this granularity. |
| **Load policy** | `loadPolicy` | `eager` — unconditionally at session start; `deferred` — on demand when intent surfaces; `conditional` — when a project-specific condition is met. |
| **Opt-out unit** | `optOutUnit` | The unit a project disables to drop the whole tool family. For plugin-bundled servers (example-game-repo-control, notebooklm), this is the `settings.json` `enabledPlugins` gate — NOT the `.mcp.json` key. For raw per-project `.mcp.json` servers (project-rag, context7), `optOutUnit == configKey` because no plugin gate exists. → § 9, `per-project-plugin-gating.md`. |

A third axis present in example-voice-system's `McpServerTopologyEntry` (`transport` / `endpointPath`, `mcpTopology.ts:207`) is **deliberately dropped**. All coordinator MCP servers are `stdio`/command-launched per `.mcp.json` — they are not HTTP-pathed — so the transport dimension adds no differentiating information in this stack. This is a divergence from example-voice-system, not an oversight.

---

## 2. The `core: none` Posture

The topology file opens with:

```yaml
core: none  # no coordinator MCP server is eager; posture is deferred-by-default
```

Unlike example-voice-system (which ships one eager-loaded core server), coordinator has **no always-loaded MCP server**. Every server is either `conditional` or `deferred`. This is a positive design fact, not a gap.

The doctrine's job is to **keep coordinator deferred-by-default** as servers are added over time — not to retrofit deferral onto an already-eager base. Any new server added with `loadPolicy: eager` must carry a named justification for why it cannot be `conditional` or `deferred`.

---

## 3. Current Entries

| configKey | loadPolicy | When it loads |
|-----------|-----------|---------------|
| `project-rag` | `conditional` | Project has a RAG index (`Saved/ProjectRag/` marker or `--project-root` arg in `.mcp.json`) |
| `context7` | `conditional` | Added per-project `.mcp.json` when API signatures matter |
| `example-game-repo-control` | `deferred` | UE workstream intent surfaces — 170 tools, UE-only |
| `notebooklm` | `deferred` | Deep-research pipeline D only |

**`conditional` is grounded in established coordinator vocabulary.** `project-rag`'s conditional policy maps directly to tiered-context-loading.md Tier-2 (code-shaped lookup when a RAG index is present), and `context7`'s conditional policy maps to the CLAUDE.md "Documentation Lookup — Context7" doctrine: "per-project on demand." These are not new concepts introduced by the topology — the topology gives them a typed label. → `tiered-context-loading.md`, `CLAUDE.md § Documentation Lookup — Context7`.

**`example-game-repo-control`'s `deferred` policy is the typed declaration of what `settings.json` plugin-gating already enforces.** `per-project-plugin-gating.md` describes how `example-game-repo-control` is disabled by default in `~/.claude/settings.json` and re-enabled only in UE-context projects. The topology's `deferred` label operates at a higher altitude — it names the *intended* load posture as a typed fact, while `settings.json` enforces it at the *mechanism* level. These two are additive, not redundant: the topology is where the EM reads the policy; `settings.json` is where the harness applies it. → `per-project-plugin-gating.md`.

---

## 4. Shape-Spec vs. Queryable Record Type

`mcp-topology.yaml` is **not** a `schemas/` entry. This distinction is load-bearing.

All 26 files under `schemas/` are **record-collection frontmatter validators**: each declares `applies_to:` and `kind:` values that `query-records.js` uses to route queries across a collection of many same-kind YAML records (handoffs, plans, lessons, improvement-queue entries). `bin/verify-schema-registry-sync.sh` line 129 makes this contract explicit — schemas without an `applies_to:` key are skipped entirely, because without it they cannot participate in the `query-records.js` dispatch surface.

`mcp-topology.yaml` is categorically different: it is a **body-shape spec for a single declaration file** — there is only ever one topology file, not a collection. It describes the structure of its own body, not the frontmatter of a record set. Adding it to `schemas/` would misuse the schemas/ machinery (which is keyed by collection cardinality and `applies_to:/kind:` routing) for an object of an entirely different kind.

If future work requires querying topology entries as records, a new query-records type would be appropriate — but that is a separate decision, not a default from current schemas/ placement.

---

## 5. Runtime Enforcement Is Deferred — The Future Seam

This file is **declaration + doctrine only**. No coordinator-owned *load-policy loader* exists today. MCP loading is handled entirely by the Claude Code harness + per-project `.mcp.json` + `settings.json` plugin-gating (→ `per-project-plugin-gating.md`). The topology is what the EM reads to understand load posture; it is not what the harness reads to enforce it.

Building a loader that honors `loadPolicy` speculatively is **YAGNI** — the harness already controls loading, and the topology gives the EM the typed view it needs to reason about that loading without a custom enforcement layer.

**What runtime enforcement would attach to, if it were ever built:**

A future runtime enforcement layer would read `mcp-topology.yaml`, resolve each `configKey` against the active `.mcp.json`, and assert that `deferred` servers are not present in the active tool surface at session-start time. It would fire at the same point as the existing SessionStart hooks (`coordinator/hooks/scripts/`), after the harness has resolved the MCP server list but before the first tool call. The topology's `loadPolicy` field is the seam a future plan would attach to.

**A named caveat for that future layer:** `.mcp.json` `${VAR}` env-expansion resolves from the OS launch shell, not from `settings.json` env — a future enforcement layer must account for this (see improvement-queue `2026-06-24-claude-code-mcp-json-var-does-not-compos`).

---

## 6. This Topology Is Not a Runtime Signal

**Non-goal:** the topology is not a runtime signal; for in-band routing see `project-rag-mcp-self-declaration.md`.

Project-RAG's self-declaration (`project_rag_instructions()`) is an in-band runtime message that a *consumer agent receives at tool-selection time* — it tells the agent what content classes are available in the current RAG index. That is a live routing signal. The coordinator MCP topology is a *static declaration the EM reads at planning time* to understand the full configured load surface. These operate at different altitudes and serve different purposes; they are not alternatives to each other.

---

## 7. Rule for Adding a New MCP Server

**Declare it in the topology with a load policy. Default `deferred` unless a named reason makes it `conditional` or `eager`.**

The one-line test: can the server be loaded on demand (when intent surfaces it) rather than at session start? If yes, `deferred`. Can it be scoped to a project-specific condition (RAG indexed, per-project `.mcp.json` add)? If yes, `conditional`. If neither, `eager` with a named justification in the `notes:` field.

The `core: none` posture is the invariant to preserve. Each addition should leave it intact.

---

## 8. Own-Declaration Model for Consumers

**`coordinator/mcp-topology.yaml` is the coordinator plugin's own instance — it is NOT shared substrate for percolation.**

The declaration file is excluded from the OSS percolation path (`.percolate-ignore` entry added 2026-06-27). It references operator-specific and other-plugin servers (`example-game-repo-control`, `notebooklm`) that are coordinator-author-specific and must not land in the OSS `coordinator-claude` publish tree. The CLAUDE.local.md editorial principle applies: these server entries are contingent on infrastructure the OSS user does not have.

**What IS shared substrate:** the type model (the YAML shape — `configKey`, `loadPolicy`, `optOutUnit`, `tools`, `notes`) and this wiki. OSS coordinator users can read this wiki, understand the model, and author their own `mcp-topology.yaml` at their plugin root for the servers they actually ship. The wiki and type model percolate; the declaration instance does not.

**If you are an OSS coordinator user setting up your own topology:**
1. Create `<your-plugin-root>/mcp-topology.yaml` following the shape documented in § 1 and the existing file as a structural template.
2. Declare only the servers your plugin or operator setup actually ships.
3. Add your instance to your own `.percolate-ignore` if you publish to a downstream OSS repo and your instance references setup-specific servers.

---

## 9. `optOutUnit` for Plugin-Backed Servers

**The `optOutUnit` for a plugin-gated server is the `settings.json` `enabledPlugins` gate, not the `.mcp.json` server key.**

When a server is gated via `settings.json` `enabledPlugins` (see `per-project-plugin-gating.md`), the correct opt-out unit is the plugin gate entry — the unit a project disables to drop the whole tool family. Using the `.mcp.json` key as `optOutUnit` for a plugin-gated server would misidentify the opt-out mechanism: the `.mcp.json` entry may still be present while the plugin gate suppresses it.

**Concrete rule:**
- **`example-game-repo-control`** is gated via `settings.json` `enabledPlugins` entry `example-game-repo-control@example-game-workbench-repo`. Its `optOutUnit` is `example-game-repo-control@example-game-workbench-repo` — that is the unit you disable in `settings.json` to suppress the 170-tool surface on non-UE projects.
- **`notebooklm`** is gated via `settings.json` `enabledPlugins` entry `notebooklm@coordinator-claude` (the deep-research plugin gate). Its `optOutUnit` is `notebooklm@coordinator-claude` — disabling the plugin gate suppresses the entire deep-research NotebookLM pipeline, not just the `.mcp.json` entry.
- **`project-rag`** and **`context7`** are raw per-project MCP servers loaded directly via `.mcp.json` — they are NOT gated via `enabledPlugins`. Their `optOutUnit` equals the server key (`project-rag` and `context7` respectively); removing from `.mcp.json` is the opt-out mechanism.

This distinction matters when an agent needs to understand what to disable: for plugin-gated servers, the `enabledPlugins` key is the correct surface; for raw MCP servers, the `.mcp.json` key is. → `per-project-plugin-gating.md`.
