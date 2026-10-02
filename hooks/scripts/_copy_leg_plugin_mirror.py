"""
_copy_leg_plugin_mirror -- plugin-mirror leg of the Copies line.

Two verdicts for the one copy: currency (doctrine source vs the published plugin mirror,
anchored on commit time because no source sha is stamped) and completeness. Completeness
is `drift` when hooks.json registration parity finds a defect, else the shared constant
`could-not-check (no expected-manifest emitted)`; parity never makes it `current`.

Invariants:
    - The source is the `.content-root` pointer target, and only when `.coordinator-dev-repo`
      is present there; the registry's source-repo key is never read (it names the mirror on cloud).
    - A mirror that is unresolvable or equals the source is could-not-check on both axes.
    - The only rename source is the source's declared `basename_rename` table; no name is
      inferred. A source registration the mirror carries only in a form the table does
      not declare (an http-daemon registration) is unverifiable, never drift.
    - Reads no manifest, allowlist or publish map. The leg spawns nothing; the only git
      work is the injectable `commit_times` provider (`git_commit_times`, refresh-only).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _copy_currency as cc  # noqa: E402

COPY = "plugin-mirror"
OWNER = "plugin"
SENTINEL = ".coordinator-dev-repo"
RENAME_TABLE_RELPATH = "setup/percolate-hooks/percolate-store.yaml"
SOURCE_PLUGIN_SUBDIR = "coordinator"
BOOTSTRAP_SCRIPT = "_hook_boot.py"

_NO_SOURCE = "no DoE source reachable via .content-root"
_NO_MIRROR = "no mirror distinct from source"
_ANCHOR_NOTE = "time-based anchor; no DoE sha is stamped on publish"
_HTTP_REASON = (
    "mirror registers this script in http-daemon form; "
    "the declared basename_rename table does not cover that transform"
)
_SCRIPT_RE = re.compile(r"hooks/scripts/([^/\\\s'\"]+)")


def _default_source_root() -> Path | None:
    from _author_root_paths import _content_root_pointer_paths

    for pointer in _content_root_pointer_paths():
        try:
            if pointer.is_file():
                text = pointer.read_text(encoding="utf-8").strip()
                if text:
                    return Path(text)
        except OSError:
            continue
    return None


def _default_mirror_plugin_root() -> Path:
    return Path(__file__).resolve().parents[2]


def source_plugin_root(source: Path) -> Path:
    return source / SOURCE_PLUGIN_SUBDIR


def git_commit_times(source: Path, mirror: Path) -> tuple[int, int] | None:
    """(source last published-path commit time, mirror last commit time); 2 spawns, refresh-only."""
    from _win_portability import no_console_creationflags

    def last(repo: Path, *tail: str) -> int | None:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--format=%ct", *tail],
            capture_output=True,
            text=True,
            timeout=10,
            **no_console_creationflags(),
        )
        text = out.stdout.strip()
        return int(text) if out.returncode == 0 and text.isdigit() else None

    src = last(source, "--", SOURCE_PLUGIN_SUBDIR)
    mir = last(mirror)
    return None if src is None or mir is None else (src, mir)


def load_basename_rename(source: Path) -> dict[str, str]:
    """The source's declared outbound basename_rename table as {src: dst}; raises when unreadable."""
    import yaml

    doc = yaml.safe_load((source / RENAME_TABLE_RELPATH).read_text(encoding="utf-8"))

    def find(node):
        if isinstance(node, dict):
            if "basename_rename" in node:
                return node["basename_rename"]
            for v in node.values():
                hit = find(v)
                if hit is not None:
                    return hit
        elif isinstance(node, list):
            for v in node:
                hit = find(v)
                if hit is not None:
                    return hit
        return None

    rows = find(doc)
    if not isinstance(rows, list):
        raise ValueError("basename_rename table absent")
    return {r["src"]: r["dst"] for r in rows if isinstance(r, dict) and "src" in r and "dst" in r}


def _registrations(hooks_json: Path) -> tuple[set[str], bool]:
    """(script basenames registered as command hooks, whether any http registration exists)."""
    data = json.loads(hooks_json.read_text(encoding="utf-8"))
    scripts: set[str] = set()
    has_http = False
    for groups in data.get("hooks", {}).values():
        for group in groups:
            for hook in group.get("hooks", []):
                if hook.get("type") == "http":
                    has_http = True
                    continue
                words = [str(hook.get("command", "")), *map(str, hook.get("args", []))]
                names = [n for w in words for n in _SCRIPT_RE.findall(w) if n != BOOTSTRAP_SCRIPT]
                if names:
                    scripts.add(names[0])
    return scripts, has_http


