"""
test_atlas_refresh_gate.py — tests for bin/verify-arch-audit-atlas-refresh.sh
                              (pre-commit gate helper for /architecture-audit Step 6.5).

Spec backlink: docs/plans/2026-06-04-architecture-audit-atlas-refresh-gate.md § C1
Spec backlink: docs/plans/2026-06-08-atlas-attested-clock-split.md (clock split)

ACs covered:
  AC2  — test_backfill_last_attested_equals_last_mapped
           (static: all 7 atlas pages have last_attested == last_mapped)
  AC3  — test_branch_b_passes_on_last_attested_bump_only
           (commit-msg token + last_attested bump + zero body delta + last_mapped unchanged)
  AC4  — test_branch_b_same_day_reattestation_passes
           (same-day re-attestation: HEAD last_attested was yesterday; staged to AUDIT_DATE)
  AC5  — test_branch_a_requires_both_clocks_and_body_diff
           (body diff + both last_mapped and last_attested staged to AUDIT_DATE → PASS branch=A)
  AC6  — test_branch_a_fails_without_last_attested_bump
           (body diff + last_mapped bumped but last_attested left at old date → FAIL teaching msg)
  (adapted) test_branch_a_pass — original AC2 adapted to two-clock schema
  (adapted) test_branch_b_pass — original AC3 adapted: Branch B no longer bumps last_mapped
  (kept)   test_neither_branch_fail — AC4 (verbatim FAIL message)
  (kept)   test_branch_a_wrong_date_fails — boundary: body diff but wrong date
  (kept)   test_branch_b_missing_token_fails — boundary: no commit-msg token
  (extra)  test_skip_when_atlas_absent — SKIP path

Each test stages content into a fresh on-disk git fixture under tmp_path
and shells out to bash for the helper (matching real-world invocation surface).

Negative-spec: tests do NOT invoke the helper as a python import; only via
               `bash <helper-path> ...` per the helper's CLI contract.
"""

import os
import subprocess
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve().parent
HELPER = _HERE.parent / "bin" / "verify-arch-audit-atlas-refresh.sh"

# Repo root is two levels up from the tests/ directory:
# tests/ → coordinator/ → plugins/coordinator-claude/ → ~/.claude (repo root)
_REPO_ROOT = _HERE.parent.parent.parent.parent


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------
def _run(cmd, cwd, env=None, check=True):
    """Shell-out helper; returns CompletedProcess."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=full_env,
        capture_output=True,
        text=True,
        check=check,
    )


def _init_repo(tmp_path: Path) -> Path:
    """Initialize a fresh git repo at tmp_path/repo with deterministic config."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], cwd=repo)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _run(["git", "config", "user.name", "Test"], cwd=repo)
    _run(["git", "config", "commit.gpgsign", "false"], cwd=repo)
    # Force LF in the index/staged content regardless of host autocrlf setting,
    # so the helper's grep+sed frontmatter parser sees pristine line endings.
    _run(["git", "config", "core.autocrlf", "false"], cwd=repo)
    _run(["git", "config", "core.eol", "lf"], cwd=repo)
    return repo


def _write_atlas(
    repo: Path,
    system: str,
    last_mapped: str,
    last_attested: str = None,
    body: str = "",
) -> Path:
    """Write an atlas page with given frontmatter clocks and body.

    last_attested defaults to last_mapped when omitted (backfill convention).
    """
    if last_attested is None:
        last_attested = last_mapped
    atlas_dir = repo / "docs" / "architecture" / "systems"
    atlas_dir.mkdir(parents=True, exist_ok=True)
    atlas_path = atlas_dir / f"{system}.md"
    # Build content without textwrap.dedent — multi-line body values would
    # break common-prefix calculation and leave the frontmatter indented.
    content = (
        "---\n"
        f"system: {system}\n"
        f"last_mapped: {last_mapped}\n"
        f"last_attested: {last_attested}\n"
        "---\n"
        "\n"
        f"# {system}\n"
        "\n"
        f"{body}\n"
    )
    # Write with explicit LF line endings to avoid Windows CRLF translation that
    # could confuse trailing-whitespace trimming in the helper's frontmatter parser.
    atlas_path.write_bytes(content.encode("utf-8"))
    return atlas_path


def _stage(repo: Path, path: Path):
    rel = path.relative_to(repo).as_posix()
    _run(["git", "add", "--", rel], cwd=repo)


def _commit_baseline(repo: Path, message: str = "baseline"):
    """Create an initial commit so the index has a HEAD to diff against."""
    # Ensure at least one file is tracked.
    readme = repo / "README.md"
    readme.write_text("baseline\n", encoding="utf-8")
    _run(["git", "add", "--", "README.md"], cwd=repo)
    _run(["git", "commit", "-q", "-m", message], cwd=repo)


