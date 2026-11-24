#!/usr/bin/env python3
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
import copy
import hashlib
import importlib.util
import json
import os
import re
import signal
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOPBACK_SOCKS = os.environ.get("UNIMATRIX_LOOPBACK_SOCKS") or "/tmp/cc-socks"  # override: tests only, never a live dir
# Registry field the mirror entries carry for the far session's real socket.
FAR_SOCKET_FIELD = "macSocketPath"
STILL_ACTIVE = 259
POLL_SECONDS = 30
STOP_POLL_SECONDS = 0.5
PROBE_SECONDS = 3
FAR_ADDRESS_BUDGET_SECONDS = 8
FAR_ADDRESSES_TRIED = 2
# Names the far box's off-network (tunnel) ssh alias; the --remote alias is always tried first.
TUNNEL_ENV = "UNIMATRIX_TUNNEL_REMOTE"


def sessions_dir():
    """Claude Code's session registry: `$CLAUDE_CONFIG_DIR/sessions`, else `~/.claude/sessions`.

    It belongs to the Claude config dir, never the settings home: settings homes on one box share it
    (plan row C0-R, 2026-11-20)."""
    config = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    return os.path.join(config, "sessions") if config else os.path.expanduser("~/.claude/sessions")


SETTINGS_HOME_KEY = "COORDINATOR_SETTINGS_HOME"


class MissingSettingsError(RuntimeError):
    """The settings-home key is unset or empty: no output root is guessed."""


class MissingRelayKeyError(RuntimeError):
    """No relay key resolves for an ordinary roster invocation; raised before any supervisor startup."""


def settings_home() -> Path:
    """The settings home named by $COORDINATOR_SETTINGS_HOME; raises MissingSettingsError when unset or empty."""
    env = os.environ.get(SETTINGS_HOME_KEY)
    if not env or not env.strip():
        raise MissingSettingsError(f"missing-settings: {SETTINGS_HOME_KEY} is unset; set it to the settings home")
    return Path(env)


def delivery_settings_home() -> Path:
    """The settings home for a delivery leg: $COORDINATOR_SETTINGS_HOME, else ~/.coordinator-claude-settings; never raises.

    An sshd forced command and a supervisor-spawned bridge or router carry no env, so every helper
    reachable from a relay delivery or a bridge send uses this form. Ordinary roster callers use settings_home()."""
    env = os.environ.get(SETTINGS_HOME_KEY)
    return Path(env) if env and env.strip() else Path.home() / ".coordinator-claude-settings"


def export_settings_home() -> None:
    """Pin the resolved delivery settings home into this process's environment so every child it spawns (bridge, router, relay) inherits it."""
    os.environ[SETTINGS_HOME_KEY] = str(delivery_settings_home())


def default_key() -> str:
    """The Unimatrix-Zero key: the settings home's, else the group-em home's; first candidate when neither exists.

    Resolves the home with delivery_settings_home(): an in-process caller (autolink, a delivery helper) carries no env.
    parse_args still refuses a missing home before it reaches here."""
    home = delivery_settings_home()
    cands = [home / ".secrets" / "ssh" / "unimatrix-zero", home / "group-em" / ".secrets" / "ssh" / "unimatrix-zero"]
    key = str(next((c for c in cands if c.is_file()), cands[0]))
    refuse_real("key_path", key)
    return key


_TEST_HOME = []


