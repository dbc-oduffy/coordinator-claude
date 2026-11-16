#!/usr/bin/env python3
"""Unimatrix pairing CLI: pin the signer, request a join, approve or revoke a member, fetch the snapshot.

Only `approve` and `revoke` construct a signer, and each signs exactly once; 1Password is touched for
nothing else. `pin`, `request` and `fetch` need no signer. The signed snapshot, the pin and the
verification live in unimatrix-membership.py; authorized_keys reconcile and `membership put|get` live in
unimatrix-relay.py. This file wires them: build the next snapshot, sign, adopt locally through the relay's
own put path, push to each reachable member over this box's relay key.

Signer key setup (once, then pin on every box):
  1. In 1Password create an SSH Key item (type Ed25519), suggested title `unimatrix-signer`, in a vault
     the 1Password SSH agent exposes: Personal, Private or Employee by default, or any vault listed in
     the agent's agent.toml.
  2. Confirm the agent offers it: `ssh-add -L` lists the key (SSH_AUTH_SOCK pointing at the 1Password agent).
  3. Export the item's public key to a file (e.g. unimatrix-signer.pub).
  4. On every box run `unimatrix-pair.py pin <pubfile>`.

Adoption never drops a relay authorized_keys line whose key no held snapshot ever listed; such lines are
kept and reported as `unenrolled` events. Only a key the prior snapshot listed and the new one omits is dropped.

Usage: unimatrix-pair.py pin <pubfile> | request [--box B] [--cidr C]... | approve <request-file|-> |
       revoke <box> | fetch <host>
"""
import argparse
import base64
import getpass
import importlib.util
import json
import os
import posixpath
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUSH_TIMEOUT_SECONDS = 30
SIGN_TIMEOUT_SECONDS = 120
WINDOWS_KEYGEN = r"C:\Windows\System32\OpenSSH\ssh-keygen.exe"
WINDOWS_AGENT_PIPE = r"\\.\pipe\openssh-ssh-agent"

