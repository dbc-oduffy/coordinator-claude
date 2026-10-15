"""klabauter-promote.py — the deliberate, gated act that moves bits from
the `candidate` release channel onto `main`, the branch consumers get on a
fresh clone.

Spec backlink: docs/plans/2026-08-15-klabauter-release-channels.md, chunk
C3; evidence bar restated verbatim in
docs/reference/klabauter-release-channels.md § "Promotion evidence bar".

A SEPARATE VERB, not a flag on `percolate-push.py`. Rationale (restated
from the plan body): promotion is a deliberate act with its own evidence
bar and its own refusal surface; hanging it off `percolate-push` would put
the act that protects consumers on the same code path as the routine that
runs every round.

REFUSAL BAR — a PM-invoked promotion refuses, naming which predicate
failed, unless predicates 1-4 hold. The PM's invocation is the only trigger.
  1. The mirror dest status is readable and its branch has an upstream
     (`percolate-push.py::_check_dest_state`; uncommitted files never
     refuse, DR-390).
  2. No DR-301 round-failure marker is present
     (`percolate-push.py::_round_failure_marker_path`).
  3. The candidate ref fast-forwards onto `main` — `main` is an ancestor of
     `candidate`. A non-fast-forward is a HARD refusal, never a merge
     commit: the byte-identity property that killed the second-clone
     option (docs/reference/klabauter-release-channels.md § "One-clone
     topology") depends on `main` never diverging from what `candidate`
     already contains.
  4. The candidate tip's `[source-head <hex>]` stamp names a source commit
     whose subject does not start with `WIP`. A committed-fact check at
     promotion (DR-390 keeps publish itself from refusing on source state);
     an unparseable stamp or unresolvable sha fails CLOSED.

Reuse, not reimplementation: `_resolve_dest`, `_check_dest_state`,
`_round_failure_marker_path`, `_resolve_default_branch` are imported from
`percolate-push.py` (loaded by path, under a private module name, same
idiom `percolate-full-payload-proof.py::_load_publish_module` already
uses for a sibling hyphenated entrypoint) rather than copied.

The CLI stays dry-run by default. A bare invocation (`klabauter-promote
<target>` with no `--confirm`) evaluates every predicate against the
`candidate` tip, reports pass/fail for each, and pushes
nothing — promotion moves bits onto a PUBLIC remote and is not reversible
for anyone who has already fetched. Only `--confirm` performs the
fast-forward push of `main`.

`promote_candidate` prints nothing; callers render `PromotionOutcome`.

Negative-spec (do not restore any of this as a "fix"):
  - Does NOT merge, rebase, or otherwise synthesize a new commit onto
    `main` — a non-fast-forward candidate is a hard refusal, never a
    merge commit (predicate 3 above).
  - Does NOT invoke `gh` — promotion is a plain `git push` of a
    fast-forward ref update, not a PR workflow; `percolate-push.py`'s PR
    leg is unrelated to this module.
  - Does NOT gate on elapsed time - promotion timing is the PM's call
    (DR-314, PM ruling 2026-10-15); do not restore a soak floor as a fix.

Usage:
    klabauter-promote.py <target> [--percolate-root <path>] [--confirm]

Exit codes:
    0 — dry-run: predicates 1-4 all passed (nothing pushed),
        or `--confirm`: the fast-forward push of `main` succeeded.
    1 — `--confirm` and the push failed (forwarded git exit code), or the
        default-branch resolution needed to name `main` failed.
    2 — usage error (bad argv, target not resolvable), or refused because
        one or more of predicates 1-4 failed.
"""
import argparse
import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

_BIN_DIR = Path(__file__).resolve().parent
_PERCOLATE_PUSH_PATH = _BIN_DIR / "percolate-push.py"

_EXIT_OK = 0
_EXIT_FAIL = 1
_EXIT_USAGE = 2


