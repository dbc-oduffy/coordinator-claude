"""
tests/project_rag/test_standalone_import.py

Covers Task 5 cross-package import guard and O29 (no heavy deps at import time).

Tests that depend on Task 5's addons.py are import-guarded with pytest.importorskip.
The no-heavy-deps test (test_no_heavy_deps_at_import_time) runs NOW — it uses a
subprocess to verify that importing coordinator_whoami does not pull torch/numpy/
pandas/chromadb/sentence_transformers into sys.modules.

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 6 (O29, Task 5)
"""
from __future__ import annotations

import subprocess
import sys

import pytest


# ---------------------------------------------------------------------------
# O29 — no heavy deps at import time (runs now)
# ---------------------------------------------------------------------------

def test_no_heavy_deps_at_import_time() -> None:
    """O29: importing coordinator_whoami must not pull torch/numpy/pandas/chromadb/sentence_transformers.

    Runs in a subprocess to get a clean sys.modules state, unaffected by this
    test session's already-imported modules.
    """
    import os
    from pathlib import Path

    # Locate the whoami/ package root so the subprocess can find coordinator_whoami.
    import coordinator_whoami as _cw_pkg
    pkg_parent = str(Path(_cw_pkg.__file__).parent.parent)

    env = os.environ.copy()
    existing_pypath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (pkg_parent + os.pathsep + existing_pypath).strip(os.pathsep)

    check_script = (
        "import coordinator_whoami; "
        "import coordinator_whoami.project_rag.cli; "
        "import sys; "
        "heavy = ['torch', 'numpy', 'pandas', 'chromadb', 'sentence_transformers']; "
        "found = [m for m in heavy if m in sys.modules]; "
        "assert not found, f'Heavy deps imported at import time: {found}'"
    )
    result = subprocess.run(
        [sys.executable, "-c", check_script],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,  # Review: Reviewer B B-F4 — add timeout to prevent hangs in CI
    )
    assert result.returncode == 0, (
        f"Heavy-dep check failed.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )


def test_import_coordinator_whoami_succeeds() -> None:
    """coordinator_whoami must be importable as a package without error."""
    try:
        import coordinator_whoami  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"import coordinator_whoami raised ImportError: {exc}")


def test_import_coordinator_whoami_project_rag_cli_succeeds() -> None:
    """coordinator_whoami.project_rag.cli must be importable without error."""
    try:
        import coordinator_whoami.project_rag.cli  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"import coordinator_whoami.project_rag.cli raised ImportError: {exc}")


def test_import_without_project_rag_core_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """coordinator_whoami must be importable even when project-rag core modules are absent.

    Removes any core.* modules from sys.modules to simulate a standalone
    environment where project-rag's full module tree is not on sys.path.
    """
    # Remove any core.* modules that may have been imported in this session.
    core_keys = [k for k in sys.modules if k == "core" or k.startswith("core.")]
    for key in core_keys:
        monkeypatch.delitem(sys.modules, key, raising=False)

    # The CLI itself tries `from core.addon_discovery import ...` inside
    # _collect_addon_blocks(), but that import is guarded in a try/except.
    # Importing the module at top level must not raise.
    try:
        # Force a fresh import by removing it from modules cache if present.
        monkeypatch.delitem(sys.modules, "coordinator_whoami.project_rag.cli", raising=False)
        import coordinator_whoami.project_rag.cli  # noqa: F401
    except ImportError as exc:
        pytest.fail(
            f"coordinator_whoami.project_rag.cli import failed when core.* absent: {exc}"
        )


# ---------------------------------------------------------------------------
# Task 5 import guard — addons.py (SKIP until Task 5 lands)
# ---------------------------------------------------------------------------

def test_import_coordinator_whoami_project_rag_addons() -> None:
    """coordinator_whoami.project_rag.addons must be importable and expose collect_addon_blocks.

    Review: Reviewer A A-F5 — Task 5 has landed; remove importorskip and promote to
    a real callable-shape assertion.
    """
    from coordinator_whoami.project_rag.addons import collect_addon_blocks
    assert callable(collect_addon_blocks), (
        "coordinator_whoami.project_rag.addons.collect_addon_blocks must be callable"
    )
