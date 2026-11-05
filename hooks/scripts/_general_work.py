"""Machine-local general-work root: the landing folder for work that fits no project.

Resolves `coordinator.general_work_root` (default `<workspace>/_general-work`, where workspace is
the recorded `coordinator.repo_home`, else the folder holding most `repos.*` checkouts, else the
user home), refuses a root inside a checkout or overlapping the group-em home,
and creates it on demand; `ensure_root` clones `coordinator.general_work_remote` into it when set, else git-inits it
(only when `.git` is absent), pins the key, converges the full coordinator-repo tree and commits only the paths it seeded. The root is
the `general-work-em` memo identity and is registered as `repos.general_work`, which
`resolve_root` exempts from the checkout refusal.
Contract: gem-cockpit-contract.md.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import _engine_root
import _gem_home
import _general_work_tree

KEY = "coordinator.general_work_root"
REPOS_KEY = "repos.general_work"
REPO_HOME_KEY = "coordinator.repo_home"
REMOTE_KEY = "coordinator.general_work_remote"
CLONE_TIMEOUT = 20
DEFAULT_DIRNAME = "_general-work"
_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _PLUGIN_ROOT / "templates" / "general-work-home" / "home-CLAUDE.md"


class RootRefused(Exception):
    """The root lands in a checkout or overlaps the group-em home; `.conflict` names it."""

    def __init__(self, root: str, conflict: str):
        self.root = root
        self.conflict = conflict
        super().__init__(f"general-work root {root} conflicts with {conflict}")


def census_repo_home() -> Path | None:
    """The folder holding most of the box's real checkouts, else None. Candidates are the `repos.*`
    roots passing `_gem_home._is_checkout` (a drive root or probe is no vote), deduplicated, with
    `repos.general_work` excluded so the root never votes for its own parent; ties break on the
    lowest path. Bounded by the key count: no filesystem walk."""
    roots: dict[str, str] = {}
    for layer in _gem_home._registry_layers():
        for k, v in layer.items():
            if k.startswith("repos.") and k != REPOS_KEY and isinstance(v, str) and v and _gem_home._is_checkout(v):
                roots.setdefault(_gem_home._norm(v), v)
    votes: dict[str, int] = {}
    for r in roots.values():
        parent = os.path.dirname(os.path.normpath(r))
        if parent:
            votes[parent] = votes.get(parent, 0) + 1
    if not votes:
        return None
    return Path(min(votes, key=lambda p: (-votes[p], _gem_home._norm(p))))


def _recorded_repo_home() -> str | None:
    value = _engine_root._registry_value(_engine_root._settings_home_registry_dir(), REPO_HOME_KEY) or None
    return value if value and os.path.isdir(value) else None


def record_repo_home() -> Path | None:
    """Pin `coordinator.repo_home` to the census result when unset; a set value is never overwritten.
    Returns the pinned or already-recorded home, None when neither exists. Best-effort on write."""
    recorded = _recorded_repo_home()
    if recorded:
        return Path(recorded)
    found = census_repo_home()
    if found is None:
        return None
    try:
        import _registry_write

        _registry_write.machine_local_set(REPO_HOME_KEY, str(found))
    except Exception:
        # Best-effort: an unwritable registry leaves the key unset; workspace_dir still censuses.
        pass
    return found


def workspace_dir() -> Path:
    """The recorded repo home, else the census of real `repos.*` checkouts, else the user home."""
    recorded = _recorded_repo_home()
    if recorded:
        return Path(recorded)
    return census_repo_home() or Path.home()


def _overlaps(a, b) -> bool:
    return _gem_home._under(a, b) or _gem_home._under(b, a)


def _inside_checkout(root: Path) -> str | None:
    """`_gem_home.inside_checkout` for the root: a strict `.git` ancestor or a `repos.*` checkout
    (a root holding `.git`) containing it refuses; a `repos.*` root equal to the root (its own
    registration) or one that is not a checkout (a drive root) does not."""
    target = _gem_home._norm(root)
    cur = Path(os.path.realpath(str(root)))
    for anc in cur.parents:
        if (anc / ".git").exists():
            return str(anc)
    for repo in _gem_home._repo_roots():
        r = _gem_home._norm(repo)
        if target != r and target.startswith(r.rstrip(os.sep) + os.sep) and _gem_home._is_checkout(repo):
            return repo
    return None


def resolve_root() -> Path:
    configured = _engine_root._registry_value(_engine_root._settings_home_registry_dir(), KEY)
    if configured:
        root = Path(configured)
    else:
        root = workspace_dir() / DEFAULT_DIRNAME
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


def _strip_repos_fence(existing: str) -> str:
    """Remove a legacy generated-repos fence (markers and everything between); text outside it is
    untouched, and a text without a complete fence comes back as is. The registry is per-box, so it
    never belongs in the committed CLAUDE.md."""
    a = existing.find(BEGIN)
    b = existing.find(END, a + 1) if a >= 0 else -1
    if a < 0 or b < 0:
        return existing
    before, after = existing[:a], existing[b + len(END):]
    if not after.strip():
        return before.rstrip("\n") + "\n"
    return before + after.lstrip("\n")


_SEED_IDENTITY = ("-c", "user.name=general-work-root", "-c", "user.email=general-work-root@localhost")


def _git(
    root: Path,
    *args: str,
    pre: tuple[str, ...] = (),
    stdin: bytes | None = None,
    timeout: float = 30,
    env: dict[str, str] | None = None,
):
    """Run git in `root`, feeding `stdin` when given; None when git is missing, fails to spawn or
    times out, so callers stay non-fatal."""
    try:
        return subprocess.run(
            ["git", *pre, "-C", str(root), *args],
            capture_output=True,
            input=stdin,
            check=False,
            timeout=timeout,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _clone(root: Path, remote: str) -> bool:
    """Clone `remote` into the existing directory `root`, never prompting and bounded by
    `CLONE_TIMEOUT`; True on success. A failed or timed-out clone's partial `.git` is removed so the
    caller can init."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    res = _git(root, "clone", "-q", "--", remote, ".", timeout=CLONE_TIMEOUT, env=env)
    if res is not None and res.returncode == 0:
        return True
    shutil.rmtree(root / ".git", ignore_errors=True)
    return False


