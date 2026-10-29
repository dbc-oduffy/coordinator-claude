#!/usr/bin/env python3
"""warm-read-load-probe.py -- what does a fixed op mix cost the warm server's pool workers in read bytes and CPU.

Resolves the live warm server (process scan for `coordinator_core/warm/server.py`, confirmed against
that clone's breadcrumb), snapshots every pool worker (psutil io_counters + cpu_times, memory and I/O
priority), drives a fixed named op mix through the engine clone's own default warm client, snapshots
again, and reports per-worker deltas. Worker processes born during the run are included in full.

`--attribute` additionally runs the same mix in-process (no warm server involved) under an audit hook
on `open`/`mmap` and ranks the files opened by estimated bytes (`st_size` per open, an upper bound),
per op, next to the process's own measured read_bytes. Read the two together: Windows `read_bytes`
counts every ReadFile including pipes, so bytes absent from the file ranking are pipe/child-output reads.

Usage:
    python coordinator/bin/warm-read-load-probe.py --json [--rounds N] [--attribute] [--engine-root PATH]

Exit 0 only when a server was found, every dispatch was served warm, and at least one op succeeded.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

SERVER_SCRIPT_TAIL = ("coordinator_core", "warm", "server.py")
#: Empty on purpose: a non-empty id makes the guards append a touch-record into the real
#: session hub (.git/coordinator-sessions/<id>/). `_run_driver` also strips the env ids.
PROBE_SESSION_ID = ""
DEFAULT_ROUNDS = 12
ATTRIBUTE_WARMUP_ROUNDS = 2
TOP_FILES = 25
MEMORY_PRIORITY_VERY_LOW = 1
IO_PRIORITY_VERY_LOW = 0

# The fixed, named op mix: the hook-path ops that dominate pool dispatch (op-latency telemetry of a
# live box: preuse_bash_dispatch, guard_editor_python_direct, preuse_search_dispatch) plus one
# compute-only op. Benign payloads only: nothing here writes repo state.
_BASH_COMMANDS = (
    "git status --short",
    "git log --oneline -5",
    "python -m pytest coordinator_core/warm/tests/test_polite_io.py -q",
    "rg -n warm_cache coordinator_core",
    "ls -la docs",
    "cat README.md",
)


def op_mix(cwd: str) -> list[dict]:
    """The ordered op list for one round: `label`, `method`, `params`, `origin`."""
    mix: list[dict] = []
    for i, cmd in enumerate(_BASH_COMMANDS):
        mix.append(
            {
                "label": f"preuse_bash_dispatch[{i}]",
                "method": "hooks.preuse_bash_dispatch",
                "params": {
                    "payload": {
                        "tool_name": "Bash",
                        "tool_input": {"command": cmd},
                        "session_id": PROBE_SESSION_ID,
                        "cwd": cwd,
                        "hook_event_name": "PreToolUse",
                    }
                },
                "origin": cwd,
            }
        )
    mix.append(
        {
            "label": "preuse_search_dispatch",
            "method": "hooks.preuse_search_dispatch",
            "params": {
                "payload": {
                    "tool_name": "Grep",
                    "tool_input": {"pattern": "warm_cache", "path": cwd},
                    "session_id": PROBE_SESSION_ID,
                    "cwd": cwd,
                    "hook_event_name": "PreToolUse",
                }
            },
            "origin": cwd,
        }
    )
    mix.append(
        {
            "label": "guard_editor_python_direct",
            "method": "hooks.guard_editor_python_direct",
            "params": {
                "payload": {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": str(Path(cwd) / "README.md")},
                    "session_id": PROBE_SESSION_ID,
                    "cwd": cwd,
                    "hook_event_name": "PreToolUse",
                }
            },
            "origin": cwd,
        }
    )
    mix.append(
        {
            "label": "memo.list",
            "method": "memo.list",
            "params": {"dry_run": True},
            "origin": cwd,
        }
    )
    return mix


# --------------------------------------------------------------------------- server discovery


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def find_server(engine_root: Path | None):
    """Return `(psutil.Process, engine_root)` of the live warm server, or `(None, None)`.

    A candidate is a process whose command line names `.../coordinator_core/warm/server.py`; its
    engine root is that script's grandparent-of-package. When several match, the one whose clone's
    breadcrumb pid equals the process pid wins.
    """
    import psutil

    from coordinator_core.warm import breadcrumb

    wanted = _norm(str(engine_root)) if engine_root is not None else None
    tail = os.path.join(*SERVER_SCRIPT_TAIL)
    found = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            for arg in proc.info["cmdline"] or ():
                if _norm(arg).endswith(os.path.normcase(tail)):
                    root = Path(arg).resolve().parents[2]
                    if wanted is None or _norm(str(root)) == wanted:
                        found.append((proc, root))
                    break
        except (psutil.Error, OSError, IndexError):
            continue
    for proc, root in found:
        crumb = breadcrumb.read_breadcrumb(root)
        if crumb and crumb.get("pid") == proc.pid:
            return proc, root
    return (found[0] if found else (None, None))


def pool_workers(server):
    """The server's `multiprocessing` spawn children (the dispatch pool workers)."""
    import psutil

    out = []
    try:
        kids = server.children()
    except psutil.Error:
        return out
    for kid in kids:
        try:
            cmd = " ".join(kid.cmdline())
        except psutil.Error:
            continue
        if "multiprocessing.spawn" in cmd or "--multiprocessing-fork" in cmd:
            out.append(kid)
    return out


