# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""merge-recovery-and-tag-cut.py — naked-Python port of the /merging-to-main
recovery-branch dance and idempotent annotated-tag cut.

Self-contained, self-resolving (Path(__file__)-relative, NO cwd dependence for
its own imports), naked-Python CLI. Ports the residual imperative bash logic
out of coordinator-content-repo's `coordinator/skills/merging-to-main/SKILL.md` Step 1 /
Step 1.5 so the skill can call this CLI by name instead of carrying the logic
inline. This file is the M3/MTM-1 chunk output of that porting pass; the
skill-side repoint (D2) is a later wave and lands in coordinator-content-repo, not here.

Subcommands (argv[1] selects):

  recovery-branch [--repo-root PATH] [--branch-name NAME]
      Runs the "on main with unpushed commits" auto-recovery dance: sync
      local main to origin/main (via the sibling sync-main.py), cut a fresh
      work/<host>/<date> branch off the pre-sync state, push it, hard-reset
      main to origin/main, then return to the new branch. Prints the
      resulting branch name to stdout (`BRANCH=<name>`) for the caller to
      capture. Ported from SKILL.md Step 1, "If on main with unpushed
      commits ahead of origin/main".

  resolve-tag-prefix --config PATH
      Parses the `tag_prefix:` frontmatter key out of a coordinator.local.md
      (or equivalent) file, matching the awk one-liner's semantics: only the
      first YAML frontmatter block is scanned (between the first two `---`
      fence lines), the first `tag_prefix:` line wins, and any inline `#...`
      comment is stripped. A quoted value is a hard authoring error
      (detect-then-fail-loud, not detect-then-silently-pick) — ported
      verbatim from SKILL.md Step 1.5 Part 2 Mode A. Absent key -> prints
      nothing, exits 0 (bare-`v*` default per DR-149).

  cut-tag TAG [--repo-root PATH] [--fetch-ref main] [--merge-ref REF]
           [--must-contain SHA] [--pr N]
      Idempotent annotated-tag cut + push: fetches `--fetch-ref` from origin,
      resolves `--merge-ref` (default: the just-fetched `--fetch-ref` tip, FETCH_HEAD) to a commit SHA, and only (re)creates + pushes
      the annotated tag when it does not already point at that commit.
      Peels an existing annotated tag (`TAG^{}`) before comparing, so the
      "already at target" skip is a genuine idempotency check against the
      underlying commit — not the tag object's own SHA (see Negative-spec
      below). Ported from SKILL.md Step 1.5 Part 2, both Mode A (git-tag-only)
      and Mode B (GH-release) share this exact tag-cut core; only the
      GH-release publish step (below) differs between the two.
      When `--must-contain SHA` is given, asserts (via `git merge-base
      --is-ancestor`) that the resolved merge_ref commit is an ancestor of
      SHA before cutting or skipping the tag — fails loud, no tag mutation,
      if it is not. The `--merge-ref origin/main` default is unaffected by
      whether `--must-contain` is passed.
      Run it AFTER `gh pr merge`, with `--pr N` (target = that PR's merge
      commit). Refuses (exit 1) when origin already has TAG at another
      commit; never force-moves a tag.
      Prints `MERGE_SHA=<sha>` and either `TAG_CUT=<tag>` or
      `TAG_SKIPPED=<tag>` to stdout.

  publish-gh-release TAG --repo OWNER/REPO --notes-file PATH
      GH-release variant only (Mode B): un-drafts an existing release for
      TAG, or creates one from --notes-file if none exists yet. Ported from
      SKILL.md Step 1.5 Part 2 Mode B's `gh release edit ... || gh release
      create ...` fallback. Does NOT cut the git tag itself — run `cut-tag`
      first; the tag push is load-bearing for currency independent of this
      human-facing release object (see SKILL.md prose at that step).

  clone-merge --into BRANCH --from REF [--repo-root PATH] [--push]
      Merges REF into BRANCH inside a disposable clone under <repo>/scratch/,
      so peers' staged files in the shared tree (which make `git merge` there
      refuse, and which no session may stash) never block a merge. REF is
      resolved in the main repo (fetch first for a remote tip). On success the
      main repo's BRANCH is fast-forwarded from the clone (git refuses that when
      BRANCH is checked out; then the printed `FF_PENDING=` command does it),
      `--push` pushes BRANCH to origin, and the clone is deleted. On conflict
      the clone is KEPT for resolution and its path printed (`CLONE=`), exit 1.
      Prints `MERGE_SHA=<sha>`.

Negative-spec:
  - Does NOT read coordinator.local.md itself for `cut-tag`/`publish-gh-release`
    — `resolve-tag-prefix` is a separate, explicit step; callers compose the
    full tag string (`<prefix>vX.Y.Z`) before calling `cut-tag`.
  - Does NOT run `gh release` from `cut-tag` — the two are separate
    subcommands so a Mode-A (git-tag-only) caller never touches `gh`.
  - Does NOT default `--merge-ref` resolution to unpeeled `git rev-parse
    <tag>` — an annotated tag's plain rev-parse returns the TAG OBJECT sha,
    not the commit it points at, which would make the "skip if already cut"
    idempotency check always miss and re-attempt `git tag -a` against an
    already-existing tag name (a real failure on retry). Peeling
    (`<tag>^{}`) is required for the stated idempotent-skip behavior.
  - Does NOT force-move an existing tag to a different commit (no `-f` on
    `git tag -a` or `git push`) — matches the source bash exactly. Each
    release cuts a distinct `vX.Y.Z` tag name, so "TAG already exists but at
    a different commit" is not a case this ceremony's design expects; it
    fails loud like the original rather than silently rewriting history.
  - Does NOT run the ancestor assertion unconditionally — `--must-contain`
    is opt-in; omitting it preserves the prior unconditional-cut behavior
    exactly (no new git spawn, no new failure mode) for callers that never
    asked for it.

Spec backlink: coordinator-content-repo coordinator/skills/merging-to-main/SKILL.md Step 1
(recovery-branch dance) and Step 1.5 Part 2 (tag_anchor=git-tag mode C4,
2026-06-01; docs/plans/2026-06-01-version-disclosure-and-boot-currency-hook.md
§ C4; DR-149) + Step 1.5 Part 2 Mode B (default GH-release publish).
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional


def _require_engine_on_path() -> None:
    """The engine root must be on sys.path before a `coordinator_core` import:
    this file is also published into the claude-klabauter mirror, where
    coordinator_core is NOT pip-installed and the interpreter's sys.path[0] is
    this bin/ directory, not the checkout root. Same bootstrap as
    coordinator/bin/coordinator-lesson-add (9b979ee5f)."""
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_engine_on_path

    require_engine_on_path(__file__)


def _no_console_flags() -> dict:
    _require_engine_on_path()
    from coordinator_core.win_portability import no_console_creationflags

    return no_console_creationflags()


_win_portability_flags = _no_console_flags


def _win_portability_passthrough_kwargs() -> dict:
    _require_engine_on_path()
    from coordinator_core.win_portability import no_console_passthrough_kwargs

    return no_console_passthrough_kwargs()


def _run(
    cmd: list[str],
    cwd: Optional[Path] = None,
    env: Optional[dict] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        check=check,
        **_no_console_flags(),
    )


def _die(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(1)


def _branch_mutation_verdict():
    """Import indirection mirroring `session_ensure_branch._branch_mutation_verdict`
    — native import, no subprocess spawn. Isolated so a missing/broken
    coordinator_core install degrades loudly via ImportError at call time
    rather than silently at module load."""
    from coordinator_core.session.worktree_safety import branch_mutation_verdict

    return branch_mutation_verdict


# ---------------------------------------------------------------------------
# recovery-branch
# ---------------------------------------------------------------------------

def _default_branch_name() -> str:
    host = socket.gethostname().lower()
    today = date.today().strftime("%Y-%m-%d")
    return f"work/{host}/{today}"


def cmd_recovery_branch(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else Path.cwd()
    branch = args.branch_name or _default_branch_name()

    branch_mutation_verdict = _branch_mutation_verdict()
    # UNQUALIFIED_BRANCH_CUT, not FRESH_CUT_AT_HEAD: this cut is bundled
    # with a hard reset of main, so it is not content-neutral and takes the
    # unchanged refuse-under-peers path.
    from coordinator_core.session.worktree_safety import UNQUALIFIED_BRANCH_CUT

    verdict = branch_mutation_verdict(
        cwd=str(repo_root), operation=UNQUALIFIED_BRANCH_CUT
    )
    if verdict.outcome != "ok":
        _die(
            "REFUSED-LIVE-PEERS: declining to cut a recovery branch and "
            f"hard-reset main — {verdict.reason}. A branch is a property of "
            "the shared TREE, not this session; recovering main here would "
            "switch every live peer's checkout and reset main out from "
            "under them. Wait for peers to clear, or resolve manually."
        )

    # Spec: docs/plans/2026-09-11-a-python-process-does-not-spawn-a-python-process.md
    # (P055-C3). Was `subprocess.run([sys.executable, sync-main.py], cwd=repo_root)`
    # -- an in-repo Python-for-Python spawn with no isolation reason. `sync_main.main`
    # reads/writes only via `os.getcwd()`-relative git calls (coordinator_core/ops/
    # sync_main.py :: _git), so the caller's `cwd=` kwarg is replicated with a
    # bounded chdir rather than dropped.
    try:
        _require_engine_on_path()
        from coordinator_core.ops.sync_main import main as _sync_main_op
    except (RuntimeError, ImportError):
        sync_rc = 1
    else:
        _prev_cwd = os.getcwd()
        os.chdir(str(repo_root))
        try:
            sync_rc = _sync_main_op([])
        finally:
            os.chdir(_prev_cwd)
    if sync_rc != 0:
        _die(
            "sync-main.py failed — local main has diverged. "
            "Investigate before creating a recovery branch."
        )

    override_env = dict(os.environ)
    override_env["COORDINATOR_OVERRIDE_BRANCH"] = "1"

    def _override(reason: str) -> dict:
        env = dict(override_env)
        env["COORDINATOR_OVERRIDE_BRANCH_REASON"] = reason
        return env

    checkout_new = _run(
        ["git", "checkout", "-b", branch],
        cwd=repo_root,
        env=_override("merging-to-main step 1 create recovery branch"),
        check=False,
    )
    if checkout_new.returncode != 0:
        _die(f"git checkout -b {branch} failed: {checkout_new.stderr.strip()}")

    push = _run(
        ["git", "push", "origin", branch, "--set-upstream"],
        cwd=repo_root,
        check=False,
    )
    if push.returncode != 0:
        _die(f"git push origin {branch} --set-upstream failed: {push.stderr.strip()}")

    checkout_main = _run(
        ["git", "checkout", "main"],
        cwd=repo_root,
        env=_override("merging-to-main step 1 checkout main for reset"),
        check=False,
    )
    if checkout_main.returncode != 0:
        _die(f"git checkout main failed: {checkout_main.stderr.strip()}")

    reset = _run(
        ["git", "reset", "--hard", "origin/main"],
        cwd=repo_root,
        check=False,
    )
    if reset.returncode != 0:
        _die(f"git reset --hard origin/main failed: {reset.stderr.strip()}")

    checkout_branch = _run(
        ["git", "checkout", branch],
        cwd=repo_root,
        env=_override("merging-to-main step 1 return to work branch"),
        check=False,
    )
    if checkout_branch.returncode != 0:
        _die(f"git checkout {branch} failed: {checkout_branch.stderr.strip()}")

    print(f"BRANCH={branch}")
    return 0


# ---------------------------------------------------------------------------
# resolve-tag-prefix
# ---------------------------------------------------------------------------

def resolve_tag_prefix(config_path: Path) -> str:
    """Port of the awk one-liner in SKILL.md Step 1.5 Part 2 Mode A.

    Scans only the first YAML frontmatter block (between the first two lone
    `---` fence lines). Returns the first `tag_prefix:` value found there,
    with any inline `# ...` comment stripped, or "" if absent. Raises
    SystemExit(1) (fail-loud) if the value is quoted — quoting is an
    authoring error, not a value this CLI should silently interpret.
    """
    text = config_path.read_text(encoding="utf-8")
    fence_count = 0
    for line in text.splitlines():
        stripped_line = line.rstrip()
        if stripped_line == "---":
            fence_count += 1
            if fence_count >= 2:
                break
            continue
        if fence_count == 1 and line.startswith("tag_prefix:"):
            value = line.split(":", 1)[1]
            # Strip a trailing inline comment ("  # ...") the same way the
            # awk sub(/[ \t]+#.*$/, "", v) did.
            hash_idx = value.find("#")
            if hash_idx != -1 and (hash_idx == 0 or value[hash_idx - 1] in " \t"):
                value = value[:hash_idx]
            value = value.strip()
            if "'" in value or '"' in value:
                _die(
                    f"FATAL: tag_prefix in {config_path} must be unquoted "
                    f"(got: {value})"
                )
            return value
    return ""


def cmd_resolve_tag_prefix(args: argparse.Namespace) -> int:
    prefix = resolve_tag_prefix(Path(args.config))
    print(prefix)
    return 0


# ---------------------------------------------------------------------------
# cut-tag
# ---------------------------------------------------------------------------

def _peeled_tag_sha(repo_root: Path, tag: str) -> Optional[str]:
    result = _run(
        ["git", "rev-parse", f"{tag}^{{}}"],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _remote_tag_sha(repo_root: Path, tag: str) -> Optional[str]:
    """Commit sha `origin` has for `tag` (peeled), or None when absent."""
    result = _run(
        ["git", "ls-remote", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        _die(f"git ls-remote origin {tag} failed: {result.stderr.strip()}")
    shas: dict[str, str] = {}
    for line in result.stdout.splitlines():
        sha, _, ref = line.partition("	")
        shas[ref.strip()] = sha.strip()
    return shas.get(f"refs/tags/{tag}^{{}}") or shas.get(f"refs/tags/{tag}")


def _merge_commit_of_pr(repo_root: Path, pr: str) -> str:
    """Merge commit `gh` reports for PR `pr` (merge, squash, or rebase merge
    all populate `mergeCommit.oid`). Dies when `gh` is absent or the PR is
    not merged yet."""
    try:
        result = _run(
            ["gh", "pr", "view", pr, "--json", "mergeCommit", "-q", ".mergeCommit.oid"],
            cwd=repo_root,
            check=False,
        )
    except FileNotFoundError:
        _die("`gh` is not on PATH — cannot resolve the PR merge commit.")
    sha = result.stdout.strip()
    if result.returncode != 0:
        _die(f"gh pr view {pr} failed: {result.stderr.strip()}")
    if not sha or sha == "null":
        _die(f"PR {pr} has no merge commit yet — cut the tag after the merge lands.")
    return sha


def _assert_is_ancestor(repo_root: Path, commit: str, must_contain: str) -> None:
    """Fail loud (no tag mutation) unless `commit` is an ancestor of
    `must_contain` — i.e. `must_contain` actually contains the merge."""
    check = _run(
        ["git", "merge-base", "--is-ancestor", commit, must_contain],
        cwd=repo_root,
        check=False,
    )
    if check.returncode != 0:
        _die(
            f"{commit} is not an ancestor of {must_contain} — refusing to "
            f"cut a tag for a commit that {must_contain} does not contain."
        )


def _next_free_hint(
    repo_root: Path,
    tag: str,
    pr: Optional[str],
    fetch_ref: str,
    merge_ref: Optional[str],
    must_contain: Optional[str],
) -> str:
    """Refusal-path advice: one batched `git ls-remote --tags origin`, then the
    first free patch tag and the exact rerun command."""
    _require_engine_on_path()
    from coordinator_core.merge_assemble import next_free_patch_tag, parse_ls_remote_tags

    listing = _run(["git", "ls-remote", "--tags", "origin"], cwd=repo_root, check=False)
    taken = parse_ls_remote_tags(listing.stdout) if listing.returncode == 0 else {tag}
    free = next_free_patch_tag(tag, taken | {tag})
    if free is None:
        return "Pick a new version or resolve by hand."
    parts = ["merge-recovery-and-tag-cut.py", "cut-tag", free]
    if pr is not None:
        parts += ["--pr", pr]
    if merge_ref is not None:
        parts += ["--merge-ref", merge_ref]
    if must_contain is not None:
        parts += ["--must-contain", must_contain]
    if fetch_ref != "main":
        parts += ["--fetch-ref", fetch_ref]
    return f"Next free patch tag: {free}. Rerun: {' '.join(parts)}"


def cut_tag(
    repo_root: Path,
    tag: str,
    fetch_ref: str = "main",
    merge_ref: Optional[str] = None,
    must_contain: Optional[str] = None,
    pr: Optional[str] = None,
) -> tuple[bool, str]:
    """Idempotent annotated-tag cut + push. Returns (cut, merge_sha).

    `cut` is True iff the tag was (re)created and pushed this call; False
    means the tag already pointed at merge_sha (idempotent skip).

    When `must_contain` is given, asserts merge_sha is an ancestor of it
    before either cutting or skipping — see module docstring.
    """
    fetch = _run(["git", "fetch", "origin", fetch_ref], cwd=repo_root, check=False)
    if fetch.returncode != 0:
        _die(f"git fetch origin {fetch_ref} failed: {fetch.stderr.strip()}")

    if pr is not None:
        merge_ref = _merge_commit_of_pr(repo_root, pr)

    # No explicit merge_ref: the tip just fetched, not a tracking ref that a
    # refspec-less or single-branch remote leaves stale.
    resolved_ref = merge_ref or "FETCH_HEAD"
    rev = _run(["git", "rev-parse", f"{resolved_ref}^{{commit}}"], cwd=repo_root, check=False)
    if rev.returncode != 0:
        _die(f"git rev-parse {resolved_ref} failed: {rev.stderr.strip()}")
    merge_sha = rev.stdout.strip()

    if must_contain is not None:
        _assert_is_ancestor(repo_root, merge_sha, must_contain)

    remote = _remote_tag_sha(repo_root, tag)
    if remote is not None and remote != merge_sha:
        _die(
            f"REFUSED: tag {tag} already exists on origin at {remote}, not "
            f"{merge_sha} — a tag is never retargeted. "
            + _next_free_hint(repo_root, tag, pr, fetch_ref, merge_ref, must_contain)
        )

    existing = _peeled_tag_sha(repo_root, tag)
    if existing is not None and existing != merge_sha:
        _die(f"REFUSED: local tag {tag} points at {existing}, not {merge_sha}.")
    if existing is None:
        tag_create = _run(
            ["git", "tag", "-a", tag, merge_sha, "-m", tag],
            cwd=repo_root,
            check=False,
        )
        if tag_create.returncode != 0:
            _die(f"git tag -a {tag} {merge_sha} failed: {tag_create.stderr.strip()}")
    elif remote == merge_sha:
        return False, merge_sha

    tag_push = _run(["git", "push", "origin", tag], cwd=repo_root, check=False)
    if tag_push.returncode != 0:
        _die(f"git push origin {tag} failed: {tag_push.stderr.strip()}")

    return True, merge_sha


def cmd_cut_tag(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else Path.cwd()
    cut, merge_sha = cut_tag(
        repo_root,
        args.tag,
        fetch_ref=args.fetch_ref,
        merge_ref=args.merge_ref,
        must_contain=args.must_contain,
        pr=args.pr,
    )
    print(f"MERGE_SHA={merge_sha}")
    print(f"TAG_CUT={args.tag}" if cut else f"TAG_SKIPPED={args.tag}")
    return 0


# ---------------------------------------------------------------------------
# publish-gh-release
# ---------------------------------------------------------------------------

def publish_gh_release(tag: str, repo: str, notes_file: Path) -> None:
    """gh release edit-or-create fallback, ported verbatim from Mode B.

    `git push origin <tag>` (via cut_tag above) is load-bearing for
    currency and must already have happened; `gh release` is purely
    human-facing discoverability layered on top.
    """
    edit = subprocess.run(
        [
            "gh", "release", "edit", tag,
            "--repo", repo,
            "--draft=false",
            "--latest",
        ],
        capture_output=True,
        text=True,
        **_no_console_flags(),
    )
    if edit.returncode == 0:
        return

    create = subprocess.run(
        [
            "gh", "release", "create", tag,
            "--repo", repo,
            "--latest",
            "--notes-file", str(notes_file),
        ],
        capture_output=True,
        text=True,
        **_no_console_flags(),
    )
    if create.returncode != 0:
        _die(
            "gh release edit and gh release create both failed:\n"
            f"edit: {edit.stderr.strip()}\ncreate: {create.stderr.strip()}"
        )


def cmd_plan_tag(args: argparse.Namespace) -> int:
    print(f"TAG_PLANNED={args.tag}")
    return 0


def cmd_publish_gh_release(args: argparse.Namespace) -> int:
    publish_gh_release(args.tag, args.repo, Path(args.notes_file))
    return 0


# ---------------------------------------------------------------------------
# clone-merge
# ---------------------------------------------------------------------------

def _rmtree(path: Path) -> None:
    """A --local clone's pack files are read-only on Windows; clear the bit and retry."""
    import shutil
    import stat

    def _retry(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onexc=_retry) if sys.version_info >= (3, 12) else shutil.rmtree(
        path, onerror=_retry
    )


