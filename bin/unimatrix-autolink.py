#!/usr/bin/env python3
"""Bring up the cross-box Unimatrix link to every configured far box, once, and stay silent.

Usage:
  unimatrix-autolink.py
  unimatrix-autolink.py restart   (stop the box router and its faces, then start the installed one)

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

When no alias is listed (or the registry is unreadable) it appends one reason line to the log and exits 0:
a receive-only box reads "no unimatrix.far_boxes configured; no supervisors started". An alias with no
existing key appends one line to the log and is skipped; other aliases still link. A held per-peer lock
logs its skip. An unreachable far box appends one line to `<settings home>/unimatrix/autolink.log`.
Nothing is ever printed to stdout (only `detached`'s one-line stderr note when nice 0 is refused) and the exit
status is always 0: a session start must not fail on it.
"""
import base64
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
KEYS_PREFIX = "unimatrix.keys."
SSH_DEFAULT_IDENTITIES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ecdsa_sk", "id_ed25519", "id_ed25519_sk", "id_xmss"}
SUPERVISORS = (("bridge", "unimatrix-roster.py"), ("inbox", "unimatrix-mirror-all.py"))
ROUTER_SCRIPT = "unimatrix-peer-router.py"
NO_ROUTER_ENV = "UNIMATRIX_AUTOLINK_NO_ROUTER"
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
    reader = roster.settings_home() / "bin" / "_machine_local.py"
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
    home = str(roster.settings_home())
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


_LIVENESS = []