FRESHNESS_NOTE = (
    "Approval freshness depends on the operator's 1Password setting 'Ask approval for each new request': under the\n"
    "default settings an earlier approval can satisfy this signature until 1Password locks. The prompt does not show\n"
    "the payload; what is printed above is what you are approving."
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_MODS = {}


def _mod(script):
    if script not in _MODS:
        _MODS[script] = _load("unimatrix_pair_" + script[9:-3].replace("-", "_"), HERE / script)
    return _MODS[script]


def _no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def agent_socket(environ=None, platform=None, home=None):
    """The 1Password agent socket or pipe: an already-set SSH_AUTH_SOCK first, else the per-OS default."""
    env = os.environ if environ is None else environ
    if env.get("SSH_AUTH_SOCK"):
        return env["SSH_AUTH_SOCK"]
    plat = platform or sys.platform
    if plat == "win32":
        return WINDOWS_AGENT_PIPE
    h = Path(home) if home else Path.home()
    if plat == "darwin":
        return posixpath.join(h.as_posix(), "Library", "Group Containers", "2BUA8C4S2C.com.1password", "t", "agent.sock")
    return posixpath.join(h.as_posix(), ".1password", "agent.sock")


def make_agent_signer(mem, pin_pub_file, environ=None, run=subprocess.run, platform=None):
    """An AgentSigner that signs with `-U` (key held in the agent), waits long enough for a human, and names a
    suppressed background prompt on timeout. Windows uses the System32 OpenSSH ssh-keygen."""
    plat = platform or sys.platform

    class PairAgentSigner(mem.AgentSigner):
        def sign(self, payload):
            mem.refuse_service_token(self.environ)
            env = dict(os.environ if self.environ is None else self.environ)
            env.update(self.extra_env)
            keygen = WINDOWS_KEYGEN if plat == "win32" and os.path.isfile(WINDOWS_KEYGEN) else "ssh-keygen"
            cmd = [keygen, "-Y", "sign", "-U", "-n", mem.NAMESPACE, "-f", self.key_file]
            try:
                r = self.run(cmd, input=payload, env=env, capture_output=True, timeout=SIGN_TIMEOUT_SECONDS,
                             creationflags=_no_window())
            except subprocess.TimeoutExpired:
                raise mem.MembershipError("signing timed out: approve the 1Password prompt (it may show 'SSH request "
                                          "waiting' if 1Password is not in the foreground)") from None
            except (OSError, subprocess.SubprocessError) as ex:
                raise mem.MembershipError(f"ssh-keygen failed to run: {type(ex).__name__}") from None
            if r.returncode or not r.stdout:
                raise mem.MembershipError("signer refused or produced no signature: "
                                          + r.stderr.decode("utf-8", "replace").strip()[:200])
            return r.stdout

    return PairAgentSigner(pin_pub_file, sock=agent_socket(environ, plat), environ=environ, run=run)


def local_member(box, cidrs, own_key_fn, recorded_fn=None, member_boxes=None):
    """This box's membership record built from existing per-pair keys; never mints.

    With `recorded_fn(member_boxes)` (-> {alias: (key path, body)}, the per-pair keys this box deploys toward
    each peer): `relay_pub` is the key for `box` when present, else the lexically smallest alias's key, and
    `relay_pubs` holds every alias matching a `member_boxes` name case-insensitively (all valid box names when
    None), keyed by the member's spelling, skipping an alias whose key body repeats an earlier one. Without it,
    `relay_pub` is `own_key_fn(box)` alone. RuntimeError when no key is recorded."""
    base = {"box": box, "host": f"{box}.local", "user": getpass.getuser(), "from_cidrs": list(cidrs)}
    if recorded_fn is None:
        _, body = own_key_fn(box)
        return {**base, "relay_pub": f"ssh-ed25519 {body}"}
    recorded = recorded_fn(member_boxes)
    if not recorded:
        raise RuntimeError(f"no recorded pair key for {box}: no deployed per-pair key (ssh-config IdentityFile or "
                           f"unimatrix.keys record) found for any peer of this box")
    default = box if box in recorded else sorted(recorded)[0]
    wanted = {str(b).lower(): b for b in member_boxes} if member_boxes is not None else None
    pubs, seen = {}, set()
    for alias in sorted(recorded):
        body = recorded[alias][1]
        peer = alias if wanted is None else wanted.get(alias.lower())
        if body in seen or peer is None or peer in pubs or not _mod("unimatrix-membership.py").BOX_RE.fullmatch(peer):
            continue
        seen.add(body)
        pubs[peer] = f"ssh-ed25519 {body}"
    member = {**base, "relay_pub": f"ssh-ed25519 {recorded[default][1]}"}
    if pubs:
        member["relay_pubs"] = pubs
    return member


def _reissue_own(mem, snap, box, own_key_fn, recorded_fn):
    """`snap` with this box's own record carrying per-pair `relay_pubs` when the held one has none.

    Same epoch as `snap`; the held record's host, user, cidrs and relay_pub are kept. Unchanged without
    `recorded_fn`, without an own record, with `relay_pubs` already set, or when no pair key is recorded."""
    if recorded_fn is None:
        return snap
    own = next((m for m in snap["members"] if m["box"] == box), None)
    if own is None or own.get("relay_pubs"):
        return snap
    try:
        fresh = local_member(box, own["from_cidrs"], own_key_fn, recorded_fn, {m["box"] for m in snap["members"]})
    except RuntimeError:
        return snap
    if not fresh.get("relay_pubs"):
        return snap
    new = {**own, "relay_pubs": fresh["relay_pubs"]}
    out = {**snap, "members": [new if m["box"] == box else m for m in snap["members"]]}
    mem._validate_shape(out)
    return out


def _default_own_key(box):
    return _mod("unimatrix-install.py").pair_key(box, adopt_only=True)


def _default_recorded(peers=None):
    return _mod("unimatrix-install.py").recorded_pair_keys(peers=peers)


def _host_key(name):
    # Same normalisation as unimatrix-doctor.py and unimatrix-autolink.py :: _host_key; change all together.
    low = str(name).strip().lower().rstrip(".")
    return low[:-len(".local")] if low.endswith(".local") else low


def _ssh_hostname(alias):
    """The HostName `ssh -G` resolves for `alias`, else None."""
    try:
        r = subprocess.run(["ssh", "-G", "--", alias], capture_output=True, text=True, timeout=5,
                           creationflags=_no_window())
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode:
        return None
    for line in (r.stdout or "").splitlines():
        name, _, val = line.partition(" ")
        if name.lower() == "hostname":
            return val.strip()
    return None


def make_host_alias_fn(recorded_fn=None):
    """host -> the recorded pair-key alias whose own name or `ssh -G` HostName is that host (case-insensitive, `.local`
    ignored), else None. The recorded listing is read once. Each listing spawns the reader and `ssh -G` per
    alias, and `local_member` lists separately, so an approve costs two listings."""
    cache = {}

    def host_alias(host):
        if "aliases" not in cache:
            try:
                cache["aliases"] = sorted((recorded_fn or _default_recorded)())
            except RuntimeError:
                cache["aliases"] = []
        want = _host_key(host)
        names = cache.setdefault("names", {})
        for alias in cache["aliases"]:
            if _host_key(alias) == want:
                return alias
            if alias not in names:
                names[alias] = _host_key(_ssh_hostname(alias) or "")
            if names[alias] == want:
                return alias
        return None

    return host_alias


def box_variants(box):
    """`box` plus its lower-cased and hyphen/underscore-stripped spellings, distinct, `box` first (Mac-mini -> macmini)."""
    out = []
    for v in (box, box.lower(), box.lower().replace("-", "").replace("_", "")):
        if v and v not in out:
            out.append(v)
    return out


def _default_read_key(name):
    """The machine-local value of `name` through the bounded engine reader, '' when the reader is missing or fails."""
    roster = _mod("unimatrix-roster.py")
    reader = roster.settings_home() / "bin" / "_machine_local.py"
    if not reader.is_file():
        return ""
    try:
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
        import cc_invoke

        cc_invoke.ensure_engine_on_path(__file__)
        from coordinator_core import machine_local_spawn

        value, ok = machine_local_spawn.get(str(reader), name)
    except Exception:
        return ""
    return value.strip() if ok and value else ""


def default_address_fn(read_key=None):
    """box -> its `unimatrix.addresses.<box>` list, read through the far-box reader under each spelling of the box
    id until one is recorded; [] when none is."""
    far = _load("unimatrix_pair_far_addresses", HERE / "lib" / "unimatrix_far_addresses.py")

    def addresses(box):
        for variant in box_variants(box):
            found = far.box_addresses(variant, read_key or _default_read_key)
            if found:
                return found
        return []

    return addresses


def make_candidate_fn(address_fn):
    """(box, user) -> alias spellings to try for a member's pair key after its own name: the box id's case/hyphen
    variants, then `user@<address>` for each address recorded for the box. The address list is read once per box."""
    cache = {}

    def candidates(box, user):
        if box not in cache:
            cache[box] = list(address_fn(box) or [])
        return box_variants(box)[1:] + ([f"{user}@{a}" for a in cache[box]] if user else [])

    return candidates


def pair_key_for_host(box, host, own_key_fn, alias_fn=None, candidate_fn=None, user=None):
    """This box's adopt-only (key path, body) toward a member: the key of the alias its links use for `host`, else the
    key recorded for `box`, else (with `candidate_fn`) one recorded under a case/hyphen variant of the box id or as
    `user@<address>`. RuntimeError when none is recorded."""
    alias = alias_fn(host) if alias_fn else None
    first_err = None
    if alias and alias != box:
        try:
            return own_key_fn(alias)
        except RuntimeError as alias_err:
            try:
                return own_key_fn(box)
            except RuntimeError as box_err:
                first_err = RuntimeError(f"{box_err} (alias {alias} matched {host}: {alias_err})")
    else:
        try:
            return own_key_fn(box)
        except RuntimeError as box_err:
            first_err = box_err
    for name in (candidate_fn(box, user) if candidate_fn else ()):
        try:
            return own_key_fn(name)
        except RuntimeError:
            continue
    raise first_err from None


def default_box():
    return socket.gethostname().split(".")[0]


def push_one(member, snapshot_line, sig_line, key, run, pin_line=None):
    """pushed | offline | refused: <reason> for one member over `ssh -i key user@host membership put`.
    A `pin_line` rides as a third stdin line so a pinless receiver can seed its pin."""
    cmd = ["ssh", "-i", str(key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "AddressFamily=inet", "-o", "ConnectTimeout=5",
           f"{member['user']}@{member['host']}", "membership", "put"]
    lines = [snapshot_line, sig_line] + ([pin_line] if pin_line else [])
    try:
        r = run(cmd, input=("\n".join(lines) + "\n").encode("ascii"), capture_output=True,
                timeout=PUSH_TIMEOUT_SECONDS, creationflags=_no_window())
    except (OSError, subprocess.SubprocessError):
        return "offline"
    lines = (r.stdout or b"").decode("utf-8", "replace").strip().splitlines()
    try:
        reply = json.loads(lines[-1]) if lines else None
    except ValueError:
        reply = None
    if r.returncode == 0 and isinstance(reply, dict) and reply.get("ok") is True:
        return "pushed"
    if isinstance(reply, dict) and reply.get("ok") is False:
        return f"refused: {reply.get('reason', '')}"[:120]
    return "offline"


def _held_verified(mem, home, pin, run):
    snap, sig = mem.load_snapshot(home)
    if snap is None:
        return None, None
    mem.verify_snapshot(snap, sig, pin, run=run)
    return snap, sig


def _read_request(source, stdin):
    text = stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    try:
        req = json.loads(text)
    except ValueError:
        raise ValueError("join request is not valid JSON") from None
    if not isinstance(req, dict):
        raise ValueError("join request must be a JSON object")
    return req


def _describe(mem, m, out):
    print(f"  box:        {m['box']}", file=out)
    print(f"  host:       {m['host']}", file=out)
    print(f"  user:       {m['user']}", file=out)
    print(f"  from_cidrs: {', '.join(m['from_cidrs']) or '(none)'}", file=out)
    print(f"  relay_pub:  {mem.fingerprint(m['relay_pub'])}", file=out)


def _apply(mem, relay, home, snap, signer, run, notifier, authorized_keys, is_admin, box, own_key_fn, self_names, out,
          alias_fn=None, candidate_fn=None, target=None):
    """Sign `snap` once, adopt it through the relay's put path, then push to the other members."""
    sig = signer.sign(mem.canonical_bytes(snap))
    snapshot_line = mem.canonical_bytes(snap).decode("ascii")
    sig_line = base64.b64encode(sig).decode("ascii")
    kw = {"is_admin": is_admin} if is_admin else {}
    reply = relay.membership_put(home, snapshot_line, sig_line, mem, authorized_keys, notifier=notifier, run=run, **kw)
    if reply.get("ok") is not True:
        raise mem.MembershipError(f"signed snapshot was not adopted: {reply.get('reason')}")
    print(f"epoch {snap['epoch']} adopted locally; authorized_keys {reply.get('authorized_keys')}", file=out)
    _push_all(mem, home, snap, snapshot_line, sig_line, run, own_key_fn, self_names, out, alias_fn, candidate_fn, target)


def _others(snap, self_names):
    me = {n.lower() for n in self_names}
    return [m for m in snap["members"] if m["box"].lower() not in me and m["host"].split(".")[0].lower() not in me]


def _repush_command(target=None):
    """The approve invocation that re-pushes the held epoch; a stdin request is carried as a here-string."""
    return f"python {Path(__file__).resolve()} approve {target if target is not None else '<request file>'}"


def _refuse_if_none_pushable(snap, self_names, own_key_fn, alias_fn, candidate_fn, target=None):
    """MembershipError when `snap` has members besides this box and no pair key reaches any of them: signing would
    strand the epoch on this box."""
    others = _others(snap, self_names)
    for m in others:
        try:
            pair_key_for_host(m["box"], m["host"], own_key_fn, alias_fn, candidate_fn, m["user"])
            return
        except RuntimeError:
            continue
    if others:
        names = ", ".join(m["box"] for m in others)
        raise _mod("unimatrix-membership.py").MembershipError(
            f"no recorded pair key reaches any member to push to ({names}); nothing signed. Record a key "
            f"(unimatrix.keys.<alias>) toward one, then re-run: {_repush_command(target)}")


def _push_all(mem, home, snap, snapshot_line, sig_line, run, own_key_fn, self_names, out, alias_fn=None,
              candidate_fn=None, target=None):
    """Push the signed snapshot to every member that is not this box, one report line each."""
    pin = mem.load_pin(home)
    pin_line = " ".join(pin.split()[:2]) if pin else None
    for m in _others(snap, self_names):
        try:
            key, _ = pair_key_for_host(m["box"], m["host"], own_key_fn, alias_fn, candidate_fn, m["user"])
        except RuntimeError:
            print(f"  {m['box']}: refused: no recorded pair key for {m['box']}; once recorded, re-push: "
                  f"{_repush_command(target)}", file=out)
            continue
        print(f"  {m['box']}: {push_one(m, snapshot_line, sig_line, key, run, pin_line)}", file=out)


def main(argv=None, out=None, err=None, stdin=None, home=None, environ=None, run=subprocess.run, signer=None,
         notifier=None, own_key_fn=None, authorized_keys=None, is_admin=None, box=None, self_names=None,
         recorded_fn=None, alias_fn=None, address_fn=None):
    """Run one subcommand; return the exit status. Every collaborator is injectable for tests.
    `own_key_fn(box)` is this box's adopt-only (key path, body) for the pair with `box`; `recorded_fn()` lists every
    recorded pair key and `alias_fn(host)` names the recorded alias whose link reaches `host`; both default to the
    real ones only when `own_key_fn` is not injected."""
    out, err, stdin = out or sys.stdout, err or sys.stderr, stdin or sys.stdin
    ap = argparse.ArgumentParser(prog="unimatrix-pair.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pin").add_argument("pubfile")
    rq = sub.add_parser("request")
    rq.add_argument("--box")
    rq.add_argument("--cidr", action="append", default=[])
    for name in ("approve", "revoke"):
        p = sub.add_parser(name)
        p.add_argument("target")
        p.add_argument("--self-cidr", action="append", default=[], help="approve on a fresh collective: this box's from_cidrs")
    sub.add_parser("fetch").add_argument("host")
    args = ap.parse_args(argv)

    mem = _mod("unimatrix-membership.py")
    roster = _mod("unimatrix-roster.py")
    home = Path(home) if home else roster.settings_home()
    if own_key_fn is None:
        own_key_fn, recorded_fn = _default_own_key, recorded_fn or _default_recorded
        alias_fn = alias_fn or make_host_alias_fn(recorded_fn)
        address_fn = address_fn or default_address_fn()
    candidate_fn = make_candidate_fn(address_fn) if address_fn else None
    box = box or getattr(args, "box", None) or default_box()
    try:
        if args.cmd == "pin":
            print(mem.write_pin(home, Path(args.pubfile).read_text(encoding="utf-8")), file=out)
            return 0
        if args.cmd == "request":
            print(json.dumps(local_member(box, args.cidr, own_key_fn, recorded_fn), sort_keys=True), file=out)
            return 0
        relay = _mod("unimatrix-relay.py")
        ak = Path(authorized_keys) if authorized_keys else Path.home() / ".ssh" / "authorized_keys"
        pin = mem.load_pin(home)
        if pin is None:
            raise mem.MembershipError("no signer pin; run `unimatrix-pair.py pin <pubfile>` first")
        if args.cmd == "fetch":
            if args.host.startswith("-"):
                raise mem.MembershipError(f"invalid host {args.host!r}")
            label = args.host.rpartition("@")[2]
            key, _ = pair_key_for_host(label.split(".")[0], label, own_key_fn, alias_fn, candidate_fn,
                                       args.host.rpartition("@")[0] or None)
            cmd = ["ssh", "-i", str(key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "AddressFamily=inet", "-o", "ConnectTimeout=5",
                   args.host, "membership", "get"]
            r = run(cmd, capture_output=True, timeout=PUSH_TIMEOUT_SECONDS, creationflags=_no_window())
            lines = (r.stdout or b"").decode("utf-8", "replace").splitlines()
            if r.returncode or len(lines) < 2:
                raise mem.MembershipError(f"{args.host} returned no membership snapshot")
            kw = {"is_admin": is_admin} if is_admin else {}
            reply = relay.membership_put(home, lines[0], lines[1], mem, ak, notifier=notifier, run=run, **kw)
            if reply.get("ok") is not True:
                raise mem.MembershipError(f"fetched snapshot refused: {reply.get('reason')}")
            print(f"epoch {reply['epoch']} adopted; authorized_keys {reply.get('authorized_keys')}", file=out)
            return 0

        mem.refuse_service_token(environ)
        prev, _ = _held_verified(mem, home, pin, run)
        names = self_names if self_names is not None else {box, default_box()}
        if args.cmd == "approve":
            member = _read_request(args.target, stdin)
            hint = args.target if args.target != "-" else f"- <<< '{json.dumps(member, sort_keys=True)}'"
            if prev is None:
                me = local_member(box, args.self_cidr, own_key_fn, recorded_fn, {box, member.get("box")})
                base = mem.next_snapshot(None, {"op": "join", "member": me})
                snap = mem.next_snapshot(base, {"op": "join", "member": member})
                snap = {**snap, "epoch": 1, "prev_digest": mem.GENESIS_DIGEST}
            elif member in prev["members"]:
                held, held_sig = mem.load_snapshot(home)
                print(f"{member['box']} is already a member; re-pushing epoch {held['epoch']}", file=out)
                _push_all(mem, home, held, mem.canonical_bytes(held).decode("ascii"),
                          base64.b64encode(held_sig).decode("ascii"), run, own_key_fn, names, out, alias_fn, candidate_fn, hint)
                return 0
            else:
                snap = mem.next_snapshot(prev, {"op": "join", "member": member})
                snap = _reissue_own(mem, snap, box, own_key_fn, recorded_fn)
            _refuse_if_none_pushable(snap, names, own_key_fn, alias_fn, candidate_fn, hint)
            print(f"Join request to approve (pin {mem.fingerprint(pin)}):", file=out)
            _describe(mem, member, out)
        else:
            if prev is None:
                raise mem.MembershipError("no membership snapshot held; nothing to revoke")
            target = next((m for m in prev["members"] if m["box"] == args.target), None)
            snap = mem.next_snapshot(prev, {"op": "revoke", "box": args.target})
            print(f"Revocation to approve (pin {mem.fingerprint(pin)}):", file=out)
            _describe(mem, target, out)
        print(FRESHNESS_NOTE, file=out)
        if signer is None:
            signer = make_agent_signer(mem, mem.pin_path(home), environ=environ, run=run)
        _apply(mem, relay, home, snap, signer, run, notifier, ak, is_admin, box, own_key_fn, names, out, alias_fn,
               candidate_fn, hint if args.cmd == "approve" else None)
        return 0
    except (mem.MembershipError, ValueError, RuntimeError, OSError) as ex:
        print(f"unimatrix-pair: {ex}", file=err)
        return 1


if __name__ == "__main__":
    sys.exit(main())
