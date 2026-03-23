---
name: python-execution-routing
description: "This skill should be used when the user wants to execute Python code in Unreal Engine Editor, automate UE tasks via Python, batch-modify actors or assets with Python, or mentions \"execute_python_code\", \"run Python in UE\", \"UE Python automation\". Also activates when the user says \"run this in the editor\", \"execute this script\", or describes an automation task that requires Python in UE. Do NOT activate for Python API documentation questions or UE Python API signature lookups — those route through ue-docs-lookup. This skill handles routing — deciding whether to dispatch the ue-python-executor agent or call execute_python_code directly."
---

# Python Execution Routing

When a Python execution task is detected in a UE context, use this routing table to decide how to handle it. The holodeck-control MCP server provides `execute_python_code` for safety-validated Python execution and the `ue-python-executor` Sonnet agent handles multi-step tasks autonomously.

## Routing Table

| Task Type | Example | Route To | Review Required? |
|-----------|---------|----------|-----------------|
| **Complex / multi-step** | "Batch-rename BP_Enemy actors and update all references" | Dispatch `ue-python-executor` agent | No (coordinator may optionally request draft) |
| **Investigative / read-only** | "List all materials using Texture_Rock" | Dispatch `ue-python-executor` agent | No |
| **Destructive (delete/destroy)** | "Delete all empty actors in the level" | Dispatch `ue-python-executor` with **"draft for review"** | **Yes** — review the agent's code before approving execution |
| **Project settings mutation** | "Change the default game mode to BP_MyGameMode" | Dispatch `ue-python-executor` with **"draft for review"** | **Yes** — CDO/settings mutations are hard to reverse |
| **Simple known script** | `print(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem))` | Call `mcp__holodeck-control__execute_python_code` directly | No |
| **Python API documentation** | "What parameters does EditorAssetLibrary.list_assets take?" | Dispatch `ue-docs-researcher` (NOT ue-python-executor) | No |
| **Architecture / design** | "Should I use Python or Blueprints for this workflow?" | Dispatch **Sid** (`game-dev:staff-game-dev`) | No |

**Rule of thumb:** If you already have the exact Python code, call `execute_python_code` directly. If the user describes a task that needs code to be written, dispatch the `ue-python-executor` agent.

## Dispatch Instructions

When dispatching the `ue-python-executor` agent, include clear instructions:

**For safe operations:**
> "Execute Python in UE: [task description]. Execute freely."

**For destructive/mutation operations:**
> "Execute Python in UE: [task description]. Draft the code for my review before executing."

The agent follows your dispatch instruction literally — it will either execute or draft based on what you tell it.

## Three Execution Modes

Users can configure different security postures. You don't need to ask — the default (First Officer) is the recommended mode.

| Mode | How It Works | Who It's For |
|------|-------------|--------------|
| **First Officer** (default) | You dispatch the `ue-python-executor` agent. Agent does RAG + code + execution. You review destructive ops. | Default — recommended |
| **Direct** | Any agent calls `execute_python_code` directly. Blocklists still protect against crashes and exploits. | Power users comfortable with git-based rollback |
| **Guardrail** (opt-in) | A PreToolUse hook fires on every `execute_python_code` call, checking that `verified_apis` is populated. Enable in `.claude/settings.json`. | Users who want forced RAG verification on all calls |

### Security Posture

| Mode | Blocked Patterns | RAG Verification | Destructive Op Check | Residual Risk |
|------|-----------------|-------------------|---------------------|---------------|
| First Officer | Yes (blocklists) | Agent does organically | Agent follows your dispatch instruction | Low |
| Direct | Yes (blocklists) | None | None | **Medium** (destructive-but-valid code passes, e.g. `destroy_actor`) |
| Guardrail | Yes (blocklists) | Hook-enforced | None | Medium (API correctness enforced, destructive ops not) |

**Blocklists are the security boundary.** They prevent crashes (EdGraphPinType, CDO mutation, infinite loops) and exploits (os, subprocess, eval/exec). They do NOT prevent destructive-but-valid UE operations like deleting assets. That protection comes from your judgment when dispatching with "draft for review."

## Important Notes

- The `ue-python-executor` agent loads the `python-execution` skill via the holodeck-control MCP tool `manage_skills` to get crash patterns and safe API examples. You don't need to provide this context — the agent handles it.
- If the agent fails after 3 retries, it returns all attempted code and the last error for your manual review.
- If the holodeck-control MCP server is not running (UE Editor not open), execution is not possible. The agent will report this immediately.
