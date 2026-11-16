#!/usr/bin/env python3
"""Diagnose every Unimatrix link, both sides: unsigned authorized_keys lines, dead or IP-pinned aliases.

Usage:
  unimatrix-doctor.py
  unimatrix-doctor.py confirm <mirror-name>

`confirm` reads the mirror's last delivery (its digest) and asks the far relay, over the box mux, for its
receipt of that line: prints CONFIRMED (exit 0) or UNCONFIRMED with the reason (exit 1).

Prints one `problem:` line per fault and exits 1 when there is any, else 0. Never constructs a signer and
never touches 1Password: the membership snapshot is verified offline against the pinned public key.

Checks, per link target (every verified member except this box; each `unimatrix.far_boxes` alias only when
no snapshot is stored, the one case autolink dials them):
the name resolves, TCP 22 connects, the relay key answers `roster`, the peer's own snapshot lists this box
at the same epoch (members only). Per far box one bridge and one inbox supervisor line (pid when alive,
remedy when not; one of each per box is the design). A mesh is symmetric: a member direction whose relay
key is absent, refused, or not authorized here is also `asymmetric: <from> -> <to> missing`. Locally: the
machine-local unimatrix.python pin is set; every authorized_keys line
that forces unimatrix-relay.py must carry a key that belongs to a verified member and an absolute interpreter
equal to autolink's pinned one; on macOS both autolink launchd labels at once, and on POSIX each orphaned
or replaced-code relay session, are problems too. The Windows
administrators_authorized_keys file is reported, never read. Network probes are injectable (run=, resolve=,
connect=); remote round trips are outside the 500ms bar, the local verify path is not.
"""
import base64
import hashlib
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TCP_SECONDS = 5
SSH_G_SECONDS = 10
KEY_RE = re.compile(r"\bssh-ed25519\s+([A-Za-z0-9+/]{16,}={0,2})")
RELAY_SCRIPT = "unimatrix-relay.py"


def _load(name, script):
    spec = importlib.util.spec_from_file_location(name, HERE / script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _short(body):
    return f"...{body[-12:]}"


def ssh_hostname(alias, run, no_window=0):
    """The HostName `ssh -G` gives `alias`, or None when ssh cannot say."""
    try:
        r = run(["ssh", "-G", "--", alias], capture_output=True, timeout=SSH_G_SECONDS, creationflags=no_window)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode:
        return None
    out = r.stdout.decode("utf-8", "replace") if isinstance(r.stdout, bytes) else (r.stdout or "")
    for line in out.splitlines():
        k, _, v = line.partition(" ")
        if k.lower() == "hostname" and v.strip():
            return v.strip()
    return None


def key_bodies(members, mem):
    """Every relay key body (`relay_pub` and each `relay_pubs`) of `members`: a line carrying any of them is signed."""
    return {body for m in members for body in mem.member_key_bodies(m)}


def unsigned_authorized_lines(path, signed):
    """[(line number, key body)] for authorized_keys lines forcing unimatrix-relay.py whose key is not in `signed`."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#") or RELAY_SCRIPT not in line:
            continue
        found = KEY_RE.findall(line)
        body = found[-1] if found else ""
        if body not in signed:
            out.append((n, body))
    return out


def forced_key_bodies(path):
    """Key bodies of the authorized_keys lines that force unimatrix-relay.py; empty when the file is unreadable."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    out = set()
    for line in text.splitlines():
        if line.lstrip().startswith("#") or RELAY_SCRIPT not in line:
            continue
        found = KEY_RE.findall(line)
        if found:
            out.add(found[-1])
    return out


def key_owner(ctx, path, line_no, body):
    """The box a forced key belongs to, else None: the ssh alias whose IdentityFile `.pub` carries `body`
    (candidates: `unimatrix.far_boxes`), else the key's comment on its authorized_keys line."""
    if not body:
        return None
    al, roster, run = ctx["autolink"], ctx["roster"], ctx["run"]
    try:
        for alias in al.far_boxes_status(roster)[0]:
            ident = al.ssh_identity_file(roster, alias, run=run)
            pub = Path(f"{ident}.pub") if ident else None
            if pub and pub.is_file() and body in pub.read_text(encoding="utf-8", errors="replace"):
                return alias
    except (OSError, AttributeError, TypeError):
        pass
    try:
        line = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[line_no - 1]
    except (OSError, IndexError):
        return None
    tail = line.partition(body)[2].split()
    return tail[0] if tail else None


def asymmetric(frm, to):
    return f"asymmetric: {frm} -> {to} missing"


def self_label(members, names):
    """This box's name as the snapshot spells it, else the first of its own names."""
    me = {n.lower() for n in names}
    for m in members:
        if m["box"].lower() in me or m["host"].split(".")[0].lower() in me:
            return m["box"]
    return sorted(names)[0] if names else "this box"


def inbound_asymmetric_problems(ctx, members, label, authorized_keys_readable):
    """`asymmetric: <peer> -> <this box> missing` for each member whose relay key addressed to this box
    (`pair_key_for`) no forced line here carries."""
    mem = ctx["membership"]
    if not authorized_keys_readable:
        return []
    pairs = _load("unimatrix_pair_contract", "lib/unimatrix_pair_contract.py").expected_directions(
        [m["box"] for m in members] + [label])
    held = forced_key_bodies(ctx["authorized_keys"])
    by_box = {m["box"].casefold(): m for m in members}
    out = []
    for frm, to in sorted(pairs):
        member = by_box.get(frm.casefold())
        if to.casefold() != label.casefold() or member is None:
            continue
        if mem.pair_key_for(member, label).split()[1] not in held:
            out.append(asymmetric(frm, to))
    return out


PRE_BANNER_RE = re.compile(r"kex_exchange_identification|banner exchange|timed out|TimeoutExpired", re.I)
SPAWN_RE = re.compile(r"Connection closed by|kex_exchange_identification|drop connection", re.I)
REMEDY_UPSTREAM = "remedy: check that box's network link and prefer wired"
REMEDY_ALL = "remedy: restart sshd on that box and read its sshd log for why it drops every source"
REMEDY_ONE = "remedy: another source reaches it; check this box's network link and route to it, prefer wired"


def source_reaches(run, src, host, no_window=0):
    """True when `src` (another box we can ssh to) gets an ssh banner from `host` port 22."""
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "AddressFamily=inet", "-o", "ConnectTimeout=5", src, "ssh-keyscan", "-T", "5", "-p", "22", host]
    try:
        r = run(cmd, capture_output=True, timeout=15, creationflags=no_window)
    except (OSError, subprocess.SubprocessError):
        return False
    return not r.returncode and b"ssh-" in (r.stdout or b"")


