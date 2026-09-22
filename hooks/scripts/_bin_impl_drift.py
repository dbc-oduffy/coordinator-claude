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
and this machine boots sessions by the dozen. A sweep that ends with a LIVE_MISSING
or MODE_UNREPAIRED finding outstanding is re-reported, not swallowed until
tomorrow: it rewinds the interval stamp so the next session booting at least
`_ATTENTION_RECHECK_SECONDS` later re-claims the interval and re-runs. That costs
one more ≤17-entry sweep per hour until the finding is repaired; a clean sweep is
unchanged.

NEGATIVE-SPEC — this never CREATES a file in `bin/`. It refreshes only names that
are already installed there. Seeding the family, pruning orphans, and the bin
manifest belong to the install substrate; a hook that added names would fight that
manifest and silently resurrect what the installer just pruned. Falling behind and
being absent are different failures, and only the first one is this module's.

NEGATIVE-SPEC — this never overwrites a COMPILED NATIVE IMAGE. A cut-over door
installs as `<name>.exe` on Windows and as the extensionless bare name on POSIX,
so a template name that ever collides with a cut-over name would otherwise
un-cut-over that door: a Mach-O/ELF/PE entry replaced by Python source, with the
door's execute bit carried over, so every caller that execs it directly gets a
file the loader cannot run. Name-only matching is what makes that reachable, and
the refusal is on the file's own bytes because those are the only honest answer.

NEGATIVE-SPEC — this module holds no exec-bit table of its own and never
infers one from a file's name, extension, or existing mode. `exec_bit` is
the engine's classification (`coordinator/lib/bin-templates-manifest.py`,
`BinTemplateEntry.exec_bit`), read fresh through `exec_bit_authority()` on
every call; a second, locally-maintained copy would drift from that table
exactly the way three same-named files (`machine-local`,
`_machine_local.py`, `claude-machine-local.ps1`) already drifted from each
other before the manifest existed — one is POSIX-executable-by-shebang, one
is a Python module never exec'd directly, one is a `.ps1` with no POSIX bit
at all, and a heuristic keyed on any of name/extension/current-mode gets at
least one of the three wrong.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

_INTERVAL_SECONDS = 24 * 60 * 60

# How soon an unrepaired ATTENTION finding gets re-reported. A sweep that ends
# with LIVE_MISSING or MODE_UNREPAIRED outstanding rewinds the interval
# stamp's mtime so the next session booting at least this long afterward
# re-claims the interval and re-runs the sweep, rather than waiting out the
# full daily cadence with the finding unreported until then. A sweep that
# ends clean leaves the stamp at `now`, which restores the daily cadence on
# its own.
_ATTENTION_RECHECK_SECONDS = 60 * 60

# No POSIX execute bit exists to lose on Windows — a module constant, not an
# inline `os.name` check, so C4's cross-platform twin has a seam to patch: an
# inline check can never reach the chmod on a Windows box, and patching
# `os.name` itself breaks `pathlib` for the rest of the test process.
_EXEC_BITS_EXIST = os.name != "nt"

_STAMP_BASENAME = ".impl-drift-checked"

# `set "_py=<absolute interpreter path>"` — the line the Windows installer bakes
# over the `__PYTHON_BIN__` token. Normalised away before comparing so a BAKED
# install never reads as drifted against its own unbaked template (see
# _normalise_for_compare).
_BAKED_PY_LINE = re.compile(r'^set "_py=.*"$', re.MULTILINE)

_TOKEN_PY_LINE = 'set "_py=__PYTHON_BIN__"'

# Leading bytes of every native-image format a door install can produce: Mach-O
# (both endiannesses plus the fat/universal header), ELF, and PE. Mirrors the
# engine's `coordinator_core.install.door_install.NATIVE_IMAGE_MAGIC`, pinned
# against it by test_bin_impl_drift; carried locally because this hook must run
# with no engine import at all (see `_engine_root`'s module docstring).
_NATIVE_IMAGE_MAGIC = (
    b"\xcf\xfa\xed\xfe",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xfe\xed\xfa\xce",
    b"\xca\xfe\xba\xbe",
    b"\x7fELF",
    b"MZ",
)