def clone_merge(repo_root: Path, into: str, source: str, push: bool) -> int:
    resolved = _run(["git", "rev-parse", "--verify", f"{source}^{{commit}}"], cwd=repo_root, check=False)
    if resolved.returncode != 0:
        _die(f"clone-merge: --from {source!r} does not resolve to a commit in {repo_root}")
    source_sha = resolved.stdout.strip()

    stamp = f"{os.getpid()}-{date.today():%Y%m%d}"
    clone = repo_root / "scratch" / f"clone-merge-{stamp}"
    cloned = _run(
        ["git", "clone", "--local", "--quiet", "--branch", into, str(repo_root), str(clone)], check=False
    )
    if cloned.returncode != 0:
        _die(f"clone-merge: cannot clone {into!r} into {clone}: {cloned.stderr.strip()}")

    merged = _run(
        ["git", "merge", "--no-ff", "--no-edit", "-m", f"Merge {source} into {into}", source_sha],
        cwd=clone,
        check=False,
    )
    if merged.returncode != 0:
        print(f"CLONE={clone.as_posix()}")
        _die(
            f"clone-merge: merging {source} into {into} stopped (clone kept for resolution):\n"
            f"{(merged.stdout + merged.stderr).strip()}"
        )
    merge_sha = _run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip()

    if push:
        url = _run(["git", "remote", "get-url", "origin"], cwd=repo_root).stdout.strip()
        pushed = _run(["git", "push", url, f"HEAD:refs/heads/{into}"], cwd=clone, check=False)
        if pushed.returncode != 0:
            print(f"CLONE={clone.as_posix()}")
            _die(f"clone-merge: push of {into} refused (clone kept): {pushed.stderr.strip()}")

    synced = _run(["git", "fetch", "--quiet", str(clone), f"{into}:{into}"], cwd=repo_root, check=False)
    if synced.returncode != 0:
        # BRANCH is checked out in the shared tree; only a fast-forward there is safe.
        print(f"FF_PENDING=git merge --ff-only {merge_sha}")
    _rmtree(clone)
    print(f"MERGE_SHA={merge_sha}")
    return 0