def _git_init(root: Path) -> None:
    """Clone `coordinator.general_work_remote` into the root when it is set, else (or when the clone
    fails) `git init` it, once; an existing `.git` is never touched, and a missing or failing git
    binary leaves the root untracked (a later `ensure` retries)."""
    if (root / ".git").exists():
        return
    remote = _engine_root._registry_value(_engine_root._settings_home_registry_dir(), REMOTE_KEY)
    if remote and _clone(root, remote):
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


def _commit_seed(root: Path, paths: list[str], message: str = "general-work root: seed coordinator state tree") -> None:
    """Stage and commit exactly `paths`, each named explicitly, skipping any path git reports as
    ignored or excluded; a no-op when none differs from HEAD. Supplies a fallback identity only
    when the box has none."""
    if not paths:
        return
    # One batched check-ignore (exit 0 = some ignored, 1 = none, >1 = failure); -z keeps names verbatim.
    res = _git(root, "check-ignore", "--stdin", "-z", stdin="\0".join(paths).encode("utf-8", "surrogateescape") + b"\0")
    if res is None or res.returncode > 1:
        return
    ignored = {p.decode("utf-8", "surrogateescape") for p in res.stdout.split(b"\0") if p}
    use = [rel for rel in paths if rel not in ignored]
    if not use:
        return
    _git(root, "add", "--", *use)
    dirty = _git(root, "status", "--porcelain", "--", *use)
    if dirty is None or not dirty.stdout.strip():
        return
    ident = _git(root, "config", "user.email")
    pre = () if ident is not None and ident.returncode == 0 and ident.stdout.strip() else _SEED_IDENTITY
    _git(root, "commit", "-q", "-m", message, "--", *use, pre=pre)


def ensure_root(template: Path | None = None) -> Path:
    """Create the root, git-init it when it has no `.git`, pin `coordinator.general_work_root` and
    `repos.general_work` when unset, converge the full coordinator-repo tree (the canonical-structure
    eager `state/` dirs, `docs/plans`, `archive/`, `tasks/`, `coordinator.local.md`, the canonical
    `.gitignore` block, `state/orientation_cache.md`) and CLAUDE.md when absent, retire a `## No ceremony here` section,
    strip a legacy generated-repos fence from CLAUDE.md (committed alone), put an unborn HEAD on
    `main`, and commit only those seed paths by explicit pathspec (excluded or ignored paths are
    skipped, never forced). The per-box repo list is never written: CLAUDE.md points at the
    machine-local registry. A repeat call with unchanged content adds no commit; best-effort, never
    raises on git or registry failure."""
    root = resolve_root()
    root.mkdir(parents=True, exist_ok=True)
    _git_init(root)
    _pin_identity(root)
    seed = root / "CLAUDE.md"
    src = template or _TEMPLATE
    tpl_text = src.read_text(encoding="utf-8") if src.is_file() else None
    # A missing template skips CLAUDE.md seeding silently; templates/general-work-home/home-CLAUDE.md must ship.
    if seed.exists():
        on_disk = seed.read_text(encoding="utf-8")
        stripped = _strip_repos_fence(on_disk)
        if stripped != on_disk:
            seed.write_text(stripped, encoding="utf-8", newline="\n")
            tracked = _git(root, "ls-files", "--error-unmatch", "--", "CLAUDE.md")
            if tracked is not None and tracked.returncode == 0:
                _commit_seed(root, ["CLAUDE.md"], "general-work root: drop per-box repos fence from CLAUDE.md")
        current = stripped
        if tpl_text is not None:
            current = _retire_no_ceremony(current, tpl_text)
    elif tpl_text is not None:
        current = tpl_text
    else:
        current = None
    if current is not None and (not seed.exists() or current != seed.read_text(encoding="utf-8")):
        seed.write_text(current, encoding="utf-8", newline="\n")
    paths = _seed_tree(root)
    _move_unborn_to_main(root)
    _commit_seed(root, paths)
    return root
