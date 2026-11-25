#!/usr/bin/env python3
"""agy sidecar entry: bring each conversation's leg up live at session start.

agy launches this once per agy process, from the declaration unimatrix-install.py writes under
<agy config>/sidecars/, with ANTIGRAVITY_LS_ADDRESS and ANTIGRAVITY_CSRF_TOKEN in its env. The
credentials never leave process env: each leg is started through unimatrix-agy-hook-launch.py's start(),
which hands them to the leg's env only. Without both variables this exits 0 and the SessionStart hook's
pending leg and the in-turn queue drain stay in force.

The SessionStart hook has no credentials, so it hands the conversation id (never a token) to this
process over a loopback listener: `handoff()` reads STATE/agy-sidecars/<agy pid>.json for the port and a
per-process nonce, and sends one JSON line {"nonce", "conversationId", "cwd"}. Pending legs this agy
process already holds are upgraded once at start, for a SessionStart that ran before the sidecar did.
The process exits, removing its record, when its agy process is gone.

unimatrix-agy-hook-launch.py, unimatrix-agy-hook-pretool.py and unimatrix-roster.py are resolved beside this file.
"""
import importlib.util
import json
import os
import secrets
import socket
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLL_SECS = 5.0
LINE_MAX = 1 << 16


def load_sibling(name) -> types.ModuleType:
    """The sibling script as a module, loaded by path (its name is not importable)."""
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def record_dir(home) -> Path:
    """STATE/agy-sidecars under the settings home: one record per live sidecar, keyed by agy pid."""
    return Path(home) / "unimatrix" / "agy-sidecars"


def credentials(env=None) -> "tuple | None":
    """(ls_address, token) from the sidecar env, or None unless both are set."""
    env = os.environ if env is None else env
    ls, token = env.get("ANTIGRAVITY_LS_ADDRESS"), env.get("ANTIGRAVITY_CSRF_TOKEN")
    return (ls, token) if ls and token else None


def handoff(conv, cwd, agy_pid, home, pid_alive, timeout=1.0) -> bool:
    """Ask the sidecar of `agy_pid` to start `conv`'s leg live; True only on its ok answer.

    False when no live sidecar record exists, the listener refuses, or the answer is not ok: the caller
    then starts the pending leg itself.
    """
    try:
        rec = json.loads((record_dir(home) / f"{agy_pid}.json").read_text(encoding="utf-8"))
        if not pid_alive(int(rec["pid"])):
            return False
        with socket.create_connection(("127.0.0.1", int(rec["port"])), timeout=timeout) as s:
            s.sendall((json.dumps({"nonce": rec["nonce"], "conversationId": conv, "cwd": cwd}) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n") and len(buf) < LINE_MAX:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
        return json.loads(buf).get("ok") is True
    except (OSError, ValueError, KeyError, TypeError):
        return False


class Hub:
    """Starts legs live from this process's env on request; holds the record's nonce."""

    def __init__(self, launch, roster, agy_pid, nonce) -> None:
        self.launch, self.roster, self.agy_pid, self.nonce = launch, roster, agy_pid, nonce
        self.state = roster.settings_home() / "unimatrix" / "agy-legs"

    def start_leg(self, conv, cwd=None) -> None:
        self.launch.start({"conversationId": conv, "agyPid": self.agy_pid, "cwd": cwd}, self.roster, self.state)

    def answer(self, line) -> dict:
        """The reply to one request line; a wrong nonce or a malformed conversation id starts nothing."""
        try:
            req = json.loads(line)
            conv = req["conversationId"]
            if not secrets.compare_digest(str(req.get("nonce", "")), self.nonce) or not self.launch.CONV_RE.match(conv):
                return {"ok": False}
            cwd = req.get("cwd")
            self.start_leg(conv, cwd if isinstance(cwd, str) and cwd else None)
        except Exception:
            return {"ok": False}
        return {"ok": True}

    def upgrade_pending(self) -> None:
        """Make live every pending leg this agy process already holds (its SessionStart ran first)."""
        for path in self.state.glob("*.json"):
            try:
                rec = json.loads(path.read_text(encoding="utf-8"))
                if rec.get("mode") == "pending" and rec.get("agy_pid") == self.agy_pid:
                    self.start_leg(rec["conversation"], rec.get("cwd"))
            except (OSError, ValueError, KeyError, TypeError):
                continue


def serve(hub, srv, pid_alive) -> None:
    """Answer handoff lines until the agy process is gone."""
    srv.settimeout(POLL_SECS)
    while pid_alive(hub.agy_pid):
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        with conn:
            conn.settimeout(5)
            buf = b""
            try:
                while not buf.endswith(b"\n") and len(buf) < LINE_MAX:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                conn.sendall((json.dumps(hub.answer(buf)) + "\n").encode())
            except OSError:
                pass


def main(env=None) -> int:
    if credentials(env) is None:
        return 0
    launch = load_sibling("unimatrix-agy-hook-launch")
    roster = launch.load_sibling("unimatrix-roster")
    agy_pid = load_sibling("unimatrix-agy-hook-pretool").agy_ancestor_pid() or os.getppid()
    hub = Hub(launch, roster, agy_pid, secrets.token_hex(16))
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    record = record_dir(roster.settings_home()) / f"{agy_pid}.json"
    try:
        record.parent.mkdir(parents=True, exist_ok=True)
        roster.write_json_atomic(str(record), {"pid": os.getpid(), "agy_pid": agy_pid,
                                               "port": srv.getsockname()[1], "nonce": hub.nonce})
        try:
            os.chmod(record, 0o600)
        except OSError:
            pass
        hub.upgrade_pending()
        serve(hub, srv, roster.pid_alive)
    finally:
        srv.close()
        try:
            record.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in sys.argv[1:]):
        print("usage: unimatrix-agy-sidecar [-h]\nagy sidecar entry; agy launches it with ANTIGRAVITY_LS_ADDRESS and ANTIGRAVITY_CSRF_TOKEN in env")
        raise SystemExit(0)
    sys.exit(main())
