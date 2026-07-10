"""
tests/project_rag/test_engine_version_probe.py

Unit tests for _probe_engine_version() — covers O33.

The probe:
  1. Resolves the bound project root via the source registry.
  2. Looks for a .uproject file at that root.
  3. Reads EngineAssociation from the .uproject JSON.
  4. Returns null on: no bound source, no .uproject, missing key, JSON error, any exception.

All tests use the PROJECT_RAG_REGISTRY_PATH env override (via mock_registry fixture
from conftest.py) so no real machine registry is touched.

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 6 (O33)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_engine_version_probe_ue_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry
) -> None:
    """O33: _probe_engine_version() must return the EngineAssociation for a UE project."""
    from coordinator_whoami.project_rag.cli import _probe_engine_version

    project_root = tmp_path / "MyUEProject"
    project_root.mkdir()

    # Write a .uproject file with EngineAssociation.
    uproject = project_root / "MyUEProject.uproject"
    uproject.write_text(
        json.dumps({
            "FileVersion": 3,
            "EngineAssociation": "5.3",
            "Category": "",
            "Description": "",
        }),
        encoding="utf-8",
    )

    mock_registry(project_root, "my-ue-project")
    monkeypatch.chdir(project_root)

    result = _probe_engine_version()
    assert result == "5.3", (
        f"_probe_engine_version() must return '5.3', got {result!r}"
    )


def test_engine_version_probe_non_ue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry
) -> None:
    """O33: _probe_engine_version() must return None when bound project has no .uproject."""
    from coordinator_whoami.project_rag.cli import _probe_engine_version

    project_root = tmp_path / "python_project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        '[project]\nname = "myproject"\n', encoding="utf-8"
    )
    # No .uproject file.

    mock_registry(project_root, "python-source")
    monkeypatch.chdir(project_root)

    result = _probe_engine_version()
    assert result is None, (
        f"_probe_engine_version() must return None for non-UE project, got {result!r}"
    )


def test_engine_version_probe_no_engine_association(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry
) -> None:
    """O33: _probe_engine_version() must return None when .uproject lacks EngineAssociation key."""
    from coordinator_whoami.project_rag.cli import _probe_engine_version

    project_root = tmp_path / "NoAssocProject"
    project_root.mkdir()

    # .uproject without EngineAssociation.
    uproject = project_root / "NoAssocProject.uproject"
    uproject.write_text(
        json.dumps({"FileVersion": 3, "Category": ""}),
        encoding="utf-8",
    )

    mock_registry(project_root, "no-assoc-source")
    monkeypatch.chdir(project_root)

    result = _probe_engine_version()
    assert result is None, (
        f"_probe_engine_version() must return None when EngineAssociation absent, got {result!r}"
    )


def test_engine_version_probe_unbound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O33: _probe_engine_version() must return None when no source is bound (no registry)."""
    from coordinator_whoami.project_rag.cli import _probe_engine_version

    # Point to a non-existent registry.
    nonexistent = tmp_path / "no_registry.json"
    monkeypatch.setenv("PROJECT_RAG_REGISTRY_PATH", str(nonexistent))
    monkeypatch.chdir(tmp_path)

    result = _probe_engine_version()
    assert result is None, (
        f"_probe_engine_version() must return None when no registry, got {result!r}"
    )


def test_engine_version_probe_malformed_uproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry
) -> None:
    """O33: _probe_engine_version() must return None without raising on malformed .uproject JSON."""
    from coordinator_whoami.project_rag.cli import _probe_engine_version

    project_root = tmp_path / "BadUProject"
    project_root.mkdir()

    # Write a malformed .uproject.
    uproject = project_root / "BadUProject.uproject"
    uproject.write_text("{not valid json", encoding="utf-8")

    mock_registry(project_root, "bad-uproject-source")
    monkeypatch.chdir(project_root)

    result = _probe_engine_version()
    assert result is None, (
        f"_probe_engine_version() must return None on malformed .uproject, got {result!r}"
    )


def test_engine_version_probe_registry_unexpected_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O33: _probe_engine_version() must return None when registry uses unexpected top-level key.

    Writes {"projects": [...]} (wrong key — expected "sources") and asserts None.

    Review: Reviewer B B-F2 — parallel to test_source_probe_registry_unexpected_schema;
    both probes delegate to _find_best_registry_entry() which validates "sources" key.
    """
    from coordinator_whoami.project_rag.cli import _probe_engine_version

    project_root = tmp_path / "myproject"
    project_root.mkdir()
    # Wrong top-level key: "projects" instead of "sources"
    wrong_schema = tmp_path / "wrong_schema.json"
    wrong_schema.write_text(
        json.dumps({"projects": [{"path": str(project_root), "name": "x"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECT_RAG_REGISTRY_PATH", str(wrong_schema))
    monkeypatch.chdir(project_root)

    result = _probe_engine_version()
    assert result is None, (
        f"_probe_engine_version() must return None for unexpected registry schema, got {result!r}"
    )


def test_engine_version_probe_empty_engine_association(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry
) -> None:
    """O33: _probe_engine_version() must return None when EngineAssociation is an empty string."""
    from coordinator_whoami.project_rag.cli import _probe_engine_version

    project_root = tmp_path / "EmptyAssocProject"
    project_root.mkdir()

    uproject = project_root / "EmptyAssocProject.uproject"
    uproject.write_text(
        json.dumps({"FileVersion": 3, "EngineAssociation": ""}),
        encoding="utf-8",
    )

    mock_registry(project_root, "empty-assoc-source")
    monkeypatch.chdir(project_root)

    result = _probe_engine_version()
    # An empty EngineAssociation string is not a valid UE version identifier and must degrade to null.
    # Review: Reviewer B B-F11 — replaced WHAT-comment (explaining or-None idiom) with WHY-comment.
    assert result is None, (
        f"_probe_engine_version() must return None for empty EngineAssociation, got {result!r}"
    )
