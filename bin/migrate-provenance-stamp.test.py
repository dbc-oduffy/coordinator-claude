#!/bin/sh
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
from __future__ import annotations
"""
migrate-provenance-stamp.test.py — unit tests for migrate-provenance-stamp.py

Tests:
  test_help_exits_zero
  test_idempotent_double_stamp
  test_lossless_stamp_adds_only_system_block
  test_existing_system_block_untouched
  test_dry_run_does_not_modify_file
  test_directory_target_processes_yaml_files

Spec backlink: [ccos-3 plan] § C3a — AC5
"""

import os
import sys
import subprocess
import tempfile

# ── Path setup ─────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(SCRIPT_DIR, "migrate-provenance-stamp.py")
PYTHON = sys.executable


def run_script(*args, **kwargs) -> subprocess.CompletedProcess:
    """Invoke migrate-provenance-stamp.py with the given args."""
    return subprocess.run(
        [PYTHON, SCRIPT, *args],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        **kwargs,
    )


# ── Fixtures ───────────────────────────────────────────────────────────────────

# A fixture record with several top-level keys but NO system: block.
RECORD_WITHOUT_SYSTEM = """\
created: 2026-06-01
title: Fix coordinator timeout
body: >
  Watchdog fires too early under load; timeout needs to be
  configurable per platform.
status: open
tags:
  - coordinator
  - timeout
  - portability
"""

# A fixture record that already has a system: block.
RECORD_WITH_SYSTEM = """\
created: 2026-05-15
title: Stale identity test assert removed
body: >
  PM depersonalization sweep removed the stale assert.
status: closed
system:
  provenance_completeness: full
  created_by_session: abc1234
"""

# Review: code-reviewer Slice-B — (F6) fixture for the no-trailing-newline branch in
# _stamp_record (migrate-provenance-stamp.py:79). When content does not end with \n,
# _stamp_record must still begin the appended block on its own line.
RECORD_WITHOUT_TRAILING_NEWLINE = RECORD_WITHOUT_SYSTEM.rstrip("\n")

# The provenance block that the script should append.
EXPECTED_BLOCK = "system:\n  provenance_completeness: unknown\n"


# ── Test helpers ───────────────────────────────────────────────────────────────


def assert_equal(actual, expected, label: str = "") -> None:
    """Fail-loud equality assertion."""
    if actual != expected:
        tag = f" [{label}]" if label else ""
        raise AssertionError(
            f"FAIL{tag}: expected {expected!r}, got {actual!r}"
        )


def assert_true(condition: bool, label: str = "") -> None:
    if not condition:
        tag = f" [{label}]" if label else ""
        raise AssertionError(f"FAIL{tag}: condition was False")


def assert_in(needle, haystack, label: str = "") -> None:
    if needle not in haystack:
        tag = f" [{label}]" if label else ""
        raise AssertionError(f"FAIL{tag}: {needle!r} not found in {haystack!r}")


def assert_not_in(needle, haystack, label: str = "") -> None:
    if needle in haystack:
        tag = f" [{label}]" if label else ""
        raise AssertionError(f"FAIL{tag}: {needle!r} unexpectedly found in {haystack!r}")


def write_fixture(path: str, content: str) -> None:
    """Write a fixture file to the given path."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def read_file(path: str) -> str:
    """Read and return file content."""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_help_exits_zero() -> None:
    """--help should exit 0 and print usage info."""
    result = run_script("--help")
    assert_equal(result.returncode, 0, "returncode")
    assert_in("migrate-provenance-stamp", result.stdout, "prog name in help")
    assert_in("--apply", result.stdout, "mentions --apply")
    assert_in("system:", result.stdout, "describes system: block")
    print("PASS: test_help_exits_zero")


def test_idempotent_double_stamp() -> None:
    """
    AC5(a) — IDEMPOTENT: running the stamp twice on the same record yields
    identical output the second time (the second run is a no-op / no diff).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        record_path = os.path.join(tmpdir, "record.yaml")
        write_fixture(record_path, RECORD_WITHOUT_SYSTEM)

        # First --apply run: stamps the record.
        result1 = run_script("--apply", record_path)
        assert_equal(result1.returncode, 0, "first run returncode")
        content_after_first = read_file(record_path)

        # Second --apply run: must be a no-op.
        result2 = run_script("--apply", record_path)
        assert_equal(result2.returncode, 0, "second run returncode")
        content_after_second = read_file(record_path)

        # File content must be byte-identical after the second run.
        assert_equal(
            content_after_second,
            content_after_first,
            "second run produces no diff (idempotent)",
        )

        # Second run output should indicate the record was skipped.
        assert_in("skipped", result2.stdout, "second run reports skipped")

    print("PASS: test_idempotent_double_stamp")


