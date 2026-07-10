#!/bin/sh
# ── sh/python polyglot trampoline ──────────────────────────────────────────────
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
from __future__ import annotations
"""
migrate-debt-backlog.test.py — test suite for migrate-debt-backlog.py.

Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C7

Tests run against a tmpdir fixture (small synthetic debt-backlog.md with
2-3 entries). No third-party deps — stdlib unittest only.

Test cases:
  - test_help_exits_zero
  - test_dryrun_writes_classification_json
  - test_table_row_parses_to_required_fields
  - test_apply_refuses_without_dryrun_file
  - test_apply_refuses_stale_dryrun
  - test_unmigrated_parse_error_stays_in_source
"""

import json
import os
import sys
import subprocess
import tempfile
import time
import unittest

# ── Locate the module under test ───────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MIGRATOR = os.path.join(_SCRIPT_DIR, "migrate-debt-backlog.py")

# ── Synthetic test fixtures ────────────────────────────────────────────────────

# A well-formed debt-backlog.md with:
#   - a header block
#   - alignment row
#   - two well-formed table rows
#   - one malformed table row (too few cells)
#   - one bullet-list section entry (which always lands as parse-error per spec)
_SYNTHETIC_DEBT_BACKLOG = """\
# Technical Debt Backlog

> Tracks architectural debt items identified during strategic reviews.
> Format: ID | Source | Status | Item | Risk | Suggested Action

| ID | Source | Status | Item | Risk | Suggested Action |
|----|--------|--------|------|------|-----------------|
| DSR-2026-04-02-1 | daily-review/the Staff Engineer/2026-04-02 | resolved | Codex plugin registered as marketplace source with no version pin. | Reproducibility liability — upstream change silently breaks plugin load. | Pin to a resolved commit SHA or release tag before open-source launch. |
| CDX-2026-04-03-1 | codex-review-gate/2026-04-03 | open | suggest-sonnet-research.sh recommends /notebooklm-research without checking for the notebooklm sub-plugin. | Misleading nudge on installs with deep-research but without notebooklm. | Gate the NotebookLM suggestion on deep-research/notebooklm directory. |
| BAD-ROW | only-two-cells |

## 2026-06-08 daily observer flags

- [ ] DSR-2026-06-08-1 [for-weekly-arch-review] Runtime-tripwire thresholds have no empirical basis — surfaces: plugins/coordinator/hooks/scripts/lib/runtime-thresholds.sh
"""

_HEADER_ONLY_BACKLOG = """\
# Technical Debt Backlog

| ID | Source | Status | Item | Risk | Suggested Action |
|----|--------|--------|------|------|-----------------|
"""


