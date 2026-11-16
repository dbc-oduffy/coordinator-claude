#!/usr/bin/env python3
"""Forced command for the unimatrix key on the receiving box: the ONLY thing that key
can run. It moves Claude Code cross-session messages between boxes and nothing else. File put/get
belongs to a separate key and forced command (unimatrix-file-relay.py); this one refuses both.

authorized_keys line (restrict = no pty, no forwarding of any kind; key body elided). The exact
line for a box, with absolute interpreter and relay paths, is printed by `unimatrix-install.py --install`:
  restrict,command="/opt/homebrew/bin/python3 /Users/me/.coordinator-claude-settings/unimatrix/unimatrix-relay.py" ssh-ed25519 <key-body> unimatrix

Modes, read from SSH_ORIGINAL_COMMAND:
  roster            print one JSON line per live local session: its registry entry
                    plus key file, so the far box can mirror it and SendMessage it.
  roster --mirrors  also print each mirror row the export skips, entry only and no key (diagnosis).
  send <pid>        read one message line on stdin and deliver it to that live
                    session's socket.
  send-batch <pid>  deliver every stdin line to that session; prints one JSON result
                    line ({"ok": true} or {"ok": false, "error": ...}) per message line.
  send-to <pid> <digest>
                    send-batch, but only when the pid's live endpoint hashes to <digest>
                    (first 16 hex of sha256 of the socket path); else exits `target mismatch`
                    before reading any line.
  send-named <pid> <digest> <name-digest>
                    send-to, and also refuses (`target mismatch`, `ambiguous`) unless the pid's
                    exported name hashes to <name-digest> and no other live local session
                    exports that name; checked before reading any line.
  send-session <pid> <digest> <name-digest> <session-id>
                    send-named, and also refuses (`target mismatch`) unless the pid's entry
                    carries exactly that sessionId; checked before reading any line.
  inbox <name>      register <name> as a session living on this box (entry + key on
                    stdin, two lines), listen on /tmp/cc-socks/unimatrix-<name>.sock, and
                    write each message delivered there to stdout as one line, so the
                    far box can hand it to the real session. Runs until ssh drops
                    (stdin EOF), then removes only the socket it bound. Local-only:
                    ordinary inbox mirrors are never advertised through roster.
  reply-inbox <name>
                    same lifetime and wire format as inbox, but explicitly advertise
                    this temporary transport endpoint to directly connected boxes.
                    Downstream mirrors are never re-exported.
  mirror-stale <name> <backoff|dead> <until-epoch> <box>
                    mark the sending box's mirror of <name> stale until that epoch; the router's
                    agent listing shows it as stale. `inbox <name>` clears the mark.
  source            print this file, so far boxes can vendor the current relay.
  receipts <session-id> <since>
                    print {"ok": true, "rows": [...]}: this box's delivery receipts (session, sha256
                    digest of the line, at/ts) for the session since that epoch. `send-session` appends one
                    per line it wrote; the message text is never stored.
  grant <grantee> <note> <ttl> <repo>
                    read the issuer's signed grant envelope (one JSON line on stdin) and hand
                    it to suite_grant.receive_relayed_grant; prints its JSON reply, exit 0 only
                    when accepted. Argv must restate the envelope or the grant is refused.
  revoke <box>:<session>
                    read the issuer's signed suite-grant-revoke envelope (one JSON line on stdin) and
                    hand it to relayed_grant_peer.receive_relayed_revoke; exit 0 only when revoked.
  keypin <box_id>   read {"box_id", "key_b64"} (one JSON line on stdin) and pin that key through
                    relayed_grant_peer.receive_key_pin; refused `no_peer` without the forced command's
                    `--peer`, `issuer_not_peer` unless box_id is that peer.
  freshness         print {"ok": true, "box_id", "result"}: this box's klabauter clone freshness from the
                    engine (fetching, and advancing the clone when the engine's freshness pass does);
                    {"ok": false, "reason"} and exit 1 when the engine cannot run.
  grant, revoke and keypin refuse `issuer_not_peer` when `--peer` is set and the envelope's issuer box differs.
  membership get    print the held signed membership snapshot (canonical JSON line, then its
                    base64 signature line); exit 1 when none is held.
  membership put    read the snapshot line and base64 signature line (and an optional signer
                    pin line, honoured only by a receiver holding no pin, and only when the
                    snapshot verifies against it) on stdin, verify against
                    the pinned signer key and the held epoch, adopt, and reconcile the
                    relay-managed authorized_keys lines (from= and --peer pins generated);
                    prints a JSON reply, exit 0 only when adopted. The relay never signs.

Wire facts this relies on (Claude Code 2.1.3xx, peerProtocol 1): a message is one
JSON line per connection, sender writes and closes, receiver sends nothing back.
A receiver only accepts a socket listed in ~/.claude/sessions with a key file.
"""
import base64
import hashlib
import json
import os
import re
import select
import shlex
import signal
import socket
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SESS = "~/.claude/sessions"
SOCKS = os.environ.get("UNIMATRIX_LOOPBACK_SOCKS") or "/tmp/cc-socks"  # override: tests only, never a live dir
INBOX_NAME_RE = re.compile(r"[A-Za-z0-9_-](?:[A-Za-z0-9_.-]{0,62}[A-Za-z0-9_-])?")


DIGEST_RE = re.compile(r"[0-9a-f]{16}")
GRANTEE_TOKEN_RE = re.compile(r"[A-Za-z0-9._:@-]{1,260}")
SESSION_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")


def socket_digest(path):
    """First 16 hex chars of the sha256 of a session endpoint path: the identity `send-to` verifies."""
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def name_digest(name):
    """First 16 hex chars of the sha256 of a session name: the identity `send-named` verifies."""
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]


def valid_inbox_name(name):
    """1-64 ASCII routing characters, no edge dots or consecutive dots/path traversal."""
    return isinstance(name, str) and ".." not in name and INBOX_NAME_RE.fullmatch(name) is not None
# Remote-supplied registry fields a mirror entry passes through; pid, socket path and
# procStart are set locally so the far box cannot point a mirror at a local socket.
MIRROR_FIELDS = {"cwd", "entrypoint", "kind", "nameSince", "nameSource", "peerFeatures",
                 "peerProtocol", "sessionId", "startedAt", "status", "statusUpdatedAt",
                 "updatedAt", "version"}


STALE_STATES = ("backoff", "dead")
STALE_SUFFIX = ".stale.json"


def stale_marker_path(name):
    return f"{SOCKS}/unimatrix-{name}{STALE_SUFFIX}"


def mark_stale(name, state, until, box):
    """Record that the sending box's mirror of `name` is down until epoch `until`.

    The far router's agent listing reads this marker, so a sender here sees the name as stale
    instead of not at all. `inbox` clears it when the mirror registers again. The marker is filed under
    the registered name but lists under the sender-box label the live mirror row carries."""
    os.makedirs(SOCKS, mode=0o700, exist_ok=True)
    path = stale_marker_path(name)
    tmp = f"{path}.tmp{os.getpid()}"
    label = client_box(client_address())[1]
    shown = f"{name.partition('.')[0]}.{label}" if label else name
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"name": shown, "state": state, "until": until, "box": box}, fh)
    os.replace(tmp, path)
    return {"ok": True}


# Every verb parse_mode accepts; a sender probes this list instead of guessing a far mirror's version.
CAPABILITIES = ["roster", "source", "specs", "capabilities", "send", "send-batch", "send-to", "send-named",
                "send-session", "receipts", "inbox-mux", "inbox", "reply-inbox", "mirror-stale",
                "membership", "grant", "revoke", "keypin", "roster-mirrors", "freshness"]


def parse_mode(original_command):
    """Map an SSH_ORIGINAL_COMMAND string to (mode, arg) or None when it is not allowed."""
    cmd = (original_command or "").split()
    if cmd == ["capabilities"]:
        return "capabilities", None
    if cmd == ["roster"]:
        return "roster", None
    if cmd == ["roster", "--mirrors"]:
        return "roster", "mirrors"
    if cmd == ["source"]:
        return "source", None
    if cmd == ["specs"]:
        return "specs", None
    if cmd == ["freshness"]:
        return "freshness", None
    if len(cmd) == 2 and cmd[0] == "send" and cmd[1].isdigit():
        return "send", int(cmd[1])
    if len(cmd) == 2 and cmd[0] == "send-batch" and cmd[1].isdigit():
        return "send-batch", int(cmd[1])
    if len(cmd) == 3 and cmd[0] == "send-to" and cmd[1].isdigit() and DIGEST_RE.fullmatch(cmd[2]):
        return "send-to", (int(cmd[1]), cmd[2])
    if (len(cmd) == 4 and cmd[0] == "send-named" and cmd[1].isdigit()
            and DIGEST_RE.fullmatch(cmd[2]) and DIGEST_RE.fullmatch(cmd[3])):
        return "send-named", (int(cmd[1]), cmd[2], cmd[3])
    if (len(cmd) == 5 and cmd[0] == "send-session" and cmd[1].isdigit()
            and DIGEST_RE.fullmatch(cmd[2]) and DIGEST_RE.fullmatch(cmd[3])
            and SESSION_ID_RE.fullmatch(cmd[4])):
        return "send-session", (int(cmd[1]), cmd[2], cmd[3], cmd[4])
    if (len(cmd) == 3 and cmd[0] == "receipts" and SESSION_ID_RE.fullmatch(cmd[1])
            and RECEIPT_SINCE_RE.fullmatch(cmd[2])):
        return "receipts", (cmd[1], float(cmd[2]))
    if cmd == ["inbox-mux"]:
        return "inbox-mux", None
    if (len(cmd) == 2 and cmd[0] in ("inbox", "reply-inbox") and valid_inbox_name(cmd[1])
            and original_command == f"{cmd[0]} {cmd[1]}"):
        return cmd[0], cmd[1]
    if (len(cmd) == 5 and cmd[0] == "mirror-stale" and valid_inbox_name(cmd[1]) and cmd[2] in STALE_STATES
            and cmd[3].isdigit() and valid_inbox_name(cmd[4])):
        return "mirror-stale", (cmd[1], cmd[2], int(cmd[3]), cmd[4])
    if cmd == ["membership", "get"] or cmd == ["membership", "put"]:
        return "membership", cmd[1]
    if cmd and cmd[0] == "grant":
        return grant_args(original_command)
    if len(cmd) == 2 and cmd[0] == "revoke" and GRANTEE_TOKEN_RE.fullmatch(cmd[1]):
        return "revoke", {"grantee": cmd[1]}
    if len(cmd) == 2 and cmd[0] == "keypin" and valid_inbox_name(cmd[1]):
        return "keypin", {"box_id": cmd[1]}
    return None


