"""
tests/project_rag/test_project_kind_probe.py

Unit tests for _probe_project_kind() — covers O34.

The probe:
  1. Resolves the bound project root via the source registry.
  2. Branches on file markers at that root:
       .uproject present          → "ue"
       pyproject.toml or requirements.txt → "python"
       package.json               → "typescript"
       else                       → null
  3. Returns null when no source is bound or on any exception.

All tests use the PROJECT_RAG_REGISTRY_PATH env override (via mock_registry fixture)
so no real machine registry is touched.

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 6 (O34)
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_project_kind_ue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry
) -> None:
    """O34: _probe_project_kind() must return 'ue' when .uproject is present at project root."""
    from coordinator_whoami.project_rag.cli import _probe_project_kind

    project_root = tmp_path / "UEProject"
    project_root.mkdir()
    (project_root / "UEProject.uproject").write_text("{}", encoding="utf-8")

    mock_registry(project_root, "ue-source")
    monkeypatch.chdir(project_root)

    result = _probe_project_kind()
    assert result == "ue", (
        f"_probe_project_kind() must return 'ue' when .uproject present, got {result!r}"
    )


def test_project_kind_python_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry
) -> None:
    """O34: _probe_project_kind() must return 'python' when pyproject.toml is present."""
    from coordinator_whoami.project_rag.cli import _probe_project_kind

    project_root = tmp_path / "PyProject"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        '[project]\nname = "myproject"\n', encoding="utf-8"
    )

    mock_registry(project_root, "python-source")
    monkeypatch.chdir(project_root)

    result = _probe_project_kind()
    assert result == "python", (
        f"_probe_project_kind() must return 'python' for pyproject.toml, got {result!r}"
    )


def test_project_kind_python_requirements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry
) -> None:
    """O34: _probe_project_kind() must return 'python' when requirements.txt is present."""
    from coordinator_whoami.project_rag.cli import _probe_project_kind

    project_root = tmp_path / "ReqsProject"
    project_root.mkdir()
    (project_root / "requirements.txt").write_text(
        "requests>=2.28\n", encoding="utf-8"
    )

    mock_registry(project_root, "reqs-source")
    monkeypatch.chdir(project_root)

    result = _probe_project_kind()
    assert result == "python", (
        f"_probe_project_kind() must return 'python' for requirements.txt, got {result!r}"
    )


def test_project_kind_typescript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry
) -> None:
    """O34: _probe_project_kind() must return 'typescript' when package.json is present."""
    from coordinator_whoami.project_rag.cli import _probe_project_kind

    project_root = tmp_path / "TSProject"
    project_root.mkdir()
    (project_root / "package.json").write_text(
        '{"name": "myapp", "version": "1.0.0"}\n', encoding="utf-8"
    )

    mock_registry(project_root, "ts-source")
    monkeypatch.chdir(project_root)

    result = _probe_project_kind()
    assert result == "typescript", (
        f"_probe_project_kind() must return 'typescript' for package.json, got {result!r}"
    )


def test_project_kind_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry
) -> None:
    """O34: _probe_project_kind() must return None when project root has no recognised markers."""
    from coordinator_whoami.project_rag.cli import _probe_project_kind

    project_root = tmp_path / "EmptyProject"
    project_root.mkdir()
    # No .uproject, no pyproject.toml, no requirements.txt, no package.json.

    mock_registry(project_root, "empty-source")
    monkeypatch.chdir(project_root)

    result = _probe_project_kind()
    assert result is None, (
        f"_probe_project_kind() must return None for empty project, got {result!r}"
    )


def test_project_kind_unbound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O34: _probe_project_kind() must return None when no source is bound (no registry)."""
    from coordinator_whoami.project_rag.cli import _probe_project_kind

    nonexistent = tmp_path / "no_registry.json"
    monkeypatch.setenv("PROJECT_RAG_REGISTRY_PATH", str(nonexistent))
    monkeypatch.chdir(tmp_path)

    result = _probe_project_kind()
    assert result is None, (
        f"_probe_project_kind() must return None when no registry, got {result!r}"
    )


def test_project_kind_ue_takes_priority_over_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry
) -> None:
    """O34: .uproject must take priority over pyproject.toml when both are present."""
    from coordinator_whoami.project_rag.cli import _probe_project_kind

    project_root = tmp_path / "UEWithPython"
    project_root.mkdir()
    # Both .uproject AND pyproject.toml — UE wins because it's checked first.
    (project_root / "UEWithPython.uproject").write_text("{}", encoding="utf-8")
    (project_root / "pyproject.toml").write_text(
        '[project]\nname = "myproject"\n', encoding="utf-8"
    )

    mock_registry(project_root, "ue-wins-source")
    monkeypatch.chdir(project_root)

    result = _probe_project_kind()
    assert result == "ue", (
        f".uproject must take priority; expected 'ue', got {result!r}"
    )


def test_project_kind_valid_enum_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_registry
) -> None:
    """O34: each scenario must return the exact expected enum value (ue, python, typescript, null).

    Review: Reviewer B B-F9 — strengthened from `result in valid_kinds` to exact
    per-scenario assertion; the weak form would accept e.g. "ue" when "python" is expected.
    """
    from coordinator_whoami.project_rag.cli import _probe_project_kind

    # Maps scenario label → (file-setup lambda, exact expected return value)
    expected: dict[str, str | None] = {
        "ue": "ue",
        "python": "python",
        "typescript": "typescript",
        "null": None,
    }

    scenarios = [
        ("ue", lambda r: (r / "P.uproject").write_text("{}", encoding="utf-8")),
        ("python", lambda r: (r / "pyproject.toml").write_text("[project]\n", encoding="utf-8")),
        ("typescript", lambda r: (r / "package.json").write_text("{}", encoding="utf-8")),
        ("null", lambda r: None),  # no file written → null
    ]

    for label, setup_fn in scenarios:
        project_root = tmp_path / f"kind_{label}"
        project_root.mkdir(exist_ok=True)
        setup_fn(project_root)
        mock_registry(project_root, f"source-{label}")
        monkeypatch.chdir(project_root)

        result = _probe_project_kind()
        assert result == expected[label], (
            f"Scenario '{label}': expected {expected[label]!r}, got {result!r}"
        )
