"""percolate-push.py — the operator's one short command for the push
step `percolate-round.py` deliberately never automates.

Spec backlink: state/handoffs/2026-08-13-one-command-publish.md, shape 1
("Keep the human press, remove the typing"). `percolate-round.py`'s module
docstring names the never-push constraint THE LOAD-BEARING CONSTRAINT
(AC9/AC10): that CLI prints a push command for the operator to run rather
than running it. This module IS that operator-run command — it resolves
the mirror path the same way `percolate-round.py` does (via
`percolate-gate.py`, by subprocess, never reimplemented), so the operator
types `percolate-push <target>` instead of a hand-typed absolute path.

DR-301 (`docs/decisions/DR-301-agent-initiated-publish-push-is-automatable.md`)
ruled that an agent-initiated push to a publish mirror is high-consequence,
not irreversible-harm-class, and moved the gate off the human keystroke
(the `COORDINATOR_SESSION_ID` refusal this module used to carry) onto
**round evidence**, verified here at push time. After this DR landed, no
mechanism gates an agent-initiated publish push through this module except
the two predicates below — `bump_foreign_repo_write`
(coordinator_core/bash_guards/bump_foreign_repo_write.py) is a Bash-surface
guard and this push never transits Bash, so it does not reach this path at
all; it stays armed for its own unrelated purpose, unweakened, but is not
what licenses this one.

Negative-spec (do not restore any of this as a "fix"):
  - Does NOT create, clear, or touch any `allow-xrepo-write` marker,
    anywhere, under any name. `bump_foreign_repo_write` denying an
    unauthorized push into a publish mirror is the guard working as
    designed (coordinator_core/bash_guards/bump_foreign_repo_write.py) —
    this module does not disarm it, and does not ask the operator to.
  - Does NOT run the superseded `COORDINATOR_SESSION_ID` check any more
    (DR-301 supersedes it, and Anti-scope forbids simply deleting it
    without a replacement gate — the two predicates below are that
    replacement). In `_cmd_push`, both predicates run in the same place
    the old session-id check used to run: AFTER `_resolve_percolate_root`,
    `_branch0_gate`, and `_resolve_dest` (target/dest resolution has to
    happen first to know which dest tree to inspect) — a prior draft of
    this docstring claimed the old check ran "before any other work,
    root/target resolution included", which was never true of the code;
    this rewrite does not carry that mismatch forward.
  - Does NOT push if the dest working tree is dirty (`_check_dest_state`)
    — this is now a refusal, not a WARN, because a dirty dest means an
    in-flight round did not finish rather than unrelated residue. Fails
    closed: a non-zero `git status` return code refuses too, and surfaces
    git's stderr, rather than being treated as a clean tree.
  - Does NOT push if a round-failure marker is present at
    `setup/percolate-state/<target>.round-failed.json`
    (percolate_root-relative, C3's marker — this module only reads it,
    never writes it). Fails closed here too: a marker that exists but
    fails to parse refuses, same as a marker naming a real failure — it
    is never treated as absent.
  - Does NOT reimplement target/dest resolution — shells out to
    `percolate-gate.py resolve-root`/`branch0-gate`/`list-targets`
    exactly as `percolate-round.py` does, and does not edit
    `percolate-gate.py`.
  - Does NOT fix the ~102-file mirror-residue problem or the
    `resolve-claude-klabauter/` declined-paths defect (handoff's Anti-scope) — the
    destination-state check below is a clean/dirty gate, never a
    pathspec-narrowing survey.

Branch-topology leg (AC8, PM ruling 2, 2026-08-14: open-and-merge, decided
not deferred). When the dest's checked-out branch IS the remote's default
branch, publishing ends at the push and `gh` is never invoked — this is
dormant but load-bearing for `claude-klabauter` today (on `main` tracking
`origin/main`). The default branch is resolved via
`git -C <dest> symbolic-ref refs/remotes/origin/HEAD` — a `git` call, not
`gh` — specifically so the dormant/default-branch case never touches `gh`
at all (tests assert this on the subprocess, not just the exit code). A
declared release channel (`_RELEASE_CHANNELS`,
docs/reference/klabauter-release-channels.md) takes the identical
push-only, no-`gh` path — a publish round landing on `candidate` must
never open or merge a PR into `main`. An unrecognised branch is neither
and still takes the PR path below.
When the checked-out branch is NOT the default and NOT a declared
channel, this module opens a PR via `gh pr create` and merges it with
`gh pr merge <branch> --merge` once the push (already gated on DR-301's
two predicates) has landed. `--merge` (not
`--squash`/`--rebase`) is the deliberate choice: it preserves the exact
commit SHAs the round's own gate evidence (CI smoke, declined_paths, etc.)
already validated, rather than rewriting them into a new squashed/rebased
commit the gate never saw. `gh` is invoked via ordinary argv-list
`subprocess.run(["gh", ...], ...)` calls — the identical shape already
used for `git` — and needs no `docs/reference/shell-out-carve-outs.md` row
(that doc governs shell-interpreter spawns only, per its own scope
statement; extended by PM ruling only, never in-chunk). Before opening or
merging a PR, `gh auth status` is checked for the `repo` scope explicitly
— never inferred from ssh authentication, since `gh` scopes are
per-feature and independently requestable — and a missing scope refuses
loudly with the exact remediation command (`gh auth refresh -s repo`). Any
`gh` failure (auth check, `pr create`, `pr merge`) fails the publish
loudly; it is never treated as a silent success.

Usage:
    percolate-push.py <target> [--percolate-root <path>]

Exit codes:
    0 — `git -C <dest> push` ran and exited 0 (and, on a non-default
        branch, the PR was opened and merged too), or dest was already in
        sync with its upstream and nothing was pushed.
    1 — `git -C <dest> push` ran and exited non-zero (forwarded), or the
        default branch could not be resolved, or `gh` (auth check, `pr
        create`, `pr merge`) failed.
    2 — usage error (bad argv, target not resolvable), or refused because
        the dest tree is dirty / has no upstream configured / its status
        could not be read, or because a round-failure marker is present
        (or unparseable) for this target — DR-301's two replacement
        predicates.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

_BIN_DIR = Path(__file__).resolve().parent
_PERCOLATE_GATE = _BIN_DIR / "percolate-gate.py"

_EXIT_OK = 0
_EXIT_FAIL = 1
_EXIT_USAGE = 2

# Declared release channels (docs/reference/klabauter-release-channels.md,
# C5/C1). A branch in this set is push-only, `gh` never invoked — same as
# the remote default branch. Membership is closed and explicit: an
# unrecognised branch is NOT a channel and must not silently become one.
_RELEASE_CHANNELS = frozenset({"candidate"})


def _run(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    return subprocess.run(cmd, **kwargs)


def _resolve_percolate_root(override: Optional[str]) -> Optional[str]:
    if override:
        return override
    result = _run([sys.executable, str(_PERCOLATE_GATE), "resolve-root"])
    if result.returncode != 0:
        print("percolate-push: could not resolve PERCOLATE_ROOT:", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        return None
    return result.stdout.strip()


def _branch0_gate(target: str, percolate_root: str) -> Optional[str]:
    result = _run(
        [sys.executable, str(_PERCOLATE_GATE), "branch0-gate", target, "--percolate-root", percolate_root]
    )
    if result.returncode != 0:
        print(f"percolate-push: target '{target}' is not ready:", file=sys.stderr)
        print(result.stdout.strip(), file=sys.stderr)
        return None
    return result.stdout.strip()


def _resolve_dest(target: str, percolate_root: str) -> Optional[str]:
    result = _run(
        [sys.executable, str(_PERCOLATE_GATE), "list-targets", "--percolate-root", percolate_root, "--target", target]
    )
    if result.returncode != 0 or not result.stdout.strip():
        print(f"percolate-push: could not resolve dest for target '{target}'.", file=sys.stderr)
        return None
    return result.stdout.strip()


def _check_dest_state(dest: str) -> Tuple[Optional[str], bool, Optional[str]]:
    """DR-301 predicate 1 — dest working tree must be clean AND have an
    upstream configured.

    Returns `(refusal_message, has_commits_to_push, branch_head)`.
    `refusal_message` is `None` only when the dest is clean and has an
    upstream; `has_commits_to_push` and `branch_head` are only meaningful
    then.

    Fails CLOSED: a non-zero `git status` return code refuses (with git's
    stderr surfaced), never falls through as if the tree were clean —
    replaces the old `_warn_if_dirty`, which treated `returncode != 0` as
    clean and only warned. `--untracked-files=normal` is passed explicitly
    so a dest-side `-uno` / `status.showUntrackedFiles=no` setting cannot
    make an unclean tree read as clean.

    Latent-bug fix (C4's `29c7385a5`, this chunk's spec): when the dest has
    NO upstream configured at all, `# branch.ab` is absent entirely from
    `--porcelain=v2 --branch` output, so `ahead` silently stayed `0` and
    the caller reported "already in sync — nothing to push", a false
    success (nothing was ever published). This is now distinguished from
    "zero commits ahead of a configured upstream" via the presence of a
    `# branch.upstream` line, and the no-upstream case is a loud refusal
    naming what is missing, never a silent OK.
    """
    result = _run(
        [
            "git", "-C", dest, "--no-optional-locks", "status",
            "--porcelain=v2", "--branch", "--untracked-files=normal",
        ]
    )
    if result.returncode != 0:
        return (
            f"percolate-push: could not read status of {dest} — refusing to push.\n"
            + result.stderr.strip(),
            False,
            None,
        )
    lines = result.stdout.splitlines()
    dirty_lines = [ln for ln in lines if ln and not ln.startswith("#")]
    if dirty_lines:
        return (
            f"percolate-push: {dest} has {len(dirty_lines)} uncommitted path(s) — refusing to push.",
            False,
            None,
        )
    branch_head: Optional[str] = None
    has_upstream = False
    ahead = 0
    for ln in lines:
        if ln.startswith("# branch.head "):
            branch_head = ln.split(" ", 2)[2].strip()
        elif ln.startswith("# branch.upstream "):
            has_upstream = True
        elif ln.startswith("# branch.ab "):
            for token in ln.split():
                if token.startswith("+"):
                    # Review: coordinator:code-reviewer — a `# branch.ab`
                    # line that fails to parse must refuse, not silently
                    # downgrade to "0 commits ahead" (a false success).
                    try:
                        ahead = int(token[1:])
                    except ValueError:
                        return (
                            f"percolate-push: {dest}'s `# branch.ab` line "
                            f"did not parse as expected ({ln!r}) — refusing "
                            "to push rather than assuming nothing to push.",
                            False,
                            branch_head,
                        )
    if not has_upstream:
        # Review: coordinator:code-reviewer — detached HEAD has no "current
        # branch", so the upstream-refusal text (and its `git push -u
        # <remote> <branch>` remediation) is misleading there.
        if branch_head == "(detached)":
            return (
                f"percolate-push: {dest} is in a detached HEAD state — "
                "refusing to push. Check out a branch with an upstream "
                f"configured (`git -C {dest} checkout <branch>`) before "
                "automating this target.",
                False,
                branch_head,
            )
        return (
            f"percolate-push: {dest} has no upstream configured for its "
            f"current branch — refusing to push. Set an upstream "
            f"(`git -C {dest} push -u <remote> <branch>` once, by hand) "
            "before automating this target.",
            False,
            branch_head,
        )
    return (None, ahead > 0, branch_head)


def _round_failure_marker_path(target: str, percolate_root: str) -> Path:
    """percolate_root-relative, same directory and naming convention as
    `<target>.lastsync` (percolate-gate.py) and `<target>.delta-state.json`
    (publish.py::_delta_state_path). C3 writes this file; this module only
    reads it."""
    return Path(percolate_root) / "setup" / "percolate-state" / f"{target}.round-failed.json"


def _check_round_failure_marker(target: str, percolate_root: str) -> Optional[str]:
    """DR-301 predicate 2 — no round-failure marker naming this target.

    Fails CLOSED: a marker that exists but cannot be parsed refuses, same
    as one naming a real failure — never treated as absent.
    """
    path = _round_failure_marker_path(target, percolate_root)
    if not path.exists():
        return None
    how_to_clear = (
        "Run `percolate-round <target>` again to a clean PASS, which clears "
        "this marker before publishing."
    )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        reason = data["reason"]
        sha = data["sha"]
    except Exception as exc:
        return (
            f"percolate-push: round-failure marker at {path} is present but "
            f"could not be read ({exc}) — refusing to push.\n{how_to_clear}"
        )
    return (
        f"percolate-push: round-failure marker present for '{target}' "
        f"(reason={reason}, sha={sha}) — refusing to push.\n{how_to_clear}"
    )


_ORIGIN_HEAD_REF = "refs/remotes/origin/HEAD"
_ORIGIN_HEAD_PREFIX = "refs/remotes/origin/"


def _resolve_default_branch(dest: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve the remote's default branch via `git`, never `gh` — this is
    what keeps the default-branch (dormant) case from invoking `gh` at
    all (AC8's dormancy half). Returns `(branch_name, refusal_message)`;
    exactly one is non-`None`.
    """
    result = _run(["git", "-C", dest, "symbolic-ref", _ORIGIN_HEAD_REF])
    if result.returncode != 0:
        return (
            None,
            f"percolate-push: could not resolve {dest}'s remote default "
            f"branch via `git symbolic-ref {_ORIGIN_HEAD_REF}` — refusing "
            "rather than guessing whether a PR is needed.\n"
            + result.stderr.strip(),
        )
    ref = result.stdout.strip()
    if not ref.startswith(_ORIGIN_HEAD_PREFIX):
        return (
            None,
            f"percolate-push: unexpected `git symbolic-ref` output for "
            f"{dest}'s remote default branch: {ref!r} — refusing rather "
            "than guessing whether a PR is needed.",
        )
    return ref[len(_ORIGIN_HEAD_PREFIX):], None