FAR_LOG_CMD = ("journalctl --since '15 min ago' -n 200 --no-pager -u ssh -u sshd 2>/dev/null || tail -n 200 /var/log/auth.log /var/log/secure 2>/dev/null"
               " || log show --last 10m --style compact --predicate 'process == \"sshd\"' 2>/dev/null")


def default_far_sshd_log(run, no_window=0, routes=()):
    """A reader (remote, host) -> far sshd log text, or None when that box gives no unprivileged shell read.

    Asks over plain ssh without sudo, trying each of `routes` (a second network path to the same box, such as the
    tunnel alias) before the direct dial, which is the link whose failure we are classifying; a forced-command
    relay key, a refusal or empty output on every route reads as None."""
    def read(remote, host):
        for target in dict.fromkeys([*routes, remote]):
            cmd = ["ssh", "-o", "BatchMode=yes", "-o", "AddressFamily=inet", "-o", "ConnectTimeout=5", target, FAR_LOG_CMD]
            try:
                r = run(cmd, capture_output=True, timeout=15, creationflags=no_window)
            except (OSError, subprocess.SubprocessError):
                continue
            out = r.stdout.decode("utf-8", "replace") if isinstance(r.stdout, bytes) else (r.stdout or "")
            if not r.returncode and out.strip():
                return out
        return None
    return read


def classify_link(remote, name, host, ctx, detail):
    """One problem line for a pre-banner failure: which of the three link classes, with its own remedy.

    Another source reaching port 22 makes it refusing-one-source. With none reaching, the far sshd log (read
    through ctx["far_sshd_log"], default `default_far_sshd_log`, never sudo) decides: spawns seen means sshd-refusing-all-sources,
    none seen means a definite unreachable-upstream; an unreadable log leaves unreachable-upstream probable."""
    srcs = [s for s in ctx.get("other_sources", ()) if s != remote]
    if any(source_reaches(ctx["run"], s, host, ctx["roster"].no_window()) for s in srcs):
        return f"{name}: refusing-one-source: {host} closes this box before the banner ({detail}) but another source reaches port 22; {REMEDY_ONE}"
    tunnel = ctx["roster"].default_tunnel()
    reader = ctx.get("far_sshd_log") or default_far_sshd_log(ctx["run"], ctx["roster"].no_window(), [tunnel] if tunnel else [])
    log = reader(remote, host) if reader else None
    if log is not None and SPAWN_RE.search(log):
        return f"{name}: sshd-refusing-all-sources: {host} sshd answers connections but drops every source before the banner ({detail}); {REMEDY_ALL}"
    certainty = "definite" if log is not None else "probable"
    return f"{name}: unreachable-upstream ({certainty}): {host} closes or times out before the banner ({detail}) and the far sshd logs no spawn" \
           f"{'' if log is not None else ' (log unreadable)'}; {REMEDY_UPSTREAM}"


