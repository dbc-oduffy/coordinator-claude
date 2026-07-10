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
Apple Silicon enrichment spec: docs/plans/2026-06-23-macos-whoami-apple-silicon-inventory.md § C1
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


def _make_apple_silicon_subprocess_mock() -> MagicMock:
    """Build a subprocess.run MagicMock keyed on sysctl argv for Apple Silicon tests.

    nvidia-smi raises FileNotFoundError (absent on Apple Silicon).
    sysctl calls return synthetic M5 Pro values matching EM-verified live data (2026-06-23).
    Any other subprocess.run call raises FileNotFoundError to isolate unrelated probes.
    """
    _SYSCTL_RESPONSES = {
        "hw.physicalcpu": "15",
        "hw.perflevel0.physicalcpu": "5",
        "hw.perflevel1.physicalcpu": "10",
        "machdep.cpu.brand_string": "Apple M5 Pro",
        "hw.model": "Mac17,9",
        "hw.memsize": "25769803776",
    }

    def _side_effect(argv, **kwargs):
        # nvidia-smi: always absent on Apple Silicon.
        if argv and argv[0] == "nvidia-smi":
            raise FileNotFoundError("no nvidia-smi on Apple Silicon")
        # sysctl: argv is ["sysctl", "-n", <key>]
        if argv and argv[0] == "sysctl" and len(argv) == 3:
            key = argv[2]
            if key in _SYSCTL_RESPONSES:
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = _SYSCTL_RESPONSES[key] + "\n"
                return mock_result
            # Unknown key: simulate sysctl returning non-zero (key absent).
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            return mock_result
        # All other subprocess calls (vm_stat, ioreg, uv, powershell, …) fail.
        raise FileNotFoundError(f"command not found: {argv[0] if argv else '?'}")

    return MagicMock(side_effect=_side_effect)


@pytest.fixture()
def apple_silicon_env(monkeypatch: pytest.MonkeyPatch):
    """Patch platform.* + subprocess.run to simulate an Apple Silicon Mac (M5 Pro)."""
    import platform as _platform
    import subprocess as _subprocess
    import sys as _sys

    monkeypatch.setattr(_platform, "system", lambda: "Darwin")
    monkeypatch.setattr(_platform, "version", lambda: "24.0.0")
    monkeypatch.setattr(_platform, "machine", lambda: "arm64")
    monkeypatch.setattr(_platform, "python_version", lambda: "3.13.1")
    monkeypatch.setattr(_sys, "platform", "darwin")
    monkeypatch.setattr(_subprocess, "run", _make_apple_silicon_subprocess_mock())
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
    # AC3 — all-branches shape totality: new Apple Silicon GPU keys must be present
    # on the Windows/absent branch too (present=False path). Values may be None/False.
    assert "integrated" in info["gpu"], "gpu missing 'integrated' key on non-Apple branch"
    assert "unified_memory_bytes" in info["gpu"], "gpu missing 'unified_memory_bytes' key on non-Apple branch"
    assert "mps_capable" in info["gpu"], "gpu missing 'mps_capable' key on non-Apple branch"
    # On a Windows/absent branch, mps_capable and integrated must be False (not None).
    assert info["gpu"]["mps_capable"] is False, (
        f"gpu['mps_capable'] must be False on non-Apple branch, got {info['gpu']['mps_capable']!r}"
    )
    assert info["gpu"]["integrated"] is False, (
        f"gpu['integrated'] must be False on non-Apple branch, got {info['gpu']['integrated']!r}"
    )
    assert info["gpu"]["unified_memory_bytes"] is None, (
        f"gpu['unified_memory_bytes'] must be None on non-Apple branch, got {info['gpu']['unified_memory_bytes']!r}"
    )
    # arch sub-shape (existing keys)
    assert "logical_cores" in info["arch"]
    assert "physical_cores" in info["arch"]
    # AC3 — new arch keys must be present (None on non-Apple-Silicon)
    assert "performance_cores" in info["arch"], "arch missing 'performance_cores' key"
    assert "efficiency_cores" in info["arch"], "arch missing 'efficiency_cores' key"
    assert "chip" in info["arch"], "arch missing 'chip' key"
    assert "model" in info["arch"], "arch missing 'model' key"
    assert info["arch"]["performance_cores"] is None, (
        f"arch['performance_cores'] must be None on non-Apple-Silicon, got {info['arch']['performance_cores']!r}"
    )
    assert info["arch"]["efficiency_cores"] is None, (
        f"arch['efficiency_cores'] must be None on non-Apple-Silicon, got {info['arch']['efficiency_cores']!r}"
    )
    # Review: code-reviewer — nit (F13): chip/model only had key-presence asserts; add None value asserts.
    assert info["arch"]["chip"] is None, (
        f"arch['chip'] must be None on non-Apple-Silicon, got {info['arch']['chip']!r}"
    )
    assert info["arch"]["model"] is None, (
        f"arch['model'] must be None on non-Apple-Silicon, got {info['arch']['model']!r}"
    )
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


