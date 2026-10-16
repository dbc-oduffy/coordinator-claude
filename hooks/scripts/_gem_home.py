"""Machine-local general-work home: the G-EM's spawn home, outside every repo checkout.

Resolves `coordinator.general_work_home` (default `<settings-home>/general-work`), refuses a
home that lands inside a git checkout or a `repos.*` root, seeds the home idempotently, and
reads the engine's live box-holder record. Zero-spawn on the resolve path (registry TOML read
directly); only `ensure_home` spawns `git init`. Contract: gem-cockpit-contract.md.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import _engine_root

KEY = "coordinator.general_work_home"
DEFAULT_DIRNAME = "general-work"
_TEMPLATE = Path(__file__).resolve().parent.parent.parent / "templates" / "general-work-home" / "home-CLAUDE.md"


class HomeRefused(Exception):
    """The configured home sits inside a checkout; `.checkout` names it."""

    def __init__(self, home: str, checkout: str):
        self.home = home
        self.checkout = checkout
        super().__init__(f"general-work home {home} is inside checkout {checkout}")


def _norm(p) -> str:
    return os.path.normcase(os.path.realpath(str(p)))


def _registry_layers() -> list[dict]:
    try:
        import tomllib
    except ImportError:
        # TRAP: no tomllib (Python < 3.11) silently disables the `repos.*` containment check
        # and ignores a configured home; only the `.git`-ancestor check still refuses.
        return []
    reg_dir = _engine_root._settings_home_registry_dir()
    layers = []
    for name in ("registry.local.toml", "registry.toml"):
        try:
            with (reg_dir / name).open("rb") as fh:
                layers.append(_engine_root._flatten_registry(tomllib.load(fh)))
        except (OSError, ValueError):
            continue
    return layers


def _repo_roots() -> list[str]:
    roots: list[str] = []
    for layer in _registry_layers():
        for k, v in layer.items():
            if k.startswith("repos.") and isinstance(v, str) and v:
                roots.append(v)
    return roots


def inside_checkout(path) -> str | None:
    """The checkout `path` lies in, else None: the first strict ancestor holding `.git`, or the
    first `repos.*` root equal to or containing it."""
    target = _norm(path)
    cur = Path(target)
    for anc in cur.parents:
        if (anc / ".git").exists():
            return str(anc)
    for root in _repo_roots():
        r = _norm(root)
        if target == r or target.startswith(r.rstrip(os.sep) + os.sep):
            return root
    return None


def resolve_home() -> Path:
    configured = _engine_root._registry_value(_engine_root._settings_home_registry_dir(), KEY)
    home = Path(configured) if configured else _engine_root._settings_home() / DEFAULT_DIRNAME
    hit = inside_checkout(home)
    if hit:
        raise HomeRefused(str(home), hit)
    return home


def is_home(cwd) -> bool:
    """True when `cwd` is the home or under it. A refused home is never a home."""
    try:
        home = _norm(resolve_home())
    except HomeRefused:
        return False
    c = _norm(cwd)
    return c == home or c.startswith(home.rstrip(os.sep) + os.sep)


def ensure_home(template: Path | None = None) -> Path:
    """Create the home, `git init` it, add `state/`, seed CLAUDE.md only when absent."""
    home = resolve_home()
    home.mkdir(parents=True, exist_ok=True)
    if not (home / ".git").exists():
        subprocess.run(
            ["git", "init", "-q", str(home)],
            check=True,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    (home / "state").mkdir(exist_ok=True)
    seed = home / "CLAUDE.md"
    src = template or _TEMPLATE
    # A missing template skips seeding silently; templates/general-work-home/home-CLAUDE.md must ship.
    # Its non-CLAUDE.md name keeps the template outside the CLAUDE.md write guard.
    if src.is_file() and not seed.exists():
        seed.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return home


def _nomination_module():
    try:
        root = _engine_root.resolve_claude_klabauter_root()
        if not root:
            return None
        _engine_root.place_engine_root_on_path(root)
        from coordinator_core.group_em import nomination

        return nomination
    except Exception:
        return None


def gem_holder() -> dict | None:
    """The engine's box holder record when live, else None. Never raises; writes nothing."""
    try:
        nom = _nomination_module()
        if nom is None:
            return None
        rec = nom.box_holder()
        if isinstance(rec, dict) and rec.get("live") is True:
            return rec
    except Exception:
        pass
    return None


def gem_root() -> str | None:
    rec = gem_holder()
    root = rec.get("repo_root") if rec else None
    return root if isinstance(root, str) and root else None
