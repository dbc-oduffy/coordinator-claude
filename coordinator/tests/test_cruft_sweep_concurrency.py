"""
test_cruft_sweep_concurrency.py — concurrency lock tests for cruft-sweep.sh.

Spec backlink: docs/plans/2026-06-09-distill-cruft-sweep.md § C1 (AC5a)
Purpose: Verify that when the lock dir is already held, a concurrent
         cruft-sweep invocation exits 0 silently, performs NO deletions,
         and writes NO log line.

Isolation: all tests use tmp_path fixtures and override HOME so the lock dir
           resolves inside tmp_path (not the real ~/.claude/state/).
           Paths passed via .as_posix() for Git-Bash compatibility on Windows.
           NEVER touches real ~/.claude/ state.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "cruft-sweep.sh"


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
# AC5a: lock contention
# ---------------------------------------------------------------------------

class TestLockContentionNoDoubleCount:
    """Lock contention: contended run exits 0, deletes nothing, logs nothing (AC5a)."""

    STALE_UUID = "cccccccc-cccc-cccc-cccc-cccccccccccc"

    def test_lock_contention_no_double_count(self, tmp_path):
        """Manually hold the lock dir; assert the contended run exits 0 with no side effects.

        The script derives LOCK_DIR from HOME: ${HOME}/.claude/state/cruft-sweep.lock.d
        We override HOME to point at tmp_path so the lock dir resolves there.
        """
        # Review: code-reviewer — lock_dir not cleaned up on assertion failure;
        # wrap in try/finally so the directory is removed even if an assertion fires.
        projects = tmp_path / "projects"
        repo_dir = projects / "repo"
        repo_dir.mkdir(parents=True)
        fh = tmp_path / "fh"
        fh.mkdir()
        log_path = tmp_path / ".claude" / "state" / "sweep-log.md"

        # Create stale content that would normally be pruned
        uuid_dir = _make_stale_uuid_dir(repo_dir, self.STALE_UUID)

        # Set up the fake HOME structure with the lock dir pre-held
        state_dir = tmp_path / ".claude" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        lock_dir = state_dir / "cruft-sweep.lock.d"
        lock_dir.mkdir()

        try:
            # Run the script with HOME overridden so LOCK_DIR → tmp_path/.claude/state/cruft-sweep.lock.d
            env = {**os.environ, "HOME": bp(tmp_path)}
            result = subprocess.run(
                ["bash", str(SCRIPT),
                 "--class", "harness",
                 "--apply",
                 "--days", "14",
                 "--projects-root", bp(projects),
                 "--file-history-root", bp(fh),
                 "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
                 "--log-path", bp(log_path),
                 ],
                capture_output=True,
                text=True,
                env=env,
            )

            # Exit 0 silently on contention
            assert result.returncode == 0, (
                f"Expected exit 0 on lock contention, got {result.returncode}; "
                f"stderr: {result.stderr}"
            )

            # No deletions: the UUID dir must still exist
            assert uuid_dir.exists(), (
                f"UUID dir {uuid_dir} must NOT be deleted when lock is contended"
            )

            # No log line appended
            assert not log_path.exists(), (
                "log-path must NOT be written when run is lock-contended"
            )

            # Lock dir must still be held (we pre-created it; the contended run must not remove it)
            assert lock_dir.exists(), (
                "lock dir must still exist after contended run exits (we hold it)"
            )
        finally:
            # Ensure the lock dir is cleaned up even if assertions fire above
            shutil.rmtree(lock_dir, ignore_errors=True)

    def test_lock_released_after_successful_run(self, tmp_path):
        """The lock dir is removed after a successful run (no orphaned lock)."""
        projects = tmp_path / "projects"
        fh = tmp_path / "fh"
        projects.mkdir(parents=True)
        fh.mkdir()
        log_path = tmp_path / ".claude" / "state" / "sweep-log.md"
        state_dir = tmp_path / ".claude" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)

        lock_dir = state_dir / "cruft-sweep.lock.d"

        env = {**os.environ, "HOME": bp(tmp_path)}
        result = subprocess.run(
            ["bash", str(SCRIPT),
             "--class", "harness",
             "--dry-run",
             "--days", "14",
             "--projects-root", bp(projects),
             "--file-history-root", bp(fh),
             "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
             "--log-path", bp(log_path),
             ],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Lock dir must be cleaned up by trap on EXIT
        assert not lock_dir.exists(), (
            f"Lock dir {lock_dir} must be removed after script exits"
        )
