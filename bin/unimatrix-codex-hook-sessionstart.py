#!/usr/bin/env python3
"""Codex SessionStart hook: bind this Codex thread to a stable peer name in peers.json.

Reads the hook payload on stdin ({"session_id": <thread id>, "cwd": ...}). Fires on every thread
start, resume, clear and fork, so each one rebinds the thread's peer name (kept while its checkout
is unchanged) to the current thread id; the router rescans peers.json, so no Codex restart is needed
and nothing depends on the id staying put.

Versioned addresses are allocated only by the engine's external session registry and projected
unchanged here. Older sessions keep the checkout/suffix fallback. A default refresh cannot replace
an owned address, and a name belonging to another target is refused. Prints a systemMessage so
registration shows in the TUI. Never fails the session: every path exits 0.

register_peer() is the shared registration helper: it takes the vendor and target, so another
vendor's SessionStart hook differs only in payload field names and vendor.
"""
import contextlib
import importlib.util
import json
import os
import re
import sys
import time
import socket
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

try:
    import fcntl
except ImportError:
    fcntl = None

HERE = Path(__file__).resolve().parent
VENDOR = "codex"
NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")


def load_sibling(name) -> "ModuleType":
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def checkout_name(cwd) -> str:
    """Basename of the checkout holding cwd (nearest ancestor with .git), else of cwd itself."""
    path = Path(cwd)
    root = next((p for p in (path, *path.parents) if (p / ".git").exists()), path)
    return NAME_RE.sub("-", root.name).strip("-")


def peer_base(payload):
    """Repo part of the peer name from the session's own payload cwd; "codex" when there is none.

    UNIMATRIX_PEER_NAME is deliberately not read: it names the launching shell's own peer, and a
    Codex started from that shell inherits it.
    """
    cwd = payload.get("cwd")
    return (checkout_name(cwd) if isinstance(cwd, str) and cwd else "") or VENDOR


def codex_holder(pid=None):
    """{codexPid, codexProcStart} of pid (default: this hook's parent, the Codex process); {} when unreadable.

    codexProcStart is omitted when the start cannot be read: a pid alone still lets liveness decide."""
    pid = os.getppid() if pid is None else pid
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return {}
    holder = {"codexPid": pid}
    try:
        holder["codexProcStart"] = load_sibling("unimatrix-liveness").proc_start(pid)
    except Exception:  # a hook must never break the session
        pass
    return holder


@contextlib.contextmanager
def _peers_lock(peers_file):
    """Hold the exclusive peers.json writer lock (flock; msvcrt byte zero with a 15s deadline on Windows)."""
    peers_file = Path(peers_file)
    peers_file.parent.mkdir(parents=True, exist_ok=True)
    lock = open(f"{peers_file}.lock", "a+b")
    try:
        if fcntl is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        else:
            import errno
            import msvcrt
            # Every writer locks byte zero of the same permanent sidecar. Atomic replace
            # protects readers, but only this lock protects concurrent hook registrations.
            lock.seek(0, os.SEEK_END)
            if not lock.tell():
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            deadline = time.monotonic() + 15
            while True:
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"peer registration lock timed out: {peers_file}") from exc
                    time.sleep(0.02)
        yield
    finally:
        lock.close()


