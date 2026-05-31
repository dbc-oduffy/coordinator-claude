"""tests/test_machine.py — coordinator_whoami.machine diagnostic surface.

Verifies the machine-info surface emits the expected host inventory and is a
PLAIN machine-info dict, NOT a whoami-contract envelope (no binding/status).

Mocks platform.* + subprocess.run to avoid the Python-3.13-on-Windows WMI hang
in platform.system (a pre-existing environment issue; see test_envelope_golden.py).

Key-presence assertions use null-permissive checks: the patched_env fixture
stubs out subprocess.run (FileNotFoundError), so probes that shell out will
return null/none values.  Tests assert on KEY PRESENCE and types (allowing null),
not on concrete values — the full value contract is verified live at merge-gate.

Spec backlink: archive/specs/2026-05-27-whoami-host-capacity-fields.md § Chunk 2
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def patched_env(monkeypatch: pytest.MonkeyPatch):
    """Patch platform.* + subprocess.run so host_probes runs without the WMI hang."""
    import platform as _platform
    import subprocess as _subprocess

    monkeypatch.setattr(_platform, "system", lambda: "Windows")
    monkeypatch.setattr(_platform, "version", lambda: "10.0.26200")
    monkeypatch.setattr(_platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(_platform, "python_version", lambda: "3.13.1")
    monkeypatch.setattr(
        _subprocess, "run",
        MagicMock(side_effect=FileNotFoundError("no nvidia-smi / no uv")),
    )
    yield


_EXPECTED_KEYS = {"os", "arch", "gpu", "mem", "disk", "host", "mem_ceiling_mechanism", "python", "uv"}

_MEM_CEILING_VALID = {"cgroup_v2", "cgroup_v1", "rlimit", "win_jobobject", "none", "unknown"}


def test_compose_machine_has_expected_keys(patched_env) -> None:
    from coordinator_whoami.machine import compose_machine

    info = compose_machine()
    assert set(info.keys()) == _EXPECTED_KEYS, (
        f"machine info must carry exactly {sorted(_EXPECTED_KEYS)}, got {sorted(info.keys())}"
    )
    # OS sub-shape
    assert "name" in info["os"]
    assert "is_windows" in info["os"]
    # GPU sub-shape (null-permissive — subprocess patched out)
    assert "present" in info["gpu"]
    assert "vram_total_mib" in info["gpu"]
    assert "name" in info["gpu"]
    assert "compute_capability" in info["gpu"]
    assert "driver_model" in info["gpu"]
    assert "device_count" in info["gpu"]
    # arch sub-shape
    assert "logical_cores" in info["arch"]
    assert "physical_cores" in info["arch"]
    # Python sub-shape
    assert "invoking_version" in info["python"]


def test_compose_machine_mem_block(patched_env) -> None:
    """mem block must carry all four byte-metric keys (values may be null under mock)."""
    from coordinator_whoami.machine import compose_machine

    info = compose_machine()
    mem = info["mem"]
    assert isinstance(mem, dict), f"mem must be a dict, got {type(mem)}"
    for key in ("total_bytes", "available_bytes", "commit_limit_bytes", "commit_available_bytes"):
        assert key in mem, f"mem missing required key {key!r}"
        assert mem[key] is None or isinstance(mem[key], int), (
            f"mem[{key!r}] must be int or null, got {type(mem[key])}"
        )


def test_compose_machine_disk_block(patched_env) -> None:
    """disk block must be a list; each entry must carry path/total_bytes/free_bytes."""
    from coordinator_whoami.machine import compose_machine

    info = compose_machine()
    disk = info["disk"]
    assert isinstance(disk, list), f"disk must be a list, got {type(disk)}"
    for entry in disk:
        assert isinstance(entry, dict), f"disk entry must be a dict, got {type(entry)}"
        for key in ("path", "total_bytes", "free_bytes"):
            assert key in entry, f"disk entry missing required key {key!r}"


def test_compose_machine_host_block(patched_env) -> None:
    """host block must carry hostname and machine_id."""
    from coordinator_whoami.machine import compose_machine

    info = compose_machine()
    host = info["host"]
    assert isinstance(host, dict), f"host must be a dict, got {type(host)}"
    assert "hostname" in host, "host missing 'hostname'"
    assert "machine_id" in host, "host missing 'machine_id'"
    # hostname must be a non-empty string (socket.gethostname() never returns null)
    assert isinstance(host["hostname"], str) and host["hostname"], (
        f"host['hostname'] must be a non-empty string, got {host['hostname']!r}"
    )
    # machine_id is best-effort — null is acceptable
    assert host["machine_id"] is None or isinstance(host["machine_id"], str), (
        f"host['machine_id'] must be str or null, got {type(host['machine_id'])}"
    )


def test_compose_machine_mem_ceiling_mechanism(patched_env) -> None:
    """mem_ceiling_mechanism must be a string in the defined enum set."""
    from coordinator_whoami.machine import compose_machine

    info = compose_machine()
    mechanism = info["mem_ceiling_mechanism"]
    assert isinstance(mechanism, str), (
        f"mem_ceiling_mechanism must be a str, got {type(mechanism)}"
    )
    assert mechanism in _MEM_CEILING_VALID, (
        f"mem_ceiling_mechanism {mechanism!r} not in valid enum {_MEM_CEILING_VALID}"
    )


def test_machine_is_not_a_whoami_envelope(patched_env) -> None:
    """Machine-state is inventory, not a binding — must NOT masquerade as an envelope."""
    from coordinator_whoami.machine import compose_machine

    info = compose_machine()
    for envelope_key in ("contract_version", "plugin_name", "binding", "status", "extras"):
        assert envelope_key not in info, (
            f"machine info must not carry envelope key {envelope_key!r} — it is diagnostic "
            f"inventory, not a whoami-contract envelope"
        )


def test_main_emits_valid_json(patched_env, capsys: pytest.CaptureFixture) -> None:
    from coordinator_whoami.machine import main

    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert set(parsed.keys()) == _EXPECTED_KEYS


def test_main_disk_path_arg(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:  # Review: code-reviewer — nit: pytest.FixturePath → Path (pathlib.Path is the correct annotation)
    """--disk-path controls the disk[] entries in the output."""
    from coordinator_whoami.machine import main

    path_a = str(tmp_path)
    path_b = str(tmp_path.parent)

    rc = main(["--disk-path", path_a, "--disk-path", path_b])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)

    disk = parsed["disk"]
    assert isinstance(disk, list), f"disk must be a list, got {type(disk)}"
    assert len(disk) == 2, f"expected 2 disk entries for 2 --disk-path args, got {len(disk)}"
    returned_paths = {entry["path"] for entry in disk}
    # The probe normalises paths (e.g. resolves symlinks on some OSes), so assert
    # via containment rather than exact equality.
    for requested in (path_a, path_b):
        assert any(
            requested in p or p in requested
            for p in returned_paths
        ), f"no disk entry matched requested path {requested!r}; got {returned_paths}"


@pytest.mark.parametrize(
    "version,expected_prefix",
    [
        ("10.0.26200", "Windows 11"),  # build >= 22000
        ("10.0.22000", "Windows 11"),  # the Win11 boundary
        ("10.0.21999", "Windows 10"),  # just below the boundary
        ("10.0.19045", "Windows 10"),  # 22H2
    ],
)
def test_windows_11_vs_10_distinguished_by_build(
    monkeypatch: pytest.MonkeyPatch, version: str, expected_prefix: str
) -> None:
    """Regression: Win11 is NT 10.0, distinguished only by build >= 22000.

    A naive name='Windows' mislabels every Win11 host (the bug the machine surface
    exposed: build 26200 reported as bare 'Windows'/10.x).

    Build now sources from sys.getwindowsversion() (hang-free), not platform.version()
    — so the seam under test is getwindowsversion().build, and sys.platform is forced
    to 'win32' so the Windows branch runs regardless of the host this test runs on.
    """
    import platform as _platform
    import sys as _sys
    from types import SimpleNamespace

    from coordinator_whoami.host_probes import _probe_os

    build = int(version.split(".")[-1])
    monkeypatch.setattr(_sys, "platform", "win32")
    monkeypatch.setattr(
        _sys, "getwindowsversion",
        lambda: SimpleNamespace(major=10, minor=0, build=build),
        raising=False,
    )
    monkeypatch.setattr(_platform, "win32_edition", lambda: None)  # isolate from edition
    result = _probe_os()
    assert result["name"].startswith(expected_prefix), (
        f"build {version} must map to {expected_prefix!r}, got {result['name']!r}"
    )
