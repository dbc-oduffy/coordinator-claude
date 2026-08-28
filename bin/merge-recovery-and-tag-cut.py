# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""merge-recovery-and-tag-cut.py — naked-Python port of the /merging-to-main
recovery-branch dance and idempotent annotated-tag cut.

Self-contained, self-resolving (Path(__file__)-relative, NO cwd dependence for
its own imports), naked-Python CLI. Ports the residual imperative bash logic
out of DoE-claude's `coordinator/skills/merging-to-main/SKILL.md` Step 1 /
Step 1.5 so the skill can call this CLI by name instead of carrying the logic
inline. This file is the M3/MTM-1 chunk output of that porting pass; the
skill-side repoint (D2) is a later wave and lands in DoE-claude, not here.

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

  cut-tag TAG [--repo-root PATH] [--fetch-ref main] [--merge-ref origin/main]
      Idempotent annotated-tag cut + push: fetches `--fetch-ref` from origin,
      resolves `--merge-ref` to a commit SHA, and only (re)creates + pushes
      the annotated tag when it does not already point at that commit.
      Peels an existing annotated tag (`TAG^{}`) before comparing, so the
      "already at target" skip is a genuine idempotency check against the
      underlying commit — not the tag object's own SHA (see Negative-spec
      below). Ported from SKILL.md Step 1.5 Part 2, both Mode A (git-tag-only)
      and Mode B (GH-release) share this exact tag-cut core; only the
      GH-release publish step (below) differs between the two.
      Prints `MERGE_SHA=<sha>` and either `TAG_CUT=<tag>` or
      `TAG_SKIPPED=<tag>` to stdout.

  publish-gh-release TAG --repo OWNER/REPO --notes-file PATH
      GH-release variant only (Mode B): un-drafts an existing release for
      TAG, or creates one from --notes-file if none exists yet. Ported from
      SKILL.md Step 1.5 Part 2 Mode B's `gh release edit ... || gh release
      create ...` fallback. Does NOT cut the git tag itself — run `cut-tag`
      first; the tag push is load-bearing for currency independent of this
      human-facing release object (see SKILL.md prose at that step).

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

Spec backlink: DoE-claude coordinator/skills/merging-to-main/SKILL.md Step 1
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


def _win_portability_flags() -> dict:
    _require_engine_on_path()
    from coordinator_core.win_portability import no_console_creationflags

    return no_console_creationflags()


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
        **_win_portability_flags(),
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

    sync_main = Path(__file__).resolve().parent / "sync-main.py"
    sync = subprocess.run(
        [sys.executable, str(sync_main)],
        cwd=str(repo_root),
        **_win_portability_passthrough_kwargs(),
    )
    if sync.returncode != 0:
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


def cut_tag(
    repo_root: Path,
    tag: str,
    fetch_ref: str = "main",
    merge_ref: str = "origin/main",
) -> tuple[bool, str]:
    """Idempotent annotated-tag cut + push. Returns (cut, merge_sha).

    `cut` is True iff the tag was (re)created and pushed this call; False
    means the tag already pointed at merge_sha (idempotent skip).
    """
    fetch = _run(["git", "fetch", "origin", fetch_ref], cwd=repo_root, check=False)
    if fetch.returncode != 0:
        _die(f"git fetch origin {fetch_ref} failed: {fetch.stderr.strip()}")

    rev = _run(["git", "rev-parse", merge_ref], cwd=repo_root, check=False)
    if rev.returncode != 0:
        _die(f"git rev-parse {merge_ref} failed: {rev.stderr.strip()}")
    merge_sha = rev.stdout.strip()

    existing = _peeled_tag_sha(repo_root, tag)
    if existing == merge_sha:
        return False, merge_sha

    tag_create = _run(
        ["git", "tag", "-a", tag, merge_sha, "-m", tag],
        cwd=repo_root,
        check=False,
    )
    if tag_create.returncode != 0:
        _die(f"git tag -a {tag} {merge_sha} failed: {tag_create.stderr.strip()}")

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
        **_win_portability_flags(),
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
        **_win_portability_flags(),
    )
    if create.returncode != 0:
        _die(
            "gh release edit and gh release create both failed:\n"
            f"edit: {edit.stderr.strip()}\ncreate: {create.stderr.strip()}"
        )


def cmd_publish_gh_release(args: argparse.Namespace) -> int:
    publish_gh_release(args.tag, args.repo, Path(args.notes_file))
    return 0


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
    p_cut.add_argument("--merge-ref", default="origin/main")
    p_cut.set_defaults(func=cmd_cut_tag)

    p_release = sub.add_parser(
        "publish-gh-release",
        help="un-draft or create the GH release for an already-cut tag",
    )
    p_release.add_argument("tag")
    p_release.add_argument("--repo", required=True)
    p_release.add_argument("--notes-file", required=True)
    p_release.set_defaults(func=cmd_publish_gh_release)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