def refuse_real(kind, value):
    """Raise unimatrix_test_home.TestHomeRefusal when a test settings home would reach a real `kind`
    (key_path, far_box, run_key); a no-op outside the test-home marker or without the guard module."""
    if not os.environ.get("UNIMATRIX_TEST_HOME"):
        return
    if not _TEST_HOME:
        path = HERE / "lib" / "unimatrix_test_home.py"
        if not path.is_file():
            return
        spec = importlib.util.spec_from_file_location("unimatrix_test_home", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _TEST_HOME.append(mod)
    _TEST_HOME[0].refuse_real(kind, value)


def _is_win(platform=None):
    return (platform or sys.platform) == "win32"


def no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


_PYTHON_INTERP = []


def console_python():
    """A real console CPython for a child argv (never a forwarder or pythonw exe); OSError when none resolves."""
    if not _PYTHON_INTERP:
        spec = importlib.util.spec_from_file_location("unimatrix_roster_python_interp", HERE / "lib" / "python_interp.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _PYTHON_INTERP.append(mod)
    found = _PYTHON_INTERP[0].resolve_console_python()
    if not found:
        raise FileNotFoundError("no console Python interpreter resolvable")
    return found


def spawn(cmd, stderr=None):
    """Start a child that can be tree-killed later: its own process group off Windows."""
    if sys.platform == "win32":
        return subprocess.Popen(cmd, stderr=stderr, creationflags=no_window())
    return subprocess.Popen(cmd, stderr=stderr, start_new_session=True)


TASKKILL_ARGV_BUDGET = 8000


def argv_chunks(items, budget=TASKKILL_ARGV_BUDGET):
    """Split string `items` into lists whose joined length stays under `budget` characters."""
    chunk, size = [], 0
    for item in items:
        if chunk and size + len(item) + 1 > budget:
            yield chunk
            chunk, size = [], 0
        chunk.append(item)
        size += len(item) + 1
    if chunk:
        yield chunk


def tree_kill_many(pids):
    """Stop every pid and its descendants: one taskkill /T per argv chunk on Windows, process groups elsewhere."""
    pids = list(pids)
    if not pids:
        return
    if sys.platform == "win32":
        for chunk in argv_chunks(str(p) for p in pids):
            subprocess.run(["taskkill", "/T", "/F", *[a for p in chunk for a in ("/PID", p)]],
                           capture_output=True, creationflags=no_window())
        return
    live = {}
    for pid in pids:
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            continue
        # A pid that shares our own group would take this process down with it.
        if pgid == os.getpgrp():
            _signal_pid(pid, signal.SIGKILL)
            continue
        live[pid] = pgid
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in list(live):
            try:
                os.killpg(live[pid], sig)
            except (ProcessLookupError, PermissionError):
                # Darwin answers EPERM, not ESRCH, once only zombies remain in the group; these are our own children.
                del live[pid]
        if not live:
            return
        time.sleep(0.2)


def tree_kill(pid):
    tree_kill_many([pid])


def _signal_pid(pid, sig):
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass


def _core_module(subname):
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    if "_unimatrix" not in sys.modules and os.path.isdir(os.path.join(bin_dir, "_unimatrix")):
        if bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
    import importlib
    return importlib.import_module(f"_unimatrix.{subname}")


def pid_alive(pid):
    return _core_module("proc").pid_alive(pid)


def _liveness():
    return _core_module("proc")


_CODEX_HOOK = []


def _codex_hook():
    if not _CODEX_HOOK:
        spec = importlib.util.spec_from_file_location(
            "unimatrix_codex_hook_sessionstart", HERE / "unimatrix-codex-hook-sessionstart.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _CODEX_HOOK.append(mod)
    return _CODEX_HOOK[0]


def entry_live(d):
    """The entry's pid is alive and, when it records a procStart, is still that process."""
    return _liveness().entry_live(d)


def mirror_orphaned(d):
    """True for a roster-made mirror (it carries the far-socket field) whose recorded roster
    supervisor is not live; an entry that records no supervisor counts as orphaned."""
    if not isinstance(d, dict) or not d.get(FAR_SOCKET_FIELD):
        return False
    return not _liveness().supervisor_live(
        {"pid": d.get("unimatrixRosterPid"), "procStart": d.get("unimatrixRosterProcStart")})


FAR_SEEN_FIELD = "unimatrixFarSeen"
FAR_SEEN_MAX_AGE_SECONDS = 5 * POLL_SECONDS
AGY_FACE_GRACE_SECONDS = 5 * POLL_SECONDS


def mirror_unbacked(d):
    """True for a bridge-relay mirror whose far row the roster supervisor has not confirmed lately.

    The bridge process alone proves nothing about the far session: each poll that still sees the far
    row stamps `unimatrixFarSeen`, and a mirror without a fresh stamp has no session behind it. A
    hand-started relay row (it names its far box in `unimatrixRemote` but has no far-socket field) is
    held to the same stamp: only a roster poll can vouch for the session behind it."""
    if not isinstance(d, dict) or not (d.get(FAR_SOCKET_FIELD) or d.get("unimatrixRemote")):
        return False
    return not _liveness().stamp_fresh(d, FAR_SEEN_FIELD, FAR_SEEN_MAX_AGE_SECONDS)


def entry_listed(d):
    """A session entry worth listing: its pid is still its process, no dead roster owns it and,
    for a mirror, its far session was seen on a recent poll and, for an agy router face, its agy
    process is still alive. `unimatrixStale` is a log marker only: a router face is written once and
    never rewritten, so a flag set while its holder was briefly unproven would otherwise hide a live
    session from every remote box for good."""
    return (entry_live(d) and not mirror_orphaned(d) and not mirror_unbacked(d)
            and not local_agy_face_unbacked(d) and not _liveness().codex_face_unbacked(d))


def local_agy_face_unbacked(d) -> bool:
    """True for an agy router face on this box whose agy process is gone. A far mirror copies the far
    face's vendor and router pid but has no peers.json row here, so it is never this box's face: its
    far session's liveness is `mirror_unbacked`'s question."""
    if isinstance(d, dict) and (d.get(FAR_SOCKET_FIELD) or d.get("unimatrixMirror")):
        return False
    return _liveness().agy_face_unbacked(d)


def far_codex_unbacked(entry):
    """True for a far Codex peer row whose box reported no live holder (`codexHolder`, stamped by
    `session_identity` on the far box), or reported none, once it is past the face grace."""
    return _liveness().far_codex_row_unbacked(entry)


def transport_row(d):
    """True for a Unimatrix transport face: infrastructure, never a peer."""
    return isinstance(d, dict) and (d.get("vendor") == "transport" or bool(d.get("unimatrixTransport")))


def far_duplicate(d, rows):
    """True when a lower alias of this mirror's box lists the same far session among `rows`."""
    remote, sock = d.get("unimatrixRemote"), d.get(FAR_SOCKET_FIELD)
    if not remote or not sock:
        return False
    scan = [(None, mirror_scan_key(r.get("unimatrixRemote"), r.get(FAR_SOCKET_FIELD)))
            for r in rows if r is not d and isinstance(r, dict) and entry_listed(r)]
    return alias_duplicate(remote, sock, scan)


def mirror_ghost(d, rows):
    """True for a mirror the listing never shows: a transport face (bar a reply inbox, which must stay
    mirrored), a far Codex row without a live holder, or the higher alias of one far session mirrored
    under two aliases of one box."""
    return bool(d.get(FAR_SOCKET_FIELD) or d.get("unimatrixRemote")) and (
        (transport_row(d) and not d.get("unimatrixReplyInbox")) or far_codex_unbacked(d) or far_duplicate(d, rows))


_SUPERSEDED_TTL_SECONDS = 1.0
_SUPERSEDED = None


def codex_superseded_faces(rows) -> dict:
    """{id(face): surviving face} over `rows`, computed once per listing and memoized on the rows' shape.

    The memo expires after `_SUPERSEDED_TTL_SECONDS`: holder liveness changes without the rows changing, so a
    caller reusing one rows list must not read a stale survivor map."""
    global _SUPERSEDED
    sig = tuple((id(r), r.get("startedAt"), r.get("pid"), r.get("target")) for r in rows if isinstance(r, dict))
    memo = _SUPERSEDED
    now = time.monotonic()
    if memo is None or memo[0] != sig or memo[1] is not rows or now - memo[3] > _SUPERSEDED_TTL_SECONDS:
        memo = (sig, rows, _liveness().codex_superseded_faces([r for r in rows if isinstance(r, dict)]), now)
        _SUPERSEDED = memo
    return memo[2]


def codex_superseded(d, rows) -> bool:
    """True for a local Codex face another face of the same holder (pid+start, else thread) outranks."""
    return isinstance(d, dict) and d.get("vendor") == "codex" and id(d) in codex_superseded_faces(rows)


def listed_row(d, rows=()) -> bool:
    """The one listing predicate: a live peer shown once. `rows` is every session entry the listing covers."""
    return (entry_listed(d) and not transport_row(d) and not mirror_ghost(d, rows)
            and not codex_superseded(d, rows))


def far_seen_fields():
    return {FAR_SEEN_FIELD: int(time.time() * 1000)}


def supervisor_fields():
    """Registry fields naming this process as the roster supervisor of the mirrors it writes."""
    pid = os.getpid()
    return {"unimatrixRosterPid": pid, "unimatrixRosterProcStart": proc_start(pid)}


def _contract():
    """The peer contract module (box_id, BOX_FIELD), loaded via _unimatrix.protocol."""
    return _core_module("protocol")


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


def linux_pid_domain(read=None):
    """The Linux harness's pidDomain: `linux:<machine-id>:<pid namespace link>` (e.g. `linux:ab12..:pid:[4026531836]`).

    `read` is (path) -> text, for tests. Falls back to the bare `linux` label when either part is unreadable."""
    def default(path):
        if path.startswith("/proc/"):
            return os.readlink(path)
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    read = read or default
    try:
        return f"linux:{read('/etc/machine-id').strip()}:{read('/proc/self/ns/pid').strip()}"
    except OSError:
        return "linux"


def pid_domain(platform=None):
    plat = platform or sys.platform
    if plat == "win32":
        return f"win32:{socket.gethostname().lower()}"
    if plat == "darwin":
        return "darwin"
    return linux_pid_domain() if platform is None else "linux"


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


def local_peer_key(raw, process_start, domain, platform=None):
    """Build a native key for the local process, preserving only a valid peer token."""
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        parsed = raw
    token = parsed.get("peerToken") if isinstance(parsed, dict) else parsed
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
        token = secrets.token_hex(16)
    field = "procStartFt" if (platform or sys.platform) == "win32" else "procStart"
    return {"peerToken": token, field: process_start, "pidDomain": domain}


def write_peer_key(path, data):
    """Replace credentials atomically, with 0600 permissions from creation on POSIX."""
    tmp = f"{path}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, separators=(",", ":"))
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def refresh_mirror_key(entry, fallback_raw):
    """Repair legacy or far-process key envelopes without rotating a valid local token."""
    if not isinstance(entry.get("procStart"), str) or not isinstance(entry.get("pidDomain"), str):
        return
    path = os.path.join(sessions_dir(), key_name(entry["pid"], entry["messagingSocketPath"]))
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raw = fallback_raw
    normalized = local_peer_key(raw, entry["procStart"], entry["pidDomain"])
    try:
        current = json.loads(raw)
    except (ValueError, TypeError):
        current = None
    if current != normalized:
        write_peer_key(path, normalized)


def recipient_token(endpoint, directory=None):
    """Read a live destination's peer key internally; credentials never cross argv or logs."""
    directory = Path(directory or sessions_dir())
    wanted = endpoint.lower() if sys.platform == "win32" else endpoint
    for path in directory.glob("*.json"):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(entry, dict):
            continue
        address, pid = entry.get("messagingSocketPath"), entry.get("pid")
        if not isinstance(address, str) or not isinstance(pid, int):
            continue
        actual = address.lower() if sys.platform == "win32" else address
        if actual != wanted or not pid_alive(pid):
            continue
        key = directory / key_name(pid, address)
        try:
            raw = key.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            if sys.platform == "win32":
                raise
            return None  # Unix receivers also support unauthenticated legacy sessions
        try:
            parsed = json.loads(raw)
        except ValueError:
            token = raw  # legacy peers wrote the token without a JSON envelope
        else:
            token = parsed.get("peerToken") if isinstance(parsed, dict) else None
        if not isinstance(token, str) or not token:
            raise ValueError("recipient key has no peerToken")
        return token
    return None



def authenticated_data(endpoint, data, directory=None):
    """Authenticate for the local recipient, replacing a far endpoint's stale auth header."""
    token = recipient_token(endpoint, directory)
    if not token:
        return data
    lines = data.splitlines(keepends=True)
    while lines:
        try:
            first = json.loads(lines[0])
        except ValueError:
            break
        if not isinstance(first, dict) or first.get("type") != "auth":
            break
        lines.pop(0)
    header = (json.dumps({"type": "auth", "token": token}) + "\n").encode("utf-8")
    return header + b"".join(lines)


def bridge_cmd(endpoint, log, remote, key, return_port=None, inbox=None, tunnel_remote=None, supervisor=None):
    """Bridge argv; `supervisor` is the roster pid the bridge exits with (its start stamp is read from the mirror entry)."""
    cmd = [console_python(), str(HERE / "unimatrix-bridge.py"), endpoint, "relay", log]
    if return_port is not None and inbox:
        cmd += [str(return_port), inbox]
    cmd += ["--remote", remote, "--key", key]
    if tunnel_remote:
        cmd += ["--tunnel-remote", tunnel_remote]
    if supervisor is not None:
        cmd += ["--supervisor", str(supervisor)]
    return cmd


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


_ENDPOINTS = {}


def ssh_endpoint(alias):
    """(host, port) that ssh dials for `alias`, read from `ssh -G` once per process; None when it prints neither.

    A failed connect drops the entry (`_dial`), so the next call re-resolves."""
    if alias in _ENDPOINTS:
        return _ENDPOINTS[alias]
    fields = ssh_fields(alias)
    if not fields.get("hostname"):
        return None
    _ENDPOINTS[alias] = (fields["hostname"], int(fields.get("port") or 22))
    return _ENDPOINTS[alias]


def _dial(alias, resolve, connect):
    """(ok, reason): one TCP connect to `alias`'s ssh endpoint; after a failure the endpoint is re-resolved
    once and dialled again only if it moved."""
    tried, reason = None, f"{alias}: no ssh endpoint"
    for _ in range(2):
        try:
            ep = resolve(alias)
            if ep is None or ep == tried:
                break
            tried = ep
            connect(ep, timeout=PROBE_SECONDS).close()
            return True, ""
        except (OSError, ValueError, subprocess.SubprocessError) as ex:
            where = f" {tried[0]}:{tried[1]}" if tried else ""
            reason = f"{alias}{where}: {type(ex).__name__}: {ex}"
            _ENDPOINTS.pop(alias, None)
    return False, reason


def lan_reachable(alias, resolve=None, connect=None):
    """True when a TCP connection to the alias's ssh endpoint opens within PROBE_SECONDS."""
    return _dial(alias, resolve or ssh_endpoint, connect or socket.create_connection)[0]


def link_probe(remote, tunnel_remote=None, resolve=None, connect=None):
    """(ok, reason): the link is up when the LAN alias or, failing that, the tunnel alias accepts a TCP
    connect within PROBE_SECONDS. Spawns nothing while the cached endpoint answers; independent of the roster."""
    reasons = []
    for alias in dict.fromkeys(a for a in (remote, tunnel_remote) if a):
        ok, why = _dial(alias, resolve or ssh_endpoint, connect or socket.create_connection)
        if ok:
            return True, ""
        reasons.append(why)
    return False, "; ".join(reasons)


def alias_identity(alias, read_fields):
    """The alias's own `ssh -G` IdentityFile when it exists on disk and is not a stock id_* key, else None:
    the relay key a per-box alias pins (the shared default key is refused by such a box)."""
    try:
        path = Path(os.path.expanduser(read_fields(alias).get("identityfile", "")))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return str(path) if path.name and not path.name.startswith("id_") and path.is_file() else None


def stable_remote(alias, reachable=None, fields=None, connect=None, read_key=None, verify=None, tcp=None, key=None) -> str | None:
    """First stable name of this far box that answers now, else None: `<box>-lan` alias, then the
    first host-key-verified address in the box's machine-local far-address list, then `<box>.local`.

    For when the alias's own pinned HostName has gone stale. Costs one `ssh -G` (on the `-lan`
    alias, shared by all legs) plus a TCP wait per leg, so call it only after the alias itself
    failed. At most FAR_ADDRESSES_TRIED listed addresses are tried within FAR_ADDRESS_BUDGET_SECONDS in all
    (the verify ssh timeout shrinks to the time left). Listed addresses and `.local` are dialled on the default port as `<user>@<name>`, the only
    shape a single ssh host token can carry; the user is the alias's own, else the one ssh resolves.
    An address that answers returns `user@<address>`; the caller keeps the box id for HostKeyAlias."""
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
            if up and lan_verified(lan, verify=verify, read_key=read_key, key=key):
                return lan
        f = get_fields()
        port = int(f.get("port") or 22)
        name = f"{host}.local"
        if port != 22:
            return None
        who = user or f.get("user")
        mux = _box_mux()
        far = mux._far_addresses()
        box = mux.box_of(host)
        addresses = far.box_addresses(box, read_key or mux.machine_local_value)
        if addresses:
            deadline = time.monotonic() + FAR_ADDRESS_BUDGET_SECONDS
            dial = tcp or far.tcp_connect
            vkey = key or alias_identity(alias, fields or ssh_fields) or default_key()

            def within(address):
                return time.monotonic() < deadline and dial(address)

            def bounded(target):
                left = max(1, int(deadline - time.monotonic()))
                return far.make_verify(box, vkey, timeout=left)(target)

            address, _skipped = far.first_answering(
                box, who, addresses[:FAR_ADDRESSES_TRIED], connect=within, verify=verify or bounded)
            if address:
                return far.target_for(who, address)
        (connect or socket.create_connection)((name, port), timeout=PROBE_SECONDS).close()
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return f"{who}@{name}" if who else name


_LAN_VERIFIED = {}
LAN_VERIFIED_TTL_SECONDS = 60


def lan_verified(alias, verify=None, read_key=None, key=None) -> bool:
    """True when the box behind LAN `alias` proved its identity, so a TCP connect alone never selects the LAN route.

    `verify(alias) -> (status, detail)` decides when injected. Otherwise a box with a pinned host key
    (`unimatrix.hostkey.<box>`) must pass one strict `roster` ssh probe, remembered LAN_VERIFIED_TTL_SECONDS;
    a box with no pinned identity has nothing to verify against and stays on the TCP prefilter (the
    unmodified `test_unimatrix_mirror_roster.py` LAN cases require it)."""
    far = _box_mux()._far_addresses()
    box = _box_mux().box_of(alias)
    if verify is None:
        try:
            pinned = far.pinned_hostkey(box, read_key or _box_mux().machine_local_value)
        except Exception:  # unreadable machine-local config: nothing pinned to check against
            return True
        if not pinned:
            return True
        seen = _LAN_VERIFIED.get(alias)
        if seen is not None and time.monotonic() - seen < LAN_VERIFIED_TTL_SECONDS:
            return True
        try:
            key = key or default_key()
        except MissingSettingsError:
            key = None
        verify = far.make_verify(box, key)
    ok = verify(alias)[0] == far.OK
    if ok:
        _LAN_VERIFIED[alias] = time.monotonic()
    else:
        _LAN_VERIFIED.pop(alias, None)
    return ok


def pick_remote(lan, tunnel=None, reachable=None, verify=None, key=None) -> str:
    """The far box's ssh alias to use now: the LAN alias when it answers and proves the box's identity, else the tunnel alias.

    With no tunnel alias configured the LAN alias is returned unprobed, so nothing here
    ever requires the tunnel to exist or be up. A LAN alias whose host key fails verification is never
    chosen; the tunnel alias is the independently authenticated fallback.
    """
    if not tunnel or tunnel == lan:
        return lan
    if not (reachable or lan_reachable)(lan):
        return tunnel
    return lan if lan_verified(lan, verify=verify, key=key) else tunnel


def stamp_supervisor(remote, role=None) -> None:
    """Write this process's `supervisor-<pid>.json` stamp, the autolink reaper's evidence of a live supervisor.

    Self-written so a supervisor started outside autolink (install, by hand) is still reapable when no
    record names it. `role` ("bridge" or "inbox") is recorded when given, so a stamp-only supervisor can
    be addressed by request_stop. A stamp that cannot be written never stops the supervisor."""
    pid = os.getpid()
    try:
        stamp = {"pid": pid, "procStart": proc_start(pid), "remote": remote}
        if role:
            stamp["role"] = role
        write_json_atomic(str(delivery_settings_home() / "unimatrix" / f"supervisor-{pid}.json"), stamp)
    except (OSError, subprocess.SubprocessError):
        pass


def stop_request_path(pid) -> Path:
    return delivery_settings_home() / "unimatrix" / f"stop-{pid}.json"


def request_stop(pid, proc_start_value, role, remote) -> None:
    """Ask the supervisor identified by (pid, procStart) to exit on its own; the request is inert to any other process."""
    path = stop_request_path(pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(str(path), {"pid": pid, "procStart": proc_start_value, "role": role, "remote": remote,
                                  "requestedAt": time.time()})


def stop_requested(own_proc_start) -> bool:
    """True only when stop-<own pid>.json exists and names `own_proc_start`.

    The caller reads its own procStart once at startup: reading it here could spawn `ps` per poll slice."""
    try:
        with open(stop_request_path(os.getpid()), encoding="utf-8") as fh:
            return json.load(fh).get("procStart") == own_proc_start
    except (OSError, ValueError, AttributeError):
        return False


def clear_stop(pid) -> None:
    """Remove `pid`'s stop request and supervisor stamp; absent files are fine."""
    for path in (stop_request_path(pid), delivery_settings_home() / "unimatrix" / f"supervisor-{pid}.json"):
        try:
            os.remove(path)
        except OSError:
            pass


def wait_or_stop(seconds, own_proc_start, sleep=None) -> bool:
    """Sleep `seconds` in STOP_POLL_SECONDS slices; True as soon as a stop is requested for this process."""
    sleep = sleep or time.sleep
    for _ in range(max(1, round(seconds / STOP_POLL_SECONDS))):
        if stop_requested(own_proc_start):
            return True
        sleep(STOP_POLL_SECONDS)
    return stop_requested(own_proc_start)


def write_json_atomic(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.replace(tmp, path)


def parse_args(argv) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="unimatrix-roster.py")
    p.add_argument("log")
    p.add_argument("skip", nargs="*", help="far socket paths whose bridges are run by hand")
    p.add_argument("--remote", required=True, help="ssh alias of the far box on the LAN (tried first)")
    p.add_argument("--tunnel-remote", default=None, help=f"ssh alias over the tunnel, used only when --remote does not answer (default: ${TUNNEL_ENV})")
    p.add_argument("--key", default=None)
    a = p.parse_args(argv)
    a.key_defaulted = not a.key
    if not a.key:
        settings_home()  # the ordinary roster CLI refuses a missing home before any side effect; default_key() itself defaults
        a.key = default_key()
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


def stable_label(remote):
    """`box_label` without a trailing mDNS `.local`, the label a mirror name carries.

    Trap: the ssh alias differs by supervisor generation (`Mac-mini.local`, then `Mac-mini`); a name built
    from the raw alias changes on every box restart and breaks each cached address."""
    label = box_label(remote)
    return label[:-len(".local")] if label.lower().endswith(".local") and len(label) > len(".local") else label


def box_key(remote):
    """Identity of the box behind an ssh alias: `box_label` lower-cased, cut at its first dot and
    stripped of a trailing `-lan`, so `machine-b`, `Machine-b.local` and `machine-b-lan` are one box
    (the same normalisation as the peer contract's `box_id`). An address (IPv4, or IPv6 with colons) stays whole."""
    host = box_label(remote).lower()
    if ":" in host or re.fullmatch(r"\d+(?:\.\d+){3}", host):
        return host
    label = host.partition(LABEL_SEP)[0] or host
    return label[:-4] if label.endswith("-lan") and len(label) > 4 else label


def alias_duplicate(remote, far_sock, scan):
    """True when another alias of this box already holds a live mirror of `far_sock`; the lowest alias
    keeps it, so two roster supervisors for one box never list the one far session twice."""
    want = box_key(remote)
    for key in {s for _, s in scan if isinstance(s, str) and "\0" in s}:
        other, _, sock = key.partition("\0")
        if sock == far_sock and other != remote and box_key(other) == want and other < remote:
            return True
    return False


def labelled(name, remote):
    """The name, a dot, then the box, for a mirror's session name; idempotent, so a re-mirror never stacks labels."""
    if not isinstance(name, str) or not name:
        return name
    return f"{bare_name(name)}{LABEL_SEP}{stable_label(remote)}"


def mirror_scan_key(remote, far_sock):
    """A remote socket belongs to one box; legacy entries without a box retain their old key."""
    return f"{remote}\0{far_sock}" if remote and far_sock else far_sock


def same_scan_target(left, right):
    """Compare box-qualified targets while still recognizing old unqualified self entries."""
    if left == right:
        return True
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    if "\0" in left and "\0" not in right:
        return left.partition("\0")[2] == right
    if "\0" in right and "\0" not in left:
        return right.partition("\0")[2] == left
    return False


def live_sessions():
    """(bare name, box-qualified far socket or None) for every live local or mirrored session."""
    rows = session_entries()
    return [(bare_name(d["name"]), mirror_scan_key(d.get("unimatrixRemote"), d.get(FAR_SOCKET_FIELD)))
            for d in rows if isinstance(d.get("name"), str) and listed_row(d, rows)]


def session_entries():
    """Every readable session entry on this box: the scan set `listed_row` collapses duplicates over."""
    sess = sessions_dir()
    try:
        files = os.listdir(sess)
    except OSError:
        return []
    rows = []
    for f in files:
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(sess, f), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(d, dict):
            rows.append(d)
    return rows


def live_bare_names(except_far_sock=None, scan=None):
    """Bare names of the live sessions; `scan` is a `live_sessions()` result reused across one sync pass.

    An entry mirroring `except_far_sock` is left out: it is the earlier mirror of the session being
    named, not a competitor for its name."""
    if scan is None:
        scan = live_sessions()
    return {n for n, sock in scan if not (except_far_sock and same_scan_target(sock, except_far_sock))}


def mirror_name(name, remote, far_sock=None, scan=None):
    """The mirror's name before listing: the bare name, or the box-labelled form when a live session
    already holds that bare name. Its sole caller, mirror_entry_name, labels the result (or uses the
    `-on-<box>` alias), so the bare form never reaches a listing.

    A far name with a dot that is not this box's label is dotted-to-hyphen first: the dot is the
    label separator, so a raw dotted name would be cut at its first dot and collide."""
    if not isinstance(name, str) or not name:
        return name
    if LABEL_SEP in name and not name.endswith((LABEL_SEP + box_label(remote), LABEL_SEP + stable_label(remote))):
        name = name.replace(LABEL_SEP, "-")
    bare = bare_name(name)
    if scan is None:
        scan = live_sessions()
    want = box_key(remote)
    # A same-named entry on this box is the face's own earlier entry (another alias, or a pre-restart socket).
    rivals = [(n, s) for n, s in scan
              if not (n == bare and isinstance(s, str) and "\0" in s and box_key(s.partition("\0")[0]) == want)]
    if bare in live_bare_names(far_sock, rivals):
        return labelled(name, remote)
    return bare_name(name)


def inbound_names():
    """Names a far box already reaches us by: live local entries its own relay holds (`unimatrixMirror`).

    The far box's inbox relay already gives such a session a local socket, so mirroring it again
    from here would list the one far session twice under one name. An inbox mirror with no peer key
    is not listable by the harness, so it never stands in for the far roster row."""
    rows = session_entries()
    sess = sessions_dir()
    return {bare_name(d.get("name")) for d in rows
            if d.get("unimatrixMirror") and listed_row(d, rows) and _has_peer_key(sess, d)}


def _has_peer_key(sess, d) -> bool:
    """False only when entry `d` names a socket and has no `.key` file beside it in `sess`."""
    pid, path = d.get("pid"), d.get("messagingSocketPath")
    if not isinstance(pid, int) or not isinstance(path, str):
        return True
    return os.path.exists(os.path.join(sess, key_name(pid, path)))


def pushed_from(d, remote):
    """True when pushed mirror entry `d` was registered by `remote`'s own client: its box stamp, else its `<bare>.<box>` label."""
    box = d.get(_contract().BOX_FIELD)
    if box:
        return box == _contract().box_id(remote)
    return any(str(d.get("name") or "").endswith(LABEL_SEP + re.sub(r"[^A-Za-z0-9_-]+", "-", lab).strip("-"))
               for lab in {box_label(remote), stable_label(remote)})


def superseded_inbound(far_rows, remote):
    """(entry path, entry) of each pushed mirror from `remote` whose far session has been replaced under its name.

    Superseded means the far roster lists the entry's bare name only under other session ids; an entry
    without a session id, or whose session the roster still lists, is current."""
    live = {}
    for r in far_rows:
        e = r["entry"]
        sid = e.get("sessionId")
        if isinstance(sid, str) and sid and isinstance(e.get("name"), str):
            live.setdefault(bare_name(e["name"]), set()).add(sid)
    stale = []
    if not live:
        return stale
    sess = sessions_dir()
    try:
        files = os.listdir(sess)
    except OSError:
        return stale
    for f in files:
        path = os.path.join(sess, f)
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if not (f.endswith(".json") and isinstance(d, dict) and d.get("unimatrixMirror")) or d.get(FAR_SOCKET_FIELD):
            continue
        sid, sids = d.get("sessionId"), live.get(bare_name(d.get("unimatrixMirrorName") or d.get("name")))
        if sids and isinstance(sid, str) and sid and sid not in sids and pushed_from(d, remote):
            stale.append((path, d))
    return stale


def prune_superseded_inbound(far_rows, remote, say):
    """Drop the registry entry and key of each superseded pushed mirror, so its name stops shadowing the live far row."""
    for path, d in superseded_inbound(far_rows, remote):
        keys = [os.path.join(os.path.dirname(path), key_name(d["pid"], d["messagingSocketPath"]))] \
            if isinstance(d.get("pid"), int) and isinstance(d.get("messagingSocketPath"), str) else []
        for p in [path, *keys]:
            try:
                os.remove(p)
            except OSError:
                pass
        say(f"unlist pushed mirror {d.get('name')} session {d.get('sessionId')}: the far box lists another session under that name")


def far_rows(fetched, remote, skip, say, keep=()):
    """The far rows worth mirroring after the superseded pushed mirrors of this box are dropped."""
    prune_superseded_inbound(fetched, remote, say)
    return mirrorable(fetched, skip, inbound_names(), keep)


def mirrorable(rows, skip, inbound, keep=()):
    """far socket -> row for the far rows worth mirroring: true far sessions only.

    A far relay older than its re-export filter still lists its own mirrors of our sessions
    (`unimatrixMirror`, or the far-socket field); mirroring those back loops every name into a
    duplicate. `inbound` is `inbound_names()`, computed once per poll by the caller.

    Trap: `inbound` only stops a NEW mirror. A far socket in `keep` (the caller's live bridges) stays in
    the result though a relay-pushed mirror now holds its name: `sync` unmirrors a bridge whose row is
    missing, so dropping it here killed the bridge of a session the far roster still lists."""
    return {r["entry"]["messagingSocketPath"]: r for r in rows
            if r["entry"]["messagingSocketPath"] not in skip
            and not (r["entry"].get("unimatrixMirror") or r["entry"].get(FAR_SOCKET_FIELD))
            and not far_codex_unbacked(r["entry"])
            and (bare_name(r["entry"].get("name")) not in inbound
                 or r["entry"]["messagingSocketPath"] in keep)}


_AGENT_OK = {}
AGENT_RECHECK_SECONDS = 60


def ensure_key_loaded(key, now=None):
    """OSError naming the wait when the encrypted `key` cannot be loaded into the agent; a loaded or
    unencrypted verdict is cached so a poll loop does not respawn ssh-add -l."""
    clock = time.time() if now is None else now
    if clock - _AGENT_OK.get(key, -AGENT_RECHECK_SECONDS) < AGENT_RECHECK_SECONDS:
        return
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location("unimatrix_passphrase_roster", HERE / "unimatrix-passphrase.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        verdict = mod.ensure_agent(key)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return
    if verdict == "locked":
        raise OSError("waiting: 1Password locked")
    if verdict == "missing":
        raise OSError("passphrase_source_missing: op CLI or unimatrix.passphrase_vault unavailable")
    _AGENT_OK[key] = clock


CONTROL_PERSIST_SECONDS = 4 * POLL_SECONDS
# Windows OpenSSH has no ControlMaster: the poll dials at most once per this many seconds per far box.
WINDOWS_DIAL_MIN_SECONDS = 2 * POLL_SECONDS
_DIALS = {}


def _now():
    return time.monotonic()


def control_path(remote, home=None, key=None) -> Path:
    """Mux socket path for far `remote` and identity `key`, under <settings home>/unimatrix/ctl; short, since
    unix socket paths cap near 104 bytes.

    Trap: ssh ignores `-i` when a master already exists at ControlPath, so a path shared across keys sends
    every caller through the first caller's key, and the far authorized_keys line for that key picks the
    command (a roster key answered `send-session` with a roster dump)."""
    tag = hashlib.sha1(f"{remote}\0{key or ''}".encode("utf-8")).hexdigest()[:10]
    return (Path(home) if home else delivery_settings_home()) / "unimatrix" / "ctl" / f"r-{tag}"


def mux_options(remote, key=None):
    """ssh options that reuse one master connection across poll ticks; empty off POSIX or when the socket dir cannot be made."""
    if _is_win():
        return []
    path = control_path(remote, key=key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        return []
    return ["-o", "ControlMaster=auto", "-o", f"ControlPath={path}", "-o", f"ControlPersist={CONTROL_PERSIST_SECONDS}"]


def _box_mux():
    mod = sys.modules.get("unimatrix_box_mux")
    if mod is None:
        spec = importlib.util.spec_from_file_location("unimatrix_box_mux", HERE / "lib" / "unimatrix_box_mux.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["unimatrix_box_mux"] = mod
        spec.loader.exec_module(mod)
    return mod


def _roster_once(remote, key, tunnel_remote) -> list:
    ensure_key_loaded(key)
    remote = pick_remote(remote, tunnel_remote, key=key)
    # Direct: the poll keeps its own Windows redial cap (`_capped_fetch`); POSIX shares the box's ControlMaster.
    r = _box_mux().for_remote(remote, key=key, direct=True, mux_options=lambda h: mux_options(h, key),
                              extra=["-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=5",
                                     "-o", "ServerAliveCountMax=2"]).run("roster", timeout=20)
    if r.returncode:
        err = r.stderr.decode("utf-8", "replace").strip().splitlines()
        raise OSError(f"roster rc={r.returncode}" + (f": {err[-1][:200]}" if err else ""))
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


RESET_TRIES = 3
RESET_BACKOFF_SECONDS = (1.0, 3.0)
_RESET_MARKERS = ("rc=255", "connection reset", "kex_exchange_identification")


def _is_reset(ex):
    text = str(ex).lower()
    return isinstance(ex, OSError) and any(m in text for m in _RESET_MARKERS) and "timed out" not in text


def _roster_with_reset_retry(remote, key, tunnel_remote):
    """`_roster_once`, retried on a connection reset (sshd MaxStartups drop) with jittered backoff, RESET_TRIES
    tries in ~20s at most; any other failure raises at once."""
    for attempt in range(RESET_TRIES):
        try:
            return _roster_once(remote, key, tunnel_remote)
        except OSError as ex:
            if not _is_reset(ex) or attempt == RESET_TRIES - 1:
                raise
            time.sleep(RESET_BACKOFF_SECONDS[attempt] * (1 + secrets.randbelow(100) / 100))


def fetch_roster(remote, key, tunnel_remote=None):
    """The far roster rows. A transient LAN stall (connect timeout, hung session) is retried once
    with the endpoint re-picked, so one dropped SYN is not a LINK-DOWN; a second failure raises.
    Off POSIX there is no mux: a dial inside WINDOWS_DIAL_MIN_SECONDS of the last one replays that
    outcome (rows or error) instead of dialling, and a failure is not retried."""
    if _is_win():
        return _capped_fetch(remote, key, tunnel_remote)
    try:
        return _roster_with_reset_retry(remote, key, tunnel_remote)
    except (OSError, subprocess.TimeoutExpired) as ex:
        if _is_reset(ex):
            raise
        return _roster_once(remote, key, tunnel_remote)


def _capped_fetch(remote, key, tunnel_remote):
    last = _DIALS.get(remote)
    if last and _now() - last[0] < WINDOWS_DIAL_MIN_SECONDS:
        if last[2]:
            raise OSError(last[2])
        return copy.deepcopy(last[1])
    try:
        rows = _roster_with_reset_retry(remote, key, tunnel_remote)
    except (OSError, subprocess.TimeoutExpired) as ex:
        _DIALS[remote] = (_now(), None, str(ex) or type(ex).__name__)
        raise
    _DIALS[remote] = (_now(), rows, "")
    return copy.deepcopy(rows)


def drop_session_files(pid):
    sess = sessions_dir()
    for f in os.listdir(sess):
        if f.startswith(f"{pid}."):
            try:
                os.remove(os.path.join(sess, f))
            except FileNotFoundError:
                pass  # the killed bridge removes its own file on exit


def unmirror(pid):
    tree_kill(pid)
    drop_session_files(pid)


def reap_orphaned_mirrors(remote, say, unbacked=False, keep=(), bridges=None):
    """Remove this far box's mirrors whose roster supervisor is gone, stopping a bridge that is still its process.

    With `unbacked`, a mirror whose far row went unconfirmed (`mirror_unbacked`) or that the listing never
    shows (`mirror_ghost`) is reaped too: the session registry lists a file by its live bridge pid, so an
    unlisted-but-present mirror still shows.
    Pids in `keep` (the caller's own bridges) are never reaped: pass it only after a poll that refreshed
    their stamps. A failed poll passes none, so a link that stays down reaps the mirrors it can no longer vouch for.
    A bridge is killed only when its entry records a procStart it still matches: a recycled pid is never signalled.
    A bridge that outlives the group signal is SIGKILLed, and a `bridges` Popen of a reaped pid is waited on, so no
    survivor or zombie keeps the far session looking held.
    Returns the reaped (pid, name) pairs: the caller owes each far session a prompt re-mirror."""
    try:
        files = os.listdir(sessions_dir())
    except OSError:
        return []
    reaped, to_kill, owners, readable, entries = [], [], [], True, []
    for f in files:
        m = re.fullmatch(r"(\d+)\.json", f)
        if not m:
            continue
        path = os.path.join(sessions_dir(), f)
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            readable = False
            continue
        pid = int(m.group(1))
        if isinstance(d, dict):
            owners.append((path, pid, d))
            entries.append(d)
    for _, pid, d in owners:
        if (d.get("pid") != pid or pid in keep
                or not (mirror_orphaned(d) or (unbacked and (mirror_unbacked(d) or mirror_ghost(d, entries))))
                or stable_label(d.get("unimatrixRemote") or "") != stable_label(remote)):
            continue
        if isinstance(d.get("procStart"), str) and d["procStart"] and entry_live(d):
            to_kill.append(pid)
        reaped.append((pid, d.get("name")))
    tree_kill_many(to_kill)
    for pid in to_kill:
        if not _is_win() and pid_alive(pid):
            _signal_pid(pid, signal.SIGKILL)
    for b in (bridges or {}).values():
        if b.pid in to_kill:
            b.poll()
    for pid, name in reaped:
        drop_session_files(pid)
        say(f"reaped orphaned mirror {name} bridge {pid}")
    gone = {pid for pid, _ in reaped}
    reap_stale_sockets([o for o in owners if o[1] not in gone], keep, readable, say)
    return reaped


SOCKET_GRACE_SECONDS = 2 * POLL_SECONDS
STALE_FIELD = "unimatrixStale"
LOOPBACK_SOCK_RE = re.compile(r"cc-msg-[0-9a-f]{32}\.sock")
PIPE_PREFIX = "\\\\.\\pipe\\"


def liveness_unknown(d):
    """True when the entry records no usable pid, so neither liveness nor death can be shown."""
    pid = d.get("pid")
    return not isinstance(pid, int) or isinstance(pid, bool)


def process_holds(d):
    """True when the entry's own live process still holds its socket; the roster that owns that process
    reaps it, so no other roster's sweep unlinks the socket out from under it."""
    return not d.get(STALE_FIELD) and entry_live(d)


def live_agy_leg_sockets():
    """Basenames of the adapter endpoints named by agy-legs records whose leg or agy process is alive.

    An agy leg's adapter socket is recorded only in `agy-legs/<conversation>.json`, apart from any
    session entry's `messagingSocketPath`, so a sweep keyed on session entries alone reads it as
    ownerless. None when a leg record is unreadable: a possible owner suspends every unlink."""
    try:
        legs = _liveness().state_dir() / "agy-legs"
        names = sorted(legs.glob("*.json")) if legs.is_dir() else []
    except OSError:
        return None
    owned = set()
    for leg in names:
        try:
            rec = json.loads(leg.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            return None
        if not isinstance(rec, dict) or not isinstance(rec.get("endpoint"), str):
            continue
        pids = [p for p in (rec.get("pid"), rec.get("agy_pid")) if isinstance(p, int) and not isinstance(p, bool)]
        if any(p > 0 and pid_alive(p) for p in pids):
            owned.add(os.path.basename(rec["endpoint"]))
    return owned


def mark_stale(path, d, say):
    """Record `unimatrixStale` on the entry at `path` so `entry_listed` drops it; the entry is never deleted."""
    if d.get(STALE_FIELD):
        return
    write_json_atomic(path, {**d, STALE_FIELD: True})
    say(f"marked stale {d.get('name')} ({d.get('messagingSocketPath')})")


def _non_session_held_sockets():
    """Loopback socket paths owned by live non-session processes (agy legs and the peer router)."""
    held = set()
    uni = settings_home() / "unimatrix"
    legs_dir = uni / "agy-legs"
    try:
        for path in legs_dir.glob("*.json"):
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            if (isinstance(rec, dict) and isinstance(rec.get("pid"), int) and pid_alive(rec["pid"])
                    and isinstance(rec.get("endpoint"), str) and rec["endpoint"]):
                held.add(rec["endpoint"])
                held.add(os.path.join(LOOPBACK_SOCKS, os.path.basename(rec["endpoint"])))
    except OSError:
        pass
    try:
        rrec = json.loads((uni / "router" / "router.pid.json").read_text(encoding="utf-8"))
        if isinstance(rrec, dict) and isinstance(rrec.get("pid"), int) and pid_alive(rrec["pid"]):
            held.add(os.path.join(LOOPBACK_SOCKS, os.path.basename(local_endpoint("unimatrix-peer-router"))))
    except (OSError, ValueError, TypeError):
        pass
    return held


def reap_stale_sockets(owners, keep, readable, say):
    """Unlink loopback cc-msg-*.sock files no listed entry owns; mark ownerless win32 pipe entries stale.

    `owners` is (entry path, pid, entry) for every readable session file. A win32 pipe cannot be
    unlinked, so its dead owner's entry is marked stale instead. An owner whose liveness is unknown is
    marked stale and its socket kept. A socket younger than `SOCKET_GRACE_SECONDS` is spared (its entry may
    not be written yet), and an unreadable session file (a possible owner) suspends every unlink."""
    listed = {d.get("messagingSocketPath") for _, pid, d in owners if pid in keep or entry_listed(d)}
    for path, pid, d in owners:
        endpoint = d.get("messagingSocketPath")
        if not isinstance(endpoint, str) or endpoint in listed or d.get(STALE_FIELD):
            continue
        if liveness_unknown(d) or endpoint.startswith(PIPE_PREFIX):
            mark_stale(path, d, say)
    if _is_win() or not readable:
        return
    try:
        socks = os.listdir(LOOPBACK_SOCKS)
    except OSError:
        return
    held = {d.get("messagingSocketPath") for _, _, d in owners if liveness_unknown(d) or process_holds(d)}
    legs = live_agy_leg_sockets()
    if legs is None:
        return
    held |= _non_session_held_sockets()
    for f in socks:
        full = os.path.join(LOOPBACK_SOCKS, f)
        if not LOOPBACK_SOCK_RE.fullmatch(f) or full in listed or full in held or f in legs:
            continue
        try:
            if time.time() - os.stat(full).st_mtime < SOCKET_GRACE_SECONDS:
                continue
            os.unlink(full)
        except OSError:
            continue
        say(f"unlinked stale socket {full}")


def reap_unbacked_agy_faces(say) -> None:
    """Remove the local registry rows of agy router faces whose agy process is gone.

    The registry lists a file by its live face pid, so an unlisted-but-present face still shows in
    ListAgents. A face younger than `AGY_FACE_GRACE_SECONDS` is spared (its leg record may not exist
    yet); the face process is signalled only while it is still the process its entry recorded."""
    try:
        files = os.listdir(sessions_dir())
    except OSError:
        return
    liveness = _liveness()
    reaped, to_kill = [], []
    for f in files:
        m = re.fullmatch(r"(\d+)\.json", f)
        if not m:
            continue
        try:
            with open(os.path.join(sessions_dir(), f), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        pid = int(m.group(1))
        if (not isinstance(d, dict) or d.get("pid") != pid or not local_agy_face_unbacked(d)
                or liveness.stamp_fresh(d, "startedAt", AGY_FACE_GRACE_SECONDS)):
            continue
        if isinstance(d.get("procStart"), str) and d["procStart"] and entry_live(d):
            to_kill.append(pid)
        reaped.append((pid, d.get("name")))
    tree_kill_many(to_kill)
    for pid, name in reaped:
        drop_session_files(pid)
        say(f"reaped unbacked agy face {name} pid {pid}")
    try:
        orphans = liveness.agy_peer_rows_orphaned()
        if orphans:
            hook = _codex_hook()
            dropped = set(hook.drop_peer_rows(delivery_settings_home() / "unimatrix" / "peers.json",
                                              {t for _, t in orphans}))
            for name, target in orphans:
                if name in dropped:
                    say(f"reaped orphaned agy peer row {name} (target {target})")
    except Exception as e:
        say(f"orphaned agy peer row reap failed: {e}")


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


def session_identity(entry, box=None):
    """Add display metadata without changing the address owned by the harness."""
    vendor = entry.get("vendor")
    if vendor not in ("codex", "agy", "grok", "claude", "transport"):
        sid = entry.get("sessionId") or ""
        if isinstance(sid, str) and sid.startswith("peer-codex-"):
            vendor = "codex"
        elif isinstance(sid, str) and sid.startswith("peer-agy-"):
            vendor = "agy"
        elif (isinstance(entry.get("version"), str)
              and re.fullmatch(r"\d+\.\d+\.\d+(?:[-+].*)?", entry["version"])
              and not str(sid).startswith("peer-")):
            vendor = "claude"
        else:
            vendor = "unknown"
    far = entry.get(FAR_SOCKET_FIELD) or entry.get("unimatrixMirror")
    origin = entry.get("box") or box or ("unknown" if far else _contract().local_box())
    out = {"vendor": vendor, "box": str(origin), "cwd": entry.get("cwd") or ""}
    holder = _liveness().codex_face_holder(entry) if box is None and vendor == "codex" else None
    if holder:
        out["codexHolder"] = holder
    return out


def mirror_identity(entry, remote):
    out = session_identity(entry, stable_label(remote))
    if entry.get("pidDomain"):
        out["farPidDomain"] = entry["pidDomain"]
    return out


def remote_mirrors(entries, remote=None):
    """Select one box's mirrors before resolving a socket that other boxes can also use."""
    entries = list(entries)
    if not remote:
        return entries
    want = stable_label(remote)
    matches = [entry for entry in entries
               if stable_label(entry.get("unimatrixRemote") or entry.get(_contract().BOX_FIELD)
                            or entry.get("box") or "") == want]
    if matches:
        return matches
    # Truly legacy records lack both remote fields. Callers still refuse ambiguous results.
    return [entry for entry in entries if not entry.get("unimatrixRemote") and not entry.get("box")]


def mirror_entry_name(entry, remote, far_sock=None, scan=None):
    """A far session's local name: always carrying its box, so no peer listing hides which host it runs on.

    Strict legacy UUID peers get a readable alias already ending `-on-<box>`; every other name takes
    the `labelled()` form."""
    name = entry.get("name")
    legacy = re.fullmatch(r"(codex|agy)-([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", str(name), re.I)
    aliased = bool(legacy) and session_identity(entry)["vendor"] != "claude"
    if aliased:
        vendor, target = legacy.groups()
        cwd = str(entry.get("cwd") or "").replace("\\", "/").rstrip("/")
        repo = re.sub(r"[^A-Za-z0-9_-]+", "-", cwd.rsplit("/", 1)[-1]).strip("-") or "session"
        box = re.sub(r"[^A-Za-z0-9_-]+", "-", str(entry.get("box") or stable_label(remote))).strip("-").lower()
        short = hashlib.sha256(target.lower().encode()).hexdigest()[:10]
        name = f"{vendor.lower()}-{repo}-{short}-on-{box or 'unknown'}"
    name = mirror_name(name, remote, mirror_scan_key(remote, far_sock), scan)
    return name if aliased else labelled(name, remote)


REMOTE_IP_FIELD = "unimatrixRemoteIp"
_remote_ips = {}
REMOTE_IP_TTL_S = 300.0
REMOTE_IP_FAIL_TTL_S = 30.0


def remote_ip(remote):
    """The far box's IP, cached per remote (300s; a failed lookup 30s); '' when it does not resolve.

    The relay matches ssh client addresses against this recorded value and never resolves names itself.
    """
    host = str(remote or "").rpartition("@")[2]
    now = time.monotonic()
    hit = _remote_ips.get(host)
    if hit is not None and now < hit[1]:
        return hit[0]
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        infos.sort(key=lambda i: i[0] != socket.AF_INET)
        ip, ttl = infos[0][4][0], REMOTE_IP_TTL_S
    except (OSError, IndexError, UnicodeError):
        ip, ttl = "", REMOTE_IP_FAIL_TTL_S
    _remote_ips[host] = (ip, now + ttl)
    return ip


BOUND_SINCE = {}  # bridge pid -> spawn time; a bridge unknown here is never judged deaf


def bridge_deaf(pid, endpoint):
    """True when a bridge this process spawned outlived `SOCKET_GRACE_SECONDS` yet its socket file is gone."""
    since = BOUND_SINCE.get(pid)
    return (since is not None and not _is_win() and time.time() - since >= SOCKET_GRACE_SECONDS
            and not os.path.exists(endpoint))


def bridge_unlisted(pid):
    """True when bridge `pid` has no registry entry: the reap dropped it, so the roster must not count it as holding the far session."""
    return not os.path.exists(os.path.join(sessions_dir(), f"{pid}.json"))


def mirror(row, cfg, say, scan=None):
    e = row["entry"]
    far_sock = e["messagingSocketPath"]
    endpoint = local_endpoint(f"{cfg.remote}:{far_sock}")
    if not _is_win():
        os.makedirs(os.path.dirname(endpoint), mode=0o700, exist_ok=True)
    b = spawn(bridge_cmd(endpoint, os.path.join(os.path.dirname(os.path.abspath(cfg.log)),
                                                f"unimatrix-bridge-{log_label(e)}.log"),
                         cfg.remote, cfg.key, tunnel_remote=cfg.tunnel_remote, supervisor=os.getpid()))
    BOUND_SINCE[b.pid] = time.time()
    time.sleep(1)
    d = {k: v for k, v in e.items() if k not in ("pid", "procStart", "pidDomain", "messagingSocketPath")}
    if "name" in d:
        d["name"] = mirror_entry_name(e, cfg.remote, far_sock, scan)
        d["unimatrixFarName"] = e["name"]
    d.update(mirror_identity(e, cfg.remote))
    c = _contract()
    d[c.BOX_FIELD] = d.get(c.BOX_FIELD) or c.box_id(cfg.remote)
    d.pop(REMOTE_IP_FIELD, None)
    ip = remote_ip(cfg.remote)
    if ip:
        d[REMOTE_IP_FIELD] = ip
    d.update(pid=b.pid, procStart=proc_start(b.pid), pidDomain=pid_domain(),
             messagingSocketPath=endpoint, farPid=e["pid"], unimatrixRemote=cfg.remote,
             **{FAR_SOCKET_FIELD: far_sock}, **supervisor_fields(), **far_seen_fields(), **engine_fields(row))
    sess = sessions_dir()
    write_json_atomic(os.path.join(sess, f"{b.pid}.json"), d)
    write_peer_key(os.path.join(sess, key_name(b.pid, endpoint)),
                   local_peer_key("", d["procStart"], d["pidDomain"]))  # a far key is never adopted
    say(f"mirror {e.get('name')} {far_sock} -> bridge {b.pid} {endpoint}")
    return b


FAR_LIVENESS_FIELDS = ("updatedAt", "statusUpdatedAt", "status")  # the far session's activity, never the face's


def far_identity_crossed(d, row, sock):
    """True when mirror record `d`, bridged under far socket `sock`, holds another far session's name or socket than `row` shows.

    The far name a mirror was built for may follow a rename only while the far session id vouches for it
    (both sides carry the same non-empty id); without that, the pipe now answers as a different session."""
    held = d.get(FAR_SOCKET_FIELD)
    if isinstance(held, str) and held and held != sock:
        return True
    far_name, now = d.get("unimatrixFarName"), row["entry"].get("name")
    if not (isinstance(far_name, str) and far_name and isinstance(now, str) and now) or far_name == now:
        return False
    sid = d.get("sessionId")
    return not (isinstance(sid, str) and sid and sid == row["entry"].get("sessionId"))


def rename_live_mirror(pid, sock, row, cfg, say, scan=None):
    """Refresh a live bridge's far identity when its stable remote socket is reused.

    The bridge's local pid/process identity stays its own. The relay destination must
    follow the remote process, which may restart without changing its socket or name.
    Never writes `sessionId`: a changed far session is crossed (`crossed_mirrors`) and rebuilt.
    """
    name = row["entry"].get("name")
    path = os.path.join(sessions_dir(), f"{pid}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return
    if not isinstance(d, dict):
        return
    refresh_mirror_key(d, "")
    updates = {}
    if d.get("unimatrixRemote") != cfg.remote:
        updates["unimatrixRemote"] = cfg.remote
    ip = remote_ip(cfg.remote)
    if ip and d.get(REMOTE_IP_FIELD) != ip:
        updates[REMOTE_IP_FIELD] = ip
    elif not ip and REMOTE_IP_FIELD in d and "unimatrixRemote" in updates:
        d.pop(REMOTE_IP_FIELD)
    for field, value in mirror_identity(row["entry"], cfg.remote).items():
        if field == "cwd" and not value:
            continue
        if d.get(field) != value:
            updates[field] = value
    contract = _contract()
    if not d.get(contract.BOX_FIELD):
        updates[contract.BOX_FIELD] = contract.box_id(cfg.remote)
    for field in FAR_LIVENESS_FIELDS:
        if field in row["entry"] and d.get(field) != row["entry"][field]:
            updates[field] = row["entry"][field]
    far_pid = row["entry"].get("pid")
    if isinstance(far_pid, int) and far_pid > 0 and d.get("farPid") != far_pid:
        updates["farPid"] = far_pid
    for field, value in supervisor_fields().items():
        if d.get(field) != value:
            updates[field] = value
    if not _liveness().stamp_fresh(d, FAR_SEEN_FIELD, POLL_SECONDS):
        updates.update(far_seen_fields())
    if isinstance(name, str) and name and not far_identity_crossed(d, row, sock):
        want = mirror_entry_name(row["entry"], cfg.remote, sock, scan)
        if d.get("unimatrixFarName") != name:
            updates["unimatrixFarName"] = name
        if d.get("name") != want:
            updates["name"] = want
    if updates:
        d.update(updates)
        write_json_atomic(path, d)
        if set(updates) != {FAR_SEEN_FIELD}:
            say(f"refresh mirror {sock} -> {d.get('name')} far pid {d.get('farPid')}")


def crossed_mirrors(bridges, rows):
    """Far sockets whose live mirror can reach the wrong session: (mirror name, far socket) pairs.

    Crossed means the bridge left a `<pid>.misroute` marker (the far end answered as another session),
    the mirror's `farPid` is not its row's pid (checked after the refresh), the mirror's `sessionId`
    differs from (or, for a legacy mirror, is missing against) its row's non-empty one, it holds another
    far session's name or socket than its row (`far_identity_crossed`; the refresh never rebinds those), or another
    live mirror of this remote carries the identical session name for a different far socket. Names
    compare in full: a box-labelled twin of a bare name is the intended disambiguation, not a crossing."""
    seen, by_name, crossed = {}, {}, set()
    for sock, row in rows.items():
        b = bridges.get(sock)
        if not b or b.poll() is not None:
            continue
        try:
            with open(os.path.join(sessions_dir(), f"{b.pid}.json"), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        name = d.get("name") if isinstance(d.get("name"), str) else row["entry"].get("name")
        seen[sock] = name
        far_pid = row["entry"].get("pid")
        if isinstance(far_pid, int) and far_pid > 0 and d.get("farPid") != far_pid:
            crossed.add(sock)
        far_sid = row["entry"].get("sessionId")
        if isinstance(far_sid, str) and far_sid and d.get("sessionId") != far_sid:
            crossed.add(sock)
        if far_identity_crossed(d, row, sock) or os.path.exists(os.path.join(sessions_dir(), f"{b.pid}.misroute")):
            crossed.add(sock)
        if isinstance(d.get("name"), str) and d["name"]:
            by_name.setdefault(d["name"], []).append(sock)
    for socks in by_name.values():
        if len(socks) > 1:
            crossed.update(socks)
    return [(seen[s], s) for s in rows if s in crossed]


def replaced_by_live_row(pid, far_sids):
    """True when mirror `pid`'s far session has been replaced: `far_sids` (bare far name -> live session ids)
    lists its far name only under other session ids, so no re-registration gap can bring it back."""
    try:
        with open(os.path.join(sessions_dir(), f"{pid}.json"), encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return False
    live = far_sids.get(bare_name(d.get("unimatrixFarName"))) if isinstance(d, dict) else None
    sid = d.get("sessionId") if isinstance(d, dict) else None
    return bool(live) and isinstance(sid, str) and bool(sid) and sid not in live and None not in live


ABSENT_POLLS_BEFORE_UNMIRROR = 2
_ABSENT = {}  # far socket -> consecutive polls its row was missing from the far roster


def sync(bridges, rows, cfg, say):
    """One reconcile pass: `rows` is far socket -> roster row; `bridges` far socket -> Popen.

    A live bridge whose row is missing is kept for `ABSENT_POLLS_BEFORE_UNMIRROR` polls in a row: a far
    router or engine respawn re-registers its sessions within seconds, and one poll landing in that gap
    must not drop a peer's mirror."""
    scan = live_sessions()
    for sock in rows:
        _ABSENT.pop(sock, None)
    for sock, row in rows.items():
        b = bridges.get(sock)
        if alias_duplicate(cfg.remote, sock, scan):
            if b:
                unmirror(bridges.pop(sock).pid)
                say(f"unmirror {sock}: another alias of this box mirrors it")
            continue
        deaf = b and b.poll() is None and (bridge_deaf(b.pid, local_endpoint(f"{cfg.remote}:{sock}"))
                                           or bridge_unlisted(b.pid))
        if b and b.poll() is None and not deaf:
            rename_live_mirror(b.pid, sock, row, cfg, say, scan)
            continue
        if deaf:
            say(f"bridge {b.pid} for {sock} lost its socket or registry entry; re-mirror")
        elif b:
            say(f"bridge {b.pid} for {sock} exited rc={b.poll()}; re-mirror")
        if b:
            BOUND_SINCE.pop(b.pid, None)
            unmirror(b.pid)
            scan = [(n, s) for n, s in scan if not same_scan_target(s, mirror_scan_key(cfg.remote, sock))]
        bridges[sock] = mirror(row, cfg, say, scan)
        nm = mirror_entry_name(row["entry"], cfg.remote, sock, scan)
        if isinstance(nm, str) and nm:
            scan.append((bare_name(nm), mirror_scan_key(cfg.remote, sock)))
    for name, sock in crossed_mirrors(bridges, rows):
        say(f"MISROUTE {name} {sock}")
        unmirror(bridges.pop(sock).pid)
    far_sids = {}
    for row in rows.values():
        if isinstance(row["entry"].get("name"), str):
            far_sids.setdefault(bare_name(row["entry"]["name"]), set()).add(row["entry"].get("sessionId"))
    for sock in [s for s in bridges if s not in rows]:
        missed = _ABSENT[sock] = _ABSENT.get(sock, 0) + 1
        if (missed < ABSENT_POLLS_BEFORE_UNMIRROR and bridges[sock].poll() is None
                and not replaced_by_live_row(bridges[sock].pid, far_sids)):
            say(f"row for {sock} absent ({missed}/{ABSENT_POLLS_BEFORE_UNMIRROR}); mirror kept")
            continue
        _ABSENT.pop(sock, None)
        unmirror(bridges.pop(sock).pid)
        say(f"unmirror {sock}")
    for sock in [s for s in _ABSENT if s not in bridges]:
        del _ABSENT[sock]


def link_state_path(alias, home=None) -> Path:
    """Link-state record path for far `alias`: <settings home>/unimatrix/link-state/<alias, path-safe>.json."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", alias)
    return (Path(home) if home else delivery_settings_home()) / "unimatrix" / "link-state" / f"{safe}.json"


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


LINK_FLIP_POLLS = 2


def link_verdict(run, ok):
    """(run, verdict): `run` is (last probe result, consecutive count). `verdict` is that result once
    LINK_FLIP_POLLS consecutive probes agree, else None, so one dropped SYN never flips the record."""
    last, n = run
    n = n + 1 if ok == last else 1
    return (ok, n), (ok if n >= LINK_FLIP_POLLS else None)


BACKOFF_CAP_SECONDS = 4 * POLL_SECONDS


def backoff_seconds(failures):
    """Sleep after `failures` consecutive failed polls: POLL_SECONDS doubling, capped at BACKOFF_CAP_SECONDS."""
    return min(POLL_SECONDS * 2 ** max(failures - 1, 0), BACKOFF_CAP_SECONDS)


def guarded(say, what, fn, *args, default=None, **kwargs):
    """Call `fn`; a raise is logged and swallowed so no single step ends the supervisor loop."""
    try:
        return fn(*args, **kwargs)
    except Exception as ex:
        say(f"{what} failed: {type(ex).__name__}: {ex}")
        return default


def require_relay_key(cfg) -> None:
    """Raise MissingRelayKeyError when the defaulted relay key is not a file: refused before any startup side effect."""
    if getattr(cfg, "key_defaulted", False) and not Path(cfg.key).is_file():
        raise MissingRelayKeyError(f"missing-relay-key: no unimatrix-zero relay key at {cfg.key}; install it or pass --key")


def main(argv=None) -> None:
    cfg = parse_args(sys.argv[1:] if argv is None else argv)
    require_relay_key(cfg)
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
    export_settings_home()
    stamp_supervisor(cfg.remote, "bridge")
    own_start = guarded(say, "own start", proc_start, os.getpid(), default=None)
    bridges = {}
    link_path = link_state_path(cfg.remote)
    # No record yet: None, so the first poll writes one and the G-EM watch sees a new box's first state.
    link = read_link_state(link_path) if os.path.exists(link_path) else None
    failures, stale, next_fetch, run = 0, False, 0.0, (None, 0)
    try:
        guarded(say, "startup reap", reap_orphaned_mirrors, cfg.remote, say)
        while True:
            if own_start is not None and stop_requested(own_start):
                say("STOPPED-BY-REQUEST")
                clear_stop(os.getpid())
                break
            ok, why = guarded(say, "link probe", link_probe, cfg.remote, cfg.tunnel_remote,
                              default=(False, "probe error"))
            run, verdict = link_verdict(run, ok)
            if verdict is not None:
                link = guarded(say, "link-state note", note_link, link, verdict, cfg.remote, why, say, link_path,
                               default=link)
            if _now() >= next_fetch:
                try:
                    rows = far_rows(fetch_roster(cfg.remote, cfg.key, cfg.tunnel_remote), cfg.remote, skip, say,
                                    keep=bridges)
                except Exception as ex:
                    failures += 1
                    if not stale:
                        say(f"ROSTER-STALE {cfg.remote}: {ex}")
                    stale = True
                    next_fetch = _now() + backoff_seconds(failures)
                    reaped = guarded(say, "reap", reap_orphaned_mirrors, cfg.remote, say, unbacked=True,
                                     bridges=bridges)
                    if reaped:
                        # A reset that reaps a live far session's mirror must not also leave it dark for the
                        # backoff: redial next tick, past the Windows replay cap. Nothing left to reap, so a
                        # link that stays down returns to the normal backoff on the following failure.
                        next_fetch = 0.0
                        _DIALS.pop(cfg.remote, None)
                else:
                    failures, stale, next_fetch = 0, False, 0.0
                    guarded(say, "sync", sync, bridges, rows, cfg, say)
                    guarded(say, "reap", reap_orphaned_mirrors, cfg.remote, say, unbacked=True,
                            keep={b.pid for b in bridges.values()})
                    guarded(say, "agy reap", reap_unbacked_agy_faces, say)
            if own_start is None:
                time.sleep(POLL_SECONDS)
            elif wait_or_stop(POLL_SECONDS, own_start):
                say("STOPPED-BY-REQUEST")
                clear_stop(os.getpid())
                break
    finally:
        tree_kill_many([b.pid for b in bridges.values()])


if __name__ == "__main__":
    main()
