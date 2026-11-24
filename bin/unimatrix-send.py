#!/usr/bin/env python3
"""Send a message to another agent through the unimatrix peer router.

For Codex and agy peers: an agent's message in is answered with this command out, addressed to
the sender, never with plain text to the human at the keyboard.

    unimatrix-send.py --to <peer-name> 'Reviewed the plan: two issues, ...'
    unimatrix-send.py --list

The sender is identified from the shell this runs in: CODEX_THREAD_ID (Codex),
ANTIGRAVITY_CONVERSATION_ID (agy), or CLAUDE_SESSION_ID / CLAUDE_CODE_SESSION_ID names the session,
or a Grok session whose registry pid is an
ancestor of this shell; the router maps it to that peer's roster name and stamps the frame with
that name and its box, so nothing is signed by hand. Reads no token and puts no credential in argv.
"""
import argparse
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from os import _Environ
    from types import ModuleType

HERE = Path(__file__).resolve().parent


def _router() -> "ModuleType":
    spec = importlib.util.spec_from_file_location("unimatrix_peer_router", HERE / "unimatrix-peer-router.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _sibling(filename, modname) -> "ModuleType":
    spec = importlib.util.spec_from_file_location(modname, HERE / filename)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _windows():
    return os.name == "nt"


def _session_entries():
    """Live session entries (dicts) from the sessions dir; no router, so it works on every OS."""
    roster = _sibling("unimatrix-roster.py", "unimatrix_roster_send")
    sess, out = roster.sessions_dir(), []
    try:
        files = sorted(os.listdir(sess))
    except OSError:
        return out
    for f in files:
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(sess, f), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if (isinstance(d, dict) and isinstance(d.get("name"), str) and isinstance(d.get("pid"), int)
                and roster.pid_alive(d["pid"])):
            out.append(d)
    return out


# Longer than the bridge's one far leg (`unimatrix-bridge.py :: _ssh_relay` runs with timeout=30): the
# bridge writes its deliveries row only after that leg, so a shorter wait reports a cold leg as undelivered.
RELAY_SETTLE_SECONDS = 35
# A mirror row may lack its host (`unimatrixRemote`) yet still carry the far-socket field or a box label.
_MIRROR_FIELDS = ("unimatrixRemote", "macSocketPath", "unimatrixBox")


def _core_module(subname):
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    if "_unimatrix" not in sys.modules and os.path.isdir(os.path.join(bin_dir, "_unimatrix")):
        if bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
    import importlib
    return importlib.import_module(f"_unimatrix.{subname}")


def _mirror_name(name):
    """The live mirror entry's own name when `name` is that name or its far name, else ''.

    The bridge keys its deliveries.jsonl row on the mirror's own name, never the bare far name."""
    contract = _core_module("protocol")
    return next((e["name"] for e in _session_entries()
                 if any(e.get(f) for f in _MIRROR_FIELDS) and name in contract.mirror_addresses(e)), "")


def _is_mirror(name) -> bool:
    """True when `name` is a live mirror here: its router receipt only means the bridge took the frame."""
    return bool(_mirror_name(name))


def relay_outcome(name, since, wait=RELAY_SETTLE_SECONDS, sleep=time.sleep, now=time.time) -> "dict | None":
    """The bridge's recorded far-relay outcome for `name` after `since`, polled up to `wait` seconds; None if none.

    The bridge answers the sender before its ssh leg, so a `written` receipt cannot say the far
    relay delivered; the bridge's deliveries.jsonl row can. Failed row wins over an ok one."""
    roster = _sibling("unimatrix-roster.py", "unimatrix_roster_send")
    path = roster.delivery_settings_home() / "unimatrix" / "deliveries.jsonl"  # ssh env carries no settings-home var
    deadline = now() + wait
    while True:
        try:
            rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except (OSError, ValueError):
            rows = []
        # A relay-pushed mirror has no bridge: its socket forwards onto the far relay's push channel and
        # records `mirror-out` under its bare registered name, never a bridge `target` row.
        pushed = {name, name.partition(".")[0]}
        mine = [r for r in rows if isinstance(r, dict) and (r.get("at") or 0) >= since and (
                (isinstance(r.get("target"), str) and r["target"].startswith(f"{name} (pid "))
                or (r.get("side") == "mirror-out" and r.get("reached") in pushed))]
        mine = [{"transport": "push", **r} if r.get("side") == "mirror-out" else r for r in mine]
        if mine:
            return next((r for r in mine if not r.get("ok")), mine[-1])
        if now() >= deadline:
            return None
        sleep(0.25)


def enqueue_state(outcome) -> str:
    """`enqueued`, `not enqueued` or `unknown` for whether the receiver took the message, from the bridge's row.

    No row, or a failed row flagged unconfirmed (the ssh leg broke after the write may have happened), is
    `unknown`; any other failed row is a refusal or a pre-write failure, so `not enqueued`."""
    if outcome is None:
        return "unknown"
    if outcome.get("ok"):
        return "enqueued"
    if outcome.get("unconfirmed") or "unconfirmed" in str(outcome.get("error", "")):
        return "unknown"
    return "not enqueued"


def _route_note(outcome) -> str:
    """` [box <box>, transport <leg>]` from the bridge's recorded row; `[box unknown]` when an older bridge's row lacks them."""
    box = outcome.get("box")
    transport = outcome.get("transport")
    if not isinstance(box, str) or not box or not isinstance(transport, str) or not transport:
        return " [box unknown]"
    return f" [box {box}, transport {transport}]"


def _reached_note(resp):
    """` (reached <session> on <box>)` when the router named the session it delivered to, else ''."""
    reached = resp.get("reached")
    if not isinstance(reached, str) or not reached:
        return ""
    box = resp.get("reached_box")
    return f" (reached {reached} on {box})" if isinstance(box, str) and box else f" (reached {reached})"


def _age(seconds) -> str:
    """`45s`, `3m05s` or `1h02m` for a non-negative age in seconds."""
    s = int(max(seconds, 0))
    return f"{s}s" if s < 60 else f"{s // 60}m{s % 60:02d}s" if s < 3600 else f"{s // 3600}h{s % 3600 // 60:02d}m"


def _pending_cell(pending) -> str:
    """`N, oldest <age>` from a router `codex_pending` entry; `-` when the peer is not Codex or the router sent none."""
    if not isinstance(pending, dict) or not isinstance(pending.get("pending"), int):
        return "-"
    n = pending["pending"]
    return f"{n}, oldest {_age(pending.get('oldest_age_s') or 0)}" if n else "0"


def _print_rows(rows) -> None:
    print("NAME\tBOX\tTHIS-BOX\tVENDOR\tSTATE\tPENDING")
    for name, box, this_box, vendor, state, pending in rows:
        print(f"{name}\t{box}\t{this_box}\t{vendor}\t{state}\t{pending}")


def _yes_no(flag):
    """`yes`/`no` for a bool this-box flag; `-` when the row carries none."""
    return "-" if not isinstance(flag, bool) else "yes" if flag else "no"


def _member_ip_hosts():
    """ip literal -> member host name, from the verified membership; {} when membership is unusable.

    Only called when a listed row's box stamp is an IP, so the common listing resolves nothing."""
    import socket
    try:
        roster = _sibling("unimatrix-roster.py", "unimatrix_roster_send")
        mem = _sibling("unimatrix-membership.py", "unimatrix_membership_send")
        members = mem.verified_members(roster.settings_home())
    except Exception:
        return {}
    out = {}
    for m in members:
        try:
            for info in socket.getaddrinfo(m["host"], None, type=socket.SOCK_STREAM):
                out.setdefault(info[4][0].split("%", 1)[0].lower(), m["host"])
        except (OSError, UnicodeError):
            continue
    return out


def _list_from_sessions() -> None:
    c = _sibling("unimatrix-peer-contract.py", "unimatrix_peer_contract_send")
    box = c.local_box()
    rows = [c.agent_row(e, box) for e in _session_entries()]
    if any(c.is_ip_literal(r["box"]) for r in rows):
        ip_hosts = _member_ip_hosts()
        for r in rows:
            if c.is_ip_literal(r["box"]):
                r["box"] = c.box_id(r["box"], ip_hosts)
    _print_rows([(r["name"], r["box"], _yes_no(r["box"] == box), r["vendor"], "via SendMessage", "-") for r in rows])
    print("Message any of these with SendMessage; ListAgents lists them too.")


def _grok_target():
    """The Grok session id whose registry pid is an ancestor of this shell, else ''."""
    try:
        peer = _core_module("adapters.grok").own_session()
    except Exception:
        return ""
    return peer["target"] if peer else ""


def own_target(env: "_Environ[str]" = os.environ, grok=None):
    """Native sender session ID; the router verifies its live registry binding."""
    return (env.get("CODEX_THREAD_ID") or env.get("ANTIGRAVITY_CONVERSATION_ID")
            or env.get("UNIMATRIX_GROK_SESSION_ID") or env.get("CLAUDE_SESSION_ID")
            or env.get("CLAUDE_CODE_SESSION_ID") or (grok or _grok_target)())


def _deliver_held_grok(name, text):
    """Deliver into a live grok in this process. None when `name` is not a grok peer.

    The router process loads the grok adapter once at startup, so a held session must
    not wait on that process. A string result is a delivery failure and must not fall
    through to a second send. A dict with written=True already tty-submitted; the
    router returns on that and does not send again.
    """
    m = _sibling("unimatrix-peer-grok.py", "unimatrix_peer_grok_deliver")
    peer = next((p for p in m.discover_peers() if p.get("name") == name), None)
    if peer is None:
        return None
    try:
        return asyncio.run(m.deliver(peer["target"], peer["cwd"], text))
    except (OSError, subprocess.SubprocessError) as e:
        return f"delivery failed: {e}"


def own_session_name(entries=None, parent_of=None, start=None, max_depth: int = 16):
    """Roster name of the live session whose pid is an ancestor of this shell, else ''.

    The router stamps a CLI send with this name so a reply to the message's `from` reaches the sender."""
    try:
        by_pid = {e["pid"]: e["name"] for e in (_session_entries() if entries is None else entries)}
        step = parent_of or _sibling("unimatrix-peer-grok.py", "unimatrix_peer_grok_send").parent_pid
        pid, seen = os.getpid() if start is None else start, set()
        for _ in range(max_depth):
            if pid in by_pid:
                return by_pid[pid]
            if pid is None or pid in seen:
                return ""
            seen.add(pid)
            pid = step(pid)
    except Exception:
        pass
    return ""


def _unreachable_why(e, ctl) -> str:
    """The OSError text; a missing/refused endpoint (WinError 2 on a named pipe, ENOENT/ECONNREFUSED on a socket) is named as the router not running."""
    if isinstance(e, (FileNotFoundError, ConnectionRefusedError)):
        return f"{e}; no router is listening on {ctl}, start unimatrix-peer-router.py"
    return str(e)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="unimatrix-send.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--to", help="name of the agent to message (see --list)")
    p.add_argument("--list", action="store_true", help="list the agents you can message")
    p.add_argument("--endpoint-dir", default=None)
    p.add_argument("text", nargs="*")
    a = p.parse_args(argv)
    r = _router()
    started = time.time() - 1  # one second of slack: the bridge stamps `at` on its own clock read, after ours
    ctl = r.endpoint_path(r.ROUTER_ENDPOINT_SEED, a.endpoint_dir)
    # Resolved before the send: a misrouted mirror is unmirrored by the roster sync while the bridge
    # records its FAILED row, so a lookup after the router's reply finds no mirror and reads success.
    to_mirror, to_mirror_name = (_is_mirror(a.to), _mirror_name(a.to)) if a.to and not a.list else (False, "")
    if a.list:
        req = {"op": "list", "as_target": own_target(), "as": "cli"}
    elif a.to and a.text:
        text = " ".join(a.text)
        held = _deliver_held_grok(a.to, text)
        if isinstance(held, dict) and held.get("user_message_chunk") is True:
            print(f"user_message_chunk {held.get('session_id')}")
            return 0
        if isinstance(held, dict) and held.get("written") is True:
            print(f"sent to {a.to}")
            return 0
        if isinstance(held, str):
            print(f"undelivered: {a.to}: {held}", file=sys.stderr)
            return 1
        target = own_target()
        req = {"op": "send", "to": a.to, "text": text, "as_target": target, "as": "cli"}
        if not target and (me := own_session_name()):
            req["as_session"] = me
    else:
        p.error("give --to NAME and the message text, or --list")
    try:
        resp = r.request_line(ctl, req)
    except OSError as e:
        why = _unreachable_why(e, ctl)
        if a.list:
            print(f"unimatrix router not reachable ({why}); listing local session records, "
                  "not the router's roster", file=sys.stderr)
            _list_from_sessions()
            return 0
        print(f"unimatrix router not reachable: {why}", file=sys.stderr)
        print("Claude sessions and bridged mirrors are reached with SendMessage; ListAgents lists them.",
              file=sys.stderr)
        return 1
    if not resp.get("ok"):
        prefix = "" if a.list else f"undelivered: {a.to}: "
        print(prefix + resp.get("error", "failed"), file=sys.stderr)
        if resp.get("peers"):
            print("agents: " + ", ".join(resp["peers"]), file=sys.stderr)
        return 1
    if a.list:
        reachable = resp.get("reachable")
        if not isinstance(reachable, list):
            print("router list reply lacks 'reachable'; restart the router", file=sys.stderr)
            return 1
        agents = {row.get("name"): row for row in resp.get("agents", []) if isinstance(row, dict)}
        peers = set(resp.get("peers", []))
        pend = resp.get("codex_pending") if isinstance(resp.get("codex_pending"), dict) else {}
        _print_rows([(name, agents.get(name, {}).get("box", "-"), _yes_no(agents.get(name, {}).get("this_box")),
                      agents.get(name, {}).get("vendor", "-"),
                      "stale" if agents.get(name, {}).get("stale") is True
                      else "ready" if name in peers else "session",
                      _pending_cell(pend.get(name))) for name in reachable])
        print("Message any of these with SendMessage; ListAgents lists them too.")
    elif resp.get("held") is True:
        print(f"held for {a.to}: {resp.get('pending', 0)} pending, oldest {_age(resp.get('oldest_age_s') or 0)}")
    elif resp.get("reply"):
        print(resp["reply"])
    elif resp.get("written") is True or resp.get("msg_id"):
        outcome = relay_outcome(to_mirror_name or a.to, started) if to_mirror else {"ok": True}
        if outcome is None:
            print(f"unconfirmed: {a.to}: no far ingest ack within {RELAY_SETTLE_SECONDS}s; receiver enqueue: "
                  "unknown (a cold leg can outlast this wait). Ask the receiving box's relay: "
                  f"`receipts {a.to.partition('.')[0]} {started - 60:.0f}` lists a row per message it enqueued "
                  "(name, session id, ref or pid all work); a row there means enqueued, none means resend",
                  file=sys.stderr)
            return 1
        elif not outcome.get("ok"):
            print(f"undelivered: {a.to}: {outcome.get('error', 'far relay refused')}"
                  + (_route_note(outcome) if to_mirror else "") + f"; receiver enqueue: {enqueue_state(outcome)}",
                  file=sys.stderr)
            return 1
        else:
            print(f"sent to {a.to}" + _reached_note(resp) + (_route_note(outcome) if to_mirror else ""))
    else:
        print(f"unconfirmed: router gave no delivery receipt for {a.to}; the message may have been delivered, "
              "check before resending", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
