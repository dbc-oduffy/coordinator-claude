# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""check-global-doctrine-mirror.py -- drift probe for the coordinator doctrine repo's in-repo
mirror of the operator's global doctrine (`~/.claude/CLAUDE.md` and
`~/.claude/CLAUDE.local.md`), tracked at repo-root `global-doctrine/`.

Purpose: `~/.claude` is a young, single-machine git repo (8 commits, first
dated one day before the 2026-07-21 cold-install clobber that regressed
`CLAUDE.md` from ~27KB of evolved doctrine down to the ~2.9KB installer
template -- see `coordinator/docs/wiki/claude-md-surfaces.md` § The
regression of record). Neither `~/.claude`'s own history nor its `origin`
remote ever contained the pre-clobber evolved file; the only reason recovery
was possible was an out-of-band `.example-doctrine-mirror-repo` backup living OUTSIDE
`~/.claude`'s blast radius. A mirror is only worth keeping if a
re-initialization of `~/.claude` cannot also destroy it -- that requires the
mirror to live in a DIFFERENT repo with its OWN independent git history,
which is exactly what `global-doctrine/` at the coordinator doctrine repo root is.

Direction of truth (load-bearing, do not invert): `global-doctrine/` is
AUTHORITATIVE -- it is the AUTHORING surface. `~/.claude` is the DERIVED live
copy the harness loads. On conflict, `global-doctrine/` wins -- `--sync`
below only ever copies mirror -> `~/.claude`, never the reverse.

REVERSED 2026-07-27 BY PM RULING; this file was the last surface still
carrying the old direction (repointed 2026-07-31). Until that ruling
`~/.claude` was authoritative and this mirror was a passive read-only
backstop. A reader who remembers that shape must find out here that it
changed deliberately rather than assume this probe regressed. What changed:
`global-doctrine/CLAUDE.md` became the place doctrine is actually authored,
and a whole enforcement envelope now keys on it -- the coordinator doctrine repo's PostToolUse
hook `derive-global-doctrine-live-copy.py` (which re-derives `~/.claude` on
every write to the tracked file), the invariant test
`coordinator/tests/test_global_doctrine_tracked_copy.py`, and the CLAUDE.md
admission gate (`hooks/scripts/_claude_md_ledger.py`, whose
`GOVERNED_AUTHORING_SURFACES` names the TRACKED surface). `~/.claude/CLAUDE.md`
carries NO byte cap and NO heading admission ledger.

The old rationale survives the inversion intact, pointed the other way: an
automated `~/.claude` -> mirror sync would make the ungated live copy a
second place doctrine could be "corrected" from, laundering an edit that
never passed the byte cap or the classification ledger into the tracked
authoring copy. That is the direction this probe must never automate.
Restoring the TRACKED copy from `~/.claude` after a mirror loss remains a
deliberate manual recovery action, never a flag on this script.

The backup rationale above is unchanged and, if anything, stronger: the
mirror still lives in a different repo with its own independent git history,
so a re-initialization of `~/.claude` cannot destroy it. It is now the
original rather than the copy.

Placement (load-bearing): `global-doctrine/` lives at the coordinator doctrine repo's REPO
ROOT, never under `coordinator/`. `coordinator/` is the percolation SOURCE
directory for the OSS `coordinator-claude` publish mirror -- the operator's
global doctrine carries personal identity content (§ Owner: name,
background) that must never reach that publish target. Verified 2026-07-22
against `~/.claude/setup/publish-targets.portable`: the `coordinator-claude|
mirror` row's per-file ALLOWLIST (field 7) is
`bin,lib,hooks,skills,agents,commands,docs/wiki/<enumerated-list>,
.claude-plugin,whoami,cockpit-contract/schema` -- every entry is a path
relative to `coordinator/` (the declared SOURCE_DIR). A repo-root
`global-doctrine/` directory is structurally outside that SOURCE_DIR and so
cannot be matched by any allowlist entry, publish invocation, or
`.percolate-ignore` pattern rooted there. This script itself ships under
`coordinator/bin/` (on the allowlist) and DOES percolate to OSS installs --
see the silent-skip behaviour below, which exists specifically so that this
probe is inert noise on any OSS install that has no `global-doctrine/`
mirror at all.