def _invoke(repo: Path, audit_date: str, system: str, commit_msg_file: str = None):
    """Invoke the helper and return CompletedProcess."""
    cmd = ["bash", str(HELPER), audit_date, system]
    if commit_msg_file is not None:
        cmd.append(commit_msg_file)
    return _run(cmd, cwd=repo, check=False)


# ---------------------------------------------------------------------------
# AC2 (plan 2026-06-08) — static backfill check: all 7 atlas pages must have
# last_attested matching last_mapped.
# ---------------------------------------------------------------------------
def test_backfill_last_attested_equals_last_mapped():
    """AC2: all atlas pages under docs/architecture/systems/ have last_attested == last_mapped."""
    atlas_dir = _REPO_ROOT / "docs" / "architecture" / "systems"
    assert atlas_dir.is_dir(), f"Atlas directory not found: {atlas_dir}"

    atlas_pages = sorted(atlas_dir.glob("*.md"))
    assert len(atlas_pages) >= 7, (
        f"Expected at least 7 atlas pages, found {len(atlas_pages)} in {atlas_dir}"
    )

    for page in atlas_pages:
        content = page.read_text(encoding="utf-8")
        lines = content.splitlines()

        last_mapped = None
        last_attested = None
        in_frontmatter = False
        fm_count = 0

        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                fm_count += 1
                if fm_count == 1:
                    in_frontmatter = True
                elif fm_count == 2:
                    in_frontmatter = False
                    break
                continue
            if in_frontmatter:
                if stripped.startswith("last_mapped:"):
                    last_mapped = stripped[len("last_mapped:"):].strip()
                elif stripped.startswith("last_attested:"):
                    last_attested = stripped[len("last_attested:"):].strip()

        assert last_attested is not None, (
            f"{page.name}: missing last_attested field in frontmatter"
        )
        assert last_mapped is not None, (
            f"{page.name}: missing last_mapped field in frontmatter"
        )
        # Semantic invariant: every audit is an attestation, every re-attestation
        # is a Branch B currency stamp — so `last_attested` advances independently
        # of `last_mapped` (rotations only). The post-migration invariant is
        # `last_attested >= last_mapped` (string-compare works on YYYY-MM-DD).
        # Strict equality holds at C1 backfill time but diverges with any Branch B
        # re-attestation (e.g. the C5 dogfood on coordinator-runtime).
        assert last_attested >= last_mapped, (
            f"{page.name}: last_attested={last_attested!r} < last_mapped={last_mapped!r} "
            f"(attestation invariant: last_attested cannot precede last_mapped)"
        )


