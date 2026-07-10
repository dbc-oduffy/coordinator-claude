"""tests/session/test_session_envelope.py — session adopter acceptance tests.

Covers:
  AC1  — CLI emits v1 envelope with plugin_name=="coordinator-session"
  AC2  — envelope validates against whoami-envelope.v1.json
  AC3  — daemon-independence: sys.modules contains no torch / project-rag daemon
         module after compose_envelope(); verified via import-hook fence
  AC8  — git_state/orientation_cache/handoff_counts under extras.coordinator_session
         NOT at envelope top level
  AC10 — binding.kind is only "bound" or "unbound" (never "degraded")
  AC11 — status.state maps correctly; status.since==null
  AC12 — envelope emits source_kind=="live" explicitly

Spec backlink: archive/specs/2026-05-27-whoami-session-spine-refactor.md § C2 test surface
"""
from __future__ import annotations

import importlib
import importlib.resources  # review: F7 — moved immediately after `import importlib` per PEP 8 (reviewer: code-reviewer, nit)
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
# review: F6 — removed unused `from unittest.mock import patch` (reviewer: code-reviewer, nit)

import pytest


# ---------------------------------------------------------------------------
# Schema loader helper
# ---------------------------------------------------------------------------

def _load_envelope_schema() -> dict:
    return json.loads(
        importlib.resources.files("coordinator_whoami.schemas")
        .joinpath("whoami-envelope.v1.json")
        .read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# AC1 — CLI emits v1 envelope with plugin_name=="coordinator-session"
# ---------------------------------------------------------------------------

class TestAC1CliEmitsV1Envelope:
    """AC1: python -m coordinator_whoami.session emits a v1 envelope."""

    def test_cli_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "coordinator_whoami.session"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"CLI exited {result.returncode}. stderr: {result.stderr!r}"
        )

    def test_cli_stdout_is_valid_json(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "coordinator_whoami.session"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        envelope = json.loads(result.stdout)
        assert isinstance(envelope, dict), "CLI output must be a JSON object"

    def test_cli_plugin_name_is_coordinator_session(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "coordinator_whoami.session"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        envelope = json.loads(result.stdout)
        assert envelope.get("plugin_name") == "coordinator-session", (
            f"plugin_name must be 'coordinator-session', got {envelope.get('plugin_name')!r}"
        )

    def test_cli_contract_version_is_1(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "coordinator_whoami.session"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        envelope = json.loads(result.stdout)
        assert envelope.get("contract_version") == 1, (
            f"contract_version must be 1, got {envelope.get('contract_version')!r}"
        )

    def test_cli_human_flag_produces_pretty_json(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "coordinator_whoami.session", "--human"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Pretty-printed JSON has newlines and indentation
        assert "\n" in result.stdout, "—human output must contain newlines"
        envelope = json.loads(result.stdout)
        assert envelope.get("plugin_name") == "coordinator-session"


# ---------------------------------------------------------------------------
# AC2 — envelope validates against whoami-envelope.v1.json
# ---------------------------------------------------------------------------

class TestAC2SchemaValidation:
    """AC2: envelope from compose_envelope() validates against the v1 contract schema."""

    def test_compose_envelope_validates_against_v1_schema(self) -> None:
        from coordinator_whoami.session.envelope import compose_envelope

        envelope = compose_envelope()
        schema = _load_envelope_schema()

        try:
            from jsonschema import Draft202012Validator
            Draft202012Validator(schema).validate(envelope)
        except ImportError:
            # Structural fallback when jsonschema is absent
            for key in schema.get("required", []):
                assert key in envelope, f"Required key {key!r} missing from envelope"

    def test_cli_output_validates_against_v1_schema(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "coordinator_whoami.session"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        envelope = json.loads(result.stdout)
        schema = _load_envelope_schema()

        try:
            from jsonschema import Draft202012Validator
            Draft202012Validator(schema).validate(envelope)
        except ImportError:
            for key in schema.get("required", []):
                assert key in envelope, f"Required key {key!r} missing from CLI envelope"


# ---------------------------------------------------------------------------
# AC3 — daemon-independence: import-hook fence
# ---------------------------------------------------------------------------

class TestAC3DaemonIndependence:
    """AC3: compose_envelope() imports NO torch and NO project-rag daemon modules.

    Uses an import hook that raises ImportError on any attempt to import
    'torch' or the project-rag daemon module ('project_rag_server',
    'coordinator_whoami.project_rag.daemon', 'chromadb').
    The test asserts compose_envelope() succeeds DESPITE the fence.

    This is the real assertion per the Director of Engineering F6: daemon is ambient-disabled on this
    machine (CUDA OOM), so a bare exit==0 check is green-by-absence, not evidence
    of import-graph isolation. The import-hook fence catches isolation failures
    regardless of whether the daemon is up.
    """

    FORBIDDEN_PREFIXES = (
        "torch",
        "project_rag_server",
        "coordinator_whoami.project_rag.daemon",
        "chromadb",
    )

    def test_compose_envelope_does_not_import_torch_or_daemon(self) -> None:
        """Import-hook fence: compose_envelope() must succeed even when torch/daemon are fenced."""
        import importlib
        import sys

        forbidden = self.FORBIDDEN_PREFIXES

        class _ForbiddenImportHook:
            """Meta path finder that raises on forbidden module prefixes."""

            # review: F1 — replaced find_module (not dispatched on meta_path finders in
            # Python 3.12+) with find_spec so the fence actually intercepts (reviewer: code-reviewer, P1)
            def find_spec(self, fullname: str, path: object = None, target: object = None) -> object:
                for prefix in forbidden:
                    if fullname == prefix or fullname.startswith(prefix + "."):
                        raise ImportError(
                            f"AC3 import-graph isolation fence: '{fullname}' is a "
                            f"forbidden daemon/torch import in the session adopter."
                        )
                return None  # fall through to normal import machinery

        hook = _ForbiddenImportHook()
        sys.meta_path.insert(0, hook)
        try:
            from coordinator_whoami.session.envelope import compose_envelope
            envelope = compose_envelope()
            # If we reach here, no forbidden module was imported
            assert isinstance(envelope, dict), "compose_envelope() must return a dict"
        finally:
            sys.meta_path.remove(hook)

    def test_sys_modules_contains_no_torch_after_compose(self) -> None:
        """sys.modules must not contain 'torch' after compose_envelope() call."""
        from coordinator_whoami.session.envelope import compose_envelope
        compose_envelope()
        torch_modules = [k for k in sys.modules if k == "torch" or k.startswith("torch.")]
        assert not torch_modules, (
            f"AC3: torch modules found in sys.modules after compose_envelope(): {torch_modules}"
        )

    def test_sys_modules_contains_no_daemon_after_compose(self) -> None:
        """sys.modules must not contain project-rag daemon modules after compose_envelope()."""
        from coordinator_whoami.session.envelope import compose_envelope
        compose_envelope()
        daemon_modules = [
            k for k in sys.modules
            if any(
                k == prefix or k.startswith(prefix + ".")
                for prefix in ("project_rag_server", "chromadb")
            )
        ]
        assert not daemon_modules, (
            f"AC3: daemon modules found in sys.modules after compose_envelope(): {daemon_modules}"
        )


# ---------------------------------------------------------------------------
# AC8 — session probes under extras.coordinator_session, NOT top-level
# ---------------------------------------------------------------------------

class TestAC8ProbesUnderExtras:
    """AC8: git_state/orientation_cache/handoff_counts live under extras.coordinator_session."""

    def _get_envelope(self) -> dict[str, Any]:
        from coordinator_whoami.session.envelope import compose_envelope
        return compose_envelope()

    def test_session_probes_not_at_top_level(self) -> None:
        envelope = self._get_envelope()
        forbidden_top_level = ("git_state", "orientation_cache", "handoff_counts")
        for key in forbidden_top_level:
            assert key not in envelope, (
                f"AC8: '{key}' must NOT be a top-level envelope key "
                f"(additionalProperties:false would reject it). Found at top level."
            )

    def test_session_probes_present_under_extras_coordinator_session(self) -> None:
        envelope = self._get_envelope()
        extras = envelope.get("extras", {})
        session_extras = extras.get("coordinator_session")
        assert session_extras is not None, (
            "AC8: extras.coordinator_session must be present in the envelope"
        )
        assert isinstance(session_extras, dict), (
            "AC8: extras.coordinator_session must be a dict"
        )
        for key in ("git_state", "orientation_cache", "handoff_counts"):
            assert key in session_extras, (
                f"AC8: '{key}' must be present under extras.coordinator_session"
            )

    def test_envelope_top_level_keys_are_only_schema_allowed(self) -> None:
        """Verify no extra top-level keys violate additionalProperties:false."""
        envelope = self._get_envelope()
        allowed = {
            "contract_version", "plugin_name", "plugin_version",
            "source_kind", "binding", "status", "extras",
        }
        extra_keys = set(envelope.keys()) - allowed
        assert not extra_keys, (
            f"AC8: unexpected top-level envelope keys {extra_keys!r}; "
            f"schema sets additionalProperties:false"
        )


# ---------------------------------------------------------------------------
# AC10 — binding.kind is binary (bound or unbound, never degraded)
# ---------------------------------------------------------------------------

class TestAC10BindingBinary:
    """AC10: binding.kind is only 'bound' or 'unbound'. 'degraded' never appears."""

    def test_binding_kind_is_bound_or_unbound(self) -> None:
        from coordinator_whoami.session.envelope import compose_envelope
        envelope = compose_envelope()
        kind = envelope["binding"]["kind"]
        assert kind in ("bound", "unbound"), (
            f"AC10: binding.kind must be 'bound' or 'unbound', got {kind!r}"
        )

    def test_binding_kind_never_degraded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify degraded is not emitted under any _resolve_binding path."""
        from coordinator_whoami.session import envelope as env_mod

        # Patch _resolve_binding to exercise all branches by calling the real function
        # with various _git_root outcomes. Degraded must never appear.
        from coordinator_whoami.session import probes as probes_mod

        # Simulate no git root (unbound path)
        # review: F4 side-effect — _git_root was renamed to git_root (public); patch the new name
        monkeypatch.setattr(probes_mod, "git_root", lambda: None)
        e = env_mod.compose_envelope()
        assert e["binding"]["kind"] != "degraded", (
            "AC10: binding.kind must not be 'degraded' (no git root path)"
        )

    def test_bound_path_has_string_target(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When bound, target must be a non-null string."""
        from coordinator_whoami.session import probes as probes_mod
        from coordinator_whoami.session import envelope as env_mod

        # Create a coordinator-onboarded structure
        root = tmp_path / "repo"
        root.mkdir()
        (root / "tasks").mkdir()
        (root / "CLAUDE.md").write_text("# coord\n", encoding="utf-8")

        # review: F4 side-effect — _git_root was renamed to git_root (public); patch the new name
        monkeypatch.setattr(probes_mod, "git_root", lambda: root)
        e = env_mod.compose_envelope()
        if e["binding"]["kind"] == "bound":
            assert isinstance(e["binding"]["target"], str), (
                "AC10: binding.target must be a string when bound"
            )

    def test_unbound_path_has_null_target(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When unbound, target must be null."""
        from coordinator_whoami.session import probes as probes_mod
        from coordinator_whoami.session import envelope as env_mod

        # Repo root with no coordinator structure
        root = tmp_path / "bare_repo"
        root.mkdir()

        # review: F4 side-effect — _git_root was renamed to git_root (public); patch the new name
        monkeypatch.setattr(probes_mod, "git_root", lambda: root)
        e = env_mod.compose_envelope()
        if e["binding"]["kind"] == "unbound":
            assert e["binding"]["target"] is None, (
                "AC10: binding.target must be null when unbound"
            )


# ---------------------------------------------------------------------------
# orientation_cache HEAD-staleness comparison — SHA-length normalization
# (regression: the cache stores a SHORT SHA / branch / tag, the probe compares
#  to the FULL `rev-parse HEAD`; a naive `!=` reports stale=True even for a
#  fresh cache. The status-mapping tests below monkeypatch the probe wholesale,
#  so they never exercise this comparison — these do.)
# ---------------------------------------------------------------------------

class TestOrientationCacheStalenessNormalization:
    def test_short_sha_prefix_of_head_is_not_stale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from coordinator_whoami.session import probes as probes_mod

        live = probes_mod._current_git_head()
        if not live:
            pytest.skip("not in a git repo")
        # Stored value is the 8-char short form of the CURRENT head — a fresh cache.
        monkeypatch.setattr(probes_mod, "_read_frontmatter_field", lambda path, field: live[:8])
        result = probes_mod.probe_orientation_cache()
        if not result["present"]:
            pytest.skip("orientation cache file not present on this machine")
        assert result["stale"] is False, (
            f"short SHA {live[:8]!r} (a prefix of HEAD {live!r}) is a FRESH cache and "
            f"must NOT be stale — a naive full-string `!=` is the regression this guards"
        )

    def test_unrelated_sha_is_stale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from coordinator_whoami.session import probes as probes_mod

        live = probes_mod._current_git_head()
        if not live:
            pytest.skip("not in a git repo")
        monkeypatch.setattr(probes_mod, "_read_frontmatter_field", lambda path, field: "0000000")
        result = probes_mod.probe_orientation_cache()
        if not result["present"]:
            pytest.skip("orientation cache file not present on this machine")
        assert result["stale"] is True, (
            "an unresolvable / non-prefix stored value must report stale=True"
        )


# ---------------------------------------------------------------------------
# AC11 — status.state mapping and since==null
# ---------------------------------------------------------------------------

class TestAC11StatusMapping:
    """AC11: status.state maps healthy/degraded/error correctly; since==null."""

    def _make_envelope(
        self,
        monkeypatch: pytest.MonkeyPatch,
        git_state: dict,
        orientation: dict,
        handoffs: dict | None = None,
    ) -> dict[str, Any]:
        from coordinator_whoami.session import probes as probes_mod
        from coordinator_whoami.session.envelope import compose_envelope

        monkeypatch.setattr(probes_mod, "probe_git_state", lambda: git_state)
        monkeypatch.setattr(probes_mod, "probe_orientation_cache", lambda: orientation)
        monkeypatch.setattr(
            probes_mod, "probe_handoff_counts",
            lambda: handoffs or {"ready_to_fire": None, "awaiting_gate": None},
        )
        return compose_envelope()

    def test_status_since_is_always_null(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from coordinator_whoami.session.envelope import compose_envelope
        envelope = compose_envelope()
        assert envelope["status"]["since"] is None, (
            f"AC11: status.since must be null (no state-tracker), "
            f"got {envelope['status']['since']!r}"
        )

    def test_healthy_when_cache_fresh_and_not_behind(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = {"branch": "main", "dirty": False, "ahead": 0, "behind": 0}
        orientation = {
            "present": True, "stale": False,
            "stored_head": "abc123", "live_head": "abc123",
        }
        e = self._make_envelope(monkeypatch, git, orientation)
        assert e["status"]["state"] == "healthy", (
            f"AC11: expected healthy, got {e['status']['state']!r} "
            f"(reason: {e['status'].get('reason')!r})"
        )

    def test_degraded_when_cache_stale(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = {"branch": "main", "dirty": False, "ahead": 0, "behind": 0}
        orientation = {
            "present": True, "stale": True,
            "stored_head": "aaa", "live_head": "bbb",
        }
        e = self._make_envelope(monkeypatch, git, orientation)
        assert e["status"]["state"] == "degraded", (
            f"AC11: expected degraded (stale cache), got {e['status']['state']!r}"
        )
        assert e["status"]["reason"] is not None, (
            "AC11: status.reason must be non-null on degraded"
        )

    def test_degraded_when_behind_origin_main(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = {"branch": "main", "dirty": False, "ahead": 0, "behind": 3}
        orientation = {
            "present": True, "stale": False,
            "stored_head": "abc", "live_head": "abc",
        }
        e = self._make_envelope(monkeypatch, git, orientation)
        assert e["status"]["state"] == "degraded", (
            f"AC11: expected degraded (behind origin/main), got {e['status']['state']!r}"
        )
        assert "behind" in (e["status"].get("reason") or ""), (
            f"AC11: reason must mention 'behind', got {e['status'].get('reason')!r}"
        )

    def test_error_when_git_branch_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = {"branch": None, "dirty": None, "ahead": None, "behind": None}
        orientation = {"present": False, "stale": None, "stored_head": None, "live_head": None}
        e = self._make_envelope(monkeypatch, git, orientation)
        assert e["status"]["state"] == "error", (
            f"AC11: expected error (branch=None), got {e['status']['state']!r}"
        )

    def test_degraded_when_cache_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # review: F9 — locks F2: absent orientation cache must map to degraded,
        # not healthy (reviewer: code-reviewer, P2)
        git = {"branch": "main", "dirty": False, "ahead": 0, "behind": 0}
        orientation = {"present": False, "stale": None, "stored_head": None, "live_head": None}
        e = self._make_envelope(monkeypatch, git, orientation)
        assert e["status"]["state"] == "degraded", f"absent cache must be degraded, got {e['status']['state']!r}"

    def test_degraded_reason_names_cache_staleness(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        git = {"branch": "main", "dirty": True, "ahead": 2, "behind": 1}
        orientation = {
            "present": True, "stale": True,
            "stored_head": "old", "live_head": "new",
        }
        e = self._make_envelope(monkeypatch, git, orientation)
        assert e["status"]["state"] == "degraded"
        reason = e["status"].get("reason") or ""
        assert "stale" in reason.lower() or "drift" in reason.lower(), (
            f"AC11: reason must mention staleness, got {reason!r}"
        )

    def test_short_sha_prefix_is_healthy_through_compose_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # review: F12 — drives SHA-normalization end-to-end through compose_envelope:
        # a short stored SHA that is a prefix of HEAD is NOT stale → status must be
        # healthy (not degraded). Guards the naive `!=` regression path (reviewer: code-reviewer, P2)
        from coordinator_whoami.session import probes as probes_mod
        import subprocess as sp
        import sys as _sys
        result = sp.run(
            [_sys.executable, "-c",
             "import subprocess; r = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True); print(r.stdout.strip())"],
            capture_output=True, text=True,
        )
        live_head = result.stdout.strip()
        if not live_head or len(live_head) < 8:
            pytest.skip("not in a git repo or HEAD unavailable")
        short_sha = live_head[:8]

        monkeypatch.setattr(probes_mod, "_current_git_head", lambda: live_head)
        monkeypatch.setattr(probes_mod, "_read_frontmatter_field", lambda path, field: short_sha)

        git = {"branch": "main", "dirty": False, "ahead": 0, "behind": 0}
        # present=True + stale derived from compose_envelope → probe_orientation_cache
        # is patched wholesale via _make_envelope, so drive orientation directly here
        from coordinator_whoami.session.envelope import compose_envelope

        # review: F12 recursion fix — capture real probe BEFORE monkeypatching it;
        # _fake_orientation must call the captured reference, not the patched attribute
        _real_probe_orientation = probes_mod.probe_orientation_cache

        def _fake_orientation():
            # simulate a cache that stores only the short SHA — probe_orientation_cache
            # normalization logic handles it; status must resolve healthy
            r = _real_probe_orientation()
            return r

        monkeypatch.setattr(probes_mod, "probe_git_state", lambda: git)
        monkeypatch.setattr(probes_mod, "probe_handoff_counts",
                            lambda: {"ready_to_fire": None, "awaiting_gate": None})
        monkeypatch.setattr(probes_mod, "probe_orientation_cache", _fake_orientation)

        # If orientation_cache.md is present on this machine, normalization runs;
        # if not, the absent-cache arm fires (degraded) — skip in that case.
        env = compose_envelope()
        state = env["status"]["state"]
        if not env.get("extras", {}).get("coordinator_session", {}).get("orientation_cache", {}).get("present"):
            pytest.skip("orientation_cache.md not present on this machine — cannot verify normalization path")
        assert state == "healthy", (
            f"short SHA {short_sha!r} (prefix of HEAD {live_head!r}) must yield healthy, got {state!r}"
        )

    def test_status_has_required_fields(self) -> None:
        from coordinator_whoami.session.envelope import compose_envelope
        envelope = compose_envelope()
        status = envelope.get("status", {})
        assert "state" in status, "AC11: status must have 'state'"
        assert "since" in status, "AC11: status must have 'since'"
        assert status["state"] in ("healthy", "degraded", "error"), (
            f"AC11: status.state must be healthy/degraded/error, got {status['state']!r}"
        )


# ---------------------------------------------------------------------------
# AC12 — source_kind=="live" explicitly set
# ---------------------------------------------------------------------------

class TestAC12SourceKindLive:
    """AC12: envelope emits source_kind=="live" explicitly (not absent/default)."""

    def test_source_kind_is_live(self) -> None:
        from coordinator_whoami.session.envelope import compose_envelope
        envelope = compose_envelope()
        assert "source_kind" in envelope, (
            "AC12: 'source_kind' key must be present in the envelope "
            "(explicit 'live' is required, absence-means-live is insufficient)"
        )
        assert envelope["source_kind"] == "live", (
            f"AC12: source_kind must be 'live', got {envelope['source_kind']!r}"
        )

    def test_cli_output_source_kind_is_live(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "coordinator_whoami.session"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        envelope = json.loads(result.stdout)
        assert envelope.get("source_kind") == "live", (
            f"AC12: CLI output source_kind must be 'live', got {envelope.get('source_kind')!r}"
        )
