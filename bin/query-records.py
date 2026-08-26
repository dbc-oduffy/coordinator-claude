"""query-records.py — CLI trampoline over the records.query engine.

Finish-strangler restoration (BIG_PORT Wave, 2026-07-24): the retired
`coordinator/bin/query-records.js` had zero surviving Python entrypoint after
Claude-klabauter's c79e66cd deletion, breaking DoE fleet callers (the fleet-scope
regression this plan's C1/D1 gate exists to prevent — see
`docs/plans/2026-07-24-python-ize-claude-klabauter-bin-oracles-doe-forwards-to.md` § A2).
This trampoline services the DoE-used flag subset only — `--type --where
--since --older-than --format --status --root --list-schemas
--include-archived --include-body --limit` — over the
already-working `coordinator/bin/lib/records_query.py` transport
(`route_mutation` -> `coordinator_core.invoke records.query`, per that
module's own docstring). It deliberately does NOT reimplement the query
grammar, liveness table, or record collection locally — those stay
engine-owned (`coordinator_core/ops/records_query.py`); this file only
translates a CLI flag surface into the op's params dict.

`--include-body` (opt-in, default off): projects `frontmatter['body']` onto
each record — post-frontmatter text for `.md` records, `null` for `.yaml`
whole-file records. The op rejects it (non-zero exit) for the synthetic
types (`handoff-ledger`, `research-claim`), which have no body to project;
this trampoline does not pre-validate that itself, it relies on the op's own
loud rejection (cockpit ask 11).

Two capabilities this trampoline adds that lib/records_query.py's own CLI
does not expose:
  --status  sugar for an `AND status=<value>` where-clause conjunct (the
            spelling DoE fences actually use, e.g.
            `query-records --type debt --status open`).
  --root    overrides the worktree root the op resolves records against
            (query-records.js's `detectRoot`) — lib/records_query.py's
            `query_records()` has no override param (it always resolves
            `repo_root` via `git rev-parse --show-toplevel` from cwd), so
            this file builds the params dict + repo_root directly rather
            than delegating to that function, reusing only its transport
            primitives (`route_mutation`, `_no_legacy`) and its default
            root-resolution fallback (`_resolve_repo_root`).
  --list-schemas
            lists the engine's queryable record types (imports
            `coordinator_core.ops.records_query._TYPE_TO_GLOB` in-process,
            same "no second copy" precedent
            `coordinator_core/ops/ceremony/records_query.py` already
            establishes for importing that same private map — see its own
            module docstring's Negative-spec).

Unported .js flags (`--validate-all`, `--fleet`, `--key`,
`--include-unparseable`, `--show-toplevel`) fail loud with a nonzero exit and
an explicit "not ported — claude-klabauter BIG_PORT" message — NEVER a silent no-op.
(`--all-repos` is `render-handoff-tracker`'s flag, not this oracle's — not
serviced or fail-louded here; confirmed via grep it never appears on a
query-records fence.) Any OTHER flag not in this file's supported set (e.g.
`--unattached`, `--sort` — real query-records.js flags, but not in this
chunk's DoE-used flag list) is left to argparse's own "unrecognized
arguments" rejection, which is already fail-loud by construction — no bespoke
handling needed for flags outside both named lists.

`--limit` was named in that unsupported list until 2026-08-20 while the parser
below has accepted and forwarded it since 2026-08-14 (`632ce6533`). A reader
who trusted this docstring over the code got the wrong answer, and one did:
Claude-klabauter-em told example-cockpit-repo-em on 2026-08-19 that the flag "is not exposed
on our trampoline" and "caps at the op's default 50", filed it, and offered to
build it. Measured through this CLI, `--limit 0` returns 258 lesson rows,
`--limit 7` returns 7, and omitting it returns 50 — the flag was never broken.
A docstring that contradicts the parser twelve lines below it is worse than no
docstring, because it reads as the authority.

Spec backlink: pln-python-ize-claude-klabauter-bin-oracles--218413 § A2
Prior node implementation: coordinator/bin/query-records.js (kept on disk
pending D1's fleet-scope-gated delete pass — not retired by this port).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from records_query import _no_legacy, _resolve_repo_root, route_mutation  # noqa: E402

# Closed list — enumeration is constitutive, not illustrative (per this repo's
# CLAUDE.md carve-out discipline). A flag NOT named here that is also not in
# the supported set below falls through to argparse's own unrecognized-
# argument rejection, which already fails loud.
_UNPORTED_FLAGS = (
    "--validate-all",
    "--fleet",
    "--key",
    "--include-unparseable",
    "--show-toplevel",
)


def _reject_unported_flags(argv: list[str]) -> None:
    """Fail loud on any unported .js flag BEFORE argparse sees it.

    Scanned ahead of argparse (rather than added as argparse options that
    raise inside a callback) so the error message is the exact
    "<flag>: not ported — claude-klabauter BIG_PORT" contract text, not argparse's own
    generic phrasing — and so a bare `--fleet=1` form is caught too (split on
    the first `=`).

    Caveat (Review: code-reviewer R1 P3): the scan is position-independent —
    it also matches a `--where` VALUE that happens to equal an unported flag
    name verbatim (e.g. a filter value literally `--fleet`), misrejecting it
    as the flag rather than a value.
    """
    for tok in argv:
        flag = tok.split("=", 1)[0]
        if flag in _UNPORTED_FLAGS:
            print(f"{flag}: not ported — claude-klabauter BIG_PORT", file=sys.stderr)
            sys.exit(2)


def _list_schemas() -> int:
    """Print the engine's queryable record types, one per line, sorted."""
    from cc_invoke import require_dispatch_engine_on_path

    try:
        claude_klabauter_root = require_dispatch_engine_on_path()
    except RuntimeError as exc:
        print(f"query-records: CLAUDE_KLABAUTER_ROOT resolution failed: {exc}", file=sys.stderr)
        return 3
    try:
        from coordinator_core.ops.records_query import _TYPE_TO_GLOB
    except ImportError as exc:
        print(
            f"query-records: coordinator_core.ops.records_query not importable: {exc}",
            file=sys.stderr,
        )
        return 3
    for type_name in sorted(_TYPE_TO_GLOB):
        print(type_name)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="query-records.py")
    parser.add_argument("--type", dest="type_", default=None)
    parser.add_argument("--where", dest="where", default="")
    parser.add_argument("--since", dest="since", default=None)
    parser.add_argument("--older-than", dest="older_than", default=None)
    parser.add_argument("--format", dest="format_", default="markdown-list")
    parser.add_argument("--status", dest="status", default=None)
    parser.add_argument("--root", dest="root", default=None)
    parser.add_argument("--limit", dest="limit", type=int, default=None)
    parser.add_argument(
        "--list-schemas",
        dest="list_schemas",
        action="store_true",
        help="List the engine's queryable record types and exit.",
    )
    parser.add_argument(
        "--include-archived",
        dest="include_archived",
        action="store_true",
        help=(
            "OPT-IN: also collect the archived counterpart of --type "
            "(handoff/plan/cross-repo-memo). Default off; every existing "
            "invocation without this flag is unaffected."
        ),
    )
    parser.add_argument(
        "--include-body",
        dest="include_body",
        action="store_true",
        help=(
            "OPT-IN: project frontmatter['body'] (post-frontmatter text, "
            "null for .yaml whole-file types) onto each record. Default "
            "off. Rejected by the op for synthetic types (handoff-ledger, "
            "research-claim)."
        ),
    )
    return parser


