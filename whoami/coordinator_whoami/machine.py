"""coordinator_whoami/machine.py — machine-info diagnostic surface.

Emits host machine/toolchain inventory (OS, arch, GPU, mem, disk, host,
mem_ceiling_mechanism, Python, uv) as plain JSON, sourced from the shared
`coordinator_whoami.host_probes` module. This is a DIAGNOSTIC surface, NOT
a cross-plugin whoami envelope: machine-state is not a *binding* (it is bound
to nothing) and carries no binding/status health verdict, so it deliberately
does not conform to whoami-envelope.v1.json. It exists so a doctor surface can
show "what host am I on" (GPU/Python/OS/RAM/disk) — distinct from the
orientation-health spine (`coordinator_whoami.session`) and the plugin-binding
adopters (`coordinator_whoami.project_rag`).

Provenance: the eight generic probes were extracted to host_probes in the
2026-05-27 whoami-session-spine refactor (C1). After C6 thinned them out of the
project_rag adopter's emitted envelope, machine-state was surfaced by no envelope;
this module is the deliberate diagnostic home (PM request, 2026-05-27).

Keys emitted by compose_machine():
    os, arch, gpu, mem, disk, host, mem_ceiling_mechanism, python, uv

Spec backlink: archive/specs/2026-05-27-whoami-host-capacity-fields.md § Chunk 2

Usage:
    python -m coordinator_whoami.machine                              # compact JSON
    python -m coordinator_whoami.machine --human                     # pretty-printed
    python -m coordinator_whoami.machine --disk-path /mnt/data       # specific volume
    python -m coordinator_whoami.machine --disk-path /vol1 --disk-path /vol2  # multi-volume
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# review: F10 — these _probe_* functions are intentional internal-caller imports;
# machine.py and the session adopter are in-package consumers with standing to use them.
# (reviewer: code-reviewer, nit — underscores preserved, no API churn)
from coordinator_whoami.host_probes import (
    _probe_arch,
    _probe_disk,
    _probe_gpu,
    _probe_host,
    _probe_mem_ceiling_mechanism,
    _probe_memory,
    _probe_os,
    _probe_python,
    _probe_uv,
)


def compose_machine(disk_paths: list[str] | None = None) -> dict[str, Any]:
    """Return the host machine/toolchain inventory.

    Keys: os, arch, gpu, mem, disk, host, mem_ceiling_mechanism, python, uv —
    sourced from host_probes. No binding, no status: this is machine inventory,
    not a health envelope.

    Args:
        disk_paths: paths to probe for disk usage; defaults to [cwd] when None
                    (delegated to _probe_disk's own default).
    """
    return {
        "os": _probe_os(),
        "arch": _probe_arch(),
        "gpu": _probe_gpu(),
        "mem": _probe_memory(),
        "disk": _probe_disk(disk_paths),
        "host": _probe_host(),
        "mem_ceiling_mechanism": _probe_mem_ceiling_mechanism(),
        "python": _probe_python(),
        "uv": _probe_uv(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit host machine/toolchain inventory as JSON."
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    parser.add_argument(
        "--disk-path",
        dest="disk_paths",
        action="append",
        metavar="PATH",
        help="Probe disk usage for PATH (repeatable; default: cwd).",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    info = compose_machine(disk_paths=args.disk_paths)
    print(json.dumps(info, indent=2) if args.human else json.dumps(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
