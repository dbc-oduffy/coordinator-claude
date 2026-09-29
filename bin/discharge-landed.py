"""discharge-landed — CLI trampoline over the engine-repo's
`handoff.discharge_landed` op (coordinator_core/ops/handoff_discharge_landed.py).

Invoke as `python3 coordinator/bin/discharge-landed.py` — no shebang / exec
bit on this file (new-file zero-budget ratchet: env_shebang; see
`nudge-new-file-zero-budget-ratchets.py`), same convention as the sibling
`handoff-discharge-criteria.py` this file is modelled on.

Purpose: a mise-en-place run (local or cloud) needs a single bareword call
that stamps every landed plan's live batons `shipped` and archives them in
one commit — the DoE-side callers (`execute-plan`, `mise-en-place`,
`workstream-complete`) reach the engine op through this trampoline rather
than importing `coordinator_core` or driving `asyncio.run` by hand. Same
house shape as `handoff-discharge-criteria.py`: argparse, a resolved repo
root, `cc_invoke.route_mutation()`, the JSON-RPC result printed verbatim.

Call shape:

    discharge-landed.py [--plan-id <id> ...] [--repo-root <path>]

`--plan-id` may be repeated; each value is forwarded as one entry of the
op's `plan_ids` list param (a plan doc's repo-relative path or its own
`plan_id:` frontmatter value — either is a legal target-plan identifier,
per the op's own `_plan_identifiers` resolution). Omitted entirely →
`plan_ids: null` is sent, which is the op's own "every plan in the repo at
implemented/landed" scope — the mise-en-place default this CLI exists to
serve; this file does NOT compute that scan itself, the op does.

Repo root resolves from the process cwd via
`coordinator_core.git.repo_root.show_toplevel()` (zero-spawn parent-walk),
not from this file's own `__file__` location — same rationale as
`block-discharge.py::_resolve_ledger_root`: the op's target repo is
whichever one the calling session (a mise-en-place run, local or cloud) is
actually working in, not wherever this CLI happens to be checked out.
`--repo-root` overrides when the caller already knows it.

Exit codes:
    0 — op reported `exit_code: 0` (batch applied or a no-op; `refused`
        entries, if any, are reported inside the printed JSON, not raised —
        a per-baton refusal is expected batch output, not a CLI failure).
        The JSON-RPC result printed to stdout, exactly as
        `json.dumps(result, ensure_ascii=False)`.
    1 — op-level refusal (`RouteMutationError`: `exit_code` 1 setup error,
        or 2 archive-and-commit failure), a transport/engine failure, or an
        unresolvable repo root.
    2 — usage error: a non-list-shaped internal state (unreachable via this
        CLI's own argparse surface; held open for parity with the sibling
        CLI's exit ladder).

Negative-spec:
    - Does NOT re-implement scope resolution, plan-baton joining, the
      landing-sha lookup, the single-flight lock, or the batch commit — all
      of that lives in `handoff_discharge_landed.py`; this file only builds
      params and prints the result.
    - Does NOT loop per plan or per baton — one call, one op invocation,
      matching the op's own one-scan/one-commit design (no CLI-side
      per-item subprocess, per the plan's anti-scope: "No per-baton
      subprocess or per-baton commit anywhere on the path").
    - Does NOT treat a non-empty `refused` list as a raise — `refused` is
      expected batch content (DR-215 note: only the op's own in-envelope
      `exit_code`/`error` distinguishes a real refusal from a reported
      per-item outcome; `route_mutation`'s `failed`-list check does not
      apply here, this op's envelope carries no `failed` key).

Spec backlink: docs/plans/2026-09-28-batch-discharge-landed-batons.md § C3;
op contract: docs/reference/discharge-landed-contract.md.
"""
from __future__ import annotations

import argparse
import sys

PROG = "discharge-landed.py"

_OP = "handoff.discharge_landed"

_BOOTSTRAP_DONE = False


def _bootstrap_cc_invoke() -> None:
    """Bind `cc_invoke` as a module-level global, idempotent.

    Mirrors `handoff-discharge-criteria.py::_bootstrap_cc_invoke` — every
    function below still does its own local `import cc_invoke` at its use
    site (keeps the module body inert on both load routes); this binder
    exists only so a caller reading `cc_invoke` off this module before
    `main()` runs (e.g. a test monkeypatching `_cli.cc_invoke.route_mutation`)
    gets the real module rather than an AttributeError.
    """
    global _BOOTSTRAP_DONE
    if _BOOTSTRAP_DONE:
        return
    global cc_invoke
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke as _cc_invoke

    cc_invoke = _cc_invoke
    _BOOTSTRAP_DONE = True


def __getattr__(name: str):
    if name == "cc_invoke":
        _bootstrap_cc_invoke()
        return globals()["cc_invoke"]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _no_fallback():
    raise RuntimeError(
        f"{PROG}: {_OP} requires the native seam (no bash fallback -- "
        "big-bang cutover); re-run the engine install step or verify "
        "CLAUDE_KLABAUTER_ROOT"
    )


def _resolve_repo_root(explicit_repo_root: str) -> str | None:
    if explicit_repo_root.strip():
        return explicit_repo_root.strip()

    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    if cc_invoke.ensure_engine_on_path(__file__) is None:
        return None
    from coordinator_core.git.repo_root import show_toplevel

    return show_toplevel()


def cmd_discharge_landed(plan_ids: list[str], repo_root_arg: str) -> int:
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    import cc_invoke

    repo_root = _resolve_repo_root(repo_root_arg)
    if not repo_root:
        print(
            f"{PROG}: cannot resolve git repo root from the current "
            "directory — no mutation attempted; pass --repo-root",
            file=sys.stderr,
        )
        return 1

    params: dict = {}
    if plan_ids:
        params["plan_ids"] = plan_ids

    try:
        result = cc_invoke.route_mutation(_OP, params, repo_root, _no_fallback)
    except cc_invoke.RouteMutationError as exc:
        print(f"{PROG}: {_OP} refused — {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(
            f"{PROG}: {_OP} failed — transport/engine failure: {exc}",
            file=sys.stderr,
        )
        return 1

    if not isinstance(result, dict):
        print(
            f"{PROG}: {_OP} returned an unexpected non-dict result: {result!r}",
            file=sys.stderr,
        )
        return 1

    import json

    print(json.dumps(result, ensure_ascii=False))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=PROG)
    p.add_argument(
        "--plan-id",
        dest="plan_ids",
        action="append",
        default=[],
        help="a target plan's repo-relative path or its own `plan_id:` "
        "frontmatter value; may be repeated. Omitted entirely -> the op's "
        "own default scope (every plan in the repo at implemented/landed).",
    )
    p.add_argument(
        "--repo-root",
        dest="repo_root",
        default="",
        help="repo to discharge against; defaults to the git toplevel "
        "walked from the current working directory",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = _build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    return cmd_discharge_landed(args.plan_ids, args.repo_root)


if __name__ == "__main__":
    sys.exit(main())
