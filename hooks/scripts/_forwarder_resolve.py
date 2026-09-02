"""Shared resolution of an installed settings-home CLI forwarder, plus the argv
form that actually launches whichever variant resolved.

Why this module exists: four SessionStart hooks (`sweep-boot.py`,
`handoff-segment-inject.py`, `pickup-autofire.py`, `mise-autofire.py`) each carried
their own copy of a probe that looked ONLY for the extensionless forwarder
(`<settings-home>/bin/<name>`), each justified by the same negative-spec -- "the
`.cmd` variant is just a shim that execs the extensionless forwarder, so resolving
it would add an indirection for nothing." That reasoning was sound for the
generation of forwarders it was written against, where the extensionless
naked-Python script was the real target on every platform.

It is no longer true. The native-forwarder generation (see
`<settings-home>/bin/_native-forwarder-manifest.json`) emits a compiled `.exe` per
name on Windows and does NOT leave an extensionless script beside it. Every one of
those four probes therefore returns None on Windows, and because all four consumers
are fail-open by design, they degrade in total silence -- no crash, no banner, no
exit-code change. The orientation-cache self-heal is the loudest case only because
it happens to record a failure row; the other three simply stop happening.

Negative-spec: does NOT resolve `.cmd`/`.bat`. Windows' `CreateProcess` -- what
`subprocess` uses under `shell=False` -- cannot launch either, so resolving one
would hand callers a path they must then shell out through `cmd.exe` to use. The
extensionless script and the native `.exe` are both directly launchable, and
between them they cover every platform the forwarder installer targets.

Negative-spec: does NOT consult `PATH` via `shutil.which`. Callers resolve against
an explicitly-passed `bin` directory so that a same-named binary earlier on `PATH`
cannot silently substitute itself for the installed forwarder.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Probe order. Extensionless first so a POSIX install (and any Windows box still
# carrying a pre-migration script) resolves to exactly what it resolved to before,
# leaving `.exe` as pure additive coverage rather than a behaviour change.
_FORWARDER_SUFFIXES = ("", ".exe")

# Suffixes whose file is a native executable, launched bare. A suffix is a
# SUFFICIENT tell and never a necessary one -- see `_is_native_image`.
_NATIVE_SUFFIXES = (".exe",)

# The native-image predicate has ONE definition in this package, in
# `_bin_impl_drift`, whose local magic tuple is already pinned against the
# engine's `coordinator_core.install.door_install.NATIVE_IMAGE_MAGIC` by
# `test_bin_impl_drift`. Importing it here rather than carrying a second copy
# means that existing pin covers this module too; a copy would need its own pin
# and could still drift in the window between them.
#
# A sibling import, not an engine import: `_bin_impl_drift` is a peer in this
# directory with no module-scope side effects, and `sessionstart-bin-drift-refresh`
# already imports from it the same way. The no-engine-import constraint in this
# package reaches `coordinator_core`, never the module beside this one.
from _bin_impl_drift import _is_native_image  # noqa: E402


def resolve_forwarder(bin_dir: Path, name: str) -> Optional[Path]:
    """Return the installed forwarder for `name` under `bin_dir`, or None.

    Pair the result with `forwarder_argv` -- the two are a unit, because which
    variant resolved determines whether an interpreter prefix is required.
    """
    for suffix in _FORWARDER_SUFFIXES:
        candidate = bin_dir / f"{name}{suffix}"
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def forwarder_argv(script_path: Path, tail: "list[str] | tuple[str, ...]" = ()) -> "list[str]":
    """Build the argv that launches `script_path`, which must have come from
    `resolve_forwarder`.

    A native image is launched bare: prefixing `sys.executable` hands machine
    code to the Python interpreter, which dies on the first byte with
    `SyntaxError: Non-UTF-8 code`. A naked-Python forwarder REQUIRES the prefix --
    a bare path works on POSIX via shebang plus exec bit, but Windows'
    `CreateProcess` does not consult shebang lines and cannot launch an
    extensionless file at all.

    Negative-spec: the SUFFIX does not decide this. `.exe` proves native, but
    nothing proves the converse -- on POSIX the cut-over door occupies the BARE
    name, which is indistinguishable by name from the naked-Python forwarder it
    replaced. Suffix-only dispatch therefore fed a Mach-O image to `python3` on
    every macOS box, and because all four consumers of this module are fail-open
    it degraded in total silence -- the same silence this module was written to
    end, in mirror image. Ask the bytes.

    Tripwire: AN-EXTENSIONLESS-SETTINGS-HOME-BIN-ENTRY-IS-NOT-PYTHON-SOURCE.
    """
    if script_path.suffix.lower() in _NATIVE_SUFFIXES:
        return [str(script_path), *tail]
    if _is_native_image(script_path):
        return [str(script_path), *tail]
    return [sys.executable, str(script_path), *tail]