def _templates_bin() -> Path:
    """This plugin's `templates/bin/` — resolved from THIS file, never from cwd.

    `<plugin>/hooks/scripts/_bin_impl_drift.py` → `<plugin>/templates/bin`. Anchoring
    on `__file__` means the refresh always reads the tree that is actually running,
    which is the correct source under both install shapes (a dev clone resolved
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


def _is_native_image(path: Path) -> bool:
    """True iff `path` opens as a compiled native image; unreadable is False.

    Asks the file's own bytes, never its name: under settings-home a cut-over
    door is the extensionless bare name on POSIX and `<name>.exe` on Windows, so
    the name carries no information about which of the two shapes is on disk.
    Unreadable answers False because the copy that follows would fail on the same
    file anyway, and this predicate's job is to name one refusal, not to
    adjudicate every I/O failure.
    """
    try:
        with open(path, "rb") as fh:
            return fh.read(8).startswith(_NATIVE_IMAGE_MAGIC)
    except OSError:
        return False


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
    Replacing an installed `bin/` entry with it would silently drop dst's
    existing mode, so this sweep would corrupt whatever mode the installer set,
    on the first refresh, on every POSIX machine.

    dst's mode is copied, NOT src's: dst-mode preservation here keeps whatever
    mode the installer already set on disk, while `exec_bit_authority()` (this
    module) is the authority on what that mode SHOULD be — two different
    questions, not a contradiction. src's mode is a property of how the plugin
    tree happened to be checked out, which is neither.
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


def exec_bit_authority() -> dict[str, bool] | None:
    """The engine's `exec_bit` classification for every `templates/bin/` name, or
    `None` when no authority is available.

    Borrows the ONE table the engine already owns
    (`coordinator/lib/bin-templates-manifest.py`, `BinTemplateEntry.exec_bit`)
    rather than holding a second copy here — see this module's own
    negative-spec above for why a local copy would drift.

    `import _engine_root` (the module, not a bound name) so C4's monkeypatch
    of `_engine_root.resolve_claude_klabauter_root` reaches this call: `from
    _engine_root import resolve_claude_klabauter_root` would bind the name into this
    module at import time, and the None-path test would then resolve the
    real root instead of the patched one. This is the same call-through form
    `test_magic_matches_the_engine_that_writes_the_images` already uses
    (`coordinator/tests/test_bin_impl_drift.py:271`). The import sits inside
    this function, not at module top, because this module is loaded by
    `spec_from_file_location` with no `hooks/scripts` on `sys.path`; a
    top-level import would fail the whole module load, while an in-function
    one resolves from `sys.modules` once the test (or the SessionStart
    entrypoint, which inserts its own directory on `sys.path`) has already
    imported `_engine_root`. `_engine_root` is the doctrine repo's resolver, not
    `coordinator_core` — this module's own docstring's "no engine import at
    all" bans the engine package, and `sessionstart-bin-drift-refresh.py`
    already imports `_engine_root` beside it.

    Returns `None` — never a partial or a default — when the root does not
    resolve, the manifest file is absent, loading it raises, or
    `ALL_BIN_TEMPLATE_FILES` is missing or not iterable as
    `(name, _, exec_bit, _)`-shaped entries. `None` means "no authority
    available", and the POSIX exec-bit leg (C2) treats it as "do not touch
    any mode" — this sweep's standing fail-open posture.

    Not cached across calls: the sweep runs once a day, so a module-level
    cache would only matter to a process that called this twice.
    """
    try:
        import _engine_root

        root = _engine_root.resolve_claude_klabauter_root()
        if not root:
            return None

        manifest_path = Path(root) / "coordinator" / "lib" / "bin-templates-manifest.py"
        if not manifest_path.is_file():
            return None

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_doe_bin_templates_manifest", manifest_path
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        entries = getattr(module, "ALL_BIN_TEMPLATE_FILES", None)
        if not entries:
            return None
        return {entry.name: entry.exec_bit for entry in entries}
    except Exception:
        return None


def _live_missing(bin_dir: Path, template_names: list[str]) -> list[str]:
    """Template names the installer claims to have written into `bin/` that are
    no longer there. REPORTED, NEVER FIXED — see this module's refresh-only
    negative-spec above; a "missing" line one step from a chmod call is exactly
    the place a later reader adds the forbidden copy-from-template repair.

    "Missing" means the INSTALLER's claim, not the template list: the exec_bit
    manifest classifies what `templates/bin/` CONTAINS, not what the installer
    WRITES into `bin/`, and several template names (the launcher templates,
    the git-bash-fast-profile pair) are declared there but never installed by
    design. This reads `<bin>/.coordinator-bin-manifest.json` instead — the
    installer's own record of what it wrote (klabauter substrate.py
    `_write_bin_manifest` / `_read_bin_manifest`) — with the same tolerance
    `_read_bin_manifest` has: absent, unreadable, malformed JSON, a non-dict,
    or a non-list `names` all mean "no record", and no record SKIPS this class
    entirely, the same fail-open posture as `exec_bit_authority()` returning
    `None`. Never falls back to the exec_bit manifest or the template list.

    Does not depend on `exec_bit_authority()` and still runs on a box where the
    engine root does not resolve.
    """
    manifest_path = bin_dir / ".coordinator-bin-manifest.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    names = data.get("names")
    if not isinstance(names, list):
        return []
    recorded = {n for n in names if isinstance(n, str)}
    return [
        name
        for name in template_names
        if name in recorded and not (bin_dir / name).is_file()
    ]


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
    """Refresh drifted `bin/` files at most once per interval; return a banner, an
    ATTENTION report, both, or None.

    Returns None on the overwhelmingly common path (checked recently, or nothing
    drifted, and nothing needs an operator) so the caller emits nothing. Any
    failure is silent by design: this is a freshness convenience, and a session
    must never fail to start because a refresh could not run.

    Two things this pass finds drift it cannot repair itself, and reports rather
    than swallows: LIVE_MISSING (an entry the installer recorded writing into
    `bin/` that is no longer there) and MODE_UNREPAIRED (an execute bit the
    exec-bit leg could not restore). Both are REPORTED, NEVER FIXED — see this
    module's refresh-only negative-spec above; this pass never seeds `bin/` and
    never writes the installer's own record.
    """
    now = time.time() if now is None else now
    stamp = bin_dir / _STAMP_BASENAME
    if not _claim_interval(stamp, now):
        return None

    src_dir = _templates_bin()
    if not src_dir.is_dir():
        return None

    template_files = [src for src in sorted(src_dir.iterdir()) if src.is_file()]

    refreshed = []
    for src in template_files:
        dst = bin_dir / src.name
        # Refresh-only, never seed — see this module's negative-spec.
        if not dst.is_file():
            continue
        # Never un-cut-over a door — see this module's negative-spec.
        if _is_native_image(dst):
            continue
        if _differs(src, dst) and _copy_atomic(src, dst):
            refreshed.append(src.name)

    # POSIX exec-bit leg (C2): a separate pass over the same installed entries,
    # after the content pass. Content drift and exec-bit loss are independent
    # events; folding this into `_copy_atomic` would only ever fix a file that
    # happened to drift in content on the same day. Contained under one
    # `except Exception` so an unexpected failure here — an authority mapping
    # that misbehaves, a stat racing a delete — discards only this pass's
    # findings, never the refresh banner already computed above.
    mode_unrepaired: list[str] = []
    try:
        if _EXEC_BITS_EXIST and (authority := exec_bit_authority()) is not None:
            for src in template_files:
                if authority.get(src.name) is not True:
                    continue
                dst = bin_dir / src.name
                if not dst.is_file() or dst.is_symlink():
                    continue
                try:
                    mode = dst.stat().st_mode
                    if mode & 0o111 != 0o111:
                        os.chmod(dst, mode | 0o111)
                        if dst.stat().st_mode & 0o111 != 0o111:
                            mode_unrepaired.append(src.name)
                except OSError:
                    mode_unrepaired.append(src.name)
    except Exception:
        pass

    # LIVE_MISSING (C3): contained the same way, under its own `except
    # Exception`, so a bad install record drops only this class and never the
    # refresh banner or the exec-bit leg's findings.
    live_missing: list[str] = []
    try:
        live_missing = _live_missing(bin_dir, [src.name for src in template_files])
    except Exception:
        live_missing = []

    if live_missing or mode_unrepaired:
        # Delivery contract: re-reported until repaired, not once a day. The
        # stamp's mtime is rewound so the next session booting at least
        # `_ATTENTION_RECHECK_SECONDS` later re-claims the interval and
        # re-runs the sweep; a clean sweep leaves the stamp at `now`, which
        # restores the daily cadence on its own. Swallowed like every other
        # stamp failure — the worst case is today's once-a-day behaviour.
        try:
            rewound = now - _INTERVAL_SECONDS + _ATTENTION_RECHECK_SECONDS
            os.utime(stamp, (rewound, rewound))
        except OSError:
            pass

    lines = []
    if refreshed:
        lines.append(
            f"── Refreshed {len(refreshed)} stale coordinator bin file(s) from this "
            f"plugin's templates: {', '.join(refreshed)} ──"
        )

    if live_missing or mode_unrepaired:
        clauses = []
        if live_missing:
            clauses.append(f"missing from the live install: {', '.join(sorted(live_missing))}")
        if mode_unrepaired:
            clauses.append(f"execute bit not restored: {', '.join(sorted(mode_unrepaired))}")
        n = len(live_missing) + len(mode_unrepaired)
        lines.append(
            f"── Attention: {n} coordinator bin file(s) need an operator: "
            + "; ".join(clauses)
            + " — re-run the coordinator install (`/coordinator:install`) to restore; "
            "do not copy from templates/bin/ ──"
        )

    if not lines:
        return None
    return "\n".join(lines)