def grant_args(original_command):
    """`grant <grantee> <note> <ttl> <repo>` (shell-quoted note; repo `-` = none) -> ("grant", dict) or None."""
    try:
        parts = shlex.split(original_command)
    except ValueError:
        return None
    if len(parts) != 5 or not parts[3].isdigit() or int(parts[3]) <= 0:
        return None
    _, grantee, note, ttl, repo = parts
    if not grantee or not note or not repo:
        return None
    return "grant", {"grantee": grantee, "note": note, "ttl": int(ttl),
                     "repo": None if repo == "-" else repo}


# Prefix-only containment: the registry entry is a local file owned by the harness.
PIPE_PREFIX = "\\\\.\\pipe\\"
TARGET_MISMATCH = "target mismatch"  # the bridge unmirrors a row on this refusal prefix


def endpoint_kind(platform=None):
    """Local-session endpoint family: named pipe on win32, unix socket on darwin/linux."""
    return "pipe" if (platform or sys.platform) == "win32" else "socket"


def alive(pid):
    if sys.platform == "win32":
        # os.kill(pid, 0) terminates the process on Windows; probe with OpenProcess instead.
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
        return bool(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


_LIVENESS = []


def _liveness():
    """The spawn-free liveness module beside this script, loaded by path on first use."""
    if not _LIVENESS:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "unimatrix_liveness", Path(__file__).resolve().parent / "unimatrix-liveness.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _LIVENESS.append(mod)
    return _LIVENESS[0]


def mirror_orphaned(d):
    """True for a roster-made mirror (it carries the far-socket field) whose recorded roster
    supervisor is not live; an entry that records no supervisor counts as orphaned."""
    if not isinstance(d, dict) or not d.get("macSocketPath"):
        return False
    return not _liveness().supervisor_live(
        {"pid": d.get("unimatrixRosterPid"), "procStart": d.get("unimatrixRosterProcStart")})


def _peers_file():
    home = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return (Path(home) if home else Path.home() / ".coordinator-claude-settings") / "unimatrix" / "peers.json"


def codex_holder_dead(d, holders):
    """True for a Codex face entry whose peers-file row records a holder that is dead or reused.

    `holders` is a one-slot cache of {target: peer row}. No recorded holder is unknown, not dead."""
    target = d.get("target")
    if d.get("vendor") != "codex" or d.get("unimatrixMirror") or not isinstance(target, str):
        return False
    if not holders:
        holders.append({str(r.get("target")): r for r in _liveness()._peer_rows(_peers_file())
                        if r.get("vendor") == "codex"})
    row = holders[0].get(target)
    return row is not None and _liveness().codex_holder_live(row) is False


def entries():
    holders = []
    for f in os.listdir(os.path.expanduser(SESS)):
        m = re.fullmatch(r"(\d+)(?:\.([0-9a-f]{16}))?\.json", f)
        if not m:
            continue
        pid = int(m.group(1))
        tag = m.group(2)
        try:
            with open(os.path.join(os.path.expanduser(SESS), f), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or d.get("pid") != pid or not _liveness().entry_live(d) or mirror_orphaned(d):
            continue
        if codex_holder_dead(d, holders):
            continue
        if tag is not None:
            # An inbox-mux entry: one process owns many names, so the key is the one for this socket.
            sock = d.get("messagingSocketPath")
            key = key_file_name(pid, sock) if isinstance(sock, str) else ""
            if tag != name_digest(str(d.get(MIRROR_NAME_FIELD) or d.get("name"))) or not os.path.isfile(
                    os.path.join(os.path.expanduser(SESS), key)):
                continue
            yield pid, d, key
            continue
        keys = [k for k in os.listdir(os.path.expanduser(SESS)) if k.startswith(f"{pid}.") and k.endswith(".key")]
        if len(keys) != 1:
            continue
        yield pid, d, keys[0]


def _engine_roots():
    """Candidate engine roots: env locators first, then the checkout this copy sits in."""
    for var in ("COORDINATOR_ENGINE_SOURCE_ROOT", "COORDINATOR_ENGINE_ROOT"):
        if os.environ.get(var):
            yield Path(os.environ[var])
    yield Path(__file__).resolve().parents[2]


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None


def _head_sha(root):
    """Checkout HEAD sha read from .git files (no git spawn); None when unresolvable."""
    git = Path(root) / ".git"
    if git.is_file():
        ptr = _read_text(git) or ""
        if not ptr.startswith("gitdir:"):
            return None
        git = (Path(root) / ptr[7:].strip()).resolve()
    head = _read_text(git / "HEAD")
    if not head:
        return None
    if not head.startswith("ref:"):
        return head
    ref = head[4:].strip()
    sha = _read_text(git / ref)
    if sha:
        return sha
    packed = _read_text(git / "packed-refs") or ""
    for ln in packed.splitlines():
        parts = ln.split()
        if len(parts) == 2 and parts[1] == ref:
            return parts[0]
    return None


def engine_fields():
    """engine_sha (published `_engine_stamp`), engine_checkout_sha and, when a surfaced record
    exists, engine_freshness. Standalone: reads files only, no coordinator_core import."""
    sha = checkout = None
    for root in _engine_roots():
        if sha is None:
            sha = _read_text(root / "coordinator_core" / "_engine_stamp")
        if checkout is None:
            checkout = _head_sha(root)
    out = {"engine_sha": sha, "engine_checkout_sha": checkout}
    home = Path(os.environ.get("COORDINATOR_SETTINGS_HOME") or Path.home() / ".coordinator-claude-settings")
    try:
        rec = json.loads((home / "coordinator" / "klabauter-freshness.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = None
    if isinstance(rec, dict) and rec:
        out["engine_freshness"] = rec
    return out


def _load_sibling(filename, modname):
    import importlib.util
    spec = importlib.util.spec_from_file_location(modname, Path(__file__).resolve().parent / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_CONTRACT = []


def local_box():
    """This box's id via the peer contract's one normaliser, loaded once."""
    if not _CONTRACT:
        _CONTRACT.append(_load_sibling("unimatrix-peer-contract.py", "unimatrix_relay_peer_contract"))
    return _CONTRACT[0].local_box()


def _console_python():
    """A real console CPython for a child argv; OSError when none resolves."""
    found = _load_sibling("lib/python_interp.py", "unimatrix_relay_python_interp").resolve_console_python()
    if not found:
        raise FileNotFoundError("no console Python interpreter resolvable")
    return found


def codex_export_refused(d, cache):
    """True for a local Codex face whose thread is not an independently sendable root (state DB)
    or has no addressable rollout (absent, or a sub-agent's session_meta): far boxes must not
    list what a send to it would fail on. `cache` holds the scan's modules, metadata and rollout index."""
    target = d.get("target")
    if d.get("vendor") != "codex" or d.get("unimatrixMirror") or not isinstance(target, str):
        return False
    if not cache:
        router = _load_sibling("unimatrix-peer-router.py", "unimatrix_peer_router")
        codex = _load_sibling("unimatrix-peer-codex.py", "unimatrix_peer_codex")
        home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        cache.update(router=router, codex=codex, home=home,
                     metadata=router.codex_thread_metadata(home), index=codex.rollout_index(home))
    if not cache["router"].codex_is_sendable_root(cache["metadata"].get(target, {})):
        return True
    return not cache["codex"].thread_addressable(target, cache["home"], cache["index"])


def relay_sha():
    """First 12 hex of the sha256 of this script with CRLF folded to LF (so a Windows checkout and a
    macOS one of the same revision agree); None when the file is unreadable. `unimatrix doctor` compares it across boxes."""
    try:
        return hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:12]
    except OSError:
        return None


def roster(mirrors=False):
    """Print one JSON row per exportable local session. `mirrors` (read-only diagnosis) also lists the
    mirror rows, unmodified, that the export skips."""
    fields = {**engine_fields(), "relay_sha": relay_sha()}
    helpers = load_roster()
    codex_cache = {}
    rows = []
    for pid, d, key in entries():
        reply_inbox = d.get("unimatrixMirror") is True and d.get("unimatrixReplyInbox") is True
        if mirrors and d.get("unimatrixMirror") and not reply_inbox:
            print(json.dumps({"entry": d, "key_name": key, **fields}))  # no key body: diagnosis only
            continue
        if d.get("macSocketPath") or (d.get("unimatrixMirror") and not reply_inbox):
            continue  # never re-export a far session we are only mirroring, whichever OS made the entry
        if codex_export_refused(d, codex_cache):
            continue
        with open(os.path.join(os.path.expanduser(SESS), key), encoding="utf-8") as fh:
            body = fh.read()
        exported = {**d, **helpers.session_identity(d)}
        if reply_inbox:
            # Advertise the hosted endpoint, not a remotely supplied mirror. Leaving
            # mirror markers would suppress its downstream mirror on the next poll.
            for field in ("unimatrixMirror", "unimatrixRemoteSocket", "unimatrixClient"):
                exported.pop(field, None)
            exported.update(vendor="transport", box=local_box())
        rows.append((pid, exported, {"entry": exported, "key_name": key, "key": body, **fields}))
    holders = {}
    for pid, exported, _ in rows:
        if exported.get("messagingSocketPath") is not None:
            holders.setdefault(exported["messagingSocketPath"], []).append(pid)
    for sock_path, pids in holders.items():
        if len(pids) > 1:
            print(f"ambiguous socket {sock_path}: pids {','.join(map(str, pids))}", file=sys.stderr)
    for _, exported, line in rows:
        if len(holders.get(exported.get("messagingSocketPath"), ())) <= 1:
            print(json.dumps(line))


MIRROR_NAME_FIELD = "unimatrixMirrorName"  # the unlabelled name a pushed mirror was registered under
_BOX_FIELDS = ("unimatrixClient", "unimatrixRemote", "unimatrixBox", "box")


def _row_names_a_box(d):
    return any(d.get(f) for f in _BOX_FIELDS)


def _row_is_from(d, client):
    """Does this roster row's far box identify the ssh client the frame came from?

    A pure string compare of the client address: the row's recorded client, else the IP the roster
    mirror recorded for the far box (`unimatrixRemoteIp`), else a remote that is itself that address.
    No name resolution happens here.
    """
    if d.get("unimatrixClient"):
        return d["unimatrixClient"] == client
    remote = str(d.get("unimatrixRemote") or "")
    return client in (d.get("unimatrixRemoteIp"), remote.rpartition("@")[2])


def local_reply_address(line):
    """Swap a far sender's `from` for the local mirror socket that reaches it.

    Relay-inbox mirrors match by unimatrixRemoteSocket; with none, a roster mirror matches by
    macSocketPath and the sending box (the client address against the row's box fields). Anything
    but exactly one candidate leaves the frame unchanged.

    A notify_when_idle frame names its sender's reply address in `from`; the receiver drops
    any address outside its own namespace. A message frame also repeats it as a `from="..."`
    attribute in its content, which is the address the receiving agent replies to.
    """
    try:
        frame = json.loads(line)
    except ValueError:
        return line
    if not isinstance(frame, dict) or not isinstance(frame.get("from"), str):
        return line
    addr = frame["from"]
    scheme = "uds:" if addr.startswith("uds:") else ""
    candidates = [d for _, d, _ in entries()
                  if d.get("unimatrixMirror") and d.get("unimatrixRemoteSocket") == addr[len(scheme):]]
    client = client_address()
    if client:
        qualified = [d for d in candidates if d.get("unimatrixClient") == client]
        candidates = qualified or [d for d in candidates if not d.get("unimatrixClient")]
    if not candidates:
        # A roster mirror holds the far socket in macSocketPath; its messagingSocketPath is key-vouched locally.
        # Another far box can hold the same socket path: a row naming its box (unimatrixRemote / unimatrixBox,
        # as roster mirrors carry) or client address matches only the sending client; a row naming none is the
        # legacy fallback.
        by_socket = [d for _, d, _ in entries()
                     if d.get("macSocketPath") == addr[len(scheme):] and d.get("messagingSocketPath")]
        candidates = [d for d in by_socket if client and _row_is_from(d, client)] \
            or [d for d in by_socket if not _row_names_a_box(d)]
    if not candidates and client:
        # The sender has no mirror here (its socket is another box's local pipe): hand the receiver
        # the sending box's reply-inbox endpoint, the one address that routes back to that box.
        candidates = [d for _, d, _ in entries()
                      if d.get("unimatrixReplyInbox") is True and d.get("unimatrixMirror")
                      and d.get("messagingSocketPath") and d.get("unimatrixClient") == client]
    if len(candidates) == 1:
        d = candidates[0]
        frame["from"] = scheme + d["messagingSocketPath"]
        msg = frame.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            msg["content"] = msg["content"].replace(
                f'from="{addr}"', f'from="{frame["from"]}"', 1)
        return json.dumps(frame).encode() + b"\n"

    return line


def load_roster():
    """The sibling registry/auth helpers, imported only for local delivery."""
    import importlib.util
    path = Path(__file__).resolve().parent / "unimatrix-roster.py"
    spec = importlib.util.spec_from_file_location("unimatrix_roster", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _exported_name(d):
    """The name a sender addresses `d` by; a pushed mirror keeps its registered (unlabelled) name."""
    return d.get(MIRROR_NAME_FIELD) or {**d, **load_roster().session_identity(d)}.get("name")


def shown_ref(name):
    """The `<bare>.<own box label>` address a far box shows for local session `name`; None for a non-name."""
    label = _own_box()
    return f"{name.partition('.')[0]}.{label}" if isinstance(name, str) and name and label else None


def _name_matches(name, digest):
    """True when `digest` is the name digest of `name` or of its shown `<bare>.<own box label>` address."""
    if not isinstance(name, str):
        return name_digest("") == digest
    return digest in (name_digest(name), name_digest(shown_ref(name) or name))


def _router_resolve(name):
    """The peer router's `resolve` answer for the session `name`; None when no router answers on this box."""
    try:
        router = _load_sibling("unimatrix-peer-router.py", "unimatrix_relay_peer_router")
        ctl = router.endpoint_path(router.ROUTER_ENDPOINT_SEED)
        answer = router.request_line(ctl, {"op": "resolve", "name": name}, 2)
    except Exception:  # no router, an older router without the op, or an unreadable answer: local checks stand
        return None
    if not isinstance(answer, dict) or "ok" not in answer or answer.get("error") == "unknown op":
        return None
    return answer


def _session_path(pid, expected_digest=None, expected_name_digest=None, expected_session_id=None):
    """The live session's messaging endpoint for `pid`; exits when it is absent or not a session endpoint.

    With `expected_digest`, the endpoint must hash to it: a pid that now holds another session
    exits `target mismatch` before any message is read. With `expected_session_id`, the entry's
    sessionId must equal it (an absent sessionId is a mismatch). With `expected_name_digest`, the exported
    name must hash to it (else `target mismatch`) and no other live non-mirror session may
    export that name (else `ambiguous`).
    """
    def refuse(message):
        record_delivery({"ok": False, "pid": pid, "session": expected_session_id, "error": message})
        sys.exit(message)

    held = [d for p, d, _ in entries() if p == pid]
    if len(held) > 1:  # an inbox-mux process owns many names under one pid: the addressed identity picks the entry
        if expected_session_id is not None:  # the session is the identity; a name or socket may be shared or stale
            by_session = [d for d in held if d.get("sessionId") == expected_session_id]
            if not by_session:
                found = ",".join(str(d.get("sessionId")) for d in held)
                refuse(f"{TARGET_MISMATCH}: pid {pid} holds sessions {found}, not addressed session {expected_session_id}")
            held = by_session
    if len(held) > 1:
        if expected_digest is not None:
            held = [d for d in held if socket_digest(str(d.get("messagingSocketPath"))) == expected_digest]
        if expected_name_digest is not None:
            held = [d for d in held if _name_matches(_exported_name(d), expected_name_digest)]
        if len(held) != 1:
            refuse(f"{TARGET_MISMATCH}: pid {pid} holds several sessions, none uniquely the addressed one")
    target = held[0] if held else None
    if not target:
        refuse(f"no live session with pid {pid}")
    path = target["messagingSocketPath"]
    if expected_digest is not None and socket_digest(path) != expected_digest:
        refuse(f"{TARGET_MISMATCH}: pid {pid} holds {target.get('name')}")
    if expected_session_id is not None and target.get("sessionId") != expected_session_id:
        found = target.get("sessionId")
        refuse(f"{TARGET_MISMATCH}: pid {pid} holds session {found} ({target.get('name')}), "
               f"not addressed session {expected_session_id}")
    if expected_name_digest is not None:
        name = _exported_name(target)
        if not _name_matches(name, expected_name_digest):
            refuse(f"{TARGET_MISMATCH}: pid {pid} holds {name}, not the addressed session")
        same = []
        for p, d, _ in entries():
            n = _exported_name(d)
            if (not (d.get("macSocketPath") or d.get("unimatrixMirror"))
                    and _name_matches(n, expected_name_digest)):
                same.append(p)
        if len(same) > 1:
            refuse(f"ambiguous: {len(same)} live sessions named {name} (pids {','.join(map(str, same))})")
    if expected_name_digest is not None:
        answer = _router_resolve(name) if isinstance(name, str) else None
        if answer is not None and not answer.get("ok"):
            refuse(f"router refused target {name}: {answer.get('error')}")
        if answer is not None and answer.get("endpoint") != path:
            refuse(f"{TARGET_MISMATCH}: router resolves {name} to another endpoint")
    if endpoint_kind() == "pipe":
        if not path.lower().startswith(PIPE_PREFIX.lower()):
            refuse(f"refusing non-session pipe {path}")
    elif os.path.dirname(path) != SOCKS or not stat.S_ISSOCK(os.stat(path).st_mode):
        refuse(f"refusing non-session socket {path}")
    name = _exported_name(target)
    _REACHED.update(pid=pid, name=name if isinstance(name, str) else None, session=target.get("sessionId"))
    return path


#: The session the last `_session_path` resolved (pid, exported name, sessionId); send-* replies name it.
_REACHED = {}


def deliveries_path():
    return settings_home() / "unimatrix" / "deliveries.jsonl"


def record_delivery(row, now=None):
    """Append one inbound outcome (delivered or refused; never message text) to deliveries.jsonl.

    Best effort: an unwritable record never fails or reorders a delivery."""
    import time
    stamp = time.time() if now is None else now
    entry = {"side": "relay-in", "at": stamp, **row}
    entry.setdefault("box", _own_box())
    try:
        path = deliveries_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)
        try:
            os.write(fd, (json.dumps(entry) + "\n").encode("utf-8"))
            size = os.fstat(fd).st_size
        finally:
            os.close(fd)
        if size > 256 * 1024:
            _trim_receipts(path)
    except OSError:
        pass


PIPE_FLUSH_DEADLINE_S = 0.3


def _flush_bounded(flush, deadline=None):
    """Run `flush` (FlushFileBuffers blocks until the pipe reader drains it, forever on a
    reader that never reads) on a worker thread; raise TimeoutError past the deadline.

    On expiry the blocked synchronous I/O is cancelled (Windows CancelSynchronousIo) so the
    worker does not outlive the handle the caller closes next."""
    import threading
    box = {}

    def work():
        try:
            flush()
        except BaseException as e:  # re-raised on the caller's thread
            box["err"] = e

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(PIPE_FLUSH_DEADLINE_S if deadline is None else deadline)
    if t.is_alive():
        _cancel_thread_io(t)
        t.join(0.05)
        raise TimeoutError("pipe flush: no live reader drained the write")
    if "err" in box:
        raise box["err"]


def _cancel_thread_io(thread):
    if os.name != "nt":
        return
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.OpenThread.restype = ctypes.c_void_p
    h = k32.OpenThread(0x0001, False, thread.native_id)  # THREAD_TERMINATE, required by CancelSynchronousIo
    if h:
        k32.CancelSynchronousIo(ctypes.c_void_p(h))
        k32.CloseHandle(ctypes.c_void_p(h))


class TargetMismatch(Exception):
    """The process serving an endpoint is not the pid the registry entry addressed."""


def _pipe_server_pid(handle):
    """The pid serving the pipe behind client `handle`; None when the OS cannot say."""
    try:
        import ctypes
        pid = ctypes.c_ulong(0)
        if ctypes.windll.kernel32.GetNamedPipeServerProcessId(ctypes.c_void_p(int(handle)), ctypes.byref(pid)):
            return pid.value
    except Exception:  # no ctypes.windll, or a handle that is not an OS handle
        pass
    return None


def _socket_peer_pid(sock):
    """The pid of the process on the far end of connected unix socket `sock`; None when the OS cannot say."""
    import struct
    try:
        if sys.platform == "darwin":
            return sock.getsockopt(0, 2)  # SOL_LOCAL, LOCAL_PEERPID
        return struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))[0]
    except (OSError, AttributeError, struct.error):
        return None


def _confirm_server(server_pid):
    """Refuse before any byte is written when the endpoint's server is not the pid `_session_path` resolved.

    The registry entry names a pid; a recycled pipe name or reused socket path can be bound by another
    process. An unanswerable OS query (None) confirms nothing and refuses nothing."""
    expected = _REACHED.get("pid")
    if expected is not None and server_pid is not None and server_pid != expected:
        served = next((d.get("sessionId") for p, d, _ in entries() if p == server_pid), None)
        addressed = _REACHED.get("session")
        raise TargetMismatch(
            f"{TARGET_MISMATCH}: endpoint is served by pid {server_pid}"
            + (f" (session {served})" if served else "") + f", not addressed pid {expected}"
            + (f" (session {addressed})" if addressed else ""))


def _write_line(path, line):
    """Deliver one message line to the session endpoint `path` (pipe on Windows, unix socket elsewhere)."""
    line = local_reply_address(line)
    if endpoint_kind() == "pipe":
        import win32file
        line = load_roster().authenticated_data(path, line, os.path.expanduser(SESS))
        h = win32file.CreateFile(path, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                                 0, None, win32file.OPEN_EXISTING, 0, None)
        try:
            _confirm_server(_pipe_server_pid(h))
            win32file.WriteFile(h, line)
            _flush_bounded(lambda: win32file.FlushFileBuffers(h))
        finally:
            win32file.CloseHandle(h)
        return
    s = socket.socket(socket.AF_UNIX)
    try:
        s.connect(path)
        _confirm_server(_socket_peer_pid(s))
        s.sendall(line)
    finally:
        s.close()


def _own_box():
    """This box's id for receipt rows and replies; None when it cannot be derived."""
    try:
        return local_box()
    except Exception:  # a row without a box is better than a delivery without a row
        return None


def send(pid):
    path = _session_path(pid)
    _write_line(path, sys.stdin.buffer.readline())


def send_batch(pid, expected_digest=None, expected_name_digest=None, expected_session_id=None):
    """Deliver every stdin line to `pid`, replying one JSON result line per message line.

    A per-line fault (a blank line included, so replies stay index-aligned with the input) is
    that line's error reply and the loop continues; only a target-level refusal exits, before
    any line is read.
    """
    _REACHED.clear()
    path = _session_path(pid, expected_digest, expected_name_digest, expected_session_id)
    reached = dict(_REACHED)
    for line in sys.stdin.buffer:
        try:
            if not line.strip():
                raise ValueError("empty message line")
            _write_line(path, line)
            reply = {"ok": True}
            if expected_session_id:
                if reached:
                    reply.update(reached=reached["name"], reached_session=reached["session"], reached_pid=pid,
                                 reached_box=_own_box(), reached_ref=shown_ref(reached["name"]))
                reply["digest"] = record_receipt(expected_session_id, line)
        except TargetMismatch as e:
            reply = {"ok": False, "error": str(e)}
        except Exception as e:  # pywintypes.error is not an OSError subclass
            reply = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        record_delivery({**reply, "pid": pid, "session": reached.get("session") or expected_session_id,
                         "name": reached.get("name"), "ref": shown_ref(reached.get("name"))})
        print(json.dumps(reply), flush=True)


RECEIPT_KEEP = 500
RECEIPT_SINCE_RE = re.compile(r"\d{1,12}(?:\.\d{1,6})?")


def receipts_path():
    return settings_home() / "unimatrix" / "receipts.jsonl"


def record_receipt(session_id, line, now=None):
    """Append one receipt (session id, sha256 of the line sans newline; never the text) and return the digest.

    The row is one O_APPEND write, so racing relays lose no row except across a trim (a row appended
    between the trim's read and its replace is dropped); the file is trimmed to
    RECEIPT_KEEP only once it passes 2*RECEIPT_KEEP rows. Any failure raises: the caller
    must not reply ok for a line it could not receipt."""
    import time
    stamp = time.time() if now is None else now
    digest = hashlib.sha256(line.rstrip(b"\n")).hexdigest()
    row = {"session": session_id, "digest": digest, "at": stamp, "box": _own_box(), "ref": shown_ref(_REACHED.get("name")),
           "ts": datetime.fromtimestamp(stamp, timezone.utc).astimezone().isoformat(timespec="seconds")}
    data = (json.dumps(row) + "\n").encode("utf-8")
    path = receipts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = _open_append(path)
    try:
        os.write(fd, data)
        size = os.fstat(fd).st_size
    finally:
        os.close(fd)
    if size > 2 * RECEIPT_KEEP * len(data):
        _trim_receipts(path)
    return digest


def _open_append(path):
    """fd whose every write lands at end-of-file atomically.

    The Windows CRT emulates O_APPEND as seek-then-write, which racing writers interleave and
    lose rows to; a handle opened with FILE_APPEND_DATA only makes the kernel do the append."""
    if os.name != "nt":
        return os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    import msvcrt
    import win32file
    handle = win32file.CreateFile(
        str(path), 0x0004,  # FILE_APPEND_DATA
        win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE | win32file.FILE_SHARE_DELETE,
        None, win32file.OPEN_ALWAYS, win32file.FILE_ATTRIBUTE_NORMAL, None)
    return msvcrt.open_osfhandle(handle.Detach(), os.O_APPEND | os.O_BINARY)


def _trim_receipts(path):
    """Rewrite `path` to its last RECEIPT_KEEP rows; a Windows replace racing a reader's open
    raises PermissionError, retried within a ~30ms total bound, then raised."""
    import time
    rows = path.read_text(encoding="utf-8").splitlines()
    if len(rows) <= 2 * RECEIPT_KEEP:
        return
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp.write_text("\n".join(rows[-RECEIPT_KEEP:]) + "\n", encoding="utf-8")
    for attempt in range(4):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 3:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.01)


def receipts(session_id, since):
    """`receipts <session-id> <since>`: this box's receipt rows for the session at or after epoch `since`."""
    try:
        lines = receipts_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    rows = []
    for raw in lines:
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("session") == session_id and (row.get("at") or 0) >= since:
            rows.append(row)
    return {"ok": True, "rows": rows}


def pid_domain():
    return "darwin" if sys.platform == "darwin" else "linux"


def proc_start(pid):
    """Process-start stamp of `pid` read without a spawn; None when it cannot be read."""
    try:
        return _liveness().proc_start(pid)
    except OSError:
        return None


def stale_holder(pid, d):
    """Is this mirror entry a corpse: its pid is live only because the OS recycled it?

    A hard reset leaves mirror entries behind; a recycled pid passes `alive` and would
    hold the name forever. A mirror records the start stamp it was born with, so a
    different stamp on that pid means another process. No recorded stamp, or ps unable
    to answer, is never proof of staleness.
    """
    recorded = d.get("procStart")
    if not isinstance(recorded, str) or not recorded:
        return False
    actual = proc_start(pid)
    return actual is not None and actual != recorded


def client_address():
    """Source address of the ssh client driving this relay ('' when not under sshd)."""
    parts = os.environ.get("SSH_CONNECTION", "").split()
    return parts[0] if parts else ""


def superseded_holder(d, client):
    """Is this live mirror relay held open by a dead connection of the same near box?

    A near box that hard-resets leaves its old `inbox` relay alive on a half-open ssh; the
    restarted client (one per name per near box) asks for the same name from the same
    address, so the old relay can only be that client's own ghost. No recorded or current
    address, or a different one, never proves it.
    """
    recorded = d.get("unimatrixClient")
    return bool(client) and isinstance(recorded, str) and recorded == client


def check_name_free(name, client="", own_pid=None):
    """Exit unless `name` is neither a live local session nor held by a live mirror relay.

    Returns (pid, key file, kill) for each mirror holder of `name` that does not count as a
    holder: a recycled-pid corpse (kill False) or a live relay superseded by `client`'s own
    reconnect (kill True). `own_pid` (the inbox-mux process) never counts as another holder.
    """
    live = list(entries())
    if any(d.get("name") == name and not d.get("unimatrixMirror") for _, d, _ in live):
        sys.exit(f"name {name} belongs to a live local session")
    # A second live mirror would duplicate the name, and its bind would orphan the older
    # relay on an unlinked socket; the caller stops the old one first.
    mirrors = [(p, d, k) for p, d, k in live
               if (d.get(MIRROR_NAME_FIELD) or d.get("name")) == name and d.get("unimatrixMirror") and p != own_pid]
    freed = [(p, k, False) for p, d, k in mirrors if stale_holder(p, d)]
    freed += [(p, k, True) for p, d, k in mirrors
              if p not in {f[0] for f in freed} and superseded_holder(d, client)]
    held = [p for p, _, _ in mirrors if p not in {f[0] for f in freed}]
    if held:
        sys.exit(f"name {name} already mirrored by live relay pid {held[0]}")
    return freed


def drop_stale(freed):
    """Stop each superseded relay, then remove the registry entry and key of every freed holder."""
    base = os.path.expanduser(SESS)
    for pid, key, kill in freed:
        if kill:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        mux_entries = [f for f in os.listdir(base) if re.fullmatch(rf"{pid}\.[0-9a-f]{{16}}\.json", f)]
        for f in (f"{pid}.json", key, *mux_entries):
            try:
                os.unlink(os.path.join(base, f))
            except OSError:
                pass


def superseded_transports(name, client, own_pid):
    """Live reply-inbox transports of the same near box under another name: (pid, entry, key file).

    One box has one reply endpoint, so a transport under a newer name supersedes the rest."""
    if not client:
        return []
    return [(p, d, k) for p, d, k in entries()
            if d.get("unimatrixMirror") is True and d.get("unimatrixReplyInbox") is True and p != own_pid
            and d.get("unimatrixClient") == client and (d.get(MIRROR_NAME_FIELD) or d.get("name")) != name]


def reap_transports(stale):
    """SIGTERM each superseded transport, then unlink its registry files and only the socket inode it bound."""
    base = os.path.expanduser(SESS)
    for pid, d, key in stale:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        sock = d.get("messagingSocketPath")
        others = [os.path.join(base, f"{pid}.json"), os.path.join(base, key)]
        if isinstance(sock, str) and isinstance(d.get("unimatrixSocketIno"), int):
            release(sock, d["unimatrixSocketIno"], others)
        else:
            release("", None, others)


def release_on_sigterm():
    """Turn SIGTERM into a normal exit so the serving loop's `finally` releases the bound socket."""
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    except ValueError:
        pass  # not the main thread


def client_box(client):
    """(box id, label) of the far box the authenticated ssh `client` address belongs to, or (None, None).

    Read from this box's own roster rows that name `client` as their far box; never from the pushed
    payload, which any client can write. With no such row the label is the sanitized client address
    (box unknown), so a push never registers under a bare name another box's session could share."""
    if not client:
        return None, None
    for _, d, _ in entries():
        if d.get("unimatrixMirror") or not _row_is_from(d, client):
            continue
        box = d.get("unimatrixBox") or None
        label = re.sub(r"[^A-Za-z0-9_-]+", "-", str(d.get("unimatrixRemote") or box or "").rpartition("@")[2]).strip("-")
        if label:
            return box, label
    return None, re.sub(r"[^A-Za-z0-9_-]+", "-", client).strip("-") or None


def mirror_entry(raw, name, box=None, label=None):
    """Registry entry for a mirror: allowlisted remote fields plus the far socket for the `from` swap.

    With a sender `label` the row is named `<bare>.<label>` (the roster pull's labelled() form, so a
    re-mirror never stacks labels), keeps the registered name in MIRROR_NAME_FIELD and carries `box`."""
    entry = {k: v for k, v in raw.items() if k in MIRROR_FIELDS}
    entry["name"] = name
    if label:
        entry["name"] = f"{name.partition('.')[0]}.{label}"
        entry[MIRROR_NAME_FIELD] = name
        if box:
            entry["unimatrixBox"] = box
    if isinstance(raw.get("messagingSocketPath"), str):
        entry["unimatrixRemoteSocket"] = raw["messagingSocketPath"]
    return entry


def key_file_name(pid, socket_path):
    """Claude Code finds a peer's key by sha256 of that peer's own socket path."""
    return f"{pid}.{hashlib.sha256(socket_path.encode()).hexdigest()}.key"


def release(sock_path, our_ino, others):
    """Unlink `others`, and the socket only when it is still the inode this relay bound."""
    try:
        mine = os.stat(sock_path).st_ino == our_ino
    except OSError:
        mine = False
    for p in ([sock_path] if mine else []) + list(others):
        try:
            os.unlink(p)
        except OSError:
            pass


def serve(srv, stdin_fd, out):
    """Forward each message delivered to `srv` to `out`; return when stdin hits EOF."""
    while True:
        ready, _, _ = select.select([srv, stdin_fd], [], [])
        if stdin_fd in ready:
            if not os.read(stdin_fd, 4096):
                return
            continue
        forward_one(srv, lambda buf: (out.write(buf), out.flush()))


def forward_one(srv, emit):
    """Accept one connection on `srv`, drain it, and pass the newline-terminated payload to `emit`."""
    c, _ = srv.accept()
    buf = b""
    while chunk := c.recv(65536):
        buf += chunk
    c.close()
    if buf.strip():
        emit(buf.rstrip(b"\n") + b"\n")


UNSUPPORTED_HOST_RC = 3  # unimatrix-inbox.py and unimatrix-mirror-all.py match this exit code


def check_inbox_host(mode):
    """Exit UNSUPPORTED_HOST_RC where mirror sessions cannot be hosted (pipe endpoints)."""
    if endpoint_kind() == "pipe":
        print(f"{mode}: mirror sessions are hosted on macOS/Linux boxes only", file=sys.stderr)
        sys.exit(UNSUPPORTED_HOST_RC)


class Mirror:
    """One registered inbox name: its bound socket and the registry files it owns."""

    def __init__(self, srv, path, our_ino, entry_path, key_path):
        self.srv, self.path, self.our_ino = srv, path, our_ino
        self.entry_path, self.key_path = entry_path, key_path

    def release(self):
        release(self.path, self.our_ino, [self.entry_path, self.key_path])

    def retire(self):
        """Release, and close the listening socket: a mux process outlives each name it hosts."""
        self.release()
        self.srv.close()


def register_name(name, raw, key_body, export_reply=False, mux=False):
    """Register mirror `name`: free-check, stale-marker clear, socket, registry entry and peer key.

    Both `inbox` (one name per process) and `inbox-mux` (many) run exactly this. `mux` names the
    entry `{pid}.{name digest}.json` so several entries can share the process pid.
    """
    if not isinstance(raw, dict):
        sys.exit("inbox: refused: entry is not a JSON object")
    if raw.get("name") not in (None, name):
        sys.exit(f"inbox: refused: entry names {raw.get('name')!r} not {name!r}")
    pid = os.getpid()
    client = client_address()
    drop_stale(check_name_free(name, client, own_pid=pid) if mux else check_name_free(name, client))
    if export_reply and not mux:
        reap_transports(superseded_transports(name, client, pid))
    try:
        os.unlink(stale_marker_path(name))
    except OSError:
        pass
    entry = mirror_entry(raw, name, *client_box(client))
    os.makedirs(SOCKS, mode=0o700, exist_ok=True)
    path = f"{SOCKS}/unimatrix-{name}.sock"
    if os.path.exists(path):
        os.unlink(path)
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(path)
    os.chmod(path, 0o600)  # bind honours umask; other local users must not reach the far session
    entry_path = key_path = None
    try:
        our_ino = os.stat(path).st_ino
        srv.listen(8)
        # Raw ps output: the harness compares it byte for byte, padded one-digit day included.
        ps = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                            capture_output=True, text=True, check=True).stdout.strip()
        entry.update(pid=pid, procStart=ps, pidDomain=pid_domain(),
                     messagingSocketPath=path, unimatrixMirror=True, unimatrixClient=client,
                     unimatrixSocketIno=our_ino)
        if export_reply:
            # This field is intentionally absent from MIRROR_FIELDS: only explicit mode
            # selection can opt in, never an untrusted registration payload.
            entry["unimatrixReplyInbox"] = True
        base = os.path.expanduser(SESS)
        entry_path = os.path.join(base, f"{pid}.{name_digest(name)}.json" if mux else f"{pid}.json")
        key_path = os.path.join(base, key_file_name(pid, path))
        with open(entry_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(entry, fh)
        helpers = load_roster()
        helpers.write_peer_key(key_path, helpers.local_peer_key(
            key_body, entry["procStart"], entry["pidDomain"]))
    except BaseException:
        srv.close()
        for leaked in (path, entry_path, key_path):
            try:
                if leaked:
                    os.unlink(leaked)
            except OSError:
                pass
        raise
    return Mirror(srv, path, our_ino, entry_path, key_path)


def inbox(name, export_reply=False):
    if not valid_inbox_name(name):
        sys.exit("inbox: name must use 1-64 ASCII letters, digits, '_', '-', or interior single dots")
    check_inbox_host("inbox")
    release_on_sigterm()
    raw = json.loads(sys.stdin.readline())
    key_body = sys.stdin.readline().rstrip("\n")
    m = register_name(name, raw, key_body, export_reply=export_reply)
    try:
        serve(m.srv, sys.stdin.fileno(), sys.stdout.buffer)
    finally:
        m.release()


def _emit_frame(out, name, frame=None, error=None):
    obj = {"name": name, "frame": frame} if error is None else {"name": name, "error": error}
    out.write(json.dumps(obj).encode() + b"\n")
    out.flush()


def _mux_apply(frame, mirrors, out):
    """Apply one add/drop/data frame from the near client to the `mirrors` table."""
    if not isinstance(frame, dict):
        return
    op, name = frame.get("op"), frame.get("name")
    if op not in ("add", "drop", "data") or not valid_inbox_name(name):
        return
    if op == "data":
        return  # the near side has nothing to deliver to a mirror; inbox ignores stdin the same way
    if name in mirrors:
        mirrors.pop(name).retire()
    if op == "drop":
        return
    try:
        mirrors[name] = register_name(name, frame.get("entry"), str(frame.get("key") or ""), mux=True)
    except SystemExit as e:
        _emit_frame(out, name, error=str(e.code))
    except Exception as e:  # one name's bind/ps/write failure must not end the process hosting every name
        _emit_frame(out, name, error=f"{type(e).__name__}: {e}")


def _wrap_line(name, out):
    def emit(buf):
        for line in buf.splitlines():
            try:
                frame = json.loads(line)
            except ValueError:
                frame = line.decode("utf-8", "replace")
            _emit_frame(out, name, frame=frame)
    return emit


def serve_mux(stdin_fd, out):
    """Serve every registered name's socket and the add/drop frame stream; return at stdin EOF.

    Single-threaded: a sender that holds a connection open stalls every name and the frame stream."""
    mirrors, pending = {}, b""
    try:
        while True:
            socks = {m.srv: n for n, m in mirrors.items()}
            ready, _, _ = select.select([*socks, stdin_fd], [], [])
            if stdin_fd in ready:
                chunk = os.read(stdin_fd, 65536)
                if not chunk:
                    return
                pending += chunk
                *lines, pending = pending.split(b"\n")
                for line in lines:
                    try:
                        _mux_apply(json.loads(line), mirrors, out)
                    except ValueError:
                        continue
                continue
            for srv in ready:
                if srv in socks:
                    forward_one(srv, _wrap_line(socks[srv], out))
    finally:
        for m in mirrors.values():
            m.retire()


def inbox_mux():
    check_inbox_host("inbox-mux")
    release_on_sigterm()
    serve_mux(sys.stdin.fileno(), sys.stdout.buffer)


def receive_grant():
    """The engine's arrival check for a relayed grant; the engine is resolved lazily."""
    try:
        from coordinator_core.group_em import suite_grant
    except ImportError:
        return _receive_via_door
    return suite_grant.receive_relayed_grant


def freshness(run=None, box_id=None):
    """The `freshness` mode's reply: this box's klabauter clone freshness from the engine, resolved lazily.

    Runs ``run_freshness(do_fetch=True)``, whose ``apply_freshness`` may advance the clone: the verb
    widens the relay key past message delivery, like ``grant``/``revoke``/``keypin``, which also
    mutate far state. Never raises; ``{"ok": False, "reason"}`` when the engine cannot run.
    """
    try:
        if run is None:
            from coordinator_core.ops.fleet.klabauter_freshness import run_freshness as run
        if box_id is None:
            from coordinator_core.group_em.box_registry import local_box_id
            box_id = local_box_id()
    except ImportError:
        return {"ok": False, "reason": "engine_unavailable"}
    try:
        return {"ok": True, "box_id": box_id, "result": run(do_fetch=True)}
    except Exception as exc:
        return {"ok": False, "reason": f"freshness_failed:{type(exc).__name__}"}


def receive_revoke():
    """The engine's arrival check for a relayed revoke; the engine is resolved lazily."""
    try:
        from coordinator_core.group_em import relayed_grant_peer
    except ImportError:
        return lambda env: _receive_via_door(env, "groupem.suite_grant_revoke_receive")
    return lambda env: relayed_grant_peer.receive_relayed_revoke(env)


def receive_keypin():
    """The engine's first-contact pin check, ``(box_id, key_b64, peer)``; resolved lazily."""
    try:
        from coordinator_core.group_em import relayed_grant_peer
    except ImportError:
        return lambda box_id, key_b64, peer: _receive_via_door(
            {"box_id": box_id, "key_b64": key_b64, "peer": peer}, "groupem.box_key_pin_from_peer", wrap=False)
    return relayed_grant_peer.receive_key_pin


def _receive_via_door(env, op="groupem.suite_grant_receive", wrap=True):
    """Arrival check through the settings-home door; never raises.

    The forced command can run under a system python with no engine and no lib/ beside this copy.
    """
    try:
        home = Path(os.environ.get("COORDINATOR_SETTINGS_HOME") or Path.home() / ".coordinator-claude-settings")
        exe = home / "bin" / ("coordinator-invoke.exe" if os.name == "nt" else "coordinator-invoke")
        proc = subprocess.run([str(exe), op, json.dumps({"envelope": env} if wrap else env)],
                              capture_output=True, text=True, timeout=30)
    except Exception as exc:
        return {"ok": False, "reason": f"door_unavailable:{type(exc).__name__}"}
    try:
        data = json.loads(proc.stdout or "")
    except Exception:
        return {"ok": False, "reason": "door_bad_reply"}
    result = data.get("result") if isinstance(data, dict) else None
    return result if isinstance(result, dict) else {"ok": False, "reason": "door_bad_reply"}


def peer_arg(argv):
    """The box named by a leading `--peer <box>` argv pair of the forced command, or None."""
    return argv[1] if len(argv) >= 2 and argv[0] == "--peer" and valid_inbox_name(argv[1]) else None


def _read_envelope(line):
    try:
        env = json.loads(line)
    except ValueError:
        return None
    return env if isinstance(env, dict) else None


def revoke(args, line, receive=None, peer=None):
    """Hand the signed revoke envelope on `line` to the arrival check; return its reply dict.

    Refused before the engine sees it when the argv grantee or, with a pinned `peer`, the issuer
    box disagrees with the envelope."""
    env = _read_envelope(line)
    if env is None:
        return {"ok": False, "reason": "bad_envelope"}
    if peer is not None and env.get("issuer_box_id") != peer:
        return {"ok": False, "reason": "issuer_not_peer"}
    sid = str(env.get("grantee_session_id", ""))
    if args["grantee"] not in (sid, f'{env.get("grantee_box_id")}:{sid}'):
        return {"ok": False, "reason": "argv_mismatch:grantee"}
    return (receive or receive_revoke())(env)


def keypin(args, line, peer=None, receive=None):
    """Pin the key on `line` (``{"box_id", "key_b64"}``) for the forced command's `peer`.

    Fails closed: no `peer` is `no_peer`; a claimed box other than the peer is `issuer_not_peer`."""
    if peer is None:
        return {"ok": False, "reason": "no_peer"}
    body = _read_envelope(line)
    if body is None:
        return {"ok": False, "reason": "bad_envelope"}
    if body.get("box_id") != peer:
        return {"ok": False, "reason": "issuer_not_peer"}
    if args["box_id"] != peer:
        return {"ok": False, "reason": "argv_mismatch:box_id"}
    return (receive or receive_keypin())(peer, body.get("key_b64"), peer)


def grant(args, line, receive=None, peer=None):
    """Hand the signed envelope on `line` to the arrival check; return its reply dict.

    The argv fields only restate the envelope: any disagreement is refused before the
    engine sees it, so argv can never widen what the issuer signed. With a pinned `peer`
    the envelope's issuer box must be that peer.
    """
    try:
        env = json.loads(line)
    except ValueError:
        env = None
    if not isinstance(env, dict):
        return {"ok": False, "reason": "bad_envelope"}
    if peer is not None and env.get("issuer_box_id") != peer:
        return {"ok": False, "reason": "issuer_not_peer"}
    sid = str(env.get("grantee_session_id", ""))
    if args["grantee"] not in (sid, f'{env.get("grantee_box_id")}:{sid}'):
        return {"ok": False, "reason": "argv_mismatch:grantee"}
    if str(env.get("note", "")) != args["note"].strip():
        return {"ok": False, "reason": "argv_mismatch:note"}
    if args["repo"] is not None and env.get("scope_root") != args["repo"]:
        return {"ok": False, "reason": "argv_mismatch:repo"}
    try:
        issued = datetime.fromisoformat(str(env["issued_at"]).replace("Z", "+00:00"))
        expires = datetime.fromisoformat(str(env["expires_at"]).replace("Z", "+00:00"))
        if round((expires - issued).total_seconds()) != args["ttl"] * 60:
            return {"ok": False, "reason": "argv_mismatch:ttl"}
    except (KeyError, ValueError, TypeError):
        return {"ok": False, "reason": "bad_ttl"}
    return (receive or receive_grant())(env)


def settings_home():
    return Path(os.environ.get("COORDINATOR_SETTINGS_HOME") or Path.home() / ".coordinator-claude-settings")


MANIFEST = "MANIFEST.sha256"
MAX_DROP_BYTES = 8 << 30  # total member bytes one put may land; larger is refused too_large
MAX_DROP_FILES = 100000  # non-manifest members (files and dirs) one put may land; more is refused too_many_files
_MANIFEST_LINE_RE = re.compile(r"([0-9a-f]{64})  (.+)")


class DropError(Exception):
    """A put/get refusal; `args[0]` is the reason code in the reply."""


def _skipped(name):
    """AppleDouble sidecars, Finder metadata and the resource-fork tree never travel."""
    return name.startswith("._") or name == ".DS_Store" or name == "__MACOSX"


def _safe_rel(rel):
    """True for a relative, forward-slash path with no empty, dot or `..` component and no skipped name."""
    parts = rel.split("/")
    return bool(rel) and not rel.startswith("/") and "\\" not in rel and "\x00" not in rel and all(
        p not in ("", ".", "..") and not _skipped(p) for p in parts)


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_bytes(manifest):
    """The manifest text for {relpath: sha256}: one "<sha256>  <relpath>" line per file, sorted."""
    return "".join(f"{sha}  {rel}\n" for rel, sha in sorted(manifest.items())).encode("utf-8")


def iter_tree(src):
    """Yield ("dir"|"file", relpath, path) for everything pack sends from `src`; pack and the client's
    cap pre-check both walk through this, so they cannot diverge. Regular files and dirs only;
    AppleDouble, symlinks and a file named MANIFEST.sha256 are skipped."""
    src = Path(src)
    if src.is_file():
        yield "file", src.name, src
        return
    for root, dnames, fnames in os.walk(src):
        dnames[:] = sorted(d for d in dnames if not _skipped(d) and not os.path.islink(os.path.join(root, d)))
        rel_root = Path(root).relative_to(src).as_posix()
        for d in dnames:
            yield "dir", d if rel_root == "." else f"{rel_root}/{d}", Path(root, d)
        for f in sorted(fnames):
            path = Path(root, f)
            rel = f if rel_root == "." else f"{rel_root}/{f}"
            if _skipped(f) or rel == MANIFEST or path.is_symlink() or not path.is_file():
                continue
            yield "file", rel, path


def pack(src, out_fp):
    """Write `src` (a file, or a folder's contents) to `out_fp` as one uncompressed tar whose first
    member is MANIFEST.sha256. Regular files and dirs only; AppleDouble/.DS_Store/__MACOSX are
    skipped. Returns the {relpath: sha256} manifest."""
    import io
    import tarfile
    src = Path(src)
    files, dirs = [], []
    for kind, rel, path in iter_tree(src):
        (dirs if kind == "dir" else files).append(rel if kind == "dir" else (rel, path))
    manifest = {rel: _sha256_file(path) for rel, path in files}
    text = manifest_bytes(manifest)
    with tarfile.open(fileobj=out_fp, mode="w|") as tf:
        info = tarfile.TarInfo(MANIFEST)
        info.size = len(text)
        info.mtime = 0
        tf.addfile(info, io.BytesIO(text))
        for rel in dirs:
            tf.add(src / rel, arcname=rel, recursive=False)
        for rel, path in files:
            tf.add(path, arcname=rel, recursive=False)
    return manifest


def _parse_manifest(data):
    manifest = {}
    for line in data.decode("utf-8", "replace").splitlines():
        m = _MANIFEST_LINE_RE.fullmatch(line)
        if not m or not _safe_rel(m.group(2)) or m.group(2) == MANIFEST or m.group(2) in manifest:
            raise DropError("bad_manifest")
        manifest[m.group(2)] = m.group(1)
        if len(manifest) > MAX_DROP_FILES:
            raise DropError("too_many_files")
    return manifest


def _need_filter():
    """Python 3.11.0-3.11.3 has no tarfile.data_filter: refuse rather than extract unfiltered."""
    import tarfile
    if not hasattr(tarfile, "data_filter"):
        raise DropError("tarfile_filter_unavailable")


def unpack(in_fp, dest):
    """Extract the tar on `in_fp` into the new dir `dest` and verify it against its MANIFEST.sha256.

    Refuses (DropError) any member that is not a regular file or dir, an unsafe or AppleDouble name,
    a file absent from the manifest, a manifest line with no member, or a sha mismatch. Returns the
    manifest. The caller owns removing `dest` on failure."""
    import tarfile
    _need_filter()
    dest = Path(dest)
    manifest, seen, total = None, set(), 0
    try:
        tf = tarfile.open(fileobj=in_fp, mode="r|")
    except tarfile.TarError:
        raise DropError("bad_tar") from None
    with tf:
        try:
            for member in tf:
                if manifest is None:
                    if member.name != MANIFEST or not member.isreg() or member.size > 64 << 20:
                        raise DropError("manifest_not_first")
                    raw = tf.extractfile(member).read()
                    manifest = _parse_manifest(raw)
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / MANIFEST).write_bytes(raw)
                    continue
                if not (member.isreg() or member.isdir()):
                    raise DropError("bad_member_type")
                if not _safe_rel(member.name) or member.name in seen:
                    raise DropError("bad_member_name")
                if member.isreg() and member.name not in manifest:
                    raise DropError("extra_file")
                total += member.size if member.isreg() else 0
                if total > MAX_DROP_BYTES:
                    raise DropError("too_large")
                if len(seen) >= MAX_DROP_FILES:
                    raise DropError("too_many_files")
                seen.add(member.name)
                tf.extract(member, dest, filter="data")
        except tarfile.TarError:
            raise DropError("bad_tar") from None
    if manifest is None:
        raise DropError("manifest_not_first")
    if not manifest:
        raise DropError("empty_drop")
    for rel, sha in manifest.items():
        path = dest / rel
        if rel not in seen or path.is_symlink() or not path.is_file():
            raise DropError("missing_file")
        if _sha256_file(path) != sha:
            raise DropError("sha_mismatch")
    return manifest