# ---------------------------------------------------------------------------
# AC5 (plan 2026-06-08) — Branch A pass with both clocks.
# (Adapted from original test_branch_a_pass which used single-clock schema.)
# ---------------------------------------------------------------------------
def test_branch_a_requires_both_clocks_and_body_diff(tmp_path):
    """AC5: body diff + BOTH last_mapped AND last_attested staged to AUDIT_DATE → PASS branch=A."""
    repo = _init_repo(tmp_path)
    _commit_baseline(repo)

    # Initial atlas (old clocks, minimal body) committed to HEAD.
    atlas = _write_atlas(repo, "demo-system", "2026-04-01", "2026-04-01", "Old body.")
    _stage(repo, atlas)
    _run(["git", "commit", "-q", "-m", "seed atlas"], cwd=repo)

    # Refresh: body change + BOTH clocks bumped to audit date.
    _write_atlas(
        repo, "demo-system", "2026-06-04", "2026-06-04",
        "Refreshed body line one.\nRefreshed body line two.",
    )
    _stage(repo, atlas)

    result = _invoke(repo, "2026-06-04", "demo-system")
    assert result.returncode == 0, result.stderr
    assert "PASS branch=A" in result.stdout, (
        f"Expected 'PASS branch=A' in stdout, got: {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Original test_branch_a_pass — kept as an alias of AC5 to preserve coverage.
# ---------------------------------------------------------------------------
def test_branch_a_pass(tmp_path):
    """Branch A: staged body diff + both last_mapped and last_attested == AUDIT_DATE → PASS branch=A."""
    test_branch_a_requires_both_clocks_and_body_diff(tmp_path)


# ---------------------------------------------------------------------------
# AC6 (plan 2026-06-08) — Branch A teaching-shape FAIL when last_attested not bumped.
# ---------------------------------------------------------------------------
def test_branch_a_fails_without_last_attested_bump(tmp_path):
    """AC6: body diff + last_mapped bumped but last_attested NOT bumped → FAIL with teaching message."""
    repo = _init_repo(tmp_path)
    _commit_baseline(repo)

    # Seed atlas with old clocks.
    atlas = _write_atlas(repo, "demo-system", "2026-04-01", "2026-04-01", "Original body.")
    _stage(repo, atlas)
    _run(["git", "commit", "-q", "-m", "seed atlas"], cwd=repo)

    # Stage body diff + last_mapped bumped to AUDIT_DATE but last_attested left at old date.
    _write_atlas(
        repo, "demo-system", "2026-06-04", "2026-04-01",
        "Updated body content — rotation happened.",
    )
    _stage(repo, atlas)

    msg_file = repo / "COMMIT_MSG"
    msg_file.write_text("arch-audit: demo-system\n", encoding="utf-8")

    result = _invoke(repo, "2026-06-04", "demo-system", commit_msg_file=str(msg_file))
    assert result.returncode == 0, result.stderr
    assert "FAIL" in result.stdout, (
        f"Expected FAIL in stdout, got: {result.stdout!r}"
    )
    assert "A real audit IS an attestation" in result.stdout, (
        f"Expected teaching-shape message in stdout, got: {result.stdout!r}"
    )
    assert "bump both clocks" in result.stdout, (
        f"Expected 'bump both clocks' in teaching message, got: {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# AC3 (plan 2026-06-08) — Branch B passes when last_attested bumped only.
# (Replaces original test_branch_b_pass which bumped last_mapped.)
# ---------------------------------------------------------------------------
def test_branch_b_passes_on_last_attested_bump_only(tmp_path):
    """AC3: commit-msg token + last_attested bump to AUDIT_DATE + zero body delta + last_mapped unchanged → PASS branch=B."""
    repo = _init_repo(tmp_path)
    _commit_baseline(repo)

    # Initial atlas: last_mapped=2026-06-01, last_attested=2026-06-01.
    atlas = _write_atlas(repo, "demo-system", "2026-06-01", "2026-06-01", "Same body content.")
    _stage(repo, atlas)
    _run(["git", "commit", "-q", "-m", "seed atlas"], cwd=repo)

    # Bump only last_attested to AUDIT_DATE; last_mapped and body unchanged.
    _write_atlas(repo, "demo-system", "2026-06-01", "2026-06-04", "Same body content.")
    _stage(repo, atlas)

    # Prepare intended commit message file with the Branch B token.
    msg_file = repo / "COMMIT_MSG"
    msg_file.write_text(
        "arch-audit: ratify demo-system atlas current\n\n"
        "atlas-current-as-of:2026-06-04\n",
        encoding="utf-8",
    )

    result = _invoke(repo, "2026-06-04", "demo-system", commit_msg_file=str(msg_file))
    assert result.returncode == 0, result.stderr
    assert "PASS branch=B" in result.stdout, (
        f"Expected 'PASS branch=B' in stdout, got: {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Original test_branch_b_pass — kept by delegation to the new AC3 test.
# Under new semantics Branch B no longer bumps last_mapped; this test now
# exercises the same path (last_attested-only bump).
# ---------------------------------------------------------------------------
def test_branch_b_pass(tmp_path):
    """Branch B (adapted): last_attested bump only + commit-msg token + zero body delta → PASS branch=B."""
    test_branch_b_passes_on_last_attested_bump_only(tmp_path)


# ---------------------------------------------------------------------------
# AC4 (plan 2026-06-08) — same-day re-attestation: HEAD last_attested was
# yesterday; staged bump to today; last_mapped unchanged.
# ---------------------------------------------------------------------------
def test_branch_b_same_day_reattestation_passes(tmp_path):
    """AC4: HEAD last_attested was AUDIT_DATE-1; staged bump to AUDIT_DATE; last_mapped unchanged → PASS branch=B."""
    repo = _init_repo(tmp_path)
    _commit_baseline(repo)

    # HEAD atlas: last_mapped and last_attested both set to "yesterday".
    atlas = _write_atlas(repo, "demo-system", "2026-06-07", "2026-06-07", "Body unchanged.")
    _stage(repo, atlas)
    _run(["git", "commit", "-q", "-m", "seed atlas"], cwd=repo)

    # Stage: bump last_attested to today (2026-06-08); last_mapped and body unchanged.
    _write_atlas(repo, "demo-system", "2026-06-07", "2026-06-08", "Body unchanged.")
    _stage(repo, atlas)

    msg_file = repo / "COMMIT_MSG"
    msg_file.write_text(
        "arch-audit: re-attest demo-system same day\n\n"
        "atlas-current-as-of:2026-06-08\n",
        encoding="utf-8",
    )

    result = _invoke(repo, "2026-06-08", "demo-system", commit_msg_file=str(msg_file))
    assert result.returncode == 0, result.stderr
    assert "PASS branch=B" in result.stdout, (
        f"Expected 'PASS branch=B' in stdout, got: {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# AC4 (original plan) — Neither branch satisfied → verbatim FAIL message.
# ---------------------------------------------------------------------------
def test_neither_branch_fail(tmp_path):
    """Stale last_attested, no body diff, no commit-msg token → FAIL message."""
    repo = _init_repo(tmp_path)
    _commit_baseline(repo)

    atlas = _write_atlas(repo, "demo-system", "2026-04-01", "2026-04-01", "Original body.")
    _stage(repo, atlas)
    _run(["git", "commit", "-q", "-m", "seed atlas"], cwd=repo)

    # Stage nothing new: clocks still 2026-04-01, no body change.
    # Helper should FAIL.
    msg_file = repo / "COMMIT_MSG"
    msg_file.write_text("arch-audit: demo-system\n", encoding="utf-8")

    result = _invoke(repo, "2026-06-04", "demo-system", commit_msg_file=str(msg_file))
    assert result.returncode == 0, result.stderr
    assert "FAIL: /architecture-audit Step 6.5 atlas-refresh gate not satisfied" in result.stdout, (
        f"Expected FAIL message in stdout, got: {result.stdout!r}"
    )
    assert "demo-system" in result.stdout
    # Both remediation prongs cited.
    assert "refresh docs/architecture/systems/demo-system.md" in result.stdout
    assert "atlas-current-as-of:2026-06-04" in result.stdout


# ---------------------------------------------------------------------------
# Finding 9 — Branch A wrong-date boundary: body diff present but last_mapped
# does NOT match AUDIT_DATE → FAIL (not PASS branch=A).
# ---------------------------------------------------------------------------
def test_branch_a_wrong_date_fails(tmp_path):
    """Body diff staged, but last_mapped bumped to a date != AUDIT_DATE → FAIL."""
    repo = _init_repo(tmp_path)
    _commit_baseline(repo)

    # Seed atlas with old clocks and body.
    atlas = _write_atlas(repo, "demo-system", "2026-04-01", "2026-04-01", "Original body.")
    _stage(repo, atlas)
    _run(["git", "commit", "-q", "-m", "seed atlas"], cwd=repo)

    # Stage body diff, but last_mapped bumped to a date other than AUDIT_DATE.
    # last_attested also set to wrong date to stay off the AC6 branch.
    _write_atlas(repo, "demo-system", "2026-05-15", "2026-05-15", "Updated body content here.")
    _stage(repo, atlas)

    # No commit-msg token.
    msg_file = repo / "COMMIT_MSG"
    msg_file.write_text("arch-audit: demo-system\n", encoding="utf-8")

    result = _invoke(repo, "2026-06-04", "demo-system", commit_msg_file=str(msg_file))
    assert result.returncode == 0, result.stderr
    assert "FAIL: /architecture-audit Step 6.5 atlas-refresh gate not satisfied" in result.stdout, (
        f"Expected FAIL message in stdout, got: {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Finding 9 — Branch B missing-token boundary: last_attested bumped to
# AUDIT_DATE with zero body delta and last_mapped unchanged, but commit-msg
# lacks atlas-current-as-of token → FAIL.
# ---------------------------------------------------------------------------
def test_branch_b_missing_token_fails(tmp_path):
    """last_attested bumped to AUDIT_DATE, zero body delta, last_mapped unchanged, but NO commit-msg token → FAIL."""
    repo = _init_repo(tmp_path)
    _commit_baseline(repo)

    # Seed atlas with old clocks and body.
    atlas = _write_atlas(repo, "demo-system", "2026-04-01", "2026-04-01", "Stable body content.")
    _stage(repo, atlas)
    _run(["git", "commit", "-q", "-m", "seed atlas"], cwd=repo)

    # Bump last_attested to AUDIT_DATE, keep last_mapped and body identical (Branch B shape).
    _write_atlas(repo, "demo-system", "2026-04-01", "2026-06-04", "Stable body content.")
    _stage(repo, atlas)

    # Commit-msg intentionally missing the atlas-current-as-of token.
    msg_file = repo / "COMMIT_MSG"
    msg_file.write_text("arch-audit: demo-system closeout\n", encoding="utf-8")

    result = _invoke(repo, "2026-06-04", "demo-system", commit_msg_file=str(msg_file))
    assert result.returncode == 0, result.stderr
    assert "FAIL: /architecture-audit Step 6.5 atlas-refresh gate not satisfied" in result.stdout, (
        f"Expected FAIL message in stdout, got: {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Extra — atlas absent → SKIP.
# ---------------------------------------------------------------------------
def test_skip_when_atlas_absent(tmp_path):
    """No atlas page for target → SKIP — no atlas page for <system>."""
    repo = _init_repo(tmp_path)
    _commit_baseline(repo)

    result = _invoke(repo, "2026-06-04", "nonexistent-system")
    assert result.returncode == 0, result.stderr
    assert "SKIP" in result.stdout
    assert "nonexistent-system" in result.stdout
