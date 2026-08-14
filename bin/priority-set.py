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
    --timeout <secs>       Max seconds to wait for the cross-process lock
                           (default: 10.0, matching the op's own default).

Exit codes:
    0 — success; the op's bare result
        ({target_id, target_kind, priority, set_by, source}) printed to
        stdout as JSON.
    1 — client-side argument error (missing --target-id / --target-kind /
        --priority).
    2 — everything else: unresolvable git repo root for the cc_invoke spawn,
        or any cc_invoke transport/op failure (op-level ValueError such as an
        out-of-enum target_kind/priority, schema-validation MutateAbort, lock
        timeout, or malformed envelope).

"""

from __future__ import annotations

import json
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(_SCRIPT_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from cc_invoke import cc_invoke  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402


def _parse_args(argv: list[str]) -> dict[str, str]:
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

    params: dict[str, str] = {
        "target_id": target_id,
        "target_kind": target_kind,
        "priority": priority,
    }
    if set_by:
        params["set_by"] = set_by
    if note:
        params["note"] = note
    if timeout:
        params["timeout"] = timeout

    return params


def main(argv: list[str]) -> int:
    params = _parse_args(argv)

    cwd_repo_root, verdict = resolve_checked_repo_root(explicit_root=None)
    if cwd_repo_root is None:
        # No git root resolved from cwd at all -- distinct from the
        # MISMATCH identity gate below (positive evidence of a DIFFERENT
        # real repo). This is "nowhere to write"; refusing here is not the
        # AC4 "UNRESOLVED never refuses" carve-out being violated.
        print(f"priority-set: cannot resolve git repo root from {os.getcwd()}", file=sys.stderr)
        return 2
    if verdict["verdict"] == "MISMATCH":
        # DR-277 named carve-out: this door dispatches priority.set, which
        # writes a priority-ledger entry into cwd_repo_root's state tree
        # (coordinator_core/ops/priority_set.py) -- a genuine WRITER, not a
        # diagnostic read. Refuse rather than write into a foreign tree.
        # UNRESOLVED never refuses (AC4).
        print(verdict["message"], file=sys.stderr)
        return 2

    try:
        result = cc_invoke("priority.set", params, cwd_repo_root)
    except RuntimeError as exc:
        print(f"priority-set: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