def _liveness():
    if not _LIVENESS:
        spec = importlib.util.spec_from_file_location("unimatrix_liveness", HERE / "unimatrix-liveness.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _LIVENESS.append(mod)
    return _LIVENESS[0]


_MEMBERSHIP = []


def _membership():
    if not _MEMBERSHIP:
        spec = importlib.util.spec_from_file_location("unimatrix_membership", HERE / "unimatrix-membership.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MEMBERSHIP.append(mod)
    return _MEMBERSHIP[0]


def state_dir(roster):
    return roster.settings_home() / "unimatrix"


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
    home = roster.settings_home()
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
    cmd = ["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "AddressFamily=inet",
           "-o", f"ConnectTimeout={PROBE_CONNECT_SECONDS}", remote, "membership", "get"]
    r = run(cmd, capture_output=True, timeout=PROBE_TIMEOUT_SECONDS, creationflags=roster.no_window())
    lines = (r.stdout or b"").decode("utf-8", "replace").splitlines()
    if r.returncode or len(lines) < 2:
        return False
    snap = json.loads(lines[0])
    home = roster.settings_home()
    held, _ = mem.load_snapshot(home)
    if held is not None and snap.get("epoch", 0) <= held["epoch"]:
        return False
    mem.adopt(home, snap, base64.b64decode(lines[1].strip(), validate=True))
    return True


NO_ALIAS_REASON = "no unimatrix.far_boxes configured; no supervisors started"


def far_boxes_status(roster, guard=False):
    """(aliases, reason): reason names why `aliases` is empty, and is None when it is not.
    `guard` refuses a real alias under a test home; the read-only doctor diagnosis leaves it off."""
    reader = roster.settings_home() / "bin" / "_machine_local.py"
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
    cmd = ["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "AddressFamily=inet",
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
    cmd = ["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "AddressFamily=inet",
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


def link_peer(roster, alias, key, say, spawn=detached, probe_fn=probe, stable_fn=None, now=None, liveness=None,
              pull_fn=None, mdns_fn=None, alias_fn=None, hosts=None):
    """Start whichever of the peer's two supervisors is not live. Never raises for a down peer.

    The mDNS live-address retry, the ssh-config alias retry, then the stable-name fallback, run only after the
    recorded name itself failed to answer; the probe outcome feeds the backoff."""
    stable_fn = stable_fn or roster.stable_remote
    liveness = liveness or _liveness()
    sdir = state_dir(roster)
    rec_path = record_path(sdir, alias)
    hosts = {} if hosts is None else hosts
    box = box_key(roster, alias, hosts)
    lock = sdir / f"autolink-{slug(box)}.lock"
    if not acquire_lock(lock):
        say(f"far box {alias}: link lock held by another start; skipped")
        return
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
            return
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
        liveness.note_probe(sdir, alias, not why, now)
        if why:
            say(f"far box {alias} unreachable: {why}" + (f" ({note})" if note else ""))
            return
        if remote != alias:
            say(f"far box {alias} pinned address stale; linked via {remote}" + (f" ({note})" if note else ""))
        if pull_fn:
            try:
                pull_fn(roster, remote, key)
            except Exception as ex:  # a refused or malformed peer snapshot never blocks the link
                say(f"far box {alias}: membership pull skipped: {type(ex).__name__}: {str(ex)[:100]}")
        tunnel = roster.default_tunnel()
        for role, script in SUPERVISORS:
            if role not in missing:
                continue
            p = spawn(supervisor_cmd(script, sdir / f"{role}-{slug(alias)}.log", remote, key, tunnel,
                                      pinned_python(roster)))
            try:
                stamp = roster.proc_start(p.pid)
            except (OSError, subprocess.SubprocessError):
                stamp = None
            rec[role] = {"pid": p.pid, "procStart": stamp}
            rec["box"] = box
            if stamp is not None:  # the reaper's evidence of a supervisor, kept after a record loses its pid
                try:
                    roster.write_json_atomic(str(sdir / f"supervisor-{p.pid}.json"),
                                             {"pid": p.pid, "procStart": stamp, "remote": remote})
                except OSError:
                    pass
            roster.write_json_atomic(str(rec_path), rec)  # per spawn: a later failure never orphans this one
        migrate()
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def machine_local_key(roster, alias, run=subprocess.run):
    """The machine-local `unimatrix.keys.<alias>` path, or None when unset or unreadable."""
    reader = roster.settings_home() / "bin" / "_machine_local.py"
    if not reader.is_file():
        return None
    try:
        r = run([pinned_python(roster), str(reader), "get", f"{KEYS_PREFIX}{alias}"],
                capture_output=True, text=True, timeout=2.0, creationflags=roster.no_window())
    except (OSError, subprocess.SubprocessError, InterpreterPinError):
        return None
    val = r.stdout.strip() if not r.returncode else ""
    return os.path.expanduser(val) if val else None


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
        if path.name not in SSH_DEFAULT_IDENTITIES and not hands_on_key(path) and path.is_file():
            return str(path)
    return None


def hands_on_key(key):
    """True for the 1Password `unimatrix-01` key, which an unattended link never uses."""
    return Path(str(key)).name.lower() == UNIMATRIX_01_KEY


def resolve_key(roster, alias, local_fn=None, ssh_fn=None):
    """The relay key for one alias: machine-local, else ssh-config IdentityFile, else the shared default.

    A source that names the hands-on `unimatrix-01` key is skipped for the next one."""
    for fn in (local_fn or machine_local_key, ssh_fn or ssh_identity_file):
        key = fn(roster, alias)
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


def stop_duplicate_pairs(roster, sdir, say, kill=None, hosts=None):
    """Keep one live supervisor pair per `box_key`; stop every other live supervisor and drop its record.

    The kept pair is the first live one, the canonical record's before any other. A record sharing the kept
    pair's pids is a stale copy of it: removed without a kill. A stop needs pid plus procStart to match."""
    kill = kill or roster.tree_kill
    for key, paths in group_records(roster, sdir, hosts).items():
        if len(paths) < 2:
            continue
        lock = Path(sdir) / f"autolink-{slug(key)}.lock"
        if not acquire_lock(lock):  # a link_peer for this box is mid-spawn; the next start cleans up
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


def ssh_hostname(roster, alias, run=subprocess.run):
    """The HostName `ssh -G` gives `alias`, else None."""
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
        if name.lower() == "hostname" and val.strip():
            return val.strip()
    return None


def member_alias(roster, box, host, aliases, hosts=None, run=subprocess.run):
    """The ssh alias this box's links use for member `box` at `host`, else `box`.

    An alias in `aliases` qualifies when its own name or its `ssh -G` HostName equals `host` (case-insensitive,
    `.local` ignored). `hosts` caches alias -> normalised HostName across calls."""
    if not host:
        return box
    hosts = {} if hosts is None else hosts
    want = _host_key(host)
    for alias in aliases:
        if alias not in hosts:
            hosts[alias] = _host_key(ssh_hostname(roster, alias, run=run) or "")
        if _host_key(alias) == want or hosts[alias] == want:
            return alias
    return box


def router_lock_held(sdir):
    """True while a router process holds `<state>/router/router.lock` (its lifetime lease), however it was started."""
    path = sdir / "router" / "router.lock"
    try:
        spec = importlib.util.spec_from_file_location("unimatrix_local_transport", HERE / "unimatrix-local-transport.py")
        transport = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(transport)
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


def run(roster=None, boxes=None, spawn=detached, probe_fn=probe, key_fn=None, stable_fn=None, now=None,
        membership=None, pull_fn=None, self_names=None, agent_fn=None, kill=None, mdns_fn=None, alias_fn=None):
    """Link every far box whose supervisors are down. A healthy box returns after reading records only.

    Explicit `boxes` are ssh aliases and bypass the snapshot. Otherwise the verified membership snapshot
    (minus this box) supplies `<user>@<host>` targets and `unimatrix.far_boxes` is read only when no
    snapshot is stored. Per alias the record check precedes key resolution, and an alias inside its probe
    backoff is skipped. The boxes cache short-circuits `healthy` for up to 24h unless the snapshot epoch
    moved since it was written."""
    key_fn = key_fn or resolve_key
    agent_fn = agent_fn or agent_state
    roster = roster or _roster()
    liveness = _liveness()
    sdir = state_dir(roster)
    sdir.mkdir(parents=True, exist_ok=True)

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
    healthy = liveness.healthy(sdir, now) and not _epoch_moved(sdir, liveness)
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
        return

    reason = NO_ALIAS_REASON
    explicit = boxes is not None
    names, epoch, snapshot_mode = {}, None, False
    if boxes is None:
        status, names, skipped, epoch, why = split_members(roster, membership, self_names)
        if status == "bad":
            say(why)
            return
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
        return
    write_cache(boxes)
    if not explicit:
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

    def link_all(aliases):
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
                if liveness.backoff_until(sdir, alias) > clock:
                    continue
                pending.append(alias)
            except Exception as ex:  # one peer's failure must not stop the next or fail the session
                say(f"far box {alias} link failed: {type(ex).__name__}: {str(ex)[:120]}")
        if snapshot_mode and pending:
            try:
                if "aliases" not in lookup:
                    lookup["aliases"] = far_boxes_status(roster)[0]
            except Exception as ex:  # noqa: BLE001 -- the registry read is shared by every pending alias
                say(f"far box lookup failed: {type(ex).__name__}: {str(ex)[:120]}")
                return
        for alias in pending:
            try:
                target = names.get(alias, alias)
                if snapshot_mode:
                    target = member_alias(roster, target, alias.rpartition("@")[2], lookup["aliases"],
                                          hosts)
                key = key_fn(roster, target)
                if not Path(key).is_file():
                    # A configured alias with no key is a misconfiguration worth one line, not silence.
                    say(f"far box {alias}: no Unimatrix-Zero key (looked for {key}); not linked")
                    continue
                verdict = agent_fn(key)
                if verdict == "locked":  # a named wait: no probe, no backoff charge
                    say(f"far box {alias}: waiting: 1Password locked")
                    continue
                if verdict == "missing":
                    say(f"far box {alias}: passphrase_source_missing: op CLI or unimatrix.passphrase_vault "
                        f"unavailable; encrypted key {key} not loaded")
                    continue
                link_peer(roster, alias, key, say, spawn=spawn, probe_fn=probe_fn, stable_fn=stable_fn,
                          now=now, liveness=liveness, pull_fn=pull_fn, mdns_fn=shared_mdns, alias_fn=alias_fn,
                          hosts=hosts)
            except Exception as ex:  # one peer's failure must not stop the next or fail the session
                say(f"far box {alias} link failed: {type(ex).__name__}: {str(ex)[:120]}")

    link_all(boxes)
    if not snapshot_mode:
        return
    try:
        status, names2, epoch2, _ = member_targets(roster, membership, self_names)
    except Exception:  # noqa: BLE001 -- the second look is best effort
        return
    if status == "ok" and epoch2 != epoch:
        names.update(names2)
        epoch = epoch2
        write_cache(names2)
        link_all([a for a in names2 if a not in boxes])


def cmd_restart():
    roster = _roster()
    sdir = state_dir(roster)
    sdir.mkdir(parents=True, exist_ok=True)
    try:
        res = restart_router(roster, sdir, print)
    except (RouterRestartError, OSError) as ex:
        print(f"router restart failed: {ex}", file=sys.stderr)
        return 1
    print(f"router restarted: {res['stopped']} old pid {res['old_pid']} new pid {res['new_pid']}")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in ("--help", "-h"):
        print(__doc__)
        return 0
    if argv == ["restart"]:
        return cmd_restart()
    try:
        run()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