def _write_synthetic_backlog(tmpdir: str, content: str = _SYNTHETIC_DEBT_BACKLOG) -> str:
    """Write the synthetic debt-backlog.md into tmpdir and return its path."""
    path = os.path.join(tmpdir, "debt-backlog.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def _run_migrator(*args, cwd: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run the migrator script with given arguments and return the completed process."""
    cmd = [sys.executable, _MIGRATOR] + list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


# ── Test Cases ─────────────────────────────────────────────────────────────────

class TestHelpExitsZero(unittest.TestCase):
    """AC: --help exits 0 and produces usage output."""

    def test_help_exits_zero(self) -> None:
        result = _run_migrator("--help")
        self.assertEqual(result.returncode, 0, f"--help should exit 0, got {result.returncode}. stderr: {result.stderr}")
        self.assertIn("migrate-debt-backlog", result.stdout.lower() + result.stderr.lower(),
                      "--help output should mention the script name")


class TestDryrunWritesClassificationJson(unittest.TestCase):
    """AC: --dry-run writes a JSON file with classifications; does not modify input."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._input = _write_synthetic_backlog(self._tmpdir)
        self._output = os.path.join(self._tmpdir, "dryrun-out.json")
        # Record input mtime before run.
        self._input_mtime_before = os.path.getmtime(self._input)

    def test_dryrun_writes_classification_json(self) -> None:
        result = _run_migrator(
            "--dry-run",
            "--input", self._input,
            "--output", self._output,
        )
        self.assertEqual(result.returncode, 0, f"dry-run failed: {result.stderr}")
        self.assertTrue(os.path.exists(self._output), "dry-run output JSON should exist")

        with open(self._output, "r", encoding="utf-8") as fh:
            entries = json.load(fh)

        self.assertIsInstance(entries, list, "dry-run JSON should be a list")
        self.assertGreater(len(entries), 0, "dry-run JSON should contain entries")

        classifications = {e["classification"] for e in entries}
        # Must have at least one to-migrate (the two well-formed table rows)
        # and at least one unmigrated-parse-error (malformed row + bullet).
        self.assertIn("to-migrate", classifications,
                      "should classify at least one row as to-migrate")
        self.assertIn("unmigrated-parse-error", classifications,
                      "should classify at least one row as unmigrated-parse-error")

        # Input file must NOT have been modified.
        input_mtime_after = os.path.getmtime(self._input)
        self.assertEqual(
            self._input_mtime_before,
            input_mtime_after,
            "dry-run must not modify the input file",
        )

    def test_dryrun_stdout_has_summary(self) -> None:
        result = _run_migrator(
            "--dry-run",
            "--input", self._input,
            "--output", self._output,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("to-migrate", result.stdout,
                      "dry-run stdout should include 'to-migrate' summary line")

    def test_dryrun_missing_input_returns_nonzero(self) -> None:
        result = _run_migrator(
            "--dry-run",
            "--input", "/nonexistent/path/debt-backlog.md",
            "--output", self._output,
        )
        self.assertNotEqual(result.returncode, 0, "should fail on missing input")


class TestTableRowParsesToRequiredFields(unittest.TestCase):
    """AC: a well-formed table row produces a parsed dict with all required fields."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._input = _write_synthetic_backlog(self._tmpdir)
        self._output = os.path.join(self._tmpdir, "dryrun-out.json")

    def test_table_row_parses_to_required_fields(self) -> None:
        result = _run_migrator(
            "--dry-run",
            "--input", self._input,
            "--output", self._output,
        )
        self.assertEqual(result.returncode, 0, f"dry-run failed: {result.stderr}")

        with open(self._output, "r", encoding="utf-8") as fh:
            entries = json.load(fh)

        to_migrate = [e for e in entries if e["classification"] == "to-migrate"]
        self.assertGreaterEqual(len(to_migrate), 2, "should have at least 2 to-migrate rows")

        required_fields = ["id", "created", "source", "status", "title", "body", "risk", "suggested_action"]
        for entry in to_migrate:
            parsed = entry.get("parsed", {})
            self.assertIsInstance(parsed, dict, "to-migrate entry should have a 'parsed' dict")
            for field in required_fields:
                self.assertIn(field, parsed, f"parsed entry missing required field: {field}")
                self.assertTrue(parsed[field], f"parsed entry has empty required field: {field}")

    def test_table_row_id_and_created_match(self) -> None:
        """DSR-2026-04-02-1 should parse with created = 2026-04-02."""
        result = _run_migrator(
            "--dry-run",
            "--input", self._input,
            "--output", self._output,
        )
        self.assertEqual(result.returncode, 0)

        with open(self._output, "r", encoding="utf-8") as fh:
            entries = json.load(fh)

        dsr_1 = next(
            (e for e in entries
             if e["classification"] == "to-migrate"
             and e.get("parsed", {}).get("id") == "DSR-2026-04-02-1"),
            None,
        )
        self.assertIsNotNone(dsr_1, "DSR-2026-04-02-1 should be a to-migrate entry")
        self.assertEqual(dsr_1["parsed"]["created"], "2026-04-02")
        self.assertEqual(dsr_1["parsed"]["status"], "resolved")

    def test_table_row_cdx_parses(self) -> None:
        """CDX prefix row should parse with status = open."""
        result = _run_migrator(
            "--dry-run",
            "--input", self._input,
            "--output", self._output,
        )
        self.assertEqual(result.returncode, 0)

        with open(self._output, "r", encoding="utf-8") as fh:
            entries = json.load(fh)

        cdx_1 = next(
            (e for e in entries
             if e["classification"] == "to-migrate"
             and e.get("parsed", {}).get("id") == "CDX-2026-04-03-1"),
            None,
        )
        self.assertIsNotNone(cdx_1, "CDX-2026-04-03-1 should be a to-migrate entry")
        self.assertEqual(cdx_1["parsed"]["status"], "open")
        self.assertEqual(cdx_1["parsed"]["source"], "codex-review-gate/2026-04-03")


class TestApplyRefusesWithoutDryrunFile(unittest.TestCase):
    """AC: --apply fails with a clear error when no dry-run file is present."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._input = _write_synthetic_backlog(self._tmpdir)

    def test_apply_refuses_without_dryrun_file(self) -> None:
        nonexistent = os.path.join(self._tmpdir, "no-such-dryrun.json")
        result = _run_migrator(
            "--apply",
            "--input", self._input,
            "--from-dryrun", nonexistent,
        )
        self.assertNotEqual(result.returncode, 0, "--apply should fail without a dry-run file")
        self.assertTrue(
            "dry-run" in result.stderr.lower() or "dry-run" in result.stdout.lower(),
            f"error message should mention dry-run. stderr: {result.stderr}, stdout: {result.stdout}",
        )

    def test_apply_refuses_no_autodiscover(self) -> None:
        """--apply without --from-dryrun should fail when no auto-discoverable dryrun exists."""
        # Run from a tmpdir that has no state/migrate-debt-backlog-dryrun-*.json files.
        result = _run_migrator(
            "--apply",
            "--input", self._input,
            cwd=self._tmpdir,
        )
        self.assertNotEqual(result.returncode, 0,
                            "--apply without any dryrun file should exit non-zero")


class TestApplyRefusesStaleDryrun(unittest.TestCase):
    """AC: --apply rejects a dry-run file older than --stale-hours."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._input = _write_synthetic_backlog(self._tmpdir)
        self._dryrun = os.path.join(self._tmpdir, "old-dryrun.json")
        # Write a minimal valid-looking dryrun JSON.
        with open(self._dryrun, "w", encoding="utf-8") as fh:
            json.dump([{"source_line": 1, "classification": "to-migrate",
                        "entry_text": "| DSR-2026-04-02-1 | ...",
                        "entry_kind": "table_row",
                        "parsed": {
                            "id": "DSR-2026-04-02-1", "created": "2026-04-02",
                            "source": "daily-review/the Staff Engineer/2026-04-02",
                            "status": "resolved", "title": "Test",
                            "body": "Body text", "risk": "Some risk",
                            "suggested_action": "Some action",
                        },
                        "reason": "ok"}], fh)
        # Backdate the file by 26 hours (well past the 24h limit).
        past_mtime = time.time() - (26 * 3600)
        os.utime(self._dryrun, (past_mtime, past_mtime))

    def test_apply_refuses_stale_dryrun(self) -> None:
        result = _run_migrator(
            "--apply",
            "--input", self._input,
            "--from-dryrun", self._dryrun,
            "--stale-hours", "24",
        )
        self.assertNotEqual(result.returncode, 0,
                            "--apply should reject a 26h-old dry-run file with limit=24h")
        error_output = result.stderr + result.stdout
        self.assertTrue(
            "stale" in error_output.lower() or "old" in error_output.lower() or
            "hours" in error_output.lower(),
            f"error should mention staleness. stderr: {result.stderr}, stdout: {result.stdout}",
        )

    def test_apply_accepts_fresh_dryrun(self) -> None:
        """A freshly-written dry-run should not be rejected for staleness."""
        # Update the mtime to now.
        now = time.time()
        os.utime(self._dryrun, (now, now))
        # We can't easily test the full apply flow without coordinator-queue-append
        # being on PATH, but the staleness check happens before the binary check.
        # We just verify the staleness error is NOT produced.
        result = _run_migrator(
            "--apply",
            "--input", self._input,
            "--from-dryrun", self._dryrun,
            "--stale-hours", "24",
        )
        error_output = result.stderr + result.stdout
        # The file is fresh so staleness error must not appear.
        self.assertNotIn(
            "stale", error_output.lower(),
            f"fresh dry-run should not produce staleness error. stderr: {result.stderr}",
        )


class TestUnmigratedParseErrorStaysInSource(unittest.TestCase):
    """AC: unmigrated-parse-error entries remain in the source file after a dry-run
    (dry-run is read-only) and are marked unmigrated-parse-error in the JSON."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._input = _write_synthetic_backlog(self._tmpdir)
        self._output = os.path.join(self._tmpdir, "dryrun-out.json")

    def test_unmigrated_parse_error_in_json(self) -> None:
        result = _run_migrator(
            "--dry-run",
            "--input", self._input,
            "--output", self._output,
        )
        self.assertEqual(result.returncode, 0)

        with open(self._output, "r", encoding="utf-8") as fh:
            entries = json.load(fh)

        parse_errors = [e for e in entries if e["classification"] == "unmigrated-parse-error"]
        self.assertGreater(len(parse_errors), 0,
                           "should have at least one unmigrated-parse-error entry "
                           "(malformed row + bullet entry)")

    def test_bad_row_classified_as_parse_error(self) -> None:
        """The 2-cell BAD-ROW should land as unmigrated-parse-error."""
        result = _run_migrator(
            "--dry-run",
            "--input", self._input,
            "--output", self._output,
        )
        self.assertEqual(result.returncode, 0)

        with open(self._output, "r", encoding="utf-8") as fh:
            entries = json.load(fh)

        bad_row_errors = [
            e for e in entries
            if e["classification"] == "unmigrated-parse-error"
            and "BAD-ROW" in e.get("entry_text", "")
        ]
        self.assertGreater(len(bad_row_errors), 0,
                           "BAD-ROW (too few cells) should be unmigrated-parse-error")

    def test_bullet_entry_classified_as_parse_error(self) -> None:
        """Bullet entries always land as unmigrated-parse-error (missing risk/suggested_action)."""
        result = _run_migrator(
            "--dry-run",
            "--input", self._input,
            "--output", self._output,
        )
        self.assertEqual(result.returncode, 0)

        with open(self._output, "r", encoding="utf-8") as fh:
            entries = json.load(fh)

        bullet_errors = [
            e for e in entries
            if e["classification"] == "unmigrated-parse-error"
            and e.get("entry_kind") == "bullet"
        ]
        self.assertGreater(len(bullet_errors), 0,
                           "bullet entries should be unmigrated-parse-error (missing fields)")

    def test_source_file_unchanged_after_dryrun(self) -> None:
        """After --dry-run, the input file must be byte-for-byte identical."""
        with open(self._input, "r", encoding="utf-8") as fh:
            content_before = fh.read()

        result = _run_migrator(
            "--dry-run",
            "--input", self._input,
            "--output", self._output,
        )
        self.assertEqual(result.returncode, 0)

        with open(self._input, "r", encoding="utf-8") as fh:
            content_after = fh.read()

        self.assertEqual(
            content_before,
            content_after,
            "input file must not be modified by --dry-run",
        )

    def test_empty_source_produces_valid_json(self) -> None:
        """A debt-backlog.md with only headers produces a valid (empty) JSON array."""
        empty_input = os.path.join(self._tmpdir, "empty-backlog.md")
        with open(empty_input, "w", encoding="utf-8") as fh:
            fh.write(_HEADER_ONLY_BACKLOG)

        empty_output = os.path.join(self._tmpdir, "empty-dryrun.json")
        result = _run_migrator(
            "--dry-run",
            "--input", empty_input,
            "--output", empty_output,
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.exists(empty_output))
        with open(empty_output, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data, [], "empty source should produce empty JSON array")


if __name__ == "__main__":
    unittest.main(verbosity=2)
