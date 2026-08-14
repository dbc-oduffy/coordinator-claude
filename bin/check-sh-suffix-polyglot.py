"""bin/check-sh-suffix-polyglot.py — Tripwire: SH-SUFFIX-POLYGLOT-RATCHET

Purpose: Prevents NEW `.sh`-suffixed sh/python polyglot trampolines from being
added anywhere in the repo. A `.sh` suffix reads as "this is bash" — but a
polyglot trampoline file (line 2 is the verbatim
  ''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
shim, same invariant asserted by check-bin-sh-polyglot.py) contains ZERO bash;
the body is Python. That mismatched suffix is both a correctness-of-signal
problem (a human or agent counting `.sh` files reasonably but wrongly
concludes the bash-migration effort never happened — 136 of 516 tracked `.sh`
files repo-wide are pure-Python bodies wearing a bash costume) and a real
per-invocation cost: the sh-shim re-exec measures ~326ms/invocation on Windows
versus invoking the same Python body directly (1306ms via the shim vs 980ms
direct, byte-identical output — see state/audits/2026-07-20-sh-suffixed-
python-trampolines.md in the coordinator doctrine repo's clone, not this repo; the path is
qualified deliberately, and its absence here is not evidence it is missing).

This is a RATCHET, not a retroactive gate: 136 pre-existing offenders are
recorded in the checked-in baseline (sh-suffix-polyglot-baseline.txt, repo-
relative paths) and do NOT fail this check. Only a polyglot trampoline file
NOT in that baseline — i.e. a brand-new one, or an existing bash `.sh` file
that regresses into a polyglot without ever losing its `.sh` suffix — fails.
The baseline is itself the human-readable inventory of the backlog; renaming
a file out of the `.sh` suffix (the eventual fix — see coordinator-auto-push
and handoff-gate-aging for precedent) should remove its line from the
baseline in the same commit.

SCAN DOMAIN (widened 2026-07-20, PM-authorized): originally this scanned only
`coordinator/bin/*.sh` non-recursive (matching check-bin-sh-polyglot.py's
domain). That undercounted the real surface — ~25 polyglot trampolines live
under coordinator/lib/, coordinator/tests/, coordinator/hooks/, and elsewhere.
The scan domain is now every file `git ls-files '*.sh'` reports as tracked,
repo-wide. `git ls-files` (not a filesystem walk) is the enumerator so that
untracked scratch files, build output, and any future vendored/dist tree
never create phantom violations — only committed content is in scope, which
is also the only content a ratchet on NEW files needs to see.

Detection model (shared with check-bin-sh-polyglot.py — membership test is
UNCHANGED by the domain widening): a file is IN-CLASS iff it contains the
verbatim trampoline within its first 20 lines. Trampoline past line 20 would
be invisible to sh at exec time (treated as body code, not a re-exec), so it
would not actually be a live polyglot mismatch. This correctly excludes files
that merely reference `command -v python3` elsewhere in their body (e.g.
coordinator/bin/coordinator-write-review-trail-facade.test.sh, genuine bash
that calls `command -v python3` at line 40 — not a trampoline, not in-class).

Spec backlink: state/audits/2026-07-20-sh-suffixed-python-trampolines.md
  (coordinator doctrine repo clone — see the citation above for why this path does not
  resolve in this repo)
Doctrine: docs/wiki/cross-platform-shell-portability.md § sh/python trampoline
Companion check: coordinator/bin/check-bin-sh-polyglot.py (asserts every
  polyglot-class member — any suffix — has the correct shebang + trampoline,
  scoped to coordinator/bin/ only; this script asserts the inverse-direction
  invariant — that `.sh`-suffixed members repo-wide are NOT polyglot, except
  for the baselined backlog).

Usage:
    check-sh-suffix-polyglot.py                       Scan all tracked .sh files
                                                        repo-wide (git ls-files).
    check-sh-suffix-polyglot.py --staged               Scope to staged .sh files
                                                        only (suitable for
                                                        pre-commit).
    check-sh-suffix-polyglot.py --list-baseline-candidates
                                                        Print every current
                                                        offender (baselined or
                                                        not), one repo-relative
                                                        path per line — used to
                                                        regenerate
                                                        sh-suffix-polyglot-
                                                        baseline.txt.

Exit codes:
    0 — OK: no un-baselined `.sh`-suffixed polyglot trampoline found
    1 — VIOLATION: a NEW `.sh`-suffixed file contains the polyglot trampoline
    2 — ERROR: unexpected failure (not a git repo, bad argument, missing
        baseline file)

Output:
    stdout — human-readable status lines (and --list-baseline-candidates output)
    stderr — violation details and error messages

Negative-spec (hard-won, mirrors check-bin-sh-polyglot.py):
    - Does NOT flag `.sh` files without the trampoline (genuine bash — a valid
      and expected class; this check has nothing to say about them).
    - Does NOT flag a baselined offender — the baseline is a ratchet floor,
      not something this check tries to shrink on its own.
    - Does NOT walk the filesystem — enumerates via `git ls-files`, so
      untracked/scratch/vendored content is never in scope.
    - Baseline entries are repo-relative paths (POSIX-separated), NOT bare
      basenames — basenames are not unique across directories once the scan
      domain is repo-wide (e.g. two different `run-tests.sh` in different
      dirs), and a basename-keyed baseline would silently allow a new
      offender that happens to share a name with a baselined one.
    - Does NOT require GNU coreutils / non-stdlib packages.
"""

