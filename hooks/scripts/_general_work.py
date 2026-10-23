"""Machine-local general-work root: the landing folder for work that fits no project.

Resolves `coordinator.general_work_root` (default `<workspace>/0-general-work`, beside the
registered `repos.*` checkouts), refuses a root inside a checkout or overlapping the group-em home,
and creates it on demand; `ensure_root` git-inits it (one `git init` spawn, only when `.git` is
absent), pins the key, converges the full coordinator-repo tree and commits only the paths it seeded. The root is
the `general-work-em` memo identity and is registered as `repos.general_work`, which
`resolve_root` exempts from the checkout refusal and the repos section omits. TRAP: the legacy `[general-work]`
brackets are glob metacharacters wherever it resolves, so the root is never handed to glob/fnmatch
and is quoted in any shell line.
Contract: gem-cockpit-contract.md.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import _engine_root
import _gem_home
import _general_work_tree

KEY = "coordinator.general_work_root"
REPOS_KEY = "repos.general_work"
DEFAULT_DIRNAME = "0-general-work"
# Legacy fallback: resolve_root returns it only when the default is absent and it exists. Code never
# creates or renames it, though `ensure` still seeds an existing legacy root in place.
LEGACY_DIRNAME = "[general-work]"
_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _PLUGIN_ROOT / "templates" / "general-work-home" / "home-CLAUDE.md"


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


def _inside_checkout(root: Path) -> str | None:
    """`_gem_home.inside_checkout` for the root: a strict `.git` ancestor or a `repos.*` root
    containing it refuses; a `repos.*` root equal to the root (its own registration) does not."""
    target = _gem_home._norm(root)
    cur = Path(os.path.realpath(str(root)))
    for anc in cur.parents:
        if (anc / ".git").exists():
            return str(anc)
    for repo in _gem_home._repo_roots():
        r = _gem_home._norm(repo)
        if target != r and target.startswith(r.rstrip(os.sep) + os.sep):
            return repo
    return None


def resolve_root() -> Path:
    configured = _engine_root._registry_value(_engine_root._settings_home_registry_dir(), KEY)
    if configured:
        root = Path(configured)
    else:
        base = workspace_dir()
        root = base / DEFAULT_DIRNAME
        if not root.exists() and (base / LEGACY_DIRNAME).exists():
            root = base / LEGACY_DIRNAME
    hit = _inside_checkout(root)
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
    try:
        own = _gem_home._norm(resolve_root())
    except RootRefused:
        own = None
    for layer in _gem_home._registry_layers():
        for k, v in layer.items():
            if k.startswith("repos.") and isinstance(v, str) and v and (
                own is None or _gem_home._norm(v) != own
            ):
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


_SEED_IDENTITY = ("-c", "user.name=general-work-root", "-c", "user.email=general-work-root@localhost")


def _git(root: Path, *args: str, pre: tuple[str, ...] = ()):
    """Run git in `root`; None when git is missing or fails to spawn, so callers stay non-fatal."""
    try:
        return subprocess.run(
            ["git", *pre, "-C", str(root), *args],
            capture_output=True,
            check=False,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _git_init(root: Path) -> None:
    """`git init` the root once; an existing `.git` is never touched, and a missing or failing git
    binary leaves the root untracked (a later `ensure` retries)."""
    if (root / ".git").exists():
        return
    _git(root, "init", "-q")


def _move_unborn_to_main(root: Path) -> None:
    """Point an unborn HEAD at `main` (`symbolic-ref` works on every git version, unlike `init -b`);
    a branch with commits is never renamed."""
    unborn = _git(root, "rev-parse", "--verify", "-q", "HEAD")
    if unborn is not None and unborn.returncode != 0:
        _git(root, "symbolic-ref", "HEAD", "refs/heads/main")


_IGNORE_ENTRIES = (".coordinator-local/", "scratch/")
_OLD_HEADING = "## No ceremony here"
_NEW_HEADING = "## Working state and memos"


def _section(text: str, heading: str) -> tuple[int, int] | None:
    """Span of the `heading` section: its line through the char before the next `## ` heading or the
    repos fence (or end of text); None when the heading line is absent."""
    start = None
    pos = 0
    for line in text.splitlines(keepends=True):
        if start is None:
            if line.rstrip("\r\n") == heading:
                start = pos
        elif line.startswith("## ") or line.startswith(BEGIN):
            return start, pos
        pos += len(line)
    return None if start is None else (start, len(text))


def _retire_no_ceremony(current: str, template_text: str) -> str:
    """Swap a `## No ceremony here` section for the template's `## Working state and memos` one;
    text outside the section is untouched, and a text without the old heading comes back as is."""
    old = _section(current, _OLD_HEADING)
    new = _section(template_text, _NEW_HEADING)
    if old is None or new is None or _section(current, _NEW_HEADING) is not None:
        return current
    body = template_text[new[0]:new[1]]
    if not body.endswith("\n"):
        body += "\n"
    if old[1] < len(current) and not body.endswith("\n\n"):
        body += "\n"
    return current[:old[0]] + body + current[old[1]:]


def _pin_identity(root: Path) -> None:
    """Pin `coordinator.general_work_root` and `repos.general_work` to `root` when each is unset; a
    set value is never overwritten."""
    for key in (KEY, REPOS_KEY):
        try:
            if _engine_root._registry_value(_engine_root._settings_home_registry_dir(), key):
                continue
            import _registry_write

            _registry_write.machine_local_set(key, str(root))
        except Exception:
            # Best-effort: an unwritable registry leaves the key unset; the next ensure retries.
            continue


def _seed_tree(root: Path) -> list[str]:
    """Converge the full coordinator tree via `seed_full_tree` and return the commit set: its paths
    plus `.gitignore` and `CLAUDE.md` when they exist (posix, root-relative)."""
    try:
        paths = _general_work_tree.seed_full_tree(root, _PLUGIN_ROOT)
        _gem_home._ensure_ignored(root, _IGNORE_ENTRIES)
    except OSError:
        paths = []
    return sorted({*paths, *(rel for rel in (".gitignore", "CLAUDE.md") if (root / rel).is_file())})


def _commit_seed(root: Path, paths: list[str]) -> None:
    """Stage and commit exactly `paths`, each named explicitly, skipping any path git reports as
    ignored or excluded; a no-op when none differs from HEAD. Supplies a fallback identity only
    when the box has none."""
    use = []
    for rel in paths:
        res = _git(root, "check-ignore", "-q", "--", rel)
        if res is None or res.returncode > 1:
            return
        if res.returncode == 1:
            use.append(rel)
    if not use:
        return
    _git(root, "add", "--", *use)
    dirty = _git(root, "status", "--porcelain", "--", *use)
    if dirty is None or not dirty.stdout.strip():
        return
    ident = _git(root, "config", "user.email")
    pre = () if ident is not None and ident.returncode == 0 and ident.stdout.strip() else _SEED_IDENTITY
    _git(root, "commit", "-q", "-m", "general-work root: seed coordinator state tree", "--", *use, pre=pre)


def ensure_root(template: Path | None = None) -> Path:
    """Create the root, git-init it when it has no `.git`, pin `coordinator.general_work_root` and
    `repos.general_work` when unset, converge the full coordinator-repo tree (the canonical-structure
    eager `state/` dirs, `docs/plans`, `archive/`, `tasks/`, `coordinator.local.md`, the canonical
    `.gitignore` block, `state/orientation_cache.md`) and CLAUDE.md when absent, retire a `## No ceremony here` section,
    refresh the generated repos section, put an unborn HEAD on `main`, and commit only those seed
    paths by explicit pathspec (excluded or ignored paths are skipped, never forced). A repeat call
    with unchanged content adds no commit; best-effort, never raises on git or registry failure."""
    root = resolve_root()
    root.mkdir(parents=True, exist_ok=True)
    _git_init(root)
    _pin_identity(root)
    seed = root / "CLAUDE.md"
    src = template or _TEMPLATE
    section = render_repos_section()
    tpl_text = src.read_text(encoding="utf-8") if src.is_file() else None
    # A missing template skips CLAUDE.md seeding silently; templates/general-work-home/home-CLAUDE.md must ship.
    if seed.exists():
        current = seed.read_text(encoding="utf-8")
        if tpl_text is not None:
            current = _retire_no_ceremony(current, tpl_text)
    elif tpl_text is not None:
        current = tpl_text
    else:
        current = None
    if current is not None:
        merged = _merge(current, section)
        if not seed.exists() or merged != seed.read_text(encoding="utf-8"):
            seed.write_text(merged, encoding="utf-8", newline="\n")
    paths = _seed_tree(root)
    _move_unborn_to_main(root)
    _commit_seed(root, paths)
    return root
