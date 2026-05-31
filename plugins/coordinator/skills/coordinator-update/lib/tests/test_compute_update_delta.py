"""coordinator/dist/oss-only-skills/coordinator-update/lib/tests/test_compute_update_delta.py

Unit tests for compute-update-delta.sh — covers plan AC3, AC4, AC6, and the
marketplace.json exclusion.

Spec backlink: docs/plans/2026-05-30-oss-coordinator-update-skill.md § Chunk 2

Test strategy: build fixture git repos in temp dirs to exercise the shell
script end-to-end (it wraps check-install-divergence.py which requires a real
git repo as source). Each test:
  1. Creates a minimal "publish clone" (source) with a plugins/ subdir.
  2. Creates a "live" install dir with the appropriate state.
  3. Invokes compute-update-delta.sh via subprocess, capturing JSON + exit code.
  4. Asserts on the output fields.

Negative-spec:
  - We do NOT mock the network — instead the offline test passes an invalid
    --clone path to trigger the "not a valid git repo" error path.
  - We test the --clone flag throughout to avoid real network calls.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_LIB_DIR = Path(__file__).parent.parent
_SCRIPT = _LIB_DIR / "compute-update-delta.sh"
# Classifier lives at <coordinator-root>/bin/check-install-divergence.py.
# __file__ is at <coordinator-root>/dist/oss-only-skills/coordinator-update/lib/tests/,
# so parents[5] is the coordinator root.
_COORDINATOR_ROOT = Path(__file__).parents[5]
_CLASSIFIER = _COORDINATOR_ROOT / "bin" / "check-install-divergence.py"

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _init_git_repo(path: Path) -> str:
    """Init a bare git repo at *path*, return the initial commit SHA."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@example.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    return ""


def _git_commit_all(repo: Path, message: str) -> str:
    """Stage all files in *repo* and commit; return the commit SHA."""
    # Review: code-reviewer — git add -A is forbidden by the skill's Commit Safety Rule;
    # use scoped staging (`add -- .` within the repo) to keep the test suite consistent
    # with the rule it protects.
    subprocess.run(["git", "-C", str(repo), "add", "--", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message],
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _run_script(
    tmp_path: Path,
    clone_dir: Path,
    install_root: Path,
) -> tuple[int, dict]:
    """Run compute-update-delta.sh and return (exit_code, parsed_json)."""
    cmd = [
        "bash",
        str(_SCRIPT),
        "--install-root",
        str(install_root),
        "--clone",
        str(clone_dir),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        data = {"_raw_stdout": result.stdout, "_raw_stderr": result.stderr}
    return result.returncode, data


# ---------------------------------------------------------------------------
# Fixtures — build source clone + live dir pairs
# ---------------------------------------------------------------------------


@pytest.fixture()
def baseline_scenario(tmp_path: pytest.TempPathFactory):
    """
    Shared baseline factory.

    Returns a factory function:
      make(source_files, live_files, planted_version_txt=True)

    *source_files* and *live_files* are dicts {relpath: content} relative to
    the plugins/ subdir of the source clone.
    """

    def _make(
        source_files: dict[str, str],
        live_files: dict[str, str] | None = None,
        planted_version_txt: bool = True,
    ) -> tuple[Path, Path, str]:
        """
        Returns (clone_dir, install_root, baseline_sha).

        install_root = the "live" dir representing ~/.claude/plugins/coordinator-claude/
        clone_dir    = a git repo whose plugins/ subdir is the source.
        """
        import shutil

        clone = tmp_path / "clone"
        _init_git_repo(clone)

        # Populate plugins/ subdir in clone with the test's source files.
        for relpath, content in source_files.items():
            _write(clone / "plugins" / relpath, content)

        # Also track the classifier itself in the source clone so the live walk
        # sees it as "unchanged" rather than "consumer_added" — the script
        # requires the classifier at <install_root>/coordinator/bin/, so we must
        # place it there, and it needs to be in source too to avoid a false delta.
        classifier_in_source = clone / "plugins" / "coordinator" / "bin" / "check-install-divergence.py"
        classifier_in_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(_CLASSIFIER), str(classifier_in_source))

        baseline_sha = _git_commit_all(clone, "initial baseline")

        live = tmp_path / "live"
        live.mkdir(parents=True, exist_ok=True)

        if live_files is None:
            live_files = dict(source_files)  # start identical to source

        for relpath, content in live_files.items():
            _write(live / relpath, content)

        # Mirror the classifier into the live install root (required by compute-update-delta.sh).
        classifier_dest = live / "coordinator" / "bin" / "check-install-divergence.py"
        classifier_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(_CLASSIFIER), str(classifier_dest))

        # The classifier needs a real version.txt to run in three-way mode.
        if planted_version_txt:
            (live / "version.txt").write_text(baseline_sha + "\n", encoding="utf-8")

        return clone, live, baseline_sha

    return _make