def cmd_clone_merge(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else Path.cwd()
    return clone_merge(repo_root.resolve(), args.into, args.source, args.push)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="merge-recovery-and-tag-cut",
        description=(
            "Recovery-branch dance + idempotent annotated-tag cut for "
            "/merging-to-main."
        ),
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_recovery = sub.add_parser(
        "recovery-branch",
        help="sync main, cut a fresh work/<host>/<date> branch, reset main",
    )
    p_recovery.add_argument("--repo-root", default=None)
    p_recovery.add_argument("--branch-name", default=None)
    p_recovery.set_defaults(func=cmd_recovery_branch)

    p_prefix = sub.add_parser(
        "resolve-tag-prefix",
        help="parse tag_prefix: from a coordinator.local.md-shaped frontmatter",
    )
    p_prefix.add_argument("--config", required=True)
    p_prefix.set_defaults(func=cmd_resolve_tag_prefix)

    p_cut = sub.add_parser(
        "cut-tag",
        help="idempotent annotated-tag cut + push",
    )
    p_cut.add_argument("tag")
    p_cut.add_argument("--repo-root", default=None)
    p_cut.add_argument("--fetch-ref", default="main")
    p_cut.add_argument("--merge-ref", default=None)
    p_cut.add_argument("--must-contain", default=None)
    p_cut.add_argument("--pr", default=None)
    p_cut.set_defaults(func=cmd_cut_tag)

    p_plan = sub.add_parser(
        "plan-tag",
        help="pre-merge: record the computed tag; creates and pushes nothing",
    )
    p_plan.add_argument("tag")
    p_plan.set_defaults(func=cmd_plan_tag)

    p_release = sub.add_parser(
        "publish-gh-release",
        help="un-draft or create the GH release for an already-cut tag",
    )
    p_release.add_argument("tag")
    p_release.add_argument("--repo", required=True)
    p_release.add_argument("--notes-file", required=True)
    p_release.set_defaults(func=cmd_publish_gh_release)

    p_clone = sub.add_parser(
        "clone-merge",
        help="merge a ref into a branch in a scratch clone, clear of the shared tree's index",
    )
    p_clone.add_argument("--into", required=True)
    p_clone.add_argument("--from", dest="source", required=True)
    p_clone.add_argument("--repo-root", default=None)
    p_clone.add_argument("--push", action="store_true")
    p_clone.set_defaults(func=cmd_clone_merge)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
