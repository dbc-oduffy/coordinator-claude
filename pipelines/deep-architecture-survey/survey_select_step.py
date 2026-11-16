"""EM-side selector for the deep architecture survey's refresh mode.

Picks the changed systems and the plans behind them by a deterministic git query, writes a
bounded preview of each plan under ``state/scratch/deep-architecture-survey/<run-id>/``, and
prints one ``survey-selection/1`` JSON object on stdout. Exit 0 with JSON, 2 on a usage error or
a non-git root. No model call.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

import yaml

# DR-1649 rule 2: a model reads a bounded preview of a plan, never the whole backlog.
PREVIEW_CAP_CHARS = 10000
MAX_PLANS_PER_SYSTEM = 5
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
SCHEMA = "survey-selection/1"
PLAN_ROOTS = ("docs/plans", "archive")
TSHIRT_RANK = {"XL": 5, "L": 4, "M": 3, "S": 2, "XS": 1}
UNRANKED = 0
SPINE_RE = re.compile(r"```yaml plan-tasks[^\n]*\n(.*?)\n```", re.S)
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
INDEX_ROW_RE = re.compile(r"^\|\s*\[([^\]]+)\]\([^)]*\)\s*\|\s*`([^`]+)`")


def _no_console() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def scratch_dir(repo_root: Path, run_id: str) -> Path:
    return repo_root / "state" / "scratch" / "deep-architecture-survey" / run_id


class GitError(Exception):
    """A git argv exited non-zero."""


# The one git seam: argv (without the leading `git`) in, stdout out, GitError on non-zero exit.
GitReader = Callable[[Sequence[str]], str]


def subprocess_git_reader(repo_root: Path) -> GitReader:
    """Production reader: runs git against `repo_root` with an argument list, no shell."""

    def read(argv: Sequence[str]) -> str:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *argv],
            capture_output=True,
            creationflags=_no_console(),
        )
        if proc.returncode != 0:
            raise GitError(proc.stderr.decode("utf-8", "replace").strip())
        return proc.stdout.decode("utf-8", "replace")

    return read


def _try(git: GitReader, *argv: str) -> str | None:
    try:
        return git(argv)
    except GitError:
        return None


def _frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def default_since(repo_root: Path) -> str | None:
    index = repo_root / "docs" / "architecture" / "systems-index.md"
    if not index.is_file():
        return None
    value = _frontmatter(index.read_text(encoding="utf-8")).get("last_mapped")
    return str(value) if value else None


def default_system_dirs(repo_root: Path) -> dict:
    """System name to dirs, read from the atlas index's system table (name link, backticked root)."""
    index = repo_root / "docs" / "architecture" / "systems-index.md"
    dirs: dict = {}
    if index.is_file():
        for line in index.read_text(encoding="utf-8").splitlines():
            m = INDEX_ROW_RE.match(line)
            if m:
                dirs[m.group(1)] = [m.group(2)]
    return dirs


def load_system_dirs(path: str | None, repo_root: Path) -> dict:
    if not path:
        return default_system_dirs(repo_root)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("system_dirs"), dict):
        data = data["system_dirs"]
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a system-to-dirs object")
    return {k: [v] if isinstance(v, str) else list(v) for k, v in data.items()}


def base_sha(git: GitReader, since: str) -> str:
    sha = (_try(git, "rev-list", "-1", f"--before={since} 23:59:59", "HEAD") or "").strip()
    return sha or EMPTY_TREE_SHA


def changed_files(git: GitReader, base: str, dirs: list) -> int:
    out = _try(git, "diff", "--name-only", f"{base}..HEAD", "--", *dirs) or ""
    return len([ln for ln in out.splitlines() if ln.strip()])


def plan_events(git: GitReader, since: str) -> list:
    """Latest event per plan path since `since`, newest first: (path, status, commit, recency)."""
    out = _try(git, "log", f"--since={since}", "--no-renames", "--name-status",
               "--format=%x00%H", "--", *PLAN_ROOTS) or ""
    seen, events = set(), []
    for block in out.split("\x00"):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        commit = lines[0].strip()
        for ln in lines[1:]:
            status, _, path = ln.partition("\t")
            if not path.endswith(".md") or path in seen:
                continue
            seen.add(path)
            events.append((path, status[:1], commit, len(events)))
    return events


def read_plan(git: GitReader, path: str, status: str, commit: str) -> tuple[str, str] | None:
    """Return (sha, text). A deleted plan is read at the deleting commit's parent."""
    sha = f"{commit}^" if status == "D" else commit
    text = _try(git, "show", f"{sha}:{path}")
    if text is None:
        return None
    if status == "D":
        sha = (_try(git, "rev-parse", sha) or "").strip() or sha
    return sha, text


