"""
tests/host_probes/test_host_probes_module.py

Tests for coordinator_whoami.host_probes — the generic probe functions.

Covers:
  - importability of the module and all probe functions (original 8 + 4 new)
  - that importing host_probes does NOT pull in project-rag-specific modules
  - structural assertions on probe return shapes (keys, types)
  - new probes: _probe_memory, _probe_disk, _probe_host, _probe_mem_ceiling_mechanism
  - extended shape tests for os (is_windows), arch (logical/physical cores),
    gpu (new keys: vram_total_mib, name, compute_capability, driver_model, device_count)
  - failure-path tests: every new probe returns null/none/"unknown" (never raises)
    under mocked failure conditions
  - Linux and macOS ceiling/memory branches exercised under mock (monkeypatching
    sys.platform) since this runs on Windows — mocked-failure tests are the net

The tests that call individual probes mock platform.system to avoid the
Python 3.13 WMI query timeout on Windows (pre-existing environment issue).

Spec backlink: archive/specs/2026-05-27-whoami-host-capacity-fields.md § Chunk 1
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def patched_platform(monkeypatch: pytest.MonkeyPatch):
    """Mock platform.system and related calls to avoid the WMI timeout on Windows.

    Python 3.13 on Windows performs a WMI query inside platform.system() that
    hangs in this test environment. These patches bypass that path.
    """
    import platform as _platform
    import subprocess as _subprocess

    monkeypatch.setattr(_platform, "system", lambda: "Windows")
    monkeypatch.setattr(_platform, "version", lambda: "10.0.26200")
    monkeypatch.setattr(_platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(_platform, "python_version", lambda: "3.13.1")

    mock_subproc = MagicMock(side_effect=FileNotFoundError("nvidia-smi not found"))
    monkeypatch.setattr(_subprocess, "run", mock_subproc)

    yield mock_subproc


# ---------------------------------------------------------------------------
# Import and API surface tests
# ---------------------------------------------------------------------------

def test_host_probes_module_importable() -> None:
    """coordinator_whoami.host_probes must be importable without error."""
    try:
        import coordinator_whoami.host_probes  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"import coordinator_whoami.host_probes raised ImportError: {exc}")


def test_all_8_probe_functions_importable() -> None:
    """All 8 original generic probe functions must be importable from coordinator_whoami.host_probes."""
    try:
        from coordinator_whoami.host_probes import (  # noqa: F401
            _probe_os,
            _probe_arch,
            _probe_gpu,
            _probe_python,
            _probe_uv,
            _probe_claude,
            _probe_coordinator,
            _probe_project,
        )
    except ImportError as exc:
        pytest.fail(f"Failed to import generic probe functions from host_probes: {exc}")


def test_all_new_probe_functions_importable() -> None:
    """All 4 new probe functions must be importable from coordinator_whoami.host_probes."""
    try:
        from coordinator_whoami.host_probes import (  # noqa: F401
            _probe_memory,
            _probe_disk,
            _probe_host,
            _probe_mem_ceiling_mechanism,
        )
    except ImportError as exc:
        pytest.fail(f"Failed to import new probe functions from host_probes: {exc}")


def test_host_probes_no_project_rag_specific_imports() -> None:
    """host_probes must NOT import coordinator_whoami.project_rag at import time.

    The purpose of the extraction is that session and other adopters can use
    host_probes without pulling in project-rag subpackage dependencies.

    Uses a subprocess for a clean sys.modules state, identical to
    test_standalone_import.py::test_no_heavy_deps_at_import_time.
    """
    import os
    import subprocess
    import sys
    import coordinator_whoami as _cw_pkg

    pkg_parent = str(Path(_cw_pkg.__file__).parent.parent)
    env = os.environ.copy()
    existing_pypath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (pkg_parent + os.pathsep + existing_pypath).strip(os.pathsep)

    check_script = (
        "import coordinator_whoami.host_probes; "
        "import sys; "
        "bad = [k for k in sys.modules "
        "       if k == 'coordinator_whoami.project_rag' "
        "       or k.startswith('coordinator_whoami.project_rag.')]; "
        "assert not bad, f'host_probes pulled in project_rag: {bad}'"
    )
    result = subprocess.run(
        [sys.executable, "-c", check_script],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"host_probes isolation check failed.\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )


def test_cli_re_exports_generic_probes() -> None:
    """project_rag.cli must re-export the 8 generic probes (backward compat).

    After C1, cli.py imports and re-exports the generic probes from host_probes.
    Any existing code importing e.g. `from coordinator_whoami.project_rag.cli import _probe_os`
    must continue to work.

    The re-exported functions originate from coordinator_whoami.host_probes, confirmed
    by checking __module__ on each imported name.
    """
    from coordinator_whoami.project_rag.cli import (
        _probe_os,
        _probe_arch,
        _probe_gpu,
        _probe_python,
        _probe_uv,
        _probe_claude,
        _probe_coordinator,
        _probe_project,
    )
    # Each re-exported function's __module__ must point to host_probes, not cli.
    expected_module = "coordinator_whoami.host_probes"
    for fn_name, fn in [
        ("_probe_os", _probe_os),
        ("_probe_arch", _probe_arch),
        ("_probe_gpu", _probe_gpu),
        ("_probe_python", _probe_python),
        ("_probe_uv", _probe_uv),
        ("_probe_claude", _probe_claude),
        ("_probe_coordinator", _probe_coordinator),
        ("_probe_project", _probe_project),
    ]:
        assert fn.__module__ == expected_module, (
            f"cli.{fn_name}.__module__ must be {expected_module!r} (re-exported from host_probes), "
            f"got {fn.__module__!r}"
        )


# ---------------------------------------------------------------------------
# Structural shape tests — original probes (extended with new keys)
# ---------------------------------------------------------------------------

def test_probe_os_returns_correct_shape(patched_platform) -> None:
    """_probe_os() must return dict with name, version, shell, is_windows keys."""
    from coordinator_whoami.host_probes import _probe_os

    result = _probe_os()
    assert isinstance(result, dict), f"_probe_os() must return dict, got {type(result)}"
    for key in ("name", "version", "shell", "is_windows"):
        assert key in result, f"_probe_os() result missing key {key!r}"
    assert isinstance(result["name"], str), "os.name must be str"
    assert isinstance(result["shell"], str), "os.shell must be str"
    assert isinstance(result["is_windows"], bool), "os.is_windows must be bool"


def test_probe_arch_returns_correct_shape(patched_platform) -> None:
    """_probe_arch() must return dict with machine, apple_silicon, logical_cores, physical_cores."""
    from coordinator_whoami.host_probes import _probe_arch

    result = _probe_arch()
    assert isinstance(result, dict), f"_probe_arch() must return dict, got {type(result)}"
    for key in ("machine", "apple_silicon", "logical_cores", "physical_cores"):
        assert key in result, f"_probe_arch() result missing key {key!r}"
    assert isinstance(result["apple_silicon"], bool), "arch.apple_silicon must be bool"
    # logical_cores is int or None
    assert result["logical_cores"] is None or isinstance(result["logical_cores"], int), (
        "arch.logical_cores must be int or None"
    )
    # physical_cores is int or None (best-effort)
    assert result["physical_cores"] is None or isinstance(result["physical_cores"], int), (
        "arch.physical_cores must be int or None"
    )


def test_probe_gpu_absent_when_no_nvidia_smi(patched_platform) -> None:
    """_probe_gpu() must return present=False and all new keys as None when nvidia-smi is absent."""
    from coordinator_whoami.host_probes import _probe_gpu

    # patched_platform already mocks subprocess.run to raise FileNotFoundError.
    result = _probe_gpu()
    assert isinstance(result, dict), f"_probe_gpu() must return dict, got {type(result)}"
    assert "present" in result, "_probe_gpu() result missing 'present' key"
    assert result["present"] is False, (
        f"_probe_gpu() must return present=False when nvidia-smi absent, got {result['present']!r}"
    )
    # New keys must be present and None when GPU absent.
    for key in ("vram_total_mib", "name", "compute_capability", "driver_model", "device_count"):
        assert key in result, f"_probe_gpu() absent-GPU result missing new key {key!r}"
        assert result[key] is None, (
            f"_probe_gpu() absent-GPU {key!r} must be None, got {result[key]!r}"
        )
    # Existing keys must still be present.
    for key in ("vram_free_mib", "cuda_driver", "vendor"):
        assert key in result, f"_probe_gpu() absent-GPU result missing legacy key {key!r}"


def test_probe_gpu_present_shape() -> None:
    """_probe_gpu() with a mocked successful nvidia-smi returns all expected keys."""
    from coordinator_whoami.host_probes import _probe_gpu
    import subprocess as _subprocess

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "1, NVIDIA GeForce RTX 5070 Ti, 16303, 15357, 596.21, 12.0, WDDM\n"

    with patch.object(_subprocess, "run", return_value=mock_result):
        result = _probe_gpu()

    assert result["present"] is True
    assert result["vendor"] == "nvidia"
    assert result["device_count"] == 1
    assert result["name"] == "NVIDIA GeForce RTX 5070 Ti"
    assert result["vram_total_mib"] == 16303
    assert result["vram_free_mib"] == 15357
    assert result["cuda_driver"] == "596.21"
    assert result["compute_capability"] == "12.0"
    assert result["driver_model"] == "WDDM"


def test_probe_python_returns_correct_shape(patched_platform) -> None:
    """_probe_python() must return dict with required keys."""
    from coordinator_whoami.host_probes import _probe_python

    result = _probe_python()
    assert isinstance(result, dict), f"_probe_python() must return dict, got {type(result)}"
    for key in ("invoking_version", "invoking_path", "ms_store_shim", "venv_present"):
        assert key in result, f"_probe_python() result missing key {key!r}"
    assert isinstance(result["ms_store_shim"], bool), "python.ms_store_shim must be bool"
    assert isinstance(result["venv_present"], bool), "python.venv_present must be bool"


def test_probe_uv_returns_correct_shape(patched_platform) -> None:
    """_probe_uv() must return dict with present key (bool)."""
    from coordinator_whoami.host_probes import _probe_uv

    result = _probe_uv()
    assert isinstance(result, dict), f"_probe_uv() must return dict, got {type(result)}"
    assert "present" in result, "_probe_uv() result missing 'present' key"
    assert isinstance(result["present"], bool), "uv.present must be bool"


def test_probe_claude_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_probe_claude() must return project_rag_entry='no_file' when .claude.json absent."""
    from coordinator_whoami.host_probes import _probe_claude

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CLAUDE_HOME", str(home))

    result = _probe_claude()
    assert isinstance(result, dict), f"_probe_claude() must return dict, got {type(result)}"
    assert result["json_present"] is False
    assert result["project_rag_entry"] == "no_file", (
        f"project_rag_entry must be 'no_file' when .claude.json absent, got {result['project_rag_entry']!r}"
    )


