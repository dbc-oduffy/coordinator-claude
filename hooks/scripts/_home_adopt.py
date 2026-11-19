"""Clone or adopt the user's GitHub `group-em` and `.claude` repos into the two homes.

`adopt_homes()` runs before `_gem_home.ensure_home` so the home already carries a `.git` when
`ensure_home` would otherwise `git init` it. Discovery only: it never creates a GitHub repo, never
pushes, never merges, and never overwrites a file already on disk.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import _engine_root
import _gem_home
import _general_work

GROUP_EM_KEY = "coordinator.group_em_home_remote_url"
CLAUDE_KEY = "coordinator.claude_home_remote_url"
# Probed in order; GitHub names are case-insensitive. Users name these repos variously.
GROUP_EM_NAMES = ("group-em", "coordinator-group-em")
CLAUDE_NAMES = (".claude", "dot-claude", "claude-settings", "claude-home")
FETCH_TIMEOUT = 60
# Machine-local or secret files: adoption turns them into untracked files a later `git add` would sweep.
CLAUDE_EXCLUDES = (".content-root", ".credentials.json")


def _registry_remote(key: str) -> str | None:
    """The registry's recorded remote URL for `key`, None when unset or unreadable."""
    try:
        return _engine_root._registry_value(_engine_root._settings_home_registry_dir(), key) or None
    except Exception:
        return None


def _record_remote(key: str, url: str) -> None:
    """Pin `key` to `url` in the machine-local registry; best-effort."""
    try:
        import _registry_write

        _registry_write.machine_local_set(key, url)
    except Exception:
        pass


def _targets() -> list[tuple[str, Path | Exception, str, tuple[str, ...]]]:
    """`(home, path-or-refusal, registry key, gh repo names)` per home."""
    try:
        gem: Path | Exception = _gem_home.resolve_home()
    except Exception as exc:
        gem = exc
    return [
        ("group-em", gem, GROUP_EM_KEY, GROUP_EM_NAMES),
        ("dot-claude", Path.home() / ".claude", CLAUDE_KEY, CLAUDE_NAMES),
    ]


class _Gh:
    """One `gh` login probe per `adopt_homes` call; bounded repo views per candidate name."""

    def __init__(self) -> None:
        self._login: str | None = None
        self._probed = False

    def discover(self, names: tuple[str, ...]) -> str | None:
        if not self._probed:
            self._probed = True
            self._login = _general_work._gh("api", "user", "--jq", ".login")
        if not self._login:
            return None
        for name in names:
            url = _general_work._gh("repo", "view", f"{self._login}/{name}", "--json", "url", "--jq", ".url")
            if url:
                return url
        return None


def _report(home: str, path, action: str, remote: str | None = None, detail: str = "") -> dict:
    return {"home": home, "path": str(path), "action": action, "remote": remote, "detail": detail}


def _out(res) -> str:
    return res.stdout.decode("utf-8", "replace").strip() if res is not None and res.returncode == 0 else ""


def _ok(res) -> bool:
    return res is not None and res.returncode == 0


def _g(path: Path, *args: str, timeout: float = 30, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes] | None:
    return _general_work._git(path, *args, timeout=timeout, stdin=stdin)


def _is_empty_dir(path: Path) -> bool:
    return path.is_dir() and not any(path.iterdir())


def _remote_default_branch(path: Path) -> tuple[str | None, bool]:
    """`(branch, reachable)`: the remote's default branch from `ls-remote --symref`; `(None, True)`
    for an empty remote with no HEAD."""
    res = _g(path, "ls-remote", "--symref", "origin", "HEAD", timeout=_general_work.GH_TIMEOUT * 2)
    if not _ok(res):
        return None, False
    for line in _out(res).splitlines():
        if line.startswith("ref:"):
            ref = line.split("\t", 1)[0][4:].strip()
            if ref.startswith("refs/heads/"):
                return ref[len("refs/heads/"):], True
    return None, True


def _restore_absent_paths(path: Path) -> str:
    """Check out, from the index, only tracked paths missing on disk; never overwrites. Returns a
    detail note."""
    listed = _g(path, "ls-files", "-z", "--deleted")
    if listed is None or listed.returncode != 0 or not listed.stdout:
        return ""
    res = _g(path, "checkout-index", "-q", "-z", "--stdin", stdin=listed.stdout, timeout=FETCH_TIMEOUT)
    return "" if _ok(res) else "some absent paths could not be restored"


def _reset_onto_remote(path: Path, branch: str) -> bool:
    """Point HEAD at `branch` and set the index to `origin/<branch>` without touching the worktree."""
    if not _ok(_g(path, "symbolic-ref", "HEAD", f"refs/heads/{branch}")):
        return False
    if not _ok(_g(path, "reset", "-q", "--mixed", f"origin/{branch}")):
        return False
    _g(path, "branch", "-q", f"--set-upstream-to=origin/{branch}", branch)
    return True


