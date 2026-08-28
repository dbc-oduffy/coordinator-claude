"""refresh-queries.py — CLI trampoline over the query-callout refresh engine.

Thin DoE-side (contract) trampoline over claude-klabauter
coordinator_core.text.refresh_queries, per DR-047 (DoE owns contract/
generator, claude-klabauter owns engine). Walks markdown for query-callout sentinel
blocks, expands or --check-verifies them in-process against
coordinator_core.ops.ceremony.records_query.query_records +
query_record_display.format_records (native port, zero node spawns as of
the 2026-07-22 de-node cutover), and supports --files-scoped runs.
Finish-strangler port of the coordinator/bin/refresh-queries.js CLI surface;
that .js file was itself retired in 480ad8f8 (2026-07-24) and its production
caller now imports this Python module directly.
"""
from __future__ import annotations
# refresh-queries.py — CLI trampoline over claude-klabauter coordinator_core.text.refresh_queries.
#
# Finish-strangler port (BIG_PORT Wave B, 2026-07-17): the node implementation
# (coordinator/bin/refresh-queries.js — 432 lines: CLI arg parse, root
# detection, query-callout spec parsing, fenced-code/inline-backtick-aware
# markdown walk, sentinel-block expansion, --check/--files modes) has been
# fully ported to coordinator_core/text/refresh_queries.py, with a co-located
# pytest (test_refresh_queries.py). This file is now a thin DoE-side
# (contract) trampoline over that claude-klabauter (engine) module, per DR-047 (DoE
# owns contract/generator, claude-klabauter owns engine).
#
# Predecessor: coordinator/bin/refresh-queries.js, whose own logic (arg parse,
# root detection, markdown walk, callout expansion, --check/--files) this
# trampoline + coordinator_core/text/refresh_queries.py fully superseded. It
# was retired in 480ad8f8 (2026-07-24) with the rest of the JS-oracle layer,
# as were coordinator/bin/query-records.js and the two co-located .sh
# regression tests that had targeted it by path. Both blockers this note
# used to record as reasons the .js was "deliberately not deleted" are
# therefore resolved.
#
# Session self-claim (SCOPE-DROP CLOSED 2026-07-27): the oracle used to
# register every written path with the active coordinator session via
# lib/coordinator_session.js's selfClaim(), best-effort. That JS shim is
# retired, and coordinator_core/text/refresh_queries.py now calls the
# in-process Python equivalent, coordinator_core.session.claims.self_claim(),
# for every path it actually writes — see that module's own docstring for
# the mechanism and the best-effort/never-fatal contract.
#
# Shebang note: the SHEBANG line above (line 1) is `python3` — this comment
# previously claimed it was `python`, NOT `python3`, which was stale against
# this file's actual line-1 shebang (corrected 2026-07-22,
# session-family-repoint C4a). `python3` not being on PATH on a clean
# Windows install (only `python`/`py` are) remains a live Windows-portability
# concern for OTHER scripts — see docs/wiki/bash-on-windows-gotchas.md
# § Windows exception — but is not this file's own shebang shape.
#
# Exit-code contract (mirrors coordinator_core.text.refresh_queries.main's
# own docstring — HARDENED per the 2026-07-17 porter-brief addendum, NOT
# byte-identical to the node oracle's conflated exit 1):
#   0 — success (no out-of-sync callouts / --check passed clean, no errors)
#   1 — BUSINESS fail: --check found out-of-sync file(s), OR a callout hit a
#       processing error (bad query type, malformed spec, missing END
#       marker). Matches the oracle's own exit 1 for these business outcomes.
#   2 — CLI usage error (unknown argument). Deliberately NOT reused as exit 1
#       (the oracle conflates the two) — see the ported module's docstring.
#   3 — TRANSPORT failure: the record-query layer is unavailable/broken. Once
#       the node bridge (query-records.js) was retired by the 2026-07-22
#       de-node cutover, reads became an in-process call into
#       coordinator_core.ops.ceremony.records_query, so this code no longer
#       covers "node missing" — what remains is an engine-root resolution or
#       import failure AT THIS trampoline layer (see below), still distinct
#       from both CLI-usage (2) and business (1) failure.
#
# Spec backlink: DoE-claude:pln-bash-to-naked-python-engine-mi-c09292
# Port recipe: DoE scratch/subagent-sandbox/bash-to-python-engine-migration/
# recipe-normalize-snippet.md (byte-parity port discipline)
# Prior node implementation: coordinator/bin/refresh-queries.js — retired in
# 480ad8f8 (2026-07-24); see the Predecessor note above.

import os
import sys


def _import_main():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    from coordinator_core.text.refresh_queries import main as _op_main
    return _op_main


def main(argv: "list[str] | None" = None) -> int:
    try:
        op_main = _import_main()
    except RuntimeError as exc:
        print(f"refresh-queries.py: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 3
    except ImportError as exc:
        print(
            f"refresh-queries.py: coordinator_core.text.refresh_queries not importable: {exc}",
            file=sys.stderr,
        )
        return 3
    return op_main((sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