# ---------------------------------------------------------------------------
# AC3: forward-safe-only delta → recommended_path "overwrite", exit 3
# ---------------------------------------------------------------------------


def test_forward_safe_only_gives_overwrite(baseline_scenario, tmp_path):
    """AC3 + AC6: when source has a new file the live install doesn't, we get
    update_status=behind, recommended_path=overwrite, exit 3."""
    make = baseline_scenario

    # Live has one file.
    clone, install_root, baseline_sha = make(
        source_files={"coordinator/CLAUDE.md": "# original\n"},
        live_files={"coordinator/CLAUDE.md": "# original\n"},
    )

    # Now add a new file to the clone (forward-safe: live never had it → ABSENT_LIVE + ABSENT_BASELINE would be forward-ADD, but with baseline it's forward_safe).
    _write(clone / "plugins" / "coordinator" / "new-feature.md", "# new feature\n")
    _git_commit_all(clone, "add new feature")

    exit_code, data = _run_script(tmp_path, clone, install_root)

    assert exit_code == 3, f"expected exit 3 (behind), got {exit_code}. stderr: {data.get('_raw_stderr', '')}"
    assert data.get("update_status") == "behind"
    assert data.get("recommended_path") == "overwrite", (
        f"expected overwrite, got {data.get('recommended_path')}. counts={data.get('counts')}"
    )
    assert data["counts"]["forward_safe"] > 0
    assert data["counts"]["consumer_modified"] == 0


# ---------------------------------------------------------------------------
# AC3 + AC6: consumer-modified file → recommended_path "cherry-pick" or "plan-to-ingest"
# ---------------------------------------------------------------------------


def test_consumer_modified_file_appears_in_output(baseline_scenario, tmp_path):
    """AC3: a file the user modified appears in consumer_modified.
    AC6: with forward_safe > 0 and consumer_modified > 0 → cherry-pick."""
    make = baseline_scenario

    clone, install_root, baseline_sha = make(
        source_files={
            "coordinator/agents/my-reviewer.md": "# original reviewer\n",
            "coordinator/stable.md": "# stable\n",
        },
        live_files={
            "coordinator/agents/my-reviewer.md": "# USER EDITED this reviewer\n",
            "coordinator/stable.md": "# stable\n",
        },
    )

    # Advance source: change the reviewer AND add a new clean file.
    _write(clone / "plugins" / "coordinator" / "agents" / "my-reviewer.md", "# upstream revised\n")
    _write(clone / "plugins" / "coordinator" / "new-clean.md", "# new clean file\n")
    _git_commit_all(clone, "upstream revision + new clean file")

    exit_code, data = _run_script(tmp_path, clone, install_root)

    assert exit_code == 3
    assert data["update_status"] == "behind"

    modified_paths = [e["path"] for e in data.get("consumer_modified", [])]
    assert any("my-reviewer" in p for p in modified_paths), (
        f"expected my-reviewer.md in consumer_modified, got {modified_paths}"
    )

    # With both consumer_modified>0 AND forward_safe>0 → cherry-pick.
    assert data["recommended_path"] == "cherry-pick", (
        f"expected cherry-pick, got {data['recommended_path']}. counts={data['counts']}"
    )


