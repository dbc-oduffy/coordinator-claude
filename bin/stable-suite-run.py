"""Run a test command and refuse to report its result unless the corpus held still.

Ported from DoE-claude `coordinator/bin/stable-suite-run.py` (W3-C1,
`docs/plans/2026-09-18-doe-holds-no-scripts.md`) -- mechanical move, no behavioural change. No
path resolution at all (§ Path resolution): every git call below is run with the default cwd
(the caller's), and nothing here touches `__file__`.

Invoked as `python coordinator/bin/stable-suite-run.py -- <cmd>`; carries no interpreter shebang on
purpose. An env-style shebang line is itself the POSIX-exec assumption this repo's own posix-exec
ratchet flags -- it caught this file on its first run, which is the gate working. The literal form
is deliberately not spelled out here: the ratchet matches on text, so writing the example out would
re-trip the very gate this paragraph is about.

Purpose: on a shared worktree several live sessions commit into, a suite result is not
trustworthy on its own. Measured 2026-08-07 on this repo: ~14 peer commits landed per 10
minutes against a ~60s suite, and three consecutive full runs produced three DIFFERENT
failure sets while every failing test passed in isolation. The tests that flicker are the
corpus-scanning ones -- ratchets, template/symbol parity, and "the live repo was not
mutated" liveness checks -- because the thing they scan changed mid-run.

So a bare red is not evidence of a defect here, and a bare green is not evidence of health:
both partly measure the peer commit rate. This wrapper brackets the run with HEAD and with
the tracked-file dirty set, and reports UNSTABLE (exit 2) when either moved, distinct from
PASS (0) and FAIL (1). An UNSTABLE result is not a failure of the code -- it means the
measurement did not happen and must be retaken.

Negative-spec -- what this deliberately does NOT do:
  - It does not create a git worktree or a clone. Parallel agents share one tree here by
    doctrine; this only observes, never checks anything out.
  - It does not quiesce peers, retry forever, or serialize anyone. It reports honestly and
    lets the caller decide.
  - It does not interpret the test output. Pass/fail is the runner's verdict, untouched.

Spec backlink: docs/plans/2026-08-07-windows-clean-the-coordinator-tests-suite.md AC7, and
state/audits/2026-08-07-windows-clean-execution-record.md (the measurement-hazard section).
"""

from __future__ import annotations

import argparse
import subprocess
import sys

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_UNSTABLE = 2


