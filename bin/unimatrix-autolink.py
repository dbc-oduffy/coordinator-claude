#!/usr/bin/env python3
"""Bring up the cross-box Unimatrix link to every configured far box, once, and name what it started.

Usage:
  unimatrix-autolink.py
  unimatrix-autolink.py --boot   (the login run: repeat the link pass every 30s until every pair is live or 600s pass)
  unimatrix-autolink.py restart   (stop the box router and its faces, then start the installed one, then link)
  unimatrix-autolink.py restart-box <alias>   (ask the box's supervisors to stop, then start one per role from this copy)

Far boxes are the members of the signed membership snapshot (verified offline against the pinned key,
minus this box), dialled as `<user>@<host>` from the record. Only when no snapshot exists are they the
comma-separated ssh aliases in the machine-local key `unimatrix.far_boxes` (transition fallback; unimatrix
doctor flags it). A snapshot that fails verification links nothing and logs one line. Each member that
answers is asked for `membership get`; a higher valid epoch is adopted (the library logs and notifies).
Every other alias this box dials (registry aliases and existing link records) is asked the same way, at most
once per PULL_SOURCES_INTERVAL_SECONDS, even when every link is healthy; an adopt relinks in the same run.
For each alias with no live supervisor pair, this starts one `unimatrix-roster.py` bridge
supervisor and one `unimatrix-mirror-all.py` inbox supervisor, detached, with only
that alias's relay key (`-o IdentitiesOnly=yes` is applied by the supervisors' ssh calls).
The key per alias is the machine-local `unimatrix.keys.<alias>`, else the IdentityFile `ssh -G` gives
the alias (an existing non-default file), else the shared key (settings home, else the group-em home).
The hands-on `unimatrix-01` key is never used: a source naming it is skipped for the next.
A probe that fails at the resolved address asks mDNS (one fresh sub-second multicast A query for the box's
.local name, no shell-out) for the live addresses, probes each other than the resolved one once, and logs both.
When that fails too, each ssh-config alias whose HostName names the same box (same host, or a live mDNS
address) is probed once with the same key; the first that answers is the remote both supervisors use.

Independently of any alias, a dead per-box `unimatrix-peer-router.py` is started once (record
`autolink-router.json`; a router holding its own lease, e.g. started by hand, counts as live).
`UNIMATRIX_AUTOLINK_NO_ROUTER=1` turns that step off.

Each link pass first replays what an absent host CLI deferred: `<settings home>/unimatrix/deferred-hosts.json`
names hosts staged without their CLI; a host whose CLI is now on PATH gets its Codex hook trust or agy plugin
install run once and its entry cleared (`replay_deferred_hosts`). No marker or no arrived CLI means no import of
unimatrix-install and no spawn.

When no alias is listed (or the registry is unreadable) it appends one reason line to the log and exits 0:
a receive-only box reads "no unimatrix.far_boxes configured; no supervisors started". An alias with no
existing key appends one line to the log and is skipped; other aliases still link. A held per-peer lock
logs its skip. An unreachable far box appends one line to `<settings home>/unimatrix/autolink.log`.
Stdout carries one line per alias that had supervisors started: `spawned bridge+inbox pair for <alias>` (or
`spawned bridge supervisor for ...`); a pass that started nothing prints one `no supervisors spawned: <alias>
(<reason>), ...` line unless every alias is parked or the pair is already live. A pair whose pids are alive but whose
link-state has read down for STALE_LINK_SECONDS is asked to stop (never killed) and relinks on the next pass. A
far-address (stable fallback) answer is never handed to the supervisors as an IP: they keep the logical peer, so mirror names carry the box id. A pass that raises prints one
stderr line `autolink failed: <Type>: <msg>` (plus `detached`'s nice-0 note) and the exit status is always 0
(a refused `restart` is 1): a session start must not fail on it.
"""
import base64
import calendar
import fnmatch
import hashlib
import hmac
import importlib.util
import ipaddress
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

HERE = Path(__file__).resolve().parent
REGISTRY_KEY = "unimatrix.far_boxes"
ALIAS_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._@-]{0,63}")
PROBE_CONNECT_SECONDS = 5
PROBE_TIMEOUT_SECONDS = 15
MDNS_GROUP = ("224.0.0.251", 5353)
MDNS_SECONDS = 0.8
UNIMATRIX_01_KEY = "unimatrix-01"
_PRIO_DARWIN_PROCESS = 4
PULL_SOURCES_INTERVAL_SECONDS = 900
PULL_STAMP_NAME = "pull-sources-stamp.json"
LOCK_STALE_SECONDS = 60
STAMP_GLOB = "supervisor-*.json"
STOP_WAIT_SECONDS = 15  # covers a roster step in flight (link probe 3s + far-address budget 8s) plus one poll slice
STALE_LINK_SECONDS = 300  # a supervisor this old whose link-state still reads down is deaf, not recovering
HOST_KEY_FAILURE = "host key verification failed"
UNLINKED_PREFIX = "no supervisors spawned: "
KEYS_PREFIX = "unimatrix.keys."
SSH_DEFAULT_IDENTITIES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ecdsa_sk", "id_ed25519", "id_ed25519_sk", "id_xmss"}
SUPERVISORS = (("bridge", "unimatrix-roster.py"), ("inbox", "unimatrix-mirror-all.py"))
ROUTER_SCRIPT = "unimatrix-peer-router.py"
NO_ROUTER_ENV = "UNIMATRIX_AUTOLINK_NO_ROUTER"
BOOT_WINDOW_SECONDS = 600
BOOT_POLL_SECONDS = 30
LOGIN_AGENT_LABEL = "com.unimatrix.autolink"  # mirrors unimatrix-install.py; autolink does not import it


PYTHON_KEY = "unimatrix.python"
_PINNED = {}


class InterpreterPinError(RuntimeError):
    """The `unimatrix.python` key names an interpreter that is not a file, or no console interpreter resolves."""


