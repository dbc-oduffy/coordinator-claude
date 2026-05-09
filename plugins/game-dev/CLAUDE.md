# Game Dev Plugin

## UE Documentation

**Full tool hierarchy and retrieval strategy:** See the **holodeck-docs** plugin CLAUDE.md. That plugin owns the documentation lookup workflow (10 tools, 421,935 vectors, hybrid BM25+semantic search).

**Quick reference** (tool names for inline use):

| Tool | Purpose |
|------|---------|
| `mcp__holodeck-docs__quick_ue_lookup` | Fast factual lookup + API validation (73K declarations) |
| `mcp__holodeck-docs__lookup_ue_class` | Exact class/method signatures by name |
| `mcp__holodeck-docs__ue_expert_examples` | Expert Q&A + production code examples |
| `mcp__holodeck-docs__search_ue_docs` | Browse by category and source type |
| `mcp__holodeck-docs__check_ue_patterns` | Anti-pattern check on generated code |
| `mcp__holodeck-docs__get_session_primer` | Session-start priming with project context |
| `mcp__holodeck-docs__ue_mcp_status` | Health check: vector store, cache stats |
| `mcp__holodeck-docs__find_symbol` | Go-to-definition: symbol location + signature by name |
| `mcp__holodeck-docs__search_symbols` | Workspace symbol search: prefix match with kind/authority filters |
| `mcp__holodeck-docs__document_symbols` | File outline: all symbols defined in a source file |

**Context7 supplements** for non-UE-internal questions:
- Vanilla C++ → `/websites/en_cppreference_w`
- UE system overviews + Blueprint → `/websites/dev_epicgames_en-us_unreal-engine`
- GAS deep-dive → `/tranek/gasdocumentation`
- UE C++ patterns → `/mrrobinofficial/guide-unrealengine`

## Sid's Role

Sid (this plugin's agent) is the **architect and reviewer** for game development work. He uses holodeck-docs MCP tools as part of deeper analysis — design decisions, code review, anti-pattern recognition, architecture recommendations.

For **simple documentation lookups** that don't need Sid's judgment, use the `ue-docs-researcher` agent from the holodeck-docs plugin instead. It's a Sonnet subagent optimized for fast, context-isolated doc retrieval.

**Routing rule:** Architecture and design → Sid. Factual lookups and doc retrieval → ue-docs-researcher.

## UE Editor Authoring (holodeck-control)

When holodeck-control MCP is connected, agents have access to UE editor authoring tools:

| Category | Tools |
|----------|-------|
| Blueprints | `manage_blueprint`, `manage_blueprint_debug` |
| Actors & Levels | `control_actor`, `manage_level`, `manage_level_structure` |
| Materials | `manage_material_authoring`, `manage_texture` |
| Animation | `manage_skeleton`, `animation_physics` |
| Landscape | `build_environment` |
| Python | `execute_python_code`, `manage_script` |
| Skills | `manage_skills` |

All tool names use the `mcp__holodeck-control__` prefix (with hyphens — the underscore variant does not resolve).

### Domain Skills Protocol

Before starting UE authoring work, follow this protocol to load operational knowledge:

1. **Suggest:** Call `manage_skills` with `action: "suggest"` and a description of the task. The server returns relevant skill names.
2. **Load:** Call `manage_skills` with `action: "load"` and the skill name. Returns operational knowledge (workflows, gotchas, critical rules) plus tool schemas for the domain.
3. **Re-load after compaction:** Skills are delivered as ephemeral tool responses — they leave context when compacted. Re-load if you lose skill context mid-task.

Skills are demand-loaded to keep context lean. Do not skip the suggest step — it catches cross-domain relevance you might miss.