def register_peer(peers_file, name, vendor, target, address=None, holder=None):
    """Upsert {name, vendor, target} into peers_file atomically; return "added", "rebound" or "present".

    name may be a callable taking the current rows and returning the name, so it is chosen under the lock.
    holder ({codexPid, codexProcStart}) is written onto the row and refreshes a prior one on rebind.

    Other rows remain unchanged. A same-target legacy name becomes an alias when an engine
    address is projected. Conflicts, unreadable JSON and non-list files raise ValueError without
    writing the peers file.
    """
    peers_file = Path(peers_file)
    with _peers_lock(peers_file):
        data, rows = None, []
        if peers_file.exists():
            try:
                data = json.loads(peers_file.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError(f"{peers_file} is not parseable JSON: {exc}") from exc
            rows = data.get("peers") if isinstance(data, dict) else data
            if not isinstance(rows, list):
                raise ValueError(f"{peers_file}: expected a list of peers or {{\"peers\": [...]}}")
        contract = load_sibling('unimatrix-peer-contract')
        address = contract.owned_codex_address(address, target) if address is not None else None
        if address is not None and vendor != 'codex':
            raise ValueError('engine-owned Codex address requires vendor codex')
        owned = [contract.owned_codex_address(r, target) for r in rows if isinstance(r, dict)
                 and r.get('vendor') == vendor and r.get('target') == target and 'address_version' in r]
        if owned:
            if any(r['name'] != owned[0]['name'] for r in owned) or (address and address['name'] != owned[0]['name']):
                raise ValueError(f'immutable engine address changed for {target}')
            address = owned[0]
        if callable(name):
            name = name(rows)
        if address:
            name = address['name']
        row = {"name": name, "vendor": vendor, "target": target}
        if holder:
            row.update(holder)
        if address:
            row.update(address)
            aliases = []
            for prior in rows:
                if isinstance(prior, dict) and prior.get('vendor') == vendor and prior.get('target') == target:
                    aliases.extend([prior.get('name'), *prior.get('aliases', [])])
            aliases = list(dict.fromkeys(alias for alias in aliases if alias != name and contract.safe_alias(alias)))
            if aliases:
                row['aliases'] = aliases
        for prior in rows:
            if not isinstance(prior, dict) or (prior.get('vendor') == vendor and prior.get('target') == target):
                continue
            prior_names = [prior.get('name'), *prior.get('aliases', [])]
            if any(alias in prior_names for alias in [name, *row.get('aliases', [])]):
                raise ValueError(f'peer alias conflict: {name!r} is owned by another target')
        stale = [r for r in rows if isinstance(r, dict) and r.get("name") != name
                 and r.get("vendor") == vendor and r.get("target") == target]
        rows = [r for r in rows if not any(r is s for s in stale)]
        status = "added"
        for i, existing in enumerate(rows):
            if isinstance(existing, dict) and existing.get("name") == name:
                if existing.get("vendor") == vendor and existing.get("target") == target:
                    merged = {**existing, **row}
                    if holder and "codexProcStart" not in holder:
                        merged.pop("codexProcStart", None)
                    if not stale and merged == existing:
                        return "present"
                    rows[i] = merged
                    status = "rebound"
                    break
                raise ValueError(f'peer alias conflict: {name!r} is owned by another target')
        else:
            rows.append(row)
            status = "rebound" if stale else "added"
        out = {**data, "peers": rows} if isinstance(data, dict) else rows
        tmp = Path(f"{peers_file}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, peers_file)
        return status


def drop_peer_rows(peers_file, targets):
    """Remove agy rows whose target is in targets under the peers lock; return the dropped names.

    Container shape (list or {"peers": [...]}) and every other row are preserved. A missing,
    unparseable or non-list file returns [] and is never written; nothing matching writes nothing.
    """
    peers_file = Path(peers_file)
    targets = set(targets)
    with _peers_lock(peers_file):
        try:
            data = json.loads(peers_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        rows = data.get("peers") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        dropped = [r for r in rows if isinstance(r, dict) and r.get("vendor") == "agy"
                   and r.get("target") in targets]
        if not dropped:
            return []
        kept = [r for r in rows if not any(r is d for d in dropped)]
        out = {**data, "peers": kept} if isinstance(data, dict) else kept
        tmp = Path(f"{peers_file}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, peers_file)
        return [d.get("name") for d in dropped]


WORKER_POINTER = (
    "Worker mode: you were launched by the PM as an autonomous worker on your own branch. "
    "Doctrine: coordinator-content-repo coordinator/docs/wiki/worker-mode.md (read it before acting)."
)


def worker_env_name():
    """The worker env marker's name, read from agent_pipe/worker_mode.py beside this repo's bin/."""
    path = HERE.parent.parent / "coordinator_core" / "agent_pipe" / "worker_mode.py"
    try:
        spec = importlib.util.spec_from_file_location("worker_mode", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.WORKER_ENV
    except Exception:  # a hook must never break the session
        return "COORDINATOR_AGENT_WORKER"


def worker_pointer(env=None):
    """WORKER_POINTER when the worker env marker is set and non-empty in env, else None."""
    env = os.environ if env is None else env
    return WORKER_POINTER if str(env.get(worker_env_name(), "")).strip() else None


def allocate_engine_address(payload, engine_root) -> None:
    """Run the published engine's registration for a root thread so its address exists before publishing.

    Idempotent: a thread with a retained address keeps it. Never raises; the reader then reports
    the thread unbound as before. Subagent starts and a missing/unstamped engine do nothing.
    """
    try:
        root = Path(engine_root)
        if payload.get("agent_id") or not root.is_absolute():
            return
        if not (root / "coordinator_core" / "_engine_stamp").read_bytes():
            return
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from coordinator_core.session import external_registry
        external_registry.register_current({**payload, "hook_event_name": "SessionStart"})
    except Exception:  # a hook must never break the session
        pass


def run(payload, peers_file=None, registry_dir=None, engine_root=None) -> "dict | None":
    """Register the payload's thread; return the hook's stdout object, or None when nothing applies.

    A set worker env marker adds the doctrine pointer as hookSpecificOutput.additionalContext.
    With engine_root the engine allocates the thread's address first, so publishing is never unbound.
    """
    if engine_root and isinstance(payload, dict):
        allocate_engine_address(payload, engine_root)
    out = _register(payload, peers_file, registry_dir)
    pointer = worker_pointer()
    if pointer:
        out = {**(out or {}), "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": pointer}}
    return out


def _register(payload, peers_file=None, registry_dir=None):
    """Register the payload's thread; return the hook's stdout object, or None when nothing applies."""
    thread = payload.get("session_id")
    if not isinstance(thread, str) or not thread.strip():
        return None
    if peers_file is None:
        peers_file = load_sibling("unimatrix-peer-router").default_peers_file()
    if registry_dir is None:
        registry_dir = load_sibling('unimatrix-roster').settings_home() / 'host-sessions' / 'codex'
    try:  # this hook runs on codex's PATH; the delivery leg may not
        load_sibling('unimatrix-peer-codex').record_binary(registry_dir)
    except Exception:  # a hook must never break the session
        pass
    address = load_sibling('unimatrix-peer-contract').read_codex_address(registry_dir, thread, socket.gethostname())
    if not address:
        return {"systemMessage": f"unimatrix: Codex thread {thread} is unbound: no engine address"}
    chosen = []

    def pick(rows):
        chosen.append(address['name'])
        return chosen[0]

    status = register_peer(peers_file, pick, VENDOR, thread, address=address, holder=codex_holder())
    return {"systemMessage": f"unimatrix: peer {chosen[0]} bound to Codex thread {thread} ({status})"}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        argv = sys.argv[1:]
        root = argv[argv.index("--engine-root") + 1] if "--engine-root" in argv[:-1] else None
        out = run(payload, engine_root=root) if isinstance(payload, dict) else None
        if out:
            print(json.dumps(out))
    except Exception as exc:  # a hook must never break the session
        print(json.dumps({"systemMessage": f"unimatrix: peer registration failed: {exc}"}))
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in __import__("sys").argv[1:]):
        print("usage: unimatrix-codex-hook-sessionstart [-h]\nCodex SessionStart hook body; reads hook JSON on stdin, emits JSON")
        raise SystemExit(0)
    sys.exit(main())
