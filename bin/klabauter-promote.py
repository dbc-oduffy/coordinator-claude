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

REFUSAL BAR — promotion refuses, naming which predicate failed, unless ALL
four hold:
  1. The mirror dest is clean (`percolate-push.py::_check_dest_state`).
  2. No DR-301 round-failure marker is present
     (`percolate-push.py::_round_failure_marker_path`).
  3. The candidate ref fast-forwards onto `main` — `main` is an ancestor of
     `candidate`. A non-fast-forward is a HARD refusal, never a merge
     commit: the byte-identity property that killed the second-clone
     option (docs/reference/klabauter-release-channels.md § "One-clone
     topology") depends on `main` never diverging from what `candidate`
     already contains.
  4. The cross-machine observation predicate (C6). C6 investigated and
     found no existing record of true cross-machine observation on this
     box (see `_check_cross_machine_observed`'s docstring for the
     candidates evaluated and why each did not qualify). It implements
     the weakest honest fallback instead — an elapsed-soak-time floor
     since the candidate ref's tip commit — and this half of the bar is
     declared UNENFORCED in
     docs/reference/klabauter-release-channels.md § "Promotion evidence
     bar". It does not invent an operator-assertion predicate and does
     not pass vacuously.

Reuse, not reimplementation: `_resolve_dest`, `_check_dest_state`,
`_round_failure_marker_path`, `_resolve_default_branch` are imported from
`percolate-push.py` (loaded by path, under a private module name, same
idiom `percolate-full-payload-proof.py::_load_publish_module` already
uses for a sibling hyphenated entrypoint) rather than copied.

Dry-run by default. A bare invocation (`klabauter-promote <target>` with
no `--confirm`) evaluates every predicate, reports pass/fail for each, and
pushes nothing — promotion moves bits onto a PUBLIC remote and is not
reversible for anyone who has already fetched. Only `--confirm` performs
the fast-forward push of `main`.

Negative-spec (do not restore any of this as a "fix"):
  - Does NOT merge, rebase, or otherwise synthesize a new commit onto
    `main` — a non-fast-forward candidate is a hard refusal, never a
    merge commit (predicate 3 above).
  - Does NOT invoke `gh` — promotion is a plain `git push` of a
    fast-forward ref update, not a PR workflow; `percolate-push.py`'s PR
    leg is unrelated to this module.
  - Does NOT treat an absent/unparseable cross-machine record as "not yet
    observed, so allow" — predicate 4 fails CLOSED, same as predicates 1
    and 2 fail closed in `percolate-push.py`.

Usage:
    klabauter-promote.py <target> [--percolate-root <path>] [--confirm]

Exit codes:
    0 — dry-run: predicates 1-3 enforced and predicate 4's soak-floor proxy
        (cross-machine half UNENFORCED) all passed (nothing pushed), or
        `--confirm`: the fast-forward push of `main` succeeded.
    1 — `--confirm` and the push failed (forwarded git exit code), or the
        default-branch resolution needed to name `main` failed.
    2 — usage error (bad argv, target not resolvable), or refused because
        one or more of the four predicates failed.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

_BIN_DIR = Path(__file__).resolve().parent
_PERCOLATE_PUSH_PATH = _BIN_DIR / "percolate-push.py"

_EXIT_OK = 0
_EXIT_FAIL = 1
_EXIT_USAGE = 2


def _load_percolate_push_module():
    """Import `coordinator/bin/percolate-push.py` under a private module
    name — same idiom `percolate-full-payload-proof.py::_load_publish_module`
    already uses for a sibling hyphenated entrypoint — so this import never
    collides with, or is confused for, a `pytest` collection of the real
    module."""
    spec = importlib.util.spec_from_file_location(
        "percolate_push_for_klabauter_promote", _PERCOLATE_PUSH_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_percolate_push_cache: dict = {}


def _percolate_push():
    """Lazily load, and cache, `coordinator/bin/percolate-push.py` — module
    body must stay inert at import, so this replaces the former module-scope
    `_load_percolate_push_module()` call."""
    if "mod" not in _percolate_push_cache:
        _percolate_push_cache["mod"] = _load_percolate_push_module()
    return _percolate_push_cache["mod"]


_CANDIDATE_BRANCH = "candidate"


def _check_fast_forward(dest: str, candidate_branch: str, main_branch: str) -> Optional[str]:
    """Predicate 3 — `main` must be an ancestor of `candidate` (a
    fast-forward). Uses `git merge-base --is-ancestor main candidate`,
    resolved against the dest's local refs for `main`
    (`refs/remotes/origin/<main_branch>`) and the currently checked-out
    `candidate` branch (HEAD, since `_check_dest_state` has already
    confirmed the dest is clean and its `branch_head` is `candidate`).

    Fails CLOSED: a non-zero, non-1 `git merge-base --is-ancestor` exit
    (i.e. neither "is an ancestor" (0) nor "is not an ancestor" (1) but a
    real error — unknown ref, corrupt repo, etc.) refuses rather than
    being read as "not an ancestor" or "is an ancestor" by guesswork.
    """
    main_ref = f"refs/remotes/origin/{main_branch}"
    result = _percolate_push()._run(
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


_CROSS_MACHINE_SOAK_FLOOR_SECONDS = 6 * 60 * 60  # 6 hours — see C6 note below.


def _check_cross_machine_observed(dest: str, target: str) -> Optional[str]:
    """Predicate 4 (C6) — the candidate ref has been observed by at least
    one machine other than the publishing one.

    INVESTIGATION VERDICT (C6, 2026-08-15): no suitable existing record
    was found. Candidates evaluated, Tier 1-3 only:

      - `coordinator/bin/percolate-liveops-preflight.py`
        (`_run` in that module) — the strongest candidate per the C6 row
        and eng-director finding 6. Read and run live: it enumerates
        `repos.*` from THIS machine's own machine-local registry and
        discriminates sessions that resolve the published engine from
        engine-working sessions, all on the invoking box. It is a live,
        unpersisted, single-machine census — it has no notion of another
        machine at all, let alone whether a given git ref has been
        fetched or checked out there. Repo-diversity on one box (project-rag,
        example-cockpit-repo, etc., all consuming the published engine here) is
        NOT machine-diversity, and this function does not relabel it as
        such.
      - A health ledger (`coordinator_core/ops/*health_ledger*`) — tracks
        goal/KR status, not git-ref observation.
      - A machine-local provenance stamp (`coordinator/bin/lib/provenance.py`)
        — stamps generator/record provenance (who/what produced a document),
        not "which machine has this ref".
      - `coordinator_core.machine_resolver.compute_machine()` — resolves
        THIS machine's own identity for local use; there is no registry
        anywhere that records "machine X has observed ref Y".
      - The engine's own resolution banner
        (`_resolve_published_engine`/session-boot banner) — reports what a
        session resolved locally; nothing publishes or aggregates that
        cross-machine.

    So: no record of true cross-machine observation exists on this box.
    Per the C6 row's fallback instruction, this implements the WEAKEST
    HONEST predicate instead — an elapsed-soak-time floor since the
    candidate ref's tip commit was made
    (`_CROSS_MACHINE_SOAK_FLOOR_SECONDS`, 6h, an EM first-guess in the
    same "lick your finger" register as C14's thresholds) — and this half
    of the evidence bar is documented as UNENFORCED in
    docs/reference/klabauter-release-channels.md § "Promotion evidence
    bar", which restates AC4 as three enforced predicates plus one
    declared-unenforced rather than reading stronger than it binds. A
    dated `state/bug-backlog/` entry names what a real implementation
    would need (a registry that records, per candidate ref sha, which
    machines have fetched/checked it out).

    NEGATIVE SPEC: does not accept an operator assertion flag, and fails
    CLOSED (refuses) on any git error rather than guessing the age.
    """
    result = _percolate_push()._run(
        ["git", "-C", dest, "log", "-1", "--format=%cI", _CANDIDATE_BRANCH]
    )
    if result.returncode != 0:
        return (
            "klabauter-promote: predicate 4 (cross-machine observation, "
            "soak-floor proxy — UNENFORCED cross-machine half, see "
            "docs/reference/klabauter-release-channels.md § 'Promotion "
            "evidence bar') could not be evaluated — `git -C "
            f"{dest} log -1 --format=%cI {_CANDIDATE_BRANCH}` exited "
            f"{result.returncode} rather than 0. Refusing rather than "
            "guessing the candidate ref's age.\n" + (result.stderr or "").strip()
        )

    committer_date_raw = (result.stdout or "").strip()
    try:
        committer_date = datetime.fromisoformat(committer_date_raw)
    except ValueError:
        return (
            "klabauter-promote: predicate 4 (cross-machine observation, "
            "soak-floor proxy — UNENFORCED cross-machine half) could not "
            f"parse the candidate ref's committer date {committer_date_raw!r}. "
            "Refusing rather than guessing the candidate ref's age."
        )

    now = datetime.now(committer_date.tzinfo) if committer_date.tzinfo else datetime.utcnow()
    elapsed_seconds = (now - committer_date).total_seconds()
    if elapsed_seconds >= _CROSS_MACHINE_SOAK_FLOOR_SECONDS:
        return None

    floor_hours = _CROSS_MACHINE_SOAK_FLOOR_SECONDS / 3600
    elapsed_hours = elapsed_seconds / 3600
    return (
        "klabauter-promote: predicate 4 (cross-machine observation) FAILED "
        "— no record of true cross-machine observation exists (C6 "
        "investigation found none; see docs/reference/"
        "klabauter-release-channels.md § 'Promotion evidence bar', item 4, "
        "declared UNENFORCED). Checking the weakest honest proxy instead: "
        f"an elapsed-soak-time floor of {floor_hours:g}h since the "
        f"candidate ref's tip commit ({committer_date_raw}). Only "
        f"{elapsed_hours:.2f}h have elapsed — refusing."
    )


def _evaluate_promotion_bar(
    dest: str, target: str, percolate_root: str, candidate_branch: str, main_branch: str
) -> List[str]:
    """Evaluate all four promotion predicates WITHOUT short-circuiting on
    each other's failures — every failing predicate is collected and
    reported, so a `--confirm` invocation (and a dry-run) always names the
    FULL set of what is blocking promotion, not just the first predicate
    hit. Exception: predicate 3 (fast-forward) requires predicate 1 (clean
    dest) to pass first — a dirty dest makes `branch_head` untrustworthy,
    so predicate 3 is skipped rather than evaluated against a possibly-wrong
    ref; it will surface on the next run once predicate 1 is fixed.
    Returns the list of refusal messages (empty when all four pass)."""
    refusals: List[str] = []

    dest_refusal, _has_commits, branch_head = _percolate_push()._check_dest_state(dest)
    if dest_refusal:
        refusals.append(f"klabauter-promote: predicate 1 (clean dest) FAILED —\n{dest_refusal}")

    marker_refusal = _percolate_push()._check_round_failure_marker(target, percolate_root)
    if marker_refusal:
        refusals.append(f"klabauter-promote: predicate 2 (no round-failure marker) FAILED —\n{marker_refusal}")

    # Predicate 3 needs the dest to be clean to trust HEAD == candidate_branch;
    # only evaluate it when predicate 1 passed.
    if not dest_refusal:
        if branch_head != candidate_branch:
            refusals.append(
                "klabauter-promote: predicate 3 (fast-forward) FAILED — "
                f"{dest}'s checked-out branch is {branch_head!r}, not the "
                f"declared release channel {candidate_branch!r}. Refusing "
                "rather than evaluating fast-forward against the wrong ref."
            )
        else:
            ff_refusal = _check_fast_forward(dest, candidate_branch, main_branch)
            if ff_refusal:
                refusals.append(ff_refusal)

    cross_machine_refusal = _check_cross_machine_observed(dest, target)
    if cross_machine_refusal:
        refusals.append(f"klabauter-promote: predicate 4 (cross-machine observation) FAILED —\n{cross_machine_refusal}")

    return refusals


def _cmd_promote(args: argparse.Namespace) -> int:
    target = args.target

    percolate_root = _percolate_push()._resolve_percolate_root(args.percolate_root)
    if percolate_root is None:
        return _EXIT_USAGE

    dest = _percolate_push()._resolve_dest(target, percolate_root)
    if dest is None:
        return _EXIT_USAGE

    main_branch, default_branch_refusal = _percolate_push()._resolve_default_branch(dest)
    if default_branch_refusal:
        print(default_branch_refusal, file=sys.stderr)
        return _EXIT_FAIL

    refusals = _evaluate_promotion_bar(
        dest, target, percolate_root, _CANDIDATE_BRANCH, main_branch
    )
    if refusals:
        for refusal in refusals:
            print(refusal, file=sys.stderr)
        print(
            f"klabauter-promote: refusing to promote '{target}' — "
            f"{len(refusals)} of 4 evidence-bar predicate(s) failed.",
            file=sys.stderr,
        )
        return _EXIT_USAGE

    if not args.confirm:
        print(
            f"klabauter-promote: DRY RUN — predicates 1-3 enforced and "
            "predicate 4's soak-floor proxy (cross-machine half UNENFORCED, "
            "see docs/reference/klabauter-release-channels.md § 'Promotion "
            f"evidence bar') all passed for '{target}'. Nothing was pushed. "
            "Re-run with --confirm to push '" + _CANDIDATE_BRANCH + "' onto '" + main_branch
            + "' (fast-forward only)."
        )
        return _EXIT_OK

    push_refspec = f"{_CANDIDATE_BRANCH}:{main_branch}"
    result = _percolate_push()._run(
        ["git", "-C", dest, "push", "origin", "--ff-only", push_refspec],
        capture_output=False,
    )
    if result.returncode != 0:
        return _EXIT_FAIL

    print(
        f"klabauter-promote: promoted '{_CANDIDATE_BRANCH}' onto "
        f"'{main_branch}' for target '{target}' (fast-forward push, "
        f"refspec {push_refspec!r}). Predicate 4's cross-machine half "
        "remained UNENFORCED (soak-floor proxy only) — see "
        "docs/reference/klabauter-release-channels.md § 'Promotion "
        "evidence bar'."
    )
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
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