# ---------------------------------------------------------------------------
# AC1 — Apple Silicon _probe_gpu() assertions
# ---------------------------------------------------------------------------

def test_probe_gpu_apple_silicon(apple_silicon_env) -> None:
    """AC1: _probe_gpu() returns the Apple Silicon shape on Darwin arm64 without nvidia-smi."""
    from coordinator_whoami.host_probes import _probe_gpu

    gpu = _probe_gpu()

    assert gpu["present"] is True, f"gpu['present'] must be True, got {gpu['present']!r}"
    assert gpu["vendor"] == "apple", f"gpu['vendor'] must be 'apple', got {gpu['vendor']!r}"
    assert gpu["integrated"] is True, f"gpu['integrated'] must be True, got {gpu['integrated']!r}"
    assert gpu["mps_capable"] is True, f"gpu['mps_capable'] must be True, got {gpu['mps_capable']!r}"
    assert isinstance(gpu["name"], str) and gpu["name"], (
        f"gpu['name'] must be a non-empty string, got {gpu['name']!r}"
    )
    assert isinstance(gpu["unified_memory_bytes"], int) and gpu["unified_memory_bytes"] == 25769803776, (
        f"gpu['unified_memory_bytes'] must be 25769803776, got {gpu['unified_memory_bytes']!r}"
    )
    # NVIDIA-only keys must be None on the Apple Silicon branch.
    for nvidia_key in ("cuda_driver", "compute_capability", "driver_model", "vram_total_mib", "vram_free_mib"):
        assert gpu[nvidia_key] is None, (
            f"gpu[{nvidia_key!r}] must be None on Apple Silicon branch, got {gpu[nvidia_key]!r}"
        )


# ---------------------------------------------------------------------------
# AC2 — Apple Silicon _probe_arch() assertions
# ---------------------------------------------------------------------------

def test_probe_arch_apple_silicon(apple_silicon_env) -> None:
    """AC2: _probe_arch() returns performance_cores/efficiency_cores/chip/model on Darwin arm64."""
    from coordinator_whoami.host_probes import _probe_arch

    arch = _probe_arch()

    assert arch["performance_cores"] == 5, (
        f"arch['performance_cores'] must be 5 (hw.perflevel0), got {arch['performance_cores']!r}"
    )
    assert arch["efficiency_cores"] == 10, (
        f"arch['efficiency_cores'] must be 10 (hw.perflevel1), got {arch['efficiency_cores']!r}"
    )
    assert arch["chip"] == "Apple M5 Pro", (
        f"arch['chip'] must be 'Apple M5 Pro', got {arch['chip']!r}"
    )
    assert arch["model"] == "Mac17,9", (
        f"arch['model'] must be 'Mac17,9', got {arch['model']!r}"
    )
    # Existing fields must still be populated.
    assert arch["apple_silicon"] is True
    assert arch["machine"] == "arm64"
    assert isinstance(arch["physical_cores"], int) and arch["physical_cores"] == 15


