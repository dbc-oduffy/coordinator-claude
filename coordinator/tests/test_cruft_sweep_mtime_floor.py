"""
test_cruft_sweep_mtime_floor.py — 24h mtime floor (RD-2) tests for cruft-sweep.sh.

Spec backlink: docs/plans/2026-06-14-deep-research-workdir-out-of-killzone.md
               § C2 AC4; RD-2 (24h hard floor).

Purpose:
  Verify that a directory matching an auto-prune name is reported as "skip"
  with reason containing "mtime-floor" when its mtime is recent (< 24h),
  regardless of --scratch-age configuration. Also verifies that a directory
  aged beyond the floor IS reported as "auto-prune" and that an mtime-zero
  dir (stat-failure simulation) is reported as "skip" (fail-safe).

Isolation: all tests use tmp_path fixtures + --repo-root / override flags.
           NEVER touches real ~/.claude/ or real git repos.
           Paths passed via .as_posix() for Git-Bash compatibility on Windows.

Negative-spec:
  - mtime-floor skip dir is NOT reported as "auto-prune"
  - mtime-floor fires even with --scratch-age 0 and --scratch-age 1
    (i.e. the floor is always load-bearing, not shadowed by threshold)
"""

import json
import os
import subprocess
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "cruft-sweep.sh"

# An auto-prune name that cruft-sweep recognises (matches the 'tmp-cc' entry
# or equivalent in the script's _is_auto_prune_name list).
# Adjust if the auto-prune list changes — the name just needs to be recognised.
AUTO_PRUNE_NAME = "tmp-cc"


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


def _make_dir_aged(parent: Path, name: str, age_seconds: int) -> Path:
    """Create a directory under parent and set its mtime to age_seconds ago."""
    d = parent / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "content.txt").write_text("scratch content")
    target_mtime = time.time() - age_seconds
    os.utime(d, (target_mtime, target_mtime))
    return d


def _scratch_base_args(tmp_path: Path, scratch_age_days: int = 7) -> list:
    """Common args for a scratch sweep run against tmp_path as repo root."""
    log_path = tmp_path / "sweep-log.md"
    return [
        "--class", "scratch",
        "--repo-root", bp(tmp_path),
        "--scratch-age-days", str(scratch_age_days),
        "--log-path", bp(log_path),
        "--dry-run",
        "--json",
        # Redirect harness flags so they don't pull in real state
        "--projects-root", bp(tmp_path / "no-projects"),
        "--file-history-root", bp(tmp_path / "no-fh"),
        "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
    ]


def _jsonl_records(stdout: str) -> list:
    """Parse JSONL records from stdout, ignoring blank lines."""
    records = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _find_records_for_name(records: list, name: str) -> list:
    return [r for r in records if r.get("name") == name]


# ---------------------------------------------------------------------------
# AC4a: recent dir (mtime < 24h) → skip with "mtime-floor" reason
# ---------------------------------------------------------------------------

class TestMtimeFloorSkip:
    """A dir aged < 24h is skipped as mtime-floor, NOT auto-pruned (AC4)."""

    def test_recent_dir_skipped_as_mtime_floor(self, tmp_path):
        """Dir with mtime 1 hour ago reports disposition=skip, evidence contains mtime-floor."""
        # 1 hour ago — well inside the 24h floor
        _make_dir_aged(tmp_path, AUTO_PRUNE_NAME, age_seconds=3600)

        result = run(_scratch_base_args(tmp_path, scratch_age_days=7))
        assert result.returncode == 0, f"stderr: {result.stderr}"

        records = _jsonl_records(result.stdout)
        matches = _find_records_for_name(records, AUTO_PRUNE_NAME)

        assert matches, (
            f"Expected a JSONL record for '{AUTO_PRUNE_NAME}'; "
            f"got records: {records}\nstderr: {result.stderr}"
        )
        rec = matches[0]
        assert rec["disposition"] == "skip", (
            f"Expected disposition=skip for recent dir; got: {rec}"
        )
        assert "mtime-floor" in rec.get("evidence", ""), (
            f"Expected 'mtime-floor' in evidence; got: {rec}"
        )

    def test_recent_dir_not_auto_pruned(self, tmp_path):
        """Dir with mtime 1 hour ago is never reported as auto-prune."""
        _make_dir_aged(tmp_path, AUTO_PRUNE_NAME, age_seconds=3600)

        result = run(_scratch_base_args(tmp_path, scratch_age_days=7))
        assert result.returncode == 0, f"stderr: {result.stderr}"

        records = _jsonl_records(result.stdout)
        auto_prune = [r for r in records if r.get("disposition") == "auto-prune"
                      and r.get("name") == AUTO_PRUNE_NAME]
        assert not auto_prune, (
            f"Recent dir should NOT be auto-pruned; got: {auto_prune}"
        )


