#!/usr/bin/env python3
"""bookkeeping-plan-ledger.py -- plans under docs/plans that reached a terminal status in a window.

Usage:
    bookkeeping-plan-ledger.py daily [ROOT] [--repo ROOT] [--since ISO] [--until ISO]
                                     [--format md|json]
    bookkeeping-plan-ledger.py weekly-candidates [ROOT] [--repo ROOT] [--week-start MONDAY]
                                     [--max N] [--preview-chars N] [--format md|json]

ROOT is a git work tree (default "."). `daily` defaults to the 24h ending now;
`weekly-candidates` to the current Monday-start week (--week-start must be a Monday)
and keeps the top --max (default 8) rows. A row is a plan whose frontmatter `status`
is terminal at the window's newest commit and was not terminal (or absent) at the last
commit before the window; `commit` is that newest commit, so `git show COMMIT:PATH`
recovers the plan. A plan added and deleted inside one window is not listed.
Rows rank by the plan's sizing `estimate.tshirt`, XXL first, `?` (unreadable) last.

md output, one bullet per row: `- [TSHIRT] TITLE -- SUMMARY (PATH @ SHA)`.
--preview-chars N (default 0, off) appends the first N chars of the plan.

Cost: four git spawns (two rev-list, diff --raw, one cat-file --batch) however many commits
or plans the window holds; stdlib only. Exit: 0 listed (an empty window lists
nothing), 1 ROOT is not a git work tree or git failed, 2 bad arguments.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys

PLANS_DIR = "docs/plans"
TERMINAL_STATUSES = frozenset(
    {"implemented", "landed", "complete", "closed_partial", "superseded", "abandoned", "closed"}
)
TSHIRT_ORDER = {"XXL": 5, "XL": 4, "L": 3, "M": 2, "S": 1, "XS": 0}
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
SHORT_SHA = 10
SUMMARY_CAP = 200
_KEY_LINE = re.compile(r"^([A-Za-z_][\w-]*):[ \t]*(.*?)\s*$")
_TSHIRT_LINE = re.compile(r"^[ \t]+tshirt:[ \t]*([A-Za-z]+)")


_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _scalar(raw: str) -> str:
    """Unquote a frontmatter scalar; drop a trailing ` # comment` on a bare one."""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        return raw[1:end] if end > 0 else raw[1:]
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def parse_frontmatter(text: str) -> dict[str, str]:
    """Top-level scalar keys of the leading `---` block; {} when there is none."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = _KEY_LINE.match(line)
        if m and m.group(1) not in out:
            out[m.group(1)] = _scalar(m.group(2))
    return out


def status_of(text: str) -> str:
    """Lower-cased first word of the frontmatter `status`, or ''."""
    words = parse_frontmatter(text).get("status", "").split()
    return words[0].lower() if words else ""


def tshirt_of(sizing_text: str) -> str:
    """`estimate.tshirt` of a sizing object, or `?`."""
    in_estimate = False
    for line in sizing_text.splitlines():
        if line.startswith("estimate:"):
            in_estimate = True
        elif in_estimate:
            m = _TSHIRT_LINE.match(line)
            if m:
                t = m.group(1).upper()
                return t if t in TSHIRT_ORDER else "?"
            if line.strip() and not line[0].isspace():
                break
    return "?"


def problem_line(text: str) -> str:
    """First non-heading, non-blank line under `## Problem`, else ''."""
    in_problem = False
    for line in text.splitlines():
        if line.startswith("## "):
            if in_problem:
                break
            in_problem = line.strip().lower() == "## problem"
        elif in_problem and line.strip() and not line.lstrip().startswith("#"):
            return line.strip()
    return ""


def is_plan_path(rel: str) -> bool:
    """A plan body, not a `<stem>.review.md` / `.prior-art-check.md` sidecar."""
    name = rel.rsplit("/", 1)[-1]
    return name.endswith(".md") and "." not in name[:-3]


class GitError(RuntimeError):
    """A git spawn failed (ROOT not a work tree, bad revision)."""


def _run(root: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", root, *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", creationflags=_NO_WINDOW,
    )
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {args[0]} exited {proc.returncode}")
    return proc.stdout


