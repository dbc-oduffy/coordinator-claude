#!/usr/bin/env python3
"""host-gpu-probe — standalone GPU probe, the sole surviving successor of coordinator_whoami.

coordinator_whoami (DoE-claude `coordinator/whoami/`) was retired
(archive/specs/2026-08-23-retire-coordinator-whoami-entirely.md). Of its twelve host probes,
project-rag and example-game-repo were asked directly which they still need, and both independently
answered GPU-only — see that plan's C9 chunk for the full consumer ruling and the citations
below. This module ports `_probe_gpu` (and its two direct helpers, `_nvidia_smi_absent` and
`_sysctl_str`, plus the `_read_hardware_concern` registry read the Apple Silicon branch uses)
verbatim from `coordinator_whoami/host_probes.py`. `_probe_mem_ceiling_mechanism` was NOT
ported — both consumers ruled it deleted: it returns "unknown" on this box even with whoami
installed and working, and neither project-rag nor example-game-repo has a live caller that reads its
value (example-game-repo's are dead plumbing — a test-only Python reference and an unused TS definition).

INVOCATION CONTRACT — subprocess only, by absolute path. This is a plain `coordinator/bin/`
module, never an importable package: project-rag's contract bans importing whoami-shaped
capability (core/host_inventory.py:6-11, "LOAD-BEARING -- do NOT replace with Python import"),
and publishing a sixth editable install for an ~80-line module was ruled out by example-game-repo as
campaign owner (a global name is the weakest possible shape for this size). Consumers shell out:

    python <repo>/coordinator/bin/host-gpu-probe.py

and read one JSON object off stdout, shaped `{"gpu": {...}}` — the same twelve-key gpu envelope
`coordinator_whoami.machine` published under its `gpu` key (present, vendor, vram_free_mib,
cuda_driver, vram_total_mib, name, compute_capability, driver_model, device_count, integrated,
unified_memory_bytes, mps_capable).

Known project-rag consumers: install_project_rag_plugin.py:2045 (torch/CUDA wheel selection),
probe_text_embed_producibility.py:41.
Known example-game-repo consumers: preflight_checks.py:406,416,487; diagnose_gpu.py:73,123,316,322;
gpu_sidecar/app.py:905; gpu_sidecar/lifecycle.py:870,902,923 (WDDM sysmem-fallback warning).

Negative spec: this module does NOT import torch, chromadb, or any heavy ML dependency — stdlib
+ subprocess only, matching the source module's own constraint. It does NOT port
`_probe_mem_ceiling_mechanism`, the OS probe, the memory probe, or any of the other nine
`host_probes.py` functions — GPU only, per the consumer ruling above. It does NOT become an
importable package member of anything — it is invoked by absolute path as a standalone script.

Path resolution: no DoE-relative path is used anywhere in this module. `_settings_home` resolves
purely through env vars (`COORDINATOR_SETTINGS_HOME`, else `CLAUDE_HOME`-or-`HOME`), never through
`Path(__file__)`'s parent chain — so this is a byte-for-byte mechanical move, arity fixed to
`main(argv)` per § Path resolution / warm-servability (`coordinator_core.warm.serve_classifier`).

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W3-C4.
"""
from __future__ import annotations

import functools
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Windows-only: suppress the console window that console-subsystem child
# processes (nvidia-smi, sysctl is POSIX-only so unaffected) flash when this
# process has no console to inherit. POSIX: empty dict.
_NO_CONSOLE_WINDOW = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
)


def _settings_home() -> Path:
    """coordinator-settings-home root, by pure path arithmetic (never a file read).

    Ported verbatim from coordinator_whoami/host_probes.py::_settings_home — same
    two-rung precedence every settings-home consumer in this repo carries
    (COORDINATOR_SETTINGS_HOME override, else CLAUDE_HOME-or-HOME joined with
    ".coordinator-claude-settings").
    """
    override = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if override:
        return Path(override)
    home = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(home) / ".coordinator-claude-settings"


