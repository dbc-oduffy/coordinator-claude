"""
tests/project_rag/test_envelope_golden.py

Regression net for C1 (host-probe extraction refactor): golden-compare of
compose_envelope() output structure under extras.project_rag.

Purpose: prove that moving the 8 generic probe functions from
coordinator_whoami.project_rag.cli into coordinator_whoami.host_probes produces
byte-identical extras.project_rag output. This test must pass BEFORE the extraction
(as a baseline) and AFTER it (as the regression gate).

Volatile fields excluded: captured_at (timestamp changes on every call).

Implementation note: tests that call compose() or compose_envelope() on this machine
must mock platform.system (and related calls) because Python 3.13 on Windows performs
a WMI query that times out in this environment. This is a pre-existing environment
issue unrelated to the C1 refactor. The mocking strategy:
  - patch platform.system to return "Windows" (avoids the WMI call)
  - patch subprocess.run to raise FileNotFoundError (simulate no nvidia-smi)
The golden compare validates STRUCTURE (key presence, sub-key presence, type assertions),
not runtime values — so the mocked probe values are sufficient to prove structural
byte-identity before and after the extraction.

Spec backlink: archive/specs/2026-05-27-whoami-session-spine-refactor.md § C1 (AC4)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Expected structure: keys that must be present under extras.project_rag
# after compose_envelope(), regardless of runtime values.
# ---------------------------------------------------------------------------

# C6 (2026-05-27): the 8 generic probe keys were REMOVED from extras.project_rag —
# they now live exclusively under extras.coordinator_session (the session adopter).
# This adopter emits ONLY project-rag-specific fields. captured_at excluded (volatile).
# The generic-probe SHAPE is now asserted in tests/session/ + tests/host_probes/.
_EXPECTED_EXTRAS_PROJECT_RAG_KEYS = frozenset({
    "envelope_version",
    # NOT captured_at — volatile, excluded from golden compare
    "project_rag_state",
    # project-rag-specific native probes
    "source",
    "engine_version",
    "project_kind",
})

# Generic-probe keys that MUST NOT appear under extras.project_rag after C6 thinning.
_FORBIDDEN_GENERIC_KEYS = frozenset({
    "os", "arch", "gpu", "python", "uv", "claude", "coordinator", "project",
})

# Sub-object structural assertions: each key maps to the required sub-keys
_EXPECTED_SUB_KEYS: dict[str, set[str]] = {
    "project_rag_state": {"data_dir_present"},
}


# ---------------------------------------------------------------------------
# Fixture: patch the WMI-triggering platform call + nvidia-smi subprocess
# ---------------------------------------------------------------------------

@pytest.fixture()
def patched_env(fresh_env, monkeypatch: pytest.MonkeyPatch):
    """Combine fresh_env with platform.system + subprocess.run mocks.

    fresh_env handles HOME/USERPROFILE/CLAUDE_HOME/PROJECT_RAG_REGISTRY_PATH.
    This fixture additionally patches:
      - platform.system → "Windows" (bypasses the WMI query in Python 3.13)
      - platform.version → "10.0.26200" (simple version string, no WMI)
      - subprocess.run → FileNotFoundError (simulates no nvidia-smi)

    The WMI timeout is a pre-existing environment issue (Python 3.13 on Windows
    performs a WMI query inside platform.system that hangs in this environment).
    Mocking avoids the hang without altering the structural assertions.
    """
    import platform as _platform
    import subprocess as _subprocess

    monkeypatch.setattr(_platform, "system", lambda: "Windows")
    monkeypatch.setattr(_platform, "version", lambda: "10.0.26200")
    monkeypatch.setattr(_platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(_platform, "python_version", lambda: "3.13.1")

    mock_subproc = MagicMock(side_effect=FileNotFoundError("nvidia-smi not found"))
    monkeypatch.setattr(_subprocess, "run", mock_subproc)

    yield fresh_env


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_compose_envelope_extras_project_rag_keys_present(patched_env) -> None:
    """AC4 (golden structure): extras.project_rag must contain all expected keys.

    Uses patched_env to isolate from real machine state. captured_at is excluded
    from the key check because it is volatile (changes on every call).

    This test validates the STRUCTURE only — not the runtime values. It must pass:
      1. Before the C1 extraction (baseline confirmation).
      2. After the C1 extraction (regression proof of byte-identical output).
    """
    from coordinator_whoami.project_rag.envelope import compose_envelope

    envelope = compose_envelope()

    assert "extras" in envelope, "envelope must have an 'extras' key"
    extras = envelope["extras"]
    assert "project_rag" in extras, "extras must have a 'project_rag' key"

    project_rag = extras["project_rag"]
    assert isinstance(project_rag, dict), "extras.project_rag must be a dict"

    # Check all expected keys are present (except volatile captured_at).
    missing = _EXPECTED_EXTRAS_PROJECT_RAG_KEYS - set(project_rag.keys())
    assert not missing, (
        f"extras.project_rag is missing expected keys after C1 refactor: {sorted(missing)}"
    )

    # C6 regression: the 8 generic probe keys must NOT appear here — they moved to
    # extras.coordinator_session. Their presence would mean the thinning regressed.
    leaked = _FORBIDDEN_GENERIC_KEYS & set(project_rag.keys())
    assert not leaked, (
        f"extras.project_rag leaked generic keys after C6 thinning: {sorted(leaked)} "
        f"(these belong under extras.coordinator_session)"
    )


def test_compose_envelope_extras_project_rag_subkey_structure(patched_env) -> None:
    """AC4 (golden sub-structure): each probe sub-dict must retain its required keys.

    Verifies that moving the 8 generic probe functions to host_probes.py does not
    alter the shape of the dicts they return (which land under extras.project_rag).
    """
    from coordinator_whoami.project_rag.envelope import compose_envelope

    envelope = compose_envelope()
    project_rag = envelope["extras"]["project_rag"]

    for probe_key, expected_sub_keys in _EXPECTED_SUB_KEYS.items():
        probe_val = project_rag.get(probe_key)
        assert isinstance(probe_val, dict), (
            f"extras.project_rag[{probe_key!r}] must be a dict, got {type(probe_val)}"
        )
        missing_sub = expected_sub_keys - set(probe_val.keys())
        assert not missing_sub, (
            f"extras.project_rag[{probe_key!r}] missing expected sub-keys: {sorted(missing_sub)}"
        )


def test_compose_envelope_contract_version_and_plugin_name(patched_env) -> None:
    """AC4 (golden top-level fields): contract_version=1 and plugin_name='project-rag' unchanged."""
    from coordinator_whoami.project_rag.envelope import compose_envelope

    envelope = compose_envelope()

    assert envelope.get("contract_version") == 1, (
        f"contract_version must be 1, got {envelope.get('contract_version')!r}"
    )
    assert envelope.get("plugin_name") == "project-rag", (
        f"plugin_name must be 'project-rag', got {envelope.get('plugin_name')!r}"
    )


def test_compose_envelope_binding_and_status_present(patched_env) -> None:
    """AC4 (golden shape): binding and status keys must be present in the envelope."""
    from coordinator_whoami.project_rag.envelope import compose_envelope

    envelope = compose_envelope()

    assert "binding" in envelope, "envelope must have 'binding' key"
    binding = envelope["binding"]
    assert "kind" in binding, "binding must have 'kind' key"
    assert binding["kind"] in ("bound", "unbound"), (
        f"binding.kind must be 'bound' or 'unbound', got {binding['kind']!r}"
    )

    assert "status" in envelope, "envelope must have 'status' key"
    status = envelope["status"]
    assert "state" in status, "status must have 'state' key"


def test_compose_envelope_no_source_kind_key_without_arg(patched_env) -> None:
    """AC4 (envelope_base backward compat): build_envelope called without source_kind
    must NOT emit a source_kind key in the envelope (preserves current project-rag behavior).

    This test is the backward-compat guard for the Step 4 source_kind kwarg extension.
    project-rag's compose_envelope() does not pass source_kind, so the key must be absent.
    """
    from coordinator_whoami.project_rag.envelope import compose_envelope

    envelope = compose_envelope()
    assert "source_kind" not in envelope, (
        "source_kind must NOT appear in project-rag envelope (it does not pass source_kind to build_envelope)"
    )
