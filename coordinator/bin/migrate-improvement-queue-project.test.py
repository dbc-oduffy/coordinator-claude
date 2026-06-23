#!/bin/sh
''''exec "$(command -v python3 || command -v python || command -v py)" "$0" "$@" #'''
"""
Tests for migrate-improvement-queue-project.py

Run: python migrate-improvement-queue-project.test.py

Tests verify:
  - test_help_exits_zero
  - test_dryrun_writes_classification_json
  - test_pipe_delimited_row_parses_to_required_fields
  - test_universal_tag_excluded
  - test_apply_refuses_stale_dryrun
  - test_change_kind_inference_sh_surface
  - test_change_kind_inference_skill_surface
  - test_change_kind_inference_wiki_surface
  - test_change_kind_inference_ambiguous_default
  - test_parse_error_on_missing_cells
  - test_proposed_target_prefix_stripped

Spec backlink: docs/plans/2026-06-15-structured-queue-medium-rollout.md § C9
"""

import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

# Resolve the path to the module under test.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_SCRIPT_DIR, "migrate-improvement-queue-project.py")

# Import the module directly for unit-testing internal helpers.
import importlib.util

_spec = importlib.util.spec_from_file_location("migrator", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]


def _run_script(*args: str) -> subprocess.CompletedProcess:
    """Run the migrator script as a subprocess with the given args."""
    return subprocess.run(
        [sys.executable, _MODULE_PATH, *args],
        capture_output=True,
        text=True,
    )


# ── Sample entries ─────────────────────────────────────────────────────────────

# A clean 5-cell project-specific entry (script surface).
_CLEAN_SH_ENTRY = (
    "- 2026-06-15 | self | hooks/scripts/block-subagent-plan-body-write.sh "
    "+ validate-frontmatter-schema.js | Check emits.tsv next time we see "
    "a validation error. Diagnostic-only. | proposed target: review emits.tsv when prompted"
)

# A clean 5-cell entry with a SKILL.md surface.
_CLEAN_SKILL_ENTRY = (
    "- 2026-05-08 | self | skills/learn-lessons/SKILL.md | "
    "Add a step to skip repos not on disk. | proposed target: SKILL.md Phase 2.6"
)

# A clean 5-cell entry with a docs/wiki/ surface.
_CLEAN_WIKI_ENTRY = (
    "- 2026-05-08 | self | docs/wiki/improvement-queue-schema.md | "
    "Append drain-writeback note. | proposed target: docs/wiki/improvement-queue-schema.md § Lifecycle"
)

# A clean 5-cell entry with an ambiguous surface (no .sh / SKILL.md / docs/wiki/).
_AMBIGUOUS_SURFACE_ENTRY = (
    "- 2026-05-08 | self | bin/tests/ | "
    "Add test-publish-depersonalize.sh covering synthetic mirror-mode target. "
    "| proposed target: bin/tests/test-publish-depersonalize.sh (new file)"
)

# An entry carrying [universal] tag — must be excluded.
_UNIVERSAL_ENTRY = (
    "- 2026-05-08 | self | docs/wiki/something.md | "
    "[universal] This is a cross-repo pattern. "
    "| proposed target: ~/.claude/docs/wiki/something.md"
)

# A malformed entry (only 3 cells).
_SHORT_ENTRY = "- 2026-05-08 | self | missing-body-and-target"

# A non-entry line (header).
_HEADER_LINE = "Actionable lessons scoped to this repository's structure."


class TestHelpExitsZero(unittest.TestCase):
    """test_help_exits_zero: --help must exit 0 and print usage."""

    def test_help_exits_zero(self) -> None:
        result = _run_script("--help")
        self.assertEqual(
            result.returncode,
            0,
            f"Expected exit 0 from --help; got {result.returncode}.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}",
        )
        self.assertIn(
            "dry-run",
            result.stdout.lower(),
            "--help output should mention --dry-run",
        )
        self.assertIn(
            "apply",
            result.stdout.lower(),
            "--help output should mention --apply",
        )


