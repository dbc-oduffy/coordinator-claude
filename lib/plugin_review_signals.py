"""Plugin-declared review-signal overlay: scans installed plugins for a shipped `review-signals.json`
and returns the available plugin names plus the review signals they contribute, so plan-blitz can
route a contributed signal to the agent its plugin names, and drop it cleanly when that plugin is
absent. DoE names no plugin agent; the declaration belongs to the plugin that ships it.

CLI (stdout is one JSON object):
    plugin_review_signals.py scan   [--plugin-root DIR ...]
    plugin_review_signals.py attach --repo-root DIR --plan PLAN.md [--plugin-root DIR ...]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ue_review_signal import _holds, ue_signal_for_writes

DECLARATION = "review-signals.json"
SCHEMA_NAME = "plugin-review-signals"
PLUGIN_ROOTS_ENV = "COORDINATOR_PLUGIN_ROOTS"
_BASE_CONTRACT = Path(__file__).resolve().parent.parent / "contract" / "review-signals.json"
_KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_TRIGGER_KINDS = ("ue-territory", "path-segment", "path-suffix", "repo-holds", "ancestor-holds")
_VALUELESS = ("ue-territory",)


def _claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".claude"


def _fallback_root(key: str, install: Path):
    """A real directory for a dangling `installPath`: the same path without its `cache` segment, else
    `<claude home>/plugins/<marketplace>/<plugin>` from the `plugin@marketplace` key. None if neither exists."""
    tries = []
    if "cache" in install.parts:
        tries.append(Path(*[p for p in install.parts if p != "cache"]))
    name, _, market = key.partition("@")
    if name and market:
        tries.append(_claude_home() / "plugins" / market / name)
    return next((t for t in tries if t.is_dir()), None)


def _resolve_installed():
    """`(roots, misses)`: install-path roots from `installed_plugins.json` (dangling paths re-resolved via
    `_fallback_root`) and a message per entry no directory could be found for."""
    roots, misses = [], []
    try:
        data = json.loads((_claude_home() / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        for key, installs in (data.get("plugins") or {}).items():
            for install in installs if isinstance(installs, list) else []:
                if not (isinstance(install, dict) and install.get("installPath")):
                    continue
                path = Path(install["installPath"])
                if path.is_dir():
                    roots.append(path)
                elif (real := _fallback_root(str(key), path)) is not None:
                    roots.append(real)
                else:
                    misses.append(f"{key}: installPath {path} does not exist; its review signals were not read")
    except (OSError, ValueError, AttributeError):
        pass
    return roots, misses


def installed_plugin_misses() -> list[str]:
    """Messages for installed plugins whose `installPath` resolves to no directory."""
    return _resolve_installed()[1]


def installed_plugin_roots(extra=()) -> list[Path]:
    """Plugin roots: `extra`, `$COORDINATOR_PLUGIN_ROOTS` (os.pathsep list), then the install paths in
    `<claude home>/plugins/installed_plugins.json`. Deduplicated, existing directories only."""
    candidates = [Path(p) for p in extra]
    candidates += [Path(p) for p in os.environ.get(PLUGIN_ROOTS_ENV, "").split(os.pathsep) if p.strip()]
    candidates += _resolve_installed()[0]
    seen, roots = set(), []
    for c in candidates:
        key = str(c.resolve()) if c.exists() else str(c)
        if key not in seen and c.is_dir():
            seen.add(key)
            roots.append(c)
    return roots


def plugin_name(root: Path) -> str:
    """The plugin's declared name (`.claude-plugin/plugin.json`), else its directory name."""
    try:
        name = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")).get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    except (OSError, ValueError, AttributeError):
        pass
    return root.name


def base_signal_ids() -> set[str]:
    try:
        return set(json.loads(_BASE_CONTRACT.read_text(encoding="utf-8"))["signals"])
    except (OSError, ValueError, KeyError):
        return set()


def _trigger_errors(triggers) -> list[str]:
    if not isinstance(triggers, list) or not triggers:
        return ["write_triggers must be a non-empty list"]
    errs = []
    for t in triggers:
        if not isinstance(t, dict) or t.get("kind") not in _TRIGGER_KINDS:
            errs.append(f"write trigger {t!r} must be an object whose kind is one of {list(_TRIGGER_KINDS)}")
        elif t["kind"] not in _VALUELESS and not (isinstance(t.get("value"), str) and t["value"].strip()):
            errs.append(f"write trigger kind {t['kind']!r} needs a non-empty string value")
    return errs


def _validate_signal(plugin: str, sig, reserved: set[str]) -> list[str]:
    if not isinstance(sig, dict):
        return ["signal entry is not an object"]
    errs = []
    sid = sig.get("id")
    if not (isinstance(sid, str) and _KEBAB.match(sid)):
        errs.append(f"id {sid!r} is not kebab-case")
    elif sid in reserved:
        errs.append(f"id {sid!r} shadows a coordinator signal")
    selects = sig.get("selects")
    if not (isinstance(selects, str) and selects.startswith(f"{plugin}:") and len(selects) > len(plugin) + 1):
        errs.append(f"selects {selects!r} must be an agent in the declaring plugin's own namespace '{plugin}:'")
    terms = sig.get("prose_terms")
    if not (isinstance(terms, list) and terms and all(isinstance(t, str) and t.strip() for t in terms)):
        errs.append("prose_terms must be a non-empty list of strings")
    errs += _trigger_errors(sig.get("write_triggers"))
    if "model" in sig and not (isinstance(sig["model"], str) and sig["model"].strip()):
        errs.append("model, when present, must be a non-empty string")
    return errs


