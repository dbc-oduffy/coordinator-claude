"""
test_cruft_sweep_phase_b.py — Phase B in-repo scratch sweep + Phase C parent-altitude
orphan sweep tests for cruft-sweep.sh.

Spec backlink: docs/plans/2026-06-09-distill-cruft-sweep.md § C2 (AC3, AC4)
Purpose: Verify name-anchored auto-prune, age gate, skip classes (backup names,
         negative-spec path components, .git boundary, recent dirs), confirm-needed
         report path (Phase B), and parent-altitude conjoint name+fingerprint gate
         with hard-exclude list (Phase C).

Isolation: all tests use tmp_path fixtures + --repo-root / --parent-root overrides.
           NEVER touches real ~/.claude/ or real git repos or real X:/ / E:/dev/.

Negative-spec: tests do not touch --class harness paths.
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


def _age_dir(d: Path, age_days: int) -> None:
    """Set mtime of directory d to age_days ago."""
    old_mtime = time.time() - age_days * 86400
    os.utime(d, (old_mtime, old_mtime))


def _make_old_dir(parent: Path, name: str, age_days: int = 10) -> Path:
    """Create a directory with a file inside and age it by age_days."""
    d = parent / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "file.txt").write_text("content")
    _age_dir(d, age_days)
    return d


def _scratch_base_args(tmp_path: Path) -> list:
    """Common args for a scratch sweep run against tmp_path as repo root."""
    log_path = tmp_path / "sweep-log.md"
    return [
        "--class", "scratch",
        "--repo-root", bp(tmp_path),
        "--scratch-age-days", "7",
        "--log-path", bp(log_path),
        # Point harness flags at non-existent dirs so they don't interfere
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


# ---------------------------------------------------------------------------
# AC3: auto-prune — name-anchored explicit cruft list
# ---------------------------------------------------------------------------

class TestAutoPruneNames:

    def test_auto_prune_nonexistent_dir(self, tmp_path):
        """'nonexistent/' aged >7d is auto-pruned on --apply; log line written."""
        d = _make_old_dir(tmp_path, "nonexistent", age_days=10)
        log_path = tmp_path / "sweep-log.md"

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not d.exists(), (
            f"'nonexistent/' should have been deleted; stderr: {result.stderr}"
        )
        assert log_path.exists(), "log file should be written after --apply prune"
        log_content = log_path.read_text()
        assert "scratch" in log_content, f"log should contain 'scratch'; got: {log_content}"

    def test_auto_prune_single_char_dir(self, tmp_path):
        """Single-char [a-z] dir aged >7d is auto-pruned on --apply."""
        d = _make_old_dir(tmp_path, "z", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not d.exists(), (
            f"single-char dir 'z/' should have been deleted; stderr: {result.stderr}"
        )

    def test_auto_prune_tmp_cc_dir(self, tmp_path):
        """'tmp-cc/' aged >7d is auto-pruned on --apply."""
        d = _make_old_dir(tmp_path, "tmp-cc", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not d.exists(), (
            f"'tmp-cc/' should have been deleted; stderr: {result.stderr}"
        )

    def test_auto_prune_fake_dir(self, tmp_path):
        """'fake/' aged >7d is auto-pruned on --apply."""
        d = _make_old_dir(tmp_path, "fake", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not d.exists(), (
            f"'fake/' should have been deleted; stderr: {result.stderr}"
        )

    def test_scratch_age_days_non_default(self, tmp_path):
        """--scratch-age-days 3 prunes a 4-day-old 'nonexistent/' dir.

        Review: code-reviewer — non-default value for --scratch-age-days was untested;
        the default is 7d so only passing 3d with a 4d-old dir exercises the flag path.
        """
        # Create a 4-day-old dir (older than 3d threshold, younger than default 7d)
        d = _make_old_dir(tmp_path, "nonexistent", age_days=4)
        log_path = tmp_path / "sweep-log.md"

        # Override age threshold to 3 days so the 4d dir should be pruned
        result = run([
            "--class", "scratch",
            "--repo-root", bp(tmp_path),
            "--scratch-age-days", "3",
            "--log-path", bp(log_path),
            "--projects-root", bp(tmp_path / "no-projects"),
            "--file-history-root", bp(tmp_path / "no-fh"),
            "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
            "--apply",
        ])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not d.exists(), (
            f"'nonexistent/' aged 4d should be deleted with --scratch-age-days 3; "
            f"stderr: {result.stderr}"
        )

    def test_auto_prune_chained_single_char_dir(self, tmp_path):
        """Chained identical single-char dirs (z/z/z/) are auto-pruned as top-level [a-z]."""
        # Create z/z/z/ chain
        inner = tmp_path / "z" / "z" / "z"
        inner.mkdir(parents=True, exist_ok=True)
        (inner / "file.txt").write_text("data")
        # Age the top-level z/
        _age_dir(tmp_path / "z", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not (tmp_path / "z").exists(), (
            f"chained 'z/z/z/' should have been deleted via top-level 'z/'; "
            f"stderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# AC3: skip — recent dirs
# ---------------------------------------------------------------------------

class TestSkipRecentDirs:

    def test_skip_recent_dir(self, tmp_path):
        """'nonexistent/' with mtime < 7d is NOT auto-pruned."""
        d = _make_old_dir(tmp_path, "nonexistent", age_days=2)  # 2d < 7d threshold

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert d.exists(), (
            f"'nonexistent/' with mtime 2d should NOT be deleted (threshold 7d); "
            f"stderr: {result.stderr}"
        )

    def test_skip_recent_single_char_dir(self, tmp_path):
        """Single-char dir with mtime 1d is NOT auto-pruned."""
        d = _make_old_dir(tmp_path, "a", age_days=1)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert d.exists(), (
            f"'a/' with mtime 1d should NOT be deleted; stderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# AC3: skip — legitimate-backup name classes
# ---------------------------------------------------------------------------

class TestSkipBackupNames:

    def test_skip_underscore_prefix(self, tmp_path):
        """Dirs with underscore-prefix are treated as legitimate backups — never deleted."""
        d = _make_old_dir(tmp_path, "_pre-refresh-snapshots", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert d.exists(), (
            f"'_pre-refresh-snapshots/' must NOT be deleted (underscore-prefix backup class); "
            f"stderr: {result.stderr}"
        )

    def test_skip_bak_suffix(self, tmp_path):
        """Dirs matching *.bak* or *-bak-* are never deleted."""
        d_bak = _make_old_dir(tmp_path, "foo.bak", age_days=10)
        d_bak_old = _make_old_dir(tmp_path, "foo-bak-old", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert d_bak.exists(), (
            f"'foo.bak/' must NOT be deleted (*.bak* backup class); "
            f"stderr: {result.stderr}"
        )
        assert d_bak_old.exists(), (
            f"'foo-bak-old/' must NOT be deleted (*-bak-* backup class); "
            f"stderr: {result.stderr}"
        )

    def test_skip_preisource_bak(self, tmp_path):
        """Dirs matching *.preisource-bak-* are never deleted."""
        d = _make_old_dir(tmp_path, "foo.preisource-bak-20260601", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert d.exists(), (
            f"'foo.preisource-bak-20260601/' must NOT be deleted; "
            f"stderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# AC3: skip — negative-spec path components
# ---------------------------------------------------------------------------

class TestSkipNegativeSpecComponents:

    def test_skip_negative_spec_components(self, tmp_path):
        """Dirs under a negative-spec component (tasks, archive, etc.) are not deleted."""
        # Create tasks/nonexistent/ — 'nonexistent' is an auto-prune name but
        # 'tasks' in the path is a negative-spec component — so must be skipped.
        d = _make_old_dir(tmp_path / "tasks", "nonexistent", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert d.exists(), (
            f"'tasks/nonexistent/' must NOT be deleted (tasks is negative-spec component); "
            f"stderr: {result.stderr}"
        )

    def test_skip_negative_spec_jsonl_disposition(self, tmp_path):
        """JSONL records for negative-spec-skipped dirs have disposition='skip'.

        Review: code-reviewer — skip disposition in JSONL output was untested for Phase B;
        a negative-spec-skipped dir must emit disposition='skip', not 'auto-prune' or
        'confirm-needed', when --dry-run --json is used.
        """
        _make_old_dir(tmp_path / "tasks", "nonexistent", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--dry-run", "--json"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        records = _jsonl_records(result.stdout)
        # Filter for any record whose path contains 'tasks'
        skip_records = [
            r for r in records
            if "tasks" in r.get("path", "") and r.get("name") == "nonexistent"
        ]
        if skip_records:
            for rec in skip_records:
                assert rec.get("disposition") == "skip", (
                    f"Expected disposition='skip' for tasks/nonexistent; got: {rec}"
                )

    def test_skip_under_state(self, tmp_path):
        """Dirs under state/ are protected by negative-spec."""
        d = _make_old_dir(tmp_path / "state", "fake", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert d.exists(), (
            f"'state/fake/' must NOT be deleted (state is negative-spec component); "
            f"stderr: {result.stderr}"
        )

    def test_skip_under_docs(self, tmp_path):
        """Dirs under docs/ are protected by negative-spec."""
        d = _make_old_dir(tmp_path / "docs", "nonexistent", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert d.exists(), (
            f"'docs/nonexistent/' must NOT be deleted (docs is negative-spec component); "
            f"stderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# AC3: skip — .git boundary
# ---------------------------------------------------------------------------

class TestSkipInsideGitBoundary:

    def test_skip_inside_git_boundary(self, tmp_path):
        """Paths with a literal .git parent component are never deleted."""
        # Create .git/nonexistent/ — the literal '.git' component triggers the guard
        git_dir = tmp_path / ".git"
        git_dir.mkdir(exist_ok=True)
        d = _make_old_dir(git_dir, "nonexistent", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert d.exists(), (
            f"'.git/nonexistent/' must NOT be deleted (.git boundary guard); "
            f"stderr: {result.stderr}"
        )

    def test_skip_inside_real_git_repo(self, tmp_path):
        """Cruft-name dir inside an actual git-init'd repo under .git/ is not deleted.

        Review: code-reviewer (F11) — the literal-.git dir test passes because the
        path-component filter sees '.git'; this variant uses git init to confirm the
        guard also fires against the real .git directory structure created by git.
        """
        import subprocess as _sp
        init_result = _sp.run(
            ["git", "init", bp(tmp_path)],
            capture_output=True, text=True,
        )
        if init_result.returncode != 0:
            # git not available or init failed — skip gracefully
            import pytest
            pytest.skip(f"git init failed: {init_result.stderr}")

        # Place a cruft-named dir inside the real .git/ directory
        git_dir = tmp_path / ".git"
        d = _make_old_dir(git_dir, "nonexistent", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert d.exists(), (
            f"'.git/nonexistent/' inside real git repo must NOT be deleted; "
            f"stderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# AC3: confirm-needed — tmp, scratch, output
# ---------------------------------------------------------------------------

class TestConfirmNeeded:

    def test_confirm_needed_tmp_reports_not_prune(self, tmp_path):
        """'tmp/' with old mtime: NOT deleted on --apply; JSONL has confirm-needed record."""
        d = _make_old_dir(tmp_path, "tmp", age_days=10)

        # --apply: must NOT delete
        result_apply = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result_apply.returncode == 0, f"stderr: {result_apply.stderr}"
        assert d.exists(), (
            f"'tmp/' must NOT be deleted (confirm-needed, not auto-prune); "
            f"stderr: {result_apply.stderr}"
        )

        # --dry-run --json: must emit confirm-needed record
        result_json = run(_scratch_base_args(tmp_path) + ["--dry-run", "--json"])
        assert result_json.returncode == 0, f"stderr: {result_json.stderr}"
        records = _jsonl_records(result_json.stdout)
        confirm_records = [r for r in records if r.get("disposition") == "confirm-needed" and r.get("name") == "tmp"]
        assert confirm_records, (
            f"Expected a confirm-needed JSONL record for 'tmp'; "
            f"got records: {records!r}"
        )
        # Confirm evidence field is non-empty
        for rec in confirm_records:
            assert rec.get("evidence"), f"evidence field must be non-empty; got: {rec}"

    def test_confirm_needed_scratch_reports_not_prune(self, tmp_path):
        """'scratch/' with old mtime: NOT deleted; JSONL has confirm-needed record."""
        d = _make_old_dir(tmp_path, "scratch", age_days=10)

        result_apply = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result_apply.returncode == 0, f"stderr: {result_apply.stderr}"
        assert d.exists(), f"'scratch/' must NOT be deleted; stderr: {result_apply.stderr}"

        result_json = run(_scratch_base_args(tmp_path) + ["--dry-run", "--json"])
        records = _jsonl_records(result_json.stdout)
        confirm_records = [r for r in records if r.get("disposition") == "confirm-needed" and r.get("name") == "scratch"]
        assert confirm_records, (
            f"Expected confirm-needed JSONL for 'scratch'; got: {records!r}"
        )

    def test_confirm_needed_output_reports_not_prune(self, tmp_path):
        """'output/' with old mtime: NOT deleted; JSONL has confirm-needed record."""
        d = _make_old_dir(tmp_path, "output", age_days=10)

        result_apply = run(_scratch_base_args(tmp_path) + ["--apply"])
        assert result_apply.returncode == 0, f"stderr: {result_apply.stderr}"
        assert d.exists(), f"'output/' must NOT be deleted; stderr: {result_apply.stderr}"

        result_json = run(_scratch_base_args(tmp_path) + ["--dry-run", "--json"])
        records = _jsonl_records(result_json.stdout)
        confirm_records = [r for r in records if r.get("disposition") == "confirm-needed" and r.get("name") == "output"]
        assert confirm_records, (
            f"Expected confirm-needed JSONL for 'output'; got: {records!r}"
        )


# ---------------------------------------------------------------------------
# AC3: JSONL wire contract — class field
# ---------------------------------------------------------------------------

class TestJsonlWireContract:

    def test_jsonl_class_is_scratch(self, tmp_path):
        """--dry-run --json --class scratch: every emitted record has class == 'scratch'."""
        # Populate several fixture dirs
        _make_old_dir(tmp_path, "nonexistent", age_days=10)
        _make_old_dir(tmp_path, "fake", age_days=10)
        _make_old_dir(tmp_path, "tmp", age_days=10)   # confirm-needed
        _make_old_dir(tmp_path, "z", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--dry-run", "--json"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        records = _jsonl_records(result.stdout)
        assert records, "Expected at least one JSONL record"
        for rec in records:
            assert rec.get("class") == "scratch", (
                f"All JSONL records must have class=='scratch'; got: {rec}"
            )

    def test_jsonl_schema_fields_present(self, tmp_path):
        """JSONL records contain all required schema fields."""
        _make_old_dir(tmp_path, "nonexistent", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--dry-run", "--json"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        records = _jsonl_records(result.stdout)
        assert records, "Expected at least one JSONL record"
        required_fields = {"class", "path", "name", "size_bytes", "mtime", "disposition", "evidence"}
        for rec in records:
            missing = required_fields - set(rec.keys())
            assert not missing, f"JSONL record missing fields {missing}; got: {rec}"

    def test_auto_prune_disposition_in_dry_run(self, tmp_path):
        """Auto-prune candidates emit disposition='auto-prune' in --dry-run --json."""
        _make_old_dir(tmp_path, "nonexistent", age_days=10)

        result = run(_scratch_base_args(tmp_path) + ["--dry-run", "--json"])
        assert result.returncode == 0, f"stderr: {result.stderr}"

        records = _jsonl_records(result.stdout)
        auto_prune_records = [r for r in records if r.get("name") == "nonexistent"]
        assert auto_prune_records, f"Expected auto-prune record for 'nonexistent'; got: {records!r}"
        for rec in auto_prune_records:
            assert rec["disposition"] == "auto-prune", (
                f"Expected disposition='auto-prune'; got: {rec}"
            )


# ---------------------------------------------------------------------------
# Regression: Phase A tests must still pass (smoke check — just invoke --class harness)
# ---------------------------------------------------------------------------

class TestPhaseARegression:

    def test_phase_a_still_runs(self, tmp_path):
        """--class harness still exits 0 (Phase B did not break Phase A dispatch)."""
        projects = tmp_path / "projects"
        projects.mkdir()
        fh = tmp_path / "fh"
        fh.mkdir()
        log_path = tmp_path / "sweep-log.md"

        result = run([
            "--class", "harness",
            "--dry-run",
            "--projects-root", bp(projects),
            "--file-history-root", bp(fh),
            "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
            "--log-path", bp(log_path),
        ])
        assert result.returncode == 0, f"Phase A regression: stderr={result.stderr}"


# ---------------------------------------------------------------------------
# Phase C (orphans) helper and test fixtures
# ---------------------------------------------------------------------------

def _orphans_base_args(parent_root: Path, tmp_path: Path) -> list:
    """Common args for an orphans sweep run with --parent-root override."""
    log_path = tmp_path / "orphans-log.md"
    return [
        "--class", "orphans",
        "--parent-root", bp(parent_root),
        "--log-path", bp(log_path),
        # Point harness/scratch flags at non-existent dirs so they don't interfere
        "--projects-root", bp(tmp_path / "no-projects"),
        "--file-history-root", bp(tmp_path / "no-fh"),
        "--handoffs-glob", bp(tmp_path / "no-handoffs") + "/*.md",
        "--repo-root", bp(tmp_path),
    ]


def _make_chroma_fingerprint(child: Path) -> None:
    """Create the vector/store/chroma.sqlite3 sonnet fingerprint inside child."""
    fp = child / "vector" / "store" / "chroma.sqlite3"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("chroma-db")


# ---------------------------------------------------------------------------
# AC4: Phase C — conjoint name+fingerprint gate
# ---------------------------------------------------------------------------

class TestOrphansAutoprune:

    def test_orphans_auto_prune_name_and_fingerprint(self, tmp_path):
        """nonexistent/ with chroma fingerprint: auto-pruned on --apply; log written."""
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "nonexistent"
        child.mkdir()
        _make_chroma_fingerprint(child)
        log_path = tmp_path / "orphans-log.md"

        result = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not child.exists(), (
            f"'nonexistent/' with chroma fingerprint should be deleted; stderr: {result.stderr}"
        )
        assert log_path.exists(), "log file should be written after --apply prune"
        log_content = log_path.read_text()
        assert "orphans" in log_content, f"log should contain 'orphans'; got: {log_content}"

    def test_orphans_name_only_skip(self, tmp_path):
        """nonexistent/ with no sonnet fingerprint: NOT pruned; JSONL has skip record."""
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "nonexistent"
        child.mkdir()
        (child / "some-real-file.txt").write_text("important content")

        result_apply = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result_apply.returncode == 0, f"stderr: {result_apply.stderr}"
        assert child.exists(), (
            f"'nonexistent/' without fingerprint must NOT be deleted; stderr: {result_apply.stderr}"
        )

        result_json = run(_orphans_base_args(parent, tmp_path) + ["--dry-run", "--json"])
        assert result_json.returncode == 0, f"stderr: {result_json.stderr}"
        records = _jsonl_records(result_json.stdout)
        skip_records = [
            r for r in records
            if r.get("name") == "nonexistent" and r.get("disposition") == "skip"
        ]
        assert skip_records, (
            f"Expected a skip JSONL record for 'nonexistent' (name matched, no fingerprint); "
            f"got: {records!r}"
        )

    def test_orphans_fingerprint_only_no_match(self, tmp_path):
        """Legitimate-name dir with chroma fingerprint: NOT pruned; NO JSONL record (silent)."""
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "my-real-repo"
        child.mkdir()
        _make_chroma_fingerprint(child)

        result_json = run(_orphans_base_args(parent, tmp_path) + ["--dry-run", "--json"])
        assert result_json.returncode == 0, f"stderr: {result_json.stderr}"
        records = _jsonl_records(result_json.stdout)
        assert not records, (
            f"'my-real-repo/' is not name-matched — must produce NO JSONL record (silent); "
            f"got: {records!r}"
        )

        result_apply = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result_apply.returncode == 0, f"stderr: {result_apply.stderr}"
        assert child.exists(), (
            f"'my-real-repo/' must NOT be deleted (not in cruft name list); "
            f"stderr: {result_apply.stderr}"
        )

    def test_orphans_untitled_glob_match(self, tmp_path):
        """untitled-thing/ matches untitled* glob + chroma fingerprint: auto-pruned."""
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "untitled-thing"
        child.mkdir()
        _make_chroma_fingerprint(child)

        result = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not child.exists(), (
            f"'untitled-thing/' should be deleted (untitled* glob + fingerprint); "
            f"stderr: {result.stderr}"
        )

    def test_orphans_lone_mcp_queries_fingerprint(self, tmp_path):
        """nonexistent/ with only mcp_queries.jsonl: fingerprint match; auto-pruned."""
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "nonexistent"
        child.mkdir()
        (child / "mcp_queries.jsonl").write_text('{"query":"test"}')
        # No other files — this is "lone"

        result = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not child.exists(), (
            f"'nonexistent/' with lone mcp_queries.jsonl should be deleted; "
            f"stderr: {result.stderr}"
        )

    def test_orphans_non_lone_mcp_queries_not_pruned(self, tmp_path):
        """nonexistent/ with mcp_queries.jsonl PLUS another file: NOT auto-pruned.

        Review: code-reviewer — existing test only tested the lone case; the spec
        says fingerprint matches only when mcp_queries.jsonl is the LONE file.
        """
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "nonexistent"
        child.mkdir()
        (child / "mcp_queries.jsonl").write_text('{"query":"test"}')
        (child / "important.md").write_text("# Real content that makes this non-lone")

        result = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert child.exists(), (
            f"'nonexistent/' with mcp_queries.jsonl + additional file must NOT be deleted "
            f"(not a lone-mcp_queries fingerprint); stderr: {result.stderr}"
        )

    def test_orphans_jsonl_class_is_orphans(self, tmp_path):
        """--dry-run --json --class orphans: emitted records have class == 'orphans'."""
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "nonexistent"
        child.mkdir()
        _make_chroma_fingerprint(child)

        result = run(_orphans_base_args(parent, tmp_path) + ["--dry-run", "--json"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        records = _jsonl_records(result.stdout)
        assert records, "Expected at least one JSONL record"
        for rec in records:
            assert rec.get("class") == "orphans", (
                f"All orphans JSONL records must have class=='orphans'; got: {rec}"
            )

    def test_orphans_apply_writes_log(self, tmp_path):
        """Full apply path writes log line with class=orphans."""
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "fake"
        child.mkdir()
        _make_chroma_fingerprint(child)
        log_path = tmp_path / "orphans-log.md"

        result = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert not child.exists(), f"'fake/' should be pruned; stderr: {result.stderr}"
        assert log_path.exists(), "log file should exist after --apply"
        log_content = log_path.read_text()
        assert "orphans" in log_content, f"log must mention 'orphans'; got: {log_content}"


# ---------------------------------------------------------------------------
# AC4: Phase C — hard-exclude list
# ---------------------------------------------------------------------------

class TestOrphansHardExclude:

    def test_orphans_hard_exclude_state_name(self, tmp_path):
        """Child named 'state' at parent-altitude: never swept even with fingerprint."""
        # Note: 'state' is NOT on the cruft name list, but we explicitly test the
        # hard-exclude path fires regardless of content, in case heuristics change.
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "state"
        child.mkdir()
        _make_chroma_fingerprint(child)
        # Also create a sibling 'tmp' that WOULD be swept (control)
        sibling = parent / "tmp"
        sibling.mkdir()
        _make_chroma_fingerprint(sibling)

        result = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert child.exists(), (
            f"'state/' must NOT be deleted (hard-exclude by name); stderr: {result.stderr}"
        )
        # Control: sibling 'tmp' should be pruned (name match + fingerprint)
        assert not sibling.exists(), (
            f"'tmp/' should have been pruned (control case); stderr: {result.stderr}"
        )

    def test_orphans_hard_exclude_docs_name(self, tmp_path):
        """Child named 'docs' at parent-altitude: never swept even with fingerprint."""
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "docs"
        child.mkdir()
        _make_chroma_fingerprint(child)

        result = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert child.exists(), (
            f"'docs/' must NOT be deleted (hard-exclude by name); stderr: {result.stderr}"
        )

    def test_orphans_hard_exclude_docs_wiki_path_component(self, tmp_path):
        """Path containing docs/wiki as nested components is protected by hard-exclude.

        Review: code-reviewer — existing test only checked a direct child named 'docs';
        the hard-exclude rule targets paths whose component is 'docs/wiki', so a nested
        path like <parent>/docs/wiki must also be protected.
        """
        parent = tmp_path / "parent"
        parent.mkdir()
        # Create docs/wiki as nested path components under parent
        wiki_dir = parent / "docs" / "wiki"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        _make_chroma_fingerprint(wiki_dir)

        result = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert wiki_dir.exists(), (
            f"'docs/wiki/' must NOT be deleted (hard-exclude path component); "
            f"stderr: {result.stderr}"
        )

    def test_orphans_hard_exclude_archive_name(self, tmp_path):
        """Child named 'archive' at parent-altitude: never swept even with fingerprint."""
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "archive"
        child.mkdir()
        _make_chroma_fingerprint(child)

        result = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert child.exists(), (
            f"'archive/' must NOT be deleted (hard-exclude by name); stderr: {result.stderr}"
        )

    def test_orphans_hard_exclude_claude_md_rooted(self, tmp_path):
        """Child named 'tmp/' with CLAUDE.md at root: hard-exclude wins over name+fingerprint."""
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "tmp"
        child.mkdir()
        _make_chroma_fingerprint(child)
        # Plant CLAUDE.md — this makes it a legitimate repo/config dir
        (child / "CLAUDE.md").write_text("# Real project instructions")

        result = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert child.exists(), (
            f"'tmp/' with CLAUDE.md at root must NOT be deleted (hard-exclude); "
            f"stderr: {result.stderr}"
        )

    def test_orphans_hard_exclude_claude_local_md_rooted(self, tmp_path):
        """Child named 'tmp/' with CLAUDE.local.md at root: hard-exclude wins."""
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "tmp"
        child.mkdir()
        _make_chroma_fingerprint(child)
        (child / "CLAUDE.local.md").write_text("# Machine-local instructions")

        result = run(_orphans_base_args(parent, tmp_path) + ["--apply"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert child.exists(), (
            f"'tmp/' with CLAUDE.local.md at root must NOT be deleted (hard-exclude); "
            f"stderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# AC4: Phase C — no output for legitimate dirs
# ---------------------------------------------------------------------------

class TestOrphansLegitDirs:

    def test_orphans_no_output_for_legit_dirs(self, tmp_path):
        """Dirs with legitimate names emit NO JSONL records regardless of contents."""
        parent = tmp_path / "parent"
        parent.mkdir()
        # Create several legit-named dirs (neither name-matched nor fingerprint-relevant)
        legit_names = ["my-sibling-repo", "another-real-thing", "example-repo", "DroneSim"]
        for name in legit_names:
            d = parent / name
            d.mkdir()
            (d / "README.md").write_text(f"# {name}")

        result = run(_orphans_base_args(parent, tmp_path) + ["--dry-run", "--json"])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        records = _jsonl_records(result.stdout)
        assert not records, (
            f"Legitimate parent-altitude dirs must produce NO JSONL records (silent); "
            f"got: {records!r}"
        )
