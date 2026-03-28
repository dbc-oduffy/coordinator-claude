# Holodeck-Docs Plugin

Wraps the holodeck-docs MCP server with context-efficient interaction layers for Unreal Engine documentation lookup.

<!-- Review: Patrik — cross-plugin runtime dependency was undocumented; agents need to know
     which features work standalone vs. which require holodeck-control. -->
**Runtime note:** Documentation features work standalone. Python execution features require the holodeck-control MCP server to be running (UE Editor open).

## UE Documentation Retrieval Hierarchy

When answering UE questions, follow this strategy in order:

1. **`mcp__holodeck-docs__quick_ue_lookup`** — Default first choice. Fast factual lookup + API validation against 73K known declarations. Use for any specific question.
2. **`mcp__holodeck-docs__ue_expert_examples`** — Expert Q&A pairs and production code examples (Lyra, sample projects). Use for "how should I..." and "show me an example of..." questions.
3. **`mcp__holodeck-docs__check_ue_patterns`** — Proactive anti-pattern check. Run on generated UE code BEFORE presenting it to the user.
4. **Context7 for C++ standard library** — Use `resolve-library-id` + `query-docs` for C++ stdlib questions (cppreference).
5. **`mcp__holodeck-docs__lookup_ue_class`** — Exact class/method signatures when you know the name. More precise than quick_ue_lookup but narrower.
6. **`mcp__holodeck-docs__search_ue_docs`** — Browse by category and source type. Use when exploring a topic area rather than answering a specific question.
7. **`mcp__holodeck-docs__get_session_primer`** — Session-start priming with project context. Call once at the beginning of a session with a project_context string describing the UE subsystems in use.

## Source Types

When using `search_ue_docs`, filter by source:

| Source | Content |
|--------|---------|
| `engine` | C++ headers from UE install |
| `samples` | Blueprint + code from sample projects (Lyra, etc.) |
| `expert` | Curated Q&A pairs (Sid + Patrik validated) |
| `community` | Community docs and tutorials |
| `cheatsheet` | Quick-reference guides |
| `notebooklm` | NotebookLM-generated summaries |

## Context Isolation

For multi-step lookups, dispatch the `ue-docs-researcher` agent (Sonnet) rather than calling tools directly. This keeps raw retrieval results out of the main conversation context — only the synthesized answer comes back.

**When to dispatch the researcher vs call tools directly:**
- Single focused lookup → call tool directly (cheaper, faster)
- Multi-step or synthesis needed → dispatch researcher (context isolation)
- Architecture/design questions → dispatch Sid (game-dev plugin), not the researcher

## Python Execution in UE Editor

For executing Python code in Unreal Engine, the plugin provides a parallel execution layer alongside the documentation layer:

| Component | Purpose |
|-----------|---------|
| `ue-python-executor` agent (Sonnet) | Autonomous Python execution: RAG lookup → code writing → execution → iteration |
| `python-execution-routing` skill | Auto-triggers on Python execution requests, provides routing table for coordinator |
| `/holodeck-docs:run-python` command | Manual invocation: code → direct execute, task → dispatch agent |

**Execution workflow:** The coordinator dispatches the `ue-python-executor` agent for complex tasks. The agent loads the `python-execution` MCP skill (via `manage_skills`) for crash patterns and safe API examples, verifies APIs via RAG, writes code, and executes via `mcp__holodeck-control__execute_python_code`. For destructive operations, the coordinator dispatches with "draft for review" so it can inspect the code before approval.

**For simple known scripts**, call `mcp__holodeck-control__execute_python_code` directly — no agent dispatch needed.

**Security:** Code is validated against crash and security blocklists before execution. Blocked: `import os`, `subprocess`, `open()`, infinite loops, CDO mutation, `EdGraphPinType()`, and more. The blocklists are the hard security boundary. Destructive-but-valid operations (deleting assets) are protected by the coordinator's judgment, not the blocklist.
