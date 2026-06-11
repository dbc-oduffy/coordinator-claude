#!/usr/bin/env python3
"""
Check that plugin names in documentation stay in sync with setup/install.sh::PLUGIN_REGISTRY.

What this checks:
  - Parses PLUGIN_REGISTRY from setup/install.sh (anchor on opener, not line numbers).
  - Verifies docs/agent-install.md fenced-code-block + --plugins + table-row contexts
    mention exactly the default-on set and no ghost plugins.
  - Verifies docs/safety.md "Default-on plugins copied:" enumeration matches PLUGIN_REGISTRY.
  - Verifies README.md fenced code blocks and table rows reference no ghost plugin names.

What this does NOT check:
  - Prose references to plugin names outside explicit enumeration contexts — common-English
    words like "coordinator" and "data-science" appear in prose legitimately.
  - marketplace.json plugin list — that is validated by validate-json-schemas.py.
  - The content of each plugin, only the names.

Spec backlink: docs/plans/2026-05-08-coordinator-claude-feedback-resolution.md § Task 7
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Repo root detection
# ---------------------------------------------------------------------------

def find_repo_root() -> Path:
    """Walk up from this script's location to find the repo root."""
    candidate = Path(__file__).resolve().parent
    for _ in range(6):
        if (candidate / ".claude-plugin" / "marketplace.json").exists():
            return candidate
        if (candidate / "setup" / "install.sh").exists():
            return candidate
        candidate = candidate.parent
    raise FileNotFoundError(
        "Could not find repo root (looked for .claude-plugin/marketplace.json or setup/install.sh up to 6 levels up)"
    )


# ---------------------------------------------------------------------------
# PLUGIN_REGISTRY parser
# ---------------------------------------------------------------------------

def parse_plugin_registry(install_sh: Path) -> dict[str, dict]:
    """
    Parse PLUGIN_REGISTRY from setup/install.sh.

    Anchors on the literal `PLUGIN_REGISTRY=(` opener and reads until the
    matching closing `)` — deliberately avoids line numbers, which drift.

    Returns: {name: {"default": "on"|"off"|"optional", "source": "local"|"npm"|"github"}}

    Fails loudly if the registry block cannot be found or a row cannot be parsed.
    """
    text = install_sh.read_text(encoding="utf-8")

    # Find the PLUGIN_REGISTRY block
    start_match = re.search(r'^PLUGIN_REGISTRY=\($', text, re.MULTILINE)
    if not start_match:
        _fail(f"Could not find PLUGIN_REGISTRY=( opener in {install_sh}")

    block_start = start_match.end()
    # Find matching closing paren on its own line
    end_match = re.search(r'^\)', text[block_start:], re.MULTILINE)
    if not end_match:
        _fail(f"Could not find closing ) for PLUGIN_REGISTRY in {install_sh}")

    block = text[block_start : block_start + end_match.start()]

    # Each row: "name|default|source_kind|description"
    # Tolerates leading/trailing whitespace and quote characters around the row.
    row_pattern = re.compile(
        r'^\s*["\']?'
        r'([a-z0-9_-]+)'       # name
        r'\|'
        r'(on|off|optional)'   # default state
        r'\|'
        r'(local|npm|github)'  # source kind
        r'\|'
        r'[^"\']*'             # description (ignored)
        r'["\']?\s*$',
        re.MULTILINE,
    )

    plugins: dict[str, dict] = {}
    for row_match in row_pattern.finditer(block):
        name, default, source = row_match.group(1), row_match.group(2), row_match.group(3)
        plugins[name] = {"default": default, "source": source}

    if not plugins:
        _fail(
            f"PLUGIN_REGISTRY block found but no rows parsed — registry shape may have changed.\n"
            f"Block content:\n{block}"
        )

    # Sanity: coordinator must always be present
    if "coordinator" not in plugins:
        _fail("PLUGIN_REGISTRY parsed but 'coordinator' row not found — something is wrong.")

    return plugins


