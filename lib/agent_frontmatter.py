"""coordinator/lib/agent_frontmatter.py — shared parser for Claude agent
`.md` definition files: frontmatter/body split, `tools:` frontmatter
parsing, declared-mcp-tool extraction, and ToolSearch `select:` bootstrap
detection.

WHY THIS EXISTS. `coordinator/tests/test_agent_mcp_tool_adoption.py` and
`coordinator/tests/test_agent_tools_no_phantom_tools.py` both parsed the
same agent-frontmatter shape independently — two hand-rolled copies of one
parser, in one repo. project-rag has already landed a third hand-rolled
copy as an interim measure for its own `plugin/agents/` gate, explicitly
marked replaceable; example-game-repo would make a fourth independent copy the next
time it needs the same gate coverage. This module is the shared
implementation both of DoE's own gates now import, and the one a consumer
repo's own gate should import instead of re-deriving.

CROSS-REPO IMPORT. This file lives under the coordinator plugin's own
`lib/` — the same live-resolved-from-source tree every other doctrine
surface in this repo resolves through (see `coordinator/agents/
prior-art-checker.md` § Bootstrap item 3 for the canonical FAIL-LOUD
`_content_root` / `CLAUDE_PLUGIN_ROOT` resolution a consumer script should
reuse to find this file). A consumer repo's own gate resolves the
coordinator root the same way, then loads this module via
`importlib.util.spec_from_file_location` (see
`coordinator/tests/test_agent_tools_no_phantom_tools.py` for the pattern
this repo's own tests use) — never vendors a copy of the parsing logic.

Spec backlink: cross-repo/inbox/2026-07-28-project-rag-em-agent-frontmatter-parse-gate-duplication.md
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

FRONTMATTER_DELIM = "---"

TOOLS_LINE = re.compile(r"^tools:\s*(.+)$", re.MULTILINE)

# Matches the value portion of a ToolSearch `select:` bootstrap query, e.g.
# `select:mcp__foo__bar,mcp__foo__baz` inside a quoted string.
SELECT_RE = re.compile(r"select:([A-Za-z0-9_,\-]+)")


def agent_files(dirs: Iterable[Path]) -> list[Path]:
    """Every `*.md` file across a directory list, sorted per-directory, de-duplicated
    across directories, silently skipping any directory that doesn't exist."""
    files: dict[Path, None] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            files.setdefault(f)
    return list(files)


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split a `.md` agent file into (frontmatter, body) on the `---` fence.
    Returns `("", text)` when there's no opening fence or it's unterminated."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != FRONTMATTER_DELIM:
        return "", text
    for i in range(1, len(lines)):
        if lines[i].strip() == FRONTMATTER_DELIM:
            frontmatter = "".join(lines[: i + 1])
            body = "".join(lines[i + 1 :])
            return frontmatter, body
    # Unterminated fence -- treat the whole file as frontmatter-less body.
    return "", text


def parse_tools_line(raw: str) -> list[str]:
    """Parses either a quoted YAML array (`["Read", "Bash"]`) or an unquoted
    comma-separated string (`Read, Write, Bash`)."""
    value = raw.strip()
    if value.startswith("["):
        inner = value.strip("[]")
        entries = [e.strip().strip("'\"") for e in inner.split(",")]
    else:
        entries = [e.strip().strip("'\"") for e in value.split(",")]
    return [e for e in entries if e]


def declared_tools(frontmatter: str) -> list[str]:
    """`[]` when the file has no `tools:` key -- a valid, unrestricted-surface shape,
    not an error."""
    match = TOOLS_LINE.search(frontmatter)
    if match is None:
        return []
    return parse_tools_line(match.group(1))


def declared_mcp_tools(frontmatter: str) -> list[str]:
    """The `mcp__*`-prefixed subset of `declared_tools`."""
    return [t for t in declared_tools(frontmatter) if t.startswith("mcp__")]


def bootstrap_tool_names(body: str) -> set[str]:
    """Only the BODY is scanned, never the frontmatter."""
    names: set[str] = set()
    for match in SELECT_RE.finditer(body):
        names.update(name for name in match.group(1).split(",") if name)
    return names
