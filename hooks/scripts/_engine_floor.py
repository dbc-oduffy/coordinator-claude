"""Plugin-to-engine floor check: is an engine root's git HEAD behind the pin?

`check_engine_floor(engine_root)` compares the engine root's own git HEAD (read
by plain file reads, no subprocess) against the plugin-owned floor in
`coordinator/engine-floor.json`, a copy of the engine's `MIN_KNOWN_GOOD_SHA` that the
doctrine EM re-copies at each percolate. Both shas live in one space: claude-klabauter
commits. A `behind` verdict is reported, never refused: this module has no
refusal branch and callers treat it as a notice. Ancestry is read from a JSON
cache under the settings home; a cache hit spawns nothing. A miss runs one `git
merge-base --is-ancestor` per uncached (running sha, floor sha) pair
(`decide_ancestry`) and records the verdict through `record_ancestry`. The
`engine-floor-decide` CLI forces a re-decision of the same pair.

Contract: never raises. Anything unreadable is `indeterminate` with a cause,
and an indeterminate engine is never treated as behind.

Negative-spec: do not import coordinator_core, and do not use the engine's
"mirror-stamp" (the engine's Percolate-Source-Head trailer) as the
stamp: it is a sha the klabauter clone cannot run merge-base on.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple, Optional

STATE_CLEAN = "clean"
STATE_BEHIND = "behind"
STATE_INDETERMINATE = "indeterminate"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CACHE_NAME = "engine-floor-ancestry.json"
_CACHED_UNDECIDED = "undecided"
_UNDECIDED_CAUSE = "git merge-base could not decide; rerun engine-floor-decide"
_TIMEOUT_SECONDS = 30


class FloorVerdict(NamedTuple):
    """`state` is clean|behind|indeterminate; `floor`/`stamp` are shas or None;
    `cause` explains an indeterminate (or is "" otherwise)."""

    state: str
    floor: Optional[str]
    stamp: Optional[str]
    cause: str


def _floor_file() -> Path:
    return Path(__file__).resolve().parents[2] / "engine-floor.json"


def _read_floor() -> str:
    data = json.loads(_floor_file().read_text(encoding="utf-8"))
    sha = str(data["min_engine_sha"]).strip().lower()
    if not _SHA_RE.match(sha):
        raise ValueError("min_engine_sha is not a 40-hex sha")
    return sha


def _git_dir(engine_root: Path) -> Path:
    dot_git = engine_root / ".git"
    if dot_git.is_dir():
        return dot_git
    text = dot_git.read_text(encoding="utf-8").strip()
    if not text.startswith("gitdir:"):
        raise ValueError(".git file has no gitdir pointer")
    target = Path(text[len("gitdir:"):].strip())
    return target if target.is_absolute() else (engine_root / target).resolve()


def _common_dir(git_dir: Path) -> Path:
    pointer = git_dir / "commondir"
    if pointer.is_file():
        target = Path(pointer.read_text(encoding="utf-8").strip())
        return target if target.is_absolute() else (git_dir / target).resolve()
    return git_dir


def _read_head_sha(engine_root: Path) -> str:
    """The engine root's HEAD commit sha from plain file reads."""
    git_dir = _git_dir(engine_root)
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref:"):
        sha = head.lower()
        if not _SHA_RE.match(sha):
            raise ValueError("detached HEAD is not a 40-hex sha")
        return sha
    ref = head[len("ref:"):].strip()
    common = _common_dir(git_dir)
    for base in (git_dir, common):
        loose = base / ref
        if loose.is_file():
            sha = loose.read_text(encoding="utf-8").strip().lower()
            if _SHA_RE.match(sha):
                return sha
            raise ValueError("loose ref is not a 40-hex sha")
    packed = common / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            if not line or line[0] in "#^":
                continue
            sha, _, name = line.partition(" ")
            if name.strip() == ref and _SHA_RE.match(sha.lower()):
                return sha.lower()
    raise ValueError("HEAD ref %s not found in loose refs or packed-refs" % ref)


def _cache_path() -> Path:
    from _engine_root import _settings_home

    return _settings_home() / _CACHE_NAME


def _cache_load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _cache_store(path: Path, key: str, verdict: str) -> None:
    """Atomic update (temp file + os.replace): concurrent hook processes share
    the cache. A failed write is dropped; the next call just re-asks git."""
    tmp_name = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _cache_load(path)
        data[key] = verdict
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=_CACHE_NAME, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp_name, path)
        tmp_name = None
    except OSError:
        pass
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def record_ancestry(floor: str, stamp: str, verdict: str) -> None:
    """Persist an ancestry verdict (clean|behind|undecided) for (stamp, floor).
    Never raises; an invalid verdict is dropped."""
    try:
        if verdict not in (STATE_CLEAN, STATE_BEHIND, _CACHED_UNDECIDED):
            return
        _cache_store(_cache_path(), "%s:%s" % (stamp, floor), verdict)
    except Exception:  # noqa: BLE001 - the never-raise contract
        pass


def _git_env() -> dict:
    """The environment minus every GIT_* override, so `-C <root>` alone picks the repository."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def decide_ancestry(engine_root: str, floor: str, stamp: str) -> str:
    """Is `floor` an ancestor of `stamp`? clean (rc 0) | behind (rc 1) | undecided
    (any other rc, timeout or spawn failure). Spawns one `git merge-base`; never raises."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(engine_root), "merge-base", "--is-ancestor", floor, stamp],
            env=_git_env(),
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return _CACHED_UNDECIDED
    if proc.returncode == 0:
        return STATE_CLEAN
    if proc.returncode == 1:
        return STATE_BEHIND
    return _CACHED_UNDECIDED


def check_engine_floor(engine_root: str) -> FloorVerdict:
    """Classify `engine_root` against the plugin floor. Never raises."""
    floor = None
    stamp = None
    try:
        try:
            floor = _read_floor()
        except Exception as exc:  # noqa: BLE001 - floor unreadable is indeterminate
            return FloorVerdict(STATE_INDETERMINATE, None, None, "floor unreadable: %s" % exc)
        try:
            stamp = _read_head_sha(Path(engine_root))
        except Exception as exc:  # noqa: BLE001 - unstamped engine is never behind
            return FloorVerdict(STATE_INDETERMINATE, floor, None, "stamp unreadable: %s" % exc)
        if stamp == floor:
            return FloorVerdict(STATE_CLEAN, floor, stamp, "")
        key = "%s:%s" % (stamp, floor)
        try:
            cache = _cache_path()
            cached = _cache_load(cache).get(key)
        except Exception:  # noqa: BLE001 - cache trouble is a miss
            cached = None
        if cached in (STATE_CLEAN, STATE_BEHIND):
            return FloorVerdict(cached, floor, stamp, "")
        if cached == _CACHED_UNDECIDED:
            return FloorVerdict(STATE_INDETERMINATE, floor, stamp, _UNDECIDED_CAUSE)
        verdict = decide_ancestry(engine_root, floor, stamp)
        record_ancestry(floor, stamp, verdict)
        if verdict in (STATE_CLEAN, STATE_BEHIND):
            return FloorVerdict(verdict, floor, stamp, "")
        return FloorVerdict(STATE_INDETERMINATE, floor, stamp, _UNDECIDED_CAUSE)
    except Exception as exc:  # noqa: BLE001 - the never-raise contract
        return FloorVerdict(STATE_INDETERMINATE, floor, stamp, "unexpected: %s" % exc)
