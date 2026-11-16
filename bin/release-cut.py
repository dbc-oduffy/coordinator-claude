#!/usr/bin/env python3
"""release-cut.py -- cut refs/heads/release/<name> from a picks manifest.

Applies an ordered pick list on top of a base ref inside a private index
(GIT_INDEX_FILE under the git dir), writes one commit whose sole parent is the
base, and points refs/heads/release/<name> at it with an explicit old value
(zero oid for a new ref). The shared worktree, shared index and every remote
are never touched; the tool prints the clean-clone command and stops.

Usage:
    release-cut.py <manifest.json> [--repo-root PATH] [--replace]

Manifest (JSON):
    {"name": "r25.1", "base": "release/r25",
     "picks": ["<sha>", ...],
     "together": [["64cb927179", "a76dc7"]]}

Every `together` group must be wholly present in `picks` or wholly absent; a
partly present group (or a member that does not resolve) refuses before any
write, naming the member. A pick whose diff (docs/ and state/ excluded) does
not apply refuses naming the pick, with no ref written.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_EXCLUDES = (":(exclude)docs", ":(exclude)state")


class CutError(Exception):
    """A refusal; the message is the whole operator-facing text."""


class _Git(NamedTuple):
    """A git outcome in the bytes shape the call sites read."""

    returncode: int
    stdout: bytes
    stderr: bytes


def _git(root: Path, *args: str, env: dict | None = None, stdin: bytes | None = None) -> _Git:
    """Run git through the shared runner, fail-loud when the engine is not colocated."""
    import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_colocated_engine_on_path

    require_colocated_engine_on_path(__file__)
    from coordinator_core.git.run import run_git

    res = run_git(list(args), cwd=str(root), env=env, input=stdin, binary=True)
    stderr = "git timed out" if res.timed_out and not res.stderr else res.stderr
    return _Git(res.returncode, res.stdout_bytes, stderr.encode("utf-8", "replace"))


def _text(cp: _Git) -> str:
    return (cp.stderr or b"").decode("utf-8", "replace").strip()


def _resolve(root: Path, rev: str) -> str | None:
    cp = _git(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    return cp.stdout.decode().strip() if cp.returncode == 0 else None


def load_manifest(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CutError(f"release-cut: cannot read manifest {path}: {exc}")
    if not isinstance(data, dict):
        raise CutError("release-cut: manifest must be a JSON object")
    name = data.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise CutError(f"release-cut: manifest 'name' invalid: {name!r}")
    if not isinstance(data.get("base"), str) or not data["base"]:
        raise CutError("release-cut: manifest 'base' must be a ref string")
    picks = data.get("picks")
    if not isinstance(picks, list) or not picks or not all(isinstance(p, str) and p for p in picks):
        raise CutError("release-cut: manifest 'picks' must be a non-empty list of shas")
    groups = data.get("together", [])
    if not isinstance(groups, list) or not all(
        isinstance(g, list) and g and all(isinstance(m, str) and m for m in g) for g in groups
    ):
        raise CutError("release-cut: manifest 'together' must be a list of sha lists")
    return data


def validate(root: Path, manifest: dict) -> tuple[str, list[tuple[str, str]]]:
    """Read-only checks. Returns (base_sha, [(pick_as_written, full_sha)])."""
    base_sha = _resolve(root, manifest["base"])
    if base_sha is None:
        raise CutError(f"release-cut: base {manifest['base']!r} does not resolve")
    resolved: list[tuple[str, str]] = []
    seen: dict[str, str] = {}
    for pick in manifest["picks"]:
        full = _resolve(root, pick)
        if full is None:
            raise CutError(f"release-cut: pick {pick} does not resolve")
        if full in seen:
            raise CutError(f"release-cut: pick {pick} duplicates {seen[full]}")
        seen[full] = pick
        resolved.append((pick, full))
    for group in manifest.get("together", []):
        members = []
        for member in group:
            full = _resolve(root, member)
            if full is None:
                raise CutError(f"release-cut: together-group member {member} does not resolve (group {group})")
            members.append((member, full))
        present = [m for m, full in members if full in seen]
        if present and len(present) != len(members):
            missing = [m for m, full in members if full not in seen]
            raise CutError(
                f"release-cut: together-group {group} is partly present; "
                f"missing member {missing[0]} (present: {', '.join(present)})"
            )
    return base_sha, resolved


def cut(root: Path, manifest: dict, *, replace: bool = False) -> tuple[str, str]:
    """Build the release commit and write the ref. Returns (ref, commit_sha)."""
    base_sha, picks = validate(root, manifest)
    ref = f"refs/heads/release/{manifest['name']}"
    cur = _git(root, "rev-parse", "--verify", "--quiet", ref)
    old = cur.stdout.decode().strip() if cur.returncode == 0 else ""
    if old and not replace:
        raise CutError(f"release-cut: {ref} already exists at {old}; pass --replace to move it")
    gitdir = Path(_git(root, "rev-parse", "--absolute-git-dir").stdout.decode().strip())
    tmp = Path(tempfile.mkdtemp(prefix="release-cut-", dir=str(gitdir)))
    try:
        env = dict(os.environ, GIT_INDEX_FILE=str(tmp / "index"))
        cp = _git(root, "read-tree", base_sha, env=env)
        if cp.returncode:
            raise CutError(f"release-cut: read-tree {base_sha} failed: {_text(cp)}")
        for written, full in picks:
            diff = _git(root, "diff", "--binary", "--no-ext-diff", "--no-textconv", f"{full}^", full, "--", ".", *_EXCLUDES)
            if diff.returncode:
                raise CutError(f"release-cut: pick {written} cannot be diffed: {_text(diff)}")
            if not diff.stdout:
                continue
            ap = _git(root, "apply", "--cached", "-3", env=env, stdin=diff.stdout)
            if ap.returncode:
                raise CutError(f"release-cut: pick {written} failed to apply: {_text(ap)}")
        wt = _git(root, "write-tree", env=env)
        if wt.returncode:
            raise CutError(f"release-cut: write-tree failed: {_text(wt)}")
        tree = wt.stdout.decode().strip()
        msg = f"{manifest['name']}: {manifest['base']} plus " + " ".join(p for p, _ in picks) + " [picks, code only]"
        ct = _git(root, "commit-tree", tree, "-p", base_sha, "-m", msg)
        if ct.returncode:
            raise CutError(f"release-cut: commit-tree failed: {_text(ct)}")
        commit = ct.stdout.decode().strip()
        old_value = old or "0" * len(base_sha)
        ur = _git(root, "update-ref", ref, commit, old_value)
        if ur.returncode:
            raise CutError(f"release-cut: update-ref {ref} failed: {_text(ur)}")
        return ref, commit
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="release-cut.py", description=__doc__.splitlines()[0])
    ap.add_argument("manifest")
    ap.add_argument("--repo-root", default=None)
    ap.add_argument("--replace", action="store_true", help="move an existing release ref")
    args = ap.parse_args(argv)
    try:
        if args.repo_root:
            root = Path(args.repo_root).resolve()
        else:
            import lib  # noqa: F401 -- bootstraps coordinator/bin/lib onto sys.path
            from repo_identity import resolve_checked_repo_root

            top, verdict = resolve_checked_repo_root(explicit_root=None)
            if verdict["verdict"] == "MISMATCH":
                print(verdict["message"], file=sys.stderr)
            if top is None:
                raise CutError("release-cut: not inside a git repo; pass --repo-root")
            root = Path(top)
        manifest = load_manifest(Path(args.manifest))
        ref, commit = cut(root, manifest, replace=args.replace)
    except CutError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    name = manifest["name"]
    print(f"release-cut: wrote {ref} -> {commit} (local only, not pushed)")
    print(f"clean-clone: git clone --single-branch -b release/{name} {root.as_posix()} scratch/release-{name}-clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
