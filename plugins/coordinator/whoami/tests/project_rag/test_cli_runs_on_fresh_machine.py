"""
tests/project_rag/test_cli_runs_on_fresh_machine.py

Exercises `coordinator_whoami.project_rag.cli.compose()` in a fixture environment
that simulates a fresh machine: no .venv, no ~/.claude.json project-rag entry, no
coordinator, no installed addons, and no project-rag source registry.

Migrated from X:/project-rag/tests/install/test_whoami_runs_on_fresh_machine.py
(352 lines). Import paths updated from `core.whoami` to
`coordinator_whoami.project_rag.cli`. The three new probes (source, engine_version,
project_kind) must degrade gracefully to null on a fresh machine.

Assertions:
  - compose() returns well-formed JSON (serialisable, top-level dict).
  - All required top-level keys are present.
  - "Not yet installed" states are represented as structured values, not crashes.
  - `addons` key exists and is a dict (possibly empty on a fresh machine).
  - apple_silicon field is a bool (not absent or wrong type).
  - source, engine_version, project_kind are all null on fresh machine (no registry).

Spec backlink: docs/plans/2026-05-19-whoami-substrate-migration.md § 8 Task 6
Origin: docs/plans/2026-05-19-first-class-install-redesign.md §W3 — file lives at X:/project-rag
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fresh_machine_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Simulate a fresh machine by redirecting $HOME / USERPROFILE to a bare tmpdir.

    The tmpdir has no .claude.json, no .claude/plugins/coordinator-claude, and
    no .venv relative to any pyproject.toml. CLAUDE_HOME is also set so
    _probe_claude() sees an empty sandbox. PROJECT_RAG_REGISTRY_PATH is
    cleared so _probe_source() / _probe_engine_version() / _probe_project_kind()
    all see no registry.
    """
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("CLAUDE_HOME", str(home))
    monkeypatch.delenv("PROJECT_RAG_REGISTRY_PATH", raising=False)

    yield home


# ---------------------------------------------------------------------------
# Required keys (original 12 + 3 new probes)
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {
    "schema_version",
    "captured_at",
    "os",
    "arch",
    "gpu",
    "python",
    "uv",
    "claude",
    "coordinator",
    "project",
    "project_rag_state",
    "addons",
    # New native probes added per PM 2026-05-19.
    "source",
    "engine_version",
    "project_kind",
}


# ---------------------------------------------------------------------------
# Original tests (migrated)
# ---------------------------------------------------------------------------

def test_compose_returns_well_formed_json(fresh_machine_env: Path) -> None:
    """compose() must return a serialisable dict with no thrown exceptions."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()

    assert isinstance(profile, dict), "compose() must return a dict"

    # Must be JSON-serialisable — no datetime objects, no non-serialisable types.
    serialised = json.dumps(profile)
    reparsed = json.loads(serialised)
    assert isinstance(reparsed, dict)


def test_compose_has_all_required_top_level_keys(fresh_machine_env: Path) -> None:
    """compose() output must contain every required top-level key (original 12 + 3 new)."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()

    missing = _REQUIRED_KEYS - set(profile.keys())
    assert not missing, f"Missing top-level keys: {sorted(missing)}"


def test_compose_schema_version_is_1(fresh_machine_env: Path) -> None:
    """schema_version must be 1 for this implementation."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    assert profile["schema_version"] == 1


def test_compose_captured_at_is_iso8601(fresh_machine_env: Path) -> None:
    """captured_at must look like an ISO 8601 UTC timestamp string."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    captured_at = profile["captured_at"]
    assert isinstance(captured_at, str)
    assert len(captured_at) >= 19, f"captured_at too short: {captured_at!r}"
    assert "T" in captured_at, f"captured_at missing 'T' separator: {captured_at!r}"


def test_fresh_machine_claude_json_absent(fresh_machine_env: Path) -> None:
    """On a fresh machine with no ~/.claude.json, project_rag_entry must be 'no_file'."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    claude_block = profile["claude"]
    assert isinstance(claude_block, dict)
    assert claude_block["project_rag_entry"] == "no_file"
    assert claude_block["json_present"] is False


def test_fresh_machine_coordinator_not_installed(fresh_machine_env: Path) -> None:
    """On a fresh machine with no coordinator plugin, installed must be False."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    coord_block = profile["coordinator"]
    assert isinstance(coord_block, dict)
    assert coord_block["installed"] is False


