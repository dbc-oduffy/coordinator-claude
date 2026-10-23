"""List deferral-shaped prose outside a plan's task spine and optionally seed it to the improvement queue.

Population: docs/plans/*.md stamped `status: implemented` with a filename date on or after --since
(default 2026-07-09); --plan PATH (repeatable) replaces it. A line is scanned unless it sits in the
frontmatter, the `## Tasks` section, a `## Distill pass` section, or a fenced block (CRLF-normalised).
A scanned line is a hit when it matches KEYWORDS and names no queue path and no `harvest-key:`.
--seed writes one `open` improvement-queue entry per hit plan through coordinator-queue-append,
idempotent on `deferral-prose-key: <plan_id>;` (plan path when the plan has no plan_id).

Exit 0: no unseeded hit. 1: report mode listed a hit not yet seeded. 2: could not check (unreadable
root or --plan, or under --seed the launcher is missing or a call failed).
Contract: coordinator/docs/wiki/coordinator-tripwires/tripwire-registry/
deferral-prose-outside-the-spine-is-audited-deferral-prose-audit.md.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, NamedTuple, Optional, Sequence

DEFAULT_SINCE = "2026-07-09"
KEYWORDS = re.compile(r"\b(?:defer\w*|follow[- ]?ups?|later)\b", re.I)
ROUTED = re.compile(r"state/(?:improvement-queue|debt-backlog|bug-backlog)/|harvest-key:", re.I)
_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_SKIP_HEADINGS = re.compile(r"^## (?:tasks|distill pass)\s*(?:\([^)]*\))?\s*$", re.I)
_KEY_PREFIX = "deferral-prose-key: "

Runner = Callable[[List[str]], int]


class Hit(NamedTuple):
    line_no: int
    text: str


class AuditError(Exception):
    """The audit could not check; the run reports missing coverage."""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    except OSError as exc:
        raise AuditError(f"cannot read {path}: {exc}") from exc


def _frontmatter_end(lines: List[str]) -> int:
    """Index of the first line after the frontmatter block (0 when there is none)."""
    if not lines or lines[0].strip() != "---":
        return 0
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i + 1
    return 0


def _frontmatter_field(lines: List[str], name: str) -> str:
    for line in lines[: _frontmatter_end(lines)]:
        m = re.match(rf"^{name}:\s*(.*?)\s*$", line)
        if m:
            return m.group(1).split(" #")[0].strip().strip("\"'")
    return ""


def out_of_spine_lines(text: str) -> List[Hit]:
    """Return (line_no, text) for every line outside frontmatter, ## Tasks, ## Distill pass and fences."""
    lines = text.split("\n")
    out: List[Hit] = []
    fence = ""
    skip_section = False
    for i in range(_frontmatter_end(lines), len(lines)):
        line = lines[i]
        stripped = line.strip()
        if fence:
            if stripped.startswith(fence):
                fence = ""
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            continue
        if line.startswith("## "):
            skip_section = bool(_SKIP_HEADINGS.match(line))
            continue
        if not skip_section:
            out.append(Hit(i + 1, line))
    return out


def find_hits(text: str) -> List[Hit]:
    return [h for h in out_of_spine_lines(text) if KEYWORDS.search(h.text) and not ROUTED.search(h.text)]


def plan_key(text: str, rel_path: str) -> str:
    return _frontmatter_field(text.split("\n"), "plan_id") or rel_path


def already_seeded(root: Path, key: str) -> bool:
    needle = f"{_KEY_PREFIX}{key};"
    for base in (root / "state" / "improvement-queue", root / "archive" / "improvement-queue"):
        if not base.is_dir():
            continue
        for f in base.rglob("*.yaml"):
            try:
                if needle in f.read_text(encoding="utf-8", errors="replace"):
                    return True
            except OSError:
                continue
    return False


def population(root: Path, plans: Sequence[str], since: str) -> List[Path]:
    if plans:
        return [Path(p) if Path(p).is_absolute() else root / p for p in plans]
    plan_dir = root / "docs" / "plans"
    if not plan_dir.is_dir():
        raise AuditError(f"no docs/plans under {root}")
    chosen = []
    for f in sorted(plan_dir.glob("*.md")):
        m = _DATE.match(f.name)
        if not m or m.group(1) < since:
            continue
        if _frontmatter_field(_read(f).split("\n"), "status") == "implemented":
            chosen.append(f)
    return chosen