def _drop_reply(root, manifest):
    return {"ok": True, "files": len(manifest), "bytes": sum(os.path.getsize(root / rel) for rel in manifest),
            "manifest_sha256": hashlib.sha256(manifest_bytes(manifest)).hexdigest()}


def load_membership():
    """The membership library beside this relay, loaded by path; None when it is not vendored here."""
    import importlib.util
    path = Path(__file__).with_name("unimatrix-membership.py")
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("unimatrix_membership", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_KEY_TYPES = r"(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-\S+|sk-\S+)"
_COMMAND_RE = re.compile(r'command="((?:[^"\\]|\\.)*)"')
_KEY_RE = re.compile(rf"\s{_KEY_TYPES}\s+(\S+)")


def managed_key_body(line):
    """Key body of an authorized_keys line whose forced command names this relay; None for any other line."""
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    cmd = _COMMAND_RE.search(text)
    if not cmd or not any(s in cmd.group(1) for s in ("unimatrix-relay.py", "unimatrix-file-relay.py")):
        return None
    key = _KEY_RE.search(text, cmd.end())
    return key.group(1) if key else None


HOMEBREW_PYTHONS = ("/opt/homebrew/bin/python3", "/usr/local/bin/python3")  # literal: the relay must run without lib/ beside it
PIN_KEY = "unimatrix.python"
_PIN_UNREAD = object()
_PIN_CACHE = {}


def _pin_value():
    """The machine-local `unimatrix.python` value when it names a file, else None; one read per settings home."""
    home = str(settings_home())
    if home not in _PIN_CACHE:
        reader = settings_home() / "bin" / "_machine_local.py"
        val = None
        if reader.is_file():
            try:
                from coordinator_core import machine_local_spawn

                raw, ok = machine_local_spawn.get(str(reader), PIN_KEY)
                val = os.path.expanduser(raw.strip()) if ok and raw and raw.strip() else None
            except Exception:  # no engine on this box: the pin reads as unset
                val = None
        _PIN_CACHE[home] = val if val and os.path.isfile(val) else None
    return _PIN_CACHE[home]


def forced_command_interpreter(pin_value=_PIN_UNREAD):
    """The interpreter the forced command runs: the `unimatrix.python` pin, else a Homebrew python3 on
    darwin (sshd's PATH python3 there is the CLT stub), else the console python; `sys.executable` last."""
    if pin_value is _PIN_UNREAD:
        pin_value = _pin_value()
    lib = Path(__file__).resolve().parent / "lib" / "python_interp.py"
    if lib.is_file():
        found = _load_sibling("lib/python_interp.py", "unimatrix_relay_python_interp").unimatrix_python(
            pin_value, homebrew=HOMEBREW_PYTHONS)
    elif pin_value:
        found = pin_value
    elif sys.platform == "darwin":
        found = next((p for p in HOMEBREW_PYTHONS if os.path.isfile(p) and os.access(p, os.X_OK)), None)
    else:
        found = None
    return found or sys.executable


def relay_line(key_body, box, pin_value=_PIN_UNREAD):
    """The restrict line for `key_body` with this copy's interpreter and path, quoted as the installer does.

    `--peer <box>` pins the calling member into the forced command."""
    interp = forced_command_interpreter(pin_value)
    parts = [f'\\"{p}\\"' if " " in p else p for p in (interp, str(Path(__file__).resolve()))]
    parts += ["--peer", box]
    return f'restrict,command="{" ".join(parts)}" ssh-ed25519 {key_body} unimatrix'


def load_file_relay_line():
    """`file_line` of the file-relay script beside this relay; None when it is not vendored here."""
    import importlib.util
    path = Path(__file__).with_name("unimatrix-file-relay.py")
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("unimatrix_file_relay_lines", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.file_line


def windows_admin():
    if sys.platform != "win32":
        return False
    import ctypes
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def reconcile_authorized_keys(members, path, membership, is_admin=windows_admin, listed=frozenset(),
                              unenrolled=None):
    """Make the relay-managed lines of `path` equal the generated lines for `members`.

    Only lines whose forced command names unimatrix-relay.py are touched; every other line keeps its
    exact bytes. A managed line already equal to its generated line stays in place; a stale pin of a
    member key is regenerated; a line for a key in `listed` (key bodies a prior snapshot listed) that
    `members` omits is dropped (a revocation). A managed line for any other key was never enrolled: it
    is kept byte-for-byte and its key body is appended to `unenrolled` when given.
    Returns admin | unchanged | updated.
    """
    if is_admin():
        return "admin"
    want = {}
    for body, line in membership.member_lines(members, relay_line, load_file_relay_line()):
        want[body] = line
    path = Path(path)
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    out, kept = [], set()
    for raw in old.splitlines(keepends=True):
        body = managed_key_body(raw)
        if body is None:
            out.append(raw)
        elif body not in want and body not in listed:
            out.append(raw)
            if unenrolled is not None and body not in unenrolled:
                unenrolled.append(body)
        elif body in want and body not in kept and raw.rstrip("\r\n") == want[body]:
            kept.add(body)
            out.append(raw)
    if out and not out[-1].endswith("\n"):
        out[-1] += "\n"
    out += [line + "\n" for body, line in want.items() if body not in kept]
    new = "".join(out)
    if new == old:
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(new, encoding="utf-8", newline="\n")
        if os.name == "posix":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return "updated"


def membership_get(home, membership):
    """(snapshot line, base64 sig line) of the held snapshot, or None when none is held. Never verifies or signs."""
    snap, sig = membership.load_snapshot(home)
    if snap is None:
        return None
    return membership.canonical_bytes(snap).decode("ascii"), base64.b64encode(sig).decode("ascii")


def _pin_pinless_receiver(home, snap, sig, pin_line, membership, notifier, run):
    """Write the pushed pin only when this box holds none and `snap` verifies against it; else do nothing.

    Verification precedes the write, so a snapshot the pushed pin does not vouch for leaves no pin file.
    Raises MembershipError (after a `refused` event) when the pushed pin cannot vouch for `snap`."""
    if not pin_line.strip() or membership.load_pin(home) is not None:
        return
    try:
        held, _ = membership.load_snapshot(home)
        membership.verify_snapshot(snap, sig, pin_line.strip(), held=held, run=run)
        fp = membership.fingerprint(pin_line)
    except membership.MembershipError as ex:
        notifier(home, {"kind": "refused", "epoch": snap.get("epoch"), "detail": f"pushed pin: {ex}"[:160]})
        raise
    membership.write_pin(home, pin_line)
    notifier(home, {"kind": "pinned", "epoch": snap.get("epoch"), "detail": f"signer pin {fp} adopted from a verified push"})


def membership_put(home, snapshot_line, sig_line, membership, authorized_keys, notifier=None,
                   is_admin=windows_admin, run=subprocess.run, pin_line=""):
    """Verify and adopt a pushed snapshot, then reconcile authorized_keys; return the reply dict.

    The pin and the epoch gate inside `membership.adopt` are the only defence: a refusal (bad
    signature, replayed epoch, fork, no pin, malformed input) appends one `refused` event and changes
    nothing. A non-empty `pin_line` pins a pinless receiver, and only when the snapshot verifies
    against it; a receiver already holding a pin ignores it. The relay never signs."""
    notifier = notifier or membership.notify
    try:
        snap = json.loads(snapshot_line)
        sig = base64.b64decode(sig_line.strip(), validate=True)
        if not isinstance(snap, dict) or not sig:
            raise ValueError("snapshot or signature empty")
    except ValueError as ex:
        notifier(home, {"kind": "refused", "detail": f"malformed push: {type(ex).__name__}"})
        return {"ok": False, "reason": "malformed"}
    try:
        prior, _ = membership.load_snapshot(home)
        try:
            listed = ({b for m in prior["members"]
                       for b in (*membership.member_key_bodies(m), *([m["file_pub"].split()[1]] if "file_pub" in m else []))}
                      if prior else set())
        except (KeyError, IndexError, TypeError, AttributeError):
            listed = set()
        _pin_pinless_receiver(home, snap, sig, pin_line, membership, notifier, run)
        members = membership.adopt(home, snap, sig, notifier=notifier, run=run)
    except membership.MembershipError as ex:
        return {"ok": False, "reason": f"refused: {ex}"[:200]}
    unenrolled = []
    result = reconcile_authorized_keys(members, authorized_keys, membership, is_admin, listed, unenrolled)
    for body in unenrolled:
        notifier(home, {"kind": "unenrolled", "epoch": snap["epoch"], "detail": f"relay line kept, key {body[:24]} not in any snapshot"})
    return {"ok": True, "epoch": snap["epoch"], "authorized_keys": result}


GIB = 1024 ** 3


def _ram_windows():
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None, None
    return status.ullTotalPhys, status.ullAvailPhys


def _ram_linux():
    fields = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            fields[key] = int(parts[0]) * 1024
    total = fields.get("MemTotal")
    return total, fields.get("MemAvailable", fields.get("MemFree"))


def _ram_darwin():
    total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                               timeout=3).stdout.strip())
    vm = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=3).stdout
    page = re.search(r"page size of (\d+) bytes", vm)
    size = int(page.group(1)) if page else 4096
    pages = 0
    for label in ("Pages free", "Pages inactive", "Pages speculative"):
        match = re.search(rf"{label}:\s+(\d+)", vm)
        pages += int(match.group(1)) if match else 0
    return total, pages * size


