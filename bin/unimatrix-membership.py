"""Signed Unimatrix membership snapshots: canonical bytes, offline verify, replay checks, pin, event log.

Loaded by path (importlib), like unimatrix-autolink.py loads unimatrix-roster.py. `home` is the settings
home; state lives in `<home>/unimatrix/membership/`: snapshot.json, snapshot.sig, signer.pub (the pin),
events.log, verified.json (digest cache so an unchanged snapshot costs no spawn).

Only a Signer signs, and only approve/revoke callers construct one. Verification needs the pinned public
key and `ssh-keygen -Y verify`: no signer, no network, no 1Password.
"""
import base64
import binascii
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

NAMESPACE = "unimatrix-membership"
GENESIS_DIGEST = "0" * 64
SERVICE_TOKEN_ENV = "OP_SERVICE_ACCOUNT_TOKEN"
BOX_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}")
HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*")
USER_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,63}")
KEY_BODY_RE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
MEMBER_FIELDS = ("box", "host", "user", "relay_pub", "from_cidrs")
SNAPSHOT_FIELDS = ("collective", "epoch", "prev_digest", "members")
RUN_TIMEOUT_SECONDS = 30


class MembershipError(Exception):
    """A snapshot, signature, pin or change that must not be trusted or applied."""


def _no_window():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def membership_dir(home):
    return Path(home) / "unimatrix" / "membership"


def canonical_bytes(snap):
    """The exact bytes that are signed and digested: sorted keys, no whitespace, ASCII-escaped JSON."""
    return json.dumps(snap, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def digest(snap):
    return hashlib.sha256(canonical_bytes(snap)).hexdigest()


def is_ip_literal(host):
    h = host.strip()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    try:
        ipaddress.ip_address(h.split("%", 1)[0])
        return True
    except ValueError:
        return False


def _validate_member(m):
    if not isinstance(m, dict) or set(m) != set(MEMBER_FIELDS):
        raise MembershipError(f"member must have exactly {list(MEMBER_FIELDS)}")
    box, host, user, pub, cidrs = (m[k] for k in MEMBER_FIELDS)
    if not isinstance(box, str) or not BOX_RE.fullmatch(box):
        raise MembershipError(f"invalid box name {box!r}")
    if not isinstance(host, str) or is_ip_literal(host) or not HOST_RE.fullmatch(host):
        raise MembershipError(f"member {box}: host must be a DNS or .local name, not an IP literal ({host!r})")
    if not isinstance(user, str) or not USER_RE.fullmatch(user):
        raise MembershipError(f"member {box}: invalid user {user!r}")
    parts = pub.split() if isinstance(pub, str) else []
    if len(parts) < 2 or parts[0] != "ssh-ed25519" or not KEY_BODY_RE.fullmatch(parts[1]):
        raise MembershipError(f"member {box}: relay_pub must be an ssh-ed25519 public key")
    if not isinstance(cidrs, list):
        raise MembershipError(f"member {box}: from_cidrs must be a list")
    for c in cidrs:
        try:
            ipaddress.ip_network(c, strict=False)
        except (ValueError, TypeError):
            raise MembershipError(f"member {box}: invalid from_cidr {c!r}") from None


def _validate_shape(snap):
    if not isinstance(snap, dict) or set(snap) != set(SNAPSHOT_FIELDS):
        raise MembershipError(f"snapshot must have exactly {list(SNAPSHOT_FIELDS)}")
    if not isinstance(snap["collective"], str) or not snap["collective"]:
        raise MembershipError("collective must be a non-empty string")
    if type(snap["epoch"]) is not int or snap["epoch"] < 1:
        raise MembershipError("epoch must be an integer >= 1")
    pd = snap["prev_digest"]
    if not isinstance(pd, str) or not re.fullmatch(r"[0-9a-f]{64}", pd):
        raise MembershipError("prev_digest must be 64 lowercase hex chars")
    if not isinstance(snap["members"], list):
        raise MembershipError("members must be a list")
    seen = set()
    for m in snap["members"]:
        _validate_member(m)
        if m["box"] in seen:
            raise MembershipError(f"duplicate member {m['box']}")
        seen.add(m["box"])


# ---- pin ----------------------------------------------------------------------------------------

def _pin_fields(text):
    lines = [ln for ln in str(text).splitlines() if ln.strip()]
    parts = lines[0].split() if len(lines) == 1 else []
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise MembershipError("pin must be exactly one ssh-ed25519 public key line")
    try:
        raw = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError):
        raise MembershipError("pin key body is not base64") from None
    return parts[0], parts[1], raw