def resolve_launcher() -> Optional[str]:
    found = shutil.which("coordinator-queue-append")
    if found:
        return found
    home = os.environ.get("COORDINATOR_SETTINGS_HOME") or str(Path.home() / ".coordinator-claude-settings")
    for name in ("coordinator-queue-append", "coordinator-queue-append.exe"):
        cand = Path(home) / "bin" / name
        if cand.is_file():
            return str(cand)
    return None


def _subprocess_runner(argv: List[str]) -> int:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    return subprocess.run(argv, creationflags=flags).returncode


def seed_plan(launcher: str, root: Path, rel: str, key: str, hits: List[Hit], runner: Runner) -> int:
    """Write one open improvement-queue entry for a plan through the launcher; return its exit code."""
    body_dir = root / "scratch" / "deferral-prose-audit"
    body_dir.mkdir(parents=True, exist_ok=True)
    body = body_dir / (re.sub(r"[^A-Za-z0-9._-]+", "_", key) + ".md")
    lines = [
        f"Deferral-shaped prose outside the task spine of `{rel}`.",
        "These lines are keyword matches (deferred/follow-up/later), unratified: none is a ratified deferral.",
        "Route each to a spine row or a queue entry, or delete it.",
        "",
    ] + [f"- {rel}:{h.line_no}: {h.text.strip()}" for h in hits]
    body.write_text("\n".join(lines) + "\n", encoding="utf-8")
    argv = [launcher, "--schema", "improvement-queue", "--status", "open", "--queue-scope", "project",
            "--change-kind", "doc-edit", "--surface", rel, "--body-file", str(body),
            "--evidence", f"{_KEY_PREFIX}{key}; plan: {rel}"]
    try:
        return runner(argv)
    finally:
        body.unlink(missing_ok=True)


def _git_toplevel() -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
    except OSError as exc:
        raise AuditError(f"git unavailable: {exc}") from exc
    if out.returncode != 0 or not out.stdout.strip():
        raise AuditError("cwd is not inside a git repo; pass --root")
    return Path(out.stdout.strip())


def main(argv: Optional[Sequence[str]] = None, runner: Optional[Runner] = None,
         launcher: Optional[str] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", help="repo root (default: git toplevel of cwd)")
    ap.add_argument("--since", default=DEFAULT_SINCE)
    ap.add_argument("--plan", action="append", default=[], help="plan file; replaces the default population")
    ap.add_argument("--seed", action="store_true")
    args = ap.parse_args(argv)
    try:
        root = Path(args.root) if args.root else _git_toplevel()
        files = population(root, args.plan, args.since)
        scans = []
        for f in files:
            text = _read(f)
            try:
                rel = f.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                rel = f.as_posix()
            hits = find_hits(text)
            if hits:
                scans.append((rel, plan_key(text, rel), hits))
        if args.seed and scans:
            launcher = launcher or resolve_launcher()
            if not launcher:
                raise AuditError("coordinator-queue-append not found on PATH or in COORDINATOR_SETTINGS_HOME/bin")
    except AuditError as exc:
        print(f"deferral-prose-audit: could not check: {exc}", file=sys.stderr)
        return 2

    total = sum(len(h) for _, _, h in scans)
    for rel, _, hits in scans:
        for h in hits:
            print(f"{rel}:{h.line_no}: {h.text.strip()}")
    seeded = skipped = unseeded = 0
    failed = False
    for rel, key, hits in scans:
        if already_seeded(root, key):
            skipped += 1
        elif args.seed:
            if seed_plan(launcher, root, rel, key, hits, runner or _subprocess_runner) == 0:
                seeded += 1
            else:
                failed = True
                print(f"deferral-prose-audit: queue-append failed for {rel}", file=sys.stderr)
        else:
            unseeded += 1
    print(f"deferral-prose-audit: {total} hit(s) in {len(scans)} plan(s); seeded {seeded}, already-seeded {skipped}")
    if failed:
        return 2
    return 1 if unseeded else 0


if __name__ == "__main__":
    sys.exit(main())