def test_lossless_stamp_adds_only_system_block() -> None:
    """
    AC5(b) — LOSSLESS: after stamping a fixture record with several keys,
    all original keys+values are present unchanged, and ONLY
    `system: {provenance_completeness: unknown}` was added.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        record_path = os.path.join(tmpdir, "record.yaml")
        write_fixture(record_path, RECORD_WITHOUT_SYSTEM)

        result = run_script("--apply", record_path)
        assert_equal(result.returncode, 0, "returncode")

        stamped = read_file(record_path)

        # All original top-level keys must be present.
        assert_in("created: 2026-06-01", stamped, "created key preserved")
        assert_in("title: Fix coordinator timeout", stamped, "title key preserved")
        assert_in("status: open", stamped, "status key preserved")
        assert_in("tags:", stamped, "tags key preserved")
        assert_in("  - coordinator", stamped, "tags coordinator value preserved")
        assert_in("  - timeout", stamped, "tags timeout value preserved")
        assert_in("  - portability", stamped, "tags portability value preserved")

        # The provenance block must be present.
        assert_in(EXPECTED_BLOCK, stamped, "system block appended")

        # The stamped file must start with the original content (lossless prefix).
        # Review: code-reviewer Slice-B — (F8) assert WITH trailing newline (not rstripped)
        # so an eaten-newline regression is caught. If _stamp_record strips the trailing
        # newline from the original before appending the block, this assertion fires.
        assert_true(
            stamped.startswith(RECORD_WITHOUT_SYSTEM),
            "original content (WITH trailing newline) is a prefix of stamped content",
        )

        # Only one top-level system: key must be present (no duplication).
        system_line_count = sum(
            1 for line in stamped.splitlines() if line.startswith("system:")
        )
        assert_equal(system_line_count, 1, "exactly one top-level system: key")

    print("PASS: test_lossless_stamp_adds_only_system_block")


def test_existing_system_block_untouched() -> None:
    """
    AC5(c) — A record that already has a `system:` block is left untouched:
    not double-stamped, not overwritten.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        record_path = os.path.join(tmpdir, "record_with_system.yaml")
        write_fixture(record_path, RECORD_WITH_SYSTEM)

        result = run_script("--apply", record_path)
        assert_equal(result.returncode, 0, "returncode")

        content_after = read_file(record_path)

        # File must be byte-identical to the original.
        assert_equal(
            content_after,
            RECORD_WITH_SYSTEM,
            "record with existing system: block is byte-identical after run",
        )

        # The script must report it as skipped.
        assert_in("skipped", result.stdout, "skipped in output")

        # Must NOT have overwritten the richer provenance with the generic unknown marker.
        assert_not_in(
            "provenance_completeness: unknown",
            content_after,
            "existing provenance_completeness: full not overwritten with unknown",
        )

    print("PASS: test_existing_system_block_untouched")


