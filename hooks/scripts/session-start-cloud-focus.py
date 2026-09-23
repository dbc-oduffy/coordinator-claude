"""SessionStart hook: arm a cloud session's focus repo; report missing agent teams.

Cloud-only, by the engine's own detector (`coordinator_core.env_locality`,
harness rung only -- a headless VM is not a cloud session); a silent no-op
everywhere else, and wherever the engine does not resolve. Two legs:

- Agent teams are on in every cloud session (the settings manifest's
  all-machines `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, applied at pre-boot).
  The harness reads that flag once, at process start, so a hook can only
  report it missing, never turn it on. Silent when it is `1`.
- `COORDINATOR_CLOUD_FOCUS_REPO`, set in the environment's env-var box (the
  one surface that reaches a session) -- `owner/repo` or bare `repo`. The hook
  locates that checkout, and on `startup` gives its session branch an empty
  anchor commit when the branch carries nothing ahead of base (GitHub refuses
  a PR with no commits). It then points the session at
  `coordinator:cloud-channel`, which pushes, opens or reuses the draft PR, and
  subscribes to it. PR creation and subscription are MCP calls only the model
  can make, which is why this hook hands off rather than finishing the job.

The anchor is written with `commit-tree` + a compare-and-swap `update-ref`,
never `git commit`: HEAD's own tree is reused, so the index and working tree
are untouched even when a peer has staged work. It never fires on the base
branch or a detached HEAD. Registered on `startup` only: the other SessionStart
sources land mid-execution, where an anchor write is unsafe.

OWN TOP-LEVEL REGISTRATION, never folded into `sessionstart-dispatch.py`: the
line is an instruction the session must act on, and that fan-in's shared
stdout is the measured truncation path (`assert-em-role.py`'s unfold record).

Contract: exit 0 on every path; every failure degrades to silence or to a
line naming what is missing. stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import resolve_claude_klabauter_root as _resolve_claude_klabauter_root  # noqa: E402
except Exception:
    def _resolve_claude_klabauter_root() -> Optional[str]:
        return None

FOCUS_ENV = "COORDINATOR_CLOUD_FOCUS_REPO"
TEAMS_FLAG_ENV = "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"

#: Where the platform mounts the repositories selected for an environment,
#: matching `cloud_setup.py`'s own `retrieval_search_roots`.
CHECKOUT_ROOTS = (Path("/home/user"), Path("/workspace"))  # abs-path-ok: cloud VM mount points, cloud-only hook

_GIT_TIMEOUT_S = 3
_REMOTE_SLUG = re.compile(r"[/:]([^/:]+)/([^/]+?)(?:\.git)?/?$")

def parse_focus(value: str) -> Tuple[Optional[str], str]:
    value = value.strip().strip("/")
    if value.lower().endswith(".git"):
        value = value[:-4]
    if "/" in value:
        owner, _, repo = value.rpartition("/")
        return owner.rpartition("/")[2] or None, repo
    return None, value


def origin_slug(checkout: Path) -> Optional[Tuple[str, str]]:
    """`(owner, repo)` of `remote "origin"`, read from `.git/config` directly."""
    try:
        text = (checkout / ".git" / "config").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    in_origin = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_origin = stripped.replace(" ", "") == '[remote"origin"]'
            continue
        if in_origin and stripped.startswith("url"):
            match = _REMOTE_SLUG.search(stripped.partition("=")[2].strip())
            return (match.group(1), match.group(2)) if match else None
    return None


def _candidates(roots: Iterable[Path]) -> List[Path]:
    seen: List[Path] = []
    for root in roots:
        try:
            children = sorted(p for p in root.iterdir() if p.is_dir())
        except OSError:
            children = []
        for path in [root, *children]:
            if path not in seen and (path / ".git").is_dir():
                seen.append(path)
    return seen


def find_checkout(owner: Optional[str], repo: str,
                  roots: Iterable[Path]) -> Optional[Tuple[Path, str]]:
    """`(checkout, "owner/repo")` for the checkout whose origin names `repo` (and
    `owner`, when given). Case-insensitive: GitHub slugs are, and env-box values
    get retyped."""
    for path in _candidates(roots):
        slug = origin_slug(path)
        if slug is None:
            continue
        if slug[1].lower() == repo.lower() and (owner is None or slug[0].lower() == owner.lower()):
            return path, f"{slug[0]}/{slug[1]}"
    return None


def read_branch(checkout: Path) -> Optional[str]:
    try:
        head = (checkout / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    prefix = "ref: refs/heads/"
    return head[len(prefix):] if head.startswith(prefix) else None


def _git(checkout: Path, *args: str, env: Optional[dict] = None) -> Optional[str]:
    try:
        done = subprocess.run(
            ["git", "-C", str(checkout), *args],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_S, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def base_branch(checkout: Path) -> Optional[str]:
    symbolic = _git(checkout, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if symbolic and symbolic.startswith("origin/"):
        return symbolic[len("origin/"):]
    for name in ("main", "master"):
        if _git(checkout, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{name}"):
            return name
    return None


def ensure_anchor(checkout: Path, branch: str, base: str, session_id: str) -> bool:
    """True when the branch can carry a PR: already ahead of base, or anchored now."""
    ahead = _git(checkout, "rev-list", "--count", f"refs/remotes/origin/{base}..HEAD")
    if ahead is None:
        return False
    if ahead != "0":
        return True
    head = _git(checkout, "rev-parse", "HEAD")
    tree = _git(checkout, "rev-parse", "HEAD^{tree}")
    if not head or not tree:
        return False
    message = (
        "cloud: open session channel\n\n"
        "Empty anchor so this branch can carry the session's draft PR "
        "(coordinator:cloud-channel).\n\n"
        f"Cloud-Session-Id: {session_id or 'unknown'}\n"
    )
    env = dict(os.environ)
    if not _git(checkout, "config", "user.email"):
        env.update(GIT_AUTHOR_NAME="Claude", GIT_AUTHOR_EMAIL="noreply@anthropic.com",
                   GIT_COMMITTER_NAME="Claude", GIT_COMMITTER_EMAIL="noreply@anthropic.com")
    commit = _git(checkout, "commit-tree", tree, "-p", head, "-m", message, env=env)
    if not commit:
        return False
    return _git(checkout, "update-ref", f"refs/heads/{branch}", commit, head) is not None


def render_teams_line(flag: str) -> Optional[str]:
    if flag == "1":
        return None
    return (
        f"CLOUD: agent teams OFF. Add {TEAMS_FLAG_ENV}=1 to the env-var box, then start a "
        "new session."
    )


def render_focus_line(focus: str, name: Optional[str], branch: Optional[str],
                      base: Optional[str], ready: bool) -> str:
    """Pure: `name` is the checkout's `owner/repo`, None when no checkout matched."""
    if name is None:
        return f"CLOUD FOCUS: no checkout matches {focus}; select that repo for this environment."
    if branch is None or (base is not None and branch == base):
        where = "a detached HEAD" if branch is None else branch
        return f"CLOUD FOCUS: {name} is on {where}; cut a branch, then run coordinator:cloud-channel."
    if not ready:
        return f"CLOUD FOCUS: {name} {branch} is level with base; commit, then run coordinator:cloud-channel."
    return f"CLOUD FOCUS: {name}, branch {branch} -> {base}. First act: invoke coordinator:cloud-channel."