def _read_hardware_concern() -> dict[str, Any]:
    """In-process, zero-subprocess read of the `hardware` machine-local concern.

    Ported verbatim from coordinator_whoami/host_probes.py::_read_hardware_concern.
    Fails open on every rung: pre-3.11 interpreter (no tomllib), missing settings-home,
    missing/unreadable/malformed TOML, or an empty/absent `[hardware]` table all return
    `{}` — callers MUST treat `{}` as "probe live", never as an error.
    """
    try:
        import tomllib
    except ImportError:
        return {}

    reg_dir = _settings_home() / "machine-local"
    hw: dict[str, Any] = {}

    for name in ("hardware.toml", "hardware.local.toml"):
        path = reg_dir / name
        try:
            if not path.is_file():
                continue
            with path.open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        hw_table = data.get("hardware")
        if isinstance(hw_table, dict):
            hw.update(hw_table)

    if not hw:
        return {}

    def _int_or_none(v: Any) -> int | None:
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    gpu_val = hw.get("gpu")
    return {
        "cores": _int_or_none(hw.get("cores")),
        "ram_gb": _int_or_none(hw.get("ram_gb")),
        "gpu": gpu_val if isinstance(gpu_val, str) and gpu_val else None,
        "vram_gb": _int_or_none(hw.get("vram_gb")),
    }


def _sysctl_str(key: str) -> str | None:
    """Read a single sysctl key as a string; return None on any failure.

    Ported verbatim from coordinator_whoami/host_probes.py::_sysctl_str.
    """
    try:
        r = subprocess.run(
            ["sysctl", "-n", key],
            capture_output=True,
            text=True,
            timeout=5,
            **_NO_CONSOLE_WINDOW,
        )
        if r.returncode == 0:
            val = r.stdout.strip()
            return val if val else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
        pass
    return None


@functools.lru_cache(maxsize=1)
def _nvidia_smi_absent() -> bool:
    """True when `nvidia-smi` is not on PATH. Resolved once per process.

    Ported verbatim from coordinator_whoami/host_probes.py::_nvidia_smi_absent. Only
    absence is cached — a machine fact that cannot change mid-process; the SUCCESS path
    (vram_free_mib etc.) stays live, never cached.
    """
    return shutil.which("nvidia-smi") is None