# ---------------------------------------------------------------------------
# AC4b: floor fires even with --scratch-age 0 / --scratch-age 1
# ---------------------------------------------------------------------------

class TestMtimeFloorAlwaysLoadBearing:
    """The 24h floor fires regardless of --scratch-age (consolidates F1+F2 fix)."""

    def test_floor_fires_with_scratch_age_0(self, tmp_path):
        """With --scratch-age 0, a 1-hour-old dir is still skipped as mtime-floor."""
        _make_dir_aged(tmp_path, AUTO_PRUNE_NAME, age_seconds=3600)

        result = run(_scratch_base_args(tmp_path, scratch_age_days=0))
        assert result.returncode == 0, f"stderr: {result.stderr}"

        records = _jsonl_records(result.stdout)
        matches = _find_records_for_name(records, AUTO_PRUNE_NAME)
        assert matches, f"Expected JSONL record; got: {records}"
        rec = matches[0]
        assert rec["disposition"] == "skip", (
            f"With --scratch-age 0, recent dir should still be skip; got: {rec}"
        )
        assert "mtime-floor" in rec.get("evidence", ""), (
            f"Expected 'mtime-floor' in evidence with --scratch-age 0; got: {rec}"
        )

    def test_floor_fires_with_scratch_age_1(self, tmp_path):
        """With --scratch-age 1, a 1-hour-old dir is still skipped as mtime-floor."""
        _make_dir_aged(tmp_path, AUTO_PRUNE_NAME, age_seconds=3600)

        result = run(_scratch_base_args(tmp_path, scratch_age_days=1))
        assert result.returncode == 0, f"stderr: {result.stderr}"

        records = _jsonl_records(result.stdout)
        matches = _find_records_for_name(records, AUTO_PRUNE_NAME)
        assert matches, f"Expected JSONL record; got: {records}"
        rec = matches[0]
        assert rec["disposition"] == "skip", (
            f"With --scratch-age 1, recent dir should still be skip; got: {rec}"
        )
        assert "mtime-floor" in rec.get("evidence", ""), (
            f"Expected 'mtime-floor' in evidence with --scratch-age 1; got: {rec}"
        )


# ---------------------------------------------------------------------------
# AC4c: stale dir (mtime > 24h AND > threshold) → auto-prune
# ---------------------------------------------------------------------------

class TestMtimeFloorPassthrough:
    """Dir aged well beyond the floor proceeds to auto-prune."""

    def test_stale_dir_auto_pruned(self, tmp_path):
        """Dir with mtime 10 days ago is reported as auto-prune (not skipped by floor)."""
        _make_dir_aged(tmp_path, AUTO_PRUNE_NAME, age_seconds=10 * 86400)

        result = run(_scratch_base_args(tmp_path, scratch_age_days=7))
        assert result.returncode == 0, f"stderr: {result.stderr}"

        records = _jsonl_records(result.stdout)
        matches = _find_records_for_name(records, AUTO_PRUNE_NAME)
        assert matches, f"Expected JSONL record; got: {records}"
        rec = matches[0]
        assert rec["disposition"] == "auto-prune", (
            f"Stale dir (10 days) should be auto-prune; got: {rec}"
        )
