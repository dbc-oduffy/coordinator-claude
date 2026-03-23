---
name: ue-editor-control
description: "This skill should be used when the user wants to perform any operation in the Unreal Engine editor. Triggers on UE editor actions: \"spawn actor\", \"build environment\", \"create level\", \"set up lighting\", \"edit blueprint\", \"create blueprint\", \"wire pins\", \"configure combat\", \"add navigation\", \"set material\", \"place volume\", \"create widget\", \"set up AI\", \"manage sequence\", \"run PIE\", \"take screenshot\", \"profile level\", \"run tests\", \"delete actor\", \"move actor\", \"duplicate\", \"add component\", \"set up replication\", or any request involving the holodeck-control MCP tools. Routes to either direct tool use (thin MCP) or domain-specific agents based on operation type and complexity."
---

# UE Editor Control — Routing Table

To handle a UE editor operation, choose between direct action (thin MCP tools in hand) and delegation (domain agents).

## Direct Action — Tools You Have

These tools are always available. Use them for quick actions and fact-finding without delegating.

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `mcp__holodeck-control__execute_python_code` | **Omni-tool.** Execute any UE Python API call | Quick one-liners, queries, bulk operations, anything the typed tools don't cover |
| `mcp__holodeck-control__inspect` | Inspect any UObject — properties, components, class hierarchy | "What is this actor?", "What components does it have?", state inspection |
| `mcp__holodeck-control__control_editor` | PIE start/stop, console commands, editor state | Play testing, running console commands, toggling editor modes |
| `mcp__holodeck-control__manage_viewport` | Screenshots, editor camera positioning | Visual inspection, capturing current state, repositioning view |
| `mcp__holodeck-control__system_control` | CVars, profiling, engine configuration | Changing engine settings, reading CVars, performance checks |

**Rule of thumb:** If you can do it in one Python line or one inspect call, just do it. Don't delegate what takes 5 seconds directly.

## Delegation — Domain Agents

For structured, multi-step operations that benefit from typed tools and domain knowledge, delegate to the appropriate agent.

### ue-world-builder — Environment & Level Design

**Delegate when:** Building or modifying the physical environment — landscapes, lighting setups, procedural geometry, level streaming, volumes, splines, navigation meshes.

**Examples:**
- "Build a desert landscape with scattered rocks and foliage"
- "Set up three-point lighting for this interior scene"
- "Create a nav mesh for the arena level"
- "Add a blocking volume around the play area"
- "Create a spline-based road through the terrain"

**Cannot do via Python:** Complex landscape sculpting, geometry script operations, spline authoring workflows.

### ue-asset-author — Asset Creation & Editing

**Delegate when:** Creating or modifying assets — blueprints (especially graph operations), materials, textures, skeletal meshes, sequences, widgets.

**Examples:**
- "Create a door blueprint with open/close logic"
- "Rewire the health component to use the new damage interface" (BP graph manipulation)
- "Set up a PBR material with roughness and normal maps"
- "Create a HUD widget showing health and ammo"
- "Build a camera sequence for the intro cutscene"

**CRITICAL:** Blueprint graph operations (adding nodes, wiring pins, creating functions) MUST go through this agent — Python cannot manipulate BP graphs. If the user says "rewire X to Y" or "add a node that...", delegate here.

### ue-gameplay-engineer — Runtime Gameplay Systems

**Delegate when:** Setting up gameplay systems — spawning configured actors, character setup, combat, AI behavior, inventory, interactions, GAS abilities, VFX, input bindings.

**Examples:**
- "Spawn 5 enemy characters with patrol AI"
- "Set up a weapon with 50 damage and 2x headshot multiplier"
- "Create a GAS ability for a dash with cooldown"
- "Add interactive doors that open on overlap"
- "Set up an inventory system with 20 slots"

**Note:** Simple actor spawning (one actor, default config) can be done via Python directly. Delegate when the actor needs complex configuration through the typed tools.

### ue-infra-engineer — Infrastructure & Testing

**Delegate when:** Performance profiling, running automation tests, validation, networking setup, session management, game framework configuration, audio setup.

**Examples:**
- "Profile this level and identify bottlenecks"
- "Run all automation tests and report results"
- "Validate all assets in /Game/Weapons/"
- "Set up multiplayer replication for the inventory"
- "Configure the game mode and game state"

## Routing Decision Flow

```
UE editor request received
  │
  ├─ Tier 1 (Direct): Quick fact-finding / one-liner?
  │   → inspect / execute_python_code / manage_viewport / control_editor / system_control
  │
  └─ Tier 2 (Dispatch): Real work in a specific domain?
      ├─ Blueprint graph operation? → ue-asset-author (Python can't do graphs)
      ├─ Environment/level/terrain → ue-world-builder
      ├─ Assets/materials/BPs/widgets → ue-asset-author
      ├─ Gameplay/combat/AI/actors → ue-gameplay-engineer
      └─ Testing/perf/networking → ue-infra-engineer

For multi-domain tasks: decompose and dispatch domain agents sequentially
with verification between steps (same pattern as coordinator pipelines).
```

## Important Notes

- **Do not call domain MCP tools directly from the main conversation.** That defeats the purpose of context isolation. Delegate to the agent instead. Domain agents use `execute_domain_tool` to call hidden tools through the proxy.
- **Agents return synthesized results.** The raw MCP tool responses stay in the agent's context, not yours.
- **Python is always the escape hatch.** If an agent can't do something or you need a quick workaround, `execute_python_code` can reach any UE API.
- **This plugin is for *doing*, not *knowing*.** For UE documentation lookups (API signatures, engine concepts, "how does X work?"), use the holodeck-docs plugin (ue-docs-researcher agent or quick_ue_lookup tool). For architecture decisions ("should I use GAS?"), dispatch Sid via the game-dev plugin. These editor control agents execute operations — they don't research or advise.
