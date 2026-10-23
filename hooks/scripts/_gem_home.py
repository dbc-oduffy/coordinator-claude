"""Machine-local group-em home: the G-EM's spawn home, outside every repo checkout.

Resolves `coordinator.group_em_home` (default `<settings-home>/group-em`), refuses a
home that lands inside a git checkout or a `repos.*` root, seeds the home idempotently, moves a
default-path legacy home into place under a liveness guard, and reads the engine's live
box-holder record. Zero-spawn on the resolve path (registry TOML read directly); only
`ensure_home` spawns `git init`. Contract: gem-cockpit-contract.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import _engine_root

KEY = "coordinator.group_em_home"
# LEGACY_*: read-only fallback. LEGACY_KEY is read, never written; the LEGACY_DIRNAME dir is
# never created. Retirement: state/debt-backlog/2026-10-16-retire-general-work-home-fallback.yaml.
LEGACY_KEY = "coordinator.general_work_home"
DEFAULT_DIRNAME = "group-em"
LEGACY_DIRNAME = "general-work"
_TEMPLATE = Path(__file__).resolve().parent.parent.parent / "templates" / "group-em-home" / "home-CLAUDE.md"


class HomeRefused(Exception):
    """The configured home sits inside a checkout; `.checkout` names it."""

    def __init__(self, home: str, checkout: str):
        self.home = home
        self.checkout = checkout
        super().__init__(f"group-em home {home} is inside checkout {checkout}")


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
    # Walk the real path, not the normcased one, so a refusal names the checkout as spelled.
    cur = Path(os.path.realpath(str(path)))
    for anc in cur.parents:
        if (anc / ".git").exists():
            return str(anc)
    for root in _repo_roots():
        r = _norm(root)
        if target == r or target.startswith(r.rstrip(os.sep) + os.sep):
            return root
    return None


def _configured() -> str | None:
    reg = _engine_root._settings_home_registry_dir()
    return _engine_root._registry_value(reg, KEY) or _engine_root._registry_value(reg, LEGACY_KEY) or None


def resolve_home() -> Path:
    configured = _configured()
    if configured:
        home = Path(configured)
    else:
        base = _engine_root._settings_home()
        home = base / DEFAULT_DIRNAME
        if not home.exists() and (base / LEGACY_DIRNAME).exists():
            home = base / LEGACY_DIRNAME
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


def _under(path, root) -> bool:
    p, r = _norm(path), _norm(root)
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def _legacy_home_live(legacy: Path) -> bool:
    """True when anything runs in `legacy`. Fails closed: any error reads as live."""
    try:
        if _under(os.getcwd(), legacy):
            return True
        lib = str(Path(__file__).resolve().parents[2] / "bin" / "lib")
        if lib not in sys.path:
            sys.path.insert(0, lib)
        import session_registry

        for row in session_registry.read_rows():
            if row.cwd and session_registry.pid_alive(row.pid) and _under(row.cwd, legacy):
                return True
        root = gem_root()
        return bool(root and _under(root, legacy))
    except Exception:
        return True


def migrate_legacy_home() -> str:
    """Rename the default-path `<settings-home>/general-work` to `group-em` when safe.

    Returns one of moved, no-legacy, configured, both-present, live, busy, refused. Only the
    default-path legacy dir moves; a configured home is never touched, neither key is written,
    and an existing target is never merged or overwritten. Never raises."""
    try:
        if _configured():
            return "configured"
        base = _engine_root._settings_home()
        legacy, target = base / LEGACY_DIRNAME, base / DEFAULT_DIRNAME
        if not legacy.exists():
            return "no-legacy"
        if target.exists():
            return "both-present"
        if inside_checkout(target):
            return "refused"
        if _legacy_home_live(legacy):
            return "live"
        os.rename(legacy, target)
        return "moved"
    except OSError:
        return "busy"
    except Exception:
        return "live"


#: Machine-local runtime state the home never commits: memo-outbox sent copies and ledger,
#: subagent share. The home's history records its own state only, so these stay untracked.
_IGNORED = (".coordinator-local/",)


def _ensure_ignored(home: Path, entries: tuple[str, ...] = _IGNORED) -> None:
    """Append any missing `entries` line (default `_IGNORED`) to the home's `.gitignore`; never rewrites a line."""
    path = home / ".gitignore"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    missing = [entry for entry in entries if entry not in lines]
    if missing:
        path.write_text("\n".join([*lines, *missing]) + "\n", encoding="utf-8")


def ensure_home(template: Path | None = None, refresh: bool = False) -> Path:
    """Migrate a legacy home when safe, then create the home, `git init` it, add `state/`, ignore
    `.coordinator-local/`, seed CLAUDE.md when absent (or on refresh)."""
    migrate_legacy_home()
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
    _ensure_ignored(home)
    seed = home / "CLAUDE.md"
    src = template or _TEMPLATE
    # A missing template skips seeding silently; templates/group-em-home/home-CLAUDE.md must ship.
    # Its non-CLAUDE.md name keeps the template outside the CLAUDE.md write guard.
    # refresh redeploys the shipped template over a local edit; the template is the source of truth.
    if src.is_file() and (refresh or not seed.exists()):
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