def local_relay_sha():
    """Same digest the relay reports as `relay_sha`: sha256 of unimatrix-relay.py, CRLF folded, first 12 hex."""
    import hashlib
    try:
        return hashlib.sha256((HERE / RELAY_SCRIPT).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:12]
    except OSError:
        return None


def relay_drift(name, roster_out):
    """Problem lines when the far relay's `roster` rows carry a relay_sha other than this box's.

    A far box with no live session prints no rows and says nothing; a row without relay_sha is a relay
    older than the field."""
    rows = []
    for ln in (roster_out or b"").decode("utf-8", "replace").splitlines():
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    local = local_relay_sha()
    if not rows or local is None:
        return []
    far = {r.get("relay_sha") for r in rows}
    if far == {local}:
        return []
    shown = ", ".join(sorted(str(s) for s in far if s)) or "none reported (relay predates relay_sha)"
    return [f"{name}: relay version drift: far relay {shown}, this box {local}; "
            f"remedy: reinstall unimatrix-relay.py on both boxes (publish, then install)"]


AUTOLINK_LABELS = ("com.unimatrix.autolink", "com.coordinator.unimatrix-autolink")  # unimatrix-install.py LOGIN_AGENT_LABEL, then LEGACY_LOGIN_AGENT_LABELS
REMEDY_INSTALL = ("remedy: run unimatrix-install.py --install from the published checkout "
                  "(python <checkout>/coordinator/bin/unimatrix-install.py --install; the installed copy lacks lib/ and cannot reap)")


def run_launchctl_list():
    """`launchctl list` stdout; empty when launchctl cannot run."""
    try:
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if not r.returncode else ""


def autolink_label_problems(listing):
    """A problem line when `launchctl list` text carries both autolink labels: two supervisors."""
    loaded = {ln.split()[-1] for ln in listing.splitlines() if ln.split()}
    if all(label in loaded for label in AUTOLINK_LABELS):
        return [f"two autolink labels are loaded in launchd ({' and '.join(AUTOLINK_LABELS)}): two supervisors; "
                f"{REMEDY_INSTALL}"]
    return []


def relay_session_problems(ps_out, parent_alive, sessions_mod, script_dir=HERE):
    """One problem line per orphaned relay session or one started before the installed relay script's st_ctime."""
    stamps = {}
    for name in sessions_mod.RELAY_SCRIPTS:
        try:
            stamps[name] = (Path(script_dir) / name).stat().st_ctime
        except OSError:
            continue
    groups = sessions_mod.classify_relay_sessions(sessions_mod.list_relay_sessions(ps_out), stamps, parent_alive)
    why = {sessions_mod.STALE: "orphaned (its sshd parent is gone)",
           sessions_mod.MISMATCHED: "running code the install has since replaced"}
    return [f"relay session pid {s.pid} ({s.script}) is {why[kind]}; {REMEDY_INSTALL} to reap it"
            for kind in (sessions_mod.STALE, sessions_mod.MISMATCHED) for s in groups[kind]]


def forced_interpreters(path):
    """Absolute interpreters named by authorized_keys lines that force unimatrix-relay.py; a bare name resolves on sshd's PATH and is not judged."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found = []
    for line in text.splitlines():
        if line.lstrip().startswith("#") or RELAY_SCRIPT not in line:
            continue
        m = re.search(r'command="((?:\\"|[^"])*)"', line)
        if not m:
            continue
        cmd = m.group(1).replace('\\"', '"').strip()
        interp = cmd[1:cmd.find('"', 1)] if cmd.startswith('"') and cmd.find('"', 1) > 0 else cmd.split(None, 1)[0]
        if os.path.isabs(interp) or re.match(r"^[A-Za-z]:[\\/]", interp) or interp.startswith("/"):
            found.append(interp)
    return found


def interpreter_split_problems(ctx):
    """A problem line when a forced-command interpreter differs from the one autolink's mirror-all runs."""
    forced = forced_interpreters(ctx["authorized_keys"])
    if not forced:
        return []
    al, roster = ctx["autolink"], ctx["roster"]
    try:
        pinned = al.pinned_python(roster)
    except al.InterpreterPinError:
        return []

    def same(a, b):
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))

    return [f"interpreter split: authorized_keys forces {interp} but autolink and mirror-all run {pinned}; {REMEDY_INSTALL} (it rewrites the forced interpreter in the local authorized_keys)"
            for interp in dict.fromkeys(forced) if not same(interp, pinned)]