def _parse_gh_token_scopes(auth_status_output: str) -> Optional[List[str]]:
    """Scopes named on `gh auth status`'s `Token scopes:` line, as exact
    tokens. `None` when no such line is present.

    Negative-spec: a substring search over the whole output is NOT
    equivalent and must not be restored. `public_repo` and
    `admin:repo_hook` both CONTAIN "repo" while granting strictly less
    than `repo` — `public_repo` cannot merge a PR on a private repository
    — so a substring test fails OPEN on exactly the tokens this check
    exists to reject.
    """
    for line in auth_status_output.splitlines():
        _, sep, rest = line.partition("Token scopes:")
        if not sep:
            continue
        return [tok.strip().strip("'\"") for tok in rest.split(",") if tok.strip()]
    return None


def _resolve_remote_host(dest: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve the hostname of `dest`'s `origin` remote, so the `gh auth
    status` scope check below can be scoped to the account/host that will
    actually own the PR calls, not whichever account's section happens to
    print first. Returns `(host, refusal_message)`; exactly one is
    non-`None`.

    Review: coordinator:code-reviewer — a multi-host or multi-account `gh`
    login prints one `Token scopes:` line per account section;
    unscoped, `_parse_gh_token_scopes` could read an unrelated account's
    scopes. Refuses loudly rather than guessing when the remote URL can't
    be parsed — a false refuse names its own remedy, a false pass does not.
    """
    result = _run(["git", "-C", dest, "remote", "get-url", "origin"])
    if result.returncode != 0:
        return (
            None,
            f"percolate-push: could not resolve {dest}'s `origin` remote "
            "URL — refusing rather than checking `gh` scopes against the "
            "wrong account.\n" + result.stderr.strip(),
        )
    url = result.stdout.strip()
    host: Optional[str] = None
    if url.startswith("git@"):
        rest = url[len("git@"):]
        host = rest.split(":", 1)[0] or None
    else:
        match = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/]+)/", url)
        if match:
            netloc = match.group(1)
            netloc = netloc.rsplit("@", 1)[-1]
            host = netloc.split(":", 1)[0] or None
    if not host:
        return (
            None,
            f"percolate-push: could not parse a host from {dest}'s "
            f"`origin` remote URL ({url!r}) — refusing rather than "
            "checking `gh` scopes against the wrong account.",
        )
    return host, None


def _check_gh_repo_scope(dest: str) -> Optional[str]:
    """Verify the `repo` scope explicitly via `gh auth status` rather than
    inferring PR create/merge capability from ssh authentication — `gh`
    scopes are per-feature and independently requestable. Scoped to
    `dest`'s own remote host (`--hostname`) so a multi-host/multi-account
    `gh` login cannot report an unrelated account's scopes."""
    host, host_refusal = _resolve_remote_host(dest)
    if host_refusal:
        return host_refusal
    result = _run(["gh", "auth", "status", "--hostname", host])
    combined = (result.stdout or "") + (result.stderr or "")
    remediation = "Run: gh auth refresh -s repo"
    if result.returncode != 0:
        return (
            "percolate-push: `gh auth status` failed — cannot verify the "
            f"'repo' scope needed to open/merge a PR.\n{combined.strip()}\n"
            f"{remediation}"
        )
    scopes = _parse_gh_token_scopes(combined)
    if scopes is None:
        return (
            "percolate-push: `gh auth status` reported no 'Token scopes:' "
            "line — cannot verify the 'repo' scope needed to open/merge a "
            f"PR.\n{combined.strip()}\n{remediation}"
        )
    if "repo" not in scopes:
        return (
            "percolate-push: gh token scopes "
            f"({', '.join(scopes) or 'none'}) do not include 'repo', which "
            f"is needed to open/merge a PR.\n{remediation}"
        )
    return None


def _existing_open_pr_exists(dest: str, branch: str) -> Tuple[bool, Optional[str]]:
    """Ask `gh` directly whether an open PR already exists for `branch`,
    rather than inferring it from `gh pr create`'s error prose (§
    `_open_and_merge_pr`) — `gh`'s error text is not a contract, so
    substring-matching a phrase like "already exists" in it is guessing.

    Returns `(exists, refusal)`. `refusal` is set (and `exists` is
    meaningless) when `gh pr list` itself fails — that failure is loud,
    never treated as "no PR exists".
    """
    result = _run(
        ["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number"],
        cwd=dest,
    )
    if result.returncode != 0:
        return False, (
            f"percolate-push: `gh pr list` failed while checking for an "
            f"existing open PR on branch {branch} — refusing to report "
            "success.\n" + (result.stderr or "").strip()
        )
    try:
        entries = json.loads(result.stdout or "[]")
    except ValueError:
        return False, (
            "percolate-push: `gh pr list` returned unparseable JSON while "
            f"checking for an existing open PR on branch {branch} — "
            "refusing to report success.\n" + (result.stdout or "").strip()
        )
    return bool(entries), None


def _open_and_merge_pr(dest: str, branch: str, target: str) -> Optional[str]:
    """Open a PR for `branch` and merge it once opened. `gh` failure at
    either step fails the publish loudly rather than reporting success.

    Merge strategy: `--merge` (not `--squash`/`--rebase`) — deliberately
    chosen so the merged commits are the exact SHAs the round's own gate
    evidence (CI smoke, declined_paths, etc.) already validated, rather
    than a new squashed/rebased commit the gate never inspected.

    A prior run may have already opened the PR and failed at the merge
    step. Rather than inferring that from `gh pr create`'s error text (not
    a contract), this asks `gh pr list` directly whether an open PR
    already exists for `branch` BEFORE attempting `create` — an
    idempotent-retry signal decided by a real query, not a substring
    guess. Every `gh pr create` failure stays loud in every other case.
    """
    already_open, list_refusal = _existing_open_pr_exists(dest, branch)
    if list_refusal:
        return list_refusal
    if not already_open:
        create = _run(["gh", "pr", "create", "--fill", "--head", branch], cwd=dest)
        if create.returncode != 0:
            return (
                f"percolate-push: `gh pr create` failed for target '{target}' "
                f"(branch {branch}) — refusing to report success.\n"
                + create.stderr.strip()
            )
    merge = _run(["gh", "pr", "merge", branch, "--merge"], cwd=dest)
    if merge.returncode != 0:
        return (
            f"percolate-push: `gh pr merge` failed for target '{target}' "
            f"(branch {branch}) — refusing to report success.\n"
            + merge.stderr.strip()
        )
    return None


def _cmd_push(args: argparse.Namespace) -> int:
    target = args.target

    percolate_root = _resolve_percolate_root(args.percolate_root)
    if percolate_root is None:
        return _EXIT_USAGE

    if _branch0_gate(target, percolate_root) is None:
        return _EXIT_USAGE

    dest = _resolve_dest(target, percolate_root)
    if dest is None:
        return _EXIT_USAGE

    # DR-301's two replacement predicates — see module docstring.
    dest_refusal, has_commits_to_push, branch_head = _check_dest_state(dest)
    if dest_refusal:
        print(dest_refusal, file=sys.stderr)
        return _EXIT_USAGE

    marker_refusal = _check_round_failure_marker(target, percolate_root)
    if marker_refusal:
        print(marker_refusal, file=sys.stderr)
        return _EXIT_USAGE

    # Branch-topology leg (AC8) — resolved via `git`, never `gh`, so the
    # dormant/default-branch case never touches `gh` at all. Resolved
    # BEFORE deciding whether to short-circuit on "nothing to push": on a
    # non-default branch, ahead==0 means "already pushed", not "done" —
    # the PR leg still has to run (or resume) on retry. Review:
    # coordinator:code-reviewer P1 — a `has_commits_to_push == False` early
    # return here used to short-circuit the PR leg unconditionally, so a
    # push that succeeded but whose PR leg then failed (default-branch
    # resolution, missing scope, `gh pr create`/`merge`) read as clean
    # success on every subsequent invocation, with the PR never opened or
    # merged.
    default_branch, default_branch_refusal = _resolve_default_branch(dest)
    if default_branch_refusal:
        print(default_branch_refusal, file=sys.stderr)
        return _EXIT_FAIL

    if not has_commits_to_push and (
        branch_head == default_branch or branch_head in _RELEASE_CHANNELS
    ):
        print(
            f"percolate-push: {dest} is already in sync with its upstream — nothing to push.",
            file=sys.stderr,
        )
        return _EXIT_OK

    if has_commits_to_push:
        result = _run(["git", "-C", dest, "push"], capture_output=False)
        if result.returncode != 0:
            return result.returncode

    if branch_head == default_branch or branch_head in _RELEASE_CHANNELS:
        return _EXIT_OK

    scope_refusal = _check_gh_repo_scope(dest)
    if scope_refusal:
        print(scope_refusal, file=sys.stderr)
        return _EXIT_FAIL

    pr_refusal = _open_and_merge_pr(dest, branch_head, target)
    if pr_refusal:
        print(pr_refusal, file=sys.stderr)
        return _EXIT_FAIL

    return _EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="percolate-push",
        description="Push a percolate publish mirror's committed round. Refuses on a dirty dest or a round-failure marker (DR-301).",
    )
    parser.add_argument("target", help="Single registered percolate target name.")
    parser.add_argument(
        "--percolate-root",
        required=False,
        help="Override PERCOLATE_ROOT (default: percolate-gate.py resolve-root).",
    )
    parser.set_defaults(func=_cmd_push)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
