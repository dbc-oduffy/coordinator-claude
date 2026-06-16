"""
test_cruft_sweep_phase_a.py — Phase A harness retention tests for cruft-sweep.sh.

Spec backlink: docs/plans/2026-06-09-distill-cruft-sweep.md § C1 (AC1, AC2)
Purpose: Verify flag surface, dry-run reporting, and predecessor UUID pre-flight.

Isolation: all tests use tmp_path fixtures + override flags.
           NEVER touches real ~/.claude/projects/, ~/.claude/file-history/,
           or ~/.claude/state/cruft-sweep-log.md.

Negative-spec: tests do not rely on --apply deleting real coordinator state;
               the predecessor-skipped test uses --apply on a tmp_path fixture
               and asserts the UUID dir is preserved.
               Tests pass paths via .as_posix() so Git-Bash can navigate them
               on Windows (forward-slash C:/... paths are portable to Git-Bash).
"""

import json
import os
import subprocess
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "cruft-sweep.sh"


def run(args, **kw):
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        **kw,
    )


def bp(p: Path) -> str:
    """Convert a Path to a bash-navigable string on all platforms.

    On Windows, Path.as_posix() gives C:/... which Git-Bash handles correctly.
    On macOS/Linux, it is equivalent to str(p).
    """
    return p.as_posix()


def _make_stale_uuid_dir(parent: Path, uuid: str, age_days: int = 15) -> Path:
    """Create a uuid directory under parent with mtime aged by age_days."""
    d = parent / uuid
    d.mkdir(parents=True, exist_ok=True)
    (d / "dummy.txt").write_text("session data")
    old_mtime = time.time() - age_days * 86400
    os.utime(d, (old_mtime, old_mtime))
    return d


def _make_stale_jsonl(parent: Path, uuid: str, age_days: int = 15) -> Path:
    """Create a <uuid>.jsonl file under parent with mtime aged by age_days."""
    f = parent / f"{uuid}.jsonl"
    f.write_text('{"role":"user","content":"hi"}\n')
    old_mtime = time.time() - age_days * 86400
    os.utime(f, (old_mtime, old_mtime))
    return f


# ---------------------------------------------------------------------------
# AC1: flag surface
# ---------------------------------------------------------------------------

