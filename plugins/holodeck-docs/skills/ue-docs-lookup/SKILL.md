---
name: ue-docs-lookup
description: "This skill should be used when the user asks about Unreal Engine APIs, classes, functions, Blueprint nodes, UE5 systems, gameplay frameworks, or needs UE code examples. Activates for questions mentioning \"Unreal Engine\", \"UE5\", \"UE4\", \"Blueprint\", UE class names (AActor, UCharacterMovementComponent, UAbilitySystemComponent), or UE concepts (GAS, Enhanced Input, CMC, replication, Slate, UMG). Also activates when the user says \"look up\", \"check the UE docs\", \"what does UE say about\", \"ask holodeck\", or \"use holodeck\". This skill handles factual lookups — architecture and design decisions should go to Sid (game-dev plugin) instead."
---

# UE Documentation Lookup

When an Unreal Engine question is detected, use the holodeck-docs MCP tools to fetch current, authoritative documentation rather than relying on training knowledge. The holodeck-docs server indexes 333K+ chunks from UE C++ headers, Epic documentation, sample projects, expert Q&A, and curated cheatsheets.

## Routing Decision

Choose the right approach based on the question type:

| Question Type | Example | Action |
|---------------|---------|--------|
| Exact API lookup | "What are the params of SetMovementMode?" | Call `mcp__holodeck-docs__quick_ue_lookup` directly |
| Class/method signature | "Show me AActor::BeginPlay declaration" | Call `mcp__holodeck-docs__lookup_ue_class` directly |
| Simple code example | "Show me UE's built-in movement modes" | Call `mcp__holodeck-docs__ue_expert_examples` directly |
| Multi-source code example | "How to set up a GAS ability with cooldowns" | Dispatch `ue-docs-researcher` agent (needs examples + class lookups) |
| Pre-presentation code check | (Before showing generated UE code to user) | Call `mcp__holodeck-docs__check_ue_patterns` proactively |
| Multi-step research | "How does Enhanced Input handle action mappings?" | Dispatch `ue-docs-researcher` agent (context isolation) |
| Broad exploration | "What systems does UE provide for AI?" | Dispatch `ue-docs-researcher` agent |
| Architecture decision | "Should I use GAS or roll my own?" | Dispatch **Sid** (`game-dev:staff-game-dev`) — NOT the researcher |
| Code review | "Review my character movement implementation" | Dispatch **Sid** — the researcher is for lookups, not reviews |
| Python execution task | "List all materials using Texture_Rock via Python" | Dispatch `ue-python-executor` agent — see `python-execution-routing` skill |
| Destructive Python | "Delete all empty actors" | Dispatch `ue-python-executor` with "draft for review" |
| Simple Python script | `print(unreal.EditorLevelLibrary.get_all_level_actors())` | Call `mcp__holodeck-control__execute_python_code` directly |

**Rule of thumb:** If the answer requires a single tool call, call the tool directly. If it requires multiple calls or synthesis, dispatch the `ue-docs-researcher` agent to keep raw results out of the main context. For Python execution tasks, see the `python-execution-routing` skill for detailed routing.

## Tool Quick Reference

| Tool | Purpose | Speed |
|------|---------|-------|
| `mcp__holodeck-docs__quick_ue_lookup` | **Default first choice.** Fast factual lookup + API validation (73K declarations) | <1s |
| `mcp__holodeck-docs__lookup_ue_class` | Exact class/method declarations by name | 1-3s |
| `mcp__holodeck-docs__ue_expert_examples` | Expert Q&A pairs + production code examples from Lyra, etc. | 1-3s |
| `mcp__holodeck-docs__search_ue_docs` | Browse by category (`cpp`/`blueprint`/`cheatsheet`) and source type | 1-3s |
| `mcp__holodeck-docs__check_ue_patterns` | Proactive anti-pattern detection on generated code | 1-3s |
| `mcp__holodeck-docs__ask_unreal_expert` | DISABLED — blocked via settings.json (v2 LLM unreliable, re-enable when v3 ships) | — |

## Important Notes

- **Do not call any single tool more than 2-3 times per question.** If results are unsatisfactory, try a different tool rather than retrying the same one.
- **Prefer `quick_ue_lookup` as the first tool** for any factual question. It's the fastest and includes API existence validation.
- **`ask_unreal_expert` is globally disabled** (blocked via `permissions.deny` in settings.json). Do not attempt to call it.
- **Context7 covers upstream libraries** (ChromaDB, FastMCP, etc.) but has zero UE coverage. Always use holodeck-docs for UE questions.
- **For architecture and design questions**, dispatch Sid via the game-dev plugin. The researcher and this skill are for factual lookups, not design judgment.
