"""Keep every live far-box session mirrored here: poll the far relay's `roster`, run one
relay-mode bridge per far session, and remove it when the session exits.

Usage:
  unimatrix-roster.py <log> [<skip-far-socket> ...] --remote <lan-ssh-alias> [--tunnel-remote <ssh-alias>] [--key <path>]

--remote is tried first; --tunnel-remote (or $UNIMATRIX_TUNNEL_REMOTE) is used only while
--remote does not answer. Without it the tunnel is never involved.

Skipped sockets have hand-run bridges. A mirror the harness will use, idle notices
included, needs: an endpoint named cc-msg-<32 hex>, procStart as the bridge's raw
process-start stamp (a string), and a key file named <pid>.<sha256(endpoint)>.key
(the endpoint lowercased on Windows).

This module also carries the process and registry helpers that unimatrix-mirror-all.py
and unimatrix-reshape.py share; they are importable without side effects.
"""
import argparse
import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOPBACK_SOCKS = "/tmp/cc-socks"
# Registry field the mirror entries carry for the far session's real socket.
FAR_SOCKET_FIELD = "macSocketPath"
STILL_ACTIVE = 259
POLL_SECONDS = 30
PROBE_SECONDS = 3
# Names the far box's off-network (tunnel) ssh alias; the --remote alias is always tried first.
TUNNEL_ENV = "UNIMATRIX_TUNNEL_REMOTE"


def sessions_dir():
    return os.path.expanduser("~/.claude/sessions")


def settings_home():
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return Path(env) if env else Path.home() / ".coordinator-claude-settings"


def default_key():
    """The Unimatrix-Zero key: the settings home's, else the group-em home's; first candidate when neither exists."""
    home = settings_home()
    cands = [home / ".secrets" / "ssh" / "unimatrix-zero", home / "group-em" / ".secrets" / "ssh" / "unimatrix-zero"]
    return str(next((c for c in cands if c.is_file()), cands[0]))


def _is_win(platform=None):
    return (platform or sys.platform) == "win32"


def no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def spawn(cmd):
    """Start a child that can be tree-killed later: its own process group off Windows."""
    if sys.platform == "win32":
        return subprocess.Popen(cmd, creationflags=no_window())
    return subprocess.Popen(cmd, start_new_session=True)