def pwsh_alias_first_problems(environ, platform):
    """A problem line on win32 when PATH resolves pwsh to a WindowsApps alias, which codex's sandbox cannot launch."""
    if platform != "win32":
        return []
    lib = str(HERE / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    from cc_invoke import place_engine_root_on_path

    place_engine_root_on_path(str(HERE.parents[1]))
    from coordinator_core.codex_runner.sandbox_preflight import alias_first_pwsh
    alias = alias_first_pwsh(environ)
    if alias is None:
        return []
    return [f"pwsh resolves first to the Store alias {alias}, which a codex sandbox cannot launch; "
            "remedy: install PowerShell 7 to %ProgramFiles%\\PowerShell\\7 or move its dir ahead of WindowsApps in PATH"]


def make_read_key(ctx):
    """A cached `read_key(key) -> str` over the machine-local reader, every spawn routed through the injected run."""
    al, roster = ctx["autolink"], ctx["roster"]
    cache = ctx.setdefault("read_key_cache", {})

    def read_key(key):
        if key in cache:
            return cache[key]
        val = ""
        reader = roster.settings_home() / "bin" / "_machine_local.py"
        if reader.is_file():
            try:
                r = ctx["run"]([al.pinned_python(roster), str(reader), "get", key], capture_output=True, text=True,
                               timeout=30, creationflags=roster.no_window())
                val = r.stdout.strip() if not r.returncode and isinstance(r.stdout, str) else ""
            except (OSError, subprocess.SubprocessError, al.InterpreterPinError):
                val = ""
        cache[key] = val
        return val

    return read_key


def _box_id(name, ctx):
    """The box id the address keys and HostKeyAlias use: a far_boxes alias `user@host` maps through box_of, as roster and box_mux do."""
    mux = ctx.get("box_mux") or _load("unimatrix_box_mux", "lib/unimatrix_box_mux.py")
    ctx["box_mux"] = mux
    return mux.box_of(name)


def address_fallback(remote, name, key, ctx):
    """(address | None, skipped) over the box's ordered address list; each candidate is verified strictly
    (HostKeyAlias=<box>, StrictHostKeyChecking=yes) with one `roster` ssh, so another machine's IP is not-this-box."""
    far = ctx.setdefault("far", None) or _load("unimatrix_far_addresses", "lib/unimatrix_far_addresses.py")
    ctx["far"] = far
    roster, run = ctx["roster"], ctx["run"]
    box = _box_id(name, ctx)
    addresses = far.box_addresses(box, ctx["read_key"] if ctx.get("read_key") else make_read_key(ctx))
    if not addresses:
        return None, []

    def connect(address):
        try:
            ctx["connect"]((address.split("%", 1)[0], 22), timeout=TCP_SECONDS).close()
        except OSError:
            return False
        return True

    def verify(target):
        cmd = ["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", f"HostKeyAlias={box}",
               "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=3", target, "roster"]
        try:
            r = run(cmd, capture_output=True, timeout=15, creationflags=roster.no_window())
        except (OSError, subprocess.SubprocessError) as ex:
            return far.UNREACHABLE, type(ex).__name__
        return far.classify(r.returncode, r.stderr)

    return far.first_answering(box, remote.rpartition("@")[0], addresses, connect=connect, verify=verify)


def failed_primary(remote, name, key, ctx, line):
    """[] with a note when a listed address answers as this box; else `line` plus any not-this-box addresses."""
    address, skipped = address_fallback(remote, name, key, ctx)
    if address is not None:
        ctx.setdefault("address_notes", []).append(f"{name}: primary name failed; box answers at {address} (host key verified)")
        return []
    line = line() if callable(line) else line
    foreign = [a for a, why in skipped if why == "not-this-box"]
    if foreign:
        line += f"; address {', '.join(foreign)} answers with a different host key (not this box)"
    return [line]


def known_hosts_fingerprints(box, ctx):
    """The SHA256 fingerprints of known_hosts entries for HostKeyAlias `box` (empty when none)."""
    kh = ctx.get("known_hosts") or Path.home() / ".ssh" / "known_hosts"
    if not Path(kh).is_file():
        return set()
    try:
        r = ctx["run"](["ssh-keygen", "-F", box, "-f", str(kh)], capture_output=True, text=True, timeout=15,
                       creationflags=ctx["roster"].no_window())
    except (OSError, subprocess.SubprocessError):
        return set()
    out = set()
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        if line.startswith("#") or len(parts) < 3:
            continue
        try:
            out.add("SHA256:" + base64.b64encode(hashlib.sha256(base64.b64decode(parts[2])).digest()).decode().rstrip("="))
        except ValueError:
            continue
    return out


def hostkey_problems(name, ctx):
    """A problem when the pinned `unimatrix.hostkey.<box>` fingerprint is not among known_hosts' entries for that box."""
    far = ctx.get("far") or _load("unimatrix_far_addresses", "lib/unimatrix_far_addresses.py")
    ctx["far"] = far
    name = _box_id(name, ctx)
    pinned = far.pinned_hostkey(name, ctx["read_key"] if ctx.get("read_key") else make_read_key(ctx))
    if not pinned:
        return []
    seen = known_hosts_fingerprints(name, ctx)
    if not seen:
        return [f"{name}: no known_hosts entry for HostKeyAlias {name}; the address resolver fails closed; "
                f"remedy: ssh once with -o HostKeyAlias={name} and confirm the key is {pinned}"]
    if pinned not in seen:
        return [f"{name}: known_hosts key for HostKeyAlias {name} ({', '.join(sorted(seen))}) differs from the pinned {pinned}; "
                "remedy: remove the stale known_hosts entry, or correct the pin if the box was reinstalled"]
    return []


def check_target(remote, name, host, key, ctx, peer_epoch_check, outbound=None):
    """Problem lines for one link target. `remote` is the dialled token, `name` the box or alias, `host` the DNS name.

    `outbound` is this box's label for a member target: a missing or refused relay key then also names the direction."""
    def gone(line):
        return [line, asymmetric(outbound, name)] if outbound else [line]

    al, roster, run = ctx["autolink"], ctx["roster"], ctx["run"]
    probs = []
    try:
        ctx["resolve"](host, 22)
    except OSError as ex:
        return failed_primary(remote, name, key, ctx, f"{name}: {host} does not resolve ({type(ex).__name__})")
    try:
        ctx["connect"]((host, 22), timeout=TCP_SECONDS).close()
    except TimeoutError as ex:
        return failed_primary(remote, name, key, ctx, lambda: classify_link(remote, name, host, ctx, type(ex).__name__))
    except OSError as ex:
        return failed_primary(remote, name, key, ctx, f"{name}: {host} refuses TCP 22 ({type(ex).__name__})")
    if not Path(key).is_file():
        probs.extend(gone(f"{name}: no relay key (looked for {key})"))
    else:
        seen_out = []

        def capture(cmd, **kw):
            r = run(cmd, **kw)
            seen_out.append(r.stdout)
            return r

        why = al.probe(roster, remote, key, run=capture, remote=remote)
        if why is None:
            probs.extend(relay_drift(name, seen_out[-1] if seen_out else b""))
        if why and PRE_BANNER_RE.search(why):
            return probs + [classify_link(remote, name, host, ctx, why)]
        if why:
            return probs + gone(f"{name}: relay key does not answer `roster` ({why})")
        if peer_epoch_check:
            probs.extend(peer_epoch_check(remote, key, name))
    return probs


def supervisor_lines(name, remote, ctx):
    """(problems, infos) for one far box: one line per supervisor role. Autolink runs one bridge and one inbox
    supervisor per far box, so N far boxes show N of each; a live one reports its recorded pid."""
    al, roster = ctx["autolink"], ctx["roster"]
    rec = al.read_record(al.state_dir(roster) / f"autolink-{al.slug(remote)}.json")
    probs, infos = [], []
    for role, script in al.SUPERVISORS:
        entry = rec.get(role) or {}
        if al.supervisor_live(roster, entry):
            infos.append(f"{name}: {role} supervisor ({script}) alive, pid {entry['pid']}")
        else:
            probs.append(f"{name}: {role} supervisor is not alive ({script}); "
                         "remedy: run unimatrix-autolink.py to respawn it, or unimatrix-autolink.py restart")
    return probs, infos


def python_pin_problems(ctx):
    """A problem line when the machine-local `unimatrix.python` pin is unset or names a missing file."""
    al, roster = ctx["autolink"], ctx["roster"]
    val = al.pin_key_value(roster, run=ctx["run"])
    if val is None:
        return [f"{al.PYTHON_KEY} is unset in machine-local (or the reader or a console python is unavailable); supervisors fall back to an unpinned interpreter; "
                f"remedy: python {roster.settings_home() / 'bin' / '_machine_local.py'} set {al.PYTHON_KEY} <absolute console python path>"]
    if not os.path.isfile(val):
        return [f"{al.PYTHON_KEY} names a missing interpreter: {val}; remedy: set it to an existing console python"]
    return []


RESERVED_IPS_KEY = "unimatrix.reserved_ips"


def reserved_ips(ctx):
    """The IPs the PM declared DHCP-reserved in machine-local `unimatrix.reserved_ips` (comma/space separated);
    empty when unset or unreadable, so an undeclared IP pin stays a problem."""
    al, roster = ctx["autolink"], ctx["roster"]
    reader = roster.settings_home() / "bin" / "_machine_local.py"
    if not reader.is_file():
        return set()
    try:
        r = ctx["run"]([al.pinned_python(roster), str(reader), "get", RESERVED_IPS_KEY], capture_output=True,
                       text=True, timeout=30, creationflags=roster.no_window())
    except (OSError, subprocess.SubprocessError, al.InterpreterPinError):
        return set()
    raw = r.stdout.strip() if not r.returncode and isinstance(r.stdout, str) else ""
    return {t for t in re.split(r"[,\s]+", raw) if t}


def _host_key(name):
    # Same normalisation as unimatrix-pair.py :: _host_key; change both together.
    low = str(name).strip().lower().rstrip(".")
    return low[:-len(".local")] if low.endswith(".local") else low


def member_alias(ctx, name, host=None):
    """The ssh alias this box's links use for member `name` at `host`, else `name`.

    An alias qualifies when its own name or its `ssh -G` HostName equals `host` (case-insensitive, `.local`
    ignored); the candidates are the machine-local `unimatrix.far_boxes` aliases. The listing and each
    HostName are read once per run."""
    if not host:
        return name
    al, roster, run = ctx["autolink"], ctx["roster"], ctx["run"]
    if "_aliases" not in ctx:
        ctx["_aliases"] = al.far_boxes_status(roster)[0]
    hosts = ctx.setdefault("_alias_hosts", {})
    want = _host_key(host)
    for alias in ctx["_aliases"]:
        if alias not in hosts:
            hosts[alias] = _host_key(ssh_hostname(alias, run, roster.no_window()) or "")
        if _host_key(alias) == want or hosts[alias] == want:
            return alias
    return name


def relay_key(ctx, name, host=None):
    """The relay key autolink would use toward `name` at `host` (resolved by `member_alias`), with every lookup
    spawn routed through the injected run."""
    al, roster, run = ctx["autolink"], ctx["roster"], ctx["run"]
    name = member_alias(ctx, name, host)
    return al.resolve_key(roster, name, local_fn=lambda r, a: al.machine_local_key(r, a, run=run),
                          ssh_fn=lambda r, a: al.ssh_identity_file(r, a, run=run))


def peer_lists_us(ctx, mine, self_names):
    """A checker (remote, key, name) -> problems: the peer's snapshot must list this box at this epoch."""
    run, roster = ctx["run"], ctx["roster"]

    def check(remote, key, name):
        verdict = ctx["autolink"].agent_state(key, run=run)
        if verdict == "locked":
            return [f"{name}: waiting: 1Password locked; encrypted key not loaded"]
        if verdict == "missing":
            return [f"{name}: passphrase_source_missing: encrypted key {key} cannot be loaded"]
        cmd = ["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "AddressFamily=inet", "-o", "ConnectTimeout=5",
               remote, "membership", "get"]
        try:
            r = run(cmd, capture_output=True, timeout=15, creationflags=roster.no_window())
            lines = (r.stdout or b"").decode("utf-8", "replace").splitlines()
            if r.returncode or not lines:
                return [f"{name}: peer holds no membership snapshot"]
            theirs = json.loads(lines[0])
            boxes = {m["box"].lower() for m in theirs["members"]} | {m["host"].split(".")[0].lower() for m in theirs["members"]}
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
            return [f"{name}: peer's membership snapshot is unreadable"]
        probs = []
        if not (boxes & {n.lower() for n in self_names}):
            probs.append(f"{name}: peer's snapshot does not list this box")
            probs.append(asymmetric(name, ctx.get("self_label") or (sorted(self_names) or ["this box"])[0]))
        if theirs.get("epoch") != mine["epoch"]:
            probs.append(f"{name}: peer holds snapshot epoch {theirs.get('epoch')}, this box holds {mine['epoch']}")
        return probs

    return check


def diagnose(ctx):
    al, roster, mem = ctx["autolink"], ctx["roster"], ctx["membership"]
    home = roster.settings_home()
    probs, notes, signed = [], [], set()
    names = ctx["self_names"] if ctx["self_names"] is not None else al.own_names()
    status, targets, skipped, epoch, why = al.split_members(roster, mem, names, run=ctx["run"])
    pin = mem.load_pin(home)
    if pin:
        try:
            notes.append(f"pin {mem.fingerprint(pin)}")
        except mem.MembershipError as ex:
            probs.append(f"signer pin unusable: {ex}")
    else:
        probs.append("no signer pin is held; remedy: run unimatrix-pair.py pin <pubfile>, "
                     "or let unimatrix-pair.py approve push it")
    if status == "bad":
        probs.append(why)
    elif status == "none":
        probs.append("no signed membership snapshot is stored; every unimatrix authorized_keys line is unsigned; "
                     "remedy: run unimatrix-pair.py approve <target> to sign and store one "
                     "(add --self-cidr <cidr> on a fresh collective)")
    else:
        verified = mem.verified_members(home, run=ctx["run"])
        signed = key_bodies(verified, mem)
        ctx["self_label"] = self_label(verified, names)
        probs.extend(inbound_asymmetric_problems(ctx, verified, ctx["self_label"], ctx["platform"] != "win32"))
    ak = ctx["authorized_keys"]
    for n, body in unsigned_authorized_lines(ak, signed):
        owner = key_owner(ctx, ak, n, body)
        probs.append(f"{ak} line {n}: forced unimatrix-relay.py key {_short(body) if body else '(unparsable)'} "
                     f"is in no signed membership record{f' (owner: {owner})' if owner else ''}; remedy: "
                     f"run unimatrix-pair.py approve for the owning box, or unimatrix-pair.py revoke <box> to drop the key")
    admin = ctx["admin_file"]
    if admin is not None and admin.exists():
        notes.append(f"{admin} exists and is not inspected here")
    if ctx["platform"] == "darwin":
        probs.extend(autolink_label_problems(ctx["launchctl_list"]()))
    if ctx["platform"] != "win32":
        sessions = _load("unimatrix_relay_sessions", "lib/unimatrix_relay_sessions.py")
        installed = home / "unimatrix"
        probs.extend(relay_session_problems((ctx["relay_ps"] or sessions.ps_snapshot)(), roster.pid_alive, sessions,
                                            script_dir=installed if installed.is_dir() else HERE))
    probs.extend(interpreter_split_problems(ctx))
    probs.extend(python_pin_problems(ctx))
    probs.extend(pwsh_alias_first_problems(ctx.get("environ", os.environ), ctx["platform"]))

    mine = {"epoch": epoch}
    checker = peer_lists_us(ctx, mine, names) if status == "ok" else None
    seen = set()
    for box, remote in skipped:
        probs.append(f"{box}: no live link path: dial name {remote!r} is not a hostname alias (fails the alias check or is an IP literal), so autolink skips it")
    ctx.setdefault("other_sources", sorted(targets))
    for remote, box in sorted(targets.items()):
        seen.add(remote)
        host = remote.rpartition("@")[2]
        probs.extend(check_target(remote, box, host, relay_key(ctx, box, host), ctx, checker, outbound=ctx.get("self_label")))
        probs.extend(hostkey_problems(box, ctx))
        sp, si = supervisor_lines(box, remote, ctx)
        probs.extend(sp)
        notes.extend(si)
        rec = al.read_record(al.state_dir(roster) / f"autolink-{al.slug(remote)}.json")
        if not all(al.supervisor_live(roster, rec.get(role) or {}) for role, _ in al.SUPERVISORS):
            probs.append(f"{box}: no live link path: this box holds no live link to a signed member")
    aliases = al.far_boxes_status(roster)[0] if status == "none" else []
    reserved = reserved_ips(ctx) if aliases else set()
    for alias in aliases:
        if alias in seen:
            continue
        host = ssh_hostname(alias, ctx["run"], roster.no_window())
        if host is None:
            probs.append(f"{alias}: far_boxes alias does not resolve in ssh config")
            continue
        if mem.is_ip_literal(host) and host not in reserved:
            probs.append(f"{alias}: far_boxes alias is pinned to IP {host}; a DHCP change breaks it; "
                         f"remedy: point the alias at a hostname (HostName <name>.local, AddressFamily inet)")
        probs.extend(check_target(alias, alias, host, relay_key(ctx, alias), ctx, None))
        probs.extend(hostkey_problems(alias, ctx))
        sp, si = supervisor_lines(alias, alias, ctx)
        probs.extend(sp)
        notes.extend(si)
    notes.extend(ctx.get("address_notes", []))
    return list(dict.fromkeys(probs)), notes


CONFIRM_SKEW_SECONDS = 300


def mirror_entry(name, sessions_dir):
    """The local registry entry of the mirror named `name` (carries unimatrixRemote and sessionId), or None."""
    try:
        files = sorted(Path(sessions_dir).glob("*.json"))
    except OSError:
        return None
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("name") == name and d.get("unimatrixRemote") and d.get("sessionId"):
            return d
    return None


def last_delivery(name, deliveries):
    """The newest deliveries.jsonl row for a send to mirror `name`, or None."""
    try:
        lines = Path(deliveries).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    found = None
    for raw in lines:
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict) and str(row.get("target", "")).startswith(f"{name} (pid "):
            found = row
    return found


