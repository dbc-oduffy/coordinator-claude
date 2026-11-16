"""Advisory fleet lint: project CLAUDE.md files that teach hand-authored handoffs.

Flags any fleet repo's CLAUDE.md naming the retired `.claude/handoffs` path, or telling the agent
to write a handoff file manually. Repos come from one `machine-local dump` read (`repos.*`). One line per
offending repo and line number, plus the remedy. Always exits 0; unreadable repos are skipped.

Contract: coordinator/docs/wiki/coordinator-tripwires/a-handoff-written-by-hand-is-not-a-handoff.md.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

CLAUDE_MD_RELPATHS = ("CLAUDE.md", ".claude/CLAUDE.md")
REMEDY = "replace with: run /handoff; handoffs live in state/handoffs/"
RETIRED_PATH = re.compile(r"\.claude(?:/|\\)handoffs")
MANUAL_WRITE = re.compile(
    r"\b(write|writes|author|create|save|hand-?author)\w*\s+(?:a|the|your|an)?\s*(?:session\s+)?handoff"
    r"(?:\s+(?:file|doc\w*|baton))?\s+(?:to|in|at|under|manually|by hand)\b"
    r"|\bhandoff\s+file\s+(?:manually|by hand)\b",
    re.I,
)
NEGATED = re.compile(r"\b(never|do not|don't|retired|instead of)\b", re.I)
RETIRED_MARK = re.compile(r"\b(retired|never|do not)\b", re.I)


def _settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if env:
        return Path(env)
    return Path(os.environ.get("CLAUDE_HOME") or Path.home()) / ".coordinator-claude-settings"


def _registry_dump() -> Dict[str, object]:
    """Every `repos.*` key and its value, resolved in-process by the machine-local kernel.

    Trap: never spawn `machine-local.cmd` here. On Windows a subprocess timeout kills cmd.exe and
    orphans its python grandchild, and a hook that fires per session turns that into a process storm.
    """
    impl = _settings_home() / "bin" / "_machine_local.py"
    spec = importlib.util.spec_from_file_location("_machine_local_kernel_handoff_lint", impl)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"machine-local kernel not loadable: {impl}")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        layers = mod._build_resolution_layers(mod._registry_dir())
        out: Dict[str, object] = {}
        for key in mod._all_keys(layers):
            if not key.startswith("repos."):
                continue
            rc, val = mod.resolve_one(key, layers)
            if rc == mod.EXIT_OPERATIONAL:
                raise RuntimeError(f"machine-local could not resolve {key}")
            if rc == mod.EXIT_OK and val is not None:
                out[key] = val
    except SystemExit as exc:
        raise RuntimeError(f"machine-local kernel exited {exc.code}") from exc
    return out


def raw_repos() -> Dict[str, object]:
    """Every `repos.*` registry key (prefix stripped) with its unvalidated value, from one registry read."""
    return {k[len("repos."):]: v for k, v in _registry_dump().items() if k.startswith("repos.")}


def fleet_repos(raw: Optional[Dict[str, object]] = None) -> Dict[str, Path]:
    """`repos.*` registry entries that are existing directories, de-duplicated by resolved path.

    `raw` is a `raw_repos()` result the caller already holds; omitted, the registry is read here.
    """
    out: Dict[str, Path] = {}
    seen: set[Path] = set()
    for key, val in (raw_repos() if raw is None else raw).items():
        if isinstance(val, str) and val and Path(val).is_dir() and Path(val).resolve() not in seen:
            seen.add(Path(val).resolve())
            out[key] = Path(val)
    return out


def _offends(line: str) -> bool:
    """A retired path flags unless "retired"/"never"/"do not" precedes it; a manual-write phrase
    flags unless a negator precedes it."""
    path_hit = RETIRED_PATH.search(line)
    if path_hit and not RETIRED_MARK.search(line[: path_hit.start()]):
        return True
    write_hit = MANUAL_WRITE.search(line)
    return bool(write_hit and not NEGATED.search(line[: write_hit.start()]))


def scan_repo(root: Path) -> Iterator[Tuple[str, int, str]]:
    """Yield (relpath, line number, stripped line) for each offending CLAUDE.md line."""
    for rel in CLAUDE_MD_RELPATHS:
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if _offends(line):
                yield rel, n, line.strip()[:120]


def report(repos: Dict[str, Path]) -> List[str]:
    return [
        f"{name}: {rel}:{n}: hand-authored handoff convention ({snippet!r}) -- {REMEDY}"
        for name, root in repos.items()
        for rel, n, snippet in scan_repo(root)
    ]


def main() -> int:
    try:
        repos = fleet_repos()
    except Exception as exc:  # advisory lint: an unreadable registry skips, never fails the hook
        print(f"lint skipped -- {exc or type(exc).__name__}")
        return 0
    for line in report(repos):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
