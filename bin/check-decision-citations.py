#!/usr/bin/env python3
"""check-decision-citations -- a cited DR-nnn / SC-DR-nnn id must resolve somewhere in the fleet.

Default mode exits 1 on a live dangling id the committed baseline does not list, 0 when clean (or
when no baseline exists), 2 when the check could not run. `--emit-baseline` rewrites
`state/baselines/decision-citations.md`; it is a reviewed act, never the reply to a fire.
Contract: coordinator/docs/wiki/doctrine-authoring/decisions-corpus.md.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

BASELINE_REL = "state/baselines/decision-citations.md"
SC_WIKI_REL = "coordinator/docs/wiki/concurrent-em-git-operations/scoped-safety-commits.md"
DECISION_DIRS = ("docs/decisions", "coordinator/docs/decisions")
EXTENSIONS = ("*.md", "*.json", "*.sh", "*.py", "*.yaml", "*.js")
EXCLUDED_PREFIXES = ("archive/", "tasks/", ".structural-index/", ".coordinator-local/")
RESERVED = frozenset({"DR-000", "DR-999", "SC-DR-000"})

_GREP_PATTERN = r"(^|[^A-Za-z0-9-])(SC-)?DR-[0-9]{3}([^0-9]|$)"
_TOKEN = re.compile(r"(?<![A-Za-z0-9-])((?:SC-)?DR-\d{3})(?!\d)")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_FILENAME_ID = re.compile(r"^(DR-\d{3})")
_FM_ID = re.compile(r"""^id:\s*["']?(DR-\d{3})""")
_KEYS_LINE = "Resolved sibling registry keys:"


class CheckError(Exception):
    """The check could not run (exit 2)."""


def _no_console() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _settings_home() -> Path:
    explicit = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if explicit:
        return Path(explicit)
    home = os.environ.get("CLAUDE_HOME") or os.path.expanduser("~")
    return Path(home) / ".coordinator-claude-settings"