# ---------------------------------------------------------------------------
# AC3 — all-branches totality via _probe_gpu() direct call on Windows/absent branch
# ---------------------------------------------------------------------------

def test_probe_gpu_absent_branch_has_all_keys(patched_env) -> None:
    """AC3: _probe_gpu() present=False branch includes integrated/unified_memory_bytes/mps_capable."""
    from coordinator_whoami.host_probes import _probe_gpu

    gpu = _probe_gpu()

    assert gpu["present"] is False
    # All three Apple Silicon keys must be PRESENT (all-branches-shape totality).
    assert "integrated" in gpu, "gpu missing 'integrated' key on absent branch"
    assert "unified_memory_bytes" in gpu, "gpu missing 'unified_memory_bytes' key on absent branch"
    assert "mps_capable" in gpu, "gpu missing 'mps_capable' key on absent branch"
    # Convention: False (bool, not None) for integrated and mps_capable on non-Apple branches.
    assert gpu["integrated"] is False
    assert gpu["mps_capable"] is False
    assert gpu["unified_memory_bytes"] is None


# ---------------------------------------------------------------------------
# F2 — NVIDIA-SUCCESS branch of _probe_gpu() (previously untested)
# Review: code-reviewer — P2: NVIDIA branch was not exercised by any test;
# only the absent/FileNotFoundError branch was covered.
# ---------------------------------------------------------------------------

def test_probe_gpu_nvidia_success_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """F2: _probe_gpu() NVIDIA-SUCCESS branch: present=True, vendor='nvidia', integrated=False, mps_capable=False."""
    import platform as _platform
    import subprocess as _subprocess

    # Force non-Darwin so the Apple Silicon branch cannot fire.
    monkeypatch.setattr(_platform, "system", lambda: "Linux")
    monkeypatch.setattr(_platform, "machine", lambda: "x86_64")

    # nvidia-smi CSV matching the probe's query column order:
    # count, name, memory.total(MiB), memory.free(MiB), driver_version, compute_cap, driver_model.current
    nvidia_smi_line = "1, NVIDIA GeForce RTX 4090, 24000, 20000, 535.0, 8.9, WDDM"

    def _side_effect(argv, **kwargs):
        if argv and argv[0] == "nvidia-smi":
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = nvidia_smi_line + "\n"
            return mock_result
        # All other subprocess calls (uv, sysctl, …) fail.
        raise FileNotFoundError(f"command not found: {argv[0] if argv else '?'}")

    monkeypatch.setattr(_subprocess, "run", MagicMock(side_effect=_side_effect))

    from coordinator_whoami.host_probes import _probe_gpu

    gpu = _probe_gpu()

    assert gpu["present"] is True, f"gpu['present'] must be True on NVIDIA branch, got {gpu['present']!r}"
    assert gpu["vendor"] == "nvidia", f"gpu['vendor'] must be 'nvidia', got {gpu['vendor']!r}"
    # Apple Silicon keys must be present and False/None on NVIDIA branch (all-branches-shape totality).
    assert "integrated" in gpu, "gpu missing 'integrated' key on NVIDIA branch"
    assert "unified_memory_bytes" in gpu, "gpu missing 'unified_memory_bytes' key on NVIDIA branch"
    assert "mps_capable" in gpu, "gpu missing 'mps_capable' key on NVIDIA branch"
    assert gpu["integrated"] is False, (
        f"gpu['integrated'] must be False on NVIDIA branch, got {gpu['integrated']!r}"
    )
    assert gpu["unified_memory_bytes"] is None, (
        f"gpu['unified_memory_bytes'] must be None on NVIDIA branch, got {gpu['unified_memory_bytes']!r}"
    )
    assert gpu["mps_capable"] is False, (
        f"gpu['mps_capable'] must be False on NVIDIA branch, got {gpu['mps_capable']!r}"
    )


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
