# Unix shebang — was generator-owned by gen-launcher-shim.py --ensure-unix; that mode was retired 2026-07-28 (POSIX-EXEC-ASSUMPTION-GUARD, PM ruling) and no longer regenerates this line.
# Spec backlink: DoE-claude DoE-claude:pln-priority-ledger-durable-pm-pri-817d40 § C3
"""priority-set.py — CLI trampoline over claude-klabauter's priority.set op
(coordinator_core/ops/priority_set.py).

Purpose: the `coordinator/bin/` door for `priority.set` — parses CLI flags
into the op's params dict and spawns the op via `coordinator/bin/lib/cc_invoke.py`'s
`cc_invoke()` (same non-bare envelope-unwrap transport `set-goal-kr-status.py`
uses). This is a thin door only: it does NOT reimplement the locked
read-modify-write, the ledger-root resolution, or the schema-validation gate.
Exactly one implementation of the priority-ledger write algorithm exists in
the repo: `coordinator_core.ops.priority_set`.

Usage:
    priority-set.py --target-id <id> --target-kind <kind> --priority <priority>
                     [--set-by <who>] [--note <text>] [--timeout <secs>]

Options:
    --target-id <id>      Identifier of the prioritized target; also the
                           ledger filename stem (required).
    --target-kind <kind>  One of "handoff" | "plan" | "roadmap" | "deliverable"
                           (required; op-side ValueError on any other value).
    --priority <priority> One of "urgent" | "high" | "medium" | "low" | "none"
                           (required). "none" is the EXPLICIT-CLEAR SENTINEL —
                           it writes a real entry, it does not delete the file.
    --set-by <who>         Identifier of the session/agent/person setting this
                           priority. Optional.
    --note <text>          Optional free-form note.
    --timeout <secs>       Max seconds to wait for the cross-process lock.
                           Capped at 2.0 (MAX_TIMEOUT_SECS): a larger value is
                           clamped, with a stderr notice, never honoured. Ask
                           for less, never for more. Omitting the flag leaves
                           the op on its own 10.0 default, which the op's
                           MAX_LOCK_TIMEOUT_SECS clamps to the same 2.0 — so
                           2.0s is the effective wait either way.

Exit codes:
    0 — success; the op's bare result
        ({target_id, target_kind, priority, set_by, source}) printed to
        stdout as JSON.
    1 — client-side argument error (missing --target-id / --target-kind /
        --priority).
    2 — everything else: unresolvable git repo root for the cc_invoke spawn,
        any cc_invoke transport/op failure (op-level ValueError such as an
        out-of-enum target_kind/priority, schema-validation MutateAbort, lock
        timeout, or malformed envelope), or an in-envelope refusal (non-zero
        'exit_code' / non-empty 'error') that cc_invoke's transport-only
        ladder returns as an ordinary bare result rather than raising —
        inspected here via cc_invoke.mutation_refusal_message() (DR-215
        exit_code trap).

"""

from __future__ import annotations

import json
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import cc_invoke, mutation_refusal_message  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402

MAX_TIMEOUT_SECS: float = 2.0
"""Ceiling on --timeout, mirroring coordinator_core.ops.priority_set's
MAX_LOCK_TIMEOUT_SECS (itself matching ipc.CEREMONY_BUDGET_SECS). Restated
rather than imported: this door reaches the op
only across the cc_invoke process boundary and cannot import coordinator_core.
The op-side clamp is the authority and holds regardless of this one; this exists
so an over-ask is answered at the door the caller typed at, not silently
downstream."""


def _clamp_timeout(raw: str) -> float:
    """Parse a --timeout argument and clamp it to MAX_TIMEOUT_SECS.

    Exits 1 on an unparseable value. A request above the ceiling is clamped, not
    refused, with a one-line stderr notice — the caller asked for a lock wait,
    and a shorter wait still does the work they asked for.
    """
    try:
        requested = float(raw)
    except ValueError:
        print(f"ERROR: --timeout must be a number, got {raw!r}", file=sys.stderr)
        sys.exit(1)
    if requested > MAX_TIMEOUT_SECS:
        print(
            f"priority-set: --timeout {requested}s exceeds the {MAX_TIMEOUT_SECS}s "
            f"ceiling; using {MAX_TIMEOUT_SECS}s",
            file=sys.stderr,
        )
        return MAX_TIMEOUT_SECS
    return requested