def _load_percolate_push_module():
    spec = importlib.util.spec_from_file_location(
        "percolate_push_for_klabauter_promote", _PERCOLATE_PUSH_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_BOOTSTRAPPED_NAMES = (
    "_percolate_push",
    "_run",
    "_resolve_percolate_root",
    "_resolve_dest",
    "_check_dest_state",
    "_round_failure_marker_path",
    "_check_round_failure_marker",
    "_resolve_default_branch",
)


_BOOTSTRAP_DONE = False


def _bootstrap_engine() -> None:
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    try:
        _percolate_push = _load_percolate_push_module()

        _run = _percolate_push._run
        _resolve_percolate_root = _percolate_push._resolve_percolate_root
        _resolve_dest = _percolate_push._resolve_dest
        _check_dest_state = _percolate_push._check_dest_state
        _round_failure_marker_path = _percolate_push._round_failure_marker_path
        _check_round_failure_marker = _percolate_push._check_round_failure_marker
        _resolve_default_branch = _percolate_push._resolve_default_branch

    finally:
        _resolved = locals()
        for _name in _BOOTSTRAPPED_NAMES:
            if _name not in globals() and _name in _resolved:
                globals()[_name] = _resolved[_name]

    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_engine()
        if name not in globals():
            global _BOOTSTRAP_DONE
            _BOOTSTRAP_DONE = False
            _bootstrap_engine()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} after bootstrap"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_CANDIDATE_BRANCH = "candidate"


def _check_fast_forward(dest: str, candidate_branch: str, main_branch: str) -> Optional[str]:
    _bootstrap_engine()
    main_ref = f"refs/remotes/origin/{main_branch}"
    result = _run(
        ["git", "-C", dest, "merge-base", "--is-ancestor", main_ref, "HEAD"]
    )
    if result.returncode == 0:
        return None
    if result.returncode == 1:
        return (
            f"klabauter-promote: predicate 3 (fast-forward) FAILED — "
            f"'{main_branch}' is not an ancestor of '{candidate_branch}' in "
            f"{dest}. Refusing: a non-fast-forward promotion would need a "
            "merge commit, which is never performed here — the "
            "byte-identity property the one-clone topology depends on "
            f"requires '{main_branch}' to already be contained in "
            f"'{candidate_branch}'."
        )
    return (
        f"klabauter-promote: predicate 3 (fast-forward) could not be "
        f"evaluated — `git merge-base --is-ancestor {main_ref} HEAD` in "
        f"{dest} exited {result.returncode} rather than 0 or 1. Refusing "
        "rather than guessing whether the candidate ref fast-forwards onto "
        f"'{main_branch}'.\n" + (result.stderr or "").strip()
    )


_SOURCE_HEAD_STAMP_RE = re.compile(r"\[source-head ([0-9a-f]{7,40})\]\s*$")


def _check_source_head_not_wip(dest: str, percolate_root: str) -> Optional[str]:
    """Predicate 4 — the source commit the candidate was cut from is not a
    WIP commit. Reads the `[source-head <hex>]` stamp off the candidate tip
    subject and resolves it in the percolate root. Fails CLOSED on an
    unparseable stamp or an unresolvable sha.
    """
    _bootstrap_engine()
    prefix = "klabauter-promote: predicate 4 (source-head not WIP)"
    tip = _run(["git", "-C", dest, "log", "-1", "--format=%s", _CANDIDATE_BRANCH])
    if tip.returncode != 0:
        return (
            f"{prefix} could not be evaluated — reading the candidate tip "
            f"subject in {dest} exited {tip.returncode}. Refusing.\n"
            + (tip.stderr or "").strip()
        )
    subject = (tip.stdout or "").strip()
    match = _SOURCE_HEAD_STAMP_RE.search(subject)
    if match is None:
        return (
            f"{prefix} could not be evaluated — the candidate tip subject "
            f"{subject!r} carries no parseable '[source-head <hex>]' stamp. "
            "Refusing."
        )
    sha = match.group(1)
    src = _run(["git", "-C", percolate_root, "log", "-1", "--format=%s", f"{sha}^{{commit}}"])
    if src.returncode != 0:
        return (
            f"{prefix} could not be evaluated — source-head {sha} does not "
            f"resolve in {percolate_root}. Refusing.\n" + (src.stderr or "").strip()
        )
    source_subject = (src.stdout or "").strip()
    if source_subject.startswith("WIP"):
        return (
            f"{prefix} FAILED — the candidate was cut from source-head "
            f"{sha}, a WIP commit ({source_subject!r}). Refusing: commit the "
            "source, republish, and promote that round."
        )
    return None