def _interp():
    spec = importlib.util.spec_from_file_location("unimatrix_python_interp", HERE / "lib" / "python_interp.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def console_python():
    """A real console CPython (never a pythonw or forwarder exe), or None."""
    return _interp().resolve_console_python()


def pin_key_value(roster, run=subprocess.run):
    """The machine-local `unimatrix.python` value, or None when unset or unreadable."""
    reader = _home(roster) / "bin" / "_machine_local.py"
    exe = console_python()
    if not reader.is_file() or not exe:
        return None
    try:
        r = run([exe, str(reader), "get", PYTHON_KEY], capture_output=True, text=True, timeout=2.0,
                creationflags=roster.no_window())
    except (OSError, subprocess.SubprocessError):
        return None
    val = r.stdout.strip() if not r.returncode else ""
    return os.path.expanduser(val) if val else None


def pinned_python(roster):
    """The one interpreter every supervisor and reader spawn uses: the `unimatrix.python` key when set (a
    missing file is an InterpreterPinError naming the key), else the shared `unimatrix_python` resolution."""
    home = str(_home(roster))
    if home not in _PINNED:
        val = pin_key_value(roster)
        if val and not os.path.isfile(val):
            raise InterpreterPinError(f"{PYTHON_KEY} names a missing interpreter: {val}")
        exe = _interp().unimatrix_python(val)
        if not exe:
            raise InterpreterPinError(f"no console python resolves; set {PYTHON_KEY}")
        _PINNED[home] = exe
    return _PINNED[home]


def _roster():
    spec = importlib.util.spec_from_file_location("unimatrix_roster", HERE / "unimatrix-roster.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _home(roster) -> Path:
    """The settings home for a login-launched autolink pass, which carries no COORDINATOR_SETTINGS_HOME."""
    return getattr(roster, "delivery_settings_home", roster.settings_home)()


_PASSPHRASE = []


def _passphrase():
    if not _PASSPHRASE:
        spec = importlib.util.spec_from_file_location("unimatrix_passphrase", HERE / "unimatrix-passphrase.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _PASSPHRASE.append(mod)
    return _PASSPHRASE[0]


def agent_state(key, run=subprocess.run):
    """ensure_agent's verdict for `key`: 'unencrypted', 'loaded', 'locked' or 'missing'. Library absent or a
    failed load reads as 'loaded' (the dial then reports its own failure)."""
    try:
        return _passphrase().ensure_agent(key, run=run)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return "loaded"


def _core_module(subname):
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    if "_unimatrix" not in sys.modules and os.path.isdir(os.path.join(bin_dir, "_unimatrix")):
        if bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
    import importlib
    return importlib.import_module(f"_unimatrix.{subname}")


def _liveness():
    return _core_module("proc")


_MEMBERSHIP = []


def _membership():
    if not _MEMBERSHIP:
        spec = importlib.util.spec_from_file_location("unimatrix_membership", HERE / "unimatrix-membership.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MEMBERSHIP.append(mod)
    return _MEMBERSHIP[0]


COPIES_STAMP_NAME = "installed-copies-stamp.json"
COPIES_CHECK_SECONDS = 300


def _digest(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def installed_copy_drift(src_bin, dest):
    """Names (relative to `dest`) of installed scripts whose bytes differ from the same-named clone script.

    Only files the box already installed are compared: a clone script it never vendored is not drift."""
    names = [p.name for p in dest.glob("*.py")] + [f"lib/{p.name}" for p in (dest / "lib").glob("*.py")]
    return sorted(n for n in names if (src_bin / n).is_file() and _digest(src_bin / n) != _digest(dest / n))


def _clone_bin(home):
    """`<clone>/coordinator/bin` of the box's klabauter clone, else None."""
    ladder = Path(home) / "bin" / "_resolve_claude_klabauter.py"
    if not ladder.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_al_resolve_klabauter", ladder)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    root, _cls = mod.resolve_claude_klabauter_root_with_class()
    src = Path(root) / "coordinator" / "bin" if root else None
    return src if src is not None and (src / "unimatrix-install.py").is_file() else None


def refresh_installed_copies(roster, now=time.time, clone_bin=_clone_bin):
    """Re-copy installed unimatrix scripts that drifted from the klabauter clone; at most once per COPIES_CHECK_SECONDS.

    Trap: the clone moves under a long-lived box (git pull, reconcile) while the SessionStart freshness leg
    only fires on a fresh session, so a box could run pre-fix scripts for days. This pass is the one thing
    that runs on every box every minute. Drift that survives the refresh is printed on stderr every pass.
    Never raises: a refresh fault must not stop linking."""
    home = _home(roster)
    sdir = state_dir(roster)
    stamp = sdir / COPIES_STAMP_NAME
    try:
        if now() - json.loads(stamp.read_text(encoding="utf-8")).get("at", 0) < COPIES_CHECK_SECONDS:
            return []
    except (OSError, ValueError, AttributeError):
        pass
    try:
        src = clone_bin(home)
        if src is None or not sdir.is_dir():
            return []
        drift = installed_copy_drift(src, sdir)
        if drift:
            spec = importlib.util.spec_from_file_location("_al_unimatrix_install", src / "unimatrix-install.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.install_scripts(src, sdir)
            drift = installed_copy_drift(src, sdir)
            with open(sdir / "autolink.log", "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} installed copies drifted from the "
                         f"clone; refreshed, {len(drift)} still differ\n")
        if drift:
            print(f"autolink: installed copies still differ from the klabauter clone: {', '.join(drift[:8])}", file=sys.stderr)
        stamp.write_text(json.dumps({"at": now(), "drift": drift}), encoding="utf-8")
        return drift
    except Exception as ex:
        print(f"autolink: installed-copy refresh failed: {type(ex).__name__}: {str(ex)[:200]}", file=sys.stderr)
        return []


def state_dir(roster):
    return _home(roster) / "unimatrix"


def own_names():
    return {socket.gethostname().split(".")[0].lower()}


def split_members(roster, mem=None, self_names=None, run=subprocess.run):
    """(status, {remote: box}, skipped, epoch, reason) for the stored membership snapshot.

    status is "none" (no snapshot stored), "bad" (stored but not verifiable; reason says why) or "ok".
    Members are dialled as `<user>@<host>` from the record, a DNS or .local hostname (ssh matches its
    `Host <hostname>` alias block, never an IP pin); this box is dropped by hostname.
    `skipped` is [(box, remote)] for each verified member whose dial name fails ALIAS_RE or is an IP literal."""
    try:
        mem = mem or _membership()
    except OSError:  # membership library not vendored on this box yet: the transition fallback applies
        return "none", {}, [], None, None
    home = _home(roster)
    try:
        snap, _ = mem.load_snapshot(home)
        if snap is None:
            return "none", {}, [], None, None
        members = mem.verified_members(home, run=run)
    except mem.MembershipError as ex:
        return "bad", {}, [], None, f"membership snapshot not usable, nothing linked from it: {str(ex)[:120]}"
    me = {n.lower() for n in (self_names if self_names is not None else own_names())}
    targets, skipped = {}, []
    for m in members:
        if m["box"].lower() in me or m["host"].split(".")[0].lower() in me:
            continue
        remote = f"{m['user']}@{m['host']}"
        if ALIAS_RE.fullmatch(remote) and not mem.is_ip_literal(m["host"]):
            targets[remote] = m["box"]
        else:
            skipped.append((m["box"], remote))
    return "ok", targets, skipped, snap["epoch"], None


def member_targets(roster, mem=None, self_names=None, run=subprocess.run):
    """(status, {remote: box}, epoch, reason): `split_members` without the skipped list."""
    status, targets, _, epoch, why = split_members(roster, mem, self_names, run=run)
    return status, targets, epoch, why


def pull_membership(roster, remote, key, run=subprocess.run):
    """Ask `remote` for `membership get` and adopt a strictly higher valid epoch; True when adopted.

    A refused snapshot is logged and notified by the library's adopt, then the error propagates."""
    mem = _membership()
    cmd = ["ssh", "-n", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "AddressFamily=inet",
           "-o", f"ConnectTimeout={PROBE_CONNECT_SECONDS}", remote, "membership", "get"]
    r = run(cmd, capture_output=True, timeout=PROBE_TIMEOUT_SECONDS, creationflags=roster.no_window())
    lines = (r.stdout or b"").decode("utf-8", "replace").splitlines()
    if r.returncode or len(lines) < 2:
        return False
    snap = json.loads(lines[0])
    home = _home(roster)
    held, _ = mem.load_snapshot(home)
    if held is not None and snap.get("epoch", 0) <= held["epoch"]:
        return False
    mem.adopt(home, snap, base64.b64decode(lines[1].strip(), validate=True))
    return True


NO_ALIAS_REASON = "no unimatrix.far_boxes configured; no supervisors started"


def far_boxes_status(roster, guard=False):
    """(aliases, reason): reason names why `aliases` is empty, and is None when it is not.
    `guard` refuses a real alias under a test home; the read-only doctor diagnosis leaves it off."""
    reader = _home(roster) / "bin" / "_machine_local.py"
    if not reader.is_file():
        return [], f"{REGISTRY_KEY} unreadable (machine-local reader missing: {reader}); no supervisors started"
    try:
        r = subprocess.run([pinned_python(roster), str(reader), "get", REGISTRY_KEY],
                           capture_output=True, text=True, timeout=2.0, creationflags=roster.no_window())
    except (OSError, subprocess.SubprocessError, InterpreterPinError) as ex:
        return [], f"{REGISTRY_KEY} unreadable ({type(ex).__name__}); no supervisors started"
    unset = r.returncode == 1 and (not (r.stderr or "").strip() or "not found in registry" in r.stderr)
    if r.returncode and not unset:  # an uncaught reader crash also exits 1, hence the stderr check above
        err = " ".join((r.stderr or "").split())[:200] or "none"
        return [], f"{REGISTRY_KEY} read failed (reader rc={r.returncode}, stderr: {err}); no supervisors started"
    raw = r.stdout.strip() if not r.returncode else ""
    if not raw:
        return [], NO_ALIAS_REASON
    seen = []
    for tok in re.split(r"[,\s]+", raw):
        if tok and ALIAS_RE.fullmatch(tok) and tok not in seen:
            seen.append(tok)
    if not seen:
        return [], f"{REGISTRY_KEY} lists no valid alias ({raw[:80]!r}); no supervisors started"
    if guard:
        for alias in seen:
            roster.refuse_real("far_box", alias)
    return seen, None


def read_far_boxes(roster):
    """Configured ssh aliases; empty when the key, the reader, or any valid alias is absent."""
    return far_boxes_status(roster, guard=True)[0]


def slug(alias):
    return alias.replace("@", "_at_")


def supervisor_live(roster, rec):
    """True when the recorded pid is alive and is the same process that was started."""
    pid = rec.get("pid")
    if not isinstance(pid, int) or not roster.pid_alive(pid):
        return False
    try:
        return roster.proc_start(pid) == rec.get("procStart")
    except (OSError, subprocess.SubprocessError):
        return False


def read_record(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def acquire_lock(path):
    """Exclusive per-peer lock so two session starts never both spawn; a stale lock is taken over."""
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(path) < LOCK_STALE_SECONDS:
                    return False
                os.remove(path)
            except OSError:
                return False
    return False


def probe(roster, alias, key, run=subprocess.run, remote=None):
    """None when the far relay answers, else a short reason. Uses only the relay key.

    `remote` overrides the dialled name (a stable-name fallback for a stale `alias`)."""
    remote = remote or roster.pick_remote(alias, roster.default_tunnel())
    cmd = ["ssh", "-n", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "AddressFamily=inet",
           "-o", f"ConnectTimeout={PROBE_CONNECT_SECONDS}", remote, "roster"]
    try:
        r = run(cmd, capture_output=True, timeout=PROBE_TIMEOUT_SECONDS, creationflags=roster.no_window())
    except (OSError, subprocess.SubprocessError) as ex:
        return type(ex).__name__
    if r.returncode:
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        return f"rc={r.returncode}" + (f": {err[-1][:120]}" if err else "")
    return None


def detached(cmd):
    """Start `cmd` fully detached from this process and the session that ran it."""
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(cmd, creationflags=flags, **kw)
    parent_nice = _own_nice()
    proc = subprocess.Popen(cmd, start_new_session=True, preexec_fn=_nice_zero, **kw)
    child_nice = _nice_of(proc.pid)
    if child_nice not in (None, 0):
        print(f"autolink: nice 0 refused for pid {proc.pid}: child nice {child_nice}, parent nice {parent_nice} "
              f"(an unprivileged child cannot lower nice; relaunch from launchd or a nice-0 parent)", file=sys.stderr)
    return proc


def _nice_zero():
    """Child-side, between fork and exec: nice 0 and no Darwin background band, whatever the parent's.
    Allocation-free; EPERM (parent above nice 0) leaves the inherited value for `detached` to report."""
    try:
        os.setpriority(os.PRIO_PROCESS, 0, 0)
    except Exception:
        pass
    try:
        os.setpriority(_PRIO_DARWIN_PROCESS, 0, 0)  # value 0 clears PRIO_DARWIN_BG on macOS
    except Exception:
        pass


def _nice_of(pid):
    try:
        return os.getpriority(os.PRIO_PROCESS, pid)
    except Exception:
        return None


def _own_nice():
    return _nice_of(0)


def supervisor_cmd(script, log, alias, key, tunnel, python):
    cmd = [python, str(HERE / script), str(log), "--remote", alias, "--key", key]
    return cmd + ["--tunnel-remote", tunnel] if tunnel else cmd


def stable_fallback(roster, alias, key, why, probe_fn, stable_fn):
    """(remote, why) after a failed probe of `alias`: the first stable name that answers, else the original why."""
    alt = stable_fn(alias)
    if alt and alt != alias:
        why_alt = probe_fn(roster, alias, key, remote=alt)
        if not why_alt:
            return alt, None
    return alias, why


def _qname(name):
    return b"".join(bytes([len(p)]) + p for p in (l.encode("idna") for l in name.rstrip(".").split("."))) + b"\0"


def _read_name(buf, i):
    """(lowercase dotted name, index after it) for the DNS name at `i`, following compression pointers."""
    labels, end, hops = [], None, 0
    while True:
        n = buf[i]
        if n & 0xC0 == 0xC0:
            if end is None:
                end = i + 2
            i, hops = ((n & 0x3F) << 8) | buf[i + 1], hops + 1
            if hops > 20:
                raise ValueError("name pointer loop")
        elif n == 0:
            return ".".join(labels).lower(), (i + 1 if end is None else end)
        else:
            labels.append(buf[i + 1:i + 1 + n].decode("ascii", "replace"))
            i += 1 + n


def parse_a_records(buf, name):
    """IPv4 addresses of `name`'s A records in one DNS message; [] for a malformed or unrelated one."""
    want, out = name.rstrip(".").lower(), []
    try:
        qd, an, ns, ar = struct.unpack(">4H", buf[4:12])
        i = 12
        for _ in range(qd):
            i = _read_name(buf, i)[1] + 4
        for _ in range(an + ns + ar):
            rname, i = _read_name(buf, i)
            rtype, rclass, _ttl, rdlen = struct.unpack(">HHIH", buf[i:i + 10])
            i += 10
            if i + rdlen > len(buf):
                break
            if rname == want and rtype == 1 and rclass & 0x7FFF == 1 and rdlen == 4:
                addr = socket.inet_ntoa(buf[i:i + 4])
                if addr not in out:
                    out.append(addr)
            i += rdlen
    except (IndexError, ValueError, struct.error):
        pass
    return out


def mdns_a_records(name, timeout=MDNS_SECONDS):
    """Current IPv4 addresses of `<name>.local` from a fresh multicast-DNS A query; [] when nothing answers.

    Sent from an ephemeral port (legacy unicast, RFC 6762 6.7), so the reply comes straight back and the
    box's own mDNS responder keeps port 5353. Asked each call; nothing is cached."""
    query = struct.pack(">6H", 0, 0, 1, 0, 0, 0) + _qname(name) + struct.pack(">HH", 1, 1)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
            for _ in range(2):
                s.sendto(query, MDNS_GROUP)
                round_end = time.monotonic() + timeout / 2
                while (wait := round_end - time.monotonic()) > 0:
                    s.settimeout(wait)
                    try:
                        addrs = parse_a_records(s.recv(4096), name)
                    except socket.timeout:
                        break
                    if addrs:
                        return addrs
    except (OSError, UnicodeError, ValueError):
        pass
    return []


def live_name(roster, alias, hostname_fn=None):
    """The `.local` name to ask mDNS for `alias`'s box, else None (an IP literal or a unicast DNS name)."""
    host = alias.rpartition("@")[2]
    if not host.lower().rstrip(".").endswith(".local"):
        host = (hostname_fn or ssh_hostname)(roster, alias) or ""
    host = host.strip().rstrip(".")
    if host.lower().endswith(".local"):
        return host
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    return f"{host}.local" if host and "." not in host else None


def _resolved_v4(name):
    try:
        return socket.getaddrinfo(name, None, socket.AF_INET)[0][4][0]
    except (OSError, IndexError):
        return None


def mdns_fallback(roster, alias, key, why, probe_fn, mdns_fn=None, resolve_fn=None, hostname_fn=None):
    """(remote, why, note) after a failed probe of `alias`: ask mDNS for the box's live addresses, probe each
    other than the resolved one once with the same key and take the first that answers.

    `remote` is `<user>@<address>` on success, else `alias` with the original `why`. `note` names the resolved
    and the live addresses (None when mDNS gave none). getaddrinfo honours a stale hosts-file line; mDNS does not."""
    name = live_name(roster, alias, hostname_fn)
    live = (mdns_fn or mdns_a_records)(name) if name else []
    if not live:
        return alias, why, None
    resolved = (resolve_fn or _resolved_v4)(name)
    user = alias.rpartition("@")[0]
    if not user:
        try:
            user = roster.ssh_fields(alias).get("user") or ""
        except (OSError, subprocess.SubprocessError, KeyError):
            user = ""
    for addr in (a for a in live if a != resolved):
        remote = f"{user}@{addr}" if user else addr
        if not probe_fn(roster, alias, key, remote=remote):
            return remote, None, f"resolved {resolved or 'nothing'} failed ({why}); live mDNS address {addr} answered"
    return alias, why, f"resolved {resolved or 'nothing'} and live mDNS {', '.join(live)} did not answer"


def ssh_config_aliases(path=None, depth=0):
    """Concrete `Host` names of the user's ssh config (wildcard and negated patterns dropped), `Include`s followed."""
    base = Path(os.path.expanduser("~/.ssh"))
    try:
        text = Path(path or base / "config").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        parts = line.split("#", 1)[0].replace("=", " ", 1).split()
        if not parts:
            continue
        kw, args = parts[0].lower(), parts[1:]
        if kw == "host":
            out += [a for a in args if ALIAS_RE.fullmatch(a)]
        elif kw == "include" and depth < 4:
            for pat in args:
                pat = os.path.expanduser(pat)
                pat = pat if os.path.isabs(pat) else str(base / pat)
                for p in sorted(Path(pat).parent.glob(Path(pat).name)):
                    out += ssh_config_aliases(p, depth + 1)
    return list(dict.fromkeys(out))


def _known_hosts_entries(path=None):
    """[(host patterns, 'type base64')] of the user's known_hosts; markers (`@cert-authority`, `@revoked`) skipped."""
    try:
        text = Path(path or Path(os.path.expanduser("~/.ssh")) / "known_hosts").read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0].startswith(("#", "@")):
            continue
        out.append((parts[0].split(","), f"{parts[1]} {parts[2]}"))
    return out


def _known_host_match(pattern, name):
    if pattern.startswith("|1|"):
        try:
            _, _, salt, digest = pattern.split("|")[:4]
            mac = hmac.new(base64.b64decode(salt), name.encode("utf-8"), hashlib.sha1).digest()
            return base64.b64encode(mac).decode("ascii") == digest
        except (ValueError, TypeError):
            return False
    if pattern.startswith("["):
        pattern = pattern[1:].partition("]")[0]
    return pattern.lower().rstrip(".") == name.lower().rstrip(".")


def known_host_keys(names, entries=None):
    """Host keys the known_hosts file records for any of `names` (a `.local` name also tried bare, and the reverse)."""
    variants = set()
    for n in names:
        n = str(n).strip().rstrip(".")
        if n:
            variants |= {n, _host_key(n), f"{_host_key(n)}.local"} if not ipaddress_literal(n) else {n}
    entries = _known_hosts_entries() if entries is None else entries
    return {k for pats, k in entries if any(_known_host_match(p, v) for p in pats for v in variants)}


def ipaddress_literal(name):
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


def relay_boxes(roster, remote, key, run=subprocess.run):
    """Lower-cased `box` names the far relay's `roster` answer reports for itself, or None when it did not answer."""
    cmd = ["ssh", "-n", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "AddressFamily=inet",
           "-o", f"ConnectTimeout={PROBE_CONNECT_SECONDS}", remote, "roster"]
    try:
        r = run(cmd, capture_output=True, timeout=PROBE_TIMEOUT_SECONDS, creationflags=roster.no_window())
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode:
        return None
    boxes = set()
    for line in (r.stdout or b"").decode("utf-8", "replace").splitlines():
        try:
            box = json.loads(line).get("entry", {}).get("box")
        except (ValueError, AttributeError):
            continue
        if isinstance(box, str) and box.strip():
            boxes.add(_host_key(box))
    return boxes


def ssh_alias_fallback(roster, alias, key, why, probe_fn, aliases_fn=None, hostname_fn=None, mdns_fn=None,
                       resolve_fn=None, entries=None, identity_fn=None, boxes_fn=None):
    """(remote, why, note, key) after the recorded name and mDNS failed: probe each ssh-config alias naming the same box.

    An alias names the box when its `ssh -G` HostName equals the recorded host (`.local`, case ignored); else when
    a known_hosts host key recorded for the alias or its HostName equals one recorded for the recorded host (no
    network, so a stale hosts line or failing mDNS cannot hide it); else when the alias (or its HostName) has a
    supervisor record in the state dir and the far relay's own `roster` answer reports the recorded host as its
    box (one ssh per such alias, which is also its probe, for a recorded name known_hosts never saw); else when
    its HostName is or resolves to a live mDNS address (asked once). The first alias that answers a probe is
    `remote` (`<user>@<alias>` when the recorded name had a user), probed with its own IdentityFile and the
    recorded `key` when it has none; `key` returned is the one that answered."""
    host = alias.rpartition("@")[2]
    want, user = _host_key(host), alias.rpartition("@")[0]
    hostname_fn = hostname_fn or ssh_hostname
    cands = [a for a in (aliases_fn or ssh_config_aliases)() if _host_key(a) != want]
    names = [(a, hostname_fn(roster, a) or "") for a in cands]
    matched = [a for a, h in names if _host_key(h) == want]
    if not matched and names:
        entries = _known_hosts_entries() if entries is None else entries
        recorded = known_host_keys([host], entries)
        if recorded:
            matched = [a for a, h in names if recorded & known_host_keys([a, h], entries)]
    answered = {}
    if not matched and names:
        held = {_host_key(a.rpartition("@")[2]) for a in record_aliases(state_dir(roster))}
        for a, h in names:
            if _host_key(a) not in held and not (h and _host_key(h) in held):
                continue
            remote = f"{user}@{a}" if user else a
            own = (identity_fn or ssh_identity_file)(roster, a) or key
            if want in ((boxes_fn or relay_boxes)(roster, remote, own) or ()):
                matched.append(a)
                answered[a] = own
    if not matched:
        name = live_name(roster, alias)
        live = set((mdns_fn or mdns_a_records)(name) if name and names else [])
        resolve = resolve_fn or _resolved_v4
        matched = [a for a, h in names if h and (h in live or resolve(h) in live)] if live else []
    for cand in matched:
        remote = f"{user}@{cand}" if user else cand
        own = answered.get(cand) or (identity_fn or ssh_identity_file)(roster, cand) or key
        if cand in answered or not probe_fn(roster, alias, own, remote=remote):
            return remote, None, f"ssh alias {cand} names the same box and answered", own
    return (alias, why,
            f"ssh alias {', '.join(matched)} named the same box and did not answer" if matched else None, key)


class Started(list):
    """The roles `link_peer` spawned; `reason` names why the pair is still not live (None when it is)."""
    reason = None


def link_peer(roster, alias, key, say, spawn=detached, probe_fn=probe, stable_fn=None, now=None, liveness=None,
              pull_fn=None, mdns_fn=None, alias_fn=None, hosts=None, lan_fn=None) -> Started:
    """Start whichever of the peer's two supervisors is not live; the roles started, empty when none. Never raises for a down peer.

    A host-key-verified LAN route (`lan_route`) is tried first and, when found, replaces the off-LAN probe;
    the supervisors still get the logical `alias` and the relay key as `--remote`/`--key`; a pair already live is never touched. Else the mDNS live-address retry, the ssh-config alias retry, then the stable-name fallback, run only after the
    recorded name itself failed to answer; the probe outcome feeds the backoff."""
    started = Started()
    stable_fn = stable_fn or roster.stable_remote
    liveness = liveness or _liveness()
    sdir = state_dir(roster)
    rec_path = record_path(sdir, alias)
    hosts = {} if hosts is None else hosts
    stable_address = False
    box = box_key(roster, alias, hosts)
    lock = sdir / f"autolink-{slug(box)}.lock"
    if not acquire_lock(lock):
        say(f"far box {alias}: link lock held by another start; skipped")
        started.reason = "link lock held"
        return started
    raw_probe = probe_fn

    def probe_fn(*args, **kwargs):  # a probe chain outlasts LOCK_STALE_SECONDS; keep the lock fresh
        try:
            os.utime(lock)
        except OSError:
            pass
        return raw_probe(*args, **kwargs)
    try:
        legacy = [p for p in group_records(roster, sdir, hosts).get(box, []) if p != rec_path]
        rec = read_record(rec_path)
        for p in legacy:  # an old raw-slug record is read once, then folded into the canonical one
            old = read_record(p)
            if not rec or (not pair_live(roster, rec) and pair_live(roster, old)):
                rec = old
        missing = [role for role, _ in SUPERVISORS if not supervisor_live(roster, rec.get(role) or {})]

        def migrate():
            if legacy:
                roster.write_json_atomic(str(rec_path), rec)
                for p in legacy:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
        if not missing:
            migrate()
            return started
        route = (lan_fn or lan_route)(roster, alias, key)
        if route is not None:
            remote, why, note = alias, None, None  # the supervisors keep the logical peer: an IP remote would key HostKeyAlias and mirror names to the address
            say(f"far box {alias}: verified LAN route {route.endpoint} (link decision only; supervisors dial {alias})")
        else:
            why = probe_fn(roster, alias, key)
            remote, note = alias, None
            if why:
                remote, why, note = mdns_fallback(roster, alias, key, why, probe_fn, mdns_fn)
            if why:
                first_note = note
                remote, why, note, key = ssh_alias_fallback(roster, alias, key, why, probe_fn, alias_fn, mdns_fn=mdns_fn)
                note = "; ".join(n for n in (first_note, note) if n) or None
            if why:
                remote, why = stable_fallback(roster, alias, key, why, probe_fn, stable_fn)
                stable_address = not why
        liveness.note_probe(sdir, alias, not why, now)
        if why:
            say(f"far box {alias} unreachable: {why}" + (f" ({note})" if note else ""))
            started.reason = f"unreachable: {why}"
            return started
        if route is None and remote != alias:
            say(f"far box {alias} pinned address stale; linked via {remote}" + (f" ({note})" if note else ""))
        if pull_fn:
            try:
                pull_fn(roster, remote, key)
            except Exception as ex:  # a refused or malformed peer snapshot never blocks the link
                say(f"far box {alias}: membership pull skipped: {type(ex).__name__}: {str(ex)[:100]}")
        supervised = remote  # the roster names mirrors by its --remote host: an address there labels them by IP
        if stable_address and ipaddress_literal(supervised.rpartition("@")[2].strip("[]")):  # the box mux re-resolves the box id to a listed address itself
            say(f"far box {alias}: answered at {supervised}; supervisors keep {alias} so mirror names carry the box id")
            supervised = alias
        tunnel = roster.default_tunnel()
        for role, script in SUPERVISORS:
            if role not in missing:
                continue
            p = spawn(supervisor_cmd(script, sdir / f"{role}-{slug(alias)}.log", supervised, key, tunnel,
                                      pinned_python(roster)))
            try:
                stamp = roster.proc_start(p.pid)
            except (OSError, subprocess.SubprocessError):
                stamp = None
            rec[role] = {"pid": p.pid, "procStart": stamp}
            rec["box"] = box
            started.append(role)
            if stamp is not None:  # the reaper's evidence of a supervisor, kept after a record loses its pid
                try:
                    roster.write_json_atomic(str(sdir / f"supervisor-{p.pid}.json"),
                                             {"pid": p.pid, "procStart": stamp, "remote": supervised, "role": role})
                except OSError:
                    pass
            roster.write_json_atomic(str(rec_path), rec)  # per spawn: a later failure never orphans this one
        migrate()
        return started
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def machine_local_key(roster, alias, run=subprocess.run):
    """The machine-local `unimatrix.keys.<alias>` path, or None when unset or unreadable."""
    reader = _home(roster) / "bin" / "_machine_local.py"
    if not reader.is_file():
        return None
    try:
        r = run([pinned_python(roster), str(reader), "get", f"{KEYS_PREFIX}{alias}"],
                capture_output=True, text=True, timeout=2.0, creationflags=roster.no_window())
    except (OSError, subprocess.SubprocessError, InterpreterPinError):
        return None
    val = r.stdout.strip() if not r.returncode else ""
    return os.path.expanduser(val) if val else None


def machine_local_value(roster, name, run=subprocess.run) -> str:
    """The raw machine-local value of `name`, '' when the reader is missing, fails or the key is unset."""
    reader = _home(roster) / "bin" / "_machine_local.py"
    if not reader.is_file():
        return ""
    try:
        r = run([pinned_python(roster), str(reader), "get", name],
                capture_output=True, text=True, timeout=2.0, creationflags=roster.no_window())
    except (OSError, subprocess.SubprocessError, InterpreterPinError):
        return ""
    return r.stdout.strip() if not r.returncode else ""


_FAR = []


def _far() -> object:
    if not _FAR:
        spec = importlib.util.spec_from_file_location("unimatrix_far_addresses", HERE / "lib" / "unimatrix_far_addresses.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _FAR.append(mod)
    return _FAR[0]


def lan_route(roster, alias, key, far=None, read_key=None, connect=None, verify=None) -> object | None:
    """The `Route` of the first host-key-verified LAN address of `alias`'s peer, else None. Never raises.

    The peer is the `unimatrix.addresses.<box>` list owner; no list costs one reader spawn and nothing else.
    A TCP connect only pre-filters: an address is chosen only when `ssh` verifies the peer's host key under
    `HostKeyAlias=<box>` with the relay `key`, so an address held by another machine is never returned."""
    try:
        far = far or _far()
        user, _, host = alias.rpartition("@")
        peer = roster._box_mux().box_of(host)
        seen = {}

        def memo(name) -> str:
            if name not in seen:
                seen[name] = (read_key or (lambda n: machine_local_value(roster, n)))(name)
            return seen[name]
        if not far.box_addresses(peer, memo):
            return None
        user = user or roster.ssh_fields(alias).get("user") or None
        route = far.select_route(peer, user, alias, read_key=memo, connect=connect or far.tcp_connect,
                                 verify=verify or far.make_verify(peer, key), relay_key=key)
    except Exception:  # noqa: BLE001 -- a LAN lookup failure falls back to the recorded route
        return None
    if route.transport != far.LAN or route.verification != far.VERIFIED or not route.endpoint:
        return None
    return route._replace(endpoint=far.target_for(user, route.endpoint))


def ssh_identity_file(roster, alias, run=subprocess.run):
    """First existing, non-default IdentityFile `ssh -G` gives the alias, else None."""
    try:
        r = run(["ssh", "-G", "--", alias], capture_output=True, text=True, timeout=PROBE_CONNECT_SECONDS,
                creationflags=roster.no_window())
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode:
        return None
    out = r.stdout.decode("utf-8", "replace") if isinstance(r.stdout, bytes) else (r.stdout or "")
    for line in out.splitlines():
        name, _, val = line.partition(" ")
        if name.lower() != "identityfile":
            continue
        path = Path(os.path.expanduser(val.strip()))
        if path.name not in SSH_DEFAULT_IDENTITIES and path.suffix.lower() != ".pub" and not hands_on_key(path) and path.is_file():
            return str(path)
    return None


def hands_on_key(key):
    """True for the 1Password `unimatrix-01` key, which an unattended link never uses."""
    return Path(str(key)).name.lower() == UNIMATRIX_01_KEY


def resolve_key(roster, alias, local_fn=None, ssh_fn=None, via=None) -> str:
    """The relay key for one alias: machine-local, else ssh-config IdentityFile, else the shared default.

    `via` is a callable giving other aliases of the same box (`matching_aliases`); their machine-local keys
    and ssh-config IdentityFiles are tried after `alias`'s own and before the shared default, so a key set
    under any matching alias (e.g. `macmini-lan` for `oduffy@Mac-mini.local`) is found.
    A source that names the hands-on `unimatrix-01` key is skipped for the next one."""
    local = local_fn or machine_local_key
    ssh_lookup = ssh_fn or ssh_identity_file
    others = [other for other in (via() if via else ()) if other != alias]

    def sources() -> Iterator[tuple]:
        yield local, alias
        for other in others:
            yield local, other
        yield ssh_lookup, alias
        for other in others:
            yield ssh_lookup, other
    for fn, name in sources():
        key = fn(roster, name)
        if key and not hands_on_key(key):
            roster.refuse_real("key_path", key)
            return key
    return roster.default_key()


def _host_key(name):
    # Same normalisation as unimatrix-pair.py and unimatrix-doctor.py :: _host_key; change all together.
    low = str(name).strip().lower().rstrip(".")
    return low[:-len(".local")] if low.endswith(".local") else low


def link_key(name):
    """Canonical identity of a link target: `<user lower>@<_host_key(host)>`, or the bare host key without a user."""
    user, at, host = str(name).strip().rpartition("@")
    host = _host_key(host)
    return f"{user.strip().lower()}@{host}" if at and user.strip() else host


def pull_sources(names, aliases, records):
    """Remotes outside the held snapshot to ask for a newer epoch, one per `link_key`.

    `names` is the snapshot's `{remote: box}`; `aliases` the registry aliases; `records` the alias of each
    existing link record. A candidate is dropped when its link key is a member's, or when it is a bare host
    matching a member's host."""
    member_keys = {link_key(n) for n in names}
    member_hosts = {k.rpartition("@")[2] for k in member_keys}
    seen, out = set(), []
    for cand in [*aliases, *records]:
        key = link_key(cand)
        if key in seen or key in member_keys or ("@" not in key and key in member_hosts):
            continue
        seen.add(key)
        out.append(cand)
    return out


def record_files(sdir):
    """[(alias, path)] for each `autolink-<slug>.json` supervisor record, the alias recovered from the file name."""
    out = []
    for p in sorted(Path(sdir).glob("autolink-*.json")):
        stem = p.stem[len("autolink-"):]
        if stem in ("boxes", "router") or stem.endswith(".backoff"):
            continue
        alias = stem.replace("_at_", "@")
        if ALIAS_RE.fullmatch(alias):
            out.append((alias, p))
    return out


def record_aliases(sdir):
    """Aliases that have an `autolink-<slug>.json` supervisor record, recovered from the file names."""
    return [alias for alias, _ in record_files(sdir)]


def record_path(sdir, alias):
    """The supervisor record of one spelling: one file per `link_key`, its name a dialable alias."""
    return Path(sdir) / f"autolink-{slug(link_key(alias))}.json"


def box_key(roster, name, hosts=None, run=subprocess.run):
    """Identity of the far box `name` spells: the normalised host of `user@host`, or of a bare alias's `ssh -G` HostName.

    `hosts` caches alias -> normalised HostName across calls; an unresolvable alias is its own host."""
    text = str(name).strip()
    if "@" in text:
        return _host_key(text.rpartition("@")[2])
    hosts = {} if hosts is None else hosts
    if text not in hosts:
        hosts[text] = _host_key(ssh_hostname(roster, text, run=run) or "")
    return hosts[text] or _host_key(text)


def record_box(roster, alias, path, hosts, run=subprocess.run):
    """The box a record serves: its stamped `box`, else resolved once and written back so the next run spawns nothing."""
    if "@" in alias:
        return box_key(roster, alias, hosts, run)
    rec = read_record(path)
    stamped = rec.get("box")
    if isinstance(stamped, str) and stamped:
        hosts.setdefault(alias, stamped)
        return stamped
    box = box_key(roster, alias, hosts, run)
    if rec and hosts.get(alias):  # an unresolved alias (ssh -G failed) is never stamped as its own box
        rec["box"] = box
        try:
            roster.write_json_atomic(str(path), rec)
        except OSError:
            pass
    return box


def resolve_record_boxes(roster, entries, hosts, run=subprocess.run):
    """Fill `hosts` for every bare-alias record that is neither stamped nor cached, resolving them concurrently.

    `ssh -G` takes one destination per call, so the unresolved set costs one spawn each, once, in parallel
    (a stamped or `user@host` record costs none); the grouping loop that follows then spawns nothing."""
    pending = sorted({a for a, p in entries if "@" not in a and a not in hosts and not read_record(p).get("box")})
    if not pending:
        return
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(8, len(pending))) as pool:
        list(pool.map(lambda alias: box_key(roster, alias, hosts, run), pending))


def group_records(roster, sdir, hosts=None, run=subprocess.run):
    """{box_key: [path]} over every supervisor record, the user@host spelling and canonical file name first."""
    hosts = {} if hosts is None else hosts
    entries = list(record_files(sdir))
    resolve_record_boxes(roster, entries, hosts, run)
    groups = {}
    for alias, path in entries:
        groups.setdefault(record_box(roster, alias, path, hosts), []).append((alias, path))

    def order(item):
        alias, path = item
        return ("@" not in alias, path != record_path(sdir, alias), alias)
    return {box: [p for _, p in sorted(items, key=order)] for box, items in groups.items()}


def pair_live(roster, rec):
    """True when both supervisors of a record are the processes that were started."""
    return all(supervisor_live(roster, rec.get(role) or {}) for role, _ in SUPERVISORS)


def _pids(rec):
    return {(rec.get(role) or {}).get("pid") for role, _ in SUPERVISORS} - {None}


def _spelling_lock_held(sdir, paths) -> bool:
    """True when a fresh per-link lock named by the `link_key` of any record in `paths` exists (never taken or removed here)."""
    wanted = {Path(p) for p in paths}
    for alias, path in record_files(sdir):
        if Path(path) not in wanted:
            continue
        lock = Path(sdir) / f"autolink-{slug(link_key(alias))}.lock"
        try:
            if time.time() - os.path.getmtime(lock) < LOCK_STALE_SECONDS:
                return True
        except OSError:
            continue
    return False


def stop_duplicate_pairs(roster, sdir, say, kill=None, hosts=None):
    """Keep one live supervisor pair per `box_key`; stop every other live supervisor and drop its record.

    The kept pair is the first live one, the canonical record's before any other. A record sharing the kept
    pair's pids is a stale copy of it: removed without a kill. A stop needs pid plus procStart to match."""
    kill = kill or roster.tree_kill
    for key, paths in group_records(roster, sdir, hosts).items():
        if len(paths) < 2:
            continue
        lock = Path(sdir) / f"autolink-{slug(key)}.lock"
        if _spelling_lock_held(sdir, paths) or not acquire_lock(lock):  # a link is mid-spawn; the next start cleans up
            continue
        try:
            recs = [(p, read_record(p)) for p in paths]
            kept = next(((p, r) for p, r in recs if pair_live(roster, r)), None)
            if kept is None:
                continue
            for path, rec in recs:
                if path == kept[0]:
                    continue
                stopped = []
                if not _pids(rec) <= _pids(kept[1]):
                    for role, _ in SUPERVISORS:
                        entry = rec.get(role) or {}
                        if entry.get("pid") not in _pids(kept[1]) and supervisor_live(roster, entry):
                            kill(entry["pid"])
                            stopped.append(f"{role} pid {entry['pid']}")
                try:
                    os.remove(path)
                except OSError:
                    pass
                if stopped:
                    say(f"far box {key}: duplicate supervisor pair stopped ({', '.join(stopped)}); kept {kept[0].name}")
        finally:
            try:
                os.remove(lock)
            except OSError:
                pass


def _unresolved_alias(sdir, path, hosts):
    """True for a bare-alias record whose box never resolved (`ssh -G` failed): its identity is a guess, never retired on."""
    alias = next((a for a, p in record_files(sdir) if p == path), "")
    return "@" not in alias and not hosts.get(alias)


def retire_non_targets(roster, sdir, say, targets, kill=None, hosts=None):
    """Stop and retire every supervisor record whose box is not a `box_key` of `targets`.

    An empty `targets` retires nothing: it is how a failed or missing target read looks. A record moves to
    `<sdir>/retired/`; a supervisor is stopped only when pid plus procStart still match. A box whose link
    lock is held is left for the next run."""
    if not targets:
        return
    kill = kill or roster.tree_kill
    hosts = {} if hosts is None else hosts
    groups = group_records(roster, sdir, hosts)
    wanted = {box_key(roster, t, hosts) for t in targets}
    for key, paths in groups.items():
        if key in wanted:
            continue
        paths = [p for p in paths if not _unresolved_alias(sdir, p, hosts)]
        if not paths:
            continue
        lock = Path(sdir) / f"autolink-{slug(key)}.lock"
        if not acquire_lock(lock):
            continue
        try:
            for path in paths:
                rec = read_record(path)
                stopped = []
                for role, _ in SUPERVISORS:
                    entry = rec.get(role) or {}
                    if supervisor_live(roster, entry):
                        kill(entry["pid"])
                        stopped.append(f"{role} pid {entry['pid']}")
                try:
                    (Path(sdir) / "retired").mkdir(exist_ok=True)
                    os.replace(path, Path(sdir) / "retired" / Path(path).name)
                except OSError:
                    continue
                say(f"far box {key}: record {Path(path).name} retired, no longer a link target"
                    + (f"; stopped {', '.join(stopped)}" if stopped else ""))
        finally:
            try:
                os.remove(lock)
            except OSError:
                pass


def reap_unrecorded(roster, sdir, say, kill=None, hosts=None):
    """Stop every live supervisor that names itself in a `supervisor-<pid>.json` stamp but sits in no record.

    A stamp is `{pid, procStart, remote}` written by `link_peer` at each spawn. A dead or reused pid
    drops its stamp without a kill; a recorded pid is left alone; a box whose link lock is held is
    left for the next run. Needs no process-table scan: only stamp files and `supervisor_live`."""
    kill = kill or roster.tree_kill
    hosts = {} if hosts is None else hosts
    recorded = set()
    for _, path in record_files(sdir):
        recorded |= _pids(read_record(path))
    for stamp in sorted(Path(sdir).glob(STAMP_GLOB)):
        entry = read_record(stamp)
        if not supervisor_live(roster, entry):
            try:
                os.remove(stamp)
            except OSError:
                pass
            continue
        if entry["pid"] in recorded:
            continue
        remote = entry.get("remote")
        box = box_key(roster, remote, hosts) if isinstance(remote, str) and remote else "unknown"
        lock = Path(sdir) / f"autolink-{slug(box)}.lock"
        if not acquire_lock(lock):
            continue
        try:
            if not supervisor_live(roster, entry):
                continue
            kill(entry["pid"])
            say(f"far box {box}: supervisor pid {entry['pid']} outside any record stopped")
            try:
                os.remove(stamp)
            except OSError:
                pass
        finally:
            try:
                os.remove(lock)
            except OSError:
                pass


def _link_down_since(roster, remote) -> float | None:
    """Epoch seconds `remote`'s link-state record has read down; None when up or absent, 0.0 when its stamp is unreadable."""
    rec = read_record(roster.link_state_path(remote))
    if rec.get("state") != "down":
        return None
    try:
        return float(calendar.timegm(time.strptime(rec.get("since"), "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return 0.0


def stop_stale_supervisors(roster, sdir, say, now) -> list:
    """Ask every record's live supervisors to exit when the link-state reads down past STALE_LINK_SECONDS; the aliases asked.

    Stale means alive yet deaf: the youngest live supervisor of the record is older than the window and its
    link-state has read down at least as long, so a pair just started is never judged before it could recover.
    The ask is a stop request, never a kill; the next pass finds the pids gone and relinks."""
    asked = []
    for alias, path in record_files(sdir):
        rec = read_record(path)
        live = [(role, rec[role]) for role, _ in SUPERVISORS if supervisor_live(roster, rec.get(role) or {})]
        if not live:
            continue
        down, youngest, remote = None, 0.0, alias
        for role, entry in live:
            stamp_path = Path(sdir) / f"supervisor-{entry['pid']}.json"
            seen = read_record(stamp_path).get("remote")
            since = _link_down_since(roster, seen if isinstance(seen, str) and seen else alias)
            if since is not None and down is None:
                down, remote = since, seen if isinstance(seen, str) and seen else alias
            try:
                youngest = max(youngest, os.path.getmtime(stamp_path))
            except OSError:
                youngest = max(youngest, os.path.getmtime(path))
        if down is None or now - down < STALE_LINK_SECONDS or now - youngest < STALE_LINK_SECONDS:
            continue
        for role, entry in live:
            if not roster.stop_request_path(entry["pid"]).exists():
                roster.request_stop(entry["pid"], entry.get("procStart"), role, remote)
        say(f"far box {alias}: supervisors alive but link {remote} down {int(now - down)}s; asked to stop, relinks next pass")
        asked.append(alias)
    return asked


def stop_supervisors(roster, sdir, say) -> list:
    """Ask every record's live supervisors to exit; the aliases asked.

    A supervisor keeps the code and environment it started with, so an install that replaced the roster or
    bridge code calls this and the next link pass relinks on the new code. The ask is a stop request, never a kill."""
    asked = []
    for alias, path in record_files(sdir):
        rec = read_record(path)
        for role, _ in SUPERVISORS:
            entry = rec.get(role) or {}
            if not supervisor_live(roster, entry) or roster.stop_request_path(entry["pid"]).exists():
                continue
            seen = read_record(Path(sdir) / f"supervisor-{entry['pid']}.json").get("remote")
            roster.request_stop(entry["pid"], entry.get("procStart"), role, seen if isinstance(seen, str) and seen else alias)
            if alias not in asked:
                asked.append(alias)
        if alias in asked:
            say(f"far box {alias}: supervisors asked to stop on replaced code; they relink on the next pass")
    return asked


def pull_due(liveness, sdir, now):
    """True when no off-snapshot pull has been stamped within PULL_SOURCES_INTERVAL_SECONDS."""
    at = liveness.read_record(Path(sdir) / PULL_STAMP_NAME).get("at")
    if not isinstance(at, (int, float)) or isinstance(at, bool):
        return True
    return not 0 <= now - at < PULL_SOURCES_INTERVAL_SECONDS


def pull_new_epoch(roster, sdir, liveness, say, key_fn, agent_fn, pull_fn, lookup, membership, self_names, now):
    """Ask each off-snapshot alias for `membership get`; True when any adopted a higher epoch.

    Stamps the throttle first, so a failing round still waits out the interval. A refused or unreachable
    source is logged and never stops the next. `lookup` carries the registry aliases to the link pass."""
    roster.write_json_atomic(str(Path(sdir) / PULL_STAMP_NAME), {"at": now})
    status, names, _, _, _ = split_members(roster, membership, self_names)
    if status == "bad":
        return False
    aliases = lookup["aliases"] = far_boxes_status(roster)[0]
    hosts = lookup.setdefault("hosts", {})
    held = [*names, *(member_alias(roster, r, r.rpartition("@")[2], aliases, hosts) for r in names)]
    adopted = False
    for remote in pull_sources(held, aliases, record_aliases(sdir)):
        try:
            key = key_fn(roster, remote)
            if not Path(key).is_file():
                continue
            verdict = agent_fn(key)
            if verdict in ("locked", "missing"):
                say(f"far box {remote}: membership pull skipped: key not loaded ({verdict})")
                continue
            adopted = bool(pull_fn(roster, remote, key)) or adopted
        except Exception as ex:  # a refused or malformed peer snapshot never blocks the next source
            say(f"far box {remote}: membership pull skipped: {type(ex).__name__}: {str(ex)[:100]}")
    return adopted


def _ssh_config_lines(path, depth=0):
    """`(keyword, value)` of each non-comment line of an ssh config file, `Include`s expanded in place."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for raw in text.splitlines():
        m = re.match(r"(\S+?)(?:\s*=\s*|\s+)(.*)$", raw.split("#", 1)[0].strip())
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2).strip()
        if key == "include" and depth < 4:
            for pat in val.split():
                pat = os.path.expanduser(pat)
                pat = pat if os.path.isabs(pat) else str(Path(os.path.expanduser("~/.ssh")) / pat)
                for inc in sorted(Path(pat).parent.glob(Path(pat).name)):
                    yield from _ssh_config_lines(inc, depth + 1)
        else:
            yield key, val


def ssh_hostname(roster, alias, run=None):
    """The HostName `alias` resolves to, read in-process from the ssh config (zero spawns, where `ssh -G`
    cost one per alias): the first matching `Host` block's HostName with `%h` expanded, else None.
    Trap: `Match` blocks are not evaluated; their lines are skipped, never applied to the alias.
    `roster` and `run` stay for the callers' signature."""
    live = True
    for key, val in _ssh_config_lines(Path(os.path.expanduser("~/.ssh")) / "config"):
        if key == "host":
            pats = val.split()
            live = any(fnmatch.fnmatchcase(alias, p) for p in pats if not p.startswith("!")) and not any(
                fnmatch.fnmatchcase(alias, p[1:]) for p in pats if p.startswith("!"))
        elif key == "match":
            live = False
        elif key == "hostname" and live and val:
            return val.replace("%h", alias).strip('"')
    return None


def matching_aliases(roster, host, aliases, hosts=None, run=subprocess.run, entries=None) -> Iterator[str]:
    """Yield each alias in `aliases` that names `host`, name or HostName matches first.

    An alias qualifies when its own name or its `ssh -G` HostName equals `host` (case-insensitive,
    `.local` ignored); else when a known_hosts host key recorded for the alias or its HostName equals one
    recorded for `host`. Trap: the second rule is what keeps an alias whose HostName is pinned to an IP
    matching; without it the link silently falls back to the default key. `hosts` caches alias ->
    normalised HostName across calls. Lazy: a caller taking the first match costs no further `ssh -G`."""
    if not host:
        return
    hosts = {} if hosts is None else hosts
    want = _host_key(host)
    named = set()
    for alias in aliases:
        if alias not in hosts:
            hosts[alias] = _host_key(ssh_hostname(roster, alias) or "")
        if _host_key(alias) == want or hosts[alias] == want:
            named.add(alias)
            yield alias
    entries = _known_hosts_entries() if entries is None else entries
    recorded = known_host_keys([host], entries)
    if recorded:
        for alias in aliases:
            if alias not in named and recorded & known_host_keys([alias, hosts[alias]], entries):
                yield alias


def member_alias(roster, box, host, aliases, hosts=None, run=subprocess.run, entries=None) -> str:
    """The first of `matching_aliases` for member `box` at `host`, else `box`."""
    return next(matching_aliases(roster, host, aliases, hosts, run, entries), box)


def router_lock_held(sdir):
    """True while a router process holds `<state>/router/router.lock` (its lifetime lease), however it was started."""
    path = sdir / "router" / "router.lock"
    try:
        transport = _core_module("transport")
        with open(path, "r+b" if sys.platform == "win32" else "rb") as fh:
            if not transport.lock_file(fh):
                return True
            transport.unlock_file(fh)
    except (OSError, ImportError):
        pass
    return False


def supervise_router(roster, sdir, say, spawn=detached, lock_held_fn=None):
    """Start the box's one peer router when it is down. Independent of any far-box alias.

    Live means the recorded pid is the same process, else the router's own lease is held (a router
    started by hand). A dead router is respawned under a per-box lock so two session starts never both spawn."""
    if os.environ.get(NO_ROUTER_ENV):
        return
    rec_path = sdir / "autolink-router.json"
    if supervisor_live(roster, read_record(rec_path)):
        return
    lock = sdir / "autolink-router.lock"
    if not acquire_lock(lock):
        return
    try:
        rec = read_record(rec_path)
        if supervisor_live(roster, rec) or (lock_held_fn or router_lock_held)(sdir):
            return
        p = spawn([pinned_python(roster), str(HERE / ROUTER_SCRIPT)])
        try:
            stamp = roster.proc_start(p.pid)
        except (OSError, subprocess.SubprocessError):
            stamp = None
        roster.write_json_atomic(str(rec_path), {"pid": p.pid, "procStart": stamp})
        say(f"peer router was down; started pid {p.pid}")
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


class RouterRestartError(RuntimeError):
    """The old router could not be stopped, or no new router was started."""


def _router_request():
    """Default shutdown requester: one `shutdown` line to the box router's private endpoint."""
    spec = importlib.util.spec_from_file_location("unimatrix_peer_router", HERE / ROUTER_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ctl = mod.endpoint_path(mod.ROUTER_ENDPOINT_SEED)
    return lambda req: mod.request_line(ctl, req, timeout=5)


def router_pid_candidates(roster, sdir):
    """(pid, procStart) the running router may be recorded under: its own record, autolink's, then face stamps."""
    out = []
    for rec in (read_record(sdir / "router" / "router.pid.json"), read_record(sdir / "autolink-router.json")):
        out.append((rec.get("pid"), rec.get("procStart")))
    try:
        paths = sorted(Path(roster.sessions_dir()).glob("*.json"))
    except OSError:
        paths = []
    for path in paths:
        entry = read_record(path)
        out.append((entry.get("unimatrixRouterPid"), entry.get("unimatrixRouterStart")))
    seen, uniq = set(), []
    for pid, stamp in out:
        if type(pid) is int and pid > 0 and stamp and (pid, stamp) not in seen:
            seen.add((pid, stamp))
            uniq.append((pid, stamp))
    return uniq


def run_launchctl(*args):
    """Run launchctl; None when it cannot launch."""
    try:
        return subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None


def launchd_agent_target(launchctl=None, platform=None, uid=None):
    """`gui/<uid>/<label>` when this is darwin and the login agent is loaded, else None.

    A router launchd starts runs at the agent's niceness; a child of the caller inherits the caller's."""
    if (platform or sys.platform) != "darwin":
        return None
    target = f"gui/{uid if uid is not None else os.getuid()}/{LOGIN_AGENT_LABEL}"
    loaded = (launchctl or run_launchctl)("print", target)
    return target if loaded is not None and loaded.returncode == 0 else None


def niced_router_warning(pid, agent_label=None, nice_fn=None):
    """A loud line when a directly spawned router inherited this caller's positive nice, else None.
    Trap: an unprivileged child cannot lower its nice, so only a launchd start (or a nice-0 caller) clears it."""
    try:
        nice = (nice_fn or (lambda: os.getpriority(os.PRIO_PROCESS, 0)))()
    except (AttributeError, OSError):
        return None
    if nice <= 0:
        return None
    uid = os.getuid() if hasattr(os, "getuid") else "$(id -u)"  # win32 has no getuid; the fix line is darwin advice
    fix = (f"stop it, then `launchctl kickstart gui/{uid}/{agent_label}`" if agent_label
           else "stop it and restart from a nice-0 shell")
    return f"WARNING: peer router pid {pid} runs at nice {nice}, inherited from this caller; {fix}"


def _kickstart_and_wait(target, rec_path, launchctl, say, wait_seconds):
    """Kickstart the agent so launchd starts the router; False when launchctl refuses or no router record
    appears within wait_seconds (a kickstart is a no-op while the agent job is mid-run); caller falls back."""
    started = launchctl("kickstart", target)
    if started is None or started.returncode != 0:
        say(f"launchctl kickstart {target} failed; starting the router directly")
        return False
    deadline = time.monotonic() + wait_seconds
    while not isinstance(read_record(rec_path).get("pid"), int):
        if time.monotonic() >= deadline:
            say(f"launchd agent {target} wrote no router record in {wait_seconds}s; starting the router directly")
            return False
        time.sleep(0.05)
    say(f"peer router started by launchd agent {target}")
    return True


def restart_router(roster, sdir, say, spawn=detached, request=None, kill=None, lock_held_fn=None, wait_seconds=10,
                   launchctl=None, platform=None, uid=None):
    """Replace the box's peer router with the installed one: {"stopped", "old_pid", "new_pid"}.

    On darwin with the login agent loaded the new router is started by `launchctl kickstart` of that agent,
    not as a child of the caller; otherwise it is a detached spawn.

    A live router is asked to `shutdown` over its control endpoint; one that predates the op, or does not
    answer, is tree-killed by a recorded pid whose process start still matches (that takes its faces with it).
    Raises RouterRestartError when the old lease stays held or no new router record appears."""
    lock_held_fn = lock_held_fn or router_lock_held
    kill = kill or roster.tree_kill
    lease = sdir / "router" / "router.lock"

    def lease_freed():
        deadline = time.monotonic() + wait_seconds
        while lock_held_fn(sdir):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)
        return True

    stopped, old_pid = "none", None
    if lock_held_fn(sdir):
        try:
            reply = (request or _router_request())({"op": "shutdown"})
        except (OSError, ValueError):
            reply = {}
        if reply.get("ok") is True:
            stopped, old_pid = "handshake", reply.get("pid")
            say(f"router pid {old_pid} acknowledged shutdown")
        if stopped == "none" or not lease_freed():
            verified = [pid for pid, stamp in router_pid_candidates(roster, sdir)
                        if roster.pid_alive(pid) and roster.proc_start(pid) == stamp]
            if not verified:
                named = ", ".join(str(p) for p, _ in router_pid_candidates(roster, sdir)) or "none recorded"
                raise RouterRestartError(
                    f"router lease {lease} is held and no recorded router pid ({named}) matches its process start")
            old_pid = verified[0]
            say(f"router did not shut down by request; killing pid {old_pid} and its faces")
            kill(old_pid)
            stopped = "tree_kill"
            if not lease_freed():
                raise RouterRestartError(f"router pid {old_pid} still holds lease {lease} after {wait_seconds}s")
    rec_path = sdir / "autolink-router.json"
    if stopped != "none" or not supervisor_live(roster, read_record(rec_path)):
        try:
            os.remove(rec_path)
        except OSError:
            pass
    target = None
    if not supervisor_live(roster, read_record(rec_path)) and not lock_held_fn(sdir):
        target = launchd_agent_target(launchctl, platform, uid)
    started_by_launchd = bool(target and _kickstart_and_wait(target, rec_path, launchctl or run_launchctl, say, wait_seconds))
    if not started_by_launchd:
        saved = os.environ.pop(NO_ROUTER_ENV, None)
        try:
            supervise_router(roster, sdir, say, spawn=spawn, lock_held_fn=lock_held_fn)
        finally:
            if saved is not None:
                os.environ[NO_ROUTER_ENV] = saved
    new_pid = read_record(rec_path).get("pid")
    if not isinstance(new_pid, int):
        raise RouterRestartError(f"no router was started: {rec_path} was not written")
    if not started_by_launchd:
        warning = niced_router_warning(new_pid, LOGIN_AGENT_LABEL if target else None)
        if warning:
            say(warning)
    return {"stopped": stopped, "old_pid": old_pid, "new_pid": new_pid}


def _epoch_moved(sdir, liveness):
    """True when a stored snapshot's epoch differs from the one the boxes cache was written at."""
    try:
        epoch = json.loads((sdir / "membership" / "snapshot.json").read_text(encoding="utf-8")).get("epoch")
    except (OSError, ValueError, AttributeError):
        return False
    return liveness.read_record(sdir / liveness.CACHE_NAME).get("epoch") != epoch


class LinkSummary(list):
    """One link pass: a `{alias, roles_started, reason}` entry per target alias that needed a link.

    `reason` is None when the alias's pair is now live, else why it is not. `pending` names the aliases a
    later pass may still link (a retryable reason); a missing key or an unloaded key is final and not listed."""

    def __init__(self) -> None:
        super().__init__()
        self.pending = []

    def add(self, alias, roles, reason, retry=True) -> None:
        self.append({"alias": alias, "roles_started": list(roles), "reason": reason})
        if reason and retry and alias not in self.pending:
            self.pending.append(alias)


def spawn_lines(summary) -> list:
    """The stdout line per alias that had supervisors started: `spawned bridge+inbox pair for <alias>`."""
    out = []
    for item in summary:
        roles = item["roles_started"]
        if len(roles) == len(SUPERVISORS):
            out.append(f"spawned {'+'.join(roles)} pair for {item['alias']}")
        elif roles:
            out.append(f"spawned {'+'.join(roles)} supervisor for {item['alias']}")
    if not out:
        unlinked = [f"{i['alias']} ({i['reason']})" for i in summary if i["reason"] and i["reason"] != "parked"]
        if unlinked:
            out.append(UNLINKED_PREFIX + ", ".join(unlinked))
    return out


def run(roster=None, boxes=None, spawn=detached, probe_fn=probe, key_fn=None, stable_fn=None, now=None,
        membership=None, pull_fn=None, self_names=None, agent_fn=None, kill=None, mdns_fn=None, alias_fn=None,
        ignore_backoff=False, lan_fn=None) -> LinkSummary:
    """Link every far box whose supervisors are down. A healthy box returns after reading records only.

    Returns the LinkSummary of the pass. `ignore_backoff` probes an alias inside its probe backoff too (the
    boot window and an explicit restart, where an earlier failure predates the network).

    Explicit `boxes` are ssh aliases and bypass the snapshot. Otherwise the verified membership snapshot
    (minus this box) supplies `<user>@<host>` targets and `unimatrix.far_boxes` is read only when no
    snapshot is stored. Per alias the record check precedes key resolution, and an alias inside its probe
    backoff is skipped. The boxes cache short-circuits `healthy` for up to 24h unless the snapshot epoch
    moved since it was written."""
    custom_key_fn = key_fn is not None
    key_fn = key_fn or resolve_key
    agent_fn = agent_fn or agent_state
    roster = roster or _roster()
    liveness = _liveness()
    sdir = state_dir(roster)
    sdir.mkdir(parents=True, exist_ok=True)
    summary = LinkSummary()

    def say(msg):
        with open(sdir / "autolink.log", "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}\n")

    try:  # the router is one per box: checked before, and regardless of, the far-box healthy short-circuit
        supervise_router(roster, sdir, say, spawn=spawn)
    except Exception as ex:  # a router failure must not stop the far links or fail the session
        say(f"peer router supervision failed: {type(ex).__name__}: {str(ex)[:120]}")
    lookup = {}
    hosts = lookup.setdefault("hosts", {})
    try:  # one live pair per box: a second spelling of the same box is stopped even when every link reads healthy
        stop_duplicate_pairs(roster, sdir, say, kill, hosts)
    except Exception as ex:  # duplicate cleanup must not stop the links or fail the session
        say(f"duplicate supervisor cleanup failed: {type(ex).__name__}: {str(ex)[:120]}")
    try:  # a supervisor outside every record (a respawn whose record was lost) is stopped on every run
        reap_unrecorded(roster, sdir, say, kill, hosts)
    except Exception as ex:  # orphan cleanup must not stop the links or fail the session
        say(f"orphan supervisor cleanup failed: {type(ex).__name__}: {str(ex)[:120]}")
    clock = time.time() if now is None else now
    try:  # a pair alive but deaf is asked to exit before the health short-circuit can pass it as live
        stale = stop_stale_supervisors(roster, sdir, say, clock)
    except Exception as ex:  # stale cleanup must not stop the links or fail the session
        stale = []
        say(f"stale supervisor check failed: {type(ex).__name__}: {str(ex)[:120]}")
    for alias in stale:
        summary.add(alias, [], "stale link; supervisors asked to stop")
    healthy = liveness.healthy(sdir, now) and not _epoch_moved(sdir, liveness) and not stale
    if boxes is None and pull_due(liveness, sdir, clock):
        try:
            adopted = pull_new_epoch(roster, sdir, liveness, say, key_fn, agent_fn, pull_fn or pull_membership,
                                     lookup, membership, self_names, clock)
        except Exception as ex:  # the off-snapshot pull is best effort and never fails the session
            adopted = False
            say(f"off-snapshot membership pull failed: {type(ex).__name__}: {str(ex)[:120]}")
        healthy = healthy and not adopted
    if healthy:
        if boxes is None:  # the last written target list is the predicate: no snapshot read, no spawn
            cached = liveness.read_record(sdir / liveness.CACHE_NAME).get("aliases")
            try:
                if isinstance(cached, list) and all(isinstance(a, str) for a in cached):
                    retire_non_targets(roster, sdir, say, cached, kill, hosts)
            except Exception as ex:  # retirement must not fail the session
                say(f"record retirement failed: {type(ex).__name__}: {str(ex)[:120]}")
        return summary

    reason = NO_ALIAS_REASON
    explicit = boxes is not None
    names, epoch, snapshot_mode = {}, None, False
    if boxes is None:
        status, names, skipped, epoch, why = split_members(roster, membership, self_names)
        if status == "bad":
            say(why)
            return summary
        if status == "ok":
            for box, remote in skipped:
                say(f"member {box}: dial name {remote!r} is not a hostname alias (fails the alias check or is an IP literal); not linked")
            snapshot_mode, boxes = True, list(names)
            reason = "membership snapshot lists no other member; no supervisors started"
        else:
            boxes, reason = far_boxes_status(roster, guard=True)
            if boxes:
                say("linking from unimatrix.far_boxes: no membership snapshot is stored; unimatrix doctor will flag it")

    def write_cache(aliases):
        data = {"aliases": list(aliases)}
        if snapshot_mode:
            data["epoch"] = epoch
        roster.write_json_atomic(str(sdir / liveness.CACHE_NAME), data)

    if not boxes:
        say(reason or NO_ALIAS_REASON)
        if snapshot_mode or (reason or NO_ALIAS_REASON) == NO_ALIAS_REASON:
            write_cache([])
        return summary
    write_cache(boxes)
    if snapshot_mode:  # the registry fallback is a transition list, not authority to retire a box's live pair
        try:
            retire_non_targets(roster, sdir, say, boxes, kill, hosts)
        except Exception as ex:  # retirement must not fail the session
            say(f"record retirement failed: {type(ex).__name__}: {str(ex)[:120]}")

    if snapshot_mode:
        stable_fn = stable_fn or (lambda alias: None)
        pull_fn = pull_fn or pull_membership
    else:
        pull_fn = None

    mdns_end = time.monotonic() + 2 * MDNS_SECONDS

    def shared_mdns(name):  # one pass shares a deadline: many down boxes never multiply the wait
        if mdns_fn:
            return mdns_fn(name)
        left = mdns_end - time.monotonic()
        return mdns_a_records(name, left) if left > 0.05 else []

    def link_all(aliases) -> None:
        pending, seen = [], set()
        groups = group_records(roster, sdir, hosts)
        for alias in aliases:
            try:
                key = box_key(roster, alias, hosts)
                if key in seen:  # another spelling (alias or user@host) of this box is already handled
                    continue
                seen.add(key)
                if any(pair_live(roster, read_record(p)) for p in groups.get(key, [])):
                    continue
                if liveness.is_parked(sdir, alias):  # a PM-held park outranks ignore_backoff; only release ends it
                    summary.add(alias, [], "parked", retry=False)
                    continue
                if not ignore_backoff and liveness.backoff_until(sdir, alias) > clock:
                    summary.add(alias, [], "probe backoff")
                    continue
                pending.append(alias)
            except Exception as ex:  # one peer's failure must not stop the next or fail the session
                say(f"far box {alias} link failed: {type(ex).__name__}: {str(ex)[:120]}")
                summary.add(alias, [], f"link failed: {type(ex).__name__}")
        if snapshot_mode and pending:
            try:
                if "aliases" not in lookup:
                    lookup["aliases"] = far_boxes_status(roster)[0]
            except Exception as ex:  # noqa: BLE001 -- the registry read is shared by every pending alias
                say(f"far box lookup failed: {type(ex).__name__}: {str(ex)[:120]}")
                for alias in pending:
                    summary.add(alias, [], f"far box lookup failed: {type(ex).__name__}")
                return
        for alias in pending:
            try:
                target = names.get(alias, alias)
                via = None
                if snapshot_mode:
                    host = alias.rpartition("@")[2]
                    target = member_alias(roster, target, host, lookup["aliases"], hosts)
                    via = lambda host=host: matching_aliases(roster, host, lookup["aliases"], hosts)  # noqa: E731
                key = key_fn(roster, target) if custom_key_fn else resolve_key(roster, target, via=via)
                if not Path(key).is_file():
                    # A configured alias with no key is a misconfiguration worth one line, not silence.
                    say(f"far box {alias}: no Unimatrix-Zero key (looked for {key}); not linked")
                    liveness.note_keyless(sdir, alias, clock)
                    summary.add(alias, [], "no relay key", retry=False)
                    continue
                verdict = agent_fn(key)
                if verdict == "locked":  # a named wait: no probe, no backoff charge
                    say(f"far box {alias}: waiting: 1Password locked")
                    summary.add(alias, [], "1Password locked")
                    continue
                if verdict == "missing":
                    say(f"far box {alias}: passphrase_source_missing: op CLI or unimatrix.passphrase_vault "
                        f"unavailable; encrypted key {key} not loaded")
                    summary.add(alias, [], "passphrase source missing", retry=False)
                    continue
                started = link_peer(roster, alias, key, say, spawn=spawn, probe_fn=probe_fn, stable_fn=stable_fn,
                                    now=now, liveness=liveness, pull_fn=pull_fn, mdns_fn=shared_mdns,
                                    alias_fn=alias_fn, hosts=hosts, lan_fn=lan_fn)
                summary.add(alias, started or [], getattr(started, "reason", None))
            except Exception as ex:  # one peer's failure must not stop the next or fail the session
                say(f"far box {alias} link failed: {type(ex).__name__}: {str(ex)[:120]}")
                summary.add(alias, [], f"link failed: {type(ex).__name__}")

    link_all(boxes)
    if not snapshot_mode:
        return summary
    try:
        status, names2, epoch2, _ = member_targets(roster, membership, self_names)
    except Exception:  # noqa: BLE001 -- the second look is best effort
        return summary
    if status == "ok" and epoch2 != epoch:
        names.update(names2)
        epoch = epoch2
        write_cache(names2)
        link_all([a for a in names2 if a not in boxes])
    return summary


DEFERRED_HOSTS_FILE = "deferred-hosts.json"  # mirrors unimatrix-install.py DEFERRED_HOSTS_FILE; read here without importing it
HOST_REPLAYS = {"codex-hook-trust": "codex", "agy-plugin-install": "agy"}
_REPLAY_TRIED = set()


def _deferred_marker(sdir) -> dict:
    """{host: {"actions": [...]}} from `<sdir>/deferred-hosts.json`; {} when absent or unreadable."""
    hosts = read_record(Path(sdir) / DEFERRED_HOSTS_FILE).get("hosts")
    return {h: v for h, v in hosts.items() if isinstance(v, dict)} if isinstance(hosts, dict) else {}


def _load_install() -> object:
    spec = importlib.util.spec_from_file_location("_al_unimatrix_install_replay", HERE / "unimatrix-install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def replay_deferred_hosts(roster, which=None, load_install=None, clone_bin=_clone_bin, say=print) -> list:
    """Run the install work a host's absent CLI deferred, once its CLI is on PATH; returns the hosts cleared.

    The common path (no marker, or no deferred CLI arrived) is one file read and one `which` per deferred
    host, never an import of unimatrix-install or a spawn. A host is tried at most once per process (a
    `--boot` run repeats link passes). Codex replays `trust_codex_hook`; agy replays the strict agy
    enrollment with consent given, since the install that staged it already had the operator's consent. A
    failure leaves the marker entry for the next login and prints one stderr line. Never raises."""
    import shutil
    which = which or shutil.which
    sdir = state_dir(roster)
    try:
        marker = _deferred_marker(sdir)
        arrived = {}
        for host, entry in marker.items():
            acts = [a for a in entry.get("actions", []) if HOST_REPLAYS.get(a) == host]
            if acts and host not in _REPLAY_TRIED and which(host):
                arrived[host] = acts
        if not arrived:
            return []
        _REPLAY_TRIED.update(arrived)
        mod = (load_install or _load_install)()
    except Exception as ex:
        print(f"autolink: deferred-host replay failed: {type(ex).__name__}: {str(ex)[:200]}", file=sys.stderr)
        return []
    cleared = []
    for host, acts in arrived.items():
        try:
            if "codex-hook-trust" in acts:
                ok, note = mod.trust_codex_hook(mod.codex_hooks_path(), dest_dir=sdir)
            else:
                bin_dir = clone_bin(_home(roster))
                if bin_dir is None:
                    raise RuntimeError("no klabauter clone resolves for the agy plugin install")
                import io
                buf = io.StringIO()
                ok = mod.enroll_agy_runtime(bin_dir.parent.parent, consent=True, dest_dir=sdir, out=buf) == 0
                note = (buf.getvalue().strip().splitlines() or ["agy enrollment refused"])[-1]
            if not ok:
                raise RuntimeError(note)
            mod.record_deferred_hosts(sdir, [], [host])
            cleared.append(host)
            say(f"autolink: {host} CLI arrived; deferred install replayed ({note})")
        except Exception as ex:
            print(f"autolink: {host} deferred install replay failed, retried next login: "
                  f"{type(ex).__name__}: {str(ex)[:200]}", file=sys.stderr)
    return cleared


def link_pass(out=print, **kw) -> LinkSummary | None:
    """One `run()` with its spawn lines printed; a raised failure is one stderr line. The summary, else None."""
    try:
        roster = kw.get("roster") or _roster()
        refresh_installed_copies(roster)
        replay_deferred_hosts(roster, say=out)
        summary = run(**kw)
    except Exception as ex:
        print(f"autolink failed: {type(ex).__name__}: {str(ex)[:200]}", file=sys.stderr)
        return None
    for line in spawn_lines(summary):
        out(line)
    return summary


def cmd_restart() -> int:
    roster = _roster()
    sdir = state_dir(roster)
    sdir.mkdir(parents=True, exist_ok=True)
    try:
        res = restart_router(roster, sdir, print)
    except (RouterRestartError, OSError) as ex:
        print(f"router restart failed: {ex}", file=sys.stderr)
        return 1
    print(f"router restarted: {res['stopped']} old pid {res['old_pid']} new pid {res['new_pid']}")
    link_pass(roster=roster, ignore_backoff=True)
    return 0


def cmd_boot(sleep=time.sleep, clock=time.monotonic, out=print) -> int:
    """Link pass every BOOT_POLL_SECONDS until every target has a live pair or BOOT_WINDOW_SECONDS ends; exit 0.

    A pass that raises is retried like an unreachable box. Backoff is bypassed on every pass: a failure
    charged before the network came up must not make the next pass skip that box."""
    start = clock()
    held = []

    def collect(line) -> None:  # an unlinked-summary line is held: a later poll may still link, so only the last pass speaks
        if line.startswith(UNLINKED_PREFIX):
            held.append(line)
        else:
            out(line)
    while True:
        held.clear()
        summary = link_pass(collect, ignore_backoff=True)
        if summary is not None and not summary.pending:
            for line in held:
                out(line)
            return 0
        left = BOOT_WINDOW_SECONDS - (clock() - start)
        if left <= 0:
            for line in held:
                out(line)
            return 0
        sleep(min(BOOT_POLL_SECONDS, left))


def _box_keys(roster, name, hosts) -> set:
    """Every identity a box name can carry: its `box_key` and its own host spelling.

    Trap: a bare alias resolves through the ssh config (HostName may be an IP), while `user@host.local` keys on
    its own host; matching on `box_key` alone misses one spelling of the same box."""
    host = _host_key(str(name).strip().rpartition("@")[2])
    return {k for k in (box_key(roster, name, hosts), host) if k}


def _box_supervisors(roster, sdir, alias, hosts, alive) -> list:
    """[{pid, procStart, role, remote}] of every live supervisor serving `alias`'s box, records first, then stamps."""
    keys = _box_keys(roster, alias, hosts)
    found, seen = [], set()

    def add(entry, role, remote) -> None:
        pid = entry.get("pid")
        if pid in seen or not alive(entry):
            return
        seen.add(pid)
        found.append({"pid": pid, "procStart": entry.get("procStart"), "role": role or "supervisor", "remote": remote})
    groups = group_records(roster, sdir, hosts)
    for key in sorted(keys):
        for path in groups.get(key, []):
            rec = read_record(path)
            for role, _ in SUPERVISORS:
                add(rec.get(role) or {}, role, alias)
    for path in sorted(Path(sdir).glob(STAMP_GLOB)):
        stamp = read_record(path)
        remote = stamp.get("remote")
        if isinstance(remote, str) and remote and _box_keys(roster, remote, hosts) & keys:
            add(stamp, stamp.get("role") if stamp.get("role") in dict(SUPERVISORS) else None, remote)
    return found


def _links_mid_spawn(sdir, own_lock) -> list:
    """Fresh per-box link locks other than `own_lock`: each is a link_peer mid-spawn through the machine-wide router."""
    held = []
    for path in Path(sdir).glob("autolink-*.lock"):
        if path.name in (Path(own_lock).name if own_lock else "", "autolink-router.lock"):
            continue
        try:
            if time.time() - path.stat().st_mtime < LOCK_STALE_SECONDS:
                held.append(path)
        except OSError:
            continue
    return held


def refresh_installed_copy(sdir, say, installer=None, own_lock=None, **kw) -> bool:
    """Bring the installed Unimatrix copy in `sdir` level with this copy's files and restart a router that runs
    other code (its faces go with it). False, after one line, when the refresh failed; True otherwise.
    A router restart waits while another box's link is mid-spawn (the next roll finds the router stale and restarts it);
    the file copy does not wait, since only this box's lock (held by the caller) guards the install.
    A copy with no installer beside it has nothing to refresh."""
    mid = _links_mid_spawn(sdir, own_lock)
    deferred = []
    if mid and "restart_router" not in kw:
        def defer(dest, say_) -> None:
            deferred.append(dest)
            say_(f"restart-box: router restart deferred: link mid-spawn ({', '.join(p.name for p in mid)})")
        kw["restart_router"] = defer
    try:
        if installer is None:
            path = HERE / "unimatrix-install.py"
            if not path.is_file():
                return True
            spec = importlib.util.spec_from_file_location("unimatrix_install_for_roll", path)
            installer = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(installer)
        done = installer.refresh_installed_copy(HERE, sdir, say, **kw)
    except Exception as exc:  # noqa: BLE001 - any refusal (pipe capability, missing scripts, router restart) is one named line
        say(f"restart-box: installed copy not refreshed: {type(exc).__name__}: {exc}; run unimatrix-install.py --install")
        return False
    if done["copied"]:
        say(f"restart-box: refreshed {len(done['copied'])} installed file(s) in {sdir}")
    if done["router"] is not None and not deferred:
        say(f"restart-box: router restarted: {done['router'].get('stopped')} old pid {done['router'].get('old_pid')} "
            f"new pid {done['router'].get('new_pid')}")
    return True


def cmd_restart_box(alias, wait=STOP_WAIT_SECONDS, link=link_peer, spawn=detached, pid_alive=None, sleep=time.sleep,
                    say=print, roster=None, refresh=None) -> int:
    """Hand a box's supervisors over by stop request: ask each live one to exit, wait, then start one per role.

    Under the box lock, first refreshes the installed Unimatrix copy from this copy and restarts a stale router;
    a held lock refreshes and restarts nothing. Another box's fresh link lock defers the router restart to the next roll,
    and the router restart itself serializes on autolink-router.lock. Never kills a supervisor: one that ignores the request fails the
    verb with no replacement started. Returns 0 only when the refresh held and the box ends with exactly one
    live supervisor per role."""
    roster = roster or _roster()
    sdir = state_dir(roster)
    sdir.mkdir(parents=True, exist_ok=True)
    hosts = {}
    probe_alive = pid_alive or roster.pid_alive

    def alive(entry) -> bool:
        pid = entry.get("pid")
        if not isinstance(pid, int) or not probe_alive(pid):
            return False
        try:
            return roster.proc_start(pid) == entry.get("procStart")
        except (OSError, subprocess.SubprocessError):
            return False
    box = box_key(roster, alias, hosts)
    lock = sdir / f"autolink-{slug(box)}.lock"
    if not acquire_lock(lock):
        say(f"restart-box: link for {alias} mid-spawn")
        return 1
    held = True
    targets = []
    written = []  # only requests this call created: a request already pending belongs to a peer
    try:
        refreshed = refresh(sdir, say) if refresh else refresh_installed_copy(sdir, say, own_lock=lock)
        targets = _box_supervisors(roster, sdir, alias, hosts, alive)
        if not targets:
            say(f"restart-box: no live supervisors found for {alias}; nothing stopped or started")
            return 1
        for t in targets:
            if roster.stop_request_path(t["pid"]).exists():
                continue
            written.append(t)
            roster.request_stop(t["pid"], t["procStart"], t["role"], t["remote"])
        for _ in range(max(1, round(wait / roster.STOP_POLL_SECONDS)) + 1):
            if not any(alive(t) for t in targets):
                break
            sleep(roster.STOP_POLL_SECONDS)
        survivors = [t for t in targets if alive(t)]
        for t in survivors:
            say(f"supervisor {t['role']} pid {t['pid']} did not honour the stop request")
        if survivors:
            return 1
        for t in targets:
            roster.clear_stop(t["pid"])
        for path in group_records(roster, sdir, hosts).get(box, []):
            try:
                os.remove(path)
            except OSError:
                pass
        os.remove(lock)
        held = False
    finally:
        if held:  # any early exit, an interrupt included, leaves no stop request pending for a late honour
            for t in written:
                try:
                    os.remove(roster.stop_request_path(t["pid"]))
                except OSError:
                    pass
            try:
                os.remove(lock)
            except OSError:
                pass
    started = link(roster, alias, resolve_key(roster, alias), say, spawn=spawn)
    if not started and HOST_KEY_FAILURE in str(getattr(started, "reason", None) or "").lower():
        say(f"restart-box: {alias}: host key verification failed; nothing spawned (re-pin the host key for {alias})")
        return 1
    live = _box_supervisors(roster, sdir, alias, hosts, alive)
    recorded = read_record(record_path(sdir, alias))
    extras = []
    for role, _ in SUPERVISORS:
        mine = [t for t in live if t["role"] == role]
        keep = next((t for t in mine if t["pid"] == (recorded.get(role) or {}).get("pid")), mine[0] if mine else None)
        extras += [t for t in mine if t is not keep]
    for t in extras:  # one per role, never two: the unrecorded twin is asked to exit, not killed
        if not roster.stop_request_path(t["pid"]).exists():
            roster.request_stop(t["pid"], t["procStart"], t["role"], t["remote"])
    for _ in range(max(1, round(wait / roster.STOP_POLL_SECONDS)) + 1 if extras else 0):
        if not any(alive(t) for t in extras):
            break
        sleep(roster.STOP_POLL_SECONDS)
    for t in extras:
        if not alive(t):
            roster.clear_stop(t["pid"])
    counts = {}
    bad = False
    final = _box_supervisors(roster, sdir, alias, hosts, alive)
    for t in final:
        counts[t["role"]] = counts.get(t["role"], 0) + 1
    final_pids = {t["pid"] for t in final}
    for t in targets:  # a count of one is not a handover when the one is a process that was asked to leave
        if t["pid"] in final_pids or probe_alive(t["pid"]):
            say(f"restart-box: {alias} old {t['role']} supervisor pid {t['pid']} is still running")
            bad = True
    for role, _ in SUPERVISORS:
        if counts.get(role, 0) != 1:
            say(f"restart-box: {alias} has {counts.get(role, 0)} live {role} supervisors after handover")
            bad = True
    if bad or not refreshed:
        return 1
    say(f"restart-box: {alias} handed over, one live supervisor per role")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in ("--help", "-h"):
        print(__doc__)
        return 0
    if argv == ["restart"]:
        return cmd_restart()
    if len(argv) == 2 and argv[0] == "restart-box":
        return cmd_restart_box(argv[1])
    if argv == ["--boot"]:
        return cmd_boot()
    link_pass()
    return 0


if __name__ == "__main__":
    sys.exit(main())
