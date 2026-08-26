#!/usr/bin/env python3
"""Install (or re-apply) the Claude Code fast-profile block into Git-for-Windows'
`/etc/profile`.

Purpose: Claude Code's Bash tool invokes `bash -c -l`, so the stock profile is sourced
and discarded once per Bash call (~800ms on Machine-a, measured). `git-bash-fast-profile.sh`
reproduces the environment spawn-free and returns early for non-interactive shells
carrying `CLAUDECODE`. This script puts that block at the top of `/etc/profile`.

Needs an ELEVATED shell -- `/etc/profile` lives inside the Git-for-Windows install root,
not the user profile. Run from an Administrator terminal.

A Git-for-Windows update replaces `/etc/profile` wholesale and silently removes the
block, restoring the cost with no coordinator change to blame. Re-run this after
updating Git. See `docs/wiki/coordinator-tripwires/tripwire-registry/
a-git-update-silently-restores-the-login-shell-tax.md`.

Negative-spec (RAG-bait):
    This script does not edit any file under `profile.d/` (the cost is in
    `/etc/profile`'s own body, not there), does not remove or reorder any stock profile
    content, and does not decide whether the fast path is TAKEN -- that is the block's
    own two-condition runtime guard (non-interactive shell AND `CLAUDECODE` set). It
    writes bytes in binary mode throughout and never re-encodes line endings: a CRLF
    introduced into `/etc/profile` breaks every bash invocation on the host.

Usage:
    python3 install-git-bash-fast-profile.py [--profile PATH] [--uninstall] [--check]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BEGIN = b"# >>> claude-code fast profile (DoE-claude) >>>"
END = b"# <<< claude-code fast profile <<<"
BACKUP_SUFFIX = ".pre-claude-fast-profile.bak"


def _default_profile() -> Path | None:
    """Locate Git-for-Windows' `/etc/profile` from the installed `git` itself.

    Derived, never hardcoded: the install root varies per host (`Program Files`,
    `Program Files (x86)`, a scoop/winget prefix, a portable unpack). `git.exe` lands in
    `<root>/cmd/` or `<root>/bin/`, so the profile is `<root>/etc/profile` either way.
    Returns None when git is not on PATH, leaving `--profile` as the explicit route.
    """
    git = shutil.which("git")
    if not git:
        return None
    for parent in Path(git).resolve().parents:
        candidate = parent / "etc" / "profile"
        if candidate.is_file():
            return candidate
    return None


def _fragment_path() -> Path:
    return Path(__file__).resolve().parent / "git-bash-fast-profile.sh"


def _strip_block(data: bytes, profile: Path) -> bytes:
    """Remove an already-installed block, wherever it sits. Returns data unchanged
    when no block is present."""
    start = data.find(BEGIN)
    if start == -1:
        return data
    end = data.find(END, start)
    if end == -1:
        raise SystemExit(
            "refusing to proceed: found the block's BEGIN marker with no END marker in "
            f"{profile} -- the file is half-edited and needs a human look"
        )
    end += len(END)
    while end < len(data) and data[end : end + 1] == b"\n":
        end += 1
    return data[:start] + data[end:]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", type=Path, default=_default_profile())
    ap.add_argument("--uninstall", action="store_true", help="remove the block")
    ap.add_argument(
        "--check",
        action="store_true",
        help="report whether the block is installed; change nothing. "
        "Exit 0 installed, 1 absent.",
    )
    args = ap.parse_args(argv)

    profile: Path | None = args.profile
    if profile is None:
        print(
            "could not locate Git-for-Windows' /etc/profile (git not on PATH). "
            "Pass --profile explicitly.",
            file=sys.stderr,
        )
        return 2
    if not profile.is_file():
        print(f"not found: {profile}", file=sys.stderr)
        return 2

    current = profile.read_bytes()
    installed = BEGIN in current

    if args.check:
        print(f"{'installed' if installed else 'ABSENT'}: {profile}")
        return 0 if installed else 1

    block = b""
    if not args.uninstall:
        fragment = _fragment_path()
        if not fragment.is_file():
            print(f"fragment missing: {fragment}", file=sys.stderr)
            return 2
        block = fragment.read_bytes()
        if b"\r\n" in block:
            print(
                f"refusing to install: {fragment} contains CRLF. A CRLF in /etc/profile "
                "breaks every bash invocation on this host.",
                file=sys.stderr,
            )
            return 2

    # Strip any prior block first, so this is idempotent and a re-apply after a Git
    # update cannot stack two copies.
    base = _strip_block(current, profile)
    new = base if args.uninstall else block + base

    if new == current:
        print(f"no change needed: {profile}")
        return 0

    backup = profile.with_name(profile.name + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(profile, backup)
        print(f"backed up stock profile -> {backup}")

    try:
        profile.write_bytes(new)
    except PermissionError:
        print(
            f"permission denied writing {profile}\n"
            "This file lives inside the Git-for-Windows install root. Re-run from an "
            "elevated (Administrator) terminal.",
            file=sys.stderr,
        )
        return 2

    print(f"{'removed block from' if args.uninstall else 'installed block into'} {profile}")
    if not args.uninstall:
        print(
            "Verify with:  bash -lc 'echo $PATH'   (should match a stock login shell)\n"
            "Force stock path for debugging:  COORDINATOR_FULL_PROFILE=1"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