from __future__ import annotations

import os
import subprocess
import sys

PROG = "check-sh-suffix-polyglot.py"

# The verbatim trampoline every polyglot-class member contains within its
# first 20 lines. Kept byte-identical to check-bin-sh-polyglot.py's TRAMPOLINE.
TRAMPOLINE = (
    "''''exec \"$(command -v python3 || command -v python || command -v py)\" "
    '"$0" "$@" #\'\'\''
)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BASELINE_FILE = os.path.join(_THIS_DIR, "sh-suffix-polyglot-baseline.txt")


def _has_trampoline(path: str) -> bool:
    """True if the file contains the verbatim trampoline within its first 20 lines."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            head = "".join(next(fh, "") for _ in range(20))
    except OSError:
        return False
    return TRAMPOLINE in head


def _load_baseline() -> set:
    """Read sh-suffix-polyglot-baseline.txt: one repo-relative path per line
    (POSIX-separated), `#`-comments and blank lines ignored. Missing file is
    an ERROR (fail loud) — an absent baseline is indistinguishable from
    "every offender is new" and would flag all 136 pre-existing files.
    """
    if not os.path.isfile(BASELINE_FILE):
        sys.stderr.write(
            "{}: ERROR — baseline file not found: {}\n".format(PROG, BASELINE_FILE)
        )
        return None
    entries = set()
    with open(BASELINE_FILE, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entries.add(line)
    return entries


def _git(args, cwd=None):
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return proc.returncode, proc.stdout
    except (OSError, ValueError):
        return 127, ""


def _repo_root():
    """Resolve the git repo root from this script's own location."""
    rc, out = _git(["-C", _THIS_DIR, "rev-parse", "--show-toplevel"])
    if rc == 0:
        return out.strip()
    return None


def _in_git_repo():
    rc, _ = _git(["-C", _THIS_DIR, "rev-parse", "--git-dir"])
    return rc == 0


def _candidate_files(staged: bool):
    """Return list of (relpath, abspath) for tracked `.sh` files repo-wide.

    relpath is repo-relative, POSIX-separated (as `git ls-files`/`git diff`
    emit it) — this is the key space the baseline is keyed on.

    In --staged mode, scope to `git diff --cached --name-only` filtered to
    `.sh` paths instead of the full tracked set. Returns None on a hard error
    (not a git repo).
    """
    if not _in_git_repo():
        sys.stderr.write("{}: ERROR — not a git repository\n".format(PROG))
        return None

    root = _repo_root()
    if not root:
        sys.stderr.write("{}: ERROR — could not resolve git repo root\n".format(PROG))
        return None

    if staged:
        rc, out = _git(["-C", root, "diff", "--cached", "--name-only"])
    else:
        rc, out = _git(["-C", root, "ls-files", "*.sh"])

    if rc != 0:
        sys.stderr.write("{}: ERROR — git enumeration failed\n".format(PROG))
        return None

    result = []
    for line in out.splitlines():
        rel = line.strip()
        if not rel or not rel.endswith(".sh"):
            continue
        abspath = os.path.join(root, rel.replace("/", os.sep))
        if os.path.isfile(abspath):
            result.append((rel, abspath))
    return sorted(result)


def _print_help():
    sys.stdout.write(__doc__.strip() + "\n")


def main(argv):
    staged = False
    list_candidates = False

    for arg in argv:
        if arg == "--staged":
            staged = True
        elif arg == "--list-baseline-candidates":
            list_candidates = True
        elif arg in ("-h", "--help"):
            _print_help()
            return 0
        else:
            sys.stderr.write("{}: unknown argument: {}\n".format(PROG, arg))
            return 2

    candidates = _candidate_files(staged)
    if candidates is None:
        return 2

    if list_candidates:
        for rel, abspath in candidates:
            if _has_trampoline(abspath):
                print(rel)
        return 0

    baseline = _load_baseline()
    if baseline is None:
        return 2

    new_offenders = []
    for rel, abspath in candidates:
        if not _has_trampoline(abspath):
            continue  # genuine bash (or not-yet-in-class) — not our concern
        if rel in baseline:
            continue  # known backlog — ratchet does not re-flag it
        new_offenders.append(rel)

    if not new_offenders:
        sys.stdout.write(
            "OK: no new .sh-suffixed polyglot trampolines "
            "(scanned {} file(s), baseline has {} known entries)\n".format(
                len(candidates), len(baseline)
            )
        )
        return 0

    sys.stderr.write(
        "VIOLATION: SH-SUFFIX-POLYGLOT-RATCHET — the following file(s) are NEW\n"
        "  `.sh`-suffixed sh/python polyglot trampolines (Python body wearing a\n"
        "  bash-suffixed costume) and are not in the checked-in baseline:\n"
    )
    for rel in new_offenders:
        sys.stderr.write("  {}\n".format(rel))
    sys.stderr.write(
        "\n"
        "Remedy: drop the `.sh` suffix instead (see coordinator-auto-push,\n"
        "        handoff-gate-aging for precedent) — a polyglot trampoline needs\n"
        "        no suffix to be invoked. If this file is intentionally joining\n"
        "        the tracked backlog, add its repo-relative path to {} with a\n"
        "        one-line reason.\n".format(BASELINE_FILE)
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