def fingerprint(pin_text):
    """OpenSSH-style `SHA256:<b64>` fingerprint, computed in-process."""
    raw = _pin_fields(pin_text)[2]
    return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")


def pin_path(home):
    return membership_dir(home) / "signer.pub"


def load_pin(home):
    """The pinned public key text, or None when no pin has been written."""
    try:
        return pin_path(home).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def write_pin(home, pub_text):
    """Write the pin once and return its fingerprint; refuses when a pin exists (no re-pin by a walk-by)."""
    kind, body, _ = _pin_fields(pub_text)
    path = pin_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "x", encoding="utf-8") as fh:
            fh.write(f"{kind} {body}\n")
    except FileExistsError:
        raise MembershipError(f"signer pin already exists at {path}; delete it deliberately to replace") from None
    return fingerprint(pub_text)


# ---- signers ------------------------------------------------------------------------------------

def refuse_service_token(environ=None):
    """The service-account route has no prompt, so no signer may run when its token is set."""
    if (os.environ if environ is None else environ).get(SERVICE_TOKEN_ENV):
        raise MembershipError(f"{SERVICE_TOKEN_ENV} is set; signing needs an interactive approval, not a service token")


def _run(cmd, run, **kw):
    try:
        return run(cmd, capture_output=True, timeout=RUN_TIMEOUT_SECONDS, creationflags=_no_window(), **kw)
    except (OSError, subprocess.SubprocessError) as ex:
        raise MembershipError(f"{cmd[0]} failed to run: {type(ex).__name__}") from None


class Signer:
    """Protocol: sign(payload_bytes) -> sig_bytes (an armored SSHSIG), raising MembershipError on refusal."""

    def sign(self, payload):
        raise NotImplementedError


class _KeygenSigner(Signer):
    def __init__(self, key_file, environ=None, run=subprocess.run, extra_env=None):
        self.key_file = str(key_file)
        self.environ = environ
        self.run = run
        self.extra_env = dict(extra_env or {})

    def sign(self, payload):
        refuse_service_token(self.environ)
        env = dict(os.environ if self.environ is None else self.environ)
        env.update(self.extra_env)
        r = _run(["ssh-keygen", "-Y", "sign", "-n", NAMESPACE, "-f", self.key_file], self.run, input=payload, env=env)
        if r.returncode or not r.stdout:
            raise MembershipError("signer refused or produced no signature: " + r.stderr.decode("utf-8", "replace").strip()[:200])
        return r.stdout


class FakeSigner(_KeygenSigner):
    """Signs with a key file on disk. Tests only: it never prompts."""


class AgentSigner(_KeygenSigner):
    """Signs through an ssh-agent holding the pinned key (`-f` is the pin's public half).

    `sock` is the agent socket or pipe; None leaves SSH_AUTH_SOCK as the environment has it. Per-platform
    socket resolution for the 1Password agent belongs to the caller that constructs this."""

    def __init__(self, pin_pub_file, sock=None, environ=None, run=subprocess.run):
        super().__init__(pin_pub_file, environ=environ, run=run, extra_env={"SSH_AUTH_SOCK": sock} if sock else None)


# ---- verify -------------------------------------------------------------------------------------

def _held_state(held):
    if held is None:
        return None
    if isinstance(held, dict) and "members" in held:
        return held["epoch"], digest(held)
    return held["epoch"], held["digest"]


