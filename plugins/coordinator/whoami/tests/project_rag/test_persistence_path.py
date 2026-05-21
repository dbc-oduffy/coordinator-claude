"""
tests/project_rag/test_persistence_path.py

Tests for persist() in coordinator_whoami.project_rag.envelope (envelope-shaped output).
Covers O7, O28, O30.

Rewired from cli.py:persist() → envelope.py:persist() per Task 4 migration completion.
whoami_profile now stores the ENVELOPE shape (contract_version, plugin_name, binding,
status, extras), not the legacy 12-key flat compose() output.

Review: Reviewer A A-F2 / Reviewer B B-F1 / B-F6 — rewrite persistence tests to import
from envelope.py and assert envelope shape; drop stale TODO comments.

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 6 (O7, O28, O30)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_home_with_claude_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a tmp home and redirect HOME/USERPROFILE so persist() writes there.

    Also unsets PROJECT_RAG_REGISTRY_PATH so new probes degrade gracefully.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("CLAUDE_HOME", str(home))
    monkeypatch.delenv("PROJECT_RAG_REGISTRY_PATH", raising=False)
    return home


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_persist_writes_to_install_profile_json(
    tmp_home_with_claude_dir: Path,
) -> None:
    """O28: persist() must write to ~/.claude/project-rag/install-profile.json.

    Verifies:
    - The file is created at the expected path.
    - The file is valid JSON.
    - A 'whoami_profile' sub-key exists and is a dict.
    - whoami_profile is envelope-shaped: contract_version, plugin_name, binding,
      status, extras all present.
    - extras.project_rag.envelope_version == 1 (envelope-version field present).
    """
    # Review: Reviewer A A-F2 — import from envelope, not cli; assert envelope shape
    from coordinator_whoami.project_rag.envelope import compose_envelope, persist

    envelope = compose_envelope()
    written_path = persist(envelope)

    # Verify path matches DR-9 convention.
    home = tmp_home_with_claude_dir
    expected_path = home / ".claude" / "project-rag" / "install-profile.json"
    assert written_path == expected_path, (
        f"persist() must write to {expected_path}, wrote to {written_path}"
    )
    assert written_path.exists(), f"install-profile.json not created at {written_path}"

    # Verify content is valid JSON.
    content = json.loads(written_path.read_text(encoding="utf-8"))
    assert isinstance(content, dict)

    # Verify whoami_profile sub-key exists and is envelope-shaped.
    assert "whoami_profile" in content, "install-profile.json must contain 'whoami_profile' key"
    wp = content["whoami_profile"]
    assert isinstance(wp, dict), f"whoami_profile must be a dict, got {type(wp)}"

    # Envelope shape assertions (Task 4 contract).
    assert wp.get("contract_version") == 1, (
        f"whoami_profile.contract_version must be 1, got {wp.get('contract_version')!r}"
    )
    assert wp.get("plugin_name") == "project-rag", (
        f"whoami_profile.plugin_name must be 'project-rag', got {wp.get('plugin_name')!r}"
    )
    assert "binding" in wp, "whoami_profile must include 'binding' key"
    assert "status" in wp, "whoami_profile must include 'status' key"
    assert "extras" in wp, "whoami_profile must include 'extras' key"
    assert wp["extras"].get("project_rag", {}).get("envelope_version") == 1, (
        "whoami_profile.extras.project_rag.envelope_version must be 1"
    )


def test_persist_merges_with_existing_content(
    tmp_home_with_claude_dir: Path,
) -> None:
    """O7: persist() must merge with existing install-profile.json content, not overwrite.

    Writes a file with 'other_key', calls persist(), verifies 'other_key' survives.
    whoami_profile is envelope-shaped post-Task-4.
    """
    # Review: Reviewer A A-F2 — import from envelope, not cli; assert envelope shape
    from coordinator_whoami.project_rag.envelope import compose_envelope, persist
    from coordinator_whoami.project_rag._paths import resolve_user_marker_dir

    # Pre-write a file with an existing key.
    user_dir = resolve_user_marker_dir()
    user_dir.mkdir(parents=True, exist_ok=True)
    profile_path = user_dir / "install-profile.json"
    profile_path.write_text(
        json.dumps({"other_key": "should_survive", "unrelated_data": [1, 2, 3]}),
        encoding="utf-8",
    )

    # Run persist().
    envelope = compose_envelope()
    persist(envelope)

    # Verify existing key survived.
    content = json.loads(profile_path.read_text(encoding="utf-8"))
    assert "other_key" in content, "persist() must not overwrite existing keys"
    assert content["other_key"] == "should_survive", (
        f"other_key was overwritten; expected 'should_survive', got {content['other_key']!r}"
    )
    assert "unrelated_data" in content, "unrelated_data must survive merge"

    # Verify whoami_profile was written in envelope shape.
    assert "whoami_profile" in content, "persist() must write 'whoami_profile' key"
    wp = content["whoami_profile"]
    assert wp.get("contract_version") == 1, "whoami_profile must be envelope-shaped (contract_version=1)"
    assert wp.get("plugin_name") == "project-rag", "whoami_profile must carry plugin_name"
    assert "binding" in wp and "status" in wp, "whoami_profile must carry binding + status"


def test_persist_returns_path_object(tmp_home_with_claude_dir: Path) -> None:
    """persist() must return a Path object pointing to the written file."""
    from coordinator_whoami.project_rag.envelope import compose_envelope, persist

    envelope = compose_envelope()
    result = persist(envelope)
    assert isinstance(result, Path), (
        f"persist() must return a Path, got {type(result)}"
    )


def test_persist_creates_parent_directories(tmp_home_with_claude_dir: Path) -> None:
    """O28: persist() must create ~/.claude/project-rag/ if it doesn't exist."""
    from coordinator_whoami.project_rag.envelope import compose_envelope, persist

    home = tmp_home_with_claude_dir
    marker_dir = home / ".claude" / "project-rag"
    # Ensure the directory does NOT exist before calling persist().
    assert not marker_dir.exists(), (
        f"Test setup: {marker_dir} must not exist before persist()"
    )

    envelope = compose_envelope()
    persist(envelope)

    assert marker_dir.exists(), (
        f"persist() must create parent directories at {marker_dir}"
    )


