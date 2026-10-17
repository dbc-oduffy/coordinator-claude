# guard-not-a-hook-entrypoint
# Native git pre-commit hook, not a hooks.json entrypoint: the commit's own
# index is only directly readable at pre-commit time.
"""Native git pre-commit hook: refuse a commit that grows the skill fleet past
its resident limit, or a skill past its banded ceiling.

THE MEASURED TREE IS THE COMMIT'S OWN INDEX, never the shared working tree.
For a pathspec commit git hands the hook a temporary index holding the
author's bytes for exactly the committed paths, so the figure charged is the
committer's own. Measuring the working tree (`rev=None`) would charge a peer's
uncommitted edit to the committer.

ALL LOGIC LIVES IN `_skill_weight_admission.py` (pure predicate) and the
harness's `sizes=` seam. This file is the untested-by-spawn wrapper: read
git, hand the mappings over, print, exit.

NEVER TAKES `.git/index.lock`: every git call is a read under
`--no-optional-locks` (`git write-tree` is rejected for that reason). It
inherits `GIT_INDEX_FILE` deliberately, so the temporary index of a pathspec
commit is what `ls-files` reads.

Modes: default reads the index; `--tree T --base B` measures two tree-ishes
(the seam for the engine commit route, which runs no git hook).

A baseline edit that raises any limit or floor against the base revision is
refused (`limit_raises`); the override hint is not printed for it.

Fail-open: a plumbing failure prints a one-line "did not run" note and exits
0; only a measured violation exits 1. Override:
COORDINATOR_OVERRIDE_PRECOMMIT_SKILL_WEIGHT_BUDGET.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = Path(__file__).resolve().parent
_TESTS = _ROOT / "coordinator" / "tests"
for _p in (_SCRIPTS, _TESTS, _TESTS / "fixtures" / "skill-weight"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

OVERRIDE_ENV = "COORDINATOR_OVERRIDE_PRECOMMIT_SKILL_WEIGHT_BUDGET"
_SKILLS_PREFIX = "coordinator/skills/"
_BASELINE_PATH = "coordinator/tests/baselines/skill-weight-budget.json"
_ADMISSION_PATH = "coordinator/hooks/scripts/_skill_weight_admission.py"
_TAG = "[skill-weight-budget-guard]"


class _GitFailure(Exception):
    pass


def _git(*args: str, stdin: bytes = b"") -> bytes:
    cmd = ["git", "--no-optional-locks", *args]
    try:
        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise _GitFailure(f"{' '.join(cmd[:3])}: {exc}") from exc
    if proc.returncode != 0:
        raise _GitFailure(f"{' '.join(cmd[:3])} exited {proc.returncode}")
    return proc.stdout


def staged_paths() -> "list[str]":
    out = _git("diff", "--cached", "--name-only", "-z").decode("utf-8", "surrogateescape")
    return [p for p in out.split("\0") if p]


def index_sizes() -> "dict[str, int]":
    """`{path: byte size}` for the skills in the index, from one `ls-files -s`
    and one `cat-file --batch-check`."""
    out = _git("ls-files", "-s", "-z", "--", "coordinator/skills").decode(
        "utf-8", "surrogateescape"
    )
    oid_of: "dict[str, str]" = {}
    for entry in out.split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        fields = meta.split()
        if len(fields) == 3 and fields[0] != "160000":
            oid_of[path] = fields[1]
    if not oid_of:
        return {}
    oids = sorted(set(oid_of.values()))
    checked = _git("cat-file", "--batch-check", stdin=("\n".join(oids) + "\n").encode())
    size_of: "dict[str, int]" = {}
    for line in checked.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] == "blob":
            size_of[parts[0]] = int(parts[2])
    return {path: size_of[oid] for path, oid in oid_of.items() if oid in size_of}


def committed_sizes(rev: str) -> "dict[str, int]":
    from _git_history import committed_blob_sizes

    sizes = committed_blob_sizes(_ROOT, rev)
    if not sizes:
        raise _GitFailure(f"no tree readable at {rev}")
    return sizes


def read_baseline(ref: str) -> dict:
    """`ref` is `:` for the index or `<tree-ish>:` for a tree."""
    return json.loads(_git("show", f"{ref}{_BASELINE_PATH}").decode("utf-8"))


def read_base_baseline(rev: str) -> "dict | None":
    """The baseline at `rev`, or None when that revision carries no baseline
    blob. Any other git failure still raises `_GitFailure`."""
    if not _git("ls-tree", rev, "--", _BASELINE_PATH).strip():
        return None
    return read_baseline(f"{rev}:")


def _resident(sizes: "dict[str, int]") -> "dict[str, int]":
    import skill_weight_harness as harness

    measured = harness.measure_all_skills(sizes=sizes)
    return {name: row["resident"] for name, row in measured.items()}


def _check(proposed_sizes, base_sizes, baseline, base_baseline) -> int:
    from _skill_weight_admission import admission_violations, limit_raises

    violations = admission_violations(
        _resident(proposed_sizes), _resident(base_sizes), baseline
    )
    raises = limit_raises(baseline, base_baseline)
    if raises:
        print(
            f"{_TAG} commit refused: a limit is never raised to admit growth; cut skill text",
            file=sys.stderr,
        )
        for line in raises + violations:
            print(f"  {line}", file=sys.stderr)
        return 1
    if not violations:
        return 0
    print(f"{_TAG} commit refused: skill growth over budget", file=sys.stderr)
    for line in violations:
        print(f"  {line}", file=sys.stderr)
    print(f"  override: {OVERRIDE_ENV}=1", file=sys.stderr)
    return 1


def main(argv: "list[str]") -> int:
    if os.environ.get(OVERRIDE_ENV):
        return 0
    tree = base = None
    args = list(argv)
    while args:
        flag = args.pop(0)
        if flag == "--tree" and args:
            tree = args.pop(0)
        elif flag == "--base" and args:
            base = args.pop(0)
        else:
            print(f"{_TAG} usage: [--tree <tree-ish> --base <rev>]", file=sys.stderr)
            return 0
    if (tree is None) != (base is None):
        print(f"{_TAG} --tree and --base go together", file=sys.stderr)
        return 0
    try:
        if tree is not None:
            return _check(
                committed_sizes(tree),
                committed_sizes(base),
                read_baseline(f"{tree}:"),
                read_base_baseline(base),
            )
        staged = staged_paths()
        if not any(
            p.startswith(_SKILLS_PREFIX) or p in (_BASELINE_PATH, _ADMISSION_PATH)
            for p in staged
        ):
            return 0
        return _check(
            index_sizes(),
            committed_sizes("HEAD"),
            read_baseline(":"),
            read_base_baseline("HEAD"),
        )
    except (_GitFailure, ValueError, KeyError, OSError, ImportError) as exc:
        print(f"{_TAG} did not run this commit: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