def test_dry_run_does_not_modify_file() -> None:
    """
    Without --apply, the script must report what would change but NOT write
    to disk. The file must be byte-identical to the original after the run.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        record_path = os.path.join(tmpdir, "record.yaml")
        write_fixture(record_path, RECORD_WITHOUT_SYSTEM)

        result = run_script(record_path)  # no --apply
        assert_equal(result.returncode, 0, "dry-run returncode")

        # File must be unchanged.
        content_after = read_file(record_path)
        assert_equal(
            content_after,
            RECORD_WITHOUT_SYSTEM,
            "dry-run did not modify the file",
        )

        # Output must mention DRY-RUN and 'would stamp'.
        assert_in("DRY-RUN", result.stdout, "DRY-RUN in output")
        assert_in("would stamp", result.stdout, "would stamp in output")

    print("PASS: test_dry_run_does_not_modify_file")


def test_no_trailing_newline_branch() -> None:
    """
    Review: code-reviewer Slice-B — (F6) Exercises the no-trailing-newline branch at
    migrate-provenance-stamp.py:79 (_stamp_record checks `not content.endswith("\\n")`
    and inserts a newline before appending the system block).

    Input: RECORD_WITHOUT_TRAILING_NEWLINE — same content as RECORD_WITHOUT_SYSTEM but
    with the trailing newline stripped.

    Assert: the stamped output starts on a new line after the original content —
    specifically, `stamped` starts with RECORD_WITHOUT_TRAILING_NEWLINE + "\\n" and
    then continues with EXPECTED_BLOCK. Equivalently, the block must appear on its
    own line, not run-on from the last line of the original.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        record_path = os.path.join(tmpdir, "no_trailing_newline.yaml")
        write_fixture(record_path, RECORD_WITHOUT_TRAILING_NEWLINE)

        result = run_script("--apply", record_path)
        assert_equal(result.returncode, 0, "returncode")

        stamped = read_file(record_path)

        # The stamped content must begin on its own line — the script must insert a
        # newline between the original content and the appended block.
        expected_prefix = RECORD_WITHOUT_TRAILING_NEWLINE + "\n"
        assert_true(
            stamped.startswith(expected_prefix),
            "stamped content starts with original + newline (block on its own line)",
        )

        # The provenance block must be present.
        assert_in(EXPECTED_BLOCK, stamped, "system block appended")

        # There must be exactly one top-level system: key.
        system_line_count = sum(
            1 for line in stamped.splitlines() if line.startswith("system:")
        )
        assert_equal(system_line_count, 1, "exactly one top-level system: key")

    print("PASS: test_no_trailing_newline_branch")


def test_missing_explicit_target_exits_nonzero() -> None:
    """
    Review: code-reviewer Slice-B — (F3) A missing explicit target (non-existent path)
    must cause a non-zero exit (detect-then-fail-loud). A typo'd path is a caller error
    and silently skipping it is a footgun.
    """
    result = run_script("--apply", "/nonexistent/path/that/does/not/exist.yaml")
    assert_true(result.returncode != 0, "missing explicit target exits non-zero")
    # The warning text should appear in stderr.
    assert_in("WARNING", result.stderr, "warning in stderr")
    assert_in("not found", result.stderr, "not found message in stderr")

    print("PASS: test_missing_explicit_target_exits_nonzero")


def test_directory_target_processes_yaml_files() -> None:
    """
    When given a directory, the script processes all *.yaml files within it.
    A record without system: gets stamped; one with system: is skipped.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        path_no_system = os.path.join(tmpdir, "alpha.yaml")
        path_has_system = os.path.join(tmpdir, "beta.yaml")
        write_fixture(path_no_system, RECORD_WITHOUT_SYSTEM)
        write_fixture(path_has_system, RECORD_WITH_SYSTEM)

        result = run_script("--apply", tmpdir)
        assert_equal(result.returncode, 0, "returncode")

        content_no_system = read_file(path_no_system)
        content_has_system = read_file(path_has_system)

        # alpha.yaml must have the system block appended.
        assert_in(EXPECTED_BLOCK, content_no_system, "alpha stamped")

        # beta.yaml must be byte-identical to original.
        assert_equal(
            content_has_system,
            RECORD_WITH_SYSTEM,
            "beta unchanged (already had system:)",
        )

        # Output must reflect the activity.
        assert_in("stamped", result.stdout, "stamped in output")
        assert_in("skipped", result.stdout, "skipped in output")

    print("PASS: test_directory_target_processes_yaml_files")


# ── Runner ─────────────────────────────────────────────────────────────────────


def main() -> None:
    tests = [
        test_help_exits_zero,
        test_idempotent_double_stamp,
        test_lossless_stamp_adds_only_system_block,
        test_existing_system_block_untouched,
        test_dry_run_does_not_modify_file,
        test_directory_target_processes_yaml_files,
        test_no_trailing_newline_branch,           # Review: code-reviewer Slice-B — F6
        test_missing_explicit_target_exits_nonzero,  # Review: code-reviewer Slice-B — F3
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as exc:
            print(f"FAIL: {test_fn.__name__}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"ERROR: {test_fn.__name__}: {type(exc).__name__}: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
