#!/usr/bin/env python3
"""CI validator: every tracked file with a '#!' shebang must be committed at mode 100755.

Spec backlink: docs/plans/2026-06-11-exec-bit-install-surface-completion.md § Chunk 6

WHY THIS VALIDATOR EXISTS
--------------------------
On Windows with core.fileMode=false, Git does not preserve executable bits in the index.
Scripts committed from Windows land at 100644 even after `git update-index --chmod=+x`.
A clean clone on any Unix machine (including OSS marketplace users) then installs
non-functional scripts — the failure is silent because Windows callers use `bash <script>`
directly, bypassing the mode bit.

This validator queries the committed index mode AND blob content via `git ls-files --stage`
(NOT on-disk stat), which is the authoritative record of what a `git clone` will deliver.
The shebang check reads from the git object store (via `git cat-file --batch`), not from
the working tree — this ensures the validator catches drift even when the working-tree copy
differs from the index, and works correctly in CI environments with sparse checkouts.

ALLOWLIST ASYMMETRY (negative-spec)
-------------------------------------
The per-commit JS test (coordinator/tests/plugin-ecosystem/exec-bit.test.js) carries
SOURCE_ONLY_ALLOWLIST and FOREIGN_OWNED_ALLOWLIST entries for files that legitimately
live at 100644 (sourced-only scripts, vendored third-party files). This CI validator
carries NO such allowlist — CI is the final strict gate. Any file that begins with '#!'
must be 100755. If a legitimate exception exists, it requires a documented architectural
reason in DR-151, not an allowlist entry here.

REPO-ROOT DISCOVERY
--------------------
The validator calls `git rev-parse --show-toplevel` at runtime rather than assuming any
fixed directory layout. This satisfies the "CI scripts in publish repos must not hardcode
layout paths" lesson (state/lessons.md, grep: "CI scripts in publish repos").

EXIT CONTRACT
--------------
  0  — all shebanged files are at 100755 (or there are no shebanged tracked files)
  1  — one or more shebanged files are at 100644 (drift detected; fix commands printed)
"""

import argparse
import shlex
import subprocess
import sys


def get_repo_root(override: str | None = None) -> str:
    """Return the absolute path to the repository root via git.

    If ``override`` is provided (via ``--repo-root`` CLI flag), it is returned
    directly without a git subprocess call — useful for callers that already
    know the root and want to avoid the ``__file__``-anchor footgun described
    below.

    Without an override, defaults to the ambient cwd (``"."``), matching the
    convention used by validate-hook-paths.py and the other sibling validators.
    In CI the workflow step already sets cwd to the repo root, so this is
    equivalent to the explicit-anchor call.  On a developer machine, callers
    that need a specific repo should pass ``--repo-root`` explicitly.

    Review: Patrik — ``__file__``-anchor is a footgun when called from outside
    the repo (e.g. meta-repo ~/.claude); ``--repo-root`` override + cwd default
    matches the sibling-validator convention.
    """
    if override is not None:
        return override

    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    if result.returncode != 0:
        print(f"ERROR: git rev-parse --show-toplevel failed: {result.stderr.strip()}")
        sys.exit(1)
    return result.stdout.strip()


def get_staged_entries(repo_root: str) -> list[tuple[str, str, str]]:
    """Return [(mode, object_hash, path)] for all files tracked in the index.

    Uses git ls-files --stage to read committed index mode and blob hash —
    NOT on-disk stat. Mode-blindness on Windows is exactly the failure this
    validator exists to catch; on-disk stat would silently miss it.
    """
    result = subprocess.run(
        ["git", "ls-files", "--stage"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if result.returncode != 0:
        print(f"ERROR: git ls-files --stage failed: {result.stderr.strip()}")
        sys.exit(1)

    entries = []
    # Review: Patrik — during merge conflicts git ls-files --stage emits stage 1/2/3 entries
    # for the same path; dedupe by path keeping the first-seen entry to avoid false positives.
    seen_paths: set[str] = set()
    for line in result.stdout.splitlines():
        # Format: <mode> SP <object> SP <stage> TAB <file>
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        meta = parts[0].split()
        if len(meta) < 2:
            continue
        mode = meta[0]
        obj_hash = meta[1]
        path = parts[1]
        if path in seen_paths:
            continue
        seen_paths.add(path)
        entries.append((mode, obj_hash, path))
    return entries


def check_shebang_via_git(repo_root: str, obj_hashes: list[str]) -> set[str]:
    """Return the set of object hashes whose blob content starts with '#!'.

    Reads from the git object store (not the working tree) so this works correctly
    in CI environments and catches drift between index and working copy.

    Uses git cat-file --batch for efficiency — one subprocess call for all blobs.
    """
    if not obj_hashes:
        return set()

    batch_input = ("\n".join(obj_hashes) + "\n").encode()
    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        input=batch_input,
        capture_output=True,
        cwd=repo_root,
    )
    if result.returncode != 0:
        print(f"ERROR: git cat-file --batch failed: {result.stderr.decode().strip()}")
        sys.exit(1)

    shebang_hashes = set()
    raw = result.stdout
    pos = 0
    while pos < len(raw):
        # Header line: "<hash> <type> <size>\n"
        newline = raw.find(b"\n", pos)
        if newline == -1:
            break
        header = raw[pos:newline].decode("ascii", errors="replace")
        pos = newline + 1

        parts = header.split()
        if len(parts) < 3 or parts[1] == "missing":
            continue

        obj_hash = parts[0]
        try:
            size = int(parts[2])
        except ValueError:
            # Review: Patrik — silent desync of binary stream parser is worse than a hard exit;
            # unexpected header format means the git cat-file output is malformed, so exit 1.
            print(f"ERROR: unexpected cat-file header format: {header!r}", file=sys.stderr)
            sys.exit(1)

        # Read exactly `size` bytes of blob content, then the trailing newline
        content_start = pos
        first_two = raw[content_start:content_start + 2]
        pos += size
        # Skip the trailing LF that git cat-file emits after each object
        if pos < len(raw) and raw[pos:pos + 1] == b"\n":
            pos += 1

        if first_two == b"#!":
            shebang_hashes.add(obj_hash)

    return shebang_hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Override the repository root (default: discovered from ambient cwd via git rev-parse).",
    )
    args = parser.parse_args()

    repo_root = get_repo_root(args.repo_root)
    entries = get_staged_entries(repo_root)

    # Collect all 100644 entries to check for shebangs
    candidates = [(mode, obj_hash, path) for mode, obj_hash, path in entries if mode == "100644"]

    if not candidates:
        print("Exec-bit check passed: all shebanged tracked files are at 100755.")
        return 0

    candidate_hashes = [obj_hash for _, obj_hash, _ in candidates]
    shebang_hashes = check_shebang_via_git(repo_root, candidate_hashes)

    offenders = [path for _, obj_hash, path in candidates if obj_hash in shebang_hashes]

    if not offenders:
        print("Exec-bit check passed: all shebanged tracked files are at 100755.")
        return 0

    print("Exec-bit check FAILED: the following shebanged files are committed at 100644:")
    for path in offenders:
        print(f"  {path}")

    print()
    print("Fix with:")
    # Review: Patrik — shlex.quote ensures paths with spaces are shell-safe
    print(f"  git update-index --chmod=+x {' '.join(shlex.quote(p) for p in offenders)}")
    print()
    print("Then commit the mode change WITHOUT a path-restricted `-- <paths>` suffix")
    print("(Windows core.fileMode=false silently resets exec bits when path-restricting).")
    print("See DR-151 for the Windows-chmod commit mechanic exception to scoped-commit doctrine.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