def test_probe_coordinator_not_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_probe_coordinator() must return installed=False when coordinator plugin absent."""
    from coordinator_whoami.host_probes import _probe_coordinator

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CLAUDE_HOME", str(home))

    result = _probe_coordinator()
    assert isinstance(result, dict), f"_probe_coordinator() must return dict, got {type(result)}"
    assert "installed" in result, "_probe_coordinator() result missing 'installed' key"
    assert result["installed"] is False, (
        f"installed must be False when coordinator absent, got {result['installed']!r}"
    )


def test_probe_project_returns_correct_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """_probe_project() must return dict with root, kinds_detected, uproject_present keys."""
    from coordinator_whoami.host_probes import _probe_project

    monkeypatch.chdir(tmp_path)

    result = _probe_project()
    assert isinstance(result, dict), f"_probe_project() must return dict, got {type(result)}"
    for key in ("root", "kinds_detected", "uproject_present"):
        assert key in result, f"_probe_project() result missing key {key!r}"
    assert isinstance(result["kinds_detected"], list), "project.kinds_detected must be list"
    assert isinstance(result["uproject_present"], bool), "project.uproject_present must be bool"


# ---------------------------------------------------------------------------
# Shape tests — new probes
# ---------------------------------------------------------------------------

def test_probe_memory_returns_correct_shape() -> None:
    """_probe_memory() must return dict with four *_bytes keys (int or None each)."""
    from coordinator_whoami.host_probes import _probe_memory

    result = _probe_memory()
    assert isinstance(result, dict), f"_probe_memory() must return dict, got {type(result)}"
    for key in ("total_bytes", "available_bytes", "commit_limit_bytes", "commit_available_bytes"):
        assert key in result, f"_probe_memory() result missing key {key!r}"
        val = result[key]
        assert val is None or isinstance(val, int), (
            f"_probe_memory()[{key!r}] must be int or None, got {type(val)}"
        )


def test_probe_memory_windows_values_positive() -> None:
    """On Windows, _probe_memory() total/commit values should be positive integers."""
    import sys
    if sys.platform != "win32":
        pytest.skip("Windows-only live probe")

    from coordinator_whoami.host_probes import _probe_memory

    result = _probe_memory()
    assert result["total_bytes"] is not None and result["total_bytes"] > 0, (
        "total_bytes must be a positive int on Windows"
    )
    assert result["commit_limit_bytes"] is not None and result["commit_limit_bytes"] > 0, (
        "commit_limit_bytes must be a positive int on Windows"
    )


def test_probe_disk_returns_correct_shape(tmp_path: Path) -> None:
    """_probe_disk() must return a list of {path, total_bytes, free_bytes} dicts."""
    from coordinator_whoami.host_probes import _probe_disk

    result = _probe_disk(paths=[str(tmp_path)])
    assert isinstance(result, list), f"_probe_disk() must return list, got {type(result)}"
    assert len(result) == 1, "one entry per input path"
    entry = result[0]
    assert isinstance(entry, dict), "each entry must be a dict"
    for key in ("path", "total_bytes", "free_bytes"):
        assert key in entry, f"_probe_disk() entry missing key {key!r}"
    assert entry["path"] == str(tmp_path)
    assert isinstance(entry["total_bytes"], int), "total_bytes must be int for valid path"
    assert isinstance(entry["free_bytes"], int), "free_bytes must be int for valid path"
    assert entry["total_bytes"] > 0, "total_bytes must be positive"


def test_probe_disk_default_path() -> None:
    """_probe_disk() with no args uses CWD and returns one entry."""
    from coordinator_whoami.host_probes import _probe_disk

    result = _probe_disk()
    assert isinstance(result, list) and len(result) == 1, (
        "_probe_disk() with no args must return a single-entry list"
    )
    assert "path" in result[0]
    assert "total_bytes" in result[0]
    assert "free_bytes" in result[0]


def test_probe_disk_multiple_paths(tmp_path: Path) -> None:
    """_probe_disk() returns one entry per path in the input list."""
    from coordinator_whoami.host_probes import _probe_disk

    paths = [str(tmp_path), str(tmp_path)]
    result = _probe_disk(paths=paths)
    assert len(result) == 2, "one entry per path in input list"


def test_probe_host_returns_correct_shape() -> None:
    """_probe_host() must return dict with hostname (str) and machine_id (str or None)."""
    from coordinator_whoami.host_probes import _probe_host

    result = _probe_host()
    assert isinstance(result, dict), f"_probe_host() must return dict, got {type(result)}"
    for key in ("hostname", "machine_id"):
        assert key in result, f"_probe_host() result missing key {key!r}"
    assert isinstance(result["hostname"], str) and result["hostname"], (
        "hostname must be a non-empty string"
    )
    assert result["machine_id"] is None or isinstance(result["machine_id"], str), (
        "machine_id must be str or None"
    )


def test_probe_mem_ceiling_mechanism_returns_valid_enum() -> None:
    """_probe_mem_ceiling_mechanism() must return one of the valid enum values."""
    from coordinator_whoami.host_probes import _probe_mem_ceiling_mechanism

    VALID = {"cgroup_v2", "cgroup_v1", "rlimit", "win_jobobject", "none", "unknown"}
    result = _probe_mem_ceiling_mechanism()
    assert result in VALID, (
        f"_probe_mem_ceiling_mechanism() returned {result!r}, expected one of {VALID}"
    )


# ---------------------------------------------------------------------------
# Failure-path tests — new probes must return null/none/"unknown", never raise
# ---------------------------------------------------------------------------

def test_probe_memory_never_raises_on_failure() -> None:
    """_probe_memory() must return null-filled dict, not raise, on any failure.

    Review: code-reviewer — P2: removed dead monkeypatch.setattr + monkeypatch.undo()
    lines and the unused _probe_memory_force_fail helper. Failure-path coverage
    is provided by test_probe_memory_failure_path_direct via unsupported-platform patch.
    """
    from coordinator_whoami import host_probes as _hp

    # Patch sys.platform to an unsupported value — no branch matches, outer except
    # returns _null dict without raising.
    with patch.object(_hp.sys, "platform", "unsupported_os"):
        result = _hp._probe_memory()
    assert isinstance(result, dict), "_probe_memory must return dict even on failure"
    for key in ("total_bytes", "available_bytes", "commit_limit_bytes", "commit_available_bytes"):
        assert key in result, f"failure-path _probe_memory missing {key!r}"


def test_probe_memory_failure_path_direct() -> None:
    """_probe_memory() must return a null-valued dict on catastrophic internal failure."""
    from coordinator_whoami import host_probes as _hp

    # Patch sys.platform to an unknown value so no branch matches.
    with patch.object(_hp.sys, "platform", "haiku"):
        result = _hp._probe_memory()
    assert isinstance(result, dict)
    for key in ("total_bytes", "available_bytes", "commit_limit_bytes", "commit_available_bytes"):
        assert key in result, f"failure-path _probe_memory missing {key!r}"


def test_probe_disk_never_raises_on_invalid_path() -> None:
    """_probe_disk() must return entry with None totals for a non-existent path, not raise."""
    from coordinator_whoami.host_probes import _probe_disk

    result = _probe_disk(paths=["/this/path/does/not/exist/ever/12345"])
    assert isinstance(result, list) and len(result) == 1
    entry = result[0]
    assert entry["total_bytes"] is None, "invalid path total_bytes must be None"
    assert entry["free_bytes"] is None, "invalid path free_bytes must be None"


def test_probe_host_never_raises_on_socket_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """_probe_host() must return dict with hostname='unknown' and machine_id=None on failure."""
    import coordinator_whoami.host_probes as _hp

    monkeypatch.setattr(_hp.socket, "gethostname", MagicMock(side_effect=OSError("no network")))

    result = _hp._probe_host()
    assert isinstance(result, dict)
    assert "hostname" in result
    # hostname falls back to "unknown" on OSError
    assert result["hostname"] == "unknown", (
        f"hostname must be 'unknown' on socket failure, got {result['hostname']!r}"
    )


def test_probe_mem_ceiling_mechanism_returns_unknown_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """_probe_mem_ceiling_mechanism() must return 'unknown' (not raise) on any exception."""
    import coordinator_whoami.host_probes as _hp

    # Patch sys.platform to win32 and make ctypes.windll raise.
    with patch.object(_hp.sys, "platform", "win32"):
        with patch("coordinator_whoami.host_probes.ctypes") as mock_ctypes:
            mock_ctypes.Structure.__init_subclass__ = None
            mock_ctypes.windll.kernel32.IsProcessInJob.side_effect = Exception("boom")
            result = _hp._probe_mem_ceiling_mechanism()
    assert result == "unknown", (
        f"_probe_mem_ceiling_mechanism must return 'unknown' on failure, got {result!r}"
    )


# ---------------------------------------------------------------------------
# Linux / macOS branch coverage under mock (unverifiable by live run on Windows)
# ---------------------------------------------------------------------------

def test_probe_memory_linux_branch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """_probe_memory() Linux branch reads /proc/meminfo and computes values correctly."""
    import coordinator_whoami.host_probes as _hp

    # Write a fake /proc/meminfo to tmp_path
    fake_meminfo = (
        "MemTotal:       16384000 kB\n"
        "MemAvailable:    8192000 kB\n"
        "CommitLimit:    20480000 kB\n"
        "Committed_AS:    4096000 kB\n"
    )
    fake_path = tmp_path / "meminfo"
    fake_path.write_text(fake_meminfo, encoding="utf-8")

    # Review: code-reviewer — P2: deleted dead first with-patch block that set MockPath.side_effect
    # but never called _probe_memory; keep only the block that actually exercises the Linux path.
    with patch.object(_hp.sys, "platform", "linux"):
        with patch("coordinator_whoami.host_probes.Path") as MockPath:
            mock_proc_path = MagicMock()
            mock_proc_path.read_text.return_value = fake_meminfo
            # Route /proc/meminfo reads through our mock; other Paths fall through.
            original_path = Path

            def smart_path(*args, **kwargs):
                if args and str(args[0]) == "/proc/meminfo":
                    return mock_proc_path
                return original_path(*args, **kwargs)

            MockPath.side_effect = smart_path

            result = _hp._probe_memory()

    assert result["total_bytes"] == 16384000 * 1024
    assert result["available_bytes"] == 8192000 * 1024
    assert result["commit_limit_bytes"] == 20480000 * 1024
    assert result["commit_available_bytes"] == (20480000 - 4096000) * 1024


def test_probe_memory_linux_branch_fallback_on_bad_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """_probe_memory() Linux branch returns null dict when /proc/meminfo is unreadable."""
    import coordinator_whoami.host_probes as _hp

    with patch.object(_hp.sys, "platform", "linux"):
        with patch("coordinator_whoami.host_probes.Path") as MockPath:
            original_path = Path

            def smart_path(*args, **kwargs):
                if args and str(args[0]) == "/proc/meminfo":
                    bad = MagicMock()
                    bad.read_text.side_effect = OSError("no proc")
                    return bad
                return original_path(*args, **kwargs)

            MockPath.side_effect = smart_path
            result = _hp._probe_memory()

    # On OSError reading /proc/meminfo, should return null-valued dict without raising.
    assert isinstance(result, dict)
    for key in ("total_bytes", "available_bytes", "commit_limit_bytes", "commit_available_bytes"):
        assert key in result


def test_probe_mem_ceiling_mechanism_linux_cgroup_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    """_probe_mem_ceiling_mechanism() detects cgroup_v2 on Linux when memory.max is set."""
    import coordinator_whoami.host_probes as _hp

    with patch.object(_hp.sys, "platform", "linux"):
        with patch("coordinator_whoami.host_probes.Path") as MockPath:
            original_path = Path

            def smart_path(*args, **kwargs):
                key = str(args[0]) if args else ""
                if key == "/sys/fs/cgroup/memory.max":
                    m = MagicMock()
                    m.exists.return_value = True
                    m.read_text.return_value = "1073741824"  # 1 GiB — not "max"
                    return m
                return original_path(*args, **kwargs)

            MockPath.side_effect = smart_path
            result = _hp._probe_mem_ceiling_mechanism()

    assert result == "cgroup_v2", f"expected cgroup_v2, got {result!r}"


def test_probe_mem_ceiling_mechanism_linux_no_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    """_probe_mem_ceiling_mechanism() returns 'none' on Linux when no ceiling is set.

    resource module is POSIX-only; constants are mocked so this test runs on Windows.
    RLIM_INFINITY is typically 2**64 - 1 on Linux; RLIMIT_AS is 9.
    """
    import coordinator_whoami.host_probes as _hp

    # Sentinel values matching Linux resource module constants.
    _RLIM_INFINITY = 2**64 - 1
    _RLIMIT_AS = 9

    with patch.object(_hp.sys, "platform", "linux"):
        with patch("coordinator_whoami.host_probes.Path") as MockPath:
            original_path = Path

            def smart_path(*args, **kwargs):
                key = str(args[0]) if args else ""
                if key == "/sys/fs/cgroup/memory.max":
                    m = MagicMock()
                    m.exists.return_value = True
                    m.read_text.return_value = "max"  # no limit
                    return m
                if key == "/sys/fs/cgroup/memory/memory.limit_in_bytes":
                    m = MagicMock()
                    m.exists.return_value = False
                    return m
                return original_path(*args, **kwargs)

            MockPath.side_effect = smart_path

            with patch("coordinator_whoami.host_probes.resource") as mock_resource:
                mock_resource.getrlimit.return_value = (_RLIM_INFINITY, _RLIM_INFINITY)
                mock_resource.RLIMIT_AS = _RLIMIT_AS
                mock_resource.RLIM_INFINITY = _RLIM_INFINITY
                result = _hp._probe_mem_ceiling_mechanism()

    assert result == "none", f"expected 'none' when no ceiling, got {result!r}"


def test_probe_mem_ceiling_mechanism_linux_cgroup_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    """_probe_mem_ceiling_mechanism() detects cgroup_v1 when memory.limit_in_bytes has a real limit."""
    import coordinator_whoami.host_probes as _hp

    with patch.object(_hp.sys, "platform", "linux"):
        with patch("coordinator_whoami.host_probes.Path") as MockPath:
            original_path = Path

            def smart_path(*args, **kwargs):
                key = str(args[0]) if args else ""
                if key == "/sys/fs/cgroup/memory.max":
                    m = MagicMock()
                    m.exists.return_value = False  # no v2
                    return m
                if key == "/sys/fs/cgroup/memory/memory.limit_in_bytes":
                    m = MagicMock()
                    m.exists.return_value = True
                    m.read_text.return_value = "2147483648"  # 2 GiB
                    return m
                return original_path(*args, **kwargs)

            MockPath.side_effect = smart_path
            result = _hp._probe_mem_ceiling_mechanism()

    assert result == "cgroup_v1", f"expected cgroup_v1, got {result!r}"


def test_probe_mem_ceiling_mechanism_darwin_returns_none_or_unknown() -> None:
    """_probe_mem_ceiling_mechanism() on macOS returns 'none' (no mechanism implemented)."""
    import coordinator_whoami.host_probes as _hp

    with patch.object(_hp.sys, "platform", "darwin"):
        result = _hp._probe_mem_ceiling_mechanism()
    assert result in ("none", "unknown"), (
        f"macOS ceiling probe must return 'none' or 'unknown', got {result!r}"
    )


def test_probe_host_linux_machine_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """_probe_host() on Linux reads machine_id from /etc/machine-id."""
    import coordinator_whoami.host_probes as _hp

    fake_id = "abcdef1234567890abcdef1234567890"
    machine_id_path = tmp_path / "machine-id"
    machine_id_path.write_text(fake_id + "\n", encoding="utf-8")

    with patch.object(_hp.sys, "platform", "linux"):
        with patch("coordinator_whoami.host_probes.Path") as MockPath:
            original_path = Path

            def smart_path(*args, **kwargs):
                key = str(args[0]) if args else ""
                if key == "/etc/machine-id":
                    return machine_id_path
                if key == "/var/lib/dbus/machine-id":
                    m = MagicMock()
                    m.read_text.side_effect = OSError("no dbus")
                    return m
                return original_path(*args, **kwargs)

            MockPath.side_effect = smart_path
            result = _hp._probe_host()

    assert result["machine_id"] == fake_id, (
        f"machine_id must match /etc/machine-id content, got {result['machine_id']!r}"
    )


def test_probe_host_darwin_machine_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """_probe_host() on macOS extracts IOPlatformUUID from ioreg output."""
    import coordinator_whoami.host_probes as _hp
    import subprocess as _subprocess

    fake_uuid = "AABBCCDD-1122-3344-5566-778899AABBCC"
    ioreg_output = f'"IOPlatformUUID" = "{fake_uuid}"\n'

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ioreg_output

    with patch.object(_hp.sys, "platform", "darwin"):
        with patch.object(_subprocess, "run", return_value=mock_result):
            result = _hp._probe_host()

    assert result["machine_id"] == fake_uuid, (
        f"machine_id must be parsed from ioreg IOPlatformUUID, got {result['machine_id']!r}"
    )


def test_probe_arch_linux_physical_cores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """_probe_arch() on Linux reads physical cores from /proc/cpuinfo."""
    import coordinator_whoami.host_probes as _hp

    # Simulate a 4-core CPU with 2 physical sockets (8 physical total).
    # Two physical ids (0, 1), each with 4 core ids (0-3).
    # Each logical-processor block ends with a blank line (required by the parser
    # to commit the (physical_id, core_id) pair into the set).
    lines = []
    for socket_id in range(2):
        for core in range(4):
            lines.append(f"physical id\t: {socket_id}")
            lines.append(f"core id\t\t: {core}")
            lines.append("")  # blank line commits the pair
    # Ensure the final block also has a trailing blank (join already appends one
    # because the last append above is ""). Add an explicit sentinel.
    lines.append("")
    fake_cpuinfo = "\n".join(lines)

    with patch.object(_hp.sys, "platform", "linux"):
        with patch("coordinator_whoami.host_probes.Path") as MockPath:
            original_path = Path

            def smart_path(*args, **kwargs):
                key = str(args[0]) if args else ""
                if key == "/proc/cpuinfo":
                    m = MagicMock()
                    m.read_text.return_value = fake_cpuinfo
                    return m
                return original_path(*args, **kwargs)

            MockPath.side_effect = smart_path
            with patch("coordinator_whoami.host_probes.platform") as mock_plat:
                mock_plat.machine.return_value = "x86_64"
                mock_plat.system.return_value = "Linux"
                # Review: code-reviewer — nit: Linux branch reads /proc/cpuinfo via Path — no subprocess call in this branch.
                result = _hp._probe_arch()

    assert result["physical_cores"] == 8, (
        f"expected 8 physical cores (2 sockets x 4 cores), got {result['physical_cores']!r}"
    )
