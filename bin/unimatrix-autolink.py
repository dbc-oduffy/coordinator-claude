"""Bring up the cross-box Unimatrix link to every configured far box, once, and stay silent.

Usage:
  unimatrix-autolink.py

Far boxes are the comma-separated ssh aliases in the machine-local key `unimatrix.far_boxes`.
For each alias with no live supervisor pair, this starts one `unimatrix-roster.py` bridge
supervisor and one `unimatrix-mirror-all.py` inbox supervisor, detached, with only
that alias's relay key (`-o IdentitiesOnly=yes` is applied by the supervisors' ssh calls).
The key per alias is the machine-local `unimatrix.keys.<alias>`, else the IdentityFile `ssh -G` gives
the alias (an existing non-default file), else the shared key (settings home, else the group-em home).

Silent exit 0 when no alias is listed. An alias with no existing key appends one line to the log and
is skipped; other aliases still link.
An unreachable far box appends one line to `<settings home>/unimatrix/autolink.log`.
Nothing is ever printed and the exit status is always 0: a session start must not fail on it.
"""
import importlib.util
import json
import os
import re
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


def state_dir(roster):
    return roster.settings_home() / "unimatrix"


def read_far_boxes(roster):
    """Configured ssh aliases; empty when the key, the reader, or any valid alias is absent."""
    reader = roster.settings_home() / "bin" / "_machine_local.py"
    if not reader.is_file():
        return []
    try:
        r = subprocess.run([sys.executable, str(reader), "get", REGISTRY_KEY],
                           capture_output=True, text=True, timeout=30, creationflags=roster.no_window())
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode:
        return []
    seen = []
    for tok in re.split(r"[,\s]+", r.stdout.strip()):
        if tok and ALIAS_RE.fullmatch(tok) and tok not in seen:
            seen.append(tok)
    return seen


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


def link_peer(roster, alias, key, say, spawn=detached, probe_fn=probe, stable_fn=None):
    """Start whichever of the peer's two supervisors is not live. Never raises for a down peer.

    The stable-name fallback runs only after the alias itself failed to answer."""
    stable_fn = stable_fn or roster.stable_remote
    sdir = state_dir(roster)
    rec_path = sdir / f"autolink-{slug(alias)}.json"
    lock = sdir / f"autolink-{slug(alias)}.lock"
    if not acquire_lock(lock):
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
        if why:
            say(f"far box {alias} unreachable: {why}")
            return
        if remote != alias:
            say(f"far box {alias} pinned address stale; linked via {remote}")
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


def run(roster=None, boxes=None, spawn=detached, probe_fn=probe, key_fn=None, stable_fn=None):
    key_fn = key_fn or resolve_key
    roster = roster or _roster()
    boxes = read_far_boxes(roster) if boxes is None else boxes
    if not boxes:
        return
    sdir = state_dir(roster)
    sdir.mkdir(parents=True, exist_ok=True)

    def say(msg):
        with open(sdir / "autolink.log", "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}\n")

    for alias in boxes:
        try:
            key = key_fn(roster, alias)
            if not Path(key).is_file():
                # A configured alias with no key is a misconfiguration worth one line, not silence.
                say(f"far box {alias}: no Unimatrix-Zero key (looked for {key}); not linked")
                continue
            link_peer(roster, alias, key, say, spawn=spawn, probe_fn=probe_fn, stable_fn=stable_fn)
        except Exception as ex:  # one peer's failure must not stop the next or fail the session
            say(f"far box {alias} link failed: {type(ex).__name__}: {str(ex)[:120]}")


def main():
    try:
        run()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
