"""Daily drift check: refresh `<settings-home>/bin/` files whose source is this
plugin's `templates/bin/`, when the installed copy has fallen behind.

WHY THIS EXISTS. `<settings-home>/bin/` is written at INSTALL time. Between
installs it is a snapshot, so a template that gains a feature ships to nobody
until an operator re-runs the installer on that machine — a source-vs-install lag
no consumer can see and none can fix from their side. Observed live: a new
`machine-local` verb landed in the template, and a downstream consumer found the
installed impl had no such verb — on the very machine that authored it. The
consumer's capability-probe fallback held, which is exactly why nothing surfaced.

COST. The steady-state path is ONE `os.stat` of a stamp file. The real comparison
runs at most once per `_INTERVAL_SECONDS` per machine, and copies only files that
actually differ. This is deliberately a daily check and not a per-session one: the
thing it watches changes when someone edits a template, not when a session starts,
and this machine boots sessions by the dozen.

NEGATIVE-SPEC — this never CREATES a file in `bin/`. It refreshes only names that
are already installed there. Seeding the family, pruning orphans, and the bin
manifest belong to the install substrate; a hook that added names would fight that
manifest and silently resurrect what the installer just pruned. Falling behind and
being absent are different failures, and only the first one is this module's.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

_INTERVAL_SECONDS = 24 * 60 * 60

_STAMP_BASENAME = ".impl-drift-checked"

# `set "_py=<absolute interpreter path>"` — the line the Windows installer bakes
# over the `__PYTHON_BIN__` token. Normalised away before comparing so a BAKED
# install never reads as drifted against its own unbaked template (see
# _normalise_for_compare).
_BAKED_PY_LINE = re.compile(r'^set "_py=.*"$', re.MULTILINE)

_TOKEN_PY_LINE = 'set "_py=__PYTHON_BIN__"'


def _templates_bin() -> Path:
    """This plugin's `templates/bin/` — resolved from THIS file, never from cwd.

    `<plugin>/hooks/scripts/_bin_impl_drift.py` → `<plugin>/templates/bin`. Anchoring
    on `__file__` means the refresh always reads the tree that is actually running,
    which is the correct source under both install shapes (a DoE dev clone resolved
    via `--plugin-dir`, and the OSS plugin root).
    """
    return Path(__file__).resolve().parents[2] / "templates" / "bin"


def _normalise_for_compare(text: str) -> str:
    """Collapse the differences an INSTALL is allowed to introduce.

    Only one exists: the Windows installer substitutes `__PYTHON_BIN__` with an
    absolute interpreter path. Comparing raw bytes would read every correctly-baked
    `.cmd` as drifted, and refreshing it would UNBAKE it — this module would then
    undo the install-time optimisation it is meant to protect, once a day, forever.

    Line endings are normalised too: `.cmd` files are written CRLF on Windows and
    the template is stored LF, which is a checkout artifact and not drift. Every CR
    is stripped rather than only the CRLF pair — a file that has been through both
    a CRLF-translating write and a CRLF-checkout carries `\\r\\r\\n`, and a
    pair-only replacement leaves a stray CR that defeats the `$` anchor below,
    which is exactly how a baked shim reads as drifted.
    """
    text = text.replace("\r", "")
    return _BAKED_PY_LINE.sub(_TOKEN_PY_LINE, text)


def _differs(src: Path, dst: Path) -> bool:
    try:
        src_text = src.read_text(encoding="utf-8")
        dst_text = dst.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Unreadable or non-text: not something this module can reason about, so
        # it is not something it should overwrite.
        return False
    return _normalise_for_compare(src_text) != _normalise_for_compare(dst_text)


def _copy_atomic(src: Path, dst: Path) -> bool:
    """Replace dst's CONTENT with src's, preserving dst's mode; True on success.

    Atomic because a dozen live sessions share this install surface and any of them
    may invoke `machine-local` mid-write. `os.replace` gives every reader either the
    old file or the new one, never a truncated interpreter script.

    The mode carry-over is load-bearing, not tidiness. `shutil.copyfile` writes
    content only, so the temp file is born at the umask default — no execute bit.
    Replacing an installed `bin/` entry with it would strip the execute bit from
    `machine-local` and `_machine_local.py` (both tracked 100755, both invoked
    directly off PATH via their shebang), so this sweep would break the very
    invocation path it exists to keep working, on the first refresh, on every POSIX
    machine.

    dst's mode is copied, NOT src's: the installer sets each file's execute bit
    deliberately and per-file (its `exec_bit` argument), so the installed file is
    the authority on what the mode should be. src's mode is a property of how the
    plugin tree happened to be checked out, which is not the same question.
    """
    tmp = dst.with_name(f"{dst.name}.{os.getpid()}.tmp")
    try:
        mode = dst.stat().st_mode
        shutil.copyfile(src, tmp)
        os.chmod(tmp, mode)
        os.replace(tmp, dst)
        return True
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def _claim_interval(stamp: Path, now: float) -> bool:
    """True if this process owns this interval's check.

    The stamp is written BEFORE the work, not after: a dozen sessions booting
    together would otherwise all see a stale stamp and all do the same scan. The
    trade is that a crash mid-refresh skips one interval — acceptable for a
    once-a-day freshness sweep, where the failure mode is 'still stale tomorrow',
    not data loss.
    """
    try:
        if now - stamp.stat().st_mtime < _INTERVAL_SECONDS:
            return False
    except OSError:
        pass  # absent or unreadable → treat as due

    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        tmp = stamp.with_name(f"{stamp.name}.{os.getpid()}.tmp")
        tmp.write_text(f"{now}\n", encoding="utf-8")
        os.replace(tmp, stamp)
    except OSError:
        return False  # read-only settings home: never block the session
    return True


def check_and_refresh(bin_dir: Path, now: float | None = None) -> str | None:
    """Refresh drifted `bin/` files at most once per interval; return a banner or None.

    Returns None on the overwhelmingly common path (checked recently, or nothing
    drifted) so the caller emits nothing. Any failure is silent by design: this is a
    freshness convenience, and a session must never fail to start because a refresh
    could not run.
    """
    now = time.time() if now is None else now
    if not _claim_interval(bin_dir / _STAMP_BASENAME, now):
        return None

    src_dir = _templates_bin()
    if not src_dir.is_dir():
        return None

    refreshed = []
    for src in sorted(src_dir.iterdir()):
        if not src.is_file():
            continue
        dst = bin_dir / src.name
        # Refresh-only, never seed — see this module's negative-spec.
        if not dst.is_file():
            continue
        if _differs(src, dst) and _copy_atomic(src, dst):
            refreshed.append(src.name)

    if not refreshed:
        return None
    return (
        f"── Refreshed {len(refreshed)} stale coordinator bin file(s) from this "
        f"plugin's templates: {', '.join(refreshed)} ──"
    )