def tree_kill(pid):
    """Stop `pid` and every descendant: taskkill /T on Windows, the process group elsewhere."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                       capture_output=True, creationflags=no_window())
        return
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return
    # A pid that shares our own group would take this process down with it.
    if pgid == os.getpgrp():
        _signal_pid(pid, signal.SIGKILL)
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            # Darwin answers EPERM, not ESRCH, once only zombies remain in the group; these are our own children.
            return
        time.sleep(0.2)


def _signal_pid(pid, sig):
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass


def pid_alive(pid):
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = wintypes.DWORD()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


_LIVENESS = []


def _liveness():
    if not _LIVENESS:
        import importlib.util
        spec = importlib.util.spec_from_file_location("unimatrix_liveness", HERE / "unimatrix-liveness.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _LIVENESS.append(mod)
    return _LIVENESS[0]


def _ps_lstart(pid):
    # The harness compares this string byte for byte with ps's own output, which pads a
    # one-digit day ("Nov  4"); collapsing the whitespace hides the entry on days 1-9.
    return subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                          capture_output=True, text=True, check=True,
                          creationflags=no_window()).stdout.strip()


def proc_start(pid, platform=None):
    """Raw process-start stamp the harness compares as a string.

    Read without a spawn through the liveness module; `ps` only when that read raises OSError off Windows."""
    try:
        return _liveness().proc_start(pid, platform)
    except OSError:
        if _is_win(platform):
            raise
        return _ps_lstart(pid)


def pid_domain(platform=None):
    plat = platform or sys.platform
    if plat == "win32":
        return f"win32:{socket.gethostname().lower()}"
    return "darwin" if plat == "darwin" else "linux"


def local_endpoint(far_socket, platform=None):
    """Local endpoint for the mirror of `far_socket`: a harness-shaped cc-msg-<32 hex> name."""
    hexname = hashlib.md5(f"unimatrix-{far_socket}".encode()).hexdigest()
    if _is_win(platform):
        return "\\\\.\\pipe\\LOCAL\\cc-msg-" + hexname
    return f"{LOOPBACK_SOCKS}/cc-msg-{hexname}.sock"


def key_name(pid, endpoint, platform=None):
    """Key file name the harness expects for a session registered on `endpoint`."""
    if _is_win(platform):
        endpoint = endpoint.lower()
    return f"{pid}.{hashlib.sha256(endpoint.encode()).hexdigest()}.key"


def bridge_cmd(endpoint, log, remote, key, return_port=None, inbox=None, tunnel_remote=None):
    cmd = [sys.executable, str(HERE / "unimatrix-bridge.py"), endpoint, "relay", log]
    if return_port is not None and inbox:
        cmd += [str(return_port), inbox]
    cmd += ["--remote", remote, "--key", key]
    return cmd + ["--tunnel-remote", tunnel_remote] if tunnel_remote else cmd


def default_tunnel():
    return os.environ.get(TUNNEL_ENV) or None


def ssh_fields(alias):
    """`ssh -G` output for `alias` as a lowercase-key dict."""
    r = subprocess.run(["ssh", "-G", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", alias],
                       capture_output=True, timeout=10, creationflags=no_window())
    fields = {}
    for line in r.stdout.decode(errors="replace").splitlines():
        k, _, v = line.partition(" ")
        fields.setdefault(k, v.strip())
    return fields


def ssh_endpoint(alias):
    """(host, port) that ssh dials for `alias`, read from `ssh -G`; None when it prints neither."""
    fields = ssh_fields(alias)
    if not fields.get("hostname"):
        return None
    return fields["hostname"], int(fields.get("port") or 22)


def lan_reachable(alias, resolve=None, connect=None):
    """True when a TCP connection to the alias's ssh endpoint opens within PROBE_SECONDS."""
    try:
        ep = (resolve or ssh_endpoint)(alias)
        if ep is None:
            return False
        (connect or socket.create_connection)(ep, timeout=PROBE_SECONDS).close()
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def stable_remote(alias, reachable=None, fields=None, connect=None):
    """First stable name of this far box that answers now, else None: `<box>-lan` alias, then `<box>.local`.

    For when the alias's own pinned HostName has gone stale. Costs one `ssh -G` (on the `-lan`
    alias, shared by both legs) plus a TCP wait per leg, so call it only after the alias itself
    failed. `.local` is dialled on the default port as `<user>@<box>.local`, the only shape a
    single ssh host token can carry; the user is the alias's own, else the one ssh resolves."""
    user, at, host = alias.rpartition("@")
    lan = f"{user}{at}{host}-lan"
    base = alias if host.endswith("-lan") else lan
    memo = []

    def get_fields():
        if not memo:
            memo.append((fields or ssh_fields)(base))
        return memo[0]

    def endpoint(_):
        f = get_fields()
        return (f["hostname"], int(f.get("port") or 22)) if f.get("hostname") else None

    try:
        if not host.endswith("-lan"):
            up = reachable(lan) if reachable else lan_reachable(lan, resolve=endpoint, connect=connect)
            if up:
                return lan
        f = get_fields()
        port = int(f.get("port") or 22)
        name = f"{host}.local"
        if port != 22:
            return None
        (connect or socket.create_connection)((name, port), timeout=PROBE_SECONDS).close()
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    who = user or f.get("user")
    return f"{who}@{name}" if who else name


def pick_remote(lan, tunnel=None, reachable=None):
    """The far box's ssh alias to use now: the LAN alias when it answers, else the tunnel alias.

    With no tunnel alias configured the LAN alias is returned unprobed, so nothing here
    ever requires the tunnel to exist or be up.
    """
    if not tunnel or tunnel == lan:
        return lan
    return lan if (reachable or lan_reachable)(lan) else tunnel


def write_json_atomic(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.replace(tmp, path)


def parse_args(argv):
    p = argparse.ArgumentParser(prog="unimatrix-roster.py")
    p.add_argument("log")
    p.add_argument("skip", nargs="*", help="far socket paths whose bridges are run by hand")
    p.add_argument("--remote", required=True, help="ssh alias of the far box on the LAN (tried first)")
    p.add_argument("--tunnel-remote", default=None, help=f"ssh alias over the tunnel, used only when --remote does not answer (default: ${TUNNEL_ENV})")
    p.add_argument("--key", default=None)
    a = p.parse_args(argv)
    a.key = a.key or default_key()
    a.tunnel_remote = a.tunnel_remote or default_tunnel()
    return a


LABEL_SEP = "."


def bare_name(name):
    """The session name without its box label (everything from the first dot); non-strings pass through.

    A dot, not an at sign: SendMessage refuses any `@` in a recipient. Session names carry hyphens,
    never dots, and the box label may itself hold dots (an IP), so the first dot is the cut."""
    return name.partition(LABEL_SEP)[0] if isinstance(name, str) else name


def box_label(remote):
    """Which box a mirror is on: the ssh alias without any `user@` prefix."""
    return str(remote).rpartition("@")[2]


def labelled(name, remote):
    """The name, a dot, then the box, for a mirror's session name; idempotent, so a re-mirror never stacks labels."""
    if not isinstance(name, str) or not name:
        return name
    return f"{bare_name(name)}{LABEL_SEP}{box_label(remote)}"


def live_sessions():
    """(bare name, far socket or None) for each live session in the sessions dir, local and mirrored alike."""
    out = []
    sess = sessions_dir()
    try:
        files = os.listdir(sess)
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
                and pid_alive(d["pid"])):
            out.append((bare_name(d["name"]), d.get(FAR_SOCKET_FIELD)))
    return out