def _run(argv: list[str], cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cwd,
            creationflags=_no_console(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def repo_root() -> Path:
    out = _run(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).resolve().parent)
    if not out or not out.strip():
        raise CheckError("cannot resolve the repo root from the script location")
    return Path(out.strip())


def _registry_repo_paths() -> dict[str, Path]:
    """Every `repos.*` registry key resolving to an existing directory on this machine."""
    name = "machine-local.cmd" if os.name == "nt" else "machine-local"
    ml = [str(_settings_home() / "bin" / name)]
    listing = _run(ml + ["keys"])
    if listing is None:
        return {}
    resolved: dict[str, Path] = {}
    for line in listing.splitlines():
        key = line.strip()
        if not key.startswith("repos."):
            continue
        value = _run(ml + ["get", key])
        if value and value.strip() and Path(value.strip()).is_dir():
            resolved[key[len("repos.") :]] = Path(value.strip())
    return resolved


def _decision_ids(repo: Path) -> set[str]:
    """DR ids a repo holds, by filename prefix OR frontmatter `id:` (the frontmatter is the key)."""
    ids: set[str] = set()
    for rel in DECISION_DIRS:
        d = repo / rel
        if not d.is_dir():
            continue
        for entry in d.iterdir():
            m = _FILENAME_ID.match(entry.name)
            if m:
                ids.add(m.group(1))
            if entry.suffix != ".md" or not entry.is_file():
                continue
            try:
                lines = entry.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            if not lines or lines[0].strip() != "---":
                continue
            for line in lines[1:]:
                if line.strip() == "---":
                    break
                fm = _FM_ID.match(line)
                if fm:
                    ids.add(fm.group(1))
    return ids


def sibling_decision_ids(root: Path) -> dict[str, set[str]]:
    """registry key -> DR ids held by that sibling; siblings without a decisions dir are skipped."""
    out: dict[str, set[str]] = {}
    for key, path in _registry_repo_paths().items():
        if path.resolve() == root.resolve():
            continue
        if not any((path / rel).is_dir() for rel in DECISION_DIRS):
            continue
        out[key] = _decision_ids(path)
    return out


def live_tokens(root: Path) -> dict[str, set[str]]:
    """id -> repo-relative files citing it in live position (outside fences and excluded trees)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "grep", "-l", "-I", "-E", "--null", "-e", _GREP_PATTERN, "--", *EXTENSIONS],
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=_no_console(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CheckError(f"git grep failed to run: {exc}") from exc
    if proc.returncode not in (0, 1):
        raise CheckError(f"git grep exited {proc.returncode}: {proc.stderr.strip()}")
    found: dict[str, set[str]] = {}
    for rel in sorted(p for p in proc.stdout.split("\0") if p.strip()):
        rel = rel.strip("\n")
        if rel.startswith(EXCLUDED_PREFIXES):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fence: tuple[str, int] | None = None
        for line in text.splitlines():
            fm = _FENCE.match(line)
            if fm:
                marker = fm.group(1)
                if fence is None:
                    fence = (marker[0], len(marker))
                elif marker[0] == fence[0] and len(marker) >= fence[1] and not line.strip().strip(marker[0]):
                    fence = None
                continue
            if fence is not None:
                continue
            for tok in _TOKEN.findall(line):
                if tok not in RESERVED:
                    found.setdefault(tok, set()).add(rel)
    return found


def _sc_wiki_ids(root: Path) -> set[str]:
    wiki = root / SC_WIKI_REL
    if not wiki.is_file():
        return set()
    return set(re.findall(r"SC-DR-\d{3}", wiki.read_text(encoding="utf-8", errors="replace")))


def classify(
    root: Path, cited: dict[str, set[str]], siblings: dict[str, set[str]]
) -> tuple[list[str], dict[str, list[str]]]:
    """(dangling ids, {sibling-only id: [resolving keys]})."""
    local = _decision_ids(root)
    sc = _sc_wiki_ids(root)
    dangling: list[str] = []
    bare: dict[str, list[str]] = {}
    for ident in sorted(cited):
        if ident.startswith("SC-"):
            if ident not in sc:
                dangling.append(ident)
        elif ident not in local:
            keys = sorted(k for k, ids in siblings.items() if ident in ids)
            if keys:
                bare[ident] = keys
            else:
                dangling.append(ident)
    return dangling, bare


def render_baseline(
    cited: dict[str, set[str]], dangling: list[str], bare: dict[str, list[str]], keys: list[str]
) -> str:
    lines = [
        "# Decision citations baseline",
        "",
        "Generated by `coordinator/bin/check-decision-citations.py --emit-baseline`. Never hand-edit a column.",
        "",
        f"{_KEYS_LINE} {', '.join(sorted(keys)) if keys else '(none)'}",
        "",
        "## Dangling",
        "",
        "| id | citing files | first citing file |",
        "|---|---|---|",
    ]
    for ident in dangling:
        files = sorted(cited[ident])
        lines.append(f"| {ident} | {len(files)} | {files[0]} |")
    lines += ["", "## Bare cross-repo inventory", "", "| id | resolving key | citing files |", "|---|---|---|"]
    for ident in sorted(bare):
        lines.append(f"| {ident} | {', '.join(bare[ident])} | {len(cited[ident])} |")
    return "\n".join(lines) + "\n"


def parse_baseline(text: str) -> tuple[set[str], list[str]]:
    """(dangling ids the baseline gates, sibling keys named in its header)."""
    ids: set[str] = set()
    keys: list[str] = []
    section = ""
    for line in text.splitlines():
        if line.startswith(_KEYS_LINE):
            value = line[len(_KEYS_LINE) :].strip()
            keys = [] if value == "(none)" else [k.strip() for k in value.split(",") if k.strip()]
        elif line.startswith("## "):
            section = line[3:].strip()
        elif section == "Dangling" and line.startswith("| "):
            cell = line.split("|")[1].strip()
            if re.fullmatch(r"(?:SC-)?DR-\d{3}", cell):
                ids.add(cell)
    return ids, keys


def emit_baseline(root: Path, siblings: dict[str, set[str]] | None = None) -> int:
    siblings = sibling_decision_ids(root) if siblings is None else siblings
    path = root / BASELINE_REL
    if path.is_file():
        _, old_keys = parse_baseline(path.read_text(encoding="utf-8"))
        lost = sorted(set(old_keys) - set(siblings))
        if lost:
            print(
                f"refusing to emit: sibling key(s) named in the existing baseline no longer resolve: {', '.join(lost)}",
                file=sys.stderr,
            )
            return 2
    cited = live_tokens(root)
    dangling, bare = classify(root, cited, siblings)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_baseline(cited, dangling, bare, list(siblings)))
    print(f"wrote {BASELINE_REL}: {len(dangling)} dangling, {len(bare)} bare cross-repo")
    return 0


def check(root: Path, siblings: dict[str, set[str]] | None = None) -> int:
    path = root / BASELINE_REL
    if not path.is_file():
        print(f"decision citations: no baseline at {BASELINE_REL}; skipped", file=sys.stderr)
        return 0
    siblings = sibling_decision_ids(root) if siblings is None else siblings
    gated, _ = parse_baseline(path.read_text(encoding="utf-8"))
    cited = live_tokens(root)
    dangling, _bare = classify(root, cited, siblings)
    new = [i for i in dangling if i not in gated]
    for ident in new:
        print(f"NEW dangling {ident}: {', '.join(sorted(cited[ident]))}")
    if new:
        return 1
    print("decision citations: clean")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--emit-baseline", action="store_true", help=f"rewrite {BASELINE_REL}")
    ap.add_argument("--root", type=Path, default=None, help="repo root (default: this script's repo)")
    args = ap.parse_args(argv)
    try:
        root = args.root if args.root is not None else repo_root()
        return emit_baseline(root) if args.emit_baseline else check(root)
    except CheckError as exc:
        print(f"decision citations: could not check: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