def test_addons_key_exists_and_is_dict(fresh_machine_env: Path) -> None:
    """addons key must be present and be a dict (possibly empty on fresh machine)."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    addons = profile["addons"]
    assert isinstance(addons, dict), "addons must be a dict"


def test_apple_silicon_is_bool(fresh_machine_env: Path) -> None:
    """arch.apple_silicon must always be a bool, never absent or None."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    arch_block = profile["arch"]
    assert isinstance(arch_block, dict)
    assert isinstance(arch_block["apple_silicon"], bool), (
        f"apple_silicon must be bool, got {type(arch_block['apple_silicon'])}"
    )


def test_os_block_has_required_keys(fresh_machine_env: Path) -> None:
    """os block must have name, version, shell."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    os_block = profile["os"]
    assert isinstance(os_block, dict)
    for key in ("name", "version", "shell"):
        assert key in os_block, f"os block missing key: {key!r}"
        assert isinstance(os_block[key], str), f"os.{key} must be str"


def test_gpu_block_has_present_key(fresh_machine_env: Path) -> None:
    """gpu block must always have a boolean 'present' field."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    gpu_block = profile["gpu"]
    assert isinstance(gpu_block, dict)
    assert "present" in gpu_block
    assert isinstance(gpu_block["present"], bool)


def test_python_block_has_required_keys(fresh_machine_env: Path) -> None:
    """python block must have invoking_version, invoking_path, ms_store_shim, venv_present."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    py_block = profile["python"]
    assert isinstance(py_block, dict)
    assert "invoking_version" in py_block
    assert "invoking_path" in py_block
    assert "ms_store_shim" in py_block
    assert "venv_present" in py_block
    assert isinstance(py_block["ms_store_shim"], bool)
    assert isinstance(py_block["venv_present"], bool)


def test_uv_block_has_present_key(fresh_machine_env: Path) -> None:
    """uv block must always have a boolean 'present' field."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    uv_block = profile["uv"]
    assert isinstance(uv_block, dict)
    assert "present" in uv_block
    assert isinstance(uv_block["present"], bool)


def test_project_block_has_required_keys(fresh_machine_env: Path) -> None:
    """project block must have root, kinds_detected, uproject_present."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    proj_block = profile["project"]
    assert isinstance(proj_block, dict)
    assert "root" in proj_block
    assert "kinds_detected" in proj_block
    assert "uproject_present" in proj_block
    assert isinstance(proj_block["kinds_detected"], list)
    assert isinstance(proj_block["uproject_present"], bool)


def test_project_rag_state_block_has_data_dir_present(fresh_machine_env: Path) -> None:
    """project_rag_state block must have a boolean data_dir_present field."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    state_block = profile["project_rag_state"]
    assert isinstance(state_block, dict)
    assert "data_dir_present" in state_block
    assert isinstance(state_block["data_dir_present"], bool)


def test_no_exceptions_from_compose(fresh_machine_env: Path) -> None:
    """compose() must never raise an exception regardless of machine state."""
    from coordinator_whoami.project_rag.cli import compose

    try:
        profile = compose()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"compose() raised an unexpected exception: {type(exc).__name__}: {exc}")


