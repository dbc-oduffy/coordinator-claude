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
| **Opt-out unit** | `optOutUnit` | The unit a project disables to drop the whole tool family. For plugin-bundled servers (example-game-repo-control), this is the `settings.json` `enabledPlugins` gate — NOT the `.mcp.json` key. For raw per-project `.mcp.json` servers (project-rag, notebooklm-mcp), `optOutUnit == configKey` because no plugin gate exists. `context7` is a third shape: a user-scope plugin whose `enabledPlugins` gate DOES drop its tool surface, plus a finer per-project `disabledMcpServers` override. → § 9, `per-project-plugin-gating.md`. |

A third axis present in example-voice-system's `McpServerTopologyEntry` (`transport` / `endpointPath`, `mcpTopology.ts:207`) is **deliberately dropped**. All coordinator MCP servers are `stdio`/command-launched per `.mcp.json` — they are not HTTP-pathed — so the transport dimension adds no differentiating information in this stack. This is a divergence from example-voice-system, not an oversight.

<!-- spec-backlink: run 2026-07-22-23h55, nugget b6-017 -->
**Reference point — example-voice-system's own topology, for scale.** Example-Voice-System's `McpServerTopologyEntry` model (the one coordinator's `boundary`/`loadPolicy`/`transport` axes are patterned on) declares five first-party servers: `example-voice-system-core` (`eager`, 8 tools), `example-voice-system-host` (`deferred`, 34), `example-voice-system-trackers` (`deferred`, 17), `example-voice-system-situational` (`conditional`, 6), `example-voice-system-extension-dev` (`deferred`, 14). Only `example-voice-system-core` is `eager` — everything else defers until ToolSearch surfaces it by intent. Coordinator's `core: none` posture (§ 2) goes one step further than this reference model: example-voice-system still keeps one eager core; coordinator has none.

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
| `plugin:context7:context7` | `deferred` | User-scope plugin, enabled fleet-wide by default; schema load defers to `ToolSearch` intent |
| `example-game-repo-control` | `deferred` | UE workstream intent surfaces — 170 tools, UE-only |
| `notebooklm-mcp` | `deferred` | Deep-research pipeline D only — user-installed external server, absent until registered |
| `claude.ai Atlassian Rovo` | `deferred` | Account-side connector, held by `atlassian-worker` |
| `claude.ai Google Drive` | `deferred` | Account-side connector, held by `drive-worker` |

**`conditional` is grounded in established coordinator vocabulary.** `project-rag`'s conditional policy maps directly to tiered-context-loading.md Tier-2 (code-shaped lookup when a RAG index is present). This is not a new concept introduced by the topology — the topology gives it a typed label. → `tiered-context-loading.md`.

**`context7` is `deferred`, not `conditional`.** It is a user-scope plugin (`context7@claude-plugins-official` in `settings.json` `enabledPlugins`), available fleet-wide by default rather than added per-project — the harness registers its server by name only and defers schema load until `ToolSearch` surfaces intent, the same mechanism as `example-game-repo-control` (§ "Deferral is the harness's job" below). Usage doctrine lives in `~/.claude/rules/context7.md`.

**`example-game-repo-control`'s `deferred` policy and `settings.json` plugin-gating are two DISTINCT, non-substitutable mechanisms, not one enforcing the other.** Verified 2026-07-27: `example-game-repo-control` is registered at **user scope** in `~/.claude.json`'s top-level `mcpServers` block, not in any plugin `.mcp.json` — the server connects in EVERY session regardless of `enabledPlugins` state. `per-project-plugin-gating.md`'s `enabledPlugins` gate does real work, but a *different* job: it suppresses the plugin's **agents, skills, and their description tokens** from discovery on non-UE projects. It cannot suppress a user-scope MCP server's tool surface — that surface is present whether or not the gate fires. What actually keeps the 170 tools cheap is a **harness behaviour**, not `settings.json`: the harness registers every server's tools by name only and defers schema loading until `ToolSearch` surfaces intent. The topology's `deferred` label names that harness-level load posture as a typed fact; `settings.json` plugin-gating is a separate, narrower control over discovery of the plugin's own agents/skills. Neither substitutes for the other. → `per-project-plugin-gating.md`.

### Deferral is the harness's job; promotion is the agent's

The harness registers every MCP server's tools by name at session start and defers their schemas — schemas are the expensive part, names are cheap. This is the mechanism the whole plugin now depends on, so it is worth stating generally rather than only in the example-game-repo-specific paragraph above.

An agent creates asymmetry with the EM purely via its own `tools:` frontmatter array, which promotes named tools to always-on (schema-loaded, no `ToolSearch` round-trip) for that agent specifically. The EM carries no such frontmatter and pays the `ToolSearch` round-trip like any other undeferred consumer — this is deliberate, not an oversight: the EM deliberately does not get that promotion (source: `example-game-workbench-repo/docs/wiki/primitives-vs-recipes.md`).

**That promotion narrows; it never widens.** A `tools:` allowlist is an allowlist over what the dispatching session could already reach — no dispatched agent reaches a tool the EM could not have reached. "EM sees 4, worker sees 50" is therefore not implementable; the only reachable shape is "EM sees 50 deferred names, worker is allowlisted to the 50." The consequences for tool-glut design — and why hiding tools from the EM is the wrong lever — are in `mcp-tool-glut-defer-dont-hide.md`.

**Hard limitation: plugin subagents do NOT support the `mcpServers` frontmatter field — the harness ignores it.** This applies to any agent loaded from a plugin's `agents/` directory, which is all of `coordinator/agents/`; it does not apply to `.claude/agents/` or `~/.claude/agents/`. So inline-`mcpServers` isolation is unavailable to any coordinator agent — the `tools:` allowlist plus harness-level deferral is the only mechanism actually available to narrow a coordinator agent's tool surface.

A 3-proxy "collapse" (example-game-repo's `execute_domain_tool` / `manage_<domain>` / server-side `search_tools`) further shrinks the allowlist an agent needs to declare, but it requires the MCP server itself to expose gateway verbs — available only for servers coordinator owns, not for third-party servers like Atlassian or Google Drive, where agents must enumerate the tools they need explicitly instead.

---

## 4. Shape-Spec vs. Queryable Record Type

`mcp-topology.yaml` is **not** a `schemas/` entry. This distinction is load-bearing.

All 26 files under `schemas/` are **record-collection frontmatter validators**: each declares `applies_to:` and `kind:` values that claude-klabauter `coordinator/bin/query-records.js` uses to route queries across a collection of many same-kind YAML records (handoffs, plans, lessons, improvement-queue entries). `bin/verify-schema-registry-sync.py` line 129 makes this contract explicit — schemas without an `applies_to:` key are skipped entirely, because without it they cannot participate in the `query-records.js` dispatch surface.

`mcp-topology.yaml` is categorically different: it is a **body-shape spec for a single declaration file** — there is only ever one topology file, not a collection. It describes the structure of its own body, not the frontmatter of a record set. Adding it to `schemas/` would misuse the schemas/ machinery (which is keyed by collection cardinality and `applies_to:/kind:` routing) for an object of an entirely different kind.

If future work requires querying topology entries as records, a new query-records type would be appropriate — but that is a separate decision, not a default from current schemas/ placement.

---

## 5. Runtime Enforcement Is Deferred — The Future Seam

This file is **declaration + doctrine only**. No coordinator-owned *load-policy loader* exists today. MCP loading is handled entirely by the Claude Code harness + per-project `.mcp.json` + `settings.json` plugin-gating (→ `per-project-plugin-gating.md`). The topology is what the EM reads to understand load posture; it is not what the harness reads to enforce it.

Building a loader that honors `loadPolicy` speculatively is **YAGNI** — the harness already controls loading, and the topology gives the EM the typed view it needs to reason about that loading without a custom enforcement layer.

**What runtime enforcement would attach to, if it were ever built:**

A future runtime enforcement layer would read `mcp-topology.yaml`, resolve each `configKey` against the active `.mcp.json`, and assert that each server's *declared* load policy matches its *registered* one — that no server declared `deferred` or `conditional` has been registered `eager`. It would fire at the same point as the existing SessionStart hooks (`coordinator/hooks/scripts/`), after the harness has resolved the MCP server list but before the first tool call. The topology's `loadPolicy` field is the seam a future plan would attach to.

**What that layer must NOT assert: that a `deferred` server's tools are absent from the active tool surface.** They are present, by name, by design — that is what deferral *is* (§ 3). An absence assertion would fail on every correctly-configured session, and the natural "fix" for it is server-side tool hiding, which example-game-repo built, shipped, and deleted. → `mcp-tool-glut-defer-dont-hide.md`.

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

**`deferred` is the harness's default and costs nothing to get — so the tool count is not the thing to weigh.** Deferral is unconditional and not size-gated (measured across six connected servers, 2 to ~37 tools: all name-only). What is genuinely always-on per server is its **`instructions` block**, which is fully resident, unbounded, and written by the server author — a 4-tool server with a long instructions block costs more than a 50-tool server with none. Read that block before adding a server, and record its rough size in `notes:`. Full cost table and the `/context` measurement recipe: `mcp-tool-glut-defer-dont-hide.md § Turning servers back on`.

---

## 8. Own-Declaration Model for Consumers

**`coordinator/mcp-topology.yaml` is the coordinator plugin's own instance — it is NOT shared substrate for percolation.**

The declaration file is excluded from the OSS percolation path (`.percolate-ignore` entry). It references operator-specific and other-plugin servers (`example-game-repo-control`, `notebooklm-mcp`) that are coordinator-author-specific and must not land in the OSS `coordinator-claude` publish tree. The `the (now-removed) meta-repo local-doctrine file` editorial principle applies: these server entries are contingent on infrastructure the OSS user does not have.

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
- **`project-rag`** and **`notebooklm-mcp`** are raw per-project MCP servers loaded directly via `.mcp.json` — they are NOT gated via `enabledPlugins`. Their `optOutUnit` equals the server key (`project-rag`, `notebooklm-mcp` respectively); removing from `.mcp.json` is the opt-out mechanism. `notebooklm-mcp` (jacob-bd/gemini-notebook-mcp-cli, v0.9.8) is the external, user-installed replacement for the retired vendored NotebookLM server — the user registers it themselves via `nlm setup add claude-code`, so it is absent from a session entirely until installed, exactly like `project-rag`.
- **`context7`** is a third, distinct shape: a user-scope plugin (`context7@claude-plugins-official`), enabled fleet-wide by default. Its opt-out is two-tier: the `settings.json` `enabledPlugins` gate for `context7@claude-plugins-official` (unlike `example-game-repo-control`'s gate, this one DOES drop the tool surface, because the server itself comes from the plugin rather than being registered independently at user scope), plus a finer per-project `disabledMcpServers` entry naming `plugin:context7:context7` — this repo uses the latter.

This distinction matters when an agent needs to understand what to disable: for plugin-gated servers, the `enabledPlugins` key is the correct surface; for raw MCP servers, the `.mcp.json` key is. → `per-project-plugin-gating.md`.

**`notebooklm-mcp`'s upstream `pipeline` tool is deliberately unwired.** coordinator orchestrates via Agent Teams; a second in-MCP workflow engine (`pipeline`) is a competing routing layer, deliberately not surfaced. A future reader hitting `pipeline` in an upstream bump should find the reasoning here rather than re-litigating it.

---

## 10. `~/.claude.json` `mcpServers` Is Login-Identity-Scoped

`~/.claude.json` holds one `oauthAccount`/`userID` plus one top-level `mcpServers` block, and that block is **scoped to the active login**. Hot-swapping accounts on one machine therefore drops all *locally-installed* MCP registrations — the new login sees an empty (or different) `mcpServers`. Server-side claude.ai MCPs are immune (they ride the account, not the local file); only the locally-registered `.mcp.json`-class servers vanish.

**Heal at the DoE/host layer, never per-consumer.** The fix is a host-owned `ensure-local-mcps` SessionStart hook that reconciles the active `mcpServers` block against a `machine-local/always-on-mcps.json` manifest — re-registering anything the account swap dropped. Do NOT patch this per-project or by hand-editing `settings.json`. SessionStart hooks wire via `coordinator/hooks/hooks.json` → `gen-settings-hooks.py` regeneration, not by editing the generated `settings.json` directly.

This is orthogonal to `loadPolicy` (§ 3): load-policy governs *when* a declared server loads; identity-scoping governs whether the registration *survives an account swap* at all. A `deferred` server that was correctly registered still disappears from `mcpServers` on login change — the host-layer heal is what restores it.

*Source: MCP-registration-drift-on-account-swap.*
