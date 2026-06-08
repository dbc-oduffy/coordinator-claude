"""
test_atlas_watch_drift.py — pytest unit tests for bin/check-atlas-watch-drift.sh.

Spec backlink: docs/plans/2026-06-04-architecture-audit-atlas-refresh-gate.md § C2
Acceptance: AC7 (shellcheck-clean — checked at dispatch time), AC8 (per-system line),
AC8b (ERROR on non-zero exit), AC8c (MALFORMED on unparseable stdout). Plus the
default-on STALE walk behaviour from the C2 spec.

Isolation: every test builds a fresh fixture git repo under tmp_path with the
expected `docs/architecture/systems/` layout and shells out to the helper via
subprocess.run(["bash", helper_path, ...]).

Negative-spec: tests do NOT touch the real ~/.claude/docs/architecture/systems/
tree or the operator's working tree.
"""

import os
import subprocess
import textwrap
from datetime import date, timedelta

import pytest


_HERE = os.path.dirname(os.path.abspath(__file__))
_HELPER = os.path.normpath(
    os.path.join(_HERE, "..", "bin", "check-atlas-watch-drift.sh")
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _init_repo(root):
    """Initialize a minimal git repo at `root` and return its path as str."""
    root = str(root)
    subprocess.run(["git", "init", "-q", root], check=True)
    # User config so commit-less repos still have a workable git context.
    subprocess.run(
        ["git", "-C", root, "config", "user.email", "test@example.com"], check=True
    )
    subprocess.run(
        ["git", "-C", root, "config", "user.name", "Test"], check=True
    )
    # Review: match C1 pattern (test_atlas_refresh_gate.py:57) — defensive against
    # future test extensions that commit; gpgsign off avoids GPG failures in CI.
    subprocess.run(["git", "-C", root, "config", "commit.gpgsign", "false"], check=True)
    systems = os.path.join(root, "docs", "architecture", "systems")
    os.makedirs(systems, exist_ok=True)
    return root, systems


def _write_atlas(systems_dir, name, last_mapped=None, last_attested=None):
    """Write a minimal atlas .md page with optional frontmatter date fields.

    last_attested is the currency timestamp read by the STALE walk (post
    atlas-attested-clock-split). last_mapped is retained for fixture realism
    but is no longer the staleness signal.
    If last_attested is not provided but last_mapped is, last_attested mirrors
    last_mapped so that existing tests exercise the STALE walk correctly.
    """
    body = ["---"]
    if last_mapped:
        body.append(f"last_mapped: {last_mapped}")
    # Resolve last_attested: explicit arg wins; fall back to mirroring last_mapped.
    attested = last_attested if last_attested is not None else last_mapped
    if attested:
        body.append(f"last_attested: {attested}")
    body.append("---")
    body.append(f"# {name} atlas")
    path = os.path.join(systems_dir, f"{name}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    return path


def _write_watch(systems_dir, name, body):
    """Write a .watch.sh sibling and chmod +x."""
    path = os.path.join(systems_dir, f"{name}.watch.sh")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(path, 0o755)
    return path


def _run_helper(repo_root, *args):
    """Run the helper inside repo_root, return CompletedProcess."""
    return subprocess.run(
        ["bash", _HELPER, *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# AC8 — per-system line emission, mixed .watch.sh presence
# ---------------------------------------------------------------------------


def test_emits_per_system_line(tmp_path):
    """Multiple atlases with mixed .watch.sh presence → one line per system."""
    today = date.today().isoformat()
    repo, systems = _init_repo(tmp_path)

    # System A: has .watch.sh emitting FRESH.
    _write_atlas(systems, "alpha", last_mapped=today)
    _write_watch(
        systems,
        "alpha",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            echo "FRESH alpha skill_count=5"
            """
        ),
    )

    # System B: no .watch.sh → should emit `FRESH <name> (no watch script)`.
    _write_atlas(systems, "bravo", last_mapped=today)

    # System C: has .watch.sh emitting DRIFT.
    _write_atlas(systems, "charlie", last_mapped=today)
    _write_watch(
        systems,
        "charlie",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            echo "DRIFT charlie expected=10 got=7"
            """
        ),
    )

    cp = _run_helper(repo, "--no-stale-walk")
    assert cp.returncode == 0, cp.stderr
    lines = [ln for ln in cp.stdout.splitlines() if ln.strip()]

    assert any(ln == "FRESH alpha skill_count=5" for ln in lines), lines
    assert any(ln == "FRESH bravo (no watch script)" for ln in lines), lines
    assert any(ln == "DRIFT charlie expected=10 got=7" for ln in lines), lines

    # Exactly one line per system (3 atlases → 3 lines with --no-stale-walk).
    assert len(lines) == 3, lines


# ---------------------------------------------------------------------------
# AC8b — non-zero exit → ERROR, never silently FRESH
# ---------------------------------------------------------------------------


def test_nonzero_exit_emits_error(tmp_path):
    """`.watch.sh` exit 1 → `ERROR <system>: ... exit=<N>`; not FRESH."""
    today = date.today().isoformat()
    repo, systems = _init_repo(tmp_path)

    _write_atlas(systems, "delta", last_mapped=today)
    _write_watch(
        systems,
        "delta",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            echo "something" >&2
            exit 1
            """
        ),
    )

    cp = _run_helper(repo, "--no-stale-walk")
    assert cp.returncode == 0, cp.stderr
    lines = [ln for ln in cp.stdout.splitlines() if ln.strip()]
    assert any(ln.startswith("ERROR delta:") and "exit=1" in ln for ln in lines), lines
    # Crucially, no FRESH line for delta.
    assert not any(ln.startswith("FRESH delta") for ln in lines), lines


# ---------------------------------------------------------------------------
# AC8c — malformed stdout → MALFORMED, never silently FRESH
# ---------------------------------------------------------------------------


def test_malformed_stdout_emits_malformed(tmp_path):
    """`.watch.sh` emits garbage → MALFORMED line; not FRESH."""
    today = date.today().isoformat()
    repo, systems = _init_repo(tmp_path)

    _write_atlas(systems, "echo-sys", last_mapped=today)
    _write_watch(
        systems,
        "echo-sys",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            echo "this is not a contract line"
            """
        ),
    )

    cp = _run_helper(repo, "--no-stale-walk")
    assert cp.returncode == 0, cp.stderr
    lines = [ln for ln in cp.stdout.splitlines() if ln.strip()]
    assert any(
        ln.startswith("MALFORMED echo-sys:") for ln in lines
    ), lines
    assert not any(ln.startswith("FRESH echo-sys") for ln in lines), lines


def test_malformed_wrong_system_name_emits_malformed(tmp_path):
    """`.watch.sh` emits a valid-shape line but wrong system name → MALFORMED."""
    today = date.today().isoformat()
    repo, systems = _init_repo(tmp_path)

    _write_atlas(systems, "foxtrot", last_mapped=today)
    _write_watch(
        systems,
        "foxtrot",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            echo "FRESH wrong-name something"
            """
        ),
    )

    cp = _run_helper(repo, "--no-stale-walk")
    assert cp.returncode == 0, cp.stderr
    lines = [ln for ln in cp.stdout.splitlines() if ln.strip()]
    assert any(ln.startswith("MALFORMED foxtrot:") for ln in lines), lines


# ---------------------------------------------------------------------------
# STALE walk default-on (and --no-stale-walk suppression)
# ---------------------------------------------------------------------------


def test_stale_walk_default_on(tmp_path):
    """Old last_attested → STALE line by default; --no-stale-walk suppresses it."""
    repo, systems = _init_repo(tmp_path)

    old_date = (date.today() - timedelta(days=90)).isoformat()
    _write_atlas(systems, "golf", last_mapped=old_date)
    # No .watch.sh — so the only signals are FRESH (no watch script) + STALE.

    # Default: STALE walk runs.
    cp_default = _run_helper(repo)
    assert cp_default.returncode == 0, cp_default.stderr
    lines_default = [ln for ln in cp_default.stdout.splitlines() if ln.strip()]
    assert any(
        ln.startswith("STALE golf") and f"last_attested={old_date}" in ln and "age=" in ln
        for ln in lines_default
    ), lines_default

    # Suppressed: --no-stale-walk drops STALE lines entirely.
    cp_off = _run_helper(repo, "--no-stale-walk")
    assert cp_off.returncode == 0, cp_off.stderr
    lines_off = [ln for ln in cp_off.stdout.splitlines() if ln.strip()]
    assert not any(ln.startswith("STALE ") for ln in lines_off), lines_off


def test_stale_walk_threshold_configurable(tmp_path):
    """--stale-days N raises the threshold (canonical flag; legacy alias still accepted)."""
    repo, systems = _init_repo(tmp_path)

    age_days = 45
    aged = (date.today() - timedelta(days=age_days)).isoformat()
    _write_atlas(systems, "hotel", last_mapped=aged)

    # Threshold 30 (default): 45d > 30d → STALE.
    cp_default = _run_helper(repo)
    lines_default = [ln for ln in cp_default.stdout.splitlines() if ln.strip()]
    assert any(ln.startswith("STALE hotel") for ln in lines_default), lines_default

    # Threshold 60 via canonical flag: 45d < 60d → no STALE.
    cp_high = _run_helper(repo, "--stale-days", "60")
    lines_high = [ln for ln in cp_high.stdout.splitlines() if ln.strip()]
    assert not any(ln.startswith("STALE hotel") for ln in lines_high), lines_high

    # Legacy alias still works (back-compat for any pre-2026-06-08 caller).
    cp_legacy = _run_helper(repo, "--last-mapped-stale-days", "60")
    lines_legacy = [ln for ln in cp_legacy.stdout.splitlines() if ln.strip()]
    assert not any(ln.startswith("STALE hotel") for ln in lines_legacy), lines_legacy


# ---------------------------------------------------------------------------
# Always exit 0 (informational contract)
# ---------------------------------------------------------------------------


def test_always_exits_zero_even_with_failures(tmp_path):
    """Mixed ERROR + MALFORMED + STALE → still exits 0."""
    repo, systems = _init_repo(tmp_path)
    old_date = (date.today() - timedelta(days=100)).isoformat()

    _write_atlas(systems, "india", last_mapped=old_date)
    _write_watch(
        systems,
        "india",
        "#!/usr/bin/env bash\nexit 2\n",
    )

    cp = _run_helper(repo)
    assert cp.returncode == 0
