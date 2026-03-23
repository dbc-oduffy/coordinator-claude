#!/usr/bin/env python3
"""Check that README.md inventory counts match actual file counts in plugins."""

import re
import sys
import pathlib

PLUGINS_ROOT = pathlib.Path("plugins")

# Regex to find section headers with claimed counts, e.g.:
#   ### Commands (18)
#   ### Skills (20)
#   ### Agents (6)
# Review: Patrik — old regex \((\d+)\) required digits immediately inside parens,
# but README has e.g. "(18, all user-invocable via /)" — comma after digits broke match.
COUNT_RE = re.compile(r"^#{1,3}\s+(\w+).*\((\d+)\b", re.MULTILINE)

# Map from section name (lowercased) to glob pattern for actual file count
# Note: agents are validated only if the README uses `### Agents (N)` format.
SECTION_GLOBS: dict[str, str] = {
    "commands": "commands/*.md",
    "skills": "skills/*/SKILL.md",
    "agents": "agents/*.md",
    "pipelines": "pipelines/*/PIPELINE.md",
}

def check_plugin(plugin_dir: pathlib.Path, errors: list):
    readme = plugin_dir / "README.md"
    if not readme.exists():
        return

    text = readme.read_text(encoding="utf-8")
    matches = COUNT_RE.findall(text)

    for section_name, claimed_str in matches:
        key = section_name.lower()
        if key not in SECTION_GLOBS:
            continue  # Section we don't track — skip

        glob_pattern = SECTION_GLOBS[key]
        actual_files = list(plugin_dir.glob(glob_pattern))
        actual_count = len(actual_files)
        claimed_count = int(claimed_str)

        if claimed_count != actual_count:
            errors.append(
                f"{readme}: section '{section_name}' claims {claimed_count} but "
                f"actual count is {actual_count} (glob: {glob_pattern})"
            )


def main():
    errors = []

    if not PLUGINS_ROOT.is_dir():
        print(f"Plugin root not found: {PLUGINS_ROOT}")
        return 1

    for plugin_dir in sorted(PLUGINS_ROOT.iterdir()):
        if not plugin_dir.is_dir():
            continue
        check_plugin(plugin_dir, errors)

    if errors:
        print("README inventory check FAILED:")
        for err in errors:
            print(f"  {err}")
        return 1

    print("README inventory check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