def test_persist_idempotent_second_call(tmp_home_with_claude_dir: Path) -> None:
    """Calling persist() twice should update whoami_profile without destroying content."""
    from coordinator_whoami.project_rag.envelope import compose_envelope, persist

    envelope1 = compose_envelope()
    persist(envelope1)

    envelope2 = compose_envelope()
    persist(envelope2)

    from coordinator_whoami.project_rag._paths import resolve_user_marker_dir
    profile_path = resolve_user_marker_dir() / "install-profile.json"
    content = json.loads(profile_path.read_text(encoding="utf-8"))

    assert "whoami_profile" in content
    wp = content["whoami_profile"]
    assert isinstance(wp, dict)
    assert wp.get("contract_version") == 1


def test_persist_captured_at_top_level(tmp_home_with_claude_dir: Path) -> None:
    """O8: persist() must write captured_at at the install-profile.json top level."""
    from coordinator_whoami.project_rag.envelope import compose_envelope, persist

    envelope = compose_envelope()
    persist(envelope)

    from coordinator_whoami.project_rag._paths import resolve_user_marker_dir
    profile_path = resolve_user_marker_dir() / "install-profile.json"
    content = json.loads(profile_path.read_text(encoding="utf-8"))

    assert "captured_at" in content, (
        "install-profile.json top level must include 'captured_at'"
    )
    assert isinstance(content["captured_at"], str)
    assert "T" in content["captured_at"], (
        f"captured_at must be ISO 8601, got {content['captured_at']!r}"
    )


def test_persist_recovers_from_corrupt_existing_json(
    tmp_home_with_claude_dir: Path,
) -> None:
    """O28: persist() must recover gracefully from a corrupt existing JSON file.

    Writes invalid JSON to the profile path, calls persist(), asserts no exception
    is raised and whoami_profile key is present in the output.

    Review: Reviewer B B-F8 — tests envelope.py:persist() crash-safety on corrupt JSON.
    """
    from coordinator_whoami.project_rag.envelope import compose_envelope, persist
    from coordinator_whoami.project_rag._paths import resolve_user_marker_dir

    user_dir = resolve_user_marker_dir()
    user_dir.mkdir(parents=True, exist_ok=True)
    profile_path = user_dir / "install-profile.json"
    # Write corrupt JSON — must NOT cause persist() to raise.
    profile_path.write_text("{not valid json", encoding="utf-8")

    envelope = compose_envelope()
    # Should not raise despite corrupt existing content.
    written_path = persist(envelope)

    content = json.loads(written_path.read_text(encoding="utf-8"))
    assert "whoami_profile" in content, (
        "persist() must write whoami_profile key even when recovering from corrupt JSON"
    )


def test_resolve_user_marker_dir_matches_dr9_path(tmp_home_with_claude_dir: Path) -> None:
    """O30: resolve_user_marker_dir() must return ~/.claude/project-rag/ (DR-9 path)."""
    from coordinator_whoami.project_rag._paths import resolve_user_marker_dir

    home = tmp_home_with_claude_dir
    expected = home / ".claude" / "project-rag"
    result = resolve_user_marker_dir()
    assert result == expected, (
        f"resolve_user_marker_dir() must return {expected}, got {result}"
    )
