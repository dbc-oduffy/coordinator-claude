#!/usr/bin/env python3
"""agy SessionStart hook: register the conversation's leg at boot.

agy's SessionStart env carries only ANTIGRAVITY_CONVERSATION_ID, not ANTIGRAVITY_CSRF_TOKEN, so the
leg starts pending: it binds its endpoint and queues peer messages. The language-server address is
discovered from the agy pid's listening ports. The first run_command through the PreToolUse hook's
rewrite (unimatrix-agy-hook-pretool.py) relaunches the leg live, which drains the queue.

Reads the payload's `conversationId`, takes the agy pid from the nearest agy.exe ancestor of this hook
(agy launches hooks through a short-lived intermediate process, so getppid() is never used; none found
records no agy pid), takes the leg cwd from the payload `cwd` else `workspacePaths[0]`, and runs unimatrix-agy-hook-launch.py's start() in-process; start() spawns the leg detached and writes
the leg record, then the conversation is upserted into peers.json (register_peer, as the Codex hook
does). Where the env does carry the address and token the leg starts live here.

Always exits 0. Prints one JSON object: a plain systemMessage noting registration when a leg record exists afterwards, else `{}`.

unimatrix-agy-hook-launch.py and unimatrix-roster.py are resolved beside this file.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = "agy"
NOTE = "Registered with the unimatrix peer router: Claude/Codex peers can message this session."


def load_sibling(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def payload_cwd(payload):
    """Payload `cwd` when a non-empty string, else the first non-empty string of `workspacePaths`, else None."""
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return cwd
    paths = payload.get("workspacePaths")
    first = paths[0] if isinstance(paths, list) and paths else None
    return first if isinstance(first, str) and first else None


def register(payload, agy_pid, engine_root=None):
    """Start the leg for payload's conversation; True when a leg record for it exists afterwards."""
    if not isinstance(payload, dict):
        return False
    launch = load_sibling("unimatrix-agy-hook-launch")
    roster = launch.load_sibling("unimatrix-roster")
    conv = payload.get("conversationId") or os.environ.get("ANTIGRAVITY_CONVERSATION_ID")
    state = roster.settings_home() / "unimatrix" / "agy-legs"
    cwd = payload_cwd(payload)
    launch.start({"conversationId": conv, "agyPid": agy_pid, "cwd": cwd}, roster, state)
    registered = isinstance(conv, str) and bool(launch.CONV_RE.match(conv)) and (state / f"{conv}.json").is_file()
    if registered:
        record_path = state / f"{conv}.json"
        bind_peer(conv, record_path)
        register_external_session(conv, cwd, record_path, engine_root=engine_root)
    return registered


def _resolve_engine_root(engine_root=None):
    """Return an absolute Path to the stamped engine root, or None when unavailable."""
    if engine_root:
        root = Path(engine_root)
        return root if root.is_absolute() else None
    env_root = os.environ.get("COORDINATOR_ENGINE_ROOT")
    if env_root:
        root = Path(env_root)
        if root.is_absolute():
            return root
    try:
        lib_dir = str(HERE / "lib")
        if lib_dir not in sys.path:
            sys.path.insert(0, lib_dir)
        from cc_invoke import resolve_colocated_claude_klabauter_root
        found = resolve_colocated_claude_klabauter_root(str(Path(__file__).resolve()))
        if found:
            root = Path(found)
            if root.is_absolute():
                return root
    except Exception:
        pass
    return None


def register_external_session(conv, cwd, record, engine_root=None) -> bool:
    """Register this Agy session in the engine's external_registry so session.whoami_live,
    session.peer_roster, and EM identity checks observe it. Never raises."""
    try:
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            return False
        root = _resolve_engine_root(engine_root)
        if root is None or not (root / "coordinator_core" / "_engine_stamp").read_bytes():
            return False
        name = None
        try:
            router = load_sibling("unimatrix-peer-router")
            rec_cwd = json.loads(Path(record).read_text(encoding="utf-8")).get("cwd") or cwd
            name = router.readable_peer_name(VENDOR, conv, rec_cwd)
        except Exception:
            name = None
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from coordinator_core.session import external_registry
        payload = {
            "session_id": conv,
            "cwd": cwd,
            "provider": VENDOR,
            "hook_event_name": "SessionStart",
            "source": "startup",
        }
        if isinstance(name, str) and name:
            payload["name"] = name
        external_registry.register_current(payload)
        return True
    except Exception:
        return False