def is_cloud_session() -> bool:
    root = _resolve_claude_klabauter_root()
    if not root:
        return False
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from coordinator_core.env_locality import harness_rung
    except Exception:  # noqa: BLE001
        return False
    hit = harness_rung()
    return hit is not None and hit.call == "cloud"


def main() -> int:
    try:
        if not is_cloud_session():
            return 0
    except Exception:  # noqa: BLE001
        return 0
    focus = os.environ.get(FOCUS_ENV, "").strip()

    lines = []
    try:
        lines.append(render_teams_line(os.environ.get(TEAMS_FLAG_ENV, "").strip()))
        if focus:
            owner, repo = parse_focus(focus)
            found = find_checkout(owner, repo, [*CHECKOUT_ROOTS, Path.cwd()]) if repo else None
            checkout, name = found if found else (None, None)
            branch = read_branch(checkout) if checkout else None
            base = base_branch(checkout) if checkout else None
            ready = base is not None
            if checkout and branch and base and branch != base:
                ready = ensure_anchor(
                    checkout, branch, base, os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID", "")
                )
            lines.append(render_focus_line(focus, name, branch, base, ready))
    except Exception:  # noqa: BLE001
        pass

    context = "\n".join(line for line in lines if line)
    if not context:
        return 0
    try:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": context,
        }}))
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