# --------------------------------------------------------------------------- priority and counters


def memory_priority(pid: int):
    """Process memory priority 1..5 (1 = VERY_LOW) on Windows; None elsewhere or on failure."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.GetProcessInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.GetProcessInformation.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        value = wintypes.ULONG(0)
        # PROCESS_INFORMATION_CLASS ProcessMemoryPriority = 0
        ok = k32.GetProcessInformation(handle, 0, ctypes.byref(value), ctypes.sizeof(value))
        return int(value.value) if ok else None
    finally:
        k32.CloseHandle(handle)


def io_priority(proc):
    """Process I/O priority (Windows: 0 VeryLow, 1 Low, 2 Normal); None when unreadable."""
    import psutil

    try:
        value = proc.ionice()
    except (psutil.Error, AttributeError, OSError):
        return None
    return int(getattr(value, "ioclass", value)) if value is not None else None


def snapshot(proc) -> dict | None:
    import psutil

    try:
        io = proc.io_counters()
        cpu = proc.cpu_times()
        return {
            "pid": proc.pid,
            "read_bytes": io.read_bytes,
            "read_count": io.read_count,
            "cpu_ms": round((cpu.user + cpu.system) * 1000.0, 1),
            "memory_priority": memory_priority(proc.pid),
            "io_priority": io_priority(proc),
            "created": proc.create_time(),
        }
    except psutil.Error:
        return None


def snapshot_all(procs) -> dict[int, dict]:
    snaps = {}
    for proc in procs:
        snap = snapshot(proc)
        if snap is not None:
            snaps[proc.pid] = snap
    return snaps


# --------------------------------------------------------------------------- drivers (child processes)

_WARM_DRIVER = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
from coordinator_core.warm import client
spec = json.load(sys.stdin)
out = []
for i, op in enumerate(spec["ops"]):
    msg = {"jsonrpc": "2.0", "id": i + 1, "method": op["method"], "params": op["params"],
           "_origin_worktree": op["origin"]}
    t0 = time.perf_counter()
    resp = client.try_warm_dispatch(msg)
    wall = (time.perf_counter() - t0) * 1000.0
    out.append({"label": op["label"], "wall_ms": round(wall, 1), "served": resp is not None,
                "ok": bool(resp) and "result" in resp})
json.dump(out, sys.stdout)
"""

