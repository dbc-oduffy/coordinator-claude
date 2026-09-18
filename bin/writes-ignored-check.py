#!/usr/bin/env python3
"""writes-ignored-check — refuse a spine whose declared writes a commit cannot take.

Ported from DoE-claude `coordinator/bin/writes-ignored-check.py` (W3-C1,
`docs/plans/2026-09-18-doe-holds-no-scripts.md`). One path-resolution seam changed (§ Path
resolution): DoE's `_load_spine_reader` treated the engine as a sibling checkout it had to find
by a fallback ladder (`$HOME/claude-klabauter`, a `parents[3]` guess), because in DoE the engine
lives in a different repo. That reasoning no longer applies here -- this script now lives INSIDE
the engine it reads, so `spine_read` is an ordinary "engine" class import: this module's own
`__file__` parent chain IS the engine root, the same resolution `coordinator/bin/goal-kr-
evidence.py` already uses for `coordinator_core.group_em.atomic_record`. The fallback ladder is
deleted, not ported (§ Path resolution: "`_engine_root` imports are deleted, not ported").

WHY THIS EXISTS. A dispatchable row's ``writes:`` entries become a commit phase's
pathspec, and two kinds of path can never be in one. The refusal for both arrives at
PREFLIGHT — after the plan certifies, after the script is emitted, after a run is
launched — and it takes down every OTHER row in the wave with it. Both were measured on
project-rag-ue-addon on 2026-09-09, each halting a run that then did nothing:

  - GITIGNORED. One row declared a producer-staging sqlite3 under a PM-authorized ignore
    rule; the seven good rows sharing its plan never ran.
  - DIRECTORY-SHAPED IN FACT. Three rows declared ``tests``, ``docs/decisions`` and a
    vendor sample tree. The commit route refuses a directory because it stages whatever
    is tracked beneath it, a wider set than the row declared.

The engine ALREADY refuses directory-shaped writes and did not fire on those three. Its
predicate is ``path.endswith("/") or endswith("\\\\")``, purely syntactic, so a path with
no trailing slash emits cleanly and is caught only at preflight, by the agent that looks
at the real filesystem. ``is_dir()`` here catches that shape before emit.

**THIS TOOL DOES NOT SUPERSEDE THE ENGINE'S CHECK. THE TWO MISS OPPOSITE CASES.**
``is_dir()`` is blind to a directory that does not exist YET — a row declaring
``tests/fixtures/whatever/`` for a tree it will create reads here as an ordinary absent
path and passes, and only the engine's trailing slash catches it. The engine is blind to
a directory that DOES exist and carries no trailing slash. Measured 2026-09-09: two
plans in one batch, one of each shape, and running either check alone would have missed
one. So run this AND let the emitter refuse. A clean report here is not a promise that
emit will succeed, and was never meant to be one.

What this tool adds is the half a string cannot answer: ASK THE FILESYSTEM AND GIT. The
prep bar can do neither and should not try — it is pure and spawn-free, and both answers
depend on the target repo's real state.

IT IS A ONE-DIRECTIONAL CHECK. Both findings are always defects in the plan, never in
the repo. Do not narrow ``.gitignore`` — those rules are deliberate and often
PM-authorized. Do not let an executor narrow a directory to a file list at commit time
either; that silently re-widens on the next peer commit. Fix the ROW: name concrete
paths, or write a tracked record of what the row produced, or mark it
``execution_mode: operator`` when its product legitimately never enters the repo. An
uncommittable declared write is usually the tell that the row also needs a host, an
engine tree, or hours of wall clock.

IT READS ONLY DISPATCHABLE ROWS. ``read_spine`` already drops closed, deferred and
operator rows, and those are exactly the rows whose ``writes:`` no commit phase will
ever see. A closed row naming an untracked artifact is correct history, not a finding.
A declared path that does not exist YET is also not a finding — most writes are files a
row has not created.

Verdicts, one per plan:
  CLEAN          every declared write on every dispatchable row can reach a commit.
  BAD-WRITE-PATH at least one cannot. Each finding names the path, its kind
                 (``ignored`` or ``directory``), and the rows that would go down with it.
  NO-SPINE       no plan-tasks spine, or one with no declared writes. NOT a finding —
                 most plans in a corpus are prose.
  UNREADABLE-SPINE a spine exists and the reader refused it, usually a YAML defect such as
                 an unquoted value containing a colon. Carries the reader's own message in
                 ``detail``. This one IS a finding, and it is not the same as NO-SPINE.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

EXIT_CLEAN = 0
EXIT_BAD_WRITE_PATH = 1
EXIT_USAGE = 3
EXIT_NO_SPINE = 4
EXIT_UNREADABLE_SPINE = 5


def _load_spine_reader():
    """Import ``read_spine`` from this engine's own tree.

    This script lives inside the engine it reads (§ Path resolution, "engine" class): the
    module's own `__file__` parent chain is the engine root, not a sibling checkout to search
    for. This tool reads the engine's own spine reader on purpose — a second parser here would
    disagree with the emitter about which rows are dispatchable, which is the whole question.
    """
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from coordinator_core.ops.dispatch_emit import spine_read  # type: ignore  # noqa: E402
    return spine_read


def declared_write_paths(spine_read, plan_path: pathlib.Path):
    """Map each declared write path to the row ids declaring it, dispatchable rows only.

    Returns ``(paths, spine_error)``. ``spine_error`` is None when the spine read
    cleanly, otherwise the reader's own message — because ABSENT and MALFORMED are
    completely different situations and reporting both as "no spine" sends the
    reader to the wrong place. Most plans are prose and legitimately have no spine;
    a MALFORMED one has a spine that a YAML defect made unreadable, which is a
    defect to fix now. Measured: an unquoted ``status: shipped`` inside a ``note:``
    made a spine MALFORMED, and this tool called it "without a spine" — the author
    had to rediscover the real cause from the emitter instead.
    """
    try:
        rows = spine_read.read_spine(plan_path)
    except Exception as exc:
        message = str(exc)
        # The reader raises ONE error type for both situations and names which
        # inside the message, so branch on that rather than on the type. ABSENT
        # is the ordinary case — most plans in a corpus are prose — and must not
        # report as a defect; MALFORMED means a spine is there and a YAML fault
        # made it unreadable. Getting this backwards makes the tool cry wolf on
        # every prose plan, which is how a check stops being run.
        if "is ABSENT" in message:
            return {}, None
        return {}, f"{type(exc).__name__}: {message}"
    out: dict = {}
    for row in rows:
        writes = row.writes
        if writes is spine_read.UNDECLARED or not writes:
            continue
        for path in writes:
            out.setdefault(path, []).append(row.id)
    return out, None


def ignored_paths(repo_root: pathlib.Path, paths: list) -> set:
    """Return the subset of *paths* git refuses to track.

    One `git check-ignore --stdin` per plan, never one per path: the spawn is the
    cost here, and a per-path loop over a corpus of plans is how a cheap check
    becomes one nobody runs.
    """
    if not paths:
        return set()
    result = subprocess.run(
        ["git", "check-ignore", "--stdin", "-z"],
        input="".join(f"{p}\0" for p in paths).encode("utf-8"),
        capture_output=True,
        cwd=str(repo_root),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return {p for p in result.stdout.decode("utf-8").split("\0") if p}


def directory_paths(repo_root: pathlib.Path, paths: list) -> set:
    """Return the subset of *paths* that are directories on disk.

    The engine's own refusal is syntactic — ``path.endswith("/")`` — so a declared
    write of ``tests`` or ``docs/decisions`` passes emit and is caught only at
    preflight, by the commit agent that looks at the real filesystem, after a run
    has already been launched. Asking ``is_dir()`` here catches it before emit,
    which is the whole point of doing it in a checker rather than in a string test.

    A path that does not exist yet is NOT a finding: most declared writes are files
    a row has not created yet, and treating absence as a defect would fire on every
    healthy spine.
    """
    return {p for p in paths if (repo_root / p).is_dir()}


def check_plan(spine_read, repo_root: pathlib.Path, plan_path: pathlib.Path) -> dict:
    declared, spine_error = declared_write_paths(spine_read, plan_path)
    if spine_error is not None:
        return {"plan": plan_path.name, "verdict": "UNREADABLE-SPINE",
                "findings": [], "detail": spine_error}
    if not declared:
        return {"plan": plan_path.name, "verdict": "NO-SPINE", "findings": []}
    ignored = ignored_paths(repo_root, sorted(declared))
    directories = directory_paths(repo_root, sorted(declared))
    findings = [
        {"path": path, "rows": declared[path],
         "kind": "ignored" if path in ignored else "directory"}
        for path in sorted(ignored | directories)
    ]
    return {
        "plan": plan_path.name,
        "verdict": "BAD-WRITE-PATH" if findings else "CLEAN",
        "findings": findings,
    }


def _targets(raw: list) -> list:
    out = []
    for item in raw:
        p = pathlib.Path(item)
        if p.is_dir():
            out.extend(sorted(p.glob("*.md")))
        else:
            out.append(p)
    return out


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        prog="writes-ignored-check",
        description="Refuse a spine whose declared writes a commit cannot take.",
    )
    parser.add_argument("target", nargs="+", help="plan file(s) or a directory of them")
    parser.add_argument("--repo-root", default=None,
                        help="repo whose ignore rules decide; defaults to the plan's own repo")
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    args = parser.parse_args(argv[1:])

    targets = _targets(args.target)
    if not targets:
        print("writes-ignored-check: no plan files in that target", file=sys.stderr)
        return EXIT_USAGE

    spine_read = _load_spine_reader()
    reports = []
    for plan_path in targets:
        if args.repo_root:
            repo_root = pathlib.Path(args.repo_root)
        else:
            repo_root = plan_path.resolve().parent
            while repo_root != repo_root.parent and not (repo_root / ".git").exists():
                repo_root = repo_root.parent
        reports.append(check_plan(spine_read, repo_root, plan_path))

    if args.json:
        import json
        print(json.dumps(reports, indent=2))
    else:
        for report in reports:
            if report["verdict"] != "BAD-WRITE-PATH":
                continue
            print(f"BAD-WRITE-PATH  {report['plan']}")
            for finding in report["findings"]:
                rows = ", ".join(finding["rows"])
                print(f"    [{finding['kind']}] {finding['path']}  <- row(s) {rows}")
        for report in reports:
            if report["verdict"] != "UNREADABLE-SPINE":
                continue
            print(f"UNREADABLE-SPINE  {report['plan']}")
            print(f"    {report.get('detail', '')}")
        clean = sum(1 for r in reports if r["verdict"] == "CLEAN")
        nospine = sum(1 for r in reports if r["verdict"] == "NO-SPINE")
        unreadable = sum(1 for r in reports if r["verdict"] == "UNREADABLE-SPINE")
        bad = sum(1 for r in reports if r["verdict"] == "BAD-WRITE-PATH")
        print(f"\n{clean} clean, {bad} with a write path no commit can take, "
              f"{unreadable} with an unreadable spine, {nospine} without a spine")

    if any(r["verdict"] == "BAD-WRITE-PATH" for r in reports):
        return EXIT_BAD_WRITE_PATH
    if any(r["verdict"] == "UNREADABLE-SPINE" for r in reports):
        return EXIT_UNREADABLE_SPINE
    if reports and all(r["verdict"] == "NO-SPINE" for r in reports):
        return EXIT_NO_SPINE
    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main(sys.argv))