# `--status` must be a bare token — a value containing " AND "/" and " would
# compose into a second where-clause conjunct (coordinator_core/ops/
# records_query.py::_parse_where splits on `\s+and\s+`), silently narrowing
# the query instead of failing loud. Review: code-reviewer — Finding 1.
_STATUS_TOKEN_RE = re.compile(r"^[\w-]+$")


def _compose_where(where: str, status: str | None) -> str:
    """AND a `--status` value into `where` as a `status=<value>` conjunct.

    `--status` is DoE-fence sugar (e.g. `--type debt --status open`) for what
    the engine's own grammar already expresses via `--where "status=open"`;
    this trampoline does not invent a new op-side param, it composes onto the
    existing `where` string before dispatch.

    Fails loud (rather than silently sanitizing) if `status` is not a bare
    token, since a raw value is interpolated into the composed where-string.
    """
    if not status:
        return where
    if not _STATUS_TOKEN_RE.match(status):
        print(
            f"--status: {status!r} is not a bare token (no whitespace/special "
            "chars allowed) — would corrupt the composed --where expression",
            file=sys.stderr,
        )
        sys.exit(2)
    clause = f"status={status}"
    return f"{where} AND {clause}" if where else clause


def main(argv: list[str] | None = None) -> int:
    effective_argv = list(argv) if argv is not None else sys.argv[1:]
    _reject_unported_flags(effective_argv)

    parser = _build_parser()
    args = parser.parse_args(effective_argv)

    if args.list_schemas:
        return _list_schemas()

    if not args.type_:
        parser.error("--type is required (unless --list-schemas)")

    where = _compose_where(args.where or "", args.status)
    repo_root = os.path.abspath(args.root) if args.root else _resolve_repo_root()

    # Closed param set — mirrors coordinator_core.ops.records_query.py's own
    # _KNOWN_PARAM_KEYS (snake_case only; no kebab aliasing). Only send keys
    # this trampoline's flags actually populate.
    params: dict[str, object] = {
        "type": args.type_,
        "where": where,
        "format": args.format_,
    }
    if args.since:
        params["since"] = args.since
    if args.older_than:
        params["older_than"] = args.older_than
    if args.include_archived:
        params["include_archived"] = True
    if args.include_body:
        params["include_body"] = True
    # `is not None`, NOT truthiness: --limit 0 is the documented way to ask
    # for unlimited results (op default is 50). A bare `if args.limit:`
    # guard would silently drop 0 back to the default. Mirrors
    # lib/records_query.query_records()'s own `is not None` guard, not
    # lib/records_query.main()'s raw-string truthiness pattern.
    if args.limit is not None:
        params["limit"] = args.limit

    try:
        result = route_mutation("records.query", params, repo_root, _no_legacy)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: any failure -> diagnostic + exit 2
        print(f"query-records: records.query invocation failed: {exc}", file=sys.stderr)
        print(
            f"  op=records.query type={args.type_} where={where!r} format={args.format_}",
            file=sys.stderr,
        )
        return 2

    if args.format_ == "json":
        # Trailing newline is deliberate here (unlike lib/records_query.py's
        # `--format json`, which writes json.dumps() verbatim with no
        # trailing newline) — harmless for any JSON-parsing consumer.
        # Review: code-reviewer — Finding 5.
        records_json = result.get("records", []) if isinstance(result, dict) else []
        sys.stdout.write(json.dumps(records_json))
        sys.stdout.write("\n")
        return 0

    records_out = result.get("records", "") if isinstance(result, dict) else ""
    if records_out and not records_out.endswith("\n"):
        records_out += "\n"
    sys.stdout.write(records_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
