#!/usr/bin/env python3
"""Validate YAML frontmatter in plugin command, skill, and agent files."""

import sys
import pathlib
import yaml

PLUGINS_ROOT = pathlib.Path(".")

# (glob pattern relative to plugin dir, required fields)
TARGETS = [
    ("commands/*.md", ["description", "allowed-tools"]),
    ("skills/*/SKILL.md", ["name", "description"]),
    ("agents/*.md", ["name", "description"]),
]

MEMORY_TYPE_VALUES = {"user", "feedback", "project", "reference"}

def validate_file(path: pathlib.Path, required_fields: list[str], errors: list):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        errors.append(f"{path}: missing frontmatter delimiter (must start with ---)")
        return

    parts = text.split("---", 2)
    if len(parts) < 3:
        errors.append(f"{path}: malformed frontmatter (missing closing ---)")
        return

    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        errors.append(f"{path}: YAML parse error: {e}")
        return

    if not isinstance(fm, dict):
        errors.append(f"{path}: frontmatter is not a mapping")
        return

    for field in required_fields:
        val = fm.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors.append(f"{path}: missing or empty required field '{field}'")

    if "allowed-tools" in fm:
        if not isinstance(fm["allowed-tools"], list):
            errors.append(f"{path}: 'allowed-tools' must be a YAML list")


def validate_memory_file(path: pathlib.Path, errors: list):
    """Validate memory file frontmatter with enum check on 'type'."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        errors.append(f"{path}: missing frontmatter delimiter (must start with ---)")
        return

    parts = text.split("---", 2)
    if len(parts) < 3:
        errors.append(f"{path}: malformed frontmatter (missing closing ---)")
        return

    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        errors.append(f"{path}: YAML parse error: {e}")
        return

    if not isinstance(fm, dict):
        errors.append(f"{path}: frontmatter is not a mapping")
        return

    for field in ("name", "description", "type"):
        val = fm.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors.append(f"{path}: missing or empty required field '{field}'")

    mem_type = fm.get("type")
    if isinstance(mem_type, str) and mem_type.strip() and mem_type not in MEMORY_TYPE_VALUES:
        errors.append(f"{path}: 'type' must be one of {sorted(MEMORY_TYPE_VALUES)}, got '{mem_type}'")


def main():
    errors = []

    if not PLUGINS_ROOT.is_dir():
        print(f"Plugin root not found: {PLUGINS_ROOT}")
        return 1

    for plugin_dir in sorted(PLUGINS_ROOT.iterdir()):
        if not plugin_dir.is_dir() or not (plugin_dir / ".claude-plugin").is_dir():
            continue
        for pattern, required in TARGETS:
            for path in sorted(plugin_dir.glob(pattern)):
                validate_file(path, required, errors)

    # Review: code-reviewer — validate_memory_file() previously had no call site (dead
    # code next to a comment excusing it). Wired in behind a glob guard mirroring
    # health-check.py's check_memory_consistency(): coordinator-claude itself ships no
    # memory files, but a consumer project layered on top of this repo may add
    # `projects/*/memory/*.md`, and this makes that case validated rather than silently
    # unchecked.
    for memory_file in sorted(pathlib.Path("projects").glob("*/memory/*.md")):
        validate_memory_file(memory_file, errors)

    if errors:
        print("Frontmatter validation FAILED:")
        for err in errors:
            print(f"  {err}")
        return 1

    print("Frontmatter validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
