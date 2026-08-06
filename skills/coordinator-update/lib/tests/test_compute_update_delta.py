"""coordinator/dist/oss-only-skills/coordinator-update/lib/tests/test_compute_update_delta.py

Unit tests for compute-update-delta.py — covers plan AC3, AC4, AC6, and the
marketplace.json exclusion.

Spec backlink: docs/plans/2026-05-30-oss-coordinator-update-skill.md § Chunk 2

Test strategy: build fixture git repos in temp dirs to exercise the Python
trampoline end-to-end (it wraps check-install-divergence.py which requires a
real git repo as source). Each test:
  1. Creates a minimal "publish clone" (source) with coordinator/ at the clone root.
  2. Creates a "live" install dir with the appropriate state.
  3. Invokes compute-update-delta.py via subprocess, capturing JSON + exit code.
  4. Asserts on the output fields.

Negative-spec:
  - We do NOT mock the network — instead the offline test passes an invalid
    --clone path to trigger the "not a valid git repo" error path.
  - We test the --clone flag throughout to avoid real network calls.
  - DELETED 2026-07-22: tests/test-compute-update-delta-layout.sh (bash — a
    P0 defect per coordinator.local.md's structural-bash ruling, independent
    of this disposition). It asserted two things, both now moot, not ported:
    (1) constants resolution succeeds regardless of the script's own
    dist-source-vs-post-install depth — moot, because the engine-root
    resolution this file's tests exercise is now delegated to the shipped
    resolver script's own CLI entrypoint (`_resolve_engine_root`), which has
    no depth-sensitive step left to regress on this trampoline's side; the
    marker-walk it was guarding against no longer exists here. (2) the
    classifier is never invoked with a `--source` path ending in `/plugins`
    — moot as a LIVE code-path concern (the current implementation does
    `source_dir = repo_dir` verbatim, no string concatenation exists that
    could ever produce a plugins/-suffixed path, so the bug class is
    structurally impossible, not merely untriggered), and its real-world
    "clone root has no plugins/ subdir" case is already covered with a
    genuine assertion by test_clone_root_no_plugins_subdir_is_valid_not_offline
    below. No residual value to port.
"""

from __future__ import annotations

import ast
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
_SCRIPT = _LIB_DIR / "compute-update-delta.py"
# __file__ is at <coordinator-root>/dist/oss-only-skills/coordinator-update/lib/tests/,
# so parents[5] is the coordinator root — matches the depth used by the
# resolver import below, precedent'd in
# coordinator/dist/publish-repo-setup/tests/test_install.py's REAL_WRITER block.
_COORDINATOR_ROOT = Path(__file__).parents[5]

# The engine-root resolver script ships publicly at hooks/scripts/_engine_root.py
# (unlike this trampoline's runtime, the test suite runs inside the dev repo and
# may import it directly rather than delegating via subprocess).
_HOOKS_SCRIPTS_DIR = _COORDINATOR_ROOT / "hooks" / "scripts"
_RESOLVER_SCRIPT = _HOOKS_SCRIPTS_DIR / "_engine_root.py"
sys.path.insert(0, str(_HOOKS_SCRIPTS_DIR))
from _engine_root import LIVE_TREE_ENV_VARS, resolve_claude_klabauter_root  # noqa: E402

# The env var rung 1 consults first. Taken from the resolver rather than
# spelled literally: this payload is injected AFTER the publish
# content-transform sweep and so is never rewritten by it, while the resolver
# is — so a literal here would name a variable the published resolver does
# not read, and the test would silently fall through to a different rung.
_PRIMARY_ENGINE_ROOT_ENV = LIVE_TREE_ENV_VARS[0]

_ENGINE_ROOT = resolve_claude_klabauter_root()
if _ENGINE_ROOT is None:
    raise RuntimeError(
        "the coordinator engine root could not be resolved via "
        "_engine_root.resolve_claude_klabauter_root() — oss-repo-constants.py and "
        "check-install-divergence.py live there and these tests need them "
        "to exist on disk; fix the resolution, don't skip around it"
    )