def spine_writes(text: str) -> list | None:
    """Writes and writes_under paths across the plan spine; None when the plan has no spine."""
    m = SPINE_RE.search(text)
    if not m:
        return None
    try:
        rows = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    if not isinstance(rows, list):
        return None
    paths = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("writes", "writes_under"):
            value = row.get(key) or []
            paths.extend([value] if isinstance(value, str) else [str(v) for v in value])
    return paths


def sizing_rank(repo_root: Path, text: str) -> int:
    ref = _frontmatter(text).get("sizing_object")
    if not isinstance(ref, str) or not ref:
        return UNRANKED
    path = repo_root / ref
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        tshirt = str(data["estimate"]["tshirt"]).upper()
    except (OSError, yaml.YAMLError, KeyError, TypeError):
        return UNRANKED
    return TSHIRT_RANK.get(tshirt, UNRANKED)


def _within(path: str, directory: str) -> bool:
    d = directory.strip("/")
    p = path.strip("/")
    return p == d or p.startswith(d + "/")


def touches(writes: list, dirs: list) -> bool:
    return any(_within(w, d) or _within(d, w) for w in writes for d in dirs)


def collect_plans(git: GitReader, repo_root: Path, since: str) -> tuple[list, int]:
    plans, without_spine = [], 0
    for path, status, commit, recency in plan_events(git, since):
        got = read_plan(git, path, status, commit)
        if got is None:
            continue
        sha, text = got
        writes = spine_writes(text)
        if writes is None:
            without_spine += 1
            continue
        plans.append({
            "path": path, "sha": sha, "writes": writes, "recency": recency,
            "rank": sizing_rank(repo_root, text), "text": text,
            "recovered_from_git": status == "D",
        })
    return plans, without_spine


def write_previews(sdir: Path, chosen: list) -> None:
    pdir = sdir / "previews"
    pdir.mkdir(parents=True, exist_ok=True)
    for plan in chosen:
        if "preview_path" in plan:
            continue
        preview = plan["text"][:PREVIEW_CAP_CHARS]
        target = pdir / f"{plan['n']}.md"
        target.write_text(preview, encoding="utf-8", newline="")
        plan["preview_path"] = target.relative_to(sdir.parents[3]).as_posix()
        plan["preview_chars"] = len(preview)


def select(git: GitReader, repo_root: Path, run_id: str, since: str, system_dirs: dict) -> dict:
    base = base_sha(git, since)
    plans, without_spine = collect_plans(git, repo_root, since)
    for n, plan in enumerate(plans, 1):
        plan["n"] = n
    changed, stable = [], []
    for name in sorted(system_dirs):
        dirs = system_dirs[name]
        count = changed_files(git, base, dirs)
        if count == 0:
            stable.append(name)
            continue
        matching = [p for p in plans if touches(p["writes"], dirs)]
        matching.sort(key=lambda p: (-p["rank"], p["recency"]))
        changed.append({"name": name, "changed_files": count, "plans": matching[:MAX_PLANS_PER_SYSTEM]})
    unique = {p["path"]: p for s in changed for p in s["plans"]}
    write_previews(scratch_dir(repo_root, run_id), list(unique.values()))
    for system in changed:
        system["plans"] = [
            {"path": p["path"], "sha": p["sha"], "preview_path": p["preview_path"],
             "preview_chars": p["preview_chars"], "recovered_from_git": p["recovered_from_git"]}
            for p in system["plans"]
        ]
    return {
        "schema": SCHEMA, "since": since, "base_sha": base,
        "preview_cap_chars": PREVIEW_CAP_CHARS,
        "changed_systems": changed, "stable_systems": stable,
        "plans_without_spine": without_spine,
    }


def main(argv: list | None = None, git: GitReader | None = None) -> int:
    """CLI entry; `git` injects the git reader (default: subprocess against --repo-root)."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--since")
    ap.add_argument("--system-dirs")
    args = ap.parse_args(argv)
    if not RUN_ID_RE.fullmatch(args.run_id):
        sys.stderr.write(f"--run-id must match {RUN_ID_RE.pattern}: {args.run_id!r}\n")
        return 2
    repo_root = Path(args.repo_root)
    git = git or subprocess_git_reader(repo_root)
    if _try(git, "rev-parse", "--git-dir") is None:
        sys.stderr.write(f"not a git repository: {repo_root}\n")
        return 2
    since = args.since or default_since(repo_root)
    if not since:
        sys.stderr.write("--since not given and systems-index.md carries no last_mapped\n")
        return 2
    try:
        system_dirs = load_system_dirs(args.system_dirs, repo_root)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"system dirs input error: {exc}\n")
        return 2
    print(json.dumps(select(git, repo_root, args.run_id, since, system_dirs), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