_ATTRIBUTE_DRIVER = r"""
import collections, json, os, sys
sys.path.insert(0, sys.argv[1])
import psutil
from coordinator_core import ipc

spec = json.load(sys.stdin)
warm, top = spec["warmup_rounds"], spec["top"]
state = {"label": None, "on": False}
files = collections.defaultdict(lambda: [0, 0, collections.Counter()])
seen_size = {}
sites = collections.defaultdict(lambda: [0, 0, set(), collections.Counter()])
engine = os.path.normcase(os.path.abspath(sys.argv[1]))

def callsite():
    # Innermost engine frame that is not the driver and not import machinery: the code that asked for the file.
    fr = sys._getframe(2)
    while fr is not None:
        name = fr.f_code.co_filename
        if not name.startswith("<"):
            norm = os.path.normcase(os.path.abspath(name))
            if norm.startswith(engine) and os.path.basename(norm) != "ipc.py":
                return os.path.relpath(norm, engine).replace(os.sep, "/") + ":" + fr.f_code.co_name + ":" + str(fr.f_lineno)
        fr = fr.f_back
    return "<outside-engine>"

def hook(event, args):
    if not state["on"] or event not in ("open", "mmap.__new__"):
        return
    if event == "mmap.__new__":
        path, est = "<mmap>", 0
    else:
        path, mode, flags = args
        if not isinstance(path, str):
            return
        wants_write = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR))
        if wants_write:
            return
        est = seen_size.get(path)
        if est is None:
            try:
                est = seen_size[path] = os.stat(path).st_size
            except OSError:
                est = seen_size[path] = 0
    rec = files[path]
    rec[0] += 1
    rec[1] += est
    rec[2][state["label"]] += est
    site = callsite()
    srec = sites[site]
    srec[0] += 1
    srec[1] += est
    srec[2].add(path)
    srec[3][state["label"]] += est

def run(rounds, measure):
    for _ in range(rounds):
        for op in spec["ops"]:
            state["label"] = op["label"]
            try:
                ipc.dispatch_from_hook(op["method"], op["params"], origin_worktree=op["origin"])
            except Exception:
                pass

sys.addaudithook(hook)
run(warm, False)
me = psutil.Process()
io0, cpu0 = me.io_counters(), me.cpu_times()
state["on"] = True
run(spec["rounds"], True)
state["on"] = False
io1, cpu1 = me.io_counters(), me.cpu_times()
ranked = sorted(files.items(), key=lambda kv: kv[1][1], reverse=True)
json.dump({
    "process_read_bytes": io1.read_bytes - io0.read_bytes,
    "process_read_count": io1.read_count - io0.read_count,
    "process_cpu_ms": round(((cpu1.user + cpu1.system) - (cpu0.user + cpu0.system)) * 1000.0, 1),
    "est_file_bytes_total": sum(v[1] for v in files.values()),
    "opens_total": sum(v[0] for v in files.values()),
    "top_files": [{"path": p, "opens": v[0], "est_bytes": v[1], "by_op": dict(v[2])} for p, v in ranked[:top]],
    "top_callsites": [
        {"callsite": s, "opens": v[0], "est_bytes": v[1], "distinct_files": len(v[2]), "by_op": dict(v[3])}
        for s, v in sorted(sites.items(), key=lambda kv: kv[1][1], reverse=True)[:top]
    ],
}, sys.stdout)
"""


def _run_driver(code: str, engine_root: Path, cwd: Path, spec: dict, timeout: float) -> dict | list:
    env = dict(os.environ)
    for key in ("PYTEST_CURRENT_TEST", "COORDINATOR_SESSION_ID", "CLAUDE_SESSION_ID"):
        env.pop(key, None)
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code, str(engine_root)],
        input=json.dumps(spec),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    stdout = proc.stdout
    start = stdout.find("[") if code is _WARM_DRIVER else stdout.find("{")
    if proc.returncode != 0 or start < 0:
        raise RuntimeError(f"driver failed rc={proc.returncode}: {proc.stderr[-600:]}")
    return json.loads(stdout[start:])


# --------------------------------------------------------------------------- report


