# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
check-forwarder-drift.py — CLI trampoline over the engine repo's
coordinator_core.plugin_health.forwarder_drift.

Read-only staleness probe for generated agent-helper bin/ forwarders: compares
the DERIVED forwarder set (a live scan of the engine repo's own `coordinator/bin/`)
against the INSTALLED forwarders in the settings-home `bin/` and the
`~/.claude/bin` compat mirror, in both directions. Surfaces daily via
/workday-start Step 1.10 Addon Health, alongside its sibling
`check-plugin-drift.py` (git/venv/SHA drift) and `check-claude-klabauter-doctor-
sentinel.py` (the engine's own doctor sentinel) — this probe closes the adjacent
gap those two don't cover: a CLI landing in (or removed from) `coordinator/
bin/` with no forwarder regenerated since, because no install has run.

Two-population exit contract (amended 2026-08-12 — see forwarder_drift.py's
module docstring, CITED-VS-UNCITED SPLIT): install-health-run's _NATIVE_LEGS
legs are fail-loud BY DESIGN because they run only at install time when
derived==installed by construction; this probe runs BETWEEN installs, where
UNCITED drift is expected transient state, not an install defect, and stays
WARN-only. A CITED-but-missing forwarder is a different population — a live
prompt surface instructing an EM to invoke something that cannot resolve —
and is not expected transient lag, so it gates.

CONTENT axis (added 2026-08-12, docs/plans/2026-08-12-auto-arm-the-dual-boot-
for-claude-klabauter-instal.md § C2): the NAME axis above answers only "does an
installed file with this name exist" — it never opens the file. The
2026-08-12 incident (this plan's Problem section) was exactly that gap: this
probe reported `364 derived == 364 installed` while the installed
`_resolve_claude_klabauter.py` — the shim every forwarder execs,
NOT itself one of the counted forwarders — was 486 lines behind its source
and missing the entire two-tier engine gate. `_check_content_axis` below
compares installed bytes for that lib (and any sibling `resolve-claude-klabauter`-
family lib substrate installs) against the source-of-truth copy under the
resolved engine root. Same CITED-VS-UNCITED posture as the name axis'
UNCITED leg: this axis is ALWAYS advisory (never affects the exit code, see
AC7) — a byte mismatch here is expected transient state between a source
edit and the next re-install, not a live-invocation failure the way a
missing CITED forwarder is.

Usage:
  check-forwarder-drift.py

Exit codes:
  0 — no drift, uncited-only drift, orphaned-forwarder drift, CONTENT-axis
      drift, or a clean skip (engine root unresolvable) — every case except
      the one below.
  1 — the cited-but-missing set (forwarder_drift.py's `cited_missing`) is
      non-empty: at least one settings-home/bin forwarder that a live
      DoE-claude prompt surface names is missing. Never fires on "could not
      determine" (AC6) — only on a positively-computed non-empty set. The
      CONTENT axis never contributes to this exit code (AC7).

Spec backlink: cross-repo/inbox/2026-07-23-claude-central-em-claude-klabauter-pickup-assemble-heads-up.md
Spec backlink: pln-auto-arm-the-dual-boot-for-mak-a41c72 § C2
Port of: coordinator/bin/check-plugin-drift.py (trampoline pattern)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import _resolve_claude_klabauter_root  # noqa: E402


def _import_module():
    """Resolve CLAUDE_KLABAUTER_ROOT, put it on sys.path, and import the ported op
    module (name axis + the pieces the CONTENT axis below reuses:
    `_PROG`, `_REMEDY`, `_resolve_settings_bin`).

    Reuses cc_invoke's battle-tested CLAUDE_KLABAUTER_ROOT resolution ladder (env var ->
    settings-home pointer file -> coordinator-claude-klabauter-root.sh) rather than
    re-deriving it — this is a plain in-process import, not an RPC invoke, so
    cc_invoke's subprocess-spawn transport (cc_invoke()/route()) is
    deliberately NOT used here.

    Returns (claude_klabauter_root, module) — `claude_klabauter_root` is also the CONTENT axis'
    resolution of the source-of-truth checkout, so it is returned rather than
    re-resolved a second time via a separate ladder call.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()
    if claude_klabauter_root not in sys.path:
        sys.path.insert(0, claude_klabauter_root)
    from coordinator_core.plugin_health import forwarder_drift as _op_module

    return claude_klabauter_root, _op_module


# Path-loaded libs substrate installs into settings-home/bin alongside every
# generated forwarder (see module docstring's CONTENT axis section). Derived
# from substrate's own install surface rather than hardcoded here (plan
# C2 body) — `_RM_FAMILY_FILES` is substrate.py's own hand-maintained tuple
# naming the resolve-claude-klabauter family (the same tuple `_install_bin_resolvers`'
# `rm_family` writer reads), so this stays in sync with whatever substrate
# actually installs into that family without re-deriving substrate's own
# install policy here.
def _content_axis_lib_names() -> tuple:
    try:
        from coordinator_core.install.substrate import _RM_FAMILY_FILES

        return tuple(_RM_FAMILY_FILES)
    except ImportError:
        # substrate.py exposes no reachable lib-family surface on this
        # checkout (unexpected — verified reachable as of 2026-08-12) —
        # fall back to the one file with proven blast radius (the incident
        # this plan's Problem section documents) rather than skipping the
        # CONTENT axis entirely.
        return ("_resolve_claude_klabauter.py",)


def _content_axis_source_dir(claude_klabauter_root: str) -> Path:
    """Source-of-truth dir for the resolve-claude-klabauter lib family — the same
    `<claude_klabauter_root>/coordinator/lib/resolve-claude-klabauter` join `_install_bin_
    resolvers`'s `resolve_claude_klabauter_lib` local computes (coordinator_core/
    install/substrate.py); not itself exposed as a callable there, so
    re-derived here from the structural layout fact, not substrate's
    install policy."""
    return Path(claude_klabauter_root) / "coordinator" / "lib" / "resolve-claude-klabauter"


def _check_content_axis(fd_module, claude_klabauter_root: str) -> "tuple[list, bool]":
    """CONTENT axis (AC5): compares installed bytes for each name in
    `_content_axis_lib_names()` against its source-of-truth copy under
    `_content_axis_source_dir(claude_klabauter_root)`. Returns (stdout_lines,
    any_drift); `any_drift` is informational only — `main()` never lets it
    change the CLI's exit code (AC7 — see module docstring's CONTENT axis
    section: a stale path-loaded lib between a source edit and the next
    re-install is expected transient state, the same argument the module's
    own CITED-VS-UNCITED SPLIT already makes for the UNCITED name-axis
    population).

    A lib that is not installed at all (missing at `settings_bin/<name>`) is
    the NAME axis' concern (it already reports derived-but-not-installed);
    the content axis has nothing to compare in that case and stays silent
    about it. A source file that itself cannot be found is reported
    (best-effort — an unusual state, e.g. a partial checkout) but is not
    counted as drift, since there is nothing to compare against."""
    label = "settings-home/bin path-loaded libs content"
    settings_bin = fd_module._resolve_settings_bin()
    if not settings_bin.is_dir():
        return (
            [
                f"[skip] {fd_module._PROG} ({label}): '{settings_bin}' does not exist — "
                "no install at this location yet"
            ],
            False,
        )

    source_dir = _content_axis_source_dir(claude_klabauter_root)
    checked = 0
    unresolved = 0
    drifted: "list[str]" = []
    lines: "list[str]" = []
    for name in _content_axis_lib_names():
        dst = settings_bin / name
        if not dst.exists():
            # NAME axis already reports this as derived-but-not-installed —
            # nothing further to say on the content axis.
            continue
        src = source_dir / name
        if not src.exists():
            unresolved += 1
            lines.append(
                f"[warn] {fd_module._PROG} ({label}): could not resolve source-of-truth for "
                f"{name} at {src} — skipping content comparison"
            )
            continue
        checked += 1
        try:
            same = dst.read_bytes() == src.read_bytes()
        except OSError as exc:
            unresolved += 1
            checked -= 1  # counted above the try; this comparison never completed
            lines.append(f"[warn] {fd_module._PROG} ({label}): could not read {name} for comparison: {exc}")
            continue
        if not same:
            drifted.append(name)

    if drifted:
        lines.append(
            f"[warn] {fd_module._PROG} ({label}): {len(drifted)} file(s) differ from their "
            f"source-of-truth copy — {fd_module._REMEDY}: {', '.join(sorted(drifted))}. This is "
            "advisory-only, exit 0 always — expected transient state between a source edit and the "
            "next re-install, same posture as the name axis' UNCITED population (see module "
            "docstring's CITED-VS-UNCITED SPLIT)."
        )
    elif unresolved:
        # Review: code-reviewer 2026-08-12 (nit): a file that could not be
        # checked (missing source-of-truth or unreadable) must not be folded
        # into "0 drifted" as if it were cleared — say so explicitly instead
        # of letting the summary line imply full coverage.
        lines.append(
            f"[ok] {fd_module._PROG} ({label}): {checked} checked, 0 drifted, "
            f"{unresolved} could not be compared (see [warn] above)"
        )
    else:
        lines.append(f"[ok] {fd_module._PROG} ({label}): {checked} checked, 0 drifted")
    return lines, bool(drifted)


def main() -> None:
    try:
        claude_klabauter_root, op_module = _import_module()
    except RuntimeError as exc:
        print(f"check-forwarder-drift.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        # Unresolvable engine root is a clean skip for this probe, not a
        # failure (see forwarder_drift.py's own resolution-ladder contract) —
        # never fail the calling ceremony.
        sys.exit(0)
    except ImportError as exc:
        print(
            f"check-forwarder-drift.py: coordinator_core.plugin_health.forwarder_drift "
            f"not importable: {exc}",
            file=sys.stderr,
        )
        sys.exit(0)

    rc = op_module.main(sys.argv[1:])

    for line in _check_content_axis(op_module, claude_klabauter_root)[0]:
        print(line)

    # AC7: the CONTENT axis never changes the CLI's exit code — see
    # _check_content_axis's docstring and this module's own docstring
    # ("Exit codes:" block).
    sys.exit(rc)


if __name__ == "__main__":
    main()
