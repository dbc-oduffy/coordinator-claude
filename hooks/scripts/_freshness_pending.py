"""_freshness_pending -- repo-level pending-freshness transport shared by the Stop producer and boot readers.

Stdlib only. Three entry points: `read_pending(repo_root)` (no lock, no mutation, no probing),
`reserve_generation(repo_root)` (a persisted monotonic token, taken before a probe starts) and
`write_pending(repo_root, observation)` (merge explicit per-signal results). The transport owns
serialization and location only; thresholds, scheduling and remediation stay with the probes.

State lives in `<session hub>/freshness-pending.json`, a FILE beside the per-session directories, so
session teardown (which removes session directories) never removes it. The hub is the one resolved
from the git COMMON dir: worktrees of one repo share it, unrelated repos never do.

Ordering: generations are allocated under the lock at probe START and compared per worktree and
signal, never by wall clock; an older slow child cannot overwrite a newer result. A result is
`due`, `clean` or `unknown`; only `due`/`clean` are stored, `unknown` (probe error, HEAD-suppressed
drift) changes nothing, so an error never clears pending state and an empty due list is not clean.

Locking: an OS advisory byte lock on `freshness-pending.lock` (`msvcrt` / `fcntl.flock`). The OS
releases it when the owner dies, so an abandoned owner never disables later writes, and a live owner
is never stolen from: contention past `LOCK_TIMEOUT_S` returns an unavailable result.

Legacy `<hub>/<session>/freshness-due.json` ({due, ts, head}, no repo field, trusted by containment
in this repo's hub) is read alongside the canonical record and kept byte-intact. A legacy signal
stays pending until a successful canonical observation of that signal with `ts >=` the legacy `ts`
covers that exact legacy observation; a changed legacy record is reconsidered.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, NamedTuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

SCHEMA_VERSION = 1
PENDING_NAME = "freshness-pending.json"
LOCK_NAME = "freshness-pending.lock"
LEGACY_MARKER_NAME = "freshness-due.json"
SIGNALS = ("update-docs", "distill")
RESULTS = ("due", "clean", "unknown")
LOCK_TIMEOUT_S = 2.0
_LOCK_POLL_S = 0.02
_MAX_BYTES = 256 * 1024
_MAX_LEGACY_DIRS = 1000
_MAX_HEAD_LEN = 128


class Reservation(NamedTuple):
    """`generation` is an int token, or None with `reason` naming why none could be issued."""

    generation: int | None
    reason: str = ""

    @property
    def available(self) -> bool:
        return self.generation is not None


class WriteOutcome(NamedTuple):
    ok: bool
    reason: str


def empty_pending() -> dict:
    return {"due": [], "ts": None, "head": "", "generation": 0, "sources": []}


# --- location and identity --------------------------------------------------------------------


def _locate(repo_root: str) -> tuple[Path, str] | None:
    """(hub dir, canonical repo identity) for a repo root, or None when the common dir is unresolvable."""
    from _git_common_dir import resolve_git_common_dir
    from _session_hub_path import hub_for_common

    common = resolve_git_common_dir(str(repo_root))
    if not common:
        return None
    return hub_for_common(Path(common)), os.path.normcase(os.path.realpath(common))


def worktree_identity(repo_root: str) -> str:
    """Canonical identity of one worktree checkout."""
    return os.path.normcase(os.path.realpath(str(repo_root)))


def _contained(path: Path, hub: Path) -> bool:
    try:
        if path.is_symlink():
            return False
        real_hub = os.path.normcase(os.path.realpath(hub))
        return os.path.normcase(os.path.realpath(path.parent)) == real_hub
    except OSError:
        return False


# --- validation -------------------------------------------------------------------------------


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _head(value: object) -> str:
    if isinstance(value, str) and len(value) <= _MAX_HEAD_LEN and value.isprintable():
        return value
    return ""


def _entry(raw: object) -> dict | None:
    if not isinstance(raw, dict) or raw.get("state") not in ("due", "clean"):
        return None
    gen = raw.get("generation")
    if not isinstance(gen, int) or isinstance(gen, bool) or gen < 0 or not _finite(raw.get("ts")):
        return None
    return {"state": raw["state"], "generation": gen, "ts": float(raw["ts"]), "head": _head(raw.get("head"))}


def _clean_state(raw: dict) -> dict:
    """Keep only valid worktree/signal entries and legacy-coverage rows."""
    worktrees: dict = {}
    for wt, body in (raw.get("worktrees") or {}).items() if isinstance(raw.get("worktrees"), dict) else []:
        if not isinstance(wt, str) or not isinstance(body, dict) or not isinstance(body.get("signals"), dict):
            continue
        signals = {s: e for s, v in body["signals"].items() if s in SIGNALS and (e := _entry(v))}
        if signals:
            worktrees[wt] = {"signals": signals}
    covered: dict = {}
    for key, row in (raw.get("legacy_covered") or {}).items() if isinstance(raw.get("legacy_covered"), dict) else []:
        if isinstance(key, str) and isinstance(row, dict) and isinstance(row.get("fp"), str):
            sigs = [s for s in row.get("signals", []) if s in SIGNALS] if isinstance(row.get("signals"), list) else []
            covered[key] = {"fp": row["fp"], "signals": sorted(set(sigs))}
    gen = raw.get("generation")
    return {
        "schema_version": SCHEMA_VERSION,
        "repo": raw.get("repo"),
        "generation": gen if isinstance(gen, int) and not isinstance(gen, bool) and gen >= 0 else 0,
        "worktrees": worktrees,
        "legacy_covered": covered,
    }


def _load(path: Path, identity: str) -> tuple[dict | None, str]:
    """(state, status); status in ok / absent / corrupt / version / identity."""
    try:
        if not path.is_file():
            return None, "absent"
        if path.stat().st_size > _MAX_BYTES:
            return None, "corrupt"
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "corrupt"
    if not isinstance(raw, dict):
        return None, "corrupt"
    if raw.get("schema_version") != SCHEMA_VERSION:
        return None, "version"
    if raw.get("repo") != identity:
        return None, "identity"
    return _clean_state(raw), "ok"


def _read_legacy(hub: Path) -> dict[str, dict]:
    """Valid legacy records keyed by session-directory name; never follows a symlink out of the hub."""
    out: dict[str, dict] = {}
    try:
        with os.scandir(hub) as it:
            for n, ent in enumerate(it):
                if n >= _MAX_LEGACY_DIRS:
                    break
                if ent.name.startswith(".") or ent.is_symlink() or not ent.is_dir(follow_symlinks=False):
                    continue
                marker = Path(ent.path, LEGACY_MARKER_NAME)
                try:
                    if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > _MAX_BYTES:
                        continue
                    raw = json.loads(marker.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(raw, dict) or not isinstance(raw.get("due"), list) or not _finite(raw.get("ts")):
                    continue
                due = sorted({s for s in raw["due"] if isinstance(s, str) and s in SIGNALS})
                head = _head(raw.get("head"))
                fp = json.dumps({"due": due, "ts": float(raw["ts"]), "head": head}, sort_keys=True)
                out[ent.name] = {"due": due, "ts": float(raw["ts"]), "head": head, "fp": fp}
    except OSError:
        pass
    return out


# --- locked mutation --------------------------------------------------------------------------


class _Lock:
    """Bounded cross-process advisory lock; the OS drops it when the owner dies."""

    def __init__(self, path: Path, timeout: float) -> None:
        self._path, self._timeout, self._fd = path, timeout, -1

    def _try(self) -> bool:
        try:
            os.lseek(self._fd, 0, os.SEEK_SET)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def __enter__(self) -> "_Lock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self._path), os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.monotonic() + self._timeout
        while not self._try():
            if time.monotonic() >= deadline:
                os.close(self._fd)
                self._fd = -1
                raise TimeoutError("freshness-pending lock busy")
            time.sleep(_LOCK_POLL_S)
        return self

    def __exit__(self, *_exc: object) -> None:
        try:
            os.lseek(self._fd, 0, os.SEEK_SET)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            os.close(self._fd)


def _atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _mutate(repo_root: str, fn: Callable[[dict, Path], tuple[dict, Any]]) -> tuple[Any, str]:
    """Run `fn(state, hub) -> (new_state, result)` under the lock; (result, "") or (None, reason)."""
    where = _locate(repo_root)
    if where is None:
        return None, "hub-unresolvable"
    hub, identity = where
    path = hub / PENDING_NAME
    try:
        with _Lock(hub / LOCK_NAME, LOCK_TIMEOUT_S):
            if path.is_symlink() or (path.exists() and not _contained(path, hub)):
                return None, "state-path-escapes-hub"
            state, status = _load(path, identity)
            if status in ("version", "identity"):
                return None, f"state-{status}"
            if status == "corrupt":
                try:
                    os.replace(path, path.with_name(f"{path.name}.corrupt-{uuid.uuid4().hex[:8]}"))
                except OSError:
                    return None, "state-corrupt-unmovable"
            if state is None:
                state = _clean_state({"repo": identity})
            state["repo"] = identity
            new_state, result = fn(state, hub)
            _atomic_write(path, new_state)
            return result, ""
    except TimeoutError:
        return None, "lock-busy"
    except OSError as exc:
        return None, f"io-error:{type(exc).__name__}"


def reserve_generation(repo_root: str) -> Reservation:
    """Persist and return the next monotonic generation; never clears or alters pending values."""

    def take(state: dict, _hub: Path) -> tuple[dict, int]:
        state["generation"] += 1
        return state, state["generation"]

    result, reason = _mutate(repo_root, take)
    return Reservation(result, "") if reason == "" else Reservation(None, reason)


def make_observation(repo_root: str, generation: int, results: dict, head: str, ts: float | None = None) -> dict:
    """Observation for `write_pending`: token, worktree identity, one result per allowlisted signal."""
    return {
        "generation": generation,
        "worktree": worktree_identity(repo_root),
        "head": head,
        "ts": time.time() if ts is None else ts,
        "results": {s: results.get(s, "unknown") for s in SIGNALS},
    }


def _valid_observation(obs: object) -> bool:
    return (
        isinstance(obs, dict)
        and isinstance(obs.get("generation"), int) and not isinstance(obs.get("generation"), bool)
        and obs["generation"] >= 0
        and isinstance(obs.get("worktree"), str) and bool(obs["worktree"])
        and _finite(obs.get("ts"))
        and isinstance(obs.get("results"), dict)
        and all(k in SIGNALS and v in RESULTS for k, v in obs["results"].items())
    )


def write_pending(repo_root: str, observation: dict) -> WriteOutcome:
    """Merge one observation: per worktree and signal, only a newer generation replaces a result."""
    if not _valid_observation(observation):
        return WriteOutcome(False, "observation-invalid")
    gen, ts, wt = observation["generation"], float(observation["ts"]), observation["worktree"]
    head = _head(observation.get("head"))
    successes = {s: r for s, r in observation["results"].items() if r in ("due", "clean")}

    def merge(state: dict, hub: Path) -> tuple[dict, bool]:
        signals = state["worktrees"].setdefault(wt, {"signals": {}})["signals"]
        for sig, result in successes.items():
            held = signals.get(sig)
            if held is None or held["generation"] <= gen:
                signals[sig] = {"state": result, "generation": gen, "ts": ts, "head": head}
        state["generation"] = max(state["generation"], gen)
        legacy = _read_legacy(hub)
        covered = {}
        for key, rec in legacy.items():
            row = state["legacy_covered"].get(key)
            sigs = set(row["signals"]) if row and row["fp"] == rec["fp"] else set()
            sigs |= {s for s in successes if s in rec["due"] and rec["ts"] <= ts}
            if sigs:
                covered[key] = {"fp": rec["fp"], "signals": sorted(sigs)}
        state["legacy_covered"] = covered
        return state, True

    done, reason = _mutate(repo_root, merge)
    return WriteOutcome(True, "written") if done else WriteOutcome(False, reason)


# --- reading ----------------------------------------------------------------------------------


def read_pending(repo_root: str) -> dict:
    """Validated union of pending signals plus newest-observation metadata; read-only, never raises.

    Keys: `due` (sorted allowlisted names), `ts` / `head` / `generation` of the newest contributing
    observation (None / "" / 0 when nothing contributes), `sources` ("canonical", "legacy").
    """
    try:
        where = _locate(repo_root)
        if where is None:
            return empty_pending()
        hub, identity = where
        state, status = _load(hub / PENDING_NAME, identity)
        if status == "ok" and not _contained(hub / PENDING_NAME, hub):
            state = None
        state = state or _clean_state({"repo": identity})
        due: set[str] = set()
        due_meta: list[tuple] = []
        all_meta: list[tuple] = []
        sources: set[str] = set()
        for body in state["worktrees"].values():
            for sig, e in body["signals"].items():
                meta = (e["ts"], e["generation"], e["head"])
                all_meta.append(meta)
                if e["state"] == "due":
                    due.add(sig)
                    due_meta.append(meta)
                    sources.add("canonical")
        for key, rec in _read_legacy(hub).items():
            row = state["legacy_covered"].get(key)
            done = set(row["signals"]) if row and row["fp"] == rec["fp"] else set()
            live = [s for s in rec["due"] if s not in done]
            if live:
                due.update(live)
                due_meta.append((rec["ts"], -1, rec["head"]))
                sources.add("legacy")
        pool = due_meta or all_meta
        if not pool:
            return {**empty_pending(), "generation": state["generation"]}
        ts, _g, head = max(pool)
        return {
            "due": sorted(due), "ts": ts, "head": head,
            "generation": state["generation"], "sources": sorted(sources),
        }
    except Exception:  # noqa: BLE001 -- a boot reader never raises
        return empty_pending()