class TestFlagSurface:
    """Verify the script's flag surface (AC1)."""

    def test_help_emits_flag_names(self, tmp_path):
        """--help emits the expected flag names."""
        result = run(["--help"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = result.stdout + result.stderr
        # Review: code-reviewer — --repo-root, --scratch-age-days, --parent-root were
        # missing from this list; all three are valid flags exposed by the script.
        for flag in ["--days", "--apply", "--dry-run", "--class", "--json",
                     "--projects-root", "--file-history-root", "--handoffs-glob",
                     "--log-path", "--quiet", "--repo-root", "--scratch-age-days",
                     "--parent-root"]:
            assert flag in output, f"flag {flag!r} missing from --help output"

    def test_unknown_flag_exits_2(self, tmp_path):
        """Unknown flag exits with code 2."""
        result = run(["--not-a-real-flag"])
        assert result.returncode == 2, (
            f"Expected exit 2 for unknown flag, got {result.returncode}; "
            f"stderr: {result.stderr}"
        )

    def test_unknown_class_exits_2(self, tmp_path):
        """Unknown --class value exits with code 2."""
        result = run(["--class", "badclass"])
        assert result.returncode == 2, (
            f"Expected exit 2 for unknown class, got {result.returncode}; "
            f"stderr: {result.stderr}"
        )

    def test_quiet_emits_grand_total_to_stderr(self, tmp_path):
        """--quiet suppresses per-class banners but MUST still emit the grand-total banner to stderr.

        Regression test for the bug discovered 2026-06-14: the script previously
        gated the grand-total emit on `QUIET=0`, suppressing it under --quiet.
        That silently broke /workday-start Step 1.11, which reads this banner
        from stderr to check the 1 GB advisory threshold. The wiki contract at
        docs/wiki/cruft-sweep-cadence.md § --quiet output contract is the
        authoritative spec: under --quiet, this one stderr line is the only output.

        Coverage scope: this test exercises --dry-run --quiet (the /workday-start
        Step 1.11 callsite). The grand-total emit at cruft-sweep.sh:1158 is mode-
        agnostic — the gate is `JSON_MODE -eq 0`, not on APPLY — so this single
        test covers both /workday-start Step 1.11 (dry-run) and /workday-complete
        Step 1.5 (apply) by extension. --dry-run is preferred here because it
        does not require staging stale-UUID fixtures whose deletion side-effects
        the emit assertion does not depend on.
        """
        projects = tmp_path / "projects"
        projects.mkdir()
        fh = tmp_path / "fh"
        fh.mkdir()
        log_path = tmp_path / "sweep-log.md"

        # --class harness keeps the test fast (no parent-root scan against real X:/, E:/dev/);
        # the grand-total emit is class-agnostic — it runs after the case-statement in cruft-sweep.sh.
        result = run([
            "--class", "harness",
            "--dry-run",
            "--quiet",
            "--days", "14",
            "--projects-root", bp(projects),
            "--file-history-root", bp(fh),
            "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
            "--log-path", bp(log_path),
        ], timeout=30)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # stdout must be empty under --quiet (no JSON, no per-class banners).
        assert result.stdout == "", (
            f"--quiet must leave stdout empty; got stdout={result.stdout!r}"
        )
        # The grand-total banner MUST appear on stderr — this is the signal
        # /workday-start Step 1.11 reads for its 1 GB threshold check.
        assert "grand total" in result.stderr, (
            f"--quiet must emit grand-total banner on stderr; got stderr={result.stderr!r}"
        )
        assert "reclaimable across all classes" in result.stderr, (
            f"grand-total banner shape changed; got stderr={result.stderr!r}"
        )

    def test_default_is_dry_run(self, tmp_path):
        """Script runs in dry-run mode by default (no log written without --apply, stale dir preserved)."""
        # Review: code-reviewer — empty fixture didn't verify that dry-run default
        # actually withholds deletions; stale dir must still exist after a default run.
        log_path = tmp_path / "sweep-log.md"
        projects = tmp_path / "projects"
        repo_dir = projects / "myrepo"
        fh = tmp_path / "fh"
        repo_dir.mkdir(parents=True)
        fh.mkdir()

        stale_dir = _make_stale_uuid_dir(repo_dir, "f0000000-0000-0000-0000-000000000000", age_days=20)

        result = run([
            "--class", "harness",
            "--projects-root", bp(projects),
            "--file-history-root", bp(fh),
            "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
            "--log-path", bp(log_path),
        ])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not log_path.exists(), "log file must not be written in dry-run mode"
        assert stale_dir.exists(), "stale UUID dir must NOT be deleted in default (dry-run) mode"


# ---------------------------------------------------------------------------
# AC2: Phase A behavior — dry-run reports size summary, --apply deletes
# ---------------------------------------------------------------------------

class TestDryRunSizeSummary:
    """Verify dry-run reports counts/bytes and writes no log (AC2)."""

    TEST_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_dry_run_reports_size_summary(self, tmp_path):
        """Dry-run reports UUID and counts; log is NOT written."""
        projects = tmp_path / "projects"
        repo_dir = projects / "myrepo"
        repo_dir.mkdir(parents=True)
        fh = tmp_path / "fh"
        fh.mkdir()
        log_path = tmp_path / "sweep-log.md"

        _make_stale_uuid_dir(repo_dir, self.TEST_UUID, age_days=15)

        result = run([
            "--class", "harness",
            "--dry-run",
            "--days", "14",
            "--projects-root", bp(projects),
            "--file-history-root", bp(fh),
            "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
            "--log-path", bp(log_path),
        ])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Banner goes to stderr; grand total goes to stdout
        combined = result.stdout + result.stderr
        assert "harness" in combined.lower(), (
            f"Expected 'harness' in output; got stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert not log_path.exists(), "log file must not be written in dry-run mode"

    def test_fresh_dirs_not_reported(self, tmp_path):
        """Directories younger than N days are not reported as auto-prune."""
        projects = tmp_path / "projects"
        repo_dir = projects / "myrepo"
        repo_dir.mkdir(parents=True)
        fh = tmp_path / "fh"
        fh.mkdir()
        log_path = tmp_path / "sweep-log.md"

        # Create a fresh dir (1 day old, threshold 14d)
        fresh_uuid = "b2c3d4e5-f6a7-8901-bcde-f12345678901"
        d = repo_dir / fresh_uuid
        d.mkdir()
        (d / "data.txt").write_text("fresh session")
        fresh_mtime = time.time() - 1 * 86400
        os.utime(d, (fresh_mtime, fresh_mtime))

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
        # With --json --dry-run, stdout should have no auto-prune record for fresh_uuid
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            assert fresh_uuid not in rec.get("name", ""), (
                f"Fresh UUID should not appear in JSONL output; got: {rec}"
            )


# ---------------------------------------------------------------------------
# AC2: predecessor UUID skip
# ---------------------------------------------------------------------------

class TestPredecessorUuidSkipped:
    """Verify predecessor UUIDs are skipped even on --apply (AC2)."""

    TEST_UUID = "dead1234-dead-dead-dead-deaddeaddead"

    def test_predecessor_uuid_skipped(self, tmp_path):
        """UUID referenced in a handoff predecessor: line is NOT deleted on --apply."""
        projects = tmp_path / "projects"
        repo_dir = projects / "myrepo"
        repo_dir.mkdir(parents=True)
        fh = tmp_path / "fh"
        fh.mkdir()
        log_path = tmp_path / "sweep-log.md"

        uuid_dir = _make_stale_uuid_dir(repo_dir, self.TEST_UUID, age_days=20)

        handoffs_dir = tmp_path / "handoffs"
        handoffs_dir.mkdir()
        (handoffs_dir / "foo.md").write_text(
            f"---\npredecessor: {self.TEST_UUID}\nstatus: active\n---\n"
        )

        result = run([
            "--class", "harness",
            "--apply",
            "--days", "14",
            "--projects-root", bp(projects),
            "--file-history-root", bp(fh),
            "--handoffs-glob", bp(handoffs_dir) + "/*.md",
            "--log-path", bp(log_path),
        ])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        assert uuid_dir.exists(), (
            f"UUID dir {uuid_dir} must NOT be deleted when UUID is referenced "
            f"as predecessor in an active handoff"
        )

    def test_non_predecessor_uuid_deleted_on_apply(self, tmp_path):
        """UUID NOT referenced in any handoff IS deleted on --apply."""
        projects = tmp_path / "projects"
        repo_dir = projects / "myrepo"
        repo_dir.mkdir(parents=True)
        fh = tmp_path / "fh"
        fh.mkdir()
        log_path = tmp_path / "sweep-log.md"

        stale_uuid = "cafebabe-cafe-cafe-cafe-cafebabecafe"
        uuid_dir = _make_stale_uuid_dir(repo_dir, stale_uuid, age_days=20)

        handoffs_dir = tmp_path / "handoffs"
        handoffs_dir.mkdir()
        (handoffs_dir / "other.md").write_text(
            "---\npredecessor: 00000000-0000-0000-0000-000000000000\n---\n"
        )

        result = run([
            "--class", "harness",
            "--apply",
            "--days", "14",
            "--projects-root", bp(projects),
            "--file-history-root", bp(fh),
            "--handoffs-glob", bp(handoffs_dir) + "/*.md",
            "--log-path", bp(log_path),
        ])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        assert not uuid_dir.exists(), (
            f"UUID dir {uuid_dir} should have been deleted (not in any handoff)"
        )
