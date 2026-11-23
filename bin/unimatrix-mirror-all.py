#!/usr/bin/env python3
"""Keep every live local session mirrored on the far box through one `unimatrix-inbox.py mux`
client (one far relay process), which adds and drops names as sessions appear and exit. A far
relay without `inbox-mux` falls back to one `inbox` client per session.

Usage:
  unimatrix-mirror-all.py <log> [<skip-name> ...] --remote <lan-ssh-alias> [--tunnel-remote <ssh-alias>] [--key <path>]

--remote is tried first; --tunnel-remote (or $UNIMATRIX_TUNNEL_REMOTE) is used only while
--remote does not answer.

A pair linked from both sides holds one mirror, on the box `mirror_owner` names; the other side's
sync starts none.

Skipped names are mirrored by a client started elsewhere. Our own mirror entries
(those carrying macSocketPath) are never exported back.
"""
import argparse
import importlib.util
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace
    from types import ModuleType

HERE = Path(__file__).resolve().parent
NAME_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")
POLL_SECONDS = 30


def _shared() -> "ModuleType":
    spec = importlib.util.spec_from_file_location("unimatrix_roster", HERE / "unimatrix-roster.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ROSTER = None


def _roster() -> "ModuleType":
    """The roster module, loaded on first use: a bin entrypoint stays inert at import."""
    global _ROSTER
    if _ROSTER is None:
        _ROSTER = _shared()
    return _ROSTER


def __getattr__(name) -> "ModuleType":
    if name == "R":
        return _roster()
    raise AttributeError(name)


def parse_args(argv) -> "Namespace":
    p = argparse.ArgumentParser(prog="unimatrix-mirror-all.py")
    p.add_argument("log")
    p.add_argument("skip", nargs="*", help="session names mirrored by a client started elsewhere")
    p.add_argument("--remote", required=True, help="ssh alias of the far box on the LAN, tried first")
    p.add_argument("--tunnel-remote", default=None, help=f"ssh alias over the tunnel, used only when --remote does not answer (default: ${_roster().TUNNEL_ENV})")
    p.add_argument("--key", default=None)
    a = p.parse_args(argv)
    a.key = a.key or _roster().default_key()
    a.tunnel_remote = a.tunnel_remote or _roster().default_tunnel()
    return a


_RELAY = None


def _relay() -> "ModuleType":
    """The relay module, loaded on first use for its `codex_holder_dead`."""
    global _RELAY
    if _RELAY is None:
        spec = importlib.util.spec_from_file_location("unimatrix_relay", HERE / "unimatrix-relay.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _RELAY = mod
    return _RELAY


def live_sessions(skip):
    """Mirrorable local sessions: pid alive, and not a Codex face whose holder is dead."""
    sess = _roster().sessions_dir()
    holders = []
    out = {}
    for f in sorted(os.listdir(sess)):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(sess, f), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        name = d.get("name")
        if d.get(_roster().FAR_SOCKET_FIELD) or not name or name in skip or not NAME_RE.fullmatch(str(name)):
            continue
        if not isinstance(d.get("pid"), int) or not d.get("messagingSocketPath"):
            continue
        if _roster().pid_alive(d["pid"]) and not _relay().codex_holder_dead(d, holders):
            out[name] = d
    return out


def inbox_cmd(d, name, log_dir, remote, key, tunnel_remote=None):
    cmd = [_roster().console_python(), str(HERE / "unimatrix-inbox.py"), str(d["pid"]), name,
           os.path.join(log_dir, f"unimatrix-inbox-{name}.log"), d["messagingSocketPath"],
           "--remote", remote, "--key", key]
    return cmd + ["--tunnel-remote", tunnel_remote] if tunnel_remote else cmd


def mux_names_path(log_dir, remote) -> str:
    """The file the mux client polls for the names to hold: name -> {pid, endpoint}."""
    return os.path.join(log_dir, f"unimatrix-inbox-mux-{re.sub(r'[^A-Za-z0-9._-]', '_', str(remote))}.names.json")


def mux_cmd(log_dir, remote, key, tunnel_remote=None):
    """The one near client for a far box: it subscribes inbox-mux once and follows the names file."""
    tag = re.sub(r"[^A-Za-z0-9._-]", "_", str(remote))
    cmd = [_roster().console_python(), str(HERE / "unimatrix-inbox.py"), "mux",
           os.path.join(log_dir, f"unimatrix-inbox-mux-{tag}.log"),
           "--names-file", mux_names_path(log_dir, remote), "--remote", remote, "--key", key]
    return cmd + ["--tunnel-remote", tunnel_remote] if tunnel_remote else cmd


UNSUPPORTED_HOST_RC = 3  # the relay's inbox exit code for a Windows far box
MUX_UNSUPPORTED_RC = 4  # unimatrix-inbox.py mux: the far relay answered `usage:` to inbox-mux
BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 600

_now = time.monotonic
ABSENT_POLLS_BEFORE_UNMIRROR = 2  # a router or engine respawn re-registers a session within seconds
# Per supervisor life: `unsupported` stops all dialing; `fails`, `retry_at` and `absent` (consecutive
# polls a session was missing) are per session name.
# `up_since` is the monotonic time a client was spawned (or first seen alive).
STABLE_SECONDS = 300  # a client must stay up this long before its death count resets
# `rc` is each name's last client exit code; `state_sig` is what the mirror-state file last recorded.
# `mux_off` latches per-name clients once a far relay answered `usage:` to inbox-mux; `mux` is
# far box -> {proc, fails, retry_at, up_since, names} for its one mux client.
_STATE = {"unsupported": False, "fails": {}, "retry_at": {}, "absent": {}, "up_since": {},
          "rc": {}, "state_sig": None, "mux_off": False, "mux": {}}


def backoff_seconds(fails):
    """Wait before respawning a client that has died `fails` times in a row without staying up."""
    return min(BACKOFF_BASE_SECONDS * 2 ** fails, BACKOFF_CAP_SECONDS)


FAR_OWNER_REFUSALS = ("belongs to a live local session", "already mirrored by live relay")


HOST_REFUSAL = "hosted on macOS/Linux boxes only"  # the relay's inbox refusal text; the rc it arrives under varies


def _client_log_tail(log_dir, name):
    try:
        with open(os.path.join(log_dir, f"unimatrix-inbox-{name}.log"), "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 4096))
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def refused_by_far_owner(log_dir, name) -> bool:
    """True when the client's last attempt was refused because the far box already holds `name`.

    The far box's pull supervisor owns such a name: one owner per name, so this push side parks it
    instead of redialing every poll and flipping the owner."""
    tail = _client_log_tail(log_dir, name)
    return any(m in tail for m in FAR_OWNER_REFUSALS)


def refused_by_far_host(log_dir, name) -> bool:
    """True when the client's last attempt was told the far box hosts no mirrors, whatever the exit code."""
    return HOST_REFUSAL in _client_log_tail(log_dir, name)


def sync(clients, live, cfg, say):
    """One reconcile pass: one mux client per far box, per-name clients once the far relay lacks inbox-mux.

    `clients` is name -> (session pid, Popen); under the mux every name holds the one shared Popen."""
    if _STATE["mux_off"]:
        return sync_per_name(clients, live, cfg, say)
    return sync_mux(clients, live, cfg, say)


def _mux_held(live, clients, m, absent, say):
    """Names the mux must hold: every live one, and an absent one for ABSENT_POLLS_BEFORE_UNMIRROR polls."""
    held = {n: {"pid": d["pid"], "endpoint": d["messagingSocketPath"]} for n, d in live.items()}
    for name in [n for n in clients if n not in live]:
        missed = absent[name] = absent.get(name, 0) + 1
        if missed < ABSENT_POLLS_BEFORE_UNMIRROR and name in m["names"]:
            say(f"session {name} absent ({missed}/{ABSENT_POLLS_BEFORE_UNMIRROR}); name kept")
            held[name] = m["names"][name]
            continue
        absent.pop(name, None)
        clients.pop(name)
        say(f"unmirror {name}")
    return held


def _mux_reap(m, clients, live, cfg, log_dir, say) -> bool:
    """Account for a mux client that exited; True when the pass must fall back to per-name clients."""
    rc = m["proc"].poll()
    m["proc"] = None
    if rc == UNSUPPORTED_HOST_RC or refused_by_far_host(log_dir, f"mux-{_tag(cfg.remote)}"):
        _STATE["unsupported"] = True
        _STATE["rc"].update({n: rc for n in set(live) | set(clients)})
        say(f"far box does not host mirror inboxes (rc={rc}); mirroring to it is off, state recorded")
        return False
    if rc == MUX_UNSUPPORTED_RC:
        _STATE["mux_off"] = True
        clients.clear()
        for k in ("fails", "retry_at", "up_since", "rc"):
            _STATE[k].clear()
        say(f"far relay lacks inbox-mux (rc={rc}); falling back to one client per mirrored inbox")
        return True
    wait = backoff_seconds(m["fails"])
    m["fails"] += 1
    m["retry_at"] = _now() + wait
    for n in set(live) | set(clients):
        _STATE["rc"][n] = rc
        _STATE["retry_at"][n] = m["retry_at"]
    say(f"mux client exited rc={rc}; retry in {wait}s")
    return False


def _tag(remote) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(remote))


def _pair_contract() -> "ModuleType":
    path = HERE / "lib" / "unimatrix_pair_contract.py"
    mod = sys.modules.get("unimatrix_pair_contract")
    if mod is None:
        spec = importlib.util.spec_from_file_location("unimatrix_pair_contract", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["unimatrix_pair_contract"] = mod
        spec.loader.exec_module(mod)
    return mod


def far_owns_mirror(cfg, say) -> bool:
    """True when the far box is the pair's mirror owner, so this side starts no mirror.

    The far side's own sync starts the one mirror; replies still return down its inbox connection.
    The near side is the owner (or the names tie) in every other case, so a pair always keeps one.
    A Windows near box never defers: it hosts no mirror inboxes, so the far owner's mirror into it is
    refused and only this side's mirror carries its sessions to the far box."""
    if sys.platform == "win32":
        return False
    box_of = _box_mux_module().box_of
    me, far = box_of(socket.gethostname()), box_of(cfg.remote)
    if me == far or _pair_contract().mirror_owner(me, far) != far:
        return False
    said_for = _STATE.setdefault("far_owner_said", set())
    if cfg.remote not in said_for:
        said_for.add(cfg.remote)
        say(f"{far} owns the {me}/{far} mirror; this side starts none")
    return True


def sync_mux(clients, live, cfg, say):
    """One reconcile pass over the far box's single mux client: it is started when a name is wanted,
    respawned under the per-name backoff curve when it dies, and told the names via a file."""
    if far_owns_mirror(cfg, say):
        return
    log_dir = os.path.dirname(os.path.abspath(cfg.log))
    m = _STATE["mux"].setdefault(cfg.remote, {"proc": None, "fails": 0, "retry_at": None,
                                              "up_since": None, "names": {}})
    absent = _STATE["absent"]
    for name in live:
        absent.pop(name, None)
    if m["proc"] is not None and m["proc"].poll() is not None and _mux_reap(m, clients, live, cfg, log_dir, say):
        return sync_per_name(clients, live, cfg, say)
    held = _mux_held(live, clients, m, absent, say)
    if held != m["names"]:
        try:
            _roster().write_json_atomic(mux_names_path(log_dir, cfg.remote), held)
            m["names"] = held
        except OSError as e:
            say(f"mux names file not written: {e}")
    proc = m["proc"]
    if proc is not None and not held:
        _roster().tree_kill(proc.pid)
        m["proc"] = proc = None
        m["up_since"] = None
    elif proc is not None:
        if _now() - m["up_since"] >= STABLE_SECONDS:
            m["fails"] = 0
    elif held and not _STATE["unsupported"] and (m["retry_at"] is None or _now() >= m["retry_at"]):
        proc = m["proc"] = _roster().spawn(mux_cmd(log_dir, cfg.remote, cfg.key, cfg.tunnel_remote))
        m["up_since"], m["retry_at"] = _now(), None
        for n in held:
            _STATE["retry_at"].pop(n, None)
        say(f"mux client {proc.pid} -> {cfg.remote}: {len(held)} names")
    if proc is None and m["retry_at"] is not None:
        for n in held:
            _STATE["retry_at"][n] = m["retry_at"]
    if proc is not None:
        for name, d in live.items():
            if name not in clients:
                say(f"mirror {name} pid {d['pid']} -> mux client {proc.pid}")
            clients[name] = (d["pid"], proc)
    write_mirror_state(log_dir, clients, live)
    publish_stale(clients, live, cfg, say)


def sync_per_name(clients, live, cfg, say) -> None:
    """One reconcile pass with one client per session: `clients` is name -> (session pid, Popen)."""
    if far_owns_mirror(cfg, say):
        return
    log_dir = os.path.dirname(os.path.abspath(cfg.log))
    fails, retry_at, absent = _STATE["fails"], _STATE["retry_at"], _STATE["absent"]
    up_since = _STATE["up_since"]
    for name in live:
        absent.pop(name, None)
    for name, d in live.items():
        if _STATE["unsupported"]:
            break
        c = clients.get(name)
        if c and c[0] == d["pid"]:
            rc = c[1].poll()
            if rc is None:
                if _now() - up_since.setdefault(name, _now()) >= STABLE_SECONDS:
                    fails.pop(name, None)  # up for STABLE_SECONDS: the next death starts the backoff over
                continue
            if rc == UNSUPPORTED_HOST_RC or refused_by_far_host(log_dir, name):
                _STATE["unsupported"] = True
                _STATE["rc"][name] = rc
                say(f"far box does not host mirror inboxes (rc={rc}); mirroring to it is off, state recorded")
                break
            _STATE["rc"][name] = rc
            if name not in retry_at:
                if refused_by_far_owner(log_dir, name):
                    wait = BACKOFF_CAP_SECONDS
                    say(f"client {c[1].pid} for {name} refused: the far box's own mirror holds the name; retry in {wait}s")
                else:
                    wait = backoff_seconds(fails.get(name, 0))
                    fails[name] = fails.get(name, 0) + 1
                    say(f"client {c[1].pid} for {name} exited rc={rc}; retry in {wait}s")
                retry_at[name] = _now() + wait
            if _now() < retry_at[name]:
                continue
        if c:
            _roster().tree_kill(c[1].pid)
        retry_at.pop(name, None)
        if not (c and c[0] == d["pid"]):
            fails.pop(name, None)
        p = _roster().spawn(inbox_cmd(d, name, log_dir, cfg.remote, cfg.key, cfg.tunnel_remote))
        clients[name] = (d["pid"], p)
        up_since[name] = _now()
        say(f"mirror {name} pid {d['pid']} -> client {p.pid}")
    for name in [n for n in clients if n not in live]:
        missed = absent[name] = absent.get(name, 0) + 1
        if missed < ABSENT_POLLS_BEFORE_UNMIRROR and clients[name][1].poll() is None:
            say(f"session {name} absent ({missed}/{ABSENT_POLLS_BEFORE_UNMIRROR}); client kept")
            continue
        absent.pop(name, None)
        up_since.pop(name, None)
        # The client's ssh child holds the far inbox open; killing python alone orphans it.
        _roster().tree_kill(clients.pop(name)[1].pid)
        say(f"unmirror {name}")
    for name in [n for n in absent if n not in clients]:
        del absent[name]
    write_mirror_state(log_dir, clients, live)
    publish_stale(clients, live, cfg, say)


STALE_RENEW_SECONDS = 600
DEAD_MARK_SECONDS = 2 * BACKOFF_CAP_SECONDS
_PUBLISHED = {}  # name -> (state, until epoch) last sent to the far box


def _box_mux() -> "ModuleType":
    """The box_mux module, for the calls that open a stream to the far box."""
    return _box_mux_module()


def _box_mux_module() -> "ModuleType":
    """The box_mux module itself; pure helpers like `box_of` read it here, never opening a stream."""
    path = HERE / "lib" / "unimatrix_box_mux.py"
    mod = sys.modules.get("unimatrix_box_mux")
    if mod is None:
        spec = importlib.util.spec_from_file_location("unimatrix_box_mux", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["unimatrix_box_mux"] = mod
        spec.loader.exec_module(mod)
    return mod


def _send_stale_mark(cfg, command):
    remote = _roster().pick_remote(cfg.remote, getattr(cfg, "tunnel_remote", None))
    return _box_mux().for_remote(remote, key=cfg.key, extra=["-o", "ConnectTimeout=10"]).run(command, b"", timeout=15)


def publish_stale(clients, live, cfg, say, send=None) -> None:
    """Tell the far box about each dead or backed-off mirror so a sender there lists it as stale.

    The mirror-state file describes this box; the far box's senders cannot read it. One relay call
    per name when its state changes or its mark is within STALE_RENEW_SECONDS of expiring, run off
    the poll loop. A refused host is not published: the far box hosts no mirrors to mark."""
    if not getattr(cfg, "remote", None):
        return
    now = time.time()
    due = []
    for name, v in mirror_states(clients, live).items():
        if v["state"] not in ("backoff", "dead"):
            _PUBLISHED.pop(name, None)
            continue
        until = max(v["retry_at_epoch"] if v["state"] == "backoff" else int(now) + DEAD_MARK_SECONDS,
                    int(now) + 60)
        sent = _PUBLISHED.get(name)
        keep = STALE_RENEW_SECONDS if v["state"] == "dead" else 0
        if sent and sent[0] == v["state"] and sent[1] - now > keep:
            continue
        _PUBLISHED[name] = (v["state"], until)
        due.append(f"mirror-stale {name} {v['state']} {until} "
                   f"{re.sub(r'[^a-z0-9-]', '-', _box_mux_module().box_of(socket.gethostname())) or 'unknown'}")
    if due:
        (send or _start_publish)(cfg, due, say)


def _start_publish(cfg, commands, say) -> None:
    def run() -> None:
        for command in commands:
            try:
                r = _send_stale_mark(cfg, command)
                if r.returncode != 0:
                    say(f"far box refused stale mark ({command.split()[1]}): rc={r.returncode}")
            except Exception as e:
                say(f"far box stale mark failed ({command.split()[1]}): {type(e).__name__}")
    threading.Thread(target=run, daemon=True).start()


MIRROR_STATE_FILE = "unimatrix-mirror-state.json"


def mirror_states(clients, live):
    """name -> {state, rc, retry_at_epoch} for every live session and every client still held.

    State is host-refused (far box cannot host mirrors, never retried), up (client running),
    backoff (client dead, a respawn is scheduled) or dead (client dead, nothing scheduled)."""
    wall_offset = time.time() - _now()
    out = {}
    for name in set(live) | set(clients):
        c = clients.get(name)
        rc = _STATE["rc"].get(name)
        retry = _STATE["retry_at"].get(name)
        if _STATE["unsupported"]:
            state = "host-refused"
        elif c and c[1].poll() is None:
            state = "up"
        elif retry is not None:
            state = "backoff"
        else:
            state = "dead"
        out[name] = {"state": state, "rc": rc,
                     "retry_at_epoch": int(retry + wall_offset) if state == "backoff" else None}
    return out


def write_mirror_state(log_dir, clients, live) -> None:
    """Atomically rewrite the mirror-state file when a name's state, rc or retry time changed."""
    states = mirror_states(clients, live)
    sig = {n: (v["state"], v["rc"], _STATE["retry_at"].get(n)) for n, v in states.items()}
    if sig == _STATE["state_sig"]:
        return
    try:
        _roster().write_json_atomic(os.path.join(log_dir, MIRROR_STATE_FILE), states)
    except OSError:
        return
    _STATE["state_sig"] = sig


_ROUTER_MODULE = None


def _router_module() -> "ModuleType":
    """Load the router module once: ensure_router probes every poll and every 0.2s while waiting."""
    global _ROUTER_MODULE
    if _ROUTER_MODULE is None:
        spec = importlib.util.spec_from_file_location("unimatrix_peer_router", HERE / "unimatrix-peer-router.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ROUTER_MODULE = mod
    return _ROUTER_MODULE


def kickstart_router_agent(say):
    """True when launchd's login agent was kickstarted to start the router (darwin, agent loaded).

    Trap: a router spawned here is this supervisor's child and inherits its nice (20 when launched
    under a niced shell); it also wins the race against autolink's kickstart, which then finds a live
    router and does nothing. Only a launchd start runs the router at the agent's nice."""
    spec = importlib.util.spec_from_file_location("unimatrix_autolink", HERE / "unimatrix-autolink.py")
    autolink = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(autolink)
    target = autolink.launchd_agent_target()
    if not target:
        return False
    started = autolink.run_launchctl("kickstart", target)
    if started is None or started.returncode != 0:
        say(f"launchctl kickstart {target} failed; spawning the router directly")
        return False
    say(f"router not answering; kickstarted launchd agent {target}")
    return True


def router_answers(ctl):
    """True when the router control endpoint answers {"op":"list"}."""
    try:
        return bool(_router_module().request_line(ctl, {"op": "list"}, timeout=2).get("ok"))
    except (OSError, ValueError):
        return False


def spawn_router_logged(err_path):
    """Start the peer router with its stderr in `err_path`: a router that dies in start() writes only a traceback."""
    cmd = [_roster().console_python(), str(HERE / "unimatrix-peer-router.py")]
    err = open(err_path, "wb")
    try:
        if sys.platform == "win32":
            return subprocess.Popen(cmd, stderr=err, creationflags=_roster().no_window())
        return subprocess.Popen(cmd, stderr=err, start_new_session=True)
    finally:
        err.close()


def router_spawn_verdict(proc, err_path) -> str:
    """Why a spawned router is not answering: its exit code and last stderr line, or that it is alive but silent."""
    rc = proc.poll()
    if rc is None:
        return f"spawned router pid {proc.pid} is alive but its endpoint does not answer"
    try:
        tail = Path(err_path).read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except OSError:
        tail = []
    return f"spawned router pid {proc.pid} exited rc={rc}: {tail[-1] if tail else 'no stderr'}"


def ensure_router(say, wait: float = 3.0) -> bool:
    """Spawn the peer router detached when its endpoint does not answer on either OS.

    A nonblocking process lock held across probe, spawn and bind keeps two supervisors (one per far
    alias) from both spawning. Returns True when this call spawned one.
    """
    if os.environ.get("UNIMATRIX_ROUTER_SUPERVISION") == "off":
        return False
    router = _router_module()
    transport = router._transport()
    ctl = router.endpoint_path(router.ROUTER_ENDPOINT_SEED)
    lock_dir = _roster().settings_home() / "unimatrix" / "router"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with open(lock_dir / "supervisor.lock", "a+b") as lock:
        if not transport.lock_file(lock):
            return False
        try:
            if router_answers(ctl):
                return False
            # A live router may be draining children with its listener already closed.
            # Its lifetime lease prevents a replacement binding before that cleanup ends.
            with open(lock_dir / "router.lock", "a+b") as lease:
                if not transport.lock_file(lease):
                    return False
                transport.unlock_file(lease)
            if not kickstart_router_agent(say):
                err_path = lock_dir / "spawn.err"
                p = spawn_router_logged(err_path)
                say(f"router not answering at {ctl}; spawned router pid {p.pid}")
            else:
                p = err_path = None
            deadline = time.time() + wait
            while time.time() < deadline and not router_answers(ctl):
                if p is not None and p.poll() is not None:
                    break
                time.sleep(0.2)
            if p is not None and not router_answers(ctl):
                say(router_spawn_verdict(p, err_path))
            return True
        finally:
            transport.unlock_file(lock)


def boot_prune(log_dir, live, say) -> None:
    """Drop the recorded mirror state of every name whose near source face is gone or dead.

    A restarted supervisor would otherwise carry the last life's rows (and re-publish their stale
    marks) for sessions it will never mirror again."""
    path = os.path.join(log_dir, MIRROR_STATE_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            states = json.load(fh)
    except (OSError, ValueError):
        return
    if not isinstance(states, dict):
        return
    kept = {n: v for n, v in states.items() if n in live}
    for name in sorted(set(states) - set(kept)):
        say(f"boot prune: {name} has no live near face; mirror state dropped")
    if kept != states:
        try:
            _roster().write_json_atomic(path, kept)
        except OSError:
            pass


def main(argv=None) -> None:
    cfg = parse_args(sys.argv[1:] if argv is None else argv)
    skip = set(cfg.skip)
    log = open(cfg.log, "a", encoding="utf-8", buffering=1)

    def say(msg) -> None:
        log.write(f"{time.strftime('%H:%M:%SZ', time.gmtime())} {msg}\n")

    if sys.platform != "win32":
        # A stop is never silent: a clean 0 would read as "nothing to mirror" while every mirror drops.
        def stopped(signum, _frame) -> None:
            say(f"stopped by signal {signum}; mirrors drop until relaunched")
            sys.exit(128 + signum)
        signal.signal(signal.SIGTERM, stopped)
    _roster().stamp_supervisor(cfg.remote, "inbox")
    try:
        own_start = _roster().proc_start(os.getpid())
    except (OSError, subprocess.SubprocessError):
        own_start = None  # no identity to address: the supervisor runs, but is not stop-requestable
    clients = {}
    try:
        boot_prune(os.path.dirname(os.path.abspath(cfg.log)), live_sessions(skip), say)
        while True:
            if own_start is not None and _roster().stop_requested(own_start):
                say("STOPPED-BY-REQUEST")
                _roster().clear_stop(os.getpid())
                break
            ensure_router(say)
            sync(clients, live_sessions(skip), cfg, say)
            if own_start is None:
                time.sleep(POLL_SECONDS)
            elif _roster().wait_or_stop(POLL_SECONDS, own_start):
                say("STOPPED-BY-REQUEST")
                _roster().clear_stop(os.getpid())
                break
    finally:
        pids = {p.pid for _, p in clients.values()}
        pids |= {m["proc"].pid for m in _STATE["mux"].values() if m["proc"] is not None}
        for pid in pids:
            _roster().tree_kill(pid)


if __name__ == "__main__":
    main()