Silent-skip contract: when `global-doctrine/` does not exist relative to the
resolved coordinator doctrine repo root, this probe exits 0 with no output -- never a
warning. This is the "silent skip (opt-in)" arm of the coordinator's
path-resolution doctrine (§ Build For Someone Else's Machine): absence of
the mirror is the expected, correct state on every OSS
install and on any coordinator doctrine repo clone that predates this feature, not a health
regression to nag about.

Usage:
    check-global-doctrine-mirror.py            # compare, report drift
    check-global-doctrine-mirror.py --sync      # re-derive ~/.claude FROM the mirror

Exit codes:
    0 -- OK (mirror absent [silent skip], or every mirrored file matches its
         ~/.claude counterpart byte-for-byte), or --sync completed
    1 -- DRIFT: at least one mirrored file differs from its ~/.claude
         counterpart, is missing on one side, or is missing on BOTH sides
         (there is no both-absent skip -- see the negative-spec entry),
         OR the coordinator doctrine repo root is unresolvable (see
         _repo_root()'s docstring) -- this is a gate/probe script, so an
         unresolvable root fails loud rather than masquerading as the
         mirror-absent silent-skip case.

Environment:
    CLAUDE_HOME -- overrides the `~/.claude` resolution root (defaults to
                   `$HOME/.claude`), matching the convention documented in
                   `coordinator/bin/count-distill-backlog.py`.
    DOE_ROOT / REPO_DOE_CLAUDE -- overrides the coordinator doctrine repo root that
                   owns `global-doctrine/` (see _repo_root()). Consulted via
                   the shared coordinator_registry.doe_root() resolver
                   (env var -> machine-local repos.doe_claude -> raise);
                   this script does NOT derive its own repo root from
                   __file__ -- see _repo_root()'s docstring for why.

Negative-spec (hard-won):
    - Does NOT write to the repo mirror under any flag -- `--sync` only ever
      writes INTO `~/.claude`. The reverse direction is manual-only, and
      deliberately so: see the direction-of-truth block above for why an
      automated live -> mirror sync would launder an ungated edit past the
      byte cap and the classification ledger.
    - Does NOT warn or error when `global-doctrine/` is absent -- that is
      the expected state on every OSS install; see silent-skip contract.
    - DOES report drift for a mirrored pair that is absent on BOTH sides --
      unconditionally, for every pair in `_MIRRORED_FILES`. There used to be
      a both-sides-absent skip carved out for `CLAUDE.local.md`, reasoning
      it was "not in play on this machine"; that framing was wrong -- the
      pair was deliberately RETIRED (commit 60b24123d, 2026-07-31: content
      folded into `CLAUDE.md`, both copies deleted, 364 citations
      repointed), not merely dormant. A retired pair does not belong in a
      live pair list at all, so `CLAUDE.local.md` was removed from
      `_MIRRORED_FILES` instead of being allowlisted -- see the comment
      there. That removal is what lets both-sides-absent stay loud for
      every remaining pair, above all `CLAUDE.md`: the one file this probe
      exists to protect (see the opening paragraph) must never silently
      report OK if both copies vanish (a second clobber, a bad `rm`, a
      broken cold-reinstall).
    - Does NOT hardcode the operator's home directory -- resolves via
      CLAUDE_HOME / os.path.expanduser("~"), so this runs on any machine.
    - Does NOT dump the full 27KB diff on drift -- caps the difflib excerpt
      (see _DIFF_EXCERPT_LINES) so a hit does not flood the session.
    - Does NOT derive the coordinator doctrine repo root from this script's own
      __file__ location -- this script migrated to claude-klabauter while
      `global-doctrine/` stayed in the coordinator doctrine repo; self-location resolution
      would silently and permanently no-op the mirror-absent skip path
      instead of ever comparing anything. See _repo_root()'s docstring.

Spec backlink: state/handoffs/2026-07-22_114921_claude-md-topology-and-global-doctrine-backup.md (Piece 2)
Spec backlink: coordinator/docs/wiki/claude-md-surfaces.md § Global doctrine mirror
"""

from __future__ import annotations

import difflib
import os
import shutil
import sys

PROG = "check-global-doctrine-mirror.py"

# (mirror-relative filename, ~/.claude-relative filename) -- currently identical
# names on both sides, kept as a pair list in case that ever diverges.
# Review: code-reviewer (Finding 1), corrected post-brief -- CLAUDE.local.md
# was deliberately RETIRED 2026-07-31 (commit 60b24123d: content folded into
# CLAUDE.md, both copies deleted, 364 citations repointed), not merely
# "never in play." A retired artifact does not belong in a live pair list,
# so it is removed here rather than allowlisted -- this also means the
# both-sides-absent branch below can stay unconditionally loud for every
# remaining pair, including CLAUDE.md, without an allowlist carve-out.
_MIRRORED_FILES = [
    ("CLAUDE.md", "CLAUDE.md"),
]

_DIFF_EXCERPT_LINES = 20


def _claude_home() -> str:
    """Resolve `~/.claude`, honoring CLAUDE_HOME per the documented
    `${CLAUDE_HOME:-$HOME}/.claude` convention (matches
    coordinator/bin/count-distill-backlog.py's `_resolve_root()`)."""
    base = (
        os.environ.get("CLAUDE_HOME")
        or os.environ.get("HOME")
        or os.environ.get("USERPROFILE")
        or os.path.expanduser("~")
    )
    return os.path.join(base, ".claude")


def _repo_root() -> str:
    """Resolve the DoE-claude REPO ROOT that owns `global-doctrine/`.

    This does NOT derive from this script's own __file__ location. That
    used to be correct when this executable lived in DoE-claude
    (coordinator/bin/../.. IS the repo root there), but this file has
    since migrated to claude-klabauter (commit b644d5a9 here, 8a28a6ca in
    DoE-claude) while `global-doctrine/` stayed put in DoE-claude at the
    REPO root -- self-location now resolves to `<claude-klabauter>/`, which
    has no `global-doctrine/` at all. Because the mirror-absent case is a
    silent skip (see module docstring's silent-skip contract), that break
    was invisible: it just made this probe permanently inert instead of
    ever comparing anything. doe_root() is the correct authority for
    "where is the DoE-claude repo," independent of where THIS script
    happens to run from. A future reader must not "restore" __file__-based
    resolution to regain the old two-hops-up shape -- that is precisely
    what caused this break.

    Resolves via doe_root() (DOE_ROOT env -> REPO_DOE_CLAUDE env ->
    machine-local repos.doe_claude -> raise). Fails loud (sys.exit(1)) if
    doe_root() cannot resolve: this is a gate/probe script, not a
    never-block hook, so an unresolvable DoE root must not silently
    masquerade as the "mirror absent, skip" case.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from coordinator_registry import _DoeUnresolvable, doe_root

    try:
        return doe_root()
    except _DoeUnresolvable as exc:
        sys.stderr.write(
            f"{PROG}: cannot resolve the coordinator doctrine repo root ({exc}). Set "
            "repos.doe_claude in the machine-local registry, or set the "
            "DOE_ROOT / REPO_DOE_CLAUDE env var.\n"
        )
        sys.exit(1)


def _mirror_dir() -> str:
    return os.path.join(_repo_root(), "global-doctrine")


def _diff_excerpt(mirror_path: str, live_path: str) -> str:
    """Return a bounded unified-diff excerpt (authoritative mirror vs derived
    live copy), capped at _DIFF_EXCERPT_LINES lines so a large-file drift hit
    doesn't flood the session."""
    try:
        with open(mirror_path, "r", encoding="utf-8", errors="replace") as fh:
            mirror_lines = fh.readlines()
    except OSError as exc:
        return f"  (could not read mirror file: {exc})\n"
    try:
        with open(live_path, "r", encoding="utf-8", errors="replace") as fh:
            live_lines = fh.readlines()
    except OSError as exc:
        return f"  (could not read ~/.claude file: {exc})\n"

    diff = list(
        difflib.unified_diff(
            mirror_lines,
            live_lines,
            fromfile=mirror_path,
            tofile=live_path,
            n=1,
        )
    )
    truncated = len(diff) > _DIFF_EXCERPT_LINES
    excerpt = diff[:_DIFF_EXCERPT_LINES]
    text = "".join(excerpt)
    if truncated:
        text += f"  ... ({len(diff) - _DIFF_EXCERPT_LINES} more diff line(s) truncated)\n"
    return text


def _compare(mirror_dir: str, claude_home: str) -> int:
    """Compare each ~/.claude live copy against its authoritative mirror
    counterpart. Returns 0 if all match, 1 if any drift is found."""
    drifted = False
    compared = 0
    for mirror_name, live_name in _MIRRORED_FILES:
        mirror_path = os.path.join(mirror_dir, mirror_name)
        live_path = os.path.join(claude_home, live_name)

        mirror_exists = os.path.isfile(mirror_path)
        live_exists = os.path.isfile(live_path)

        if not mirror_exists and not live_exists:
            sys.stderr.write(
                f"{PROG}: DRIFT -- both sides missing: {mirror_path} and "
                f"{live_path} (neither the authoritative source nor the "
                "live copy exists -- this is the double-deletion case "
                "this probe exists to catch)\n"
            )
            drifted = True
            continue
        if not mirror_exists:
            sys.stderr.write(
                f"{PROG}: DRIFT -- authoritative source missing: {mirror_path} "
                f"(a live {live_path} exists with no tracked authoring copy behind it)\n"
            )
            drifted = True
            continue
        if not live_exists:
            sys.stderr.write(
                f"{PROG}: DRIFT -- live copy never derived: {live_path} "
                f"(authoritative {mirror_path} exists) -- run '{PROG} --sync'\n"
            )
            drifted = True
            continue

        compared += 1
        mirror_size = os.path.getsize(mirror_path)
        live_size = os.path.getsize(live_path)

        with open(mirror_path, "rb") as fh:
            mirror_bytes = fh.read()
        with open(live_path, "rb") as fh:
            live_bytes = fh.read()

        if mirror_bytes == live_bytes:
            continue

        drifted = True
        sys.stderr.write(
            "DRIFT DETECTED: live {} no longer matches its authoritative source.\n".format(
                live_name
            )
        )
        sys.stderr.write(f"  Authoritative source : {mirror_path} ({mirror_size} bytes)\n")
        sys.stderr.write(f"  Stale live copy      : {live_path} ({live_size} bytes)\n")
        sys.stderr.write(
            "  Direction of truth   : global-doctrine/ wins on conflict -- run "
            f"'{PROG} --sync' to re-derive ~/.claude FROM the mirror.\n"
        )
        sys.stderr.write(
            "  If the live-side edit was the intended one, do NOT sync it back by "
            "hand -- re-author it in global-doctrine/ so the byte cap and the "
            "classification ledger see it.\n"
        )
        sys.stderr.write("  Diff excerpt (source -> live, capped):\n")
        sys.stderr.write(_diff_excerpt(mirror_path, live_path))

    if not drifted:
        sys.stdout.write(
            "OK: ~/.claude matches the global-doctrine/ authoring copy byte-for-byte "
            "({} file(s) in play)\n".format(compared)
        )
        return 0

    sys.stderr.write(
        f"{PROG}: mirror drift detected -- see above for remediation ('{PROG} --sync').\n"
    )
    return 1


def _sync(mirror_dir: str, claude_home: str) -> int:
    """Re-derive the ~/.claude live copies FROM the authoritative mirror.
    Never writes into the mirror.

    This is the same derivation the DoE-claude PostToolUse hook
    `derive-global-doctrine-live-copy.py` performs on every write to the
    tracked file; this flag is the manual catch-up for the cases that hook
    cannot see (a cold re-install that clobbered `~/.claude`, an out-of-band
    edit, a machine where the hook did not fire)."""
    updated = []
    for mirror_name, live_name in _MIRRORED_FILES:
        mirror_path = os.path.join(mirror_dir, mirror_name)
        live_path = os.path.join(claude_home, live_name)

        if not os.path.isfile(mirror_path):
            if os.path.isfile(live_path):
                sys.stderr.write(
                    f"{PROG}: --sync -- authoritative source missing, skipped: "
                    f"{mirror_path} (live {live_path} left untouched -- this flag "
                    "never writes into the mirror)\n"
                )
            continue

        if os.path.isfile(live_path):
            with open(live_path, "rb") as fh:
                existing = fh.read()
            with open(mirror_path, "rb") as fh:
                incoming = fh.read()
            if existing == incoming:
                continue

        os.makedirs(os.path.dirname(live_path), exist_ok=True)
        shutil.copyfile(mirror_path, live_path)
        updated.append(live_name)

    if updated:
        sys.stdout.write(
            "SYNCED: re-derived {} in {} from the global-doctrine/ authoring copy\n".format(
                ", ".join(updated), claude_home
            )
        )
    else:
        sys.stdout.write("OK: ~/.claude live copy already current -- nothing to derive\n")
    return 0


def main(argv: list[str]) -> int:
    do_sync = False
    for arg in argv:
        if arg == "--sync":
            do_sync = True
        elif arg in ("-h", "--help"):
            sys.stdout.write(__doc__.strip() + "\n")
            return 0
        else:
            sys.stderr.write(f"{PROG}: unknown argument: {arg}\n")
            return 2

    mirror_dir = _mirror_dir()
    if not os.path.isdir(mirror_dir):
        # Silent skip -- see module docstring's silent-skip contract. This is
        # the expected state on every OSS install and on any DoE-claude clone
        # that predates this feature.
        return 0

    claude_home = _claude_home()

    if do_sync:
        return _sync(mirror_dir, claude_home)
    return _compare(mirror_dir, claude_home)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