def live_bare_names(except_far_sock=None, scan=None):
    """Bare names of the live sessions; `scan` is a `live_sessions()` result reused across one sync pass.

    An entry mirroring `except_far_sock` is left out: it is the earlier mirror of the session being
    named, not a competitor for its name."""
    if scan is None:
        scan = live_sessions()
    return {n for n, sock in scan if not (except_far_sock and sock == except_far_sock)}


def mirror_name(name, remote, far_sock=None, scan=None):
    """The session name a mirror carries: bare, so SendMessage can address it, unless a live session
    already holds that bare name, then the box-labelled form keeps the two distinct.

    A far name with a dot that is not this box's label is dotted-to-hyphen first: the dot is the
    label separator, so a raw dotted name would be cut at its first dot and collide."""
    if not isinstance(name, str) or not name:
        return name
    if LABEL_SEP in name and not name.endswith(LABEL_SEP + box_label(remote)):
        name = name.replace(LABEL_SEP, "-")
    if bare_name(name) in live_bare_names(far_sock, scan):
        return labelled(name, remote)
    return bare_name(name)


def inbound_names():
    """Names a far box already reaches us by: live local entries its own relay holds (`unimatrixMirror`).

    The far box's inbox relay already gives such a session a local socket, so mirroring it again
    from here would list the one far session twice under one name."""
    names = set()
    sess = sessions_dir()
    for f in os.listdir(sess):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(sess, f), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("unimatrixMirror") and isinstance(d.get("pid"), int) and pid_alive(d["pid"]):
            names.add(bare_name(d.get("name")))
    return names


def mirrorable(rows, skip, inbound):
    """far socket -> row for the far rows worth mirroring: true far sessions only.

    A far relay older than its re-export filter still lists its own mirrors of our sessions
    (`unimatrixMirror`, or the far-socket field); mirroring those back loops every name into a
    duplicate. `inbound` is `inbound_names()`, computed once per poll by the caller."""
    return {r["entry"]["messagingSocketPath"]: r for r in rows
            if r["entry"]["messagingSocketPath"] not in skip
            and not (r["entry"].get("unimatrixMirror") or r["entry"].get(FAR_SOCKET_FIELD))
            and bare_name(r["entry"].get("name")) not in inbound}


def _roster_once(remote, key, tunnel_remote):
    remote = pick_remote(remote, tunnel_remote)
    r = subprocess.run(["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                        "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
                        remote, "roster"],
                       capture_output=True, timeout=20, creationflags=no_window())
    if r.returncode:
        err = r.stderr.decode("utf-8", "replace").strip().splitlines()
        raise OSError(f"roster rc={r.returncode}" + (f": {err[-1][:200]}" if err else ""))
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def fetch_roster(remote, key, tunnel_remote=None):
    """The far roster rows. A transient LAN stall (connect timeout, hung session) is retried once
    with the endpoint re-picked, so one dropped SYN is not a LINK-DOWN; a second failure raises."""
    try:
        return _roster_once(remote, key, tunnel_remote)
    except (OSError, subprocess.TimeoutExpired):
        return _roster_once(remote, key, tunnel_remote)


def unmirror(pid):
    tree_kill(pid)
    sess = sessions_dir()
    for f in os.listdir(sess):
        if f.startswith(f"{pid}."):
            os.remove(os.path.join(sess, f))


def log_label(entry):
    """Log-file label from a far-supplied entry: the name only when it is path-safe, else the pid."""
    name = entry.get("name")
    if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", name) and not name.startswith("."):
        return name
    return str(entry["pid"])


ENGINE_FIELDS = ("engine_sha", "engine_checkout_sha", "engine_freshness")


def engine_fields(row):
    """The far box's engine identity fields present on a roster row; nothing else is passed."""
    return {k: row[k] for k in ENGINE_FIELDS if k in row}


