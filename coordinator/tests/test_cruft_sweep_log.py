"""
test_cruft_sweep_log.py — sweep log append behavior tests for cruft-sweep.sh.

Spec backlink: docs/plans/2026-06-09-distill-cruft-sweep.md § C1 (AC5)
Purpose: Verify that the sweep log is appended to on --apply and never
         written on --dry-run.

Isolation: all tests use tmp_path fixtures + override flags.
           NEVER touches real ~/.claude/state/cruft-sweep-log.md.
           Paths passed via .as_posix() for Git-Bash compatibility on Windows.
"""

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
    """Convert Path to bash-navigable string (Git-Bash C:/... compatible)."""
    return p.as_posix()


def _make_stale_uuid_dir(parent: Path, uuid: str, age_days: int = 20) -> Path:
    """Create a stale uuid directory with dummy content."""
    d = parent / uuid
    d.mkdir(parents=True, exist_ok=True)
    (d / "session.txt").write_text("old session state")
    old_mtime = time.time() - age_days * 86400
    os.utime(d, (old_mtime, old_mtime))
    return d


# ---------------------------------------------------------------------------
# AC5: log behavior
# ---------------------------------------------------------------------------

class TestLogAppendApplyOnly:
    """Verify log append semantics: apply writes, dry-run never writes (AC5)."""

    UUID_A = "11111111-1111-1111-1111-111111111111"
    UUID_B = "22222222-2222-2222-2222-222222222222"

    def _setup(self, tmp_path):
        projects = tmp_path / "projects"
        repo_dir = projects / "repo"
        repo_dir.mkdir(parents=True)
        fh = tmp_path / "fh"
        fh.mkdir()
        return projects, fh

    def test_dry_run_never_writes_log(self, tmp_path):
        """--dry-run must NOT write to log-path, even when items are found."""
        log_path = tmp_path / "sweep-log.md"
        projects, fh = self._setup(tmp_path)
        repo_dir = projects / "repo"

        _make_stale_uuid_dir(repo_dir, self.UUID_A)

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
        assert not log_path.exists(), (
            "log-path must NOT be created/written under --dry-run"
        )

    def test_apply_appends_log_line(self, tmp_path):
        """--apply appends one line per non-empty class to log-path."""
        log_path = tmp_path / "sweep-log.md"
        projects, fh = self._setup(tmp_path)
        repo_dir = projects / "repo"

        _make_stale_uuid_dir(repo_dir, self.UUID_B)

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

        assert log_path.exists(), (
            "log-path must be created on --apply when items are pruned"
        )
        log_content = log_path.read_text()
        assert "harness" in log_content, (
            f"Expected 'harness' in log; got: {log_content!r}"
        )
        # Should contain a timestamp-like pattern (ISO 8601 T separator)
        assert "T" in log_content, (
            f"Expected ISO timestamp in log; got: {log_content!r}"
        )

    def test_apply_no_items_no_log(self, tmp_path):
        """--apply with no stale items does NOT write a log line."""
        log_path = tmp_path / "sweep-log.md"
        projects, fh = self._setup(tmp_path)
        repo_dir = projects / "repo"

        # Only create a fresh (1-day-old) dir — should not be pruned
        fresh_uuid = "33333333-3333-3333-3333-333333333333"
        d = repo_dir / fresh_uuid
        d.mkdir(parents=True)
        (d / "data.txt").write_text("fresh")
        fresh_mtime = time.time() - 1 * 86400
        os.utime(d, (fresh_mtime, fresh_mtime))

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
        # Review: code-reviewer — permissive if-guard allowed a spurious log write to pass silently;
        # unconditional assert ensures a log file is never created when no items are pruned.
        assert not log_path.exists(), "log must not be written when no items are pruned"

    def test_multiple_apply_runs_append(self, tmp_path):
        """Multiple --apply runs append separate lines (not overwrite)."""
        log_path = tmp_path / "sweep-log.md"

        for i, uuid in enumerate([
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        ]):
            projects = tmp_path / f"projects_{i}"
            repo_dir = projects / "repo"
            repo_dir.mkdir(parents=True)
            fh = tmp_path / f"fh_{i}"
            fh.mkdir()
            _make_stale_uuid_dir(repo_dir, uuid)

            result = run([
                "--class", "harness",
                "--apply",
                "--days", "14",
                "--projects-root", bp(projects),
                "--file-history-root", bp(fh),
                "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
                "--log-path", bp(log_path),
            ])
            assert result.returncode == 0, f"run {i} stderr: {result.stderr}"

        log_content = log_path.read_text()
        lines = [l for l in log_content.splitlines() if "harness" in l]
        assert len(lines) >= 2, (
            f"Expected at least 2 harness log lines from 2 apply runs; "
            f"got {len(lines)}: {log_content!r}"
        )
