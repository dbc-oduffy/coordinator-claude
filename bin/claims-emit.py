
from __future__ import annotations

import json
import os
import sys

_TRANSPORT_FAIL = 3

_USAGE = (
    "usage: claims-emit --producer <slug> --out <stem> --ran-at <rfc3339> "
    "--pipeline <token>\n"
    "\n"
    "Reads a bare top-level JSON array of claim records from STDIN.\n"
    "--ran-at (RFC3339, timezone-aware) and --pipeline (non-blank, never\n"
    "derived from --producer) are required flags:\n"
    "  --ran-at     — the producer-asserted run timestamp.\n"
    "  --pipeline   — the producer-asserted pipeline.\n"
    "\n"
    "Writes <stem>.claims.json (the array) and <stem>.claims.meta.json\n"
    "(the ran_at/pipeline/producer sidecar) as an atomic pair.\n"
    "\n"
    "Exit codes: 0 both files written; 1 producer-side failure (a claim\n"
    "record fails schema validation, or the write itself fails); 2 invalid\n"
    "invocation (missing/malformed --producer, --out, --ran-at, --pipeline,\n"
    "or a malformed/absent STDIN payload)."
)

_HELP_FLAGS = ("--help", "-h", "help")


def _import_module():
    import lib  # noqa: F401 — bootstraps coordinator/bin/lib onto sys.path
    from cc_invoke import require_dispatch_engine_on_path

    claude_klabauter_root = require_dispatch_engine_on_path()
    import coordinator_core.claims_emit as _mod

    return _mod


def main(argv: list[str]) -> int:
    if any(tok in _HELP_FLAGS for tok in argv):
        print(_USAGE)
        return 0

    producer: str | None = None
    out: str | None = None
    ran_at: str | None = None
    pipeline: str | None = None
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--producer":
            if i + 1 >= len(argv):
                print("claims-emit: --producer requires a value", file=sys.stderr)
                print(_USAGE, file=sys.stderr)
                return 2
            producer = argv[i + 1]
            i += 2
        elif tok == "--out":
            if i + 1 >= len(argv):
                print("claims-emit: --out requires a value", file=sys.stderr)
                print(_USAGE, file=sys.stderr)
                return 2
            out = argv[i + 1]
            i += 2
        elif tok == "--ran-at":
            if i + 1 >= len(argv):
                print("claims-emit: --ran-at requires a value", file=sys.stderr)
                print(_USAGE, file=sys.stderr)
                return 2
            ran_at = argv[i + 1]
            i += 2
        elif tok == "--pipeline":
            if i + 1 >= len(argv):
                print("claims-emit: --pipeline requires a value", file=sys.stderr)
                print(_USAGE, file=sys.stderr)
                return 2
            pipeline = argv[i + 1]
            i += 2
        else:
            print(f"claims-emit: unrecognized argument {tok!r}", file=sys.stderr)
            print(_USAGE, file=sys.stderr)
            return 2

    if not producer or not producer.strip():
        print("claims-emit: --producer <slug> is required", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2

    if not out or not out.strip():
        print("claims-emit: --out <stem> is required", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2

    if not ran_at or not ran_at.strip():
        print("claims-emit: --ran-at <rfc3339> is required", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2

    if not pipeline or not pipeline.strip():
        print("claims-emit: --pipeline <token> is required", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2

    raw_stdin = sys.stdin.read()
    try:
        claims = json.loads(raw_stdin) if raw_stdin.strip() else None
    except json.JSONDecodeError as exc:
        print(f"claims-emit: STDIN is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(claims, list):
        print(
            "claims-emit: STDIN must be a bare top-level JSON array of claim records",
            file=sys.stderr,
        )
        return 2

    try:
        mod = _import_module()
    except RuntimeError as exc:
        print(f"claims-emit: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL
    except ImportError as exc:
        print(f"claims-emit: coordinator_core.claims_emit not importable: {exc}", file=sys.stderr)
        return _TRANSPORT_FAIL

    return mod.emit_claims(
        claims,
        producer=producer,
        ran_at=ran_at,
        pipeline=pipeline,
        out_stem=out,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
