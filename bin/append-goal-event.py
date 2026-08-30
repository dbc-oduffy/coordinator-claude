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

Batch form (amplification-gate fix, 2026-08-19 — see
coordinator_core/tests/test_no_unbatched_per_item_git_spawn.py's exemption
register): --events-file <path> replaces the single-event flags above with
ONE spawn covering N events. `<path>` names a JSON file holding an array of
event objects, each shaped like a single call's varying fields (period,
period_value, text, and the optional passthrough fields — parent_goal_id,
weekly_perceptible [bool], key_results_status [list], goal_id, status).
--repo and --root stay CLI-level flags and apply to every event in the
batch, exactly as they would to N separate single-event invocations sharing
the same repo/root (emit-goal-from-artifact.py's actual call shape — every
goal file in one repo already shared --repo/--root across its per-file
spawns before this fix).

The batch is carried as ONE `events` list param on ONE goal.append dispatch
(one `coordinator_core.invoke` spawn total, not one per event) — the op
itself fans the list out into N in-process append_goal() writes, no further
subprocess spawns anywhere in the chain. See `_main_batch()` below and
coordinator_core/ops/goal_append.py::_goal_append_batch (the engine-side
half this batch form actually depends on — a naive events-file that still
called `_cc_invoke_bare()` once per event would only move the fan-out down
a level, which is exactly what this two-part fix corrects).

