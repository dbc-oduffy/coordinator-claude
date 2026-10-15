"""Scan project CLAUDE.md files for fleet rules they state instead of pointing at.

Two finding classes, matched per line (CRLF-normalised, case-insensitive, regex only):
`stale` = a signature of coordinator/contract/retired-claims.json (a retired fleet claim stated as
live; exit 1); `restated` = a signature of coordinator/contract/fleet-rule-homes.json (a homed fleet
rule written out; advisory). A line naming the entry's `home` file is a pointer and is not reported.

Exit 0: no stale finding. 1: a stale finding. 2: could not check (malformed contract, unreadable
registry). Contract: coordinator/docs/wiki/coordinator-tripwires/tripwire-registry/
a-project-claude-md-holds-no-fleet-rules-fleet-claude-md-fleet-rule-scan.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence, Tuple

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RETIRED_CLAIMS = PLUGIN_ROOT / "contract" / "retired-claims.json"
FLEET_RULE_HOMES = PLUGIN_ROOT / "contract" / "fleet-rule-homes.json"
_HOOK = PLUGIN_ROOT / "hooks" / "scripts" / "check-fleet-claude-md-handoff-convention.py"


class ContractError(Exception):
    """A contract file or the registry could not be read; the run reports missing coverage."""


class Rule(NamedTuple):
    cls: str
    id: str
    patterns: Tuple["re.Pattern[str]", ...]
    remedy: str
    home_name: str


def _load_hook():
    spec = importlib.util.spec_from_file_location("fleet_claude_md_hook", _HOOK)
    if spec is None or spec.loader is None:
        raise ContractError(f"cannot load {_HOOK}")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        raise ContractError(f"cannot load {_HOOK.name}: {exc or type(exc).__name__}") from exc
    return mod


def _read_entries(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        entries = data["entries"]
        if not isinstance(entries, list):
            raise TypeError("entries is not a list")
        if not all(isinstance(e, dict) for e in entries):
            raise TypeError("an entry is not an object")
        return entries
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ContractError(f"{path.name}: {exc}") from exc


def _compile(entry: dict, path: Path) -> Tuple["re.Pattern[str]", ...]:
    try:
        sigs = entry["signatures"]
        if not isinstance(sigs, list) or not sigs:
            raise TypeError("signatures must be a non-empty list")
        return tuple(re.compile(s, re.I) for s in sigs)
    except (KeyError, TypeError, re.error) as exc:
        raise ContractError(f"{path.name}: entry {entry.get('id', '?')!r}: {exc}") from exc


def load_rules() -> List[Rule]:
    retired, homes = RETIRED_CLAIMS, FLEET_RULE_HOMES
    rules: List[Rule] = []
    for e in _read_entries(retired):
        rules.append(Rule("stale", str(e.get("id", "?")), _compile(e, retired),
                          f"retired by {e.get('retired_by', '?')}; cut the line", ""))
    for e in _read_entries(homes):
        try:
            home = e["home"]
            if not isinstance(home, str):
                raise TypeError("home is not a string")
        except (KeyError, TypeError) as exc:
            raise ContractError(f"{homes.name}: entry {e.get('id', '?')!r}: bad home: {exc}") from exc
        rules.append(Rule("restated", str(e.get("id", "?")), _compile(e, homes),
                          f"point at {home}; do not restate", home.replace("\\", "/").rsplit("/", 1)[-1].lower()))
    return rules


def scan_file(path: Path, rules: Sequence[Rule]) -> List[Tuple[int, Rule, str]]:
    """(line number, matched rule, first 120 chars) per finding; an unreadable file has none."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    hits: List[Tuple[int, Rule, str]] = []
    for n, line in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1):
        low = line.lower()
        for rule in rules:
            if rule.home_name and rule.home_name in low:
                continue
            if any(p.search(line) for p in rule.patterns):
                hits.append((n, rule, line.strip()[:120]))
    return hits


def find_repo_root(start: Path) -> Optional[Path]:
    for d in (start, *start.parents):
        if (d / ".git").exists():
            return d
    return None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--repo-root", help="repo whose CLAUDE.md files are scanned (default: nearest .git ancestor of cwd)")
    ap.add_argument("--path", action="append", help="scan exactly this file (repeatable)")
    ap.add_argument("--fleet", action="store_true", help="scan every existing machine-local repos.* root")
    args = ap.parse_args(argv)

    try:
        rules = load_rules()
        hook = _load_hook() if args.fleet or not args.path else None
        targets: List[Tuple[str, Path, str]] = []
        skipped: List[str] = []
        if args.path:
            for p in args.path:
                pp = Path(p)
                if not pp.is_file():
                    raise ContractError(f"--path {p}: not a readable file")
                targets.append((pp.resolve().parent.name, pp, pp.name))
        elif args.fleet:
            try:
                raw = hook.raw_repos()
            except Exception as exc:
                raise ContractError(f"registry unreadable: {exc or type(exc).__name__}") from exc
            scanned = hook.fleet_repos(raw)
            skipped = [key for key in raw if key not in scanned]
            for name, root in scanned.items():
                targets += [(name, root / rel, rel) for rel in hook.CLAUDE_MD_RELPATHS]
        else:
            root = Path(args.repo_root) if args.repo_root else find_repo_root(Path.cwd())
            if root is None:
                raise ContractError("no .git ancestor of cwd; pass --repo-root")
            targets += [(root.resolve().name, root / rel, rel) for rel in hook.CLAUDE_MD_RELPATHS]
    except ContractError as exc:
        print(f"could not check -- {exc}", file=sys.stderr)
        return 2

    stale = 0
    for repo, path, rel in targets:
        for n, rule, snippet in scan_file(path, rules):
            print(f"{repo}: {rel}:{n}: {rule.cls} [{rule.id}] ({snippet}) -- {rule.remedy}")
            stale += rule.cls == "stale"
    if args.fleet and skipped:
        print("skipped: " + ", ".join(skipped))
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