def confirm(name, ctx, out, sessions_dir=None, deliveries=None, channel=None):
    """`confirm <mirror-name>`: ask the far relay whether it holds a receipt for the last delivery to the mirror.

    Prints CONFIRMED or UNCONFIRMED (with the reason); returns 0 only for CONFIRMED, 1 otherwise."""
    home = ctx["roster"].settings_home()
    entry = mirror_entry(name, sessions_dir or Path.home() / ".claude" / "sessions")
    if entry is None:
        print(f"UNCONFIRMED: no mirror named {name} in the local session registry", file=out)
        return 1
    row = last_delivery(name, deliveries or Path(home) / "unimatrix" / "deliveries.jsonl")
    if row is None:
        print(f"UNCONFIRMED: no delivery to {name} is recorded", file=out)
        return 1
    if not row.get("ok"):
        print(f"UNCONFIRMED: the last delivery to {name} failed ({row.get('error')})", file=out)
        return 1
    digest = row.get("digest")
    if not digest:
        print(f"UNCONFIRMED: the last delivery to {name} carries no digest (the bridge predates receipts)", file=out)
        return 1
    mux = _load("unimatrix_box_mux", "lib/unimatrix_box_mux.py")
    remote = entry["unimatrixRemote"]
    key = relay_key(ctx, mux.resolve_remote(remote)[1], remote.rpartition("@")[2])
    if channel is None:
        channel = lambda r, k: mux.for_remote(r, key=k, extra=["-o", "ConnectTimeout=10"])
    since = max(0, int((row.get("at") or 0) - CONFIRM_SKEW_SECONDS))
    r = channel(remote, key).run(f"receipts {entry['sessionId']} {since}", b"", timeout=30)
    def text(stream):
        return stream.decode("utf-8", "replace") if isinstance(stream, bytes) else (stream or "")

    reply, err = text(r.stdout), text(r.stderr)
    if "usage:" in reply or "usage:" in err:
        print("UNCONFIRMED: the far relay lacks receipts; upgrade it", file=out)
        return 1
    if r.returncode:
        print(f"UNCONFIRMED: the far relay did not answer ({err.strip()[:200]})", file=out)
        return 1
    try:
        rows = json.loads(reply.strip().splitlines()[-1])["rows"]
    except (ValueError, KeyError, IndexError, TypeError):
        print("UNCONFIRMED: the far relay's receipts reply was unreadable", file=out)
        return 1
    if any(isinstance(x, dict) and x.get("digest") == digest for x in rows):
        print(f"CONFIRMED: the far box holds a receipt for the last delivery to {name}", file=out)
        return 0
    print(f"UNCONFIRMED: the far box holds no receipt for the last delivery to {name}", file=out)
    return 1