Prints a JSON array of {"ok": bool, "result"|"error": ...} objects, one per
input event, in input order — never the bare single-result object the
non-batch path prints. Exit code: 0 only if every event succeeded, 2 if the
dispatch itself failed transport/op-side OR any individual event's outcome
was ok=False, 1 for a malformed --events-file or a malformed response
envelope (mirrors the --key-results-status client-side parse-error
precedent below).
    append-goal-event.sh --events-file <path> [--repo <r>] [--root <p>]

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
        transport/op failure (the engine root unresolvable, coordinator_core.invoke
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

_BOOTSTRAPPED_NAMES = (
    "resolve_checked_repo_root",
    "_op_timeout_ceiling",
    "_resolve_claude_klabauter_root",
    "_timeout_exceeded_message",
)


def _bootstrap_age() -> None:
    """Bind the deferred cc_invoke/repo_identity names this module's own
    functions read as globals, each guarded independently so a caller (a
    test's `mock.patch.object`/plain assignment ahead of `main()`) that has
    already set one of these names on the module is never clobbered by a
    later real import -- only a name still absent from `__dict__` is bound.
    """
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path

    global resolve_checked_repo_root
    if "resolve_checked_repo_root" not in globals():
        from repo_identity import resolve_checked_repo_root as _rcr

        resolve_checked_repo_root = _rcr

    global _op_timeout_ceiling, _resolve_claude_klabauter_root, _timeout_exceeded_message
    if (
        "_op_timeout_ceiling" not in globals()
        or "_resolve_claude_klabauter_root" not in globals()
        or "_timeout_exceeded_message" not in globals()
    ):
        from cc_invoke import (
            _op_timeout_ceiling as _otc,
            _resolve_claude_klabauter_root as _rmr,
            _timeout_exceeded_message as _tem,
        )

        if "_op_timeout_ceiling" not in globals():
            _op_timeout_ceiling = _otc
        if "_resolve_claude_klabauter_root" not in globals():
            _resolve_claude_klabauter_root = _rmr
        if "_timeout_exceeded_message" not in globals():
            _timeout_exceeded_message = _tem


def __getattr__(name: str):
    """PEP 562 hook so a caller reaching for one of `_BOOTSTRAPPED_NAMES`
    before `main()`/`_cc_invoke_bare()` has run -- a test monkeypatching this
    module, or any consumer importing it rather than executing it -- triggers
    `_bootstrap_age()` lazily instead of finding the name absent.

    NEGATIVE SPEC -- `_bootstrap_age()` guards each name independently (no
    single flag/sentinel), so this hook never needs a forced re-run: a name
    missing from `__dict__` is always filled by the plain call above, and a
    name a caller already set (test stub, `mock.patch.object`) is never
    clobbered by it.
    """
    if name in _BOOTSTRAPPED_NAMES:
        _bootstrap_age()
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    _bootstrap_age()

    claude_klabauter_root = _resolve_claude_klabauter_root()

    env = dict(os.environ)
    # BOTH names, same value, for the duration of the rename window. Setting
    # only the retired name gives the child an environment where the variable
    # IS set and every post-C14 reader has stopped reading it, so the failure
    # surfaces rungs downstream of the pin that caused it.
    env["CLAUDE_KLABAUTER_ROOT"] = claude_klabauter_root
    env["COORDINATOR_ENGINE_ROOT"] = claude_klabauter_root
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
        "--events-file",
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
    events_file = ""

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
            elif tok == "--events-file":
                events_file = val
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
        "events_file": events_file,
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


def _main_batch(parsed: dict[str, object]) -> int:
    """Batch entry point for --events-file.

    ONE process (this one) makes exactly ONE goal.append dispatch — i.e. one
    _cc_invoke_bare() call, one coordinator_core.invoke spawn — carrying
    every event in the file as the op's `events` list param (2026-08-19
    amplification-gate fix, second pass: the first pass moved the per-item
    fan-out from emit-goal-from-artifact.py's N `sys.executable` spawns down
    into N _cc_invoke_bare() spawns inside this process, which the
    amplification-gate measurement caught as the SAME defect one level
    lower. `events` batching on the op itself (see
    coordinator_core/ops/goal_append.py::_goal_append_batch) is what
    actually collapses the whole run to one process spawn: this script's
    own subprocess call, period. The op fans out into N in-process
    append_goal() calls on the engine side — zero further subprocess
    spawns — and returns one {"events": [...]} envelope carrying a
    per-event ok/error outcome in input order, which this function
    reprints verbatim to stdout.

    Exit codes: 1 for a malformed --events-file (client-side, mirrors the
    --key-results-status JSON-parse precedent in _build_params) OR a
    malformed response envelope (missing/non-list "events" — an engine-side
    contract violation this script cannot recover from); 2 if the dispatch
    itself failed transport/op-side, OR any individual event's outcome came
    back ok=False; 0 only when every event succeeded.
    """
    events_path = parsed["events_file"]
    try:
        with open(events_path, "r", encoding="utf-8") as fh:
            events = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: --events-file could not be read as JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(events, list):
        print("ERROR: --events-file must contain a JSON array of event objects", file=sys.stderr)
        return 1

    repo_root = _resolve_repo_root()

    params: dict[str, object] = {
        "repo": parsed["repo"] or None,
        "coordinator_root_path": parsed["root"],
        "events": events,
    }
    try:
        envelope = _cc_invoke_bare("goal.append", params, repo_root)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    outcomes = envelope.get("events")
    if not isinstance(outcomes, list):
        print(
            "ERROR: goal.append batch response missing an 'events' array "
            f"(got: {envelope!r})",
            file=sys.stderr,
        )
        return 1

    any_failed = False
    for i, outcome in enumerate(outcomes):
        if not isinstance(outcome, dict) or not outcome.get("ok"):
            print(f"[append-goal-event] batch event {i} failed: {outcome}", file=sys.stderr)
            any_failed = True

    print(json.dumps(outcomes, ensure_ascii=False))
    return 2 if any_failed else 0


def _resolve_repo_root() -> str:
    """Resolve the repo root via the checked resolver (repo_identity).

    READER classification (DR-277 / plan C5): a MISMATCH is advisory only --
    warn to stderr and proceed with the resolved root rather than refuse. An
    UNRESOLVED verdict NEVER refuses (AC4) -- it just means the check could
    not run; the resolved root (or lack thereof) is still honored below.
    """
    _bootstrap_age()

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
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import ensure_engine_on_path

    ensure_engine_on_path(__file__)

    parsed = _parse_args(argv)
    if parsed["events_file"]:
        return _main_batch(parsed)
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