def mirror(row, cfg, say, scan=None):
    e = row["entry"]
    far_sock = e["messagingSocketPath"]
    endpoint = local_endpoint(far_sock)
    if not _is_win():
        os.makedirs(os.path.dirname(endpoint), mode=0o700, exist_ok=True)
    b = spawn(bridge_cmd(endpoint, os.path.join(os.path.dirname(os.path.abspath(cfg.log)),
                                                f"unimatrix-bridge-{log_label(e)}.log"),
                         cfg.remote, cfg.key, tunnel_remote=cfg.tunnel_remote))
    time.sleep(1)
    d = {k: v for k, v in e.items() if k not in ("pid", "procStart", "pidDomain", "messagingSocketPath")}
    if "name" in d:
        d["name"] = mirror_name(d["name"], cfg.remote, far_sock, scan)
    d.update(pid=b.pid, procStart=proc_start(b.pid), pidDomain=pid_domain(),
             messagingSocketPath=endpoint, farPid=e["pid"], **{FAR_SOCKET_FIELD: far_sock}, **engine_fields(row))
    sess = sessions_dir()
    write_json_atomic(os.path.join(sess, f"{b.pid}.json"), d)
    with open(os.path.join(sess, key_name(b.pid, endpoint)), "w", encoding="utf-8") as kf:
        kf.write(row["key"])  # never logged
    say(f"mirror {e.get('name')} {far_sock} -> bridge {b.pid} {endpoint}")
    return b


def rename_live_mirror(pid, sock, row, cfg, say, scan=None):
    """Re-evaluate the name of the live mirror `pid` against the sessions now alive; rewrite it only on change."""
    name = row["entry"].get("name")
    if not isinstance(name, str) or not name:
        return
    path = os.path.join(sessions_dir(), f"{pid}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return
    want = mirror_name(name, cfg.remote, sock, scan)
    if isinstance(d, dict) and d.get("name") != want:
        d["name"] = want
        write_json_atomic(path, d)
        say(f"rename mirror {sock} -> {want}")


def sync(bridges, rows, cfg, say):
    """One reconcile pass: `rows` is far socket -> roster row; `bridges` far socket -> Popen."""
    scan = live_sessions()
    for sock, row in rows.items():
        b = bridges.get(sock)
        if b and b.poll() is None:
            rename_live_mirror(b.pid, sock, row, cfg, say, scan)
            continue
        if b:
            unmirror(b.pid)
            scan = [(n, s) for n, s in scan if s != sock]
        bridges[sock] = mirror(row, cfg, say, scan)
        nm = mirror_name(row["entry"].get("name"), cfg.remote, sock, scan)
        if isinstance(nm, str) and nm:
            scan.append((bare_name(nm), sock))
    for sock in [s for s in bridges if s not in rows]:
        unmirror(bridges.pop(sock).pid)
        say(f"unmirror {sock}")


def link_state_path(alias, home=None):
    """Link-state record path for far `alias`: <settings home>/unimatrix/link-state/<alias, path-safe>.json."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", alias)
    return (Path(home) if home else settings_home()) / "unimatrix" / "link-state" / f"{safe}.json"


def read_link_state(path):
    """The recorded state ("up"|"down") at `path`; "up" when absent or unreadable."""
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return "down" if isinstance(d, dict) and d.get("state") == "down" else "up"
    except (OSError, ValueError):
        return "up"


def note_link(prev, ok, alias, reason, say, path):
    """Return the link state after one poll; on a change only, write the record and log one line.

    Record contract (read by coordinator_core/group_em/watch.py): one JSON file per far alias at
    `link_state_path(alias)` holding {"alias", "state": "up"|"down", "since": UTC ISO-8601, "reason"}.
    A failed record write is logged and never raised."""
    state = "up" if ok else "down"
    if state == prev:
        return state
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    say(f"LINK-{state.upper()} {alias}" + (f": {reason}" if reason else ""))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(str(path), {"alias": alias, "state": state, "since": since, "reason": reason or ""})
    except (OSError, ValueError, TypeError) as ex:
        say(f"link-state write failed: {ex}")
    return state


def main(argv=None):
    cfg = parse_args(sys.argv[1:] if argv is None else argv)
    skip = set(cfg.skip)
    log = open(cfg.log, "a", encoding="utf-8", buffering=1)

    def say(msg):
        log.write(f"{time.strftime('%H:%M:%SZ', time.gmtime())} {msg}\n")

    if sys.platform != "win32":
        # A stop is never silent: a clean 0 would read as "nothing to mirror" while every mirror drops.
        def stopped(signum, _frame):
            say(f"stopped by signal {signum}; mirrors drop until relaunched")
            sys.exit(128 + signum)
        signal.signal(signal.SIGTERM, stopped)
    bridges = {}
    link_path = link_state_path(cfg.remote)
    link = read_link_state(link_path)
    try:
        while True:
            try:
                rows = mirrorable(fetch_roster(cfg.remote, cfg.key, cfg.tunnel_remote), skip, inbound_names())
            except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as ex:
                say(f"roster failed: {ex}")
                link = note_link(link, False, cfg.remote, str(ex), say, link_path)
                time.sleep(POLL_SECONDS)
                continue
            link = note_link(link, True, cfg.remote, "", say, link_path)
            sync(bridges, rows, cfg, say)
            time.sleep(POLL_SECONDS)
    finally:
        for b in bridges.values():
            tree_kill(b.pid)


if __name__ == "__main__":
    main()
