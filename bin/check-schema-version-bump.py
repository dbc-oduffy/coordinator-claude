#!/usr/bin/env python3
# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""bin/check-schema-version-bump.py — Tripwire: canonical-structure.yaml must not
change without a corresponding bump to coordinator-schema-version.

Purpose: Enforces the invariant that any structural schema change is
accompanied by a version increment, so that consumer repos' currency stamps
correctly drift-detect after a plugin upgrade.

Spec backlink: docs/plans/2026-05-29-it-just-works-agentic-install-currency.md § Chunk 1
Port backlink: docs/plans/2026-07-19-debash-coordinator-windows.md § E3-b

Usage:
  check-schema-version-bump.py [--staged | --commit=<ref>]

  --staged           (default) Inspects the current git index (staged diff vs HEAD).
                      Suitable for use in a PreToolUse commit hook.
  --commit=<ref>      Inspects the diff introduced by <ref> vs its parent (<ref>~1).
                      Suitable for use in CI or post-commit checks.

Exit codes:
  0 — OK (canonical-structure.yaml not changed, or changed with version bump)
  1 — VIOLATION: canonical-structure.yaml changed without coordinator-schema-version bump
  2 — ERROR: could not determine diff (not a git repo, ref not found, etc.)

Output:
  stdout — human-readable status line
  stderr — error details only

Environment:
  COORDINATOR_PLUGIN_ROOT  Optional. Path to the plugin root containing
                            canonical-structure.yaml and coordinator-schema-version.
                            Defaults to the directory one level above this script
                            (i.e., <plugin-root>/bin/../ when invoked as bin/check-schema-version-bump.py).

Negative-spec (hard-won):
  - This script does NOT check consumer repos — only the plugin root.
  - This script does NOT block on other file changes — only canonical-structure.yaml.
  - Renaming canonical-structure.yaml is out of scope; update CANONICAL_FILE below.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

CANONICAL_FILE = "canonical-structure.yaml"
VERSION_FILE = "coordinator-schema-version"


def _run_git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", cwd, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--commit")
    parser.add_argument("-h", "--help", action="store_true", dest="show_help")
    try:
        args, unknown = parser.parse_known_args(argv)
    except SystemExit:
        return 2
    if unknown:
        print(
            "check-schema-version-bump.py: unknown argument: %s" % unknown[0],
            file=sys.stderr,
        )
        return 2

    if args.show_help:
        print(__doc__)
        return 0

    mode = "commit" if args.commit else "staged"
    commit_ref = args.commit or ""

    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.environ.get(
        "COORDINATOR_PLUGIN_ROOT", os.path.join(script_dir, "..")
    )

    toplevel = _run_git(plugin_root, "rev-parse", "--show-toplevel")
    if toplevel.returncode != 0:
        print(
            "check-schema-version-bump.py: ERROR — not a git repo at '%s'"
            % plugin_root,
            file=sys.stderr,
        )
        return 2
    git_root = toplevel.stdout.strip()

    abs_plugin_root = os.path.abspath(plugin_root)

    prefix_proc = _run_git(abs_plugin_root, "rev-parse", "--show-prefix")
    if prefix_proc.returncode != 0:
        print(
            "check-schema-version-bump.py: ERROR — could not resolve plugin "
            "root relative to git root",
            file=sys.stderr,
        )
        return 2
    rel_plugin_root = prefix_proc.stdout.strip()

    rel_canonical = rel_plugin_root + CANONICAL_FILE
    rel_version = rel_plugin_root + VERSION_FILE

    if mode == "staged":
        diff_proc = _run_git(git_root, "diff", "--cached", "--name-only")
        if diff_proc.returncode != 0:
            print(
                "check-schema-version-bump.py: ERROR — could not read staged diff",
                file=sys.stderr,
            )
            return 2
        changed_names = diff_proc.stdout
    else:
        verify_proc = _run_git(git_root, "rev-parse", "--verify", commit_ref)
        if verify_proc.returncode != 0:
            print(
                "check-schema-version-bump.py: ERROR — ref not found: %s"
                % commit_ref,
                file=sys.stderr,
            )
            return 2
        diff_proc = _run_git(
            git_root, "diff", commit_ref + "~1", commit_ref, "--name-only"
        )
        if diff_proc.returncode != 0:
            print(
                "check-schema-version-bump.py: ERROR — could not diff %s"
                % commit_ref,
                file=sys.stderr,
            )
            return 2
        changed_names = diff_proc.stdout

    changed_set = set(changed_names.splitlines())
    canonical_changed = rel_canonical in changed_set
    version_changed = rel_version in changed_set

    if not canonical_changed:
        print("OK: %s not modified — no version bump required" % CANONICAL_FILE)
        return 0

    if version_changed:
        print("OK: %s modified and %s bumped" % (CANONICAL_FILE, VERSION_FILE))
        return 0

    version_path = os.path.join(abs_plugin_root, VERSION_FILE)
    try:
        with open(version_path, "r", encoding="utf-8") as fh:
            current_version = fh.read().strip()
    except OSError:
        current_version = "?"

    print(
        "VIOLATION: %s was modified but %s was not bumped." % (CANONICAL_FILE, VERSION_FILE)
    )
    print(
        "  Consumers rely on the version integer to detect schema drift. "
        "Every structural"
    )
    print("  change to canonical-structure.yaml must be accompanied by a version increment.")
    print(
        "  Fix: increment the integer in %s (currently: %s) and re-stage."
        % (rel_version, current_version)
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
