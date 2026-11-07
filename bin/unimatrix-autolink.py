"""Bring up the cross-box Unimatrix link to every configured far box, once, and stay silent.

Usage:
  unimatrix-autolink.py

Far boxes are the members of the signed membership snapshot (verified offline against the pinned key,
minus this box), dialled as `<user>@<host>` from the record. Only when no snapshot exists are they the
comma-separated ssh aliases in the machine-local key `unimatrix.far_boxes` (transition fallback; unimatrix
doctor flags it). A snapshot that fails verification links nothing and logs one line. Each member that
answers is asked for `membership get`; a higher valid epoch is adopted (the library logs and notifies).
For each alias with no live supervisor pair, this starts one `unimatrix-roster.py` bridge
supervisor and one `unimatrix-mirror-all.py` inbox supervisor, detached, with only
that alias's relay key (`-o IdentitiesOnly=yes` is applied by the supervisors' ssh calls).
The key per alias is the machine-local `unimatrix.keys.<alias>`, else the IdentityFile `ssh -G` gives
the alias (an existing non-default file), else the shared key (settings home, else the group-em home).

When no alias is listed (or the registry is unreadable) it appends one reason line to the log and exits 0:
a receive-only box reads "no unimatrix.far_boxes configured; no supervisors started". An alias with no
existing key appends one line to the log and is skipped; other aliases still link. A held per-peer lock
logs its skip. An unreachable far box appends one line to `<settings home>/unimatrix/autolink.log`.
Nothing is ever printed and the exit status is always 0: a session start must not fail on it.
"""
import base64
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REGISTRY_KEY = "unimatrix.far_boxes"
ALIAS_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._@-]{0,63}")
PROBE_CONNECT_SECONDS = 5
PROBE_TIMEOUT_SECONDS = 15
LOCK_STALE_SECONDS = 60
KEYS_PREFIX = "unimatrix.keys."
SSH_DEFAULT_IDENTITIES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ecdsa_sk", "id_ed25519", "id_ed25519_sk", "id_xmss"}
SUPERVISORS = (("bridge", "unimatrix-roster.py"), ("inbox", "unimatrix-mirror-all.py"))


