"""
tests/project_rag/test_source_probe.py

Unit tests for _probe_source() — covers O32.

Registry format: ~/.project-rag/projects.json with shape:
    {"sources": [{"path": "/abs/path/to/project", "name": "source-name"}, ...]}

The PROJECT_RAG_REGISTRY_PATH env var overrides the default registry path,
so tests always use tmp files and never touch real machine state.

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 6 (O32)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_source_probe_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry) -> None:
    """O32: _probe_source() must return the source name when cwd is under a registered project root."""
    from coordinator_whoami.project_rag.cli import _probe_source

    project_root = tmp_path / "myproject"
    project_root.mkdir()
    mock_registry(project_root, "my-source")

    # Run the probe with cwd = project_root (exact match).
    monkeypatch.chdir(project_root)
    result = _probe_source()
    assert result == "my-source", (
        f"_probe_source() must return 'my-source' when cwd is registered project root, got {result!r}"
    )


def test_source_probe_bound_subdirectory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry) -> None:
    """O32: _probe_source() must return source name when cwd is a SUBDIRECTORY of the registered root."""
    from coordinator_whoami.project_rag.cli import _probe_source

    project_root = tmp_path / "myproject"
    subdir = project_root / "src" / "core"
    subdir.mkdir(parents=True)
    mock_registry(project_root, "sub-source")

    monkeypatch.chdir(subdir)
    result = _probe_source()
    assert result == "sub-source", (
        f"_probe_source() must match when cwd is under registered root, got {result!r}"
    )


def test_source_probe_unbound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry) -> None:
    """O32: _probe_source() must return None when registry exists but no entry covers cwd."""
    from coordinator_whoami.project_rag.cli import _probe_source

    # Register a project root that is NOT a parent of cwd.
    other_root = tmp_path / "other_project"
    other_root.mkdir()
    mock_registry(other_root, "other-source")

    # cwd is tmp_path itself — not under other_root.
    monkeypatch.chdir(tmp_path)
    result = _probe_source()
    assert result is None, (
        f"_probe_source() must return None when cwd not under any registered root, got {result!r}"
    )


def test_source_probe_registry_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O32: _probe_source() must return None without raising when registry does not exist."""
    from coordinator_whoami.project_rag.cli import _probe_source

    # Point to a path that does not exist.
    nonexistent = tmp_path / "no_such_registry.json"
    monkeypatch.setenv("PROJECT_RAG_REGISTRY_PATH", str(nonexistent))
    monkeypatch.chdir(tmp_path)

    result = _probe_source()
    assert result is None, (
        f"_probe_source() must return None when registry absent, got {result!r}"
    )


def test_source_probe_via_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O32: _probe_source() must honour PROJECT_RAG_REGISTRY_PATH env override."""
    from coordinator_whoami.project_rag.cli import _probe_source

    project_root = tmp_path / "env_project"
    project_root.mkdir()

    # Write a custom registry at a non-standard path.
    custom_registry = tmp_path / "custom_registry.json"
    custom_registry.write_text(
        json.dumps({"sources": [{"path": str(project_root), "name": "env-source"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECT_RAG_REGISTRY_PATH", str(custom_registry))
    monkeypatch.chdir(project_root)

    result = _probe_source()
    assert result == "env-source", (
        f"_probe_source() must use PROJECT_RAG_REGISTRY_PATH override, got {result!r}"
    )


def test_source_probe_longest_prefix_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O32: when multiple registry entries cover cwd, the longest (most-specific) path wins."""
    from coordinator_whoami.project_rag.cli import _probe_source

    # Register a parent and a more-specific child root.
    parent_root = tmp_path / "parent"
    child_root = parent_root / "child"
    child_root.mkdir(parents=True)

    custom_registry = tmp_path / "registry.json"
    custom_registry.write_text(
        json.dumps({
            "sources": [
                {"path": str(parent_root), "name": "parent-source"},
                {"path": str(child_root), "name": "child-source"},
            ]
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("PROJECT_RAG_REGISTRY_PATH", str(custom_registry))
    monkeypatch.chdir(child_root)

    result = _probe_source()
    assert result == "child-source", (
        f"Longest prefix must win; expected 'child-source', got {result!r}"
    )


def test_source_probe_malformed_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O32: _probe_source() must return None without raising on malformed JSON registry."""
    from coordinator_whoami.project_rag.cli import _probe_source

    malformed = tmp_path / "bad_registry.json"
    malformed.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("PROJECT_RAG_REGISTRY_PATH", str(malformed))
    monkeypatch.chdir(tmp_path)

    result = _probe_source()
    assert result is None, (
        f"_probe_source() must return None on malformed registry, got {result!r}"
    )


def test_source_probe_registry_unexpected_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O32: _probe_source() must return None when registry uses an unexpected top-level key.

    Writes {"projects": [...]} (wrong key — expected "sources") and asserts None.

    Review: Reviewer B B-F2 — missing "sources" key causes _find_best_registry_entry()
    to return None via the isinstance check on raw.get("sources").
    """
    from coordinator_whoami.project_rag.cli import _probe_source

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

    result = _probe_source()
    assert result is None, (
        f"_probe_source() must return None for unexpected registry schema (wrong top-level key), got {result!r}"
    )