def _probe_gpu() -> dict[str, Any]:
    """Probe GPU presence via nvidia-smi or Apple Silicon sysctl (no torch import).

    Ported verbatim from coordinator_whoami/host_probes.py::_probe_gpu (host_probes.py:470).

    Returns keys: present, vendor, vram_free_mib, cuda_driver,
    vram_total_mib, name, compute_capability, driver_model, device_count,
    integrated, unified_memory_bytes, mps_capable.

    All-branches shape totality: all twelve keys are present in every return dict.
    On non-NVIDIA/non-Apple-Silicon machines, present=False and all keys are None
    except integrated=False and mps_capable=False (boolean, not None).

    Apple Silicon branch (Darwin arm64, nvidia-smi absent/failing):
      present=True, vendor="apple", name=machdep.cpu.brand_string,
      integrated=True, unified_memory_bytes=hw.memsize (bytes, int),
      mps_capable=True (derived from Darwin+arm64 — NO torch import).
      Nvidia-only fields (cuda_driver, compute_capability, driver_model,
      vram_total_mib, vram_free_mib, device_count) are None.

    Per-device fields (vram_total_mib, vram_free_mib, name, compute_capability,
    driver_model) describe device 0 only; device_count is the total across all
    devices. Multi-GPU per-device enumeration is out of scope — consumers that
    need per-device breakdown must query nvidia-smi independently.

    nvidia-smi query column order:
      count, name, memory.total(MiB), memory.free(MiB),
      driver_version, compute_cap, driver_model.current
    """
    if not _nvidia_smi_absent():
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=count,name,memory.total,memory.free,driver_version,compute_cap,driver_model.current",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                **_NO_CONSOLE_WINDOW,
            )
            if result.returncode == 0:
                lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
                if lines:
                    parts = [p.strip() for p in lines[0].split(",")]

                    def _int_or_none(val: str) -> int | None:
                        try:
                            return int(val)
                        except (ValueError, TypeError):
                            return None

                    def _str_or_none(val: str) -> str | None:
                        if not val or val.upper() in ("N/A", "[N/A]"):
                            return None
                        return val

                    device_count = _int_or_none(parts[0]) if len(parts) > 0 else None
                    gpu_name = _str_or_none(parts[1]) if len(parts) > 1 else None
                    vram_total = _int_or_none(parts[2]) if len(parts) > 2 else None
                    vram_free = _int_or_none(parts[3]) if len(parts) > 3 else None
                    driver = _str_or_none(parts[4]) if len(parts) > 4 else None
                    compute_cap = _str_or_none(parts[5]) if len(parts) > 5 else None
                    driver_model = _str_or_none(parts[6]) if len(parts) > 6 else None

                    return {
                        "present": True,
                        "vendor": "nvidia",
                        "vram_free_mib": vram_free,
                        "cuda_driver": driver,
                        "vram_total_mib": vram_total,
                        "name": gpu_name,
                        "compute_capability": compute_cap,
                        "driver_model": driver_model,
                        "device_count": device_count,
                        # Apple Silicon keys — absent on NVIDIA branch.
                        "integrated": False,
                        "unified_memory_bytes": None,
                        "mps_capable": False,
                    }
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError, ValueError):
            pass

    # Apple Silicon branch: Darwin + arm64 + no working nvidia-smi.
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        chip_name = _read_hardware_concern().get("gpu") or _sysctl_str("machdep.cpu.brand_string")
        unified_memory_bytes: int | None = None
        try:
            memsize_str = _sysctl_str("hw.memsize")
            if memsize_str is not None:
                unified_memory_bytes = int(memsize_str)
        except (ValueError, TypeError):
            unified_memory_bytes = None
        return {
            "present": True,
            "vendor": "apple",
            "name": chip_name,
            "integrated": True,
            "unified_memory_bytes": unified_memory_bytes,
            "mps_capable": True,
            # NVIDIA-only fields absent on Apple Silicon.
            "vram_free_mib": None,
            "cuda_driver": None,
            "vram_total_mib": None,
            "compute_capability": None,
            "driver_model": None,
            "device_count": None,
        }

    return {
        "present": False,
        "vendor": None,
        "vram_free_mib": None,
        "cuda_driver": None,
        "vram_total_mib": None,
        "name": None,
        "compute_capability": None,
        "driver_model": None,
        "device_count": None,
        # Apple Silicon keys — absent on no-GPU fallback branch.
        "integrated": False,
        "unified_memory_bytes": None,
        "mps_capable": False,
    }


def _absent_envelope() -> dict[str, Any]:
    """The all-None, present=False envelope — the shape every consumer degrades to."""
    return {
        "present": False,
        "vendor": None,
        "vram_free_mib": None,
        "cuda_driver": None,
        "vram_total_mib": None,
        "name": None,
        "compute_capability": None,
        "driver_model": None,
        "device_count": None,
        "integrated": False,
        "unified_memory_bytes": None,
        "mps_capable": False,
    }


def main(argv: list[str] | None = None) -> int:
    """Emit `{"gpu": <envelope>}` as JSON on stdout. Always exits 0, always well-formed.

    `argv` is accepted (never parsed — this CLI takes no arguments) so the warm door can call
    `main(argv)` uniformly across every `coordinator/bin/` entrypoint
    (`coordinator_core.warm.serve_classifier :: _main_arity_ok`); the door still replays
    `sys.argv[1:]` from the `__main__` guard below (ARGV_SHAPE_TAIL).

    The catch-all is STRUCTURAL, not redundant. `_probe_gpu`'s branches are each
    individually fail-open, but "therefore nothing can escape" is an argument from
    exhaustive exception enumeration, and that argument silently stops being true the
    first time a branch grows a call whose failure mode nobody re-enumerated. Consumers
    are fail-open by contract and degrade on the ENVELOPE; they cannot degrade on a
    traceback and a non-zero exit, which is what an escaped exception hands them
    instead of JSON.

    This is the shape the retirement that produced this file kept finding: a guard that
    cannot run reads as a guard that passed. Here the guard is present rather than
    argued.
    """
    del argv  # unused — see docstring
    try:
        envelope = _probe_gpu()
    except Exception:  # noqa: BLE001 — fail-open contract; never a traceback to a consumer
        envelope = _absent_envelope()
    print(json.dumps({"gpu": envelope}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