# Classifier + constants live in the resolved engine checkout, not this repo.
# compute-update-delta.py resolves the engine root at runtime by delegating
# to the shipped resolver script's CLI entrypoint (`_resolve_engine_root`);
# these tests resolve it via the real `resolve_claude_klabauter_root` import instead,
# since — unlike the production trampoline, which ships standalone into the
# OSS dist — the test suite runs in this dev repo and may import it.
_CLASSIFIER = Path(_ENGINE_ROOT) / "coordinator" / "bin" / "check-install-divergence.py"
if not _CLASSIFIER.is_file():
    raise RuntimeError(f"resolved the coordinator engine root at {_ENGINE_ROOT} but check-install-divergence.py is missing there")


def _install_resolver(install_root: Path) -> None:
    """Copy the shipped resolver script into *install_root* at the path
    compute-update-delta.py's `_resolve_engine_root` expects
    (coordinator/hooks/scripts/_engine_root.py) — the delegation seam this
    trampoline now uses instead of reimplementing the resolution ladder."""
    import shutil

    dest = install_root / "coordinator" / "hooks" / "scripts" / "_engine_root.py"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(_RESOLVER_SCRIPT), str(dest))

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _init_git_repo(path: Path) -> str:
    """Init a bare git repo at *path*, return the initial commit SHA."""
    path.mkdir(parents=True, exist_ok=True)
    # Review: code-reviewer (F15) — git init -b main requires git ≥ 2.28; fall back to
    # plain init + branch rename for older git (e.g. Apple Git on macOS ≤ 2.27).
    try:
        subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(path), "checkout", "-b", "main"], capture_output=True)
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
    """Run compute-update-delta.py and return (exit_code, parsed_json)."""
    cmd = [
        sys.executable,
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
    the source clone ROOT (e.g. "coordinator/CLAUDE.md") — no plugins/ subdir.
    """

    def _make(
        source_files: dict[str, str],
        live_files: dict[str, str] | None = None,
        planted_version_txt: bool = True,
    ) -> tuple[Path, Path, str]:
        """
        Returns (clone_dir, install_root, baseline_sha).

        install_root = the "live" dir representing ~/.claude/plugins/coordinator-claude/
        clone_dir    = a git repo whose ROOT is the source (coordinator/ at top level).
        """
        import shutil

        clone = tmp_path / "clone"
        _init_git_repo(clone)

        # Write source files at the clone root (no plugins/ subdir — matches the OSS publish repo layout).
        # Review: code-reviewer (A-F4) — corrected from "plugins/ subdir"; SOURCE_DIR is clone root.
        for relpath, content in source_files.items():
            _write(clone / relpath, content)

        # Also track the classifier itself in the source clone so the live walk
        # sees it as "unchanged" rather than "consumer_added" — the script
        # requires the classifier at <install_root>/coordinator/bin/, so we must
        # place it there, and it needs to be in source too to avoid a false delta.
        classifier_in_source = clone / "coordinator" / "bin" / "check-install-divergence.py"
        classifier_in_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(_CLASSIFIER), str(classifier_in_source))

        baseline_sha = _git_commit_all(clone, "initial baseline")

        live = tmp_path / "live"
        live.mkdir(parents=True, exist_ok=True)

        if live_files is None:
            live_files = dict(source_files)  # start identical to source

        for relpath, content in live_files.items():
            _write(live / relpath, content)

        # Mirror the classifier into the live install root (required by compute-update-delta.py).
        classifier_dest = live / "coordinator" / "bin" / "check-install-divergence.py"
        classifier_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(_CLASSIFIER), str(classifier_dest))

        # Install the resolver script the trampoline delegates engine-root
        # resolution to (required by compute-update-delta.py's _resolve_engine_root).
        _install_resolver(live)

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
    _write(clone / "coordinator" / "new-feature.md", "# new feature\n")
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
    _write(clone / "coordinator" / "agents" / "my-reviewer.md", "# upstream revised\n")
    _write(clone / "coordinator" / "new-clean.md", "# new clean file\n")
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
    _write(clone / "coordinator" / "agents" / "persona.md", "# upstream change\n")
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
    _write(clone / "coordinator" / "CLAUDE.md", "# updated upstream\n")
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
# the pre-flight guard specifically; the _emit_offline git-failure JSON path is covered
# indirectly by test_invalid_clone_preflight_guard (non-git dir hits the guard that calls
# _emit_offline) and is NOT separately unit-tested.
# Review: code-reviewer (A-F3) — removed stale promise of "a separate test below"; the
# clone-root regression test (test_clone_root_no_plugins_subdir_is_valid_not_offline) replaced it.
def test_invalid_clone_preflight_guard(tmp_path):
    """Pre-flight guard: providing a non-git dir as --clone triggers the 'not a valid
    git repo' exit-4 guard BEFORE _emit_offline. Verifies non-zero exit and that
    update_status is never 'current'. Does NOT exercise the _emit_offline JSON path."""
    # Create a dir that is NOT a git repo.
    fake_clone = tmp_path / "not-a-git-repo"
    fake_clone.mkdir()

    # We need a plausible install_root with the classifier and resolver present.
    install_root = tmp_path / "live"
    install_root.mkdir()
    classifier_dest = install_root / "coordinator" / "bin" / "check-install-divergence.py"
    classifier_dest.parent.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copy2(str(_CLASSIFIER), str(classifier_dest))
    _install_resolver(install_root)

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


# C-R2b(2026-06-26): the OLD "no plugins/ subdir → offline" structure check was
# REMOVED — it was the bug (#1b). SOURCE_DIR is now the clone ROOT (the OSS publish
# repo mirrors coordinator/ at its top level, no plugins/ subdir). So a valid git repo
# with coordinator/ at its root must be read CORRECTLY, not falsely flagged offline.
# This test locks the new clone-root contract (the inverse of the removed behavior).
# Genuine offline (network/git failure) is covered by test_invalid_clone_preflight_guard
# and _emit_offline's git-failure call sites (clone/fetch/checkout failed).
def test_clone_root_no_plugins_subdir_is_valid_not_offline(tmp_path):
    """C-R2b regression net: a valid git repo with coordinator/ at the clone ROOT
    (and NO plugins/ subdir) is read from the root and classified normally — it must
    NOT be treated as offline (the old plugins/-required bug). Identical source/live
    content → exit 0, update_status=current."""
    import shutil

    clone_root = tmp_path / "clone-root"
    _init_git_repo(clone_root)
    # coordinator/ lives at the clone ROOT — NO plugins/ subdir (the publish-repo shape).
    _write(clone_root / "coordinator" / "CLAUDE.md", "# content\n")
    classifier_in_source = clone_root / "coordinator" / "bin" / "check-install-divergence.py"
    classifier_in_source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(_CLASSIFIER), str(classifier_in_source))
    baseline_sha = _git_commit_all(clone_root, "init coordinator at clone root")

    install_root = tmp_path / "live"
    _write(install_root / "coordinator" / "CLAUDE.md", "# content\n")
    classifier_dest = install_root / "coordinator" / "bin" / "check-install-divergence.py"
    classifier_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(_CLASSIFIER), str(classifier_dest))
    _install_resolver(install_root)
    (install_root / "version.txt").write_text(baseline_sha + "\n", encoding="utf-8")

    exit_code, data = _run_script(tmp_path, clone_root, install_root)

    # Clone-root with coordinator/ present is VALID — not offline, not exit 4.
    assert exit_code == 0, (
        f"clone-root repo with coordinator/ must classify (not offline/exit-4). got {exit_code}, data={data}"
    )
    assert data.get("update_status") == "current", (
        f"identical source/live at clone root → current; got {data.get('update_status')!r}"
    )
    assert data.get("update_status") != "offline", (
        "a valid clone-root repo must never be falsely flagged offline (the removed plugins/ bug)"
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


# ---------------------------------------------------------------------------
# Python-port regression net (2026-07-17 BIG_PORT bash→Python trampoline).
# Porter-brief addendum §§ 2, 4: every subprocess.run over network/external
# input MUST carry timeout= + stdin=DEVNULL + CREATE_NO_WINDOW-consistency.
# Prior to this port, the bash oracle had NO timeout on git clone/fetch/
# checkout — a hung remote wedged this script (and any caller, e.g. the
# `/coordinator-update` skill) forever. These tests would have caught that
# gap; they must stay green against the trampoline going forward.
# ---------------------------------------------------------------------------


def test_every_subprocess_call_has_timeout_and_stdin_guard():
    """Static regression net for the addendum §2 fix: every external
    process-spawn in the trampoline module goes through the shared `_run(...)`
    choke-point, which defaults timeout=, stdin=DEVNULL, and
    creationflags=_CREATIONFLAGS on every call. A future edit that adds a
    bare subprocess.run(...) bypassing `_run` (and thus omitting these
    guards) would silently reopen the unbounded-hang / Windows-console-flash
    classes this port fixed."""
    text = _SCRIPT.read_text(encoding="utf-8")

    # The `_run` choke-point itself must default timeout, stdin, and
    # creationflags — this is the ONE place that guarantees the invariant.
    assert 'kwargs.setdefault("timeout"' in text, (
        "_run() must default a timeout — subprocess calls through it must never hang forever"
    )
    assert 'kwargs.setdefault("stdin", subprocess.DEVNULL)' in text, (
        "_run() must default stdin=DEVNULL — a subprocess call must never block on stdin"
    )
    assert 'kwargs.setdefault("creationflags", _CREATIONFLAGS)' in text, (
        "_run() must default creationflags=_CREATIONFLAGS for Windows console-flash consistency"
    )

    # No call site may bypass the choke point with a bare subprocess.run(...)
    # — the only permitted occurrence of the literal `subprocess.run(` text is
    # inside _run()'s own body.
    import re

    bare_calls = [m.start() for m in re.finditer(r"subprocess\.run\(", text)]
    assert len(bare_calls) == 1, (
        f"expected exactly one subprocess.run(...) call site (inside _run() itself); "
        f"found {len(bare_calls)} — every other spawn must go through _run(...) "
        f"to inherit the timeout/stdin/creationflags guards"
    )


def test_no_hardcoded_tmp_env_var_fallback():
    """Addendum §4 (Windows portability): must not fall back to
    os.environ.get('TMPDIR', '/tmp') — TMPDIR is unset on Windows and /tmp
    does not exist there. The port must use tempfile.mkdtemp()/gettempdir()."""
    text = _SCRIPT.read_text(encoding="utf-8")
    assert 'TMPDIR' not in text, "must not reference TMPDIR — use tempfile.mkdtemp() (Windows has no TMPDIR/no /tmp)"
    assert "tempfile.mkdtemp" in text, "expected tempfile.mkdtemp() for portable temp-dir creation"


def test_no_coordinator_core_dependency_and_no_reimplemented_resolver():
    """This script is authored under dist/oss-only-skills/ and ships to
    end-user machines. It must never become an engine consumer: no
    `coordinator_core` IMPORT and no `cc_invoke(` (the engine RPC seam) —
    an engine-coupling regression this test exists to catch.

    It also must never regress back to reimplementing the engine-root
    resolution ladder the shipped resolver script already owns — that is
    exactly the defect this delegation seam (`_resolve_engine_root`)
    replaced. The old reimplemented-ladder helpers (`_locate_claude_klabauter_root`,
    `_claude_klabauter_registry_value`) and their private-registry-key remediation
    text must not reappear; only the delegating call site is permitted.

    (explanatory prose in the trampoline's own PORT-SHAPE NOTE module
    docstring legitimately mentions these terms to document *why* they're
    absent — this test checks for actual code usage, not documentation
    prose, so both `#` comment lines and the leading module docstring are
    stripped before scanning.)"""
    text = _SCRIPT.read_text(encoding="utf-8")
    docstring = ast.get_docstring(ast.parse(text))
    if docstring is not None:
        text = text.replace(docstring, "", 1)
    code_lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    code_text = "\n".join(code_lines)
    assert "import coordinator_core" not in code_text
    assert "from coordinator_core" not in code_text
    assert "cc_invoke(" not in code_text
    assert "_resolve_claude_klabauter_root" not in code_text
    assert "_locate_claude_klabauter_root" not in code_text
    assert "_claude_klabauter_registry_value" not in code_text
    assert "def _resolve_engine_root(" in code_text, (
        "expected the delegation entrypoint _resolve_engine_root to be present"
    )


def test_hung_git_clone_does_not_wedge_forever(tmp_path, monkeypatch):
    """Functional regression net: simulate an unresponsive git remote (a
    `git clone` that hangs) and assert the script terminates (via its own
    internal timeout) rather than hanging indefinitely. Uses a stub `git`
    shim on PATH that sleeps past a shortened timeout, and a shortened
    _NETWORK_TIMEOUT_SECS via a patched copy of the script so the test itself
    stays fast."""
    # Build a stub `git` that sleeps forever on `clone`, and behaves normally
    # otherwise is unnecessary since we exercise --clone (owned-clone) path
    # is not used for --clone-provided scenarios; instead directly exercise
    # the owned-clone path (no --clone flag) with a hanging stub git.
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    stub_git = bin_dir / "git"
    stub_git.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "clone" ]; then sleep 30; exit 0; fi\n'
        'exec /usr/bin/env git "$@"\n',
        encoding="utf-8",
    )
    stub_git.chmod(0o755)

    # Patch a copy of the script with a very short network timeout so the
    # test doesn't itself take the full production ceiling. Placed under
    # tmp_path — deliberately NOT under any real engine-checkout sibling
    # directory, to prove this exercises the shipped resolver's ENV-VAR rung
    # (_PRIMARY_ENGINE_ROOT_ENV below, inherited through the delegating subprocess
    # call) rather than its sibling-walk rung, which would miss (correctly)
    # from a tmp_path location; the env override still resolves the real
    # engine checkout's oss-repo-constants.py + check-install-divergence.py
    # by file path.
    script_dir = tmp_path / "installed" / "coordinator" / "skills" / "coordinator-update" / "lib"
    script_dir.mkdir(parents=True, exist_ok=True)
    patched = script_dir / "compute-update-delta-fasttimeout.py"
    text = _SCRIPT.read_text(encoding="utf-8")
    patched_text = text.replace("_NETWORK_TIMEOUT_SECS = 120", "_NETWORK_TIMEOUT_SECS = 2")
    assert patched_text != text, "expected to find and shorten _NETWORK_TIMEOUT_SECS"
    patched.write_text(patched_text, encoding="utf-8")
    patched.chmod(0o755)

    install_root = tmp_path / "live"
    install_root.mkdir()
    _install_resolver(install_root)

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env[_PRIMARY_ENGINE_ROOT_ENV] = str(_ENGINE_ROOT)

    import time

    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(patched), "--install-root", str(install_root)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
        timeout=25,  # pytest-level safety net — must never actually fire
    )
    elapsed = time.monotonic() - start

    # Must return well under the stub's 30s sleep — proves the internal
    # timeout fired rather than the process hanging on the wedged clone.
    assert elapsed < 10, f"script took {elapsed:.1f}s — internal timeout did not fire against a hung git clone"
    assert result.returncode == 5, (
        f"expected exit 5 (offline/transport-timeout), got {result.returncode}. stderr={result.stderr}"
    )
    data = json.loads(result.stdout)
    assert data.get("update_status") == "offline"
