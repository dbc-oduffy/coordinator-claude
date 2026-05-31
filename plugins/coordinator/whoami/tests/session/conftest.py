"""Shared pytest fixtures for coordinator_whoami.session tests.

Spec backlink: archive/specs/2026-05-27-whoami-session-spine-refactor.md § C2 test surface
"""
from __future__ import annotations

from pathlib import Path
import pytest


@pytest.fixture()
def fake_git_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal coordinator-onboarded repo structure in tmp_path.

    Creates:
      tasks/            — coordinator task-management surface
      CLAUDE.md         — coordinator anchor (satisfies has_tracker check)
      tasks/handoffs/   — for query-records to scan

    Does NOT create a real git repo (no .git) — tests that need git state
    mock _run_git / _git_root directly.
    """
    root = tmp_path / "fake_repo"
    root.mkdir()
    (root / "tasks").mkdir()
    (root / "tasks" / "handoffs").mkdir()
    (root / "CLAUDE.md").write_text("# fake coordinator root\n", encoding="utf-8")
    return root


@pytest.fixture()
def fake_orientation_cache(fake_git_root: Path) -> Path:
    """Write a tasks/orientation_cache.md with a known git_head_at_generation."""
    cache = fake_git_root / "tasks" / "orientation_cache.md"
    cache.write_text(
        "---\ngit_head_at_generation: abc123def456\n---\n\n# Orientation cache\n",
        encoding="utf-8",
    )
    return cache
