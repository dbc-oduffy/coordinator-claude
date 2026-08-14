# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
"""
append-goal-event.sh — CLI trampoline over claude-klabauter's goal.append op
(coordinator_core/ops/goal_append.py), dispatched via a local `--bare`
coordinator_core.invoke spawn (same wire shape coordinator-core-invoke.sh's
cc_invoke() uses).

Purpose: DR-210/AC4 finished strangler — goal.append routes through the claude-klabauter
invoke transport unconditionally (spawn-per-call, DR-215). There is no legacy
body left to strangle: this trampoline parses the same CLI contract the
pre-port bash body exposed (period/period-value/text/repo/root + the C11
passthrough flags), builds the goal.append JSON-RPC params object exactly as
the bash body's jq filter did, and spawns
`coordinator_core.invoke goal.append --bare --params-file <f> --repo <root>`.
On any transport/op failure it fails loud (no fallback).

Deliberately does NOT reuse coordinator/bin/lib/cc_invoke.py's own `cc_invoke()`
function: that sibling spawns coordinator_core.invoke WITHOUT `--bare` and
unwraps a full JSON-RPC envelope (`envelope["result"]`), a different wire shape
than the bash oracle's `--bare`/`--params-file` transport this script's own
parity test (append-goal-event-facade.test.sh) exercises. `_resolve_claude_klabauter_root()`,
`_op_timeout_ceiling()`, and `_timeout_exceeded_message()` are reused from that
module (the timeout ceiling and its remedy text, not the wire transport, per
coordinator:code-reviewer P3, 2026-08-08); the spawn+fail-closed ladder below is
otherwise a local, `--bare`-shaped mirror of coordinator-core-invoke.sh's
cc_invoke(), scoped to this one call site.

Usage (extended from the pre-port bash body — zero caller repoints for the
pre-existing flags, AC8; --status is new, see below):
    append-goal-event.sh --period <day|week|repo> --period-value <v>
                          --text <s> [--repo <r>] [--root <p>]
                          [--weekly-perceptible <true|false>] [--parent-goal-id <id>]
                          [--key-results-status <json-array>] [--goal-id <id>]
                          [--status <active|done|dropped|...>]

--status, when supplied, IS forwarded into the dispatched params (as
`status`) and passed straight through to the goal.append op UNVALIDATED here
— the op itself is the single source of truth for the valid-status enum
(coordinator_core/ops/goal_append.py `_valid_statuses()`/`append_goal()`);
this trampoline does not duplicate that enum. Callers computing a
wire-status from an artifact's authored status (e.g. emit-goal-from-artifact.py's
`_map_status()`) pass the already-mapped wire value here.

--goal-id, when supplied, IS forwarded into the dispatched params (as
`goal_id`) — the op honours an explicitly-supplied goal_id, using it verbatim
in preference to its own content-hash derivation (fallback unchanged when
--goal-id is absent/empty). This closes a cross-repo-blocking gap: two
independent producers minting the same logical goal by content-hash alone can
mint two different ids for it; an explicit --goal-id lets them agree on one
identity up front. See coordinator_core/ops/goal_append.py's `append_goal()`
docstring for the full precedence rule and the shape a supplied id must match.

Exit codes — reproduced from EMPIRICAL bash-oracle behavior, not the pre-port
bash header's own stale claim (that header text asserted "1 — bad --period,
missing --text", but the actual bash body never validated those client-side;
they surface as a cc_invoke op-error and rc=2, same as any other transport/op
failure). Faithfully carried over, not "fixed" mid-port:
    0 — success; the native op's bare JSON-RPC result printed to stdout,
        exactly as `json.dumps(result, ensure_ascii=False)` (bare, unindented,
        matching coordinator_core.invoke's --bare success-path serialization).
    1 — a client-side --key-results-status JSON-parse failure (the one arg
        this trampoline itself validates before dispatch, mirroring the bash
        body's `jq -e .` pre-check), OR an unrecognized CLI flag (fixed
        2026-07-25: an unrecognized token used to be silently skipped —
        see the CLI-parsing block below for why that was itself a defect).
    2 — everything else: unresolvable git repo root, OR any cc_invoke
        transport/op failure (CLAUDE_KLABAUTER_ROOT unresolvable, coordinator_core.invoke
        unimportable, op-level ValueError such as missing/invalid --period,
        --period-value, or --text, timeout, malformed envelope).

Spec backlink: pln-strang-01-respin-tc3-emission--bdd397 § C3
Prior backlink: docs/plans/2026-06-22-cockpit-tc-3-coordinator-emission.md § C2
Finish backlink: docs/plans/2026-07-15-bash-to-naked-python-engine-migration.md § T2 AC4
Port backlink: docs/plans/2026-07-16-bash-clean-slate-residual-migration.md
Parity oracle (this port): coordinator/bin/append-goal-event-facade.test.sh
(DoE a2fe06f8, 2026-07-22)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

GENERATES = []  # writes only a NamedTemporaryFile params payload (deleted after the subprocess call) and prints to stdout — the goal.append write itself happens inside the dispatched coordinator_core.invoke subprocess, not this trampoline

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import (  # noqa: E402
    _op_timeout_ceiling,
    _resolve_claude_klabauter_root,
    _timeout_exceeded_message,
    ensure_engine_on_path,
)
from repo_identity import resolve_checked_repo_root  # noqa: E402

ensure_engine_on_path(__file__)


def _cc_invoke_bare(op: str, params: dict[str, object], repo_root: str) -> dict[str, object]:
    """Spawn coordinator_core.invoke in --bare mode and return the bare result dict.

    Local mirror of coordinator-core-invoke.sh's cc_invoke() fail-closed ladder
    (timeout / nonzero exit / empty stdout / non-JSON stdout), shaped for the
    --bare/--params-file wire contract (see module docstring for why this isn't
    cc_invoke.py's own cc_invoke()). --bare means a successful invoke's stdout
    IS the result object directly -- no jsonrpc/id/result envelope to unwrap.

    Raises RuntimeError on any transport/op failure (never returns on failure).

    Timeout ceiling and the TimeoutExpired remedy text are computed via cc_invoke.py's
    own `_op_timeout_ceiling`/`_timeout_exceeded_message` (not re-derived here) — see
    Review note on the except-branch below.
    """
    claude_klabauter_root = _resolve_claude_klabauter_root()

    env = dict(os.environ)
    env["CLAUDE_KLABAUTER_ROOT"] = claude_klabauter_root
    sep = os.pathsep
    existing_pp = env.get("PYTHONPATH", "")
    if f"{sep}{claude_klabauter_root}{sep}" not in f"{sep}{existing_pp}{sep}":
        env["PYTHONPATH"] = f"{claude_klabauter_root}{sep}{existing_pp}" if existing_pp else claude_klabauter_root

    timeout = _op_timeout_ceiling(op, claude_klabauter_root, env)

    params_fh = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="cc-invoke-params-", delete=False, encoding="utf-8"
    )
    try:
        json.dump(params, params_fh)
        params_fh.close()

        try:
            from coordinator_core.win_portability import no_console_creationflags

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "coordinator_core.invoke",
                    op,
                    "--bare",
                    "--params-file",
                    params_fh.name,
                    "--repo",
                    repo_root,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                **no_console_creationflags(),
            )
        except subprocess.TimeoutExpired as exc:
            # Review: coordinator:code-reviewer P3 (2026-08-08) — was a third, divergent
            # hand-built "engine timeout after Ns" message with no ceiling derivation
            # (same defect class AC7 targets, minus the install-blame text). Routed
            # through cc_invoke.py's shared _timeout_exceeded_message instead of
            # duplicating it a third time.
            raise RuntimeError(_timeout_exceeded_message(op, timeout)) from exc
    finally:
        try:
            os.unlink(params_fh.name)
        except OSError:
            pass

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(
            f"cc_invoke: invoke process exited {proc.returncode} (op={op}) — "
            f"op or dispatch error\n  stderr: {stderr}"
        )

    if not proc.stdout:
        raise RuntimeError(f"cc_invoke: empty stdout from invoke (op={op})")

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"cc_invoke: invoke stdout is not valid JSON (op={op}): {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# CLI parsing — mirrors the pre-port bash body's for/case loop shape (value
# flags consume a following token), EXCEPT for the unrecognized-token case:
# the bash body (and this script, until this fix) silently skipped an
# unrecognized token, which let a typo'd or not-yet-wired flag (--status was
# exactly this case — silently dropped for the goal artifact-status gap to
# go undetected) look accepted when it was actually a no-op. An unrecognized
# token is now a loud, non-zero-exit error (see _parse_args below).
# ---------------------------------------------------------------------------
_FLAGS_WITH_VALUE = frozenset(
    {
        "--period",
        "--period-value",
        "--text",
        "--repo",
        "--root",
        "--weekly-perceptible",
        "--parent-goal-id",
        "--key-results-status",
        "--goal-id",
        "--status",
    }
)


def _parse_args(argv: list[str]) -> dict[str, object]:
    period = ""
    period_value = ""
    text = ""
    repo = ""
    root = "."
    weekly_perceptible: str | None = None
    parent_goal_id = ""
    key_results_status: str | None = None
    goal_id_arg = ""
    status_arg: str | None = None

    i = 0
    n = len(argv)
    while i < n:
        tok = argv[i]
        if tok in _FLAGS_WITH_VALUE:
            val = argv[i + 1] if i + 1 < n else ""
            if tok == "--period":
                period = val
            elif tok == "--period-value":
                period_value = val
            elif tok == "--text":
                text = val
            elif tok == "--repo":
                repo = val
            elif tok == "--root":
                root = val
            elif tok == "--weekly-perceptible":
                weekly_perceptible = val
            elif tok == "--parent-goal-id":
                parent_goal_id = val
            elif tok == "--key-results-status":
                key_results_status = val
            elif tok == "--goal-id":
                goal_id_arg = val
            elif tok == "--status":
                status_arg = val
            i += 2
        else:
            print(f"ERROR: unrecognized argument: {tok}", file=sys.stderr)
            sys.exit(1)

    return {
        "period": period,
        "period_value": period_value,
        "text": text,
        "repo": repo,
        "root": root,
        "weekly_perceptible": weekly_perceptible,
        "parent_goal_id": parent_goal_id,
        "key_results_status": key_results_status,
        "goal_id": goal_id_arg,
        "status": status_arg,
    }


def _build_params(parsed: dict[str, object]) -> dict[str, object]:
    """Build the goal.append params dict, matching the bash body's jq filter (D9 nullability)."""
    params: dict[str, object] = {
        "period": parsed["period"],
        "period_value": parsed["period_value"],
        "text": parsed["text"],
        "repo": parsed["repo"] or None,
        "coordinator_root_path": parsed["root"],
        "parent_goal_id": parsed["parent_goal_id"] or None,
        "goal_id": parsed["goal_id"] or None,
        "status": parsed["status"] or None,
    }
    if parsed["weekly_perceptible"] is not None:
        params["weekly_perceptible"] = parsed["weekly_perceptible"] == "true"
    if parsed["key_results_status"] is not None:
        try:
            params["key_results_status"] = json.loads(parsed["key_results_status"])
        except json.JSONDecodeError:
            print("ERROR: --key-results-status must be a valid JSON array", file=sys.stderr)
            sys.exit(1)
    return params


def _resolve_repo_root() -> str:
    """Resolve the repo root via the checked resolver (repo_identity).

    READER classification (DR-277 / plan C5): a MISMATCH is advisory only --
    warn to stderr and proceed with the resolved root rather than refuse. An
    UNRESOLVED verdict NEVER refuses (AC4) -- it just means the check could
    not run; the resolved root (or lack thereof) is still honored below.
    """
    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict["verdict"] == "MISMATCH":
        print(verdict["message"], file=sys.stderr)
    if not root:
        print(
            f"append-goal-event.sh: cannot resolve git repo root from {os.getcwd()}",
            file=sys.stderr,
        )
        sys.exit(2)
    return root


def main(argv: list[str]) -> int:
    parsed = _parse_args(argv)
    params = _build_params(parsed)
    repo_root = _resolve_repo_root()

    try:
        result = _cc_invoke_bare("goal.append", params, repo_root)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
