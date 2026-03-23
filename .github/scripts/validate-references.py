#!/usr/bin/env python3
"""Validate cross-file references: routing files, MEMORY.md links, and markdown links in plugins/docs."""

import re
import sys
import pathlib

LINK_RE = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')


def check_routing_files(errors: list):
    """Check that agent names in routing.md files have matching agent .md files."""
    # Collect all agent stems across all plugins for cross-plugin resolution
    all_agent_stems: set[str] = set()
    for pd in pathlib.Path("plugins").iterdir():
        if pd.is_dir() and (pd / "agents").is_dir():
            all_agent_stems.update(p.stem for p in (pd / "agents").glob("*.md"))

    for routing in pathlib.Path("plugins").rglob("routing.md"):
        plugin_dir = routing.parent
        agents_dir = plugin_dir / "agents"
        if not agents_dir.is_dir():
            continue

        text = routing.read_text(encoding="utf-8")
        existing_agents = {p.stem for p in agents_dir.glob("*.md")}

        # Track which agent stems are referenced in this routing file
        referenced_stems: set[str] = set()

        # Single pass: check `agents/foo.md` references AND **Backstop:** entries
        for line_num, line in enumerate(text.splitlines(), 1):
            for match in re.finditer(r'agents/([a-zA-Z0-9_-]+)\.md', line):
                stem = match.group(1)
                referenced_stems.add(stem)
                agent_file = agents_dir / f"{stem}.md"
                if not agent_file.exists():
                    errors.append(f"{routing}:{line_num}: broken agent reference '{match.group(0)}' — file not found")

            # Backstop chain validation: warn when **Backstop:** AgentName doesn't resolve
            # Names in routing may not exactly match filenames — fuzzy match against stems
            # Searches all plugin agent directories so cross-plugin references (e.g. game-dev
            # routing referencing "Patrik") resolve against coordinator agents correctly.
            for match in re.finditer(r'\*\*Backstop:\*\*\s+(\S+)', line):
                raw_name = match.group(1).rstrip(".,;)")
                # Collect all table-row agent names for orphan check too
                referenced_stems.add(raw_name.lower())
                # Convert name to kebab-case for fuzzy match attempt
                kebab = raw_name.lower().replace("í", "i").replace("ó", "o")
                found = any(
                    kebab in stem or stem in kebab or stem.startswith(kebab)
                    for stem in all_agent_stems
                )
                if not found:
                    print(
                        f"Warning: {routing}:{line_num}: backstop '{raw_name}' has no matching agent file",
                        file=sys.stderr,
                    )

        # Orphan agent warning: agent files not referenced by any routing table row
        for agent_stem in sorted(existing_agents):
            # Check if this stem appears in any agents/foo.md reference in routing
            if agent_stem not in referenced_stems:
                # Also check if the agent name appears anywhere in the routing text
                if agent_stem not in text.lower().replace("-", " ") and agent_stem not in text:
                    print(
                        f"Warning: {agents_dir / (agent_stem + '.md')} not referenced in any routing table",
                        file=sys.stderr,
                    )


def iter_lines_outside_code_blocks(text: str):
    """Yield (line_num, line) for lines NOT inside fenced code blocks."""
    in_code_block = False
    for line_num, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            yield line_num, line


def check_memory_links(errors: list):
    """Check that markdown links in MEMORY.md files resolve.

    coordinator-claude is a distribution package — no live memory files to check.
    This function is a no-op stub; extend it if you add a projects/ directory.
    """
    pass


def is_excluded_path(path: pathlib.Path) -> bool:
    """Skip upstream reference docs and bundled content we don't control."""
    parts = path.parts
    # Skip reference subdirectories (bundled upstream docs)
    if "references" in parts:
        return True
    # Skip known upstream files copied from Anthropic
    if path.name == "anthropic-best-practices.md":
        return True
    return False


def check_markdown_links(errors: list):
    """Check relative markdown links in plugins/ and docs/ directories.

    Skips plugins/cache/ (third-party plugins we don't control) and reference docs.
    """
    search_dirs = [pathlib.Path("plugins"), pathlib.Path("docs")]
    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for md_file in sorted(search_dir.rglob("*.md")):
            if is_excluded_path(md_file):
                continue
            text = md_file.read_text(encoding="utf-8")
            base_dir = md_file.parent
            for line_num, line in iter_lines_outside_code_blocks(text):
                for match in LINK_RE.finditer(line):
                    target = match.group(2)
                    if target.startswith(("http://", "https://", "#", "mailto:", "/")):
                        continue
                    target_path = target.split("#")[0]
                    if not target_path:
                        continue
                    # Skip markdown link-style references like [params]
                    if target_path.startswith("["):
                        continue
                    resolved = (base_dir / target_path).resolve()
                    if not resolved.exists():
                        errors.append(f"{md_file}:{line_num}: broken link '{target}' — target not found")


def main():
    errors = []

    check_routing_files(errors)
    check_memory_links(errors)
    check_markdown_links(errors)

    if errors:
        print("Reference validation FAILED:")
        for err in errors:
            print(f"  {err}")
        return 1

    print("Reference validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
