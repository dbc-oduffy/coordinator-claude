#!/usr/bin/env python3
"""Release gate: one probe from every enrolled box must reach a Machine-a session.

For each far box in the signed membership roster, ssh to it over its `unimatrix-control-<box>` alias with
its control key (`~/.ssh/unimatrix_control_<box>`; the relay key is a forced command and cannot run a
shell) and run its `unimatrix-send` to a live local session with a unique probe line, then poll this
box's relay `receipts <session-id> <since>` for a new delivery digest within a per-box poll budget. One
line per box: `arrived`, `queued-then-delivered` or `missing` (with the hop that lost it). The boxes
that must pass are the machine-local key `unimatrix.inbound_gate_boxes`; others are probed and printed
`[not required]` but never fail. Exit 0 only when every required box arrived or was queued-then-delivered;
exit 1 names every missing required box; exit 2 when the roster is unusable or no local target session
exists. With the key unset every enrolled far box is required (a stderr note names the key to set).

    unimatrix-inbound-gate.py [--to NAME --session-id SID] [--timeout SECONDS] [--interval SECONDS] [--send-command CMD] [--key PATH]
    (required boxes: machine-local key unimatrix.inbound_gate_boxes)

The receipts oracle matches a digest absent from the baseline taken before the probe (the relay's
digest covers the wire line, which the sender wraps, so the probe text cannot be hashed ahead);
rows are never filtered by a sender field (the deployed relay records none); box names compare case-folded.
Boxes probe one at a time, so a digest new since the baseline is that box's probe.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_TIMEOUT_S = 20.0
DEFAULT_INTERVAL_S = 1.0
SSH_TIMEOUT_S = 60
# Interpreter candidates tried on the far box in order (homebrew first: a stock /usr/bin/python3 may be 3.9).
_PY_CANDIDATES = ("/opt/homebrew/bin/python3", "python3", '"$HOME/.pyenv/shims/python3"', "/usr/local/bin/python3",
                  "/usr/bin/python3")
_FAR_SEND_PATH = "${COORDINATOR_SETTINGS_HOME:-$HOME/.coordinator-claude-settings}/bin/unimatrix-send"
REQUIRED_KEY = "unimatrix.inbound_gate_boxes"

ARRIVED = "arrived"
QUEUED = "queued-then-delivered"
MISSING = "missing"

# ssh's own connect-timeout stderr; the runner's TimeoutExpired (a hung command) never matches, so a probe is not resent.
_CONNECT_TIMEOUT = re.compile(r"(?:Connection|Operation) timed out|Connection timeout", re.I)
RETRY_NOTE = "ssh retried once after connect timeout"

READ_KEY = object()  # main(required=READ_KEY) reads REQUIRED_KEY; an explicit set or None (every box) skips the read

# Registry fields that mark a mirror of a far session; the router and relay exclude the same set.
_MIRROR_MARKERS = ("unimatrixRemote", "macSocketPath", "unimatrixMirror", "farPid")


def _sibling(rel: str, key: str) -> Any:
    mod = sys.modules.get(key)
    if mod is None:
        spec = importlib.util.spec_from_file_location(key, HERE / rel)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {rel}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[key] = mod
        spec.loader.exec_module(mod)
    return mod


def _no_window() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def _text(stream: Any) -> str:
    return stream.decode("utf-8", "replace") if isinstance(stream, bytes) else (stream or "")


def new_probe(box: str) -> str:
    """A probe line unique to this run and box; plain words so it needs no shell quoting."""
    return f"inbound-gate-probe from {box} {uuid.uuid4().hex[:12]}"


def local_target(entries: Any, name: str | None = None, session_id: str | None = None) -> tuple[str, str] | None:
    """(name, session id) of the local session the probes go to, or None.

    An explicit name+id wins; else the entry named `name`, else the first live non-mirror entry."""
    if name and session_id:
        return name, session_id
    rows = [e for e in entries if isinstance(e, dict) and isinstance(e.get("name"), str)
            and isinstance(e.get("sessionId"), str) and not any(e.get(k) for k in _MIRROR_MARKERS)]
    if name:
        rows = [e for e in rows if e["name"] == name]
    else:
        # A far box resolves `<name>.<box>` and refuses a name two sessions share, so prefer a unique one.
        counts: dict[str, int] = {}
        for e in entries:
            if isinstance(e, dict) and isinstance(e.get("name"), str):
                counts[e["name"]] = counts.get(e["name"], 0) + 1
        rows = [e for e in rows if counts[e["name"]] == 1] or rows
    return (rows[0]["name"], rows[0]["sessionId"]) if rows else None


def _digests(rows: Any) -> set:
    """Digests of the receipt rows, whatever other keys they carry: arrival is a digest absent from the
    pre-probe baseline."""
    return {r["digest"] for r in rows if isinstance(r, dict) and r.get("digest")}


def _fold(name: str) -> str:
    return str(name).strip().lower()


def control_route(box: str, ssh_dir: Path | None = None) -> tuple[str, str] | str:
    """(ssh alias, control key path) of far `box`, or the reason there is none.

    The key is `~/.ssh/unimatrix_control_<name>` and the alias `unimatrix-control-<name>` (unimatrix-install.py
    control_key / CONTROL_ALIAS_PREFIX naming); `<name>` is the box id as the roster spells it, else lowercased,
    else with every non-alphanumeric dropped (roster `Mac-mini` is installed as `macmini`). Never mints a key."""
    ui = _sibling("unimatrix-install.py", "unimatrix_inbound_gate_install")
    names: list[str] = []
    for cand in (ui._ALIAS_UNSAFE.sub("-", box), ui._ALIAS_UNSAFE.sub("-", box).lower(),
                 re.sub(r"[^a-z0-9]", "", box.lower())):
        if cand and cand not in names:
            names.append(cand)
    ssh_dir = ssh_dir or Path.home() / ".ssh"
    for name in names:
        key = ssh_dir / f"unimatrix_control_{name}"
        if key.is_file():
            return f"{ui.CONTROL_ALIAS_PREFIX}{name}", str(key)
    return f"no control key {ssh_dir / ('unimatrix_control_' + names[0])} (nor {', '.join(names[1:]) or 'other spellings'}); " \
           f"run unimatrix-install.py --control-key {box}"


def required_boxes(read: Any = None) -> set[str] | None:
    """Folded box names of the `unimatrix.inbound_gate_boxes` machine-local key (comma or space separated), or
    None when the key is unset."""
    value = (read or _sibling("lib/unimatrix_box_mux.py", "unimatrix_inbound_gate_mux").machine_local_value)(REQUIRED_KEY)
    names = {_fold(n) for n in re.split(r"[,\s]+", value or "") if n}
    return names or None


def far_send_command() -> str:
    """Shell prefix that runs the far box's installed `unimatrix-send` by path under an interpreter the far box
    resolves itself: the first of `_PY_CANDIDATES` that is python >= 3.11; none is a typed `no python3>=3.11` exit
    127 (reported missing at hop send), never a silent run under an older python.

    The non-interactive ssh PATH carries neither the settings-home `bin/` nor a usable python everywhere, so
    neither is assumed; the snippet is plain sh that zsh and bash both accept."""
    cands = " ".join(_PY_CANDIDATES)
    return ('s() ( F="' + _FAR_SEND_PATH + '"; if [ "$(head -c 2 "$F")" = "#!" ]; then '
            'for c in ' + cands + '; do if "$c" -c "import sys; sys.exit(sys.version_info < (3, 11))" '
            '>/dev/null 2>&1; then PY="$c"; break; fi; done; [ -n "$PY" ] || { echo "no python3>=3.11 on this box" >&2; exit 127; }; '
            'exec "$PY" "$F" "$@"; fi; exec "$F" "$@"); s')


def probe_box(member: dict, target: tuple[str, str], *, run_ssh: Any, fetch_receipts: Any, key: str,
              send_command: str | None = None, timeout: float = DEFAULT_TIMEOUT_S,
              interval: float = DEFAULT_INTERVAL_S, sleep: Any = time.sleep, now: Any = time.time,
              local_box: str | None = None) -> tuple[str, str, str, str]:
    """Probe one far box: (box, status, hop, detail).

    `run_ssh(member, key, command)` -> CompletedProcess, dialling `member["alias"]`; `fetch_receipts(session_id,
    since)` -> rows. The poll budget is `timeout / interval` receipts reads, never a clock deadline. With
    `local_box` the target is addressed `<name>.<local_box>`: a far box that mirrors two same-named sessions
    treats the bare name as ambiguous. `send_command` None runs `far_send_command()`."""
    box = member["box"]
    name, sid = target
    since = now() - 1
    baseline = _digests(fetch_receipts(sid, since))
    addressed = f"{name}.{_fold(local_box)}" if local_box else name
    text = shlex.quote(new_probe(box))
    base = send_command or far_send_command()
    command = f"{base} --to {shlex.quote(addressed)} {text}"
    if addressed != name:
        # A far box may know this box under another label (an address, `<box>-lan`): fall back to the bare name.
        command += f" || {'s' if send_command is None else base} --to {shlex.quote(name)} {text}"
    res = run_ssh(member, key, command)
    retried = False
    if res.returncode == 255 and _CONNECT_TIMEOUT.search(_text(res.stderr)):
        retried = True
        res = run_ssh(member, key, command)
    if res.returncode == 255:
        detail = _text(res.stderr).strip()[:200] or "ssh failed"
        return box, MISSING, "ssh", detail + (f"; {RETRY_NOTE}" if retried else "")
    send_failed = res.returncode != 0
    polls = max(1, int(timeout // interval)) if interval > 0 else 1
    for n in range(polls):
        if _digests(fetch_receipts(sid, since)) - baseline:
            return box, (ARRIVED if n == 0 else QUEUED), "relay-in", RETRY_NOTE if retried else ""
        if n + 1 < polls:
            sleep(interval)
    tail = f"; {RETRY_NOTE}" if retried else ""
    if send_failed:
        return box, MISSING, "send", ((_text(res.stderr) or _text(res.stdout)).strip()[:200] or f"rc {res.returncode}") + tail
    return box, MISSING, "relay-in", f"no receipt for {sid} within {timeout:g}s{tail}"


def run_gate(members: Any, target: tuple[str, str], *, run_ssh: Any, fetch_receipts: Any, route_for: Any, out: Any,
             required: set[str] | None = None, **kw: Any) -> list[str]:
    """Probe each member in order, print one line per box, return the missing REQUIRED box names.

    `route_for(member)` -> (alias, key) or a reason string (missing at hop route). A box outside `required`
    (None = every box) is probed and printed but never counted."""
    missing = []
    for m in members:
        box = m["box"]
        route = route_for(m)
        if isinstance(route, str):
            status, hop, detail = MISSING, "route", route
        else:
            _, status, hop, detail = probe_box({**m, "alias": route[0]}, target, run_ssh=run_ssh,
                                               fetch_receipts=fetch_receipts, key=route[1], **kw)
        needed = required is None or _fold(box) in required
        line = f"{box}: {status}" + (f" (hop {hop}{': ' + detail if detail else ''})" if status == MISSING
                                     else f" ({detail})" if detail else "")
        print(line + ("" if needed else " [not required]") if status == MISSING else line, file=out)
        if status == MISSING and needed:
            missing.append(box)
    return missing


def _ssh_runner(timeout: int = SSH_TIMEOUT_S) -> Any:
    def run(member: dict, key: str, command: str) -> subprocess.CompletedProcess:
        argv = ["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none", "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=10", member["alias"], command]
        try:
            return subprocess.run(argv, capture_output=True, timeout=timeout, creationflags=_no_window())
        except Exception as ex:
            return subprocess.CompletedProcess(argv, 255, b"", f"{type(ex).__name__}: {ex}".encode())
    return run


def _roster_ctx() -> tuple[Any, Any]:
    roster = _sibling("unimatrix-roster.py", "unimatrix_inbound_gate_roster")
    mem = _sibling("unimatrix-membership.py", "unimatrix_inbound_gate_membership")
    return roster, mem


def main(argv=None, out=None, run_ssh=None, fetch_receipts=None, route_for=None, members=None, entries=None,
         local_box=None, sleep=time.sleep, required=READ_KEY) -> int:
    p = argparse.ArgumentParser(prog="unimatrix-inbound-gate.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--to", help="local session name the probes address (default: first live local session)")
    p.add_argument("--session-id", help="that session's id (default: its registry sessionId)")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="per-box receipts poll budget, seconds")
    p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S, help="seconds between receipts polls")
    p.add_argument("--send-command", default=None,
                   help="command that runs unimatrix-send on the far box (default: the installed script by path "
                        "under a python >= 3.11 the far box resolves)")
    p.add_argument("--key", default=None, help="ssh identity replacing the control key of every box that has a control alias (default: the box's control key)")
    a = p.parse_args(argv)
    out = out or sys.stdout
    try:
        roster, mem = _roster_ctx()
        roster.export_settings_home()  # an ssh login session carries no env: pin the delivery default before any strict read
        if members is None:
            members = mem.verified_members(roster.settings_home())
        if entries is None:
            entries = roster.session_entries()
        if local_box is None:
            local_box = _sibling("unimatrix-peer-contract.py", "unimatrix_inbound_gate_contract").local_box()
    except Exception as ex:
        print(f"inbound gate: membership unusable: {type(ex).__name__}: {ex}", file=sys.stderr)
        return 2
    far = [m for m in members if m.get("box") != local_box]
    if not far:
        print("inbound gate: no far box is enrolled; nothing to probe", file=out)
        return 0
    target = local_target(entries, a.to, a.session_id)
    if target is None:
        print("inbound gate: no live local session to receive probes (pass --to NAME --session-id SID)",
              file=sys.stderr)
        return 2
    if fetch_receipts is None:
        relay = _sibling("unimatrix-relay.py", "unimatrix_inbound_gate_relay")
        fetch_receipts = lambda sid, since: relay.receipts(sid, since)["rows"]
    if required is READ_KEY:
        required = required_boxes()
        if required is None:
            print(f"inbound gate: machine-local key {REQUIRED_KEY} is unset; requiring every enrolled far box "
                  f"(set the key to the comma-separated boxes that must pass)", file=sys.stderr)
    if route_for is None:
        def route_for(m: dict) -> tuple[str, str] | str:
            found = control_route(m["box"])
            if a.key and not isinstance(found, str):
                return found[0], a.key
            return found
    missing = [n for n in sorted(required or ()) if n != _fold(local_box) and not any(_fold(m["box"]) == n for m in far)]
    for n in missing:
        print(f"{n}: missing (hop roster: required box is not enrolled)", file=out)
    missing += run_gate(far, target, run_ssh=run_ssh or _ssh_runner(), fetch_receipts=fetch_receipts,
                        route_for=route_for, out=out, required=required, send_command=a.send_command,
                        timeout=a.timeout, interval=a.interval, sleep=sleep, local_box=local_box)
    if missing:
        print(f"inbound gate FAILED: no probe arrived from {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