@dataclass(frozen=True)
class ParityResult:
    """Registration parity: `dropped` and `missing` are drift, `unverifiable` is could-not-check."""

    dropped: tuple[str, ...] = field(default_factory=tuple)
    missing: tuple[str, ...] = field(default_factory=tuple)
    unverifiable: tuple[str, ...] = field(default_factory=tuple)

    @property
    def drift(self) -> bool:
        return bool(self.dropped or self.missing)


def check_registration_parity(
    source: Path, mirror_plugin_root: Path, rename: dict[str, str] | None = None
) -> ParityResult:
    """(1) each source command registration is a mirror command registration after the declared
    rename; (2) each mirror command registration's script exists in the mirror."""
    table = load_basename_rename(source) if rename is None else rename
    src_scripts, _ = _registrations(source_plugin_root(source) / "hooks" / "hooks.json")
    mir_scripts, mir_http = _registrations(mirror_plugin_root / "hooks" / "hooks.json")
    dropped: list[str] = []
    unverifiable: list[str] = []
    for script in sorted(src_scripts):
        if table.get(script, script) in mir_scripts:
            continue
        (unverifiable if mir_http else dropped).append(script)
    missing = sorted(
        s for s in mir_scripts if not (mirror_plugin_root / "hooks" / "scripts" / s).is_file()
    )
    return ParityResult(tuple(dropped), tuple(missing), tuple(unverifiable))


def _both_unchecked(reason: str) -> list[cc.CopyVerdict]:
    return [
        cc.could_not_check(COPY, cc.CURRENCY, reason),
        cc.could_not_check(COPY, cc.COMPLETENESS, reason),
    ]


def _currency(source: Path, mirror: Path, commit_times) -> cc.CopyVerdict:
    times = commit_times(source, mirror)
    if times is None:
        return cc.could_not_check(COPY, cc.CURRENCY, f"commit times unavailable ({_ANCHOR_NOTE})")
    src_t, mir_t = times
    if src_t > mir_t:
        return cc.CopyVerdict(
            COPY,
            cc.CURRENCY,
            cc.DRIFT,
            detail=f"source moved {src_t - mir_t}s after last publish ({_ANCHOR_NOTE})",
            remedy=cc.no_local_remedy(OWNER),
        )
    return cc.CopyVerdict(
        COPY,
        cc.CURRENCY,
        cc.CURRENT,
        evidence=f"no source commit after last publish ({_ANCHOR_NOTE})",
    )


def _completeness(parity: ParityResult) -> cc.CopyVerdict:
    if not parity.drift:
        return cc.file_completeness_verdict(COPY, OWNER)
    parts = []
    if parity.dropped:
        parts.append("registration dropped from mirror: " + ", ".join(parity.dropped))
    if parity.missing:
        parts.append("mirror registers absent script: " + ", ".join(parity.missing))
    return cc.CopyVerdict(
        COPY, cc.COMPLETENESS, cc.DRIFT, detail="; ".join(parts), remedy=cc.no_local_remedy(OWNER)
    )


def check_plugin_mirror(
    source_root: Callable[[], Path | None] | str | Path | None = None,
    mirror_plugin_root: Callable[[], Path | None] | str | Path | None = None,
    publish_mirror: Callable[[], Path | None] | str | Path | None = None,
    commit_times: Callable[[Path, Path], tuple[int, int] | None] | None = None,
    rename: dict[str, str] | None = None,
) -> list[cc.CopyVerdict]:
    """[currency, completeness] verdicts; any argument left None resolves from the box.

    The mirror is the live plugin root unless that equals the source's plugin root, in which
    case `publish_mirror` is tried; neither distinct from the source is could-not-check.
    """

    def resolve(value, default):
        got = value() if callable(value) else value
        if value is None:
            got = default()
        return Path(got) if got else None

    source = resolve(source_root, _default_source_root)
    if source is None or not (source / SENTINEL).is_file():
        return _both_unchecked(_NO_SOURCE)
    src_plugin = source_plugin_root(source).resolve()
    mirror = resolve(mirror_plugin_root, _default_mirror_plugin_root)
    if mirror is None or mirror.resolve() == src_plugin:
        mirror = resolve(publish_mirror, lambda: None)
    if mirror is None or mirror.resolve() == src_plugin or mirror.resolve() == source.resolve():
        return _both_unchecked(_NO_MIRROR)
    currency = _currency(source, mirror, commit_times or git_commit_times)
    parity = check_registration_parity(source, mirror, rename)
    return [currency, _completeness(parity)]


def legs(**kwargs) -> list[cc.CopyVerdict]:
    """The legs as the banner calls them: each axis wrapped so it can never raise or render current unrun."""

    def axis(index: int, name: str) -> cc.CopyVerdict:
        return cc.run_leg(COPY, name, lambda: check_plugin_mirror(**kwargs)[index])

    return [axis(0, cc.CURRENCY), axis(1, cc.COMPLETENESS)]
