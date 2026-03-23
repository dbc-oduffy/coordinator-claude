# Holodeck-Control Plugin

Context-efficient wrapper for the holodeck-control MCP server. Uses a two-tier dispatch model to reduce ~48K tokens of tool definitions to ~8 visible tools, while preserving full capability through the `execute_domain_tool` proxy.

## Design Rationale: Context-Efficient Delegation

Withholding tool schemas from the EM is a deliberate design choice with two benefits:

1. **Token savings (~40K):** The full holodeck-control tool catalog is ~48K tokens of JSON schema. The EM sees only 8 tool definitions (~8K tokens). Domain agents get full schemas loaded fresh in their dedicated context.
2. **Cognitive steering:** An EM with 200 tools in context gravitates toward direct execution. Thin tool visibility makes delegation the path of least resistance — the EM naturally routes to specialists rather than reaching for tools it can barely see.

The `execute_domain_tool` proxy is the bridge: domain agents use it to call any hidden tool by name with full parameter schemas in their context. The EM can use it too (it's visible), but would need to ToolSearch for schemas and lacks the domain agent's pre-loaded verification protocols and operational patterns — making delegation the higher-quality path.

This pattern is replicable: any MCP server with many tools can use the same thin-proxy + domain-agent architecture to keep the EM's context lean while preserving full capability through delegation.

## Architecture: Two-Tier Dispatch

```
                          EM (Opus coordinator)
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                        │
     Tier 1: Direct         Orchestrator            Tier 2: Dispatch
     (EM uses tool)      (Opus, read-only)        (EM → Sonnet agent)
          │               inspect + plan                   │
    thin MCP tools        returns specs             domain agent
    (8 in hand)           EM dispatches           (single-domain)
```

**Single-domain tasks:** EM dispatches the domain agent directly.
**Multi-domain / underspecified tasks:** EM dispatches the orchestrator (read-only planner) to get a structured execution plan, then dispatches domain agents sequentially per the plan, verifying between steps. The orchestrator cannot dispatch agents or mutate state — it inspects and plans only.

### Tier 1: Direct — Tools in Hand (Thin Mode)

Quick one-liners, fact-finding, simple mutations. No delegation overhead.

| Tool | Purpose |
|------|---------|
| `execute_python_code` | Omni-tool — any UE Python API call |
| `inspect` | UObject inspection — properties, components, class hierarchy |
| `control_editor` | PIE control, console commands, editor state |
| `manage_viewport` | Screenshots, camera positioning |
| `system_control` | CVars, profiling, engine configuration |
| `manage_tools` | Enable/disable tools at runtime (escape hatch: `reset` restores all) |
| `manage_skills` | Load domain-specific operational skills |
| `execute_domain_tool` | **Proxy:** call any hidden tool by name |

### Tier 2: Dispatch — Domain Agents (Precise Spec)

The EM defines the task precisely. The Sonnet agent executes and verifies.

| Agent | Model | Color | Role |
|-------|-------|-------|------|
| ue-project-orchestrator | Opus | red | **Read-only planner.** Inspects editor state, decomposes cross-domain/underspecified tasks into per-agent specs, returns execution plan. Cannot dispatch agents or mutate state. |
| ue-world-builder | Sonnet | green | Environment, levels, lighting, terrain, volumes, splines, navigation, PCG, instancing, collision |
| ue-asset-author | Sonnet | cyan | Blueprints (**graph ops — Python CANNOT do this**), materials, textures, widgets, sequences, movie render, media, data assets, data tables |
| ue-gameplay-engineer | Sonnet | yellow | Actors, combat, AI, GAS, inventory, VFX, input, checkpoints, quests, objectives, demo replay, localization |
| ue-infra-engineer | Sonnet | magenta | Performance, tests, networking, audio, game framework, scalability, accessibility, modding, build, subsystems |

**Orchestrator → EM → Domain agents.** The orchestrator plans; the EM dispatches; domain agents execute via `execute_domain_tool` proxy. Domain agents include verification protocols (inspect/screenshot) and return structured completion reports.

## Tool Visibility

Only 8 core tools are visible in the MCP `tools/list` response. All other tools are hidden and accessible only through the `execute_domain_tool` proxy (used by domain agents).

**Visible tools:** `inspect`, `control_editor`, `system_control`, `manage_viewport`, `execute_python_code`, `manage_tools`, `manage_skills`, `execute_domain_tool`

- **Debugging:** `manage_tools` can temporarily enable/disable individual tools or categories
- **Protected tools:** `manage_tools`, `inspect`, and `execute_domain_tool` cannot be disabled

## Routing

The `ue-editor-control` skill auto-triggers on UE editor intent and provides the routing table. The `/dispatch` command allows explicit manual routing to domain agents.

**Key routing rule:** Blueprint graph operations (add nodes, wire pins, create functions) MUST go through ue-asset-author — Python cannot manipulate BP graphs.

**Python is the escape hatch:** `execute_python_code` can reach any UE API. Use it for quick one-liners. Delegate to agents for multi-step structured operations.

## Relationship to holodeck-docs Plugin

This plugin handles **editor control** (doing things). The holodeck-docs plugin handles **documentation lookup** (knowing things). They're complementary:
- "How does GAS work?" → holodeck-docs (ue-docs-researcher)
- "Set up a GAS ability with cooldown" → holodeck-control (ue-gameplay-engineer)
- "Should I use GAS?" → game-dev plugin (Sid)