class Objects:
    """One `git cat-file --batch` process answering `<rev>:<path>` / blob-id lookups."""

    def __init__(self, root: str) -> None:
        self._p = subprocess.Popen(
            ["git", "-C", root, "cat-file", "--batch"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=False, creationflags=_NO_WINDOW,
        )
        assert self._p.stdin is not None and self._p.stdout is not None
        self._in = self._p.stdin
        self._out = self._p.stdout

    def get(self, spec: str) -> str | None:
        """Text of the object `spec` names, or None when it does not exist."""
        self._in.write(spec.encode("utf-8") + b"\n")
        self._in.flush()
        header = self._out.readline().split()
        if len(header) != 3:
            return None
        size = int(header[2])
        body = self._out.read(size + 1)[:size]
        return body.decode("utf-8", errors="replace")

    def close(self) -> None:
        self._in.close()
        self._p.wait()


def window_edges(root: str, since: str, until: str) -> tuple[str, str] | None:
    """(base, newest): the last commit at or before `since` (empty tree when none) and the
    last at or before `until`; None when no commit falls inside the window."""
    newest = _run(root, "rev-list", "-n1", f"--until={until}", "HEAD").strip()
    if not newest:
        return None
    base = _run(root, "rev-list", "-n1", f"--until={since}", newest).strip()
    if base == newest:
        return None
    return base or EMPTY_TREE, newest


def changed_plans(root: str, base: str, newest: str) -> list[tuple[str, str, str]]:
    """(path, old blob, new blob) of plan bodies added or modified between the window edges."""
    out = _run(
        root, "diff", "--raw", "-z", "--no-renames", "--no-abbrev", "--diff-filter=AM",
        base, newest, "--", PLANS_DIR,
    )
    tok = out.split("\x00")
    rows = []
    for i in range(0, len(tok) - 1, 2):
        meta = tok[i].lstrip(":").split()
        if len(meta) >= 5 and is_plan_path(tok[i + 1]):
            rows.append((tok[i + 1], meta[2], meta[3]))
    return rows


def _terminal_blob(objs: Objects, spec: str) -> bool:
    if set(spec) <= {"0"}:
        return False
    text = objs.get(spec)
    return text is not None and status_of(text) in TERMINAL_STATUSES


def build_rows(root: str, since: str, until: str, preview_chars: int = 0) -> list[dict]:
    """Ranked rows for the window; [] when it holds no commit."""
    edges = window_edges(root, since, until)
    if edges is None:
        return []
    base, newest = edges
    rows = []
    objs = Objects(root)
    try:
        for path, old_blob, new_blob in changed_plans(root, base, newest):
            if not _terminal_blob(objs, new_blob) or _terminal_blob(objs, old_blob):
                continue
            text = objs.get(new_blob) or ""
            fm = parse_frontmatter(text)
            sizing = fm.get("sizing_object", "")
            sizing_text = objs.get(f"{newest}:{sizing}") if sizing and sizing != "null" else None
            title = fm.get("title") or path.rsplit("/", 1)[-1][:-3]
            summary = fm.get("summary") or problem_line(text) or title
            row = {
                "plan_path": path,
                "title": title,
                "summary": " ".join(summary.split())[:SUMMARY_CAP],
                "tshirt": tshirt_of(sizing_text) if sizing_text else "?",
                "commit": newest[:SHORT_SHA],
                "status": status_of(text),
            }
            if preview_chars > 0:
                row["preview"] = text[:preview_chars]
            rows.append(row)
    finally:
        objs.close()
    rows.sort(key=lambda r: (-TSHIRT_ORDER.get(r["tshirt"], -1), r["plan_path"]))
    return rows


def render_md(rows: list[dict]) -> str:
    out = []
    for r in rows:
        said = r["title"] if r["summary"] == r["title"] else f"{r['title']} -- {r['summary']}"
        out.append(f"- [{r['tshirt']}] {said} ({r['plan_path']} @ {r['commit']})")
        if r.get("preview"):
            out.append("  ```\n" + "\n".join("  " + ln for ln in r["preview"].splitlines()) + "\n  ```")
    return "\n".join(out)


def _aware(value: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(value)
    return d if d.tzinfo else d.astimezone()


def window_for(args: argparse.Namespace, now: dt.datetime) -> tuple[str, str]:
    """(since, until) ISO strings for the subcommand; ValueError on bad input."""
    if args.cmd == "daily":
        until = _aware(args.until) if args.until else now
        since = _aware(args.since) if args.since else until - dt.timedelta(days=1)
        return since.isoformat(), until.isoformat()
    if args.week_start:
        start = dt.date.fromisoformat(args.week_start)
        if start.weekday() != 0:
            raise ValueError(f"--week-start {args.week_start} is not a Monday")
    else:
        start = now.date() - dt.timedelta(days=now.weekday())
    since = dt.datetime.combine(start, dt.time()).astimezone()
    return since.isoformat(), (since + dt.timedelta(days=7)).isoformat()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bookkeeping-plan-ledger.py", description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daily", help="plans terminal in a window (default 24h ending now)")
    d.add_argument("--since", help="ISO date or datetime")
    d.add_argument("--until", help="ISO date or datetime")
    w = sub.add_parser("weekly-candidates", help="top plans terminal in a Monday-start week")
    w.add_argument("--week-start", help="a Monday, YYYY-MM-DD (default current week)")
    w.add_argument("--max", type=int, default=8, help="rows kept (default 8)")
    w.add_argument("--preview-chars", type=int, default=0, help="plan preview length (default off)")
    for p in (d, w):
        p.add_argument("root", nargs="?", default=None)
        p.add_argument("--repo", default=None)
        p.add_argument("--format", choices=("md", "json"), default="md")
    args = ap.parse_args(argv)

    root = args.repo or args.root or "."
    try:
        since, until = window_for(args, dt.datetime.now().astimezone())
    except ValueError as exc:
        print(f"bookkeeping-plan-ledger: {exc}", file=sys.stderr)
        return 2
    try:
        rows = build_rows(root, since, until, getattr(args, "preview_chars", 0))
    except (GitError, OSError) as exc:
        print(f"bookkeeping-plan-ledger: {exc}", file=sys.stderr)
        return 1
    if args.cmd == "weekly-candidates":
        rows = rows[: max(args.max, 0)]
    print(json.dumps(rows) if args.format == "json" else render_md(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
