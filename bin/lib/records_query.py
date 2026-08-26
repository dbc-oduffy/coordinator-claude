"""records_query.py — native records.query trampoline.

Port of: records-query-facade.sh (DoE 9df969d2, 2026-07-19).

Purpose: exposes query_records(type, where, format, limit) — a drop-in
replacement for the retired cc_records_query bash function — dispatching the
native records.query op via cc_invoke.route_mutation (coordinator/bin/lib/cc_invoke.py).
No local --bare/legacy ladder is inlined here; route_mutation + cc_invoke_bare's
shared machinery in cc_invoke.py is imported, per Wave-1 shared-helper doctrine.

Windows de-bash campaign (2026-07-19), Wave 1 shape-(b) facade repoint: the
ported bash facade (three-state strangler; State-1 fell back to
`node query-records.js`) is DELETED in this change — big-bang cutover, no
bash fallback. legacy_fn RAISES unconditionally; route_mutation's State-1
(seam-absent) path becomes a hard error instead of a legacy dispatch.

Spec backlink: strang-11 C11-12 records.query repoint (retired facade's
original spec); docs/plans/2026-07-19-debash-coordinator-windows.md (Wave 1,
Category B).

Usage (CLI):
    python3 records_query.py <type> <where> [<format>] [<limit>]
        [--sort SORT] [--since SINCE] [--older-than OLDER_THAN]
    python3 records_query.py --unattached [--format FORMAT] [--limit LIMIT]
        [--sort SORT] [--since SINCE] [--older-than OLDER_THAN]
      <type>    record type. The op serves the full queryable record-type set,
                which is engine-owned (claude-klabauter), not client-owned — do not
                treat any list here as exhaustive. Verified working from this
                tree (2026-07-22): handoff, handoff-archived, plan,
                cross-repo-memo, bug, debt, improvement, decision-guide,
                completion, decision, review, lesson, handoff-ledger,
                research-claim.
      <where>   equality-AND filter: "field=value AND field=value"
      <format>  "paths" (default) | "json" | "markdown-list"
                markdown-list is a plain passthrough across all queryable
                types, verified via:
                  python3 records_query.py handoff "" markdown-list 3
                emitting `- [title](path) — status` lines.
      <limit>   optional result cap (int). Omitted/empty -> op default (50).
                `0` means UNLIMITED (no cap) — this is the op's own contract,
                confirmed empirically against the live engine: limit=0 on a
                corpus of 89 `decision` records returns all 89, not zero.
      --unattached
                request the op's native `unattached` union lens instead of a
                single `<type>`/`<where>` query — a union across the
                engine-owned UNATTACHED type set, each record tagged with its
                own source type. Mutually exclusive with `<type>`/`<where>`;
                sort and limit apply ONCE to the assembled union (engine-side),
                never per constituent type.
      --sort    passthrough sort spec, e.g. `-created` or `-loe.tshirt`
                (leading `-` = descending). Engine-owned; this trampoline
                does not reimplement sorting. Composes with --unattached
                (applies once to the assembled union — EM-verified live
                2026-07-22). NOTE: `--sort "-created"` as two space-
                separated argv tokens is rewritten internally to
                `--sort=-created` before argparse sees it — a bare
                space-separated leading-dash value would otherwise be
                misparsed by argparse as an unknown flag ("expected one
                argument"). See `_rewrite_leading_dash_values()`.
      --since   passthrough duration filter, e.g. `90d`, `1d`. Engine-owned
                date filtering; verified live (2026-07-22) on a 46-record
                `handoff` baseline: since=1d -> 17, since=9999d -> 46 (all).
                Composes with --unattached (verified: since=1d narrowed the
                562-record unattached union to 48).
      --older-than
                passthrough duration filter, e.g. `6d`, `9999d` — inverse
                sense of --since. Verified live (2026-07-22) on the same
                46-record baseline: older_than=9999d -> 0, older_than=6d ->
                28.
                ⚠ TRAP: the CLI flag is kebab `--older-than`, but the
                params-dict key sent to the op is snake_case `older_than`
                (argparse gives this automatically via `dest=`). This
                spelling divergence is DELIBERATE, not a bug to "fix" — see
                the silent-drop warning below and query_records()'s
                docstring.

    ⚠ SILENT-DROP TRAP — READ BEFORE ADDING A NEW PASSTHROUGH PARAM:
    the records.query op does NOT error on an unrecognized param key. It
    silently ignores it and returns the FULL UNFILTERED result set, exit 0.
    EM-verified live (2026-07-22) on a 46-record `handoff` baseline: sending
    the CORRECT snake_case `older_than: "9999d"` returned 0 records; sending
    the WRONG kebab `older-than: "9999d"` (indistinguishable in shape from a
    fully-invented bogus key) silently returned all 46 — the op gave no
    signal that the param was ignored. If you add a new filter, VERIFY THE
    EXACT PARAM KEY against the live engine before trusting a documented or
    assumed spelling; a wrong key is silent, not loud.

    Emits to stdout (mirrors the retired facade's State-2 parse contract):
      format=paths: newline-joined paths, 0 lines when empty (no bare blank
                    line a `grep -c .` would miscount as 1).
      format=json:  JSON array, structurally equivalent to the retired
                    query-records.js --format json output.

    Exit codes:
      0  success.
      2  any transport or op-level failure, OR a malformed invocation (e.g.
         neither --unattached nor <type> given) — legible diagnostic on
         stderr. NEVER falls back to a legacy path (native-primary integrity;
         no legacy path exists post-cutover).

Library:
    from records_query import query_records
    query_records(record_type, where, format_="paths", limit=None, *,
                   unattached=False, sort=None, since=None,
                   older_than=None) -> str
    Raises RuntimeError (from cc_invoke/route_mutation) on any failure.
    Raises ValueError if unattached=True is combined with a non-empty
    record_type/where (ambiguous request — fail loud, never silently pick one).
    sort/since/older_than are optional string passthroughs — "" and None both
    mean absent; see the Usage block above and the SILENT-DROP TRAP note for
    why the params-dict key for older_than must stay snake_case.

Negative-spec:
    - Does NOT reimplement route()/route_mutation()/cc_invoke() — imports them
      from cc_invoke.py.
    - Does NOT fall back to `node query-records.js` on any path — that legacy
      leg is retired with the bash facade it lived in.
    - Does NOT spawn a shell — subprocess dispatch is entirely inside
      cc_invoke.py's argv-list subprocess.run() calls.
    - Does NOT treat `limit=0` as falsy/absent — a `if limit:` guard would
      silently truncate an explicit "give me everything" request to the op's
      default cap (50); the guard below is `is not None` specifically to keep
      0 distinguishable from omitted/None.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from cc_invoke import route_mutation  # noqa: E402
from repo_identity import resolve_checked_repo_root  # noqa: E402


def _resolve_repo_root() -> str:
    """Resolve the CALLER's repo root via the checked resolver
    (`repo_identity.resolve_checked_repo_root`) — route_mutation's third
    positional is `repo_root` (the caller's repo), never claude-klabauter's own
    checkout — see cc_invoke.py's route()/route_mutation() docstrings.

    Classification: READER (AC10). On MISMATCH — positive evidence the cwd
    names a DIFFERENT real repo than the harness anchor — warn to stderr and
    proceed with the resolved root anyway; a wrong-repo *read* is misleading,
    not destructive, and DR-277
    (docs/decisions/DR-277-guards-are-advisory-by-default-two-named.md) keeps
    guards advisory by default. UNRESOLVED (no sid, no registry record, no
    git root at all, ...) NEVER refuses either — falls back to os.getcwd()
    exactly as the predecessor's git-failure branch did.
    """
    root, verdict = resolve_checked_repo_root(explicit_root=None)
    if verdict.get("verdict") == "MISMATCH":
        print(verdict.get("message", "records_query: repo-identity MISMATCH"), file=sys.stderr)
    if root:
        return root
    return os.getcwd()


def _no_legacy() -> None:
    """State-1 (seam-absent) handler — big-bang cutover has no legacy path."""
    raise RuntimeError(
        "records_query: legacy bash path retired (Windows de-bash campaign, "
        "big-bang cutover 2026-07-19) — native coordinator_core.invoke "
        "records.query is required; there is no fallback to fall back to. "
        "Verify COORDINATOR_ENGINE_ROOT and the claude-klabauter coordinator_core install."
    )


def query_records(
    record_type: str,
    where: str,
    format_: str = "paths",
    limit: int | None = None,
    *,
    unattached: bool = False,
    sort: str | None = None,
    since: str | None = None,
    older_than: str | None = None,
) -> str:
    """Query records via the native records.query op; return formatted output.

    Mirrors the retired cc_records_query State-2 parse contract exactly:
      format=paths: newline-joined string; empty -> "" (0 lines, not a bare
                    trailing newline `grep -c .` would count as 1).
      format=json:  JSON array string.

    unattached=True requests the op's native `unattached` union lens instead
    of a single-type query: `type`/`where` are omitted from params entirely
    and `{"unattached": True, ...}` is sent instead — the op assembles a union
    across its own engine-owned UNATTACHED type set, tagging each record with
    its source type, and applies sort/limit once to the assembled union (never
    per constituent type). Passing unattached=True together with a non-empty
    record_type/where is ambiguous (which one wins?) and raises ValueError
    rather than silently picking a side.

    sort/since/older_than are optional passthrough filters — this trampoline
    does NOT reimplement sorting or date filtering locally; the engine owns
    that. EM-verified live (2026-07-22) to compose cleanly with
    unattached=True too: sort/since/older_than all apply once to the
    assembled union, same as they do to a single-type query.

    ⚠ SILENT-DROP TRAP (EM-verified 2026-07-22): the op does NOT error on an
    unrecognized param — it silently ignores it and returns the full
    unfiltered result set, exit 0. `older_than` (snake_case) is the correct
    params-dict key; sending kebab `older-than` is indistinguishable from a
    typo'd bogus key — both are silently dropped and the query returns
    EVERYTHING while the caller believes it filtered. Verified: `older_than:
    "9999d"` on a 46-record baseline returned 0 (correct); `older-than:
    "9999d"` returned all 46 (silently ignored). Do not "fix" this key to
    match the CLI's kebab `--older-than` flag spelling — they are
    deliberately different, and the params-dict key must stay snake_case.

    Raises RuntimeError on any transport or op-level failure (propagated
    from route_mutation/cc_invoke) — callers must not swallow this into a
    false-empty result (that would mask a live-but-broken engine).
    """
    if unattached and (record_type or where):
        raise ValueError(
            "query_records: unattached=True is mutually exclusive with a "
            f"non-empty record_type/where (got record_type={record_type!r}, "
            f"where={where!r}) — ambiguous request, refusing to silently "
            "pick one."
        )

    repo_root = _resolve_repo_root()
    params: dict[str, object] = {"format": format_}
    if unattached:
        params["unattached"] = True
    else:
        params["type"] = record_type
        params["where"] = where
    # `is not None`, NOT a truthiness check: the op treats limit=0 as
    # UNLIMITED (verified empirically — a `decision` corpus of 89 records
    # returns all 89 under limit=0, and only 50 under omitted limit). A bare
    # `if limit:` guard drops the falsy 0 from params, silently downgrading an
    # explicit "no cap" request into the op's default 50-record truncation.
    if limit is not None:
        params["limit"] = int(limit)
    # sort/since/older_than are all-string params where "" and None both mean
    # "absent" (unlike limit's 0, there is no falsy-but-meaningful value
    # here) — a truthiness guard is correct and intentional for these three.
    if sort:
        params["sort"] = sort
    if since:
        params["since"] = since
    if older_than:
        # NB: snake_case `older_than` is the params-dict key the op expects.
        # The CLI's user-facing flag is kebab `--older-than` (see main()) —
        # that spelling divergence is deliberate and is exactly the trap
        # documented in this function's docstring above; do not "normalize"
        # this key to kebab to match the flag name.
        params["older_than"] = older_than

    result = route_mutation("records.query", params, repo_root, _no_legacy)

    if format_ == "json":
        records_json = result.get("records", []) if isinstance(result, dict) else []
        return json.dumps(records_json)

    records_paths = result.get("records", "") if isinstance(result, dict) else ""
    if not records_paths:
        return ""
    return records_paths if records_paths.endswith("\n") else records_paths + "\n"


_LEADING_DASH_VALUE_FLAGS = ("--sort", "--since", "--older-than")


def _rewrite_leading_dash_values(argv: list[str]) -> list[str]:
    """Rewrite `--sort -created` (space-separated) into `--sort=-created`
    (equals form) before argparse sees it.

    Descending sort specs are the canonical shape for this op (`-created`,
    `-loe.tshirt` — leading `-` = descending, per this module's Usage
    docstring) and every caller in the dispatch brief invokes them exactly
    this way: `--sort "-created"` as two separate argv tokens. argparse's
    default optional-argument parsing treats any token starting with `-`
    that isn't a recognized negative-number literal as a NEW flag, not a
    value — so `["--sort", "-created"]` fails with "expected one argument"
    even though the caller's intent is unambiguous. The `--flag=value`
    equals form sidesteps this (argparse never re-tokenizes text after the
    `=`), so this rewrite is applied only to the three flags whose
    documented values legitimately start with `-` — it does not touch
    --format/--limit/--unattached or the positionals.
    """
    rewritten: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if (
            tok in _LEADING_DASH_VALUE_FLAGS
            and i + 1 < len(argv)
            and argv[i + 1].startswith("-")
            and argv[i + 1] not in ("-", "--")
        ):
            rewritten.append(f"{tok}={argv[i + 1]}")
            i += 2
            continue
        rewritten.append(tok)
        i += 1
    return rewritten


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="records_query.py")
    # nargs="?" on both positionals (rather than required) so --unattached can
    # omit type/where entirely; validated post-parse below. Every pre-existing
    # positional invocation shape (`<type> <where> [<format>] [<limit>]`) is
    # unaffected — nargs="?" only widens what's *also* accepted.
    parser.add_argument("type", nargs="?", default=None)
    parser.add_argument("where", nargs="?", default=None)
    parser.add_argument("format", nargs="?", default=None)
    parser.add_argument("limit", nargs="?", default=None)
    parser.add_argument(
        "--unattached",
        action="store_true",
        help="Request the native `unattached` union lens instead of a single "
        "<type>/<where> query. Mutually exclusive with <type>/<where>.",
    )
    # --format/--limit flags (distinct dest from the positionals above, to
    # avoid an attribute collision) exist SPECIFICALLY for --unattached
    # invocations: with type/where omitted, the format/limit positionals
    # would otherwise be ambiguous with argparse's left-to-right positional
    # fill (an omitted type/where means the NEXT positional given is
    # consumed as type, not format — there is no way to "skip" a nargs="?"
    # positional from the CLI). The flags let --unattached callers name
    # format/limit unambiguously; the positionals remain the only path for
    # every pre-existing non---unattached invocation, unchanged.
    parser.add_argument("--format", dest="format_flag", default=None)
    parser.add_argument("--limit", dest="limit_flag", default=None)
    # sort/since/older-than: pure passthrough flags for filters the op
    # already understands (EM-verified live 2026-07-22) — no local
    # reimplementation of sorting/date-filtering here. Compose with both
    # positional and --unattached invocations; also verified to compose with
    # each other and with --unattached (sort/since/older_than all apply once
    # to the assembled union, same as a single-type query).
    parser.add_argument("--sort", dest="sort", default=None)
    parser.add_argument("--since", dest="since", default=None)
    # NB: user-facing flag is kebab `--older-than`; argparse gives us
    # `args.older_than` (snake_case) automatically via dest inference below.
    # The params-dict key sent to the op MUST stay snake_case `older_than` —
    # see query_records()'s docstring for the silent-drop trap this guards
    # against (kebab `older-than` in the params dict is silently ignored by
    # the op, returning an unfiltered result set instead of erroring).
    parser.add_argument("--older-than", dest="older_than", default=None)
    effective_argv = list(argv) if argv is not None else sys.argv[1:]
    args = parser.parse_args(_rewrite_leading_dash_values(effective_argv))

    if not args.unattached and args.type is None:
        parser.error("type is required unless --unattached is given")
    if args.unattached and (args.type is not None or args.where is not None):
        parser.error("--unattached is mutually exclusive with <type>/<where>")

    record_type = args.type or ""
    where = args.where or ""
    format_ = args.format_flag if args.format_flag is not None else (args.format or "paths")
    limit_raw = args.limit_flag if args.limit_flag is not None else args.limit

    try:
        # `if limit_raw else None`, not `is not None`: limit_raw is the RAW
        # CLI string here (pre-int()), and an omitted positional/flag already
        # defaults to None — the only falsy-but-present string is "", which
        # only arises from an explicit empty-string arg and should still mean
        # "no limit given". The string "0" is truthy and survives this guard
        # intact, so `... 0` reaches query_records()'s own `is not None`
        # guard as limit=0, preserving the unlimited semantics end to end.
        limit_int = int(limit_raw) if limit_raw else None
        out = query_records(
            record_type,
            where,
            format_,
            limit_int,
            unattached=args.unattached,
            sort=args.sort,
            since=args.since,
            older_than=args.older_than,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary: any failure -> diagnostic + exit 2
        print(f"records_query: records.query invocation failed: {exc}", file=sys.stderr)
        print(
            f"  op=records.query type={record_type} unattached={args.unattached} "
            f"format={format_}",
            file=sys.stderr,
        )
        print(
            "  Native engine broken or unreachable. NOT falling back to legacy "
            "(native-primary integrity).",
            file=sys.stderr,
        )
        return 2

    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