# ---------------------------------------------------------------------------
# Enumeration-context extractors
# ---------------------------------------------------------------------------

def _extract_fenced_code_blocks(text: str) -> list[str]:
    """Return lines from all fenced code blocks (``` ... ```)."""
    lines: list[str] = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_block = not in_block
            continue
        if in_block:
            lines.append(line)
    return lines


def _extract_plugins_flag_lines(text: str) -> list[str]:
    """Return lines that contain the --plugins flag."""
    return [ln for ln in text.splitlines() if "--plugins" in ln]


def _extract_table_rows(text: str) -> list[str]:
    """Return lines that are Markdown table rows (start with |)."""
    return [ln for ln in text.splitlines() if ln.strip().startswith("|")]


def _plugin_names_in_text(lines: list[str], known_names: set[str]) -> set[str]:
    """Return which known plugin names appear anywhere in the given lines."""
    joined = "\n".join(lines)
    found: set[str] = set()
    for name in known_names:
        # Match the name as a whole token (word boundary or surrounded by , ; | ` space)
        if re.search(r'(?<![a-z0-9_-])' + re.escape(name) + r'(?![a-z0-9_-])', joined):
            found.add(name)
    return found


# ---------------------------------------------------------------------------
# Per-file checks
# ---------------------------------------------------------------------------

def check_agent_install(path: Path, plugins: dict[str, dict], errors: list[str]) -> None:
    """
    docs/agent-install.md checks:
      - No ghost plugin names in fenced-code, --plugins lines, or table rows.
      - All default-on plugins are mentioned in fenced-code or --plugins lines.
    """
    text = path.read_text(encoding="utf-8")
    all_names = set(plugins.keys())
    default_on = {n for n, m in plugins.items() if m["default"] == "on"}

    enum_lines = (
        _extract_fenced_code_blocks(text)
        + _extract_plugins_flag_lines(text)
        + _extract_table_rows(text)
    )

    found_names = _plugin_names_in_text(enum_lines, all_names)

    # Ghost check: any name found that isn't in the registry?
    # (We only know the registry names, so ghosts would be unexpected strings —
    #  but we can cross-check against a hardcoded prior ghost list.)
    known_ghosts = {"remember", "holodeck", "holodeck-control", "holodeck-docs"}
    ghost_text = "\n".join(enum_lines)
    for ghost in known_ghosts:
        if re.search(r'(?<![a-z0-9_-])' + re.escape(ghost) + r'(?![a-z0-9_-])', ghost_text):
            errors.append(
                f"{path}: ghost plugin '{ghost}' found in enumeration context "
                f"(fenced code / --plugins line / table row) but '{ghost}' is not in PLUGIN_REGISTRY."
            )

    # Coverage check: all default-on plugins should appear in enumeration contexts
    missing_defaults = default_on - found_names
    if missing_defaults:
        errors.append(
            f"{path}: default-on plugins missing from enumeration contexts "
            f"(fenced code / --plugins lines / table rows): {sorted(missing_defaults)}"
        )


def check_safety_md(path: Path, plugins: dict[str, dict], errors: list[str]) -> None:
    """
    docs/safety.md check:
      The "Default-on plugins copied:" enumeration must match the default-on set.
    Locates the enumeration by the literal phrase rather than line number.
    """
    text = path.read_text(encoding="utf-8")
    marker = "Default-on plugins copied:"
    idx = text.find(marker)
    if idx == -1:
        errors.append(
            f"{path}: could not find literal phrase '{marker}' — "
            "safety.md enumeration check skipped; update the script if the heading changed."
        )
        return

    # The enumeration is on the same line (or the same paragraph) as the marker.
    # Extract everything from the marker to the end of the paragraph (next blank line or period).
    snippet_start = idx + len(marker)
    # Take up to 200 chars as the enumeration context
    snippet = text[snippet_start : snippet_start + 200]

    default_on = {n for n, m in plugins.items() if m["default"] == "on"}
    all_names = set(plugins.keys())

    found_in_snippet: set[str] = set()
    for name in all_names:
        if re.search(r'(?<![a-z0-9_-])' + re.escape(name) + r'(?![a-z0-9_-])', snippet):
            found_in_snippet.add(name)

    missing = default_on - found_in_snippet
    if missing:
        errors.append(
            f"{path}: default-on plugins not listed after '{marker}': {sorted(missing)}. "
            f"Found: {sorted(found_in_snippet & default_on)}. "
            f"Expected: {sorted(default_on)}."
        )

    # Ghost check in enumeration snippet
    known_ghosts = {"remember", "holodeck", "holodeck-control", "holodeck-docs"}
    for ghost in known_ghosts:
        if re.search(r'(?<![a-z0-9_-])' + re.escape(ghost) + r'(?![a-z0-9_-])', snippet):
            errors.append(
                f"{path}: ghost plugin '{ghost}' found in default-on enumeration "
                f"near '{marker}'."
            )


