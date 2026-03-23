#!/usr/bin/env python3
"""Validate that hook script paths in hooks.json resolve to existing files."""

import json
import re
import sys
import pathlib

PLUGINS_ROOT = pathlib.Path("plugins")

# Matches script paths after bash/sh/python/python3/node invocations, skipping flags.
# Review: Patrik — skip flags (e.g. `bash -e script.sh`) so we capture the script path, not the flag.
SCRIPT_PATH_RE = re.compile(r'(?:bash|sh|python3?|node)\s+(?:-\w+\s+)*(\S+)')

def resolve_script_path(command: str, plugin_dir: pathlib.Path) -> list[pathlib.Path]:
    """Extract and resolve script paths from a hook command string."""
    resolved = []
    for match in SCRIPT_PATH_RE.finditer(command):
        raw_path = match.group(1)
        # Replace the plugin root variable with the actual directory
        resolved_str = raw_path.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_dir))
        resolved.append(pathlib.Path(resolved_str))
    return resolved


def check_hooks_file(hooks_json_path: pathlib.Path, plugin_dir: pathlib.Path, errors: list):
    try:
        data = json.loads(hooks_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{hooks_json_path}: JSON parse error: {e}")
        return

    hooks_section = data.get("hooks", {})
    if not isinstance(hooks_section, dict):
        return

    for event_name, matchers in hooks_section.items():
        if not isinstance(matchers, list):
            continue
        for matcher_group in matchers:
            if not isinstance(matcher_group, dict):
                continue
            hook_entries = matcher_group.get("hooks", [])
            if not isinstance(hook_entries, list):
                continue
            for hook in hook_entries:
                if not isinstance(hook, dict):
                    continue
                if hook.get("type") != "command":
                    continue
                command = hook.get("command", "")
                script_paths = resolve_script_path(command, plugin_dir)
                for script_path in script_paths:
                    if not script_path.exists():
                        errors.append(
                            f"{hooks_json_path}: hook command references missing file: "
                            f"'{script_path}' (from command: '{command}')"
                        )


def main():
    errors = []

    if not PLUGINS_ROOT.is_dir():
        print(f"Plugin root not found: {PLUGINS_ROOT}")
        return 1

    for plugin_dir in sorted(PLUGINS_ROOT.iterdir()):
        if not plugin_dir.is_dir():
            continue

        # Check hooks/hooks.json first, then hooks.json at plugin root
        candidate_paths = [
            plugin_dir / "hooks" / "hooks.json",
            plugin_dir / "hooks.json",
        ]
        for hooks_path in candidate_paths:
            if hooks_path.exists():
                check_hooks_file(hooks_path, plugin_dir, errors)

    if errors:
        print("Hook path validation FAILED:")
        for err in errors:
            print(f"  {err}")
        return 1

    print("Hook path validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