def build_report(args) -> tuple[dict, int]:
    import psutil

    cwd = Path(args.repo).resolve()
    engine_root_arg = Path(args.engine_root).resolve() if args.engine_root else None
    server, engine_root = find_server(engine_root_arg)
    if server is None:
        return {"error": "no live warm server found"}, 2

    from coordinator_core.warm import breadcrumb

    crumb = breadcrumb.read_breadcrumb(engine_root) or {}
    mix = op_mix(str(cwd))
    ops = [op for _ in range(args.rounds) for op in mix]

    before_workers = pool_workers(server)
    before = snapshot_all(before_workers)
    server_before = snapshot(server)

    t0 = time.perf_counter()
    results = _run_driver(_WARM_DRIVER, engine_root, cwd, {"ops": ops}, timeout=600)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    after_workers = pool_workers(server)
    after = snapshot_all(after_workers)
    server_after = snapshot(server)

    worker_rows = []
    for pid, snap in sorted(after.items()):
        base = before.get(pid)
        row = {
            "pid": pid,
            "born_during_run": base is None,
            "read_bytes_delta": snap["read_bytes"] - (base["read_bytes"] if base else 0),
            "read_count_delta": snap["read_count"] - (base["read_count"] if base else 0),
            "cpu_ms_delta": round(snap["cpu_ms"] - (base["cpu_ms"] if base else 0.0), 1),
            "read_bytes_lifetime": snap["read_bytes"],
            "cpu_ms_lifetime": snap["cpu_ms"],
            "memory_priority": snap["memory_priority"],
            "io_priority": snap["io_priority"],
        }
        worker_rows.append(row)

    per_op: dict[str, dict] = {}
    for r in results:
        agg = per_op.setdefault(r["label"], {"n": 0, "served": 0, "ok": 0, "wall_ms_sum": 0.0})
        agg["n"] += 1
        agg["served"] += int(r["served"])
        agg["ok"] += int(r["ok"])
        agg["wall_ms_sum"] += r["wall_ms"]
    for agg in per_op.values():
        agg["wall_ms_mean"] = round(agg.pop("wall_ms_sum") / agg["n"], 1)

    served = sum(r["served"] for r in results)
    ok = sum(r["ok"] for r in results)
    report = {
        "schema": 1,
        "engine_root": str(engine_root),
        "engine_sha": crumb.get("engine_sha"),
        "server_pid": server.pid,
        "rounds": args.rounds,
        "dispatched": len(results),
        "served_warm": served,
        "ok": ok,
        "driver_elapsed_ms": round(elapsed_ms, 1),
        "worker_count": len(worker_rows),
        "totals": {
            "worker_read_bytes_delta": sum(w["read_bytes_delta"] for w in worker_rows),
            "worker_read_count_delta": sum(w["read_count_delta"] for w in worker_rows),
            "worker_cpu_ms_delta": round(sum(w["cpu_ms_delta"] for w in worker_rows), 1),
            "workers_lifetime_read_bytes": sum(w["read_bytes_lifetime"] for w in worker_rows),
            "workers_lifetime_cpu_ms": round(sum(w["cpu_ms_lifetime"] for w in worker_rows), 1),
        },
        "server_process_delta": (
            {
                "read_bytes": server_after["read_bytes"] - server_before["read_bytes"],
                "cpu_ms": round(server_after["cpu_ms"] - server_before["cpu_ms"], 1),
            }
            if server_before and server_after
            else None
        ),
        "priority": {
            "all_memory_very_low": bool(worker_rows)
            and all(w["memory_priority"] == MEMORY_PRIORITY_VERY_LOW for w in worker_rows),
            "all_io_very_low": bool(worker_rows)
            and all(w["io_priority"] == IO_PRIORITY_VERY_LOW for w in worker_rows),
            "memory_priorities": sorted({w["memory_priority"] for w in worker_rows if w["memory_priority"] is not None}),
            "io_priorities": sorted({w["io_priority"] for w in worker_rows if w["io_priority"] is not None}),
        },
        "workers": worker_rows,
        "per_op": per_op,
    }
    if args.attribute:
        report["attribution"] = _run_driver(
            _ATTRIBUTE_DRIVER,
            engine_root,
            cwd,
            {"ops": mix, "rounds": args.rounds, "warmup_rounds": ATTRIBUTE_WARMUP_ROUNDS, "top": TOP_FILES},
            timeout=900,
        )
    code = 0 if served == len(results) and ok > 0 else 1
    return report, code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="emit the report as JSON (default: human summary)")
    ap.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    ap.add_argument("--attribute", action="store_true", help="also run the in-process per-file attribution pass")
    ap.add_argument("--engine-root", help="engine clone whose warm server to attach to (default: discovered)")
    ap.add_argument("--repo", default=str(_REPO), help="worktree the ops are issued against")
    args = ap.parse_args(argv)
    report, code = build_report(args)
    if args.json or "error" in report:
        print(json.dumps(report, indent=2))
    else:
        t = report["totals"]
        print(
            f"server {report['server_pid']} workers {report['worker_count']} "
            f"served {report['served_warm']}/{report['dispatched']} "
            f"read {t['worker_read_bytes_delta'] / 1048576:.1f} MiB cpu {t['worker_cpu_ms_delta']} ms "
            f"mem_prio {report['priority']['memory_priorities']} io_prio {report['priority']['io_priorities']}"
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