def main(argv=None, run=subprocess.run, resolve=socket.getaddrinfo, connect=socket.create_connection,
         authorized_keys=None, self_names=None, platform=None, out=None, roster=None,
         autolink=None, far_sshd_log=None, launchctl_list=None, relay_ps=None, environ=None, read_key=None,
         known_hosts=None, sessions_dir=None, deliveries=None, channel=None):
    out = out or sys.stdout
    al = autolink or _load("unimatrix_autolink", "unimatrix-autolink.py")
    roster = roster or al._roster()
    if argv and argv[0] == "confirm":
        if len(argv) != 2:
            print("usage: unimatrix-doctor.py [confirm <mirror-name>]", file=out)
            return 2
        return confirm(argv[1], {"autolink": al, "roster": roster, "run": run}, out,
                       sessions_dir=sessions_dir, deliveries=deliveries, channel=channel)
    mem = al._membership()
    plat = platform or sys.platform
    admin = Path(os.environ.get("ProgramData") or Path(os.environ.get("SystemDrive", "C:") + os.sep) / "ProgramData") / "ssh" / "administrators_authorized_keys" \
        if plat == "win32" else None
    ctx = {"autolink": al, "roster": roster, "membership": mem, "run": run, "resolve": resolve, "connect": connect,
           "authorized_keys": Path(authorized_keys) if authorized_keys else Path.home() / ".ssh" / "authorized_keys",
           "self_names": self_names, "admin_file": admin, "far_sshd_log": far_sshd_log, "platform": plat,
           "launchctl_list": launchctl_list or run_launchctl_list, "relay_ps": relay_ps,
           "environ": os.environ if environ is None else environ, "read_key": read_key, "known_hosts": known_hosts}
    probs, notes = diagnose(ctx)
    for p in probs:
        print(f"problem: {p}", file=out)
    for n in notes:
        print(f"info: {n}", file=out)
    return 1 if probs else 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in sys.argv[1:]):
        print("usage: unimatrix-doctor [-h]\nunimatrix health diagnostic")
        raise SystemExit(0)
    sys.exit(main(sys.argv[1:]))