def _check_chain(snap, held):
    st = _held_state(held)
    if st is None:
        if snap["epoch"] == 1 and snap["prev_digest"] != GENESIS_DIGEST:
            raise MembershipError("genesis snapshot must carry the zero prev_digest")
        return
    epoch, dig = st
    if snap["epoch"] <= epoch:
        raise MembershipError(f"replay: epoch {snap['epoch']} <= held epoch {epoch}")
    if snap["epoch"] == epoch + 1 and snap["prev_digest"] != dig:
        raise MembershipError("fork: prev_digest does not match the held snapshot")


def _ssh_verify(canon, sig, pin_text, run):
    kind, body, _ = _pin_fields(pin_text)
    tmp = tempfile.mkdtemp(prefix="unimatrix-verify-")
    try:
        allowed = Path(tmp) / "allowed_signers"
        sigfile = Path(tmp) / "snapshot.sig"
        allowed.write_text(f'signer namespaces="{NAMESPACE}" {kind} {body}\n', encoding="utf-8")
        sigfile.write_bytes(sig if isinstance(sig, bytes) else sig.encode("utf-8"))
        r = _run(["ssh-keygen", "-Y", "verify", "-f", str(allowed), "-I", "signer", "-n", NAMESPACE, "-s", str(sigfile)],
                 run, input=canon)
        if r.returncode:
            raise MembershipError("signature does not verify against the pinned key")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def verify_snapshot(snap, sig, pin, held=None, run=subprocess.run):
    """Return the member list of a snapshot signed by the pinned key, else raise MembershipError.

    `held` is the snapshot (or `{"epoch","digest"}`) this box already holds: epoch <= held is a replay and,
    for epoch == held+1, a prev_digest other than the held digest is a fork. A larger jump cannot be
    chain-checked (the box missed epochs) and is accepted on signature alone."""
    _validate_shape(snap)
    if pin is None:
        raise MembershipError("no signer pin; run pin first")
    _check_chain(snap, held)
    _ssh_verify(canonical_bytes(snap), sig, pin, run)
    return [dict(m) for m in snap["members"]]


# ---- snapshot build -----------------------------------------------------------------------------

def next_snapshot(prev, change):
    """The unsigned epoch+1 snapshot for `change`: `{"op": "join", "member": {...}}` or `{"op": "revoke", "box": name}`.

    `prev` None creates epoch 1 (change may carry `collective`, default "unimatrix")."""
    if not isinstance(change, dict):
        raise MembershipError("change must be a dict")
    if prev is None:
        collective, epoch, prev_digest, members = change.get("collective", "unimatrix"), 1, GENESIS_DIGEST, []
    else:
        _validate_shape(prev)
        collective, epoch, prev_digest = prev["collective"], prev["epoch"] + 1, digest(prev)
        members = [dict(m) for m in prev["members"]]
    op = change.get("op")
    if op == "join":
        member = change.get("member")
        _validate_member(member)
        if any(m["box"] == member["box"] for m in members):
            raise MembershipError(f"{member['box']} is already a member")
        members.append(dict(member))
    elif op == "revoke":
        box = change.get("box")
        if not any(m["box"] == box for m in members):
            raise MembershipError(f"{box!r} is not a member")
        members = [m for m in members if m["box"] != box]
    else:
        raise MembershipError(f"unknown change op {op!r}")
    members.sort(key=lambda m: m["box"])
    snap = {"collective": collective, "epoch": epoch, "prev_digest": prev_digest, "members": members}
    _validate_shape(snap)
    return snap


# ---- storage ------------------------------------------------------------------------------------

def load_snapshot(home):
    """(snapshot, sig_bytes) as stored, unverified; (None, None) when no snapshot has been adopted."""
    d = membership_dir(home)
    try:
        snap = json.loads((d / "snapshot.json").read_text(encoding="utf-8"))
        sig = (d / "snapshot.sig").read_bytes()
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as ex:
        raise MembershipError(f"stored snapshot unreadable ({type(ex).__name__})") from None
    return snap, sig


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _cache_key(snap, sig, pin):
    h = hashlib.sha256()
    for part in (canonical_bytes(snap), sig, pin.encode("utf-8")):
        h.update(hashlib.sha256(part).digest())
    return h.hexdigest()