def _attach_and_adopt(home: str, path: Path, remote: str, fresh_git: bool) -> dict:
    """Give `path` (populated, no `.git`, or `.git` without an `origin` and an unborn HEAD) the
    remote. Index-only reset, then only absent paths are checked out. Cleans up what it added on failure."""

    def undo() -> None:
        if fresh_git:
            shutil.rmtree(path / ".git", ignore_errors=True)
        else:
            _g(path, "remote", "remove", "origin")

    if fresh_git and not _ok(_g(path, "init", "-q")):
        undo()
        return _report(home, path, "failed", remote, "git init failed")
    if not _ok(_g(path, "remote", "add", "origin", remote)):
        undo()
        return _report(home, path, "failed", remote, "git remote add failed")
    if not _ok(_g(path, "fetch", "-q", "origin", timeout=FETCH_TIMEOUT)):
        undo()
        return _report(home, path, "failed", remote, "git fetch failed")
    branch, reachable = _remote_default_branch(path)
    if not reachable:
        undo()
        return _report(home, path, "failed", remote, "git ls-remote failed")
    if branch is None:
        return _report(home, path, "attached", remote, "remote is empty; origin set, nothing reset")
    if not _reset_onto_remote(path, branch):
        undo()
        return _report(home, path, "failed", remote, f"could not reset index onto origin/{branch}")
    note = _restore_absent_paths(path)
    return _report(home, path, "adopted", remote, note or f"index set to origin/{branch}; worktree untouched")


def _attach_existing_git(home: str, path: Path, remote: str) -> dict:
    """`.git` without an `origin`: add it, fetch, then adopt (unborn HEAD), attach (related
    history) or report diverged and drop the origin it added."""
    if not _ok(_g(path, "remote", "add", "origin", remote)):
        return _report(home, path, "failed", remote, "git remote add failed")
    if not _ok(_g(path, "fetch", "-q", "origin", timeout=FETCH_TIMEOUT)):
        _g(path, "remote", "remove", "origin")
        return _report(home, path, "failed", remote, "git fetch failed")
    branch, reachable = _remote_default_branch(path)
    if not reachable:
        _g(path, "remote", "remove", "origin")
        return _report(home, path, "failed", remote, "git ls-remote failed")
    if branch is None:
        return _report(home, path, "attached", remote, "remote is empty; origin set")
    if not _ok(_g(path, "rev-parse", "--verify", "-q", "HEAD")):
        _g(path, "remote", "remove", "origin")
        return _attach_and_adopt(home, path, remote, fresh_git=False)
    upstream = f"origin/{branch}"
    related = _ok(_g(path, "merge-base", "HEAD", upstream))
    nested = _ok(_g(path, "merge-base", "--is-ancestor", "HEAD", upstream)) or _ok(
        _g(path, "merge-base", "--is-ancestor", upstream, "HEAD")
    )
    if not (related and nested):
        _g(path, "remote", "remove", "origin")
        return _report(home, path, "diverged", remote, f"local history and {upstream} have each moved; nothing merged or reset")
    return _report(home, path, "attached", remote, f"origin set; local history is related to {upstream}")


def _exclude_machine_local(path: Path) -> None:
    """Append `CLAUDE_EXCLUDES` to the repo's `info/exclude`, idempotently."""
    res = _g(path, "rev-parse", "--git-path", "info/exclude")
    rel = _out(res)
    if not rel:
        return
    target = (path / rel) if not Path(rel).is_absolute() else Path(rel)
    try:
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        have = set(existing.splitlines())
        missing = [e for e in CLAUDE_EXCLUDES if e not in have]
        if missing:
            target.parent.mkdir(parents=True, exist_ok=True)
            sep = "" if not existing or existing.endswith("\n") else "\n"
            target.write_text(existing + sep + "\n".join(missing) + "\n", encoding="utf-8")
    except OSError:
        pass


def _adopt_one(home: str, path, key: str, names: tuple[str, ...], gh: _Gh) -> dict:
    if isinstance(path, Exception):
        return _report(home, "", "failed", None, f"home refused: {path}")
    if (path / ".git").exists():
        origin = _g(path, "remote", "get-url", "origin")
        if _ok(origin):
            return _report(home, path, "kept", _out(origin), "already has an origin")
    remote = _registry_remote(key)
    discovered = False
    if not remote:
        remote = gh.discover(names)
        discovered = bool(remote)
    if not remote:
        return _report(home, path, "no-remote", None, "no registry remote and gh found no matching repo")

    if not path.exists() or _is_empty_dir(path):
        created = not path.exists()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _report(home, path, "failed", remote, f"mkdir failed: {exc}")
        if _general_work._clone(path, remote):
            result = _report(home, path, "cloned", remote, "")
        else:
            if created:
                try:
                    path.rmdir()
                except OSError:
                    pass
            return _report(home, path, "failed", remote, "git clone failed")
    elif (path / ".git").exists():
        result = _attach_existing_git(home, path, remote)
    elif path.is_dir():
        result = _attach_and_adopt(home, path, remote, fresh_git=True)
    else:
        return _report(home, path, "failed", remote, "path exists and is not a directory")

    if result["action"] in ("cloned", "adopted", "attached"):
        if discovered:
            _record_remote(key, remote)
        if home == "dot-claude":
            _exclude_machine_local(path)
    return result


def adopt_homes() -> list[dict]:
    """Clone or adopt the user's `group-em` and `.claude` GitHub repos; one report per home:
    `{home, path, action, remote, detail}` with action one of cloned, adopted, attached, kept,
    no-remote, diverged, failed. Never raises, never pushes, never overwrites an on-disk file."""
    gh = _Gh()
    reports = []
    for home, path, key, names in _targets():
        try:
            reports.append(_adopt_one(home, path, key, names, gh))
        except Exception as exc:
            reports.append(_report(home, path if not isinstance(path, Exception) else "", "failed", None, f"{type(exc).__name__}: {exc}"))
    return reports
