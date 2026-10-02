"""Report-only check: warns when an agent's frontmatter `tools:` names an `mcp__<server>__`
namespace that no local config registers.

Resolution sources (config home = `CLAUDE_CONFIG_DIR` if set, else `Path.home()`):
  - `mcpServers` keys in `<config-home>/.claude.json`, top level and
    `projects[<repo root>].mcpServers`
  - `mcpServers` keys in `<repo root>/.mcp.json`
  - `plugin_<plugin>_<server>` namespaces: a truthy `enabledPlugins` key `<plugin>@*` in
    `<config-home>/settings.json`

`claude_ai_*` namespaces are account-side connectors no local file records; they are listed as
unverifiable, never as missing. Always exits 0.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_NS_RE = re.compile(r"mcp__([A-Za-z0-9_.-]+?)__")
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "lib"))
from frontmatter_scan import read_text, scan_frontmatter  # noqa: E402
sys.path.insert(0, str(_ROOT / "hooks" / "scripts"))
try:  # hooks/scripts is overlaid at publish; absent in a bare claude-klabauter checkout
    from _git_root_walk import git_root_walk  # noqa: E402
except ImportError:
    def git_root_walk():
        return None


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _config_home() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home()


def _servers(block: object) -> set[str]:
    return set(block) if isinstance(block, dict) else set()


def registered_servers(repo_root: Path, config_home: Path) -> set[str]:
    claude_json = _load_json(config_home / ".claude.json")
    names = _servers(claude_json.get("mcpServers"))
    projects = claude_json.get("projects")
    if isinstance(projects, dict):
        for key in (str(repo_root), repo_root.as_posix()):
            entry = projects.get(key)
            if isinstance(entry, dict):
                names |= _servers(entry.get("mcpServers"))
    names |= _servers(_load_json(repo_root / ".mcp.json").get("mcpServers"))
    return names


def enabled_plugins(config_home: Path) -> set[str]:
    block = _load_json(config_home / "settings.json").get("enabledPlugins")
    if not isinstance(block, dict):
        return set()
    return {k.split("@", 1)[0] for k, v in block.items() if v}


def agent_namespaces(agent_file: Path) -> set[str]:
    tools = scan_frontmatter(read_text(agent_file)).get("tools", "")
    entries = tools if isinstance(tools, list) else [tools]
    return {m.group(1) for entry in entries for m in _NS_RE.finditer(entry)}


def check(agents_dir: Path, repo_root: Path, config_home: Path) -> tuple[list[str], list[str]]:
    servers = registered_servers(repo_root, config_home)
    plugins = enabled_plugins(config_home)
    missing: list[str] = []
    unverifiable: set[str] = set()
    for agent in sorted(agents_dir.glob("*.md")):
        for ns in sorted(agent_namespaces(agent)):
            if ns.startswith("claude_ai_"):
                unverifiable.add(ns)
            elif ns in servers:
                continue
            elif ns.startswith("plugin_") and any(ns.startswith(f"plugin_{p}_") for p in plugins):
                continue
            else:
                missing.append(f"{agent.name}: mcp__{ns}__ is not registered in any local config")
    return missing, sorted(unverifiable)


def main() -> int:
    repo_root = Path(git_root_walk() or Path.cwd())
    missing, unverifiable = check(_ROOT / "agents", repo_root, _config_home())
    for line in missing:
        print(f"WARN {line}")
    if unverifiable:
        print("unverifiable (account-side): " + ", ".join(f"mcp__{n}__" for n in unverifiable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
