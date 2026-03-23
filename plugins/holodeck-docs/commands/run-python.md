---
description: Execute Python code in UE Editor via holodeck-control MCP server
allowed-tools: ["Agent", "ToolSearch"]
argument-hint: <python code or task description>
---

# /holodeck-docs:run-python

Executes Python in Unreal Engine Editor via the holodeck-control MCP server. Validates code against crash and security blocklists before execution.

## Usage

```
/holodeck-docs:run-python <python code or task description>
```

## Routing

- **If the argument contains actual Python code** (has `import unreal`, `unreal.*` calls, `print()`, assignment operators, etc.) → Call `mcp__holodeck-control__execute_python_code` directly with the code.

- **If the argument describes a task** in natural language (e.g., "list all static mesh actors", "rename BP_Enemy to BP_Hostile") → Dispatch the `ue-python-executor` agent to write and execute the code.

## Examples

Direct code execution:
```
/holodeck-docs:run-python import unreal; print(unreal.EditorLevelLibrary.get_all_level_actors())
```

Task dispatch:
```
/holodeck-docs:run-python list all materials that reference Texture_Rock
/holodeck-docs:run-python rename all BP_Enemy actors to BP_Hostile
/holodeck-docs:run-python count static mesh actors by mesh type
```

## Notes

- Code is validated against crash and security blocklists before reaching UE. Blocked patterns (e.g., `import os`, `subprocess`, `while True:` without break) return an error with an explanation.
- For destructive operations (delete, destroy), consider using the `ue-python-executor` agent with "draft for review" to inspect the code before execution.
- Requires UE Editor running with the ClaudeUnrealHolodeck plugin loaded.
