#!/usr/bin/env python3
"""box-memory-snapshot.py [--top N] [--admit-peak GIB] -- one-screen box memory snapshot (Windows and macOS).

On macOS available is the kernel figure, commit limit is physical + swap capacity, nonpaged pool
and cache fields print `unavailable`, and top consumers rank by `ri_phys_footprint` (resident +
compressed + swapped), which can far exceed `ps` RSS. Prints Available, commit used vs limit, system cache working set, standby, nonpaged pool and the
top N consumers by private commit. A counter that fails to read prints `unavailable` for that
field alone. `--admit-peak GIB` adds one line, `ADMIT ...` (exit 0) or `HOLD ...` naming the
failed clause (exit 4); the figure is net of `reserved=`, the sum over live START pids without an
END in admission.jsonl of max(0, declared_peak_mb - tree RSS). `--json` emits the same fields. Other hosts: exit 6.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional

PROG = "box-memory-snapshot"
_LIB = Path(__file__).resolve().parent / "lib"
_UNAVAILABLE = "unavailable"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _LIB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # the host's @dataclass classes resolve annotations through it
    spec.loader.exec_module(module)
    return module


def _load_cache_host():
    """Instantiate the promoted Win32FileCacheHost; its sibling import needs lib on sys.path."""
    if str(_LIB) not in sys.path:
        sys.path.insert(0, str(_LIB))
    import file_cache_win32

    return file_cache_win32.Win32FileCacheHost()


def _gib(value: int) -> float:
    return round(value / 1024**3, 2)


def _try(fn: Callable):
    try:
        return fn()
    except Exception:
        return None


def _top_consumers_gov(gov, top: int) -> list:
    foot = gov.footprints()
    cmds = {p.pid: p.cmd for p in gov.list_procs()}
    ranked = sorted(foot.items(), key=lambda kv: kv[1], reverse=True)[:top]
    return [
        {"pid": pid, "private_commit_mb": round(mb, 1), "cmd": cmds.get(pid, "")[:100]}
        for pid, mb in ranked
    ]


def _top_consumers_table(proc_table_fn: Callable, cmdline_fn: Callable, top: int) -> list:
    """Rank the one process-table read by private bytes; read a cmdline for the top N rows only."""
    ranked = sorted(proc_table_fn(), key=lambda r: r.private_bytes, reverse=True)[: max(top, 0)]
    return [
        {
            "pid": r.pid,
            "private_commit_mb": round(r.private_bytes / 1024**2, 1),
            "cmd": (cmdline_fn(r.pid) or "")[:100],
        }
        for r in ranked
    ]


def build_snapshot(status, nonpaged_fn, cache_host_fn, consumers_fn: Callable, top: int) -> dict:
    cache = _try(lambda: cache_host_fn().read_memory())
    nonpaged = _try(nonpaged_fn)
    consumers = _try(lambda: consumers_fn(top))
    return {
        "available_gib": _gib(status.avail_phys) if status else _UNAVAILABLE,
        "commit_used_gib": _gib(status.commit_used) if status else _UNAVAILABLE,
        "commit_limit_gib": _gib(status.commit_limit) if status else _UNAVAILABLE,
        "system_cache_ws_gib": _gib(cache.cache_bytes) if cache else _UNAVAILABLE,
        "standby_gib": _gib(cache.standby_bytes) if cache else _UNAVAILABLE,
        "nonpaged_pool_gib": _gib(nonpaged) if nonpaged is not None else _UNAVAILABLE,
        "top_consumers": consumers if consumers is not None else _UNAVAILABLE,
    }


def _render(snap: dict) -> str:
    lines = [
        f"Available:        {snap['available_gib']} GiB",
        f"Commit:           {snap['commit_used_gib']} / {snap['commit_limit_gib']} GiB",
        f"System cache WS:  {snap['system_cache_ws_gib']} GiB",
        f"Standby:          {snap['standby_gib']} GiB",
        f"Nonpaged pool:    {snap['nonpaged_pool_gib']} GiB",
    ]
    top = snap["top_consumers"]
    if top == _UNAVAILABLE:
        lines.append(f"Top consumers:    {_UNAVAILABLE}")
    else:
        lines.append("Top consumers by private commit:")
        for row in top:
            lines.append(f"  {row['pid']:>7}  {row['private_commit_mb']:>9.1f} MB  {row['cmd']}")
    return "\n".join(lines)


def _admit_line(verdict, peak_gib: float, status, limit: int) -> str:
    if verdict.admit:
        return f"ADMIT peak={peak_gib}GiB need_avail={_gib(int(verdict.need_avail))}GiB"
    failed = []
    if not verdict.avail_ok:
        failed.append(
            f"available: need {_gib(int(verdict.need_avail))}GiB > avail {_gib(status.avail_phys)}GiB"
        )
    if not verdict.commit_ok:
        failed.append(
            f"commit: used {_gib(status.commit_used)}GiB + peak {peak_gib}GiB > limit {_gib(limit)}GiB"
        )
    return f"HOLD peak={peak_gib}GiB failed {'; '.join(failed)}"


def main(
    argv: Optional[list] = None,
    *,
    platform: Optional[str] = None,
    status_fn: Optional[Callable] = None,
    nonpaged_fn: Optional[Callable] = None,
    cache_host_fn: Optional[Callable] = None,
    governor=None,
    rss_fn: Optional[Callable] = None,
    alive_fn: Optional[Callable] = None,
    proc_table_fn: Optional[Callable] = None,
    cmdline_fn: Optional[Callable] = None,
) -> int:
    parser = argparse.ArgumentParser(prog=PROG, description="One-screen box memory snapshot.")
    parser.add_argument("--top", type=int, default=10, help="top N consumers (default 10)")
    parser.add_argument("--admit-peak", type=float, metavar="GIB", help="check admission of a peak")
    parser.add_argument("--cushion-pct", type=float, default=25.0, help="available cushion percent")
    parser.add_argument("--commit-limit-gib", type=float, help="override the commit limit")
    parser.add_argument("--admission-file", help="admission.jsonl path (default: settings-home channel)")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    host = _load("box_memory_host")
    plat = platform if platform is not None else sys.platform
    if plat not in ("win32", "darwin"):
        return host.unsupported(PROG, plat, "reads Windows or macOS memory counters")
    if governor is None and proc_table_fn is None:
        missing = host.require_psutil(PROG)
        if missing is not None:
            return missing

    status_fn = status_fn or host.read_memory_status
    if plat == "darwin":
        # No nonpaged pool or file-cache counters on macOS: those fields print `unavailable`.
        nonpaged_fn = nonpaged_fn or (lambda: None)
        cache_host_fn = cache_host_fn or (lambda: SimpleNamespace(read_memory=lambda: None))
    else:
        nonpaged_fn = nonpaged_fn or host.nonpaged_pool_bytes
        cache_host_fn = cache_host_fn or _load_cache_host
    if plat == "win32":
        table_fn = proc_table_fn or host.proc_table
        cmd_fn = cmdline_fn or host.proc_cmdline
        consumers_fn = lambda top: _top_consumers_table(table_fn, cmd_fn, top)
    else:
        gov_fn = (lambda: governor) if governor is not None else host.load_governor
        consumers_fn = lambda top: _top_consumers_gov(gov_fn(), top)

    status = _try(status_fn)
    snap = build_snapshot(status, nonpaged_fn, cache_host_fn, consumers_fn, args.top)
    code = 0
    admit_line = None
    if args.admit_peak is not None:
        if status is None:
            print(f"{PROG}: cannot read memory status for admission", file=sys.stderr)
            return 1
        peak = int(args.admit_peak * host.GIB)
        limit = int(args.commit_limit_gib * host.GIB) if args.commit_limit_gib is not None else status.commit_limit
        reserved = host.reserved_bytes(
            args.admission_file or host.admission_file(),
            **({"rss_fn": rss_fn} if rss_fn else {}),
            **({"alive_fn": alive_fn} if alive_fn else {}),
        )
        status = dataclasses.replace(
            status,
            avail_phys=max(0, status.avail_phys - reserved),
            commit_used=status.commit_used + reserved,
        )
        verdict = host.admit(
            peak, status, cushion_pct=args.cushion_pct, commit_limit=limit
        )
        admit_line = _admit_line(verdict, args.admit_peak, status, limit) + f" reserved={_gib(reserved)}GiB"
        snap["admit"] = {
            "reserved_gib": _gib(reserved),
            "verdict": "ADMIT" if verdict.admit else "HOLD",
            "peak_gib": args.admit_peak,
            "need_avail_gib": _gib(int(verdict.need_avail)),
            "avail_ok": verdict.avail_ok,
            "commit_ok": verdict.commit_ok,
        }
        code = 0 if verdict.admit else 4

    if args.json:
        print(json.dumps(snap))
    else:
        print(_render(snap))
        if admit_line:
            print(admit_line)
    return code


if __name__ == "__main__":
    sys.exit(main())
