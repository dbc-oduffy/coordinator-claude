"""Stop leg: a NEW top-level directory on a drive root is recorded and blocks the stop.

Why after-the-fact: the PreToolUse drive-root guards see shell command text, but a
drive-root stray usually comes from code -- a test handing a bare "/fake-root" to a
path API resolves it to the current drive root on Windows, and no command ever names it. Diffing
the root against a baseline at every Stop catches any writer, test runs included.

Contract:
  stdin   -- Stop JSON (session_id, transcript_path, cwd, stop_hook_active)
  roots   -- the drive anchors of cwd, the repo root and the home dir; overridden by
             COORDINATOR_DRIVE_ROOTS (os.pathsep-separated) for tests
  baseline-- JSON {root: [dir names]} at COORDINATOR_DRIVE_ROOT_BASELINE, else
             <settings home>/state/drive-root-baseline.json. A root seen for the first
             time is seeded silently; a fire adds the new names, so each stray is
             recorded once, and a removed name is dropped so a re-creation fires again.
  fire    -- block-discharge record + exit 2, naming the session and, when this
             session's transcript tail shows one, the command that mentioned the name.
  override-- COORDINATOR_ALLOW_DRIVE_ROOT_NEW_DIR=1 (guard-override-keys convention): the
             baseline still absorbs the new names, but nothing fires. For a directory the
             PM creates on purpose; without it, such a directory blocks one Stop, once.
Never raises: any failure degrades to exit 0 with nothing written.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

GUARD = "guard-drive-root-new-dir"
TRIPWIRE = "SCRATCH-AT-A-DRIVE-ROOT-IS-LITTER"
OVERRIDE_KEY = "COORDINATOR_ALLOW_DRIVE_ROOT_NEW_DIR"
_TAIL_BYTES = 400_000


def _settings_home() -> Path:
    env = os.environ.get("COORDINATOR_SETTINGS_HOME")
    return Path(env) if env else Path.home() / ".coordinator-claude-settings"


def _baseline_path() -> Path:
    env = os.environ.get("COORDINATOR_DRIVE_ROOT_BASELINE")
    return Path(env) if env else _settings_home() / "state" / "drive-root-baseline.json"


def _roots(cwd: str, repo_root: str | None) -> list[str]:
    env = os.environ.get("COORDINATOR_DRIVE_ROOTS")
    if env:
        return [r for r in env.split(os.pathsep) if r]
    anchors = []
    for p in (cwd, repo_root, str(Path.home())):
        if p:
            anchor = Path(p).anchor
            if anchor and anchor not in anchors:
                anchors.append(anchor)
    return anchors


def _dir_names(root: str) -> set[str]:
    try:
        with os.scandir(root) as it:
            return {e.name for e in it if e.is_dir(follow_symlinks=False)}
    except OSError:
        return set()


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _creating_command(transcript_path: str, name: str) -> str | None:
    """Last Bash/PowerShell command in this session's transcript tail naming `name`."""
    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "rb") as fh:
            if size > _TAIL_BYTES:
                fh.seek(size - _TAIL_BYTES)
            tail = fh.read().decode("utf-8", "replace")
    except (OSError, TypeError):
        return None
    found = None
    for line in tail.splitlines():
        if name not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        msg = entry.get("message") if isinstance(entry, dict) else None
        for block in (msg.get("content") if isinstance(msg, dict) else None) or []:
            if (isinstance(block, dict) and block.get("type") == "tool_use"
                    and block.get("name") in ("Bash", "PowerShell")):
                command = (block.get("input") or {}).get("command")
                if isinstance(command, str) and name in command:
                    found = command
    return found


def _record_fire(repo_root: str, session_id: str, reason: str) -> str | None:
    try:
        from _engine_root import place_engine_root_on_path, resolve_claude_klabauter_root

        root = resolve_claude_klabauter_root()
        if not root:
            return None
        place_engine_root_on_path(root)
        from coordinator_core.block_discharge import record_fire
    except Exception:
        return None
    try:
        return record_fire(repo_root, session_id, GUARD, reason)
    except Exception:
        return None


def _git_root(cwd: str) -> str | None:
    try:
        from _git_root_walk import git_root_walk

        return git_root_walk(cwd)
    except Exception:
        return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return 0
    try:
        raw_cwd = payload.get("cwd")
        cwd: str = raw_cwd if isinstance(raw_cwd, str) and raw_cwd else os.getcwd()
        repo_root = _git_root(cwd)
        baseline_path = _baseline_path()
        baseline = _load(baseline_path)
        new: list[tuple[str, str]] = []
        changed = False
        for root in _roots(cwd, repo_root):
            current = _dir_names(root)
            if not current:
                continue
            known = baseline.get(root)
            if not isinstance(known, list):
                baseline[root] = sorted(current)
                changed = True
                continue
            known_set = set(known)
            new.extend((root, n) for n in sorted(current - known_set))
            if current != known_set:
                baseline[root] = sorted(current)
                changed = True
        if changed:
            _save(baseline_path, baseline)
    except Exception:
        return 0
    if not new or os.environ.get(OVERRIDE_KEY) == "1":
        return 0

    session_id = payload.get("session_id") or "unknown-session"
    anchor_repo: str = repo_root or cwd
    lines = [f"[guard] {GUARD}: new top-level director{'y' if len(new) == 1 else 'ies'} "
             f"on a drive root since the last check (session {session_id}):"]
    for root, name in new:
        command = _creating_command(payload.get("transcript_path") or "", name)
        where = os.path.join(root, name)
        lines.append(f"  {where}" + (f"  <- command: {command[:300]}" if command
                                     else "  <- no command in this session's transcript names it "
                                          "(another session, or code such as a test resolving a bare '/path')"))
    lines.append(f"Scratch lives in <repo>/scratch/ and tests write only under tmp_path. Find the "
                 f"writer, fix it, then remove the directory. Tripwire: {TRIPWIRE}.")
    reason = "\n".join(lines) + "\n"
    nonce = _record_fire(anchor_repo, session_id, reason)
    if nonce:
        reason += (f"Recorded as {nonce}. When you have acted on this, run:\n"
                   f'  block-discharge record --nonce {nonce} --action "<what you did>" '
                   f'--repo-root "{anchor_repo}"\n')
    else:
        reason += "Could not record this fire (engine unresolvable or write failed).\n"
    sys.stderr.write(reason)
    return 2


if __name__ == "__main__":
    sys.exit(main())
