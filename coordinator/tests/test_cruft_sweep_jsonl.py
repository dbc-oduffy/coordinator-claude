"""
test_cruft_sweep_jsonl.py — JSONL wire-format tests for cruft-sweep.sh.

Spec backlink: docs/plans/2026-06-09-distill-cruft-sweep.md § C1 (AC5b)
Purpose: Verify that --dry-run --json emits valid JSONL records with the
         required schema {class, path, name, size_bytes, mtime, disposition,
         evidence} and that disposition values are within the allowed set.

Isolation: all tests use tmp_path fixtures + override flags.
           Paths passed via .as_posix() for Git-Bash compatibility on Windows.
           NEVER touches real ~/.claude/ state.
"""

import json
import os
import subprocess
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "cruft-sweep.sh"

REQUIRED_KEYS = {"class", "path", "name", "size_bytes", "mtime", "disposition", "evidence"}
VALID_DISPOSITIONS = {"auto-prune", "confirm-needed", "skip"}


def run(args, **kw):
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        **kw,
    )


def bp(p: Path) -> str:
    """Convert Path to bash-navigable string (Git-Bash C:/... compatible)."""
    return p.as_posix()


def _make_stale_uuid_dir(parent: Path, uuid: str, age_days: int = 20) -> Path:
    """Create a stale uuid directory with dummy content."""
    d = parent / uuid
    d.mkdir(parents=True, exist_ok=True)
    (d / "session.txt").write_text("old session state here")
    old_mtime = time.time() - age_days * 86400
    os.utime(d, (old_mtime, old_mtime))
    return d


def _make_stale_jsonl(parent: Path, uuid: str, age_days: int = 20) -> Path:
    """Create a stale <uuid>.jsonl file."""
    f = parent / f"{uuid}.jsonl"
    f.write_text('{"role":"user","content":"old transcript"}\n')
    old_mtime = time.time() - age_days * 86400
    os.utime(f, (old_mtime, old_mtime))
    return f


# ---------------------------------------------------------------------------
# AC5b: JSONL schema
# ---------------------------------------------------------------------------

class TestDryRunJsonlSchema:
    """Verify JSONL record schema from --dry-run --json (AC5b)."""

    UUID_1 = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    UUID_2 = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

    def test_dry_run_jsonl_schema(self, tmp_path):
        """--dry-run --json emits valid JSONL with required keys and valid disposition."""
        projects = tmp_path / "projects"
        repo_dir = projects / "repo"
        repo_dir.mkdir(parents=True)
        fh = tmp_path / "fh"
        fh.mkdir()
        log_path = tmp_path / "sweep-log.md"

        _make_stale_uuid_dir(repo_dir, self.UUID_1)
        _make_stale_jsonl(repo_dir, self.UUID_2)

        result = run([
            "--class", "harness",
            "--dry-run",
            "--json",
            "--days", "14",
            "--projects-root", bp(projects),
            "--file-history-root", bp(fh),
            "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
            "--log-path", bp(log_path),
        ])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Parse JSONL from stdout
        records = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                records.append(rec)
            except json.JSONDecodeError as e:
                raise AssertionError(
                    f"Invalid JSON line: {line!r}\nError: {e}"
                ) from e

        # Must have at least one record (we created stale content)
        assert len(records) >= 1, (
            f"Expected at least 1 JSONL record; got 0. stdout: {result.stdout!r}"
        )

        for rec in records:
            # All required keys present
            missing = REQUIRED_KEYS - set(rec.keys())
            assert not missing, (
                f"Record missing keys {missing}: {rec!r}"
            )

            # class must be "harness"
            assert rec["class"] == "harness", (
                f"Expected class='harness'; got {rec['class']!r}: {rec!r}"
            )

            # disposition must be in the allowed set
            assert rec["disposition"] in VALID_DISPOSITIONS, (
                f"Invalid disposition {rec['disposition']!r}; "
                f"must be one of {VALID_DISPOSITIONS}: {rec!r}"
            )

            # size_bytes must be a non-negative integer
            assert isinstance(rec["size_bytes"], (int, float)), (
                f"size_bytes must be numeric; got {type(rec['size_bytes'])}: {rec!r}"
            )
            assert rec["size_bytes"] >= 0, (
                f"size_bytes must be >= 0; got {rec['size_bytes']}: {rec!r}"
            )

            # mtime must be a positive number
            assert isinstance(rec["mtime"], (int, float)), (
                f"mtime must be numeric; got {type(rec['mtime'])}: {rec!r}"
            )
            assert rec["mtime"] > 0, (
                f"mtime must be > 0 (epoch seconds); got {rec['mtime']}: {rec!r}"
            )

            # path and name must be non-empty strings
            assert isinstance(rec["path"], str) and rec["path"], (
                f"path must be a non-empty string: {rec!r}"
            )
            assert isinstance(rec["name"], str) and rec["name"], (
                f"name must be a non-empty string: {rec!r}"
            )

            # evidence must be a string
            assert isinstance(rec["evidence"], str), (
                f"evidence must be a string: {rec!r}"
            )

    def test_no_json_output_on_apply(self, tmp_path):
        """--apply without --json does not emit JSONL lines to stdout."""
        projects = tmp_path / "projects"
        repo_dir = projects / "repo"
        repo_dir.mkdir(parents=True)
        fh = tmp_path / "fh"
        fh.mkdir()
        log_path = tmp_path / "sweep-log.md"

        _make_stale_uuid_dir(repo_dir, self.UUID_1)

        result = run([
            "--class", "harness",
            "--apply",
            "--days", "14",
            "--projects-root", bp(projects),
            "--file-history-root", bp(fh),
            "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
            "--log-path", bp(log_path),
        ])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Review: code-reviewer — try/except swallowed invalid JSON lines, masking bugs;
        # unconditional assert: --apply without --json must produce no stdout at all.
        assert not result.stdout.strip(), (
            f"Expected no stdout on --apply without --json; got: {result.stdout!r}"
        )

    def test_jsonl_no_log_written(self, tmp_path):
        """--dry-run --json does NOT write to log-path."""
        projects = tmp_path / "projects"
        repo_dir = projects / "repo"
        repo_dir.mkdir(parents=True)
        fh = tmp_path / "fh"
        fh.mkdir()
        log_path = tmp_path / "sweep-log.md"

        _make_stale_uuid_dir(repo_dir, self.UUID_1)

        result = run([
            "--class", "harness",
            "--dry-run",
            "--json",
            "--days", "14",
            "--projects-root", bp(projects),
            "--file-history-root", bp(fh),
            "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
            "--log-path", bp(log_path),
        ])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not log_path.exists(), (
            "log-path must NOT be written under --dry-run even with --json"
        )


