#!/usr/bin/env python3
"""Per-phase process time and child-spawn count of the forced-command `roster` handler.

Imports unimatrix-relay.py by path and runs its `roster()` with the sessions scan, liveness checks,
codex checks and output wrapped by counters, then prints one JSON document. Read-only: it never
writes the sessions dir, and roster rows go to a counter, not to stdout.

process_ms is user+system CPU of this process plus its reaped children (os.times). Windows reports
no children times, so `spawns` (every subprocess.Popen) is the spawn measure there.

Phases nest (entry_live, codex_checks and json_load run inside the entries scan), so phase_ms entries
overlap and their sum can exceed process_ms; `other` is clamped at zero and is not a residual.
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BIN = Path(__file__).resolve().parent
_ENTRY_NAME = re.compile(r"(\d+)(?:\.([0-9a-f]{16}))?\.json")


REQUIRED_PHASES = ("listdir", "json_load", "entry_live", "codex_checks", "print")


def _cpu_ms():
    t = os.times()
    return (t.user + t.system + t.children_user + t.children_system) * 1000.0


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Meter:
    """Accumulates per-phase CPU ms and call counts, and counts Popen spawns."""

    def __init__(self) -> None:
        self.phase_ms = {p: 0.0 for p in REQUIRED_PHASES}
        self.phase_calls = {p: 0 for p in REQUIRED_PHASES}
        self.spawns = 0
        self.rows = 0
        self.entries_yielded = 0
        self.candidates = None

    def timed(self, phase, fn):
        def wrapper(*args, **kwargs):
            start = _cpu_ms()
            try:
                return fn(*args, **kwargs)
            finally:
                self.phase_ms[phase] = self.phase_ms.get(phase, 0.0) + _cpu_ms() - start
                self.phase_calls[phase] = self.phase_calls.get(phase, 0) + 1
        return wrapper


def measure(relay_path=None, sessions_dir=None):
    """Run the relay's roster() under the meter; returns the report dict. Rows are counted, never
    written; the stderr ambiguity notes pass through."""
    relay = _load(Path(relay_path) if relay_path else BIN / "unimatrix-relay.py", "unimatrix_relay_timing")
    if sessions_dir is not None:
        relay.SESS = str(sessions_dir)
    sess = os.path.expanduser(relay.SESS)
    meter = Meter()

    real_listdir, real_json_load, real_popen = os.listdir, json.load, subprocess.Popen

    def listdir(path: str = "."):
        names = real_listdir(path)
        if meter.candidates is None and os.path.abspath(os.fspath(path)) == os.path.abspath(sess):
            meter.candidates = sum(1 for n in names if _ENTRY_NAME.fullmatch(n))
        return names

    class _SpawnCounter(real_popen):
        def __init__(self, *args, **kwargs) -> None:
            meter.spawns += 1
            super().__init__(*args, **kwargs)

    def relay_print(*args, file=None, **kwargs) -> None:
        if file is None or file is sys.stdout:
            meter.rows += 1
        else:
            print(*args, file=file, **kwargs)

    live = relay._liveness()
    saved = {
        "listdir": os.listdir, "json_load": json.load, "popen": subprocess.Popen,
        "entry_live": live.entry_live, "entries": relay.entries,
        "mirror_orphaned": relay.mirror_orphaned, "codex_holder_dead": relay.codex_holder_dead,
        "codex_export_refused": relay.codex_export_refused, "engine_fields": relay.engine_fields,
        "relay_sha": relay.relay_sha, "load_roster": relay.load_roster,
        "print": relay.__dict__.get("print"),
    }
    real_entries = relay.entries

    def counted_entries():
        for item in real_entries():
            meter.entries_yielded += 1
            yield item

    def load_roster_wrapped():
        mod = saved["load_roster"]()
        mod.session_identity = meter.timed("session_identity", mod.session_identity)
        return mod

    os.listdir = meter.timed("listdir", listdir)
    json.load = meter.timed("json_load", real_json_load)
    subprocess.Popen = _SpawnCounter
    live.entry_live = meter.timed("entry_live", saved["entry_live"])
    relay.mirror_orphaned = meter.timed("mirror_orphaned", saved["mirror_orphaned"])
    relay.codex_holder_dead = meter.timed("codex_checks", saved["codex_holder_dead"])
    relay.codex_export_refused = meter.timed("codex_checks", saved["codex_export_refused"])
    relay.engine_fields = meter.timed("engine_fields", saved["engine_fields"])
    relay.relay_sha = meter.timed("relay_sha", saved["relay_sha"])
    relay.load_roster = meter.timed("load_roster", load_roster_wrapped)
    relay.entries = counted_entries
    relay.print = meter.timed("print", relay_print)

    start = _cpu_ms()
    try:
        relay.roster()
    finally:
        total = _cpu_ms() - start
        os.listdir, json.load, subprocess.Popen = saved["listdir"], saved["json_load"], saved["popen"]
        live.entry_live = saved["entry_live"]
        relay.entries = saved["entries"]
        relay.mirror_orphaned = saved["mirror_orphaned"]
        relay.codex_holder_dead = saved["codex_holder_dead"]
        relay.codex_export_refused = saved["codex_export_refused"]
        relay.engine_fields = saved["engine_fields"]
        relay.relay_sha = saved["relay_sha"]
        relay.load_roster = saved["load_roster"]
        if saved["print"] is None:
            relay.__dict__.pop("print", None)
        else:
            relay.print = saved["print"]

    candidates = meter.candidates or 0
    phases = {k: round(v, 2) for k, v in sorted(meter.phase_ms.items())}
    phases["other"] = round(max(0.0, total - sum(meter.phase_ms.values())), 2)
    return {
        "process_ms": round(total, 2),
        "spawns": meter.spawns,
        "rows": meter.rows,
        "entries_candidates": candidates,
        "entries_yielded": meter.entries_yielded,
        "entries_skipped": max(0, candidates - meter.entries_yielded),
        "phase_ms": phases,
        "phase_calls": dict(sorted(meter.phase_calls.items())),
        "sessions_dir": sess,
        "platform": sys.platform,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sessions-dir", help="sessions dir to scan (default: the relay's own)")
    ap.add_argument("--relay", help="path of unimatrix-relay.py (default: the sibling copy)")
    args = ap.parse_args(argv)
    print(json.dumps(measure(args.relay, args.sessions_dir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
