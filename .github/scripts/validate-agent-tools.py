#!/usr/bin/env python3
"""Validate that agent access-mode declarations are consistent with their tools lists.

read-only agents must not have Write, Edit, or Bash in their tools list,
and must have Read. read-write agents are unrestricted. Agents without
access-mode are skipped (backwards compatible).
"""

import sys
import pathlib
import yaml

PLUGINS_ROOT = pathlib.Path("plugins")

WRITE_TOOLS = {"Write", "Edit", "Bash"}

def validate_agent(path: pathlib.Path, errors: list):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return  # No frontmatter — not our concern here (validate-frontmatter handles it)

    parts = text.split("---", 2)
    if len(parts) < 3:
        return

    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        errors.append(f"{path}: YAML parse error: {e}")
        return

    if not isinstance(fm, dict):
        return

    access_mode = fm.get("access-mode")
    tools = fm.get("tools", [])
    if access_mode is None:
        if isinstance(tools, list) and len(tools) > 0:
            errors.append(
                f"{path}: has 'tools' but no 'access-mode' field — "
                f"add 'access-mode: read-only' or 'access-mode: read-write'"
            )
        return
    if not isinstance(tools, list):
        # validate-frontmatter will catch this; skip here
        return

    if access_mode == "read-only":
        # Must not have any write tools
        forbidden = WRITE_TOOLS & set(tools)
        if forbidden:
            errors.append(
                f"{path}: access-mode is 'read-only' but tools list contains "
                f"write-capable tools: {sorted(forbidden)}"
            )
        # Must have Read
        if "Read" not in tools:
            errors.append(
                f"{path}: access-mode is 'read-only' but 'Read' is missing from tools list"
            )
    elif access_mode == "read-write":
        pass  # No restrictions
    else:
        errors.append(
            f"{path}: unknown access-mode value '{access_mode}' "
            f"(expected 'read-only' or 'read-write')"
        )


def main():
    errors = []

    if not PLUGINS_ROOT.is_dir():
        print(f"Plugin root not found: {PLUGINS_ROOT}")
        return 1

    for plugin_dir in sorted(PLUGINS_ROOT.iterdir()):
        if not plugin_dir.is_dir():
            continue
        agents_dir = plugin_dir / "agents"
        if not agents_dir.is_dir():
            continue
        for agent_file in sorted(agents_dir.glob("*.md")):
            validate_agent(agent_file, errors)

    if errors:
        print("Agent tools validation FAILED:")
        for err in errors:
            print(f"  {err}")
        return 1

    print("Agent tools validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