def _gpu_cmd(argv):
    out = subprocess.run(argv, capture_output=True, text=True, timeout=3,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return out.stdout if out.returncode == 0 else ""


def _gpu_windows():
    out = _gpu_cmd(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    return out.splitlines()[0].strip() if out.strip() else None


def _gpu_darwin():
    for line in _gpu_cmd(["system_profiler", "SPDisplaysDataType"]).splitlines():
        if "Chipset Model:" in line:
            return line.split(":", 1)[1].strip()
    return None


def _gpu_linux():
    out = _gpu_cmd(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    if out.strip():
        return out.splitlines()[0].strip()
    for line in _gpu_cmd(["lspci"]).splitlines():
        if re.search(r"VGA compatible|3D controller|Display controller", line):
            return line.split(": ", 1)[-1].strip()
    return None


def _safe(probe):
    try:
        return probe()
    except Exception:
        return None


def probe_specs(platform=None):
    """This box's RAM, CPU and GPU as one record; any field the OS will not give is None."""
    platform = platform or sys.platform
    ram = {"win32": _ram_windows, "darwin": _ram_darwin}.get(platform, _ram_linux)
    gpu = {"win32": _gpu_windows, "darwin": _gpu_darwin}.get(platform, _gpu_linux)
    total, available = _safe(ram) or (None, None)
    return {
        "box": local_box(),
        "ram_gb": round(total / GIB, 1) if total else None,
        "ram_available_gb": round(available / GIB, 1) if available else None,
        "cpu_cores": os.cpu_count(),
        "gpu": _safe(gpu),
        "sampled_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def main():
    try:
        import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
        from cc_invoke import ensure_engine_on_path

        ensure_engine_on_path(__file__)
    except ImportError:  # a receiving-box copy carries no lib/; the engine resolves lazily
        pass
    parsed = parse_mode(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
    if parsed is None:
        sys.exit("usage: roster | capabilities | specs | send <pid> | send-batch <pid> | send-to <pid> <digest> | send-named <pid> <digest> <name-digest> | send-session <pid> <digest> <name-digest> <session-id> | receipts <session-id> <since> | inbox <name> | inbox-mux | reply-inbox <name> | source | "
                 "grant <grantee> <note> <ttl> <repo> | revoke <grantee> | keypin <box_id> | freshness | membership get | membership put")
    mode, arg = parsed
    if mode == "membership":
        membership = load_membership()
        if membership is None:
            sys.exit("membership library not vendored beside the relay")
        home = settings_home()
        if arg == "get":
            held = membership_get(home, membership)
            if held is None:
                sys.exit("no membership snapshot held")
            print(held[0])
            print(held[1])
            return
        reply = membership_put(home, sys.stdin.readline(), sys.stdin.readline(), membership,
                               Path.home() / ".ssh" / "authorized_keys", pin_line=sys.stdin.readline())
        print(json.dumps(reply))
        sys.exit(0 if reply.get("ok") is True else 1)
    if mode in ("grant", "revoke", "keypin"):
        peer = peer_arg(sys.argv[1:])
        line = sys.stdin.readline()
        if mode == "grant":
            reply = grant(arg, line, peer=peer)
        elif mode == "revoke":
            reply = revoke(arg, line, peer=peer)
        else:
            reply = keypin(arg, line, peer=peer)
        print(json.dumps(reply))
        sys.exit(0 if reply.get("ok") is True else 1)
    if mode == "freshness":
        reply = freshness()
        print(json.dumps(reply))
        sys.exit(0 if reply.get("ok") is True else 1)
    if mode == "mirror-stale":
        print(json.dumps(mark_stale(*arg)))
    elif mode == "capabilities":
        print(json.dumps({"ok": True, "capabilities": CAPABILITIES, "relay_sha": relay_sha()}))
    elif mode == "roster":
        roster(mirrors=arg == "mirrors")
    elif mode == "specs":
        print(json.dumps(probe_specs()))
    elif mode == "receipts":
        print(json.dumps(receipts(*arg)))
    elif mode == "send":
        send(arg)
    elif mode == "send-batch":
        send_batch(arg)
    elif mode in ("send-to", "send-named", "send-session"):
        send_batch(*arg)
    elif mode == "source":
        # Far boxes vendor this relay; serving our own text keeps syncs off the full-shell key.
        sys.stdout.buffer.write(Path(__file__).read_bytes())
    elif mode == "inbox-mux":
        inbox_mux()
    else:
        inbox(arg, export_reply=mode == "reply-inbox")


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in sys.argv[1:]):
        print("usage: unimatrix-relay [-h]\nunimatrix relay daemon")
        raise SystemExit(0)
    main()