def _git(*args: str) -> str | None:
    """Read-only git query. Never mutates; returns None (never '') on any failure.

    Review: coordinator:code-reviewer -- a failed git call (not on PATH, run outside a
    repo, non-zero exit) must never collapse to the same value an empty-but-successful
    result would produce. `_corpus_fingerprint` folding "git could not be asked" into
    "git said nothing" is exactly the false-confidence failure mode this whole tool
    exists to prevent.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=False,
            creationflags=_NO_WINDOW,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _corpus_fingerprint() -> tuple[str | None, str | None]:
    """(HEAD sha, tracked-file dirty set). Both must hold still across the run.

    HEAD alone is insufficient: a peer editing a tracked file without committing moves the
    corpus just as effectively. Untracked paths are excluded on purpose -- scratch output
    from the run itself would otherwise self-report as instability.

    Either element being None means "could not fingerprint," never "empty." The caller
    must treat that as UNSTABLE, not as a trivially-equal pair of successful reads.
    """
    return _git("rev-parse", "HEAD"), _git("diff", "--name-only", "HEAD")


def _failing_node_ids(command: list[str]) -> list[str]:
    """Collect failing node ids by re-running the suite with -q and parsing FAILED lines.

    Parsed rather than taken from a plugin so this works against any stock pytest.
    """
    proc = subprocess.run(
        [*command, "-p", "no:randomly"],
        capture_output=True,
        text=True,
        check=False,
        creationflags=_NO_WINDOW,
    )
    # Review: coordinator:code-reviewer Finding 3 -- pytest's own short summary section
    # (`short test summary info`) is the only place `FAILED ` lines are structurally
    # trustworthy; scanning raw combined stdout+stderr picks up a test's own captured
    # output if it happens to print a line starting with "FAILED ". Restricting the scan
    # to the summary section, and splitting the node id from its trailing " - <reason>"
    # (rightmost occurrence, since a reason phrase is free text and the node id is not)
    # rather than the first space, keeps parametrized ids containing spaces intact.
    lines = (proc.stdout + proc.stderr).splitlines()
    summary_start = None
    for idx, line in enumerate(lines):
        if "short test summary info" in line:
            summary_start = idx + 1
            break

    scan_lines = lines[summary_start:] if summary_start is not None else lines
    ids: list[str] = []
    for line in scan_lines:
        stripped = line.strip()
        if not stripped.startswith("FAILED "):
            continue
        rest = stripped[len("FAILED ") :]
        node = rest.rsplit(" - ", 1)[0].strip()
        if "::" in node:
            ids.append(node)
    return ids


def _pytest_base(command: list[str]) -> list[str]:
    """Strip the original test-path/selector args from `command`, leaving the bare runner.

    Review: coordinator:code-reviewer Finding 4 -- the prior filter matched only args
    literally starting with the forward-slash string "coordinator/tests", which silently
    passed through on a Windows-native path (`coordinator\\tests\\...`), an absolute path,
    or a `-k` selector -- leaving the original scope concatenated with the newly-appended
    solo node id, defeating isolation. This strips any arg whose separator-normalized form
    contains "coordinator/tests" as a path segment sequence, plus a `-k`/its value, and
    fails LOUDLY (rather than silently falling back to a possibly-wrong runner) when
    nothing was stripped -- an unrecognized arg shape means the caller's assumption about
    scope-argument shape does not hold here.
    """
    stripped: list[str] = []
    kept: list[str] = []
    skip_next = False
    for tok in command:
        if skip_next:
            stripped.append(tok)
            skip_next = False
            continue
        if tok == "-k":
            stripped.append(tok)
            skip_next = True
            continue
        # Separator-normalized only to compare an ARG against a path-shaped substring — this token
        # may not be a path at all (`-q`, `--no-header`), so PureWindowsPath would be the wrong
        # tool: it would happily reinterpret a non-path argument as one. A literal replace is
        # correct here precisely because the comparison is textual, not filesystem semantics.
        normalized = tok.replace("\\", "/")  # abs-path-ok: arg-shape comparison, not a path operation
        if "coordinator/tests" in normalized:
            stripped.append(tok)
            continue
        kept.append(tok)

    if not stripped:
        print(
            "stable-suite-run: WARNING — could not identify a test-path/selector arg to "
            f"strip from {command!r}; falling back to a bare `python -m pytest`, which may "
            "not match the caller's actual runner or venv.",
            file=sys.stderr,
        )
        return ["python", "-m", "pytest"]
    return kept


def _triage_isolation(command: list[str]) -> None:
    """Split a stable FAIL into genuine failures and order-dependent ones.

    Why this exists: "passes alone, fails in the suite" and its inverse have both produced
    wrong conclusions on this repo. A per-file green is routinely mistaken for proof a fix
    landed, and a suite red is routinely mistaken for a defect when it is shared-state
    leakage between tests. Re-running each failing node id ALONE separates the two
    mechanically instead of by argument.

    An order-dependent verdict is NOT an all-clear: it means the defect is in the coupling
    (shared temp markers, registries, cwd), not in the test's own subject. It is a different
    bug with a different owner, not the absence of one.
    """
    # Review: coordinator:code-reviewer Finding 2 -- `_failing_node_ids` re-runs the whole
    # suite a second time from scratch, and that second run was previously unbracketed: if
    # a peer commits between the caller's already-certified-stable run and this one, the
    # triage below is computed against a different corpus than the one just certified, with
    # nothing reporting that. Bracket it here too, the same way `main` brackets the primary
    # run, and warn (without hiding the triage output — it's still informative) if it moved.
    fp_before = _corpus_fingerprint()
    node_ids = _failing_node_ids(command)
    fp_after = _corpus_fingerprint()
    if None in (*fp_before, *fp_after) or fp_before != fp_after:
        print(
            "stable-suite-run: WARNING — the corpus moved (or could not be fingerprinted) "
            "during the triage re-run; the GENUINE/ORDER-DEPENDENT breakdown below is "
            "computed against a possibly-different corpus than the run just certified "
            "stable, and carries no stability guarantee of its own.",
            file=sys.stderr,
        )

    if not node_ids:
        print(
            "stable-suite-run: triage found no parseable FAILED node ids — "
            "is the command a pytest invocation?",
            file=sys.stderr,
        )
        return

    base = _pytest_base(command)
    genuine: list[str] = []
    order_dependent: list[str] = []
    for node in node_ids:
        solo = subprocess.run(
            [*base, node, "-q", "--no-header"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=_NO_WINDOW,
        )
        (genuine if solo.returncode != 0 else order_dependent).append(node)

    print(
        f"\nstable-suite-run: isolation triage of {len(node_ids)} failure(s) —\n"
        f"  GENUINE ({len(genuine)}): fail alone too. These are real defects.\n"
        f"  ORDER-DEPENDENT ({len(order_dependent)}): pass alone. The defect is in the coupling "
        f"between tests (shared markers, registries, cwd), not in the test's own subject — a "
        f"different bug, not a non-bug.",
        file=sys.stderr,
    )
    for node in genuine:
        print(f"    GENUINE          {node}", file=sys.stderr)
    for node in order_dependent:
        print(f"    ORDER-DEPENDENT  {node}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a command and flag whether the repo corpus moved underneath it.",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=1,
        help="Retake the measurement up to N times, stopping at the first stable one.",
    )
    parser.add_argument(
        "--triage-isolation",
        action="store_true",
        help=(
            "On a stable FAIL, re-run each failing pytest node id ALONE and split the failures "
            "into genuine (fails both ways) and order-dependent (passes alone). Requires the "
            "command to be a pytest invocation."
        ),
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="The command to run, after `--`. Its own exit code is passed through when stable.",
    )
    args = parser.parse_args(argv)

    command = [c for c in args.command if c != "--"]
    if not command:
        parser.error("no command given; pass it after `--`")

    for attempt in range(1, max(1, args.attempts) + 1):
        head_before, dirty_before = _corpus_fingerprint()
        # Review: coordinator:code-reviewer Finding 6 (nit) -- consistent with `_git` and
        # the triage sub-runs, so a wrapped console-mode test runner doesn't pop a window.
        completed = subprocess.run(command, check=False, creationflags=_NO_WINDOW)
        head_after, dirty_after = _corpus_fingerprint()

        # Review: coordinator:code-reviewer Finding 1 -- a None on either side means git
        # could not be queried at all, which is NOT the same as "held still." Treat it as
        # UNSTABLE (a distinct reason, not folded into the moved-HEAD/moved-files cases
        # below) rather than letting None == None report a false PASS/FAIL.
        if None in (head_before, dirty_before, head_after, dirty_after):
            print(
                "\nstable-suite-run: UNSTABLE — git could not be queried (not on PATH, not "
                f"a repo, or a failing git call), attempt {attempt} of {args.attempts}. The "
                f"runner reported exit {completed.returncode}, but this tool has no evidence "
                "the corpus held still, so that number means nothing.",
                file=sys.stderr,
            )
            continue

        stable = head_before == head_after and dirty_before == dirty_after
        if stable:
            verdict = "PASS" if completed.returncode == 0 else "FAIL"
            print(
                f"\nstable-suite-run: {verdict} — corpus held still at {head_before[:9]} "
                f"for the whole run (attempt {attempt}).",
                file=sys.stderr,
            )
            if completed.returncode != 0 and args.triage_isolation:
                _triage_isolation(command)
            return EXIT_PASS if completed.returncode == 0 else EXIT_FAIL

        moved = "HEAD" if head_before != head_after else "tracked-file edits"
        print(
            f"\nstable-suite-run: UNSTABLE — {moved} changed during the run "
            f"({head_before[:9]} -> {head_after[:9]}), attempt {attempt} of {args.attempts}. "
            f"The runner reported exit {completed.returncode}, but the corpus it measured is "
            f"not the corpus on disk, so that number means nothing.",
            file=sys.stderr,
        )

    print(
        "stable-suite-run: no stable measurement obtained. Retake it when the tree is quieter, "
        "or reconcile with the sessions committing into it — do NOT read the last exit code as a "
        "verdict.",
        file=sys.stderr,
    )
    return EXIT_UNSTABLE


if __name__ == "__main__":
    raise SystemExit(main())
