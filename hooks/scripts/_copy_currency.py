"""
_copy_currency -- three-state verdict contract for the copies a session runs.

One question per verdict: is this copy current, drifted, or unknown, and why.
Legs build `CopyVerdict`s, run inside `run_leg`, and `render_copies_lines`
prints the pinned `Copies:` banner. Stdlib-only; no spawns.

Invariants:
    - `current` requires non-empty evidence; `could-not-check` requires a reason.
    - `run_leg` converts any exception into could-not-check, never current.
    - A `drift` remedy is a confirmed-reachable command or the literal
      `no local remedy -- <owner> publish`; never `setup.py`.
    - File completeness joins the publisher's expected-manifest (`MANIFEST_RELPATH`)
      (`{"schema": 1, "source_head": .., "paths": {posix: blob_sha1}}`) against the
      mirror checkout's own `.git/index`, parsed in-process: a missing, mismatched or
      size-dirty path is drift (symlink and gitlink entries skip the size compare). No
      manifest, an unparseable one, or an index this parser cannot read (v4, split-index,
      sparse-index, non-sha1) is could-not-check, never current. A same-size working-tree
      edit is invisible to this check.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

CURRENT = "current"
DRIFT = "drift"
COULD_NOT_CHECK = "could-not-check"
STATES = (CURRENT, DRIFT, COULD_NOT_CHECK)

CURRENCY = "currency"
COMPLETENESS = "completeness"
AXES = (CURRENCY, COMPLETENESS)

NO_MANIFEST_REASON = "no expected-manifest emitted"
MANIFEST_RELPATH = ".coordinator/expected-manifest.json"
_DRIFT_NAMES_SHOWN = 5

ENGINE_CONSUMED_SYMBOLS = ("coordinator_core.warm.skew.publish_lag",)


def no_local_remedy(owner: str) -> str:
    """The only admissible remedy for a drift no command on this box can fix."""
    return f"no local remedy — {owner} publish"


@dataclass(frozen=True)
class CopyVerdict:
    """One copy, one axis, one state. Construction enforces the three rules."""

    copy: str
    axis: str
    state: str
    detail: str = ""
    evidence: str = ""
    remedy: str = ""

    def __post_init__(self) -> None:
        if self.axis not in AXES:
            raise ValueError(f"axis must be one of {AXES}, got {self.axis!r}")
        if self.state not in STATES:
            raise ValueError(f"state must be one of {STATES}, got {self.state!r}")
        if self.state == CURRENT and not self.evidence.strip():
            raise ValueError("a current verdict requires non-empty evidence")
        if self.state == COULD_NOT_CHECK and not self.detail.strip():
            raise ValueError("a could-not-check verdict requires a reason in detail")
        if self.state == DRIFT:
            if not self.remedy.strip():
                raise ValueError("a drift verdict requires a remedy")
            if "setup.py" in self.remedy:
                raise ValueError("a drift remedy must not name setup.py")


def could_not_check(copy: str, axis: str, reason: str, remedy: str = "") -> CopyVerdict:
    return CopyVerdict(copy, axis, COULD_NOT_CHECK, detail=reason, remedy=remedy)


def file_completeness_verdict(copy: str, owner: str = "claude-klabauter") -> CopyVerdict:
    """Completeness verdict for a copy whose publisher emits no manifest."""
    return could_not_check(
        copy, COMPLETENESS, NO_MANIFEST_REASON, remedy=no_local_remedy(owner)
    )


_UNSUPPORTED_EXTENSIONS = {b"link": "split-index", b"sdir": "sparse-index"}
_MODE_SYMLINK, _MODE_GITLINK = 0o120000, 0o160000
_UNREADABLE = "mirror git index unreadable"


def _parse_index(git_dir: Path) -> tuple[dict[str, tuple[str, int, int]] | None, str]:
    """({posix path: (blob sha1, size, mode)}, "") or (None, why this parser cannot read it)."""
    try:
        data = (git_dir / "index").read_bytes()
    except OSError:
        return None, _UNREADABLE
    if len(data) < 32 or data[:4] != b"DIRC":
        return None, _UNREADABLE
    if hashlib.sha1(data[:-20]).digest() != data[-20:]:
        return None, "mirror git index is not a sha1 index (non-sha1 object format or corrupt)"
    version, count = struct.unpack(">II", data[4:12])
    if version not in (2, 3):
        return None, f"mirror git index version {version} not parsed"
    entries: dict[str, tuple[str, int, int]] = {}
    pos = 12
    for _ in range(count):
        start = pos
        if pos + 62 > len(data):
            return None, _UNREADABLE
        mode = struct.unpack(">I", data[pos + 24 : pos + 28])[0]
        size = struct.unpack(">I", data[pos + 36 : pos + 40])[0]
        sha = data[pos + 40 : pos + 60].hex()
        flags = struct.unpack(">H", data[pos + 60 : pos + 62])[0]
        pos += 62
        if flags & 0x4000:
            pos += 2
        end = data.find(b"\0", pos)
        if end < 0:
            return None, _UNREADABLE
        path = data[pos:end].decode("utf-8", "surrogateescape")
        pos = start + ((end - start + 8) & ~7)
        if (flags >> 12) & 0x3 == 0:
            entries[path] = (sha, size, mode)
    limit = len(data) - 20
    while pos + 8 <= limit:
        sig = data[pos : pos + 4]
        if sig in _UNSUPPORTED_EXTENSIONS:
            return None, f"mirror git index uses {_UNSUPPORTED_EXTENSIONS[sig]}, not parsed"
        pos += 8 + struct.unpack(">I", data[pos + 4 : pos + 8])[0]
    return entries, ""


def read_index_entries(git_dir: Path) -> dict[str, tuple[str, int]] | None:
    """{posix path: (blob sha1, size)} from a version 2 or 3 sha1 `index`; None if unreadable.

    Version 4 path-prefix compression, split-index and sparse-index are not parsed. Stage-nonzero
    (conflicted) entries are skipped, so a conflicted path reads as missing.
    """
    entries, _ = _parse_index(git_dir)
    return None if entries is None else {p: (e[0], e[1]) for p, e in entries.items()}


def _git_dir(root: Path) -> Path | None:
    dot = root / ".git"
    if dot.is_dir():
        return dot
    try:
        text = dot.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    target = Path(text[len("gitdir:") :].strip())
    return target if target.is_absolute() else (root / target)


def _names(paths: list[str]) -> str:
    shown = ", ".join(sorted(paths)[:_DRIFT_NAMES_SHOWN])
    more = len(paths) - _DRIFT_NAMES_SHOWN
    return shown + (f" (+{more} more)" if more > 0 else "")


def manifest_completeness_verdict(
    copy: str, mirror_root: str | Path, owner: str = "claude-klabauter"
) -> CopyVerdict:
    """Completeness of a mirror checkout against its publisher's expected-manifest."""
    root = Path(mirror_root)
    try:
        manifest = json.loads((root / MANIFEST_RELPATH).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return file_completeness_verdict(copy, owner)
    except (OSError, ValueError) as exc:
        return could_not_check(copy, COMPLETENESS, f"expected-manifest unreadable: {exc}")
    if not isinstance(manifest, dict):
        manifest = {}
    paths = manifest.get("paths")
    if manifest.get("schema") != 1 or not isinstance(paths, dict) or not paths:
        return could_not_check(copy, COMPLETENESS, "expected-manifest is not schema 1 with paths")
    git_dir = _git_dir(root)
    entries, why = _parse_index(git_dir) if git_dir else (None, _UNREADABLE)
    if entries is None:
        return could_not_check(copy, COMPLETENESS, why)
    missing, mismatched, dirty = [], [], []
    for path, blob in paths.items():
        entry = entries.get(path)
        if entry is None:
            missing.append(path)
        elif entry[0] != blob:
            mismatched.append(path)
        else:
            try:
                st = os.lstat(root / path)
                if entry[2] not in (_MODE_SYMLINK, _MODE_GITLINK) and st.st_size != entry[1]:
                    dirty.append(path)
            except OSError:
                missing.append(path)
    head = str(manifest.get("source_head") or "")[:10]
    if not (missing or mismatched or dirty):
        return CopyVerdict(
            copy,
            COMPLETENESS,
            CURRENT,
            evidence=f"{len(paths)} manifest paths match the mirror's git index, sizes agree (source {head})",
        )
    parts = [
        f"{label} {len(group)}: {_names(group)}"
        for label, group in (("missing", missing), ("mismatched", mismatched), ("dirty", dirty))
        if group
    ]
    return CopyVerdict(
        copy,
        COMPLETENESS,
        DRIFT,
        detail=f"against manifest source {head}: " + "; ".join(parts),
        remedy=no_local_remedy(owner),
    )


def run_leg(copy: str, axis: str, leg: Callable[[], CopyVerdict]) -> CopyVerdict:
    """Run a leg; any exception or non-verdict return becomes could-not-check."""
    try:
        verdict = leg()
    except Exception as exc:  # noqa: BLE001 -- the contract is to never raise
        return could_not_check(copy, axis, f"leg raised {type(exc).__name__}: {exc}")
    if not isinstance(verdict, CopyVerdict):
        return could_not_check(copy, axis, "leg returned no CopyVerdict")
    return verdict


def resolve_engine_symbol(
    symbol: str, engine_root: str | Path | None
) -> tuple[Callable | None, str]:
    """Resolve a dotted engine symbol under engine_root.

    Returns (callable, "") or (None, reason naming the symbol). The module is
    loaded by file path under a private name so the resolved root is the only
    source and sys.modules is not polluted.
    """
    if not engine_root:
        return None, f"{symbol}: no engine root resolved"
    module_path, _, attr = symbol.rpartition(".")
    if not module_path:
        return None, f"{symbol}: not a dotted symbol"
    root = Path(engine_root)
    parts = module_path.split(".")
    candidate = root.joinpath(*parts).with_suffix(".py")
    if not candidate.is_file():
        return None, f"{symbol}: module file absent under engine root"
    name = "_copy_currency_engine_" + "_".join(parts)
    try:
        spec = importlib.util.spec_from_file_location(name, candidate)
        if spec is None or spec.loader is None:
            return None, f"{symbol}: module not loadable"
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(name, None)
    except Exception as exc:  # noqa: BLE001
        return None, f"{symbol}: import failed ({type(exc).__name__}: {exc})"
    fn = getattr(module, attr, None)
    if not callable(fn):
        return None, f"{symbol}: symbol does not resolve"
    return fn, ""


def _detail_line(v: CopyVerdict) -> str:
    detail = f"{COULD_NOT_CHECK} ({v.detail})" if v.state == COULD_NOT_CHECK else v.detail
    text = f"   {v.copy} {v.axis}: {detail}"
    if v.remedy:
        text += f" — remedy: {v.remedy}"
    return text


def _cell(verdicts: Iterable[CopyVerdict], copy: str, axis: str) -> str:
    for v in verdicts:
        if v.copy == copy and v.axis == axis:
            return v.state
    return COULD_NOT_CHECK


def render_copies_lines(verdicts: Iterable[CopyVerdict]) -> list[str]:
    """Pinned `Copies:` banner: one summary line, then a detail line per non-current verdict.

    A (copy, axis) cell with no verdict renders could-not-check, never current.
    """
    vs = list(verdicts)
    head = (
        "── Copies: "
        f"engine-mirror currency={_cell(vs, 'engine-mirror', CURRENCY)} "
        f"completeness={_cell(vs, 'engine-mirror', COMPLETENESS)}; "
        f"plugin-mirror currency={_cell(vs, 'plugin-mirror', CURRENCY)} "
        f"completeness={_cell(vs, 'plugin-mirror', COMPLETENESS)}; "
        f"capability-index currency={_cell(vs, 'capability-index', CURRENCY)}"
    )
    lines = [head]
    for v in vs:
        if v.state != CURRENT:
            lines.append(_detail_line(v))
    return lines