# ---------------------------------------------------------------------------
# F5: --class all multi-class JSONL run
# ---------------------------------------------------------------------------

class TestAllClassJsonl:
    """Verify --class all --dry-run --json emits records for all three classes (F5).

    Review: code-reviewer — the --class all multi-class JSONL path was untested;
    this test builds a fixture with harness, scratch, and orphans candidates and
    asserts records for all three classes appear in the output.
    """

    STALE_UUID = "ffffffff-ffff-ffff-ffff-ffffffffffff"

    def test_class_all_emits_all_three_classes(self, tmp_path):
        """--class all --dry-run --json produces records with class in {harness, scratch, orphans}."""
        # --- harness candidate: stale UUID dir ---
        projects = tmp_path / "projects"
        repo_dir = projects / "testrepo"
        repo_dir.mkdir(parents=True)
        fh = tmp_path / "fh"
        fh.mkdir()
        _make_stale_uuid_dir(repo_dir, self.STALE_UUID, age_days=20)

        # --- scratch candidate: stale 'nonexistent/' under repo-root ---
        repo_root = tmp_path / "repo-root"
        repo_root.mkdir(parents=True)
        scratch_dir = repo_root / "nonexistent"
        scratch_dir.mkdir()
        (scratch_dir / "file.txt").write_text("old scratch")
        old_mtime = time.time() - 10 * 86400  # 10 days old, threshold 7
        os.utime(scratch_dir, (old_mtime, old_mtime))

        # --- orphans candidate: 'fake/' with chroma fingerprint ---
        parent_root = tmp_path / "parent-vol"
        parent_root.mkdir()
        orphan_dir = parent_root / "fake"
        orphan_dir.mkdir()
        chroma = orphan_dir / "vector" / "store" / "chroma.sqlite3"
        chroma.parent.mkdir(parents=True)
        chroma.write_text("chroma-db")

        log_path = tmp_path / "sweep-log.md"

        result = run([
            "--class", "all",
            "--dry-run",
            "--json",
            "--days", "14",
            "--projects-root", bp(projects),
            "--file-history-root", bp(fh),
            "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
            "--log-path", bp(log_path),
            "--repo-root", bp(repo_root),
            "--scratch-age-days", "7",
            "--parent-root", bp(parent_root),
        ])
        assert result.returncode == 0, (
            f"Expected exit 0; got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Parse JSONL
        records = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

        assert records, f"Expected JSONL records from --class all; got none. stdout={result.stdout!r}"

        classes_seen = {r.get("class") for r in records}
        assert "harness" in classes_seen, (
            f"Expected 'harness' class record; got classes: {classes_seen}; records: {records!r}"
        )
        assert "scratch" in classes_seen, (
            f"Expected 'scratch' class record; got classes: {classes_seen}; records: {records!r}"
        )
        assert "orphans" in classes_seen, (
            f"Expected 'orphans' class record; got classes: {classes_seen}; records: {records!r}"
        )
