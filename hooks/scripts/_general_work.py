"""Machine-local general-work root: the landing folder for work that fits no project.

Resolves `coordinator.general_work_root` (default `<workspace>/[general-work]`, beside the
registered `repos.*` checkouts), refuses a root inside a checkout or overlapping the group-em home,
and creates it on demand; `ensure_root` git-inits it (one `git init` spawn, only when `.git` is
absent). TRAP: the brackets are glob
metacharacters, so the root is never handed to glob/fnmatch and is quoted in any shell line.
Contract: gem-cockpit-contract.md.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import _engine_root
import _gem_home

KEY = "coordinator.general_work_root"
DEFAULT_DIRNAME = "[general-work]"
_TEMPLATE = Path(__file__).resolve().parent.parent.parent / "templates" / "general-work-home" / "home-CLAUDE.md"


class RootRefused(Exception):
    """The root lands in a checkout or overlaps the group-em home; `.conflict` names it."""

    def __init__(self, root: str, conflict: str):
        self.root = root
        self.conflict = conflict
        super().__init__(f"general-work root {root} conflicts with {conflict}")


def workspace_dir() -> Path:
    """The single common parent of the `repos.*` roots, else the user home."""
    parents = {os.path.dirname(os.path.normpath(r)) for r in _gem_home._repo_roots()}
    if len(parents) == 1:
        only = parents.pop()
        if only:
            return Path(only)
    return Path.home()


def _overlaps(a, b) -> bool:
    return _gem_home._under(a, b) or _gem_home._under(b, a)


def resolve_root() -> Path:
    configured = _engine_root._registry_value(_engine_root._settings_home_registry_dir(), KEY)
    root = Path(configured) if configured else workspace_dir() / DEFAULT_DIRNAME
    hit = _gem_home.inside_checkout(root)
    if hit:
        raise RootRefused(str(root), hit)
    try:
        gem = _gem_home.resolve_home()
    except _gem_home.HomeRefused:
        return root
    if _overlaps(root, gem):
        raise RootRefused(str(root), str(gem))
    return root


def is_general_work(cwd) -> bool:
    """True when `cwd` is the root or under it with no `.git` between them; a refused root is never one."""
    try:
        root = resolve_root()
    except RootRefused:
        return False
    if not _gem_home._under(cwd, root):
        return False
    stop = _gem_home._norm(root)
    cur = Path(os.path.realpath(str(cwd)))
    while _gem_home._norm(cur) != stop:
        if (cur / ".git").exists():
            return False
        if cur.parent == cur:
            return False
        cur = cur.parent
    return True


BEGIN = "<!-- BEGIN generated: repos -->"
END = "<!-- END generated: repos -->"


def named_repos() -> list[tuple[str, str]]:
    """Registered `repos.*` as (key, path) sorted by key; the local layer wins over the shared one."""
    found: dict[str, str] = {}
    for layer in _gem_home._registry_layers():
        for k, v in layer.items():
            if k.startswith("repos.") and isinstance(v, str) and v:
                found.setdefault(k[len("repos."):], v)
    return sorted(found.items())


def render_repos_section() -> str:
    """The marker-fenced registry section; a pure function of the registry, so reruns are byte-stable."""
    lines = [
        BEGIN,
        "## Repos on this box",
        "",
        "Generated from the machine-local repo registry (`repos.*` keys). Query it with "
        "`machine-local keys | grep '^repos\\.'` and `machine-local get repos.<key>`; "
        "`general-work-root ensure` regenerates this section when the registry changes.",
        "",
        "If the work involves one of these repos, do not do it here: route it to that repo. "
        "Tell the user which repo owns it, then continue in that repo's folder.",
        "",
    ]
    repos = named_repos()
    if not repos:
        lines.append("No `repos.*` entries were readable from the registry (none registered, or Python < 3.11 "
                     "without tomllib); check `machine-local keys` before assuming no repo applies.")
    for name, path in repos:
        lines.append(f"- `{name}`: `{path}`. Route work on {name} (its code, plans, issues) there.")
    lines += ["", END]
    return "\n".join(lines)


def _merge(existing: str, section: str) -> str:
    """Replace the fenced section in place, else append it; text outside the fence is never touched."""
    a = existing.find(BEGIN)
    b = existing.find(END, a + 1) if a >= 0 else -1
    if a >= 0 and b >= 0:
        return existing[:a] + section + existing[b + len(END):]
    return existing.rstrip("\n") + "\n\n" + section + "\n"


def _git_init(root: Path) -> None:
    """`git init` the root once; an existing `.git` is never touched, and a missing or failing git
    binary leaves the root untracked (a later `ensure` retries)."""
    if (root / ".git").exists():
        return
    try:
        subprocess.run(
            ["git", "init", "-q", str(root)],
            capture_output=True,
            check=False,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        pass


def ensure_root(template: Path | None = None) -> Path:
    """Create the root, git-init it when it has no `.git`, seed CLAUDE.md when absent, and refresh
    its generated repos section. No `state/`; history is never touched on a repeat call."""
    root = resolve_root()
    root.mkdir(parents=True, exist_ok=True)
    _git_init(root)
    seed = root / "CLAUDE.md"
    src = template or _TEMPLATE
    section = render_repos_section()
    if seed.exists():
        current = seed.read_text(encoding="utf-8")
    # A missing template skips seeding silently; templates/general-work-home/home-CLAUDE.md must ship.
    elif src.is_file():
        current = src.read_text(encoding="utf-8")
    else:
        return root
    merged = _merge(current, section)
    if not seed.exists() or merged != current:
        seed.write_text(merged, encoding="utf-8", newline="\n")
    return root
