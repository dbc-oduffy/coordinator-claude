"""Codex SessionStart hook: bind this Codex thread to a stable peer name in peers.json.

Reads the hook payload on stdin ({"session_id": <thread id>, "cwd": ...}). Fires on every thread
start, resume, clear and fork, so each one rebinds the same peer name to the current thread id; the
router rescans peers.json, so no Codex restart is needed and nothing depends on the id staying put.

Peer name: the UNIMATRIX_PEER_NAME env var, else codex- plus the cwd basename. Prints a systemMessage so the
registration shows in the TUI. Never fails the session: every path exits 0.

register_peer() is the shared registration helper: it takes the vendor and target, so another
vendor's SessionStart hook differs only in payload field names and vendor.
"""
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: replace stays atomic, only the read-modify-write lock is skipped
    fcntl = None

HERE = Path(__file__).resolve().parent
VENDOR = "codex"
NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")


def load_sibling(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def peer_name(payload, env=None):
    """Stable peer name: the env override, else codex-<cwd basename>, else codex."""
    env = os.environ if env is None else env
    explicit = NAME_RE.sub("-", (env.get("UNIMATRIX_PEER_NAME") or "").strip()).strip("-")
    if explicit:
        return explicit
    cwd = payload.get("cwd")
    base = NAME_RE.sub("-", Path(cwd).name).strip("-") if isinstance(cwd, str) and cwd else ""
    return f"{VENDOR}-{base}" if base else VENDOR


def register_peer(peers_file, name, vendor, target):
    """Upsert {name, vendor, target} into peers_file atomically; return "added", "rebound" or "present".

    The file's other rows are kept as written; a missing file is created. An unreadable or
    non-list file raises ValueError and is left untouched.
    """
    peers_file = Path(peers_file)
    peers_file.parent.mkdir(parents=True, exist_ok=True)
    lock = open(f"{peers_file}.lock", "a", encoding="utf-8")
    try:
        if fcntl is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        data, rows = None, []
        if peers_file.exists():
            try:
                data = json.loads(peers_file.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError(f"{peers_file} is not parseable JSON: {exc}") from exc
            rows = data.get("peers") if isinstance(data, dict) else data
            if not isinstance(rows, list):
                raise ValueError(f"{peers_file}: expected a list of peers or {{\"peers\": [...]}}")
        row = {"name": name, "vendor": vendor, "target": target}
        status = "added"
        for i, existing in enumerate(rows):
            if isinstance(existing, dict) and existing.get("name") == name:
                if existing.get("vendor") == vendor and existing.get("target") == target:
                    return "present"
                rows[i] = row
                status = "rebound"
                break
        else:
            rows.append(row)
        out = {**data, "peers": rows} if isinstance(data, dict) else rows
        tmp = Path(f"{peers_file}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, peers_file)
        return status
    finally:
        lock.close()


def run(payload, peers_file=None, env=None):
    """Register the payload's thread; return the hook's stdout object, or None when nothing applies."""
    thread = payload.get("session_id")
    if not isinstance(thread, str) or not thread.strip():
        return None
    if peers_file is None:
        peers_file = load_sibling("unimatrix-peer-router").default_peers_file()
    name = peer_name(payload, env)
    status = register_peer(peers_file, name, VENDOR, thread)
    return {"systemMessage": f"unimatrix: peer {name} bound to Codex thread {thread} ({status})"}


def main():
    try:
        payload = json.load(sys.stdin)
        out = run(payload) if isinstance(payload, dict) else None
        if out:
            print(json.dumps(out))
    except Exception as exc:  # a hook must never break the session
        print(json.dumps({"systemMessage": f"unimatrix: peer registration failed: {exc}"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
