"""Diagnose every Unimatrix link, both sides: unsigned authorized_keys lines, dead or IP-pinned aliases.

Usage:
  unimatrix-doctor.py

Prints one `problem:` line per fault and exits 1 when there is any, else 0. Never constructs a signer and
never touches 1Password: the membership snapshot is verified offline against the pinned public key.

Checks, per link target (every verified member except this box, plus each `unimatrix.far_boxes` alias):
the name resolves, TCP 22 connects, the relay key answers `roster`, the peer's own snapshot lists this box
at the same epoch (members only), and both bridge supervisors are alive. Locally: every authorized_keys line
that forces unimatrix-relay.py must carry a key that belongs to a verified member. The Windows
administrators_authorized_keys file is reported, never read. Network probes are injectable (run=, resolve=,
connect=); remote round trips are outside the 500ms bar, the local verify path is not.
"""
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


def key_bodies(members):
    return {m["relay_pub"].split()[1] for m in members}


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


def check_target(remote, name, host, key, ctx, peer_epoch_check):
    """Problem lines for one link target. `remote` is the dialled token, `name` the box or alias, `host` the DNS name."""
    al, roster, run = ctx["autolink"], ctx["roster"], ctx["run"]
    probs = []
    try:
        ctx["resolve"](host, 22)
    except OSError as ex:
        return [f"{name}: {host} does not resolve ({type(ex).__name__})"]
    try:
        ctx["connect"]((host, 22), timeout=TCP_SECONDS).close()
    except OSError as ex:
        return [f"{name}: {host} refuses TCP 22 ({type(ex).__name__})"]
    if not Path(key).is_file():
        probs.append(f"{name}: no relay key (looked for {key})")
    else:
        why = al.probe(roster, remote, key, run=run, remote=remote)
        if why:
            return probs + [f"{name}: relay key does not answer `roster` ({why})"]
        if peer_epoch_check:
            probs.extend(peer_epoch_check(remote, key, name))
    rec = al.read_record(al.state_dir(roster) / f"autolink-{al.slug(remote)}.json")
    for role, _ in al.SUPERVISORS:
        if not al.supervisor_live(roster, rec.get(role) or {}):
            probs.append(f"{name}: {role} supervisor is not alive")
    return probs


def relay_key(ctx, name):
    """The relay key autolink would use for `name`, with every lookup spawn routed through the injected run."""
    al, roster, run = ctx["autolink"], ctx["roster"], ctx["run"]
    return al.resolve_key(roster, name, local_fn=lambda r, a: al.machine_local_key(r, a, run=run),
                          ssh_fn=lambda r, a: al.ssh_identity_file(r, a, run=run))


def peer_lists_us(ctx, mine, self_names):
    """A checker (remote, key, name) -> problems: the peer's snapshot must list this box at this epoch."""
    run, roster = ctx["run"], ctx["roster"]

    def check(remote, key, name):
        cmd = ["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
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
        if theirs.get("epoch") != mine["epoch"]:
            probs.append(f"{name}: peer holds snapshot epoch {theirs.get('epoch')}, this box holds {mine['epoch']}")
        return probs

    return check


def diagnose(ctx):
    al, roster, mem = ctx["autolink"], ctx["roster"], ctx["membership"]
    home = roster.settings_home()
    probs, notes, signed = [], [], set()
    names = ctx["self_names"] if ctx["self_names"] is not None else al.own_names()
    status, targets, epoch, why = al.member_targets(roster, mem, names, run=ctx["run"])
    pin = mem.load_pin(home)
    if pin:
        try:
            notes.append(f"pin {mem.fingerprint(pin)}")
        except mem.MembershipError as ex:
            probs.append(f"signer pin unusable: {ex}")
    if status == "bad":
        probs.append(why)
    elif status == "none":
        probs.append("no signed membership snapshot is stored; every unimatrix authorized_keys line is unsigned")
    else:
        signed = key_bodies(mem.verified_members(home, run=ctx["run"]))
    ak = ctx["authorized_keys"]
    for n, body in unsigned_authorized_lines(ak, signed):
        probs.append(f"{ak} line {n}: forced unimatrix-relay.py key {_short(body) if body else '(unparsable)'} "
                     "is in no signed membership record")
    admin = ctx["admin_file"]
    if admin is not None and admin.exists():
        notes.append(f"{admin} exists and is not inspected here")

    mine = {"epoch": epoch}
    checker = peer_lists_us(ctx, mine, names) if status == "ok" else None
    seen = set()
    for remote, box in sorted(targets.items()):
        seen.add(remote)
        host = remote.rpartition("@")[2]
        probs.extend(check_target(remote, box, host, relay_key(ctx, box), ctx, checker))
    aliases, _ = al.far_boxes_status(roster)
    for alias in aliases:
        if alias in seen:
            continue
        host = ssh_hostname(alias, ctx["run"], roster.no_window())
        if host is None:
            probs.append(f"{alias}: far_boxes alias does not resolve in ssh config")
            continue
        if mem.is_ip_literal(host):
            probs.append(f"{alias}: far_boxes alias is pinned to IP {host}; a DHCP change breaks it")
        probs.extend(check_target(alias, alias, host, relay_key(ctx, alias), ctx, None))
    return probs, notes


def main(argv=None, run=subprocess.run, resolve=socket.getaddrinfo, connect=socket.create_connection,
         authorized_keys=None, self_names=None, platform=None, out=None, roster=None,
         autolink=None):
    out = out or sys.stdout
    al = autolink or _load("unimatrix_autolink", "unimatrix-autolink.py")
    roster = roster or al._roster()
    mem = al._membership()
    plat = platform or sys.platform
    admin = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "ssh" / "administrators_authorized_keys" \
        if plat == "win32" else None
    ctx = {"autolink": al, "roster": roster, "membership": mem, "run": run, "resolve": resolve, "connect": connect,
           "authorized_keys": Path(authorized_keys) if authorized_keys else Path.home() / ".ssh" / "authorized_keys",
           "self_names": self_names, "admin_file": admin}
    probs, notes = diagnose(ctx)
    for p in probs:
        print(f"problem: {p}", file=out)
    for n in notes:
        print(f"info: {n}", file=out)
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
