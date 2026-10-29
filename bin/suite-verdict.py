"""suite-verdict -- run the full suite once, bisect each red to its first-red commit, and record the verdict.

The EM launches this in the background under a live tier-u grant; fold and publish only read the
file it writes (`state/warp/suite-verdicts/<sha>.json`, the SuiteVerdict shape of
`coordinator_core.ops.dispatch_emit.run_truth_contract`). Bulk work, outside the 500ms bar.

Invoked as `python coordinator/bin/suite-verdict.py [--repo R] [--sha S] [--good G] [-- <test cmd>]`.
Without a command it runs `<this interpreter> -m pytest -q -rfE -p no:cacheprovider`; the nodeid of each
red is appended to the same command for the bisect. A command after `--` records tier "custom",
which fold_bar refuses as not "full". Exit codes:
  0 = written green, or written UNAVAILABLE (tier "unavailable": pytest not importable, no command given)
  1 = written with reds, or nothing parseable
  2 = usage
  3 = refused (no live grant) or engine unreachable

Each red records `first_red_commit`, its subject, and `bar`: the test file that should have caught it at that
commit (the carrier for a bug-blitz fold's bisect and why-no-bar requirement; fold_bar reads it, never re-derives).

Negative-spec: never touches the working tree (each probe runs in a `git archive` export of one
commit), never hard-codes an interpreter version, never writes without a live grant.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Callable, Optional

_REFUSED = 3
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_DEFAULT_CMD = ("-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider")
# `\S+` cuts a parametrized id containing a space; the cut id never reproduces, so it records unbisected (non-green).
_RED_LINE = re.compile(r"^(?:FAILED|ERROR) (\S+)")
_COUNT = re.compile(r"(\d+) (failed|passed|skipped|error|errors)\b")

GrantCheck = Callable[[], "tuple[bool, str]"]


def _shared_git_run():
    """`coordinator_core.git.run.run_git`, with the engine put on sys.path first when the script runs bare."""
    try:
        from coordinator_core.git.run import run_git
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        require_dispatch_engine_on_path()
        from coordinator_core.git.run import run_git
    return run_git


def _git_text(repo: Path, *args: str) -> str:
    res = _shared_git_run()(["-C", str(repo), *args])
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout.strip()


def parse_suite_output(text: str) -> Optional[dict]:
    """Counts and red nodeids from a pytest `-q -rf` transcript; None when no summary line exists."""
    reds: list[str] = []
    for line in text.splitlines():
        m = _RED_LINE.match(line)
        if m and m.group(1) not in reds:
            reds.append(m.group(1))
    counts = {"failed": 0, "passed": 0, "skipped": 0}
    seen = False
    for line in text.splitlines():
        if _RED_LINE.match(line) or " in " not in line or not _COUNT.search(line):
            continue
        for n, kind in _COUNT.findall(line):
            seen = True
            counts["failed" if kind.startswith("error") or kind == "failed" else kind] += int(n)
    if not seen:
        return None
    return {**counts, "reds": reds}


def _export(repo: Path, commit: str, dest: Path) -> None:
    res = _shared_git_run()(["-C", str(repo), "archive", commit], binary=True)
    if res.returncode != 0:
        raise RuntimeError(f"git archive {commit} failed: {res.stderr.strip()}")
    with tarfile.open(fileobj=io.BytesIO(res.stdout_bytes)) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:
            tar.extractall(dest)


def _red_at(repo: Path, commit: str, cmd: list[str], nodeid: str, scratch: Path) -> bool:
    """True iff `nodeid` fails (pytest exit 1, or 2 for a collection error) in an export of `commit`; absent test is not red."""
    work = Path(tempfile.mkdtemp(prefix="probe-", dir=scratch))
    try:
        _export(repo, commit, work)
        proc = subprocess.run(
            [*cmd, nodeid], cwd=work, capture_output=True, text=True, creationflags=_NO_WINDOW,
        )
        return proc.returncode in (1, 2)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def first_red_commit(repo: Path, commits: list[str], nodeid: str, cmd: list[str], scratch: Path) -> str:
    """Binary-search `commits` (first-parent, oldest first, ending at the verdict sha) for the first commit where `nodeid` is red.

    Returns "" when the red does not reproduce in isolation at the last commit (flaky or order-dependent): an
    unbisected red, which keeps the verdict non-green.
    """
    if not commits or not _red_at(repo, commits[-1], cmd, nodeid, scratch):
        return ""
    lo, hi = 0, len(commits) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if _red_at(repo, commits[mid], cmd, nodeid, scratch):
            hi = mid
        else:
            lo = mid + 1
    return commits[lo]


def build_verdict(
    repo: Path, sha: str, cmd: list[str], grant_ref: str, good: Optional[str] = None
) -> Optional[dict]:
    """Run the suite on an export of `sha`, bisect each red; None when the run produced no summary."""
    with tempfile.TemporaryDirectory(prefix="suite-verdict-") as tmp:
        scratch = Path(tmp)
        work = scratch / "head"
        work.mkdir()
        _export(repo, sha, work)
        proc = subprocess.run(
            cmd, cwd=work, capture_output=True, text=True, creationflags=_NO_WINDOW,
        )
        parsed = parse_suite_output(proc.stdout + "\n" + proc.stderr)
        if parsed is None:
            return None
        rng = f"{good}..{sha}" if good else sha
        commits = _git_text(repo, "rev-list", "--first-parent", "--reverse", rng).split() if parsed["reds"] else []
        firsts = {nid: first_red_commit(repo, commits, nid, cmd, scratch) for nid in parsed["reds"]}
        subjects = _subjects(repo, sorted({c for c in firsts.values() if c}))
        reds = [
            {
                "nodeid": nid,
                "first_red_commit": first,
                "first_red_subject": subjects.get(first, ""),
                "bar": nid.split("::", 1)[0],
            }
            for nid, first in firsts.items()
        ]
    return {
        "sha": sha, "tier": "full", "failed": parsed["failed"], "passed": parsed["passed"],
        "skipped": parsed["skipped"], "reds": reds, "grant_ref": grant_ref,
    }


def _subjects(repo: Path, commits: list[str]) -> "dict[str, str]":
    """Subject line per commit, batched into one `git log --no-walk` call."""
    if not commits:
        return {}
    out = _git_text(repo, "log", "--no-walk=unsorted", "--format=%H%x09%s", *commits)
    return dict(line.split("\t", 1) for line in out.splitlines() if "\t" in line)


def unavailable_verdict(sha: str, grant_ref: str, reason: str) -> dict:
    """A verdict that measured nothing: tier is not "full", so fold_bar refuses it."""
    return {
        "sha": sha, "tier": "unavailable", "failed": 0, "passed": 0, "skipped": 0,
        "reds": [], "grant_ref": grant_ref, "unavailable": reason,
    }


def write_verdict(repo: Path, verdict: dict) -> Path:
    path = repo / "state" / "warp" / "suite-verdicts" / f"{verdict['sha']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def _engine_grant_check() -> "tuple[bool, str]":
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import require_dispatch_engine_on_path

        require_dispatch_engine_on_path()
        import coordinator_core.session.grant_directive as directive
    except (ImportError, RuntimeError) as exc:
        return False, f"engine unreachable: {exc}"
    code, message = directive.run_grant_directive(["check"])
    return code == 0, message


def main(argv: list[str], grant_check: Optional[GrantCheck] = None) -> int:
    if "--" in argv:
        i = argv.index("--")
        argv, tail = argv[:i], argv[i + 1:]
    else:
        tail = []
    ap = argparse.ArgumentParser(prog="suite-verdict")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--sha", default="HEAD")
    ap.add_argument("--good", default=None, help="last known-green commit bounding the bisect")
    args = ap.parse_args(argv)

    granted, ref = (grant_check or _engine_grant_check)()
    if not granted:
        print(f"suite-verdict: refused, no live tier-u grant ({ref})", file=sys.stderr)
        return _REFUSED

    repo = Path(args.repo).resolve()
    sha = _git_text(repo, "rev-parse", args.sha)
    if not tail and importlib.util.find_spec("pytest") is None:
        verdict = unavailable_verdict(sha, ref, "pytest not importable; install with: pip install pytest")
        print(write_verdict(repo, verdict))
        return 0
    cmd = tail or [sys.executable, *_DEFAULT_CMD]
    verdict = build_verdict(repo, sha, cmd, ref, args.good)
    if verdict is None:
        print("suite-verdict: no test summary in the run output; nothing written", file=sys.stderr)
        return 1
    if tail:
        verdict["tier"] = "custom"
    print(write_verdict(repo, verdict))
    return 0 if not verdict["failed"] and not verdict["reds"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