def test_probe_claude_per_project_install_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_probe_claude() must return 'healthy' when entry is in per-project mcpServers."""
    from coordinator_whoami.project_rag.cli import _probe_claude

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)

    claude_json = home / ".claude.json"
    claude_json.write_text(
        json.dumps({
            "mcpServers": {},
            "projects": {
                "/some/project/root": {
                    "mcpServers": {
                        "project-rag": {
                            "command": "python",
                            "args": ["/some/project/project_rag_mcp/project_rag_server.py"],
                        }
                    }
                }
            },
        }),
        encoding="utf-8",
    )

    monkeypatch.setenv("CLAUDE_HOME", str(home))
    result = _probe_claude()

    assert result["json_present"] is True
    assert result["project_rag_entry"] == "healthy", (
        f"Per-project install must report 'healthy', got {result['project_rag_entry']!r}"
    )


def test_probe_claude_absent_when_no_entry_anywhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_probe_claude() must return 'absent' when project-rag is not in any mcpServers location."""
    from coordinator_whoami.project_rag.cli import _probe_claude

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)

    claude_json = home / ".claude.json"
    claude_json.write_text(
        json.dumps({
            "mcpServers": {},
            "projects": {
                "/some/project/root": {
                    "mcpServers": {"other-tool": {"command": "other"}}
                }
            },
        }),
        encoding="utf-8",
    )

    monkeypatch.setenv("CLAUDE_HOME", str(home))
    result = _probe_claude()

    assert result["json_present"] is True
    assert result["project_rag_entry"] == "absent", (
        f"No entry anywhere must report 'absent', got {result['project_rag_entry']!r}"
    )


def test_invocation_as_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """python -m coordinator_whoami.project_rag must exit 0 and emit parseable JSON to stdout."""
    import subprocess

    home = tmp_path / "home"
    home.mkdir(exist_ok=True)

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CLAUDE_HOME"] = str(home)
    env.pop("PROJECT_RAG_REGISTRY_PATH", None)

    # Ensure coordinator_whoami is on the subprocess PYTHONPATH.
    # The package lives at whoami/ and is importable from there.
    import importlib
    import coordinator_whoami as _cw_pkg
    pkg_parent = str(Path(_cw_pkg.__file__).parent.parent)
    existing_pypath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (pkg_parent + os.pathsep + existing_pypath).strip(os.pathsep)

    result = subprocess.run(
        [sys.executable, "-m", "coordinator_whoami.project_rag", "--no-persist"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        timeout=30,  # Review: Reviewer B B-F4 — add timeout to prevent hangs in CI
    )
    assert result.returncode == 0, (
        f"python -m coordinator_whoami.project_rag exited {result.returncode}.\n"
        f"stdout: {result.stdout!r}\n"
        f"stderr: {result.stderr!r}"
    )
    # stdout must be parseable JSON.
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(f"stdout is not valid JSON: {exc}\n{result.stdout!r}")
    assert isinstance(parsed, dict)
    # R2 (Task 4): main() now emits envelope-shaped JSON; contract_version replaces schema_version.
    assert "contract_version" in parsed, (
        f"Expected envelope-shaped output with 'contract_version' key; got keys: {list(parsed)}"
    )
    # schema_version must NOT appear at envelope top level — it lives inside extras.project_rag.
    # Review: Reviewer B B-F12 — assert old key absent to prevent Task 4 regression.
    assert "schema_version" not in parsed, (
        "schema_version must not appear at envelope top level (Task 4 migration)"
    )


# ---------------------------------------------------------------------------
# New probe graceful-degradation tests (fresh machine — no registry)
# ---------------------------------------------------------------------------

def test_fresh_machine_source_is_null(fresh_machine_env: Path) -> None:
    """O32: source must be null on a fresh machine with no project-rag registry."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    assert "source" in profile, "compose() must include 'source' key"
    assert profile["source"] is None, (
        f"source must be null on fresh machine, got {profile['source']!r}"
    )


def test_fresh_machine_engine_version_is_null(fresh_machine_env: Path) -> None:
    """O33: engine_version must be null on a fresh machine with no project-rag registry."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    assert "engine_version" in profile, "compose() must include 'engine_version' key"
    assert profile["engine_version"] is None, (
        f"engine_version must be null on fresh machine, got {profile['engine_version']!r}"
    )


def test_fresh_machine_project_kind_is_null(fresh_machine_env: Path) -> None:
    """O34: project_kind must be null on a fresh machine with no project-rag registry."""
    from coordinator_whoami.project_rag.cli import compose

    profile = compose()
    assert "project_kind" in profile, "compose() must include 'project_kind' key"
    assert profile["project_kind"] is None, (
        f"project_kind must be null on fresh machine, got {profile['project_kind']!r}"
    )


def test_new_probes_do_not_crash_on_fresh_machine(fresh_machine_env: Path) -> None:
    """O32/O33/O34: all three new probes must degrade to null without raising exceptions."""
    from coordinator_whoami.project_rag.cli import (
        _probe_source,
        _probe_engine_version,
        _probe_project_kind,
    )

    try:
        source = _probe_source()
        engine_version = _probe_engine_version()
        project_kind = _probe_project_kind()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"New probe raised an unexpected exception: {type(exc).__name__}: {exc}")

    assert source is None
    assert engine_version is None
    assert project_kind is None


