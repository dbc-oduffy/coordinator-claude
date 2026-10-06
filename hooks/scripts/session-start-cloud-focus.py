"""SessionStart hook: arm a cloud session's focus repo.

Cloud-only, by the engine's own detector (`coordinator_core.env_locality`,
harness rung only -- a headless VM is not a cloud session); a silent no-op
everywhere else, and wherever the engine does not resolve. One leg:
`COORDINATOR_CLOUD_FOCUS_REPO`, set in the environment's env-var box (the
one surface that reaches a session) -- `owner/repo` or bare `repo`. The hook
locates that checkout, reads its branch and base from `.git` files (it spawns
nothing), and points the session at `coordinator:cloud-channel`, which writes
the empty anchor commit when the branch is level with base, pushes, opens or
reuses the draft PR, and subscribes to it. PR creation and subscription are
MCP calls only the model can make, which is why this hook hands off rather
than finishing the job.

Hosted as a head leg of `sessionstart-dispatch.py` on `startup`, emitting at
stream offset 0 under the pinned head budget.

Contract: exit 0 on every path; every failure degrades to silence or to a
line naming what is missing. stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

_HOOKS_DIR = str(Path(__file__).resolve().parent)
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
try:
    from _engine_root import (  # noqa: E402
        place_engine_root_on_path as _place_engine_root_on_path,
        resolve_claude_klabauter_root as _resolve_claude_klabauter_root,
    )
except Exception:
    def _resolve_claude_klabauter_root() -> Optional[str]:
        return None

    def _place_engine_root_on_path(root):
        if root and root not in sys.path[:2]:
            sys.path.insert(1 if sys.path else 0, root)
        return root

FOCUS_ENV = "COORDINATOR_CLOUD_FOCUS_REPO"

# Must match cloud_setup.py's own retrieval_search_roots. abs-path-ok: cloud VM mount points, cloud-only hook.
CHECKOUT_ROOTS = (Path("/home/user"), Path("/workspace"))  # abs-path-ok: cloud checkout-root literal the hook probes

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


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def base_branch(checkout: Path) -> Optional[str]:
    """Base branch from `.git` files only: origin/HEAD symref, packed-refs, loose refs."""
    git = checkout / ".git"
    head = _read(git / "refs" / "remotes" / "origin" / "HEAD").strip()
    prefix = "ref: refs/remotes/origin/"
    if head.startswith(prefix) and head[len(prefix):].strip():
        return head[len(prefix):].strip()
    packed = {
        line.split(None, 1)[1].strip()
        for line in _read(git / "packed-refs").splitlines()
        if line and line[0] not in "#^" and len(line.split(None, 1)) == 2
    }
    for name in ("main", "master"):
        ref = f"refs/remotes/origin/{name}"
        if ref in packed or (git / ref).is_file():
            return name
    return None


def render_focus_line(focus: str, name: Optional[str], branch: Optional[str],
                      base: Optional[str], ready: bool) -> str:
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
    _place_engine_root_on_path(root)
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
        if focus:
            owner, repo = parse_focus(focus)
            found = find_checkout(owner, repo, [*CHECKOUT_ROOTS, Path.cwd()]) if repo else None
            checkout, name = found if found else (None, None)
            branch = read_branch(checkout) if checkout else None
            base = base_branch(checkout) if checkout else None
            lines.append(render_focus_line(focus, name, branch, base, base is not None))
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
