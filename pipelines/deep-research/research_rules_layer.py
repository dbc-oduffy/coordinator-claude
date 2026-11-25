"""Research-rules layer reader: which installed plugins' `research-rules.json` apply to a target repo,
and the tools they require. Stdlib-only; imported by research-rules-gate.py and by the project-rag-first
nudge. DoE names no plugin's rules: every rule, tool name and section heading comes from the declaration.

An absent, unreadable or non-applying declaration yields no layer. A declaration whose `applies_when`
fires but whose body is invalid yields a layer-less `issues` entry so the gate can refuse loudly.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from plugin_review_signals import installed_plugin_roots, plugin_name, trigger_fires  # noqa: E402

DECLARATION = "research-rules.json"
SCHEMA_NAME = "plugin-research-rules"
STAGE_ROLES = ("scope", "prior-art", "scout", "specialist", "synthesizer")
STAGE_ALIASES = {
    "scout-haiku": "scout", "scout-sonnet": "scout", "rescout": "scout",
    "synthesize": "synthesizer", "synthesize-2": "synthesizer",
}
GREP_LINE = ("Grep is for prose/literal strings that are not identifiers; "
             "identifier and symbol lookups go through required_tools")
_KEY = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
_TOOL = re.compile(r"^[A-Za-z0-9_.-]+$")
_RULES_PATH = re.compile(r"^(?!/)(?!.*\.\.)(?![A-Za-z]:)[^\\]+\.md$")
_READER_TIMEOUT_S = 2.0

KeyResolver = Callable[[str], "str | None"]


def _settings_home() -> Path:
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    return Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"


def resolve_settings_key(key: str) -> "str | None":
    """The value of a settings-home registry key, or None when the reader, the key or its value is absent.

    Spawns the installed `machine-local` reader; the `MACHINE_LOCAL_<KEY>` environment variable is the
    fallback rung the reader itself ends on. Never raises, never guesses a path.
    """
    reader = _settings_home() / "bin" / "_machine_local.py"
    if reader.is_file():
        try:
            res = subprocess.run(
                [sys.executable, str(reader), "get", key], capture_output=True, text=True,
                check=False, timeout=_READER_TIMEOUT_S,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return os.environ.get("MACHINE_LOCAL_" + key.upper().replace(".", "_")) or None


def _norm(path) -> str:
    return os.path.normcase(os.path.normpath(str(path).replace("\\", "/"))).replace("\\", "/")


def served_repos_names(entries, repo_root: Path) -> bool:
    """Whether a served-repos JSON document names `repo_root`: a path entry resolving to it, or a bare
    directory name equal to its name. Entries are strings or objects with `path`/`root`/`repo`."""
    if isinstance(entries, dict):
        entries = entries.get("repos") or entries.get("served_repos") or []
    if not isinstance(entries, list):
        return False
    target = _norm(repo_root.resolve())
    name = repo_root.resolve().name.lower()
    for entry in entries:
        if isinstance(entry, dict):
            entry = entry.get("path") or entry.get("root") or entry.get("repo")
        if not isinstance(entry, str) or not entry.strip():
            continue
        text = entry.strip()
        if "/" in text.replace("\\", "/") or ":" in text:
            try:
                if _norm(Path(text).expanduser().resolve()) == target:
                    return True
            except (OSError, ValueError):
                continue
        elif text.lower() == name:
            return True
    return False


def _trigger_ok(trigger) -> bool:
    if not isinstance(trigger, dict):
        return False
    if trigger.get("kind") == "repo-holds":
        return isinstance(trigger.get("value"), str) and bool(trigger["value"].strip())
    if trigger.get("kind") == "served-repos-file":
        return isinstance(trigger.get("settings_key"), str) and bool(_KEY.match(trigger["settings_key"]))
    return False


def _fires(trigger: dict, repo_root: Path, resolve_key: KeyResolver) -> bool:
    if trigger["kind"] == "repo-holds":
        return trigger_fires({"kind": "repo-holds", "value": trigger["value"]}, [], repo_root)
    value = resolve_key(trigger["settings_key"])
    if not value:
        return False
    try:
        return served_repos_names(json.loads(Path(value).read_text(encoding="utf-8")), repo_root)
    except (OSError, ValueError):
        return False


def _body_errors(doc: dict, root: Path) -> list[str]:
    errs = []
    stages = doc.get("stages", {})
    if not isinstance(stages, dict):
        errs.append("stages must be an object")
    else:
        for role, rel in stages.items():
            if role not in STAGE_ROLES:
                errs.append(f"stage role {role!r} is not one of {list(STAGE_ROLES)}")
            elif not (isinstance(rel, str) and _RULES_PATH.match(rel)):
                errs.append(f"stages.{role} must be a plugin-relative .md path")
    fams = doc.get("scout_required_tool_families", [])
    if not isinstance(fams, list):
        errs.append("scout_required_tool_families must be a list")
    else:
        for fam in fams:
            ok = (isinstance(fam, dict) and isinstance(fam.get("name"), str) and fam["name"]
                  and isinstance(fam.get("tools"), list) and fam["tools"]
                  and all(isinstance(t, str) and _TOOL.match(t) for t in fam["tools"])
                  and isinstance(fam.get("min_calls"), int) and not isinstance(fam["min_calls"], bool)
                  and fam["min_calls"] >= 1)
            if not ok:
                errs.append(f"scout family {fam!r} needs name, tools[] and min_calls >= 1")
    secs = doc.get("synthesis_sections", [])
    if not (isinstance(secs, list) and all(isinstance(s, str) and s.strip() for s in secs)):
        errs.append("synthesis_sections must be a list of non-empty strings")
    fill = doc.get("fill_request")
    if fill is not None:
        if not (isinstance(fill, dict) and isinstance(fill.get("heading"), str) and fill["heading"].strip()
                and isinstance(fill.get("owner_repo"), str) and fill["owner_repo"].strip()):
            errs.append("fill_request needs heading and owner_repo")
        elif not secs:
            errs.append("fill_request needs synthesis_sections")
    return errs


def _build_layer(plugin: str, root: Path, doc: dict) -> dict:
    families = [dict(f) for f in doc.get("scout_required_tool_families", [])]
    tools: list[str] = []
    for fam in families:
        tools += [t for t in fam["tools"] if t not in tools]
    return {
        "plugin": plugin,
        "root": str(root),
        "stages": {role: str(root / rel) for role, rel in doc.get("stages", {}).items()},
        "families": families,
        "required_tools": tools,
        "synthesis_sections": list(doc.get("synthesis_sections", [])),
        "fill_request": dict(doc["fill_request"]) if doc.get("fill_request") else None,
    }


def read_layers(repo_root, plugin_roots=None, resolve_key: "KeyResolver | None" = None) -> dict:
    """`{layers, issues}` for the target repo: each installed plugin's declaration whose `applies_when` fires.

    `plugin_roots=None` scans the installed roots; an explicit list (even empty) is used as given.
    `issues` names every declaration that fires but is invalid, or is unreadable: a layer the gate cannot
    trust is an issue, never silence.
    """
    repo = Path(repo_root)
    resolve = resolve_key or resolve_settings_key
    roots = installed_plugin_roots() if plugin_roots is None else [Path(r) for r in plugin_roots]
    layers, issues = [], []
    for root in roots:
        decl = root / DECLARATION
        if not decl.is_file():
            continue
        plugin = plugin_name(root)
        try:
            doc = json.loads(decl.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            issues.append(f"{plugin}: {DECLARATION} unreadable: {exc}")
            continue
        triggers = doc.get("applies_when") if isinstance(doc, dict) else None
        if not (isinstance(triggers, list) and triggers and all(_trigger_ok(t) for t in triggers)):
            issues.append(f"{plugin}: {DECLARATION} has no valid applies_when list")
            continue
        if not any(_fires(t, repo, resolve) for t in triggers):
            continue
        errs = [] if (doc.get("schema") == SCHEMA_NAME and doc.get("schema_version") == 1) else [
            f"schema must be '{SCHEMA_NAME}' version 1"]
        errs += _body_errors(doc, root)
        if errs:
            issues.append(f"{plugin}: {DECLARATION} applies here but is invalid: " + "; ".join(errs))
            continue
        layers.append(_build_layer(plugin, root, doc))
    return {"layers": layers, "issues": issues}


def applicable_layers(repo_root, plugin_roots=None, resolve_key: "KeyResolver | None" = None) -> list[dict]:
    """The layers (see `read_layers`) that apply to `repo_root`; invalid declarations are dropped."""
    return read_layers(repo_root, plugin_roots, resolve_key)["layers"]


def required_tools(repo_root, plugin_roots=None, resolve_key: "KeyResolver | None" = None) -> list[str]:
    """Ordered, de-duplicated union of the `required_tools` of every layer applying to `repo_root`."""
    tools: list[str] = []
    for layer in applicable_layers(repo_root, plugin_roots, resolve_key):
        tools += [t for t in layer["required_tools"] if t not in tools]
    return tools