class TestDryrunWritesClassificationJson(unittest.TestCase):
    """test_dryrun_writes_classification_json: --dry-run writes a valid JSON audit log."""

    def test_dryrun_writes_classification_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a small synthetic improvement-queue.md.
            queue_file = os.path.join(tmpdir, "improvement-queue.md")
            with open(queue_file, "w", encoding="utf-8") as fh:
                fh.write("# Per-project improvement queue\n\n")
                fh.write(_CLEAN_SH_ENTRY + "\n")
                fh.write(_UNIVERSAL_ENTRY + "\n")
                fh.write(_SHORT_ENTRY + "\n")

            out_file = os.path.join(tmpdir, "dryrun.json")
            result = _run_script(
                "--dry-run",
                "--input", queue_file,
                "--output", out_file,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"--dry-run exited non-zero:\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}",
            )
            self.assertTrue(
                os.path.isfile(out_file),
                f"Expected dryrun JSON at {out_file}; not found.",
            )

            with open(out_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            self.assertIsInstance(data, list, "Dry-run output must be a JSON array.")
            # Should have 3 entries (one per non-header line).
            self.assertEqual(len(data), 3, f"Expected 3 entries; got {len(data)}.")

            # Verify the classification keys exist on every entry.
            for row in data:
                self.assertIn("source_line", row)
                self.assertIn("classification", row)
                self.assertIn("entry_text", row)
                self.assertIn("reason", row)

            classifications = {row["classification"] for row in data}
            self.assertIn("to-migrate", classifications)
            self.assertIn("unmigrated-universal-leftover", classifications)
            self.assertIn("unmigrated-parse-error", classifications)


class TestPipeDelimitedRowParsesToRequiredFields(unittest.TestCase):
    """test_pipe_delimited_row_parses_to_required_fields: a clean 5-cell row produces all required fields."""

    def test_pipe_delimited_row_parses_to_required_fields(self) -> None:
        result = _mod._parse_project_entry(_CLEAN_SH_ENTRY + "\n")

        self.assertIsNotNone(result, "_parse_project_entry returned None for a valid entry.")
        self.assertEqual(result["classification"], "to-migrate")

        # All five logical cells must be present and non-empty.
        for field in ("created", "surface", "body", "proposed_target", "title", "change_kind"):
            self.assertIn(field, result, f"Missing field: {field}")
            self.assertTrue(result[field], f"Field '{field}' is empty.")

        # created must look like an ISO date.
        self.assertRegex(
            result["created"],
            r"^\d{4}-\d{2}-\d{2}$",
            f"created field {result['created']!r} is not an ISO date.",
        )

        # title is synthesized from first 80 chars of body.
        self.assertLessEqual(
            len(result["title"]),
            80,
            f"title should be ≤80 chars; got {len(result['title'])}.",
        )

        # proposed_target must NOT carry the "proposed target: " prefix.
        self.assertFalse(
            result["proposed_target"].startswith("proposed target:"),
            f"proposed_target still has prefix: {result['proposed_target']!r}",
        )


class TestUniversalTagExcluded(unittest.TestCase):
    """test_universal_tag_excluded: [universal]-tagged entries classify as unmigrated-universal-leftover."""

    def test_universal_tag_excluded(self) -> None:
        result = _mod._parse_project_entry(_UNIVERSAL_ENTRY + "\n")

        self.assertIsNotNone(result)
        self.assertEqual(
            result["classification"],
            "unmigrated-universal-leftover",
            f"Expected 'unmigrated-universal-leftover'; got {result['classification']!r}",
        )
        # Must NOT be classified as to-migrate.
        self.assertNotEqual(result["classification"], "to-migrate")


class TestApplyRefusesStaleDryrun(unittest.TestCase):
    """test_apply_refuses_stale_dryrun: --apply exits non-zero when the dry-run file is too old."""

    def test_apply_refuses_stale_dryrun(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a syntactically valid dry-run JSON file.
            stale_path = os.path.join(tmpdir, "stale-dryrun.json")
            with open(stale_path, "w", encoding="utf-8") as fh:
                json.dump([], fh)

            # Backdate the file's mtime by 25 hours (> 24h limit).
            twenty_five_hours_ago = time.time() - (25 * 3600)
            os.utime(stale_path, (twenty_five_hours_ago, twenty_five_hours_ago))

            # Write a dummy input file so the path check doesn't fail first.
            queue_file = os.path.join(tmpdir, "improvement-queue.md")
            with open(queue_file, "w", encoding="utf-8") as fh:
                fh.write("# empty\n")

            result = _run_script(
                "--apply",
                "--from-dryrun", stale_path,
                "--input", queue_file,
                "--stale-hours", "24",
            )

            self.assertNotEqual(
                result.returncode,
                0,
                "--apply must exit non-zero when the dry-run file is stale.",
            )
            # The error message may say "stale" or "old" or "limit" — check for
            # the age limit value which is always present.
            self.assertTrue(
                "stale" in result.stderr.lower()
                or "old" in result.stderr.lower()
                or "limit" in result.stderr.lower(),
                f"Error message should mention staleness; got: {result.stderr!r}",
            )


class TestChangeKindInferenceSh(unittest.TestCase):
    """change_kind → script-edit when surface contains '.sh'."""

    def test_change_kind_inference_sh_surface(self) -> None:
        kind, ambiguous = _mod._infer_change_kind("hooks/scripts/block-subagent.sh")
        self.assertEqual(kind, "script-edit")
        self.assertFalse(ambiguous)


class TestChangeKindInferenceSkill(unittest.TestCase):
    """change_kind → skill-edit when surface contains 'SKILL.md'."""

    def test_change_kind_inference_skill_surface(self) -> None:
        kind, ambiguous = _mod._infer_change_kind("skills/learn-lessons/SKILL.md")
        self.assertEqual(kind, "skill-edit")
        self.assertFalse(ambiguous)


class TestChangeKindInferenceWiki(unittest.TestCase):
    """change_kind → wiki-append when surface contains 'docs/wiki/'."""

    def test_change_kind_inference_wiki_surface(self) -> None:
        kind, ambiguous = _mod._infer_change_kind("docs/wiki/improvement-queue-schema.md")
        self.assertEqual(kind, "wiki-append")
        self.assertFalse(ambiguous)


class TestChangeKindInferenceAmbiguous(unittest.TestCase):
    """change_kind → script-edit (default) with inference='ambiguous' when surface matches no rule."""

    def test_change_kind_inference_ambiguous_default(self) -> None:
        kind, ambiguous = _mod._infer_change_kind("bin/tests/")
        self.assertEqual(kind, "script-edit", "Default kind must be script-edit.")
        self.assertTrue(ambiguous, "Ambiguous flag must be True when no rule matches.")


class TestParseErrorOnMissingCells(unittest.TestCase):
    """_parse_project_entry returns unmigrated-parse-error when fewer than 5 cells present."""

    def test_parse_error_on_missing_cells(self) -> None:
        result = _mod._parse_project_entry(_SHORT_ENTRY + "\n")
        self.assertIsNotNone(result)
        self.assertEqual(result["classification"], "unmigrated-parse-error")


class TestProposedTargetPrefixStripped(unittest.TestCase):
    """proposed_target field has 'proposed target: ' prefix stripped."""

    def test_proposed_target_prefix_stripped(self) -> None:
        # Construct a line with an explicit known proposed_target value.
        line = (
            "- 2026-05-08 | self | setup/publish.sh:88-95 | "
            "Promote the 7 persona-name patterns into REVIEW_PATTERNS. "
            "| proposed target: setup/publish.sh (REVIEW_PATTERNS array)\n"
        )
        result = _mod._parse_project_entry(line)
        self.assertIsNotNone(result)
        self.assertEqual(result["classification"], "to-migrate")
        self.assertEqual(
            result["proposed_target"],
            "setup/publish.sh (REVIEW_PATTERNS array)",
            f"Expected prefix stripped; got {result['proposed_target']!r}",
        )


class TestNonEntryLineReturnsNone(unittest.TestCase):
    """_parse_project_entry returns None for non-bullet lines."""

    def test_header_line_returns_none(self) -> None:
        result = _mod._parse_project_entry(_HEADER_LINE + "\n")
        self.assertIsNone(result, "Header line should return None.")

    def test_blank_line_returns_none(self) -> None:
        result = _mod._parse_project_entry("\n")
        self.assertIsNone(result, "Blank line should return None.")


class TestDryrunOutputNotModifiesInput(unittest.TestCase):
    """--dry-run must NOT modify the input file."""

    def test_dryrun_does_not_modify_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = os.path.join(tmpdir, "improvement-queue.md")
            original_content = f"{_CLEAN_SH_ENTRY}\n{_UNIVERSAL_ENTRY}\n"
            with open(queue_file, "w", encoding="utf-8") as fh:
                fh.write(original_content)

            out_file = os.path.join(tmpdir, "dryrun.json")
            _run_script("--dry-run", "--input", queue_file, "--output", out_file)

            with open(queue_file, "r", encoding="utf-8") as fh:
                after = fh.read()

            self.assertEqual(
                original_content,
                after,
                "--dry-run must not modify the input file.",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
