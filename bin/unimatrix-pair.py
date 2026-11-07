"""Unimatrix pairing CLI: pin the signer, request a join, approve or revoke a member, fetch the snapshot.

Only `approve` and `revoke` construct a signer, and each signs exactly once; 1Password is touched for
nothing else. `pin`, `request` and `fetch` need no signer. The signed snapshot, the pin and the
verification live in unimatrix-membership.py; authorized_keys reconcile and `membership put|get` live in
unimatrix-relay.py. This file wires them: build the next snapshot, sign, adopt locally through the relay's
own put path, push to each reachable member over this box's relay key.

Usage: unimatrix-pair.py pin <pubfile> | request [--box B] [--cidr C]... | approve <request-file|-> |
       revoke <box> | fetch <host>
"""
import argparse
import base64
import getpass
import importlib.util
import json
import os
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
    h = Path(home) if home else Path.home()
    if plat == "win32":
        return WINDOWS_AGENT_PIPE
    if plat == "darwin":
        return str(h / "Library" / "Group Containers" / "2BUA8C4S2C.com.1password" / "t" / "agent.sock")
    return str(h / ".1password" / "agent.sock")


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


def local_member(box, cidrs, own_key_fn):
    """This box's membership record: `<box>.local`, the current user, and its relay public key."""
    _, body = own_key_fn(box)
    return {"box": box, "host": f"{box}.local", "user": getpass.getuser(),
            "relay_pub": f"ssh-ed25519 {body}", "from_cidrs": list(cidrs)}


def _default_own_key(box):
    return _mod("unimatrix-install.py").pair_key(box)


def default_box():
    return socket.gethostname().split(".")[0]


def push_one(member, snapshot_line, sig_line, key, run):
    """pushed | offline | refused: <reason> for one member over `ssh -i key user@host membership put`."""
    cmd = ["ssh", "-i", str(key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
           f"{member['user']}@{member['host']}", "membership", "put"]
    try:
        r = run(cmd, input=f"{snapshot_line}\n{sig_line}\n".encode("ascii"), capture_output=True,
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


def _apply(mem, relay, home, snap, signer, run, notifier, authorized_keys, is_admin, box, own_key_fn, self_names, out):
    """Sign `snap` once, adopt it through the relay's put path, then push to the other members."""
    sig = signer.sign(mem.canonical_bytes(snap))
    snapshot_line = mem.canonical_bytes(snap).decode("ascii")
    sig_line = base64.b64encode(sig).decode("ascii")
    kw = {"is_admin": is_admin} if is_admin else {}
    reply = relay.membership_put(home, snapshot_line, sig_line, mem, authorized_keys, notifier=notifier, run=run, **kw)
    if reply.get("ok") is not True:
        raise mem.MembershipError(f"signed snapshot was not adopted: {reply.get('reason')}")
    print(f"epoch {snap['epoch']} adopted locally; authorized_keys {reply.get('authorized_keys')}", file=out)
    key, _ = own_key_fn(box)
    me = {n.lower() for n in self_names}
    for m in snap["members"]:
        if m["box"].lower() in me or m["host"].split(".")[0].lower() in me:
            continue
        print(f"  {m['box']}: {push_one(m, snapshot_line, sig_line, key, run)}", file=out)


def main(argv=None, out=None, err=None, stdin=None, home=None, environ=None, run=subprocess.run, signer=None,
         notifier=None, own_key_fn=None, authorized_keys=None, is_admin=None, box=None, self_names=None):
    """Run one subcommand; return the exit status. Every collaborator is injectable for tests."""
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
    own_key_fn = own_key_fn or _default_own_key
    box = box or getattr(args, "box", None) or default_box()
    try:
        if args.cmd == "pin":
            print(mem.write_pin(home, Path(args.pubfile).read_text(encoding="utf-8")), file=out)
            return 0
        if args.cmd == "request":
            print(json.dumps(local_member(box, args.cidr, own_key_fn), sort_keys=True), file=out)
            return 0
        relay = _mod("unimatrix-relay.py")
        ak = Path(authorized_keys) if authorized_keys else Path.home() / ".ssh" / "authorized_keys"
        pin = mem.load_pin(home)
        if pin is None:
            raise mem.MembershipError("no signer pin; run `unimatrix-pair.py pin <pubfile>` first")
        if args.cmd == "fetch":
            if args.host.startswith("-"):
                raise mem.MembershipError(f"invalid host {args.host!r}")
            key, _ = own_key_fn(box)
            cmd = ["ssh", "-i", str(key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
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
            if prev is None:
                me = local_member(box, args.self_cidr, own_key_fn)
                base = mem.next_snapshot(None, {"op": "join", "member": me})
                snap = mem.next_snapshot(base, {"op": "join", "member": member})
                snap = {**snap, "epoch": 1, "prev_digest": mem.GENESIS_DIGEST}
            else:
                snap = mem.next_snapshot(prev, {"op": "join", "member": member})
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
        _apply(mem, relay, home, snap, signer, run, notifier, ak, is_admin, box, own_key_fn, names, out)
        return 0
    except (mem.MembershipError, ValueError, RuntimeError, OSError) as ex:
        print(f"unimatrix-pair: {ex}", file=err)
        return 1


if __name__ == "__main__":
    sys.exit(main())
