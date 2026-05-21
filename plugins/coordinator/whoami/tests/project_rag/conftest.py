"""Shared pytest fixtures for coordinator_whoami.project_rag tests.

Provides:
  fresh_env    — monkeypatch HOME/USERPROFILE/CLAUDE_HOME to a bare tmpdir
                 (also available as tmp_home alias for backward compat).
  mock_subprocess_run — patch subprocess.run for nvidia-smi calls in _probe_gpu.
  mock_registry — write a controllable ~/.project-rag/projects.json with a
                  single bound project entry.

Helpers (non-fixture):
  _load_cli_schema() — load cli_output.v1.json from package-vendored location.

Review: Reviewer B B-F5 — consolidated fresh_env here (was duplicated in
  test_cli_schema.py and test_envelope_conformance.py); yield-based form.
Review: Reviewer B B-F10 — moved _load_cli_schema() helper here to eliminate
  duplication between test_cli_schema.py and test_envelope_conformance.py.

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 6
"""
from __future__ import annotations

import importlib.resources
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _load_cli_schema() -> dict:
    """Load cli_output.v1.json from the package-vendored location.

    Review: Reviewer B B-F10 — canonical location; avoids duplication between
    test_cli_schema.py and test_envelope_conformance.py.
    """
    return json.loads(
        importlib.resources.files("coordinator_whoami.project_rag.schemas")
        .joinpath("cli_output.v1.json")
        .read_text(encoding="utf-8")
    )


@pytest.fixture()
def fresh_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect HOME/USERPROFILE/CLAUDE_HOME to a bare tmpdir.

    Guarantees no ~/.claude.json, no coordinator plugin, no .venv adjacent to
    any pyproject.toml, and no project-rag registry. CLAUDE_HOME is also set
    so _probe_claude() sees the empty sandbox rather than the developer's real
    ~/.claude.json.

    Review: Reviewer B B-F5 — canonical yield-based fixture; duplicates in
    test_cli_schema.py and test_envelope_conformance.py removed.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("CLAUDE_HOME", str(home))
    # Ensure the project-rag registry does NOT exist by default.
    monkeypatch.delenv("PROJECT_RAG_REGISTRY_PATH", raising=False)
    yield home


# Backward-compat alias — tests that request tmp_home still work.
tmp_home = fresh_env


@pytest.fixture()
def mock_subprocess_run(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch subprocess.run so nvidia-smi calls don't hit real hardware.

    By default the mock simulates nvidia-smi not found (FileNotFoundError),
    so _probe_gpu() returns present=False. Individual tests may reconfigure
    the mock's side_effect or return_value to simulate NVIDIA GPUs.
    """
    import subprocess

    mock = MagicMock(side_effect=FileNotFoundError("nvidia-smi not found"))
    monkeypatch.setattr(subprocess, "run", mock)
    return mock


@pytest.fixture()
def mock_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a controllable ~/.project-rag/projects.json registry.

    Returns a factory callable: `mock_registry(project_root, name)` writes a
    registry entry so that _probe_source() / _resolve_bound_project_root()
    can find the bound project. The PROJECT_RAG_REGISTRY_PATH env var is set
    to the tmp registry file so tests do not depend on a real ~/.project-rag/.

    Usage:
        def test_something(tmp_path, mock_registry):
            project_root = tmp_path / "myproject"
            project_root.mkdir()
            mock_registry(project_root, "my-source")
            # Now _probe_source() from cwd=project_root returns "my-source".
    """
    registry_file = tmp_path / "projects.json"

    # Start with an empty registry.
    registry_file.write_text(json.dumps({"sources": []}), encoding="utf-8")
    monkeypatch.setenv("PROJECT_RAG_REGISTRY_PATH", str(registry_file))

    def _add_entry(project_root: Path, name: str) -> None:
        existing = json.loads(registry_file.read_text(encoding="utf-8"))
        existing["sources"].append({"path": str(project_root), "name": name})
        registry_file.write_text(json.dumps(existing), encoding="utf-8")

    return _add_entry