def _dest_and_marker_refusals(
    dest: str, target: str, percolate_root: str,
) -> Tuple[List[str], bool, Optional[str]]:
    """Predicates 1 and 2. Returns (refusals, dest_ok, branch_head);
    `branch_head` is meaningful only when `dest_ok`."""
    _bootstrap_engine()
    refusals: List[str] = []
    dest_refusal, _has_commits, branch_head = _check_dest_state(dest)
    if dest_refusal:
        refusals.append(f"klabauter-promote: predicate 1 (clean dest) FAILED —\n{dest_refusal}")
    marker_refusal = _check_round_failure_marker(target, percolate_root)
    if marker_refusal:
        refusals.append(f"klabauter-promote: predicate 2 (no round-failure marker) FAILED —\n{marker_refusal}")
    return refusals, not dest_refusal, branch_head


def _wrong_channel_refusal(dest: str, branch_head: Optional[str], candidate_branch: str) -> str:
    return (
        "klabauter-promote: predicate 3 (fast-forward) FAILED — "
        f"{dest}'s checked-out branch is {branch_head!r}, not the "
        f"declared release channel {candidate_branch!r}. Refusing "
        "rather than evaluating fast-forward against the wrong ref."
    )


def _evaluate_bar(
    dest: str, target: str, percolate_root: str, candidate_branch: str, main_branch: str,
) -> List[str]:
    """Returns the refusals (predicates 1-4). Prints nothing."""
    _bootstrap_engine()

    refusals, dest_ok, branch_head = _dest_and_marker_refusals(dest, target, percolate_root)

    if dest_ok:
        if branch_head != candidate_branch:
            refusals.append(_wrong_channel_refusal(dest, branch_head, candidate_branch))
        else:
            ff_refusal = _check_fast_forward(dest, candidate_branch, main_branch)
            if ff_refusal:
                refusals.append(ff_refusal)

    wip_refusal = _check_source_head_not_wip(dest, percolate_root)
    if wip_refusal:
        refusals.append(wip_refusal)

    return refusals


@dataclass(frozen=True)
class PromotionOutcome:
    """Result of `promote_candidate`. `message` is the line the CLI prints
    for this outcome (stdout on a pass, stderr otherwise). `followup_warning`
    is a separate stderr line the CLI also prints."""

    promoted: bool
    refusals: Tuple[str, ...]
    push_failed: bool
    main_branch: Optional[str]
    promoted_sha: Optional[str]
    message: str
    followup_warning: str = ""


def _refused(
    refusals: List[str], target: str, main_branch: Optional[str],
) -> PromotionOutcome:
    return PromotionOutcome(
        promoted=False, refusals=tuple(refusals), push_failed=False,
        main_branch=main_branch, promoted_sha=None,
        message=(
            f"klabauter-promote: refusing to promote '{target}' — "
            f"{len(refusals)} of 4 evidence-bar predicate(s) failed."
        ),
    )


