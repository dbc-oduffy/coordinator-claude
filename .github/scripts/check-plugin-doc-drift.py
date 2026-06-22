#!/usr/bin/env python3
"""
Check that plugin names in documentation stay in sync with the marketplace registry
(.claude-plugin/marketplace.json).

What this checks:
  - Reads the plugin list from .claude-plugin/marketplace.json (the flat-layout source of
    truth; the legacy setup/install.sh::PLUGIN_REGISTRY no longer ships).
  - Verifies docs/agent-install.md fenced-code-block + --plugins + table-row contexts
    mention the default-on set and no ghost plugins.
  - Verifies docs/safety.md "Default-on plugins copied:" enumeration matches the default-on set.
  - Verifies README.md fenced code blocks and table rows reference no ghost plugin names.

Note: marketplace.json carries plugin names + sources but no install-default state, so the
documented recommended set (coordinator + deep-research, per the agent-install.md tier table)
is encoded below as DEFAULT_ON.

What this does NOT check:
  - Prose references to plugin names outside explicit enumeration contexts — common-English
    words like "coordinator" and "data-science" appear in prose legitimately.
  - marketplace.json plugin list — that is validated by validate-json-schemas.py.
  - The content of each plugin, only the names.

Spec backlink: docs/plans/2026-05-08-coordinator-claude-feedback-resolution.md § Task 7
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# Documented recommended ("default-on") set — coordinator (core) + deep-research
# (recommended), per the agent-install.md tier table. marketplace.json does not
# carry an install-default state, so it is encoded here.
DEFAULT_ON = {"coordinator", "deep-research"}


# ---------------------------------------------------------------------------
# Repo root detection
# ---------------------------------------------------------------------------

def find_repo_root() -> Path:
    """Walk up from this script's location to find the repo root."""
    candidate = Path(__file__).resolve().parent
    for _ in range(6):
        if (candidate / ".claude-plugin" / "marketplace.json").exists():
            return candidate
        candidate = candidate.parent
    raise FileNotFoundError(
        "Could not find repo root (looked for .claude-plugin/marketplace.json up to 6 levels up)"
    )


# ---------------------------------------------------------------------------
# Marketplace registry parser
# ---------------------------------------------------------------------------

def parse_marketplace(marketplace_json: Path) -> dict[str, dict]:
    """
    Read the plugin list from .claude-plugin/marketplace.json (the flat-layout
    source of truth; setup/install.sh::PLUGIN_REGISTRY no longer ships).

    The manifest carries name + source but no install-default state, so the
    documented recommended set (DEFAULT_ON) decides each plugin's "default" value.

    Returns: {name: {"default": "on"|"optional", "source": <relative path>}}

    Fails loudly if the manifest cannot be parsed or carries no plugins.
    """
    try:
        data = json.loads(marketplace_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        _fail(f"Could not read/parse {marketplace_json}: {exc}")

    plugins: dict[str, dict] = {}
    for entry in data.get("plugins", []):
        name = entry.get("name")
        if not name:
            continue
        plugins[name] = {
            "default": "on" if name in DEFAULT_ON else "optional",
            "source": entry.get("source", ""),
        }

    if not plugins:
        _fail(
            f"marketplace.json found but no plugins parsed — manifest shape may have changed: {marketplace_json}"
        )

    # Sanity: coordinator must always be present
    if "coordinator" not in plugins:
        _fail("marketplace.json parsed but 'coordinator' not found — something is wrong.")

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

    # Coverage uses ALL enumeration contexts (fenced code, --plugins lines, table rows).
    enum_lines = (
        _extract_fenced_code_blocks(text)
        + _extract_plugins_flag_lines(text)
        + _extract_table_rows(text)
    )
    found_names = _plugin_names_in_text(enum_lines, all_names)

    # Ghost check fires ONLY in actual install-command contexts (fenced code +
    # --plugins lines) — NOT descriptive table rows. A tier table that names an
    # excluded plugin ("specialized — not part of this install: holodeck") is correct
    # guidance, not a ghost; the hazard is a ghost in a real `claude plugin install` /
    # `--plugins` invocation, which these contexts catch.
    install_context_lines = (
        _extract_fenced_code_blocks(text) + _extract_plugins_flag_lines(text)
    )
    known_ghosts = {"remember", "holodeck", "holodeck-control", "holodeck-docs"}
    ghost_text = "\n".join(install_context_lines)
    for ghost in known_ghosts:
        if re.search(r'(?<![a-z0-9_-])' + re.escape(ghost) + r'(?![a-z0-9_-])', ghost_text):
            errors.append(
                f"{path}: ghost plugin '{ghost}' found in an install-command context "
                f"(fenced code / --plugins line) but '{ghost}' is not in the marketplace registry."
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

    # Ghost check fires only in fenced install-command blocks — NOT table rows or prose,
    # which legitimately name excluded/external plugins (e.g. an "other plugins worth
    # knowing" list linking clangd-lsp, or a tier table naming holodeck as excluded).
    ghost_text = "\n".join(_extract_fenced_code_blocks(text))

    known_ghosts = {"remember", "holodeck", "holodeck-control", "holodeck-docs"}
    for ghost in known_ghosts:
        if re.search(r'(?<![a-z0-9_-])' + re.escape(ghost) + r'(?![a-z0-9_-])', ghost_text):
            errors.append(
                f"{path}: ghost plugin '{ghost}' found in a fenced install-command block "
                f"but '{ghost}' is not in the marketplace registry."
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
    print("Plugins (parsed from .claude-plugin/marketplace.json):")
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

    marketplace_json = repo_root / ".claude-plugin" / "marketplace.json"
    agent_install = repo_root / "docs" / "agent-install.md"
    safety_md = repo_root / "docs" / "safety.md"
    readme = repo_root / "README.md"

    # Parse registry from the marketplace manifest
    try:
        plugins = parse_marketplace(marketplace_json)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR parsing marketplace.json: {exc}", file=sys.stderr)
        return 2

    _print_registry(plugins)
    print()

    errors: list[str] = []

    # (path, checker, required) — safety.md is optional (not present in the flat
    # marketplace layout); a missing optional file is skipped, not an error.
    for path, checker, required in [
        (agent_install, check_agent_install, True),
        (safety_md, check_safety_md, False),
        (readme, check_readme, True),
    ]:
        if not path.exists():
            if required:
                errors.append(f"Expected file not found: {path}")
            else:
                print(f"(skipped — optional file absent: {path.name})")
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