# ---------------------------------------------------------------------------
# GPU probe test using mock_subprocess_run
# Review: Reviewer B B-F13 — adds coverage for _probe_gpu() on a mocked NVIDIA machine;
# fills real coverage gap and activates the mock_subprocess_run conftest fixture.
# ---------------------------------------------------------------------------

def test_gpu_probe_with_nvidia_smi(
    fresh_machine_env: Path, mock_subprocess_run: object
) -> None:
    """_probe_gpu() must return present=True with vendor=nvidia on a mocked successful nvidia-smi.

    Reconfigures mock_subprocess_run to return a successful nvidia-smi response with
    known free VRAM and driver version, then asserts the returned dict shape.

    Review: Reviewer B B-F13 — option (a): fill the coverage gap with a real test
    rather than removing the fixture.
    """
    import subprocess
    from unittest.mock import MagicMock

    # Reconfigure the conftest mock to simulate a successful nvidia-smi response.
    # mock_subprocess_run is already patched onto subprocess.run by the fixture.
    mock = mock_subprocess_run  # type: MagicMock
    mock.side_effect = None  # clear FileNotFoundError default
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "22000, 535.129.03\n"
    mock.return_value = mock_result

    from coordinator_whoami.project_rag.cli import _probe_gpu

    result = _probe_gpu()

    assert result["present"] is True, (
        f"_probe_gpu() must return present=True on successful nvidia-smi, got {result['present']!r}"
    )
    assert result["vendor"] == "nvidia", (
        f"_probe_gpu() must return vendor='nvidia', got {result['vendor']!r}"
    )
    assert result["vram_free_mib"] == 22000, (
        f"_probe_gpu() must parse vram_free_mib=22000, got {result['vram_free_mib']!r}"
    )
    assert result["cuda_driver"] == "535.129.03", (
        f"_probe_gpu() must parse cuda_driver='535.129.03', got {result['cuda_driver']!r}"
    )


# ---------------------------------------------------------------------------
# O2/O3 flag tests — --human / --refresh
# Review: Reviewer B B-F3 — add --human flag test; document --refresh as no-op.
#
# NOTE on --refresh: the flag is accepted by the CLI parser but is currently a
# no-op (compose_envelope() always re-runs all probes). A TODO remains to add
# cache-aware short-circuit logic; when that lands, add a test that verifies
# --refresh forces a re-run even with a recent profile on disk.
# ---------------------------------------------------------------------------

def test_invocation_with_human_flag(tmp_path: Path) -> None:
    """O2: python -m coordinator_whoami.project_rag --human must emit pretty-printed JSON.

    Pretty-printed output contains newlines (\n) in the stdout string, which
    compact JSON does not (except for the trailing newline from print()).

    Review: Reviewer B B-F3 — O2/O3 PARTIAL coverage; --human flag test added.
    """
    import subprocess
    import sys
    import os

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env["CLAUDE_HOME"] = str(tmp_path)
    env.pop("PROJECT_RAG_REGISTRY_PATH", None)

    import coordinator_whoami as _cw_pkg
    pkg_parent = str(Path(_cw_pkg.__file__).parent.parent)
    existing_pypath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (pkg_parent + os.pathsep + existing_pypath).strip(os.pathsep)

    result = subprocess.run(
        [sys.executable, "-m", "coordinator_whoami.project_rag", "--human", "--no-persist"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        timeout=30,
    )
    assert result.returncode == 0, (
        f"--human flag caused non-zero exit.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
    # Pretty-printed JSON has internal newlines; compact does not.
    assert "\n" in result.stdout, (
        f"--human output must be pretty-printed (contain newlines); got {result.stdout[:200]!r}"
    )
