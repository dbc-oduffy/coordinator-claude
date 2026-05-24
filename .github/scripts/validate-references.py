#!/usr/bin/env python3
"""Validate cross-file references: routing files, MEMORY.md links, and markdown links in plugins/docs."""

import re
import sys
import pathlib

LINK_RE = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')

# Top-level directories in this publish repo. Resolved link targets whose
# first path component is not one of these are sibling-repo references
# (e.g. project-rag, project-rag-ue-addon) that exist in the source meta-repo
# layout but not here; skip rather than fail.
REPO_TOP_DIRS = {
    "archive", "assets", "cross-repo", "docs", "evals", "experiments",
    "plugins", "setup", "tasks", "tests", ".github",
}


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
            # routing referencing "the Staff Engineer") resolve against coordinator agents correctly.
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


# Addon-protocol wikis mirrored from the project-rag sibling repo. Their
# internal cross-links reference neighbor files in project-rag's wiki that
# aren't copied into this publish layout; the docs themselves are still
# useful here as addon-protocol reference. Skip link-validation on these.
ADDON_PROTOCOL_MIRROR_WIKIS = {
    "docs/wiki/addon-chunker-categories.md",
    "docs/wiki/addon-protocol.md",
    "docs/wiki/capability-dispatch.md",
    "docs/wiki/corpus-band-protocol.md",
    "docs/wiki/host-addon-separation-of-concerns.md",
    "docs/wiki/host-vs-addons.md",
}


def is_excluded_path(path: pathlib.Path) -> bool:
    """Skip upstream reference docs and bundled content we don't control."""
    parts = path.parts
    # Skip reference subdirectories (bundled upstream docs)
    if "references" in parts:
        return True
    # Skip known upstream files copied from Anthropic
    if path.name == "anthropic-best-practices.md":
        return True
    posix = path.as_posix()
    # Skip install-time rendered templates under plugins/coordinator/dist/publish-repo-*/.
    # Their relative links (docs/wiki/, setup/, etc.) resolve at the consumer's ~/.claude/
    # after setup/install.sh, not at publish time in this repo.
    if "/dist/publish-repo-" in posix or posix.startswith("plugins/coordinator/dist/publish-repo-"):
        return True
    # Skip addon-protocol mirror wikis (sibling-repo internal links).
    if posix in ADDON_PROTOCOL_MIRROR_WIKIS:
        return True
    return False


def check_markdown_links(errors: list):
    """Check relative markdown links in plugins/ and docs/ directories.

    Skips plugins/cache/ (third-party plugins we don't control) and reference docs.
    Skips links whose resolved target escapes the repo root — those reference
    sibling repos (e.g. project-rag, project-rag-ue-addon) that exist in the
    source meta-repo layout but not in this publish-repo's layout.
    """
    repo_root = pathlib.Path(".").resolve()
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
                    # Skip sibling-repo references — targets that either escape
                    # repo root via '..', or whose first path component is not
                    # a known top-level dir in this repo (e.g. '../../../../project-rag/...'
                    # collapses to '<repo>/project-rag/...' which doesn't exist here
                    # but resolves correctly in the source meta-repo layout).
                    try:
                        rel = resolved.relative_to(repo_root)
                    except ValueError:
                        continue
                    rel_parts = rel.parts
                    if rel_parts and rel_parts[0] not in REPO_TOP_DIRS:
                        continue
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
