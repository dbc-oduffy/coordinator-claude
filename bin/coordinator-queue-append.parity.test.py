#!/bin/sh
# ── sh/python polyglot trampoline ─────────────────────────────────────────────
# Matches the CLI's trampoline so `bash coordinator-queue-append.parity.test.py` works.
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
from __future__ import annotations
"""
coordinator-queue-append.parity.test.py — field-parity CHARACTERIZATION tests.

Spec backlink: docs/plans/2026-06-25-example-initiative-tc-2-queues-lessons-consolidation.md § Chunk P

PURPOSE: pins the CURRENT (HEAD) accept/reject behavior of coordinator-queue-append
and coordinator-lesson-promote as a golden corpus. This is the regression net that
later loader-delegation chunks (which replace the hardcoded SCHEMAS dict with a
runtime load from coordinator/schemas/*.yaml) are verified against.

These tests exercise the CLIs through their EXTERNAL SUBPROCESS INTERFACE only —
no import of implementation code. Each case asserts exactly one verdict: accept
(exit 0) or reject (exit non-zero).

Parity cases by shape:
  coordinator-queue-append --schema debt-backlog:  4 cases
    (a) valid minimal                          → accept
    (b) valid full (all fields)                → accept
    (c) missing required field (--risk)        → reject
    (d) invalid enum (--status bogus)          → reject
    (d2) invalid enum (--severity P9)          → reject

  coordinator-queue-append --schema bug-backlog:   5 cases
    (a) valid minimal                          → accept
    (b) valid full (all fields)                → accept
    (c) missing required field (--severity)    → reject
    (d) invalid enum (--status bogus)          → reject
    (e) --status wontfix                       → accept (wontfix IS valid for bug-backlog)

  coordinator-queue-append --schema improvement-queue: 5 cases
    (a) valid minimal                          → accept
    (b) missing required field (--surface)     → reject
    (c) invalid --change-kind bogus            → reject
    (d) --queue-scope central                  → accept
    (e) --queue-scope project                  → accept
    NOTE: invalid --queue-scope values are rejected by the application validation
    in main() (before schema validation, after argparse) — not by argparse choices=.
    Tests for invalid --queue-scope are out of scope here; they are already covered
    by the existing coordinator-queue-append.test.py (Test 10 / Test 2 paths).

  coordinator-lesson-promote:                       4 cases
    (a) valid invocation                       → accept
    (b) missing --title                        → reject
    (c) missing --change-kind                  → reject
    (d) invalid --change-kind bogus            → reject

Total: 19 parity cases (debt=5, bug=5, improvement=5, lesson=4;
 d and d2 for debt count as 2 distinct subcases of case (d)).

INVARIANT: all cases must be GREEN against current HEAD before any loader-delegation
chunk is applied. Do NOT add fail-loud/missing-schemas battery here — that behavior
does not exist on current HEAD (the CLIs do not read schemas/*.yaml yet).

Run with: python3 bin/coordinator-queue-append.parity.test.py
"""

import os
import subprocess
import sys
import tempfile

# Portable Windows CREATE_NO_WINDOW flag — resolves to the flag on Windows and
# 0 (no-op) on macOS/Linux. Used for all subprocess invocations of python to
# suppress console popup under the headless Claude Code Bash-tool parent.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---------------------------------------------------------------------------
# Test infrastructure (mirrors coordinator-queue-append.test.py)
# ---------------------------------------------------------------------------

TESTS_PASSED = 0
TESTS_FAILED = 0
FAILURES: list[str] = []


def _queue_append_script_path() -> str:
    """Absolute path to coordinator-queue-append."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "coordinator-queue-append")


def _lesson_promote_script_path() -> str:
    """Absolute path to coordinator-lesson-promote."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "coordinator-lesson-promote")


def _python() -> str:
    """Return the Python interpreter running this test (Windows-compatible zero-probe)."""
    return sys.executable