def verified_members(home, run=subprocess.run):
    """Members of the stored snapshot, verified against the pin; [] when none is stored.

    An unchanged snapshot+sig+pin hits verified.json and spawns nothing."""
    snap, sig = load_snapshot(home)
    if snap is None:
        return []
    pin = load_pin(home)
    if pin is None:
        raise MembershipError("snapshot present but no signer pin")
    key = _cache_key(snap, sig, pin)
    cache = membership_dir(home) / "verified.json"
    try:
        if json.loads(cache.read_text(encoding="utf-8")).get("key") == key:
            _validate_shape(snap)
            return [dict(m) for m in snap["members"]]
    except (OSError, ValueError, AttributeError):
        pass
    members = verify_snapshot(snap, sig, pin, run=run)
    _atomic_write(cache, json.dumps({"key": key, "epoch": snap["epoch"]}).encode("utf-8"))
    return members


# ---- events and notification --------------------------------------------------------------------

def _desktop_notify(title, message, run=subprocess.run):
    """Best-effort platform notification; any failure or missing notifier is silent (the log is the record)."""
    try:
        if sys.platform == "darwin" and shutil.which("osascript"):
            script = "on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run"
            cmd = ["osascript", "-e", script, title, message]
        elif sys.platform == "win32":
            return False  # no non-shell notifier on Windows: events.log is the record
        elif shutil.which("notify-send"):
            cmd = ["notify-send", title, message]
        else:
            return False
        run(cmd, capture_output=True, timeout=12, creationflags=_no_window())
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def notify(home, event, desktop=_desktop_notify):
    """Append `event` (a dict) to events.log as one JSON line, then raise a desktop notification.

    The log append is the durable record; a missing notifier degrades to log-only and never raises."""
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **event}
    path = membership_dir(home) / "events.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    text = " ".join(str(rec.get(k, "")) for k in ("kind", "box", "epoch", "detail") if rec.get(k, "") != "")
    try:
        desktop("Unimatrix membership", text[:200])
    except Exception:  # noqa: BLE001 -- a notifier must never fail the membership operation
        pass
    return rec


def adopt(home, snap, sig, notifier=notify, run=subprocess.run):
    """Verify `snap` against the pin and the held epoch, write it atomically, log and notify. Return the members.

    A rejected snapshot appends a `refused` event (and notifies) before the error propagates, so a forged
    push is seen."""
    held, _ = load_snapshot(home)
    try:
        members = verify_snapshot(snap, sig, load_pin(home), held=held, run=run)
    except MembershipError as ex:
        notifier(home, {"kind": "refused", "epoch": snap.get("epoch") if isinstance(snap, dict) else None, "detail": str(ex)[:160]})
        raise
    d = membership_dir(home)
    _atomic_write(d / "snapshot.sig", sig if isinstance(sig, bytes) else sig.encode("utf-8"))
    _atomic_write(d / "snapshot.json", canonical_bytes(snap))
    pin = load_pin(home)
    _atomic_write(d / "verified.json", json.dumps({"key": _cache_key(snap, sig if isinstance(sig, bytes) else sig.encode("utf-8"), pin),
                                                   "epoch": snap["epoch"]}).encode("utf-8"))
    old = {m["box"] for m in held["members"]} if held else set()
    new = {m["box"] for m in members}
    for box in sorted(new - old):
        notifier(home, {"kind": "join", "box": box, "epoch": snap["epoch"]})
    for box in sorted(old - new):
        notifier(home, {"kind": "revoke", "box": box, "epoch": snap["epoch"]})
    if not (new ^ old):
        notifier(home, {"kind": "adopted", "epoch": snap["epoch"]})
    return members


# ---- authorized_keys ----------------------------------------------------------------------------

def authorized_keys_lines(members, relay_line_fn):
    """One authorized_keys line per member: `relay_line_fn(key_body)` with `from="<cidrs>",` prefixed.

    A member with no from_cidrs gets the relay line unprefixed."""
    out = []
    for m in members:
        _validate_member(m)
        line = relay_line_fn(m["relay_pub"].split()[1])
        out.append(f'from="{",".join(m["from_cidrs"])}",{line}' if m["from_cidrs"] else line)
    return out