def scan(plugin_roots=None) -> dict:
    """`{availablePlugins, signals, issues}` over `plugin_roots` (default: installed plugin roots).

    A malformed declaration, or a signal entry that fails validation, is skipped and named in `issues`;
    it never raises. A plugin with no `review-signals.json` is available and contributes nothing.
    """
    if plugin_roots is None:
        roots, issues = installed_plugin_roots(), installed_plugin_misses()
    else:
        roots, issues = [Path(r) for r in plugin_roots], []
    reserved = base_signal_ids()
    available, signals, taken = [], [], set()
    for root in roots:
        plugin = plugin_name(root)
        if plugin not in available:
            available.append(plugin)
        decl = root / DECLARATION
        if not decl.is_file():
            continue
        try:
            doc = json.loads(decl.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            issues.append(f"{plugin}: {DECLARATION} unreadable: {exc}")
            continue
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA_NAME or not isinstance(doc.get("signals"), list):
            issues.append(f"{plugin}: {DECLARATION} is not a '{SCHEMA_NAME}' document with a signals list")
            continue
        for sig in doc["signals"]:
            errs = _validate_signal(plugin, sig, reserved | taken)
            if errs:
                issues.append(f"{plugin}: signal {sig.get('id') if isinstance(sig, dict) else sig!r} skipped: " + "; ".join(errs))
                continue
            taken.add(sig["id"])
            signals.append({
                "id": sig["id"], "plugin": plugin, "selects": sig["selects"],
                "model": sig.get("model") or "opus",
                "prose_terms": list(sig["prose_terms"]), "write_triggers": list(sig["write_triggers"]),
            })
    return {"availablePlugins": available, "signals": signals, "issues": issues}


def _norm_parts(raw) -> list[str]:
    norm = str(raw).replace("\\", "/")
    return [p for p in PurePosixPath(norm).parts if p not in ("/", ".")]


def trigger_fires(trigger: dict, writes, repo_root) -> bool:
    """Whether one write trigger matches the plan's repo-relative `writes` under `repo_root`.

    `ue-territory` reuses `ue_signal_for_writes`; `path-segment` is a case-insensitive path component;
    `path-suffix` a case-insensitive file suffix; `repo-holds` a glob directly under `repo_root`;
    `ancestor-holds` a glob in any ancestor directory of a write (below `repo_root`).
    """
    kind, value = trigger.get("kind"), trigger.get("value")
    root = Path(repo_root)
    if kind == "ue-territory":
        return ue_signal_for_writes(writes, root)
    if kind == "repo-holds":
        return _holds(root, value)
    for raw in writes or []:
        parts = _norm_parts(raw)
        if not parts:
            continue
        if kind == "path-segment" and any(p.lower() == value.lower() for p in parts):
            return True
        if kind == "path-suffix" and parts[-1].lower().endswith(value.lower()):
            return True
        if kind == "ancestor-holds":
            top = len(parts) if str(raw).replace("\\", "/").endswith("/") else len(parts) - 1
            if any(_holds(root.joinpath(*parts[:d]), value) for d in range(top, 0, -1)):
                return True
    return False


def signals_for_writes(signals, writes, repo_root) -> list[str]:
    """Ids of the contributed `signals` whose write triggers fire for `writes`."""
    return [s["id"] for s in signals if any(trigger_fires(t, writes, repo_root) for t in s["write_triggers"])]


def plan_writes(plan_path) -> list[str]:
    """Every `writes:` path in the plan's `## Tasks` spine rows (inline `[a, b]` lists and block lists)."""
    text = Path(plan_path).read_text(encoding="utf-8", errors="replace")
    writes: list[str] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^\s*(?:-\s+)?writes:\s*(.*)$", line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest.startswith("["):
            writes += [p.strip().strip("'\"") for p in rest.strip("[]").split(",") if p.strip()]
        elif not rest:
            for nxt in lines[i + 1:]:
                item = re.match(r"^\s+-\s+(.*\S)\s*$", nxt)
                if not item:
                    break
                writes.append(item.group(1).strip("'\""))
    return writes


def attach(plan_path, repo_root, plugin_roots=None) -> dict:
    """`{attached: [ids]}` plus the scan, for the plan at `plan_path` under `repo_root`."""
    found = scan(plugin_roots)
    found["attached"] = signals_for_writes(found["signals"], plan_writes(plan_path), repo_root)
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "attach"):
        p = sub.add_parser(name)
        p.add_argument("--plugin-root", action="append", default=[])
        if name == "attach":
            p.add_argument("--repo-root", required=True)
            p.add_argument("--plan", required=True)
    args = ap.parse_args(argv)
    roots = installed_plugin_roots(args.plugin_root)
    out = scan(roots) if args.cmd == "scan" else attach(args.plan, args.repo_root, roots)
    out["issues"] = installed_plugin_misses() + out["issues"]
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