def _run_queue_append(
    args: list[str],
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    """Invoke coordinator-queue-append as a subprocess."""
    effective_env = {**os.environ}
    if env:
        effective_env.update(env)
    return subprocess.run(
        [_python(), _queue_append_script_path()] + args,
        env=effective_env,
        capture_output=True,
        text=True,
        cwd=cwd,
        creationflags=_NO_WINDOW,
    )


def _run_lesson_promote(
    args: list[str],
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Invoke coordinator-lesson-promote as a subprocess."""
    effective_env = {**os.environ}
    if env:
        effective_env.update(env)
    return subprocess.run(
        [_python(), _lesson_promote_script_path()] + args,
        env=effective_env,
        capture_output=True,
        text=True,
        creationflags=_NO_WINDOW,
    )


def pass_test(name: str) -> None:
    global TESTS_PASSED
    TESTS_PASSED += 1
    print(f"  PASS: {name}")


def fail_test(name: str, reason: str) -> None:
    global TESTS_FAILED
    TESTS_FAILED += 1
    msg = f"  FAIL: {name} — {reason}"
    FAILURES.append(msg)
    print(msg)


def _assert_accept(
    name: str,
    result: subprocess.CompletedProcess,
) -> bool:
    """Assert that the CLI accepted (exit 0). Returns True if passed."""
    if result.returncode != 0:
        fail_test(
            name,
            f"expected exit 0 (accept) but got {result.returncode}. "
            f"stderr: {result.stderr!r}",
        )
        return False
    return True


def _assert_reject(
    name: str,
    result: subprocess.CompletedProcess,
) -> bool:
    """Assert that the CLI rejected (exit non-zero). Returns True if passed."""
    if result.returncode == 0:
        fail_test(name, "expected non-zero exit (reject) but got 0")
        return False
    return True


# ---------------------------------------------------------------------------
# Shared arg builders
# ---------------------------------------------------------------------------

def _debt_backlog_minimal_args() -> list[str]:
    """Minimal valid debt-backlog args (all required fields per schema)."""
    return [
        "--schema", "debt-backlog",
        "--title", "Parity test debt entry",
        "--body", "Body text for parity debt test.",
        "--status", "open",
        "--source", "daily-review/parity/2026-06-26",
        "--risk", "Parity risk description.",
        "--proposed-action", "Take the parity action.",
        "--from-repo", "test-repo-em",
    ]


def _bug_backlog_minimal_args() -> list[str]:
    """Minimal valid bug-backlog args (all required fields per schema)."""
    return [
        "--schema", "bug-backlog",
        "--title", "Parity test bug entry",
        "--body", "Body text for parity bug test.",
        "--status", "open",
        "--surface", "coordinator/parity-test",
        "--severity", "P2",
        "--from-repo", "test-repo-em",
    ]


def _improvement_queue_minimal_args() -> list[str]:
    """Minimal valid improvement-queue args (all required fields per schema)."""
    return [
        "--schema", "improvement-queue",
        "--title", "Parity test improvement entry",
        "--body", "Body text for parity improvement test.",
        "--status", "open",
        "--surface", "plugins/coordinator/skills/workstream-complete/SKILL.md",
        "--proposed-action", "plugins/coordinator/skills/",
        "--change-kind", "skill-edit",
        "--from-repo", "test-repo-em",
    ]


# ---------------------------------------------------------------------------
# debt-backlog parity cases (5 subcases under 4 labeled cases: a, b, c, d, d2)
# ---------------------------------------------------------------------------

def test_debt_backlog_valid_minimal() -> None:
    """Case (a): valid minimal debt-backlog → accept."""
    name = "debt-backlog (a) valid minimal → accept"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            _debt_backlog_minimal_args(),
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_accept(name, result):
        pass_test(name)


def test_debt_backlog_valid_full() -> None:
    """Case (b): valid full debt-backlog (all optional fields present) → accept."""
    name = "debt-backlog (b) valid full → accept"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            [
                "--schema", "debt-backlog",
                "--title", "Parity test debt entry full",
                "--body", "Full body text for parity debt test.",
                "--status", "open",
                "--source", "daily-review/parity-full/2026-06-26",
                "--risk", "Full risk description.",
                "--proposed-action", "Full proposed action.",
                "--from-repo", "test-repo-em",
                # optional debt fields
                "--severity", "P2",
                "--evidence", "abc1234def5678",
                "--surface", "bin/coordinator-queue-append",
                "--tags", "parity,full",
                "--closed-at", "2026-06-26",
                "--closed-by", "abc1234",
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_accept(name, result):
        pass_test(name)


def test_debt_backlog_missing_required_field() -> None:
    """Case (c): missing required field (--risk omitted) → reject."""
    name = "debt-backlog (c) missing required field (--risk) → reject"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            [
                "--schema", "debt-backlog",
                "--title", "T",
                "--body", "B",
                "--status", "open",
                "--source", "daily-review/parity",
                "--proposed-action", "Some action.",
                "--from-repo", "test-repo-em",
                # --risk is intentionally omitted
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_reject(name, result):
        combined = result.stdout + result.stderr
        if "risk" not in combined.lower():
            fail_test(name, f"error output does not mention 'risk'. stderr: {result.stderr!r}")
        else:
            pass_test(name)


def test_debt_backlog_invalid_status_enum() -> None:
    """Case (d): invalid --status enum value → reject."""
    name = "debt-backlog (d) invalid --status bogus → reject"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            [
                "--schema", "debt-backlog",
                "--title", "T",
                "--body", "B",
                "--status", "bogus",  # not in {open, closed, deferred}
                "--source", "daily-review/parity",
                "--risk", "Some risk.",
                "--proposed-action", "Some action.",
                "--from-repo", "test-repo-em",
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_reject(name, result):
        combined = result.stdout + result.stderr
        if "open" not in combined:
            fail_test(name, f"error output does not name valid status values. stderr: {result.stderr!r}")
        else:
            pass_test(name)


def test_debt_backlog_invalid_severity_enum() -> None:
    """Case (d2): invalid --severity enum value (P9 not in P0-P3) → reject."""
    name = "debt-backlog (d2) invalid --severity P9 → reject"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            [
                "--schema", "debt-backlog",
                "--title", "T",
                "--body", "B",
                "--status", "open",
                "--source", "daily-review/parity",
                "--risk", "Some risk.",
                "--proposed-action", "Some action.",
                "--from-repo", "test-repo-em",
                "--severity", "P9",  # not in {P0, P1, P2, P3}
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_reject(name, result):
        combined = result.stdout + result.stderr
        if "P0" not in combined and "P1" not in combined:
            fail_test(name, f"error output does not name valid severity values. stderr: {result.stderr!r}")
        else:
            pass_test(name)


# ---------------------------------------------------------------------------
# bug-backlog parity cases (5 cases: a, b, c, d, e)
# ---------------------------------------------------------------------------

def test_bug_backlog_valid_minimal() -> None:
    """Case (a): valid minimal bug-backlog → accept."""
    name = "bug-backlog (a) valid minimal → accept"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            _bug_backlog_minimal_args(),
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_accept(name, result):
        pass_test(name)


def test_bug_backlog_valid_full() -> None:
    """Case (b): valid full bug-backlog (all optional fields present) → accept."""
    name = "bug-backlog (b) valid full → accept"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            [
                "--schema", "bug-backlog",
                "--title", "Parity test bug entry full",
                "--body", "Full body text for parity bug test.",
                "--status", "open",
                "--surface", "coordinator/parity-test-full",
                "--severity", "P1",
                "--from-repo", "test-repo-em",
                # optional bug fields
                "--repro-steps", "1. Do X. 2. Observe Y.",
                "--environment", "macOS + bash 5.2",
                "--why-blocked", "Needs upstream fix.",
                "--tags", "parity,bug,full",
                "--evidence", "def5678abc1234",
                "--closed-at", "2026-06-26",
                "--closed-by", "def5678",
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_accept(name, result):
        pass_test(name)


def test_bug_backlog_missing_required_field() -> None:
    """Case (c): missing required field (--severity omitted) → reject."""
    name = "bug-backlog (c) missing required field (--severity) → reject"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            [
                "--schema", "bug-backlog",
                "--title", "T",
                "--body", "B",
                "--status", "open",
                "--surface", "coordinator/parity",
                "--from-repo", "test-repo-em",
                # --severity is intentionally omitted
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_reject(name, result):
        combined = result.stdout + result.stderr
        if "severity" not in combined.lower():
            fail_test(name, f"error output does not mention 'severity'. stderr: {result.stderr!r}")
        else:
            pass_test(name)


def test_bug_backlog_invalid_status_enum() -> None:
    """Case (d): invalid --status enum value → reject."""
    name = "bug-backlog (d) invalid --status bogus → reject"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            [
                "--schema", "bug-backlog",
                "--title", "T",
                "--body", "B",
                "--status", "bogus",  # not in {open, closed, deferred, wontfix}
                "--surface", "coordinator/parity",
                "--severity", "P2",
                "--from-repo", "test-repo-em",
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_reject(name, result):
        combined = result.stdout + result.stderr
        if "open" not in combined:
            fail_test(name, f"error output does not name valid status values. stderr: {result.stderr!r}")
        else:
            pass_test(name)


def test_bug_backlog_wontfix_status_accepted() -> None:
    """Case (e): --status wontfix is ACCEPTED for bug-backlog.

    bug-backlog status enum extends the base enum with 'wontfix':
    {open, closed, deferred, wontfix}. This is the characterization of the
    asymmetry — wontfix is valid for bug-backlog but NOT for debt-backlog.
    """
    name = "bug-backlog (e) --status wontfix → accept (wontfix IS valid for bug-backlog)"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            [
                "--schema", "bug-backlog",
                "--title", "Known bug we will not fix",
                "--body", "This issue is a known limitation and will not be addressed.",
                "--status", "wontfix",  # explicitly in the bug-backlog status enum
                "--surface", "coordinator/parity",
                "--severity", "P3",
                "--from-repo", "test-repo-em",
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_accept(name, result):
        pass_test(name)


# ---------------------------------------------------------------------------
# improvement-queue parity cases (5 cases: a, b, c, d, e)
# ---------------------------------------------------------------------------

def test_improvement_queue_valid_minimal() -> None:
    """Case (a): valid minimal improvement-queue → accept."""
    name = "improvement-queue (a) valid minimal → accept"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            _improvement_queue_minimal_args(),
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_accept(name, result):
        pass_test(name)


def test_improvement_queue_missing_required_field() -> None:
    """Case (b): missing required field (--surface omitted) → reject."""
    name = "improvement-queue (b) missing required field (--surface) → reject"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            [
                "--schema", "improvement-queue",
                "--title", "T",
                "--body", "B",
                "--status", "open",
                "--proposed-action", "plugins/coordinator/",
                "--change-kind", "skill-edit",
                "--from-repo", "test-repo-em",
                # --surface is intentionally omitted
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_reject(name, result):
        combined = result.stdout + result.stderr
        if "surface" not in combined.lower():
            fail_test(name, f"error output does not mention 'surface'. stderr: {result.stderr!r}")
        else:
            pass_test(name)


def test_improvement_queue_invalid_change_kind() -> None:
    """Case (c): invalid --change-kind value → reject.

    Valid improvement-queue change_kind values (hardcoded in SCHEMAS dict, current HEAD):
    script-edit, skill-edit, wiki-append, wiki-new, hook-edit, agent-prompt-edit.

    Note: 'doctrine-edit' is NOT in the improvement-queue enum (it IS in
    coordinator-lesson-promote's CHANGE_KIND_VALUES, but those are separate enums).
    """
    name = "improvement-queue (c) invalid --change-kind bogus → reject"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            [
                "--schema", "improvement-queue",
                "--title", "T",
                "--body", "B",
                "--status", "open",
                "--surface", "plugins/coordinator/",
                "--proposed-action", "plugins/coordinator/",
                "--change-kind", "bogus",  # not in the improvement-queue enum
                "--from-repo", "test-repo-em",
            ],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_reject(name, result):
        combined = result.stdout + result.stderr
        if "skill-edit" not in combined and "change-kind" not in combined.lower():
            fail_test(
                name,
                f"error output does not name valid change-kind values. stderr: {result.stderr!r}",
            )
        else:
            pass_test(name)


def test_improvement_queue_queue_scope_central_accepted() -> None:
    """Case (d): --queue-scope central → accept (valid scope value for improvement-queue).

    QUEUE_APPEND_OUTPUT_ROOT takes precedence over the central-scope CLAUDE_HOME redirect
    (see _output_path precedence: env override → central → cwd), so using the env var
    here controls output for test isolation without needing a real or fake ~/.claude.
    This tests only the accept/reject verdict, not the write destination.

    NOTE on invalid --queue-scope: an invalid value (e.g. --queue-scope bogus) is
    rejected by the application-level validation in main() — NOT by argparse choices=
    (the --queue-scope flag has no choices= constraint in argparse). The check runs
    before schema validation and exits 1, naming valid values {central, project}.
    Tests for invalid --queue-scope are in coordinator-queue-append.test.py (Test 10);
    they are out of scope for this parity file.
    """
    name = "improvement-queue (d) --queue-scope central → accept"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            _improvement_queue_minimal_args() + ["--queue-scope", "central"],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_accept(name, result):
        pass_test(name)


def test_improvement_queue_queue_scope_project_accepted() -> None:
    """Case (e): --queue-scope project → accept (valid scope value, default behavior)."""
    name = "improvement-queue (e) --queue-scope project → accept"
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _run_queue_append(
            _improvement_queue_minimal_args() + ["--queue-scope", "project"],
            env={"QUEUE_APPEND_OUTPUT_ROOT": tmpdir},
            cwd=tmpdir,
        )
    if _assert_accept(name, result):
        pass_test(name)


# ---------------------------------------------------------------------------
# coordinator-lesson-promote parity cases (4 cases: a, b, c, d)
# ---------------------------------------------------------------------------

def test_lesson_promote_valid() -> None:
    """Case (a): valid coordinator-lesson-promote invocation → accept.

    Uses LESSON_PROMOTE_OUTBOX_ROOT env var (absolute outbox path) to redirect
    output to a temp dir, matching the pattern from coordinator-lesson-promote.test.py.
    """
    name = "coordinator-lesson-promote (a) valid invocation → accept"
    with tempfile.TemporaryDirectory() as tmpdir:
        outbox = os.path.join(tmpdir, "state", "lessons-outbox")
        result = _run_lesson_promote(
            [
                "--title", "Parity test lesson",
                "--body", "This lesson verifies the CLI accepts valid inputs on current HEAD.",
                "--change-kind", "doctrine-edit",
                "--target-wiki", "docs/wiki/executor-discipline.md",
            ],
            env={"LESSON_PROMOTE_OUTBOX_ROOT": outbox},
        )
    if _assert_accept(name, result):
        pass_test(name)


def test_lesson_promote_missing_title() -> None:
    """Case (b): missing --title → reject (argparse required field)."""
    name = "coordinator-lesson-promote (b) missing --title → reject"
    with tempfile.TemporaryDirectory() as tmpdir:
        outbox = os.path.join(tmpdir, "state", "lessons-outbox")
        result = _run_lesson_promote(
            [
                "--body", "Body without a title.",
                "--change-kind", "doctrine-edit",
                "--target-wiki", "docs/wiki/some.md",
            ],
            env={"LESSON_PROMOTE_OUTBOX_ROOT": outbox},
        )
    if _assert_reject(name, result):
        combined = result.stdout + result.stderr
        if "title" not in combined.lower():
            fail_test(name, f"error output does not mention 'title'. stderr: {result.stderr!r}")
        else:
            pass_test(name)


def test_lesson_promote_missing_change_kind() -> None:
    """Case (c): missing --change-kind → reject (argparse required field)."""
    name = "coordinator-lesson-promote (c) missing --change-kind → reject"
    with tempfile.TemporaryDirectory() as tmpdir:
        outbox = os.path.join(tmpdir, "state", "lessons-outbox")
        result = _run_lesson_promote(
            [
                "--title", "Parity lesson without change kind",
                "--body", "Body without a change-kind.",
                "--target-wiki", "docs/wiki/some.md",
            ],
            env={"LESSON_PROMOTE_OUTBOX_ROOT": outbox},
        )
    if _assert_reject(name, result):
        combined = result.stdout + result.stderr
        if "change-kind" not in combined.lower() and "change_kind" not in combined.lower():
            fail_test(
                name,
                f"error output does not mention 'change-kind'. stderr: {result.stderr!r}",
            )
        else:
            pass_test(name)


def test_lesson_promote_invalid_change_kind() -> None:
    """Case (d): invalid --change-kind value → reject.

    coordinator-lesson-promote uses argparse choices= for --change-kind (unlike
    coordinator-queue-append which does post-parse validation in main()). argparse
    exits 2 on a choices violation and names the valid values in the error message.

    Valid change_kind values for coordinator-lesson-promote (current HEAD):
    doctrine-edit, agent-prompt-edit, hook-edit, script-edit,
    snippet-sync-update, wiki-new, wiki-append, skill-edit.

    NOTE: this enum differs from the improvement-queue change_kind enum in
    coordinator-queue-append (which lacks doctrine-edit and snippet-sync-update).
    Both are hardcoded in their respective CLIs; loader-delegation will replace
    them with a runtime load from coordinator/schemas/*.yaml.
    """
    name = "coordinator-lesson-promote (d) invalid --change-kind bogus → reject"
    with tempfile.TemporaryDirectory() as tmpdir:
        outbox = os.path.join(tmpdir, "state", "lessons-outbox")
        result = _run_lesson_promote(
            [
                "--title", "Parity lesson with bogus change kind",
                "--body", "Body with bogus change kind.",
                "--change-kind", "bogus",  # not in CHANGE_KIND_VALUES
                "--target-wiki", "docs/wiki/some.md",
            ],
            env={"LESSON_PROMOTE_OUTBOX_ROOT": outbox},
        )
    if _assert_reject(name, result):
        combined = result.stdout + result.stderr
        if "doctrine-edit" not in combined and "change-kind" not in combined.lower():
            fail_test(
                name,
                f"error output does not name valid change-kind values. stderr: {result.stderr!r}",
            )
        else:
            pass_test(name)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    print("coordinator-queue-append.parity.test.py")
    print("=" * 60)
    print("Field-parity CHARACTERIZATION tests — golden corpus for HEAD behavior.")
    print("All cases must be GREEN before any loader-delegation chunk is applied.")
    print()

    print("--- debt-backlog (5 cases: a, b, c, d, d2) ---")
    test_debt_backlog_valid_minimal()
    test_debt_backlog_valid_full()
    test_debt_backlog_missing_required_field()
    test_debt_backlog_invalid_status_enum()
    test_debt_backlog_invalid_severity_enum()

    print()
    print("--- bug-backlog (5 cases: a, b, c, d, e) ---")
    test_bug_backlog_valid_minimal()
    test_bug_backlog_valid_full()
    test_bug_backlog_missing_required_field()
    test_bug_backlog_invalid_status_enum()
    test_bug_backlog_wontfix_status_accepted()

    print()
    print("--- improvement-queue (5 cases: a, b, c, d, e) ---")
    test_improvement_queue_valid_minimal()
    test_improvement_queue_missing_required_field()
    test_improvement_queue_invalid_change_kind()
    test_improvement_queue_queue_scope_central_accepted()
    test_improvement_queue_queue_scope_project_accepted()

    print()
    print("--- coordinator-lesson-promote (4 cases: a, b, c, d) ---")
    test_lesson_promote_valid()
    test_lesson_promote_missing_title()
    test_lesson_promote_missing_change_kind()
    test_lesson_promote_invalid_change_kind()

    print()
    total = TESTS_PASSED + TESTS_FAILED
    print(f"Results: {TESTS_PASSED} passed, {TESTS_FAILED} failed (total: {total})")
    if FAILURES:
        print()
        print("Failures:")
        for msg in FAILURES:
            print(msg)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