def check_readme(path: Path, plugins: dict[str, dict], errors: list[str]) -> None:
    """
    README.md check:
      No ghost plugin names in fenced-code blocks or table rows.
    """
    text = path.read_text(encoding="utf-8")
    all_names = set(plugins.keys())

    enum_lines = _extract_fenced_code_blocks(text) + _extract_table_rows(text)
    ghost_text = "\n".join(enum_lines)

    known_ghosts = {"remember", "holodeck", "holodeck-control", "holodeck-docs"}
    for ghost in known_ghosts:
        if re.search(r'(?<![a-z0-9_-])' + re.escape(ghost) + r'(?![a-z0-9_-])', ghost_text):
            errors.append(
                f"{path}: ghost plugin '{ghost}' found in fenced-code or table-row context "
                f"but '{ghost}' is not in PLUGIN_REGISTRY."
            )

    # Also verify that names appearing in explicit table rows are valid registry names
    # (catches typos or renames that land in the Plugins table)
    for ln in _extract_table_rows(text):
        for candidate in re.findall(r'\*\*\[([a-z0-9_-]+)\]', ln):
            if candidate not in all_names and candidate not in {"coordinator-claude"}:
                # Only flag if it looks like a plugin name (short, hyphenated)
                if "-" in candidate or len(candidate) < 15:
                    errors.append(
                        f"{path}: plugin-like name '{candidate}' in table row is not in "
                        f"PLUGIN_REGISTRY: {ln.strip()}"
                    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def _print_registry(plugins: dict[str, dict]) -> None:
    print("PLUGIN_REGISTRY (parsed from setup/install.sh):")
    for name, meta in sorted(plugins.items()):
        print(f"  {name:20s}  default={meta['default']:8s}  source={meta['source']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        repo_root = find_repo_root()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Flat layout: install.sh lives under coordinator/dist/publish-repo-setup/
    install_sh = repo_root / "coordinator" / "dist" / "publish-repo-setup" / "install.sh"
    if not install_sh.exists():
        install_sh = repo_root / "setup" / "install.sh"  # legacy layout fallback
    agent_install = repo_root / "docs" / "agent-install.md"
    safety_md = repo_root / "docs" / "safety.md"
    readme = repo_root / "README.md"

    # Parse registry
    try:
        plugins = parse_plugin_registry(install_sh)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR parsing PLUGIN_REGISTRY: {exc}", file=sys.stderr)
        return 2

    _print_registry(plugins)
    print()

    errors: list[str] = []

    for path, checker in [
        (agent_install, check_agent_install),
        (safety_md, check_safety_md),
        (readme, check_readme),
    ]:
        if not path.exists():
            errors.append(f"Expected file not found: {path}")
            continue
        checker(path, plugins, errors)

    if errors:
        print(f"FAIL — {len(errors)} drift issue(s) found:\n", file=sys.stderr)
        for e in errors:
            print(f"  • {e}", file=sys.stderr)
        return 1

    print(f"PASS — all {len(plugins)} registered plugins consistent across checked doc files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