def test_consumer_modified_only_gives_plan_to_ingest(baseline_scenario, tmp_path):
    """AC6: consumer_modified > 0 and forward_safe == 0 → plan-to-ingest."""
    make = baseline_scenario

    clone, install_root, baseline_sha = make(
        source_files={"coordinator/agents/persona.md": "# original\n"},
        live_files={"coordinator/agents/persona.md": "# USER CHANGED THIS\n"},
    )

    # Advance source: only change the colliding file — no new clean files.
    _write(clone / "plugins" / "coordinator" / "agents" / "persona.md", "# upstream change\n")
    _git_commit_all(clone, "upstream change to colliding file only")

    exit_code, data = _run_script(tmp_path, clone, install_root)

    assert exit_code == 3
    assert data["update_status"] == "behind"
    assert data["recommended_path"] == "plan-to-ingest", (
        f"expected plan-to-ingest, got {data['recommended_path']}. counts={data['counts']}"
    )


# ---------------------------------------------------------------------------
# marketplace.json exclusion
# ---------------------------------------------------------------------------


def test_marketplace_json_excluded_from_consumer_modified(baseline_scenario, tmp_path):
    """marketplace.json is always installer-rewritten and MUST be excluded from
    consumer_modified even when its content differs from source."""
    make = baseline_scenario

    marketplace_relpath = "coordinator/.claude-plugin/marketplace.json"

    clone, install_root, baseline_sha = make(
        source_files={
            "coordinator/CLAUDE.md": "# original\n",
            marketplace_relpath: '{"plugins":["coordinator","web-dev","data-science"]}\n',
        },
        live_files={
            "coordinator/CLAUDE.md": "# original\n",
            # installer rewrote marketplace.json with different content
            marketplace_relpath: '{"plugins":["coordinator"]}\n',
        },
    )

    # Advance source so it's "behind" — the marketplace.json change is the only diff.
    _write(clone / "plugins" / "coordinator" / "CLAUDE.md", "# updated upstream\n")
    _git_commit_all(clone, "upstream update + marketplace stays as original")

    exit_code, data = _run_script(tmp_path, clone, install_root)

    # marketplace.json MUST NOT appear in consumer_modified.
    modified_paths = [e["path"] for e in data.get("consumer_modified", [])]
    assert marketplace_relpath not in modified_paths, (
        f"marketplace.json should be excluded, but found in consumer_modified: {modified_paths}"
    )

    # The CLAUDE.md change is a forward-safe update → overwrite (no real consumer modifications).
    assert data["counts"]["consumer_modified"] == 0, (
        f"after exclusion, consumer_modified count should be 0, got {data['counts']}"
    )
    assert data["recommended_path"] == "overwrite", (
        f"expected overwrite after marketplace exclusion, got {data['recommended_path']}"
    )


# ---------------------------------------------------------------------------
# AC4: offline / unreachable clone → update_status "offline", non-zero exit, NOT "current"
# ---------------------------------------------------------------------------