def bind_peer(conv, record):
    """Upsert this conversation into peers.json as an agy peer, named as the router names a leg record.

    Never raises: the leg record already registers the peer with the router, so a peers.json
    failure (lock timeout, conflicting alias) only loses the durable row.
    """
    try:
        router = load_sibling("unimatrix-peer-router")
        cwd = json.loads(record.read_text(encoding="utf-8")).get("cwd")
        name = router.readable_peer_name(VENDOR, conv, cwd)
        return load_sibling("unimatrix-codex-hook-sessionstart").register_peer(
            router.default_peers_file(), name, VENDOR, conv)
    except Exception:
        return None


def _repo_claude_md(cwd, max_bytes=24000):
    """Collect standing repo conventions (CLAUDE.md) from nearest .git root down to cwd, capped cleanly at max_bytes."""
    if not isinstance(cwd, str) or not cwd:
        return None
    cur = Path(cwd).resolve()
    if not cur.is_dir():
        return None
    chain = [cur, *cur.parents]
    git_idx = next((i for i, p in enumerate(chain) if (p / ".git").exists()), None)
    dirs = list(reversed(chain[: git_idx + 1])) if git_idx is not None else [cur]
    seen = set()
    sections = []
    for d in dirs:
        candidate = d / "CLAUDE.md"
        if not candidate.is_file():
            continue
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        content = candidate.read_text(encoding="utf-8", errors="replace").strip()
        if content:
            sections.append(f"[Project standing conventions: {resolved}]\n{content}")
    if not sections:
        return None
    text = "\n\n".join(sections)
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    kept = []
    used = 0
    for line in text.splitlines(keepends=True):
        line_bytes = len(line.encode("utf-8"))
        if used + line_bytes > max_bytes:
            break
        kept.append(line)
        used += line_bytes
    if kept:
        return "".join(kept).rstrip("\r\n")
    return encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip("\r\n") or None


def reply(registered, worker_pointer=None, failure=None, repo_doctrine=None) -> dict:
    # Trap: agy (observed 2026-11-04) panics "cannot convert string to message" on a SessionStart
    # systemMessage carrying metadata.user_markdown, despite its own docs; notes go as plain text.
    notes = ([NOTE] if registered else []) + [n for n in (worker_pointer, failure, repo_doctrine) if n]
    return {"injectSteps": [{"systemMessage": {"systemMessage": n}} for n in notes]} if notes else {}


def main(argv=None) -> int:
    out = {}
    try:
        args = list(sys.argv[1:] if argv is None else argv)
        root = args[args.index("--engine-root") + 1] if "--engine-root" in args[:-1] else None
        payload = json.load(sys.stdin)
        try:
            pointer = load_sibling("unimatrix-codex-hook-sessionstart").worker_pointer()
        except Exception:
            pointer = None
        failure = None
        try:
            repo_doctrine = _repo_claude_md(payload_cwd(payload))
        except Exception:
            repo_doctrine = None
        failure = None
        try:
            agy_pid = load_sibling("unimatrix-agy-hook-pretool").agy_ancestor_pid()
            registered = register(payload, agy_pid, root) if root is not None else register(payload, agy_pid)
        except Exception as exc:  # the session still starts; the cause rides as a note, as the Codex hook does
            registered, failure = False, f"unimatrix: peer registration failed: {exc}"
        out = reply(registered, pointer, failure, repo_doctrine)
    except Exception:
        out = {}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    if any(_a in ("-h", "--help") for _a in __import__("sys").argv[1:]):
        print("usage: unimatrix-agy-hook-sessionstart [-h]\nAntigravity SessionStart hook body; reads hook JSON on stdin, emits JSON")
        raise SystemExit(0)
    sys.exit(main())