def promote_candidate(
    dest: str, target: str, percolate_root: str, *, confirm: bool,
) -> PromotionOutcome:
    """Evaluate predicates 1-4 on the `candidate` tip and, with `confirm`,
    fast-forward `main`. Prints nothing."""
    _bootstrap_engine()

    main_branch, default_branch_refusal = _resolve_default_branch(dest)
    if default_branch_refusal:
        return PromotionOutcome(
            promoted=False, refusals=(), push_failed=False,
            main_branch=None, promoted_sha=None, message=default_branch_refusal,
        )

    refusals = _evaluate_bar(dest, target, percolate_root, _CANDIDATE_BRANCH, main_branch)
    if refusals:
        return _refused(refusals, target, main_branch)

    if not confirm:
        return PromotionOutcome(
            promoted=False, refusals=(), push_failed=False,
            main_branch=main_branch, promoted_sha=None,
            message=(
                f"klabauter-promote: DRY RUN — predicates 1-4 passed for '{target}'. "
                "Nothing was pushed. "
                "Re-run with --confirm to push '" + _CANDIDATE_BRANCH + "' onto '" + main_branch
                + "' (fast-forward only)."
            ),
        )

    push_refspec = f"{_CANDIDATE_BRANCH}:{main_branch}"
    result = _run(
        # A non-force push already refuses anything but a fast-forward; git
        # push has no --ff-only. `_run` captures, so the refusal is re-printed.
        ["git", "-C", dest, "push", "origin", push_refspec],
    )
    if result.returncode != 0:
        return PromotionOutcome(
            promoted=False, refusals=(), push_failed=True,
            main_branch=main_branch, promoted_sha=None,
            message=(result.stderr or result.stdout or "").strip(),
        )
    # The push moves only the remote ref; a local main left behind reads as an unpromoted
    # tree to anyone checking `git log main` in the mirror. Fast-forward-only, so it never rewrites.
    local = _run(["git", "-C", dest, "fetch", ".", push_refspec])
    warning = ""
    if local.returncode != 0:
        warning = (
            f"klabauter-promote: remote '{main_branch}' promoted; local '{main_branch}' not "
            f"fast-forwarded: {(local.stderr or local.stdout or '').strip()}"
        )
    return PromotionOutcome(
        promoted=True, refusals=(), push_failed=False,
        main_branch=main_branch, promoted_sha=None,
        message=(
            f"klabauter-promote: promoted '{_CANDIDATE_BRANCH}' onto "
            f"'{main_branch}' for target '{target}' (fast-forward push, "
            f"refspec {push_refspec!r})."
        ),
        followup_warning=warning,
    )


def _cmd_promote(args: argparse.Namespace) -> int:
    _bootstrap_engine()
    target = args.target

    percolate_root = _resolve_percolate_root(args.percolate_root)
    if percolate_root is None:
        return _EXIT_USAGE

    dest = _resolve_dest(target, percolate_root)
    if dest is None:
        return _EXIT_USAGE

    outcome = promote_candidate(dest, target, percolate_root, confirm=bool(args.confirm))
    if outcome.main_branch is None:
        print(outcome.message, file=sys.stderr)
        return _EXIT_FAIL
    if outcome.refusals:
        for refusal in outcome.refusals:
            print(refusal, file=sys.stderr)
        print(outcome.message, file=sys.stderr)
        return _EXIT_USAGE
    if outcome.push_failed:
        print(outcome.message, file=sys.stderr)
        return _EXIT_FAIL
    if outcome.followup_warning:
        print(outcome.followup_warning, file=sys.stderr)
    print(outcome.message)
    return _EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="klabauter-promote",
        description=(
            "Promote the 'candidate' release channel onto 'main'. Dry-run "
            "by default — evaluates the evidence bar and pushes nothing "
            "unless --confirm is passed."
        ),
    )
    parser.add_argument("target", help="Single registered percolate target name.")
    parser.add_argument(
        "--percolate-root",
        required=False,
        help="Override PERCOLATE_ROOT (default: percolate-gate.py resolve-root).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Actually push the fast-forward promotion. Omit for a dry-run.",
    )
    parser.set_defaults(func=_cmd_promote)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _bootstrap_engine()
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
