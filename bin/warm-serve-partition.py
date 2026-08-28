"""warm-serve-partition.py — prints the warm-serve partition over the
committed allowlist, computed by `coordinator_core.warm.serve_classifier`.

Purpose: the origin plan's Problem section names three prior counts of "how
many `coordinator/bin` names warm-serve" that were each wrong by more than
fifty names, produced by an uncommitted scratch script each time. This CLI
is the replacement: run it, get the same partition
`coordinator_core.warm.tests.test_serve_classifier`'s live-corpus test
verifies structurally consistent, with nothing to re-derive by hand.

Module-scope shape: only stdlib imports at the top level (`json`, `sys`,
`pathlib`), matching the same import-purity conjunct this CLI's own
classifier enforces on every OTHER allowlisted name — see
`coordinator_core.warm.serve_classifier`'s module docstring, delta 3. The
engine-root `sys.path` bootstrap and the `coordinator_core` import are both
deferred into `main()`, not performed at module scope, for the same reason:
this file is itself named in `warm_entrypoint_allowlist.json` and must not
be the one CLI its own gate would flag.

Usage:
    python3 coordinator/bin/warm-serve-partition.py            # JSON partition report
    python3 coordinator/bin/warm-serve-partition.py --findings # + every underlying Finding

Exit codes:
    0  always -- this is a read-only report, never a pass/fail gate (see
       `coordinator_core/warm/tests/test_every_allowlisted_name_warm_serves.py`,
       chunk C8, for the enforcing guard).

Spec backlink: docs/plans/2026-08-27-every-bin-name-warm-serves-and-a-classifier-says-so.md, chunk C1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    args = argv[1:]
    show_findings = "--findings" in args

    engine_root = Path(__file__).resolve().parents[2]
    if str(engine_root) not in sys.path:
        sys.path.insert(0, str(engine_root))

    from coordinator_core.warm import serve_classifier

    names = serve_classifier.load_allowlist_names()
    verdicts = serve_classifier.classify_population(names)
    report = serve_classifier.partition_report(verdicts)

    output: dict = {"population": "warm_entrypoint_allowlist.json:entrypoints", "partition": report}
    if show_findings:
        output["findings"] = [
            {"path": f.path, "line": f.line, "reason": f.reason, "text": f.text}
            for f in serve_classifier.findings_for(verdicts)
        ]

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
