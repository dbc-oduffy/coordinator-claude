"""Load-time surface snapshot for the restart-is-a-probe-verdict rule.

SessionStart records a per-surface hash of everything Claude Code reads only at load;
`bin/needs-restart.py` re-hashes and diffs. Stdlib only, no subprocess, never raises.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, Optional

#: A change in these needs a full restart; every other surface is picked up by /reload-plugins.
RESTART_SURFACES = ("settings_env", "mcp")
RELOAD_SURFACES = ("plugin", "enabled_plugins", "settings_hooks", "agents", "hooks_json")
_KEEP = 50


def settings_home() -> Path:
    explicit = os.environ.get("COORDINATOR_SETTINGS_HOME")
    if explicit:
        return Path(explicit)
    base = os.environ.get("CLAUDE_HOME") or str(Path.home())
    return Path(base) / ".coordinator-claude-settings"


def cache_dir() -> Path:
    return settings_home() / "cache" / "restart-snapshots"


def _claude_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))


def _plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def _h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hj(obj: object) -> str:
    return _h(json.dumps(obj, sort_keys=True, default=str).encode("utf-8"))


def _load(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _file_hash(path: Path) -> str:
    try:
        return _h(path.read_bytes())
    except Exception:
        return "absent"


def compute_surfaces(cwd: Optional[str] = None) -> Dict[str, str]:
    cfg = _claude_dir()
    settings = _load(cfg / "settings.json")
    settings = settings if isinstance(settings, dict) else {}
    root = _plugin_root()

    manifest = None
    for rel in (".claude-plugin/plugin.json", "coordinator/.claude-plugin/plugin.json"):
        manifest = _load(root / rel)
        if manifest is not None:
            break
    version = manifest.get("version") if isinstance(manifest, dict) else None

    agents = []
    try:
        for p in sorted((cfg / "agents").iterdir()):
            try:
                st = p.stat()
                agents.append([p.name, st.st_size, int(st.st_mtime)])
            except Exception:
                continue
    except Exception:
        pass

    claude_json = _load(Path.home() / ".claude.json")
    mcp = {
        "user": claude_json.get("mcpServers") if isinstance(claude_json, dict) else None,
        "project": _file_hash(Path(cwd or os.getcwd()) / ".mcp.json"),
        "settings": settings.get("mcpServers"),
        "plugin": _file_hash(root / ".mcp.json"),
    }
    hooks_json = root / "hooks" / "hooks.json"
    if not hooks_json.exists():
        hooks_json = root / "coordinator" / "hooks" / "hooks.json"

    return {
        "plugin": _hj(version),
        "enabled_plugins": _hj(settings.get("enabledPlugins")),
        "settings_env": _hj(settings.get("env")),
        "settings_hooks": _hj(settings.get("hooks")),
        "agents": _hj(agents),
        "mcp": _hj(mcp),
        "hooks_json": _file_hash(hooks_json),
    }


def _snapshot_path(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_.") or "unknown"
    return cache_dir() / (safe + ".json")


def write_snapshot(session_id: str, source: str = "", cwd: Optional[str] = None) -> None:
    """Fail-open. `clear`/`compact` keep the process's load-time state, so they never overwrite."""
    try:
        if not session_id:
            return
        path = _snapshot_path(session_id)
        if source in ("clear", "compact") and path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"session_id": session_id, "ts": time.time(), "surfaces": compute_surfaces(cwd)}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
        os.replace(tmp, path)
        old = sorted(cache_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in old[_KEEP:]:
            try:
                p.unlink()
            except Exception:
                pass
    except Exception:
        pass


def read_snapshot(session_id: str = "") -> Optional[dict]:
    """This session's snapshot, else the most recent one."""
    try:
        if session_id:
            snap = _load(_snapshot_path(session_id))
            if isinstance(snap, dict):
                return snap
        files = sorted(cache_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files:
            snap = _load(p)
            if isinstance(snap, dict):
                return snap
    except Exception:
        pass
    return None


def verdict(session_id: str = "", cwd: Optional[str] = None) -> str:
    try:
        snap = read_snapshot(session_id)
        if not snap:
            return "none"
        old = snap.get("surfaces") or {}
        new = compute_surfaces(cwd)
        changed = {k for k in new if old.get(k) != new[k]}
        if changed & set(RESTART_SURFACES):
            return "restart"
        if changed & set(RELOAD_SURFACES):
            return "/reload-plugins"
    except Exception:
        pass
    return "none"
