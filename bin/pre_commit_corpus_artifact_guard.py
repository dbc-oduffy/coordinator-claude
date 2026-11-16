#!/usr/bin/env python3
"""coordinator/bin/pre_commit_corpus_artifact_guard.py — refuse a commit that stages a
project-rag corpus artifact, or any oversized real blob.

Purpose: the belt-and-braces half of the fleet ruling that a corpus artifact is never
committed (coordinator-content-repo's ``coordinator-content-repo coordinator/docs/wiki/coordinator-tripwires/corpus-artifact-is-never-committed.md``).
The ignore stanza is the primary defence; this catches the cases the stanza cannot,
because a `.gitignore` rule is silent once a path is staged with ``git add -f`` or was
already tracked before the rule existed.

TWO INDEPENDENT LEGS, and the path leg is the load-bearing one.

  1. PATH leg — any staged path under ``.project-rag-corpus-artifacts/`` or
     ``.project-rag-corpus-store/`` is refused REGARDLESS OF SIZE. A size-only guard
     (the shape the prior art in project-rag-ue-addon implements) passes a small or
     partially-written corpus directory, which is still a corpus artifact in a commit
     and still the thing the ruling forbids. Size is a proxy for the real predicate;
     this leg is the real predicate.
  2. SIZE leg — any staged real blob over the threshold, wherever it lives. This is the
     generic push-limit catch: GitHub hard-rejects a non-LFS blob over 100 MB, so a
     commit that passes locally fails at push after the network round-trip. Defaulting
     to 95 MB leaves margin.

Ported from project-rag-ue-addon's ``bin/pre-commit-oversized-blob-guard.sh`` per the
fleet's standing ruling that structural bash is a defect (claude-klabauter CLAUDE.md §
Runtime conventions). Not a translation — the path leg is new, and the LFS-pointer
reasoning is dropped because git-LFS is ruled out for this artifact class on the merits,
so an over-threshold staged blob here has no legitimate pointer form to be confused with.

No DoE-relative paths: every path this guard touches is staged-index state in the caller's
own repo, read via `git` subprocess calls -- nothing here is `Path(__file__)`-derived, so no
adaptation was needed for its move from coordinator-content-repo into claude-klabauter
(docs/plans/2026-09-18-doe-holds-no-scripts.md § Path resolution).

Windows-first: no shell, no bash, no ``find``. Every git call goes through
``subprocess.run`` with a list argv, so a path containing a space or a drive letter
survives; paths are compared with forward slashes because that is what git emits on
every platform, including Windows.

Exit codes:
  0 — nothing staged violates either leg (including the no-staged-files case).
  1 — at least one violation; the commit is refused and the reason printed to stderr.

Bypass (both legs): ``CORPUS_ARTIFACT_OK=1 git commit ...``
Threshold override, MiB, size leg only: ``OVERSIZE_BLOB_MAX_MB=<N> git commit ...``

Negative-spec:
  - Does NOT stage, unstage, or modify anything. A guard that repairs the index behind
    the author is a guard that surprises them mid-commit; this one refuses and explains.
  - Does NOT read or write ``.gitignore``. The stanza is scaffolded by repo-setup Phase
    3f; this script never edits it and never infers policy from its contents.
  - Does NOT consult the network, project-rag, or any registry. It must run offline in a
    pre-commit hook on a laptop.
  - Does NOT substitute 0 for an unmeasurable blob. A path that vanished from the index
    mid-run (a concurrent ``git add`` on this shared tree) is skipped, never silently
    passed as zero-sized.

Spec backlink: docs/plans/2026-09-18-doe-holds-no-scripts.md, chunk W2-C5.

Standalone contract: runs standalone as a hook body and resolves on its own when no shared
per-commit resolution is available. Never imports `coordinator_core` itself on the guard
path: the only reach is `_load_commit_resolution`, a guarded load by file path (checkout
root appended to sys.path) whose failure falls back. It runs with no engine-root bootstrap,
so it keeps its own fallback git spawns and is exempt from the shared git runner
(`coordinator_core/tests/test_shared_git_runner.py :: _CONTRACT_EXEMPT_MODULES`).
Only ``--install-hook`` imports it, after putting this checkout's engine root on sys.path.
The staged set comes from `hooks/commit_resolution.py`, loaded by file path and shared
with the other hooks of the same commit; its own spawn is only the load-failure fallback.

``--install-hook`` (run in the target repo) is the sanctioned install and repair of this
repo's ``.git/hooks/pre-commit``: absent -> write the self-resolving hook body; already
that body -> rewrite only if stale; a copied forwarder stub -> replaced via the hook
disposition table (original kept as ``pre-commit.retired``); any other hook -> left
untouched, exit 2.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

# A console-subsystem child with no console of its own allocates a fresh conhost on
# Windows -- with a visible window. Every git spawn below is short-lived and
# output-captured, so without this each one flashes. 0 on POSIX, where the flag doesn't exist.
_NO_CONSOLE = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

_CORPUS_PREFIXES = (
    ".project-rag-corpus-artifacts/",
    ".project-rag-corpus-store/",
)

_DEFAULT_MAX_MB = 95
_BYPASS_ENV = "CORPUS_ARTIFACT_OK"
_MAX_MB_ENV = "OVERSIZE_BLOB_MAX_MB"


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            shell=False,
            timeout=15,
            **_NO_CONSOLE,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(["git", *args], 124, "", "git timed out")


def _hook_git_dir() -> str:
    """The hook's git dir with no spawn: `$GIT_DIR`, else `./.git` (a directory, or a
    `gitdir:` file for a linked worktree). git runs hooks with cwd at the worktree root.
    "" when underivable."""
    try:
        env_git_dir = os.environ.get("GIT_DIR", "").strip()
        if env_git_dir:
            return env_git_dir
        cwd = os.getcwd()
        dotgit = os.path.join(cwd, ".git")
        if os.path.isdir(dotgit):
            return dotgit
        if os.path.isfile(dotgit):
            with open(dotgit, encoding="utf-8") as fh:
                first_line = fh.readline().strip()
            if first_line.startswith("gitdir:"):
                target = first_line[len("gitdir:"):].strip()
                if target and not os.path.isabs(target):
                    target = os.path.normpath(os.path.join(cwd, target))
                return target
    except Exception:
        pass
    return ""


def _load_commit_resolution():
    """Load the shared-resolution module by file path from this checkout. It imports
    `coordinator_core.git.run`, so this checkout's root joins sys.path (appended, lowest
    precedence). None when absent or broken."""
    try:
        import importlib.util

        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in sys.path:
            sys.path.append(root)
        path = os.path.join(root, "coordinator_core", "hooks", "commit_resolution.py")
        spec = importlib.util.spec_from_file_location("_corpus_guard_commit_resolution", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _staged_paths() -> list[str]:
    """Paths introducing new content: added, modified, renamed. Deletes introduce no blob.
    A rename counts -- `git mv` then `git add -f` records as R, and the destination is a
    real blob that would be pushed.

    Reads the per-commit shared resolution (one `git diff --cached` across every hook of
    the commit); falls back to its own spawn only when that module or the git dir is
    unavailable."""
    resolution = _load_commit_resolution()
    git_dir = _hook_git_dir() if resolution is not None else ""
    if resolution is not None and git_dir:
        try:
            return resolution.names_filtered(git_dir, "AMR", 15)
        except Exception as exc:
            print(f"[corpus-artifact-guard] could not read the staged set ({exc}); allowing", file=sys.stderr)
            return []
    proc = _git(["diff", "--cached", "--name-only", "--diff-filter=AMR"])
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _staged_size(path: str) -> int | None:
    """None is deliberately distinct from 0: an unmeasurable path is skipped rather than
    passed, so a concurrent index write on this shared tree never converts an oversized
    blob into a silent pass."""
    proc = _git(["cat-file", "-s", f":{path}"])
    if proc.returncode != 0:
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return None


def _max_bytes() -> int:
    raw = os.environ.get(_MAX_MB_ENV, "")
    try:
        mb = int(raw) if raw else _DEFAULT_MAX_MB
    except ValueError:
        mb = _DEFAULT_MAX_MB
    if mb <= 0:
        mb = _DEFAULT_MAX_MB
    return mb * 1024 * 1024


def _write_hook_atomic(path, body: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(body.encode("utf-8"))
    if os.name != "nt":
        os.chmod(tmp, 0o755)
    os.replace(tmp, path)


def _install_hook() -> int:
    """Install or repair this repo's pre-commit hook; see the module docstring."""
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from coordinator_core.git import hook_dispositions
    from coordinator_core.git.corpus_guard_hook import STAMP, hook_body, is_forwarder_stub
    from coordinator_core.git.git_dir import resolve_git_common_dir

    top = _git(["rev-parse", "--show-toplevel"])
    if top.returncode != 0 or not top.stdout.strip():
        print("[corpus-artifact-guard] --install-hook: not inside a git repo", file=sys.stderr)
        return 2
    root = Path(top.stdout.strip())
    hooks = resolve_git_common_dir(root) / "hooks"
    target = hooks / "pre-commit"

    body = hook_body()
    if is_forwarder_stub(body):
        print("[corpus-artifact-guard] generated hook body is a forwarder stub; refusing", file=sys.stderr)
        return 2

    if not target.exists():
        hooks.mkdir(parents=True, exist_ok=True)
        _write_hook_atomic(target, body)
        print(f"[corpus-artifact-guard] installed {target}")
        return 0

    try:
        text = target.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        text = ""
    if STAMP in text:
        if text == body:
            print(f"[corpus-artifact-guard] {target} is current")
        else:
            _write_hook_atomic(target, body)
            print(f"[corpus-artifact-guard] rewrote {target}")
        return 0
    if is_forwarder_stub(text):
        verdicts = hook_dispositions.apply_repo(root, check_only=False)
        for entry_id, hook, verdict in verdicts:
            print(f"[corpus-artifact-guard] {entry_id} {hook}: {verdict}")
        replaced = [v for v in verdicts if v[0] == "forwarder-stub-pre-commit"]
        return 0 if replaced and replaced[0][2] in ("replaced", "current") else 2
    print(f"[corpus-artifact-guard] {target} is not an engine hook; left untouched", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pre_commit_corpus_artifact_guard.py",
        description="Refuse a commit that stages a project-rag corpus artifact or an oversized blob.",
    )
    parser.add_argument(
        "--install-hook",
        action="store_true",
        help="install or repair this repo's .git/hooks/pre-commit with the self-resolving hook body",
    )
    args = parser.parse_args(argv[1:] if argv is not None else None)

    if args.install_hook:
        return _install_hook()

    if os.environ.get(_BYPASS_ENV) == "1":
        print(f"[corpus-artifact-guard] bypassed via {_BYPASS_ENV}=1", file=sys.stderr)
        return 0

    staged = _staged_paths()
    if not staged:
        return 0

    max_bytes = _max_bytes()
    max_mb = max_bytes // (1024 * 1024)

    corpus_hits: list[str] = []
    oversized: list[str] = []

    for path in staged:
        normalized = path.replace("\\", "/")
        if any(normalized.startswith(p) for p in _CORPUS_PREFIXES):
            corpus_hits.append(path)
            continue
        size = _staged_size(path)
        if size is None or size <= max_bytes:
            continue
        size_mb = -(-size // (1024 * 1024))
        oversized.append(f"{path}: {size_mb} MB (limit {max_mb} MB)")

    if not corpus_hits and not oversized:
        return 0

    out = sys.stderr
    print("[corpus-artifact-guard] commit REFUSED.\n", file=out)

    if corpus_hits:
        print(
            "A project-rag corpus artifact is staged. Fleet ruling: a corpus artifact is\n"
            "NEVER committed, in any repo, in any form, git-LFS included. It is regenerable,\n"
            "so history on one is cost with no consumer.\n",
            file=out,
        )
        for hit in corpus_hits:
            print(f"  {hit}", file=out)
        print(
            "\nThese paths are gitignored, so they reached the index via `git add -f` or were\n"
            "tracked before the stanza existed. Unstage them:\n"
            "    git restore --staged -- <path>\n"
            "If they were already tracked, untrack them so the ignore rule takes effect:\n"
            "    git rm -r --cached <path>\n"
            "Ruling: the coordinator content repo's wiki, coordinator-tripwires/"
            "corpus-artifact-is-never-committed.md\n",
            file=out,
        )

    if oversized:
        print(
            "Staged blob(s) exceed the push limit. GitHub rejects any pushed blob over\n"
            "100 MB, so this commit would succeed locally and fail at push.\n",
            file=out,
        )
        for hit in oversized:
            print(f"  {hit}", file=out)
        print(
            f"\nRaise the threshold for a known-legitimate large file:\n"
            f"    {_MAX_MB_ENV}=<N> git commit ...\n",
            file=out,
        )

    print(f"To override both legs deliberately:\n    {_BYPASS_ENV}=1 git commit ...", file=out)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