def _roster():
    spec = importlib.util.spec_from_file_location("unimatrix_roster", HERE / "unimatrix-roster.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def member_targets(roster, mem=None, self_names=None, run=subprocess.run):
    """(status, {remote: box}, epoch, reason) for the stored membership snapshot.

    status is "none" (no snapshot stored), "bad" (stored but not verifiable; reason says why) or "ok".
    Members are dialled as `<user>@<host>` from the record; this box is dropped by hostname."""
    try:
        mem = mem or _membership()
    except OSError:  # membership library not vendored on this box yet: the transition fallback applies
        return "none", {}, None, None
    home = roster.settings_home()
    try:
        snap, _ = mem.load_snapshot(home)
        if snap is None:
            return "none", {}, None, None
        members = mem.verified_members(home, run=run)
    except mem.MembershipError as ex:
        return "bad", {}, None, f"membership snapshot not usable, nothing linked from it: {str(ex)[:120]}"
    me = {n.lower() for n in (self_names if self_names is not None else own_names())}
    targets = {}
    for m in members:
        if m["box"].lower() in me or m["host"].split(".")[0].lower() in me:
            continue
        remote = f"{m['user']}@{m['host']}"
        if ALIAS_RE.fullmatch(remote):
            targets[remote] = m["box"]
    return "ok", targets, snap["epoch"], None


def pull_membership(roster, remote, key, run=subprocess.run):
    """Ask `remote` for `membership get` and adopt a strictly higher valid epoch; True when adopted.

    A refused snapshot is logged and notified by the library's adopt, then the error propagates."""
    mem = _membership()
    cmd = ["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
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


def far_boxes_status(roster):
    """(aliases, reason): reason names why `aliases` is empty, and is None when it is not."""
    reader = roster.settings_home() / "bin" / "_machine_local.py"
    if not reader.is_file():
        return [], f"{REGISTRY_KEY} unreadable (machine-local reader missing: {reader}); no supervisors started"
    try:
        r = subprocess.run([sys.executable, str(reader), "get", REGISTRY_KEY],
                           capture_output=True, text=True, timeout=30, creationflags=roster.no_window())
    except (OSError, subprocess.SubprocessError) as ex:
        return [], f"{REGISTRY_KEY} unreadable ({type(ex).__name__}); no supervisors started"
    raw = r.stdout.strip() if not r.returncode else ""
    if not raw:
        return [], NO_ALIAS_REASON
    seen = []
    for tok in re.split(r"[,\s]+", raw):
        if tok and ALIAS_RE.fullmatch(tok) and tok not in seen:
            seen.append(tok)
    if not seen:
        return [], f"{REGISTRY_KEY} lists no valid alias ({raw[:80]!r}); no supervisors started"
    return seen, None


def read_far_boxes(roster):
    """Configured ssh aliases; empty when the key, the reader, or any valid alias is absent."""
    return far_boxes_status(roster)[0]


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
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
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
    cmd = ["ssh", "-i", key, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
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
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) \
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(cmd, creationflags=flags, **kw)
    return subprocess.Popen(cmd, start_new_session=True, **kw)


def supervisor_cmd(script, log, alias, key, tunnel):
    cmd = [sys.executable, str(HERE / script), str(log), "--remote", alias, "--key", key]
    return cmd + ["--tunnel-remote", tunnel] if tunnel else cmd


def stable_fallback(roster, alias, key, why, probe_fn, stable_fn):
    """(remote, why) after a failed probe of `alias`: the first stable name that answers, else the original why."""
    alt = stable_fn(alias)
    if alt and alt != alias:
        why_alt = probe_fn(roster, alias, key, remote=alt)
        if not why_alt:
            return alt, None
    return alias, why


def link_peer(roster, alias, key, say, spawn=detached, probe_fn=probe, stable_fn=None, now=None, liveness=None,
              pull_fn=None):
    """Start whichever of the peer's two supervisors is not live. Never raises for a down peer.

    The stable-name fallback runs only after the alias itself failed to answer; the probe outcome feeds the backoff."""
    stable_fn = stable_fn or roster.stable_remote
    liveness = liveness or _liveness()
    sdir = state_dir(roster)
    rec_path = sdir / f"autolink-{slug(alias)}.json"
    lock = sdir / f"autolink-{slug(alias)}.lock"
    if not acquire_lock(lock):
        say(f"far box {alias}: link lock held by another start; skipped")
        return
    try:
        rec = read_record(rec_path)
        missing = [role for role, _ in SUPERVISORS if not supervisor_live(roster, rec.get(role) or {})]
        if not missing:
            return
        why = probe_fn(roster, alias, key)
        remote = alias
        if why:
            remote, why = stable_fallback(roster, alias, key, why, probe_fn, stable_fn)
        liveness.note_probe(sdir, alias, not why, now)
        if why:
            say(f"far box {alias} unreachable: {why}")
            return
        if remote != alias:
            say(f"far box {alias} pinned address stale; linked via {remote}")
        if pull_fn:
            try:
                pull_fn(roster, remote, key)
            except Exception as ex:  # a refused or malformed peer snapshot never blocks the link
                say(f"far box {alias}: membership pull skipped: {type(ex).__name__}: {str(ex)[:100]}")
        tunnel = roster.default_tunnel()
        for role, script in SUPERVISORS:
            if role not in missing:
                continue
            p = spawn(supervisor_cmd(script, sdir / f"{role}-{slug(alias)}.log", remote, key, tunnel))
            try:
                stamp = roster.proc_start(p.pid)
            except (OSError, subprocess.SubprocessError):
                stamp = None
            rec[role] = {"pid": p.pid, "procStart": stamp}
        roster.write_json_atomic(str(rec_path), rec)
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
        r = run([sys.executable, str(reader), "get", f"{KEYS_PREFIX}{alias}"],
                capture_output=True, text=True, timeout=30, creationflags=roster.no_window())
    except (OSError, subprocess.SubprocessError):
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
    for line in r.stdout.splitlines():
        name, _, val = line.partition(" ")
        if name.lower() != "identityfile":
            continue
        path = Path(os.path.expanduser(val.strip()))
        if path.name not in SSH_DEFAULT_IDENTITIES and path.is_file():
            return str(path)
    return None


def resolve_key(roster, alias, local_fn=None, ssh_fn=None):
    """The relay key for one alias: machine-local, else ssh-config IdentityFile, else the shared default."""
    local_fn, ssh_fn = local_fn or machine_local_key, ssh_fn or ssh_identity_file
    return local_fn(roster, alias) or ssh_fn(roster, alias) or roster.default_key()


def _epoch_moved(sdir, liveness):
    """True when a stored snapshot's epoch differs from the one the boxes cache was written at."""
    try:
        epoch = json.loads((sdir / "membership" / "snapshot.json").read_text(encoding="utf-8")).get("epoch")
    except (OSError, ValueError, AttributeError):
        return False
    return liveness.read_record(sdir / liveness.CACHE_NAME).get("epoch") != epoch


def run(roster=None, boxes=None, spawn=detached, probe_fn=probe, key_fn=None, stable_fn=None, now=None,
        membership=None, pull_fn=None, self_names=None):
    """Link every far box whose supervisors are down. A healthy box returns after reading records only.

    Explicit `boxes` are ssh aliases and bypass the snapshot. Otherwise the verified membership snapshot
    (minus this box) supplies `<user>@<host>` targets and `unimatrix.far_boxes` is read only when no
    snapshot is stored. Per alias the record check precedes key resolution, and an alias inside its probe
    backoff is skipped. The boxes cache short-circuits `healthy` for up to 24h unless the snapshot epoch
    moved since it was written."""
    key_fn = key_fn or resolve_key
    roster = roster or _roster()
    liveness = _liveness()
    sdir = state_dir(roster)
    if liveness.healthy(sdir, now) and not _epoch_moved(sdir, liveness):
        return
    sdir.mkdir(parents=True, exist_ok=True)

    def say(msg):
        with open(sdir / "autolink.log", "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}\n")

    reason = NO_ALIAS_REASON
    names, epoch, snapshot_mode = {}, None, False
    if boxes is None:
        status, names, epoch, why = member_targets(roster, membership, self_names)
        if status == "bad":
            say(why)
            return
        if status == "ok":
            snapshot_mode, boxes = True, list(names)
            reason = "membership snapshot lists no other member; no supervisors started"
        else:
            boxes, reason = far_boxes_status(roster)
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

    if snapshot_mode:
        stable_fn = stable_fn or (lambda alias: None)
        pull_fn = pull_fn or pull_membership
    else:
        pull_fn = None
    clock = time.time() if now is None else now

    def link_all(aliases):
        for alias in aliases:
            try:
                rec = read_record(sdir / f"autolink-{slug(alias)}.json")
                if all(supervisor_live(roster, rec.get(role) or {}) for role, _ in SUPERVISORS):
                    continue
                if liveness.backoff_until(sdir, alias) > clock:
                    continue
                key = key_fn(roster, names.get(alias, alias))
                if not Path(key).is_file():
                    # A configured alias with no key is a misconfiguration worth one line, not silence.
                    say(f"far box {alias}: no Unimatrix-Zero key (looked for {key}); not linked")
                    continue
                link_peer(roster, alias, key, say, spawn=spawn, probe_fn=probe_fn, stable_fn=stable_fn,
                          now=now, liveness=liveness, pull_fn=pull_fn)
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


def main():
    try:
        run()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