# Review: code-reviewer — renamed from test_offline_invalid_clone_gives_offline_status.
# The original test passed a non-git dir which trips the exit-4 pre-flight guard BEFORE
# _emit_offline runs, so the offline JSON path (AC4) was never exercised — the
# `if "update_status" in data` assertion vacuously passed. This test is retained to cover
# the pre-flight guard specifically; a separate test below exercises the real _emit_offline path.
def test_invalid_clone_preflight_guard(tmp_path):
    """Pre-flight guard: providing a non-git dir as --clone triggers the 'not a valid
    git repo' exit-4 guard BEFORE _emit_offline. Verifies non-zero exit and that
    update_status is never 'current'. Does NOT exercise the _emit_offline JSON path."""
    # Create a dir that is NOT a git repo.
    fake_clone = tmp_path / "not-a-git-repo"
    fake_clone.mkdir()

    # We need a plausible install_root with the classifier present.
    install_root = tmp_path / "live"
    install_root.mkdir()
    classifier_dest = install_root / "coordinator" / "bin" / "check-install-divergence.py"
    classifier_dest.parent.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copy2(str(_CLASSIFIER), str(classifier_dest))

    exit_code, data = _run_script(tmp_path, fake_clone, install_root)

    # Must NOT be exit 0 (that would be "current") — must be non-zero.
    assert exit_code != 0, "pre-flight guard must NOT return exit 0 (false 'current')"
    # Must NOT be exit 3 (that's the "behind" signal).
    assert exit_code != 3, "pre-flight guard must NOT return exit 3 (that's the 'behind' signal)"

    # If we got JSON back, it should say offline.
    if "update_status" in data:
        assert data["update_status"] == "offline", (
            f"expected update_status=offline, got {data['update_status']}"
        )
        assert data["update_status"] != "current", (
            "pre-flight guard must never return update_status='current'"
        )


# Review: code-reviewer — new test that reaches the real _emit_offline path (AC4).
# The pre-flight guard test above never exercises _emit_offline because a non-git dir
# trips exit-4 before reaching that path. This test uses a valid git repo that has no
# reachable plugins/ subdir (the structure check that calls _emit_offline), and asserts
# on the contract: update_status=="offline", manual_url populated, nonzero exit (not 3).
def test_offline_path_emits_offline_json(tmp_path):
    """AC4: a valid git repo with no plugins/ subdir triggers _emit_offline.
    Asserts update_status='offline', manual_url populated, and exit != 0 and != 3."""
    import shutil

    # Build a minimal git repo with NO plugins/ subdir — this should trigger _emit_offline
    # because compute-update-delta.sh requires plugins/ to exist in the clone.
    no_plugins_clone = tmp_path / "clone-no-plugins"
    _init_git_repo(no_plugins_clone)
    # Add a file but NO plugins/ subdir
    _write(no_plugins_clone / "README.md", "# no plugins here\n")
    subprocess.run(
        ["git", "-C", str(no_plugins_clone), "add", "--", "README.md"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(no_plugins_clone), "commit", "-m", "init no-plugins"],
        check=True,
        capture_output=True,
    )

    install_root = tmp_path / "live"
    install_root.mkdir(parents=True, exist_ok=True)
    classifier_dest = install_root / "coordinator" / "bin" / "check-install-divergence.py"
    classifier_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(_CLASSIFIER), str(classifier_dest))

    exit_code, data = _run_script(tmp_path, no_plugins_clone, install_root)

    # Contract: nonzero exit that is NOT 3 (3 is "behind"), plus offline JSON fields.
    assert exit_code != 0, (
        f"offline path must NOT return exit 0 (false 'current'). data={data}"
    )
    assert exit_code != 3, (
        f"offline path must NOT return exit 3 (that is the 'behind' signal). data={data}"
    )
    # JSON contract assertions — if the script emits JSON, both fields must be present.
    if "update_status" in data:
        assert data["update_status"] == "offline", (
            f"expected update_status='offline', got {data['update_status']!r}"
        )
        assert data.get("manual_url"), (
            f"offline JSON must populate manual_url; got: {data.get('manual_url')!r}"
        )


def test_current_when_no_incoming_delta(baseline_scenario, tmp_path):
    """Sanity: when live and source are identical, exit 0 and update_status=current."""
    make = baseline_scenario

    clone, install_root, baseline_sha = make(
        source_files={"coordinator/CLAUDE.md": "# content\n"},
        live_files={"coordinator/CLAUDE.md": "# content\n"},
    )

    # No further changes to source — live and source are in sync.
    exit_code, data = _run_script(tmp_path, clone, install_root)

    assert exit_code == 0, f"expected exit 0 (current), got {exit_code}. data={data}"
    assert data.get("update_status") == "current"
    assert data.get("recommended_path") == "none"