def _parse_args(argv: list[str]) -> dict[str, object]:
    target_id = ""
    target_kind = ""
    priority = ""
    set_by = ""
    note = ""
    timeout = ""

    i = 0
    n = len(argv)
    while i < n:
        arg = argv[i]
        if arg == "--target-id":
            if i + 1 >= n:
                print("ERROR: --target-id requires an argument", file=sys.stderr)
                sys.exit(1)
            target_id = argv[i + 1]
            i += 2
        elif arg == "--target-kind":
            if i + 1 >= n:
                print("ERROR: --target-kind requires an argument", file=sys.stderr)
                sys.exit(1)
            target_kind = argv[i + 1]
            i += 2
        elif arg == "--priority":
            if i + 1 >= n:
                print("ERROR: --priority requires an argument", file=sys.stderr)
                sys.exit(1)
            priority = argv[i + 1]
            i += 2
        elif arg == "--set-by":
            if i + 1 >= n:
                print("ERROR: --set-by requires an argument", file=sys.stderr)
                sys.exit(1)
            set_by = argv[i + 1]
            i += 2
        elif arg == "--note":
            if i + 1 >= n:
                print("ERROR: --note requires an argument", file=sys.stderr)
                sys.exit(1)
            note = argv[i + 1]
            i += 2
        elif arg == "--timeout":
            if i + 1 >= n:
                print("ERROR: --timeout requires an argument", file=sys.stderr)
                sys.exit(1)
            timeout = argv[i + 1]
            i += 2
        elif arg in ("--help", "-h"):
            sys.stdout.write(__doc__ or "")
            sys.exit(0)
        else:
            print(f"ERROR: Unknown argument: {arg}", file=sys.stderr)
            sys.exit(1)

    if not target_id:
        print("ERROR: --target-id is required", file=sys.stderr)
        sys.exit(1)
    if not target_kind:
        print("ERROR: --target-kind is required", file=sys.stderr)
        sys.exit(1)
    if not priority:
        print("ERROR: --priority is required", file=sys.stderr)
        sys.exit(1)

    params: dict[str, object] = {
        "target_id": target_id,
        "target_kind": target_kind,
        "priority": priority,
    }
    if set_by:
        params["set_by"] = set_by
    if note:
        params["note"] = note
    if timeout:
        params["timeout"] = _clamp_timeout(timeout)

    return params


def main(argv: list[str]) -> int:
    params = _parse_args(argv)

    # DR-277 (accepted): the cwd identity gate that used to sit here refused
    # on MISMATCH against a stale rationale -- `priority.set` is
    # scope="none" (coordinator_core/ops/priority_set.py), so cwd_repo_root
    # never leaves this CLI and the op writes to a CENTRAL ledger root
    # (coordinator_state_root(central=True)), never derived from cwd_repo_root.
    # There was nothing to advise on: the fact checked (does cwd's repo
    # identity match?) has no bearing on where this op writes, so the gate
    # is removed outright rather than demoted to a warning (a warning would
    # be pure nag against DR-277's own "reserve deny() for cases where no
    # correct rewrite exists"). `cwd_repo_root` is still resolved below --
    # it is the spawn cwd for the cc_invoke child, not a write-location check.
    # The verdict is deliberately UNUSED. C18 (state/dispatch-briefs/
    # 2026-08-20-a-refusal-cannot-exit-zero/C18.md, DR-277 EM decision D5)
    # removed this door's cwd identity gate outright rather than demoting it to a
    # warning: `priority.set` is scope="none" (coordinator_core/ops/priority_set.py)
    # and resolves its ledger write centrally via `coordinator_state_root(central=True)`,
    # never from `cwd_repo_root` -- so a MISMATCH here has nothing to advise on and
    # refusing would block a write that was never going to the wrong tree. Do not
    # reintroduce a MISMATCH branch: `tests/test_priority_set_no_cwd_gate.py` pins
    # its absence. The `cwd_repo_root is None` refusal below is unrelated to
    # identity ("nowhere to spawn from") and stays.
    cwd_repo_root, _verdict = resolve_checked_repo_root(explicit_root=None)
    if cwd_repo_root is None:
        # No git root resolved from cwd at all -- "nowhere to spawn from".
        print(f"priority-set: cannot resolve git repo root from {os.getcwd()}", file=sys.stderr)
        return 2

    try:
        result = cc_invoke("priority.set", params, cwd_repo_root)
    except RuntimeError as exc:
        print(f"priority-set: {exc}", file=sys.stderr)
        return 2

    message = mutation_refusal_message("priority.set", result)
    if message is not None:
        print(f"priority-set: {message}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
